"""Scalar draw-clause interpretation for Ledger refresh transitions."""
from __future__ import annotations

from collections.abc import Mapping


_RIDERS = frozenset({
    "both_hands_to_bottom", "discard_basic_f_energy", "other_to_bottom", "self_switch",
    "shuffle_both_hands", "shuffle_own_hand_in", "shuffle_self_in",
})
_AMOUNT_CONDITIONS = frozenset({
    "coin_tails", "exactly_6_prizes_remaining", "opp_3_or_fewer_prizes",
    "hand_size_10_plus_after_draw", "all_own_pokemon_team_rocket",
})


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def draw_shape_problem(clause) -> str | None:
    if clause.kind != "draw":
        return "kind is not `draw`"
    if not _positive_int(clause.amount) and not _positive_int(clause.to_hand_size):
        return "`amount` or `to_hand_size` must be a positive integer"
    if clause.rider not in (None, *_RIDERS):
        return "unsupported draw rider"
    if clause.condition not in (None, "pokemon_ko_last_turn"):
        return "unsupported draw condition"
    own_if = clause.amount_if
    opponent_if = clause.opponent_amount_if
    for branch in (own_if, opponent_if):
        if branch is None:
            continue
        quantity_keys = set(branch) - {"condition"} if isinstance(branch, Mapping) else set()
        if (not isinstance(branch, Mapping)
                or branch.get("condition") not in _AMOUNT_CONDITIONS
                or quantity_keys not in ({"amount"}, {"to_hand_size"})
                or not _positive_int(branch.get(next(iter(quantity_keys), "")))):
            return "unsupported conditional draw amount"
    opponent = clause.opponent_amount
    if opponent is not None and not _positive_int(opponent):
        return "invalid opponent draw amount"
    if opponent_if is not None and (opponent is None or own_if is None):
        return "opponent conditional draw lacks a shared branch"
    if (own_if is not None and opponent_if is not None
            and own_if["condition"] != opponent_if["condition"]):
        return "draw conditions disagree"
    if (clause.rider == "shuffle_both_hands") != (opponent is not None):
        return "symmetric shuffle and opponent draw must occur together"
    return None


def _condition_holds(condition: str, my_prizes: int, opponent_prizes: int, *,
                     my_hand_size: int | None, base_amount: int,
                     all_own_pokemon_team_rocket: bool | None,
                     cards_leaving_hand: int) -> bool:
    if condition == "exactly_6_prizes_remaining":
        return my_prizes == 6
    if condition == "opp_3_or_fewer_prizes":
        return 0 < opponent_prizes <= 3
    if condition == "hand_size_10_plus_after_draw":
        return (my_hand_size is not None
                and max(0, my_hand_size - cards_leaving_hand) + base_amount >= 10)
    if condition == "all_own_pokemon_team_rocket":
        return all_own_pokemon_team_rocket is True
    return False


def _draw_count(amount, to_hand_size, hand_size: int | None,
                cards_leaving_hand: int) -> int:
    if _positive_int(to_hand_size):
        remaining = (0 if hand_size is None else
                     max(0, hand_size - cards_leaving_hand))
        return max(0, int(to_hand_size) - remaining)
    return int(amount or 0)


def draw_branches(clause, my_prizes_remaining: int,
                  opponent_prizes_remaining: int, *,
                  my_hand_size: int | None = None,
                  all_own_pokemon_team_rocket: bool | None = None,
                  cards_leaving_hand: int = 0,
                  ) -> tuple[tuple[int, int], ...] | None:
    """Equally likely ``(mine, theirs)`` draw counts from a supported draw Clause."""
    if draw_shape_problem(clause) is not None:
        return None
    base = (_draw_count(
                clause.amount, clause.to_hand_size, my_hand_size, cards_leaving_hand),
            int(clause.opponent_amount or 0))
    own_if = clause.amount_if
    opponent_if = clause.opponent_amount_if
    condition = ((own_if or opponent_if) or {}).get("condition")
    if condition is None:
        return (base,)
    alternate = (_draw_count(
                     (own_if or {}).get("amount", base[0]),
                     (own_if or {}).get("to_hand_size"), my_hand_size,
                     cards_leaving_hand),
                 int((opponent_if or {}).get("amount", base[1])))
    if condition == "coin_tails":
        return (base, alternate)
    return (alternate,) if _condition_holds(
        condition, my_prizes_remaining, opponent_prizes_remaining,
        my_hand_size=my_hand_size, base_amount=base[0],
        all_own_pokemon_team_rocket=all_own_pokemon_team_rocket,
        cards_leaving_hand=cards_leaving_hand) else (base,)


__all__ = ("draw_branches",)
