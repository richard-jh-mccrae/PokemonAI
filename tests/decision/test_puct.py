from dataclasses import dataclass, replace
from types import SimpleNamespace
import time
import pytest

from common.api import ActionIdentity
from common.decision import (
    ActionChoiceIdentity, DecisionCoordinator, PolicyConfiguration, StateValuation, ValueScale,
)
from common.ledger.search import UniformPolicyModel
from common.puct import (PuctConfiguration, PuctDecisionPolicy, PuctSearch,
                         evaluation_profile, inspection_profile, play_profile)
from common.decision.turn import (DirectTurnSearchProvider, NodeKind, SearchNode,
                                  SearchStateKey)
from common.decision.turn import ChancePlan
from common.decision.puct import PuctEvidence, PuctOutcome
from common.observation import ObservationRecord, ObservationStateBuilder
from common.options import LegalAction
from ledger_helpers import DARK_E, DRAGAPULT, body, player, printout


SCALE = ValueScale("test-worth", 1)


def puct_evidence(result):
    evidence = result.search.evidence
    assert isinstance(evidence, PuctEvidence)
    return evidence


class GraphEnvironment:
    identity = "controlled-turn-graph-v1"

    def __init__(self, values, edges, *, root="root", seat=0, root_turn=1,
                 private="controlled", reuse_allowed=True):
        self.values = values
        self.edges = edges
        self.nodes = {}
        self.valuation_values = {}
        self.names = {}
        self.closed = False
        self.private = private
        self.reuse_allowed = reuse_allowed
        for index, name in enumerate(values):
            actions = tuple(LegalAction(ActionIdentity(label), (i,), ((i,),), ())
                            for i, (label, _) in enumerate(edges.get(name, ())))
            observation = replace(ObservationStateBuilder((DRAGAPULT, DARK_E) * 30).root(
                printout(me=player(active=body(DRAGAPULT, 1, hp=100 - index)))),
                seat=seat, legal_actions=actions)
            self.valuation_values[observation.position_key] = values[name]
            self.names[observation.position_key] = name
            self.nodes[name] = SearchNode(
                NodeKind.PLAYER_DECISION if actions else NodeKind.TURN_BOUNDARY,
                seat, seat, observation, SearchStateKey(f"{index:064x}"), root_turn, None, None, name)
        self.root = self.nodes[root]

    def legal_actions(self, node):
        return node.observation.legal_actions

    @property
    def retained_states(self):
        return len(self.nodes)

    def ledger_state(self, node):
        return node.observation

    def chance_plan(self, node, sample_count):
        raise SearchContractError("controlled node has no chance plan")

    def sample_for_search(self, node, experiment_seed, sample_index):
        raise SearchContractError("controlled node has no chance transition")

    def transition(self, node, action):
        successor = next(target for label, target in self.edges[self.names[node.observation.position_key]]
                         if label == action.kind)
        return SimpleNamespace(node=self.nodes[successor])

    def close(self):
        self.closed = True

    def reuse_from(self, previous, node):
        return (self.reuse_allowed and self.root.state_key == node.state_key
                and self.root.observation == node.observation)

    def reproduction_input(self):
        return f'{{"private":"{self.private}","schema":"controlled-graph-input","version":1}}'


class GraphEvaluator:
    identity = "controlled-value-v1"
    value_scale = SCALE
    accepted_model_identity = "controlled-model-v1"

    def __init__(self, values):
        self.values = values

    def evaluate(self, request):
        observation = request.state
        return StateValuation(observation.position_key, self.values[observation.position_key],
                              SCALE, observation.seat, self.identity,
                              evaluation_model_identity=request.evaluation_model.identity)


def decide(environment, configuration=None, *, search=None, policy=None, guard=None, evaluator=None):
    coordinator = DecisionCoordinator(
        evaluator=evaluator or GraphEvaluator(environment.valuation_values),
        evaluation_model=SimpleNamespace(identity="controlled-model-v1"),
        search=search or PuctSearch(),
        search_configuration=configuration or PuctConfiguration(simulation_limit=64),
        policy_model=policy or UniformPolicyModel(),
        decision_policy=PuctDecisionPolicy(), policy_configuration=PolicyConfiguration())
    return coordinator.decide(
        environment.root.observation,
        provider=environment,
        strict=True,
        execution_guard=guard,
    )


