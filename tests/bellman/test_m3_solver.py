from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from common import (
    ActionIdentity, Actor, Chance, Choice, DecisionState, Deterministic, Ledger, ReferenceSolver,
    ProductionLimits, ProductionSolver, RevealChoice, RevealOutcome, SearchLimits, Terminal,
)
from common.algebra import Edge, WeightedEdge
from common.commutativity import ActionFootprint, action_footprint, independent
from common.options import LegalAction
from common.value import CardFacts, Potential, ValueOracle, ValueRegistry


CARD = 900
DECK = (CARD,)


def _obs(node, *, hand=(), board=0.0, supporter=False):
    return {"node": node, "current": {"yourIndex": 0, "board": board,
            "supporterPlayed": supporter, "energyAttached": False, "retreated": False,
            "stadiumPlayed": False,
            "players": [
                {"hand": [{"id": cid, "serial": 10 + i, "playerIndex": 0}
                          for i, cid in enumerate(hand)],
                 "active": [], "bench": [], "discard": [], "prize": []},
                {"hand": None, "active": [], "bench": [], "discard": [], "prize": []},
            ]}, "select": {"context": 0, "option": []}}


REGISTRY = ValueRegistry(functions={CARD: ("search",)}, facts={CARD: CardFacts()})


def _state(node, **kwargs):
    return DecisionState.from_observation(_obs(node, **kwargs), deck=DECK, deck_name="test",
                                          value_registry_identity=REGISTRY.identity)


def _action(kind, index=0):
    return LegalAction(ActionIdentity(kind, (kind,)), (index,), ((index,),), ())


class Graph:
    def __init__(self, actions, transitions):
        self._actions, self._transitions = actions, transitions

    def actions(self, state):
        return self._actions[state.obs["node"]]

    def transition(self, state, action):
        return self._transitions[(state.obs["node"], action.identity.kind)]

    def actor(self, state):
        return Actor.OURS


class FootprintedGraph(Graph):
    def __init__(self, actions, transitions, footprints):
        super().__init__(actions, transitions)
        self._footprints = footprints
        self.calls = []

    def transition(self, state, action):
        self.calls.append((state.obs["node"], action.identity.kind))
        return super().transition(state, action)

    def footprint(self, state, action):
        return self._footprints[action.identity.kind]


def _oracle():
    return ValueOracle(REGISTRY, lambda obs: Potential(
        float(obs["current"].get("board", 0.0)),
        (("board", float(obs["current"].get("board", 0.0))),)))


def test_complete_line_continues_and_commits_only_first_action():
    root, mid, finish = _state("root", hand=(CARD,)), _state("mid", hand=(), board=0.02), \
        _state("finish", hand=(), board=0.20)
    attach, supporter, end, attack = (_action("attach"), _action("play"), _action("end", 1),
                                      _action("attack"))
    graph = Graph(
        {"root": (attach, end), "mid": (supporter, end), "finish": (attack, end)},
        {("root", "attach"): Deterministic(mid),
         ("mid", "play"): Deterministic(finish),
         ("finish", "attack"): Terminal(finish, "attack resolved", Ledger())},
    )
    decision = ReferenceSolver(graph, _oracle()).decide(root)
    assert decision.action.kind == "attach"
    assert decision.chosen == (0,)
    assert decision.value > 0.0
    assert decision.diagnostics["ledger"]["continuation"] > 0.0


def test_production_turn_search_has_no_depth_limit():
    """Width and nodes bound production; a finite legal turn is never cut off by action count."""
    action, end = _action("play"), _action("end", 1)
    states = [_state(f"step-{index}", board=index / 100.0) for index in range(13)]
    actions = {state.obs["node"]: (action, end) for state in states}
    transitions = {
        (states[index].obs["node"], "play"): Deterministic(states[index + 1])
        for index in range(len(states) - 1)
    }
    transitions[(states[-1].obs["node"], "play")] = Terminal(
        states[-1], "win", Ledger())

    decision = ProductionSolver(
        Graph(actions, transitions), _oracle(),
        limits=ProductionLimits(max_nodes=100, beam_width=1),
    ).decide(states[0])

    assert decision.action.kind == "play"
    assert decision.diagnostics["root"].nodes == len(states)
    assert "max_depth" not in decision.diagnostics["production"]


