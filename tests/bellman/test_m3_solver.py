from __future__ import annotations

from dataclasses import replace

import pytest

from common.bellman import (
    ActionIdentity, Actor, Chance, Choice, DecisionState, Deterministic, Ledger, ReferenceSolver,
    ProductionLimits, ProductionSolver, RevealChoice, RevealOutcome, SearchLimits, Terminal,
)
from common.bellman.algebra import Edge, WeightedEdge
from common.bellman.options import LegalAction
from common.bellman.value import CardFacts, Potential, ValueOracle, ValueRegistry


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
    from common.bellman.engine import CgpyTransitionProvider
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
