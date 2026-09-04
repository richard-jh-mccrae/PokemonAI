from cgpy.experiment import TurnSearchEnvironment
from common.decision.turn import NodeKind
from real_engine_helpers import BodySpec, lock_main_allowances, scenario
from common.decision import DecisionCoordinator, EvaluationStatus, PolicyConfiguration
from common.ledger import LedgerPolicyBaseline, LedgerPolicyConfiguration, LedgerPolicyModel
from common.ledger.decision import LedgerValueEvaluator
from common.puct import PuctConfiguration, PuctDecisionPolicy, PuctSearch
from common.decision.puct import PuctOutcome
import pytest
import json
from common.puct import dumps_decision


def test_lillie_sample_slots_resume_real_engine_without_eager_expansion():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(1227, 3),
        me_top=(3, 1030, 1223, 3, 1031, 17),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    lock_main_allowances(engine, supporter=False)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    play = next(action for action in environment.legal_actions(environment.root)
                if action.identity.kind == "play")
    chance = environment.transition(environment.root, play.identity).node
    assert chance.kind is NodeKind.CHANCE
    retained = environment.retained_states

    plan = environment.chance_plan(chance, 16)

    assert plan.estimated
    assert plan.probabilities == (1 / 16,) * 16
    assert environment.retained_states == retained
    first = environment.sample_for_search(chance, 607, 7)
    repeat = environment.sample_for_search(chance, 607, 7)
    assert first == repeat
    assert first.node.kind is NodeKind.PLAYER_DECISION
    assert len(first.node.observation.me.hand) > 0
    assert environment.legal_actions(first.node)
    environment.close()
    assert environment.retained_states == 0


def test_verified_reroot_preserves_unresolved_chance_slot_seeds():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(1159, 1227),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    lock_main_allowances(engine, supporter=False)
    previous = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    attach = next(action for action in previous.legal_actions(previous.root)
                  if action.identity.kind == "attach")
    prepared = previous.transition(previous.root, attach.identity).node
    play = next(action for action in previous.legal_actions(prepared) if action.identity.kind == "play")
    chance = previous.transition(prepared, play.identity).node
    reference = previous.sample_for_search(chance, 607, 7)
    current = TurnSearchEnvironment.from_engine(previous._node_state(prepared).engine, perspective_seat=0,
                                                knowledge=prepared.observation.knowledge)

    assert current.reuse_from(previous, prepared)
    repeated = current.sample_for_search(chance, 607, 7)

    assert repeated == reference
    previous.close()
    current.close()


@pytest.mark.parametrize("prior_limit", (1, 512))
def test_real_ledger_priors_are_bounded_and_search_continues_after_preparation_fallback(prior_limit):
    engine, agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(1227, 3),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    lock_main_allowances(engine, supporter=False)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    evaluator = LedgerValueEvaluator()
    model = agent.ledger.ctx
    baseline = LedgerPolicyBaseline("puct-test", evaluator.identity, (model.identity,), evaluator.value_scale.identity)
    policy = LedgerPolicyModel(LedgerPolicyConfiguration(
        8.0, 0.01, (EvaluationStatus.COMPLETE, EvaluationStatus.ESTIMATED)), baseline)
    coordinator = DecisionCoordinator(
        evaluator, model, PuctSearch(),
        PuctConfiguration(simulation_limit=24, prior_node_operations=prior_limit,
                          prior_total_operations=prior_limit * 2),
        policy, PuctDecisionPolicy(), PolicyConfiguration(), ledger_baseline_identity="puct-test")

    result = coordinator.decide(environment.root, provider=environment, strict=True)

    assert result.search.puct.outcome is PuctOutcome.SEARCHED, result.search.failure
    assert result.chosen is not None
    prior = result.search.puct.prior_distributions[0]
    assert prior.preparation_limited == (prior_limit == 1)
    if prior_limit == 1:
        assert prior.distribution.fallback_reason is not None
    else:
        assert prior.distribution.fallback_reason is None
        assert len({item.final_prior for item in prior.distribution.actions}) > 1
    assert result.search.puct.work.evaluations > 2
    assert environment.retained_states == 0
    record = json.loads(dumps_decision(result, environment.root.observation, coordinator.search_configuration))
    assert record["schema"] == "puct-decision"
    assert record["executed_action"] is None
    assert record["chosen_action"] is not None
    assert len(record["candidates"]) == len(environment.root.observation.legal_actions)
    assert record["evidence"]["resources"]
