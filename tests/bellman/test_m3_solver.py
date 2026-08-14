from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from common import (
    ActionIdentity, Actor, Chance, Choice, DecisionState, Deterministic, Ledger, ReferenceSolver,
    NeedModel, PilotProfile, ProductionLimits, ProductionSolver, RevealChoice, RevealOutcome,
    SearchLimits, Terminal,
)
from common.algebra import Edge, WeightedEdge
from common.commutativity import ActionFootprint, action_footprint, independent
from common.needs import ActionFocus, NeedBeam, semantic_action_key
from common.options import LegalAction
import common.solver as solver_module
from common.value import CardFacts, Potential, ValueOracle, ValueRegistry


CARD = 900
DECK = (CARD,)


def _obs(node, *, hand=(), board=0.0, supporter=False, context=0):
    return {"node": node, "current": {"yourIndex": 0, "board": board,
            "supporterPlayed": supporter, "energyAttached": False, "retreated": False,
            "stadiumPlayed": False,
            "players": [
                {"hand": [{"id": cid, "serial": 10 + i, "playerIndex": 0}
                          for i, cid in enumerate(hand)],
                 "active": [], "bench": [], "discard": [], "prize": []},
                {"hand": None, "active": [], "bench": [], "discard": [], "prize": []},
            ]}, "select": {"context": context, "option": []}}


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


class ResolvedEndGraph(Graph):
    def resolve_end(self, state, action):
        return self.transition(state, action)


class UnchangedEndGraph(Graph):
    def resolve_end(self, state, action):
        return None


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


def test_provider_can_resolve_forced_end_transition_value():
    root, expired = _state("root", board=0.2), _state("expired")
    end = _action("end")
    decision = ReferenceSolver(
        ResolvedEndGraph({"root": (end,)}, {("root", "end"): Deterministic(expired)}),
        _oracle(),
    ).decide(root)

    assert decision.value == pytest.approx(-0.2)
    assert decision.diagnostics["ledger"]["costs"] == {"board": pytest.approx(0.2)}


def test_provider_can_retain_exact_zero_end_when_nothing_forced_changes():
    root, end = _state("root", board=0.2), _action("end")
    decision = ReferenceSolver(UnchangedEndGraph({"root": (end,)}, {}), _oracle()).decide(root)

    assert decision.value == 0.0


def test_provider_resolves_expected_value_across_forced_end_chance():
    root = _state("root", board=0.2)
    low, high = _state("low", board=0.1), _state("high", board=0.3)
    end = _action("end")
    chance = Chance((WeightedEdge(0.5, "tails", Deterministic(low)),
                     WeightedEdge(0.5, "heads", Deterministic(high))))
    decision = ReferenceSolver(
        ResolvedEndGraph({"root": (end,)}, {("root", "end"): chance}), _oracle(),
    ).decide(root)

    assert decision.complete
    assert decision.value == pytest.approx(0.0)
    assert decision.diagnostics["ledger"]["benefits"] == {"board": pytest.approx(0.05)}
    assert decision.diagnostics["ledger"]["costs"] == {"board": pytest.approx(0.05)}


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


