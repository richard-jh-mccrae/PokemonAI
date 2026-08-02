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


#: The `Rule` values `data/EN_Card_Data.csv` uses, and the `CardStat` flags each one means. This is
#: the ONE place the mapping is spelled: the CSV's Rule text is presentation, `CardStat.ex` /
#: `.megaEx` are what the engine hands the agent, and nothing in `src/` joins the two (the Provider is
#: built from engine card data, never from this CSV). The prize NUMBERS are deliberately absent —
#: every test below resolves them through `CardStat.prize_value`, the shipped reader, rather than
#: restating `{1, 2, 3}` and then checking a constant against its own restatement.
_RULE_FLAGS = {"n/a": dict(ex=False, megaEx=False),
               "Pokémon ex": dict(ex=True, megaEx=False),
               "Mega Pokémon ex": dict(ex=True, megaEx=True)}


def _bodies() -> dict:
    """``{Card ID: (hp, Rule)}`` for every BODY in the card set — Trainers and Energy report no HP.

    One walk, shared by both recomputations below. It was two near-identical walks (same filter, same
    `assert len(...) == 1061`) until Issue #313 item 2g added the second; two ideas of what "the
    population" is, in one file, is the shape ADR-0087 charges for at repo scale."""
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

    Called rather than restated on purpose: `common.scouting` must not import `common.strategy`, so
    `strategy.context.MAX_PRIZE_VALUE` and this property are two spellings of one fact and cannot be
    merged. Routing every test's prize figure through the property is what keeps them from drifting."""
    from common.scouting.provider import CardStat
    return CardStat(0, **_RULE_FLAGS[rule]).prize_value


@pytest.mark.req("REQ-CURRENCY-0001")
def test_prize_damage_rate_recomputes_from_the_card_set():
    """ADR-0100 §3 / ADR-0078 decision 2: the Prize Damage Rate is DERIVED, so a reviewer can
    recompute it and a future set can re-derive it. This test IS that recomputation — the median
    HP-per-prize over every body in `data/EN_Card_Data.csv` at the `docs/rules.md` §6 prize values
    (Mega ex 3, ex 2, else 1).

    Pinning the literal instead would make the constant tuned-by-another-name."""
    per_prize = [hp / _prize_of(rule) for hp, rule in _bodies().values()]
    assert statistics.median(per_prize) == PRIZE_DAMAGE_RATE


