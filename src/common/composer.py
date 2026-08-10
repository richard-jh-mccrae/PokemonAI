"""Beam search over within-turn action SEQUENCES, scored by end-state differencing::

    score(sequence) = state_value(end board) + EV(terminal action),   EV(end-turn) = 0

ARMED as the MAIN decider (ADR-0131); it ABSTAINS on a tie rather than overrule the sequencer. Rulings:
ADR-0092 / 0121 / 0129 / 0131; blind spots `data/leaf_lab/wave3-rulings.md` §3b; caps whitelisted at
`sound_rules.composer-budget-caps`."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

from common import apply_option as ao
from common import board_choice
from common import board_delta
from common import board_expectation as bx
from common import snapshot_coverage
from common.board_delta import Unmodellable
from common.option_equivalence import (
    AREA_ACTIVE, AREA_BENCH, AREA_HAND, canonical_keys, class_representatives, fan_out,
    option_equivalence, semantic_option_fingerprint,
)
from common.state_model import (
    SEMANTIC_STATE_KEY_SCHEMA, SemanticStateKey, ability_allowance_marker, canonicalize,
    ability_allowance_spent, semantic_state_key,
)
from common.state_value import attack_ev, attack_ev_legs, registry_identity, state_value
from common.strategy.context import _ABILITY, _ATTACH, _ATTACK, _END, _EVOLVE, _PLAY, _RETREAT


#: How many candidate sequences survive each pruning step. **Derived from a TIME budget, not tuned and
#: not derived from acceptance coverage** — the whitelist entry carries the arithmetic.
BEAM_WIDTH = 4

#: Maximum actions BEFORE the terminal action — the deepest commutative block the lattice may reach.
#: Costs nothing over 2 on today's corpus; kept at 4 because that saturation is a seam-coverage fact.
SEQUENCE_DEPTH = 4

#: Beam-admission band, **in prizes**: a candidate within this of the k-th survives. It IS
#: `family_diag.DECIDER_FLOOR`, re-declared because `tools/` must never be a `src/` dependency.
EPSILON = 0.005

FRONTIER_KEY_SCHEMA = 1
DIAGNOSTIC_SCHEMA = 2
REFERENCE_COMPLETE = "COMPLETE"
REFERENCE_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FrontierKey:
    schema: int
    state: SemanticStateKey
    remaining_actions: tuple
    remaining_depth: int
    boundary: tuple


@dataclass(frozen=True)
class ReferenceBudget:
    max_depth: int
    max_transition_evals: int
    max_unique_nodes: int
    wall_ms: int | None = None


@dataclass(frozen=True)
class ReferenceResult:
    status: str
    cap_reason: str = ""
    composer: object = None
    best_semantic_path: tuple = ()
    best_score: float | None = None
    co_best_first_actions: tuple = ()
    generated_by_depth: tuple = ()
    mergeable_by_depth: tuple = ()
    unique_by_depth: tuple = ()
    unmergeable_by_depth: tuple = ()
    merged_by_depth: tuple = ()
    largest_merge_class: int = 0
    block_resets: int = 0
    transition_evals: int = 0
    runtime_ms: float = 0.0
    depth_reached: int = 0
    beam_first_action_recall: bool | None = None
    full_sequence_agreement: bool | None = None
    score_regret: float | None = None

def _bench_max(model) -> int:
    """The engine's own ``benchMax`` for my side, or `board_delta`'s fallback — so the two halves of
    "is this deploy legal" cannot disagree about the cap."""
    from common.board_delta import bench_max
    return bench_max(getattr(model, "source_obs", None) or {}, int(getattr(model, "my_index", 0)))


#: ADR-0095 decision 1's six tiers over StateModel facts. The two Pilot-side KO_SCORE nuances are
#: deliberately NOT reproduced: both are score-conditional, and a canonical ORDER must not be.
TIER_INFORMATIVE = 0     # free AND informative: a draw / search / dig, a Bench fill, an evolve
TIER_COMMIT_FREE = 1     # free but COMMITTING: an Item / Stadium play that reveals nothing
TIER_SUPPORTER = 2       # the one-per-turn Supporter
TIER_COMMITMENT = 3      # the blind / costly commitments: the Energy attach, a Tool equip
TIER_SHUFFLE = 4         # a hand-SHUFFLE Supporter — it nukes the hand, so attach before it
TIER_ENDER = 5           # the turn-ENDER, plus Retreat / End / anything uncharacterised

#: The tag that makes a Supporter a hand-NUKE, so an Energy attach sequences ahead of it.
_SHUFFLE_TAG = "shuffle_hand"


@dataclass(frozen=True)
class Step:
    """``option`` is the dict **as applied** — re-resolved and STRIPPED of the origin stamp.
    ``index`` is the depth-0 menu index the composer would COMMIT if this sequence wins."""

    option: Mapping
    index: int
    tier: int
    fate: str
    #: The instance a deferred-target expansion chose. **Advisory, not a commitment**: the follow-up
    #: select RE-DECIDES on the real board through the same :func:`rank_targets` (ADR-0121 D6).
    chosen_target: tuple = ()
    target_classes: int = 0
    semantic_key: str = ""


@dataclass(frozen=True)
class Candidate:
    """``score = leaf + terminal_ev``, with ``EV(end-turn) = 0``. A non-empty ``coverage_gap`` means
    the seam could not price something — REPORTED, never silently competing with a scored sequence."""

    steps: tuple = ()
    terminal: Mapping | None = None
    terminal_index: int | None = None
    leaf: float = 0.0
    terminal_ev: float = 0.0
    score: float = 0.0
    coverage_gap: str = ""
    truncated: int = 0
    origins: tuple = ()
    origin_indices: tuple = ()
    terminal_semantic_key: str = ""

    @property
    def semantic_path(self) -> tuple:
        path = tuple(step.semantic_key for step in self.steps)
        return path + ((self.terminal_semantic_key,) if self.terminal is not None else ())

    @property
    def first_semantic_actions(self) -> tuple:
        return tuple(sorted({path[0] for path in self.origins if path}))

    @property
    def first_index(self):
        if self.steps:
            return self.steps[0].index
        return self.terminal_index

    def working(self) -> dict:
        return {"leaf": self.leaf, "terminal_ev": self.terminal_ev, "score": self.score,
                "steps": len(self.steps), "truncated": self.truncated,
                "coverage_gap": self.coverage_gap, "origin_count": len(self.origins),
                "first_semantic_actions": list(self.first_semantic_actions)}


@dataclass(frozen=True)
class Bounds:
    """**Both** bounds of one expectation node, plus what the cap dropped. Reported rather than
    reduced: the two are wrong in OPPOSITE directions and the gap is this seam's exposure."""

    index: int
    best: float
    expected: float
    classes: int
    truncated: int
    total_probability: float

    def working(self) -> dict:
        return {"index": self.index, "best": self.best, "expected": self.expected,
                "gap": self.best - self.expected, "classes": self.classes,
                "truncated": self.truncated, "total_probability": self.total_probability}


@dataclass(frozen=True)
class Margin:
    """How close the chosen line's FIRST step came to the beam cutoff. ``in_beam`` is False when it
    survived only on the epsilon band or not at all — the beam-width sizing signal."""

    rank: int | None = None
    k: int = 0
    ranked: int = 0
    in_beam: bool = False
    admitted: bool = False
    always_expand: bool = False
    chosen_delta: float | None = None
    kth_delta: float | None = None
    margin_to_kth: float | None = None
    immediate_rank: int | None = None
    immediate_delta: float | None = None
    admission_rank: int | None = None
    admission_score: float | None = None
    kth_admission_score: float | None = None
    admission_margin: float | None = None
    admission_reason: str = ""
    stop_score: float | None = None
    continuation_estimate: float | None = None
    continuation_gain: float | None = None
    continuation_action: str = ""
    continuation_kind: str = ""
    changed_admission: bool = False

    def working(self) -> dict:
        return {"rank": self.rank, "k": self.k, "ranked": self.ranked, "in_beam": self.in_beam,
                "admitted": self.admitted, "always_expand": self.always_expand,
                "chosen_delta": self.chosen_delta, "kth_delta": self.kth_delta,
                "margin_to_kth": self.margin_to_kth,
                "immediate_rank": self.immediate_rank, "immediate_delta": self.immediate_delta,
                "admission_rank": self.admission_rank, "admission_score": self.admission_score,
                "kth_admission_score": self.kth_admission_score,
                "admission_margin": self.admission_margin,
                "admission_reason": self.admission_reason,
                "stop_score": self.stop_score,
                "continuation_estimate": self.continuation_estimate,
                "continuation_gain": self.continuation_gain,
                "continuation_action": self.continuation_action,
                "continuation_kind": self.continuation_kind,
                "changed_admission": self.changed_admission}


