import hashlib
from dataclasses import dataclass, replace

import pytest

from common.api import ActionIdentity
from common.decision import EvaluationStatus, StateValuation, ValueScale
from common.ledger import EvaluationModel
from cgpy.experiment import (
    ChanceBranchKey,
    ChanceExpansion,
    ChanceExpansionStatus,
    ChanceSuccessor,
    ChanceTransition,
    NodeKind,
    PrimitiveTransition,
    SearchNode,
    SearchStateKey,
    ExperimentSnapshot,
    TurnSearchEnvironment,
)
from cgpy.experiment.teacher import WithinHorizonTeacher
from cgpy.experiment.teacher_contracts import (
    TeacherCoverage,
    TeacherSearchConfiguration,
    TeacherSearchResult,
)
from real_engine_helpers import BodySpec, lock_main_allowances, scenario
from teacher_helpers import end_only_snapshot


def test_teacher_public_api_is_available_from_experiment_package():
    from cgpy.experiment import (TeacherBatchRunner, TeacherCoverage,
                                 TeacherExecutionConfiguration,
                                 TeacherSearchConfiguration,
                                 WithinHorizonTeacher)

    assert WithinHorizonTeacher.identity.endswith("-v1")
    assert TeacherCoverage.COMPLETE.value == "complete"
    assert TeacherSearchConfiguration().time_cap_seconds == 600.0
    assert TeacherExecutionConfiguration().root_timeout_seconds == 660.0
    assert TeacherBatchRunner is not None


def _key(label: str) -> SearchStateKey:
    return SearchStateKey(hashlib.sha256(label.encode()).hexdigest())


def _node(label: str, kind: NodeKind) -> SearchNode:
    return SearchNode(kind, 0 if "decision" in kind.value else None, 0,
                      object(), _key(label), 1, None, None, object())


@dataclass(frozen=True)
class _Action:
    identity: ActionIdentity


class _GraphEnvironment:
    def __init__(self, root, edges, expansions=None):
        self.root = root
        self.edges = edges
        self.expansions = expansions or {}

    def legal_actions(self, node):
        return tuple(_Action(action) for action in self.edges.get(node.state_key.digest, ()))

    def transition(self, node, action):
        child = self.edges[(node.state_key.digest, action)]
        return PrimitiveTransition(
            node.state_key, action, child.state_key, child.kind,
            child.boundary_reason, child.failure, child)

    def expand(self, node, request):
        return self.expansions[node.state_key.digest]

    def node_kind(self, node):
        return node.kind

    def state_key(self, node):
        return node.state_key


class _Model:
    identity = "teacher-test-model"


class _Evaluator:
    identity = "teacher-test-evaluator"

    def __init__(self, values):
        self.values = values

    def evaluate(self, request):
        node = request.state
        return StateValuation(
            node.state_key.digest, self.values[node.state_key.digest],
            ValueScale("teacher-test", 1), 0, self.identity,
            status=EvaluationStatus.COMPLETE)


class _RootFailingEvaluator(_Evaluator):
    def evaluate(self, request):
        if request.state.state_key.digest == _key("root").digest:
            raise RuntimeError("root Ledger unavailable")
        return super().evaluate(request)


class _Clock:
    def __init__(self, values):
        self.values = iter(values)
        self.last = 0.0

    def __call__(self):
        self.last = next(self.values, self.last)
        return self.last


def test_teacher_compares_complete_root_actions_and_round_trips_result():
    root = _node("root", NodeKind.PLAYER_DECISION)
    alpha_leaf = _node("alpha-leaf", NodeKind.TURN_BOUNDARY)
    beta_leaf = _node("beta-leaf", NodeKind.TURN_BOUNDARY)
    alpha = ActionIdentity("alpha")
    beta = ActionIdentity("beta")
    environment = _GraphEnvironment(root, {
        root.state_key.digest: (alpha, beta),
        (root.state_key.digest, alpha): alpha_leaf,
        (root.state_key.digest, beta): beta_leaf,
    })
    values = {
        root.state_key.digest: 1.0,
        alpha_leaf.state_key.digest: 2.0,
        beta_leaf.state_key.digest: 4.5,
    }

    result = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605,
        configuration=TeacherSearchConfiguration())

    assert result.coverage is TeacherCoverage.COMPLETE
    assert result.preferred_action == beta
    assert [(item.action, item.expected_value, item.delta)
            for item in result.root_actions] == [
        (alpha, 2.0, 1.0), (beta, 4.5, 3.5)]
    assert result.selected_policy[0].action == beta
    assert tuple(step.action for step in result.principal_variation
                 if step.action is not None) == (beta,)
    assert result.best_full_sequence == (beta,)
    assert result.benchmark_ready is False
    assert TeacherSearchResult.loads(result.dumps()) == result


