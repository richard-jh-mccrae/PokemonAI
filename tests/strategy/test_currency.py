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
    """ADR-0100 §3 / ADR-0078 decision 2: the Prize Damage Rate is DERIVED, so a reviewer can
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
    assert len(bodies) == 1061                            # the population ADR-0100 measured
    assert statistics.median(bodies.values()) == PRIZE_DAMAGE_RATE


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

    Two spellings of one fact are pinned together in one place, which is the net ADR-0087 asks for
    when a shared import is not reachable: `common.scouting` must not depend on `common.strategy`, so
    `CardStat.prize_value` cannot read `strategy.context.MAX_PRIZE_VALUE`. This test walks the Rule
    column of `data/EN_Card_Data.csv`, resolves each body through `CardStat.prize_value` — the OTHER
    reader, called rather than restated — and asserts the constant is that population's actual
    maximum. A future set introducing a fourth Rule fails the vocabulary assertion rather than
    silently topping out below its own ceiling."""
    import csv as _csv

    from common import needs
    from common.scouting.provider import CardStat
    from common.strategy.context import MAX_PRIZE_VALUE

    bodies = {}                             # by Card ID, as the Prize-Damage-Rate recomputation is
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            if (row.get("HP") or "").strip().isdigit() and int(row["HP"]) > 0:
                bodies[row["Card ID"]] = (row.get("Rule") or "n/a").strip()
    rules = set(bodies.values())
    # The whole Rule vocabulary this set uses — anything else and the mapping below is incomplete.
    assert rules == {"n/a", "Pokémon ex", "Mega Pokémon ex"}
    assert len(bodies) == 1061                             # the same population as the rate above

    # Each Rule resolved through the OTHER reader, so the two cannot disagree about the ceiling.
    got = {rule: CardStat(0, ex=(rule != "n/a"), megaEx=(rule == "Mega Pokémon ex")).prize_value
           for rule in rules}
    assert got == {"n/a": 1, "Pokémon ex": 2, "Mega Pokémon ex": 3}
    assert max(got.values()) == MAX_PRIZE_VALUE == 3

    # ...and the ceiling is that maximum plus the survival term's own cap — the bound ADR-0076
    # Amendment E quotes ("max ~3.9") when it names the denomination debt this item pays down.
    assert needs.TARGET_VALUE_CEILING == pytest.approx(3.9)
    assert needs.TARGET_VALUE_CEILING == MAX_PRIZE_VALUE + needs._SURVIVAL_CAP


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
    from common.card_worth import TAG_TIER

    assert currency.GUST_TARGET_BAND == TAG_TIER["gust"] == pytest.approx(10.0)
    assert currency.GUST_TARGET_WORTH_RATE == pytest.approx(10.0 / 3.9)

    # A full-ceiling target is worth exactly the band; nothing can exceed it, including a value the
    # bound does not cover (the clamp is what keeps the band a band).
    assert currency.target_value_to_worth(3.9) == pytest.approx(10.0)
    assert currency.target_value_to_worth(99.0) == pytest.approx(10.0)
    assert currency.target_value_to_worth(0.0) == 0.0
    # The modal corpus target — a 1-prize body bought no survival turns — lands on the incumbent
    # routing's own median (2.500 over 228 measured slots), which is what makes the band a
    # PRESERVATION choice with evidence rather than an assertion.
    assert currency.target_value_to_worth(1.0) == pytest.approx(2.564, abs=0.001)

    src = inspect.getsource(currency)
    assert "prize<->worth rate, scoped to one seam" in src


@pytest.mark.req("REQ-CURRENCY-0006")
def test_the_gust_target_slot_can_finally_outrank_the_cards_own_latent_worth():
    """The defect the denomination fixes, stated as the property that was FALSE before it.

    A held Boss's Orders opens two slots it is eligible for: its own `gust_target` slot, and the
    `general` latent-worth slot every worth-carrying card gets at `TAG_TIER["gust"] x
    _GENERAL_WORTH_W` = **4.5**. Fed a raw prize-equivalent the gust slot topped out at 3.9 — BELOW
    that floor on every board there is — so the assignment never once chose the instrument ADR-0076
    built, and its "0 decision flips" measured inertness rather than agreement.

    Asserted as the inequality rather than against a frame, because the claim is structural: it must
    hold for every board with a target worth more than the modal one, not for a fixture. The floor is
    IMPORTED rather than spelled `0.45` here, so a re-weight moves this test with it instead of
    leaving it asserting against a number the agent no longer uses."""
    from common import needs
    from common.card_worth import TAG_TIER
    from common.pilot import _GENERAL_WORTH_W

    general_floor = TAG_TIER["gust"] * _GENERAL_WORTH_W                 # == 4.5
    assert currency.target_value_to_worth(needs.TARGET_VALUE_CEILING) > general_floor  # ceiling wins
    assert currency.target_value_to_worth(2.0) > general_floor          # ...as does a 2-prize body
    assert needs.TARGET_VALUE_CEILING < general_floor  # ...and the RAW prize-equivalent never could
