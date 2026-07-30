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

import inspect

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
    a derivation, not ahead of it. **It survived Issue #199** — ADR-0080 ran the anchor gate, found
    the corpus's one candidate priced 0.000 on both instruments (so the rate divided out), and ruled
    the rate MOOT for deny rather than deriving it. The guard therefore stays, permanently rather
    than pending, and ADR-0083's seam-scoped `DEPLOY_BAND` below is explicitly NOT this constant."""
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


@pytest.mark.req("REQ-CURRENCY-0004")
def test_the_deploy_band_is_present_pinned_and_labelled_as_a_preservation_choice():
    """ADR-0083 (Issue #197) amendment C — the honest half of the guard above.

    The Deploy Marginal's two Worth legs are dimensionless RATIOS (`marginal / DEPLOY_WORTH_SCALE`),
    so the Worth scale never escapes the Needs assignment and no universal rate is needed. But
    `DEPLOY_BAND / DEPLOY_WORTH_SCALE` still has units of damage-per-worth-point: it IS a
    worth<->damage rate, scoped to one seam. Amendment B made the rate local, small and honestly
    labelled — not unnecessary — and this test is where "honestly labelled" is enforced rather than
    merely asserted in prose.

    Three things are pinned:

    * the SCALE is the shipped ceiling on a single card's assignment contribution, not a fresh
      number — a ratio divided by an invented divisor would be the fudge wearing a different hat;
    * the BAND reproduces the incumbent rung range it replaces (+12..+25), which is what makes it a
      PRESERVATION choice the Decision Gate can check, and the check ADR-0073's `_PRIZE_UNIT = 12`
      (wrong by ~8x) never had;
    * the module says so in prose, so the third entry in ADR-0078's catalogue cannot be mistaken for
      a derivation by the next reader.
    """
    from common.card_worth import ROLE_TIER

    assert currency.DEPLOY_WORTH_SCALE == max(ROLE_TIER.values())   # derived, not invented
    assert currency.DEPLOY_WORTH_SCALE == pytest.approx(30.0)

    # The band lands a FULL-relevance deploy inside the range of the rungs it replaces, so the swap
    # starts behaviour-preserving. The incumbent range is the deleted bench/fetch rung weights.
    assert 12.0 <= currency.DEPLOY_BAND <= 25.0

    # ...and the honesty is in the file, not only in the ADR.
    src = inspect.getsource(currency)
    assert "preservation" in src.lower()
    assert "never a derivation" in src.lower() or "not a derivation" in src.lower()
    assert "reconcil" in src.lower()          # the debt, should a general rate ever land
