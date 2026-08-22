import pytest

from common.algebra import Deterministic
from common.decision import (
    CandidateDisposition,
    CandidateRoster,
    DecisionDelta,
    EvaluationRequest,
    EvaluationStatus,
    PolicyConfiguration,
    SearchConfiguration,
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

    def evaluate(self, request):
        board = getattr(request.state, "observation", request.state)
        self.calls[board.position_key] = self.calls.get(board.position_key, 0) + 1
        return super().evaluate(request)


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
