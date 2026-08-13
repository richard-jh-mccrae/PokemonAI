"""Deck-neutral terminal utility for full-turn Bellman search.

The evaluator contains no action policy and no card-specific behavior. It maps observable state
facts to prize-equivalent utility; the engine and Bellman recursion determine how actions change
those facts.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .information import BellmanDeckProfile
from .damage import compute_active_damage
from .damage_context import SideFacts, damage_context
from .value import Potential, ValueRegistry, worth_to_prizes


ENERGY_COLORLESS = 0
ENERGY_WILDCARD = 10
MINIMUM_HP = 1
KNOCKED_OUT_HP = 0
TERMINAL_GAME_UTILITY = 100.0
DAMAGE_COUNTERS_PER_PRIZE = 200.0
DAMAGE_COUNTER_SIZE = 10
STANDARD_PRIZE_COUNT = 6
FUTURE_HAND_ACCESS_DISCOUNT = 0.75
OPPONENT_ROLE_PRESENCE_SHARE = 0.90
OPPONENT_ROLE_HEALTH_SHARE = 0.10
SAFE_DAMAGE_RESERVE_SHARE = 0.25
OPPONENT_ROLE_THREAT_SHARE = 0.20
OPPONENT_ROLE_WORTH_NORMALIZER = 30.0
BENCH_ATTACK_ACCESS_SHARE = 0.50
EVOLVED_BODY_PRIZE_SHARE = 0.040


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

    def __init__(self, stats, *, registry: ValueRegistry,
                 profile: BellmanDeckProfile | None = None,
                 scale: UtilityScale = UtilityScale(), root_seat: int | None = None,
                 opponent_role_worth=None):
        self.stats = stats
        self.registry = registry
        self.profile = profile or BellmanDeckProfile.from_registry(registry)
        self.scale = scale
        self.root_seat = None if root_seat is None else int(root_seat)
        self.opponent_role_worth = {int(card_id): max(0.0, float(worth))
                                    for card_id, worth in (opponent_role_worth or {}).items()}
        self._stat_cache = {}
        self._attack_cache = {}
        self._resource_job_cache = {}
        self._prize_job_capacities_cache = None

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

    def _side_facts(self, player, *, attacking_body=None) -> SideFacts:
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

    def _attack_value(self, body, codes, defender, attacker_facts, defender_facts) -> float:
        card_id = body.get("id")
        stat = self._stat(card_id)
        defender_stat = self._stat(defender.get("id")) if defender else None
        if stat is None or defender is None or defender_stat is None:
            return 0.0
        hp = max(MINIMUM_HP, int(defender.get("hp", MINIMUM_HP)))
        prizes = self._prizes(defender)
        context = damage_context(attacker_facts, defender_facts)
        defender_tags = frozenset(self.registry.functions.get(int(defender.get("id", 0)), ()))
        best = 0.0
        for attack_id in getattr(stat, "attacks", ()) or ():
            attack = self._attack(attack_id)
            if attack is None:
                continue
            required = tuple(getattr(attack, "energyTypes", ()) or ())
            readiness = _pay_fraction(codes, required)
            damage = max(float(compute_active_damage(
                             attack, stat, defender_stat, defender_tags, context=context)),
                         float(getattr(attack, "benchSnipe", 0) or 0))
            best = max(best, prizes * min(1.0, damage / hp) * readiness)
        return best

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

    def _readiness(self, me, opponent, *, opponent_moves_next: bool = False) -> float:
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
                        body, _energy_codes(body), defender, attacker_facts, opponent_facts)
                        for defender in defenders), default=0.0))
        own = max(max(active_values, default=0.0),
                  BENCH_ATTACK_ACCESS_SHARE * max(bench_values, default=0.0))
        incoming_values = []
        if mine is not None:
            for body in _bodies(opponent):
                attacker_facts = self._side_facts(opponent, attacking_body=body)
                incoming_values.append(self._attack_value(
                    body, _energy_codes(body), mine, attacker_facts, me_facts)
                    * (1.0 + OPPONENT_ROLE_THREAT_SHARE
                       * self.opponent_role_worth.get(int(body.get("id", 0)), 0.0)
                       / OPPONENT_ROLE_WORTH_NORMALIZER))
        incoming = max(incoming_values, default=0.0)
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
        result = (("role", roles[0], category) if roles else
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

    def _board_resources(self, me) -> float:
        capacities = self._prize_job_capacities()
        body_ids = {int(body.get("id", 0)) for body in _bodies(me)}
        required_partners = dict(self.profile.partners)
        jobs: dict[tuple, list[float]] = {}
        for body in _bodies(me):
            for card_id in self._stack_ids(body):
                partners = required_partners.get(card_id, ())
                if partners and not set(partners).issubset(body_ids):
                    continue
                jobs.setdefault(self._resource_job(card_id), []).append(
                    self.registry.worth(card_id))
        worth = sum(sum(sorted(values, reverse=True)[:capacities.get(card_job, len(values))])
                    for card_job, values in jobs.items())
        return float(worth_to_prizes(worth))

    def _development(self, me) -> float:
        """Value realized by turning a line piece into a developed body.

        The retained pre-evolution stack already proves that development occurred.  Scale the
        improvement by the evolved body's prize liability so the term stays card- and deck-neutral.
        """
        return sum(self._prizes(body) * EVOLVED_BODY_PRIZE_SHARE
                   for body in (me.get("bench") or ()) if body and body.get("preEvolution"))

    def _hand_resources(self, me, *, setup_complete: bool) -> float:
        capacities = self._prize_job_capacities()
        occupied = Counter(self._resource_job(card_id)
                           for body in _bodies(me) for card_id in self._stack_ids(body))
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
            remaining = max(0, capacities.get(card_job, 1) - occupied.get(card_job, 0))
            worth += sum(sorted(values, reverse=True)[:remaining])
        return FUTURE_HAND_ACCESS_DISCOUNT * float(worth_to_prizes(worth))

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
        families = {
            "game": 0.0,
            "prize_race": float(len(opponent.get("prize") or ()) - len(me.get("prize") or ())),
            "damage": (self._damage_progress(opponent)
                       - self._damage_progress(me) * (
                           1.0 if lethal_exposure < 0.0 else SAFE_DAMAGE_RESERVE_SHARE)),
            "readiness": self._readiness(
                me, opponent,
                opponent_moves_next=int(observation.get("bellmanActor", seat)) != seat),
            "multi_target_ko": (0.0 if observation.get("bellmanHistoricalMain")
                                else self._multi_target_ko_ready(me, opponent)),
            # Historical isolated effect menus lack the parent attack continuation. Do not infer a
            # future multi-target line from that deliberately partial state.
            "board": self._board_resources(me),
            "development": self._development(me),
            "hand": self._hand_resources(me, setup_complete=int(current.get("turn", 0)) > 0),
            "opponent_roles": self._opponent_role_pressure(opponent),
            "prize_plan": self._prize_plan(me, opponent),
        }
        return Potential(sum(families.values()), tuple(sorted(families.items())))


__all__ = ("BoardPotential", "UtilityScale")
