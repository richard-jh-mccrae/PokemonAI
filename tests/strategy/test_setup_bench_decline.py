"""The PREGAME setup bench: we never place one (ADR-0086 decision 9).

`Pilot._never_pre_bench` refuses every `_SETUP_BENCH` placement outright — a RULE, not a price.
Deferring is weakly DOMINANT, checked at source: the placement is optional (`docs/rulebook.txt` L97);
no attack reaches me before my own first turn in either seat (`docs/rules.md` §2); no Ability damage
can either (only Basics are in play, and no damage-counter Ability sits on a Basic); and the player
going first cannot play a Supporter to strip my hand (rulebook L133).
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.strategy.context import _SETUP_BENCH  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "corrections" / "setup_bench_decline_f3.json"


def _build_mega_lucario_pilot():
    spec = importlib.util.spec_from_file_location("tune", REPO / "tools" / "train" / "tune.py")
    tune = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tune)
    pilot, _ = tune._build_pilot("mega_lucario")
    return pilot


@pytest.mark.req("REQ-FETCH-0031")
def test_f3_declines_pre_benching_the_supporter_tutor():
    """On the real f3 pregame state the Pilot DECLINES rather than benching Meowth ex, so Last-Ditch
    Catch survives for an in-game bench. The OUTCOME held across all three mechanisms this has had."""
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert _build_mega_lucario_pilot().decide(fx["obs"]) == []


@pytest.mark.req("REQ-FETCH-0031")
def test_the_refusal_is_unconditional_even_for_the_wincon_line_base():
    """The rule does not weigh the body: the Line base is benched on turn 1 instead, losing nothing.
    Kept because "surely we still want the line base down" would reintroduce a pregame price."""
    RIOLU = 677
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    obs = json.loads(json.dumps(fx["obs"]))
    me = obs["current"]["players"][obs["current"].get("yourIndex", 0)]
    me["hand"].append({"id": RIOLU})
    obs["select"]["option"].append({"type": 3, "area": 2, "playerIndex": 0,
                                    "index": len(me["hand"]) - 1})
    assert _build_mega_lucario_pilot().decide(obs) == []


@pytest.mark.req("REQ-FETCH-0031")
def test_the_refusal_is_scoped_to_the_pregame_select():
    """`_never_pre_bench` keys on `_SETUP_BENCH` and nothing else. Asserted on the filter directly: a
    board-level test would confound the rule with whatever the equation happens to score."""
    pilot = _build_mega_lucario_pilot()
    assert pilot._never_pre_bench({"context": _SETUP_BENCH}, [0]) == []
    assert pilot._never_pre_bench({"context": _SETUP_BENCH}, [0, 1]) == []
    for ctx in (0, 7, 9):                       # MAIN / TO_HAND / TO_BENCH: all left alone
        assert pilot._never_pre_bench({"context": ctx}, [0, 1]) == [0, 1]
    assert pilot._never_pre_bench({}, [0]) == [0]      # no context: never silently refuses
