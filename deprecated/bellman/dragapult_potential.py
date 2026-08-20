from .potential import (
    DAMAGE_COUNTERS_PER_PRIZE, BoardPotential, _bodies, _energy_codes, _pay_fraction,
)
from .value import Potential, worth_to_prizes


ABILITY_FUEL_SHARE = 0.50
ITEM_LOCK_PRIZE_SHARE = 0.25
SPECIAL_CONDITION_PRIZE_SHARES = {
    "poisoned": 0.05, "burned": 0.10, "asleep": 0.25,
    "paralyzed": 0.50, "confused": 0.20,
}


class DragapultPotential(BoardPotential):
    def _bench_ko_prizes(self, attack, bench) -> float:
        """Phantom Dive splits its counters, so several small benched bodies can fall together
        where the shared single-target reach sees only the largest one it can reach."""
        direct = max((self._prizes(bench[index])
                      for index in self._bench_ko_indices(attack, bench)), default=0)
        spread = attack.clause("bench_spread")
        counter_budget = (int(spread.amount or 0) if spread is not None else 0) // 10
        prizes = [0] * (counter_budget + 1)
        for target in bench:
            if bool(getattr(self._card(target.get("id")), "tera", False)):
                continue
            hp = int(target.get("hp", 0) or 0)
            cost = (hp + 9) // 10
            if hp <= 0 or cost > counter_budget:
                continue
            reward = self._prizes(target)
            for used in range(counter_budget, cost - 1, -1):
                prizes[used] = max(prizes[used], prizes[used - cost] + reward)
        return float(max(direct, max(prizes, default=0)))

    def __call__(self, observation) -> Potential:
        base = super().__call__(observation)
        current = observation.get("current") or {}
        if int(current.get("result", -1)) != -1:
            return base
        seat = int(current.get("yourIndex", 0)) if self.root_seat is None else self.root_seat
        players = current.get("players") or ()
        me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
        opponent_seat = 1 - seat
        opponent = players[opponent_seat] if opponent_seat < len(players) else {}

        def ability_energy_cost(body):
            """Energy an Ability needs to fire, off the record's typed clause parameters."""
            types = []
            for ability in getattr(self._card(body.get("id")), "abilities", ()) or ():
                for clause in ability.clauses:
                    if clause.condition_energy_type is not None:
                        types.append(int(clause.condition_energy_type))
                    if clause.rider_energy_type is not None:
                        types.extend([int(clause.rider_energy_type)]
                                     * int(clause.rider_amount or 1))
            return tuple(types)

        def ability_fuel(player):
            return sum(
                worth_to_prizes(self.registry.worth(int(body.get("id", 0))))
                * ABILITY_FUEL_SHARE
                * _pay_fraction(_energy_codes(body), cost)
                for body in _bodies(player)
                if (cost := ability_energy_cost(body)))

        def conditions(player):
            return sum(value for condition, value in SPECIAL_CONDITION_PRIZE_SHARES.items()
                       if player.get(condition))

        def overkill(player):
            return sum(max(0, -int(body.get("hp", 0) or 0)) for body in _bodies(player)) \
                / DAMAGE_COUNTERS_PER_PRIZE

        locked_seat = (observation.get("bellmanTransient") or {}).get("item_lock_seat")
        active = next((body for body in me.get("active") or () if body), None)
        if (locked_seat is None and int(observation.get("bellmanActor", seat)) == opponent_seat
                and active is not None and "item_lock" in self.registry.functions.get(
                    int(active.get("id", 0)), ())):
            locked_seat = opponent_seat
        additions = {
            "ability_fuel": ability_fuel(me) - ability_fuel(opponent),
            "special_conditions": conditions(opponent) - conditions(me),
            "counter_efficiency": overkill(me) - overkill(opponent),
            "item_lock": (ITEM_LOCK_PRIZE_SHARE if locked_seat == opponent_seat
                          else -ITEM_LOCK_PRIZE_SHARE if locked_seat == seat else 0.0),
            "reusable_draw_line": sum(
                worth_to_prizes(self.registry.worth(int(card_id)))
                for card_id in observation.get("bellmanRecycledCardIds") or ()
                if "recycle_line" in self.registry.functions.get(int(card_id), ())),
        }
        families = {**dict(base.families), **additions}
        return Potential(sum(families.values()), tuple(sorted(families.items())), base.unknowns)


__all__ = ("DragapultPotential",)
