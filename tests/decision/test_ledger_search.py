from dataclasses import replace
import math
from types import SimpleNamespace

import pytest

from common.algebra import Chance, Deterministic, WeightedEdge
from common.decision import (
    CandidateDisposition,
    CandidateRoster,
    ContinuationResult,
    DecisionDelta,
    EvaluationRequest,
    EvaluationStatus,
    PolicyConfiguration,
    RealizedOutcome,
    SearchConfiguration,
    ValueComponent,
    ValuedCandidate,
)
from common.ledger import EvaluationModel
from common.ledger.decision import LEDGER_VALUE_SCALE, LedgerValueEvaluator
from common.ledger.evaluate import evaluate
from common.ledger.preview import price_actions
from common.ledger.search import (
    GreedyDecisionPolicy,
    LedgerOnePlySearch,
    UniformPolicyModel,
)
from common.ledger.seam import PreviewState
from common.observation import ObservationStateBuilder
from deprecated.bellman.state import DecisionState
from ledger_helpers import DARK_E, DRAGAPULT, ScriptedProvider, action, body, player, printout
from tools.train.ledger_parity import assert_decision_parity


DECK = (DRAGAPULT, DARK_E) * 30


class CountingLedgerEvaluator(LedgerValueEvaluator):
    identity = "counting-ledger"

    def __init__(self):
        self.calls = {}
        self.parent_states = []

    def evaluate_with_state(self, request, parent_state=None):
        board = getattr(request.state, "observation", request.state)
        self.calls[board.position_key] = self.calls.get(board.position_key, 0) + 1
        self.parent_states.append(parent_state)
        return super().evaluate_with_state(request, parent_state)


def test_one_ply_search_retains_every_candidate_and_explicit_successor():
    observation = printout(me=player(active=body(DRAGAPULT, 1), hand=[DARK_E]))
    board = ObservationStateBuilder(DECK).root(observation)
    root = PreviewState(observation, board, "root", deck=DECK,
                        deck_counts=board.deck_counts or ())
    attached_observation = printout(
        me=player(active=body(DRAGAPULT, 1, energies=(8,)), hand=[]))
    attached_board = ObservationStateBuilder(DECK).root(attached_observation)
    attached = DecisionState.from_observation(
        attached_observation, deck=DECK, deck_name="test", value_registry_identity="test")
    attach, end = action("attach", (0,)), action("end", (1,))
    provider = ScriptedProvider(
        menus={"root": (attach, end)},
        nodes={("root", attach.identity): Deterministic(attached)},
    )

    evaluator = CountingLedgerEvaluator()
    model = EvaluationModel.build()
    configuration = SearchConfiguration()
    result = LedgerOnePlySearch().search(
        EvaluationRequest(root, model),
        evaluator,
        UniformPolicyModel(),
        provider,
        configuration,
    )

    assert tuple(candidate.action for candidate in result.roster.candidates) == (attach, end)
    priced, free_end = result.roster.candidates
    assert priced.status in {EvaluationStatus.COMPLETE, EvaluationStatus.ESTIMATED}
    assert priced.successors
    assert sum(successor.probability for successor in priced.successors) == 1.0
    assert priced.successors[0].state.position_key == attached_board.position_key
    assert priced.successors[0].action_path == (attach.identity,)
    assert priced.successors[0].trace.start_position_key == board.position_key
    assert priced.successors[0].trace.actions == (attach.identity,)
    assert priced.successors[0].trace.terminal_position_key == attached_board.position_key
    assert priced.prior == 0.5
    assert free_end.disposition is CandidateDisposition.ENDS_TURN
    assert free_end.delta.total == 0.0
    assert free_end.successors[0].state is board
    assert free_end.successors[0].action_path == (end.identity,)
    assert set(evaluator.calls.values()) == {1}

    legacy_prices = price_actions(
        root, board, evaluate(board, model).total, provider, model, configuration)
    choice = GreedyDecisionPolicy().choose(result.roster, PolicyConfiguration())
    assert_decision_parity(
        legacy_prices, result, choice, forced=False,
        configuration=PolicyConfiguration())