def test_production_partial_order_reduction_skips_only_the_reverse_commutative_order():
    root = _state("root")
    after_alpha = _state("after-alpha", board=0.1)
    after_beta = _state("after-beta", board=0.1)
    finish = _state("finish", board=0.2)
    alpha, beta, end = _action("alpha"), _action("beta", 1), _action("end", 2)
    graph = FootprintedGraph(
        {"root": (alpha, beta, end), "after-alpha": (beta, end),
         "after-beta": (alpha, end), "finish": (end,)},
        {("root", "alpha"): Deterministic(after_alpha),
         ("root", "beta"): Deterministic(after_beta),
         ("after-alpha", "beta"): Deterministic(finish),
         ("after-beta", "alpha"): Deterministic(finish)},
        {"alpha": ActionFootprint(("alpha",), writes=frozenset({"alpha"})),
         "beta": ActionFootprint(("beta",), writes=frozenset({"beta"})),
         "end": ActionFootprint(("end",), barrier=True)},
    )

    decision = ProductionSolver(
        graph, _oracle(), limits=ProductionLimits(max_nodes=50, root_probe_nodes=50),
    ).decide(root)

    assert decision.action.kind == "alpha"
    assert ("after-alpha", "beta") in graph.calls
    assert ("after-beta", "alpha") not in graph.calls
    assert decision.diagnostics["production"]["commutative_permutations_pruned"] >= 1


def test_chance_boundary_clears_partial_order_sleep_set():
    root = _state("chance-root")
    after_alpha = _state("chance-after-alpha", board=0.1)
    after_beta = _state("chance-after-beta", board=0.1)
    finish = _state("chance-finish", board=0.2)
    alpha, beta, end = _action("alpha"), _action("beta", 1), _action("end", 2)
    graph = FootprintedGraph(
        {"chance-root": (alpha, beta, end), "chance-after-alpha": (beta, end),
         "chance-after-beta": (alpha, end), "chance-finish": (end,)},
        {("chance-root", "alpha"): Deterministic(after_alpha),
         ("chance-root", "beta"): Chance((WeightedEdge(1.0, "outcome", Deterministic(after_beta)),)),
         ("chance-after-alpha", "beta"): Deterministic(finish),
         ("chance-after-beta", "alpha"): Deterministic(finish)},
        {"alpha": ActionFootprint(("alpha",), writes=frozenset({"alpha"})),
         "beta": ActionFootprint(("beta",), writes=frozenset({"beta"})),
         "end": ActionFootprint(("end",), barrier=True)},
    )

    ProductionSolver(
        graph, _oracle(), limits=ProductionLimits(max_nodes=50, root_probe_nodes=50),
    ).decide(root)

    assert ("chance-after-beta", "alpha") in graph.calls


