"""Print one frame's complete board state as plain text.

    python tools/train/frame_view.py 82756664-97
    python tools/train/frame_view.py 82756664-97 --brief       # drop card rule text
    python tools/train/frame_view.py 82756664-97 --width 100   # wide terminal
    python tools/train/frame_view.py 82756664-97 --deck-order
    python tools/train/frame_view.py 82756664-97 --replay path/to/replay.json
    python tools/train/frame_view.py --list                # every resolvable frame key
    python tools/train/frame_view.py --list 82756664       # ...in one episode

The read-out is deliberately fixed in shape and section order so two sittings on the same frame are
comparable, and wrapped to a narrow column (38 chars by default) so it reads on a phone. See
`train.blunder.frame_view` for what each section means, where the snapshot comes from, and why the
per-turn flags are labelled with the *turn player* rather than "you".
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

from train.blunder.frame_view import (  # noqa: E402
    WIDTH, available_frames, dump, parse_frame_key,
)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(
        prog="frame_view",
        description="Print one frame's complete board state as a plain-text list.")
    ap.add_argument("key", nargs="?",
                    help="frame key <episode>-<frame>, e.g. 82756664-97")
    ap.add_argument("--replay", type=Path, default=None,
                    help="read the frame from this replay film instead of searching "
                         "(lets ANY frame resolve, not only tagged ones)")
    ap.add_argument("--deck-order", action="store_true",
                    help="also print the deck in its recorded order (engine-internal — not a "
                         "legitimate top-of-deck read)")
    ap.add_argument("--width", type=int, default=WIDTH, metavar="N",
                    help=f"column width (default {WIDTH}, sized for reading on a phone)")
    ap.add_argument("--brief", action="store_true",
                    help="drop attack and ability rule text — the bulk of the length. Every zone, "
                         "count and flag is still printed")
    ap.add_argument("--list", nargs="?", const="", metavar="EPISODE",
                    help="list every frame key resolvable from the committed stores, optionally "
                         "just one episode's")
    args = ap.parse_args(argv)

    if args.list is not None:
        episode = int(args.list) if args.list else None
        keys = available_frames(episode)
        if not keys:
            print("no frame keys found in the committed stores")
            return 1
        for key in keys:
            print(key)
        return 0

    if not args.key:
        ap.error("a frame key is required, e.g. 82756664-97 (or use --list)")

    try:
        parse_frame_key(args.key)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        print(dump(args.key, deck_order=args.deck_order, replay_path=args.replay,
                   width=args.width, effects=not args.brief), end="")
    except LookupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        try:
            episode, _ = parse_frame_key(args.key)
            same = available_frames(episode)
            if same:
                print(f"frames that DO resolve for episode {episode}: {', '.join(same)}",
                      file=sys.stderr)
        except ValueError:
            pass
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