@pytest.mark.req("REQ-CURRENCY-0002")
def test_the_hoist_keeps_every_existing_import_working():
    """ADR-0078: the constant moved homes, it did not change value. `promote_retreat_value` re-exports
    it, so ADR-0100's consumers and tests are untouched by the hoist."""
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
    than pending, and ADR-0086's seam-scoped `DEPLOY_BAND` below is explicitly NOT this constant —
    nor is Issue #261 item 2f's seam-scoped `ITEM_HOLD_WORTH_RATE`, which is the trainer row of this
    very catalogue made explicit. That row USED to read `_DENIAL_ITEM_COST / TAG_TIER["gust"]`: a
    ratio between two constants that never met in an expression, which is precisely why nothing
    stopped it drifting. Reading it off the shipped rate instead is strictly stronger — the number
    this test guards is now the number the agent actually multiplies by.

    **`prize_to_worth` stays absent too, and Issue #313 item 2g did NOT add it** — that name would be
    the GENERAL prize↔worth rate, which composes through the missing leg above
    (`PRIZE_DAMAGE_RATE / WORTH_DAMAGE_RATE`) and so cannot exist while that leg does not.
    `target_value_to_worth` is a different animal and is guarded on its own terms below: it divides
    the opponent-target marginal by that marginal's OWN derived ceiling first, so what crosses is a
    dimensionless [0, 1] fraction of a Worth band, exactly as the deploy legs do."""
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
    """ADR-0086 (Issue #197) amendment C — the honest half of the guard above.

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
      PRESERVATION choice the Decision Gate can check, and the check ADR-0100's `_PRIZE_UNIT = 12`
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


@pytest.mark.req("REQ-CURRENCY-0005")
def test_the_target_ceiling_is_the_card_sets_own_prize_ceiling():
    """Issue #313 item 2g: the gust-target ratio's yardstick is DERIVED, so a reviewer can recompute
    it — and it is recomputed HERE from the card set, not pinned.

    Two spellings of one fact are pinned together, which is the net ADR-0087 asks for when a shared
    import is not reachable: `common.scouting` must not depend on `common.strategy`, so
    `CardStat.prize_value` cannot read `strategy.context.MAX_PRIZE_VALUE`. The maximum here is taken
    over the real card set and resolved through `CardStat.prize_value` (`_prize_of`) — the OTHER
    reader, called rather than restated. A future set introducing a fourth Rule fails inside
    `_bodies()` rather than silently topping out below its own ceiling."""
    from common import needs
    from common.strategy.context import MAX_PRIZE_VALUE

    assert max(_prize_of(rule) for _hp, rule in _bodies().values()) == MAX_PRIZE_VALUE == 3

    # ...and the ceiling is that maximum plus the survival term's own cap — the bound ADR-0076
    # Amendment E quotes ("max ~3.9") when it names the denomination debt this item pays down.
    assert needs.TARGET_VALUE_CEILING == MAX_PRIZE_VALUE + needs._SURVIVAL_CAP
    assert needs.TARGET_VALUE_CEILING == pytest.approx(3.9)


@pytest.mark.req("REQ-CURRENCY-0006")
def test_the_gust_target_band_is_the_disruption_tier_and_the_rate_falls_out_of_it():
    """Issue #313 item 2g / ADR-0080 decision 4 — the prize↔worth seam, on `DEPLOY_BAND`'s terms.

    The catalogue's FOURTH row, and the first on the prize↔worth pair. Three things are pinned, the
    same three the deploy band's sibling test pins:

    * the SCALE is the marginal's own derived ceiling, not a fresh divisor (asserted above);
    * the BAND is the shipped disruption tier — so the crossing introduces NO new number, and the
      incumbent it preserves (a gust card's pre-ADR-0076 `deny` slot at `TAG_TIER["gust"] / 2**t`)
      is reproduced rather than replaced;
    * the module says so in prose, so the row cannot be mistaken for a derivation.
    """
    from common import needs
    from common.card_worth import TAG_TIER

    ceiling = needs.TARGET_VALUE_CEILING
    assert currency.GUST_TARGET_BAND == TAG_TIER["gust"] == pytest.approx(10.0)
    assert currency.GUST_TARGET_WORTH_RATE == pytest.approx(TAG_TIER["gust"] / ceiling)

    # A full-ceiling target is worth exactly the band; nothing can exceed it, including a value the
    # bound does not cover (the clamp is what keeps the band a band).
    assert currency.target_value_to_worth(ceiling) == pytest.approx(currency.GUST_TARGET_BAND)
    assert currency.target_value_to_worth(99.0) == pytest.approx(currency.GUST_TARGET_BAND)
    assert currency.target_value_to_worth(0.0) == 0.0
    # The modal corpus target — a 1-prize body that bought no survival turns — lands on the incumbent
    # routing's own median (2.500 over 228 measured slots), which is what makes the band a
    # PRESERVATION choice with evidence rather than an assertion. Written as the rate rather than as
    # `2.564` so the assertion tracks a re-band of the tiers instead of pinning yesterday's quotient.
    assert currency.target_value_to_worth(1.0) == pytest.approx(currency.GUST_TARGET_WORTH_RATE)
    assert 2.4 < currency.target_value_to_worth(1.0) < 2.7    # ...and that IS the incumbent's median

    src = inspect.getsource(currency)
    assert "prize" in src.lower() and "scoped to one seam" in src.lower()


@pytest.mark.req("REQ-CURRENCY-0006")
def test_the_gust_target_slot_can_now_outrank_the_cards_own_latent_worth():
    """The defect the denomination fixes, stated as the comparison that could not come out right.

    A held Boss's Orders is eligible for two slots: its own `gust_target` slot, and the `general`
    latent-worth slot at `worth x deploy x _GENERAL_WORTH_W x liq` — **whose CEILING is 4.5**. A card
    takes at most one slot, so the DP compares them; fed a raw prize-equivalent the gust slot topped
    out at 3.9 and could not reach that ceiling at all, so it could only ever win where the general
    slot had already been discounted by `deploy`/`liq` or was absent.

    ⚠️ **This is a comparison against a CEILING, so it does not by itself prove the slot never won**
    — 4.5 is not a floor, and the corpus measurement (ADR-TEMP-313: the assignment covered a
    `gust_target` slot on 1 frame in 80 before, 25 after) is what carries that claim. What is
    asserted here is the part that IS structural: the reachability of the top of the range.

    The floor is IMPORTED rather than spelled `0.45`, so a re-weight moves this test with it instead
    of leaving it asserting against a number the agent no longer uses."""
    from common import needs
    from common.card_worth import TAG_TIER
    from common.pilot import _GENERAL_WORTH_W

    general_ceiling = TAG_TIER["gust"] * _GENERAL_WORTH_W               # == 4.5
    assert currency.target_value_to_worth(needs.TARGET_VALUE_CEILING) > general_ceiling
    assert currency.target_value_to_worth(2.0) > general_ceiling        # ...as does a 2-prize body
    assert needs.TARGET_VALUE_CEILING < general_ceiling  # ...and the RAW prize-equivalent never could
