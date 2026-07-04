"""`_finish_turn_last._wins_now` fix for the ep83661649 f54 blunder (2026-07-04), engine-backed on the
real mega_starmie state (`tests/fixtures/corrections/wins_now_f54.json`).

A KO-class score coming ONLY from a bench SNIPE (a 1-prize Staryu) must NOT be read as a game-winning
Active KO — it credited the opponent Active's 3-prize value for any KO-class attack. Gated on
`board.active_can_ko` (my Active actually KOs the opp Active), so the snipe attack falls back to
develop-first (attack-last): the Pilot builds its win-condition THIS turn and the free snipe-KO still
lands after, instead of prematurely spending the turn on the snipe.

NOTE: the residual "which Mega gets the Energy" (active vs bench, `dont-overbuild-the-doomed-wincon`
firing off an over-estimated Incoming) is the separate affordability follow-up —
docs/todo/incoming-affordability.md.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

FIXTURE = REPO / "tests" / "fixtures" / "corrections" / "wins_now_f54.json"


def _build_mega_starmie_pilot():
    """The real engine-backed mega_starmie Pilot (mirrors main.py via tune._build_pilot)."""
    spec = importlib.util.spec_from_file_location("tune", REPO / "tools" / "train" / "tune.py")
    tune = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tune)
    pilot, _ = tune._build_pilot("mega_starmie")
    return pilot


@pytest.mark.req("REQ-PILOT-0007")
def test_f54_builds_the_wincon_instead_of_the_premature_bench_snipe():
    """REQ-PILOT-0007: on the f54 state the Pilot does NOT take the 1-prize bench snipe-KO immediately
    (option 13, Jetting Blow) — `_wins_now` no longer mis-reads it as game-winning — it develops first
    (an Attach that builds toward Nebula Beam); the snipe-KO still follows same turn (attack-last)."""
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pilot = _build_mega_starmie_pilot()
    chosen = pilot.decide(fx["obs"])
    assert fx["chosen"] == [13]                          # the recorded blunder was the premature attack
    assert 13 not in chosen, f"still taking the premature snipe-KO: {chosen}"
    # the pick develops a body (an Attach onto an in-play Pokémon carries inPlayArea/inPlayIndex) —
    # building the win-condition, not the turn-ending Attack / End
    opt = fx["obs"]["select"]["option"][chosen[0]]
    assert opt.get("inPlayArea") is not None, f"expected an Attach onto a body, got {opt}"
