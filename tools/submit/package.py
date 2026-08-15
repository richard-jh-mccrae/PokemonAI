"""Assemble a self-contained submission directory and zip it (see ADR-0004).

Copies a deck-specific declaration together with the shared Bellman runtime, scouting data, and
native engine. Offline diagnostic engines are categorically excluded. It writes a self-contained
manifest brief, then zips the exact staged bundle to
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
import json

REPO = Path(__file__).resolve().parents[2]
MS = REPO / "src"
# Ship code, not docs. `attack_overrides.provenance.json` is documentation wearing a `.json`
# extension — the runtime loads only `attack_overrides.json` (ADR-0108 §1).
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.md", "docs", "engine.py",
                                 "attack_overrides.provenance.json")
FORBIDDEN_KAGGLE_TOKEN = b"cgpy"


def _assert_kaggle_runtime_boundary(stage: Path) -> None:
    """Reject offline-only code by both archive path and content, including generated files."""
    for path in sorted(candidate for candidate in stage.rglob("*") if candidate.is_file()):
        relative = path.relative_to(stage).as_posix()
        if FORBIDDEN_KAGGLE_TOKEN.decode() in relative.lower():
            raise ValueError(f"offline-only path cannot ship to Kaggle: {relative}")
        if FORBIDDEN_KAGGLE_TOKEN in path.read_bytes().lower():
            raise ValueError(f"offline-only reference cannot ship to Kaggle: {relative}")


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
    """Deploy-artifact basename `<name>_<YYYYMMDD>_<githash>`; `when`/`git_hash` exist to stamp
    deterministically in tests."""
    when = when or datetime.now()
    git_hash = _git_hash(repo) if git_hash is None else git_hash
    return f"{name}_{when:%Y%m%d}_{git_hash}"


def package(name: str, dist: Path, *, agents_root: Path | None = None, stamp: bool = True,
            prev_deck: dict | None = None, prev_build_id: int | None = None,
            prev_hyps: dict | None = None, overlay: Path | str | None = None,
            strategy_enabled: bool | None = None) -> Path:
    """Stage `dist/<name>/` and zip it -> the zip path. Only the ZIP carries the stamp, so a build
    history accumulates while the staged dir is scratch. Shared runtime packages always come from
    `src/`."""
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
    shutil.copytree(MS / "common", stage / "common", ignore=_IGNORE)
    shutil.copytree(MS / "cg", stage / "cg", ignore=_IGNORE)

    when, git_hash = datetime.now(), _git_hash(REPO)  # one stamp for brief and zip name
    from submit.brief import build_manifest, render_brief, render_brief_csv  # lazy: avoid import cycle
    pilot_values = None
    if overlay is not None:
        payload = json.loads(Path(overlay).read_text(encoding="utf-8"))
        pilot_values = payload.get("pilot", {})
        if not isinstance(pilot_values, dict):
            raise ValueError("overlay pilot must be an object")
    if strategy_enabled is not None:
        pilot_values = {**(pilot_values or {}),
                        "strategy.focus_enabled": 1.0 if strategy_enabled else 0.0}
    if pilot_values:
        (stage / "runtime_config.json").write_text(
            json.dumps({"pilot": pilot_values}, sort_keys=True), encoding="utf-8")
    manifest = build_manifest(
        stage, when=when, git_hash=git_hash, agent_name=name,
        pilot_values=pilot_values)
    brief = render_brief(manifest, prev_deck=prev_deck, prev_build_id=prev_build_id)
    (stage / "brief.html").write_text(brief, encoding="utf-8")
    (stage / "brief.csv").write_text(render_brief_csv(manifest), encoding="utf-8", newline="")
    _assert_kaggle_runtime_boundary(stage)

    stem = artifact_stem(name, when=when, git_hash=git_hash) if stamp else name
    return Path(shutil.make_archive(str(Path(dist) / stem), "zip", root_dir=stage))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name", help="agent directory under src/agents/")
    ap.add_argument("--out", default=str(REPO / "dist"))
    ap.add_argument("--no-stamp", action="store_true",
                    help="name the zip <name>.zip (omit the datetime/githash stamp)")
    ap.add_argument("--overlay", default=None,
                    help="pilot overlay JSON recorded in the packaged brief")
    ap.add_argument("--strategy", choices=("on", "off"), default=None,
                    help="record the canonical Strategy beam A/B toggle")
    args = ap.parse_args()
    zip_path = package(
        args.name, Path(args.out), stamp=not args.no_stamp, overlay=args.overlay,
        strategy_enabled=None if args.strategy is None else args.strategy == "on")
    print(f"packaged -> {zip_path}")


if __name__ == "__main__":
    main()
