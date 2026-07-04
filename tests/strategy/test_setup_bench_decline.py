"""The PREGAME setup-bench DECLINE (ep83661652 f3, 2026-07-04): two coupled pieces.

1. `decide()` single-pick take-fewer — at an OPTIONAL select (`minCount == 0`) the Pilot may DECLINE
   (return fewer picks) when the best option is actively DISCOURAGED (score < 0), instead of always
   taking `maxCount` options. Previously it could never decline an optional single-pick.
2. `dont-pre-bench-the-supporter-tutor` (−15) — a `supporter_tutor` Pokémon (Meowth ex) at
   `_SETUP_BENCH` scores negative, so the take-fewer declines: don't bench it in the pregame setup
   (Last-Ditch Catch triggers on an IN-GAME bench, and when it's the only Basic it should go Active).

A positive/neutral optional pick is still placed (the trim only drops score < 0).
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.cards import CardFunctions  # noqa: E402
from common.pilot import Pilot  # noqa: E402
from common.scouting.provider import CardStat  # noqa: E402
from common.strategy import Strategy  # noqa: E402
from common.strategy.context import _SETUP_BENCH  # noqa: E402
from common.strategy.general_strategy import GENERAL_STRATEGY  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "corrections" / "setup_bench_decline_f3.json"


def _build_mega_lucario_pilot():
    spec = importlib.util.spec_from_file_location("tune", REPO / "tools" / "train" / "tune.py")
    tune = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tune)
    pilot, _ = tune._build_pilot("mega_lucario")
    return pilot


@pytest.mark.req("REQ-FETCH-0031")
def test_f3_declines_pre_benching_the_supporter_tutor():
    """REQ-FETCH-0031: on the real f3 pregame state the Pilot DECLINES (chosen == []) rather than
    benching Meowth ex — the supporter_tutor is saved for an in-game bench / the Active Spot."""
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pilot = _build_mega_lucario_pilot()
    assert pilot.decide(fx["obs"]) == [], "should decline the optional pregame bench of Meowth ex"


def _setup_bench_obs(hand_ids):
    """A minimal SETUP_BENCH select (minCount 0, maxCount 1) offering each hand card as a bench pick."""
    opts = [{"type": "Card", "area": 2, "index": i, "playerIndex": 0} for i in range(len(hand_ids))]
    return {"current": {"players": [{"active": [None], "bench": [], "hand": [{"id": c} for c in hand_ids]},
                                    {"active": [None], "bench": []}], "yourIndex": 0, "turn": 0},
            "select": {"context": _SETUP_BENCH, "minCount": 0, "maxCount": 1, "option": opts}}


def test_decline_only_drops_a_discouraged_pick_not_a_neutral_basic():
    """REQ-FETCH-0031: the single-pick take-fewer trims a score-<0 pick (the supporter_tutor) but keeps
    a plain startable Basic (bench-fill-a-basic +12) — an optional bench of a normal body still happens."""
    MEOWTH, RIOLU = 1071, 677
    stats = {MEOWTH: CardStat(MEOWTH, name="Meowth ex", hp=170, ex=True),
             RIOLU: CardStat(RIOLU, name="Riolu", hp=80)}
    funcs = CardFunctions({MEOWTH: ["supporter_tutor"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    assert pilot.decide(_setup_bench_obs([MEOWTH])) == []          # supporter_tutor: declined
    assert pilot.decide(_setup_bench_obs([RIOLU])) == [0]          # a plain Basic: still benched