@dataclass(frozen=True)
class ComposerResult:
    """``fanned`` spreads each Option-Equivalence class's 1-ply delta over its members; ``order`` is
    the depth-0 ranking. **``chosen`` is None on a menu the seam can price nothing on** — a REPORT."""

    chosen: Candidate | None = None
    candidates: tuple = ()
    #: The candidates that remain after sound terminal dominance. `candidates` stays complete audit data.
    selection_candidates: tuple = ()
    margin: Margin = field(default_factory=Margin)
    fanned: tuple = ()
    order: tuple = ()
    admission: tuple = ()
    admission_details: dict = field(default_factory=dict)
    changed_admission: frozenset = frozenset()
    admitted: frozenset = frozenset()
    always_expanded: frozenset = frozenset()
    blocks: tuple = ()
    gaps: tuple = ()
    #: Both bounds of every expectation node this run met, newest last; the gap is its exposure.
    bounds: tuple = ()
    stats: dict = field(default_factory=dict)
    #: The root-board value equation.  This deliberately rides with the result rather than being
    #: re-derived by telemetry: downloaded replay analysis must inspect the exact calculation that
    #: ranked this menu.
    root_value: float = 0.0
    root_terms: dict = field(default_factory=dict)

    def margin_for(self, index: int) -> Margin:
        """The margin telemetry for ANY depth-0 option — the acceptance claim is about the option the
        HUMAN ruled, and measuring the composer's own pick would pass by construction."""
        base = _margin_at(self.order, self.always_expanded, self.admitted, self.margin.k, index)
        ordered = sorted(self.admission, key=lambda row: (-row[1], row[0]))
        rank = next((n + 1 for n, (i, _score) in enumerate(ordered) if i == index), None)
        score = next((score for i, score in ordered if i == index), None)
        kth = ordered[self.margin.k - 1][1] if len(ordered) >= self.margin.k else None
        reason = "always-expand" if index in self.always_expanded else \
            "hard-top-k" if rank is not None and rank <= self.margin.k else \
            "epsilon" if index in self.admitted else "cut"
        return replace(base, immediate_rank=base.rank, immediate_delta=base.chosen_delta,
                       admission_rank=rank, admission_score=score, kth_admission_score=kth,
                       admission_margin=None if score is None or kth is None else score - kth,
                       admission_reason=reason,
                       changed_admission=index in self.changed_admission,
                       **self.admission_details.get(index, {}))

    def working(self) -> dict:
        """Complete JSON-safe Composer working for decision telemetry.

        Keep the original result fields intact for callers, but make every input to the sequence
        comparison observable in a Kaggle stderr replay: the root value equation, 1-ply deltas,
        ranked/admitted candidates, expectation bounds, and every generated sequence.
        """
        def candidate(c):
            return {**c.working(), "first_index": c.first_index,
                    "step_indices": [s.index for s in c.steps],
                    "terminal_index": c.terminal_index,
                    "semantic_path": list(c.semantic_path),
                    "origins": [list(path) for path in c.origins],
                    "origin_indices": [list(path) for path in c.origin_indices]}

        return {
            "root": {"value": self.root_value, "terms": self.root_terms},
            "differencing": [[i, delta] for i, delta in enumerate(self.fanned)],
            "ranked": [[i, delta] for i, delta in self.order],
            "admission": [[i, score] for i, score in self.admission],
            "admitted": sorted(self.admitted),
            "always_expanded": sorted(self.always_expanded),
            "blocks": [list(block) for block in self.blocks],
            "bounds": [bound.working() for bound in self.bounds],
            "candidates": [candidate(c) for c in self.candidates],
            "selection_candidates": [candidate(c) for c in self.selection_candidates],
            "gaps": list(self.gaps),
            "stats": self.stats,
        }


def resolve_against(model, option: Mapping) -> dict | None:
    """``option`` re-pointed at the INSTANCES it named, on the board ``model`` actually holds — None
    when one is gone. A stored dict replayed from a permuted position applies a different play."""
    obs = getattr(model, "source_obs", None) or {}
    seat = int(getattr(model, "my_index", 0))
    named = option.get("playerIndex")
    if named is not None and int(named) != seat:
        return dict(option)                      # an option about THEIR board keys nothing of mine
    players = ((obs.get("current") or {}).get("players")) or []
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    out = dict(option)

    hand_serial, body_serial = _origin_serials(option)
    if hand_serial is not None:
        index = _index_of(me.get("hand") or (), hand_serial)
        if index is None:
            return None
        out["index"] = index
    if body_serial is not None:
        for area, zone in ((AREA_ACTIVE, "active"), (AREA_BENCH, "bench")):
            index = _index_of(me.get(zone) or (), body_serial)
            if index is not None:
                out["inPlayArea"], out["inPlayIndex"] = area, index
                break
        else:
            return None
    return out


#: The instance key rides the option DICT, not a parallel map — the dict is what travels through the
#: beam. Private-by-name: a leading underscore is not a legal engine field.
_ORIGIN = "_composer_origin"


def stamp_origin(model, option: Mapping) -> dict:
    """Stamp serial plus card id: fixture serial reuse must not re-point an option to another card."""
    hand_serial, body_serial = ao.option_serials(model, option)
    return {**option, _ORIGIN: (_origin_key(model, option, hand_serial, hand=True),
                                _origin_key(model, option, body_serial, hand=False))}


def _origin_serials(option: Mapping):
    """The stamped instance key, or ``(None, None)``. Unstamped means *"nothing to re-resolve"*,
    never *"resolve it from the current indices"* — that is the silent failure this prevents."""
    origin = option.get(_ORIGIN)
    if not origin:
        return None, None
    return origin[0], origin[1]


def _origin_key(model, option: Mapping, serial, *, hand: bool):
    """``(serial, card id)`` where both facts exist; a bare serial preserves unknown-card handling."""
    if serial is None:
        return None
    obs = getattr(model, "source_obs", None) or {}
    seat = int(getattr(model, "my_index", 0))
    players = ((obs.get("current") or {}).get("players")) or []
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    if hand:
        cards, index = me.get("hand") or (), option.get("index")
    else:
        area = "active" if option.get("inPlayArea") == AREA_ACTIVE else "bench"
        cards, index = me.get(area) or (), option.get("inPlayIndex")
    card = cards[index] if isinstance(index, int) and 0 <= index < len(cards) else None
    card_id = card.get("id") if isinstance(card, Mapping) else None
    return (serial, card_id) if card_id is not None else serial


def _index_of(cards, key):
    serial, card_id = key if isinstance(key, tuple) else (key, None)
    for i, card in enumerate(cards or ()):
        if card and card.get("serial") == serial and (card_id is None or card.get("id") == card_id):
            return i
    return None


def strip_origin(option: Mapping) -> dict:
    """Separate from :func:`resolve_against` so the boundary is not a matter of call order."""
    return {k: v for k, v in option.items() if k != _ORIGIN}


def _still_legal(model, option: Mapping) -> bool:
    """Would the engine still offer this option on ``model``'s board? Only the limits an EARLIER STEP
    of this sequence can spend; a first-turn evolve is safe by construction (`docs/rules.md` §3/§4)."""
    kind = ao.transition_kind(option)
    if kind == _ABILITY:
        body = _ability_body(model, option)
        if body is None:
            return False
        clauses = board_delta.card_clauses(model.combat, body.card_id)
        allowances = {clause.get("allowance") for clause in clauses
                      if clause.get("allowance") is not None}
        if len(allowances) == 1:
            marker = ability_allowance_marker(
                allowances.pop(), card_id=body.card_id, body_serial=body.body.get("serial"))
            return not ability_allowance_spent(model, marker)
        return True
    if kind == _RETREAT:
        return not model.retreated
    card = _option_card_stat(model, option)
    if kind == _ATTACH:
        if card is None:
            return False
        if getattr(card, "is_tool", False):
            body = _target_body(model, option)
            return body is not None and not body.tool_ids
        return not model.energy_attached
    if kind == _EVOLVE:
        body = _target_body(model, option)
        return body is not None and not body.new_in_play
    if kind == _PLAY:
        if card is None:
            return False
        if getattr(card, "is_supporter", False):
            return not model.supporter_played
        if getattr(card, "is_stadium", False):
            return not model.stadium_played and model.stadium_id != card.cardId
        if getattr(card, "is_pokemon", False) and not getattr(card, "evolvesFrom", None):
            return len(model.mine.bench) < _bench_max(model)
        return True                              # an Item — no per-turn allowance and no capacity
    return True                                  # terminal kinds and anything the seam refuses


