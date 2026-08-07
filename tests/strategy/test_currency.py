"""Currency — the derived exchange rates between the value scales (`common/currency.py`, ADR-0078).

What makes a rate legitimate is that a reviewer can RECOMPUTE it, so the recomputations live beside
the constants. A constant appearing here without a derivation is the fudge ADR-0065 forbids, and
`_PRIZE_UNIT = 12` is the standing example of what it costs.
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


# The ONE place the CSV's `Rule` text is mapped to `CardStat` flags — nothing in `src/` joins the
# two. Prize NUMBERS stay absent: every test resolves them through `CardStat.prize_value`.
_RULE_FLAGS = {"n/a": dict(ex=False, megaEx=False),
               "Pokémon ex": dict(ex=True, megaEx=False),
               "Mega Pokémon ex": dict(ex=True, megaEx=True)}


def _bodies() -> dict:
    """``{Card ID: (hp, Rule)}`` for every BODY in the card set — Trainers and Energy report no HP.
    ONE walk, shared by both recomputations: two ideas of "the population" is ADR-0087's charge."""
    out = {}
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            hp = int(row["HP"]) if (row.get("HP") or "").strip().isdigit() else 0
            if hp > 0:
                out[row["Card ID"]] = (hp, (row.get("Rule") or "n/a").strip())
    assert len(out) == 1061                    # the population ADR-0100 measured
    assert set(r for _hp, r in out.values()) == set(_RULE_FLAGS), (
        "the card set uses a Rule this file does not know — the mapping above is incomplete, and "
        "every prize figure derived from it is understated")
    return out


def _prize_of(rule: str) -> int:
    """The prizes a body under ``rule`` yields, through the SHIPPED reader (`CardStat.prize_value`).
    Called rather than restated: `common.scouting` must not import `common.strategy`."""
    from common.scouting.provider import CardStat
    return CardStat(0, **_RULE_FLAGS[rule]).prize_value


@pytest.mark.req("REQ-CURRENCY-0001")
def test_prize_damage_rate_recomputes_from_the_card_set():
    """ADR-0100 §3 / ADR-0078 decision 2. This test IS the recomputation — the median HP-per-prize
    over every body at `docs/rules.md` §6 values; pinning the literal would tune by another name."""
    per_prize = [hp / _prize_of(rule) for hp, rule in _bodies().values()]
    assert statistics.median(per_prize) == PRIZE_DAMAGE_RATE


@pytest.mark.req("REQ-CURRENCY-0002")
def test_the_hoist_keeps_every_existing_import_working():
    """ADR-0078: the constant moved homes, it did not change value; `promote_retreat_value` re-exports."""
    from common import promote_retreat_value as prv
    assert prv.PRIZE_DAMAGE_RATE is PRIZE_DAMAGE_RATE
    assert prize_to_damage(3.0) == pytest.approx(300.0)   # a 3-prize body, in damage
    assert prize_to_damage(0.0) == 0.0


@pytest.mark.req("REQ-CURRENCY-0003")
def test_the_worth_leg_stays_absent_until_its_anchor_is_captured():
    """ADR-0078 decision 3: there is NO general worth<->damage rate, and inventing one is the ADR-0065
    fudge. ADR-0080 ruled it MOOT rather than deriving it, so this guard is permanent, not pending."""
    assert not hasattr(currency, "WORTH_DAMAGE_RATE")
    assert not hasattr(currency, "prize_to_worth")

    from common.card_worth import ENERGY_TIER, TAG_TIER
    from common.hold_value import ITEM_HOLD_FLOOR
    from common.strategy.context import ENERGY_RECOVER
    # The ~9x disagreement, asserted so it cannot drift silently before #199 rules it.
    trainer_rate = currency.ITEM_HOLD_WORTH_RATE
    energy_rate = ENERGY_RECOVER / ENERGY_TIER
    assert trainer_rate == pytest.approx(1.0)
    assert ITEM_HOLD_FLOOR == pytest.approx(TAG_TIER["gust"]), (
        "the finiteness floor is the disruption-Trainer band, which is WHY the seam's rate is 1.0 — "
        "if the two part company the catalogue row above stops describing anything")
    assert energy_rate == pytest.approx(160 / 3 / 8)      # ADR-0078 (#172): the derived rate
    assert energy_rate / trainer_rate > 6          # same two scales, two answers — no single rate


