"""Op-conformance gate (ADR-0050 M4 item 4): every interpreter op carries a committed
semantic pin — a fixture trace that exercised a ChainDef containing it and replayed
divergence-free. The parity gate (test_replay_fixtures) proves the traces are green;
this test proves the op → pinning-trace mapping stays COMPLETE as ops are added.

An op with no pinning fixture yet must be listed in UNPINNED — exactly (a new op silently
missing coverage fails, and pinning a listed op forces shrinking the list).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "parity"))

from cgpy.chain import OPS  # noqa: E402
from report import build_ledger  # noqa: E402

# Ops with no committed micro-trace yet — each entry says what a pin needs.
UNPINNED = {
    "xDiscardEnergyAttachSelf",   # Regi-Charge family: menu-gated on discard fuel; a
                                  # capture must first bank energies in the discard
    "xDiscardHandDraw",           # "Discard your hand and draw N" — no live seeded
                                  # trainer carries it alone yet (multi-sentence texts)
}


def test_every_op_has_a_committed_pin_or_is_declared_unpinned():
    ledger = build_ledger()
    covered = set(ledger["summary"]["ops"]["coveredOps"])
    uncovered = set(OPS) - covered
    newly_uncovered = uncovered - UNPINNED
    assert not newly_uncovered, (
        f"interpreter ops without a committed pinning trace: {sorted(newly_uncovered)} "
        f"— capture a micro-trace (tools/parity/capture_card.py), commit it under "
        f"tests/fixtures/parity/, or add the op to UNPINNED with a reason")
    stale = UNPINNED - uncovered
    assert not stale, (
        f"UNPINNED entries now covered — remove them: {sorted(stale)}")


def test_conformance_counts_match_ledger():
    ledger = build_ledger()
    ops = ledger["summary"]["ops"]
    assert ops["total"] == len(OPS)
    assert ops["covered"] == len(set(ops["coveredOps"]))
