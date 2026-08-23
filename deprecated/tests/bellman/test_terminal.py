from __future__ import annotations

from types import SimpleNamespace

import pytest

from common import (
    ActionIdentity,
    Actor,
    Chance,
    Choice,
    Deterministic,
    Refresh,
    RevealChoice,
    RevealOutcome,
    Terminal,
    Unknown,
)
from deprecated.bellman import PlanRequest
from deprecated.bellman.state import DecisionState
from deprecated.bellman import BellmanTurnPlanner, Potential, ValueRegistry
from common.algebra import Edge, WeightedEdge
from common.options import LegalAction
from deprecated.bellman.terminal import (
    ProofStep,
    TerminalLimits,
    TerminalProver,
    proof_lock_step,
    proof_step_failure,
    terminal_effects_supported,
)


def _obs(node: str, *, turn: int = 3):
    return {
        "node": node,
        "current": {
            "yourIndex": 0,
            "turn": turn,
            "supporterPlayed": False,
            "energyAttached": False,
            "retreated": False,
            "stadiumPlayed": False,
            "players": [
                {"hand": [], "active": [], "bench": [], "discard": [], "prize": []},
                {"hand": None, "active": [], "bench": [], "discard": [], "prize": []},
            ],
        },
        "select": {"context": 0, "option": []},
    }


def _state(node: str, *, turn: int = 3):
    return DecisionState.from_observation(
        _obs(node, turn=turn), deck=(1,), deck_name="terminal-test")


def _action(kind: str, index: int):
    return LegalAction(ActionIdentity(kind, (kind, index)), (index,), ((index,),), ())


class _Graph:
    def __init__(self, actions, transitions, actors=None):
        self._actions = actions
        self._transitions = transitions
        self._actors = actors or {}

    def actions(self, state):
        return self._actions.get(state.obs["node"], ())

    def transition(self, state, action):
        return self._transitions[(state.obs["node"], action.identity.kind)]

    def actor(self, state):
        return self._actors.get(state.obs["node"], Actor.OURS)


class _AvailableGraph(_Graph):
    available = True
    backend = "terminal-test"
    _error = ""

    def close(self):
        pass


class _TrackedGraph(_AvailableGraph):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.closed = 0

    def close(self):
        self.closed += 1


class _UnsupportedGraph(_Graph):
    @staticmethod
    def terminal_action_supported(_state, _action):
        return False


def test_uncovered_ability_fails_closed_even_when_card_stats_deny_an_ability():
    state = _state("root")
    action = _action("ability", 0)
    stat = SimpleNamespace(is_pokemon=True, hasAbility=False)
    stats = SimpleNamespace(get=lambda _card_id: stat)
    effects = SimpleNamespace(
        clauses=lambda _card_id: (), fully_covers=lambda _card_id: False)

    assert not terminal_effects_supported(
        state, action, card_id=1, recipient_id=None, effects=effects, stats=stats)


def test_terminal_prover_returns_a_guaranteed_current_turn_policy():
    root, setup, won, next_turn = (
        _state("root"), _state("setup"), _state("won"), _state("next", turn=4))
    attach, attack, end = _action("attach", 0), _action("attack", 1), _action("end", 2)
    graph = _Graph(
        {"root": (attach, end), "setup": (attack, end)},
        {("root", "attach"): Deterministic(setup),
         ("root", "end"): Deterministic(next_turn),
         ("setup", "attack"): Terminal(won, "win"),
         ("setup", "end"): Deterministic(next_turn)},
    )

    proof = TerminalProver(graph, limits=TerminalLimits(50, 1.0)).prove(root)

    assert proof is not None
    assert proof.first_action == attach
    assert tuple(step.action.kind for step in proof.continuation) == ("attack",)
    assert proof.decisions == 2
    assert proof.terminal_result == "win"


def test_terminal_prover_rejects_one_losing_positive_probability_outcome():
    root, won, lost = _state("root"), _state("won"), _state("lost")
    attack = _action("attack", 0)
    graph = _Graph(
        {"root": (attack,)},
        {("root", "attack"): Chance((
            WeightedEdge(0.5, "heads", Terminal(won, "win")),
            WeightedEdge(0.5, "tails", Terminal(lost, "attack resolved")),
        ))},
    )

    assert TerminalProver(graph, limits=TerminalLimits(50, 1.0)).prove(root) is None


def test_terminal_prover_requires_every_opponent_choice_to_win():
    root, response, won, lost = (
        _state("root"), _state("response"), _state("won"), _state("lost"))
    attack = _action("attack", 0)
    graph = _Graph(
        {"root": (attack,)},
        {("root", "attack"): Choice(Actor.OPPONENT, (
            Edge("accept", Terminal(won, "win")),
            Edge("escape", Terminal(lost, "attack resolved")),
        ))},
    )

    assert TerminalProver(graph, limits=TerminalLimits(50, 1.0)).prove(root) is None