def _option_card_stat(model, option: Mapping):
    """FROM HAND: every §3 allowance is keyed on what is PLAYED, not on what it lands on."""
    obs = getattr(model, "source_obs", None) or {}
    seat = int(getattr(model, "my_index", 0))
    players = ((obs.get("current") or {}).get("players")) or []
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    area, index = option.get("area"), option.get("index")
    if area not in (None, AREA_HAND) or not isinstance(index, int) or index < 0:
        return None
    hand = me.get("hand") or ()
    if index >= len(hand) or not hand[index]:
        return None
    return model.card_stat(hand[index].get("id"))


def _target_body(model, option: Mapping):
    area, index = option.get("inPlayArea"), option.get("inPlayIndex")
    if not isinstance(index, int) or index < 0:
        return None
    if area == AREA_ACTIVE:
        active = model.mine.active
        return active if index == 0 else None
    if area == AREA_BENCH:
        bench = model.mine.bench
        return bench[index] if index < len(bench) else None
    return None


def _ability_body(model, option: Mapping):
    area, index = option.get("area"), option.get("index")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        return None
    if area == AREA_ACTIVE:
        return model.mine.active if index == 0 else None
    if area == AREA_BENCH:
        return model.mine.bench[index] if index < len(model.mine.bench) else None
    return None


#: `trigger` -> the option KIND that clause fires with. `test_composer.py` asserts this covers exactly
#: `snapshot_coverage.CLAUSE_SELECTORS["trigger"]`, so a new value cannot fall through to "no ride".
_TRIGGER_KIND = {"on_attach": _ATTACH, "on_evolve": _EVOLVE, "on_bench_play": _PLAY,
                 "on_attack": _ATTACK}


def _reveal_rides(model, option: Mapping) -> bool:
    """Does a revealing clause actually FIRE here? Narrower than the footprint's *"can this CARD
    reveal at all?"*. Fail closed: an untriggered clause rides a `_PLAY` and no other kind."""
    from common.board_delta import card_clauses
    kind = ao.transition_kind(option)
    card = _option_card_stat(model, option)
    if card is None:
        return kind == _PLAY                       # unreadable: keep the conservative `_PLAY` answer
    for clause in card_clauses(getattr(model, "combat", None), card.cardId) or ():
        values = set(snapshot_coverage.clause_values(clause))
        if not (values & snapshot_coverage.REVEALING_CLAUSES):
            continue
        trigger = clause.get("trigger")
        if trigger is not None:
            if _TRIGGER_KIND.get(trigger) == kind:
                return True
        elif kind == _PLAY:
            return True
    return False


def canonical_tier(model, option: Mapping, footprint=None) -> int:
    """This option's information-before-commitment TIER (ADR-0095 decision 1). TOTAL over the menu
    even though a revealing option can never join a block, so no key falls through to menu position."""
    kind = ao.transition_kind(option)
    if kind in (_ATTACK, _END, _RETREAT):
        return TIER_ENDER
    card = _option_card_stat(model, option)
    # A hand shuffle hides the resulting cards rather than revealing a usable choice.  It therefore
    # must retain the post-attach tier even though its draw clause is marked as a potential revealer.
    if kind == _PLAY and card is not None and getattr(card, "is_supporter", False) \
            and _shuffles_hand(model, card):
        return TIER_SHUFFLE
    fp = footprint if footprint is not None else ao.option_footprint(model, option)
    if fp.reveals_information:
        return TIER_INFORMATIVE
    if kind == _EVOLVE:
        return TIER_INFORMATIVE                  # "evolve a benched Pokemon" rides the free band
    if kind == _ATTACH:
        return TIER_COMMITMENT                   # Energy AND Tool: a Tool is an `_ATTACH` (tier 3)
    if kind == _PLAY and card is not None:
        if getattr(card, "is_supporter", False):
            return TIER_SUPPORTER
        if getattr(card, "is_pokemon", False):
            return TIER_INFORMATIVE              # a Bench fill is free and reveals a better target
        return TIER_COMMIT_FREE                  # an Item / a Stadium: free but committing
    return TIER_ENDER                            # uncharacterised: last, fail closed


def _shuffles_hand(model, card) -> bool:
    functions = getattr(getattr(model, "combat", None), "functions", None)
    if functions is None:
        return False
    try:
        return _SHUFFLE_TAG in (functions.tags(card.cardId) or ())
    except Exception:                            # noqa: BLE001 — an unknown card is not a shuffler
        return False


def canonical_key(model, option: Mapping, index: int, canon: str, footprint=None) -> tuple:
    """``canon`` is the ADR-0103 fingerprint, so permuting the menu invents no new keys."""
    return (canonical_tier(model, option, footprint), canon, index)


def commutative_blocks(model, options: Sequence[Mapping], indices=None) -> tuple:
    """For TELEMETRY — the beam asks :func:`_admissible_in_block` instead. Fail closed."""
    prints = {i: ao.option_footprint(model, options[i])
              for i in (range(len(options)) if indices is None else indices)
              if not ao.is_terminal(options[i])}
    blocks: list[list[int]] = []
    for i in sorted(prints):
        for block in blocks:
            if all(ao.footprints_commute(prints[i], prints[j]) for j in block):
                block.append(i)
                break
        else:
            blocks.append([i])
    return tuple(tuple(b) for b in blocks if len(b) > 1)


def subset_lattice(members: Sequence) -> tuple:
    """Every SUBSET of ``members`` in one canonical order — ``2**n`` tuples, never the
    ``sum(n!/(n-k)!)`` ordered prefixes. The same rule :func:`_admissible_in_block` applies."""
    out = [()]
    for member in members:
        out = out + [prefix + (member,) for prefix in out]
    return tuple(out)


def _admissible_in_block(key, block_keys) -> bool:
    """Only when ``key`` sorts strictly after every member — the rule that turns the beam's tree into
    the SUBSET lattice, generating each subset exactly once instead of merging duplicates after."""
    return all(key > other for other in block_keys)


def terminal_ev(model, option: Mapping) -> tuple:
    """``(EV in prizes, AttackEV or None, coverage-gap reason)`` for a TERMINAL option. ⚠️ Reads
    `AttackEV.total`, never the working-dict sum, which is FROZEN ASYMMETRIC. No leg = a GAP, not 0."""
    kind = ao.transition_kind(option)
    if kind == _END:
        return 0.0, None, ""
    if kind != _ATTACK:
        return 0.0, None, f"option kind {kind} is terminal but is neither attack nor end-turn"
    attack_id = option.get("attackId")
    for leg in attack_ev_legs(model):
        if leg.attack_id == attack_id:
            ev = attack_ev(**leg.kwargs)
            return float(ev.total), ev, ""
    return 0.0, None, (
        f"attack {attack_id!r} has no `attack_ev_legs` leg on this board — its EV is UNKNOWN, and "
        f"pricing it 0.0 would rank a real attack below every scored line")


def continuation_ev(model) -> float:
    """The best terminal action still REACHABLE, in prizes — the second summand of a CUT line
    (ADR-0129). ⚠️ Answers from the BOARD, not the menu, so :func:`_stop_here` must not inherit it."""
    return max((float(attack_ev(**leg.kwargs).total) for leg in attack_ev_legs(model)), default=0.0)


@dataclass(frozen=True)
class ScoredTarget:
    """One instance of a deferred target, scored on the board it produces; ``rank`` is 1-based."""

    rank: int
    leaf: float
    model: object
    fingerprint: tuple = ()
    probability: float = 0.0


@dataclass(frozen=True)
class TargetChoice:
    """``leaf`` is the score that ORDERS — the MAX over the enumeration — while ``expected`` is the
    availability-weighted mean carried alongside as the reported lower bound."""

    scored: tuple = ()
    leaf: float = 0.0
    expected: float = 0.0
    truncated: int = 0
    total_probability: float = 0.0

    @property
    def best(self) -> ScoredTarget | None:
        return self.scored[0] if self.scored else None

    @property
    def runner_up(self) -> float | None:
        return self.scored[1].leaf if len(self.scored) > 1 else None

    def working(self) -> dict:
        return {"classes": len(self.scored), "leaf": self.leaf, "expected": self.expected,
                "gap": self.leaf - self.expected, "runner_up": self.runner_up,
                "truncated": self.truncated, "total_probability": self.total_probability}


