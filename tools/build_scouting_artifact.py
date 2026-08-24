"""Compile the shipped Scouting artifact from the meta store.

Reads `data/meta/meta.db` + `cards.json` and writes
`src/common/scouting/artifact.json`. Native-lib-free. Run after the daily
fetch; re-bundle/submit deliberately.

Usage:
    python tools/build_scouting_artifact.py [--out PATH] [--half-life 21] [--min-episodes 50]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # makes `meta_tracker` importable

from meta_tracker.cards import load_cards            # noqa: E402
from meta_tracker.compile_scouting import compile_artifact  # noqa: E402
from meta_tracker.store import connect, load_episodes      # noqa: E402

DEFAULT_OUT = (Path(__file__).resolve().parents[1]
               / "src" / "common" / "scouting" / "artifact.json")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--half-life", type=float, default=21.0)
    ap.add_argument("--min-episodes", type=int, default=50)
    args = ap.parse_args()

    episodes = load_episodes(connect())
    now = datetime.now(timezone.utc).isoformat()
    artifact = compile_artifact(episodes, load_cards(), now=now,
                                half_life_days=args.half_life, min_episodes=args.min_episodes)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(artifact['dossiers'])} dossiers from "
          f"{artifact['meta']['episode_count']} episodes -> {out}")


if __name__ == "__main__":
    main()
