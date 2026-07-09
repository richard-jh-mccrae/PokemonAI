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


@pytest.mark.req("REQ-PLAN-0030")
@pytest.mark.parametrize("agent,fixture", [
    ("mega_starmie", "ms_lethal_recover_energy_to_win_f110.json"),   # grab the {W} that wins (active)
    ("mega_lucario", "ml_lethal_retreat_boost_to_ko_f24.json"),      # attach {F} to Solrock (boost line)
    ("mega_lucario", "ml_lethal_recover_energy_retreat_ko_f26.json"),  # fetch {F}, retreat-into-Mega KO
    ("mega_lucario", "ml_lethal_recover_energy_via_gong_f48.json"),  # grab Fighting Gong (energy tutor)
])
def test_lethal_recover_takes_the_enabling_step(agent, fixture):
    """On each captured state the shipped Pilot takes the lethal-enabling grab/attach the human wanted,
    not the develop it took live (the recover-the-energy-that-wins line is now seen)."""
    fx = _fx(fixture)
    chosen = _shipped_pilot(agent).explain(fx["obs"]).chosen
    assert all(c in chosen for c in fx["correct"]), (
        f"{fixture}: chose {chosen}, expected the lethal-enabling {fx['correct']} ({fx.get('correct_label')})")