def test_unverified_baseline_identity_cannot_certify_teacher_output():
    root = _node("root", NodeKind.PLAYER_DECISION)
    leaf = _node("certification-leaf", NodeKind.TURN_BOUNDARY)
    action = ActionIdentity("advance")
    environment = _GraphEnvironment(root, {
        root.state_key.digest: (action,),
        (root.state_key.digest, action): leaf,
    })
    values = {root.state_key.digest: 0.0, leaf.state_key.digest: 1.0}

    result = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605,
        baseline_identity="not-a-verified-frozen-baseline")

    assert result.coverage is TeacherCoverage.COMPLETE
    assert result.baseline_identity == "not-a-verified-frozen-baseline"
    assert result.benchmark_ready is False


def test_unavailable_root_baseline_keeps_absolute_teacher_values_without_delta():
    root = _node("root", NodeKind.PLAYER_DECISION)
    leaf = _node("leaf", NodeKind.TURN_BOUNDARY)
    action = ActionIdentity("advance")
    environment = _GraphEnvironment(root, {
        root.state_key.digest: (action,),
        (root.state_key.digest, action): leaf,
    })

    result = WithinHorizonTeacher(
        _RootFailingEvaluator({leaf.state_key.digest: 8.0})).search_environment(
            environment, evaluation_model=_Model(), experiment_seed=605)

    assert result.coverage is TeacherCoverage.COMPLETE
    assert result.preferred_action == action
    assert result.root_actions[0].expected_value == 8.0
    assert result.root_actions[0].delta is None
    assert result.baseline_value is None
    assert result.baseline_quality is EvaluationStatus.UNAVAILABLE
    assert result.value_quality is EvaluationStatus.UNAVAILABLE
    assert result.benchmark_ready is False
    assert result.failure == "RuntimeError: root Ledger unavailable"


def _exact_chance_fixture():
    root = _node("chance-root", NodeKind.PLAYER_DECISION)
    chance = _node("chance", NodeKind.CHANCE)
    low = _node("low", NodeKind.TURN_BOUNDARY)
    high = _node("high", NodeKind.TURN_BOUNDARY)
    roll = ActionIdentity("roll")
    branches = tuple(ChanceBranchKey.exact(
        method="coin", index=index, root_state_key=root.state_key.digest,
        node_state_key=chance.state_key.digest, action=roll)
                     for index in range(2))
    probabilities = (0.25, 0.75)
    leaves = (low, high)
    transitions = tuple(ChanceTransition(
        chance.state_key, None, None, leaf.state_key, leaf.kind, None, None, leaf,
        branch_key=branch, method="coin", probability=probability)
                        for branch, probability, leaf in zip(
                            branches, probabilities, leaves))
    expansion = ChanceExpansion(
        chance.state_key, "coin", ChanceExpansionStatus.COMPLETE,
        transitions, tuple(ChanceSuccessor(
            probability, (branch,), leaf)
                           for branch, probability, leaf in zip(
                               branches, probabilities, leaves)),
        16, 12, 2, 2, 2)
    environment = _GraphEnvironment(root, {
        root.state_key.digest: (roll,),
        (root.state_key.digest, roll): chance,
    }, {chance.state_key.digest: expansion})
    values = {
        root.state_key.digest: 1.0,
        low.state_key.digest: 2.0,
        high.state_key.digest: 6.0,
    }
    return environment, values, branches, low, high


def test_teacher_backs_up_exact_chance_and_keeps_the_policy_branched():
    environment, values, branches, low, high = _exact_chance_fixture()

    result = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605)

    assert result.root_actions[0].expected_value == 5.0
    assert result.root_actions[0].delta == 4.0
    assert [(leaf.state_key, leaf.probability) for leaf in result.leaves] == [
        (low.state_key.digest, 0.25), (high.state_key.digest, 0.75)]
    assert result.best_full_sequence is None
    assert result.principal_variation[-1].branch_keys == (branches[1].digest,)


