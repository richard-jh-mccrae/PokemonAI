"""Effect Clauses on the committed NATIVE engine — the measured-magnitude smoke gate (ADR-0032).

NATIVE-ONLY, enforced below: pointed at the twin these would measure cgpy against cgpy, and the
twin's `probe_card` scenarios do not align anyway. Heal needs the combat scenario to align (a
damaged Pokémon when the card is drawn), so those tests retry a bounded number of passes; a WRONG
measured amount always fails.
"""
import pytest

from conftest import on_cgpy_twin
from meta_tracker.card_effects import classify_effect_clauses, merge_clauses
from meta_tracker.cards import load_cards
from meta_tracker.probe_cards import probe_card

if on_cgpy_twin():
    pytest.skip("engine-audited effect probes: circular on the cgpy twin", allow_module_level=True)

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


# A FAILURE, not a skip: a skip hides the case that matters, a probe-harness regression that stops
# the scenario aligning at all — after which these tests report green forever, measuring nothing.
_NEVER_ALIGNED = ("combat scenario never aligned in %d passes — the claim was MEASURED on nothing. "
                  "For the rider case this also fires when the heal aligned but the RIDER never "
                  "did (Super Potion only discards an Energy if the healed body had one). Suspect "
                  "a probe-harness regression before bad luck; re-run once to tell them apart."
                  % _HEAL_PASSES)


def _measured_heal(cid, cards, *, rider=None):
    """Max heal clause across bounded combat passes (None if never aligned). ``rider`` names a rider
    the CALLER will assert — pass it, or the loop can stop before that clause was ever observed."""
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
    # A damaged Mega on the Bench behind a damaged non-Mega Active: the Active's exclusion from the
    # offer is the observed `mega_only`. Retries absorb shuffle noise; a wrong offer always fails.
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
