"""Seeded free-run self-play smoke (ADR-0050 M4 item 8) — DLL-free.

Whole games on the cgpy engine alone under a seeded chaos policy: no crash, only legal
selections, and the game TERMINATES (a result, or the step cap without an exception).
This exercises flows no replay pins frame-by-frame (fresh shuffles, novel line-ups) —
the cheap always-on complement to the nightly full-pool parity run.

The policy never picks a deferred attack (using one raises UnsupportedCard by design;
the menu offers them for parity — Phantom-Dive-class pin).
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from cgpy.chain import def_for, is_deferred  # noqa: E402
from cgpy.engine import Engine  # noqa: E402
from cgpy.rng import SeededRng  # noqa: E402

_MAX_STEPS = 4000


def _deck(agent: str) -> list[int]:
    p = REPO / "src" / "agents" / agent / "deck.csv"
    return [int(x) for x in p.read_text(encoding="utf-8").split()[:60]]


def _choose(sel, rng: random.Random) -> list[int]:
    opts = sel.options
    lo, hi = sel.min_count, sel.max_count
    legal = list(range(len(opts)))
    if sel.context == 0:                        # MAIN: never pick a deferred attack
        legal = [i for i in legal
                 if opts[i].get("type") != 13
                 or not is_deferred(def_for(f"attack:{opts[i]['attackId']}"))]
    k = rng.randint(lo, hi) if hi >= lo else lo
    if k == 0 and hi >= 1 and rng.random() < 0.5:
        k = 1
    if sel.context == 0:
        non_end = [i for i in legal if opts[i].get("type") != 14]
        if non_end and rng.random() < 0.8:
            return [rng.choice(non_end)]
        return [legal[-1]]                      # END is always last
    k = min(k, len(legal))
    return rng.sample(legal, k) if k else []


@pytest.mark.parametrize("pair,seed", [
    (("mega_starmie", "mega_starmie"), 424242),
    (("mega_lucario", "dragapult_ex"), 434343),
])
def test_selfplay_terminates_without_crash(pair, seed):
    rng = random.Random(seed)
    eng, err_player, err_type = Engine.start(_deck(pair[0]), _deck(pair[1]),
                                             rng=SeededRng(seed))
    assert eng is not None, f"deck rejected: seat {err_player} errorType {err_type}"
    for _ in range(_MAX_STEPS):
        if eng.gs.result != -1:
            break
        sel = eng.gs.pending
        assert sel is not None, "no result and no pending select — the engine stalled"
        eng.step(_choose(sel, rng))
    # Termination (or the cap) with zero exceptions IS the smoke's assertion; a finished
    # game additionally carries a coherent result code.
    if eng.gs.result != -1:
        assert eng.gs.result in (0, 1, 2)
