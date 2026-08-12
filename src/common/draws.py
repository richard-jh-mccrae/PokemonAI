"""Scalar draw-clause interpretation for Bellman chance nodes."""
from __future__ import annotations

from collections.abc import Mapping


_RIDERS = frozenset({"shuffle_own_hand_in", "shuffle_both_hands"})
_AMOUNT_CONDITIONS = frozenset({
    "coin_tails", "exactly_6_prizes_remaining", "opp_3_or_fewer_prizes",
    "hand_size_10_plus_after_draw",
})


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def draw_shape_problem(clause: Mapping) -> str | None:
    if clause.get("kind") != "draw":
        return "kind is not `draw`"
    if not _positive_int(clause.get("amount")):
        return "`amount` must be a positive integer"
    if clause.get("rider") not in (None, *_RIDERS):
        return "unsupported draw rider"
    if clause.get("condition") not in (None, "pokemon_ko_last_turn"):
        return "unsupported draw condition"
    own_if = clause.get("amount_if")
    opponent_if = clause.get("opponent_amount_if")
    for branch in (own_if, opponent_if):
        if branch is None:
            continue
        if (not isinstance(branch, Mapping)
                or branch.get("condition") not in _AMOUNT_CONDITIONS
                or set(branch) != {"condition", "amount"}
                or not _positive_int(branch.get("amount"))):
            return "unsupported conditional draw amount"
    opponent = clause.get("opponent_amount")
    if opponent is not None and not _positive_int(opponent):
        return "invalid opponent draw amount"
    if opponent_if is not None and (opponent is None or own_if is None):
        return "opponent conditional draw lacks a shared branch"
    if (own_if is not None and opponent_if is not None
            and own_if["condition"] != opponent_if["condition"]):
        return "draw conditions disagree"
    if (clause.get("rider") == "shuffle_both_hands") != (opponent is not None):
        return "symmetric shuffle and opponent draw must occur together"
    return None


def _condition_holds(condition: str, my_prizes: int, opponent_prizes: int, *,
                     my_hand_size: int | None, base_amount: int) -> bool:
    if condition == "exactly_6_prizes_remaining":
        return my_prizes == 6
    if condition == "opp_3_or_fewer_prizes":
        return 0 < opponent_prizes <= 3
    if condition == "hand_size_10_plus_after_draw":
        return my_hand_size is not None and max(0, my_hand_size - 1) + base_amount >= 10
    return False


def draw_branches(clause: Mapping, my_prizes_remaining: int,
                  opponent_prizes_remaining: int, *,
                  my_hand_size: int | None = None) -> tuple[tuple[int, int], ...] | None:
    """Equally likely ``(mine, theirs)`` draw counts from a supported clause."""
    if draw_shape_problem(clause) is not None:
        return None
    base = (int(clause["amount"]), int(clause.get("opponent_amount") or 0))
    own_if = clause.get("amount_if")
    opponent_if = clause.get("opponent_amount_if")
    condition = ((own_if or opponent_if) or {}).get("condition")
    if condition is None:
        return (base,)
    alternate = (int((own_if or {}).get("amount", base[0])),
                 int((opponent_if or {}).get("amount", base[1])))
    if condition == "coin_tails":
        return (base, alternate)
    return (alternate,) if _condition_holds(
        condition, my_prizes_remaining, opponent_prizes_remaining,
        my_hand_size=my_hand_size, base_amount=base[0]) else (base,)


__all__ = ("draw_branches",)
