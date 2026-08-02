"""Build a **wave scan sheet** — every Discrimination Gate flip the developer still has to rule,
with the evidence to rule it, derived rather than transcribed.

    python tools/train/leaf_lab.py diff --baseline data/leaf_lab/baseline.json --out gate.json
    python tools/train/wave_scan.py --diff gate.json --out data/leaf_lab/wave3-scan-sheet.md \
                                    --ruled data/leaf_lab/wave3-rulings.md

It exists because of a question asked mid-wave-3 (Issue #262): *"So many of these frames' correction
answer is right in their rationale. must we really go through all of these?"* The answer was no —
every `Correction` already carries its `rationale`, `correct_label` and `category`, so the sheet the
developer needs can be GENERATED from the corpus and the live leaf. Nothing here is retyped, which is
the point: a hand-maintained sheet drifts from the gate the moment either moves, and a wave that
takes a week is exactly when that happens.

**Excluded automatically:** frames already ruled (parsed out of the ruling record), frames the
Held-out Ledger owns, and frames whose ruling is voided. All three are already resolved — putting
them in front of the developer again is the "broken for three phases becomes scenery" failure the
gate readout's own doctrine warns about.

The default verdict for everything listed is REVERT — the recorded label stands and the leaf is
wrong — because that is the verdict that changes nothing on disk. Only a CONFORM re-captures a
baseline row, so only a CONFORM is worth the developer's time.
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
    """Frame keys already carrying a verdict in the ruling record.

    Parsed out of the committed Markdown rather than kept as a second list, so the record stays the
    ONE place a verdict lives. The record escapes the pipes in a frame key for the Markdown table
    (``81904451\\|0\\|decision\\|24``), so they are unescaped back here."""
    if not path or not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    return {m.replace("\\|", "|") for m in re.findall(r"`(\d+\\\|\d+\\\|\w+\\\|\d+)`", text)}


def intent_of(correction) -> str:
    """What the developer said they wanted, from WHEREVER this Correction's scope records it.

    A decision-scope record carries it in ``rationale``. A **turn**-scope record carries it in
    ``turn_plan`` (``intended_line`` + ``expected_end_board``) and its ``rationale`` is empty — so
    reading only ``rationale`` reports a turn Correction as having no stated intent at all.

    Measured 2026-08-02 (Issue #262): `86090164|1|turn|2` reached the developer's triage list as
    *"no rationale is recorded"* and got flagged as the one frame that could not be triaged from the
    corpus. It has a turn plan — *"Attach energy to our active dreepy, retreat to Budew, DO NOT play
    Lillie's this turn, because we want to evolve our Dunsparce next turn"* — which decides the frame
    outright. The blank was this generator's, not the corpus's, and a blank that reads as "the human
    never said" is the worst possible failure for a sheet whose entire job is to relay what they
    said."""
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
