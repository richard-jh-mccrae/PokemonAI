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
    """f4: at the pregame SETUP_BENCH the only option is a 2nd Munkidori while one is Active (in the
    setup logs). `dont-pre-bench-a-redundant-utility` (-15) sinks the +12 bench-fill so the single-pick
    take-fewer DECLINES — the copy is saved as Ultra-Ball fodder."""
    fx = _fixture("dp_dont_pre_bench_redundant_munkidori_f4")
    pilot = _pilot("dragapult_ex")
    assert pilot.decide(fx["obs"]) == [], "should decline the optional pregame bench of a 2nd Munkidori"
    board = pilot._board(fx["obs"], fx["obs"]["select"])
    assert 112 in board.setup_placed_ids                      # the Active Munkidori, read from the logs


@pytest.mark.req("REQ-FETCH-0031")
def test_f4_without_the_setup_log_the_basic_is_still_benched():
    """Neutrality: strip the pregame placement log and the same Munkidori bench is no longer redundant
    (`setup_placed_ids` empty) -> the rung stays silent and the optional bench happens. Proves the
    fix rides the setup-log signal, not a blanket decline."""
    fx = _fixture("dp_dont_pre_bench_redundant_munkidori_f4")
    obs = json.loads(json.dumps(fx["obs"]))
    obs["logs"] = []                                          # drop the pregame MOVE_CARD placements
    pilot = _pilot("dragapult_ex")
    board = pilot._board(obs, obs["select"])
    assert board.setup_placed_ids == frozenset()
    assert pilot.decide(obs) == [0], "without the redundancy signal a startable Basic is still benched"


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
