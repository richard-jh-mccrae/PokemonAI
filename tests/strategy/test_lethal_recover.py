"""Lethal-recover (ADR-0030) — the grab-enables-lethal tactical (`_grab_lethal_tactical`).

The win rung (plan_turn) is MAIN-only, so a lethal whose FIRST step is a resource GRAB at a `_TO_HAND`
search/recover select is expressed as a KO_SCORE-class tactical on the grab option instead. Grabbing a
reusable Basic Energy (direct) or a `tutor_energy` card the deck can cash — then attaching it onto the
Active or retreating into a benched attacker — that delivers a min-bound KO of the opponent's Active
scores KO_SCORE + prize, mirroring `_attach_lethal_tactical`. Two outright thrown WINS (f110, f24) + two
missed KOs (f26, f48) across mega_starmie + mega_lucario. Fixtured through the shipped, engine-backed
Pilot (`decide()`), the strict retest bar.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot(agent)
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
    """Two option indices are interchangeable iff they achieve the SAME lethal-enabling step. For an
    ATTACH that means the same energy card onto a body with the same card id — so attaching {F} to
    EITHER of two identical benched Solrock is the same enabler (ml f24 has two Solrock; the fixture
    pins one arbitrarily). Non-attach steps compare by exact index."""
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
    ("mega_lucario", "ml_lethal_retreat_boost_to_ko_f24.json"),      # attach {F} to Solrock (boost line)
    ("mega_lucario", "ml_lethal_recover_energy_retreat_ko_f26.json"),  # fetch {F}, retreat-into-Mega KO
    ("mega_lucario", "ml_lethal_recover_energy_via_gong_f48.json"),  # grab Fighting Gong (energy tutor)
])
def test_lethal_recover_takes_the_enabling_step(agent, fixture):
    """On each captured state the shipped Pilot takes the lethal-enabling grab/attach the human wanted,
    not the develop it took live (the recover-the-energy-that-wins line is now seen). The human's
    `correct` index is matched up to INTERCHANGEABILITY (`_equivalent`) — attaching the {F} to either
    of two identical Solrock is the same enabler, so the assertion doesn't over-pin one of two equal
    targets (ml f24)."""
    fx = _fx(fixture)
    obs = fx["obs"]
    chosen = _shipped_pilot(agent).explain(obs).chosen
    assert all(any(_equivalent(obs, ch, c) for ch in chosen) for c in fx["correct"]), (
        f"{fixture}: chose {chosen}, expected the lethal-enabling {fx['correct']} ({fx.get('correct_label')})")