def test_chance_branch_cap_cannot_shrink_sampling_into_complete_evidence():
    environment, values, _branches, _low, _high = _exact_chance_fixture()

    result = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605,
        configuration=TeacherSearchConfiguration(chance_branch_cap=1))

    assert result.coverage is TeacherCoverage.INCOMPLETE
    assert result.preferred_action is None
    assert result.root_actions[0].stop_reason.value == "chance_cap"
    assert result.statistics.chance_branches == 1


def test_cycle_in_one_root_challenger_blocks_the_preferred_action():
    root = _node("cycle-root", NodeKind.PLAYER_DECISION)
    safe_leaf = _node("safe-leaf", NodeKind.TURN_BOUNDARY)
    loop = _node("loop", NodeKind.PLAYER_DECISION)
    safe = ActionIdentity("safe")
    enter = ActionIdentity("enter-loop")
    again = ActionIdentity("again")
    environment = _GraphEnvironment(root, {
        root.state_key.digest: (safe, enter),
        (root.state_key.digest, safe): safe_leaf,
        (root.state_key.digest, enter): loop,
        loop.state_key.digest: (again,),
        (loop.state_key.digest, again): loop,
    })
    values = {
        root.state_key.digest: 1.0,
        safe_leaf.state_key.digest: 2.0,
    }

    result = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605)

    assert result.coverage is TeacherCoverage.INCOMPLETE
    assert result.preferred_action is None
    assert result.root_actions[0].expected_value == 2.0
    assert result.root_actions[1].expected_value is None
    assert result.root_actions[1].stop_reason.value == "cycle"
    assert result.statistics.cycles == 1


def test_terminal_values_are_proven_and_unavailable_successor_blocks_ruling():
    root = _node("terminal-root", NodeKind.PLAYER_DECISION)
    win = _node("terminal-win", NodeKind.TERMINAL)
    unavailable = _node("terminal-unavailable", NodeKind.UNAVAILABLE)
    finish = ActionIdentity("finish")
    unknown = ActionIdentity("unknown")
    environment = _GraphEnvironment(root, {
        root.state_key.digest: (finish, unknown),
        (root.state_key.digest, finish): win,
        (root.state_key.digest, unknown): unavailable,
    })
    values = {root.state_key.digest: 0.0, win.state_key.digest: 1_000.0}

    result = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605)

    assert result.coverage is TeacherCoverage.INCOMPLETE
    assert result.preferred_action is None
    assert result.root_actions[0].expected_value == 1_000.0
    assert result.root_actions[0].leaves[0].kind is NodeKind.TERMINAL
    assert result.root_actions[1].coverage is TeacherCoverage.UNAVAILABLE


def test_current_environment_and_ledger_back_up_terminal_win_and_loss():
    engine, _runtime = scenario(
        "mega_starmie", me_active=BodySpec((1030,)),
        them_active=BodySpec((1030,)))
    lock_main_allowances(engine)
    root = TurnSearchEnvironment.from_engine(
        engine, perspective_seat=0).root
    terminal_nodes = []
    for winner in (0, 1):
        terminal = engine.fork()
        terminal.gs.result = winner
        terminal.gs.pending = None
        terminal_nodes.append(TurnSearchEnvironment.from_engine(
            terminal, perspective_seat=0).root)
    win, loss = ActionIdentity("win"), ActionIdentity("loss")
    environment = _GraphEnvironment(root, {
        root.state_key.digest: (win, loss),
        (root.state_key.digest, win): terminal_nodes[0],
        (root.state_key.digest, loss): terminal_nodes[1],
    })

    result = WithinHorizonTeacher().search_environment(
        environment, evaluation_model=EvaluationModel.build(), experiment_seed=605)

    assert result.coverage is TeacherCoverage.COMPLETE
    assert result.preferred_action == win
    assert all(action.leaves[0].kind is NodeKind.TERMINAL
               for action in result.root_actions)
    assert result.root_actions[0].expected_value > 0
    assert result.root_actions[1].expected_value < 0


