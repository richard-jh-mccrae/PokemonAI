"""One board, one number: worth × where-it-sits, summed over both sides, mine minus theirs.

The whole equation (docs/plans/PokemonAI_Ledger_Plan.md §1): every visible card contributes its
worth times a zone multiplier; attached energy pays only where a unit fills an attack slot;
damage scales a body toward `damage_floor` and HP below zero counts as zero, so overkill buys
nothing; free bench slots hold harmonic option value, so the last slot is the dear one;
rule-box bodies carry prize liability; the opponent's unseen cards are counted, never read.
Everything unpriceable degrades to a floor and lands in `Valuation.gaps` — the decision still
happens, the gap is the worklist."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from common.board import BoardState
from common.board.nodes import Body, Side

from .worth import (Demand, LedgerContext, any_attack_payable, base_worth, demand_scale,
                    line_reach, top_attack_cost, usable_units)


@dataclass(frozen=True)
class Valuation:
    """The number, its audit trail, and what could not be priced."""

    total: float
    parts: tuple[tuple[str, float], ...]
    gaps: tuple[str, ...]

    def part(self, name: str) -> float:
        return next((value for label, value in self.parts if label == name), 0.0)


def evaluate(board: BoardState, ctx: LedgerContext) -> Valuation:
    parts: list[tuple[str, float]] = []
    gaps: list[str] = []

    result = board.turn.result
    if isinstance(result, (int, bool)) and not isinstance(result, bool) and result >= 0:
        if int(result) == 2:
            # The engine's simultaneous outcome (result 2) is a DRAW: worth neither the win
            # nor the loss, so a line that draws still beats a line that loses.
            parts.append(("result", 0.0))
        else:
            won = int(result) == board.seat
            parts.append(("result", ctx.weights.win_value if won else -ctx.weights.win_value))

    for label, side, sign in (("me", board.me, 1.0), ("them", board.them, -1.0)):
        own = sign > 0
        for name, value in _side_parts(side, ctx, gaps, own=own,
                                       deck_counts=board.deck_counts if own else None):
            parts.append((f"{label}.{name}", sign * value))

    parts.append(("prize_race",
                  ctx.weights.prize_race * (board.them.prize_count - board.me.prize_count)))
    return Valuation(total=sum(value for _, value in parts),
                     parts=tuple(parts), gaps=tuple(gaps))


def _side_parts(side: Side, ctx: LedgerContext, gaps: list, *, own: bool, deck_counts):
    weights = ctx.weights
    demand = Demand.read(side, ctx)
    # The reach gate for this side's evolution lines: an opponent's hand and deck are unknown,
    # which gates their future colorless slots at the partial credit, never at zero.
    reach = line_reach(demand.hand_name_counts, deck_counts if own else None, ctx)
    copies: Counter = Counter()
    bodies_value = 0.0
    for body in side.bodies:
        # The Nth fielded copy of the same card saturates: its role is already being done.
        bodies_value += _body_value(body, ctx, gaps, reach=reach, own=own,
                                    is_active=body is side.active,
                                    discount=weights.surplus_copy ** copies[body.card.card_id])
        copies[body.card.card_id] += 1
    yield "bodies", bodies_value
    if side.active is not None:
        worth, _ = base_worth(side.active.card.card_id, side.active.card.facts, ctx, own=own)
        ready = any_attack_payable(side.active.card.facts, side.active.energies)
        yield "active", (weights.active_premium * worth
                         * (1.0 if ready else weights.active_unready_fraction))
    # The clamp bounds a corrupt benchMax: no printed format offers more than 8 slots.
    yield "bench_slots", weights.bench_slot_value * _harmonic(
        min(8, max(0, side.bench_max - len(side.bench))))
    yield "liability", -weights.prize_liability * sum(
        max(0, _prize_value(body) - 1) for body in side.bodies)

    if own and side.hand is not None:
        yield "hand", _bag_value(side.hand, weights.zone_in_hand, demand, ctx, gaps,
                                 deck_counts)
    else:
        yield "hand", (side.hand_count * weights.opponent_unknown_card_worth
                       * weights.zone_in_hand)

    if own and deck_counts is not None:
        total = 0.0
        for card_id, count in deck_counts:
            worth, gap = base_worth(card_id, ctx.facts(card_id), ctx)
            if gap:
                gaps.append(f"deck: {gap}")
            total += count * worth * weights.zone_in_deck
        yield "deck", total
    else:
        unknown = (weights.opponent_unknown_card_worth if not own
                   else weights.unknown_card_worth)
        yield "deck", side.deck_count * unknown * weights.zone_in_deck

    discard = 0.0
    for card in side.discard:
        worth, gap = base_worth(card.card_id, card.facts, ctx, own=own)
        if gap:
            gaps.append(f"discard: {gap}")
        discard += worth * weights.zone_in_discard
    yield "discard", discard

    yield "status", -(weights.status_asleep * side.asleep
                      + weights.status_paralyzed * side.paralyzed
                      + weights.status_confused * side.confused
                      + weights.status_poisoned * side.poisoned
                      + weights.status_burned * side.burned)


def _body_value(body: Body, ctx: LedgerContext, gaps: list, *, reach=None,
                discount: float = 1.0, own: bool = True, is_active: bool = False) -> float:
    weights = ctx.weights
    worth, gap = base_worth(body.card.card_id, body.card.facts, ctx, own=own)
    if gap:
        gaps.append(f"in play: {gap}")
    value = worth * discount * weights.zone_in_play

    usable = usable_units(body.card.facts, body.energies, ctx, reach)
    useless = len(body.energies) - usable
    energy_worth = 0.0
    for card in body.energy_cards:
        # An end-of-turn-discarding Energy on a BENCHED body evaporates before the body can
        # ever attack (ADR-0150): its worth is a rental nobody rides, priced zero.
        if not is_active and "discard_eot" in (getattr(card.facts, "tags", ()) or ()):
            continue
        unit_worth, gap = base_worth(card.card_id, card.facts, ctx, own=own)
        if gap:
            gaps.append(f"attached: {gap}")
        energy_worth += unit_worth
    if body.energies and not body.energy_cards:
        energy_worth = len(body.energies) * weights.kind_worth["energy"]
    per_unit = energy_worth / len(body.energies) if body.energies else 0.0
    value += per_unit * (usable * weights.zone_attached_usable
                         + useless * weights.zone_attached_useless)
    if weights.concentration and body.energies:
        cost = top_attack_cost(body.card.facts, ctx, reach)
        if cost > 0:
            progress = min(1.0, usable / cost)
            value += weights.concentration * worth * discount * progress * progress

    for card in body.tools:
        tool_worth, gap = base_worth(card.card_id, card.facts, ctx, own=own)
        if gap:
            gaps.append(f"tool: {gap}")
        value += tool_worth * weights.zone_tool_attached
    for card in body.pre_evolution:
        under_worth, gap = base_worth(card.card_id, card.facts, ctx, own=own)
        if gap:
            gaps.append(f"under: {gap}")
        value += under_worth * weights.zone_under_body

    # Size is worth (ADR-0151): printed max HP needs no store record, so even an unknown
    # opponent body carries threat weight — and the multiplier below makes chip damage a
    # constant real loss per HP on any body.
    value += weights.hp_value * (body.max_hp / 100.0)
    hp_fraction = (max(0, body.hp) / body.max_hp) if body.max_hp > 0 else 1.0
    return value * (weights.damage_floor + (1.0 - weights.damage_floor) * hp_fraction)


def _bag_value(bag, zone: float, demand: Demand, ctx: LedgerContext, gaps: list,
               deck_counts) -> float:
    # A copy already fielded counts against the hand copy's demand: same job, already staffed.
    copies_seen: Counter = Counter(demand.body_id_counts)
    total = 0.0
    for card in bag:
        worth, gap = base_worth(card.card_id, card.facts, ctx)
        if gap:
            gaps.append(f"hand: {gap}")
        scale = demand_scale(card.card_id, card.facts, demand,
                             copies_seen[card.card_id], ctx, deck_counts)
        copies_seen[card.card_id] += 1
        total += worth * scale * zone
    return total


def _prize_value(body: Body) -> int:
    return getattr(body.card.facts, "prize_value", 1) if body.card.facts is not None else 1


def _harmonic(count: int) -> float:
    return sum(1.0 / k for k in range(1, count + 1))


__all__ = ("Valuation", "evaluate")
