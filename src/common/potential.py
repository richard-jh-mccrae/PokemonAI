"""Deck-neutral terminal utility for full-turn Bellman search.

The evaluator contains no action policy and no card-specific behavior. It maps observable state
facts to prize-equivalent utility; the engine and Bellman recursion determine how actions change
those facts.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .card_worth import KNOWN_CARD_FLOOR, function_role
from .energy import ENERGY_COLORLESS, payment_fraction, provision_units
from .information import BellmanDeckProfile
from .damage import bench_reach, compute_active_damage
from .damage_context import SideFacts, damage_context
from .strategy.context import _DAMAGE, _TO_ACTIVE
from .value import Potential, ValueRegistry, worth_to_prizes


MINIMUM_HP = 1
KNOCKED_OUT_HP = 0
TERMINAL_GAME_UTILITY = 100.0
DAMAGE_COUNTERS_PER_PRIZE = 200.0
DAMAGE_COUNTER_SIZE = 10
STANDARD_PRIZE_COUNT = 6
FUTURE_HAND_ACCESS_DISCOUNT = 0.75
OPPONENT_ROLE_PRESENCE_SHARE = 0.90
OPPONENT_ROLE_HEALTH_SHARE = 0.10
SAFE_DAMAGE_RESERVE_SHARE = 0.10
OPPONENT_ROLE_THREAT_SHARE = 0.20
OPPONENT_ROLE_WORTH_NORMALIZER = 30.0
BENCH_ATTACK_ACCESS_SHARE = 0.50
EVOLVED_BODY_PRIZE_SHARE = 0.040
DEPLOYED_BASIC_LINE_PRIZE_SHARE = 0.020
KO_PRESSURE_SHARE = 0.000001
#: ADR-0060's strip/gift currency: one hidden opponent card = the known-card floor.
OPPONENT_HAND_CARD_WORTH = KNOWN_CARD_FLOOR
#: Checkup facts (docs/rules.md L161): poison places 1 counter; burn places 2 UNCONDITIONALLY —
#: the coin only decides whether the burn then cures, never whether the damage lands.
POISON_CHECKUP_DAMAGE = 10
BURN_CHECKUP_DAMAGE = 20.0
#: Forecast share of a statused Active's attack: wake/attack coins and the paralysis turn-skip
#: (docs/rules.md L156-166); our own sleep sees two checkups before our next attack window.
INCOMING_CONDITION_SHARE = {"asleep": 0.5, "paralyzed": 0.0, "confused": 0.5}
OWN_CONDITION_SHARE = {"asleep": 0.75, "confused": 0.5}

_UNSET = object()


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
    return payment_fraction(codes, required)


def _hand_count(player) -> int:
    hand = player.get("hand")
    return len(hand) if hand is not None else int(player.get("handCount", 0) or 0)


def board_parity(board: float, role_pressure: float) -> float:
    """Our board Worth over the opponent's role-pressure magnitude, in ``[0, 1]`` (ADR-0141).
    No resolved pressure means nothing to be behind of, so parity stays whole."""
    if role_pressure <= 0.0:
        return 1.0
    return min(1.0, max(0.0, board) / role_pressure)


def own_stadium(current, seat: int) -> tuple:
    return tuple(card for card in (current.get("stadium") or ())
                 if card and card.get("playerIndex") is not None
                 and int(card["playerIndex"]) == seat)


def _active_condition_share(player, table) -> float:
    """Special conditions ride the player payload and apply to that side's Active only."""
    share = 1.0
    for name, factor in table.items():
        if player.get(name):
            share *= factor
    return share