def rank_targets(model, expectation) -> TargetChoice:
    """**THE evaluator for a deferred target — one entry point, BOTH sites** (ADR-0121 decision 6):
    the MAIN menu and the follow-up select, which REPLANS rather than replaying a commitment."""
    scored = sorted(
        (ScoredTarget(rank=0, leaf=float(state_value(c.model)), model=c.model,
                      fingerprint=tuple(c.fingerprint or ()), probability=float(c.probability))
         for c in expectation.classes),
        key=lambda s: (-s.leaf, s.fingerprint))
    ranked = tuple(ScoredTarget(rank=n + 1, leaf=s.leaf, model=s.model, fingerprint=s.fingerprint,
                                probability=s.probability) for n, s in enumerate(scored))
    mass = float(expectation.total_probability)
    return TargetChoice(
        scored=ranked,
        leaf=ranked[0].leaf if ranked else 0.0,
        expected=(sum(s.probability * s.leaf for s in ranked) / mass) if mass > 0.0 else 0.0,
        truncated=int(expectation.truncated), total_probability=mass)


def choose_target(model, option: Mapping, *, seat_index=None, cap=None, ranker=None):
    """The MAIN-site front door onto :func:`rank_targets`; None when the space is unmodellable."""
    from common import board_choice
    kwargs = {} if cap is None else {"cap": cap}
    try:
        expectation = board_choice.deferred_target(
            model, dict(option), seat_index=seat_index, ranker=ranker, **kwargs)
    except Unmodellable:
        return None
    return rank_targets(model, expectation)


def selection_key(model, candidate: Candidate) -> tuple:
    """The ONE ordering key for choosing among candidates: score, then touched-card Worth, then a
    card-id sort and the menu index. Never falls through to raw generation order."""
    worth, card_id = 0.0, -1
    step = candidate.steps[0] if candidate.steps else None
    option = step.option if step is not None else candidate.terminal
    if option is not None:
        stat = _option_card_stat(model, option)
        if stat is not None:
            card_id = int(getattr(stat, "cardId", -1) or -1)
            worth = float(model.mine.role_worth(stat.cardId))
    index = candidate.first_index
    semantic_path = candidate.semantic_path or ("\uffff",)
    return (bool(candidate.coverage_gap), -round(candidate.score, ao.SCORE_PLACES), -worth, card_id,
            semantic_path,
            index if index is not None else 1 << 30)


def _attack_leg(model, candidate: Candidate):
    """The active-target terminal leg for this candidate, or None outside the attack seam."""
    terminal = candidate.terminal or {}
    if ao.transition_kind(terminal) != _ATTACK:
        return None
    attack_id = terminal.get("attackId")
    return next((leg for leg in attack_ev_legs(model) if leg.attack_id == attack_id), None)


def _direct_active_ko(model, candidate: Candidate) -> bool:
    """A direct, deterministic Knock Out of the current Active from the terminal extractor."""
    leg = _attack_leg(model, candidate)
    if candidate.steps or candidate.coverage_gap or leg is None:
        return False
    values = leg.kwargs
    hp = float(values.get("target_hp") or 0.0)
    return bool(hp > 0.0 and float(values.get("ko_probability") or 0.0) >= 1.0
                and float(values.get("damage") or 0.0) >= hp)


def _survives_recoil(model, candidate: Candidate) -> bool:
    """A recoil Knock Out is a draw, so it cannot establish a direct match win."""
    active = getattr(getattr(model, "mine", None), "active", None)
    leg = _attack_leg(model, candidate)
    recoil = getattr(getattr(model, "combat", None), "rider_recoil", None)
    if active is None or leg is None or not callable(recoil):
        return False
    return float(recoil(leg.attack_id)) < float(getattr(active, "hp_remaining", 0) or 0)


def _direct_prize_win(model, candidate: Candidate) -> bool:
    """A sound terminal winner: deterministic active KO, last prizes, and no recoil draw."""
    leg = _attack_leg(model, candidate)
    if not (_direct_active_ko(model, candidate) and leg is not None and _survives_recoil(model, candidate)):
        return False
    need = int(getattr(getattr(model, "prize_race", None), "my_prizes_remaining", 0) or 0)
    return bool(need > 0 and float(leg.kwargs.get("target_prizes") or 0.0) >= need)


def _direct_terminal_attack(candidate: Candidate) -> bool:
    """A root-menu attack, so terminal dominance does not overrule a setup line."""
    return bool(not candidate.steps and not candidate.coverage_gap
                and ao.transition_kind(candidate.terminal or {}) == _ATTACK)


def _one_prize_active_ko(model, candidate: Candidate) -> bool:
    """A direct active Knock Out whose own prize leg is one; rider prizes remain terminal payoff."""
    leg = _attack_leg(model, candidate)
    return bool(_direct_active_ko(model, candidate) and leg is not None
                and float(leg.kwargs.get("target_prizes") or 0.0) == 1.0)


def _active_has_energy(model) -> bool:
    """The current Active holds a real attached Energy that a same-payoff gust would preserve."""
    active = getattr(getattr(model, "theirs", None), "active", None)
    body = getattr(active, "body", None) or {}
    return bool(body.get("energyCards") or body.get("energies"))


def _starts_with_gust(model, candidate: Candidate) -> bool:
    """Whether the line opens with a semantically tagged gust, not a card-id exception."""
    if not candidate.steps:
        return False
    try:
        return board_choice.choice_key(
            model, dict(candidate.steps[0].option), seat_index=int(getattr(model, "my_index", 0))) == "gust"
    except Unmodellable:
        return False


def _same_terminal_payoff(candidate: Candidate, direct: Candidate) -> bool:
    """The gust line takes the same prizes as an available direct active Knock Out."""
    return (round(float(candidate.terminal_ev), ao.SCORE_PLACES)
            == round(float(direct.terminal_ev), ao.SCORE_PLACES))


def _selection_candidates(model, candidates: Sequence[Candidate]) -> tuple:
    """Apply only sound terminal dominance before the ordinary candidate ordering."""
    if not candidates:
        return ()
    ordinary = min(candidates, key=lambda c: selection_key(model, c))
    direct_wins = tuple(c for c in candidates if _direct_prize_win(model, c))
    if direct_wins and _direct_terminal_attack(ordinary):
        return direct_wins
    direct_kos = tuple(c for c in candidates if _one_prize_active_ko(model, c))
    if not direct_kos or not _active_has_energy(model):
        return tuple(candidates)
    return tuple(
        candidate for candidate in candidates
        if not (_starts_with_gust(model, candidate)
                and any(_same_terminal_payoff(candidate, direct) for direct in direct_kos))
    )


@dataclass(frozen=True)
class _Node:
    model: object
    steps: tuple = ()
    used: frozenset = frozenset()
    block: tuple = ()            # canonical keys of the open block's members
    block_prints: tuple = ()     # their footprints, for the pairwise commutativity test
    truncated: int = 0
    leaf: float = 0.0
    origins: tuple = ((),)
    origin_indices: tuple = ((),)
    root_options: tuple = ()
    continuation_boundary: bool = False
    required_pick: bool = False


def frontier_key(node: _Node, *, remaining_depth: int) -> FrontierKey | None:
    """Exact continuation identity: board, remaining legal semantic actions, depth and boundary."""
    state_key = semantic_state_key(node.model)
    if state_key is None:
        return None
    actions = []
    for index, stamped in node.root_options:
        if index in node.used:
            continue
        option = resolve_against(node.model, stamped)
        if option is None or not _still_legal(node.model, option):
            continue
        fingerprint = semantic_option_fingerprint(strip_origin(option), node.model.source_obs)
        if fingerprint is None:
            return None
        actions.append(fingerprint)
    select = dict((node.model.source_obs or {}).get("select") or {})
    select.pop("option", None)
    boundary = (canonicalize(select), node.continuation_boundary, node.required_pick)
    return FrontierKey(FRONTIER_KEY_SCHEMA, state_key, tuple(sorted(actions)),
                       int(remaining_depth), boundary)


