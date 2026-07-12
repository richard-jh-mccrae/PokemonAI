"""God-free cabt episodes convert and replay divergence-free (ADR-0050 M4).

Real meta-deck games through the reveal-oracle path: draw/coin binding from the
mover's own windows, prize identities at take time, deck order from revealed
listings, look-at-top-N pre-binding from DECK->LOOKING move logs. DLL-free.
REQ-CGPY-0002.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "parity"))

from from_cabt import convert  # noqa: E402

from cgpy.verify.replayer import replay  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures"

EPISODES = [
    ("match-replay.json", 60),              # arena episode (Iono deck; card 269)
    ("episode-81364540-replay.json.gz", 43),  # kaggle episode (look-reveal binding)
]


@pytest.mark.parametrize("name,frames", EPISODES, ids=lambda v: str(v))
def test_cabt_episode_replays_clean(name, frames):
    path = FIXTURES / name
    if name.endswith(".gz"):
        payload = json.loads(gzip.decompress(path.read_bytes()))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    trace = convert(payload)
    assert len(trace.frames) == frames, "conversion shrank — the episode changed?"
    report = replay(trace)
    assert report.clean, f"\n{report}"