def test_direct_provider_contract_is_explicit_and_incomplete_providers_are_rejected():
    environment = GraphEnvironment({"root": 0.0}, {})
    assert isinstance(environment, DirectTurnSearchProvider)

    incomplete = SimpleNamespace(root=environment.root, identity="incomplete")
    coordinator = DecisionCoordinator(
        evaluator=GraphEvaluator(environment.valuation_values),
        evaluation_model=SimpleNamespace(identity="controlled-model-v1"),
        search=PuctSearch(), search_configuration=PuctConfiguration(simulation_limit=1),
        policy_model=UniformPolicyModel(), decision_policy=PuctDecisionPolicy(),
        policy_configuration=PolicyConfiguration())
    with pytest.raises(TypeError, match="supported provider contract"):
        coordinator.decide(incomplete.root.observation, provider=incomplete, strict=True)


class DelayGraphEvaluator(GraphEvaluator):
    def __init__(self, values, delayed_value):
        super().__init__(values)
        self.delayed_value = delayed_value

    def evaluate(self, request):
        if self.values[request.state.position_key] == self.delayed_value:
            time.sleep(20)
        return super().evaluate(request)


class BiasedPolicy:
    identity = "controlled-biased-prior-v1"

    def priors(self, request):
        distribution = UniformPolicyModel().priors(request)
        if len(distribution.actions) != 2:
            return distribution
        actions = tuple(
            replace(item, normalized_score=prior, final_prior=prior)
            for item, prior in zip(distribution.actions, (0.99, 0.01)))
        return replace(distribution, model_identity=self.identity,
                       configuration_identity=self.identity, actions=actions, actual_floor=0.01)


def test_puct_discovers_same_player_sequence_that_beats_greedy_leaf_value():
    environment = GraphEnvironment(
        {"root": 0.0, "setup": 0.0, "immediate": 3.0, "finish": 10.0, "waste": -2.0},
        {"root": (("setup", "setup"), ("immediate", "immediate")),
         "setup": (("finish", "finish"), ("waste", "waste"))})

    result = decide(environment)

    assert result.chosen is not None, result.search.outcome.failure
    assert result.chosen.identity == ActionIdentity("setup")
    assert result.roster.identities == (
        ActionChoiceIdentity(ActionIdentity("setup"), (0,)),
        ActionChoiceIdentity(ActionIdentity("immediate"), (1,)),
    )
    evidence = result.search.evidence
    assert isinstance(evidence, PuctEvidence)
    assert evidence.root_edges[0].statistics.visits > evidence.root_edges[1].statistics.visits
    assert evidence.root_edges[0].statistics.mean_value > 3.0
    assert evidence.simulations == 64
    assert tuple(step.action for step in evidence.principal_variation) == (
        ActionIdentity("setup"), ActionIdentity("finish"))
    assert evidence.principal_variation_stop_reason == "turn_boundary"


def test_tree_inspection_is_opt_in_and_contains_only_legal_observations():
    values = {"root": 0.0, "setup": 1.0, "finish": 4.0}
    edges = {"root": (("setup", "setup"), ("finish", "finish"))}

    ordinary = decide(
        GraphEnvironment(values, edges),
        PuctConfiguration(simulation_limit=2))
    inspected = decide(
        GraphEnvironment(values, edges, private="must-not-leak"),
        PuctConfiguration(simulation_limit=2),
        search=PuctSearch(capture_tree=True))

    assert puct_evidence(ordinary).inspection is None
    graph = puct_evidence(inspected).inspection
    assert graph is not None
    assert (puct_evidence(ordinary).configuration_identity
            == puct_evidence(inspected).configuration_identity)
    assert graph.root_node_id == 0
    assert len(graph.nodes) == 3
    assert len(graph.edges) == 2
    assert graph.nodes[0].visits == 2
    assert graph.nodes[0].outgoing_visits == 2
    assert graph.nodes[0].valuation.total == 0.0
    assert graph.nodes[0].valuation.components == ()
    assert graph.edges[0].action == ActionIdentity("setup")
    assert sum(edge.visits for edge in graph.edges) == 2
    leaves = [node for node in graph.nodes if node.depth == 1]
    assert sum(node.visits for node in leaves) == 2
    assert all(node.outgoing_visits == 0 for node in leaves)
    for node in graph.nodes:
        restored = ObservationRecord.loads(node.observation).to_state()
        assert restored.decision_key == node.decision_key
        assert "must-not-leak" not in node.observation


