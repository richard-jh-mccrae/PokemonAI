"""Dynamic Prize Maps over the opponent-reachable bodies currently in play."""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations

from common.strategy import PrizePlan


@dataclass(frozen=True)
class PrizeMap:
    remaining: int
    route: tuple[int, ...]
    printed_prizes: int
    overrun: int
    preference: tuple[int, ...] = field(default=(), repr=False)

    def plan_rank_key(self) -> tuple[int, ...]:
        return tuple(-value for value in self.preference)

    def as_dict(self) -> dict:
        return {
            "remaining": self.remaining,
            "route": list(self.route),
            "printed_prizes": self.printed_prizes,
            "overrun": self.overrun,
        }


def derive_prize_map(board, ctx) -> PrizeMap:
    """Project our defensible Active-first knockout route from live prize liabilities."""
    remaining = max(0, int(board.them.prize_count))
    if remaining == 0 or board.me.active is None:
        return PrizeMap(remaining, (), 0, 0)
    active = _liability(board.me.active, ctx)
    bench = tuple(_liability(body, ctx) for body in board.me.bench)
    candidates = []
    for suffix in permutations(bench):
        route = _until_game((active, *suffix), remaining)
        printed = sum(value for _card_id, value in route)
        complete = printed >= remaining
        overrun = max(0, printed - remaining) if complete else 0
        preference = _preference(route, ctx.prize_plan, ctx)
        structural = (int(complete), overrun if complete else printed, len(route))
        candidates.append((structural, preference, route, printed, overrun))
    _structural, preference, route, printed, overrun = max(
        candidates, key=lambda row: (row[0], row[1]))
    return PrizeMap(remaining, tuple(card_id for card_id, _value in route),
                    printed, overrun, preference)


def _liability(body, ctx) -> tuple[int, int]:
    card_id = int(body.card.card_id)
    return card_id, int(getattr(ctx.facts(card_id), "prize_value", 1) or 1)


def _until_game(route, remaining):
    chosen, printed = [], 0
    for liability in route:
        chosen.append(liability)
        printed += liability[1]
        if printed >= remaining:
            break
    return tuple(chosen)


def _preference(route, plan: PrizePlan, ctx) -> tuple[int, ...]:
    card_ids = tuple(card_id for card_id, _value in route)
    limit = len(card_ids)

    def positions(selector):
        return tuple(index for index, card_id in enumerate(card_ids)
                     if selector == card_id or (isinstance(selector, str)
                                                and selector in ctx.card_roles(card_id)))

    offers = []
    for selector in plan.offer:
        found = positions(selector)
        offers.append(limit - found[0] if found else 0)
    protects = []
    for selector in plan.protect:
        found = positions(selector)
        protects.append(found[-1] + 1 if found else limit + 1)
    return (*offers, *protects)


__all__ = ("PrizeMap", "derive_prize_map")
