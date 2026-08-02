"""Hand-size relief as a SCORING term (ADR-0102, Issue #261 item 2c — promoting the hand-disruption
grill's design B).

A hand refresh changes how hard an attacker that scales off a hand hits me next turn, and the value
of that is the SURVIVAL it buys — Δ `turns_to_ko_me` between the hands as they stand and the hands
the card leaves both players on, priced in the shared sub-prize survival currency and crossed to the
damage scale on `PRIZE_DAMAGE_RATE`:

    relief = prize_to_damage( survival_value( shift, phase ) )

Two scalers, both verified at `data/EN_Card_Data.csv`:

  * `atk_hand` — **Alakazam** (MEG 743, Powerful Hand: *"2 damage counters … for each card in your
    hand"* = 20 per card in THEIR hand). Only a SYMMETRIC refresh moves it (Judge / Harlequin /
    Unfair Stamp); Lillie's and Lacey leave their hand alone.
  * `def_hand` — **Mega Froslass ex** (861, Resentful Refrain, *"50 damage for each card in your
    opponent's hand"*) and **Chandelure** (98, Mind Ruler, 30/card). Every refresh moves MY hand, so
    a self-only Lillie's reaches this leg too.

Every board below sits at six prizes each with no race read, so `needs.phase_scale` is its 0.3 base
and ONE turn of survival is `0.3 x 0.5 prize x 100 damage/prize` = **15 damage**. That is the whole
arithmetic: every number asserted below is turns-of-survival x 15.

It REPLACES the three flat rungs (`play-harlequin-vs-hand-size` +25, `disrupt-when-unfavored` +18,
`strip-the-stacked-engine-hand` +22), which are deleted — the last two tests here are the ones that
say why a flat could not do this job.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]

JUDGE, HARLEQUIN, LILLIES = 1213, 1223, 1227
KADABRA_MEG = 742          # forward line → Alakazam (MEG 743), Powerful Hand 20/card
FROSLASS_EX = 861          # Resentful Refrain, 50 per card in MY hand
STARYU = 1030              # no hand scaler anywhere in its line
TURN = 15.0                # one turn of survival on these boards (see the module docstring)
PLAY, MAIN = 7, 0


@pytest.fixture(scope="module")
def pilot():
    """A FRESH real (engine-backed) pilot — the deck-agnostic provider loads the full card data, so
    Alakazam's and Mega Froslass ex's scalers and the Kadabra→Alakazam forward line resolve for
    real."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot("mega_starmie")[0]


def _obs(refresh_id, *, opp_hand, my_hp, opp_active=KADABRA_MEG, opp_energy=(7, 7), my_hand_extra=0):
    """A MAIN menu whose only play is `refresh_id`. Six prizes each and no race read, so the phase
    scaler is its 0.3 base; my Active is an energyless body so nothing of mine clouds the read."""
    hand = [{"id": refresh_id}] + [{"id": STARYU}] * my_hand_extra
    prize = [{}] * 6
    me = {"active": [{"id": STARYU, "energies": [], "hp": my_hp}], "bench": [{"id": STARYU}],
          "hand": hand, "handCount": len(hand), "discard": [], "prize": list(prize)}
    opp = {"active": [{"id": opp_active, "energies": list(opp_energy), "hp": 250}], "bench": [],
           "handCount": opp_hand, "discard": [], "prize": list(prize)}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 4},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None}, "logs": []}


def _relief(pilot, card, **kw):
    """The term ALONE, off the same seam `test_refresh_swing_pilot` prices the swing through — a
    Board built on the obs plus the two ctx fields the term reads. Isolating it beats differencing
    two boards' `tactical`, which would silently absorb any other term that moved."""
    from common.strategy.context import _PLAY
    obs = _obs(card, **kw)
    board = pilot._board_hypothetical(obs)
    return pilot._hand_size_relief_tactical(
        obs, board, SimpleNamespace(card_id=card, option_type=_PLAY, tags=()))


# ── the `atk_hand` leg: THEIR hand, Powerful Hand ────────────────────────────────────────────────
@pytest.mark.req("REQ-DISRUPT-0002")
def test_stripping_a_stacked_alakazam_hand_buys_survival_turns(pilot):
    """Judge into an 8-card Alakazam hand redraws them to 4, halving Powerful Hand from 160 to 80.
    Against a 100 HP Active that is one turn of survival (+15); against 330 HP the accumulating
    clock stretches by two (+30). The magnitude is the SURVIVAL bought, not the damage denied —
    the same 80 damage is worth different amounts on different bodies, which is the whole reason
    the flat +25 could not price it."""
    assert _relief(pilot, JUDGE, opp_hand=8, my_hp=100) == pytest.approx(TURN)
    assert _relief(pilot, JUDGE, opp_hand=8, my_hp=330) == pytest.approx(2 * TURN)


@pytest.mark.req("REQ-DISRUPT-0002")
def test_harlequin_prices_on_its_coin_ev_exactly_as_the_swing_oracle_does(pilot):
    """Harlequin's 5/3 and 3/5 branches average to the same redraw 4 Judge prints, so it prices
    identically here — the EV convention `refresh.net_change` already uses, not a second one."""
    assert _relief(pilot, HARLEQUIN, opp_hand=8, my_hp=100) == pytest.approx(TURN)


@pytest.mark.req("REQ-DISRUPT-0002")
def test_refilling_an_empty_alakazam_hand_is_priced_NEGATIVE(pilot):
    """The ml 85709280 f111 shape, and the hole the flat +25 could never close: their hand is 1, so
    Powerful Hand threatens 20 — Judge redraws them UP to 4 and arms it to 80, cutting my clock from
    five turns to two. −30, so the term DECLINES the play. Sign-correct by construction: nothing
    gates this, the arithmetic does it."""
    assert _relief(pilot, JUDGE, opp_hand=1, my_hp=100) == pytest.approx(-2 * TURN)


