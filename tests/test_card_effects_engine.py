"""Effect Clauses on the committed native engine — the measured-magnitude smoke gate.

Engine-backed (drives the real probe, like ``test_lethal_engine.py``), offline on
Windows + Linux. Proves the probe→classify pipeline reads the *quantities* the boolean
tags discard: an unambiguous draw trainer measures its printed count, unambiguous heal
trainers measure their printed amounts. Card texts verified at source (cg.api
``all_card_data``), never memory:

  * 1224 Cheren (Supporter): "Draw 3 cards." — deterministic on the stable pass.
  * 1112 Super Potion (Item): "Heal 60 damage from 1 of your Pokémon. If you healed
    any damage in this way, discard an Energy from that Pokémon." — combat pass;
    also carries the measured ``discard_own_energy`` rider.
  * 1117 Potion (Item): "Heal 30 damage from 1 of your Pokémon." — combat pass.

Heal needs the combat scenario to align (a damaged Pokémon when the card is drawn),
which happens ~1-in-N games — the same variance the functions builder absorbs with
``_COMBAT_PASSES``. These tests retry a bounded number of passes and *skip* if the
scenario never aligned (alignment is stochastic infrastructure, not the claim under
test); a *wrong measured amount* always fails.
"""
import pytest

from meta_tracker.card_effects import classify_effect_clauses, merge_clauses
from meta_tracker.cards import load_cards
from meta_tracker.probe_cards import probe_card

_HEAL_PASSES = 30   # p(align) ~ 0.2/pass -> p(never) ~ 0.1%; passes are ~ms on the native engine


@pytest.fixture(scope="module")
def cards():
    return load_cards()


@pytest.mark.req("REQ-EFFECT-0009")
def test_cheren_measures_draw_3(cards):
    # "Draw 3 cards." — the stable pass is deterministic (the card plays as soon as
    # it is drawn), so this is a hard assert: exactly 3 DRAW logs -> amount 3.
    rec = probe_card(1224, cards, attack=False)
    assert rec is not None, "Cheren never became playable — probe harness regression?"
    clauses = classify_effect_clauses(cards[1224], probe=rec)
    assert {"kind": "draw", "amount": 3} in clauses


def _measured_heal(cid, cards):
    """Max heal clause across bounded combat passes (None if never aligned)."""
    measured = []
    for _ in range(_HEAL_PASSES):
        rec = probe_card(cid, cards, attack=True)
        if rec is None:
            continue
        measured = merge_clauses(measured, classify_effect_clauses(cards[cid], probe=rec))
        if any(c["kind"] == "heal" for c in measured):
            break                             # aligned — the amount is the claim under test
    return next((c for c in measured if c["kind"] == "heal"), None)


@pytest.mark.req("REQ-EFFECT-0010")
def test_super_potion_measures_heal_60_with_discard_rider(cards):
    heal = _measured_heal(1112, cards)
    if heal is None:
        pytest.skip("combat scenario never aligned (stochastic); re-run")
    assert heal["amount"] == 60
    assert heal.get("rider") == "discard_own_energy"   # own ENERGY->DISCARD after the heal


@pytest.mark.req("REQ-EFFECT-0010")
def test_potion_measures_heal_30(cards):
    heal = _measured_heal(1117, cards)
    if heal is None:
        pytest.skip("combat scenario never aligned (stochastic); re-run")
    assert heal["amount"] == 30


@pytest.mark.req("REQ-EFFECT-0017")
def test_wallys_compassion_observes_mega_only(cards):
    # The restriction-observation board (ADR-0032 item 6): a damaged Mega Lucario ex
    # retreated to the Bench behind a damaged non-Mega Active. Wally's Compassion
    # ("Heal all damage from 1 of your Mega Evolution Pokemon ex") must OFFER only the
    # bench Mega — the damaged Active's exclusion is the observed `mega_only`. The
    # drive handles both setup cases deterministically; retries absorb shuffle noise
    # (mulligans), a wrong offer always fails.
    from meta_tracker.card_effects import derive_restriction
    from meta_tracker.probe_restrictions import probe_heal_restriction

    last = None
    for _ in range(3):
        rec = probe_heal_restriction(1229, cards)
        if not rec.get("error"):
            got = derive_restriction(rec["board"], rec["offered"])
            assert got == {"restriction": "mega_only"}, \
                f"offered {rec['offered']} on board {rec['board']}"
            return
        last = rec["error"]
    pytest.fail(f"observation board never assembled: {last}")
