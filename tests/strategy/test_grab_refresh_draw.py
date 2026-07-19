"""Swing-informed grab grading (hand-disruption grill ruling 2, 2026-07-19) — the disruptor sibling
of the gusting grill.

At a TO_HAND draw-Supporter grab, `grab-a-draw-supporter-in-setup` gives a FLAT +10 to every
`draw` Supporter, so Judge and Lillie's tie and the option INDEX decides (ep86088989 f29, CRITICAL:
the agent grabbed Judge; the human wanted Lillie's — "Lillies would have been far more helpful").
The ADR-0060 swing oracle already separates them: early (six prizes) Lillie's redraws 8 to Judge's
4. `_grab_refresh_draw_tactical` reads that own-draw count as a sub-point tie-break, so the
bigger-ceiling refresh is grabbed among equals — without disturbing the band (a draw Supporter can
never out-grab the +15 chain opener or a +18 line piece).

The overall pick at f29 stays the seam-C chain opener (Team Rocket's Petrel, +15) — the
Petrel-vs-Lillie's residual is filed for human re-review (the grill spec). This pins ONLY the
disruptor-jurisdiction claim: Lillie's ≻ Judge among the draw Supporters.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CORR = REPO / "data" / "corrections"

PETREL, JUDGE, LILLIES = 1219, 1213, 1227


def _record(episode: str, frame: int) -> dict:
    for jf in CORR.glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if str(d.get("episode_id")) == episode and d.get("decision", {}).get("frame") == frame:
                return d
    raise AssertionError(f"correction {episode}-{frame} not found in data/corrections/")


def _pilot():
    """A FRESH pilot per test — the Pilot is stateful across `explain()` calls (corpus discipline)."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot("mega_lucario")[0]


@pytest.mark.req("REQ-DISRUPT-0001")
def test_lillies_outranks_judge_at_the_grab():
    """ep86088989 f29: among the tied draw Supporters, Lillie's (redraws more) now out-scores Judge,
    and both still ride the `grab-a-draw-supporter-in-setup` band."""
    rec = _record("86088989", 29)
    dec = _pilot().explain(rec["obs"])
    by_card = {}
    for t in dec.options:
        by_card.setdefault(t.card_id, t)
    judge, lillies = by_card[JUDGE], by_card[LILLIES]
    assert lillies.score > judge.score
    assert any(h.id == "grab-a-draw-supporter-in-setup" for h, _ in judge.fired)
    assert any(h.id == "grab-a-draw-supporter-in-setup" for h, _ in lillies.fired)


@pytest.mark.req("REQ-DISRUPT-0001")
def test_the_grab_tie_break_stays_below_the_chain_opener_band():
    """The tie-break is sub-point: it separates the draw Supporters but never lifts one over the
    seam-C chain opener (Petrel, +15). The overall pick is unchanged — the Petrel-vs-Lillie's
    residual is a re-review item, not this build's claim."""
    rec = _record("86088989", 29)
    dec = _pilot().explain(rec["obs"])
    by_card = {}
    for t in dec.options:
        by_card.setdefault(t.card_id, t)
    petrel, lillies = by_card[PETREL], by_card[LILLIES]
    assert petrel.score > lillies.score
    assert any(h.id == "grab-the-chain-opener" for h, _ in petrel.fired)
