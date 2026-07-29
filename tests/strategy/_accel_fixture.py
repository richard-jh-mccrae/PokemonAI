"""A real accel-stranded board for the Deploy Marginal's accel-unlock leg (ADR-0081 decision 8).

Built on the REAL mega_lucario pilot rather than a hand-stubbed one, because the leg reads card
facts the stub would have to re-assert: Mega Lucario ex's Aura Jab is the rider ("Attach up to 3
Basic {F} Energy cards from your discard pile to your Benched Pokémon in any way you like"), Riolu is
the Line pre-evolution that receives, and Mega Brave's `{F}{F}` is the need that bounds how much
Energy the recipient can actually use. Same approach as `test_setup_bench_decline.py`.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.strategy.context import _MAIN, _PLAY  # noqa: E402

MEGA_LUCARIO_EX, RIOLU, BASIC_F = 678, 677, 6


def _mega_lucario_pilot():
    spec = importlib.util.spec_from_file_location("tune", REPO / "tools" / "train" / "tune.py")
    tune = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tune)
    pilot, _ = tune._build_pilot("mega_lucario")
    pilot.deploy_value = True                     # the decider under test; shipped armed-OFF
    return pilot


def accel_obs(*, recipient_benched: bool = False, discard_energy: int = 3) -> dict:
    """Mega Lucario ex Active (the accelerator), Riolu in hand, {F} Energy in the discard.

    With `recipient_benched` the Bench already holds a Riolu, so the rider is NOT stranded and the
    unlock must price 0 — the rule's hand-written stand-down, derived."""
    bench = [{"id": RIOLU, "hp": 80, "energies": []}] if recipient_benched else []
    me = {"active": [{"id": MEGA_LUCARIO_EX, "hp": 340, "energies": [BASIC_F]}],
          "bench": bench,
          "hand": [{"id": RIOLU}],
          "discard": [{"id": BASIC_F} for _ in range(discard_energy)],
          "prize": [None] * 6, "deckCount": 40}
    opp = {"active": [{"id": MEGA_LUCARIO_EX, "hp": 340, "energies": []}],
           "bench": [], "prize": [None] * 6, "hand": None, "handCount": 3, "deckCount": 40}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 6,
                        "supporterPlayed": False, "energyAttached": False},
            "select": {"context": _MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": _PLAY, "index": 0}, {"type": 14}]}}


def accel_pilot(*, recipient_benched: bool = False):
    """``(pilot, obs, option)`` — the option being the Riolu deploy."""
    obs = accel_obs(recipient_benched=recipient_benched)
    return _mega_lucario_pilot(), obs, obs["select"]["option"][0]
