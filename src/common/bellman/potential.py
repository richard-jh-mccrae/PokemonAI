"""Fast, direct full-turn board potential for the Mega Starmie Bellman prototype."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .information import BellmanDeckProfile
from .value import Potential
from common.strategy.context import _ATTACH_FROM, _TO_ACTIVE


ENERGY_COLORLESS = 0
ENERGY_WILDCARD = 10
ENERGY_CODES = frozenset(range(0, ENERGY_WILDCARD + 1))
MIN_HP = 1
ATTACK_DAMAGE_NORMALIZER = 210.0
MULTI_PRIZE_LINE_FLOOR = 3
MAX_RETAINED_ENERGY_FOR_THREAT = 4
MAX_LOADED_ENERGY_FOR_CHIP = 3
BENCH_READINESS_WEIGHT = 0.30
BENCH_LINE_PROGRESS_WEIGHT = 10.0
FORWARD_DAMAGE_WEIGHT = 0.35
SCOUT_MULTI_PRIZE_WEIGHT = 3.0
DAMAGE_PROGRESS_CAP = 0.85
DAMAGE_PROGRESS_SATURATION = 0.85
LOADED_CHIP_WEIGHT = 0.15
SNIPE_DANGER_WEIGHT = 0.50
ACCELERATOR_DURABILITY_DISCOUNT = 0.45
EXTRA_LINE_BODY_VALUE = 0.025
EXTRA_LINE_TOP_VALUE = 0.06
EXTRA_ACCELERATOR_VALUE = 0.02
BASE_LINE_ENERGY_WEIGHT = 0.70
PERSISTENT_ATTACH_DAMAGE_WEIGHT = 0.10
LOW_HAND_REFRESH_THRESHOLD = 3
ENERGY_THREAT_STEP = 0.25
MIN_LINE_REDUNDANCY = 2
BOARD_BODY_CAPACITY = 6
HISTORICAL_REFRESH_VALUE_MULTIPLIER = 0.75
HISTORICAL_TOP_ENERGY_CAP = 3
HISTORICAL_TOP_ENERGY_DIVISOR = 3.0
DURABILITY_WEIGHT = 0.25
DURABILITY_HP_NORMALIZER = 100.0
OPPONENT_HAND_CARD_PENALTY = 0.035
OPPONENT_HAND_BASELINE = 4
SCOUT_CHIP_ROLE_WEIGHTS = {
    "attacker": 5.0, "prize_liability": 5.0, "disruption_target": 3.0,
    "engine": 2.0, "fragile_preevo": 1.2, "avoid": 0.45,
}
FUTURE_THREAT_PRIORITY_MULTIPLIER = 1.25
PRESSURE_ROLE_WEIGHTS = {
    "prize_liability": 2.0, "attacker": 1.25, "fragile_preevo": 1.15, "avoid": 0.55,
}
PRIZE_LIABILITY_PRESSURE_EXPONENT = 1
OTHER_PRESSURE_EXPONENT = 3
PRESSURE_WEIGHT = 0.45
DAMAGE_FRACTION_EXPONENT = 2


@dataclass(frozen=True)
class BoardSeeds:
    game: float = 100.0
    prize: float = 1.0
    chip: float = 0.35
    health: float = 0.30
    readiness: float = 0.85
    future_threat: float = 0.18
    attack_threat: float = 1.0
    line_base: float = 0.18
    # A spare declared base behind an evolved top is insurance for a multi-prize line, not
    # generic bench filler. Price it before committing the turn-ending attack.
    line_backup: float = 0.40
    line_top: float = 0.32
    accelerator: float = 0.12
    turbo_recipient: float = 0.24
    # The extra turn unlocked by an immediately fundable declared accelerator. This is a
    # board-state potential, rather than a card-specific action bonus.
    turbo_turn: float = 0.80
    needed_hand_card: float = 0.20
    persistent_line_energy: float = 0.05
    prize_route_active: float = 0.75
    prize_route_body: float = 0.10
    prize_route_exact_body: float = 0.05


def _bodies(player):
    return tuple(body for body in tuple(player.get("active") or ()) +
                 tuple(player.get("bench") or ()) if body)


def _energy_codes(body):
    codes = body.get("energies")
    if codes is not None:
        return [int(code) for code in codes]
    return [int(card.get("energyType", ENERGY_COLORLESS)) for card in body.get("energyCards") or ()]


def _pay_fraction(codes, required) -> float:
    required = list(int(code) for code in required)
    if not required:
        return 1.0
    remaining = list(codes)
    paid = 0
    for need in (code for code in required if code != ENERGY_COLORLESS):
        found = next((index for index, code in enumerate(remaining)
                      if code in (need, ENERGY_WILDCARD)), None)
        if found is not None:
            remaining.pop(found)
            paid += 1
    colorless = sum(code == ENERGY_COLORLESS for code in required)
    paid += min(colorless, len(remaining))
    return paid / len(required)


class MegaStarmiePotential:
    """Single, inexpensive absolute potential. Consequences are differenced once by ValueOracle."""

    def __init__(self, stats, *, functions=None, profile: BellmanDeckProfile = BellmanDeckProfile(),
                 seeds: BoardSeeds = BoardSeeds(), threat_roles=None, root_seat: int | None = None):
        self.stats = stats
        self.functions = functions
        self.profile = profile
        self.seeds = seeds
        self.threat_roles = {int(key): str(value) for key, value in (threat_roles or {}).items()}
        # ``current.yourIndex`` is the player whose turn the *successor* observation describes.
        # It changes after our attack; the value function must stay from the root Pilot's view.
        self.root_seat = None if root_seat is None else int(root_seat)

    def _stat(self, card_id):
        return self.stats.get(int(card_id)) if self.stats and card_id is not None else None

    def _tags(self, card_id) -> frozenset[str]:
        if self.functions is None or card_id is None:
            return frozenset()
        return frozenset(self.functions.tags(int(card_id)))

    def _is_access_card(self, card_id) -> bool:
        tags = self._tags(card_id)
        # A direct search/tutor establishes a dependency immediately.  Draw/dig is valued by its
        # explicit chance transition, so treating it as certain access here double-counts it.
        return bool(tags.intersection({"search", "tutor", "bench_fill"}))

    def _energy_provision(self, card_id, stat) -> tuple[tuple[int, ...], bool]:
        tags = self._tags(card_id)
        burst = next((tag for tag in tags if tag.startswith("provides_evo:")), None)
        if burst and getattr(stat, "evolvesFrom", None):
            return (ENERGY_COLORLESS,) * max(1, int(burst.split(":", 1)[1])), False
        energy = self._stat(card_id)
        code = getattr(energy, "energyType", None)
        return ((int(code) if code is not None else ENERGY_COLORLESS,), "discard_eot" not in tags)

    def _prizes(self, body) -> int:
        stat = self._stat(body.get("id"))
        return int(getattr(stat, "prize_value", 1) if stat else 1)

    def _persistent_codes(self, body):
        cards = body.get("energyCards") or ()
        if cards and self.functions is not None:
            return [code for code, card in zip(_energy_codes(body), cards)
                    if "discard_eot" not in self.functions.tags(int(card.get("id", 0)))]
        return _energy_codes(body)

    def _attack_profile(self, body, *, next_attach=False):
        card_id = int(body.get("id", 0))
        codes = self._persistent_codes(body)
        best_fraction = best_ready = 0.0
        forward = (self.stats.forward_card_ids(card_id)
                   if self.stats and hasattr(self.stats, "forward_card_ids") else ())
        for profile_id in {card_id, *forward}:
            stat = self._stat(profile_id)
            if stat is None:
                continue
            profile_fraction = 0.0
            for attack_id in getattr(stat, "attacks", ()) or ():
                attack = self.stats.attack(attack_id) if hasattr(self.stats, "attack") else None
                if attack is None:
                    continue
                required = tuple(getattr(attack, "energyTypes", ()) or ())
                fraction = _pay_fraction(codes, required)
                if next_attach and fraction < 1.0:
                    candidates = ENERGY_CODES
                    fraction = max(_pay_fraction(codes + [code], required)
                                   for code in candidates)
                damage = float(getattr(attack, "damage", 0) or 0)
                profile_fraction += damage / ATTACK_DAMAGE_NORMALIZER * fraction ** DAMAGE_FRACTION_EXPONENT
                if fraction >= 1.0:
                    best_ready = max(best_ready, damage)
            best_fraction = max(best_fraction, profile_fraction)
        return best_fraction, best_ready

    def _side_damage(self, player, sign, *, scouting=False):
        total = 0.0
        bodies = ([(body, False) for body in player.get("active") or () if body]
                  + [(body, True) for body in player.get("bench") or () if body])
        for body, benched in bodies:
            maximum = max(MIN_HP, int(body.get("maxHp", body.get("hp", MIN_HP))))
            lost = max(0, maximum - int(body.get("hp", maximum)))
            card_id = int(body.get("id", 0))
            forward = (self.stats.forward_max_damage(card_id)
                       if self.stats and hasattr(self.stats, "forward_max_damage") else 0)
            role = self.threat_roles.get(card_id, "") if scouting else ""
            role_weight = SCOUT_CHIP_ROLE_WEIGHTS.get(role, 1.0)
            stat = self._stat(card_id)
            forward_ids = (self.stats.forward_card_ids(card_id)
                           if scouting and self.stats
                           and hasattr(self.stats, "forward_card_ids") else ())
            future_prizes = max([self._prizes(body)] + [
                int(getattr(self._stat(candidate), "prize_value", 1) or 1)
                for candidate in forward_ids])
            # Bench chip is deliberate future setup, so Scouting's line/prize/energy evidence
            # matters. Partial Active damage is discounted unless the attack actually takes the KO.
            line_progress = (BENCH_LINE_PROGRESS_WEIGHT if benched and forward_ids
                             and getattr(stat, "stage", None) == "stage1" else 0.0)
            relevance = (role_weight + FORWARD_DAMAGE_WEIGHT * forward / ATTACK_DAMAGE_NORMALIZER + line_progress
                         + (SCOUT_MULTI_PRIZE_WEIGHT * max(0, future_prizes - 1)
                            if scouting and benched else 0.0))
            raw = self.seeds.chip * relevance * lost / maximum
            progress = DAMAGE_PROGRESS_CAP * (1.0 - math.exp(-raw / DAMAGE_PROGRESS_SATURATION))
            # Damage on a loaded body advances removal of a present threat even when generic
            # damage progress is already saturated. Scouting's role keeps this from turning into
            # a generic "hit whichever body has Energy" rule.
            loaded_progress = (min(DAMAGE_PROGRESS_CAP, LOADED_CHIP_WEIGHT * role_weight
                                   * min(MAX_LOADED_ENERGY_FOR_CHIP, len(self._persistent_codes(body)))
                                   * lost / maximum)
                               if scouting and benched else 0.0)
            total += sign * self._prizes(body) * (progress + loaded_progress)
        return total

    def _survival(self, me, opponent):
        mine = next((body for body in (me.get("active") or ()) if body), None)
        theirs = next((body for body in (opponent.get("active") or ()) if body), None)
        if mine is None or theirs is None:
            return 0.0
        _progress, incoming = self._attack_profile(theirs, next_attach=True)
        hp = max(MIN_HP, int(mine.get("hp", MIN_HP)))
        exposure = min(1.0, incoming / hp)
        value = -self.seeds.health * self._prizes(mine) * exposure
        snipe = 0.0
        stat = self._stat(theirs.get("id"))
        codes = self._persistent_codes(theirs)
        if stat is not None:
            for attack_id in getattr(stat, "attacks", ()) or ():
                attack = self.stats.attack(attack_id) if hasattr(self.stats, "attack") else None
                if attack is None:
                    continue
                required = tuple(getattr(attack, "energyTypes", ()) or ())
                candidates = ENERGY_CODES
                ready = max(_pay_fraction(codes + [code], required) for code in candidates)
                if ready >= 1.0:
                    snipe = max(snipe, float(getattr(attack, "benchSnipe", 0) or 0))
        if snipe:
            for body in me.get("bench") or ():
                card_id = int(body.get("id", 0))
                effective_prizes = (max(MULTI_PRIZE_LINE_FLOOR, self._prizes(body))
                                    if card_id in self.profile.line_cards else self._prizes(body))
                build, _ready = self._attack_profile(body)
                value -= (SNIPE_DANGER_WEIGHT * self.seeds.health * effective_prizes * (1.0 + build)
                          * min(1.0, snipe / max(MIN_HP, int(body.get("hp", MIN_HP)))))
        return value

    def _readiness(self, player, sign, *, opponent=False):
        rows = []
        for body in _bodies(player):
            progress, _damage = self._attack_profile(body, next_attach=opponent)
            rows.append(progress)
        rows.sort(reverse=True)
        return sign * self.seeds.readiness * sum(
            progress * (1.0 if index == 0 else BENCH_READINESS_WEIGHT)
            for index, progress in enumerate(rows))

    def _future_threat(self, opponent):
        total = 0.0
        for body in _bodies(opponent):
            card_id = int(body.get("id", 0))
            role = self.threat_roles.get(card_id, "")
            role_factor = (FUTURE_THREAT_PRIORITY_MULTIPLIER
                           if role in {"attacker", "prize_liability", "fragile_preevo"} else 1.0)
            energy_factor = 1.0 + ENERGY_THREAT_STEP * min(
                MAX_RETAINED_ENERGY_FOR_THREAT, len(self._persistent_codes(body)))
            forward = (self.stats.forward_max_damage(card_id)
                       if self.stats and hasattr(self.stats, "forward_max_damage") else 0)
            total -= (self.seeds.future_threat * role_factor * energy_factor
                      * self._prizes(body) * forward / ATTACK_DAMAGE_NORMALIZER)
        return total

    def attack_threat(self, observation) -> float:
        """Reach-weighted opponent attack capacity removable by a resolved attack.

        This is deliberately separate from the passive board potential.  A potential must not
        alter an unrelated nested target merely because one body has a high printed ceiling; an
        attack that actually damages or removes that body should receive the counterfactual
        denial credit once in its transition ledger.
        """
        current = observation.get("current") or {}
        seat = (int(current.get("yourIndex", 0)) if self.root_seat is None
                else self.root_seat)
        players = current.get("players") or ()
        opponent = players[1 - seat] if len(players) > 1 and players[1 - seat] else {}
        total = 0.0
        for body in _bodies(opponent):
            card_id = int(body.get("id", 0))
            role = self.threat_roles.get(card_id, "")
            role_factor = (FUTURE_THREAT_PRIORITY_MULTIPLIER if role in {
                "attacker", "prize_liability", "fragile_preevo",
            } else 1.0)
            energy_factor = 1.0 + ENERGY_THREAT_STEP * min(
                MAX_RETAINED_ENERGY_FOR_THREAT, len(self._persistent_codes(body)))
            progress, _ready_damage = self._attack_profile(body, next_attach=True)
            health = max(0.0, min(1.0, int(body.get("hp", 0)) /
                                  max(MIN_HP, int(body.get("maxHp", body.get("hp", MIN_HP))))))
            total += (self.seeds.attack_threat * role_factor * energy_factor
                      * self._prizes(body) * progress * health)
        return total

    def _pressure(self, me, opponent):
        attacker = next((body for body in (me.get("active") or ()) if body), None)
        defender = next((body for body in (opponent.get("active") or ()) if body), None)
        if attacker is None or defender is None:
            return 0.0
        _progress, damage = self._attack_profile(attacker)
        if damage <= 0:
            return 0.0
        card_id = int(defender.get("id", 0))
        role = self.threat_roles.get(card_id, "")
        role_factor = PRESSURE_ROLE_WEIGHTS.get(role, 1.0)
        prizes = self._prizes(defender)
        hp = max(MIN_HP, int(defender.get("hp", MIN_HP)))
        reach = min(1.0, damage / hp)
        # A loaded multi-prize target has useful partial pressure; speculative one-prize lines
        # become valuable chiefly at the actual KO boundary.
        exponent = (PRIZE_LIABILITY_PRESSURE_EXPONENT if role == "prize_liability"
                    else OTHER_PRESSURE_EXPONENT)
        # Readiness against the current Active is option value, never more valuable than taking
        # that body's prizes. Squaring prizes made a three-prize KO worth less than preserving the
        # threat of that KO, so keep pressure linear and below the prize conversion boundary.
        return PRESSURE_WEIGHT * role_factor * prizes * prizes * reach ** exponent

    def _development(self, me):
        bodies = _bodies(me)
        ids = [int(body.get("id", 0)) for body in bodies]
        active = next((body for body in (me.get("active") or ()) if body), None)
        value = 0.0
        for line in self.profile.lines:
            base, top = line[0], line[-1]
            base_count, top_count = ids.count(base), ids.count(top)
            value += ((self.seeds.line_base if base_count and not top_count else 0.0)
                      + (self.seeds.line_backup if base_count and top_count else 0.0)
                      + max(0, base_count - (0 if top_count else 1)) * EXTRA_LINE_BODY_VALUE
                      + (self.seeds.line_top if top_count else 0.0)
                      + max(0, top_count - 1) * EXTRA_LINE_TOP_VALUE)
        accelerator_count = sum(ids.count(card_id) for card_id in self.profile.accelerators)
        value += ((self.seeds.accelerator if accelerator_count else 0.0)
                  + max(0, accelerator_count - 1) * EXTRA_ACCELERATOR_VALUE)
        for body in bodies:
            card_id = int(body.get("id", 0))
            if card_id in self.profile.line_bases:
                value += BASE_LINE_ENERGY_WEIGHT * self.seeds.persistent_line_energy * len(_energy_codes(body))
            elif card_id in self.profile.line_tops:
                value += self.seeds.persistent_line_energy * len(_energy_codes(body))
        if active and int(active.get("id", 0)) in self.profile.accelerators and any(
                card_id in self.profile.line_cards for card_id in ids[1:]):
            value += self.seeds.turbo_recipient
            hand_ids = {int(card.get("id", 0)) for card in me.get("hand") or () if card}
            turbo_ready, _damage = self._attack_profile(active, next_attach=True)
            if turbo_ready and hand_ids.intersection(
                    set(self.profile.reusable_energy) | set(self.profile.burst_energy)):
                value += self.seeds.turbo_turn
        return value

    def _card_prizes(self, card_id: int) -> int:
        stat = self._stat(card_id)
        return int(getattr(stat, "prize_value", 1) if stat else 1)

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

    def _route_body_score(self, bodies, suffix) -> float:
        available = [int(body.get("id", 0)) for body in bodies]
        matched = exact = 0
        for desired in suffix:
            match = next((index for index, card_id in enumerate(available)
                          if card_id == desired), None)
            if match is not None:
                exact += 1
            else:
                match = next((index for index, card_id in enumerate(available)
                              if self._can_develop_into(card_id, desired)), None)
            if match is not None:
                matched += 1
                available.pop(match)
        return (self.seeds.prize_route_body * matched
                + self.seeds.prize_route_exact_body * exact)

    def _prize_plan(self, me, opponent) -> float:
        """Value the deck-declared KO order that makes the opponent cross its win threshold late."""
        if not self.profile.prize_routes or self.profile.prizes_to_win is None:
            return 0.0
        prizes_taken = self.profile.prizes_to_win - len(opponent.get("prize") or ())
        if prizes_taken < 0:
            return 0.0
        active = next((body for body in (me.get("active") or ()) if body), None)
        bodies = _bodies(me)
        candidates = []
        for route in self.profile.prize_routes:
            if sum(self._card_prizes(card_id) for card_id in route) <= self.profile.prizes_to_win:
                continue
            suffix = self._route_suffix(route, prizes_taken)
            if not suffix:
                continue
            active_value = (self.seeds.prize_route_active
                            if active and int(active.get("id", 0)) == suffix[0] else 0.0)
            candidates.append(active_value + self._route_body_score(bodies, suffix))
        return max(candidates, default=0.0)

    def _attach_option(self, me, opponent, current, select, *, historical=False,
                       next_turn=False):
        if (not historical and int((select or {}).get("context", -1)) != 0):
            return 0.0
        if bool(current.get("energyAttached")) and not next_turn:
            return 0.0
        active = next((body for body in (me.get("active") or ()) if body), None)
        defender = next((body for body in (opponent.get("active") or ()) if body), None)
        if active is None or defender is None:
            return 0.0
        hand = {int(card.get("id", 0)) for card in me.get("hand") or () if card}
        stat = self._stat(active.get("id"))
        active_id = int(active.get("id", 0))
        line_top = next((line[-1] for line in self.profile.lines
                         if line[0] == active_id and line[-1] in hand), None)
        if line_top is not None:
            stat = self._stat(line_top)
        if stat is None:
            return 0.0
        candidates = []
        existing = self._persistent_codes(active)
        for card_id in (*self.profile.reusable_energy, *self.profile.burst_energy):
            if card_id not in hand:
                continue
            provision, persistent = self._energy_provision(card_id, stat)
            best = 0.0
            for attack_id in getattr(stat, "attacks", ()) or ():
                attack = self.stats.attack(attack_id) if hasattr(self.stats, "attack") else None
                if attack is None:
                    continue
                required = tuple(getattr(attack, "energyTypes", ()) or ())
                if _pay_fraction(existing + list(provision), required) < 1.0:
                    continue
                damage = float(getattr(attack, "damage", 0) or 0)
                hp = max(MIN_HP, int(defender.get("hp", MIN_HP)))
                prizes = self._prizes(defender)
                payoff = self.seeds.chip * prizes * min(1.0, damage / hp)
                if damage >= hp:
                    payoff += self.seeds.prize * prizes
                    if prizes >= len(me.get("prize") or ()):
                        payoff += self.seeds.game
                if persistent:
                    payoff += PERSISTENT_ATTACH_DAMAGE_WEIGHT * damage / ATTACK_DAMAGE_NORMALIZER
                best = max(best, payoff)
            candidates.append(best)
        return max(candidates, default=0.0)

    def _needs(self, me, opponent, current, select, *, historical=False,
               historical_context=None):
        bodies = _bodies(me)
        ids = {int(body.get("id", 0)) for body in bodies}
        hand = {int(card.get("id", 0)) for card in me.get("hand") or () if card}
        active = next((body for body in (me.get("active") or ()) if body), None)
        value = 0.0
        bases, tops = self.profile.line_bases, self.profile.line_tops
        if active and int(active.get("id", 0)) in self.profile.accelerators and not ids & (bases | tops):
            value += self.seeds.needed_hand_card * bool(
                hand.intersection(bases) or any(self._is_access_card(card_id) for card_id in hand))
        if ids.intersection(bases) and not ids.intersection(tops):
            value += self.seeds.needed_hand_card * bool(
                hand.intersection(tops) or any(self._is_access_card(card_id) for card_id in hand))
        if (len(ids & (bases | tops)) < MIN_LINE_REDUNDANCY
                and len(bodies) < BOARD_BODY_CAPACITY and hand.intersection(bases)):
            value += self.seeds.needed_hand_card
        # Energy committed to the board is owned by readiness/development.  Pricing the same attack
        # once as an Energy-in-hand need and again after attachment makes satisfying demand a loss.
        # Historical nested TO_HAND frames cannot replay their missing parent continuation; their
        # explicit marker therefore carries the one immediate attach/attack counterfactual instead.
        if historical:
            if (len(me.get("hand") or ()) <= LOW_HAND_REFRESH_THRESHOLD and any(
                    "shuffle_hand" in self._tags(card_id)
                    and "hand_disruption" not in self._tags(card_id) for card_id in hand)):
                value += HISTORICAL_REFRESH_VALUE_MULTIPLIER * self.seeds.needed_hand_card
            if int(historical_context or -1) == _ATTACH_FROM:
                evolved_energy = max(
                    (len(self._persistent_codes(body)) for body in bodies
                     if int(body.get("id", 0)) in tops), default=0)
                value += (self.seeds.line_top * min(HISTORICAL_TOP_ENERGY_CAP, evolved_energy)
                          / HISTORICAL_TOP_ENERGY_DIVISOR)
            value += self._attach_option(
                me, opponent, current, select, historical=True,
                next_turn=int(historical_context or -1) == _TO_ACTIVE)
        return value

    def _durability(self, me):
        value = 0.0
        for body in _bodies(me):
            stat = self._stat(body.get("id"))
            if stat is None:
                continue
            bonus = max(0, int(body.get("maxHp", stat.hp)) - int(stat.hp))
            card_id = int(body.get("id", 0))
            effective_prizes = (max(MULTI_PRIZE_LINE_FLOOR, self._prizes(body))
                                if card_id in self.profile.line_cards else self._prizes(body))
            line_factor = ACCELERATOR_DURABILITY_DISCOUNT if card_id in self.profile.accelerators else 1.0
            value += DURABILITY_WEIGHT * effective_prizes * line_factor * bonus / DURABILITY_HP_NORMALIZER
        return value

    @staticmethod
    def _opponent_hand(opponent):
        size = (len(opponent.get("hand") or ()) if opponent.get("hand") is not None
                else int(opponent.get("handCount", 0)))
        return -OPPONENT_HAND_CARD_PENALTY * (size - OPPONENT_HAND_BASELINE)

    def __call__(self, observation) -> Potential:
        current = observation.get("current") or {}
        seat = (int(current.get("yourIndex", 0)) if self.root_seat is None
                else self.root_seat)
        players = current.get("players") or ()
        me = players[seat] if len(players) > seat and players[seat] else {}
        opponent = players[1 - seat] if len(players) > 1 and players[1 - seat] else {}
        result = int(current.get("result", -1))
        if result != -1:
            game = self.seeds.game if result == seat else -self.seeds.game
            return Potential(game, (("game", game),))
        families = {
            "game": 0.0,
            "prize_race": self.seeds.prize * (
                len(opponent.get("prize") or ()) - len(me.get("prize") or ())),
            # Opponent chip is attack progress.  Our own HP belongs to ``survival`` where it is
            # priced against the opponent's reachable damage; including it here rewarded a heal
            # even when the Active was perfectly safe and double-counted the same health swing.
            "damage": self._side_damage(opponent, 1.0, scouting=True),
            "survival": self._survival(me, opponent),
            "readiness": self._readiness(me, 1.0) + self._readiness(opponent, -1.0,
                                                                 opponent=True),
            "threat": self._future_threat(opponent),
            "pressure": self._pressure(me, opponent),
            "development": self._development(me),
            "prize_plan": self._prize_plan(me, opponent),
            "needs": self._needs(
                me, opponent, current, observation.get("select"),
                historical=bool(observation.get("bellmanHistoricalMain")),
                historical_context=observation.get("bellmanHistoricalContext")),
            "durability": self._durability(me),
            "opponent_hand": self._opponent_hand(opponent),
        }
        return Potential(sum(families.values()), tuple(sorted(families.items())))


__all__ = ("BoardSeeds", "MegaStarmiePotential")
