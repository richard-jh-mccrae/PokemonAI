"""**The Retreat Cost a body actually pays** — the grant-aware read, in one place (ADR-0100 §8,
Issue #392). Three shipped card shapes move the printed `CardStat.retreatCost`: a flat SIGNED
attached-Tool delta (`retreatReduction`; Gravity Gemstone is −1, so a retreat can cost MORE than
printed — Issue #306), a CONDITIONAL Tool (`retreatFreeAtHp`), and a BOARD-LEVEL Ability on ANOTHER
of my bodies (`retreatFreeGrant`), which no per-card read and no engine field could ever see.

Every read fails **CLOSED**: an unreadable or unmodelled grant charges the PRINTED cost.

⚠️ Two known gaps, both deliberately untouched here because closing either MOVES corpus decisions.
A fourth grant shape (Ethan's Magcargo 356, a SELF Ability conditional on its own attachments) is
unparsed, so it is charged its printed 3. And `Pilot._can_retreat`, `planner._promotion_ease` and
`planner._retreat_shortfall` consult NO board-level grant, so they still answer differently from
this module on a board with Latias ex benched. Both are owed to Issue #149.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from common.strategy.context import _METAL


@dataclass(frozen=True)
class RetreatPayment:
    """One reachable payment: physical card indices and each card's supplied-unit count."""

    card_indices: tuple[int, ...]
    supplied_units: tuple[int, ...]

    @property
    def total_units(self) -> int:
        return sum(self.supplied_units)


def payment_options(active: dict | None, cost: int, *, stat_of, combat) -> tuple[RetreatPayment, ...]:
    """Reachable unit-funded payments, stopping the instant a chosen card covers the remainder."""
    from common.board_delta import Unmodellable, units_for_cards

    required = max(0, int(cost))
    if required == 0:
        return (RetreatPayment((), ()),)
    if not active or stat_of is None or combat is None:
        raise Unmodellable("retreat payment lacks a readable Active, Stat Provider, or combat provider")
    holder = stat_of(active.get("id"))
    if holder is None:
        raise Unmodellable(f"{active.get('id')}: no holder stat for retreat payment")
    cards = tuple(active.get("energyCards") or ())
    counts = []
    for card in cards:
        units = units_for_cards(combat, (card,), holder_stat=holder)
        counts.append(len(units))

    reachable = []
    usable = tuple(index for index, count in enumerate(counts) if count > 0)
    for size in range(1, len(usable) + 1):
        for selected in combinations(usable, size):
            total = sum(counts[index] for index in selected)
            if total < required:
                continue
            if not any(total - counts[last] < required for last in selected):
                continue
            reachable.append(RetreatPayment(selected, tuple(counts[index] for index in selected)))
    return tuple(reachable)


def attached_tool_stats(body: dict | None, stat_of):
    """The ONE place the engine's ``tools`` list is resolved — it appears as bare ids AND as
    id-carrying dicts. Unknown ids are skipped."""
    if not body or stat_of is None:
        return
    for tool in (body.get("tools") or []):
        tid = tool.get("id") if isinstance(tool, dict) else tool
        tstat = stat_of(tid) if tid is not None else None
        if tstat is not None:
            yield tstat


def attached_retreat_delta(body: dict | None, stat_of) -> int:
    """The amount to SUBTRACT from a printed Retreat Cost. SIGNED (Issue #306): the sum can be
    negative, so this is not a subtraction of non-negatives."""
    total = 0
    for tool in attached_tool_stats(body, stat_of):
        total += tool.retreatReduction
    return total


def retreat_free_granted(active: dict | None, stat, *, my_bodies=(), stat_of, combat) -> bool:
    """``my_bodies`` is every in-play body on MY side, since the grantor is not the body retreating.
    Unknown predicate -> False (fail-closed). LATENT: no deck holding a grantor is built as a Pilot."""
    if not active or stat is None or stat_of is None:
        return False
    for body in my_bodies or ():
        cid = (body or {}).get("id")
        gstat = stat_of(cid) if cid is not None else None
        grant = getattr(gstat, "retreatFreeGrant", None) if gstat is not None else None
        if grant == "basic" and (getattr(stat, "stage", None) or "").lower() == "basic":
            return True
        if grant == "metal_attached" and combat is not None \
                and combat.attached_type_counts(active).get(_METAL):
            return True
    return False


def effective_retreat_cost(active: dict | None, *, stat_of, my_bodies=(), combat=None) -> int:
    """The count of Energy a retreat actually discards. The three grant shapes resolve in the order
    the rules make them bite; 0 on an unknown stat rather than a guess."""
    if not active or stat_of is None:
        return 0
    stat = stat_of(active.get("id"))
    if stat is None:
        return 0
    hp = active.get("hp") or 0
    for tstat in attached_tool_stats(active, stat_of):
        free_at = getattr(tstat, "retreatFreeAtHp", 0)
        if free_at and hp and hp <= free_at:
            return 0                                  # Rescue Board on a damaged holder
    cost = getattr(stat, "retreatCost", 0) - attached_retreat_delta(active, stat_of)
    if cost > 0 and retreat_free_granted(active, stat, my_bodies=my_bodies, stat_of=stat_of,
                                         combat=combat):
        return 0
    return max(0, cost)


__all__ = ("RetreatPayment", "payment_options", "attached_tool_stats", "attached_retreat_delta",
           "retreat_free_granted", "effective_retreat_cost")