def test_puct_reports_measured_worker_transport_costs():
    environment = GraphEnvironment(
        {"root": 0.0, "left": 1.0, "right": 2.0},
        {"root": (("left", "left"), ("right", "right"))})

    result = decide(environment, PuctConfiguration(
        simulation_limit=2, worker_count=2, batch_size=2))

    transport = puct_evidence(result).transport
    assert transport.worker_count == 2
    assert transport.startup_seconds >= 0
    assert transport.request_messages > 0
    assert transport.response_messages >= transport.request_messages
    assert transport.request_bytes > 0
    assert transport.response_bytes > 0


def test_policy_priors_change_root_allocation_without_becoming_values():
    environment = GraphEnvironment(
        {"root": 0.0, "guided": 0.0, "better": 1.0},
        {"root": (("guided", "guided"), ("better", "better"))})

    result = decide(
        environment, PuctConfiguration(simulation_limit=8, exploration=100.0),
        policy=BiasedPolicy())

    guided, better = puct_evidence(result).root_edges
    distribution = puct_evidence(result).prior_distributions[0].distribution
    assert tuple(item.final_prior for item in distribution.actions) == (0.99, 0.01)
    assert guided.statistics.visits > better.statistics.visits
    assert guided.statistics.mean_value == 0.0


def test_transition_exhaustion_returns_completed_action_and_preserves_unvisited_roster():
    environment = GraphEnvironment(
        {"root": 0.0, "first": 1.0, "second": 2.0},
        {"root": (("first", "first"), ("second", "second"))})

    result = decide(environment, PuctConfiguration(simulation_limit=100, transition_limit=1))

    assert result.search.outcome.termination.code == "transition_limit", result.search.outcome.failure
    assert puct_evidence(result).work.transitions == 1
    assert puct_evidence(result).work.evaluations == 2
    assert len(result.roster.actions) == 2
    chosen_edge = next(edge for edge in puct_evidence(result).root_edges
                       if edge.choice == result.chosen_candidate.choice)
    assert chosen_edge.statistics.visits == 1
    unvisited = next(edge for edge in puct_evidence(result).root_edges
                     if not edge.statistics.visits)
    assert result.search.candidate_for(unvisited.choice).delta is None
    assert unvisited.statistics.mean_value is None


class CoinEnvironment(GraphEnvironment):
    def __init__(self):
        super().__init__(
            {"root": 0.0, "coin": 0.0, "safe": 4.0, "win": 10.0, "lose": 0.0},
            {"root": (("coin", "coin"), ("safe", "safe"))})
        self.nodes["coin"] = replace(self.nodes["coin"], kind=NodeKind.CHANCE)

    def chance_plan(self, node, sample_count):
        return ChancePlan(node.observation.decision_key, "coin", (0.5, 0.5), False)

    def sample_for_search(self, node, experiment_seed, sample_index):
        return SimpleNamespace(node=self.nodes["win" if sample_index else "lose"])


def test_chance_backup_averages_outcomes_and_reuses_realized_slots():
    result = decide(CoinEnvironment(), PuctConfiguration(simulation_limit=2000))

    assert result.chosen.identity == ActionIdentity("coin")
    chosen_edge = next(edge for edge in puct_evidence(result).root_edges
                       if edge.choice == result.chosen_candidate.choice)
    assert 4.5 < chosen_edge.statistics.mean_value < 5.5
    assert puct_evidence(result).work.chances == 2
    chance = puct_evidence(result).chance_nodes[0]
    assert chance.resolved_slots == 2
    assert chance.distinct_successors == 2
    assert chance.completed_visits == chosen_edge.statistics.visits


def test_initialization_exhaustion_stops_without_fabricating_an_action():
    environment = CoinEnvironment()
    result = decide(environment, PuctConfiguration(evaluation_limit=1))
    assert result.chosen is None
    assert puct_evidence(result).outcome is PuctOutcome.INITIALIZATION_DEGRADED
    assert puct_evidence(result).simulations == 0
    assert all(edge.statistics.visits == 0 for edge in puct_evidence(result).root_edges)
    assert environment.closed


