"""Deck-scoped admissible actions for Teacher search."""
from __future__ import annotations


ALL_LEGAL_ACTION_POLICY = "all_legal-v1"
MEGA_STARMIE_ACTION_POLICY = "mega_starmie-v1"
SUPPORTED_ACTION_POLICIES = frozenset((
    ALL_LEGAL_ACTION_POLICY,
    MEGA_STARMIE_ACTION_POLICY,
))

_BUDDY_BUDDY_POFFIN = 1086
_MEGA_SIGNAL = 1145
_SALVATORE = 1189
_HILDA = 1225
_MEGA_STARMIE_EX = 1031


def teacher_action_policy_for_agent(agent: str) -> str:
    return (MEGA_STARMIE_ACTION_POLICY
            if str(agent) == "mega_starmie" else ALL_LEGAL_ACTION_POLICY)


def _selected_card_ids(select, action) -> tuple[int, ...]:
    card_ids = []
    for selection in action.selection:
        if not 0 <= selection < len(select.options):
            continue
        option = select.options[selection]
        card_id = option.cardId
        index = option.index
        if (card_id is None and select.deck is not None
                and isinstance(index, int) and 0 <= index < len(select.deck)):
            card_id = select.deck[index].card_id
        if card_id is not None:
            card_ids.append(int(card_id))
    return tuple(card_ids)


def admissible_teacher_actions(observation, actions, policy: str):
    actions = tuple(actions)
    if policy == ALL_LEGAL_ACTION_POLICY:
        return actions
    if policy != MEGA_STARMIE_ACTION_POLICY:
        raise ValueError(f"unsupported Teacher action policy {policy!r}")
    select = observation.select
    effect_id = None if select is None or select.effect is None else select.effect.card_id
    if effect_id == _BUDDY_BUDDY_POFFIN:
        maximum = max((len(action.selection) for action in actions), default=0)
        return tuple(action for action in actions if len(action.selection) == maximum)
    if effect_id in (_MEGA_SIGNAL, _SALVATORE, _HILDA):
        accepted = tuple(action for action in actions if action.selection)
        if not accepted:
            return actions
        if effect_id == _HILDA:
            mega = tuple(action for action in accepted
                         if _MEGA_STARMIE_EX in _selected_card_ids(select, action))
            if mega:
                return mega
        return accepted
    return actions


__all__ = (
    "ALL_LEGAL_ACTION_POLICY", "MEGA_STARMIE_ACTION_POLICY",
    "SUPPORTED_ACTION_POLICIES", "admissible_teacher_actions",
    "teacher_action_policy_for_agent",
)
