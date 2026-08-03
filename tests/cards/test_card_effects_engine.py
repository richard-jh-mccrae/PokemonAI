"""Effect Clauses on the committed NATIVE engine — the measured-magnitude smoke gate.

NATIVE-ONLY, enforced below (#178). These tests do not check cgpy; they DERIVE what a card does by
probing the engine (ADR-0032, the engine-audited effect compendium). Point them at the twin and they
measure cgpy against cgpy — circular, and the twin's `probe_card` scenarios do not align anyway, so
under `CG_ENGINE=py` they simply fail with a heal that was measured on nothing.


Engine-backed (drives the real probe, like ``test_lethal_engine.py``), offline on
Windows + Linux. Proves the probe→classify pipeline reads the *quantities* the boolean
tags discard: an unambiguous draw trainer measures its printed count, unambiguous heal
trainers measure their printed amounts. Card texts verified at source (cg.api
``all_card_data``), never memory:

  * 1224 Cheren (Supporter): "Draw 3 cards." — stable pass, with bounded retry if
    the probe deck itself caps the draw.
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

from conftest import on_cgpy_twin
from meta_tracker.card_effects import classify_effect_clauses, merge_clauses
from meta_tracker.cards import load_cards
from meta_tracker.probe_cards import probe_card

if on_cgpy_twin():
    pytest.skip("engine-audited effect probes: circular on the cgpy twin", allow_module_level=True)

# Re-sized from measurement, not from the estimate (#178). The old value was 30 on an assumed
# p(align) ~ 0.2/pass -> p(never) ~ 0.1%; running the module 25× showed the two heal probes failing
# to align ~4% of the time, so the real p(align) is ~0.10/pass and 30 passes was ~40× flakier than
# the comment claimed. That went unnoticed because a miss was a `pytest.skip` — invisible in CI.
# Now that a miss is a FAILURE the budget has to match the measured rate: 0.9^120 ~ 3e-6.
_HEAL_PASSES = 120  # p(align) ~ 0.10/pass MEASURED -> p(never) ~ 3e-6; passes ~ms on native engine


@pytest.fixture(scope="module")
def cards():
    return load_cards()


@pytest.mark.req("REQ-EFFECT-0009")
def test_cheren_measures_draw_3(cards):
    # "Draw 3 cards." — stable pass, with bounded retry on measured deck exhaustion.
    # Hard assert: exactly 3 DRAW logs -> amount 3.
    rec = probe_card(1224, cards, attack=False)
    assert rec is not None, "Cheren never became playable or every retry was deck-limited"
    clauses = classify_effect_clauses(cards[1224], probe=rec)
    assert {"kind": "draw", "amount": 3} in clauses


# A FAILURE, not a skip (#178). These probes drive the live native engine, so alignment is
# stochastic in principle — but `_HEAL_PASSES`=30 puts p(never) around 0.1%, and measured
# 2026-07-27 it aligned 25/25. A skip at that rate is not protecting the suite from bad luck; it
# is hiding the case that matters, a probe-harness regression that stops the scenario aligning at
# all — after which these tests report green-ish forever without measuring a thing. The module
# already takes this line elsewhere ("Cheren never became playable — probe harness regression?").
_NEVER_ALIGNED = ("combat scenario never aligned in %d passes — the claim was MEASURED on nothing. "
                  "For the rider case this also fires when the heal aligned but the RIDER never "
                  "did (Super Potion only discards an Energy if the healed body had one). Suspect "
                  "a probe-harness regression before bad luck; re-run once to tell them apart."
                  % _HEAL_PASSES)


def _measured_heal(cid, cards, *, rider=None):
    """Max heal clause across bounded combat passes (None if never aligned).

    ``rider`` names a rider the CALLER is going to assert. Pass it, or this loop stops one
    observation too early: a rider is a per-resolution fact (Super Potion only discards an Energy
    if the healed body had one), and `merge_clauses` keys on ``(kind, restriction, condition,
    rider)`` — so a riderless heal and a riderful heal are two SEPARATE clauses. Breaking on "any
    heal" could therefore stop before the rider was ever seen, and `next(... kind == "heal")` could
    return the riderless clause even when both were observed. Both bugs, one symptom: `assert None
    == 'discard_own_energy'` on a heal that measured 60 correctly.

    Caught by the #178 determinism backstop on its 11th repeat, ~2 weeks after the assertion was
    written — it was invisible before because a miss surfaced as a `pytest.skip`. The loop now
    stops on the clause the caller will actually assert.
    """
    def _pick(clauses):
        heals = [c for c in clauses if c["kind"] == "heal"]
        if rider is not None:
            return next((c for c in heals if c.get("rider") == rider), None)
        return heals[0] if heals else None

    measured = []
    for _ in range(_HEAL_PASSES):
        rec = probe_card(cid, cards, attack=True)
        if rec is None:
            continue
        measured = merge_clauses(measured, classify_effect_clauses(cards[cid], probe=rec))
        hit = _pick(measured)                 # aligned — the amount is the claim under test
        if hit is not None:
            return hit
    return _pick(measured)


@pytest.mark.req("REQ-EFFECT-0010")
def test_super_potion_measures_heal_60_with_discard_rider(cards):
    heal = _measured_heal(1112, cards, rider="discard_own_energy")
    assert heal is not None, _NEVER_ALIGNED
    assert heal["amount"] == 60
    assert heal.get("rider") == "discard_own_energy"   # own ENERGY->DISCARD after heal


@pytest.mark.req("REQ-EFFECT-0010")
def test_potion_measures_heal_30(cards):
    heal = _measured_heal(1117, cards)
    assert heal is not None, _NEVER_ALIGNED
    assert heal["amount"] == 30


@pytest.mark.req("REQ-EFFECT-0017")
def test_wallys_compassion_observes_mega_only(cards):
    # Restriction-observation board (ADR-0032 item 6): a damaged Mega Lucario ex
    # retreated to Bench behind a damaged non-Mega Active. Wally's Compassion
    # ("Heal all damage from 1 of your Mega Evolution Pokemon ex") must OFFER only the
    # bench Mega — damaged Active's exclusion is the observed `mega_only`. Drive
    # handles both setup cases deterministically; retries absorb shuffle noise
    # (mulligans), a wrong offer always fails
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
