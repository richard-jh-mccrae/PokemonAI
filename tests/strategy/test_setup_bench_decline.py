"""The PREGAME setup-bench DECLINE (ep83661652 f3, 2026-07-04; re-ruled 2026-07-30): two pieces.

1. `decide()` single-pick take-fewer — at an OPTIONAL select (`minCount == 0`) the Pilot may DECLINE
   (return fewer picks) when the best option is actively DISCOURAGED (score < 0), instead of always
   taking `maxCount` options. Unchanged, and still the mechanism.
2. WHAT makes the score negative. Was `dont-pre-bench-the-supporter-tutor` (−15); since ADR-0081 it
   is the Deploy Marginal's exposure leg, which prices Meowth ex's 2-prize liability instead of
   asserting a flat penalty.

**f3 itself now BENCHES, and that is the ruling, not a regression.** User ruling 2026-07-30 on the
Decision Gate's `83661652|0|decision|3`: on that board Lunatone is Active and the hand is two {F},
two Lillie's, a Boss's and Meowth ex — the tutor is the ONLY Pokémon held. Declining leaves a
one-body board, and a single Knock Out then loses the game outright. So the exposure fallback stands
down when there is no other body to bench instead (ADR-0081 Amendment F), and the placement survives
at 0.0 — placed because nothing outranks it, never because it was endorsed.

The decline is therefore tested on the case that still holds: a `supporter_tutor` offered ALONGSIDE
another Basic, where declining costs nothing. A positive/neutral optional pick is still placed.
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
def test_f3_benches_the_tutor_because_it_is_the_only_body_held():
    """REQ-FETCH-0031, RE-RULED 2026-07-30: on the real f3 pregame state the Pilot PLACES Meowth ex.

    This test asserted the opposite until the Decision Gate sitting on `83661652|0|decision|3`. The
    old reading — save the tutor for an in-game bench so Last-Ditch Catch is not wasted — is right in
    general and is what `test_the_tutor_is_declined_when_another_body_is_held` still guards. It is
    wrong HERE because Meowth ex is the only Pokémon in the hand: declining does not defer the
    Ability, it leaves a one-body board that loses outright to one Knock Out.

    The placement is worth 0.0, not a positive: the body is placed because nothing outranks it
    (ADR-0081 Amendment F stands the exposure fallback down), never because it was endorsed."""
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pilot = _build_mega_lucario_pilot()
    assert pilot.decide(fx["obs"]) == [0]
    row = pilot.explain(fx["obs"]).options[0].deploy_working
    assert row["exposure"] == 0 and row["total"] == 0     # stood down, not endorsed


def _setup_bench_obs(hand_ids):
    """A minimal SETUP_BENCH select (minCount 0, maxCount 1) offering each hand card as a bench pick."""
    opts = [{"type": "Card", "area": 2, "index": i, "playerIndex": 0} for i in range(len(hand_ids))]
    return {"current": {"players": [{"active": [None], "bench": [], "hand": [{"id": c} for c in hand_ids]},
                                    {"active": [None], "bench": []}], "yourIndex": 0, "turn": 0},
            "select": {"context": _SETUP_BENCH, "minCount": 0, "maxCount": 1, "option": opts}}


@pytest.mark.req("REQ-FETCH-0031")
def test_the_tutor_is_declined_when_another_body_is_held():
    """REQ-FETCH-0031: the decline SURVIVES the f3 re-ruling — put a plain Basic in the hand beside
    the tutor and the one-body argument evaporates, so the exposure leg speaks again and declines.

    This is the pairing that shows Amendment F is narrow. The same Meowth ex, the same select; the
    only thing that changed is whether declining costs me a board. Riolu is offered as a second
    OPTION too, so the decline is a real preference between two available placements rather than an
    artefact of there being nothing else to pick.

    The negative is the Deploy Marginal's EXPOSURE leg, not `dont-pre-bench-the-supporter-tutor`
    (−15, deleted): the pregame Actives are face down so the Prize Path is unreadable, and the
    fallback prices Meowth ex's 2-prize body at one prize of EXCESS. The Ability leg contributes
    nothing — at Set Up "once during your turn" is unsatisfiable, so decision 3's zero is DERIVED."""
    RIOLU = 677
    # Built by ADDING a Riolu to the REAL f3 board, not by hand: a synthetic pregame whose opponent
    # holds no Pokémon at all reads `their_path_turns == 0.0` rather than None, and the fallback this
    # test is about only fires when the Path is genuinely unreadable.
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    obs = json.loads(json.dumps(fx["obs"]))
    me = obs["current"]["players"][obs["current"].get("yourIndex", 0)]
    me["hand"].append({"id": RIOLU})
    obs["select"]["option"].append({"type": 3, "area": 2, "playerIndex": 0,
                                    "index": len(me["hand"]) - 1})

    pilot = _build_mega_lucario_pilot()
    dec = pilot.explain(obs)
    meowth = next(o for o in dec.options if o.card_id == 1071)
    assert meowth.deploy_working["exposure"] > 0     # the liability is priced again
    assert meowth.score < 0                          # ...and it sinks the placement
    assert 1071 not in [dec.options[i].card_id for i in dec.chosen]


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