def test_needs_focus_schedules_every_root_without_deleting_a_legal_branch(monkeypatch):
    root = _state("focus-root")
    alpha = _state("alpha", board=0.5)
    alpha_finish = _state("alpha-finish", board=0.6)
    beta = _state("beta", board=0.3)
    gamma = _state("gamma", board=0.2)
    first, second, third, end = (
        _action("alpha", 0), _action("beta", 1), _action("gamma", 2), _action("end", 3))

    class FixedBeamBuilder:
        def __init__(self, *_args, **_kwargs):
            pass

        def build(self, _state, _actions, ranking=None):
            del ranking
            return NeedBeam(
                focused=(ActionFocus(
                    semantic_action_key(first), "play", (), 1.0, "current need"),),
                safety=(ActionFocus(
                    semantic_action_key(end), "end", (), 0.0, "turn boundary"),),
                unknown=(), paths=(), features=(), elapsed_ms=0.0, exhausted=False,
                inactive=(
                    ActionFocus(semantic_action_key(second), "play", (), 0.0,
                                "no current need"),
                    ActionFocus(semantic_action_key(third), "play", (), 0.0,
                                "no current need"),
                ),
            )

    monkeypatch.setattr(solver_module, "NeedBeamBuilder", FixedBeamBuilder)
    oracle = _oracle()
    oracle.needs = NeedModel(REGISTRY, lambda obs: Potential(
        float(obs["current"].get("board", 0.0)),
        (("board", float(obs["current"].get("board", 0.0))),)))
    graph = FootprintedGraph(
            {"focus-root": (first, second, third, end),
             "alpha": (first, end), "alpha-finish": (end,),
             "beta": (end,), "gamma": (end,)},
            {("focus-root", "alpha"): Deterministic(alpha),
             ("alpha", "alpha"): Deterministic(alpha_finish),
             ("focus-root", "beta"): Deterministic(beta),
             ("focus-root", "gamma"): Deterministic(gamma)},
            {kind: ActionFootprint((kind,), barrier=True)
             for kind in ("alpha", "beta", "gamma", "end")},
        )
    solver = ProductionSolver(
        graph,
        oracle,
        limits=ProductionLimits(max_nodes=50),
        profile=PilotProfile.resolve(global_values={"needs.focus_enabled": 1.0}),
    )

    decision = solver.decide(root)

    assert decision.action.kind == "alpha"
    assert decision.diagnostics["production"]["needs_later_wave"] == 2
    assert decision.diagnostics["production"]["needs_clock_scale"] == 1.0
    assert decision.diagnostics["production"]["root_branch_nodes"] == (3, 1, 2, 2)
    assert {call for call in graph.calls if call[0] == "focus-root"} == {
        ("focus-root", "alpha"), ("focus-root", "beta"), ("focus-root", "gamma")}


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
    assert decision.diagnostics["production"]["structural_prunes"][0]["proof_type"] == \
        "commutativity"


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