def test_every_candidate_delta_is_expected_successor_ledger_minus_root_ledger():
    observation = printout(me=player(active=body(DRAGAPULT, 1), hand=[DARK_E]))
    board = ObservationStateBuilder(DECK).root(observation)
    root = PreviewState(observation, board, "root", deck=DECK,
                        deck_counts=board.deck_counts or ())
    stronger = DecisionState.from_observation(
        printout(me=player(active=body(DRAGAPULT, 1, energies=(8,)), hand=[])),
        deck=DECK, deck_name="test", value_registry_identity="test")
    unchanged = DecisionState.from_observation(
        observation, deck=DECK, deck_name="test", value_registry_identity="test")
    attach, end = action("attach", (0,)), action("end", (1,))
    provider = ScriptedProvider(
        menus={"root": (attach, end)},
        nodes={("root", attach.identity): Chance((
            WeightedEdge(0.25, "stronger", Deterministic(stronger)),
            WeightedEdge(0.75, "unchanged", Deterministic(unchanged)),
        ))},
    )

    result = LedgerOnePlySearch().search(
        EvaluationRequest(root, EvaluationModel.build()), LedgerValueEvaluator(),
        UniformPolicyModel(), provider, SearchConfiguration())

    for candidate in result.roster.candidates:
        expected = math.fsum(
            successor.probability * successor.valuation.total
            for successor in candidate.successors) - result.baseline.total
        assert candidate.delta.total == pytest.approx(expected)
        assert candidate.search_value.total == pytest.approx(
            result.baseline.total + candidate.delta.total)
        assert {successor.valuation.evaluator_identity
                for successor in candidate.successors} == {
                    LedgerValueEvaluator.identity}


def test_search_rejects_non_distribution_policy_priors():
    class InvalidPolicyModel:
        identity = "invalid-priors"

        def priors(self, state, actions):
            return tuple(0.75 for _action in actions)

    observation = printout(me=player(active=body(DRAGAPULT, 1)))
    board = ObservationStateBuilder(DECK).root(observation)
    root = PreviewState(observation, board, "root", deck=DECK,
                        deck_counts=board.deck_counts or ())
    provider = ScriptedProvider(menus={"root": (action("end", (0,)),
                                                       action("end", (1,)))}, nodes={})

    with pytest.raises(ValueError, match="normalized distribution"):
        LedgerOnePlySearch().search(
            EvaluationRequest(root, EvaluationModel.build()), LedgerValueEvaluator(),
            InvalidPolicyModel(), provider, SearchConfiguration())


def test_exhausted_budget_marks_every_root_action_unavailable(monkeypatch):
    class StoppedBudget:
        stop_reason = "time_budget"
        frontier = []
        nodes = 0

        def check(self):
            return True

    monkeypatch.setattr(
        "common.ledger.search.BudgetController", lambda _configuration: StoppedBudget())
    observation = printout(me=player(active=body(DRAGAPULT, 1)))
    board = ObservationStateBuilder(DECK).root(observation)
    root = PreviewState(observation, board, "root", deck=DECK,
                        deck_counts=board.deck_counts or ())
    first, second = action("card", (0,)), action("card", (1,))
    provider = ScriptedProvider(menus={"root": (first, second)}, nodes={})

    result = LedgerOnePlySearch().search(
        EvaluationRequest(root, EvaluationModel.build()), LedgerValueEvaluator(),
        UniformPolicyModel(), provider, SearchConfiguration())

    assert {candidate.status for candidate in result.roster.candidates} == {
        EvaluationStatus.UNAVAILABLE}
    with pytest.raises(ValueError, match="no comparable candidates"):
        GreedyDecisionPolicy().choose(result.roster, PolicyConfiguration())


