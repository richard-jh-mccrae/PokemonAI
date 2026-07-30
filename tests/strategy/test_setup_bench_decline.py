"""The PREGAME setup bench: we never place one (ADR-0081 decision 9).

This module used to be about the DECLINE MECHANISM — `decide()`'s single-pick take-fewer trimming a
placement some Hypothesis scored below zero (`dont-pre-bench-the-supporter-tutor` −15, later the
Deploy Marginal's exposure leg). That framing is retired. The pregame is not a decision we price at
all: `Pilot._never_pre_bench` refuses every `_SETUP_BENCH` placement outright.

Why it is a RULE and not a price, all checked at source:

* the placement is optional — "put **up to** 5 more Basic Pokémon face down on your Bench"
  (`docs/rulebook.txt` L97), hence `minCount 0`;
* no ATTACK can reach me before my own first turn in either seat (`docs/rules.md` §2, rulebook L152);
* no ABILITY damage can either — only Basics are in play on turn 1, since neither player may evolve on
  their own first turn (`docs/rules.md` §4), and none of the 21 damage-counter Abilities in
  `EN_Card_Data.csv` sits on a Basic;
* and the Basics I keep in hand cannot be stripped, because the player going first cannot play a
  Supporter (rulebook L133).

So deferring is weakly dominant: never worse, and it preserves every bench-drop Ability (Meowth ex's
Last-Ditch Catch — the case that opened Issue #197) plus a turn of information.

The take-fewer mechanism itself is NOT tested here any more — it is alive and covered at `_TO_BENCH`
in `test_fetch_doctrine.py`, which is where it still decides something.
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
    """The frame this module was built on: on the real f3 pregame state the Pilot DECLINES rather than
    benching Meowth ex, so Last-Ditch Catch survives for an in-game bench.

    Ruled 2026-07-04, re-affirmed 2026-07-30. The OUTCOME is unchanged across every mechanism this
    has had — a −15 rung, then the exposure leg, now the rule — which is why it stays the anchor."""
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert _build_mega_lucario_pilot().decide(fx["obs"]) == []


@pytest.mark.req("REQ-FETCH-0031")
def test_the_refusal_is_unconditional_even_for_the_wincon_line_base():
    """The rule does not weigh the body, and this is the assertion that says so.

    An hour before decision 9 this file asserted the OPPOSITE — that Riolu, the win-condition Line
    base, must still be benched at Set Up — because the mechanism then was a price and a needed body
    could outbid its own exposure. Under the rule there is nothing to outbid: Riolu is benched on turn
    1 instead, losing nothing, since my first turn precedes any legal attack in either seat.

    Kept as a test rather than dropped, because "surely we still want the line base down" is exactly
    the intuition that would quietly reintroduce a pregame price."""
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
    """Soundness bound: `_never_pre_bench` keys on `_SETUP_BENCH` and nothing else, so an in-game
    bench play is untouched and still the Deploy Marginal's to price. Asserted on the filter directly
    — a board-level test would confound the rule with whatever the equation happens to score."""
    pilot = _build_mega_lucario_pilot()
    assert pilot._never_pre_bench({"context": _SETUP_BENCH}, [0]) == []
    assert pilot._never_pre_bench({"context": _SETUP_BENCH}, [0, 1]) == []
    for ctx in (0, 7, 9):                       # MAIN / TO_HAND / TO_BENCH: all left alone
        assert pilot._never_pre_bench({"context": ctx}, [0, 1]) == [0, 1]
    assert pilot._never_pre_bench({}, [0]) == [0]      # no context: never silently refuses
