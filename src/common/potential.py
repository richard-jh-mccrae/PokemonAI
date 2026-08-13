"""Deck-neutral terminal utility for full-turn Bellman search.

The evaluator contains no action policy and no card-specific behavior. It maps observable state
facts to prize-equivalent utility; the engine and Bellman recursion determine how actions change
those facts.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from math import comb

from .information import BellmanDeckProfile
from .damage import compute_active_damage
from .damage_context import SideFacts, damage_context
from .fetch import WINDOW, fetch_target_matches
from .needs import CoverageEdge, NeedModel, best_assignment
from .value import Potential, ValueRegistry, worth_to_prizes
from common.strategy.context import _ATTACH, _ATTACK, _DECK, _EVOLVE, _MAIN, _PLAY


ENERGY_COLORLESS = 0
ENERGY_WILDCARD = 10
MINIMUM_HP = 1
KNOCKED_OUT_HP = 0
TERMINAL_GAME_UTILITY = 100.0
DAMAGE_COUNTERS_PER_PRIZE = 200.0
DAMAGE_COUNTER_SIZE = 10
STANDARD_PRIZE_COUNT = 6
FUTURE_HAND_ACCESS_DISCOUNT = 0.75
FUTURE_ATTACK_ACCESS_DISCOUNT = FUTURE_HAND_ACCESS_DISCOUNT
OPPONENT_ROLE_PRESENCE_SHARE = 0.90
OPPONENT_ROLE_HEALTH_SHARE = 0.10
SAFE_DAMAGE_RESERVE_SHARE = 0.25
OPPONENT_ROLE_THREAT_SHARE = 0.20
OPPONENT_ROLE_WORTH_NORMALIZER = 30.0
BENCH_ATTACK_ACCESS_SHARE = 0.50
EVOLVED_BODY_PRIZE_SHARE = 0.040
_POTENTIAL_VOLATILE_KEYS = frozenset({
    "logs", "name", "remainingOverageTime", "serial", "step", "turnActionCount",
})


def _potential_semantic(value):
    if isinstance(value, dict):
        return {key: _potential_semantic(child) for key, child in value.items()
                if key not in _POTENTIAL_VOLATILE_KEYS}
    if isinstance(value, list):
        return [_potential_semantic(child) for child in value]
    if isinstance(value, tuple):
        return tuple(_potential_semantic(child) for child in value)
    return value


@dataclass(frozen=True)
class UtilityScale:
    """Only the lexicographic game result needs a scale above prize-equivalent state utility."""

    game: float = TERMINAL_GAME_UTILITY


def _bodies(player):
    return tuple(body for body in (
        tuple(player.get("active") or ()) + tuple(player.get("bench") or ())) if body)


def _energy_codes(body):
    codes = body.get("energies")
    if codes is not None:
        return [int(code) for code in codes]
    return [int(card.get("energyType", ENERGY_COLORLESS))
            for card in body.get("energyCards") or ()]


def _pay_fraction(codes, required) -> float:
    required = [int(code) for code in required]
    if not required:
        return 1.0
    remaining = list(codes)
    paid = 0
    for energy_type in (code for code in required if code != ENERGY_COLORLESS):
        index = next((index for index, code in enumerate(remaining)
                      if code in (energy_type, ENERGY_WILDCARD)), None)
        if index is not None:
            remaining.pop(index)
            paid += 1
    colorless = sum(code == ENERGY_COLORLESS for code in required)
    paid += min(colorless, len(remaining))
    return paid / len(required)


class BoardPotential:
    """Absolute observable-state utility used at every Bellman transition.

    Card identities enter only through the supplied card facts, declared deck relationships, and
    printed attacks. No action kind, named card, matchup, or tactical sequence is preferred here.
    """

    def __init__(self, stats, *, registry: ValueRegistry, effects=None,
                 profile: BellmanDeckProfile | None = None,
                 scale: UtilityScale = UtilityScale(), root_seat: int | None = None,
                 opponent_role_worth=None):
        self.stats = stats
        self.registry = registry
        self.effects = effects
        self.profile = profile or BellmanDeckProfile.from_registry(registry)
        self.scale = scale
        self.root_seat = None if root_seat is None else int(root_seat)
        self.opponent_role_worth = {int(card_id): max(0.0, float(worth))
                                    for card_id, worth in (opponent_role_worth or {}).items()}
        self._side_facts_cache = {}
        self._known_prize_counts = Counter()
        self._reachable_access_cache = {}
        self._reachable_source_cache = {}
        self._base_potential_cache = {}
        self._deriving_needs = False
        self._prepared_needs = None
        self._prepared_need_routes = {}
        self._prepared_hand_serials = frozenset()
        self._prepared_hand_counts = Counter()
        self._prepared_base_total = 0.0
        self._need_model = NeedModel(
            registry, self._potential_without_needs, effects=effects, stats=stats)

    def _potential_without_needs(self, observation) -> Potential:
        """Evaluate a hypothetical need outcome without recursively deriving that same demand."""
        key = self.cache_key(observation)
        cached = self._base_potential_cache.get(key)
        if cached is not None:
            return cached
        previous = self._deriving_needs
        self._deriving_needs = True
        try:
            potential = self(observation)
            self._base_potential_cache[key] = potential
            return potential
        finally:
            self._deriving_needs = previous

    @staticmethod
    def cache_key(observation) -> str:
        """Canonical key containing exactly the observation families read by this evaluator."""

        current = observation.get("current") or {}
        select = observation.get("select") or {}
        payload = {
            "current": _potential_semantic(current),
            "actor": observation.get("bellmanActor", current.get("yourIndex")),
            "transient": observation.get("bellmanTransient") or {},
            "select_context": select.get("context"),
            "attack_available": any(
                int(option.get("type", -1)) == _ATTACK for option in (select.get("option") or ())),
        }
        return hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()

    @lru_cache(maxsize=None)
    def _stat(self, card_id):
        return self.stats.get(int(card_id)) if self.stats and card_id is not None else None

    @lru_cache(maxsize=None)
    def _attack(self, attack_id):
        return self.stats.attack(int(attack_id)) if self.stats and attack_id is not None else None

    def _prizes(self, body) -> int:
        stat = self._stat(body.get("id"))
        return int(getattr(stat, "prize_value", 1) if stat is not None else 1)

    def _card_prizes(self, card_id: int) -> int:
        stat = self._stat(card_id)
        return int(getattr(stat, "prize_value", 1) if stat is not None else 1)

    def _side_facts(self, player, *, attacking_body=None, damage_boosts=()) -> SideFacts:
        cache_key = (id(player), id(attacking_body), repr(tuple(damage_boosts)))
        cached = self._side_facts_cache.get(cache_key)
        if cached is not None:
            return cached
        bodies = _bodies(player)
        active = attacking_body or next(
            (body for body in (player.get("active") or ()) if body), None)
        bench = tuple(body for body in (player.get("bench") or ()) if body)

        def stat_for(card):
            return self._stat(card.get("id")) if card else None

        def counters(body):
            maximum = int(body.get("maxHp", body.get("hp", 0)) or 0)
            return max(0, maximum - int(body.get("hp", maximum) or 0)) // DAMAGE_COUNTER_SIZE

        discard_stats = tuple(stat_for(card) for card in (player.get("discard") or ()))
        basic_by_type: dict[int, int] = {}
        for stat in discard_stats:
            if stat is None or not getattr(stat, "is_basic_energy", False):
                continue
            energy_type = getattr(stat, "energyType", None)
            if energy_type is not None:
                basic_by_type[int(energy_type)] = basic_by_type.get(int(energy_type), 0) + 1

        def card_name(body):
            stat = stat_for(body)
            return str(getattr(stat, "name", "") or "")

        def attack_names(body):
            stat = stat_for(body)
            if stat is None:
                return ()
            return tuple(str(getattr(self.stats.attack(attack_id), "name", "") or "")
                         for attack_id in (getattr(stat, "attacks", ()) or ()))

        boosts = []
        for tool in (active.get("tools") or ()) if active else ():
            stat = stat_for(tool)
            amount = int(getattr(stat, "damageBoost", 0) or 0) if stat is not None else 0
            if amount:
                boosts.append((amount, getattr(stat, "damageBoostType", None),
                               bool(getattr(stat, "damageBoostVsEx", False))))
        for modifier in damage_boosts:
            if not isinstance(modifier, dict):
                continue
            amount = int(modifier.get("bonus", 0) or 0)
            if amount:
                boosts.append((amount, modifier.get("attackerEnergyType"),
                               bool(modifier.get("defenderExOnly"))))

        deck_cards = tuple(player.get("deck") or ())
        deck_basic_by_type: dict[int, int] | None = {} if deck_cards else None
        if deck_basic_by_type is not None:
            for card in deck_cards:
                stat = stat_for(card)
                if stat is None or not getattr(stat, "is_basic_energy", False):
                    continue
                energy_type = getattr(stat, "energyType", None)
                if energy_type is not None:
                    deck_basic_by_type[int(energy_type)] = (
                        deck_basic_by_type.get(int(energy_type), 0) + 1)

        prize = player.get("prize")
        prizes_taken = STANDARD_PRIZE_COUNT - len(prize) if prize is not None else 0
        hand = player.get("hand")
        hand_size = len(hand) if hand is not None else int(player.get("handCount", 0) or 0)
        result = SideFacts(
            hand_size=hand_size,
            active_energy=len(_energy_codes(active)) if active else 0,
            bench_count=len(bench),
            prizes_taken=prizes_taken,
            active_counters=counters(active) if active else 0,
            counters_in_play=sum(counters(body) for body in bodies),
            bench_stage2=sum(bool(getattr(stat_for(body), "stage2", False)) for body in bench),
            ex_in_play=sum(bool(getattr(stat_for(body), "is_ex_body", False)) for body in bodies),
            discard_energy_total=sum(bool(getattr(stat, "is_energy", False))
                                     for stat in discard_stats if stat is not None),
            discard_basic_by_type=basic_by_type,
            bench_names=tuple(card_name(body) for body in bench),
            in_play_names=tuple(card_name(body) for body in bodies),
            in_play_attack_names=tuple(attack_names(body) for body in bodies),
            damage_boosts=tuple(boosts),
            deck_count=(len(deck_cards) if deck_cards else None),
            deck_basic_by_type=deck_basic_by_type,
        )
        self._side_facts_cache[cache_key] = result
        return result

    def _attack_value(self, body, codes, defender, attacker_facts, defender_facts, *,
                      terminal_if_ko: bool = False, terminal_access: float = 1.0) -> float:
        card_id = body.get("id")
        stat = self._stat(card_id)
        defender_stat = self._stat(defender.get("id")) if defender else None
        if stat is None or defender is None or defender_stat is None:
            return 0.0
        # Existing damage belongs exclusively to the damage-progress family. Readiness measures
        # repeatable attack capacity against the printed body, so attacking cannot manufacture a
        # second benefit merely by shrinking the defender's remaining HP denominator.
        hp = max(MINIMUM_HP, int(defender.get("maxHp", defender.get("hp", MINIMUM_HP))))
        prizes = self._prizes(defender)
        context = damage_context(attacker_facts, defender_facts)
        defender_tags = frozenset(self.registry.functions.get(int(defender.get("id", 0)), ()))
        best = 0.0
        for attack_id in getattr(stat, "attacks", ()) or ():
            attack = self.stats.attack(attack_id) if hasattr(self.stats, "attack") else None
            if attack is None:
                continue
            required = tuple(getattr(attack, "energyTypes", ()) or ())
            readiness = _pay_fraction(codes, required)
            damage = max(float(compute_active_damage(
                             attack, stat, defender_stat, defender_tags, context=context)),
                         float(getattr(attack, "benchSnipe", 0) or 0))
            payoff = (self.scale.game * terminal_access
                      if terminal_if_ko and damage >= hp and readiness >= 1.0
                      else prizes * min(1.0, damage / hp) * readiness)
            best = max(best, payoff)
        return best

    def _retreat_cost(self, body) -> int:
        stat = self._stat(body.get("id"))
        cost = int(getattr(stat, "retreatCost", 0) or 0) if stat is not None else 0
        for tool in body.get("tools") or ():
            tool_stat = self._stat(tool.get("id"))
            cost -= int(getattr(tool_stat, "retreatReduction", 0) or 0) \
                if tool_stat is not None else 0
        threshold = int(getattr(stat, "retreatFreeAtHp", 0) or 0) if stat is not None else 0
        if threshold and int(body.get("hp", 0) or 0) <= threshold:
            return 0
        return max(0, cost)

    def _can_retreat(self, player, body, *, available: bool) -> bool:
        if not available or player.get("asleep") or player.get("paralyzed"):
            return False
        return len(_energy_codes(body)) >= self._retreat_cost(body)

    def _attack_capacity_now(self, body, owner, opponent, defender_groups, *, damage_boosts=()) -> float:
        if not defender_groups:
            return 0.0
        values = []
        attacker_facts = self._side_facts(
            owner, attacking_body=body, damage_boosts=damage_boosts)
        defender_facts = self._side_facts(opponent)
        terminal_if_ko = len(_bodies(opponent)) == 1
        terminal_access = FUTURE_HAND_ACCESS_DISCOUNT ** sum(
            bool(modifier.get("future")) for modifier in damage_boosts
            if isinstance(modifier, dict))
        for access, defenders in defender_groups:
            value = min((self._attack_value(
                body, _energy_codes(body), defender,
                attacker_facts, defender_facts, terminal_if_ko=terminal_if_ko,
                terminal_access=terminal_access)
                         for defender in defenders), default=0.0)
            values.append(float(access) * value)
        return sum(values)

    @staticmethod
    def _promoted_owner(player, promoted):
        """Observable side state after moving one reserve body into the Active Spot."""

        current_active = tuple(body for body in (player.get("active") or ()) if body)
        reserves = tuple(body for body in (player.get("bench") or ()) if body)
        promoted_serial = promoted.get("serial")
        removed = False
        remaining = []
        for body in reserves:
            same = (promoted_serial is not None and body.get("serial") == promoted_serial) or \
                (promoted_serial is None and not removed and body is promoted)
            if same and not removed:
                removed = True
                continue
            remaining.append(body)
        moved = dict(player)
        moved["active"] = [promoted]
        moved["bench"] = [*remaining, *current_active]
        return moved

    @staticmethod
    def _evolution_inventory(owner):
        held = tuple(sorted(int(card["id"]) for card in (owner.get("hand") or ())
                            if card and card.get("id") is not None))
        visible = [*held]
        visible.extend(int(card["id"]) for card in (owner.get("discard") or ())
                       if card and card.get("id") is not None)
        for body in _bodies(owner):
            visible.extend(BoardPotential._stack_ids(body))
            visible.extend(BoardPotential._installed_ids(body))
        return held, tuple(sorted(visible))

    def _remaining_deck_pool(self, owner):
        remaining = Counter(dict(self.profile.deck_counts))
        _held, visible = self._evolution_inventory(owner)
        remaining.subtract(visible)
        remaining.subtract(self._known_prize_counts)
        return Counter({card_id: count for card_id, count in remaining.items() if count > 0})

    @staticmethod
    def _deck_presence_probability(copies: int, pool_size: int, deck_size: int) -> float:
        copies = max(0, min(int(copies), int(pool_size)))
        deck_size = max(0, min(int(deck_size), int(pool_size)))
        if not copies or not pool_size or not deck_size:
            return 0.0
        if pool_size - copies < deck_size:
            return 1.0
        return 1.0 - comb(pool_size - copies, deck_size) / comb(pool_size, deck_size)

    def _fetch_clauses(self, card_id: int):
        if self.effects is None:
            return ()
        return tuple(
            clause for clause in self.effects.clauses(card_id)
            if clause.get("kind") == "fetch" and clause.get("zone", "deck") == "deck"
            and not any(clause.get(field) for field in ("dig", "condition", "name_family"))
            and clause.get("trigger") in (None, "on_bench_play")
        )

    def _reachable_card_access(self, owner):
        """Maximum probability-discounted access through legal, typed fetch chains.

        This is generic graph reachability over effect clauses. It supplies successor potential for
        resources beyond the current turn; the rules engine remains authoritative for exact same-
        turn costs, supporter limits, and menus.
        """

        cache_key = id(owner)
        cached = self._reachable_access_cache.get(cache_key)
        if cached is not None:
            return cached
        hand = tuple(int(card["id"]) for card in (owner.get("hand") or ())
                     if card and card.get("id") is not None)
        access = {card_id: 1.0 for card_id in hand}
        source_access = {card_id: {card_id: 1.0} for card_id in access}
        frontier = [(card_id, card_id) for card_id in access]
        remaining = self._remaining_deck_pool(owner)
        pool_size = sum(remaining.values())
        deck_size = int(owner.get("deckCount", pool_size) or 0)
        bench_count = len(tuple(body for body in (owner.get("bench") or ()) if body))
        bench_max = int(owner.get("benchMax", 5) or 5)

        while frontier:
            origin, source = frontier.pop(0)
            path_access = source_access[origin][source]
            for clause in self._fetch_clauses(source):
                if clause.get("trigger") == "on_bench_play" and bench_count >= bench_max:
                    continue
                if clause.get("cost_required") and clause.get("cost") == "discard_2" \
                        and len(hand) < 3:
                    continue
                for target, copies in remaining.items():
                    stat = self._stat(target)
                    if not fetch_target_matches(clause, stat, reading=WINDOW):
                        continue
                    present = self._deck_presence_probability(copies, pool_size, deck_size)
                    candidate = path_access * FUTURE_HAND_ACCESS_DISCOUNT * present
                    if candidate <= source_access[origin].get(target, 0.0):
                        continue
                    source_access[origin][target] = candidate
                    access[target] = max(access.get(target, 0.0), candidate)
                    frontier.append((origin, target))
        result = access, remaining
        self._reachable_access_cache[cache_key] = result
        self._reachable_source_cache[cache_key] = source_access
        return result

    def _future_forms(self, body, owner):
        card_access, remaining = self._reachable_card_access(owner)
        pool_size = sum(remaining.values())
        evolved = dict(body)
        current_id = int(body.get("id", 0))
        for line in self.profile.lines:
            if current_id not in line[:-1]:
                continue
            access = 1.0
            position = line.index(current_id)
            for target in line[position + 1:]:
                availability = card_access.get(int(target))
                if availability is None:
                    copies = remaining.get(int(target), 0)
                    availability = (copies / pool_size) if pool_size else 0.0
                access *= FUTURE_ATTACK_ACCESS_DISCOUNT * availability
                if access <= 0.0:
                    break
                stat = self._stat(target)
                if stat is None:
                    break
                old_max = max(MINIMUM_HP, int(evolved.get(
                    "maxHp", evolved.get("hp", 0)) or 0))
                damage = max(0, old_max - int(evolved.get("hp", old_max) or 0))
                evolved = dict(evolved, id=int(target),
                               maxHp=int(getattr(stat, "hp", old_max) or old_max))
                evolved["hp"] = max(MINIMUM_HP, evolved["maxHp"] - damage)
                yield evolved, access

    def _body_attack_capacity(self, body, owner, opponent, defender_groups, *, future: bool,
                              damage_boosts=(), role_threat: bool = False) -> float:
        def weighted(candidate, value):
            if not role_threat:
                return value
            return value * (
                1.0 + OPPONENT_ROLE_THREAT_SHARE
                * self.opponent_role_worth.get(int(candidate.get("id", 0)), 0.0)
                / OPPONENT_ROLE_WORTH_NORMALIZER)

        value = weighted(body, self._attack_capacity_now(
            body, owner, opponent, defender_groups, damage_boosts=damage_boosts))
        if not future:
            return value
        candidates = [value]
        candidates.extend(
            access
            * weighted(form, self._attack_capacity_now(
                form, owner, opponent, defender_groups, damage_boosts=damage_boosts))
            for form, access in self._future_forms(body, owner))
        return max(candidates)

    def _damage_progress(self, player) -> float:
        total = 0.0
        for body in _bodies(player):
            maximum = max(MINIMUM_HP, int(body.get("maxHp", body.get("hp", MINIMUM_HP))))
            health = max(KNOCKED_OUT_HP, int(body.get("hp", maximum)))
            total += (maximum - health) / DAMAGE_COUNTERS_PER_PRIZE
        return total

    def _reachable_defenders(self, body, *, opponent_moves_next: bool):
        variants = [body]
        if not opponent_moves_next or not hasattr(self.stats, "forward_card_ids"):
            return tuple(variants)
        maximum = max(MINIMUM_HP, int(body.get("maxHp", body.get("hp", MINIMUM_HP))))
        damage = max(KNOCKED_OUT_HP, maximum - int(body.get("hp", maximum)))
        for card_id in self.stats.forward_card_ids(int(body.get("id", 0))) or ():
            if card_id not in self.opponent_role_worth:
                continue
            stat = self._stat(card_id)
            if stat is None:
                continue
            evolved = dict(body)
            evolved["id"] = int(card_id)
            evolved["maxHp"] = int(getattr(stat, "hp", maximum) or maximum)
            evolved["hp"] = max(MINIMUM_HP, evolved["maxHp"] - damage)
            variants.append(evolved)
        return tuple(variants)

    def _defender_groups(self, opponent, *, opponent_moves_next: bool):
        active = tuple(body for body in (opponent.get("active") or ()) if body)
        bench = tuple(body for body in (opponent.get("bench") or ()) if body)
        groups = [
            (1.0, self._reachable_defenders(body, opponent_moves_next=opponent_moves_next))
            for body in active
        ]
        reserve = [
            self._reachable_defenders(body, opponent_moves_next=True) for body in bench
        ]
        if reserve:
            # Only one opposing reserve can become the next Active. Preserve uncertainty within
            # each evolution family, then value the most consequential reachable reserve once.
            groups.append((FUTURE_ATTACK_ACCESS_DISCOUNT, max(
                reserve,
                key=lambda variants: max((self._prizes(body) for body in variants), default=0))))
        return tuple(groups)

    @staticmethod
    def _aggregate_readiness(active_now, active_future, bench_values, *, can_retreat,
                             attack_available):
        ordered = sorted(bench_values, reverse=True)
        reserve_value = sum(
            FUTURE_ATTACK_ACCESS_DISCOUNT ** (index + 1) * value
            for index, value in enumerate(ordered))
        if not attack_available:
            return (FUTURE_ATTACK_ACCESS_DISCOUNT * active_future
                    + FUTURE_ATTACK_ACCESS_DISCOUNT * reserve_value)
        stay = active_now + reserve_value
        if not (ordered and can_retreat):
            return stay
        promoted = (ordered[0]
                    + FUTURE_ATTACK_ACCESS_DISCOUNT * active_future
                    + sum(FUTURE_ATTACK_ACCESS_DISCOUNT ** (index + 1) * value
                          for index, value in enumerate(ordered[1:])))
        return max(stay, promoted)

    def _readiness_components(self, player, opponent, *, retreat_available: bool,
                              opponent_moves_next: bool, damage_boosts=(),
                              role_threat: bool = False):
        active = next((body for body in (player.get("active") or ()) if body), None)
        defender_groups = self._defender_groups(
            opponent, opponent_moves_next=opponent_moves_next)
        if not defender_groups:
            return active, defender_groups, 0.0, 0.0, [], False
        active_now = (self._body_attack_capacity(
            active, player, opponent, defender_groups, future=False,
            damage_boosts=damage_boosts, role_threat=role_threat)
                      if active is not None else 0.0)
        active_future = (self._body_attack_capacity(
            active, player, opponent, defender_groups, future=True,
            damage_boosts=damage_boosts, role_threat=role_threat)
                         if active is not None else 0.0)
        bench_values = [self._body_attack_capacity(
            body, self._promoted_owner(player, body), opponent, defender_groups, future=True,
            damage_boosts=damage_boosts, role_threat=role_threat)
            for body in (player.get("bench") or ()) if body]
        can_retreat = bool(active is not None and self._can_retreat(
            player, active, available=retreat_available))
        return active, defender_groups, active_now, active_future, bench_values, can_retreat

    def _side_readiness(self, player, opponent, *, retreat_available: bool,
                        attack_available: bool, opponent_moves_next: bool, damage_boosts=(),
                        role_threat: bool = False) -> float:
        _active, _defenders, active_now, active_future, bench_values, can_retreat = \
            self._readiness_components(
                player, opponent, retreat_available=retreat_available,
                opponent_moves_next=opponent_moves_next, damage_boosts=damage_boosts,
                role_threat=role_threat)
        return self._aggregate_readiness(
            active_now, active_future, bench_values, can_retreat=can_retreat,
            attack_available=attack_available)

    def _reachable_energy_codes(self, player):
        access, _remaining = self._reachable_card_access(player)
        codes = []
        for card_id, availability in access.items():
            facts = self.registry.facts.get(card_id)
            if facts is None or not (facts.typed_basic_energy or facts.energy_type is not None):
                continue
            stat = self._stat(card_id)
            energy_type = getattr(stat, "energyType", None) if stat is not None else None
            if energy_type is not None:
                codes.append((int(energy_type), float(availability)))
        return tuple(codes)

    def _hand_damage_boosts(self, player):
        """Printed damage modifiers presently reachable by playing cards from hand."""

        boosts = []
        for card in player.get("hand") or ():
            stat = self._stat(card.get("id")) if card else None
            amount = int(getattr(stat, "damageBoost", 0) or 0) if stat is not None else 0
            if amount:
                boosts.append({
                    "bonus": amount,
                    "attackerEnergyType": getattr(stat, "damageBoostType", None),
                    "defenderExOnly": bool(getattr(stat, "damageBoostVsEx", False)),
                    "future": True,
                })
        return tuple(boosts)

    @staticmethod
    def _with_energy(player, target, energy_type: int):
        target_serial = target.get("serial")
        changed = dict(player)
        for zone in ("active", "bench"):
            bodies = []
            used = False
            for body in player.get(zone) or ():
                same = (target_serial is not None and body.get("serial") == target_serial) or \
                    (target_serial is None and not used and body is target)
                if same and not used:
                    body = dict(body)
                    body["energies"] = [*_energy_codes(body), int(energy_type)]
                    used = True
                bodies.append(body)
            changed[zone] = bodies
        return changed

    def _readiness(self, me, opponent, *, retreat_available: bool,
                   attack_available: bool, opponent_moves_next: bool = False,
                   damage_boosts=(), manual_attach_available: bool = False) -> float:
        active, defender_groups, active_now, active_future, bench_values, can_retreat = \
            self._readiness_components(
                me, opponent, retreat_available=retreat_available,
                opponent_moves_next=opponent_moves_next, damage_boosts=damage_boosts)
        own = self._aggregate_readiness(
            active_now, active_future, bench_values, can_retreat=can_retreat,
            attack_available=attack_available)
        if manual_attach_available and defender_groups:
            alternatives = [own]
            for energy_type, access in self._reachable_energy_codes(me):
                for body_index, body in enumerate(_bodies(me)):
                    with_energy = self._with_energy(me, body, energy_type)
                    attached = _bodies(with_energy)[body_index]
                    next_active_now, next_active_future = active_now, active_future
                    next_bench = list(bench_values)
                    next_retreat = can_retreat
                    if body_index == 0 and active is not None:
                        next_active_now = self._body_attack_capacity(
                            attached, with_energy, opponent, defender_groups, future=False,
                            damage_boosts=damage_boosts)
                        next_active_future = self._body_attack_capacity(
                            attached, with_energy, opponent, defender_groups, future=True,
                            damage_boosts=damage_boosts)
                        next_retreat = self._can_retreat(
                            with_energy, attached, available=retreat_available)
                    else:
                        bench_index = body_index - (1 if active is not None else 0)
                        if not 0 <= bench_index < len(next_bench):
                            continue
                        next_bench[bench_index] = self._body_attack_capacity(
                            attached, self._promoted_owner(with_energy, attached), opponent,
                            defender_groups, future=True, damage_boosts=damage_boosts)
                    deployed = self._aggregate_readiness(
                        next_active_now, next_active_future, next_bench,
                        can_retreat=next_retreat, attack_available=attack_available)
                    alternatives.append(own + access * (deployed - own))
            best_attachment = max(alternatives)
            own += FUTURE_HAND_ACCESS_DISCOUNT * (best_attachment - own)
        incoming = self._side_readiness(
            opponent, me, retreat_available=True, attack_available=True,
            opponent_moves_next=False, role_threat=True)
        return own - incoming

    def _multi_target_ko_ready(self, me, opponent) -> float:
        """Prize value of a currently ready attack that can KO Active and Bench together."""
        defender = next((body for body in (opponent.get("active") or ()) if body), None)
        bench = tuple(body for body in (opponent.get("bench") or ()) if body)
        if defender is None or not bench:
            return 0.0
        defender_stat = self._stat(defender.get("id"))
        if defender_stat is None:
            return 0.0
        defender_facts = self._side_facts(opponent)
        defender_tags = frozenset(self.registry.functions.get(int(defender.get("id", 0)), ()))
        best = 0.0
        for body in _bodies(me):
            stat = self._stat(body.get("id"))
            if stat is None:
                continue
            context = damage_context(
                self._side_facts(me, attacking_body=body), defender_facts)
            codes = _energy_codes(body)
            for attack_id in getattr(stat, "attacks", ()) or ():
                attack = self._attack(attack_id)
                if attack is None or _pay_fraction(
                        codes, tuple(getattr(attack, "energyTypes", ()) or ())) < 1.0:
                    continue
                active_damage = compute_active_damage(
                    attack, stat, defender_stat, defender_tags, context=context)
                if active_damage < int(defender.get("hp", MINIMUM_HP)):
                    continue
                snipe = int(getattr(attack, "benchSnipe", 0) or 0)
                target_prizes = max((self._prizes(target) for target in bench
                                     if snipe >= int(target.get("hp", MINIMUM_HP))), default=0)
                if target_prizes:
                    best = max(best, float(self._prizes(defender) + target_prizes))
        return best

    def _lethal_exposure(self, defender_side, attacker_side) -> float:
        """Prize liability reachable by an opposing printed attack on a future turn."""
        active = next((body for body in (defender_side.get("active") or ()) if body), None)
        bench = tuple(body for body in (defender_side.get("bench") or ()) if body)
        if active is None:
            return 0.0
        active_stat = self._stat(active.get("id"))
        if active_stat is None:
            return 0.0
        active_tags = frozenset(self.registry.functions.get(int(active.get("id", 0)), ()))
        defender_facts = self._side_facts(defender_side)
        worst = 0.0
        for body in _bodies(attacker_side):
            stat = self._stat(body.get("id"))
            if stat is None:
                continue
            context = damage_context(
                self._side_facts(attacker_side, attacking_body=body), defender_facts)
            for attack_id in getattr(stat, "attacks", ()) or ():
                attack = self._attack(attack_id)
                if attack is None:
                    continue
                exposed = 0.0
                active_damage = compute_active_damage(
                    attack, stat, active_stat, active_tags, context=context)
                if active_damage >= int(active.get("hp", MINIMUM_HP)):
                    exposed += self._prizes(active)
                snipe = int(getattr(attack, "benchSnipe", 0) or 0)
                exposed += max((self._prizes(target) for target in bench
                                if snipe >= int(target.get("hp", MINIMUM_HP))), default=0)
                worst = max(worst, exposed)
        return -worst

    @staticmethod
    def _stack_ids(body):
        # Attached Energy and Tools are not generic board material. Their value is the mechanical
        # state they create (attack capacity, HP, damage, retreat access); counting their card Worth
        # as well would pay merely for moving them out of the hand and reward useless attachments.
        rows = [body]
        rows.extend(body.get("preEvolution") or ())
        return tuple(int(card.get("id") if isinstance(card, dict) else card)
                     for card in rows
                     if card is not None and (not isinstance(card, dict) or card.get("id") is not None))

    @staticmethod
    def _installed_ids(body):
        return tuple(int(card["id"]) for card in (body.get("tools") or ())
                     if card and card.get("id") is not None)

    def _resource_job(self, card_id: int):
        roles = tuple(sorted(self.registry.roles.get(card_id, ())))
        functions = tuple(sorted(tag for tag in self.registry.functions.get(card_id, ())
                                 if not str(tag).startswith("provides:")))
        facts = self.registry.facts.get(card_id)
        category = "pokemon" if facts is not None and facts.pokemon else "card"
        return (("role", roles[0], category) if roles else
                ("function", functions[0], category) if functions else
                ("card", card_id, category))

    def _prize_job_capacities(self):
        capacities = {}
        for route in self.profile.prize_routes:
            counts = Counter(self._resource_job(int(card_id)) for card_id in route)
            for card_job, count in counts.items():
                capacities[card_job] = max(capacities.get(card_job, 1), count)
        return capacities

    @staticmethod
    def _job_limit(card_job, values, capacities):
        # Persistent Pokémon compete for one structural job unless the declared prize route needs
        # more. Physical consumables remain independently usable; collapsing them would make one
        # copy free to spend whenever another copy remains in hand.
        _kind, _name, category = card_job
        return capacities.get(card_job, 1 if category == "pokemon" else len(values))

    def _board_resources(self, me) -> float:
        capacities = self._prize_job_capacities()
        body_ids = {int(body.get("id", 0)) for body in _bodies(me)}
        held_ids = {int(card["id"]) for card in (me.get("hand") or ())
                    if card and card.get("id") is not None}
        accessible_ids = body_ids | held_ids
        required_partners = dict(self.profile.partners)
        jobs: dict[tuple, list[float]] = {}
        for body in _bodies(me):
            for card_id in self._stack_ids(body):
                partners = required_partners.get(card_id, ())
                if partners and not set(partners).issubset(accessible_ids):
                    continue
                missing = len(set(partners) - body_ids)
                jobs.setdefault(self._resource_job(card_id), []).append(
                    FUTURE_HAND_ACCESS_DISCOUNT ** missing * self.registry.worth(card_id))
            for card_id in self._installed_ids(body):
                jobs.setdefault(self._resource_job(card_id), []).append(
                    FUTURE_HAND_ACCESS_DISCOUNT * self.registry.worth(card_id))
        worth = sum(sum(sorted(values, reverse=True)[:self._job_limit(
                        card_job, values, capacities)])
                    for card_job, values in jobs.items())
        return float(worth_to_prizes(worth))

    def _development(self, me) -> float:
        """Value realized by turning a line piece into a developed body.

        The retained pre-evolution stack already proves that development occurred.  Scale the
        improvement by the evolved body's prize liability so the term stays card- and deck-neutral.
        """
        return sum(self._prizes(body) * EVOLVED_BODY_PRIZE_SHARE
                   for body in (me.get("bench") or ()) if body and body.get("preEvolution"))

    def _hand_resources(self, me, *, setup_complete: bool = False) -> float:
        capacities = self._prize_job_capacities()
        occupied = Counter(self._resource_job(card_id)
                           for body in _bodies(me)
                           for card_id in (*self._stack_ids(body), *self._installed_ids(body)))
        candidates: dict[tuple, list[float]] = {}
        for card in (me.get("hand") or ()):
            if not card or card.get("id") is None:
                continue
            card_id = int(card["id"])
            facts = self.registry.facts.get(card_id)
            tags = self.registry.functions.get(card_id, ())
            if (setup_complete and "opener" in tags
                    and facts is not None and facts.stage != "basic"):
                continue
            card_job = self._resource_job(card_id)
            candidates.setdefault(card_job, []).append(self.registry.worth(card_id))
        worth = 0.0
        for card_job, values in candidates.items():
            remaining = max(0, self._job_limit(card_job, values, capacities)
                            - occupied.get(card_job, 0))
            worth += sum(sorted(values, reverse=True)[:remaining])
        # A typed tutor is an option, not merely the cardboard currently in hand. Replace its
        # intrinsic Worth with a better probability-discounted reachable outcome when one exists;
        # never sum every legal target, since a search choice can realize only one branch.
        self._reachable_card_access(me)
        source_access = self._reachable_source_cache.get(id(me), {})
        present_ids = {int(body.get("id", 0)) for body in _bodies(me)} | {
            int(card["id"]) for card in (me.get("hand") or ())
            if card and card.get("id") is not None
        }
        required_partners = dict(self.profile.partners)
        for source, outcomes in source_access.items():
            source_worth = self.registry.worth(source)
            best = source_worth
            for target, access in outcomes.items():
                if target == source:
                    continue
                usable_access = float(access)
                for partner in required_partners.get(int(target), ()):
                    if int(partner) not in present_ids:
                        usable_access *= float(outcomes.get(int(partner), 0.0))
                best = max(best, usable_access * self.registry.worth(target))
            worth += max(0.0, best - source_worth)
        return FUTURE_HAND_ACCESS_DISCOUNT * float(worth_to_prizes(worth))

    def prepare_needs(self, observation, seat: int) -> None:
        """Freeze visible demand as the option Trainer/Supporter tutors carry through this solve."""
        current = observation.get("current") or {}
        players = current.get("players") or ()
        me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
        hand_ids = tuple(int(card["id"]) for card in (me.get("hand") or ())
                         if card and card.get("id") is not None)
        self._prepared_hand_serials = frozenset(
            int(card["serial"]) for card in (me.get("hand") or ())
            if card and card.get("serial") is not None)
        self._prepared_hand_counts = Counter(hand_ids)
        pending_source, _offered = self._pending_source_and_targets(observation)
        fetchers = list(card_id for card_id in hand_ids
                        if any(clause.get("target") in ("supporter", "trainer")
                               for clause in self._fetch_clauses(card_id)))
        if (pending_source and pending_source not in fetchers
                and any(clause.get("target") in ("supporter", "trainer")
                        for clause in self._fetch_clauses(pending_source))):
            fetchers.append(pending_source)
        fetchers = tuple(fetchers)
        self._prepared_needs = ()
        self._prepared_need_routes = {}
        if not fetchers:
            return
        needs = self._need_model.immediate(observation, seat)
        self._prepared_base_total = self._potential_without_needs(observation).total
        if not needs:
            return
        supporter_available = not bool(current.get("supporterPlayed"))
        available = self._remaining_deck_pool(me)
        self._prepared_needs = self._need_model.uncovered_by_hand(
            needs, hand_ids, supporter_available=supporter_available,
            discard_capacity=max(0, len(hand_ids) - 1), available_targets=available)
        if not self._prepared_needs:
            return
        bench_capacity = max(0, int(me.get("benchMax", 5) or 5)
                             - len(tuple(body for body in (me.get("bench") or ()) if body)))
        for card_id in fetchers:
            self._prepared_need_routes[card_id] = self._need_model.routes(
                card_id, self._prepared_needs,
                supporter_available=supporter_available,
                discard_capacity=max(0, len(hand_ids) - 1), bench_capacity=bench_capacity,
                available_targets=available, committed=card_id == pending_source)

    @staticmethod
    def _pending_source_and_targets(observation) -> tuple[int, frozenset[int]]:
        select = observation.get("select") or {}
        source = select.get("effect") or select.get("contextCard") or {}
        source_id = source.get("id") if isinstance(source, dict) else source
        deck = tuple(select.get("deck") or ())
        targets = set()
        for option in select.get("option") or ():
            if int(option.get("area", -1)) != _DECK:
                continue
            index = option.get("index")
            if isinstance(index, int) and 0 <= index < len(deck) and deck[index]:
                targets.add(int(deck[index].get("id", 0)))
        return int(source_id or 0), frozenset(targets)

    @staticmethod
    def _playable_hand_positions(observation, hand) -> frozenset[int]:
        select = observation.get("select") or {}
        if int(select.get("context", -1)) != _MAIN:
            return frozenset()
        playable = set()
        for option in select.get("option") or ():
            if int(option.get("type", -1)) not in (_PLAY, _ATTACH, _EVOLVE):
                continue
            index = option.get("index")
            if isinstance(index, int) and 0 <= index < len(hand) and hand[index]:
                playable.add(index)
        return frozenset(playable)

    def _need_route_access(self, observation, seat: int) -> float:
        """Value current progress along a prepared, still-legal same-turn need route."""
        needs = tuple(self._prepared_needs or ())
        routes = tuple(route for rows in self._prepared_need_routes.values() for route in rows
                       if len(route.path) > 1)
        if not needs or not routes:
            return 0.0
        current = observation.get("current") or {}
        players = current.get("players") or ()
        me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
        hand = tuple(me.get("hand") or ())
        playable = self._playable_hand_positions(observation, hand)
        available = self._remaining_deck_pool(me)
        signatures = []
        serialless_seen = Counter()
        for hand_index in sorted(playable):
            card_id = int(hand[hand_index].get("id", 0))
            serial = hand[hand_index].get("serial")
            if serial is None:
                serialless_seen[card_id] += 1
                fetched = serialless_seen[card_id] > self._prepared_hand_counts.get(card_id, 0)
            else:
                fetched = int(serial) not in self._prepared_hand_serials
            edges = []
            for route in routes:
                for position, route_card in enumerate(route.path):
                    if int(route_card) != card_id:
                        continue
                    # A downstream card already held when demand was frozen is a direct out, not
                    # evidence that this route progressed. Only the source or a newly fetched copy
                    # can carry the route forward.
                    if position > 0 and not fetched:
                        continue
                    edges.append(CoverageEdge(
                        route.need_index, route.progress_value(position),
                        fetched_targets=tuple(route.path[position + 1:])))
            signatures.append(tuple(edges))

        source_id, offered = self._pending_source_and_targets(observation)
        pending_edges = []
        if source_id:
            for route in routes:
                for position, route_card in enumerate(route.path[:-1]):
                    next_card = int(route.path[position + 1])
                    target_exists = (next_card in offered if offered
                                     else int(available.get(next_card, 0)) > 0)
                    if int(route_card) == source_id and target_exists:
                        pending_edges.append(CoverageEdge(
                            route.need_index, route.progress_value(position, pending=True),
                            fetched_targets=tuple(route.path[position + 1:])))
        if pending_edges:
            signatures.append(tuple(pending_edges))
        return float(best_assignment(
            signatures, len(needs), target_counts=available).value) if signatures else 0.0

    def search_focus(self, observation) -> float:
        """Positive only while a prepared same-turn need route has legal visible progress."""
        current = observation.get("current") or {}
        seat = int(current.get("yourIndex", 0)) if self.root_seat is None else self.root_seat
        return (self._need_route_access(observation, seat)
                + self._fulfilled_need_access(observation, seat))

    @staticmethod
    def _same_need(left, right) -> bool:
        left_kind = str(left.key).split(":", 1)[0]
        right_kind = str(right.key).split(":", 1)[0]
        left_targets = {int(card_id) for card_id, _value in left.direct}
        right_targets = {int(card_id) for card_id, _value in right.direct}
        return left_kind == right_kind and bool(left_targets & right_targets)

    def _fulfilled_need_access(self, observation, seat: int) -> float:
        """Transfer route value into the resulting state until base potential pays it back."""
        prepared = tuple(self._prepared_needs or ())
        if not prepared:
            return 0.0
        players = ((observation.get("current") or {}).get("players") or ())
        mine = players[seat] if 0 <= seat < len(players) and players[seat] else {}
        if mine.get("hand") is None:
            return 0.0
        current = self._need_model.immediate(observation, seat)
        fulfilled = sum(
            max((float(value) for _card_id, value in need.direct), default=0.0)
            for need in prepared
            if not any(self._same_need(need, candidate) for candidate in current)
        )
        if fulfilled <= 0.0:
            return 0.0
        base_gain = max(
            0.0, self._potential_without_needs(observation).total - self._prepared_base_total)
        return max(0.0, fulfilled - base_gain)

    def _opponent_role_pressure(self, opponent) -> float:
        """Remaining existence plus health Worth of roles declared by the matched scouting Brief."""
        total = 0.0
        for body in _bodies(opponent):
            worth = self.opponent_role_worth.get(int(body.get("id", 0)), 0.0)
            if not worth:
                continue
            health = max(KNOCKED_OUT_HP, int(body.get("hp", MINIMUM_HP)))
            total += worth_to_prizes(worth) * (
                OPPONENT_ROLE_PRESENCE_SHARE
                + OPPONENT_ROLE_HEALTH_SHARE * health / DAMAGE_COUNTERS_PER_PRIZE)
        return -total

    def _route_suffix(self, route, prizes_taken: int):
        cumulative = 0
        for index, card_id in enumerate(route):
            if cumulative == prizes_taken:
                return route[index:]
            cumulative += self._card_prizes(card_id)
        return () if cumulative == prizes_taken else None

    def _can_develop_into(self, card_id: int, payoff_id: int) -> bool:
        return card_id == payoff_id or any(
            card_id in line[:-1] and line[-1] == payoff_id for line in self.profile.lines)

    def _route_body_readiness(self, body, payoff_id: int) -> float:
        """Printed-attack readiness from resources already committed to the route body.

        A future manual attachment is an alternative use of the next Energy, not free route
        readiness: it may instead fund an Ability cost, retreat, or another attacker. Bellman search
        values that future choice from the hand state itself.
        """
        stat = self._stat(payoff_id)
        attacks = tuple(getattr(stat, "attacks", ()) or ()) if stat is not None else ()
        if not attacks:
            return 1.0
        codes = _energy_codes(body)
        return max((
            _pay_fraction(
                codes, tuple(getattr(self.stats.attack(attack_id), "energyTypes", ()) or ()))
            for attack_id in attacks if self.stats.attack(attack_id) is not None
        ), default=0.0)

    def _prize_plan(self, me, opponent) -> float:
        if not self.profile.prize_routes or not self.profile.prizes_to_win:
            return 0.0
        prizes_lost = self.profile.prizes_to_win - len(me.get("prize") or ())
        if prizes_lost < 0:
            return 0.0
        active = next((body for body in (me.get("active") or ()) if body), None)
        board = list(_bodies(me))
        card_access, _remaining = self._reachable_card_access(me)
        values = []
        for route in self.profile.prize_routes:
            route_prizes = sum(self._card_prizes(card_id) for card_id in route)
            excess = route_prizes - self.profile.prizes_to_win
            if excess <= 0:
                continue
            suffix = self._route_suffix(route, prizes_lost)
            if active is not None and (not suffix or not self._can_develop_into(
                    int(active.get("id", 0)), int(suffix[0]))):
                # The route is an ideal, not a brittle history assertion. After an off-route KO,
                # resume at the earliest route body matching the current Active.
                suffix = next((route[index:] for index, card_id in enumerate(route)
                               if self._can_develop_into(
                                   int(active.get("id", 0)), int(card_id))), None)
            if not suffix:
                continue
            bodies = list(board)
            route_access = 1.0
            matched = []
            for desired in suffix:
                index = next((index for index, body in enumerate(bodies)
                              if int(body.get("id", 0)) == desired), None)
                if index is not None:
                    matched.append((bodies.pop(index), desired))
                    continue
                base_index = next((index for index, body in enumerate(bodies)
                                   if self._can_develop_into(
                                       int(body.get("id", 0)), desired)), None)
                availability = float(card_access.get(int(desired), 0.0))
                if base_index is None or availability <= 0.0:
                    route_access = 0.0
                    break
                body = bodies.pop(base_index)
                route_access *= availability
                matched.append((body, desired))
            if (active is not None and suffix
                    and not self._can_develop_into(int(active.get("id", 0)), suffix[0])):
                route_access = 0.0
            if route_access <= 0.0 or len(matched) != len(suffix):
                continue
            # The route earns its extra prizes only as a chain. Card access supplies its
            # probability; the next reserve's printed attack readiness supplies temporal viability.
            next_body, next_payoff = matched[1] if len(matched) > 1 else matched[0]
            values.append(float(excess) * route_access * self._route_body_readiness(
                next_body, next_payoff))
        return max(values, default=0.0)

    def __call__(self, observation) -> Potential:
        self._side_facts_cache.clear()
        self._reachable_access_cache.clear()
        self._reachable_source_cache.clear()
        self._known_prize_counts = Counter(
            {int(card_id): int(count) for card_id, count in
             (observation.get("own_prizes") or {}).items()})
        current = observation.get("current") or {}
        seat = int(current.get("yourIndex", 0)) if self.root_seat is None else self.root_seat
        players = current.get("players") or ()
        me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
        opponent_seat = 1 - seat
        opponent = (players[opponent_seat]
                    if 0 <= opponent_seat < len(players) and players[opponent_seat] else {})
        result = int(current.get("result", -1))
        if result != -1:
            game = self.scale.game if result == seat else -self.scale.game
            return Potential(game, (("game", game),))
        lethal_exposure = self._lethal_exposure(me, opponent)
        transient = observation.get("bellmanTransient") or {}
        damage_boosts = tuple(transient.get("damage_boosts") or ())
        reachable_damage_boosts = (*damage_boosts, *self._hand_damage_boosts(me))
        attack_available = (
            int(((observation.get("select") or {}).get("context", -1))) == _MAIN
            and any(int(option.get("type", -1)) == _ATTACK
                    for option in ((observation.get("select") or {}).get("option") or ())))
        if not self._deriving_needs:
            if self._prepared_needs is None:
                self._deriving_needs = True
                try:
                    self.prepare_needs(observation, seat)
                finally:
                    self._deriving_needs = False
        families = {
            "game": 0.0,
            "prize_race": float(len(opponent.get("prize") or ()) - len(me.get("prize") or ())),
            "damage": (self._damage_progress(opponent)
                       - self._damage_progress(me) * (
                           1.0 if lethal_exposure < 0.0 else SAFE_DAMAGE_RESERVE_SHARE)),
            "readiness": self._readiness(
                me, opponent,
                retreat_available=not bool(current.get("retreated")),
                attack_available=attack_available,
                opponent_moves_next=int(observation.get("bellmanActor", seat)) != seat,
                damage_boosts=reachable_damage_boosts,
                manual_attach_available=not bool(current.get("energyAttached"))),
            "multi_target_ko": (0.0 if observation.get("bellmanHistoricalMain")
                                else self._multi_target_ko_ready(me, opponent)),
            # Historical isolated effect menus lack the parent attack continuation. Do not infer a
            # future multi-target line from that deliberately partial state.
            "board": self._board_resources(me),
            "development": self._development(me),
            "hand": self._hand_resources(me, setup_complete=int(current.get("turn", 0)) > 0)
                + (0.0 if self._deriving_needs else (
                    self._need_route_access(observation, seat)
                    + self._fulfilled_need_access(observation, seat))),
            "opponent_roles": self._opponent_role_pressure(opponent),
            "prize_plan": self._prize_plan(me, opponent),
        }
        return Potential(sum(families.values()), tuple(sorted(families.items())))


__all__ = ("BoardPotential", "UtilityScale")
