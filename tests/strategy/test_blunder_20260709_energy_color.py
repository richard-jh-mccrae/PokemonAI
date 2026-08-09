"""Blunder round 2026-07-09 (dragapult_ex) — draw-engine line detection."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _pilot(deck):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(deck)[0]


def test_draw_engine_detection_flags_the_engine_line_not_the_single_hop_engines():
    """A base is flagged when its PAYOFF carries `draw`/`stall`, even when the base itself is untagged."""
    p = _pilot("dragapult_ex")
    assert p._is_draw_engine_body(305)                         # Dunsparce -> Dudunsparce
    assert p._is_draw_engine_body(66)                          # Dudunsparce itself
    assert not p._is_draw_engine_body(676)                     # Solrock — no draw, no drawing evolution
    assert p._is_draw_engine_body(675)                         # Lunatone — Lunar Cycle draws
