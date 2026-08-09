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

from poc_t4_flips import marks, param

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


# FUNCTION-scoped: a FRESH pilot per replay. A Pilot's ADR-0033 transient-grant tracker is
# MATCH-scoped, so one Pilot replaying several episodes cross-contaminates.
@pytest.fixture
def lucario():
    return _pilot("mega_lucario")


@pytest.fixture
def starmie():
    return _pilot("mega_starmie")


@pytest.fixture
def dragapult():
    return _pilot("dragapult_ex")


# ── planner-code ────────────────────────────────────────────────────────────────────────────────
def test_lethal_bench_the_attack_enabler_f13(lucario):
    """Fetching the partner that turns the attack on must be scored KO_SCORE-class, not by fetch rungs."""
    fx = _fixture("ml_lethal_bench_the_attack_enabler_f13")
    chosen, d = _decide(lucario, fx)
    assert chosen == fx["correct"]
    assert d.options[fx["correct"][0]].tactical >= 1000


def test_no_phantom_grab_lethal_on_an_unretreatable_active_f39(lucario):
    """The Active cannot pay its retreat and the benched attacker is already funded, so the grab is
    neither legal nor necessary."""
    fx = _fixture("ml_phantom_grab_lethal_unretreatable_active_f39")
    chosen, d = _decide(lucario, fx)
    assert chosen == fx["correct"]
    assert all(o.tactical < 1000 for o in d.options), "no option may claim a lethal here"


def test_grab_lethal_still_fires_when_legal_and_necessary_f48(lucario):
    """The counter-fixture: the Active CAN pay its retreat, so the fetched Energy is the marginal one."""
    fx = _fixture("ml_lethal_recover_energy_via_gong_f48")
    chosen, d = _decide(lucario, fx)
    assert chosen == fx["correct"]
    assert d.options[fx["correct"][0]].tactical >= 1000


@pytest.mark.parametrize("name", [param("ml_dont_wake_the_giant_with_the_locking_ko_f88"),
                                  "ml_dont_wake_the_giant_boost_ko_f48"])
def test_dont_wake_the_giant_takes_the_lock_free_attack(lucario, name):
    """The only KO route burns the answer and wakes a body we cannot KO, so take the lock-free attack.
    Guarded on a COMMITTED Turn Line, because a scoring tie would otherwise be a false pass."""
    fx = _fixture(name)
    chosen, d = _decide(lucario, fx)
    assert chosen == fx["correct"]
    assert d.planned is not None and d.planned.next_step == list(chosen), (
        "the pick did not come from a committed Turn Line — a bare scoring tie would look identical")


# ── general-hypothesis ──────────────────────────────────────────────────────────────────────────
def test_dont_fund_the_non_attacking_body_at_attach_from_f121(lucario):
    """The correction's content is the ENGINE exclusion, satisfied structurally by the role gate. WHICH
    attacker takes the load is a target-choice DIVERGENCE — the decider prices one routed unit at a time."""
    fx = _fixture("ml_aurajab_dont_load_the_engine_f121")
    chosen, d = _decide(lucario, fx)
    rows = {r["i"]: r for r in d.attach_working["eq"]}
    lunatone = next(r for r in rows.values() if r["target"] == 675)
    assert lunatone["role_gated"] is True and lunatone["attack_axis"] == 0.0
    assert chosen[0] != lunatone["i"], "the Aura Jab load went to the engine again"
    assert rows[fx["correct"][0]]["tactical"] > 0, "the human's target is not even priced"


# This frame FLIPPED BACK once the tie-defer (`planner._tied_first_steps`) landed. No xfail owed.
def test_dont_fund_the_supporter_tutor_at_the_manual_attach_f84(lucario):
    """A spent utility body 'needs' 3 Energy for its attack and so out-scored an online attacker."""
    fx = _fixture("ml_dont_energize_the_supporter_tutor_f84")
    assert _decide(lucario, fx)[0] == fx["correct"]


