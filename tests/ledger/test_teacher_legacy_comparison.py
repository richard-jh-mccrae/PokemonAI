from agent_helpers import deck, strategy
from common.engine import CgpyTransitionProvider
from common.ledger import EvaluationModel
from cgpy.experiment import TurnSearchEnvironment
from cgpy.experiment.teacher import WithinHorizonTeacher
from deprecated.bellman import build_teacher_runtime
from real_engine_helpers import BodySpec, lock_main_allowances, observation, scenario


def test_current_teacher_matches_legacy_on_a_representative_starmie_turn():
    deck_name = "mega_starmie"
    engine, _runtime = scenario(
        deck_name,
        me_active=BodySpec((1030, 1031), energies=(3,)),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    lock_main_allowances(engine)
    root_observation = observation(engine)

    legacy = build_teacher_runtime(
        strategy(deck_name), deck(deck_name),
        provider_factory=CgpyTransitionProvider).decide(root_observation)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    current = WithinHorizonTeacher().search_environment(
        environment, evaluation_model=EvaluationModel.build(), experiment_seed=605)

    assert legacy.complete
    assert current.coverage.value == "complete"
    assert {action.action for action in current.root_actions} == {
        action.identity for action in environment.legal_actions(environment.root)}
    assert current.preferred_action == legacy.action
    assert current.preferred_action.kind == "attack"
