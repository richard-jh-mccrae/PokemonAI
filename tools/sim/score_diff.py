"""score_diff — the behavior-neutrality gate for Pilot/Strategy refactors.

Replays a corpus of recorded decision states (``obs``) through the CURRENT build's Pilot and
compares per-frame decisions against a saved capture of a reference build. Two modes:

- ``scores`` — per-option scores AND the chosen option must be identical (score-equality; the
  fold-into-general gate). Fired rule IDS are deliberately not compared — a fold renames rules
  without moving scores.
- ``choice`` — only the chosen option must be identical (decision-equality; the gate for
  near-neutral vocabulary fixes, e.g. a Function-Tag addition).

Corpus sources (both offline, engine-backed via the committed cg binaries):
- Corrections (``data/corrections/**/corrections.jsonl``) — every record carries the live ``obs``.
- Replay films (``env.toJSON()`` files, e.g. ``tools/sim/selfplay.py`` output) — every decision
  frame whose next frame recorded ``obs`` + ``selected``.

    python tools/sim/score_diff.py capture --agent mega_starmie --out data/score_diff/base.json
    python tools/sim/score_diff.py diff    --agent mega_starmie --baseline data/score_diff/base.json
    # both accept: --corrections data/corrections --replays data/replays/selfplay/<stem> [--mode]

Exit code 0 = no divergence. Any divergence prints per-frame detail (key, chosen, first score
delta) and exits 1.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.telemetry import to_record  # noqa: E402


def slim(record: dict) -> dict:
    """The comparable projection of a telemetry record: chosen + per-option (index, score)."""
    return {"chosen": list(record.get("chosen") or []),
            "opts": [(o["i"], o["score"]) for o in record.get("opts") or []]}


def diff_records(before: dict | None, after: dict | None, *, mode: str = "scores") -> list[str]:
    """Divergences between two per-frame records ([] = equal under ``mode``)."""
    if (before is None) != (after is None):
        return ["record missing on one side"]
    if before is None:
        return []
    b, a = slim(before), slim(after)
    out = []
    if b["chosen"] != a["chosen"]:
        out.append(f"chosen {b['chosen']} -> {a['chosen']}")
    if mode == "scores" and b["opts"] != a["opts"]:
        moved = [(i, s0, s1) for (i, s0), (_, s1) in zip(b["opts"], a["opts"]) if s0 != s1] \
            if len(b["opts"]) == len(a["opts"]) else None
        out.append(f"scores {b['opts']} -> {a['opts']}" if moved is None
                   else f"score moved at opts {moved}")
    return out


def corrections_corpus(root: Path | str):
    """Yield ``("corr:<episode>:<frame>", obs)`` for every committed Correction carrying obs."""
    # The store owns both HOW a record is constructed and WHERE the logs live (ADR-0087
    # decision 1). This already constructed correctly; asking for the file list too removes the last
    # local copy of the layout.
    from train.blunder.store import jsonl_files, load_corrections
    for f in jsonl_files(root):
        for c in load_corrections(f):
            if c.obs is not None:
                yield f"corr:{c.episode_id}:{(c.decision or {}).get('frame')}", c.obs


def replay_corpus(replays):
    """Yield ``("replay:<episode>:<frame>", obs)`` for every decision frame of loaded replays.

    A decision prompted at film frame ``i`` records its ``selected`` and the aligned agent ``obs``
    one frame later (``film[i+1]``) — same alignment as the blunder pipeline (backfill_obs)."""
    from train.blunder.decisions import _film
    for replay in replays:
        episode = (replay.get("info") or {}).get("EpisodeId")
        film = _film(replay)
        for i, frame in enumerate(film):
            select = frame.get("select")
            if not isinstance(select, dict) or not select.get("option"):
                continue
            nxt = film[i + 1] if i + 1 < len(film) else None
            if not nxt or nxt.get("selected") is None or nxt.get("obs") is None:
                continue
            yield f"replay:{episode}:{i}", nxt["obs"]


def capture_corpus(pilot, corpus) -> dict:
    """Re-derive the decision at every corpus state: ``{key: telemetry record}``."""
    out = {}
    for key, obs in corpus:
        out[key] = to_record(pilot.explain(obs))
    return out


def _load_replays(dirs):
    from meta_tracker.parse import load_replay
    for d in dirs:
        for p in sorted(Path(d).rglob("*.json")) + sorted(Path(d).rglob("*.json.gz")):
            yield load_replay(p)


def _corpus(args):
    yield from corrections_corpus(args.corrections)
    if args.replays:
        yield from replay_corpus(_load_replays(args.replays))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("capture", "diff"):
        p = sub.add_parser(name)
        p.add_argument("--agent", default="mega_starmie")
        p.add_argument("--corrections", default=str(REPO / "data" / "corrections"))
        p.add_argument("--replays", nargs="*", default=[],
                       help="replay dirs (env.toJSON films, e.g. a selfplay corpus)")
    sub.choices["capture"].add_argument("--out", required=True)
    sub.choices["diff"].add_argument("--baseline", required=True)
    sub.choices["diff"].add_argument("--mode", choices=("scores", "choice"), default="scores")
    args = ap.parse_args(argv)

    from train.tune import _build_pilot
    pilot, _ = _build_pilot(args.agent)
    records = capture_corpus(pilot, _corpus(args))

    if args.cmd == "capture":
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(records), encoding="utf-8")
        print(f"captured {len(records)} frames -> {out}")
        return 0

    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    divergent = 0
    for key in sorted(set(baseline) | set(records)):
        problems = diff_records(baseline.get(key), records.get(key), mode=args.mode)
        if problems:
            divergent += 1
            print(f"DIVERGED {key}: {'; '.join(problems)}")
    print(f"{len(records)} frames vs {len(baseline)} baseline: "
          f"{divergent} divergent ({args.mode} mode)")
    return 1 if divergent else 0


if __name__ == "__main__":
    raise SystemExit(main())
