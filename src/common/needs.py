"""Deck-neutral demand and known-card coverage for Bellman value calculations.

This module describes value opportunities.  It never chooses an action, samples a hidden card,
steps a rules engine, or constructs a hypothetical draw.  The only future projection is the
deterministic next-turn legality of cards already visible in our hand.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from .fetch import REACH, WINDOW, fetch_target_matches


DEFAULT_BENCH_CAPACITY = 5
DEFAULT_ENERGY_CODE = 0
FETCHER_CARD_COUNT = 1
FLOAT_TIE_DIGITS = 12
MINIMUM_BODY_HP = 10
MINIMUM_ENERGY_UNITS = 1
NEXT_STAGE_OFFSET = 1
NEXT_TURN_OPTION_DISCOUNT = 0.75
TUTOR_STEP_DISCOUNT = 0.75


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
    fetched_targets: tuple[int, ...] = ()

    @property
    def target_path(self) -> tuple[int, ...]:
        if self.fetched_targets:
            return tuple(int(card_id) for card_id in self.fetched_targets)
        return (() if self.fetched_target is None else (int(self.fetched_target),))


@dataclass(frozen=True)
class NeedRoute:
    """One typed card chain leading to a currently valuable board operation."""

    need_index: int
    value: float
    path: tuple[int, ...]


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
                targets = (raw_edge.target_path if isinstance(raw_edge, CoverageEdge)
                           else (() if target is None else (int(target),)))
                if targets:
                    counts = list(available)
                    valid = True
                    for target_id in targets:
                        position = target_positions.get(int(target_id))
                        if position is None or counts[position] <= 0:
                            valid = False
                            break
                        counts[position] -= 1
                    if not valid:
                        continue
                    next_available = tuple(counts)
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

    def operation_gain_from(self, baseline: float, after) -> float:
        return max(0.0, float(self.potential(after).total - baseline))

    def immediate(self, observation, seat: int) -> tuple[Need, ...]:
        current = observation.get("current") or {}
        players = current.get("players") or ()
        mine = players[seat] if len(players) > seat else {}
        needs: list[Need] = []
        rows = tuple(body_rows(mine))
        baseline = float(self.potential(observation).total)

        for area, index, body in rows:
            if body.get("appearThisTurn"):
                continue
            target = self._next_stage(body.get("id"))
            if target is None:
                continue
            evolved = self._evolve(observation, seat, area, index, target)
            gain = self.operation_gain_from(baseline, evolved)
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
                    best = max(best, self.operation_gain_from(baseline, attached))
                if best > 0.0:
                    energy_edges[int(candidate)] = best
            if energy_edges:
                needs.append(Need("fund_attack", tuple(sorted(energy_edges.items()))))

        retreat_edges = self._retreat_edges(observation, seat, rows, baseline)
        if retreat_edges:
            needs.append(Need("retreat_access", tuple(sorted(retreat_edges.items()))))

        damage_edges = self._damage_edges(observation, seat, baseline)
        if damage_edges:
            needs.append(Need("damage_threshold", tuple(sorted(damage_edges.items()))))

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
            gain = self.operation_gain_from(baseline, deployed)
            if gain > 0.0:
                first_key = len(needs)
                needs.extend(Need(f"deploy_line:{first_key + offset}", ((base, gain),))
                             for offset in range(missing))
        return tuple(needs)

    def routes(self, card_id: int, needs: tuple[Need, ...], *,
               supporter_available: bool, discard_capacity: int,
               bench_capacity: int = DEFAULT_BENCH_CAPACITY, available_targets=None,
               _path: tuple[int, ...] = ()) -> tuple[NeedRoute, ...]:
        """Typed need routes reachable from one visible card.

        This is value propagation over printed fetch clauses. It does not select a target or invent
        a card: every downstream identity must have a remaining deck copy, and every edge remains a
        normal Bellman choice in the rules engine.
        """
        card_id = int(card_id)
        if card_id in _path:
            return ()
        path = (*_path, card_id)
        stat = self.stat(card_id)
        if stat is None:
            return ()
        is_supporter = bool(getattr(stat, "is_supporter", False))
        if is_supporter and not supporter_available:
            return ()

        routes = [NeedRoute(index, float(dict(need.direct).get(card_id, 0.0)), (card_id,))
                  for index, need in enumerate(needs)
                  if float(dict(need.direct).get(card_id, 0.0)) > 0.0]
        clauses = tuple(self.effects.clauses(card_id)) if self.effects is not None else ()
        next_supporter = supporter_available and not is_supporter
        for clause in clauses:
            if clause.get("kind") != "fetch" or clause.get("zone") != "deck":
                continue
            if any(clause.get(field) for field in ("dig", "condition", "name_family")):
                continue
            trigger = clause.get("trigger")
            if trigger not in (None, "on_bench_play"):
                continue
            if trigger == "on_bench_play" and bench_capacity <= 0:
                continue
            required_discards = discard_cost(clause) if clause.get("cost_required") else 0
            if required_discards > discard_capacity:
                continue
            target_counts = available_targets or {}
            for target, count in sorted(target_counts.items()):
                target = int(target)
                if count <= 0 or target in path:
                    continue
                if not fetch_target_matches(clause, self.stat(target), reading=WINDOW):
                    continue
                child = self.routes(
                    target, needs, supporter_available=next_supporter,
                    discard_capacity=max(0, discard_capacity - required_discards),
                    bench_capacity=max(0, bench_capacity - int(trigger == "on_bench_play")),
                    available_targets=available_targets, _path=path)
                routes.extend(NeedRoute(
                    route.need_index, TUTOR_STEP_DISCOUNT * route.value,
                    (card_id, *route.path))
                    for route in child)
        by_route = {(route.need_index, route.path): route for route in routes}
        return tuple(sorted(by_route.values(), key=lambda route: (
            route.need_index, -round(route.value, FLOAT_TIE_DIGITS), route.path)))

    def hand_access(self, needs: tuple[Need, ...], hand_ids, *,
                    supporter_available: bool, discard_capacity: int,
                    bench_capacity: int = DEFAULT_BENCH_CAPACITY,
                    available_targets=None) -> ResolvedAssignment:
        """Maximum compatible need coverage already available from the visible hand."""
        signatures = []
        for card_id in hand_ids:
            routes = self.routes(
                int(card_id), needs, supporter_available=supporter_available,
                discard_capacity=discard_capacity, bench_capacity=bench_capacity,
                available_targets=available_targets)
            signatures.append(tuple(CoverageEdge(
                route.need_index, route.value, fetched_targets=route.path[1:])
                for route in routes))
        return best_assignment(signatures, len(needs), target_counts=available_targets)

    def uncovered_by_direct_hand(self, needs: tuple[Need, ...], hand_ids, *,
                                 supporter_available: bool) -> tuple[Need, ...]:
        """Needs not already supplied by a playable card identity in the visible hand."""
        signatures = []
        for card_id in hand_ids:
            stat = self.stat(card_id)
            if (stat is not None and getattr(stat, "is_supporter", False)
                    and not supporter_available):
                signatures.append(())
                continue
            signatures.append(tuple(
                CoverageEdge(index, float(dict(need.direct).get(int(card_id), 0.0)))
                for index, need in enumerate(needs)
                if float(dict(need.direct).get(int(card_id), 0.0)) > 0.0))
        assignment = best_assignment(signatures, len(needs))
        return tuple(need for index, need in enumerate(needs)
                     if not assignment.covered_mask & (1 << index))

    def best_route(self, card_id: int, needs: tuple[Need, ...], **kwargs) -> NeedRoute | None:
        routes = self.routes(card_id, needs, **kwargs)
        return max(routes, key=lambda route: (
            round(route.value, FLOAT_TIE_DIGITS), -len(route.path), route.path), default=None)

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

    def _retreat_edges(self, observation, seat: int, rows, baseline: float) -> dict[int, float]:
        current = observation.get("current") or {}
        if current.get("retreated"):
            return {}
        mine = (current.get("players") or ())[seat]
        active = next((body for area, _index, body in rows if area == "active"), None)
        if active is None or not tuple(body for body in (mine.get("bench") or ()) if body):
            return {}
        tool_edges = {}
        for candidate in self.registry.facts:
            stat = self.stat(candidate)
            reduction = int(getattr(stat, "retreatReduction", 0) or 0) if stat else 0
            if reduction <= 0 or active.get("tools"):
                continue
            changed = copy.deepcopy(observation)
            changed_active = next(body for body in
                                  changed["current"]["players"][seat]["active"] if body)
            changed_active.setdefault("tools", []).append({"id": int(candidate)})
            gain = self.operation_gain_from(baseline, changed)
            player = changed["current"]["players"][seat]
            reserves = tuple(body for body in (player.get("bench") or ()) if body)
            for promoted_index, promoted in enumerate(reserves):
                switched = copy.deepcopy(changed)
                switched_player = switched["current"]["players"][seat]
                old_active = next(body for body in switched_player.get("active") or () if body)
                promoted_body = switched_player["bench"].pop(promoted_index)
                switched_player["active"] = [promoted_body]
                switched_player["bench"].append(old_active)
                switched["current"]["retreated"] = True
                gain = max(gain, self.operation_gain_from(baseline, switched))
            if gain > 0.0:
                tool_edges[int(candidate)] = gain
        best = max(tool_edges.values(), default=0.0)
        if best > 0.0:
            for candidate, tags in self.registry.functions.items():
                if "switch" in tags:
                    tool_edges[int(candidate)] = max(tool_edges.get(int(candidate), 0.0), best)
        return tool_edges

    def _damage_edges(self, observation, seat: int, baseline: float) -> dict[int, float]:
        edges = {}
        for candidate in self.registry.facts:
            stat = self.stat(candidate)
            amount = int(getattr(stat, "damageBoost", 0) or 0) if stat else 0
            if amount <= 0:
                continue
            changed = copy.deepcopy(observation)
            self._remove_one_hand_identity(changed, seat, int(candidate))
            transient = changed.setdefault("bellmanTransient", {})
            transient["damage_boosts"] = [*tuple(transient.get("damage_boosts") or ()), {
                "bonus": amount,
                "attackerEnergyType": getattr(stat, "damageBoostType", None),
                "defenderExOnly": bool(getattr(stat, "damageBoostVsEx", False)),
            }]
            gain = self.operation_gain_from(baseline, changed)
            if gain > 0.0:
                edges[int(candidate)] = gain
        return edges

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
    def _remove_one_hand_identity(observation, seat: int, card_id: int) -> None:
        hand = observation["current"]["players"][seat].get("hand")
        if hand is None:
            return
        position = next((index for index, card in enumerate(hand)
                         if card and int(card.get("id", 0)) == int(card_id)), None)
        if position is not None:
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
    "CoverageEdge", "Need", "NeedModel", "NeedRoute", "ResolvedAssignment", "RetainedAssignment",
    "RetainedOption", "best_assignment", "best_retained_assignment", "coverage_signature",
)
