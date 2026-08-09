"""The shared agent runtime (ADR-0055): one deployment PROFILE + one Pilot build for every agent.

The Pilot ctor stays the raw-scoring layer; the deployment config lives in ``common.runtime.PROFILE``
and completeness is asserted against the ctor signature, so a new kill-switch that is not
consciously added to the profile fails CI.
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

# The shipped deployment config — the A/B-cleared / user-decided values every agent runs.
EXPECTED_SHIPPED = {
    "search_budget": 0,
    "posture": True,                # ADR-0026
    "lethal_verify": True,          # ADR-0030
    "lethal_seed_exact": True,      # ADR-0050
    # `planner_engine_rank` (ADR-0031) is DELETED by Issue #386 — ranking end states is the
    # composer's job and it does it closed-form; `TurnLine.ranked_by`'s "engine" value died with it.
    "planner_key_threat": True,     # ADR-0031
    "lethal_family": True,          # ADR-0037
    "lethal_veto": True,            # ADR-0037
    "promote_ko_aware": True,       # Proposal C
    "boost_lethal": True,           # Proposal B
    "retreat_enabler_lethal": True,  # retreat-enabler lethal
    "disruptor_lock_maneuver": True,  # offensive item-lock
    "matchup_targeting": True,      # ADR-0051 MatchupPlan spine
    "objectives_race": True,        # ADR-0040
    "objectives_path": True,        # ADR-0040
    "objectives_phases": True,      # ADR-0040
    "gamble_lines": True,           # ADR-0039
    "snipe_prize_redundant": True,  # ADR-0044
    "snipe_prize_reach": True,      # rider-reach Prize-Path tie-break
    "forced_promotion": True,       # ADR-0044
    "match_planner_steer": True,    # ADR-0045 S3
    # `forgo_ko` (ADR-0045 S4) is DELETED by Issue #386: it gated a rung ABOVE the decider, which
    # under 1-ply differencing is one sequence out-scoring another — no OFF meaning left to express.
    "prize_economy_fetch": True,    # ADR-0048
    # `evolving_wincon_priority` RETIRED by ADR-0085 Amendment G — inert once its rungs were deleted.
    "value_model": False,           # ADR-0042 armed-off: ships only after its own ladder A/B
    "ko_target_whiff": True,        # KO-target rebuild-odds tiebreak
    "opp_resource_reads": True,     # deck-out grind nudge
    "enabler_item_composer": True,  # ko_for_prizes composer
    "leaf_hand_value": False,       # ADR-0065 armed-OFF: the develop-rung leaf's hand-value term
    # `develop_rollout` and `leaf_option_equivalence` are DELETED by Issue #386: the rollout scorer is
    # gone, and Option-Equivalence classing (ADR-0091) is unconditional inside the composer.
    "copy_top_value": True,         # Issue #289 ON: known-top carry + Slowking copy-top value.
    "evolve_value": True,           # the EVOLVE DECIDER (ADR-0070); the rungs it replaced are
                                    # DELETED, so OFF is degraded mode rather than a rollback
    "deploy_value": True,           # the DEPLOY DECIDER (ADR-0086); every rung it replaced is
                                    # DELETED, so OFF is degraded mode rather than a rollback
    "attach_value": True,           # the ATTACH DECIDER (ADR-0069); the baseline_energy rungs are
                                    # DELETED, so OFF is degraded mode rather than a rollback
    "promote_retreat_value": True,  # the PROMOTE/RETREAT DECIDER (ADR-0100): the Sub-lethal Residual
                                    # at a DERIVED 100 damage/prize. OFF is degraded mode
    "doom_matched_relax": True,     # a matched Read confirms-or-clears a worst-case `active_doomed`
                                    # cry (relax-only); unmatched stays worst-case
    "recur_fuel_relax": True,       # ADR-0076 quantifies the `_doom_recur_fueled` relax-block
    "gust_target_slots": True,      # ADR-0076 generalizes `deny_slot` to a `gust_target` kind
    "scaled_threat_rank": True,     # Issue #213: the threat rank prices a body through the Damage
                                    # Formula against the live board, not printed `maxDamage`
    "deny_strip_delta": True,       # ADR-0078 / ADR-0084. Arm only TOGETHER with `deny_relevance` —
                                    # its only consumer lives inside that flag's branch
    "snipe_relevance": True,        # ADR-0083: the Snipe Relevance scalar decides the DAMAGE
                                    # bench-target select; the additive target rungs stand down
    "deny_relevance": True,         # ADR-0080 / ADR-0093. Arm TOGETHER with `deny_strip_delta`
    "leaf_followups": False,        # Issue #387: deck opt-in; Mega Starmie validates first
}


def _ctor_flag_params() -> set[str]:
    """Every Pilot.__init__ keyword that is deployment configuration (not a seam)."""
    sig = inspect.signature(Pilot.__init__)
    return {name for name in sig.parameters if name != "self"} - SEAM_PARAMS


@pytest.mark.req("REQ-WIRE-0003")
def test_profile_covers_every_pilot_flag():
    """Both ways: a new ctor kill-switch fails here until its shipped value is added to the
    profile, and a stale profile key fails here when its ctor param is retired."""
    flags = _ctor_flag_params()
    missing = sorted(flags - PROFILE.keys())
    assert not missing, (
        f"Pilot ctor flags missing from runtime PROFILE: {missing} — decide their shipped "
        f"value and add them (this is how a new feature ships to EVERY agent at once).")
    stale = sorted(PROFILE.keys() - flags)
    assert not stale, f"PROFILE keys with no Pilot ctor param: {stale} — retire them."


@pytest.mark.req("REQ-WIRE-0001")
def test_profile_ships_the_validated_best_config():
    """No armed-off switch may silently flip ON without its evidence gate."""
    assert PROFILE == EXPECTED_SHIPPED


def _raw_seams():
    """Lib-free knowledge seams so build_pilot never touches the engine in these tests."""
    return dict(stats=DictCardStatProvider({}), scout=None, briefs=[])


@pytest.mark.req("REQ-WIRE-0003")
def test_build_pilot_applies_the_shipped_profile():
    """The runtime, not the ctor default, decides what a deployed agent runs."""
    pilot = build_pilot(Strategy(), [1] * 60, **_raw_seams())
    for flag, shipped in PROFILE.items():
        if flag == "value_model":
            assert pilot.value_model is None    # armed-off gate False -> no model loaded
            continue
        assert getattr(pilot, flag) == shipped, f"{flag} != PROFILE value {shipped}"


@pytest.mark.req("REQ-WIRE-0003")
def test_params_beat_the_profile():
    """A Strategy param overrides the profile per flag, so the battle.py A/B lever keeps
    forcing any switch."""
    strategy = Strategy(params={"posture": False, "search_budget": 50})
    pilot = build_pilot(strategy, [1] * 60, **_raw_seams())
    assert pilot.posture is False               # forced OFF through params
    assert pilot.search_budget == 50            # scalar param overrides the profile's 0
    assert pilot.lethal_family is True          # untouched flags still ship from the profile


@pytest.mark.req("REQ-WIRE-0003")
def test_explicit_params_argument_beats_strategy_params():
    """``params=`` is the already-merged Strategy+overlay dict the shell resolves."""
    strategy = Strategy(params={"posture": False})
    pilot = build_pilot(strategy, [1] * 60, params={"posture": True}, **_raw_seams())
    assert pilot.posture is True


# --- make_agent: the whole shell, from a real bundle-shaped dir (cwd = agent dir, deck.csv +
# tuned.json beside it), engine-backed exactly like the grader loads it.

@pytest.mark.req("REQ-WIRE-0004")
def test_make_agent_builds_the_deployed_agent(monkeypatch):
    """The harness contract is a 1-arg ``agent(obs)`` callable with the pilot reachable for
    probes/tools as ``agent.pilot``."""
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
    """AGENT_OVERLAY params reach the built Pilot through make_agent (the ADR-0021 A/B lever)."""
    overlay = tmp_path / "exp.json"
    overlay.write_text(json.dumps({"params": {"posture": False}}), encoding="utf-8")
    monkeypatch.chdir(FIXTURE)
    monkeypatch.setenv("AGENT_OVERLAY", str(overlay))
    monkeypatch.setenv("AGENT_NO_TELEMETRY", "1")
    agent = make_agent(_fixture_strategy())
    assert agent.pilot.posture is False


@pytest.mark.req("REQ-WIRE-0004")
def test_make_agent_emits_telemetry_unless_silenced(monkeypatch):
    """Decision Telemetry (ADR-0019) per decision; the battle protocol channel depends on
    AGENT_NO_TELEMETRY=1 silencing it."""
    from common import telemetry
    emitted = []
    monkeypatch.chdir(FIXTURE)
    monkeypatch.delenv("AGENT_NO_TELEMETRY", raising=False)
    monkeypatch.setattr(telemetry, "emit", lambda decision, tier: emitted.append(tier))
    agent = make_agent(_fixture_strategy())
    select = make_select([opt(PLAY, area=HAND, index=0)], current=state(hand=[1030]))
    agent(select)
    assert emitted == [0]                            # emitted once, tier 0 (search_budget 0)
