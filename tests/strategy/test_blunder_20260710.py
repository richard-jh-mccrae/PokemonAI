"""Correction fixtures gating the 2026-07-10 blunder round (data/strategy/proposals/blunder-20260710-round.md).

Each test re-derives the tagged decision through the REAL engine-backed Pilot and asserts the human's
`correct` option is now chosen. The three `planner-code` proposals additionally assert WHICH layer drove
the pick (`lethal` / `planned`), since a scoring coincidence would be a false pass.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _decide(pilot, fx: dict):
    d = pilot.explain(fx["obs"])
    return d.chosen, d


@pytest.fixture(scope="module")
def lucario():
    return _pilot("mega_lucario")


@pytest.fixture(scope="module")
def starmie():
    return _pilot("mega_starmie")


@pytest.fixture(scope="module")
def dragapult():
    return _pilot("dragapult_ex")


# ── planner-code ────────────────────────────────────────────────────────────────────────────────
def test_lethal_bench_the_attack_enabler_f13(lucario):
    """ml 85058051 f13 (CRITICAL): fetch the Lunatone that turns Cosmic Beam on; the KO empties their
    board and wins. The grab must be scored KO_SCORE-class, not by the ordinary fetch rungs."""
    fx = _fixture("ml_lethal_bench_the_attack_enabler_f13")
    chosen, d = _decide(lucario, fx)
    assert chosen == fx["correct"]
    assert d.options[fx["correct"][0]].tactical >= 1000


def test_no_phantom_grab_lethal_on_an_unretreatable_active_f39(lucario):
    """ml 85059103 f39 (CRITICAL): a 0-Energy Meowth ex (retreat 1) cannot retreat, and the benched Mega
    already affords Aura Jab — so the Energy grab is neither legal nor necessary. No KO_SCORE claim."""
    fx = _fixture("ml_phantom_grab_lethal_unretreatable_active_f39")
    chosen, d = _decide(lucario, fx)
    assert chosen == fx["correct"]
    assert all(o.tactical < 1000 for o in d.options), "no option may claim a lethal here"


def test_grab_lethal_still_fires_when_legal_and_necessary_f48(lucario):
    """The counter-fixture: ml 84890060 f48 keeps its lethal — a 1-Energy Lunatone Active CAN pay its
    retreat-1, and the benched Mega carries zero, so the fetched {F} is the marginal Energy."""
    fx = _fixture("ml_lethal_recover_energy_via_gong_f48")
    chosen, d = _decide(lucario, fx)
    assert chosen == fx["correct"]
    assert d.options[fx["correct"][0]].tactical >= 1000


@pytest.mark.parametrize("name", ["ml_dont_wake_the_giant_with_the_locking_ko_f88",
                                  "ml_dont_wake_the_giant_boost_ko_f48"])
def test_dont_wake_the_giant_takes_the_lock_free_attack(lucario, name):
    """ml f88 (CRITICAL) / f48: the only KO route burns the answer (Mega Brave self-locks; the boost is
    consumable) and wakes a body we cannot KO, while their pinned Active cannot escape. Attack anyway —
    with the lock-free attack. The Planner must own the pick (a scoring tie would be a false pass)."""
    fx = _fixture(name)
    chosen, d = _decide(lucario, fx)
    assert chosen == fx["correct"]
    assert d.planned is not None and d.planned.goal == "forgo_ko"


# ── general-hypothesis ──────────────────────────────────────────────────────────────────────────
def test_dont_fund_the_non_attacking_body_at_attach_from_f121(lucario):
    """ml f121 (CRITICAL): Aura Jab's bench-load must not go to Lunatone."""
    fx = _fixture("ml_aurajab_dont_load_the_engine_f121")
    assert _decide(lucario, fx)[0] == fx["correct"]


def test_dont_fund_the_supporter_tutor_at_the_manual_attach_f84(lucario):
    """ml f84: Meowth ex 'needs' 3 Energy for Tuck Tail and so out-scored an online Riolu."""
    fx = _fixture("ml_dont_energize_the_supporter_tutor_f84")
    assert _decide(lucario, fx)[0] == fx["correct"]


def test_dont_feed_the_draw_engine_dragapult_f21(dragapult):
    """dragapult f21 (CRITICAL), the same rule cross-agent: Dunsparce evolves into a `draw` engine."""
    fx = _fixture("dragapult_dont_feed_draw_engine_f21")
    assert _decide(dragapult, fx)[0] == fx["correct"]