class BoardPotential:
    """Absolute observable-state utility used at every Bellman transition.

    Card identities enter only through the supplied card facts, declared deck relationships, and
    printed attacks. No action kind, named card, matchup, or tactical sequence is preferred here.
    """

    def __init__(self, stats, *, registry: ValueRegistry,
                 profile: BellmanDeckProfile | None = None,
                 scale: UtilityScale = UtilityScale(), root_seat: int | None = None,
                 opponent_role_worth=None, isolated_selection: bool = False,
                 opponent_hand_share: float = 0.0, root_observation=None):
        self.stats = stats
        self.registry = registry
        self.profile = profile or BellmanDeckProfile.from_registry(registry)
        self.scale = scale
        self.root_seat = None if root_seat is None else int(root_seat)
        self.opponent_role_worth = {int(card_id): max(0.0, float(worth))
                                    for card_id, worth in (opponent_role_worth or {}).items()}
        self.isolated_selection = bool(isolated_selection)
        # Every consumer of the opponent-hand term must read THIS share, or the paths disagree.
        self.opponent_hand_share = max(0.0, float(opponent_hand_share))
        # Pinned to the deciding position, never per successor: ADR-0141 amendment, or the scaling
        # leaks into the damage and development families.
        self.board_parity = 1.0
        self._stat_cache = {}
        self._attack_cache = {}
        self._resource_job_cache = {}
        self._prize_job_capacities_cache = None
        self._cost_cap_cache = {}
        self._tags_cache = {}
        # Facts, energy codes, and damage contexts recur ~17x within one evaluation over the same
        # player/body dicts.  The observation is immutable for the duration of one ``__call__``, so
        # results are keyed by object identity and the cache lives only for that call.
        self._call_cache = None
        if root_observation is not None:
            self.board_parity = self._root_board_parity(root_observation)

    def _sides(self, current):
        seat = int(current.get("yourIndex", 0)) if self.root_seat is None else self.root_seat
        players = current.get("players") or ()

        def side(index):
            return players[index] if 0 <= index < len(players) and players[index] else {}

        return seat, side(seat), side(1 - seat)

    def _root_board_parity(self, observation) -> float:
        current = observation.get("current") or {}
        seat, me, opponent = self._sides(current)
        role_pressure = -self._opponent_role_pressure(opponent)
        return board_parity(self._own_board_resources(me, stadium=own_stadium(current, seat)),
                            role_pressure)

    def _stat(self, card_id):
        if not self.stats or card_id is None:
            return None
        card_id = int(card_id)
        if card_id not in self._stat_cache:
            self._stat_cache[card_id] = self.stats.get(card_id)
        return self._stat_cache[card_id]

    def _attack(self, attack_id):
        attack_id = int(attack_id)
        if attack_id not in self._attack_cache:
            self._attack_cache[attack_id] = (
                self.stats.attack(attack_id) if hasattr(self.stats, "attack") else None)
        return self._attack_cache[attack_id]

    def _prizes(self, body) -> int:
        stat = self._stat(body.get("id"))
        return int(getattr(stat, "prize_value", 1) if stat is not None else 1)

    def _card_prizes(self, card_id: int) -> int:
        stat = self._stat(card_id)
        return int(getattr(stat, "prize_value", 1) if stat is not None else 1)

    def _codes(self, body):
        cache = self._call_cache
        if cache is None:
            return _energy_codes(body)
        key = ("codes", id(body))
        found = cache.get(key)
        if found is None:
            found = cache[key] = _energy_codes(body)
        return found

    def _tags(self, card_id) -> frozenset:
        card_id = int(card_id)
        found = self._tags_cache.get(card_id)
        if found is None:
            found = self._tags_cache[card_id] = frozenset(
                self.registry.functions.get(card_id, ()))
        return found

    def _context(self, attacker_facts: SideFacts, defender_facts: SideFacts) -> dict:
        cache = self._call_cache
        if cache is None:
            return damage_context(attacker_facts, defender_facts)
        key = ("ctx", id(attacker_facts), id(defender_facts))
        found = cache.get(key)
        if found is None:
            found = cache[key] = damage_context(attacker_facts, defender_facts)
        return found

    def _side_facts(self, player, *, attacking_body=None) -> SideFacts:
        cache = self._call_cache
        if cache is None:
            return self._build_side_facts(player, attacking_body=attacking_body)
        key = ("sf", id(player), id(attacking_body))
        found = cache.get(key)
        if found is None:
            found = cache[key] = self._build_side_facts(player, attacking_body=attacking_body)
        return found

    def _build_side_facts(self, player, *, attacking_body=None) -> SideFacts:
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
            return tuple(str(getattr(self._attack(attack_id), "name", "") or "")
                         for attack_id in (getattr(stat, "attacks", ()) or ()))

        boosts = []
        for tool in (active.get("tools") or ()) if active else ():
            stat = stat_for(tool)
            amount = int(getattr(stat, "damageBoost", 0) or 0) if stat is not None else 0
            if amount:
                boosts.append((amount, getattr(stat, "damageBoostType", None),
                               bool(getattr(stat, "damageBoostVsEx", False))))

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
        return SideFacts(
            hand_size=hand_size,
            active_energy=len(self._codes(active)) if active else 0,
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

    def _defender_tool_transient(self, defender) -> dict | None:
        """Attached-tool damage reduction on the defending BODY — without it the forecast reads
        only the Pokémon card's own printed defenses and overestimates every KO."""
        cache = self._call_cache
        if cache is not None:
            key = ("tool", id(defender))
            found = cache.get(key, _UNSET)
            if found is not _UNSET:
                return found
        holder_stat = self._stat(defender.get("id"))
        holder_type = getattr(holder_stat, "energyType", None) if holder_stat else None
        reduction, typed = 0, []
        for tool in (defender.get("tools") or ()):
            stat = self._stat(tool.get("id") if isinstance(tool, dict) else tool)
            amount = int(getattr(stat, "damageReduction", 0) or 0) if stat else 0
            if not amount:
                continue
            holders = getattr(stat, "damageReductionHolderTypes", None)
            if holders is not None and holder_type not in holders:
                continue                               # Thick Scale on a non-{N} holder is inert
            types = getattr(stat, "damageReductionTypes", None)
            needs_ability = bool(getattr(stat, "damageReductionRequiresAbility", False))
            if types is None and not needs_ability:
                reduction += amount
            else:                                      # attacker-gated: resolved per attack
                typed.append((amount, types, needs_ability))
        result = {}
        if reduction:
            result["reduction"] = reduction
        if typed:
            result["typed"] = tuple(typed)
        result = result or None
        if cache is not None:
            cache[key] = result
        return result

    def _condition_share(self, player, table) -> float:
        cache = self._call_cache
        if cache is None:
            return _active_condition_share(player, table)
        key = ("cond", id(player), id(table))
        found = cache.get(key)
        if found is None:
            found = cache[key] = _active_condition_share(player, table)
        return found

    def _attack_value(self, body, codes, defender, attacker_facts, defender_facts, *,
                      require_ready: bool = False) -> float:
        card_id = body.get("id")
        stat = self._stat(card_id)
        defender_stat = self._stat(defender.get("id")) if defender else None
        if stat is None or defender is None or defender_stat is None:
            return 0.0
        hp = max(MINIMUM_HP, int(defender.get("hp", MINIMUM_HP)))
        prizes = self._prizes(defender)
        context = self._context(attacker_facts, defender_facts)
        transient = self._defender_tool_transient(defender)
        defender_tags = self._tags(defender.get("id", 0))
        best = 0.0
        for attack_id in getattr(stat, "attacks", ()) or ():
            attack = self._attack(attack_id)
            if attack is None:
                continue
            required = tuple(getattr(attack, "energyTypes", ()) or ())
            readiness = _pay_fraction(codes, required)
            if require_ready and readiness < 1.0:
                continue
            damage = max(float(compute_active_damage(
                             attack, stat, defender_stat, defender_tags, context=context,
                             defender_transient=transient)),
                         float(bench_reach(attack)))
            best = max(best, prizes * min(1.0, damage / hp) * readiness)
        return best

    def _damage_progress(self, player) -> float:
        total = 0.0
        body_ids = Counter(int(body.get("id", 0)) for body in _bodies(player))
        for body in _bodies(player):
            maximum = max(MINIMUM_HP, int(body.get("maxHp", body.get("hp", MINIMUM_HP))))
            health = max(KNOCKED_OUT_HP, int(body.get("hp", maximum)))
            damage = maximum - health
            # Linear progress prices every damage counter.  Convex KO pressure additionally
            # prices concentration: the same new damage is more useful on an already injured
            # target because it is closer to converting into prizes.
            total += (damage / DAMAGE_COUNTERS_PER_PRIZE
                      + (self._prizes(body) * KO_PRESSURE_SHARE * (damage / maximum) ** 2
                         if (self.isolated_selection
                             and body_ids[int(body.get("id", 0))] > 1) else 0.0))
        active = next((body for body in (player.get("active") or ()) if body), None)
        if active is not None:
            pending = ((POISON_CHECKUP_DAMAGE if player.get("poisoned") else 0.0)
                       + (BURN_CHECKUP_DAMAGE if player.get("burned") else 0.0))
            if pending:
                remaining = max(KNOCKED_OUT_HP, int(active.get("hp", MINIMUM_HP)))
                total += min(pending, remaining) / DAMAGE_COUNTERS_PER_PRIZE
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

    def _readiness(self, me, opponent, *, opponent_moves_next: bool = False,
                   include_incoming: bool = True) -> float:
        mine = next((body for body in (me.get("active") or ()) if body), None)
        theirs = next((body for body in (opponent.get("active") or ()) if body), None)
        defenders = (self._reachable_defenders(
            theirs, opponent_moves_next=opponent_moves_next) if theirs is not None else ())
        opponent_facts = self._side_facts(opponent)
        me_facts = self._side_facts(me)
        active_values = []
        bench_values = []
        if theirs is not None:
            for bodies, values in (((me.get("active") or ()), active_values),
                                   ((me.get("bench") or ()), bench_values)):
                for body in (body for body in bodies if body):
                    attacker_facts = self._side_facts(me, attacking_body=body)
                    values.append(min((self._attack_value(
                        body, self._codes(body), defender, attacker_facts, opponent_facts)
                        for defender in defenders), default=0.0))
        own = max(max(active_values, default=0.0)
                  * self._condition_share(me, OWN_CONDITION_SHARE),
                  BENCH_ATTACK_ACCESS_SHARE * max(bench_values, default=0.0))
        incoming_values = []
        if include_incoming and mine is not None:
            incoming_active_share = self._condition_share(opponent, INCOMING_CONDITION_SHARE)
            for body in _bodies(opponent):
                attacker_facts = self._side_facts(opponent, attacking_body=body)
                incoming_values.append(self._attack_value(
                    body, self._codes(body), mine, attacker_facts, me_facts)
                    * (incoming_active_share if body is theirs else 1.0)
                    * (1.0 + OPPONENT_ROLE_THREAT_SHARE
                       * self.opponent_role_worth.get(int(body.get("id", 0)), 0.0)
                       / OPPONENT_ROLE_WORTH_NORMALIZER))
        incoming = max(incoming_values, default=0.0)
        return own - incoming

    def _attack_coverage(self, body, codes, me, opponent, *, require_ready=False) -> float:
        active = next((target for target in (opponent.get("active") or ()) if target), None)
        bench = tuple(target for target in (opponent.get("bench") or ()) if target)
        if active is None and not bench:
            return 0.0
        attacker_facts = self._side_facts(me, attacking_body=body)
        defender_facts = self._side_facts(opponent)
        active_value = (self._attack_value(
            body, codes, active, attacker_facts, defender_facts,
            require_ready=require_ready) if active else 0.0)
        next_value = max((self._attack_value(
            body, codes, defender, attacker_facts, defender_facts,
            require_ready=require_ready)
                          for defender in bench), default=0.0)
        return active_value + next_value

    def _next_attachment_coverage(self, me, opponent) -> float:
        active = next((body for body in (me.get("active") or ()) if body), None)
        if active is None:
            return 0.0
        energy_provisions = []
        for card in me.get("hand") or ():
            stat = self._stat(card.get("id")) if card else None
            if stat is None or not getattr(stat, "is_energy", False):
                continue
            energy_type = getattr(stat, "energyType", None)
            if energy_type is not None:
                units = provision_units(
                    self.registry.functions, int(card.get("id", 0)),
                    evolved=bool(active.get("preEvolution")))
                energy_provisions.append((int(energy_type), max(1, units)))
        codes = self._codes(active)
        return max((self._attack_ko_coverage(
            active, [*codes, *([energy_type] * units)], me, opponent)
                    for energy_type, units in energy_provisions), default=0.0)

    def _attack_ko_coverage(self, body, codes, me, opponent) -> float:
        defender = next((target for target in (opponent.get("active") or ()) if target), None)
        if defender is None:
            return 0.0
        stat = self._stat(body.get("id"))
        defender_stat = self._stat(defender.get("id"))
        if stat is None or defender_stat is None:
            return 0.0
        attacker_facts = self._side_facts(me, attacking_body=body)
        defender_facts = self._side_facts(opponent)
        defender_tags = self._tags(defender.get("id", 0))
        transient = self._defender_tool_transient(defender)
        best = 0.0
        for attack_id in getattr(stat, "attacks", ()) or ():
            attack = self._attack(attack_id)
            if attack is None or _pay_fraction(
                    codes, tuple(getattr(attack, "energyTypes", ()) or ())) < 1.0:
                continue
            damage = compute_active_damage(
                attack, stat, defender_stat, defender_tags,
                context=self._context(attacker_facts, defender_facts),
                defender_transient=transient)
            if damage < int(defender.get("hp", MINIMUM_HP)):
                continue
            bench_prizes = self._bench_ko_prizes(attack, opponent.get("bench") or ())
            best = max(best, float(self._prizes(defender) + bench_prizes))
        return best

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
        defender_tags = self._tags(defender.get("id", 0))
        transient = self._defender_tool_transient(defender)
        best = 0.0
        for body in _bodies(me):
            stat = self._stat(body.get("id"))
            if stat is None:
                continue
            context = self._context(
                self._side_facts(me, attacking_body=body), defender_facts)
            codes = self._codes(body)
            for attack_id in getattr(stat, "attacks", ()) or ():
                attack = self._attack(attack_id)
                if attack is None or _pay_fraction(
                        codes, tuple(getattr(attack, "energyTypes", ()) or ())) < 1.0:
                    continue
                active_damage = compute_active_damage(
                    attack, stat, defender_stat, defender_tags, context=context,
                    defender_transient=transient)
                if active_damage < int(defender.get("hp", MINIMUM_HP)):
                    continue
                target_prizes = self._bench_ko_prizes(attack, bench)
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
        active_tags = self._tags(active.get("id", 0))
        defender_facts = self._side_facts(defender_side)
        attacker_active = next(
            (body for body in (attacker_side.get("active") or ()) if body), None)
        attacker_active_share = self._condition_share(
            attacker_side, INCOMING_CONDITION_SHARE)
        active_transient = self._defender_tool_transient(active)
        worst = 0.0
        for body in _bodies(attacker_side):
            stat = self._stat(body.get("id"))
            if stat is None:
                continue
            context = self._context(
                self._side_facts(attacker_side, attacking_body=body), defender_facts)
            for attack_id in getattr(stat, "attacks", ()) or ():
                attack = self._attack(attack_id)
                if attack is None:
                    continue
                exposed = 0.0
                active_damage = compute_active_damage(
                    attack, stat, active_stat, active_tags, context=context,
                    defender_transient=active_transient)
                if active_damage >= int(active.get("hp", MINIMUM_HP)):
                    exposed += self._prizes(active)
                exposed += self._bench_ko_prizes(attack, bench)
                if body is attacker_active:
                    exposed *= attacker_active_share
                worst = max(worst, exposed)
        return -worst

    def _bench_ko_prizes(self, attack, bench) -> float:
        snipe = bench_reach(attack)
        return float(max((self._prizes(target) for target in bench
                          if snipe >= int(target.get("hp", MINIMUM_HP))), default=0))

    @staticmethod
    def _stack_ids(body):
        rows = [body]
        rows.extend(body.get("preEvolution") or ())
        rows.extend(body.get("energyCards") or ())
        rows.extend(body.get("tools") or ())
        return tuple(int(card.get("id") if isinstance(card, dict) else card)
                     for card in rows
                     if card is not None and (not isinstance(card, dict) or card.get("id") is not None))

    def _resource_job(self, card_id: int):
        card_id = int(card_id)
        if card_id in self._resource_job_cache:
            return self._resource_job_cache[card_id]
        roles = tuple(sorted(self.registry.roles.get(card_id, ())))
        functions = tuple(sorted(tag for tag in self.registry.functions.get(card_id, ())
                                 if not str(tag).startswith("provides:")))
        facts = self.registry.facts.get(card_id)
        category = "pokemon" if facts is not None and facts.pokemon else "card"
        intrinsic_role = function_role(functions)
        result = (("role", roles[0], category) if roles else
                  ("role", intrinsic_role, category) if intrinsic_role else
                  ("function", functions[0], category) if functions else
                  ("card", card_id, category))
        self._resource_job_cache[card_id] = result
        return result

    def _prize_job_capacities(self):
        if self._prize_job_capacities_cache is not None:
            return self._prize_job_capacities_cache
        capacities = {}
        for route in self.profile.prize_routes:
            counts = Counter(self._resource_job(int(card_id)) for card_id in route)
            for card_job, count in counts.items():
                capacities[card_job] = max(capacities.get(card_job, 1), count)
        self._prize_job_capacities_cache = capacities
        return capacities

    def _own_board_resources(self, me, stadium=()) -> float:
        """OUR side only: registry Worth reads 0.0 for cards outside our deck, not "no board"."""
        capacities = self._prize_job_capacities()
        body_ids = {int(body.get("id", 0)) for body in _bodies(me)}
        required_partners = dict(self.profile.partners)
        jobs: dict[tuple, list[float]] = {}
        for body in _bodies(me):
            for card_id in self._stack_ids(body):
                stat = self._stat(card_id)
                if stat is not None and getattr(stat, "is_energy", False):
                    continue
                partners = required_partners.get(card_id, ())
                if partners and not set(partners).issubset(body_ids):
                    continue
                jobs.setdefault(self._resource_job(card_id), []).append(
                    self.registry.worth(card_id))
        # Our Stadium in play is a board resource like any attached card; without this a Stadium
        # play was a pure hand loss and the agent was structurally disincentivised from it.
        for card in stadium:
            if card and card.get("id") is not None:
                jobs.setdefault(self._resource_job(int(card["id"])), []).append(
                    self.registry.worth(int(card["id"])))
        worth = sum(sum(sorted(values, reverse=True)[:capacities.get(card_job, len(values))])
                    for card_job, values in jobs.items())
        return float(worth_to_prizes(worth))

    def _held_card_usable(self, me, card_id: int) -> bool:
        stat = self._stat(card_id)
        if stat is None:
            return True
        bodies = _bodies(me)
        if getattr(stat, "is_energy", False):
            return self.isolated_selection or any(
                len(self._codes(body)) < self._energy_cost_cap(int(body.get("id", 0)))
                for body in bodies)
        evolves_from = getattr(stat, "evolvesFrom", None)
        if not evolves_from:
            return True
        parent = self.registry.line_parents.get(int(card_id))
        return any(
            (parent is not None and int(body.get("id", 0)) == int(parent))
            or getattr(self._stat(body.get("id")), "name", None) == evolves_from
            for body in bodies
        )

    def _energy_cost_cap(self, card_id: int) -> int:
        card_id = int(card_id)
        found = self._cost_cap_cache.get(card_id)
        if found is not None:
            return found
        found = self._cost_cap_cache[card_id] = self._build_energy_cost_cap(card_id)
        return found

    def _build_energy_cost_cap(self, card_id: int) -> int:
        candidates = [int(card_id)]
        if hasattr(self.stats, "forward_card_ids"):
            candidates.extend(int(candidate)
                              for candidate in (self.stats.forward_card_ids(int(card_id)) or ()))
        cap = 0
        for candidate in candidates:
            stat = self._stat(candidate)
            for attack_id in (getattr(stat, "attacks", ()) or ()) if stat is not None else ():
                attack = self._attack(attack_id)
                cap = max(cap, len(tuple(getattr(attack, "energyTypes", ()) or ()))
                          if attack is not None else 0)
        return cap

    def _active_ko_ready(self, me, opponent) -> bool:
        attacker = next((body for body in (me.get("active") or ()) if body), None)
        defender = next((body for body in (opponent.get("active") or ()) if body), None)
        if attacker is None or defender is None:
            return False
        return self._attack_value(
            attacker, self._codes(attacker), defender,
            self._side_facts(me, attacking_body=attacker), self._side_facts(opponent),
        ) >= self._prizes(defender)

    def _energy_position(self, me, opponent, *, historical_context=None) -> float:
        """Usable attached-resource value, shaped by deployment urgency and survival.

        Energy on an identical full-health backup is exposure while the Active's largest attack
        remains unfunded; the Active's prize liability prices that delay.
        """
        total = 0.0
        active_ko_ready = self._active_ko_ready(me, opponent)
        for body in _bodies(me):
            cap = self._energy_cost_cap(int(body.get("id", 0)))
            if cap <= 0:
                continue
            maximum = max(MINIMUM_HP, int(body.get("maxHp", body.get("hp", MINIMUM_HP))))
            survival = max(0.0, min(1.0, int(body.get("hp", maximum)) / maximum))
            cards = tuple(card for card in (body.get("energyCards") or ()) if card)
            remaining = cap
            values = []
            overcap = 0.0
            for card in cards:
                supplied = provision_units(
                    self.registry.functions, int(card.get("id", 0)),
                    evolved=bool(body.get("preEvolution")))
                units = min(remaining, supplied)
                unit_value = worth_to_prizes(
                    self.registry.worth(int(card.get("id", 0)))) / supplied
                values.extend(
                    unit_value
                    for _ in range(units))
                overcap += max(0, supplied - units) * unit_value
                remaining -= units
            if not values:
                values = [worth_to_prizes(self.registry.seeds.energy)] * min(
                    cap, len(self._codes(body)))
            diversify = (not self.isolated_selection or active_ko_ready
                          or bool(body.get("preEvolution")))
            shaped = sum(value / (index + 1) if diversify else value * (index + 1)
                         for index, value in enumerate(values))
            if not self.isolated_selection or historical_context != _DAMAGE:
                shaped *= self._attack_coverage(body, self._codes(body), me, opponent)
            total += survival * shaped - overcap
        active = next((body for body in (me.get("active") or ()) if body), None)
        if active is not None and not self.isolated_selection:
            cap = self._energy_cost_cap(int(active.get("id", 0)))
            missing = max(0, cap - len(self._codes(active)))
            active_maximum = max(
                MINIMUM_HP, int(active.get("maxHp", active.get("hp", MINIMUM_HP))))
            active_full = int(active.get("hp", 0)) >= active_maximum
            if missing and active_full:
                backups = tuple(body for body in (me.get("bench") or ()) if body
                                and int(body.get("id", 0)) == int(active.get("id", 0))
                                and int(body.get("hp", 0)) >= max(
                                    MINIMUM_HP,
                                    int(body.get("maxHp", body.get("hp", MINIMUM_HP)))))
                stranded_units = sum(len(self._codes(body)) for body in backups)
                total -= (self._prizes(active) * missing
                          * min(1.0, stranded_units / max(1, cap)))
        return total

    def _development(self, me) -> float:
        """Value deployed and evolved pieces of declared evolution lines."""
        evolved = sum(self._prizes(body) * EVOLVED_BODY_PRIZE_SHARE
                      for body in _bodies(me) if body.get("preEvolution"))
        line_payoff = {
            int(line[0]): self._card_prizes(int(line[-1]))
            for line in self.registry.lines if len(line) > 1
        }
        deployed = sum(
            line_payoff.get(int(body.get("id", 0)), 0) * DEPLOYED_BASIC_LINE_PRIZE_SHARE
            for body in _bodies(me) if not body.get("preEvolution")
        )
        return evolved + deployed

    def _hand_resources(self, me, *, setup_complete: bool) -> float:
        capacities = self._prize_job_capacities()
        occupied = Counter(self._resource_job(card_id)
                           for body in _bodies(me) for card_id in self._stack_ids(body)
                           if not (self.isolated_selection
                                   and self._stat(card_id) is not None
                                   and getattr(self._stat(card_id), "is_energy", False)))
        candidates: dict[tuple, list[float]] = {}
        for card in (me.get("hand") or ()):
            if not card or card.get("id") is None:
                continue
            card_id = int(card["id"])
            if not self._held_card_usable(me, card_id):
                continue
            facts = self.registry.facts.get(card_id)
            tags = self.registry.functions.get(card_id, ())
            if (setup_complete and "opener" in tags
                    and facts is not None and facts.stage != "basic"):
                continue
            card_job = self._resource_job(card_id)
            held_worth = self.registry.worth(card_id)
            if self.isolated_selection and "discard_eot" in tags:
                held_worth *= 0.20
            candidates.setdefault(card_job, []).append(held_worth)
        worth = 0.0
        for card_job, values in candidates.items():
            remaining = max(0, capacities.get(card_job, 1) - occupied.get(card_job, 0))
            worth += sum(sorted(values, reverse=True)[:remaining])
        return FUTURE_HAND_ACCESS_DISCOUNT * float(worth_to_prizes(worth))

    def _hand_demand(self, me) -> float:
        """Value visible cards and general access by presently missing board jobs."""
        occupied = Counter(self._resource_job(card_id)
                           for body in _bodies(me) for card_id in self._stack_ids(body))
        capacities = self._prize_job_capacities()
        missing_slots = sum(max(0, capacity - occupied[job])
                            for job, capacity in capacities.items())
        value = 0.0
        access = 0.0
        seen = Counter()
        for card in (me.get("hand") or ()):
            if not card or card.get("id") is None:
                continue
            card_id = int(card["id"])
            if not self._held_card_usable(me, card_id):
                continue
            job = self._resource_job(card_id)
            capacity = capacities.get(job, 1)
            if occupied[job] + seen[job] < capacity:
                seen[job] += 1
                value += worth_to_prizes(self.registry.worth(card_id))
            tags = frozenset(self.registry.functions.get(card_id, ()))
            if (self.isolated_selection and missing_slots
                    and {"draw", "dig", "tutor_energy"}.intersection(tags)):
                access += missing_slots * worth_to_prizes(self.registry.worth(card_id))
        return 0.01 * value + FUTURE_HAND_ACCESS_DISCOUNT * access

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

    def _prize_plan(self, me, opponent) -> float:
        if not self.profile.prize_routes or not self.profile.prizes_to_win:
            return 0.0
        prizes_taken = self.profile.prizes_to_win - len(opponent.get("prize") or ())
        if prizes_taken < 0:
            return 0.0
        active = next((body for body in (me.get("active") or ()) if body), None)
        board_ids = [int(body.get("id", 0)) for body in _bodies(me)]
        hand_ids = [int(card["id"]) for card in (me.get("hand") or ())
                    if card and card.get("id") is not None]
        values = []
        for route in self.profile.prize_routes:
            route_prizes = sum(self._card_prizes(card_id) for card_id in route)
            excess = route_prizes - self.profile.prizes_to_win
            if excess <= 0:
                continue
            suffix = self._route_suffix(route, prizes_taken)
            if not suffix:
                continue
            bodies = list(board_ids)
            held = list(hand_ids)
            covered = 0
            for desired in suffix:
                index = next((index for index, card_id in enumerate(bodies)
                              if card_id == desired), None)
                if index is not None:
                    bodies.pop(index)
                    covered += 1
                    continue
                base_index = next((index for index, card_id in enumerate(bodies)
                                   if self._can_develop_into(card_id, desired)), None)
                payoff_index = next((index for index, card_id in enumerate(held)
                                     if card_id == desired), None)
                if base_index is None or payoff_index is None:
                    break
                bodies.pop(base_index)
                held.pop(payoff_index)
                covered += 1
            if (active is not None and suffix
                    and not self._can_develop_into(int(active.get("id", 0)), suffix[0])):
                covered = 0
            # The declared route makes the opponent take `excess` additional
            # prizes. Its utility is therefore measured in those prize units,
            # attenuated only by the fraction of the remaining route presently
            # available on board or directly in hand.
            values.append(float(excess) * (covered / len(suffix)))
        return max(values, default=0.0)

    def __call__(self, observation) -> Potential:
        self._call_cache = {}
        try:
            return self._evaluate(observation)
        finally:
            self._call_cache = None

    def _evaluate(self, observation) -> Potential:
        current = observation.get("current") or {}
        seat, me, opponent = self._sides(current)
        result = int(current.get("result", -1))
        if result != -1:
            game = self.scale.game if result == seat else -self.scale.game
            return Potential(game, (("game", game),))
        lethal_exposure = self._lethal_exposure(me, opponent)
        historical_context = observation.get("bellmanHistoricalContext")
        selection_context = (historical_context if historical_context is not None
                             else (observation.get("select") or {}).get("context"))
        promoted_after_attack = (self.isolated_selection
                                 and historical_context == _TO_ACTIVE)
        readiness = self._readiness(
            me, opponent,
            opponent_moves_next=int(observation.get("bellmanActor", seat)) != seat,
            include_incoming=not promoted_after_attack)
        if promoted_after_attack:
            readiness = self._next_attachment_coverage(me, opponent)
        board = self._own_board_resources(me, stadium=own_stadium(current, seat))
        opponent_roles = self._opponent_role_pressure(opponent)
        families = {
            "game": 0.0,
            "prize_race": float(len(opponent.get("prize") or ()) - len(me.get("prize") or ())),
            "damage": (self._damage_progress(opponent)
                       - self._damage_progress(me) * (
                           1.0 if lethal_exposure < 0.0 else SAFE_DAMAGE_RESERVE_SHARE)),
            "readiness": readiness,
            "multi_target_ko": (0.0 if observation.get("bellmanHistoricalMain")
                                else self._multi_target_ko_ready(me, opponent)),
            # Historical isolated effect menus lack the parent attack continuation. Do not infer a
            # future multi-target line from that deliberately partial state.
            "board": board,
            "energy_position": self._energy_position(
                me, opponent, historical_context=selection_context),
            "development": self._development(me),
            "hand": self._hand_resources(me, setup_complete=int(current.get("turn", 0)) > 0),
            "hand_demand": self._hand_demand(me),
            "opponent_roles": opponent_roles,
            "opponent_hand": (-self.board_parity
                              * self.opponent_hand_share
                              * worth_to_prizes(OPPONENT_HAND_CARD_WORTH)
                              * _hand_count(opponent)),
            "prize_plan": self._prize_plan(me, opponent),
        }
        return Potential(sum(families.values()), tuple(sorted(families.items())))

    def optimistic_ceiling(self, _observation, **_context) -> float:
        return self.scale.game


__all__ = ("BoardPotential", "UtilityScale")
