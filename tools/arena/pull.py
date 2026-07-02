"""Pull PvC replays off the Arena host into this repo (the SSH pull, ADR-0033).

Usage:
    python tools/arena/pull.py rich@workbox /srv/PokemonAI

Copies data/replays/PvC/*.json from the remote repo into the local
data/replays/PvC/ (replays are gitignored, so git never carries them). Plain
scp — present on Windows and Linux alike.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_LOCAL_PVC = Path(__file__).resolve().parents[2] / "data" / "replays" / "PvC"


def build_command(host: str, remote_repo: str, *, dest: Path | None = None) -> list[str]:
    dest = Path(dest) if dest else _LOCAL_PVC
    dest.mkdir(parents=True, exist_ok=True)
    remote = f"{host}:{remote_repo.rstrip('/')}/data/replays/PvC/*.json"
    return ["scp", remote, str(dest)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("host", help="ssh destination, e.g. rich@workbox")
    ap.add_argument("remote_repo", help="repo root on the host, e.g. /srv/PokemonAI")
    args = ap.parse_args()
    cmd = build_command(args.host, args.remote_repo)
    print(" ".join(cmd))
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
