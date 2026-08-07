"""The machine-store writer + run manifest (S3a §D4).

Machine Corrections ride the SAME rails as human ones, distinguished only by ``provenance="machine"``.
They land in the gitignored, **wholesale-rewritten** ``data/corrections/machine/`` store — a re-run
replaces it, so re-runs cannot duplicate. The θ precision gate is the safety net, amortized.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from train.blunder.correction import build_correction
from train.blunder.store import DEFAULT_ROOT

MACHINE_DIR = DEFAULT_ROOT / "machine"
MACHINE_STORE = MACHINE_DIR / "corrections.jsonl"
MACHINE_MANIFEST = MACHINE_DIR / "manifest.json"


def _rationale(dis: dict) -> str:
    """The auto rationale. Deliberately free of the uppercase ``CRITICAL`` token — that is the human marker."""
    return (f"value_delta: expert best option {dis['correct']} P(win)={dis['v_best']:.3f} beats "
            f"chosen option {dis['chosen']} P(win)={dis['v_chosen']:.3f} "
            f"(delta={dis['delta']:.3f}). per-option P(win): {dis.get('v_table', {})}. "
            f"[machine label; provenance=machine]")


def to_correction(dis: dict, agent: str):
    """A machine Correction from a disagreement; ``chosen`` is overridden to the choice PROVIDER's pick."""
    decision = dataclasses.replace(dis["decision"], chosen=[dis["chosen"]])
    return build_correction(
        decision,
        source="own",                                  # both self-play seats are ours (tune.py own-filter)
        agent=agent,
        correct=[dis["correct"]],
        category="value_delta",
        rationale=_rationale(dis),
        provenance="machine",
        chosen_label=str(dis["chosen"]),
        correct_label=str(dis["correct"]),
        agent_build=None,                              # corpus games aren't submission builds
    )


def cap_by_delta(dis_list, cap: int):
    """The ``cap`` largest-|ΔV| disagreements plus the dropped count, so the caller reports rather than truncates."""
    ordered = sorted(dis_list, key=lambda d: abs(d["delta"]), reverse=True)
    if cap is None or len(ordered) <= cap:
        return ordered, 0
    return ordered[:cap], len(ordered) - cap


def write_machine_store(corrections, dest: Path | str = MACHINE_STORE) -> Path:
    """Rewrite the store WHOLESALE. No append — it is regenerable, so a re-run can never duplicate."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        for c in corrections:
            fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    return dest


def write_manifest(manifest: dict, dest: Path | str = MACHINE_MANIFEST) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest
