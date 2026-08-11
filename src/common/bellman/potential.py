"""Fast, direct full-turn board potential for the Mega Starmie Bellman prototype."""
from __future__ import annotations

from dataclasses import dataclass

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

    def __init__(self, stats, *, seeds: BoardSeeds = BoardSeeds(), threat_roles=None):
        self.stats = stats
        self.seeds = seeds
        self.threat_roles = {int(key): str(value) for key, value in (threat_roles or {}).items()}

    def _stat(self, card_id):
        return self.stats.get(int(card_id)) if self.stats and card_id is not None else None

    def _prizes(self, body) -> int:
        stat = self._stat(body.get("id"))
        return int(getattr(stat, "prize_value", 1) if stat else 1)

    def _attack_profile(self, body, *, next_attach=False):
        stat = self._stat(body.get("id"))
        if stat is None:
            return 0.0, 0.0
        codes = _energy_codes(body)
        best_fraction = best_ready = 0.0
        for attack_id in getattr(stat, "attacks", ()) or ():
            attack = self.stats.attack(attack_id) if hasattr(self.stats, "attack") else None
            if attack is None:
                continue
            fraction = _pay_fraction(codes, getattr(attack, "energyTypes", ()) or ())
            if next_attach and fraction < 1.0:
                required = tuple(getattr(attack, "energyTypes", ()) or ())
                candidates = {0, 1, 2, 3, 4, 5, 6, 7, 8, 10}
                fraction = max(_pay_fraction(codes + [code], required) for code in candidates)
            damage = float(getattr(attack, "damage", 0) or 0)
            best_fraction = max(best_fraction, damage / 210.0 * fraction)
            if fraction >= 1.0:
                best_ready = max(best_ready, damage)
        return best_fraction, best_ready

    def _side_damage(self, player, sign):
        total = 0.0
        for body in _bodies(player):
            maximum = max(1, int(body.get("maxHp", body.get("hp", 1))))
            lost = max(0, maximum - int(body.get("hp", maximum)))
            total += sign * self.seeds.chip * self._prizes(body) * lost / maximum
        return total

    def _survival(self, me, opponent):
        mine = next((body for body in (me.get("active") or ()) if body), None)
        theirs = next((body for body in (opponent.get("active") or ()) if body), None)
        if mine is None or theirs is None:
            return 0.0
        _progress, incoming = self._attack_profile(theirs, next_attach=True)
        hp = max(1, int(mine.get("hp", 1)))
        exposure = min(1.0, incoming / hp)
        return -self.seeds.health * self._prizes(mine) * exposure

    def _readiness(self, player, sign, *, opponent=False):
        total = 0.0
        for index, body in enumerate(_bodies(player)):
            progress, _damage = self._attack_profile(body, next_attach=opponent)
            position = 1.0 if index == 0 else 0.78
            total += sign * self.seeds.readiness * position * progress
        return total

    def _future_threat(self, opponent):
        total = 0.0
        for body in _bodies(opponent):
            card_id = int(body.get("id", 0))
            forward = (self.stats.forward_max_damage(card_id)
                       if self.stats and hasattr(self.stats, "forward_max_damage") else 0)
            role = self.threat_roles.get(card_id, "")
            role_factor = 1.25 if role in {"attacker", "prize_liability", "fragile_preevo"} else 1.0
            total -= self.seeds.future_threat * role_factor * self._prizes(body) * forward / 210.0
        return total

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
                value += self.seeds.persistent_line_energy * len(_energy_codes(body))
            elif card_id == MEGA_STARMIE:
                value += self.seeds.persistent_line_energy * len(_energy_codes(body))
        if active and int(active.get("id", 0)) == CINDERACE and any(
                card_id in (STARYU, MEGA_STARMIE) for card_id in ids[1:]):
            value += self.seeds.turbo_recipient
        return value

    def _needs(self, me):
        bodies = _bodies(me)
        ids = {int(body.get("id", 0)) for body in bodies}
        hand = {int(card.get("id", 0)) for card in me.get("hand") or () if card}
        active = next((body for body in (me.get("active") or ()) if body), None)
        value = 0.0
        if active and int(active.get("id", 0)) == CINDERACE and not ids & {STARYU, MEGA_STARMIE}:
            value += self.seeds.needed_hand_card * (STARYU in hand)
        if STARYU in ids and MEGA_STARMIE not in ids:
            value += self.seeds.needed_hand_card * (MEGA_STARMIE in hand)
        if active is not None:
            _progress, ready = self._attack_profile(active)
            if not ready and WATER in hand:
                value += self.seeds.needed_hand_card * 0.55
        if MEGA_STARMIE in ids and IGNITION in hand:
            value += self.seeds.needed_hand_card * 0.60
        return value

    def __call__(self, observation) -> Potential:
        current = observation.get("current") or {}
        seat = int(current.get("yourIndex", 0))
        players = current.get("players") or ()
        me = players[seat] if len(players) > seat and players[seat] else {}
        opponent = players[1 - seat] if len(players) > 1 and players[1 - seat] else {}
        result = int(current.get("result", -1))
        families = {
            "game": (self.seeds.game if result == seat else
                     -self.seeds.game if result not in (-1, seat) else 0.0),
            "prize_race": self.seeds.prize * (
                len(opponent.get("prize") or ()) - len(me.get("prize") or ())),
            "damage": self._side_damage(opponent, 1.0) + self._side_damage(me, -1.0),
            "survival": self._survival(me, opponent),
            "readiness": self._readiness(me, 1.0) + self._readiness(opponent, -1.0,
                                                                 opponent=True),
            "threat": self._future_threat(opponent),
            "development": self._development(me),
            "needs": self._needs(me),
        }
        return Potential(sum(families.values()), tuple(sorted(families.items())))


__all__ = ("BoardSeeds", "MegaStarmiePotential")