def compose(model, options: Sequence[Mapping], *, k: int = BEAM_WIDTH, epsilon: float = EPSILON,
            depth: int = SEQUENCE_DEPTH, search_api=None, deterministic=None,
            clauses_cover=None, shed=None, continuation_boundary: bool = False,
            required_pick: bool = False, exact_dedup: bool = True,
            continuation_admission: bool = True) -> ComposerResult:
    """Production beam; Issue #496's measured frontier policy remains opt-in after its runtime gate."""
    result, _state = _compose_core(
        model, options, k=k, epsilon=epsilon, depth=depth, search_api=search_api,
        deterministic=deterministic, clauses_cover=clauses_cover, shed=shed,
        continuation_boundary=continuation_boundary, required_pick=required_pick,
        exact_dedup=exact_dedup, continuation_admission=continuation_admission)
    return result


def _compose_core(model, options: Sequence[Mapping], *, k: int, epsilon: float, depth: int,
                  search_api=None, deterministic=None, clauses_cover=None, shed=None,
                  continuation_boundary: bool = False, required_pick: bool = False,
                  exact_dedup: bool = True, continuation_admission: bool = True,
                  reference_budget: ReferenceBudget | None = None):
    if int(k) < 1 or int(depth) < 0:
        # Caller error, so it RAISES where a modelling gap refuses. Not pedantry: `k=0` indexes the
        # k-th as [-1] and admits the entire menu — a beam that silently stops being one.
        raise ValueError(
            f"k={k!r}, depth={depth!r}: a beam must keep at least one candidate and cannot search a "
            f"negative number of plies. k=0 would index the k-th candidate as [-1] and admit "
            f"everything, which reads as a working beam while being none.")
    t0 = time.perf_counter()
    obs = getattr(model, "source_obs", None) or {}
    options = list(options or [])
    equiv = option_equivalence(options, obs)
    reps = class_representatives(equiv, len(options))
    canon = canonical_keys(options, obs)
    stamped = [stamp_origin(model, o) for o in options]

    state = _Run(k=k, epsilon=epsilon, depth=depth, search_api=search_api,
                 deterministic=deterministic, clauses_cover=clauses_cover, shed=shed,
                 canon=canon, reps=reps, stamped=stamped,
                 continuation_boundary=bool(continuation_boundary),
                 required_pick=bool(required_pick), reference_budget=reference_budget,
                 started_at=t0)

    root_terms = {}
    root_options = tuple((i, stamped[i]) for i in reps)
    root = _Node(model=model, leaf=float(state_value(model, working=root_terms)),
                 root_options=root_options,
                 continuation_boundary=bool(continuation_boundary),
                 required_pick=bool(required_pick))
    frontier, root_ranked = [root], None
    legacy = reference_budget is None and not exact_dedup and not continuation_admission
    try:
        for ply in range(depth + 1):
            generated = []
            for node in frontier:
                ranked = _rank(state, node, remaining_depth=depth - ply)
                if node is root:
                    root_ranked = ranked
                if legacy:
                    admitted = _admit(state, ranked)
                    if node is root:
                        state.admitted_root.update(entry.index for entry in admitted)
                    generated.extend(_expand_all(state, node, admitted))
                else:
                    generated.extend(_expand_all(state, node, ranked))
            if not generated:
                break
            if ply == depth:
                state.depth_truncated += len(generated)
                break
            if legacy:
                frontier = _prune_nodes(state, generated)
                continue
            remaining = depth - ply - 1
            unique, row = _deduplicate_nodes(state, generated, remaining_depth=remaining,
                                             enabled=exact_dedup)
            state.unique_nodes += len(unique)
            if reference_budget is not None and state.unique_nodes > reference_budget.max_unique_nodes:
                raise _ReferenceCap("max_unique_nodes")
            frontier = _retain_nodes(state, unique, remaining_depth=remaining,
                                     continuation=continuation_admission,
                                     exhaustive=reference_budget is not None,
                                     record_root=ply == 0)
            row["retained"] = len(frontier)
            row["epsilon_extras"] = max(0, len(frontier) - min(state.k, len(unique))) \
                if reference_budget is None else 0
            state.depth_stats.append(row)
    except _ReferenceCap as cap:
        state.cap_reason = str(cap)

    ranked0 = root_ranked or []
    selection_candidates = _selection_candidates(model, state.candidates)
    chosen = min(selection_candidates, key=lambda c: selection_key(model, c)) \
        if selection_candidates else None
    result = ComposerResult(
        chosen=chosen,
        candidates=tuple(sorted(state.candidates, key=lambda c: selection_key(model, c))),
        selection_candidates=tuple(sorted(selection_candidates, key=lambda c: selection_key(model, c))),
        margin=_margin(state, ranked0, chosen),
        fanned=tuple(fan_out([state.one_ply.get(i) for i in range(len(options))], equiv)),
        order=tuple((e.index, e.delta) for e in ranked0 if not e.refused),
        admission=tuple(sorted(state.admission.items(), key=lambda row: (-row[1], row[0]))),
        admission_details=dict(state.admission_details),
        changed_admission=frozenset(state.changed_admission),
        admitted=_admitted_indices(state, ranked0), always_expanded=_free_indices(ranked0),
        blocks=commutative_blocks(model, stamped, reps),
        gaps=tuple(state.gaps),
        bounds=tuple(state.bounds),
        stats={"schema": DIAGNOSTIC_SCHEMA, "leaf_evals": state.leaf_evals, "nodes": state.nodes,
               "candidates": len(state.candidates), "truncated": state.truncated,
               "depth_truncated": state.depth_truncated,
               "expectation_nodes": len(state.bounds),
               "expanded_families": state.expanded_families,
               "expansion_children": state.expansion_children,
               "transition_evals": state.transition_evals,
               "changed_admission": len(state.changed_admission),
               "depths": tuple(state.depth_stats),
               "block_resets": state.block_resets,
               "largest_merge_class": state.largest_merge_class,
               "state_key_schema": SEMANTIC_STATE_KEY_SCHEMA,
               "frontier_key_schema": FRONTIER_KEY_SCHEMA,
               "value_registry_identity": registry_identity(),
               "ms": (time.perf_counter() - t0) * 1000.0},
        root_value=root.leaf, root_terms=root_terms)
    return result, state


def compose_reference(model, options: Sequence[Mapping], *, budget: ReferenceBudget,
                      search_api=None, deterministic=None, clauses_cover=None, shed=None,
                      continuation_boundary: bool = False,
                      required_pick: bool = False,
                      beam_result: ComposerResult | None = None) -> ReferenceResult:
    """Bounded exhaustive policy over the production transition/Candidate core; caps report UNKNOWN."""
    if budget.max_depth < 0 or budget.max_transition_evals < 1 or budget.max_unique_nodes < 1:
        raise ValueError("reference limits must allow non-negative depth and positive work caps")
    result, state = _compose_core(
        model, options, k=1, epsilon=0.0, depth=budget.max_depth,
        search_api=search_api, deterministic=deterministic, clauses_cover=clauses_cover, shed=shed,
        continuation_boundary=continuation_boundary, required_pick=required_pick,
        exact_dedup=True, continuation_admission=False, reference_budget=budget)
    reason = state.cap_reason
    if not reason and state.depth_truncated:
        reason = "max_depth"
    if not reason and state.gaps:
        reason = "refusal_or_coverage"
    chosen = result.chosen
    best = None if chosen is None else round(chosen.score, ao.SCORE_PLACES)
    co_best = set()
    if best is not None:
        for candidate in result.selection_candidates:
            if not candidate.coverage_gap and round(candidate.score, ao.SCORE_PLACES) == best:
                co_best.update(candidate.first_semantic_actions)
                if not candidate.first_semantic_actions and candidate.semantic_path:
                    co_best.add(candidate.semantic_path[0])
    complete = not reason
    beam_chosen = None if beam_result is None else beam_result.chosen
    beam_first = None
    if beam_chosen is not None:
        beam_first = next(iter(beam_chosen.first_semantic_actions), None)
        if beam_first is None and beam_chosen.semantic_path:
            beam_first = beam_chosen.semantic_path[0]
    rows = tuple(state.depth_stats)
    return ReferenceResult(
        status=REFERENCE_UNKNOWN if reason else REFERENCE_COMPLETE, cap_reason=reason,
        composer=result, best_semantic_path=() if chosen is None else chosen.semantic_path,
        best_score=None if chosen is None else chosen.score,
        co_best_first_actions=tuple(sorted(co_best)),
        generated_by_depth=tuple(row["generated"] for row in rows),
        mergeable_by_depth=tuple(row["mergeable"] for row in rows),
        unique_by_depth=tuple(row["unique"] for row in rows),
        unmergeable_by_depth=tuple(row["unmergeable"] for row in rows),
        merged_by_depth=tuple(row["merged"] for row in rows),
        largest_merge_class=state.largest_merge_class, block_resets=state.block_resets,
        transition_evals=state.transition_evals, runtime_ms=result.stats["ms"],
        depth_reached=len(rows),
        beam_first_action_recall=(None if not complete or beam_chosen is None
                                  else beam_first in co_best),
        full_sequence_agreement=(None if not complete or beam_chosen is None or chosen is None
                                 else beam_chosen.semantic_path == chosen.semantic_path),
        score_regret=(None if not complete or beam_chosen is None or chosen is None
                      else max(0.0, chosen.score - beam_chosen.score)))


