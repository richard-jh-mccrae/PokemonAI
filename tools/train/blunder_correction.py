"""blunder_correction -- open a replay (or a directory of them) in the tagging shell.

    python tools/train/blunder_correction.py <replay.json|.gz | dir/> --team <ourTeam> --agent mega_starmie

A single Replay file tags one Episode; a directory (e.g. data/replays/<build_stem>/) is batch
mode -- the shell's ◀/▶ steps across its Replays in episode-id order without leaving the tool.
Serves the local tagging shell (official viewer + side panel) and appends each tagged blunder to
the Correction log. Turn-plan tags can execute the full alternate line through cgpy, prove safe
action reordering, and persist a machine-gradeable proof. See docs/blunder-inspector.md.
"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

from train.blunder.batch import discover_replays  # noqa: E402
from train.blunder.provenance import build_identity  # noqa: E402
from train.blunder.shell import serve  # noqa: E402
from train.blunder.store import DEFAULT_PATH  # noqa: E402

_VIEWER_DIST = Path(__file__).resolve().parent / "blunder" / "viewer" / "dist"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tag blunders in a replay (or a directory) -> Corrections")
    ap.add_argument("replay", help="a cabt replay (.json/.json.gz) OR a directory of them (batch)")
    ap.add_argument("--team", help="our Kaggle team name (to auto-detect our seat)")
    ap.add_argument("--agent", default="",
                    help="deck build name, e.g. mega_starmie (auto-detected from the replay's "
                         "build folder when omitted)")
    ap.add_argument("--source", default="own", choices=["own", "peer"])
    ap.add_argument("--submission-id", type=int, default=None)
    ap.add_argument("--agent-version", default=None)
    ap.add_argument("--store", default=str(DEFAULT_PATH), help="Correction log path (JSONL)")
    ap.add_argument("--viewer-dir", default=str(_VIEWER_DIST))
    ap.add_argument("--port", type=int, default=8077)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    replays = discover_replays(args.replay)   # one file, or every Replay in a dir (batch)
    if not replays:
        raise SystemExit(f"no replays found at {args.replay}")
    detected = build_identity(replays[0])["agent"]   # from build-folder stem (own tags auto-fill)
    print(f"blunder_correction: {len(replays)} replay(s) from {args.replay}")
    print(f"  agent for own blunders: {args.agent or detected or '(unknown — pass --agent)'}"
          + ("" if args.agent else "  [auto-detected]" if detected else ""))
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}/")).start()
    serve(
        replays, store_path=args.store, agent=args.agent, source=args.source,
        our_team=args.team, submission_id=args.submission_id,
        agent_version=args.agent_version,
        viewer_dir=args.viewer_dir, port=args.port,
    )


if __name__ == "__main__":
    main()
