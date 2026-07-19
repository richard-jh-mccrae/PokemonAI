"""Reporting-only hand-size-attacker relief (hand-disruption grill ruling 1a/2a, 2026-07-19).

Playing a `hand_disruption` refresh (Judge / Harlequin / Unfair Stamp) against a hand-size attacker
in the opponent's ACTIVE forward line (Abra→Kadabra→Alakazam, Powerful Hand = 20 damage per card in
THEIR hand, aimed at MY Active) changes how hard that attack hits me next turn. The signal is the
signed Powerful-Hand damage swing:

    relief = handSizeDamage × (their hand now − their redraw count)

verified from the printed card text (Powerful Hand: "2 damage counters … for each card in your
hand" = 20/card; Judge redraws both players to 4).

It is REPORTING-ONLY: surfaced on the OptionTrace (and telemetry `hs_relief`) but NEVER added to
`score` — the flat `play-harlequin-vs-hand-size` (+25) rung still drives. It exists so the
calculation is VISIBLE while evidence accumulates toward promotion (making it functional, marginal
vs my own KO, and retiring the flat rungs). See docs/plans/hand-disruption-grill-spec.md §Design B.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

JUDGE, LILLIES = 1213, 1227
KADABRA_MEG = 742          # forward line → Alakazam (MEG 743), Powerful Hand 20/card
POWERFUL_HAND_PER_CARD = 20
PLAY, MAIN = 7, 0


def _pilot():
    """A FRESH real (engine-backed) pilot — the deck-agnostic provider loads the full card data, so
    Alakazam's `handSizeDamage` and the Kadabra→Alakazam forward line resolve for real."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot("mega_starmie")[0]


def _obs(refresh_id, opp_hand, opp_active=KADABRA_MEG):
    """A MAIN menu whose only play is `refresh_id`, facing an opponent whose Active line reaches a
    hand-size attacker. My Active is an energyless body so no hand-independent forward threat clouds
    the board (the isolated Powerful-Hand swing is what we report)."""
    me = {"active": [{"id": 1030, "energies": [], "hp": 70}], "bench": [{"id": 1030}],
          "hand": [{"id": refresh_id}], "discard": [], "prize": []}
    opp = {"active": [{"id": opp_active, "energies": [7, 7], "hp": 80}], "bench": [],
           "handCount": opp_hand, "discard": [], "prize": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 4},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None}, "logs": []}


@pytest.mark.req("REQ-DISRUPT-0002")
def test_stripping_a_stacked_alakazam_hand_reports_denied_damage():
    """Judge into an 8-card Alakazam hand redraws them to 4: 20 × (8 − 4) = 80 damage DENIED off my
    Active. Positive relief, surfaced in telemetry."""
    from common.telemetry import to_record
    dec = _pilot().explain(_obs(JUDGE, opp_hand=8))
    trace = dec.options[0]
    assert trace.hand_size_relief == POWERFUL_HAND_PER_CARD * (8 - 4)   # +80
    assert to_record(dec)["opts"][0]["hs_relief"] == 80.0


@pytest.mark.req("REQ-DISRUPT-0002")
def test_refilling_an_empty_alakazam_hand_reports_armed_damage():
    """The latent-hole case, now VISIBLE: Judge into a 1-card Alakazam hand redraws them UP to 4,
    arming Powerful Hand for 20 × (1 − 4) = −60. Negative relief — sign-correct by construction."""
    trace = _pilot().explain(_obs(JUDGE, opp_hand=1)).options[0]
    assert trace.hand_size_relief == POWERFUL_HAND_PER_CARD * (1 - 4)   # −60


@pytest.mark.req("REQ-DISRUPT-0002")
def test_no_swing_at_the_redraw_count_and_no_attacker():
    """At exactly the redraw count (4) the swing is 0; and a refresh facing NO hand-size attacker
    reports 0 (a Staryu Active has no Powerful Hand in its line)."""
    assert _pilot().explain(_obs(JUDGE, opp_hand=4)).options[0].hand_size_relief == 0.0
    assert _pilot().explain(_obs(JUDGE, opp_hand=8, opp_active=1030)).options[0].hand_size_relief == 0.0


@pytest.mark.req("REQ-DISRUPT-0002")
def test_a_self_only_refresh_never_reports_relief():
    """Lillie's shuffles only MY hand (`shuffle_hand`, not `hand_disruption`), so it cannot change
    the opponent's Powerful Hand — 0 whatever their hand size."""
    assert _pilot().explain(_obs(LILLIES, opp_hand=8)).options[0].hand_size_relief == 0.0


@pytest.mark.req("REQ-DISRUPT-0002")
def test_the_relief_signal_is_inert_never_entering_the_score():
    """The whole point: it REPORTS, it does not DRIVE. The option's `score` is exactly the fired
    hypothesis weights plus the tactical sum — the +80 relief is NOT in it."""
    trace = _pilot().explain(_obs(JUDGE, opp_hand=8)).options[0]
    assert trace.hand_size_relief == 80.0
    assert trace.score == pytest.approx(sum(w for _h, w in trace.fired) + trace.tactical)
