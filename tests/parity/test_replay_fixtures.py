"""Parity-corpus presence guard (ADR-0059).

Replay correctness and clone safety share one stronger per-trace lane in
``test_clone_safety.py``; they must not be run twice.
"""
from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "parity"
TRACES = sorted(FIXTURES.glob("*.trace.json.gz"))


def test_fixture_corpus_present():
    assert len(TRACES) >= 10, "the committed parity corpus should not shrink"
