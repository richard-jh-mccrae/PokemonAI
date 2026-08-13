"""Deck-neutral demand and known-card coverage for Bellman value calculations.

This module describes value opportunities.  It never chooses an action, samples a hidden card,
steps a rules engine, or constructs a hypothetical draw.  The only future projection is the
deterministic next-turn legality of cards already visible in our hand.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from .fetch import REACH, fetch_target_matches


DEFAULT_BENCH_CAPACITY = 5
DEFAULT_ENERGY_CODE = 0
FETCHER_CARD_COUNT = 1
FLOAT_TIE_DIGITS = 12
MINIMUM_BODY_HP = 10
MINIMUM_ENERGY_UNITS = 1
NEXT_STAGE_OFFSET = 1
NEXT_TURN_OPTION_DISCOUNT = 0.75


@dataclass(frozen=True)
class Need:
    """One board demand and the direct card identities that can satisfy it."""

    key: str
    direct: tuple[tuple[int, float], ...]
    timing: str = "immediate"


@dataclass(frozen=True)
class CoverageEdge:
    """A card's value when assigned to one need."""

    need_index: int
    value: float
    fetched_target: int | None = None


@dataclass(frozen=True)
class ResolvedAssignment:
    """Maximum non-duplicated assignment over card-to-need coverage."""

    value: float
    covered_mask: int
    used_card_mask: int = 0


@dataclass(frozen=True)
class RetainedOption:
    """A deterministic next-turn option requiring visible hand positions."""

    key: str
    required_cards: tuple[int, ...]
    value: float
    description: str


@dataclass(frozen=True)
class RetainedAssignment:
    """Best compatible set of deterministic next-turn options."""

    value: float
    options: tuple[RetainedOption, ...]


def body_rows(player):
    for area in ("active", "bench"):
        for index, body in enumerate(player.get(area) or ()):
            if body:
                yield area, index, body


def discard_cost(clause) -> int:
    cost = str(clause.get("cost") or "")
    if not cost.startswith("discard_"):
        return 0
    try:
        return max(0, int(cost.split("_", 1)[1]))
    except (TypeError, ValueError):
        return 0


def coverage_signature(edges: dict[int, float]) -> tuple[tuple[int, float], ...]:
    return tuple(sorted((int(index), round(float(value), FLOAT_TIE_DIGITS))
                        for index, value in edges.items() if value > 0.0))


def best_assignment(signatures, need_count: int, *, target_counts=None) -> ResolvedAssignment:
    """Assign tokens to needs without reusing a fetched deck target.

    Plain ``(need_index, value)`` pairs remain valid direct-resource edges. ``CoverageEdge`` adds
    an optional fetched target; its limited count is consumed only when that edge is selected.
    """
    target_counts = target_counts or {}
    target_ids = tuple(sorted(int(card_id) for card_id, count in target_counts.items() if count > 0))
    target_positions = {card_id: index for index, card_id in enumerate(target_ids)}
    initial_counts = tuple(int(target_counts[card_id]) for card_id in target_ids)
    dp = {(0, initial_counts): (0.0, 0)}
    for card_index, signature in enumerate(signatures):
        advanced = dict(dp)
        for (mask, available), (value, used) in dp.items():
            for raw_edge in signature:
                if isinstance(raw_edge, CoverageEdge):
                    need_index, edge_value, target = (
                        raw_edge.need_index, raw_edge.value, raw_edge.fetched_target)
                else:
                    need_index, edge_value = raw_edge
                    target = None
                bit = 1 << need_index
                if mask & bit:
                    continue
                next_available = available
                if target is not None:
                    position = target_positions.get(int(target))
                    if position is None or available[position] <= 0:
                        continue
                    next_available = (*available[:position], available[position] - 1,
                                      *available[position + 1:])
                new_mask = mask | bit
                candidate = (value + edge_value, used | (1 << card_index))
                state = (new_mask, next_available)
                previous = advanced.get(state)
                if (previous is None or
                        (round(candidate[0], FLOAT_TIE_DIGITS), candidate[1])
                        > (round(previous[0], FLOAT_TIE_DIGITS), previous[1])):
                    advanced[state] = candidate
        dp = advanced
    (mask, _available), (value, used) = max(
        dp.items(), key=lambda row: (round(row[1][0], FLOAT_TIE_DIGITS), row[0][0], row[1][1]))
    return ResolvedAssignment(value, mask, used)