def test_explicit_cancellation_is_not_reported_as_budget_exhaustion():
    from common.decision import DecisionCancellation

    cancellation = DecisionCancellation()
    cancellation.cancel()
    result = decide(CoinEnvironment(), guard=cancellation)

    assert result.chosen is None
    assert result.search.outcome.termination.code == "cancelled"
    assert puct_evidence(result).outcome is PuctOutcome.CANCELLED
    assert result.search.outcome.failure is None


class BrokenEnvironment(CoinEnvironment):
    def transition(self, node, action):
        if action.kind == "safe":
            raise RuntimeError("broken engine")
        return super().transition(node, action)


def test_hard_failure_stops_even_when_an_earlier_simulation_completed():
    environment = BrokenEnvironment()
    result = decide(environment)
    assert result.chosen is None
    assert puct_evidence(result).outcome is PuctOutcome.HARD_FAILURE
    assert puct_evidence(result).simulations >= 1
    assert result.search.outcome.failure.message == "broken engine"
    assert '"schema":"controlled-graph-input"' in puct_evidence(result).reproduction_input
    assert environment.closed


class PartlyUnavailableEnvironment(GraphEnvironment):
    def transition(self, node, action):
        result = super().transition(node, action)
        if action.kind == "unsupported":
            return SimpleNamespace(node=replace(
                result.node, kind=NodeKind.UNAVAILABLE,
                failure="focal hand update is unavailable"))
        return result


def test_explicitly_unavailable_action_is_excluded_without_hiding_the_gap():
    environment = PartlyUnavailableEnvironment(
        {"root": 0.0, "unsupported": 10.0, "supported": 1.0},
        {"root": (("unsupported", "unsupported"), ("supported", "supported"))})

    result = decide(environment, PuctConfiguration(simulation_limit=8))

    assert puct_evidence(result).outcome is PuctOutcome.SEARCHED
    assert result.chosen.identity == ActionIdentity("supported")
    rejected = puct_evidence(result).root_edges[0].statistics
    assert rejected.exclusion == "focal hand update is unavailable"
    assert rejected.visits == 0


def test_actual_single_action_bypasses_evaluation_and_simulation():
    environment = GraphEnvironment({"root": 0.0, "end": 1.0}, {"root": (("end", "end"),)})
    environment.valuation_values.clear()
    result = decide(environment)
    assert result.chosen.identity == ActionIdentity("end")
    assert puct_evidence(result).outcome is PuctOutcome.FORCED
    assert puct_evidence(result).work.evaluations == 0
    assert puct_evidence(result).simulations == 0
    assert result.baseline is None
    assert puct_evidence(result).principal_variation_stop_reason == "no_completed_edge"


def test_state_capacity_exhaustion_preserves_honest_resource_evidence():
    result = decide(CoinEnvironment(), PuctConfiguration(state_limit=1, batch_size=4))

    assert result.chosen is None
    assert result.search.outcome.termination.code == "state_limit"
    assert puct_evidence(result).work.state_capacity_charged == 1
    assert puct_evidence(result).work.transitions == 0
    assert puct_evidence(result).cache_entries == 1
    assert puct_evidence(result).cache_capacity_charged > puct_evidence(result).cache_entries


def test_joint_batches_have_identical_structural_evidence_across_worker_counts():
    results = [decide(CoinEnvironment(), PuctConfiguration(
        simulation_limit=96, batch_size=4, worker_count=workers)) for workers in (1, 2, 4)]
    reference = results[0]
    for result in results[1:]:
        assert result.chosen == reference.chosen
        assert result.roster == reference.roster
        assert puct_evidence(result).work == puct_evidence(reference).work
        assert puct_evidence(result).chance_nodes == puct_evidence(reference).chance_nodes
    assert puct_evidence(reference).batches == 24
    assert puct_evidence(reference).peak_pending == 4
    timing = puct_evidence(reference).timing
    assert timing.prior_seconds + timing.search_seconds + timing.overhead_seconds == pytest.approx(timing.elapsed_seconds)


