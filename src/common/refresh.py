"""Closed-form shuffle-refresh valuation; never samples or plans a hypothetical redraw."""
from __future__ import annotations

import copy
from collections import Counter
from itertools import repeat
from math import comb

from .algebra import Ledger, Refresh
from .draws import draw_branches, draw_shape_problem
from .needs import NEXT_TURN_OPTION_DISCOUNT, Need, NeedModel, best_assignment
from .value import KNOWN_CARD_FLOOR, worth_to_prizes


SHUFFLE_OWN_HAND_RIDER = "shuffle_own_hand_in"
SHUFFLE_BOTH_HANDS_RIDER = "shuffle_both_hands"
SHUFFLE_RIDERS = frozenset({SHUFFLE_OWN_HAND_RIDER, SHUFFLE_BOTH_HANDS_RIDER})
HELD_OPTION_FAMILIES = frozenset({"hand", "prize_plan"})
HAND_SIZE_TACTICAL_FAMILIES = frozenset({"readiness"})
FETCHER_CARD_COUNT = 1


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


def _sample_distribution(counts: Counter, draws: int):
    """Exact multivariate-hypergeometric distribution over semantic coverage signatures."""
    total = sum(counts.values())
    draws = min(max(0, int(draws)), total)
    if draws == 0:
        return {(): 1.0}
    categories = tuple(sorted(((signature, int(count)) for signature, count in counts.items()
                               if count > 0), key=lambda row: repr(row[0])))
    denominator = comb(total, draws)
    outcomes: dict[tuple, float] = {}

    def visit(index: int, remaining: int, selected: tuple, ways: int) -> None:
        if index == len(categories):
            if remaining == 0:
                key = tuple(signature for signature, count in selected
                            for _ in repeat(None, count) if signature)
                outcomes[key] = outcomes.get(key, 0.0) + ways / denominator
            return
        signature, available = categories[index]
        for count in range(min(available, remaining) + 1):
            visit(index + 1, remaining - count, (*selected, (signature, count)),
                  ways * comb(available, count))

    visit(0, draws, (), 1)
    return outcomes


