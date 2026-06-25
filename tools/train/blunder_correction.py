"""blunder_correction -- open a replay in the tagging shell and author Corrections.

    python tools/train/blunder_correction.py <replay.json|.gz> --team <ourTeam> --agent mega_starmie

Loads a cabt replay, serves the local tagging shell (official viewer + side panel),
and appends each tagged blunder to the Correction log. See docs/blunder-inspector.md.
"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "my_submissions"))

from meta_tracker.parse import load_replay  # noqa: E402
from train.blunder.shell import serve  # noqa: E402
from train.blunder.store import DEFAULT_PATH  # noqa: E402

_VIEWER_DIST = Path(__file__).resolve().parent / "blunder" / "viewer" / "dist"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tag blunders in a replay -> Corrections")
    ap.add_argument("replay", help="path to a cabt replay (.json or .json.gz)")
    ap.add_argument("--team", help="our Kaggle team name (to auto-detect our seat)")
    ap.add_argument("--agent", default="", help="deck build name, e.g. mega_starmie")
    ap.add_argument("--source", default="own", choices=["own", "peer"])
    ap.add_argument("--submission-id", type=int, default=None)
    ap.add_argument("--agent-version", default=None)
    ap.add_argument("--store", default=str(DEFAULT_PATH), help="Correction log path (JSONL)")
    ap.add_argument("--viewer-dir", default=str(_VIEWER_DIST))
    ap.add_argument("--port", type=int, default=8077)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    replay = load_replay(args.replay)
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}/")).start()
    serve(
        replay, store_path=args.store, agent=args.agent, source=args.source,
        our_team=args.team, submission_id=args.submission_id,
        agent_version=args.agent_version, viewer_dir=args.viewer_dir, port=args.port,
    )


if __name__ == "__main__":
    main()