def test_neutral_ties_are_reproducible():
    root = _node("tie-root", NodeKind.PLAYER_DECISION)
    leaf = _node("tie-leaf", NodeKind.TURN_BOUNDARY)
    alpha = ActionIdentity("alpha")
    beta = ActionIdentity("beta")
    environment = _GraphEnvironment(root, {
        root.state_key.digest: (alpha, beta),
        (root.state_key.digest, alpha): leaf,
        (root.state_key.digest, beta): leaf,
    })
    values = {root.state_key.digest: 0.0, leaf.state_key.digest: 1.0}

    first = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605)
    second = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605)

    assert first.preferred_action == second.preferred_action
    assert first.indifference_set == (alpha, beta)
    assert first.semantic_identity == second.semantic_identity


def test_node_cap_retains_completed_work_but_blocks_the_root_ruling():
    root = _node("cap-root", NodeKind.PLAYER_DECISION)
    first_leaf = _node("first-cap-leaf", NodeKind.TURN_BOUNDARY)
    second_leaf = _node("second-cap-leaf", NodeKind.TURN_BOUNDARY)
    first = ActionIdentity("first")
    second = ActionIdentity("second")
    environment = _GraphEnvironment(root, {
        root.state_key.digest: (first, second),
        (root.state_key.digest, first): first_leaf,
        (root.state_key.digest, second): second_leaf,
    })
    values = {
        root.state_key.digest: 0.0,
        first_leaf.state_key.digest: 1.0,
        second_leaf.state_key.digest: 2.0,
    }

    result = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605,
        configuration=TeacherSearchConfiguration(node_cap=2))

    assert result.coverage is TeacherCoverage.INCOMPLETE
    assert result.preferred_action is None
    assert result.root_actions[0].expected_value == 1.0
    assert result.root_actions[1].stop_reason.value == "node_cap"
    assert result.statistics.nodes_visited == 2


def test_long_finite_turn_does_not_use_python_recursion_as_a_horizon():
    root = _node("long-root", NodeKind.PLAYER_DECISION)
    decisions = tuple(_node(f"long-{index}", NodeKind.FORCED_DECISION)
                      for index in range(1_100))
    leaf = _node("long-leaf", NodeKind.TURN_BOUNDARY)
    start = ActionIdentity("start")
    edges = {
        root.state_key.digest: (start,),
        (root.state_key.digest, start): decisions[0],
    }
    for index, decision in enumerate(decisions):
        action = ActionIdentity("step", (index,))
        child = decisions[index + 1] if index + 1 < len(decisions) else leaf
        edges[decision.state_key.digest] = (action,)
        edges[(decision.state_key.digest, action)] = child
    environment = _GraphEnvironment(root, edges)
    values = {root.state_key.digest: 0.0, leaf.state_key.digest: 7.0}

    result = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605,
        configuration=TeacherSearchConfiguration(
            node_cap=2_000, path_node_cap=1_500))

    assert result.coverage is TeacherCoverage.COMPLETE
    assert result.root_actions[0].expected_value == 7.0
    assert len(result.best_full_sequence) == 1_101
    assert result.statistics.nodes_visited == 1_102


def test_time_and_path_caps_are_distinct_deterministic_node_boundaries():
    root = _node("boundary-root", NodeKind.PLAYER_DECISION)
    leaf = _node("boundary-leaf", NodeKind.TURN_BOUNDARY)
    action = ActionIdentity("advance")
    environment = _GraphEnvironment(root, {
        root.state_key.digest: (action,),
        (root.state_key.digest, action): leaf,
    })
    values = {root.state_key.digest: 0.0, leaf.state_key.digest: 1.0}

    timed = WithinHorizonTeacher(
        _Evaluator(values), clock=_Clock((0.0, 0.0, 11.0, 11.0))).search_environment(
            environment, evaluation_model=_Model(), experiment_seed=605,
            configuration=TeacherSearchConfiguration(time_cap_seconds=10.0))
    path_capped = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605,
        configuration=TeacherSearchConfiguration(path_node_cap=1))

    assert timed.root_actions[0].stop_reason.value == "time_cap"
    assert timed.statistics.nodes_visited == 1
    assert path_capped.root_actions[0].stop_reason.value == "path_cap"
    assert path_capped.statistics.nodes_visited == 1