def test_declared_deterministic_play_commutes_with_independent_attachment():
    observation = {
        "current": {"yourIndex": 0, "players": [
            {"hand": [{"id": 901}, {"id": 902}],
             "active": [{"id": 903, "serial": 44}], "bench": []},
            {"hand": None, "active": [{"id": 904, "serial": 45}], "bench": []},
        ]},
        "select": {"context": 0, "option": [
            {"type": 8, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
            {"type": 7, "index": 1},
        ]},
    }
    state = SimpleNamespace(obs=observation)
    attach = LegalAction(ActionIdentity("attach"), (0,), ((0,),), ())
    play = LegalAction(ActionIdentity("play"), (1,), ((1,),), ())

    class Effects:
        @staticmethod
        def clauses(card_id):
            return ({"kind": "gust"},) if card_id == 902 else ()

    class Stats:
        @staticmethod
        def get(card_id):
            return SimpleNamespace(is_supporter=card_id == 902, is_stadium=False)

    attach_footprint = action_footprint(state, attach, effects=Effects(), stats=Stats())
    play_footprint = action_footprint(state, play, effects=Effects(), stats=Stats())
    assert independent(attach_footprint, play_footprint)


def test_information_effect_is_a_partial_order_barrier():
    observation = {
        "current": {"yourIndex": 0, "players": [
            {"hand": [{"id": 905}], "active": [], "bench": []},
            {"hand": None, "active": [], "bench": []},
        ]},
        "select": {"context": 0, "option": [{"type": 7, "index": 0}]},
    }
    state = SimpleNamespace(obs=observation)
    play = LegalAction(ActionIdentity("play"), (0,), ((0,),), ())

    class Effects:
        @staticmethod
        def clauses(_card_id):
            return ({"kind": "draw", "amount": 2},)

    footprint = action_footprint(state, play, effects=Effects())
    assert footprint.barrier


def test_all_negative_actions_choose_end_zero():
    root, spent = _state("root", hand=(CARD,)), _state("spent", hand=())
    play, end = _action("play"), _action("end", 1)
    graph = Graph({"root": (play, end), "spent": (end,)},
                  {("root", "play"): Deterministic(spent)})
    decision = ReferenceSolver(graph, _oracle()).decide(root)
    assert decision.action.kind == "end"
    assert decision.value == 0.0


def test_equal_utility_uses_the_shorter_bellman_continuation():
    root, mid, finish = _state("root"), _state("mid"), _state("finish", board=0.2)
    long, followup, direct, end = (
        _action("ability"), _action("attach"), _action("play"), _action("end", 1))
    graph = Graph(
        {"root": (long, direct, end), "mid": (followup, end), "finish": (end,)},
        {("root", "ability"): Deterministic(mid),
         ("mid", "attach"): Deterministic(finish),
         ("root", "play"): Deterministic(finish)},
    )

    assert ReferenceSolver(graph, _oracle()).decide(root).action.kind == "play"


def test_budget_dependent_lower_bound_is_not_transposition_cached():
    root, finish = _state("root"), _state("finish", board=0.2)
    play, end = _action("play"), _action("end", 1)
    solver = ProductionSolver(
        Graph({"root": (play, end), "finish": (end,)},
              {("root", "play"): Deterministic(finish)}),
        _oracle(), limits=ProductionLimits(max_nodes=1),
    )

    bounded = solver._state(root)
    assert not bounded.evaluation.complete
    assert root.semantic_key not in solver._memo

    solver.nodes = 0
    solver.limits = SearchLimits(10)
    exact = solver._state(root)
    assert exact.evaluation.complete
    assert exact.value == pytest.approx(0.2)


def test_mandatory_choice_ignores_optional_menu_width_cap():
    """A forced selection must return a legal Bellman action, never crash on a width cap."""
    root = _state("mandatory")
    low, high = _state("low", board=0.1), _state("high", board=0.4)
    choose_low, choose_high, end = _action("choose_low", 0), _action("choose_high", 1), _action("end")
    decision = ProductionSolver(
        Graph(
            {"mandatory": (choose_low, choose_high), "low": (end,), "high": (end,)},
            {("mandatory", "choose_low"): Deterministic(low),
             ("mandatory", "choose_high"): Deterministic(high)},
        ),
        _oracle(), limits=ProductionLimits(max_nodes=20, effect_choice_width=1),
    ).decide(root)

    assert decision.chosen == (1,)
    assert decision.action.kind == "choose_high"


def test_production_successive_halving_refines_only_the_best_incomplete_root():
    root = _state("root")
    promising = _state("promising", board=0.10)
    payoff = _state("payoff", board=0.50)
    distraction = _state("distraction", board=0.05)
    larger_hidden_payoff = _state("larger-hidden-payoff", board=0.90)
    build, distract, continue_build, continue_distract, end = (
        _action("build", 0), _action("distract", 1), _action("continue_build", 0),
        _action("continue_distract", 0), _action("end", 2),
    )
    decision = ProductionSolver(
        Graph(
            {"root": (build, distract, end), "promising": (continue_build, end),
             "payoff": (end,), "distraction": (continue_distract, end),
             "larger-hidden-payoff": (end,)},
            {("root", "build"): Deterministic(promising),
             ("promising", "continue_build"): Deterministic(payoff),
             ("root", "distract"): Deterministic(distraction),
             ("distraction", "continue_distract"): Deterministic(larger_hidden_payoff)},
        ),
        _oracle(),
        limits=ProductionLimits(
            max_nodes=10, root_probe_nodes=1, root_refinement_width=1),
    ).decide(root)

    production = decision.diagnostics["production"]
    assert decision.action.kind == "build"
    assert production["root_branch_nodes"][0] > 1
    assert production["root_branch_nodes"][1] == 1
    assert production["root_refinement_width"] == 1


def test_opponent_min_and_known_chance_are_recursive_nodes():
    root = _state("root")
    good, bad = _state("leaf", board=0.4), _state("leaf2", board=-0.1)
    end = _action("end")
    act = _action("play")
    graph = Graph(
        {"root": (act, end), "leaf": (end,), "leaf2": (end,)},
        {("root", "play"): Choice(Actor.OPPONENT,
            (Edge("good for us", Deterministic(good)), Edge("bad for us", Deterministic(bad))))},
    )
    assert ReferenceSolver(graph, _oracle()).decide(root).action.kind == "end"
    graph._transitions[("root", "play")] = Chance((
        WeightedEdge(0.75, "good", Deterministic(good)),
        WeightedEdge(0.25, "bad", Deterministic(bad)),
    ))
    assert ReferenceSolver(graph, _oracle()).decide(root).action.kind == "play"


def test_reveal_choice_uses_remaining_turn_value_not_static_card_precedence():
    root = _state("root")
    static_high = _state("static-high", board=0.10)
    useful = _state("useful", board=0.0)
    payoff = _state("payoff", board=0.50)
    dig, use, end = _action("play"), _action("ability"), _action("end", 1)
    graph = Graph(
        {"root": (dig, end), "static-high": (end,), "useful": (use, end), "payoff": (end,)},
        {("root", "play"): RevealChoice(
            Actor.OURS,
            (Edge("higher static worth", Deterministic(static_high)),
             Edge("board-useful card", Deterministic(useful))),
            (RevealOutcome(1.0, ("higher static worth", "board-useful card")),),
        ),
         ("useful", "ability"): Deterministic(payoff)},
    )

    decision = ReferenceSolver(graph, _oracle()).decide(root)

    assert decision.action.kind == "play"
    assert decision.value == pytest.approx(0.50)
    assert decision.diagnostics["root"].stopped_reason == "expected value after revealed choice"


def test_information_before_commitment_wins_by_expected_continuation_value():
    """E[max continuation | reveal] beats committing before the same uncertainty resolves."""
    root = _state("root")
    response_a = _state("response-a", board=0.8)
    response_b = _state("response-b", board=0.8)
    miss = _state("miss")
    observe, commit, end = _action("play"), _action("attach"), _action("end", 1)
    graph = Graph(
        {"root": (observe, commit, end), "response-a": (end,),
         "response-b": (end,), "miss": (end,)},
        {("root", "play"): RevealChoice(
            Actor.OURS,
            (Edge("response-a", Deterministic(response_a)),
             Edge("response-b", Deterministic(response_b))),
            (RevealOutcome(0.5, ("response-a",)),
             RevealOutcome(0.5, ("response-b",))),
         ),
         ("root", "attach"): Chance((
             WeightedEdge(0.5, "commit happened to fit", Deterministic(response_a)),
             WeightedEdge(0.5, "commit did not fit", Deterministic(miss)),
         ))},
    )

    reference = ReferenceSolver(graph, _oracle()).decide(root)
    production = ProductionSolver(
        graph, _oracle(), limits=ProductionLimits(max_nodes=20)).decide(root)

    assert reference.action.kind == production.action.kind == "play"
    assert reference.value == production.value == pytest.approx(0.8)


@pytest.mark.parametrize("kind", ["attach", "evolve", "retreat", "heal", "fetch", "gust", "play"])
def test_deterministic_function_families_use_the_same_equation(kind):
    root, after = _state("root", hand=(CARD,)), _state("after", hand=(), board=0.25)
    action, end = _action(kind), _action("end", 1)
    graph = Graph({"root": (action, end), "after": (end,)},
                  {("root", kind): Deterministic(after)})
    decision = ReferenceSolver(graph, _oracle()).decide(root)
    assert decision.action.kind == kind
    assert decision.diagnostics["ledger"]["benefits"]["board"] == 0.25


def test_cgpy_provider_reconstructs_a_real_corpus_main_menu_without_ranking():
    from pathlib import Path
    from common.engine import CgpyTransitionProvider
    from train.blunder.store import load_corrections

    repo = Path(__file__).resolve().parents[2]
    correction = next(c for c in load_corrections(repo / "data" / "corrections")
                      if c.agent == "mega_starmie" and c.obs is not None
                      and ((c.obs.get("select") or {}).get("context") == 0))
    deck = tuple(int(line) for line in (repo / "src" / "agents" / "mega_starmie" /
                                        "deck.csv").read_text().split())
    state = DecisionState.from_observation(correction.obs, deck=deck, deck_name="mega_starmie")
    provider = CgpyTransitionProvider(state)
    assert provider.available, provider._error
    actions = provider.actions(state)
    assert {action.identity.kind for action in actions} == {
        {7: "play", 8: "attach", 9: "evolve", 10: "ability", 12: "retreat",
         13: "attack", 14: "end"}.get(option["type"], f"option_{option['type']}")
        for option in correction.obs["select"]["option"]}
