"""Lethal-recover (ADR-0030) — the grab-enables-lethal tactical (`_grab_lethal_tactical`).

The win rung (plan_turn) is MAIN-only, so a lethal whose FIRST step is a resource GRAB at a `_TO_HAND`
select is expressed as a KO_SCORE-class tactical on the grab option instead.
"""
import json
import sys
from pathlib import Path

import pytest

from poc_t4_flips import param_for

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent):
    """The develop rung's ENGINE ROLLOUT is pinned OFF: it ranks on `_engine_leaf_value`, whose sims
    run off a process-global unseedable RNG, so the retest bar becomes a sample (Issue #160)."""
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot(agent)
    pilot.develop_rollout = False
    return pilot


def _fx(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / name).read_text(encoding="utf-8"))


_AREA_ZONE = {4: "active", 5: "bench"}          # engine area code → the obs player zone


def _target_body_id(obs: dict, opt: dict):
    """The card id of the Pokémon an ATTACH option targets (via inPlayArea/inPlayIndex → my zones),
    or None for a non-attach / unresolved target."""
    if opt.get("type") != 8:                    # 8 = Attach
        return None
    cur = obs.get("current") or {}
    players = cur.get("players") or []
    yi = cur.get("yourIndex", 0)
    me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
    bodies = me.get(_AREA_ZONE.get(opt.get("inPlayArea")) or "") or []
    i = opt.get("inPlayIndex")
    return bodies[i].get("id") if (isinstance(i, int) and 0 <= i < len(bodies)) else None


def _equivalent(obs: dict, chosen_idx: int, correct_idx: int) -> bool:
    """The SAME lethal-enabling step: for an ATTACH, the same energy card onto a body with the same
    card id (two identical benched Solrock are one enabler); every other kind, the exact index."""
    opts = obs["select"]["option"]
    a, b = opts[chosen_idx], opts[correct_idx]
    if a.get("type") != b.get("type"):
        return False
    if a.get("type") == 8:
        tid = _target_body_id(obs, b)
        return (a.get("cardName") == b.get("cardName") and tid is not None
                and _target_body_id(obs, a) == tid)
    return chosen_idx == correct_idx


@pytest.mark.req("REQ-PLAN-0030")
@pytest.mark.parametrize("agent,fixture", [
    ("mega_starmie", "ms_lethal_recover_energy_to_win_f110.json"),   # grab the {W} that wins (active)
    param_for("ml_lethal_retreat_boost_to_ko_f24",                # attach {F} to Solrock (boost line)
              "mega_lucario", "ml_lethal_retreat_boost_to_ko_f24.json",
              id="mega_lucario-ml_lethal_retreat_boost_to_ko_f24.json"),
    ("mega_lucario", "ml_lethal_recover_energy_retreat_ko_f26.json"),  # fetch {F}, retreat-into-Mega KO
    ("mega_lucario", "ml_lethal_recover_energy_via_gong_f48.json"),  # grab Fighting Gong (energy tutor)
])
def test_lethal_recover_takes_the_enabling_step(agent, fixture):
    fx = _fx(fixture)
    obs = fx["obs"]
    chosen = _shipped_pilot(agent).explain(obs).chosen
    assert all(any(_equivalent(obs, ch, c) for ch in chosen) for c in fx["correct"]), (
        f"{fixture}: chose {chosen}, expected the lethal-enabling {fx['correct']} ({fx.get('correct_label')})")


@pytest.mark.req("REQ-PLAN-0030")
def test_the_retest_bar_is_stream_invariant():
    """12 drives is a cheap sampling TRIPWIRE for a rung nobody has written yet, not a proof — any
    rung ranking on a simmed board makes a retest verdict a sample rather than a fact (Issue #160)."""
    fx = _fx("ml_lethal_retreat_boost_to_ko_f24.json")
    obs = fx["obs"]
    assert _shipped_pilot("mega_lucario").develop_rollout is False, (
        "the develop rung's engine rollout is back on the retest path; its leaf values are not "
        "reproducible across engine RNG streams, so the retest bar becomes a sample")
    picks = {tuple(_shipped_pilot("mega_lucario").explain(obs).chosen) for _ in range(12)}
    assert len(picks) == 1, f"the retest decision is stream-dependent — got {sorted(picks)} across 12 drives"