def test_complete_transposition_is_reused_but_counted():
    root = _node("memo-root", NodeKind.PLAYER_DECISION)
    leaf = _node("memo-leaf", NodeKind.TURN_BOUNDARY)
    first = ActionIdentity("first-route")
    second = ActionIdentity("second-route")
    environment = _GraphEnvironment(root, {
        root.state_key.digest: (first, second),
        (root.state_key.digest, first): leaf,
        (root.state_key.digest, second): leaf,
    })
    values = {root.state_key.digest: 0.0, leaf.state_key.digest: 3.0}

    result = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605)

    assert result.coverage is TeacherCoverage.COMPLETE
    assert result.statistics.cache_hits == 1
    assert result.statistics.transpositions == 1
    assert result.statistics.leaf_evaluations == 1


def test_sampled_chance_is_complete_coverage_but_estimated_value_quality():
    environment, values, _branches, _low, _high = _exact_chance_fixture()
    chance_key = next(iter(environment.expansions))
    environment.expansions[chance_key] = replace(
        environment.expansions[chance_key],
        status=ChanceExpansionStatus.ESTIMATED, support_size=None)

    result = WithinHorizonTeacher(_Evaluator(values)).search_environment(
        environment, evaluation_model=_Model(), experiment_seed=605)

    assert result.coverage is TeacherCoverage.COMPLETE
    assert result.value_quality is EvaluationStatus.ESTIMATED
    assert result.root_actions[0].value_quality is EvaluationStatus.ESTIMATED


def test_elapsed_measurement_is_not_part_of_teacher_semantic_identity():
    root = _node("identity-root", NodeKind.PLAYER_DECISION)
    leaf = _node("identity-leaf", NodeKind.TURN_BOUNDARY)
    action = ActionIdentity("only")
    environment = _GraphEnvironment(root, {
        root.state_key.digest: (action,),
        (root.state_key.digest, action): leaf,
    })
    values = {root.state_key.digest: 0.0, leaf.state_key.digest: 1.0}

    immediate = WithinHorizonTeacher(
        _Evaluator(values), clock=_Clock((0.0,) * 5)).search_environment(
            environment, evaluation_model=_Model(), experiment_seed=605)
    slower = WithinHorizonTeacher(
        _Evaluator(values), clock=_Clock((10.0, 10.0, 10.0, 15.0))).search_environment(
            environment, evaluation_model=_Model(), experiment_seed=605)

    assert immediate.statistics.elapsed_seconds == 0.0
    assert slower.statistics.elapsed_seconds == 5.0
    assert immediate.semantic_identity == slower.semantic_identity


@pytest.mark.parametrize("deck_name", (
    "dragapult_ex", "mega_lucario", "mega_starmie"))
def test_teacher_traverses_a_real_complete_turn_for_each_deck(deck_name):
    snapshot = end_only_snapshot(deck_name)

    result = WithinHorizonTeacher().search(
        snapshot, evaluation_model=EvaluationModel.build(), experiment_seed=605)

    assert result.snapshot_id == snapshot.snapshot_id
    assert result.coverage is TeacherCoverage.COMPLETE
    assert len(result.root_actions) == 1
    assert result.preferred_action == result.root_actions[0].action
    assert result.leaves[0].kind is NodeKind.TURN_BOUNDARY
    assert result.statistics.nodes_visited == 2


@pytest.mark.parametrize(("deck_name", "active", "bench"), (
    ("dragapult_ex", BodySpec((119,), energies=(2,)), BodySpec((119,))),
    ("mega_lucario", BodySpec((677, 678), energies=(6,)), BodySpec((673, 674))),
    ("mega_starmie", BodySpec((1030, 1031), energies=(3,)), BodySpec((1030,))),
))
def test_teacher_completes_representative_real_turns_for_all_decks(
        deck_name, active, bench):
    engine, _runtime = scenario(
        deck_name, me_active=active, me_bench=(bench,), them_active=active)
    lock_main_allowances(engine)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)

    result = WithinHorizonTeacher().search_environment(
        environment, evaluation_model=EvaluationModel.build(), experiment_seed=605)

    assert result.coverage is TeacherCoverage.COMPLETE
    assert result.preferred_action is not None
    assert len(result.root_actions) >= 2
    assert all(action.best_full_sequence for action in result.root_actions)
    assert all(action.leaves for action in result.root_actions)
    if deck_name == "dragapult_ex":
        retreat = next(action for action in result.root_actions
                       if action.action.kind == "retreat")
        assert tuple(action.kind for action in retreat.best_full_sequence) == (
            "retreat", "energy", "card", "end")
