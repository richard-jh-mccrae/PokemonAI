"""Closed-form shuffle-refresh valuation; never samples or plans a hypothetical redraw."""
from __future__ import annotations

import copy
from collections import Counter
from math import sqrt

from .algebra import Ledger, Refresh
from .draws import draw_branches, draw_shape_problem
from .demand import DemandModel, access_probability
from .value import KNOWN_CARD_FLOOR, held_card_worth, worth_to_prizes


SHUFFLE_OWN_HAND_RIDER = "shuffle_own_hand_in"
SHUFFLE_BOTH_HANDS_RIDER = "shuffle_both_hands"
SHUFFLE_RIDERS = frozenset({SHUFFLE_OWN_HAND_RIDER, SHUFFLE_BOTH_HANDS_RIDER})
HELD_OPTION_FAMILIES = frozenset({"hand", "hand_demand", "prize_plan"})
HAND_SIZE_TACTICAL_FAMILIES = frozenset({"readiness"})
FUTURE_PAYOFF_ACCESS_DISCOUNT = 0.75


def played_card_id(state, action) -> int | None:
    """Resolve a MAIN play through the public hand/menu, without engine-private state."""
    if action.identity.kind != "play" or len(action.selection) != 1:
        return None
    observation = state.obs
    options = ((observation.get("select") or {}).get("option") or ())
    option_index = action.selection[0]
    if not 0 <= option_index < len(options):
        return None
    option = options[option_index]
    hand_index = option.get("index")
    current = observation.get("current") or {}
    option_seat = option.get("playerIndex")
    seat = state.root_seat if option_seat is None else int(option_seat)
    players = current.get("players") or ()
    player = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    hand = player.get("hand") or ()
    if not isinstance(hand_index, int) or not 0 <= hand_index < len(hand) or not hand[hand_index]:
        return None
    return int(hand[hand_index]["id"])


def refresh_transition(state, action, effects) -> Refresh | None:
    """Describe a generic shuffle-refresh as printed counts, with no sampled successor."""
    card_id = played_card_id(state, action)
    clauses = effects.clauses(card_id) if effects is not None and card_id is not None else ()
    candidates = tuple(clause for clause in clauses
                       if clause.get("kind") == "draw" and clause.get("rider") in SHUFFLE_RIDERS)
    if len(candidates) != 1 or draw_shape_problem(candidates[0]) is not None:
        return None
    current = state.obs.get("current") or {}
    players = current.get("players") or ()
    mine = players[state.root_seat] if len(players) > state.root_seat else {}
    opponent = players[1 - state.root_seat] if len(players) > 1 else {}
    branches = draw_branches(
        candidates[0], len(mine.get("prize") or ()), len(opponent.get("prize") or ()),
        my_hand_size=len(mine.get("hand") or ()),
    )
    if not branches:
        return None
    return Refresh(card_id, branches,
                   candidates[0].get("rider") == SHUFFLE_BOTH_HANDS_RIDER)


def _families(potential) -> dict[str, float]:
    return {str(name): float(value) for name, value in potential.families}