def test_root_evaluation_time_is_inside_the_search_deadline(monkeypatch):
    evaluated = False

    class Deadline:
        def __init__(self):
            self.stop_reason = "complete"
            self.frontier = []
            self.nodes = 0

        def check(self):
            if evaluated:
                self.stop_reason = "time_budget"
                return True
            return False

    class MarkingEvaluator(LedgerValueEvaluator):
        def evaluate_with_state(self, request, parent_state=None):
            nonlocal evaluated
            value = super().evaluate_with_state(request, parent_state)
            evaluated = True
            return value

    monkeypatch.setattr(
        "common.ledger.search.BudgetController", lambda _configuration: Deadline())
    observation = printout(me=player(active=body(DRAGAPULT, 1)))
    board = ObservationStateBuilder(DECK).root(observation)
    root = PreviewState(observation, board, "root", deck=DECK,
                        deck_counts=board.deck_counts or ())
    first, second = action("card", (0,)), action("card", (1,))
    provider = ScriptedProvider(menus={"root": (first, second)}, nodes={})

    result = LedgerOnePlySearch().search(
        EvaluationRequest(root, EvaluationModel.build()), MarkingEvaluator(),
        UniformPolicyModel(), provider, SearchConfiguration())

    assert result.stop_reason == "time_budget"
    assert all(candidate.status is EvaluationStatus.UNAVAILABLE
               for candidate in result.roster.candidates)


def test_forced_action_reports_a_deadline_crossed_during_root_evaluation(monkeypatch):
    evaluated = False

    class Deadline:
        stop_reason = "complete"
        frontier = []
        nodes = 0

        def check(self):
            if evaluated:
                self.stop_reason = "time_budget"
                return True
            return False

    class MarkingEvaluator(LedgerValueEvaluator):
        def evaluate_with_state(self, request, parent_state=None):
            nonlocal evaluated
            value = super().evaluate_with_state(request, parent_state)
            evaluated = True
            return value

    monkeypatch.setattr(
        "common.ledger.search.BudgetController", lambda _configuration: Deadline())
    select = {"type": 1, "context": 7, "minCount": 1, "maxCount": 1,
              "option": [{"type": 3, "index": 0}], "deck": None,
              "contextCard": None, "effect": None, "remainDamageCounter": 0,
              "remainEnergyCost": 0}
    observation = printout(me=player(active=body(DRAGAPULT, 1)), select=select)
    board = ObservationStateBuilder(DECK).root(observation)
    root = PreviewState(observation, board, "root", deck=DECK,
                        deck_counts=board.deck_counts or ())
    ending = action("end", (0,))
    provider = ScriptedProvider(menus={"root": (ending,)}, nodes={})

    result = LedgerOnePlySearch().search(
        EvaluationRequest(root, EvaluationModel.build()), MarkingEvaluator(),
        UniformPolicyModel(), provider, SearchConfiguration())

    assert result.stop_reason == "time_budget"
    assert result.roster.candidates[0].status is EvaluationStatus.UNAVAILABLE
    assert result.roster.candidates[0].delta is None


def test_search_owns_and_reuses_the_previous_turn_snapshot():
    builder = ObservationStateBuilder(DECK)
    first_observation = printout(
        me=player(active=body(DRAGAPULT, 1), hand=[DARK_E]))
    first_board = builder.root(first_observation)
    second_observation = printout(
        me=player(active=body(DRAGAPULT, 1, energies=(8,)), hand=[]))
    second_board, delta = builder.advance(first_board, second_observation)
    ending = action("end", (0,))
    evaluator = CountingLedgerEvaluator()
    search = LedgerOnePlySearch()
    model = EvaluationModel.build()

    first = search.search(
        EvaluationRequest(PreviewState(
            first_observation, first_board, "first", deck=DECK,
            deck_counts=first_board.deck_counts or ()), model),
        evaluator, UniformPolicyModel(), ScriptedProvider(
            menus={"first": (ending,)}, nodes={}), SearchConfiguration())
    search.search(
        EvaluationRequest(PreviewState(
            second_observation, second_board, "second", deck=DECK,
            deck_counts=second_board.deck_counts or ()), model,
            first.baseline, delta),
        evaluator, UniformPolicyModel(), ScriptedProvider(
            menus={"second": (ending,)}, nodes={}), SearchConfiguration())

    assert evaluator.parent_states[0] is None
    assert evaluator.parent_states[1] is not None


