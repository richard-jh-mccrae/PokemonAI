"""`_finish_turn_last._wins_now` must not read a bench-snipe KO as game-winning.

Residual affordability follow-up: ADR-0064.
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
    spec = importlib.util.spec_from_file_location("tune", REPO / "tools" / "train" / "tune.py")
    tune = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tune)
    pilot, _ = tune._build_pilot("mega_starmie")
    return pilot


@pytest.mark.req("REQ-PILOT-0007")
def test_f54_builds_the_wincon_instead_of_the_premature_bench_snipe():
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pilot = _build_mega_starmie_pilot()
    chosen = pilot.decide(fx["obs"])
    assert fx["chosen"] == [13]
    assert 13 not in chosen, f"still taking the premature snipe-KO: {chosen}"
    # an Attach onto an in-play body carries inPlayArea; Attack / End do not
    opt = fx["obs"]["select"]["option"][chosen[0]]
    assert opt.get("inPlayArea") is not None, f"expected an Attach onto a body, got {opt}"