@dataclass
class _Run:
    """A record rather than closure variables, so the helpers below are testable in isolation."""

    k: int
    epsilon: float
    depth: int
    search_api: object
    deterministic: object
    clauses_cover: object
    canon: list
    reps: list
    stamped: list
    #: A CARD follow-up commits exactly one choice, then returns to a fresh MAIN menu. Its after-board
    #: receives the terminal action still reachable there; stale root options must not be replayed.
    continuation_boundary: bool = False
    required_pick: bool = False
    #: `None` makes a costed search REFUSE and name the seam, never price its cost as free.
    shed: object = None
    candidates: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    bounds: list = field(default_factory=list)    # both bounds of every expectation node (§S3.5)
    one_ply: dict = field(default_factory=dict)   # depth-0 delta per representative index
    leaf_evals: int = 0
    nodes: int = 0
    truncated: int = 0
    depth_truncated: int = 0
    expanded_families: int = 0        # §S7 D4: options whose deferred target was fanned out
    expansion_children: int = 0       # the instances scored across all of them
    transition_evals: int = 0
    rank_cache: dict = field(default_factory=dict)
    admission: dict = field(default_factory=dict)
    depth_stats: list = field(default_factory=list)
    block_resets: int = 0
    largest_merge_class: int = 1
    reference_budget: ReferenceBudget | None = None
    started_at: float = 0.0
    unique_nodes: int = 0
    cap_reason: str = ""
    admitted_root: set = field(default_factory=set)
    admission_details: dict = field(default_factory=dict)
    changed_admission: set = field(default_factory=set)


def _ask(resolver, option):
    """A callable seam input is asked; anything else passes through."""
    return resolver(option) if callable(resolver) else resolver


class _ReferenceCap(RuntimeError):
    pass


def _check_reference_budget(state: _Run):
    budget = state.reference_budget
    if budget is None:
        return
    if state.transition_evals >= budget.max_transition_evals:
        raise _ReferenceCap("max_transition_evals")
    if budget.wall_ms is not None and (time.perf_counter() - state.started_at) * 1000.0 >= budget.wall_ms:
        raise _ReferenceCap("wall_ms")


def _rank(state: _Run, node: _Node, *, remaining_depth: int | None = None) -> list:
    """Ordered by delta with a deterministic tail, never menu position. Availability is RE-checked."""
    cache_key = None if remaining_depth is None else frontier_key(node, remaining_depth=remaining_depth)
    if cache_key is not None and cache_key in state.rank_cache:
        return state.rank_cache[cache_key]
    out = []
    for i in state.reps:
        if i in node.used:
            continue
        option = resolve_against(node.model, state.stamped[i])
        if option is None or not _still_legal(node.model, option):
            continue
        entry = _one_ply(state, node, option, i)
        if entry is None:
            continue
        if not node.steps:
            # Recorded HERE, not after admission, so `fanned` answers for every option the menu
            # offered — a None must never mean "pruned" where the caller reads "unfingerprintable".
            state.one_ply[i] = entry.delta
        out.append(entry)
    out.sort(key=lambda e: (e.refused, -float(e.delta or 0.0), e.key))
    if cache_key is not None:
        state.rank_cache[cache_key] = out
    return out


@dataclass(frozen=True)
class _Ranked:
    index: int
    option: dict
    key: tuple
    delta: float | None
    after: object            # the model to continue from, or None (terminal / refused / reveal)
    fate: str
    footprint: object
    terminal: bool = False
    reveals: bool = False
    refused: bool = False
    truncated: int = 0
    ev: float = 0.0
    gap: str = ""
    #: The deferred-target expansion this option resolved through, so the `Step` can name WHICH won.
    choice: object = None
    semantic_key: str = ""
    outcome_kind: str = "ordinary"


def _one_ply(state: _Run, node: _Node, option: dict, index: int):
    """Apply and price one option. CHOSEN outcomes take max; DEALT outcomes take expectation."""
    _check_reference_budget(state)
    state.transition_evals += 1
    semantic = semantic_option_fingerprint(strip_origin(option), node.model.source_obs) or ""
    if ao.is_terminal(option):
        ev, _detail, gap = terminal_ev(node.model, option)
        if gap:
            state.gaps.append(f"{_frame_of(option)}: {gap}")
        return _Ranked(index=index, option=option,
                       key=(TIER_ENDER, state.canon[index], index),
                       delta=ev, after=None, fate=ao.TERMINAL, footprint=ao.Footprint(),
                       terminal=True, ev=ev, gap=gap, semantic_key=semantic,
                       outcome_kind="terminal")
    cover = _ask(state.clauses_cover, option)
    footprint = ao.option_footprint(node.model, option, clauses_cover=cover)
    key = canonical_key(node.model, option, index, state.canon[index], footprint)

    def _refuse(reason: str) -> _Ranked:
        state.gaps.append(f"{_frame_of(option)}: {reason}")
        return _Ranked(index=index, option=option, key=key, delta=None, after=None,
                       fate=ao.REFUSED, footprint=footprint, refused=True, gap=reason,
                       semantic_key=semantic)

    try:
        closed = bx.closed_form_transition(node.model, option, score=state_value,
                                           clauses_cover=cover, shed=state.shed)
    except Unmodellable as gap:
        return _refuse(str(gap))
    if isinstance(closed, ao.Expectation):
        state.leaf_evals += len(closed.classes)
        leaf = float(closed.ordering(state_value))
        state.bounds.append(Bounds(index=index, best=float(closed.best(state_value)),
                                   expected=float(closed.expected(state_value)),
                                   classes=len(closed.classes), truncated=closed.truncated,
                                   total_probability=float(closed.total_probability)))
        return _Ranked(index=index, option=option, key=key, delta=leaf - node.leaf, after=None,
                       fate=ao.MODELLED, footprint=footprint, reveals=True, ev=leaf,
                       semantic_key=semantic, outcome_kind=str(closed.resolution))
    if isinstance(closed, ao.ScalarTransition):
        state.leaf_evals += 1
        leaf = float(state_value(closed.model)) + closed.scalar
        return _Ranked(index=index, option=option, key=key, delta=leaf - node.leaf, after=None,
                       fate=ao.MODELLED, footprint=footprint, reveals=True, ev=leaf,
                       semantic_key=semantic, outcome_kind="scalar-reveal")

    if footprint.reveals_information and ao.transition_kind(option) == _ABILITY:
        return _refuse(
            "a revealing `_ABILITY` is an in-play source, not a malformed hand `_PLAY`; "
            "closed-form Ability sources are deliberately deferred to Issue #469")

    deferred = board_choice.has_deferred_target(
        node.model, option, seat_index=int(getattr(node.model, "my_index", 0)))
    if footprint.reveals_information and _reveal_rides(node.model, option) and not deferred:
        if ao.transition_kind(option) != _PLAY:
            return _refuse(
                "a revealing clause RIDES this option and it is not a `_PLAY`, so neither seam can "
                "price it: `board_expectation` enumerates a played Item/Supporter's search and "
                "refuses a reveal riding another kind, while the point transition consults no "
                "clauses on this kind at all and would apply the structural half while silently "
                "DROPPING the reveal — an under-reported delta, which at ordering time is a pruned "
                "option rather than an undervalued one")
        try:
            result = bx.expectation(node.model, option, shed=state.shed, score=state_value)
        except Unmodellable as gap:
            return _refuse(str(gap))
        state.leaf_evals += len(result.classes)
        try:
            best = float(result.best(state_value))
            lower = float(result.expected(state_value))
            leaf = float(result.ordering(state_value))
        except ValueError as gap:                # an un-enumerated effect: an unknown, not a zero
            return _refuse(str(gap))
        state.truncated += result.truncated
        state.bounds.append(Bounds(index=index, best=best, expected=lower,
                                    classes=len(result.classes), truncated=result.truncated,
                                    total_probability=float(result.total_probability)))
        return _Ranked(index=index, option=option, key=key, delta=leaf - node.leaf, after=None,
                       fate=ao.MODELLED, footprint=footprint, reveals=True,
                       truncated=result.truncated, ev=leaf, semantic_key=semantic,
                       outcome_kind=str(result.resolution))

    result = ao.apply_option(node.model, option, depth=len(node.steps),
                             search_api=state.search_api,
                             deterministic=_ask(state.deterministic, option),
                             clauses_cover=cover,
                             expand_deferred_targets=True)
    if ao.must_expand(result):
        return _refuse(f"{result.scope}: {result.reason}")
    if isinstance(result, ao.Expectation):
        # A CHOICE node: score every instance and emit ONE `_Ranked`, so the fan-out is
        # evaluation-time and `k` keeps its pre-expansion meaning. Not a boundary — `after` is set.
        choice = rank_targets(node.model, result)
        state.leaf_evals += len(choice.scored)
        state.expanded_families += 1
        state.expansion_children += len(choice.scored)
        state.truncated += choice.truncated
        state.bounds.append(Bounds(index=index, best=choice.leaf, expected=choice.expected,
                                    classes=len(choice.scored), truncated=choice.truncated,
                                    total_probability=choice.total_probability))
        if choice.best is None:
            return _refuse(
                "the deferred-target space enumerated to zero classes — an un-enumerated effect, "
                "and pricing it 0.0 would rank a real play below every scored line")
        return _Ranked(index=index, option=option, key=key, delta=choice.leaf - node.leaf,
                       after=choice.best.model, fate=ao.MODELLED, footprint=footprint,
                       truncated=choice.truncated, ev=choice.leaf, choice=choice,
                       semantic_key=semantic, outcome_kind=str(result.resolution))
    after = ao.require_model(result)
    state.leaf_evals += 1
    leaf = float(state_value(after))
    return _Ranked(index=index, option=option, key=key, delta=leaf - node.leaf, after=after,
                   fate=ao.ENGINE_RESOLVED if isinstance(result, ao.EngineResolved) else ao.MODELLED,
                   footprint=footprint, ev=leaf, semantic_key=semantic)