class RefreshEvaluator:
    """Exact draw Odds over Bellman hand value minus surrendered visible options."""

    def __init__(self, registry, family_evaluator, *, effects=None, stats=None, **_ignored):
        self.registry = registry
        self.family_evaluator = family_evaluator
        self.effects = effects
        self.stats = stats
        self.demand = DemandModel(registry, family_evaluator, effects=effects, stats=stats)

    def evaluate(self, state, node: Refresh, *, include_next_turn=True) -> tuple[Ledger, tuple[dict, ...]]:
        observation = state.obs
        current = observation.get("current") or {}
        players = current.get("players") or ()
        mine = players[state.root_seat] if len(players) > state.root_seat else {}
        opponent = players[1 - state.root_seat] if len(players) > 1 else {}
        hand = tuple(card for card in (mine.get("hand") or ())
                     if card and card.get("id") is not None)
        returned = [int(card["id"]) for card in hand]
        try:
            returned.remove(int(node.card_id))
        except ValueError:
            pass
        held_cost = self._held_option_cost(state, node.card_id)
        branch_rows = []
        demands = tuple(demand for demand in self.demand.immediate(observation, state.root_seat)
                        if demand.timing == "immediate")
        held_demand_cost = self.demand.covered_by_hand_value(
            demands, returned, supporter_available=state.budgets.supporter,
            discard_capacity=max(0, len(returned) - 1),
            available_targets=Counter(dict(state.deck_counts)),
            observation=observation, seat=state.root_seat)
        uncovered = self.demand.uncovered_by_hand(
            demands, returned, supporter_available=state.budgets.supporter,
            discard_capacity=max(0, len(returned) - 1),
            available_targets=Counter(dict(state.deck_counts)),
            observation=observation, seat=state.root_seat)
        weighted_draw = 0.0
        branch_probability = 1.0 / len(node.draws)
        for own_draw, opponent_draw in node.draws:
            draw_mean, draw_deviation = self._draw_value_moments(
                state, returned, int(own_draw))
            draw_value = max(0.0, draw_mean - draw_deviation)
            access_value = self._expected_board_access(
                state, uncovered, returned, int(own_draw))
            tactical = self._hand_size_tactical_delta(
                observation, state.root_seat, int(own_draw), int(opponent_draw),
                opponent_shuffles=node.opponent_shuffles,
            )
            opponent_value = (worth_to_prizes(
                KNOWN_CARD_FLOOR * (len(opponent.get("hand") or ())
                                    if opponent.get("hand") is not None
                                    else int(opponent.get("handCount", 0) or 0))
                - KNOWN_CARD_FLOOR * int(opponent_draw))
                              if node.opponent_shuffles else 0.0)
            weighted_draw += branch_probability * draw_mean
            branch_rows.append({
                "own_draw": int(own_draw), "opponent_draw": int(opponent_draw),
                "expected_hand_value": draw_mean,
                "hand_value_deviation": draw_deviation,
                "lower_confidence_hand_value": draw_value,
                "board_access_value": access_value,
                "held_demand_value": held_demand_cost,
                "hand_size_tactical": tactical,
                "opponent_hand": opponent_value,
            })
        benefits = {}
        costs = {}
        if held_cost > 0.0:
            costs["refresh_held_options"] = held_cost
        for label, value in (("refresh_expected_hand", weighted_draw),):
            if value > 0.0:
                benefits[label] = value
            elif value < 0.0:
                costs[label] = -value
        return (Ledger(tuple(sorted(benefits.items())), tuple(sorted(costs.items()))),
                tuple(branch_rows))

    def _potential(self, observation):
        return self.family_evaluator(observation)

    def _held_option_cost(self, state, played_card_id: int) -> float:
        observation = state.obs
        seat = state.root_seat
        retained = copy.deepcopy(observation)
        hand = retained["current"]["players"][seat].get("hand") or []
        retained["current"]["players"][seat]["handCount"] = len(hand)
        before = _families(self._potential(retained))
        stripped = copy.deepcopy(retained)
        player = stripped["current"]["players"][seat]
        player["hand"] = []
        player["handCount"] = 0
        after = _families(self._potential(stripped))
        total = sum(max(0.0, before.get(name, 0.0) - after.get(name, 0.0))
                    for name in HELD_OPTION_FAMILIES)
        capped_marginals = 0.0
        played_reconciled = False
        for index, card in enumerate(hand):
            without_card = copy.deepcopy(retained)
            without_hand = without_card["current"]["players"][seat]["hand"]
            without_hand.pop(index)
            without_card["current"]["players"][seat]["handCount"] = len(without_hand)
            families = _families(self._potential(without_card))
            marginal = sum(max(0.0, before.get(name, 0.0) - families.get(name, 0.0))
                           for name in HELD_OPTION_FAMILIES)
            card_id = int(card["id"])
            held_worth = held_card_worth(
                self.registry, self.effects, self.stats, state, card_id)
            component = (min(marginal, worth_to_prizes(held_worth))
                         if held_worth < self.registry.worth(card_id)
                         else marginal)
            if card_id == int(played_card_id) and not played_reconciled:
                component = max(component, worth_to_prizes(held_worth))
                played_reconciled = True
            capped_marginals += component
        return min(total, capped_marginals)

    def _draw_value_moments(self, state, returned, draws: int) -> tuple[float, float]:
        if draws <= 0:
            return 0.0, 0.0
        counts = Counter({int(card_id): int(count) for card_id, count in state.deck_counts})
        counts.update(int(card_id) for card_id in returned)
        total = sum(counts.values())
        if total <= 0:
            return 0.0, 0.0
        observation = copy.deepcopy(state.obs)
        player = observation["current"]["players"][state.root_seat]
        player["hand"] = []
        player["handCount"] = 0
        baseline = _families(self._potential(observation))
        population = []
        for card_id, count in counts.items():
            candidate = copy.deepcopy(observation)
            candidate_player = candidate["current"]["players"][state.root_seat]
            candidate_player["hand"] = [{"id": card_id, "playerIndex": state.root_seat}]
            candidate_player["handCount"] = 1
            families = _families(self._potential(candidate))
            marginal = sum(max(0.0, families.get(name, 0.0) - baseline.get(name, 0.0))
                           for name in HELD_OPTION_FAMILIES)
            population.extend((marginal,) * count)
        sample = min(int(draws), total)
        mean = sample * sum(population) / total
        if total <= 1 or sample >= total:
            return mean, 0.0
        population_mean = sum(population) / total
        population_variance = sum(
            (value - population_mean) ** 2 for value in population) / total
        variance = sample * (total - sample) / (total - 1) * population_variance
        return mean, sqrt(max(0.0, variance))

    def _expected_board_access(self, state, demands, returned, draws: int) -> float:
        if not demands or draws <= 0:
            return 0.0
        counts = Counter({int(card_id): int(count) for card_id, count in state.deck_counts})
        counts.update(int(card_id) for card_id in returned)
        pool = tuple(card_id for card_id, count in counts.items() for _ in range(count))
        values = [0.0] * len(demands)
        eligible = [set() for _demand in demands]
        for card_id in counts:
            tokens = self.demand.coverage_slots(
                card_id, demands, supporter_available=state.budgets.supporter,
                discard_capacity=max(0, int(draws) - 1), available_targets=counts,
                recipient_units=self.demand.energy_units_by_recipient(
                    state.obs, state.root_seat, card_id), resource_group=f"draw:{card_id}")
            for token in tokens:
                for edge in token:
                    eligible[edge.demand_index].add(card_id)
                    demand = demands[edge.demand_index]
                    payoff = 0.0
                    if demand.capability == "deploy":
                        line = next((line for line in self.registry.lines
                                     if card_id in line[:-1]), ())
                        if line:
                            payoff = (FUTURE_PAYOFF_ACCESS_DISCOUNT
                                      * self.registry.prizes(line[-1]))
                    values[edge.demand_index] = max(
                        values[edge.demand_index], edge.value + payoff)
        return sum(access_probability(pool, draws, card_ids) * values[index]
                   for index, card_ids in enumerate(eligible))

    def _hand_size_tactical_delta(self, observation, seat: int, own_draw: int,
                                  opponent_draw: int, *, opponent_shuffles: bool) -> float:
        before = _families(self._potential(observation))
        after_observation = copy.deepcopy(observation)
        players = after_observation["current"]["players"]
        players[seat]["hand"] = None
        players[seat]["handCount"] = int(own_draw)
        opponent_seat = 1 - seat
        if opponent_shuffles:
            players[opponent_seat]["hand"] = None
            players[opponent_seat]["handCount"] = int(opponent_draw)
        after = _families(self._potential(after_observation))
        return sum(after.get(name, 0.0) - before.get(name, 0.0)
                   for name in HAND_SIZE_TACTICAL_FAMILIES)


__all__ = ("RefreshEvaluator", "played_card_id", "refresh_transition")