@pytest.mark.xfail(strict=True, reason=marks("dragapult_dont_feed_draw_engine_f21")[0].kwargs["reason"])
def test_dont_feed_the_draw_engine_dragapult_f21(dragapult):
    """The role gate carries the exclusion here: this deck runs the JTG Dunsparce (305), which DOES
    print Retreat 1 unlike the TEF printing, so its mobility channel is not zero."""
    fx = _fixture("dragapult_dont_feed_draw_engine_f21")
    chosen, d = _decide(dragapult, fx)
    rows = {r["i"]: r for r in d.attach_working["eq"]}
    engine = next(r for r in rows.values() if r["target"] == 305)
    assert engine["role_gated"] is True
    assert engine["attack_axis"] == 0.0 and engine["build"] > 0   # gated, not merely unbuildable
    assert chosen[0] != engine["i"], "the only {D} went into the draw engine again"


# XFAIL RETIRED by Issue #423's Tool channel. The `FLIPS` row of the same name STAYS: it records the
# COMPOSER's flip, and the composer still prices a Tool attach at 0.0 — only the Pilot now does not.
def test_a_tool_attach_is_not_an_energy_attach_f87(lucario):
    """The retreat tool belongs on the Active, and only the Active pays a Retreat Cost for it to buy
    down. Both legs of `_tool_attach_value` read the Active, so a bench recipient differences to 0."""
    fx = _fixture("ml_air_balloon_on_the_active_f87")
    d = lucario.explain(fx["obs"])
    active_attach, bench_attach = fx["correct"][0], 2
    assert d.options[active_attach].score > d.options[bench_attach].score
    assert d.chosen[0] == active_attach, "the frame now DECIDES it, not merely scores it higher"






@pytest.mark.parametrize("name", ["ms_snipe_ko_beats_positional_stack_f45",
                                  "ms_snipe_ko_beats_positional_stack_f63",
                                  "ms_snipe_the_energized_ex_f45"])
def test_a_ko_dominates_the_positional_snipe_stack(starmie, name):
    """Three positional snipe bonuses summed past the KO rung, and the forced-promotion read picked a
    body that cannot attack next turn."""
    fx = _fixture(name)
    assert _decide(starmie, fx)[0] == fx["correct"]


@pytest.mark.parametrize("name,agent_name", [
    param("dragapult_concentrate_line_preevo_f85", "dragapult"),
    param("dragapult_promote_over_fragile_base_f31", "dragapult"),
])
def test_line_readiness_signals_model_the_multi_stage_line(request, name, agent_name):
    """The corpus's first 2-stage line: `priority_wincon_slot` must see a STARTED pre-evo, and
    `evolve_to_ready_wincon_available` must require the payoff's IMMEDIATE pre-evolution."""
    pilot = request.getfixturevalue(agent_name)
    fx = _fixture(name)
    assert _decide(pilot, fx)[0] == fx["correct"]


@pytest.mark.xfail(strict=True, reason=marks("ml_lethal_retreat_boost_to_ko_f24")[0].kwargs["reason"])
def test_a_bare_preevo_is_never_the_concentrate_slot_f24(lucario):
    """With every pre-evo bare there is nothing to concentrate, so the attach stays free. Also the
    repo's determinism tracer (Issue #178) — this frame once answered by engine-RNG position."""
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")
    assert _decide(lucario, fx)[0] == fx["correct"]


# ── apply pass 2 (2026-07-10): the dragapult round's remaining general rules ────────────────────
def test_dont_strip_energy_from_a_harmless_active_f6(dragapult):
    """`incoming_active_damage` is no help here: it is affordability-blind and reads an unaffordable
    attack, so the discard-scaling attack that computes to 0 has to be read separately."""
    fx = _fixture("dragapult_hammer_no_threat_f6")
    assert _decide(dragapult, fx)[0] == fx["correct"]
@pytest.mark.parametrize("name", [param("dragapult_poffin_whiff_take_gust_ko_f79"),
                                  param("dragapult_gust_ko_over_accel_f81")])
def test_a_ko_setup_gust_precedes_the_supporter_that_would_eat_its_slot(dragapult, name):
    """The old tier guard demoted any gust while ANY menu KO existed — but a bench-SPREAD KO is not
    forfeited by a gust, so the free develop ate the one-per-turn Supporter slot."""
    fx = _fixture(name)
    assert _decide(dragapult, fx)[0] == fx["correct"]


def test_grab_lunar_cycle_fuel_f71(lucario):
    """Lucario's retained Gong rung fires when its Lunar Cycle engine has no Fighting fuel."""
    fx = _fixture("ml_grab_the_playable_item_f71")
    fired = {h.id for option in lucario.explain(fx["obs"]).options for h, _ in option.fired}
    assert "grab-lunar-cycle-fuel" in fired
