"""The shared agent runtime (ADR-0055): one deployment PROFILE + one Pilot build for every agent.

The Pilot ctor stays the raw-scoring layer; the validated-best deployment config lives in
``common.runtime.PROFILE`` — the ONE home for "what ships". These tests replace the per-file
AST pattern `test_agent_wiring.py` pinned pre-0055: the profile is now data, so completeness
is asserted against the Pilot ctor signature (a new kill-switch that isn't consciously added
to the profile fails CI) and the shipped values are pinned as a worked example.
"""
import importlib.util
import inspect
import json
from pathlib import Path

import pytest

from common.pilot import Pilot
from common.runtime import PROFILE, build_pilot, make_agent
from common.scouting.provider import DictCardStatProvider
from common.strategy import Strategy
from pilot_helpers import HAND, PLAY, make_select, opt, state

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "agents" / "mega_starmie"


def _fixture_strategy():
    spec = importlib.util.spec_from_file_location("rt_fixture_strategy", FIXTURE / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.STRATEGY

# Ctor params that wire knowledge/strategy seams rather than deployment configuration —
# everything else in Pilot.__init__ is a deployment flag and MUST appear in PROFILE.
SEAM_PARAMS = frozenset({
    "strategy", "deck", "general_strategy", "overrides", "stats", "functions", "effects",
    "scout", "briefs",
})

# The shipped deployment config — the A/B-cleared / user-decided values every agent runs
# (independent source: the pre-0055 main.py literals and their ADR decision records).
EXPECTED_SHIPPED = {
    "search_budget": 0,
    "posture": True,                # ADR-0026
    "lethal_verify": True,          # ADR-0030
    "lethal_seed_exact": True,      # ADR-0050
    "planner_engine_rank": True,    # ADR-0031
    "planner_key_threat": True,     # ADR-0031
    "lethal_family": True,          # ADR-0037
    "lethal_veto": True,            # ADR-0037
    "promote_ko_aware": True,       # Proposal C (2026-07-11)
    "boost_lethal": True,           # Proposal B (2026-07-11)
    "retreat_enabler_lethal": True,  # ml f15 retreat-enabler lethal (2026-07-13, engine-confirmed)
    "disruptor_lock_maneuver": True,  # dragapult f20 offensive item-lock (2026-07-13, ship-and-refine)
    "matchup_targeting": True,      # ADR-0051 MatchupPlan spine (retired brief_preevo/brief_engine)
    "objectives_race": True,        # ADR-0040
    "objectives_path": True,        # ADR-0040
    "objectives_phases": True,      # ADR-0040
    "gamble_lines": True,           # ADR-0039
    "snipe_prize_redundant": True,  # ADR-0044 (user decision 2026-07-06)
    "snipe_prize_reach": True,      # snipe-targeting grill (2026-07-21) — rider-reach Prize-Path tie-break
    "forced_promotion": True,       # ADR-0044
    "match_planner_steer": True,    # ADR-0045 S3
    "forgo_ko": True,               # ADR-0045 S4
    "prize_economy_fetch": True,    # ADR-0048
    # `evolving_wincon_priority` RETIRED by ADR-0085 Amendment G — inert once the rungs it stood
    # down were deleted. f22 is now asserted against the scalar in test_snipe_evolving_wincon_f22.py
    "value_model": False,           # ADR-0042 armed-off: ships only after its own ladder A/B
    "ko_target_whiff": True,        # BUILD 1 armed-ON 2026-07-14 (ladder-testing): KO-target rebuild-odds tiebreak
    "opp_resource_reads": True,     # BUILD 2 armed-ON 2026-07-14 (ladder-testing): deck-out grind nudge
    "enabler_item_composer": True,  # BUILD 3 armed-ON 2026-07-14 (ladder-testing): ko_for_prizes composer
    "discard_keep_value": True,     # ADR-0065 seam-D armed-ON 2026-07-19 (ladder-testing): the card-worth
                                    # equation decides a forced discard, replacing the `_DISCARD` ladder
    "needs_keep_value": True,       # ADR-0065 WP-N4 armed-ON 2026-07-20 (dev-window): the keep-value v2
                                    # needs-assignment decides the forced discard, superseding v1 (12/12 corpus)
    "leaf_hand_value": False,       # ADR-0065 WP-N5b armed-OFF 2026-07-20: the develop-rung leaf's hand-value
                                    # term (readiness consumes needs), gated on the leaf-lab bench before arming
    "develop_rollout": True,        # develop-rung armed-ON 2026-07-15 (ladder-testing): within-turn rollout rung
    "leaf_option_equivalence": True,  # ADR-0091 (#247) ON at build: indistinguishable options are ONE
                                    # decision — sim one representative per class, fan the class MAX out.
                                    # Not a new leaf term awaiting ladder evidence; it deletes an
                                    # inconsistency the simulator itself disproved (1167.0 vs 95.4).
    "evolve_value": True,           # the EVOLVE DECIDER, shipped ON 2026-07-25 (ADR-0070, #140). The swap
                                    # protocol's batched review is closed (6 FIX, 0 regression) and the
                                    # four baseline_evolution rungs it replaced are DELETED, so OFF is
                                    # degraded mode rather than a rollback.
    "deploy_value": True,           # the DEPLOY DECIDER, shipped ON 2026-07-30 (ADR-0086, Issue #197). The
                                    # Decision Gate is ruled and EVERY rung it replaced is DELETED —
                                    # `keep-a-bench` included, since ADR-0096 decision 2 — so OFF is
                                    # degraded mode rather than a rollback.
    "attach_value": True,           # the ATTACH DECIDER, shipped ON 2026-07-25 (ADR-0069): the axes-sum
                                    # marginal IS the energy-attach decision; 19 baseline_energy rungs are
                                    # DELETED, so OFF is documented DEGRADED MODE, never a rollback
    "promote_retreat_value": True,  # the PROMOTE/RETREAT DECIDER, shipped ON 2026-07-27 (ADR-0100, #141):
                                    # the Sub-lethal Residual in the damage currency, at a DERIVED
                                    # 100 damage/prize. Eleven of the twelve promote/retreat rungs it
                                    # replaced are DELETED (only `retreat-to-wall-the-line` survives, as
                                    # #165's Maneuver), so OFF is degraded mode rather than a rollback.
    "doom_matched_relax": True,     # doom-shadow grill armed-ON 2026-07-23: matched-Read charged doom
                                    # (`_DOOM_CHARGED`) confirms-or-clears a worst-case `active_doomed`
                                    # cry (relax-only); unmatched = worst-case
    "recur_fuel_relax": True,       # ADR-0076 (#186) armed-ON 2026-07-27: quantifies the
                                    # `_doom_recur_fueled` relax-block; corpus-swept clean (0/331)
                                    # AND cleared the ADR-0072 mid-build paired-A/B tripwire
                                    # (+2.4% delta, CI-lo -1.1%, 0 crashes/2400 games)
    "gust_target_slots": True,      # ADR-0076 (#186) armed-ON 2026-07-27: generalizes `deny_slot`
                                    # to a `gust_target` kind; 0 decision flips over 331 corpus
                                    # frames AND cleared the ADR-0072 mid-build tripwire (-0.75%
                                    # delta, CI-lo -4.3%, 0 crashes/2400 games)
    "scaled_threat_rank": True,     # Issue #213 armed-ON 2026-07-30: the threat rank and the
                                    # forced-promotion read price a body through the Damage Formula
                                    # against the live board instead of printed `maxDamage`, and the
                                    # flat `_HAND_SIZE_ATTACKER_BOOST` proxy is deleted. Ships ON
                                    # because OFF would make the change a no-op on the board and
                                    # both ADR-0072 merit gates measure the ON behaviour
    "deny_strip_delta": True,       # ADR-0078 / Issue #199 (S3c). ARMED-ON 2026-07-31 (Issue #228)
                                    # TOGETHER with `deny_relevance`, never alone — its only consumer
                                    # lives inside that flag's branch, and that flag alone would
                                    # leave the tie to engine option order (the ADR-0062 defect).
                                    # ADR-0084 (Issue #217) gave it its
                                    # consumer — the target pick's lexicographic tiebreak among
                                    # candidates tied on relevance, which orders a tie and never GATES
                                    # one (a `strip_shift > 0` keep-price gate suppresses 128/218
                                    # relevance-positive rows). STILL OFF, so that consumer is inert:
                                    # arming is owed by Issue #228
    "snipe_relevance": True,        # ADR-0083 / Issue #188 (S4-snipe): the **Snipe Relevance** scalar
                                    # decides the DAMAGE bench-target select; the six additive target
                                    # rungs + the MatchupPlan steer stand down together while armed.
                                    # Armed-ON 2026-07-30 (ADR-0085 Amendment C) after the OFF path
                                    # measured byte-identical and all three bars cleared: Decision
                                    # Gate, Discrimination Gate (run ARMED, per ADR-0072 decision 5),
                                    # and the mid-build Tripwire (-1.25 pp, CI [-4.79, +2.29], 0
                                    # crashes / 2400 games — `mid_build_verdict` True)
    "deny_relevance": True,         # ADR-0080 / Issue #199 (S3c). **ARMED-ON 2026-07-31
                                    # (Issue #228, ADR-0093), closing Phase 1e and discharging
                                    # the directive-1 debt.** The Discrimination Gate's blocker was a
                                    # DEFECT, not the leaf weighting ADR-0084 Amendment B point 3
                                    # diagnosed: `_opponent_target_rows` returned None mid-sim, and
                                    # `deny_relevance_best` could not express absence, so the fire
                                    # rung read the dataclass default as a measured whiff. Three
                                    # frames moved, each by exactly `_PLANNER_SURVIVAL_W` 50.0.
                                    # Fixed, then armed; all three bars cleared at `baed389` vs
                                    # baseline `a8da62d` — Discrimination Gate PASS with the fix in
                                    # and flags OFF (0 picks moved, which is what makes the armed run
                                    # attributable), Discrimination Gate PASS armed (0 unruled,
                                    # 0 ruled), Decision Gate PASS armed (372 frames, agree
                                    # 250/346 -> 250/346, 0 picks moved). What ALSO clears:
                                    # `_DENIAL_BENCH`'s retirement to the promotion gate, with 0 sign
                                    # changes over 21 Hammer-ruled frames and **0 decision flips over
                                    # 331 corpus frames at the real `decide()`** — the retest decision
                                    # 5 made a precondition, because gate 1 proved SIGN only and the
                                    # promotion gate inflates the rung's MAGNITUDE where it opens
                                    # (f79 55->95, f26 16.25->95, f24 17.5->100)
}


def _ctor_flag_params() -> set[str]:
    """Every Pilot.__init__ keyword that is deployment configuration (not a seam)."""
    sig = inspect.signature(Pilot.__init__)
    return {name for name in sig.parameters if name != "self"} - SEAM_PARAMS


@pytest.mark.req("REQ-WIRE-0003")
def test_profile_covers_every_pilot_flag():
    """REQ-WIRE-0003: PROFILE and the Pilot ctor's flag params match EXACTLY, both ways — a
    new kill-switch added to the ctor fails here until its shipped value is consciously added
    to the profile (the pre-0055 bug class: a flag omitted from one main.py ran that agent's
    layer dark), and a stale profile key fails here when its ctor param is retired."""
    flags = _ctor_flag_params()
    missing = sorted(flags - PROFILE.keys())
    assert not missing, (
        f"Pilot ctor flags missing from runtime PROFILE: {missing} — decide their shipped "
        f"value and add them (this is how a new feature ships to EVERY agent at once).")
    stale = sorted(PROFILE.keys() - flags)
    assert not stale, f"PROFILE keys with no Pilot ctor param: {stale} — retire them."


@pytest.mark.req("REQ-WIRE-0001")
def test_profile_ships_the_validated_best_config():
    """REQ-WIRE-0001 (inverted from the per-file AST pins): the shipped values are the
    A/B-cleared / user-decided deployment config — in particular no armed-off switch
    (brief_engine, value_model) silently flips ON without its evidence gate."""
    assert PROFILE == EXPECTED_SHIPPED


def _raw_seams():
    """Lib-free knowledge seams so build_pilot never touches the engine in these tests."""
    return dict(stats=DictCardStatProvider({}), scout=None, briefs=[])


@pytest.mark.req("REQ-WIRE-0003")
def test_build_pilot_applies_the_shipped_profile():
    """REQ-WIRE-0003: with no params, every flag on the built Pilot reads its PROFILE value —
    the runtime, not the ctor default, decides what a deployed agent runs."""
    pilot = build_pilot(Strategy(), [1] * 60, **_raw_seams())
    for flag, shipped in PROFILE.items():
        if flag == "value_model":
            assert pilot.value_model is None    # armed-off gate False -> no model loaded
            continue
        assert getattr(pilot, flag) == shipped, f"{flag} != PROFILE value {shipped}"


@pytest.mark.req("REQ-WIRE-0003")
def test_params_beat_the_profile():
    """REQ-WIRE-0003: a Strategy param (or overlay param — merged upstream by
    load_overrides_and_params) overrides the profile per flag, so the battle.py A/B lever
    (AGENT_OVERLAY) and a deck's own params keep forcing any switch."""
    strategy = Strategy(params={"posture": False, "search_budget": 50})
    pilot = build_pilot(strategy, [1] * 60, **_raw_seams())
    assert pilot.posture is False               # forced OFF through params
    assert pilot.search_budget == 50            # scalar param overrides the profile's 0
    assert pilot.lethal_family is True          # untouched flags still ship from the profile


@pytest.mark.req("REQ-WIRE-0003")
def test_explicit_params_argument_beats_strategy_params():
    """REQ-WIRE-0003: the ``params=`` argument (the already-merged Strategy+overlay dict the
    shell resolves) wins over ``strategy.params`` when both are given."""
    strategy = Strategy(params={"posture": False})
    pilot = build_pilot(strategy, [1] * 60, params={"posture": True}, **_raw_seams())
    assert pilot.posture is True


# --- make_agent: the whole shell, exercised from a real bundle-shaped dir (cwd = agent dir,
# deck.csv + tuned.json beside it), engine-backed exactly like the grader loads it.

@pytest.mark.req("REQ-WIRE-0004")
def test_make_agent_builds_the_deployed_agent(monkeypatch):
    """REQ-WIRE-0004: make_agent(STRATEGY) is the whole pre-0055 main.py shell — deck read
    from cwd, tuned.json applied, knowledge seams wired, provider warmed in the pregame
    window, profile flags ON — and returns the harness contract: a 1-arg ``agent(obs)``
    callable (with the pilot reachable for probes/tools as ``agent.pilot``)."""
    monkeypatch.chdir(FIXTURE)
    monkeypatch.setenv("AGENT_NO_TELEMETRY", "1")
    agent = make_agent(_fixture_strategy())

    pilot = agent.pilot
    assert len(pilot.deck) == 60                     # deck.csv read from cwd
    assert pilot.overrides                           # fixture tuned.json reached the Pilot
    assert pilot.lethal_family is True               # profile applied (spot: ADR-0037 rung)
    assert pilot.scout is not None and pilot.briefs  # recognition + Briefs wired
    assert pilot.stats._cache is not None            # provider warmed at build (pregame
    #                                                  window), not lazily on turn 1

    select = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)],
                         current=state(hand=[1086, 1030]))
    chosen = agent(select)                           # the module-level agent(obs) contract
    assert isinstance(chosen, list) and all(isinstance(i, int) for i in chosen)