def test_search_rejects_a_same_position_snapshot_from_a_different_menu():
    observation = printout(me=player(active=body(DRAGAPULT, 1)))
    board = ObservationStateBuilder(DECK).root(observation)
    root = PreviewState(observation, board, "root", deck=DECK,
                        deck_counts=board.deck_counts or ())
    ending = action("end", (0,))
    provider = ScriptedProvider(menus={"root": (ending,)}, nodes={})
    evaluator = CountingLedgerEvaluator()
    search = LedgerOnePlySearch()
    model = EvaluationModel.build()

    first = search.search(
        EvaluationRequest(root, model), evaluator, UniformPolicyModel(),
        provider, SearchConfiguration())
    search.search(
        EvaluationRequest(
            root, model, replace(first.baseline, cache_key="different-menu"),
            SimpleNamespace(parts=())),
        evaluator, UniformPolicyModel(), provider, SearchConfiguration())

    assert evaluator.parent_states[-1] is None


def test_search_never_reuses_incremental_state_across_evaluator_identities():
    class FirstEvaluator(CountingLedgerEvaluator):
        identity = "first-ledger-semantics"

    class SecondEvaluator(CountingLedgerEvaluator):
        identity = "second-ledger-semantics"

    builder = ObservationStateBuilder(DECK)
    first_observation = printout(
        me=player(active=body(DRAGAPULT, 1), hand=[DARK_E]))
    first_board = builder.root(first_observation)
    second_observation = printout(
        me=player(active=body(DRAGAPULT, 1, energies=(8,)), hand=[]))
    second_board, delta = builder.advance(first_board, second_observation)
    ending = action("end", (0,))
    search = LedgerOnePlySearch()
    model = EvaluationModel.build()
    first_evaluator = FirstEvaluator()
    second_evaluator = SecondEvaluator()

    first = search.search(
        EvaluationRequest(PreviewState(
            first_observation, first_board, "first", deck=DECK,
            deck_counts=first_board.deck_counts or ()), model),
        first_evaluator, UniformPolicyModel(), ScriptedProvider(
            menus={"first": (ending,)}, nodes={}), SearchConfiguration())
    assert first.baseline.evaluator_identity == FirstEvaluator.identity
    search.search(
        EvaluationRequest(PreviewState(
            second_observation, second_board, "second", deck=DECK,
            deck_counts=second_board.deck_counts or ()), model,
            first.baseline, delta),
        second_evaluator, UniformPolicyModel(), ScriptedProvider(
            menus={"second": (ending,)}, nodes={}), SearchConfiguration())

    assert second_evaluator.parent_states[0] is None


def test_forced_roster_marks_each_candidate_forced():
    select = {"type": 1, "context": 7, "minCount": 1, "maxCount": 1,
              "option": [{"type": 3, "index": 0}, {"type": 3, "index": 1}],
              "deck": None, "contextCard": None, "effect": None,
              "remainDamageCounter": 0, "remainEnergyCost": 0}
    observation = printout(me=player(active=body(DRAGAPULT, 1)), select=select)
    board = ObservationStateBuilder(DECK).root(observation)
    root = PreviewState(observation, board, "root", deck=DECK,
                        deck_counts=board.deck_counts or ())
    first, second = action("discard", (0,)), action("discard", (1,))
    landing = DecisionState.from_observation(
        printout(me=player(active=body(DRAGAPULT, 1))), deck=DECK,
        deck_name="test", value_registry_identity="test")
    provider = ScriptedProvider(
        menus={"root": (first, second)},
        nodes={("root", first.identity): Deterministic(landing),
               ("root", second.identity): Deterministic(landing)})

    result = LedgerOnePlySearch().search(
        EvaluationRequest(root, EvaluationModel.build()), LedgerValueEvaluator(),
        UniformPolicyModel(), provider, SearchConfiguration())

    assert result.roster.forced
    assert {candidate.disposition for candidate in result.roster.candidates} == {
        CandidateDisposition.FORCED}


def test_greedy_policy_ignores_unavailable_candidate_instead_of_scoring_it_zero():
    unavailable = ValuedCandidate(
        action("ability", (0,)), None, CandidateDisposition.CONTINUES_TURN,
        EvaluationStatus.UNAVAILABLE)
    ending = ValuedCandidate(
        action("end", (1,)),
        DecisionDelta(0.0, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN,
        EvaluationStatus.COMPLETE)

    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster((unavailable, ending)), PolicyConfiguration())

    assert chosen.action is ending.action
    assert chosen.reason == "best_turn_ender"


