"""Independent text-oracle audit of function tags (``meta_tracker.function_audit``).

Lib-free: feeds synthetic ``(tags, text)`` pairs. The audit cross-checks probe-derived tags
against the card's rules text — a tag with no supporting text cue is a *suspected false
positive*; a strong text cue with no matching tag is a *suspected miss*. Heuristic by design.
"""
import pytest

from meta_tracker.function_audit import audit_card


@pytest.mark.req("REQ-FUNC-0012")
def test_tag_with_no_supporting_text_is_flagged_unsupported():
    # tagged `heal` but the text never mentions healing → suspect probe false positive
    unsupported, _ = audit_card(["heal"], "This attack does 30 damage to the Active Pokémon.")
    assert "heal" in unsupported


@pytest.mark.req("REQ-FUNC-0012")
def test_tag_supported_by_text_is_not_flagged():
    unsupported, _ = audit_card(["heal"], "Heal 30 damage from this Pokémon.")
    assert "heal" not in unsupported


@pytest.mark.req("REQ-FUNC-0012")
def test_strong_text_cue_without_tag_is_flagged_missing():
    # text clearly inflicts a Special Condition but the card wasn't tagged → suspect probe miss
    _, missing = audit_card([], "Your opponent's Active Pokémon is now Asleep.")
    assert "sleep" in missing


@pytest.mark.req("REQ-FUNC-0012")
def test_spread_supported_by_damage_counter_text():
    text = "Put 6 damage counters on your opponent's Benched Pokémon in any way you like."
    unsupported, missing = audit_card(["spread"], text)
    assert unsupported == [] and "spread" not in missing


@pytest.mark.req("REQ-FUNC-0012")
def test_counter_move_text_flags_missing_heal_and_spread():
    # Munkidori's Adrena-Brain — moving damage counters off mine onto the opponent's = heal + snipe.
    # Shipped as just `status` (from its attack), so the audit should flag both as missing.
    text = "you may move up to 3 damage counters from 1 of your Pokémon to 1 of your opponent’s Pokémon."
    _, missing = audit_card(["confuse"], text)   # Munkidori ships its attack's condition + this
    assert "heal" in missing and "spread" in missing


@pytest.mark.req("REQ-FUNC-0012")
def test_self_mill_for_damage_is_not_energy_denial():
    # Mega Abomasnow: discards from YOUR OWN deck for damage; "opponent" is a damage-reduction clause
    text = ("Discard the top 6 cards of your deck, this attack does 100 damage for each Basic Energy "
            "card you discarded. During your opponent's next turn, this Pokémon takes 30 less damage.")
    _, missing = audit_card([], text)
    assert "energy_denial" not in missing


@pytest.mark.req("REQ-FUNC-0012")
def test_retrieve_from_discard_pile_is_recycle():
    # Levincia (both-player stadium): "from their discard pile into their hand" is recycle
    text = "Each player may put up to 2 Basic Energy cards from their discard pile into their hand."
    _, missing = audit_card([], text)
    assert "recycle" in missing


@pytest.mark.req("REQ-FUNC-0012")
def test_cant_be_recycled_text_is_not_recycle():
    # Neutralization Zone: "can't be put into your hand or deck from the discard pile" — the opposite
    text = ("Prevent all damage to Pokémon without a Rule Box from the opponent's Pokémon ex. "
            "This card can’t be put into your hand or deck from the discard pile.")
    _, missing = audit_card([], text)
    assert "recycle" not in missing and "hand_disruption" not in missing


@pytest.mark.req("REQ-FUNC-0012")
def test_prevention_text_is_not_spread():
    # Battle Cage PREVENTS damage counters on the bench — protection, the opposite of spread
    text = "Prevent all damage counters from being placed on Benched Pokémon by effects of attacks and Abilities."
    _, missing = audit_card([], text)
    assert "spread" not in missing


@pytest.mark.req("REQ-FUNC-0012")
def test_opponent_discards_their_hand_is_hand_disruption():
    # Xerosic's Machinations says "their hand" (not "opponent's hand") — still hand disruption
    text = "Your opponent discards cards from their hand until they have 3 cards in their hand."
    _, missing = audit_card([], text)
    assert "hand_disruption" in missing


@pytest.mark.req("REQ-FUNC-0012")
def test_look_and_take_dig_and_draw_are_supported():
    # Drakloak's Recon Directive — dig+draw, both should read as supported (not false "unsupported")
    text = "Look at the top 2 cards of your deck and put 1 of them into your hand."
    unsupported, _ = audit_card(["dig", "draw"], text)
    assert unsupported == []


@pytest.mark.req("REQ-FUNC-0012")
def test_non_behavioral_tags_are_ignored_by_the_text_audit():
    # the audit only judges behavioral tags; any other label (e.g. a leftover structural one) is
    # not in the cue set, so it's never flagged "unsupported"
    unsupported, _ = audit_card(["item", "ace_spec"], "Draw 3 cards.")
    assert unsupported == []
