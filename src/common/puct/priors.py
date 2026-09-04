from __future__ import annotations

from common.algebra import Actor, Chance, Deterministic, Terminal, WeightedEdge
from common.decision import CandidateDisposition, DecisionDelta, SearchConfiguration, ValuedCandidate
from common.decision.action_policy import admissible_actions
from common.decision.turn import NodeKind, SearchContractError
from common.ledger.decision import ledger_valuation_from_state
from common.ledger.preview import price_actions
from common.refresh import refresh_transition


def prepare_ledger_candidates(session, node, actions):
    bridge = _PreviewBridge(session)
    state = bridge.bind(node.state)
    compute = SearchConfiguration(
        time_budget_ms=None, chance_sample_budget=session.configuration.prior_chance_samples,
        chance_seed=session.configuration.seed)
    prices = price_actions(
        state, node.state.observation, node.valuation.total, bridge, session.request.evaluation_model,
        compute=compute, valuation_fn=lambda board: ledger_valuation_from_state(session.evaluate(board)),
        state_valuation_fn=session.evaluate)
    return tuple(ValuedCandidate(
        price.action, DecisionDelta(price.swing, node.valuation.scale),
        CandidateDisposition.ENDS_TURN if price.ends_turn else CandidateDisposition.CONTINUES_TURN,
        price.status, gaps=price.gaps) for price in prices)


class _PreviewBridge:
    def __init__(self, session):
        self.session = session
        self.nodes = {}
        self.root = None

    def bind(self, node):
        state = self.session.provider.ledger_state(node)
        self.nodes[id(state)] = node
        if self.root is None:
            self.root = state
        return state

    def actions(self, state):
        node = self.nodes[id(state)]
        actions = self.session.provider.legal_actions(node)
        if state is self.root:
            return actions
        return admissible_actions(node.observation, actions, self.session.configuration.action_policy)

    def actor(self, state):
        return Actor.OURS

    def before_chance_sample(self):
        return self.session.budget.begin_local("chances", creates_state=True)

    def transition(self, state, action):
        refresh = refresh_transition(state, action)
        if refresh is not None:
            return refresh
        node = self.session.transition(self.nodes[id(state)], action)
        return self.convert(node)

    def convert(self, node):
        if node.kind is NodeKind.UNAVAILABLE or node.failure:
            raise SearchContractError(node.failure or "unavailable prior transition")
        if node.kind is NodeKind.CHANCE:
            plan = self.session.provider.chance_plan(node, self.session.configuration.prior_chance_samples)
            children = tuple(WeightedEdge(
                probability, str(index), self.convert(self.session.sample(node, index)))
                for index, probability in enumerate(plan.probabilities))
            return Chance(children)
        state = self.bind(node)
        if node.kind in (NodeKind.TERMINAL, NodeKind.TURN_BOUNDARY, NodeKind.INFORMATION_BOUNDARY):
            return Terminal(state, node.kind.value)
        return Deterministic(state)