def best_retained_assignment(options: tuple[RetainedOption, ...]) -> RetainedAssignment:
    """Weighted set packing over visible cards and mutually exclusive opportunity keys."""
    if not options:
        return RetainedAssignment(0.0, ())
    keys = {key: index for index, key in enumerate(sorted(
        {option.key for option in options}))}
    dp: dict[tuple[int, int], tuple[float, tuple[RetainedOption, ...]]] = {(0, 0): (0.0, ())}
    for option in options:
        card_mask = sum(1 << index for index in option.required_cards)
        key_mask = 1 << keys[option.key]
        advanced = dict(dp)
        for (used_cards, used_keys), (value, chosen) in dp.items():
            if used_cards & card_mask or used_keys & key_mask:
                continue
            state = (used_cards | card_mask, used_keys | key_mask)
            candidate = (value + option.value, (*chosen, option))
            previous = advanced.get(state)
            if previous is None or round(candidate[0], FLOAT_TIE_DIGITS) > round(
                    previous[0], FLOAT_TIE_DIGITS):
                advanced[state] = candidate
        dp = advanced
    value, chosen = max(dp.values(), key=lambda row: (
        round(row[0], FLOAT_TIE_DIGITS), tuple(option.description for option in row[1])))
    return RetainedAssignment(value, chosen)


