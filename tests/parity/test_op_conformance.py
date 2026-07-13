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

# Ops with no committed god micro-trace yet — each entry says what a pin needs.
UNPINNED: set[str] = {
    # Riptide's shuffle-back: capture_card can't fire Riptide (it's menu-gated at 0
    # discard-{W} and chaos never fills the discard, fired=0), and a god-free cabt trace
    # can't live in tests/fixtures/parity/ (test_search_api needs god-frame seeding).
    # Pinned instead by the committed green cabt fixture episode-83970983 (Riptide clean,
    # the op fires) in test_cabt_replays.py.
    "xShuffleDiscardEnergyToDeck",
    # Powerglass's end-of-turn attach-from-discard is a between-turns tool passive
    # capture_card can't stage (needs an Active Powerglass holder + a Basic Energy in
    # the discard at the owner's end of turn). Pinned by the committed green cabt fixture
    # episode-83119861 (Powerglass clean, the op fires) in test_cabt_replays.py.
    "xEotAttachEnergyFromDiscard",
    # The 2026-07-13 fan-out ops — each is verified by a committed cabt fixture in
    # test_cabt_replays.py (clean end-to-end for the CLEAN cards; a partial-replay
    # _guard for the ADVANCED cards whose episode has a later unrelated blocker).
    # capture_card can't easily stage most (a specific board/hand/discard state).
    "xDiscardEnergyAttachChoose",   # Blaziken ex Seething Spirit — fixture 83486999 (clean)
    "xDiscardToolsInPlay",          # Tool Scrapper — fixture 83665798 (clean)
    "xFirstEffectChoose",           # Kieran "Choose 1" — fixture 83457493 (clean)
    "xCurseBlast",                  # Dusclops/Dusknoir Cursed Blast — offer fixture 85605555
                                    # (clean) + self-KO guard 83689598
    "xOppHandRevealDiscardMulti",   # Eri — guard 82225138 (advanced)
    "xBothBottomHandCoinDraw",      # Lucian — guard 85687339 (advanced)
    "xOppHandRevealChooseFiltered", # Energy Swatter — guard 82006648 (advanced)
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
