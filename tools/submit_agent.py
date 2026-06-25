"""submit_agent — the Submission lifecycle CLI (ADR-0019).

    python tools/submit_agent.py build  <agent> [--label L]   # package + record to the build ledger
    python tools/submit_agent.py submit [N] [--allow-dirty]   # upload build N (default: latest)
    python tools/submit_agent.py collect <id> --replays DIR   # record performance from replays
    python tools/submit_agent.py dashboard                    # render the over-time view

`build` packages an agent and logs it locally (no upload). `submit` uploads a *prior* build's
exact zip — gated: refuses a dirty build, runs the Agent Check. See tools/submit/CONTEXT.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from submit.build import DEFAULT_BUILDS, DEFAULT_HISTORY, DEFAULT_OUT, build  # noqa: E402
from submit.submit import submit  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Build/submit a Submission (ADR-0019). <agent> is a directory under src/agents/.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python tools/submit_agent.py build  mega_starmie [--label L]\n"
            "  python tools/submit_agent.py submit                 # upload the latest build\n"
            "  python tools/submit_agent.py submit 3 --allow-dirty # upload build #3\n"
            "  python tools/submit_agent.py collect 3 --replays data/replays/\n"
            "  python tools/submit_agent.py dashboard\n"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="package an agent + record it to the build ledger (no upload)")
    b.add_argument("agent", help="agent directory under src/agents/")
    b.add_argument("--label", help="experiment name recorded with the build")
    b.add_argument("--submission-id", type=int, help="override the monotonic id")
    b.add_argument("--out", default=str(DEFAULT_OUT))
    b.add_argument("--builds", default=str(DEFAULT_BUILDS))
    b.add_argument("--agents-root", default=None)

    s = sub.add_parser("submit", help="upload a prior build (default: latest) to the competition")
    s.add_argument("build_id", nargs="?", type=int, help="which build to submit (default: most recent)")
    s.add_argument("--allow-dirty", action="store_true", help="permit submitting a dirty build")
    s.add_argument("--out", default=str(DEFAULT_OUT))
    s.add_argument("--builds", default=str(DEFAULT_BUILDS))
    s.add_argument("--history", default=str(DEFAULT_HISTORY))
    s.add_argument("--agents-root", default=None)

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
    elif args.cmd == "collect":
        from submit.collect import collect, fetch_from_dir, kaggle_score
        sample = collect(args.submission_id, score_fn=kaggle_score,
                         fetch_fn=lambda _ref: fetch_from_dir(args.replays), seat=args.seat)
        print(f"collected #{args.submission_id}: {sample['record']} score={sample['public_score']}")
    elif args.cmd == "build":
        row = build(Path(args.agent).name, out=args.out, builds=args.builds,
                    agents_root=args.agents_root, submission_id=args.submission_id, label=args.label)
        print(f"built #{row['submission_id']} -> {row['artifact']}.zip")
    else:  # submit
        row = submit(args.build_id, out=args.out, builds=args.builds, history=args.history,
                     agents_root=args.agents_root, allow_dirty=args.allow_dirty)
        print(f"submitted #{row['submission_id']}: {row['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