def test_greedy_policy_uses_explicit_end_as_the_zero_cost_waiting_baseline():
    continuing = ValuedCandidate(
        action("attach", (0,)),
        DecisionDelta(-0.12, LEDGER_VALUE_SCALE),
        CandidateDisposition.CONTINUES_TURN,
        EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(-0.12, 0.05, True),
    )
    ending = ValuedCandidate(
        action("end", (1,)),
        DecisionDelta(-0.23, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN,
        EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            -0.23, 0.0, False,
            realized_outcomes=(RealizedOutcome.EXPLICIT_TURN_END,)),
    )

    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster((continuing, ending)), PolicyConfiguration())

    assert chosen.action is ending.action
    assert chosen.reason == "best_turn_ender"


def test_greedy_policy_spends_a_continuation_that_beats_a_forced_ender():
    continuing = ValuedCandidate(
        action("attach", (0,)),
        DecisionDelta(-0.12, LEDGER_VALUE_SCALE),
        CandidateDisposition.CONTINUES_TURN,
        EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(-0.12, 0.05, True),
    )
    ending = ValuedCandidate(
        action("attack", (1,)),
        DecisionDelta(-0.23, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN,
        EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(-0.23, 0.0, False),
    )

    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster((continuing, ending)), PolicyConfiguration())

    assert chosen.action is continuing.action
    assert chosen.reason == "positive_continuation"


def test_positive_end_transition_does_not_hide_a_positive_continuation():
    continuing = ValuedCandidate(
        action("ability", (0,)), DecisionDelta(0.1, LEDGER_VALUE_SCALE),
        CandidateDisposition.CONTINUES_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(0.1, 0.0, True),
    )
    ending = ValuedCandidate(
        action("end", (1,)), DecisionDelta(0.3, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE,
    )

    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster((continuing, ending)), PolicyConfiguration())

    assert chosen.action is continuing.action


def test_forced_policy_includes_local_action_opportunity_when_ranking_choices():
    costly = ValuedCandidate(
        action("card", (0,)), DecisionDelta(0.1, LEDGER_VALUE_SCALE),
        CandidateDisposition.FORCED, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(0.1, -0.2, True),
    )
    cheaper = ValuedCandidate(
        action("card", (1,)), DecisionDelta(0.0, LEDGER_VALUE_SCALE),
        CandidateDisposition.FORCED, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(0.0, 0.0, True),
    )

    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster((costly, cheaper), forced=True), PolicyConfiguration())

    assert chosen.action is cheaper.action


def test_greedy_policy_prepares_a_body_before_an_eligible_hand_refresh():
    refresh = ValuedCandidate(
        action("play", (0,)), DecisionDelta(0.18, LEDGER_VALUE_SCALE),
        CandidateDisposition.CONTINUES_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            0.18, 0.0, True, zones_replaced=("hand",),
            allowances_consumed=("supporter_played",),
            opportunities_consumed=("play",)),
    )
    basic = ValuedCandidate(
        action("play", (1,)), DecisionDelta(-0.15, LEDGER_VALUE_SCALE),
        CandidateDisposition.CONTINUES_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            -0.15, 0.0, True, immediately_usable_outputs=("in_play",),
            opportunities_created=("future_evolve",),
            opportunities_preserved=("play",)),
    )
    ending = ValuedCandidate(
        action("end", (2,)), DecisionDelta(-0.1, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE,
    )

    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster((refresh, basic, ending)), PolicyConfiguration())

    assert chosen.action is basic.action


def test_greedy_policy_recognizes_knockout_only_from_observable_state_change():
    ending = ValuedCandidate(
        action("end", (0,)), DecisionDelta(0.0, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE)
    knockout = ValuedCandidate(
        action("attack", (1,)), DecisionDelta(
            1.0, LEDGER_VALUE_SCALE,
            (ValueComponent("prize.race", 1.0, 1.0, 1.0),)),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            1.0, 0.0, False,
            realized_outcomes=(RealizedOutcome.OPPONENT_ACTIVE_KNOCKOUT,
                               RealizedOutcome.ACTION_ENDED_TURN)))

    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster((ending, knockout)), PolicyConfiguration())

    assert chosen.action is knockout.action