@pytest.mark.req("REQ-WIRE-0004")
def test_make_agent_overlay_forces_a_flag(monkeypatch, tmp_path):
    """REQ-WIRE-0004: AGENT_OVERLAY params reach the built Pilot through make_agent — the
    battle.py A/B lever (ADR-0021) can force any profile flag off (or on)."""
    overlay = tmp_path / "exp.json"
    overlay.write_text(json.dumps({"params": {"posture": False}}), encoding="utf-8")
    monkeypatch.chdir(FIXTURE)
    monkeypatch.setenv("AGENT_OVERLAY", str(overlay))
    monkeypatch.setenv("AGENT_NO_TELEMETRY", "1")
    agent = make_agent(_fixture_strategy())
    assert agent.pilot.posture is False


@pytest.mark.req("REQ-WIRE-0004")
def test_make_agent_emits_telemetry_unless_silenced(monkeypatch):
    """REQ-WIRE-0004: the shell emits Decision Telemetry (ADR-0019) per decision — tier 0
    for a searchless profile — and AGENT_NO_TELEMETRY=1 silences it (the battle protocol
    channel depends on that)."""
    from common import telemetry
    emitted = []
    monkeypatch.chdir(FIXTURE)
    monkeypatch.delenv("AGENT_NO_TELEMETRY", raising=False)
    monkeypatch.setattr(telemetry, "emit", lambda decision, tier: emitted.append(tier))
    agent = make_agent(_fixture_strategy())
    select = make_select([opt(PLAY, area=HAND, index=0)], current=state(hand=[1030]))
    agent(select)
    assert emitted == [0]                            # emitted once, tier 0 (search_budget 0)
