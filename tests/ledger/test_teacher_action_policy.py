from types import SimpleNamespace

from common.api import ActionIdentity
from common.observation import Card, Option, SelectPrompt
from common.options import LegalAction
from cgpy.experiment import (
    ALL_LEGAL_ACTION_POLICY, MEGA_STARMIE_ACTION_POLICY,
    admissible_teacher_actions, teacher_action_policy_for_agent,
)


def _action(name, *selection):
    return LegalAction(ActionIdentity(name), tuple(selection), (tuple(selection),), ())


def _observation(effect_id, card_ids):
    return SimpleNamespace(select=SelectPrompt(
        type=None, context=None, min_count=0, max_count=2,
        remain_damage_counter=None, remain_energy_cost=None,
        options=tuple(Option(index=index) for index in range(len(card_ids))),
        deck=tuple(Card(card_id, index, 0)
                   for index, card_id in enumerate(card_ids)),
        context_card=None, effect=Card(effect_id, None, 0)))


def test_all_legal_policy_preserves_every_engine_action():
    actions = (_action("decline"), _action("pick", 0))

    assert admissible_teacher_actions(
        _observation(1086, (1030,)), actions, ALL_LEGAL_ACTION_POLICY) == actions


def test_mega_starmie_poffin_always_takes_the_maximum_staryu_count():
    actions = (
        _action("decline"), _action("one", 0), _action("two", 0, 1),
    )

    assert admissible_teacher_actions(
        _observation(1086, (1030, 1030)), actions,
        MEGA_STARMIE_ACTION_POLICY) == (actions[2],)


def test_mega_signal_and_salvatore_never_decline_a_live_target():
    actions = (_action("decline"), _action("fetch", 0))

    for effect_id in (1145, 1189):
        assert admissible_teacher_actions(
            _observation(effect_id, (1031,)), actions,
            MEGA_STARMIE_ACTION_POLICY) == (actions[1],)


def test_hilda_prefers_mega_starmie_then_keeps_both_energy_choices():
    pokemon = (_action("decline"), _action("cinderace", 0), _action("starmie", 1))
    energy = (_action("decline"), _action("water", 0), _action("ignition", 1))

    assert admissible_teacher_actions(
        _observation(1225, (666, 1031)), pokemon,
        MEGA_STARMIE_ACTION_POLICY) == (pokemon[2],)
    assert admissible_teacher_actions(
        _observation(1225, (3, 17)), energy,
        MEGA_STARMIE_ACTION_POLICY) == energy[1:]


def test_action_policy_is_deck_scoped():
    assert teacher_action_policy_for_agent("mega_starmie") == MEGA_STARMIE_ACTION_POLICY
    assert teacher_action_policy_for_agent("dragapult_ex") == ALL_LEGAL_ACTION_POLICY


def test_exhausted_search_keeps_its_only_legal_decline():
    actions = (_action("decline"),)

    for effect_id in (1086, 1145, 1189, 1225):
        assert admissible_teacher_actions(
            _observation(effect_id, ()), actions,
            MEGA_STARMIE_ACTION_POLICY) == actions
