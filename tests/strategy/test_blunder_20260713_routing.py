"""Blunder round 2026-07-13 (dragapult_ex) — energy-COLOUR routing + setup redundancy (follow-up drain).

Three heavier-signal proposals from blunder-20260713-2d2a113.md, each keyed on a NEW signal:

  - f22 (ToHand fetch): `fetch-the-ability-fuel-color` (+5) credits a colour that switches a DORMANT
    in-play Ability on — grab the {D} a bare Munkidori needs for Adrena-Brain over the redundant
    attack-colour {R} already in hand. Backed by `CardStat.abilityEnergyTypes` (parsed from Ability
    text "if this Pokémon has any {X} Energy attached") -> `board.in_play_unfueled_ability_colors`.
  - f86 (AttachTo, CRITICAL): `attach-off-color-at-fixed-recipient` (-8) demotes an Energy no in-play
    body can use (`board.in_play_required_colors` = attack costs UNION ability fuel) — {D} onto the
    dragon line that needs {P}. The recipient isn't carried per-option here, so it's a sound
    board-union floor.
  - f4 (SETUP_BENCH): `dont-pre-bench-a-redundant-utility` (-15) declines benching a 2nd standalone
    utility Basic already placed (Munkidori while one is Active). Setup-aware: the just-placed Active
    shows only in the MOVE_CARD logs (`board.setup_placed_ids`), so the obs-zone redundancy misses it.

The f18/f21 anchors (attack-colour + draw-engine) stay green in test_blunder_20260709_energy_color.py.
"""
import json
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _pilot(deck):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(deck)[0]


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json").read_text(encoding="utf-8"))


def _fired_ids(option):
    return {h.id for h, _w in option.fired}


@pytest.mark.req("REQ-GEN-0074")
def test_f22_fetch_the_ability_fuel_color_over_a_redundant_attack_color():
    """f22: at a Crispin Energy search the {R}/{P} attack colours tie at +3, but the {D} that switches
    a bare Munkidori's Adrena-Brain on wins on `fetch-the-ability-fuel-color` (+5) — an Ability is
    repeatable free value, and the {R} is already in hand while the {R}{P} dragon line is two
    evolutions from attacking."""
    fx = _fixture("dp_fetch_the_ability_color_f22")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [3] Basic {D}, not [0] Basic {R}
    assert "fetch-the-ability-fuel-color" in _fired_ids(dec.options[fx["correct"][0]])


@pytest.mark.req("REQ-GEN-0074")
def test_f86_attach_the_recipients_color_not_the_off_color():
    """f86 (CRITICAL): at an ATTACH_TO where every option scored 0, the {D} options are demoted by
    `attach-off-color-at-fixed-recipient` (-8) because no in-play body uses {D} (no Munkidori in
    play), so the {P} the dragon line needs for Phantom Dive wins."""
    fx = _fixture("dp_attach_the_recipients_color_f86")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [1] Basic {P}, not [0] Basic {D}
    assert "attach-off-color-at-fixed-recipient" in _fired_ids(dec.options[fx["chosen"][0]])   # the {D} pick


@pytest.mark.req("REQ-GEN-0074")
def test_off_color_demote_silent_on_a_board_colour():
    """Soundness: the ATTACH_TO demote fires ONLY on a colour no in-play body needs — the {P} the
    dragon line uses is never demoted (it's in `in_play_required_colors`)."""
    fx = _fixture("dp_attach_the_recipients_color_f86")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert "attach-off-color-at-fixed-recipient" not in _fired_ids(dec.options[fx["correct"][0]])  # {P} kept


@pytest.mark.req("REQ-FETCH-0031")
def test_f4_declines_pre_benching_a_redundant_utility_basic():
    """f4: at the pregame SETUP_BENCH the only option is a 2nd Munkidori while one is Active. The
    ruled answer is to DECLINE — "we typically only ever need a single Munkidori in play. this second
    copy is a perfect fodder for Ultra Ball" (user, 2026-07-30).

    Carried by ADR-0084 decision 9 — we never bench during Set Up — rather than by a price. This
    frame had three mechanisms in one day: `dont-pre-bench-a-redundant-utility` (−15), then the
    exposure leg charging a redundant pregame copy its full prize value, now the rule. The ruling
    never moved; only the reason did, and the rule is the one that reaches it without needing a
    per-frame signal to notice the redundancy.

    The `setup_placed_ids` assertion this carried is gone WITH that mechanism: the redundancy read no
    longer produces the decline, so asserting it would fix a signal the behaviour does not use."""
    fx = _fixture("dp_dont_pre_bench_redundant_munkidori_f4")
    assert _pilot("dragapult_ex").decide(fx["obs"]) == []


# `test_f4_without_the_setup_log_the_basic_is_still_benched` stood here until ADR-0084 decision 9. It
# was the NEUTRALITY half of the redundancy fix — strip the pregame placement log and the same
# Munkidori is benched again, proving the decline rode `setup_placed_ids` rather than being a blanket
# refusal. Under decision 9 it IS a blanket refusal, deliberately and for reasons read off the
# rulebook, so the property that test existed to DENY is now the intended behaviour. Its replacement
# asserts the same shape from the other side: `test_setup_bench_decline.py::
# test_the_refusal_is_unconditional_even_for_the_wincon_line_base`.


@pytest.mark.req("REQ-GEN-0074")
def test_ability_fuel_parser_reads_the_attached_energy_condition():
    """`parse_card_ability_energy` extracts the {X} an Ability is gated on ("if this Pokémon has any
    {D} Energy attached" -> {D}=7); empty for an Ability that needs no attached Energy, or none."""
    from common.scouting.provider import parse_card_ability_energy

    def card(*texts):
        return types.SimpleNamespace(skills=[types.SimpleNamespace(text=t) for t in texts])

    assert parse_card_ability_energy(card("if this Pokemon has any {D} Energy attached, move counters")) == (7,)
    assert parse_card_ability_energy(card("Once during your turn, you may draw 3 cards.")) == ()
    assert parse_card_ability_energy(card()) == ()
    # an accelerator's "attach a {X} Energy" ACTION is not a fuel condition -> not matched
    assert parse_card_ability_energy(card("attach a {R} Energy from your deck to this Pokemon")) == ()
