"""submit_agent — the Submission lifecycle CLI (ADR-0019).

    python tools/submit_agent.py build  <agent> [--label L]   # package + record to the build ledger
    python tools/submit_agent.py submit [N] [--allow-dirty] [--skip-check]  # upload build N
    python tools/submit_agent.py collect <id> --replays DIR   # record performance from replays
    python tools/submit_agent.py dashboard                    # render the over-time view

`build` packages an agent and logs it locally (no upload). `submit` uploads a *prior* build's
exact zip — gated: refuses a dirty build, runs the Agent Check. See tools/submit/CONTEXT.md.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from submit.build import DEFAULT_BUILDS, DEFAULT_HISTORY, DEFAULT_OUT, build  # noqa: E402
from submit.submit import submit  # noqa: E402


def _build_id(v: str) -> int:
    """A build number for `submit` — with a hint when someone passes an agent name out of habit."""
    try:
        return int(v)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a build number (or omit it for the latest build). To build and submit an "
            f"agent, run `build {v}` first, then `submit`.")


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
    s.add_argument("build_id", nargs="?", type=_build_id, help="which build to submit (default: most recent)")
    s.add_argument("--allow-dirty", action="store_true", help="permit submitting a dirty build")
    s.add_argument("--skip-check", action="store_true",
                   help="upload with no deployability check at all (no mirror match, no "
                        "structure check) — a broken artifact will not be caught locally")
    s.add_argument("--out", default=str(DEFAULT_OUT))
    s.add_argument("--builds", default=str(DEFAULT_BUILDS))
    s.add_argument("--history", default=str(DEFAULT_HISTORY))
    s.add_argument("--agents-root", default=None)

    c = sub.add_parser("collect", help="download a submitted build's replays + score → performance.jsonl")
    c.add_argument("submission_id", nargs="?", type=int, help="which submission (default: latest submitted)")
    c.add_argument("--max-replays", type=int, default=20, help="max episodes to download")
    c.add_argument("--history", default=str(DEFAULT_HISTORY))

    d = sub.add_parser("dashboard", help="render the over-time state-vs-performance dashboard")
    d.add_argument("--out", default=str(REPO / "data" / "dashboard.html"))
    args = ap.parse_args(argv)

    if args.cmd == "dashboard":
        from submit.dashboard import build_dashboard
        print(f"dashboard -> {build_dashboard(out=args.out)}")
    elif args.cmd == "collect":
        from submit.collect import collect_submission
        sample = collect_submission(args.submission_id, history=args.history,
                                    max_replays=args.max_replays)
        print(f"collected #{sample['submission_id']}: {sample['record']} score={sample['public_score']}")
    elif args.cmd == "build":
        row = build(Path(args.agent).name, out=args.out, builds=args.builds,
                    agents_root=args.agents_root, submission_id=args.submission_id, label=args.label)
        print(f"built #{row['submission_id']} -> {row['artifact']}.zip")
    else:  # submit
        row = submit(args.build_id, out=args.out, builds=args.builds, history=args.history,
                     agents_root=args.agents_root, allow_dirty=args.allow_dirty,
                     skip_check=args.skip_check)
        print(f"submitted #{row['submission_id']}: {row['message']}")
    return 0


def cli() -> int:
    """Render expected failures concisely; retain opt-in tracebacks for development."""
    try:
        return main()
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(f"ERROR: {exc.code}", file=sys.stderr)
            return 1
        return int(exc.code or 0)
    except KeyboardInterrupt:
        print("ERROR: interrupted; upload was not recorded", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI boundary owns presentation
        if os.environ.get("SUBMIT_AGENT_DEBUG") == "1":
            raise
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Set SUBMIT_AGENT_DEBUG=1 to show the full traceback.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