class RefreshEvaluator:
    """Expected current and next-turn Need coverage minus surrendered visible options."""

    def __init__(self, registry, family_evaluator, *, effects=None, stats=None, need_model=None):
        self.registry = registry
        self.family_evaluator = family_evaluator
        self.effects = effects
        self.stats = stats
        self.needs = need_model or NeedModel(
            registry, family_evaluator, effects=effects, stats=stats)

    def evaluate(self, state, node: Refresh, *, include_next_turn=True) -> tuple[Ledger, tuple[dict, ...]]:
        observation = state.obs
        current = observation.get("current") or {}
        players = current.get("players") or ()
        mine = players[state.root_seat] if len(players) > state.root_seat else {}
        opponent = players[1 - state.root_seat] if len(players) > 1 else {}
        current_needs = self.needs.immediate(observation, state.root_seat)
        immediate = tuple(need for need in current_needs if need.timing != "next_turn")
        hand = tuple(card for card in (mine.get("hand") or ())
                     if card and card.get("id") is not None)
        returned = [int(card["id"]) for card in hand]
        try:
            returned.remove(int(node.card_id))
        except ValueError:
            pass
        held_cost = self._held_option_cost(
            observation, state.root_seat, played_card_id=node.card_id)
        retained = self.needs.next_turn_retained(
            observation, state.root_seat, returned,
        )
        next_turn = (self.needs.new_next_turn_needs(
            observation, state.root_seat, current=current_needs)
                     if include_next_turn else ())
        branch_rows = []
        weighted_needs = weighted_next_turn = weighted_tactical = weighted_opponent = 0.0
        branch_probability = 1.0 / len(node.draws)
        for own_draw, opponent_draw in node.draws:
            uncovered = self.needs.uncovered_by_hand(
                immediate, returned,
                supporter_available=state.budgets.supporter,
                discard_capacity=max(0, len(returned) - FETCHER_CARD_COUNT),
                available_targets=Counter({int(card_id): int(count)
                                           for card_id, count in state.deck_counts}),
                observation=observation, seat=state.root_seat,
            )
            need_value = self._expected_need_value(
                state, uncovered, returned, int(own_draw),
                supporter_available=state.budgets.supporter,
            )
            next_turn_value = NEXT_TURN_OPTION_DISCOUNT * self._expected_need_value(
                state, self._root_value(next_turn), returned, int(own_draw),
                supporter_available=True)
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
            weighted_needs += branch_probability * need_value
            weighted_next_turn += branch_probability * next_turn_value
            weighted_tactical += branch_probability * tactical
            weighted_opponent += branch_probability * opponent_value
            branch_rows.append({
                "own_draw": int(own_draw), "opponent_draw": int(opponent_draw),
                "needs": tuple(need.key for need in uncovered),
                "need_value": need_value, "hand_size_tactical": tactical,
                "next_turn_needs": tuple(need.key for need in next_turn),
                "next_turn_need_value": next_turn_value,
                "opponent_hand": opponent_value,
            })
        benefits = {}
        costs = {}
        if held_cost > 0.0:
            costs["refresh_held_options"] = held_cost
        if retained.value > 0.0:
            costs["refresh_next_turn_options"] = retained.value
        for label, value in (("refresh_immediate_needs", weighted_needs),
                             ("refresh_next_turn_needs", weighted_next_turn),
                             ("refresh_hand_size_tactical", weighted_tactical),
                             ("refresh_opponent_hand", weighted_opponent)):
            if value > 0.0:
                benefits[label] = value
            elif value < 0.0:
                costs[label] = -value
        diagnostics = tuple({
            **row,
            "retained_options": tuple(option.description for option in retained.options),
            "retained_value": retained.value,
        } for row in branch_rows)
        return Ledger(tuple(sorted(benefits.items())), tuple(sorted(costs.items()))), diagnostics

    def _potential(self, observation):
        return self.family_evaluator(observation)

    @staticmethod
    def _root_value(needs):
        normalized = []
        for need in needs:
            root_value = max((value for _card_id, value in need.direct), default=0.0)
            normalized.append(Need(
                need.key, tuple((card_id, root_value) for card_id, _value in need.direct),
                timing=need.timing, recipient=need.recipient,
                capability=need.capability, slot=need.slot,
                ceiling=root_value, alternative=need.alternative))
        return tuple(normalized)

    def _held_option_cost(self, observation, seat: int, *, played_card_id: int) -> float:
        retained = copy.deepcopy(observation)
        hand = retained["current"]["players"][seat].get("hand") or []
        played_index = next((index for index, card in enumerate(hand)
                             if card and int(card.get("id", 0)) == int(played_card_id)), None)
        if played_index is not None:
            hand.pop(played_index)
        retained["current"]["players"][seat]["handCount"] = len(hand)
        before = _families(self._potential(retained))
        stripped = copy.deepcopy(retained)
        player = stripped["current"]["players"][seat]
        player["hand"] = []
        player["handCount"] = 0
        after = _families(self._potential(stripped))
        return sum(max(0.0, before.get(name, 0.0) - after.get(name, 0.0))
                   for name in HELD_OPTION_FAMILIES)

    def _expected_need_value(self, state, needs, returned, draws: int, *,
                             supporter_available: bool) -> float:
        if not needs or draws <= 0:
            return 0.0
        current = state.obs.get("current") or {}
        players = current.get("players") or ()
        mine = players[state.root_seat] if len(players) > state.root_seat else {}
        hidden_counts = Counter({int(card_id): int(count) for card_id, count in state.deck_counts})
        returned_counts = Counter(int(card_id) for card_id in returned)
        refreshed_counts = hidden_counts + returned_counts
        discard_capacity = max(0, int(draws) - FETCHER_CARD_COUNT)

        recipient_units = {
            card_id: self.needs.energy_units_by_recipient(state.obs, state.root_seat, card_id)
            for card_id in refreshed_counts
        }

        def semantic_counts(identity_counts):
            grouped = Counter()
            for card_id, count in identity_counts.items():
                slots = self.needs.coverage_slots(
                    card_id, needs, supporter_available=supporter_available,
                    discard_capacity=discard_capacity, available_targets=refreshed_counts,
                    recipient_units=recipient_units[card_id], resource_group="class")
                # Only card identities capable of filling one of these needs must remain distinct.
                # Every other identity is equivalent filler for this closed-form calculation.
                grouped[int(card_id) if slots else None] += count
            return grouped

        hidden_semantic = semantic_counts(hidden_counts)
        returned_semantic = semantic_counts(returned_counts)
        actual_deck = min(int(mine.get("deckCount", 0) or 0), sum(hidden_counts.values()))
        returned_total = sum(returned_counts.values())
        draws = min(int(draws), actual_deck + returned_total)
        denominator = comb(actual_deck + returned_total, draws)
        expected = 0.0
        minimum_returned = max(0, draws - actual_deck)
        maximum_returned = min(draws, returned_total)
        hidden_distributions = {}
        returned_distributions = {}
        for returned_draws in range(minimum_returned, maximum_returned + 1):
            hidden_draws = draws - returned_draws
            split = (comb(returned_total, returned_draws) * comb(actual_deck, hidden_draws)
                     / denominator)
            returned_distribution = returned_distributions.setdefault(
                returned_draws, _sample_distribution(returned_semantic, returned_draws))
            hidden_distribution = hidden_distributions.setdefault(
                hidden_draws, _sample_distribution(hidden_semantic, hidden_draws))
            for returned_signatures, returned_probability in returned_distribution.items():
                for hidden_signatures, hidden_probability in hidden_distribution.items():
                    drawn_ids = tuple(card_id for card_id in (
                        *returned_signatures, *hidden_signatures) if card_id is not None)
                    remaining_targets = refreshed_counts.copy()
                    remaining_targets.subtract(drawn_ids)
                    remaining_targets = Counter({card_id: count for card_id, count
                                                 in remaining_targets.items() if count > 0})
                    tokens = tuple(
                        token for resource_index, card_id in enumerate(drawn_ids)
                        for token in self.needs.coverage_slots(
                            card_id, needs, supporter_available=supporter_available,
                            discard_capacity=discard_capacity,
                            available_targets=remaining_targets,
                            recipient_units=recipient_units[card_id],
                            resource_group=f"drawn:{resource_index}"))
                    assignment = best_assignment(
                        tokens, len(needs), target_counts=remaining_targets)
                    expected += (split * returned_probability * hidden_probability
                                 * assignment.value)
        return expected

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
