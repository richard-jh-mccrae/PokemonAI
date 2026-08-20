"""Sound current-turn terminal proof over the shared transition algebra.

The prover returns a guarded policy only when every represented uncertainty reaches a native win.
Unknown, analytic refresh, timeout, cap, cycle, or turn-boundary states make it abstain.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from time import monotonic

from common.algebra import (
    Actor, Chance, Choice, Deterministic, Refresh, RevealChoice, Terminal, Unknown,
)
from common.api import ActionIdentity
from common.effects import terminal_effects_supported
from common.options import LegalAction
from .state import DecisionState


TERMINAL_WIN = "win"
_RESOURCE_KINDS = frozenset({"attach", "evolve", "play", "retreat", "ability", "skill"})
_ACTION_ORDER = {
    "attack": 0, "ability": 1, "skill": 2, "play": 3,
    "evolve": 4, "attach": 5, "retreat": 6, "end": 99,
}


@dataclass(frozen=True)
class TerminalLimits:
    max_nodes: int
    max_seconds: float
    max_decisions: int = 12


@dataclass(frozen=True)
class ProofStep:
    expected_state_key: str
    legal_menu_digest: str
    chosen: tuple[int, ...]
    action: ActionIdentity
    profile_hash: str
    proof_id: str
    turn: int
    seat: int


@dataclass(frozen=True)
class TerminalProof:
    proof_id: str
    first_action: LegalAction
    continuation: tuple[ProofStep, ...]
    terminal_result: str
    decisions: int
    irreversible_resources: int
    nodes: int
    elapsed_ms: float


@dataclass(frozen=True)
class _Proof:
    path: tuple[tuple[DecisionState, LegalAction], ...]
    decisions: int
    resources: int


def _universal(proofs: tuple[_Proof, ...]) -> _Proof | None:
    if not proofs:
        return None
    policy = {}
    for proof in proofs:
        for state, action in proof.path:
            previous = policy.get(state.plan_key)
            if previous is not None and previous[1].identity != action.identity:
                return None
            policy[state.plan_key] = (state, action)
    ordered = tuple(policy[key] for key in sorted(policy))
    return _Proof(ordered, max(row.decisions for row in proofs),
                  max(row.resources for row in proofs))


def proof_step_failure(step: ProofStep, state: DecisionState, *,
                       profile_hash: str, proof_id: str) -> str | None:
    current = state.obs.get("current") or {}
    guards = (
        (step.profile_hash == profile_hash, "profile_changed"),
        (step.proof_id == proof_id, "proof_changed"),
        (step.turn == int(current.get("turn", 0)), "turn_changed"),
        (step.seat == int(current.get("yourIndex", 0)), "seat_changed"),
        (step.legal_menu_digest == state.legal_menu_digest, "legal_menu_changed"),
        (step.expected_state_key == state.plan_key, "semantic_state_changed"),
    )
    return next((reason for valid, reason in guards if not valid), None)


def proof_lock_step(steps: tuple[ProofStep, ...], state: DecisionState, *,
                    profile_hash: str, proof_id: str) -> tuple[ProofStep | None, str | None]:
    for step in steps:
        if proof_step_failure(
                step, state, profile_hash=profile_hash, proof_id=proof_id) is None:
            return step, None
    if not steps:
        return None, "empty"
    first = steps[0]
    common = (
        (first.profile_hash == profile_hash, "profile_changed"),
        (first.proof_id == proof_id, "proof_changed"),
        (first.turn == int((state.obs.get("current") or {}).get("turn", 0)), "turn_changed"),
        (first.seat == int((state.obs.get("current") or {}).get("yourIndex", 0)), "seat_changed"),
    )
    return None, next((reason for valid, reason in common if not valid),
                      "semantic_state_changed")


class TerminalProver:
    """Find a guaranteed win before Strategies or Bellman rank ordinary actions."""

    def __init__(self, provider, *, limits: TerminalLimits, profile_hash: str = ""):
        self.provider = provider
        self.limits = limits
        self.profile_hash = str(profile_hash)
        self.nodes = 0
        self.elapsed_ms = 0.0
        self.stopped_reason = "not_started"
        self._root_turn = 0
        self._root_key = ""
        self._deadline = 0.0
        self._active: set[str] = set()
        self._failed: set[tuple[str, int]] = set()
        self._depth_cutoff = False
        self._candidates: tuple[str, ...] = ()
        self._proved_action = None
        self._candidate_results: dict[str, str] = {}
        self._uncertainties: list[str] = []
        self._transitions = {}

    def prove(self, state: DecisionState) -> TerminalProof | None:
        started = monotonic()
        self.nodes = 0
        self._active.clear()
        self._transitions.clear()
        self._root_turn = int((state.obs.get("current") or {}).get("turn", 0))
        self._root_key = state.semantic_key
        self._candidates = tuple(str(action.identity) for action in self.provider.actions(state))
        self._proved_action = None
        self._uncertainties.clear()
        self._deadline = started + max(0.0, float(self.limits.max_seconds))
        self._failed.clear()
        self._depth_cutoff = False
        self._candidate_results = {action: "unproved" for action in self._candidates}
        result = self._state(state, max(1, int(self.limits.max_decisions)))
        self.elapsed_ms = (monotonic() - started) * 1000.0
        if result is None or not result.path:
            if self.stopped_reason not in {"node_cap", "time_cap", "unsupported_uncertainty"}:
                self.stopped_reason = "decision_cap" if self._depth_cutoff else "no_proof"
            return None
        first_state, first_action = result.path[0]
        payload = (first_state.plan_key, first_action.identity,
                   tuple((row.plan_key, action.identity) for row, action in result.path[1:]))
        proof_id = hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()[:20]
        continuation = tuple(self._step(row, action, proof_id)
                             for row, action in result.path[1:])
        self.stopped_reason = "proved"
        self._proved_action = str(first_action.identity)
        return TerminalProof(
            proof_id, first_action, continuation, TERMINAL_WIN,
            result.decisions, result.resources, self.nodes, self.elapsed_ms)

    def diagnostics(self, proof: TerminalProof | None) -> dict:
        return {
            "attempted": True,
            "result": "proved" if proof is not None else "abstained",
            "reason": self.stopped_reason,
            "proof_id": proof.proof_id if proof is not None else None,
            "verification": "shared_transition_algebra" if proof is not None else None,
            "lock_event": ("created" if proof is not None and proof.continuation
                           else "terminal_action" if proof is not None else "none"),
            "candidates": tuple({
                "action": action,
                "result": self._candidate_results.get(action, "unproved"),
            } for action in self._candidates),
            "uncertainties": tuple(dict.fromkeys(self._uncertainties)),
            "decisions": proof.decisions if proof is not None else None,
            "irreversible_resources": proof.irreversible_resources if proof is not None else None,
            "nodes": self.nodes,
            "elapsed_ms": self.elapsed_ms,
        }

    def _step(self, state: DecisionState, action: LegalAction, proof_id: str) -> ProofStep:
        current = state.obs.get("current") or {}
        return ProofStep(
            state.plan_key, state.legal_menu_digest, action.selection, action.identity,
            self.profile_hash, proof_id, int(current.get("turn", 0)),
            int(current.get("yourIndex", state.root_seat)))

    def _available(self) -> bool:
        if self.nodes >= max(0, int(self.limits.max_nodes)):
            self.stopped_reason = "node_cap"
            return False
        if monotonic() >= self._deadline:
            self.stopped_reason = "time_cap"
            return False
        return True

    def _same_turn(self, state: DecisionState) -> bool:
        return int((state.obs.get("current") or {}).get("turn", -1)) == self._root_turn

    @staticmethod
    def _order(proof: _Proof):
        canonical = tuple(str(action.identity) for _state, action in proof.path)
        return proof.decisions, proof.resources, canonical

    def _transition(self, state: DecisionState, action: LegalAction):
        key = state.semantic_key, action.identity
        if key not in self._transitions:
            self._transitions[key] = self.provider.transition(state, action)
        return self._transitions[key]

    def _action_order(self, state: DecisionState, action: LegalAction):
        energy_first = 1
        effect = (state.obs.get("select") or {}).get("effect") or {}
        effects = getattr(self.provider, "effects", None)
        clauses = tuple(effects.clauses(effect.get("id"))) if effects is not None \
            and effect.get("id") is not None else ()
        if any(clause.get("target") == "basic_energy" for clause in clauses):
            ids = tuple(int(value) for part in action.identity.parts
                        for value in re.findall(r'"id":(\d+)', part))
            stats = getattr(self.provider, "stats", None)
            if stats is not None and any(
                    getattr(stats.get(card_id), "is_basic_energy", False) for card_id in ids):
                energy_first = 0
        return _ACTION_ORDER.get(action.identity.kind, 50), energy_first, str(action.identity)

    def _state(self, state: DecisionState, remaining_decisions: int) -> _Proof | None:
        if not self._same_turn(state) or not self._available():
            if not self._same_turn(state):
                self.stopped_reason = "turn_boundary"
            return None
        key = state.semantic_key
        memo_key = key, remaining_decisions
        if memo_key in self._failed:
            return None
        if key in self._active:
            self.stopped_reason = "cycle"
            return None
        self.nodes += 1
        self._active.add(key)
        actions = tuple(sorted(self.provider.actions(state),
                               key=lambda action: self._action_order(state, action)))
        actor = self.provider.actor(state)
        if actor is Actor.OURS and remaining_decisions <= 0:
            self._depth_cutoff = bool(actions)
            self._active.remove(key)
            return None
        if actor is Actor.OURS:
            context = int((state.obs.get("select") or {}).get("context", -1))
            attacks = tuple(action for action in actions if action.identity.kind == "attack")
            remainder = tuple(action for action in actions if action.identity.kind != "attack")
            batches = ((attacks, *tuple((action,) for action in remainder))
                       if context == 0 and attacks else (actions,))
            for batch in batches:
                batch_proofs = []
                for action in batch:
                    root_action = key == self._root_key
                    supported = getattr(self.provider, "terminal_action_supported", None)
                    if supported is not None and not supported(state, action):
                        self.stopped_reason = "unsupported_uncertainty"
                        self._uncertainties.append(f"unsupported:{action.identity}")
                        if root_action:
                            self._candidate_results[str(action.identity)] = "unsupported"
                        continue
                    child_budget = remaining_decisions - 1
                    if batch_proofs:
                        child_budget = min(
                            child_budget,
                            min(proof.decisions for proof in batch_proofs) - 1)
                    child = self._node(self._transition(state, action), child_budget)
                    if child is None:
                        if root_action:
                            self._candidate_results[str(action.identity)] = "refuted"
                        continue
                    resources = child.resources + int(action.identity.kind in _RESOURCE_KINDS)
                    proof = _Proof(((state, action), *child.path), child.decisions + 1, resources)
                    batch_proofs.append(proof)
                    if root_action:
                        self._candidate_results[str(action.identity)] = "proved"
                if batch_proofs:
                    self._active.remove(key)
                    return min(batch_proofs, key=self._order)
            self._active.remove(key)
            if self._available():
                self._failed.add(memo_key)
            return None
        proofs = []
        for action in actions:
            root_action = key == self._root_key
            supported = getattr(self.provider, "terminal_action_supported", None)
            if supported is not None and not supported(state, action):
                self.stopped_reason = "unsupported_uncertainty"
                self._uncertainties.append(f"unsupported:{action.identity}")
                if root_action:
                    self._candidate_results[str(action.identity)] = "unsupported"
                self._active.remove(key)
                if self._available():
                    self._failed.add(memo_key)
                return None
                continue
            child = self._node(
                self._transition(state, action),
                remaining_decisions - 1 if actor is Actor.OURS else remaining_decisions)
            if child is None:
                if root_action:
                    self._candidate_results[str(action.identity)] = "refuted"
                self._active.remove(key)
                if self._available():
                    self._failed.add(memo_key)
                return None
                continue
            proofs.append(child)
        self._active.remove(key)
        if not proofs:
            if self._available():
                self._failed.add(memo_key)
            return None
        return _universal(tuple(proofs))

    def _node(self, node, remaining_decisions: int) -> _Proof | None:
        if isinstance(node, Terminal):
            return _Proof((), 0, 0) if node.result == TERMINAL_WIN else None
        if isinstance(node, Deterministic):
            return self._state(node.state, remaining_decisions)
        if isinstance(node, (Unknown, Refresh)):
            self.stopped_reason = "unsupported_uncertainty"
            self._uncertainties.append(type(node).__name__)
            return None
        if isinstance(node, Chance):
            proofs = tuple(self._node(edge.node, remaining_decisions) for edge in node.children
                           if float(edge.probability) > 0.0)
            if not proofs or any(proof is None for proof in proofs):
                return None
            complete = tuple(proof for proof in proofs if proof is not None)
            return _universal(complete)
        if isinstance(node, Choice):
            proofs = tuple(self._node(edge.node, remaining_decisions) for edge in node.children)
            complete = tuple(proof for proof in proofs if proof is not None)
            if node.actor is Actor.OPPONENT and len(complete) != len(proofs):
                return None
            if not complete:
                return None
            if node.actor is Actor.OURS:
                return min(complete, key=self._order)
            return _universal(complete)
        if isinstance(node, RevealChoice):
            by_label = {edge.label: self._node(edge.node, remaining_decisions)
                        for edge in node.choices}
            selected = []
            for outcome in node.outcomes:
                proofs = tuple(by_label[label] for label in outcome.choices
                               if by_label.get(label) is not None)
                if node.actor is Actor.OPPONENT:
                    if len(proofs) != len(outcome.choices):
                        return None
                    selected.extend(proofs)
                elif proofs:
                    selected.append(min(proofs, key=self._order))
                else:
                    return None
            complete = tuple(selected)
            return _universal(complete)
        return None


__all__ = (
    "ProofStep", "TerminalLimits", "TerminalProof", "TerminalProver",
    "proof_lock_step", "proof_step_failure", "terminal_effects_supported",
)
