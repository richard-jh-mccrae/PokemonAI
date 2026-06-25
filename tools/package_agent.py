"""Assemble a self-contained submission directory and zip it (see ADR-0004).

Copies a deck-specific agent (`agents/<name>/`'s `*.py` + `deck.csv`) together with the
shared `common/` and `cg/` packages (and the compiled `common/scouting/artifact.json`)
into `dist/<name>/`, then zips it — the staged dir *is* the exact shipped bundle.

Usage:
    python tools/package_agent.py <name> [--out dist]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MS = REPO / "my_submissions"
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.md", "docs")  # ship code, not docs


def package(name: str, dist: Path, *, agents_root: Path | None = None) -> Path:
    """Stage `dist/<name>/` and zip it; return the zip path.

    `name` may be a bare agent name or a path to its dir (only the basename is used).
    `agents_root` overrides where the agent dir lives (default `my_submissions/agents/`) — e.g. a
    test fixture; the shared `common/` and `cg/` always come from `my_submissions/`.
    """
    name = Path(name).name or name  # accept a path (e.g. tab-completed) or a bare name
    agent_dir = (Path(agents_root) if agents_root else MS / "agents") / name
    if not (agent_dir / "main.py").exists():
        raise SystemExit(f"no agent at {agent_dir}")

    stage = Path(dist) / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    for py in sorted(agent_dir.glob("*.py")):  # main.py + sibling modules (e.g. strategy.py)
        shutil.copy2(py, stage / py.name)
    shutil.copy2(agent_dir / "deck.csv", stage / "deck.csv")
    shutil.copytree(MS / "common", stage / "common", ignore=_IGNORE)
    shutil.copytree(MS / "cg", stage / "cg", ignore=_IGNORE)

    return Path(shutil.make_archive(str(Path(dist) / name), "zip", root_dir=stage))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name", help="agent directory under my_submissions/agents/")
    ap.add_argument("--out", default=str(REPO / "dist"))
    args = ap.parse_args()
    zip_path = package(args.name, Path(args.out))
    print(f"packaged -> {zip_path}")


if __name__ == "__main__":
    main()