def _step_of(entry: _Ranked) -> Step:
    """One `_Ranked` as the `Step` that leaves this module — the ONE construction site, so the
    origin-stripping and the deferred-target attribution cannot drift between the two callers."""
    choice = entry.choice
    best = None if choice is None else choice.best
    semantic = entry.semantic_key if best is None else f"{entry.semantic_key}|target={best.fingerprint!r}"
    return Step(option=strip_origin(entry.option), index=entry.index, tier=entry.key[0],
                fate=entry.fate,
                chosen_target=() if best is None else best.fingerprint,
                target_classes=0 if choice is None else len(choice.scored),
                semantic_key=semantic)


def _frame_of(option: Mapping) -> str:
    hand, body = _origin_serials(option)
    return f"kind {ao.transition_kind(option)} (hand {hand}, body {body})"


def _admit(state: _Run, ranked: list) -> list:
    """Top-k PLUS anything within :data:`EPSILON` of the k-th — a DIFFERENT mechanism from
    :func:`selection_key`. Terminal and refused entries are admitted UNCONDITIONALLY."""
    free = [e for e in ranked if e.terminal or e.refused]
    scored = [e for e in ranked if not (e.terminal or e.refused)]
    if len(scored) <= state.k:
        return free + scored
    cutoff = scored[state.k - 1].delta - state.epsilon
    return free + [e for e in scored if e.delta >= cutoff]


def _expand_all(state: _Run, node: _Node, ranked: list) -> list:
    """Emit non-frontier candidates and every continuable child; admission happens depth-wide."""
    state.nodes += 1
    children = []
    if not (state.required_pick and state.continuation_boundary and not node.steps):
        state.candidates.append(_stop_here(state, node))
    for entry in ranked:
        if entry.terminal:
            state.candidates.append(_terminal_candidate(node, entry))
            continue
        if entry.refused or entry.after is None:
            state.candidates.append(_gap_or_reveal_candidate(node, entry))
            continue
        if state.continuation_boundary and not node.steps:
            state.candidates.append(_continuation_candidate(node, entry))
            continue
        commutes = all(ao.footprints_commute(entry.footprint, fp) for fp in node.block_prints)
        if commutes and node.block and not _admissible_in_block(entry.key, node.block):
            continue                             # this subset already exists in canonical order
        step = _step_of(entry)
        origins = tuple(sorted({path + (step.semantic_key,) for path in node.origins}))
        origin_indices = tuple(sorted({path + (entry.index,) for path in node.origin_indices}))
        children.append(_Node(
            model=entry.after, steps=node.steps + (step,), used=node.used | {entry.index},
            block=(node.block + (entry.key,)) if commutes else (entry.key,),
            block_prints=(node.block_prints + (entry.footprint,)) if commutes
            else (entry.footprint,),
            truncated=node.truncated + entry.truncated, leaf=node.leaf + entry.delta,
            origins=origins, origin_indices=origin_indices, root_options=node.root_options,
            continuation_boundary=node.continuation_boundary, required_pick=node.required_pick))
    return children


def _expand(state: _Run, node: _Node, ranked: list) -> list:
    """Compatibility helper for focused tests; production uses the depth-wide pipeline."""
    return _expand_all(state, node, _admit(state, ranked))


def _deduplicate_nodes(state: _Run, nodes: list, *, remaining_depth: int,
                       enabled: bool = True):
    groups = {}
    unmergeable = []
    if enabled:
        for node in nodes:
            key = frontier_key(node, remaining_depth=remaining_depth)
            if key is None:
                unmergeable.append(node)
            else:
                groups.setdefault(key, []).append(node)
    else:
        unmergeable = list(nodes)
    unique = list(unmergeable)
    mergeable = sum(len(group) for group in groups.values())
    for group in groups.values():
        state.largest_merge_class = max(state.largest_merge_class, len(group))
        origins = tuple(sorted({path for node in group for path in node.origins}))
        origin_indices = tuple(sorted({path for node in group for path in node.origin_indices}))
        representative_path = origins[0]
        representative = min((node for node in group if representative_path in node.origins),
                             key=lambda n: tuple(step.index for step in n.steps))
        blocks = {node.block for node in group}
        if len(blocks) == 1:
            block, block_prints = representative.block, representative.block_prints
        else:
            block, block_prints = (), ()
            state.block_resets += 1
        unique.append(_Node(
            model=representative.model, steps=representative.steps, used=representative.used,
            block=block, block_prints=block_prints, truncated=representative.truncated,
            leaf=representative.leaf, origins=origins, origin_indices=origin_indices,
            root_options=representative.root_options,
            continuation_boundary=representative.continuation_boundary,
            required_pick=representative.required_pick))
    unique.sort(key=lambda n: (min(n.origins), tuple(step.index for step in n.steps)))
    row = {"generated": len(nodes), "mergeable": mergeable,
           "unmergeable": len(unmergeable), "unique": len(unique),
           "merged": len(nodes) - len(unique),
           "largest_merge_class": max((len(group) for group in groups.values()), default=1),
           "block_resets": state.block_resets,
           "origin_count": sum(len(node.origins) for node in unique),
           "distinct_first_semantic_actions": len({path[0] for node in unique
                                                    for path in node.origins if path})}
    return unique, row


def _admission_score(state: _Run, node: _Node, *, remaining_depth: int,
                     continuation: bool):
    best = node.leaf
    best_entry = None
    if continuation and remaining_depth > 0:
        for entry in _rank(state, node, remaining_depth=remaining_depth):
            if entry.refused:
                continue
            if entry.terminal:
                score = node.leaf + entry.ev
            elif entry.after is None:
                score = _gap_or_reveal_candidate(node, entry).score
            else:
                score = node.leaf + float(entry.delta or 0.0)
            if score > best or (score == best and best_entry is not None
                                and entry.semantic_key < best_entry.semantic_key):
                best, best_entry = score, entry
    return best, best_entry


