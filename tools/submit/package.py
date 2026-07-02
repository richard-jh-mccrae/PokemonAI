"""Assemble a self-contained submission directory and zip it (see ADR-0004).

Copies a deck-specific agent (`agents/<name>/`'s `*.py` + `deck.csv` + `tuned.json` when
present) together with the shared `common/` and `cg/` packages (and the compiled
`common/scouting/artifact.json`) into `dist/<name>/`, writes a self-contained `brief.html`
(the embedded decision-steering **Manifest** — provenance, hypotheses, capabilities, deck;
see ADR-0019), then zips it to
`dist/<name>_<YYYYMMDD>_<githash>.zip` — the staged dir *is* the exact shipped bundle,
and the stamped zip names the deploy artifact by build date + commit (`-dirty` suffix when the
work tree has uncommitted changes). `--no-stamp` falls back to a stable `dist/<name>.zip`.

Usage:
    python tools/submit/package.py <name> [--out dist] [--no-stamp]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MS = REPO / "src"
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.md", "docs")  # ship code, not docs


def _git_hash(repo: Path) -> str:
    """Short HEAD hash, `-dirty` when the work tree is modified; `nogit` if git is unavailable."""
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        short = git("rev-parse", "--short", "HEAD")
        return f"{short}-dirty" if git("status", "--porcelain") else short
    except (OSError, subprocess.SubprocessError):
        return "nogit"


def artifact_stem(name: str, *, when: datetime | None = None, git_hash: str | None = None,
                  repo: Path = REPO) -> str:
    """Deploy-artifact basename `<name>_<YYYYMMDD>_<githash>` (build date + commit).

    `when` / `git_hash` default to now / `HEAD`; pass them to stamp deterministically (tests).
    """
    when = when or datetime.now()
    git_hash = _git_hash(repo) if git_hash is None else git_hash
    return f"{name}_{when:%Y%m%d}_{git_hash}"


def package(name: str, dist: Path, *, agents_root: Path | None = None, stamp: bool = True,
            prev_deck: dict | None = None, prev_build_id: int | None = None,
            prev_hyps: dict | None = None) -> Path:
    """Stage `dist/<name>/` and zip it; return the zip path.

    `name` may be a bare agent name or a path to its dir (only the basename is used).
    `agents_root` overrides where the agent dir lives (default `src/agents/`) — e.g. a
    test fixture; the shared `common/` and `cg/` always come from `src/`.
    `stamp` (default) names the zip `<name>_<date>_<githash>.zip`; pass False for a stable
    `<name>.zip`. The staged dir stays `dist/<name>/` either way (scratch, overwritten per build);
    only the zip carries the stamp, so a build history accumulates while the stage does not.
    Ships `tuned.json` when present and always writes a self-contained `brief.html` (the
    embedded Manifest, ADR-0019) at the bundle root. `prev_deck`/`prev_build_id` (the previous
    build's deck) drive the brief's highlighted deck-change callout.
    """
    name = Path(name).name or name  # accept a path (e.g. tab-completed) or bare name
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
    if (tuned := agent_dir / "tuned.json").exists():   # machine weight overrides (ADR-0018), if present
        shutil.copy2(tuned, stage / "tuned.json")
    if (tuned_meta := agent_dir / "tuned.meta.json").exists():  # training provenance sidecar (ADR-0019)
        shutil.copy2(tuned_meta, stage / "tuned.meta.json")
    shutil.copytree(MS / "common", stage / "common", ignore=_IGNORE)
    shutil.copytree(MS / "cg", stage / "cg", ignore=_IGNORE)

    when, git_hash = datetime.now(), _git_hash(REPO)  # one stamp for brief and zip name
    from submit.brief import build_manifest, render_brief  # lazy: avoid import cycle
    manifest = build_manifest(stage, when=when, git_hash=git_hash, agent_name=name)
    brief = render_brief(manifest, prev_deck=prev_deck, prev_build_id=prev_build_id, prev_hyps=prev_hyps)
    (stage / "brief.html").write_text(brief, encoding="utf-8")

    stem = artifact_stem(name, when=when, git_hash=git_hash) if stamp else name
    return Path(shutil.make_archive(str(Path(dist) / stem), "zip", root_dir=stage))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name", help="agent directory under src/agents/")
    ap.add_argument("--out", default=str(REPO / "dist"))
    ap.add_argument("--no-stamp", action="store_true",
                    help="name the zip <name>.zip (omit the datetime/githash stamp)")
    args = ap.parse_args()
    zip_path = package(args.name, Path(args.out), stamp=not args.no_stamp)
    print(f"packaged -> {zip_path}")


if __name__ == "__main__":
    main()
