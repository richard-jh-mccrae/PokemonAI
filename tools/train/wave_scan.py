"""Build a **wave scan sheet** — every Discrimination Gate flip the developer still has to rule,
with the evidence to rule it, derived rather than transcribed.

    python tools/train/leaf_lab.py diff --baseline data/leaf_lab/baseline.json --out gate.json
    python tools/train/wave_scan.py --diff gate.json --out <sheet.md> --ruled <rulings.md>

Nothing here is retyped: a hand-maintained sheet drifts from the gate the moment either moves.

Excluded automatically: frames already ruled, held out, or voided — all three are resolved, and
re-presenting them is the "becomes scenery" failure the gate readout's doctrine warns about.

The default verdict is REVERT, because that is the verdict that changes nothing on disk; only a
CONFORM re-captures a baseline row, so only a CONFORM is worth the developer's time.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


def ruled_keys(path: Path) -> set:
    """Parsed out of the committed Markdown rather than kept as a second list, so the record stays
    the ONE place a verdict lives. The table ESCAPES a frame key's pipes; they are unescaped here."""
    if not path or not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    return {m.replace("\\|", "|") for m in re.findall(r"`(\d+\\\|\d+\\\|\w+\\\|\d+)`", text)}


def intent_of(correction) -> str:
    """From WHEREVER the scope records it: a turn-scope record's intent is in ``turn_plan`` and its
    ``rationale`` is EMPTY, so reading only ``rationale`` reports it as having no stated intent."""
    rationale = " ".join((getattr(correction, "rationale", "") or "").split())
    if rationale:
        return rationale
    plan = getattr(correction, "turn_plan", None) or {}
    line = " ".join(str(plan.get("intended_line") or "").split())
    end = " ".join(str(plan.get("expected_end_board") or "").split())
    if line and end:
        return f"[turn plan] {line} — expected end board: {end}"
    return f"[turn plan] {line or end}" if (line or end) else ""


def scan_rows(diff: dict, *, ruled=()) -> list:
    """One row per flip still owed a ruling, worst-ranked first."""
    from train.blunder.frame_view import _Cards, _option_summary
    from train.gates import keyed_corrections
    from train.leaf_lab import _cgpy_pilot_builder, evaluate_leaf_on_correction

    excused = set(ruled) | set(diff.get("held_out") or {}) | set(diff.get("voided") or {})
    keyed = dict(keyed_corrections(None))
    pilot_for, cards = _cgpy_pilot_builder(), _Cards()
    rows = []
    for key in diff.get("ok_to_miss") or []:
        if key in excused:
            continue
        c = keyed.get(key)
        if c is None:
            continue
        opts = (c.obs.get("select") or {}).get("option") or []
        cur = c.obs.get("current") or {}
        row = evaluate_leaf_on_correction(pilot_for(c.agent), c)
        vals = row.get("values") or []
        top = max((i for i, v in enumerate(vals) if v is not None),
                  key=lambda i: vals[i], default=None)

        def label(i):
            if i is None or i >= len(opts):
                return "?"
            return " ".join(_option_summary(i, opts[i], cur, cards, c.seat).split())

        rows.append({
            "key": key, "agent": c.agent, "category": c.category,
            "your_pick": c.correct_label or (label(c.correct[0]) if c.correct else "?"),
            "rationale": intent_of(c),
            "leaf_pick": label(top),
            "rank": row.get("correct_rank"), "n": row.get("n_options"),
        })
    return sorted(rows, key=lambda r: (-(r["rank"] or 0), r["key"]))


def render(rows: list, diff: dict, *, issue: str) -> str:
    esc = lambda s: (s or "").replace("|", "\\|")                      # noqa: E731 — table cells
    out = [f"# Wave-3 scan sheet — the {len(rows)} flips still owed a ruling (Issue {issue})", "",
           "**Generated, never hand-maintained** — regenerate with `tools/train/wave_scan.py` (see its",
           "docstring). `your pick` and `your rationale` come straight off the committed Correction,",
           "`leaf picks` is what the T3 leaf actually ranks first, and `rank` is where your pick landed.",
           "Worst-ranked first, so the frames the leaf is most wrong about read first.", "",
           "**How to use it.** The default verdict is `REVERT` — your recorded pick stands and the leaf",
           "is wrong. You only need to name the frames where the leaf's pick is genuinely **fine** (a",
           "`CONFORM`). Silence on a row means REVERT. CONFORM is the only verdict that changes anything",
           "on disk, so it is the only one worth the time.", "",
           "Frames already ruled, held out onto an owner, or carrying a voided ruling are excluded",
           "automatically — they are resolved, and re-presenting them is how a gate readout becomes",
           "wallpaper.", "",
           "| # | frame | agent | category | your pick | leaf picks | rank | your rationale |",
           "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        out.append(f"| {i} | `{esc(r['key'])}` | {r['agent']} | {r['category']} "
                   f"| {esc(r['your_pick'])} | {esc(r['leaf_pick'])} | {r['rank']}/{r['n']} "
                   f"| {esc(r['rationale'])} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Generate a wave ruling scan sheet from a gate artifact")
    ap.add_argument("--diff", type=Path, required=True,
                    help="the `leaf_lab.py diff --out` artifact for the build being ruled")
    ap.add_argument("--out", type=Path, required=True, help="the Markdown sheet to write")
    ap.add_argument("--ruled", type=Path, default=None,
                    help="the ruling record whose already-ruled frames are excluded")
    ap.add_argument("--issue", default="#262", help="the track issue the wave belongs to")
    args = ap.parse_args(argv)

    diff = json.loads(args.diff.read_text(encoding="utf-8"))
    already = ruled_keys(args.ruled)
    rows = scan_rows(diff, ruled=already)
    # LF bytes: this file is committed and read on both platforms (CLAUDE.md), and `write_text`
    # would frame it per whichever OS ran the command.
    args.out.write_bytes(render(rows, diff, issue=args.issue).encode("utf-8"))
    print(f"{len(rows)} owed a ruling  ({len(diff.get('ok_to_miss') or [])} flips, "
          f"{len(already)} already ruled, {len(diff.get('held_out') or {})} held out, "
          f"{len(diff.get('voided') or {})} voided)  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