@pytest.mark.req("REQ-DISRUPT-0002")
def test_a_self_only_refresh_cannot_touch_their_hand(pilot):
    """Lillie's shuffles only MY hand, so their Powerful Hand is untouched — the `opponent_shuffles`
    discriminator, applied here for the same reason `refresh.net_change` applies it."""
    assert _relief(pilot, LILLIES, opp_hand=8, my_hp=100) == 0.0


# ── the `def_hand` leg: MY hand, Resentful Refrain ───────────────────────────────────────────────
@pytest.mark.req("REQ-DISRUPT-0002")
def test_dumping_my_own_hand_denies_a_defender_hand_scaler(pilot):
    """Mega Froslass ex reads MY hand at 50 damage a card, so holding ten is 500 incoming. Judge
    redraws me to 4 (200) and buys a turn against a 330 HP Active: +15. Nothing about this leg is
    "hand disruption" — it is the same survival question asked of the other hand, and pricing only
    the opponent's would have left the bigger of the two scalers in the set unmodelled."""
    assert _relief(pilot, JUDGE, opp_hand=4, my_hp=330, opp_active=FROSLASS_EX,
                   opp_energy=(7, 7, 7), my_hand_extra=9) == pytest.approx(TURN)


@pytest.mark.req("REQ-DISRUPT-0002")
def test_lillies_draws_too_many_to_help_against_froslass_at_six_prizes(pilot):
    """The discrimination a flat rung cannot draw: on the SAME board, Lillie's at exactly six prizes
    draws EIGHT, so my hand goes 10 → 8 and Resentful Refrain still reads 400 against 330 HP. Judge
    is the survival play and Lillie's is not, off the two cards' own printed draw counts."""
    assert _relief(pilot, LILLIES, opp_hand=4, my_hp=330, opp_active=FROSLASS_EX,
                   opp_energy=(7, 7, 7), my_hand_extra=9) == 0.0


@pytest.mark.req("REQ-DISRUPT-0002")
def test_refreshing_a_small_hand_into_a_defender_scaler_is_negative(pilot):
    """The mirror hole on the `def_hand` side: with one card in hand Resentful Refrain reads 50, and
    Judge draws me up to 4 — 200 incoming, a turn off my own clock. −15."""
    assert _relief(pilot, JUDGE, opp_hand=4, my_hp=330, opp_active=FROSLASS_EX,
                   opp_energy=(7, 7, 7)) == pytest.approx(-TURN)


# ── the marginal: zero whenever the hand does not decide my survival ─────────────────────────────
@pytest.mark.req("REQ-DISRUPT-0002")
def test_zero_at_the_redraw_count_and_with_no_hand_scaler_in_play(pilot):
    """At exactly the redraw count nothing moves; against a line with no hand scaler at all the two
    clock reads are equal. No card-fact gate produces these zeros — the clock does."""
    assert _relief(pilot, JUDGE, opp_hand=4, my_hp=100) == 0.0
    assert _relief(pilot, JUDGE, opp_hand=8, my_hp=100, opp_active=STARYU) == 0.0


@pytest.mark.req("REQ-DISRUPT-0002")
def test_zero_when_the_knock_out_lands_either_way(pilot):
    """MARGINAL vs my own KO (grill ruling 1a): against a 70 HP Active, Powerful Hand kills next turn
    at eight cards (160) AND at four (80). 80 damage is denied and it is worth nothing, because the
    Knock Out is unchanged. The flat +25 paid full price for exactly this board."""
    assert _relief(pilot, JUDGE, opp_hand=8, my_hp=70) == 0.0


# ── the promotion itself ─────────────────────────────────────────────────────────────────────────
@pytest.mark.req("REQ-DISRUPT-0002")
def test_the_relief_now_DRIVES_and_arrives_inside_the_tactical_sum(pilot):
    """The inertness test, re-pointed rather than deleted (the grill spec's re-baseline surface says
    it must survive promotion's rewiring). `score == Σ fired weights + tactical` still holds — that
    invariant is about the option trace's shape, not about this term — and the relief is now INSIDE
    `tactical` instead of sitting beside the score on a reporting field.

    Proven by moving only the opponent's Active between two otherwise identical boards: the +15 the
    isolated term reports is the difference the whole option's `tactical` shows."""
    stacked = pilot.explain(_obs(JUDGE, opp_hand=8, my_hp=100)).options[0]
    no_scaler = pilot.explain(_obs(JUDGE, opp_hand=8, my_hp=100, opp_active=STARYU)).options[0]
    assert stacked.score == pytest.approx(sum(w for _h, w in stacked.fired) + stacked.tactical)
    assert stacked.tactical - no_scaler.tactical == pytest.approx(TURN)
    assert not hasattr(stacked, "hand_size_relief"), "the reporting-only field must be gone"


@pytest.mark.req("REQ-DISRUPT-0002")
def test_the_three_flat_disruption_rungs_are_deleted(pilot):
    """The swap IS the deletion (ADR-0092 directive 1): the promoted term must not ship beside the
    proxies it replaces, or one board would pay twice for one quantity."""
    from common.strategy.baseline import baseline_disruption
    ids = {h.id for h in baseline_disruption.HYPOTHESES}
    assert ids.isdisjoint({"play-harlequin-vs-hand-size", "disrupt-when-unfavored",
                           "strip-the-stacked-engine-hand"})
