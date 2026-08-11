from pathlib import Path

import pytest

from train.blunder.store import load_corrections
from train.tune import _build_pilot


REPO = Path(__file__).resolve().parents[2]
ROWS = tuple(c for c in load_corrections(REPO / "data" / "corrections")
             if c.agent == "mega_starmie")


def _correction(episode, frame):
    return next(c for c in ROWS
                if c.episode_id == episode and int(c.decision.get("frame", -1)) == frame)


@pytest.mark.parametrize(("episode", "frame", "expected"), (
    (82522698, 62, [15]),       # direct game win dominates setup
    (82749168, 88, [8]),        # direct game win dominates information
    (85163079, 30, [0]),        # loaded future win condition is the gust target
    (83116081, 21, [0]),        # Turbo Flare concentrates on the developed line
    (82224509, 56, [1]),        # Scouting ranks the real snipe threat
    (82523811, 61, [3]),        # future three-prize line outranks filler
    (82752604, 62, [0]),        # loaded Drakloak outranks the wall
    (82753102, 85, [0]),        # Kadabra line outranks Dunsparce
    (83966968, 79, [1]),        # damaged multi-prize gust target
    (84897262, 110, [1]),       # fetched Water unlocks the game win
    (82749168, 21, [7]),        # duplicate Hammers cannot crowd out useful Turbo Flare
    (82228017, 4, [1]),         # satisfying held Energy demand is persistent development
    (82752604, 16, [2]),        # redundant Mega Signal loses to the resolving attack
    (82717711, 18, [1]),        # a legal beneficial attack beats exact-zero End
    (83116081, 76, [5]),        # heal then reattach then KO survives bounded search
    (83456015, 35, [3]),        # exposed Active is healed before the typed KO line
    (81785223, 39, [2]),        # visible Energy makes Clefairy the immediate snipe threat
    (81785223, 45, [2]),        # the same threat rule survives a different Bench ordering
    (82225138, 46, [0]),        # current Scouting overrides the stale Dwebble target label
))
def test_rationale_led_hard_gates(episode, frame, expected):
    pilot = _build_pilot("mega_starmie")[0]
    assert pilot.decide(_correction(episode, frame).obs) == expected


def test_heal_targets_the_exposed_active_not_the_loaded_safe_bench():
    pilot = _build_pilot("mega_starmie")[0]
    assert pilot.decide(_correction(None, 100).obs) == [0]