class NeedModel:
    """Derive immediate demands and deterministic next-turn visible-hand options."""

    def __init__(self, registry, family_evaluator, *, effects=None, stats=None):
        self.registry = registry
        self.family_evaluator = family_evaluator
        self.effects = effects
        self.stats = stats

    def stat(self, card_id):
        return self.stats.get(int(card_id)) if self.stats is not None and card_id is not None else None

    def potential(self, observation):
        return self.family_evaluator(observation)

    def operation_gain(self, before, after) -> float:
        return max(0.0, float(self.potential(after).total - self.potential(before).total))

    def immediate(self, observation, seat: int) -> tuple[Need, ...]:
        current = observation.get("current") or {}
        players = current.get("players") or ()
        mine = players[seat] if len(players) > seat else {}
        needs: list[Need] = []
        rows = tuple(body_rows(mine))

        for area, index, body in rows:
            if body.get("appearThisTurn"):
                continue
            target = self._next_stage(body.get("id"))
            if target is None:
                continue
            evolved = self._evolve(observation, seat, area, index, target)
            gain = self.operation_gain(observation, evolved)
            if gain > 0.0:
                needs.append(Need(f"evolve:{area}:{index}", ((target, gain),)))

        if not bool(current.get("energyAttached")):
            energy_edges = {}
            for candidate in self.registry.facts:
                stat = self.stat(candidate)
                if stat is None or not getattr(stat, "is_energy", False):
                    continue
                best = 0.0
                for area, index, body in rows:
                    body_stat = self.stat(body.get("id"))
                    if body_stat is None or not tuple(getattr(body_stat, "attacks", ()) or ()):
                        continue
                    attached = copy.deepcopy(observation)
                    target_body = attached["current"]["players"][seat][area][index]
                    units = self._energy_units(candidate, target_body)
                    energy_type = getattr(stat, "energyType", None)
                    code = DEFAULT_ENERGY_CODE if energy_type is None else int(energy_type)
                    target_body.setdefault("energies", []).extend([code] * units)
                    target_body.setdefault("energyCards", []).append({"id": int(candidate)})
                    best = max(best, self.operation_gain(observation, attached))
                if best > 0.0:
                    energy_edges[int(candidate)] = best
            if energy_edges:
                needs.append(Need("fund_attack", tuple(sorted(energy_edges.items()))))

        bench_space = max(0, int(mine.get("benchMax", DEFAULT_BENCH_CAPACITY))
                          - len(mine.get("bench") or ()))
        for line in self.registry.lines:
            if not line or bench_space <= 0:
                continue
            base, payoff = int(line[0]), int(line[-1])
            desired = max((route.count(payoff) for route in self.registry.prize_routes), default=1)
            present = sum(int(body.get("id", 0)) in line for _area, _index, body in rows)
            missing = min(bench_space, max(0, desired - present))
            if missing <= 0:
                continue
            deployed = copy.deepcopy(observation)
            stat = self.stat(base)
            hp = int(getattr(stat, "hp", MINIMUM_BODY_HP) or MINIMUM_BODY_HP)
            deployed["current"]["players"][seat].setdefault("bench", []).append(
                {"id": base, "hp": hp, "maxHp": hp, "appearThisTurn": True,
                 "preEvolution": [], "energies": [], "energyCards": [], "tools": []})
            gain = self.operation_gain(observation, deployed)
            if gain > 0.0:
                first_key = len(needs)
                needs.extend(Need(f"deploy_line:{first_key + offset}", ((base, gain),))
                             for offset in range(missing))
        return tuple(needs)

    def coverage_slots(self, card_id: int, needs: tuple[Need, ...], *,
                       supporter_available: bool, discard_capacity: int,
                       available_targets=None) -> tuple[tuple[CoverageEdge, ...], ...]:
        """Independent resources a card can supply, respecting printed fetch capacity.

        A multi-target fetch contributes one assignment token per printed target.  The tokens are
        capped by matching targets still available in the deck, so a Tutor is never an out once all
        of its relevant targets are visible, discarded, or known prized.
        """
        edges = {index: dict(need.direct).get(int(card_id), 0.0)
                 for index, need in enumerate(needs)}
        edges = {index: value for index, value in edges.items() if value > 0.0}
        direct = tuple(CoverageEdge(index, value) for index, value in sorted(edges.items()))
        stat = self.stat(card_id)
        if stat is None or getattr(stat, "is_pokemon", False) or getattr(stat, "is_energy", False):
            return (direct,) if direct else ()
        if getattr(stat, "is_supporter", False) and not supporter_available:
            return (direct,) if direct else ()
        tokens = []
        clauses = tuple(self.effects.clauses(card_id)) if self.effects is not None else ()
        for clause in clauses:
            if clause.get("kind") != "fetch" or clause.get("zone") != "deck":
                continue
            if not all(not clause.get(field) for field in
                       ("trigger", "dig", "condition", "name_family")):
                continue
            if bool(clause.get("cost_required")) and discard_cost(clause) > discard_capacity:
                continue
            reachable = tuple(
                CoverageEdge(index, value, int(target))
                for index, need in enumerate(needs)
                for target, value in need.direct
                if (fetch_target_matches(clause, self.stat(target), reading=REACH)
                    and (available_targets is None
                         or int(available_targets.get(int(target), 0)) > 0))
            )
            matching_targets = {
                edge.fetched_target for edge in reachable
            }
            remaining_targets = (sum(int(available_targets.get(target, 0))
                                     for target in matching_targets)
                                 if available_targets is not None else len(matching_targets))
            printed_capacity = max(1, int(clause.get("amount", 1) or 1))
            for _ in range(min(printed_capacity, remaining_targets)):
                if reachable:
                    tokens.append(reachable)
        return tuple(token for token in (direct, *tokens) if token)

    def uncovered_by_hand(self, needs: tuple[Need, ...], hand_ids, *,
                          supporter_available: bool, discard_capacity: int,
                          available_targets=None) -> tuple[Need, ...]:
        signatures = []
        for card_id in hand_ids:
            stat = self.stat(card_id)
            if stat is not None and getattr(stat, "is_supporter", False):
                continue
            signatures.extend(self.coverage_slots(
                int(card_id), needs,
                supporter_available=supporter_available,
                discard_capacity=discard_capacity,
                available_targets=available_targets))
        assignment = best_assignment(signatures, len(needs), target_counts=available_targets)
        return tuple(need for index, need in enumerate(needs)
                     if not assignment.covered_mask & (1 << index))

    def next_turn_retained(self, observation, seat: int, hand_ids) -> RetainedAssignment:
        """Value deterministic next-turn uses of cards already visible now."""
        projected = self._next_turn_observation(observation, seat, hand_ids)
        original_player = observation["current"]["players"][seat]
        appeared = {(area, index) for area, index, body in body_rows(original_player)
                    if body.get("appearThisTurn")}
        options: list[RetainedOption] = []
        hand = projected["current"]["players"][seat].get("hand") or ()

        for area, index in sorted(appeared):
            body = projected["current"]["players"][seat][area][index]
            target = self._next_stage(body.get("id"))
            if target is None:
                continue
            for hand_index, card in enumerate(hand):
                if not card or int(card.get("id", 0)) != target:
                    continue
                evolved = self._evolve(projected, seat, area, index, target,
                                       consumed_cards=(hand_index,))
                gain = self.operation_gain(projected, evolved) * NEXT_TURN_OPTION_DISCOUNT
                if gain <= 0.0:
                    continue
                key = f"develop:{area}:{index}"
                option = RetainedOption(key, (hand_index,), gain,
                                        f"evolve:{area}:{index}:{target}")
                options.append(option)

        return best_retained_assignment(tuple(options))

    def _next_stage(self, card_id) -> int | None:
        card_id = int(card_id or 0)
        for line in self.registry.lines:
            if card_id in line[:-1]:
                return int(line[line.index(card_id) + NEXT_STAGE_OFFSET])
        return None

    def _evolve(self, observation, seat: int, area: str, index: int, target: int, *,
                consumed_cards: tuple[int, ...] = ()):
        evolved = copy.deepcopy(observation)
        self._remove_hand_positions(evolved, seat, consumed_cards)
        body = evolved["current"]["players"][seat][area][index]
        previous = int(body.get("id", 0))
        target_stat = self.stat(target)
        old_max = int(body.get("maxHp", body.get("hp", 0)) or 0)
        damage = max(0, old_max - int(body.get("hp", old_max) or 0))
        body.setdefault("preEvolution", []).append({"id": previous})
        body["id"] = int(target)
        body["appearThisTurn"] = True
        if target_stat is not None and int(getattr(target_stat, "hp", 0) or 0) > 0:
            body["maxHp"] = int(target_stat.hp)
            body["hp"] = max(MINIMUM_BODY_HP, int(target_stat.hp) - damage)
        return evolved

    def _energy_units(self, card_id: int, body) -> int:
        tags = self.registry.functions.get(int(card_id), ())
        base = self._tag_amount(tags, "provides:")
        evolution = self._tag_amount(tags, "provides_evo:") if body.get("preEvolution") else 0
        return max(MINIMUM_ENERGY_UNITS, base, evolution)

    @staticmethod
    def _tag_amount(tags, prefix: str) -> int:
        amounts = []
        for tag in tags:
            if not str(tag).startswith(prefix):
                continue
            try:
                amounts.append(max(0, int(str(tag).split(":", 1)[1])))
            except ValueError:
                continue
        return max(amounts, default=0)

    @staticmethod
    def _remove_hand_positions(observation, seat: int, positions) -> None:
        hand = observation["current"]["players"][seat].setdefault("hand", [])
        for position in sorted(set(int(value) for value in positions), reverse=True):
            if 0 <= position < len(hand):
                hand.pop(position)
        observation["current"]["players"][seat]["handCount"] = len(hand)

    @staticmethod
    def _next_turn_observation(observation, seat: int, hand_ids):
        projected = copy.deepcopy(observation)
        current = projected["current"]
        current["turn"] = int(current.get("turn", 0)) + 1
        current["supporterPlayed"] = False
        current["energyAttached"] = False
        current["retreated"] = False
        current["stadiumPlayed"] = False
        player = current["players"][seat]
        player["hand"] = [{"id": int(card_id)} for card_id in hand_ids]
        player["handCount"] = len(player["hand"])
        for _area, _index, body in body_rows(player):
            body["appearThisTurn"] = False
        return projected


__all__ = (
    "CoverageEdge", "Need", "NeedModel", "ResolvedAssignment", "RetainedAssignment",
    "RetainedOption", "best_assignment", "best_retained_assignment", "coverage_signature",
)