def test_deadline_keeps_completed_batch_work_and_rejects_late_results():
    environment = GraphEnvironment(
        {"root": 0.0, "quick": 1.0, "slow": 2.0},
        {"root": (("quick", "quick"), ("slow", "slow"))})
    result = decide(
        environment,
        PuctConfiguration(simulation_limit=2, batch_size=2, worker_count=2,
                          time_limit_seconds=10, cleanup_reserve_seconds=1),
        evaluator=DelayGraphEvaluator(environment.valuation_values, 2.0))
    visits = tuple(edge.statistics.visits for edge in puct_evidence(result).root_edges)

    assert result.search.outcome.termination.code == "time_limit"
    assert puct_evidence(result).outcome is PuctOutcome.SEARCHED, (
        {item.category: (item.reserved, item.attempted, item.completed, item.uncertain)
         for item in puct_evidence(result).resources}, result.search.outcome.failure, visits)
    assert puct_evidence(result).simulations == 1
    assert sum(visits) == 1
    assert result.chosen.identity.kind == "quick"
    assert environment.closed
    time.sleep(0.05)
    assert tuple(edge.statistics.visits
                 for edge in puct_evidence(result).root_edges) == visits


def test_verified_reuse_can_choose_inherited_evidence_with_no_new_simulations():
    from common.decision import DecisionDeadlineExceeded

    class Expired:
        def check(self):
            raise DecisionDeadlineExceeded("match allowance exhausted")

    values = {"root": 0.0, "setup": 0.0, "immediate": 3.0, "finish": 10.0, "waste": -2.0}
    edges = {"root": (("setup", "setup"), ("immediate", "immediate")),
             "setup": (("finish", "finish"), ("waste", "waste"))}
    search = PuctSearch()
    configuration = PuctConfiguration(simulation_limit=64, reuse_tree=True)
    first = GraphEnvironment(values, edges)
    decide(first, configuration, search=search)
    second = GraphEnvironment(values, edges, root="setup")

    result = decide(second, configuration, search=search, guard=Expired())

    assert puct_evidence(result).outcome is PuctOutcome.SEARCHED
    assert result.chosen.identity.kind == "finish"
    assert puct_evidence(result).simulations == 0
    assert puct_evidence(result).inherited_visits > 0
    assert puct_evidence(result).reuse_reason == "verified_subtree"
    chosen_edge = next(edge for edge in puct_evidence(result).root_edges
                       if edge.choice == result.chosen_candidate.choice)
    assert chosen_edge.statistics.inherited_visits == chosen_edge.statistics.visits
    assert first.closed
    search.close()
    assert second.closed


def test_private_reproduction_input_does_not_change_legal_view_search():
    values = {"root": 0.0, "left": 1.0, "right": 2.0}
    edges = {"root": (("left", "left"), ("right", "right"))}
    results = [decide(GraphEnvironment(values, edges, private=value))
               for value in ("hidden-a", "hidden-b")]

    assert results[0].chosen == results[1].chosen
    assert results[0].roster == results[1].roster
    assert (puct_evidence(results[0]).reproduction_input
            != puct_evidence(results[1]).reproduction_input)


def test_prior_normalization_uses_preparation_allowance_and_falls_back_uniformly():
    environment = GraphEnvironment(
        {"root": 0.0, "guided": 0.0, "better": 1.0},
        {"root": (("guided", "guided"), ("better", "better"))})

    result = decide(
        environment,
        PuctConfiguration(simulation_limit=4, prior_node_operations=1,
                          prior_total_operations=1),
        policy=BiasedPolicy())

    evidence = puct_evidence(result).prior_distributions[0]
    assert evidence.preparation_limited
    assert evidence.distribution.fallback_reason.value == "requested_uniform"
    assert tuple(item.final_prior for item in evidence.distribution.actions) == (0.5, 0.5)


class NestedChanceEnvironment(GraphEnvironment):
    def __init__(self):
        super().__init__(
            {"root": 0.0, "draw": 0.0, "forced": 0.0, "safe": 1.0, "finish": 5.0},
            {"root": (("draw", "draw"), ("safe", "safe")),
             "forced": (("finish", "finish"),)})
        self.nodes["draw"] = replace(self.nodes["draw"], kind=NodeKind.CHANCE)
        self.nodes["forced"] = replace(self.nodes["forced"], kind=NodeKind.FORCED_DECISION)

    def chance_plan(self, node, sample_count):
        return ChancePlan(node.observation.decision_key, "nested-draw", (1.0,), True)

    def sample_for_search(self, node, experiment_seed, sample_index):
        return SimpleNamespace(node=self.nodes["forced"])


