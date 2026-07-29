"""Currency — the derived exchange rates between the value scales (`common/currency.py`, ADR-0078).

The Prize Damage Rate's recomputation moved here from `test_promote_retreat_value.py` when ADR-0078
hoisted the constant out of the promote/retreat module: the property that makes it legitimate is that
a reviewer can RECOMPUTE it, so the test belongs beside the constant rather than beside its first
consumer.

The second test is the one that matters most for #199: it asserts the Worth leg stays ABSENT until
its corpus anchor is captured. A constant appearing here without a derivation is precisely the fudge
ADR-0065 forbids, and `_PRIZE_UNIT = 12` is the standing example of what it costs.
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

import pytest

from common import currency
from common.currency import PRIZE_DAMAGE_RATE, prize_to_damage

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.req("REQ-CURRENCY-0001")
def test_prize_damage_rate_recomputes_from_the_card_set():
    """ADR-0073 §3 / ADR-0078 decision 2: the Prize Damage Rate is DERIVED, so a reviewer can
    recompute it and a future set can re-derive it. This test IS that recomputation — the median
    HP-per-prize over every body in `data/EN_Card_Data.csv` at the `docs/rules.md` §6 prize values
    (Mega ex 3, ex 2, else 1).

    Pinning the literal instead would make the constant tuned-by-another-name."""
    prizes = {"n/a": 1, "Pokémon ex": 2, "Mega Pokémon ex": 3}
    bodies = {}
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            hp = int(row["HP"]) if (row.get("HP") or "").strip().isdigit() else 0
            if hp > 0:                                    # Trainers / Energy report no HP
                bodies[row["Card ID"]] = hp / prizes[(row.get("Rule") or "n/a").strip()]
    assert len(bodies) == 1061                            # the population ADR-0073 measured
    assert statistics.median(bodies.values()) == PRIZE_DAMAGE_RATE


@pytest.mark.req("REQ-CURRENCY-0002")
def test_the_hoist_keeps_every_existing_import_working():
    """ADR-0078: the constant moved homes, it did not change value. `promote_retreat_value` re-exports
    it, so ADR-0073's consumers and tests are untouched by the hoist."""
    from common import promote_retreat_value as prv
    assert prv.PRIZE_DAMAGE_RATE is PRIZE_DAMAGE_RATE
    assert prize_to_damage(3.0) == pytest.approx(300.0)   # a 3-prize body, in damage
    assert prize_to_damage(0.0) == 0.0


@pytest.mark.req("REQ-CURRENCY-0003")
def test_the_worth_leg_stays_absent_until_its_anchor_is_captured():
    """ADR-0078 decision 3, and the guard that keeps #199 honest: there is NO worth↔damage rate, and
    inventing one is the ADR-0065 fudge. The two shipped constant-pairs that price the same object on
    both scales disagree by ~9x, so no pair-matching shortcut exists either — the rate needs a
    keep-side corpus anchor the corpus does not yet hold.

    This test FAILS the moment someone adds the constant, which is the point: it must arrive with
    #199's derivation, not ahead of it."""
    assert not hasattr(currency, "WORTH_DAMAGE_RATE")
    assert not hasattr(currency, "prize_to_worth")

    from common.card_worth import ENERGY_TIER, TAG_TIER
    from common.strategy.context import ENERGY_RECOVER
    from common.pilot import _DENIAL_ITEM_COST
    # The ~9x disagreement, asserted so it cannot drift silently before #199 rules it.
    trainer_rate = _DENIAL_ITEM_COST / TAG_TIER["gust"]
    energy_rate = ENERGY_RECOVER / ENERGY_TIER
    assert trainer_rate == pytest.approx(1.0)
    assert energy_rate == pytest.approx(160 / 3 / 8)      # ADR-0078 (#172): the derived rate
    assert energy_rate / trainer_rate > 6          # same two scales, two answers — no single rate