def test_a_tool_attach_is_not_an_energy_attach_f87(lucario):
    """ml f87 (CRITICAL): the retreat tool belongs on the Active. Scored in isolation — at the live
    frame the forgo-KO rung now commits Aura Jab instead, so `decide()` there is the planner's."""
    fx = _fixture("ml_air_balloon_on_the_active_f87")
    d = lucario.explain(fx["obs"])
    active_attach, bench_attach = fx["correct"][0], 2
    assert d.options[active_attach].score > d.options[bench_attach].score


def test_dont_buff_an_attack_you_cannot_use_f69(lucario):
    """ml f69 (CRITICAL): Accelerating Stab self-locked, so the engine offered no ATTACK at all."""
    fx = _fixture("ml_ppp_attack_transient_locked_f69")
    assert _decide(lucario, fx)[0] == fx["correct"]


def test_open_with_an_attacker_not_the_pure_engine_f1(lucario):
    """ml f1: Lunatone and Riolu both scored 0.0 and the option index opened the engine."""
    fx = _fixture("ml_open_with_an_attacker_not_the_engine_f1")
    assert _decide(lucario, fx)[0] == fx["correct"]


@pytest.mark.parametrize("name", ["ms_snipe_ko_beats_positional_stack_f45",
                                  "ms_snipe_ko_beats_positional_stack_f63",
                                  "ms_snipe_the_energized_ex_f45"])
def test_a_ko_dominates_the_positional_snipe_stack(starmie, name):
    """Three positional snipe bonuses summed past `snipe-for-the-ko`; and the forced-promotion read
    picked a body that cannot attack next turn (and, in f45, one that is Tera-immune on the Bench)."""
    fx = _fixture(name)
    assert _decide(starmie, fx)[0] == fx["correct"]


@pytest.mark.parametrize("name,agent_name", [
    ("dragapult_concentrate_line_preevo_f85", "dragapult"),
    ("dragapult_promote_over_fragile_base_f31", "dragapult"),
])
def test_line_readiness_signals_model_the_multi_stage_line(request, name, agent_name):
    """The corpus's first 2-stage line: `priority_wincon_slot` must see a STARTED pre-evo, and
    `evolve_to_ready_wincon_available` must require the payoff's IMMEDIATE pre-evolution."""
    pilot = request.getfixturevalue(agent_name)
    fx = _fixture(name)
    assert _decide(pilot, fx)[0] == fx["correct"]


def test_a_bare_preevo_is_never_the_concentrate_slot_f24(lucario):
    """Guard on the pre-evo fallback: with every Riolu bare there is nothing to concentrate, so the
    attach stays free for the winning Solrock line (ml 84889011 f24)."""
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")
    assert _decide(lucario, fx)[0] == fx["correct"]


# ── apply pass 2 (2026-07-10): the dragapult round's remaining general rules ────────────────────
def test_dont_strip_energy_from_a_harmless_active_f6(dragapult):
    """dragapult f6: Kyogre pays Riptide with its one {W}, but Riptide does 20 per Basic {W} in its OWN
    discard — which is empty. It cannot hurt us, so the Crushing Hammer is thrown away.
    `incoming_active_damage` is no help: it is affordability-blind and reads the unaffordable 130."""
    fx = _fixture("dragapult_hammer_no_threat_f6")
    assert _decide(dragapult, fx)[0] == fx["correct"]


def test_fetch_the_attack_color_over_an_off_colour_energy_f18(dragapult):
    """dragapult f18: every Energy tied at `fetch-energy-when-starved` (+35) and the option index took
    the deck's single off-colour {D}. Phantom Dive names {R}{P}."""
    fx = _fixture("dragapult_fetch_attack_color_f18")
    assert _decide(dragapult, fx)[0] == fx["correct"]


@pytest.mark.parametrize("name", ["dragapult_poffin_whiff_take_gust_ko_f79",
                                  "dragapult_gust_ko_over_accel_f81"])
def test_a_ko_setup_gust_precedes_the_supporter_that_would_eat_its_slot(dragapult, name):
    """dragapult f79 (CRITICAL) / f81: Boss's Orders scored highest (+50) yet was sequenced behind the
    free develops, so Crispin / Buddy-Buddy Poffin went first and forfeited the one-per-turn Supporter.
    The old tier guard demoted any gust while ANY menu KO existed — but that KO came from a bench
    SPREAD, which a gust does not forfeit."""
    fx = _fixture(name)
    assert _decide(dragapult, fx)[0] == fx["correct"]


def test_grab_lunar_cycle_fuel_f71(lucario):
    """ml f71: Petrel resolved on a dead hand with the Solrock/Lunatone engine online but no {F} to pay
    Lunar Cycle's discard. Fighting Gong is the Item that fetches exactly that."""
    fx = _fixture("ml_grab_the_playable_item_f71")
    assert _decide(lucario, fx)[0] == fx["correct"]
