"""The PREGAME setup-bench DECLINE (ep83661652 f3, 2026-07-04): two pieces.

1. `decide()` single-pick take-fewer — at an OPTIONAL select (`minCount == 0`) the Pilot may DECLINE
   (return fewer picks) when the best option is actively DISCOURAGED (score < 0), instead of always
   taking `maxCount` options. Unchanged, and still the mechanism.
2. WHAT makes the score negative. Was `dont-pre-bench-the-supporter-tutor` (−15); since ADR-0081 it
   is the Deploy Marginal's exposure leg, which prices Meowth ex's 2-prize liability instead of
   asserting a flat penalty.

The decline briefly flipped on 2026-07-30 (ADR-0081 Amendment F: with no other Pokémon in hand,
declining leaves a one-body board) and was restored the same day by the user's own narrowing —
`docs/rules.md` §2 puts my first turn before the first legal attack in either seat, so the tutor can
be benched on turn 1 *with* Last-Ditch Catch. Waiting costs nothing here; benching costs the Ability.

The corpus record for this frame CANNOT express that: at `decision` scope `correct` is mandatory and
must index a legal option (`correction.py`), so a decline has no representation and the record reads
`chosen == correct == [0]`. It is held out of the Decision Gate on exactly that ground
(`ml0703_decline_the_setup_tutor_f3.json`), and the ruling lives HERE instead.
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
    benching Meowth ex — the supporter_tutor is saved for an in-game bench, which is strictly better
    because the SAME body can be benched on turn 1 and still fire Last-Ditch Catch.

    THIS is the frame's ruling of record. The corpus correction cannot carry it: a decline needs
    `correct: []`, which `decision` scope forbids, so the sweep sees `chosen == correct == [0]` and
    would read the decline as a regression. The frame is held out on that ground, and this test is
    what actually gates the behaviour."""
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pilot = _build_mega_lucario_pilot()
    assert pilot.decide(fx["obs"]) == [], "should decline the optional pregame bench of Meowth ex"


def _setup_bench_obs(hand_ids):
    """A minimal SETUP_BENCH select (minCount 0, maxCount 1) offering each hand card as a bench pick."""
    opts = [{"type": "Card", "area": 2, "index": i, "playerIndex": 0} for i in range(len(hand_ids))]
    return {"current": {"players": [{"active": [None], "bench": [], "hand": [{"id": c} for c in hand_ids]},
                                    {"active": [None], "bench": []}], "yourIndex": 0, "turn": 0},
            "select": {"context": _SETUP_BENCH, "minCount": 0, "maxCount": 1, "option": opts}}


def test_the_decline_is_the_deploy_marginals_exposure_leg():
    """REQ-FETCH-0031: the trim fires because the pick scores < 0, and since ADR-0081 that negative is
    the Deploy Marginal's EXPOSURE leg, not `dont-pre-bench-the-supporter-tutor` (−15, deleted).

    The pregame Actives are face down, so the Prize Path is unreadable (`their_path_turns is None`)
    and exposure falls back to the body's own liability: Meowth ex is a 2-prize ex, one prize of
    EXCESS over an unavoidable 1-prize body. The Ability leg contributes nothing — at Set Up "once
    during your turn" is unsatisfiable, so decision 3's zero is DERIVED — leaving the exposure alone
    to sink the placement."""
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    option = _build_mega_lucario_pilot().explain(fx["obs"]).options[0]
    assert option.score < 0
    row = option.deploy_working
    assert row["exposure"] > 0 and row["ability_relevance"] == 0
    assert row["total"] < 0


def test_decline_only_drops_a_discouraged_pick_not_a_neutral_basic():
    """REQ-FETCH-0031: the take-fewer trims only the DISCOURAGED pick — a plain startable Basic
    (`bench-fill-a-basic` +12) is still placed, so the trim never becomes a blanket decline.

    `deploy_value=True` is passed explicitly: the Pilot ctor defaults every feature OFF (the shipped
    state lives in `runtime.PROFILE`, which `tune._build_pilot` applies), so without it this pilot has
    no decider and the test would measure the ctor default. The DECLINE half lives in the two tests
    above, on the real f3 board — a hand-built pregame with an opponent holding no Pokémon at all
    reads `their_path_turns == 0.0` rather than None, which suppresses the exposure fallback the
    decline depends on."""
    RIOLU = 677
    stats = {RIOLU: CardStat(RIOLU, name="Riolu", hp=80)}
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  functions=CardFunctions({}), deploy_value=True)
    assert pilot.decide(_setup_bench_obs([RIOLU])) == [0]          # a plain Basic: still benched