def test_nested_draw_interruption_does_not_redirect_into_a_cheaper_root_path():
    result = decide(
        NestedChanceEnvironment(),
        PuctConfiguration(simulation_limit=8, transition_limit=1),
        policy=BiasedPolicy())

    assert result.chosen.identity.kind == "draw"
    assert result.search.outcome.termination.code == "transition_limit", result.search.outcome.failure
    assert puct_evidence(result).outcome is PuctOutcome.SEARCHED
    assert puct_evidence(result).work.transitions == 1
    assert puct_evidence(result).work.chances == 1
    assert tuple(edge.statistics.visits
                 for edge in puct_evidence(result).root_edges) == (1, 0)


@pytest.mark.parametrize("limit,reason", (("node", "node_limit"), ("cache", "cache_limit")))
def test_tree_and_cache_caps_stop_before_an_unsupported_backup(limit, reason):
    configuration = (PuctConfiguration(node_limit=1, simulation_limit=4)
                     if limit == "node" else PuctConfiguration(cache_limit=1, simulation_limit=4))
    result = decide(GraphEnvironment(
        {"root": 0.0, "left": 1.0, "right": 2.0},
        {"root": (("left", "left"), ("right", "right"))}), configuration)

    assert result.chosen is None
    assert result.search.outcome.termination.code == reason
    assert puct_evidence(result).outcome is PuctOutcome.INITIALIZATION_DEGRADED


@pytest.mark.parametrize("factory,reason", (
    (lambda values, edges: (GraphEnvironment(values, edges),
                            GraphEnvironment(values, edges, root="setup", root_turn=2)),
     "configuration_or_horizon_changed"),
    (lambda values, edges: (GraphEnvironment(values, edges),
                            GraphEnvironment(values, edges, root="setup", reuse_allowed=False)),
     "ownership_or_state_unverified"),
    (lambda values, edges: (GraphEnvironment(values, edges),
                            GraphEnvironment(values, edges, root="missing")),
     "state_not_retained"),
))
def test_reuse_rejects_incompatible_horizon_ownership_and_outcome(factory, reason):
    from common.decision import DecisionDeadlineExceeded

    class Expired:
        def check(self):
            raise DecisionDeadlineExceeded("stop after reuse check")

    values = {"root": 0.0, "setup": 0.0, "other": 1.0, "finish": 2.0,
              "waste": -1.0, "missing": 0.0}
    edges = {"root": (("setup", "setup"), ("other", "other")),
             "setup": (("finish", "finish"), ("waste", "waste")), "missing": ()}
    first, second = factory(values, edges)
    search = PuctSearch()
    configuration = PuctConfiguration(simulation_limit=32, reuse_tree=True)
    decide(first, configuration, search=search)

    result = decide(second, configuration, search=search, guard=Expired())

    assert puct_evidence(result).reuse_reason == reason
    search.close()


@pytest.mark.parametrize("profile", (play_profile, inspection_profile, evaluation_profile))
def test_declared_profiles_run_the_same_bounded_puct_contract(profile):
    configuration = profile(
        "unknown-agent", reuse_tree=False, simulation_limit=4,
        transition_limit=8, evaluation_limit=8, chance_limit=8,
        state_limit=16, node_limit=16, cache_limit=24,
        time_limit_seconds=10, cleanup_reserve_seconds=1)
    result = decide(GraphEnvironment(
        {"root": 0.0, "left": 1.0, "right": 2.0},
        {"root": (("left", "left"), ("right", "right"))}), configuration)

    assert result.chosen is not None
    assert puct_evidence(result).configuration_identity == configuration.identity


def test_fresh_mode_discards_the_previous_tree():
    values = {"root": 0.0, "left": 1.0, "right": 2.0}
    edges = {"root": (("left", "left"), ("right", "right"))}
    search = PuctSearch()
    configuration = PuctConfiguration(simulation_limit=4, reuse_tree=False)
    first = GraphEnvironment(values, edges)
    decide(first, configuration, search=search)
    second = GraphEnvironment(values, edges)

    result = decide(second, configuration, search=search)

    assert puct_evidence(result).reuse_reason == "fresh_requested"
    assert first.closed and second.closed
