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
    ("episode-84073333-replay.json.gz", 111),  # Lucky Helmet reactive draw-2-when-damaged
    ("episode-82749168-replay.json.gz", 96),   # Sparkling Crystal Tera cost -1
    ("episode-82229122-replay.json.gz", 110),  # Deluxe Bomb reactive counters; Crustle snipe
    ("episode-85046764-replay.json.gz", 152),  # Relicanth Memory Dive: Archaludon ex uses
                                               # Duraludon's Hammer In / Raging Hammer
    ("episode-83285531-replay.json.gz", 84),   # Nebula Beam ignore-effects pierces Full
                                               # Metal Lab's -30 (+ Memory Dive)
    ("episode-82234130-replay.json.gz", 114),  # Latias ex Skyliner: Basic Pokémon retreat free
    ("episode-83692318-replay.json.gz", 144),  # clean Froslass-deck game (Munkidori/Risky-Ruins
                                               # counter placements; general counter coverage)
    ("episode-83286739-replay.json.gz", 83),   # Xerosic's Machinations: opponent discards to 3
    ("episode-83665001-replay.json.gz", 51),   # Sacred Ash: shuffle Pokémon from discard to deck
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


def test_froslass_freezing_shroud_fires():
    """Froslass "Freezing Shroud" puts a Checkup damage counter on every ability-Pokémon
    (both sides, except Froslass). This episode isn't clean end-to-end (a later,
    unrelated blocker), but WITHOUT the ability cgpy diverges at the very first
    Freezing-Shroud checkup (frame 54: both Drakloak + both Munkidori take a counter,
    the Froslass Active skipped); WITH it, the replay sails well past. Guards the
    between-turns counter placement + order without needing a fully-clean fixture."""
    path = FIXTURES / "episode-83697279-replay.json.gz"
    payload = json.loads(gzip.decompress(path.read_bytes()))
    report = replay(convert(payload))
    assert report.frames_green > 54, (
        f"Freezing Shroud regressed — diverged at the checkup:\n{report}")