def test_fetch_into_hand_is_an_information_barrier():
    observation = {
        "current": {"yourIndex": 0, "players": [
            {"hand": [{"id": 901}, {"id": 905}],
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
    fetch = LegalAction(ActionIdentity("play"), (1,), ((1,),), ())

    class Effects:
        @staticmethod
        def clauses(card_id):
            return ({"kind": "fetch", "target": "supporter", "zone": "deck"},) \
                if card_id == 905 else ()

    attach_footprint = action_footprint(state, attach, effects=Effects())
    fetch_footprint = action_footprint(state, fetch, effects=Effects())

    assert fetch_footprint.barrier
    assert fetch_footprint.information_first
    assert not independent(attach_footprint, fetch_footprint)


def test_supporter_fetch_is_a_commitment_not_free_information():
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
            return ({"kind": "fetch", "target": "evolution", "zone": "deck",
                     "dest": "in_play"},)

    class Stats:
        @staticmethod
        def get(_card_id):
            return SimpleNamespace(is_supporter=True, is_stadium=False)

    footprint = action_footprint(state, play, effects=Effects(), stats=Stats())

    assert footprint.barrier
    assert footprint.commitment
    assert not footprint.information_first


def test_bench_fetch_without_a_remaining_target_is_a_commitment():
    observation = {
        "current": {"yourIndex": 0, "players": [
            {"hand": [{"id": 905}], "active": [], "bench": [], "benchMax": 5},
            {"hand": None, "active": [], "bench": []},
        ]},
        "select": {"context": 0, "option": [{"type": 7, "index": 0}]},
    }
    state = SimpleNamespace(obs=observation, deck_counts=((906, 2),))
    play = LegalAction(ActionIdentity("play"), (0,), ((0,),), ())

    class Effects:
        @staticmethod
        def clauses(_card_id):
            return ({"kind": "fetch", "target": "basic_pokemon", "zone": "deck",
                     "dest": "bench"},)

    class Stats:
        @staticmethod
        def get(_card_id):
            return SimpleNamespace(is_pokemon=False, is_supporter=False, is_stadium=False)

    footprint = action_footprint(state, play, effects=Effects(), stats=Stats())

    assert footprint.barrier
    assert footprint.commitment
    assert not footprint.information_first


def test_shuffle_refresh_is_not_safe_information_first():
    observation = {
        "current": {"yourIndex": 0, "players": [
            {"hand": [{"id": 1213}], "active": [], "bench": []},
            {"hand": None, "active": [], "bench": []},
        ]},
        "select": {"context": 0, "option": [{"type": 7, "index": 0}]},
    }
    state = SimpleNamespace(obs=observation)
    play = LegalAction(ActionIdentity("play"), (0,), ((0,),), ())

    class Effects:
        @staticmethod
        def clauses(_card_id):
            return ({"kind": "draw", "amount": 4, "rider": "shuffle_both_hands"},)

    footprint = action_footprint(state, play, effects=Effects())
    assert footprint.barrier
    assert not footprint.information_first


def test_information_first_prunes_only_the_commitment_then_fetch_order():
    root = _state("info-root")
    after_attach = _state("after-attach", board=0.2)
    after_fetch = _state("after-fetch", board=0.1)
    finish = _state("info-finish", board=0.8)
    attach, fetch, end = _action("attach"), _action("play", 1), _action("end", 2)
    graph = FootprintedGraph(
        {"info-root": (attach, fetch, end), "after-attach": (fetch, end),
         "after-fetch": (attach, end), "info-finish": (end,)},
        {("info-root", "attach"): Deterministic(after_attach),
         ("info-root", "play"): Deterministic(after_fetch),
         ("after-attach", "play"): Deterministic(finish),
         ("after-fetch", "attach"): Deterministic(finish)},
        {"attach": ActionFootprint(("attach",), commitment=True),
         "play": ActionFootprint(("play",), barrier=True, information_first=True),
         "end": ActionFootprint(("end",), barrier=True)},
    )

    oracle = _oracle()
    oracle.need_coverage_value = lambda _state, action: (
        1.0 if action.identity.kind == "play" else 0.0)
    decision = ProductionSolver(
        graph, oracle, limits=ProductionLimits(max_nodes=50, root_probe_nodes=50),
    ).decide(root)

    assert decision.action.kind == "play"
    assert ("after-attach", "play") not in graph.calls
    assert ("after-fetch", "attach") in graph.calls
    assert any(row["proof_type"] == "information_before_commitment"
               for row in decision.diagnostics["production"]["structural_prunes"])


def test_immediate_need_preparation_precedes_a_commitment():
    root = _state("need-root")
    after_setup = _state("after-setup", board=0.1)
    after_attach = _state("after-attach", board=0.2)
    finish = _state("need-finish", board=0.8)
    attach, setup, end = _action("attach"), _action("play", 1), _action("end", 2)
    graph = FootprintedGraph(
        {"need-root": (attach, setup, end), "after-attach": (setup, end),
         "after-setup": (attach, end), "need-finish": (end,)},
        {("need-root", "attach"): Deterministic(after_attach),
         ("need-root", "play"): Deterministic(after_setup),
         ("after-attach", "play"): Deterministic(finish),
         ("after-setup", "attach"): Deterministic(finish)},
        {"attach": ActionFootprint(("attach",), commitment=True),
         "play": ActionFootprint(("play",), barrier=True),
         "end": ActionFootprint(("end",), barrier=True)},
    )
    oracle = _oracle()
    oracle.need_coverage_ledger = lambda _state, action: (
        ("deployment", Ledger((("board", 0.2),), ()))
        if action.identity.kind == "play" else None)

    decision = ProductionSolver(
        graph, oracle, limits=ProductionLimits(max_nodes=50, root_probe_nodes=50),
    ).decide(root)

    assert decision.action.kind == "play"
    assert any(row["proof_type"] == "needs_before_commitment"
               for row in decision.diagnostics["production"]["structural_prunes"])


def test_urgent_heal_retains_free_recovery_that_fills_a_need():
    root = _state("heal-root")
    recovered = _state("recovered", board=0.1)
    healed = _state("healed", board=0.2)
    finish = _state("finish", board=0.8)
    recover, heal, end = _action("recover"), _action("heal", 1), _action("end", 2)
    graph = FootprintedGraph(
        {"heal-root": (heal, recover, end), "recovered": (heal, end),
         "healed": (end,), "finish": (end,)},
        {("heal-root", "heal"): Deterministic(healed),
         ("heal-root", "recover"): Deterministic(recovered),
         ("recovered", "heal"): Deterministic(finish)},
        {"heal": ActionFootprint(("heal",), commitment=True),
         "recover": ActionFootprint(("recover",), barrier=True),
         "end": ActionFootprint(("end",), barrier=True)},
    )
    oracle = _oracle()
    oracle.heal_repositions_energy = lambda _state, action: action.identity.kind == "heal"
    oracle.heal_need_value = lambda _state, action: (
        1.0 if action.identity.kind == "heal" else None)
    oracle.recovery_need_value = lambda _state, action: (
        0.5 if action.identity.kind == "recover" else 0.0)

    decision = ProductionSolver(
        graph, oracle, limits=ProductionLimits(max_nodes=50, root_probe_nodes=50),
    ).decide(root)

    assert decision.action.kind == "recover"


def test_incomplete_forced_discard_uses_stable_immediate_value_fallback():
    from common.solver import Evaluation, _select_our_action

    keep, waste = _action("discard_keep"), _action("discard_waste", 1)
    chosen, _result = _select_our_action((
        (keep, Evaluation(0.2, Ledger((('hand', 0.2),), ()), False)),
        (waste, Evaluation(0.9, Ledger((), (('hand', 0.1),), 1.0), False)),
    ), 8)

    assert chosen == keep


def test_bench_fetch_and_evolution_do_not_claim_retreat_commutativity():
    observation = {
        "current": {"yourIndex": 0, "players": [
            {"hand": [{"id": 905}, {"id": 906}],
             "active": [{"id": 903, "serial": 44}],
             "bench": [{"id": 904, "serial": 45}]},
            {"hand": None, "active": [{"id": 907, "serial": 46}], "bench": []},
        ]},
        "select": {"context": 0, "option": [
            {"type": 7, "index": 0},
            {"type": 9, "index": 1, "inPlayArea": 5, "inPlayIndex": 0},
            {"type": 12},
        ]},
    }
    state = SimpleNamespace(obs=observation)
    fetch = LegalAction(ActionIdentity("play"), (0,), ((0,),), ())
    evolve = LegalAction(ActionIdentity("evolve"), (1,), ((1,),), ())
    retreat = LegalAction(ActionIdentity("retreat"), (2,), ((2,),), ())

    class Effects:
        @staticmethod
        def clauses(card_id):
            return ({"kind": "fetch", "target": "basic_pokemon", "zone": "deck",
                     "dest": "bench"},) if card_id == 905 else ()

    fetch_footprint = action_footprint(state, fetch, effects=Effects())
    evolve_footprint = action_footprint(state, evolve, effects=Effects())
    retreat_footprint = action_footprint(state, retreat, effects=Effects())

    assert fetch_footprint.barrier
    assert retreat_footprint.barrier
    assert not independent(fetch_footprint, retreat_footprint)
    assert not independent(evolve_footprint, retreat_footprint)


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