def _retain_nodes(state: _Run, nodes: list, *, remaining_depth: int,
                  continuation: bool, exhaustive: bool, record_root: bool = False):
    scored = []
    for node in nodes:
        score, entry = _admission_score(state, node, remaining_depth=remaining_depth,
                                        continuation=continuation)
        scored.append((score, min(node.origins), node, entry))
        if record_root:
            for path in node.origin_indices:
                if path:
                    state.admission[path[0]] = max(score, state.admission.get(path[0], float("-inf")))
                    detail = {"stop_score": node.leaf,
                              "continuation_estimate": score,
                              "continuation_gain": score - node.leaf,
                              "continuation_action": "" if entry is None else entry.semantic_key,
                              "continuation_kind": "stop" if entry is None else entry.outcome_kind}
                    state.admission_details[path[0]] = detail
    scored.sort(key=lambda row: (-row[0], row[1], tuple(step.index for step in row[2].steps)))

    def cut(rows):
        if exhaustive or len(rows) <= state.k:
            return rows
        cutoff = rows[state.k - 1][0] - state.epsilon
        return [row for row in rows if row[0] >= cutoff]

    retained = cut(scored)
    if record_root:
        baseline = sorted(((node.leaf, min(node.origins), node, None) for node in nodes),
                          key=lambda row: (-row[0], row[1], tuple(step.index for step in row[2].steps)))
        baseline_ids = {id(row[2]) for row in cut(baseline)}
        retained_ids = {id(row[2]) for row in retained}
        changed_ids = baseline_ids ^ retained_ids if continuation else set()
        for _score, _path, node, _entry in retained:
            for path in node.origin_indices:
                if path:
                    state.admitted_root.add(path[0])
        for node in nodes:
            if id(node) in changed_ids:
                state.changed_admission.update(path[0] for path in node.origin_indices if path)
    return [row[2] for row in retained]


def _continuation_candidate(node: _Node, entry: _Ranked) -> Candidate:
    """One committed CARD choice plus the best terminal action reachable on its after-board."""
    leaf = node.leaf + entry.delta
    ev = continuation_ev(entry.after)
    step = _step_of(entry)
    return Candidate(steps=(step,), terminal=None, leaf=leaf, terminal_ev=ev,
                     score=leaf + ev, truncated=node.truncated + entry.truncated,
                     origins=tuple(sorted({path + (step.semantic_key,) for path in node.origins})),
                     origin_indices=tuple(sorted({path + (entry.index,)
                                                  for path in node.origin_indices})))


def _stop_here(state: _Run, node: _Node) -> Candidate:
    """Take ``node``'s steps and stop — ``EV(terminal) = 0``. ⚠️ It does NOT carry
    :func:`continuation_ev`: crediting it would let *"commit nothing"* win a decision outright."""
    return Candidate(steps=node.steps, terminal=None, leaf=node.leaf, terminal_ev=0.0,
                     score=node.leaf, truncated=node.truncated, origins=node.origins,
                     origin_indices=node.origin_indices)


def _terminal_candidate(node: _Node, entry: _Ranked) -> Candidate:
    """The leaf is the board the terminal action was reached FROM; its EV is the 2nd summand."""
    return Candidate(steps=node.steps, terminal=strip_origin(entry.option),
                     terminal_index=entry.index, leaf=node.leaf, terminal_ev=entry.ev,
                     score=node.leaf + entry.ev, coverage_gap=entry.gap,
                     truncated=node.truncated,
                     origins=tuple(sorted({path + (entry.semantic_key,) for path in node.origins})),
                     origin_indices=tuple(sorted({path + (entry.index,)
                                                  for path in node.origin_indices})),
                     terminal_semantic_key=entry.semantic_key)


def _gap_or_reveal_candidate(node: _Node, entry: _Ranked) -> Candidate:
    """A line that STOPS at this option. A REVEAL keeps its `best()` and carries
    :func:`continuation_ev`; a REFUSAL keeps the node's leaf — its value is UNKNOWN, not zero."""
    step = _step_of(entry)
    if entry.refused:
        leaf, ev = node.leaf, 0.0
    else:
        leaf, ev = node.leaf + entry.delta, continuation_ev(node.model)
    return Candidate(steps=node.steps + (step,), terminal=None, leaf=leaf, terminal_ev=ev,
                     score=leaf + ev, coverage_gap=entry.gap,
                     truncated=node.truncated + entry.truncated,
                     origins=tuple(sorted({path + (step.semantic_key,) for path in node.origins})),
                     origin_indices=tuple(sorted({path + (entry.index,)
                                                  for path in node.origin_indices})))


def _prune_nodes(state: _Run, nodes: list) -> list:
    """The same top-k-plus-epsilon rule the option ranking uses — one rule, asked twice."""
    if len(nodes) <= state.k:
        return nodes
    ordered = sorted(nodes, key=lambda n: (-n.leaf, tuple(s.index for s in n.steps)))
    cutoff = ordered[state.k - 1].leaf - state.epsilon
    return [n for n in ordered if n.leaf >= cutoff]


def _margin_at(order: tuple, free: frozenset, admitted: frozenset, k: int, index) -> Margin:
    """The ONE margin computation, so the composer's line and the human's are measured alike."""
    kth = order[k - 1][1] if len(order) >= k else None
    if index is None:
        return Margin(k=k, ranked=len(order), kth_delta=kth)
    rank = next((n + 1 for n, (i, _d) in enumerate(order) if i == index), None)
    delta = next((d for i, d in order if i == index), None)
    return Margin(rank=rank, k=k, ranked=len(order),
                  in_beam=rank is not None and rank <= k and index not in free,
                  admitted=index in admitted, always_expand=index in free,
                  chosen_delta=delta, kth_delta=kth,
                  margin_to_kth=None if (delta is None or kth is None) else delta - kth)


def _free_indices(ranked0: list) -> frozenset:
    return frozenset(e.index for e in ranked0 if e.terminal or e.refused)


def _admitted_indices(state: _Run, ranked0: list) -> frozenset:
    return frozenset(state.admitted_root) | _free_indices(ranked0)


def _margin(state: _Run, ranked0: list, chosen: Candidate | None) -> Margin:
    """The chosen line's first step against the beam cutoff. THREE survival fields: *"did it survive"*
    (``admitted`` / ``always_expand``) and *"did it earn its place by score"* (``in_beam``) differ."""
    # Refusals are retained as free diagnostics, but are unscored unknowns rather than one-ply ranks.
    scored = tuple((e.index, e.delta) for e in ranked0 if not e.refused)
    index = None if chosen is None else chosen.first_index
    base = _margin_at(scored, _free_indices(ranked0),
                      _admitted_indices(state, ranked0), state.k, index)
    ordered = sorted(state.admission.items(), key=lambda row: (-row[1], row[0]))
    admission_rank = next((n + 1 for n, (i, _score) in enumerate(ordered) if i == index), None)
    admission_score = state.admission.get(index)
    kth = ordered[state.k - 1][1] if len(ordered) >= state.k else None
    reason = "always-expand" if index in _free_indices(ranked0) else \
        "hard-top-k" if admission_rank is not None and admission_rank <= state.k else \
        "epsilon" if index in state.admitted_root else "cut"
    return replace(base, immediate_rank=base.rank, immediate_delta=base.chosen_delta,
                   admission_rank=admission_rank, admission_score=admission_score,
                   kth_admission_score=kth,
                   admission_margin=None if admission_score is None or kth is None
                   else admission_score - kth, admission_reason=reason,
                   changed_admission=index in state.changed_admission,
                   **state.admission_details.get(index, {}))


__all__ = (
    "BEAM_WIDTH", "SEQUENCE_DEPTH", "EPSILON",
    "FRONTIER_KEY_SCHEMA", "DIAGNOSTIC_SCHEMA", "REFERENCE_COMPLETE", "REFERENCE_UNKNOWN",
    "TIER_INFORMATIVE", "TIER_COMMIT_FREE", "TIER_SUPPORTER", "TIER_COMMITMENT", "TIER_SHUFFLE",
    "TIER_ENDER",
    "FrontierKey", "ReferenceBudget", "ReferenceResult",
    "Step", "Candidate", "Margin", "Bounds", "ComposerResult", "ScoredTarget", "TargetChoice",
    "compose", "compose_reference", "frontier_key", "selection_key", "terminal_ev", "continuation_ev",
    "canonical_tier", "canonical_key",
    "commutative_blocks", "subset_lattice", "resolve_against", "stamp_origin", "strip_origin",
    "rank_targets", "choose_target",
)
