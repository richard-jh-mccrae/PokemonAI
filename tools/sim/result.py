"""The Battle Result: the persisted, machine-readable record of one Battle (ADR-0021 amendment).

One immutable, self-describing object per run — an aggregate header (provenance, the experiment
overlay measured, params incl. the seat split, tally + win-rate + Wilson CI) plus the per-Match
`matches[]` rows that are the **source of truth** every aggregate recomputes from. Appended to a
committed `data/battles.jsonl` via the generic JSONL helpers in `submit.history`. No `verdict` is
stored — that is interpretation, derived on read.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from sim.battle import balanced_tally, wilson_ci
from submit.history import append_history, read_history

SCHEMA_VERSION = 1

DEFAULT_LOG = Path(__file__).resolve().parents[2] / "data" / "battles.jsonl"


def read_battles(path=DEFAULT_LOG) -> list[dict]:
    """Every Battle Result row in append order (missing log -> [])."""
    return read_history(path)


def append_battle(path, row: dict) -> None:
    """Append one immutable Battle Result row to the committed JSONL log."""
    append_history(path, row)


def next_battle_id(path=DEFAULT_LOG) -> int:
    """The next monotonic `battle_id` (max recorded + 1, or 1 for an empty/absent log)."""
    return max((r.get("battle_id", 0) for r in read_battles(path)), default=0) + 1


def deck_hash(ids: list[int]) -> str:
    """Order-independent digest of a 60-card decklist, so a deck change shows as a hash diff."""
    blob = ",".join(str(i) for i in sorted(ids)).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()[:16]


def _contestant(side: str, row: dict, deck_ids: list[int], overlay) -> dict:
    """One side's identity + provenance + the config under test (ADR-0021 amendment)."""
    sid = row.get("submission_id")
    return {
        "side": side,
        "kind": "working-tree" if sid == "src" else "build",
        "submission_id": sid,
        "agent": row.get("agent"),
        "git_hash": row.get("git_hash"),
        "label": row.get("label"),
        "artifact_stem": row.get("artifact"),
        "deck_hash": deck_hash(deck_ids),
        "overlay": overlay,
    }


def build_battle_result(*, battle_id, ran_at, run_git_hash, mode, contestants, records, params,
                        hypothesis="") -> dict:
    """Assemble one Battle Result from the seat-balanced `records` (list[BattleMatch])."""
    bt = balanced_tally(records)
    n = bt["n"]
    lo, hi = wilson_ci(bt["a_wins"], n)
    return {
        "schema_version": SCHEMA_VERSION,
        "battle_id": battle_id,
        "ran_at": ran_at,
        "run_git_hash": run_git_hash,
        "mode": mode,
        "hypothesis": hypothesis,
        "params": params,
        "reproducibility": {"seeded": False, "kind": "statistical"},
        "tally": {k: bt[k] for k in ("n", "a_wins", "b_wins", "draws", "a_crashes", "b_crashes")},
        "by_seat": {str(s): bt["by_seat"][s] for s in (0, 1)},   # str keys: JSON-stable round-trip
        "win_rate": (bt["a_wins"] / n) if n else 0.0,
        "wilson_ci": {"lo": lo, "hi": hi, "z": 1.96},
        "contestants": [
            _contestant("A" if i == 0 else "B", c["row"], c["deck_ids"], c.get("overlay"))
            for i, c in enumerate(contestants)
        ],
        "matches": [
            {"match_index": i, "a_seat": r.a_seat, "winner": r.winner, "crashed": list(r.crashed)}
            for i, r in enumerate(records)
        ],
    }
