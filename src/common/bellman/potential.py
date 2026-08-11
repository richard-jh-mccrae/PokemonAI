"""Fast, direct full-turn board potential for the Mega Starmie Bellman prototype."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .value import Potential


STARYU, MEGA_STARMIE, CINDERACE = 1030, 1031, 666
WATER, IGNITION = 3, 17


@dataclass(frozen=True)
class BoardSeeds:
    game: float = 100.0
    prize: float = 1.0
    chip: float = 0.35
    health: float = 0.30
    readiness: float = 0.85
    future_threat: float = 0.18
    line_base: float = 0.18
    line_top: float = 0.32
    accelerator: float = 0.12
    turbo_recipient: float = 0.24
    needed_hand_card: float = 0.20
    persistent_line_energy: float = 0.05


def _bodies(player):
    return tuple(body for body in tuple(player.get("active") or ()) +
                 tuple(player.get("bench") or ()) if body)


def _energy_codes(body):
    codes = body.get("energies")
    if codes is not None:
        return [int(code) for code in codes]
    return [int(card.get("energyType", 0)) for card in body.get("energyCards") or ()]


def _pay_fraction(codes, required) -> float:
    required = list(int(code) for code in required)
    if not required:
        return 1.0
    remaining = list(codes)
    paid = 0
    for need in (code for code in required if code != 0):
        found = next((index for index, code in enumerate(remaining)
                      if code in (need, 10)), None)
        if found is not None:
            remaining.pop(found)
            paid += 1
    colorless = sum(code == 0 for code in required)
    paid += min(colorless, len(remaining))
    return paid / len(required)


class MegaStarmiePotential:
    """Single, inexpensive absolute potential. Consequences are differenced once by ValueOracle."""

    def __init__(self, stats, *, functions=None, seeds: BoardSeeds = BoardSeeds(), threat_roles=None):
        self.stats = stats
        self.functions = functions
        self.seeds = seeds
        self.threat_roles = {int(key): str(value) for key, value in (threat_roles or {}).items()}

    def _stat(self, card_id):
        return self.stats.get(int(card_id)) if self.stats and card_id is not None else None

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
                    candidates = {0, 1, 2, 3, 4, 5, 6, 7, 8, 10}
                    fraction = max(_pay_fraction(codes + [code], required)
                                   for code in candidates)
                damage = float(getattr(attack, "damage", 0) or 0)
                profile_fraction += damage / 210.0 * fraction ** 2
                if fraction >= 1.0:
                    best_ready = max(best_ready, damage)
            best_fraction = max(best_fraction, profile_fraction)
        return best_fraction, best_ready

    def _side_damage(self, player, sign, *, scouting=False):
        total = 0.0
        bodies = ([(body, False) for body in player.get("active") or () if body]
                  + [(body, True) for body in player.get("bench") or () if body])
        for body, benched in bodies:
            maximum = max(1, int(body.get("maxHp", body.get("hp", 1))))
            lost = max(0, maximum - int(body.get("hp", maximum)))
            card_id = int(body.get("id", 0))
            forward = (self.stats.forward_max_damage(card_id)
                       if self.stats and hasattr(self.stats, "forward_max_damage") else 0)
            role = self.threat_roles.get(card_id, "") if scouting else ""
            role_weight = {
                "attacker": 5.0, "prize_liability": 5.0,
                "disruption_target": 3.0, "engine": 2.0,
                "fragile_preevo": 1.2, "avoid": 0.45,
            }.get(role, 1.0)
            stat = self._stat(card_id)
            forward_ids = (self.stats.forward_card_ids(card_id)
                           if scouting and self.stats
                           and hasattr(self.stats, "forward_card_ids") else ())
            future_prizes = max([self._prizes(body)] + [
                int(getattr(self._stat(candidate), "prize_value", 1) or 1)
                for candidate in forward_ids])
            # Bench chip is deliberate future setup, so Scouting's line/prize/energy evidence
            # matters. Partial Active damage is discounted unless the attack actually takes the KO.
            line_progress = (4.0 if benched and forward_ids
                             and getattr(stat, "stage", None) == "stage1" else 0.0)
            relevance = (role_weight + 0.35 * forward / 210.0 + line_progress
                         + (3.0 * max(0, future_prizes - 1)
                            if scouting and benched else 0.0))
            raw = self.seeds.chip * relevance * lost / maximum
            progress = 0.85 * (1.0 - math.exp(-raw / 0.85))
            # Damage on a loaded body advances removal of a present threat even when generic
            # damage progress is already saturated. Scouting's role keeps this from turning into
            # a generic "hit whichever body has Energy" rule.
            loaded_progress = (min(0.85, 0.15 * role_weight
                                   * min(3, len(self._persistent_codes(body)))
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
        hp = max(1, int(mine.get("hp", 1)))
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
                candidates = {0, 1, 2, 3, 4, 5, 6, 7, 8, 10}
                ready = max(_pay_fraction(codes + [code], required) for code in candidates)
                if ready >= 1.0:
                    snipe = max(snipe, float(getattr(attack, "benchSnipe", 0) or 0))
        if snipe:
            for body in me.get("bench") or ():
                card_id = int(body.get("id", 0))
                effective_prizes = 3 if card_id in (STARYU, MEGA_STARMIE) else self._prizes(body)
                build, _ready = self._attack_profile(body)
                value -= (0.5 * self.seeds.health * effective_prizes * (1.0 + build)
                          * min(1.0, snipe / max(1, int(body.get("hp", 1)))))
        return value

    def _readiness(self, player, sign, *, opponent=False):
        rows = []
        for body in _bodies(player):
            progress, _damage = self._attack_profile(body, next_attach=opponent)
            rows.append(progress)
        rows.sort(reverse=True)
        return sign * self.seeds.readiness * sum(
            progress * (1.0 if index == 0 else 0.30)
            for index, progress in enumerate(rows))

    def _future_threat(self, opponent):
        total = 0.0
        for body in _bodies(opponent):
            card_id = int(body.get("id", 0))
            forward = (self.stats.forward_max_damage(card_id)
                       if self.stats and hasattr(self.stats, "forward_max_damage") else 0)
            role = self.threat_roles.get(card_id, "")
            role_factor = 1.25 if role in {"attacker", "prize_liability", "fragile_preevo"} else 1.0
            energy_factor = 1.0 + 0.25 * min(4, len(self._persistent_codes(body)))
            total -= (self.seeds.future_threat * role_factor * energy_factor
                      * self._prizes(body) * forward / 210.0)
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
        role_factor = {"prize_liability": 2.0, "attacker": 1.25,
                       "fragile_preevo": 1.15, "avoid": 0.55}.get(role, 1.0)
        prizes = self._prizes(defender)
        hp = max(1, int(defender.get("hp", 1)))
        reach = min(1.0, damage / hp)
        # A loaded multi-prize target has useful partial pressure; speculative one-prize lines
        # become valuable chiefly at the actual KO boundary (the 60/50-HP Boss fixture).
        exponent = 1 if role == "prize_liability" else 3
        # Readiness against the current Active is option value, never more valuable than taking
        # that body's prizes. Squaring prizes made a three-prize KO worth less than preserving the
        # threat of that KO, so keep pressure linear and below the prize conversion boundary.
        return 0.45 * role_factor * prizes * prizes * reach ** exponent

    def _development(self, me):
        bodies = _bodies(me)
        ids = [int(body.get("id", 0)) for body in bodies]
        active = next((body for body in (me.get("active") or ()) if body), None)
        staryu_count = ids.count(STARYU)
        mega_count = ids.count(MEGA_STARMIE)
        cinderace_count = ids.count(CINDERACE)
        value = ((self.seeds.line_base if staryu_count and not mega_count else 0.0)
                 + max(0, staryu_count - (0 if mega_count else 1)) * 0.025
                 + (self.seeds.line_top if mega_count else 0.0)
                 + max(0, mega_count - 1) * 0.06
                 + (self.seeds.accelerator if cinderace_count else 0.0)
                 + max(0, cinderace_count - 1) * 0.02)
        for body in bodies:
            card_id = int(body.get("id", 0))
            if card_id == STARYU:
                value += 0.70 * self.seeds.persistent_line_energy * len(_energy_codes(body))
            elif card_id == MEGA_STARMIE:
                value += self.seeds.persistent_line_energy * len(_energy_codes(body))
        if active and int(active.get("id", 0)) == CINDERACE and any(
                card_id in (STARYU, MEGA_STARMIE) for card_id in ids[1:]):
            value += self.seeds.turbo_recipient
        return value

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
        if (int(active.get("id", 0)) == STARYU and MEGA_STARMIE in hand):
            stat = self._stat(MEGA_STARMIE)
        if stat is None:
            return 0.0
        candidates = []
        existing = self._persistent_codes(active)
        for card_id, provision, persistent in ((WATER, (WATER,), True),
                                                (IGNITION, (0, 0, 0), False)):
            if card_id not in hand:
                continue
            if card_id == IGNITION and not getattr(stat, "evolvesFrom", None):
                provision = (0,)
            best = 0.0
            for attack_id in getattr(stat, "attacks", ()) or ():
                attack = self.stats.attack(attack_id) if hasattr(self.stats, "attack") else None
                if attack is None:
                    continue
                required = tuple(getattr(attack, "energyTypes", ()) or ())
                if _pay_fraction(existing + list(provision), required) < 1.0:
                    continue
                damage = float(getattr(attack, "damage", 0) or 0)
                hp = max(1, int(defender.get("hp", 1)))
                prizes = self._prizes(defender)
                payoff = self.seeds.chip * prizes * min(1.0, damage / hp)
                if damage >= hp:
                    payoff += self.seeds.prize * prizes
                    if prizes >= len(me.get("prize") or ()):
                        payoff += self.seeds.game
                if persistent:
                    payoff += 0.10 * damage / 210.0
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
        if active and int(active.get("id", 0)) == CINDERACE and not ids & {STARYU, MEGA_STARMIE}:
            value += self.seeds.needed_hand_card * bool(
                hand.intersection({STARYU, 1086, 1121, 1225}))
        if STARYU in ids and MEGA_STARMIE not in ids:
            value += self.seeds.needed_hand_card * bool(
                hand.intersection({MEGA_STARMIE, 1121, 1145, 1189, 1225}))
        if len(ids & {STARYU, MEGA_STARMIE}) < 2 and len(bodies) < 6 and STARYU in hand:
            value += self.seeds.needed_hand_card
        # Energy committed to the board is owned by readiness/development.  Pricing the same attack
        # once as an Energy-in-hand need and again after attachment makes satisfying demand a loss.
        # Historical nested TO_HAND frames cannot replay their missing parent continuation; their
        # explicit marker therefore carries the one immediate attach/attack counterfactual instead.
        if historical:
            if 1227 in hand and len(me.get("hand") or ()) <= 3:
                value += 0.75 * self.seeds.needed_hand_card
            if int(historical_context or -1) == 21:
                evolved_energy = max(
                    (len(self._persistent_codes(body)) for body in bodies
                     if int(body.get("id", 0)) == MEGA_STARMIE), default=0)
                value += self.seeds.line_top * min(3, evolved_energy) / 3.0
            value += self._attach_option(
                me, opponent, current, select, historical=True,
                next_turn=int(historical_context or -1) == 4)
        return value

    def _durability(self, me):
        value = 0.0
        for body in _bodies(me):
            stat = self._stat(body.get("id"))
            if stat is None:
                continue
            bonus = max(0, int(body.get("maxHp", stat.hp)) - int(stat.hp))
            card_id = int(body.get("id", 0))
            effective_prizes = 3 if card_id in (STARYU, MEGA_STARMIE) else self._prizes(body)
            line_factor = 0.45 if card_id == CINDERACE else 1.0
            value += 0.25 * effective_prizes * line_factor * bonus / 100.0
        return value

    @staticmethod
    def _opponent_hand(opponent):
        size = (len(opponent.get("hand") or ()) if opponent.get("hand") is not None
                else int(opponent.get("handCount", 0)))
        return -0.035 * (size - 4)

    def __call__(self, observation) -> Potential:
        current = observation.get("current") or {}
        seat = int(current.get("yourIndex", 0))
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
            "damage": (self._side_damage(opponent, 1.0, scouting=True)
                       + self._side_damage(me, -1.0)),
            "survival": self._survival(me, opponent),
            "readiness": self._readiness(me, 1.0) + self._readiness(opponent, -1.0,
                                                                 opponent=True),
            "threat": self._future_threat(opponent),
            "pressure": self._pressure(me, opponent),
            "development": self._development(me),
            "needs": self._needs(
                me, opponent, current, observation.get("select"),
                historical=bool(observation.get("bellmanHistoricalMain")),
                historical_context=observation.get("bellmanHistoricalContext")),
            "durability": self._durability(me),
            "opponent_hand": self._opponent_hand(opponent),
        }
        return Potential(sum(families.values()), tuple(sorted(families.items())))


__all__ = ("BoardSeeds", "MegaStarmiePotential")