def test_greedy_policy_takes_a_ready_knockout_over_a_non_prize_ender():
    ending = ValuedCandidate(
        action("end", (0,)), DecisionDelta(0.0, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE)
    knockout = ValuedCandidate(
        action("attack", (1,)), DecisionDelta(
            -1.0, LEDGER_VALUE_SCALE,
            (ValueComponent("prize.race", 1.0, -1.0, -1.0),)),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            -1.0, 0.0, False,
            realized_outcomes=(RealizedOutcome.OPPONENT_ACTIVE_KNOCKOUT,
                               RealizedOutcome.ACTION_ENDED_TURN)))

    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster((ending, knockout)), PolicyConfiguration())

    assert chosen.action is knockout.action


def test_greedy_policy_does_not_force_a_bench_knockout_over_active_damage():
    active_damage = ValuedCandidate(
        action("attack", (0,)), DecisionDelta(1.0, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE)
    bench_knockout = ValuedCandidate(
        action("attack", (1,)), DecisionDelta(
            0.5, LEDGER_VALUE_SCALE,
            (ValueComponent("prize.race", 1.0, 0.5, 0.5),)),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE)

    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster((active_damage, bench_knockout)), PolicyConfiguration())

    assert chosen.action is active_damage.action


def test_greedy_policy_does_not_let_negative_development_delay_active_knockout():
    development = ValuedCandidate(
        action("play", (0,)), DecisionDelta(-0.1, LEDGER_VALUE_SCALE),
        CandidateDisposition.CONTINUES_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            -0.1, 0.0, True,
            immediately_usable_outputs=("in_play",),
            opportunities_preserved=("end", "play")))
    knockout = ValuedCandidate(
        action("attack", (1,)), DecisionDelta(-1.0, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            -1.0, 0.0, False,
            realized_outcomes=(RealizedOutcome.OPPONENT_ACTIVE_KNOCKOUT,
                               RealizedOutcome.ACTION_ENDED_TURN)))
    ending = ValuedCandidate(
        action("end", (2,)), DecisionDelta(0.0, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE)

    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster((development, knockout, ending)), PolicyConfiguration())

    assert chosen.action is knockout.action


def test_greedy_policy_does_not_let_negative_evolution_delay_active_knockout():
    evolution = ValuedCandidate(
        action("evolve", (0,)), DecisionDelta(-0.1, LEDGER_VALUE_SCALE),
        CandidateDisposition.CONTINUES_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            -0.1, 0.0, True,
            immediately_usable_outputs=("in_play", "ready_attacker"),
            opportunities_preserved=("attack", "end", "play")))
    knockout = ValuedCandidate(
        action("attack", (1,)), DecisionDelta(-1.0, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            -1.0, 0.0, False,
            realized_outcomes=(RealizedOutcome.OPPONENT_ACTIVE_KNOCKOUT,
                               RealizedOutcome.ACTION_ENDED_TURN)))
    ending = ValuedCandidate(
        action("end", (2,)), DecisionDelta(0.0, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            0.0, 0.0, False,
            realized_outcomes=(RealizedOutcome.EXPLICIT_TURN_END,)))

    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster((evolution, knockout, ending)), PolicyConfiguration())

    assert chosen.action is knockout.action


def test_greedy_policy_keeps_raw_ranking_between_attacks_when_one_kos_active():
    knockout = ValuedCandidate(
        action("attack", (0,)), DecisionDelta(0.5, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            0.5, 0.0, False,
            realized_outcomes=(RealizedOutcome.OPPONENT_ACTIVE_KNOCKOUT,
                               RealizedOutcome.ACTION_ENDED_TURN)))
    stronger_attack = ValuedCandidate(
        action("attack", (1,)), DecisionDelta(1.0, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            1.0, 0.0, False,
            realized_outcomes=(RealizedOutcome.ACTION_ENDED_TURN,)))
    ending = ValuedCandidate(
        action("end", (2,)), DecisionDelta(2.0, LEDGER_VALUE_SCALE),
        CandidateDisposition.ENDS_TURN, EvaluationStatus.COMPLETE,
        continuation=ContinuationResult(
            2.0, 0.0, False,
            realized_outcomes=(RealizedOutcome.EXPLICIT_TURN_END,)))

    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster((knockout, stronger_attack, ending)), PolicyConfiguration())

    assert chosen.action is stronger_attack.action