def test_terminal_prover_accepts_our_existential_reveal_choice_in_every_outcome():
    root, branch_a, branch_b, won, lost = (
        _state("root"), _state("branch-a"), _state("branch-b"),
        _state("won"), _state("lost"))
    play, choose_a, choose_b = (
        _action("play", 0), _action("choose_a", 0), _action("choose_b", 1))
    graph = _Graph(
        {"root": (play,), "branch-a": (choose_a,), "branch-b": (choose_b,)},
        {("root", "play"): RevealChoice(
            Actor.OURS,
            (Edge("good-a", Deterministic(branch_a)),
             Edge("good-b", Deterministic(branch_b)),
             Edge("bad", Terminal(lost, "attack resolved"))),
            (RevealOutcome(0.5, ("good-a", "bad")),
             RevealOutcome(0.5, ("good-b", "bad"))),
        ),
         ("branch-a", "choose_a"): Terminal(won, "win"),
         ("branch-b", "choose_b"): Terminal(won, "win")},
    )

    proof = TerminalProver(graph, limits=TerminalLimits(50, 1.0)).prove(root)

    assert proof is not None
    assert {step.expected_state_key for step in proof.continuation} == {
        branch_a.plan_key, branch_b.plan_key}
    selected, failure = proof_lock_step(
        proof.continuation, branch_b, profile_hash="", proof_id=proof.proof_id)
    assert failure is None
    assert selected.action == choose_b.identity


@pytest.mark.parametrize("node", (
    Unknown("unsupported", "hidden card"),
    Refresh(1, ((5, 5),), True),
))
def test_terminal_prover_abstains_on_unenumerated_uncertainty(node):
    root = _state("root")
    play = _action("play", 0)
    prover = TerminalProver(
        _Graph({"root": (play,)}, {("root", "play"): node}),
        limits=TerminalLimits(50, 1.0))

    assert prover.prove(root) is None
    assert prover.stopped_reason == "unsupported_uncertainty"


@pytest.mark.parametrize("enabler", ("attach", "retreat", "evolve", "play", "ability"))
def test_terminal_prover_handles_each_declared_enabling_action(enabler):
    root, ready, won = _state("root"), _state("ready"), _state("won")
    setup, attack = _action(enabler, 0), _action("attack", 1)
    graph = _Graph(
        {"root": (setup,), "ready": (attack,)},
        {("root", enabler): Deterministic(ready),
         ("ready", "attack"): Terminal(won, "win")},
    )

    proof = TerminalProver(graph, limits=TerminalLimits(50, 1.0)).prove(root)

    assert proof is not None
    assert proof.first_action.identity.kind == enabler


def test_terminal_module_validates_every_lock_guard():
    state = _state("root")
    action = _action("attack", 0)
    current = state.obs["current"]
    step = ProofStep(
        state.plan_key, state.legal_menu_digest, action.selection, action.identity,
        "profile", "proof", current["turn"], current["yourIndex"])

    assert proof_step_failure(
        step, state, profile_hash="profile", proof_id="proof") is None
    assert proof_step_failure(
        step, state, profile_hash="changed", proof_id="proof") == "profile_changed"
    assert proof_step_failure(
        step, state, profile_hash="profile", proof_id="changed") == "proof_changed"


def test_terminal_prover_does_not_cross_the_turn_boundary():
    root, next_turn, won = _state("root"), _state("next", turn=4), _state("won", turn=4)
    play, attack = _action("play", 0), _action("attack", 1)
    graph = _Graph(
        {"root": (play,), "next": (attack,)},
        {("root", "play"): Deterministic(next_turn),
         ("next", "attack"): Terminal(won, "win")},
    )

    assert TerminalProver(graph, limits=TerminalLimits(50, 1.0)).prove(root) is None


def test_terminal_prover_rejects_a_sampled_hidden_dependency():
    root, won = _state("root"), _state("won")
    draw = _action("play", 0)
    graph = _UnsupportedGraph(
        {"root": (draw,)}, {("root", "play"): Terminal(won, "win")})
    prover = TerminalProver(graph, limits=TerminalLimits(50, 1.0))

    assert prover.prove(root) is None
    assert prover.stopped_reason == "unsupported_uncertainty"


def test_planner_commits_terminal_proof_before_bellman_utility():
    root, won, rich, next_turn = (
        _state("root"), _state("won"), _state("rich"), _state("next", turn=4))
    attack, play, end = _action("attack", 0), _action("play", 1), _action("end", 2)
    graph = _AvailableGraph(
        {"root": (attack, play, end), "rich": (end,)},
        {("root", "attack"): Terminal(won, "win"),
         ("root", "play"): Deterministic(rich),
         ("root", "end"): Deterministic(next_turn),
         ("rich", "end"): Deterministic(next_turn)},
    )
    registry = ValueRegistry(functions={}, facts={})
    planner = BellmanTurnPlanner(
        registry=registry,
        family_evaluator=lambda obs: Potential(
            10.0 if obs.get("node") == "rich" else 0.0, ()),
        provider_factory=lambda *_args, **_kwargs: graph,
    )

    decision = planner.decide(PlanRequest(root.obs, (1,), "terminal-test"))

    assert decision.action == attack.identity
    assert decision.diagnostics["terminal_proof"]["result"] == "proved"


def test_failed_proof_and_bellman_share_one_provider():
    root, next_turn = _state("root"), _state("next", turn=4)
    end = _action("end", 0)
    graph = _TrackedGraph(
        {"root": (end,)}, {("root", "end"): Deterministic(next_turn)})
    created = []

    def factory(*_args, **_kwargs):
        created.append(graph)
        return graph

    planner = BellmanTurnPlanner(
        registry=ValueRegistry(functions={}, facts={}),
        family_evaluator=lambda _obs: Potential(0.0, ()),
        provider_factory=factory,
    )
    request = PlanRequest(root.obs, (1,), "terminal-test")

    assert planner.prove(request) is None
    decision = planner.decide(request, terminal_checked=True)

    assert decision.action == end.identity
    assert len(created) == 1
    assert graph.closed == 1
