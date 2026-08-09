"""Blunder round 2026-07-13 (dragapult_ex) — energy-COLOUR routing + setup redundancy.

`fetch-the-ability-fuel-color` credits a colour that switches a DORMANT in-play Ability on (backed by
`CardStat.abilityEnergyTypes`); `attach-off-color-at-fixed-recipient` demotes a colour no in-play body
can use — a sound board-UNION floor, since the recipient is not carried per-option at that select.
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
def test_off_color_demote_silent_on_a_board_colour():
    """The demote fires ONLY on a colour outside `in_play_required_colors`."""
    fx = _fixture("dp_attach_the_recipients_color_f86")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert "attach-off-color-at-fixed-recipient" not in _fired_ids(dec.options[fx["correct"][0]])  # {P} kept


@pytest.mark.req("REQ-FETCH-0031")
def test_f4_declines_pre_benching_a_redundant_utility_basic():
    """Carried by ADR-0086 decision 9 — we never bench during Set Up — rather than by a price, so the
    `setup_placed_ids` assertion is gone with the mechanism it belonged to."""
    fx = _fixture("dp_dont_pre_bench_redundant_munkidori_f4")
    assert _pilot("dragapult_ex").decide(fx["obs"]) == []


# `test_f4_without_the_setup_log_the_basic_is_still_benched` stood here until ADR-0086 decision 9 made
# the refusal unconditional; `test_setup_bench_decline.py` now asserts that shape from the other side.


@pytest.mark.req("REQ-GEN-0074")
def test_ability_fuel_parser_reads_the_attached_energy_condition():
    """Extracts the {X} an Ability is GATED on; an accelerator's "attach a {X}" ACTION is not a gate."""
    from common.scouting.provider import parse_card_ability_energy

    def card(*texts):
        return types.SimpleNamespace(skills=[types.SimpleNamespace(text=t) for t in texts])

    assert parse_card_ability_energy(card("if this Pokemon has any {D} Energy attached, move counters")) == (7,)
    assert parse_card_ability_energy(card("Once during your turn, you may draw 3 cards.")) == ()
    assert parse_card_ability_energy(card()) == ()
    # an accelerator's "attach a {X} Energy" ACTION is not a fuel condition -> not matched
    assert parse_card_ability_energy(card("attach a {R} Energy from your deck to this Pokemon")) == ()
