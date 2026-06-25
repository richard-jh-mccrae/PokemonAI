"""submit_agent — the Submission lifecycle CLI (ADR-0019).

    python tools/submit_agent.py build  <agent> [--label L] [--submission-id N]
    python tools/submit_agent.py submit <agent> [--label L] [--allow-dirty]

`build` is safe and silent (packages + records). `submit` is gated: it refuses a `-dirty` tree,
runs the Agent Check, then uploads to the Simulation competition. See tools/submit/CONTEXT.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from submit.build import DEFAULT_HISTORY, DEFAULT_OUT, build  # noqa: E402
from submit.submit import submit  # noqa: E402


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("agent", help="agent directory under src/agents/")
    p.add_argument("--label", help="experiment name recorded with the submission")
    p.add_argument("--submission-id", type=int, help="override the monotonic id")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--history", default=str(DEFAULT_HISTORY))
    p.add_argument("--agents-root", default=None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Build/submit a Submission (ADR-0019). <agent> is a directory under src/agents/.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python tools/submit_agent.py build   mega_starmie [--label L] [--submission-id N]\n"
            "  python tools/submit_agent.py submit  mega_starmie [--label L] [--allow-dirty]\n"
            "  python tools/submit_agent.py collect 1 --replays data/replays/\n"
            "  python tools/submit_agent.py dashboard\n"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    _common(sub.add_parser("build", help="package + record (never uploads)"))
    s = sub.add_parser("submit", help="gated upload to the Simulation competition")
    _common(s)
    s.add_argument("--allow-dirty", action="store_true", help="permit a dirty work tree (discouraged)")
    c = sub.add_parser("collect", help="record a submission's performance from its replays + score")
    c.add_argument("submission_id", type=int)
    c.add_argument("--replays", required=True, help="dir of <stem>.replay.json + <stem>.log.json pairs")
    c.add_argument("--seat", type=int, default=0)
    d = sub.add_parser("dashboard", help="render the over-time state-vs-performance dashboard")
    d.add_argument("--out", default=str(REPO / "data" / "dashboard.html"))
    args = ap.parse_args(argv)

    if args.cmd == "dashboard":
        from submit.dashboard import build_dashboard
        print(f"dashboard -> {build_dashboard(out=args.out)}")
        return 0
    if args.cmd == "collect":
        from submit.collect import collect, fetch_from_dir, kaggle_score
        sample = collect(args.submission_id, score_fn=kaggle_score,
                         fetch_fn=lambda _ref: fetch_from_dir(args.replays), seat=args.seat)
        print(f"collected #{args.submission_id}: {sample['record']} score={sample['public_score']}")
        return 0

    kw = dict(out=args.out, history=args.history, agents_root=args.agents_root,
              submission_id=args.submission_id, label=args.label)
    if args.cmd == "build":
        row = build(args.agent, **kw)
        print(f"built #{row['submission_id']} -> {row['artifact']}.zip")
    else:
        row = submit(args.agent, allow_dirty=args.allow_dirty, **kw)
        print(f"submitted #{row['submission_id']}: {row['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