@pytest.mark.req("REQ-CURRENCY-0004")
def test_the_deploy_band_is_present_pinned_and_labelled_as_a_preservation_choice():
    """ADR-0086 amendment C. `DEPLOY_BAND / DEPLOY_WORTH_SCALE` has units of damage-per-worth-point —
    a worth<->damage rate scoped to ONE seam, which the module must label as such in prose."""
    from common.card_worth import ROLE_TIER

    assert currency.DEPLOY_WORTH_SCALE == max(ROLE_TIER.values())   # derived, not invented
    assert currency.DEPLOY_WORTH_SCALE == pytest.approx(30.0)

    # A FULL-relevance deploy lands inside the range of the rungs it replaces (the deleted
    # bench/fetch rung weights), so the swap starts behaviour-preserving.
    assert 12.0 <= currency.DEPLOY_BAND <= 25.0

    # ...and the honesty is in the file, not only in the ADR.
    src = inspect.getsource(currency)
    assert "preservation" in src.lower()
    assert "never a derivation" in src.lower() or "not a derivation" in src.lower()
    assert "reconcil" in src.lower()          # the debt, should a general rate ever land


@pytest.mark.req("REQ-CURRENCY-0005")
def test_the_target_ceiling_is_the_card_sets_own_prize_ceiling():
    """Issue #313 item 2g: recomputed HERE from the card set, not pinned. Two spellings held together
    (ADR-0087) because `common.scouting` must not depend on `common.strategy`."""
    from common import needs
    from common.strategy.context import MAX_PRIZE_VALUE

    assert max(_prize_of(rule) for _hp, rule in _bodies().values()) == MAX_PRIZE_VALUE == 3

    # ...plus the survival term's own cap — the bound ADR-0076 Amendment E quotes ("max ~3.9").
    assert needs.TARGET_VALUE_CEILING == MAX_PRIZE_VALUE + needs._SURVIVAL_CAP
    assert needs.TARGET_VALUE_CEILING == pytest.approx(3.9)


@pytest.mark.req("REQ-CURRENCY-0006")
def test_the_gust_target_band_is_the_disruption_tier_and_the_rate_falls_out_of_it():
    """Issue #313 item 2g / ADR-0080 decision 4 — the prize<->worth seam on `DEPLOY_BAND`'s terms: the
    BAND is the shipped disruption tier, so the crossing introduces NO new number."""
    from common import needs
    from common.card_worth import TAG_TIER

    ceiling = needs.TARGET_VALUE_CEILING
    assert currency.GUST_TARGET_BAND == TAG_TIER["gust"] == pytest.approx(10.0)
    assert currency.GUST_TARGET_WORTH_RATE == pytest.approx(TAG_TIER["gust"] / ceiling)

    # A full-ceiling target is worth exactly the band, and the clamp is what keeps a band a band.
    assert currency.target_value_to_worth(ceiling) == pytest.approx(currency.GUST_TARGET_BAND)
    assert currency.target_value_to_worth(99.0) == pytest.approx(currency.GUST_TARGET_BAND)
    assert currency.target_value_to_worth(0.0) == 0.0
    # Written as the rate rather than as `2.564`, so this tracks a re-band of the tiers instead of
    # pinning yesterday's quotient.
    assert currency.target_value_to_worth(1.0) == pytest.approx(currency.GUST_TARGET_WORTH_RATE)
    assert 2.4 < currency.target_value_to_worth(1.0) < 2.7    # ...and that IS the incumbent's median

    src = inspect.getsource(currency)
    assert "prize" in src.lower() and "scoped to one seam" in src.lower()


@pytest.mark.req("REQ-CURRENCY-0006")
def test_the_gust_target_slot_can_now_outrank_the_cards_own_latent_worth():
    """A held Boss's Orders competes for its own `gust_target` slot against the `general` latent-worth
    slot, whose CEILING is 4.5 — fed a raw prize-equivalent the gust slot topped out at 3.9 (ADR-0107)."""
    from common import needs
    from common.card_worth import TAG_TIER
    from common.pilot import _GENERAL_WORTH_W

    general_ceiling = TAG_TIER["gust"] * _GENERAL_WORTH_W               # == 4.5
    assert currency.target_value_to_worth(needs.TARGET_VALUE_CEILING) > general_ceiling
    assert currency.target_value_to_worth(2.0) > general_ceiling        # ...as does a 2-prize body
    assert needs.TARGET_VALUE_CEILING < general_ceiling  # ...and the RAW prize-equivalent never could
