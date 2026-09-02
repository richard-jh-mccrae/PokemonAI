"""Stable source, agent, and discovery identities shared by simulation runs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def agent_identity(agents_root: Path, name: str) -> dict:
    directory = Path(agents_root) / name
    files = sorted(path for path in directory.rglob("*") if path.is_file()
                   and "__pycache__" not in path.parts and path.suffix != ".pyc")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(directory).as_posix().encode()
        body = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big") + relative)
        digest.update(len(body).to_bytes(8, "big") + body)
    strategy = directory / "strategy.py"
    overlay_sha256 = None
    if strategy.is_file():
        declared = runpy.run_path(str(strategy)).get("STRATEGY")
        if declared is not None:
            overlay = dict(declared.ledger_overlay)
            overlay_sha256 = hashlib.sha256(json.dumps(
                overlay, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "deck_sha256": _sha256(directory / "deck.csv"),
        "strategy_sha256": _sha256(strategy) if strategy.is_file() else None,
        "ledger_overlay_sha256": overlay_sha256,
        "agent_tree_sha256": digest.hexdigest(),
    }


def git_source_identity(repo: Path, *, allow_dirty: bool, exclude_paths=()) -> dict:
    repo = Path(repo).resolve()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    excluded = []
    for value in map(Path, exclude_paths):
        try:
            relative = value.resolve().relative_to(repo)
        except ValueError:
            continue
        if relative == Path("."):
            raise ValueError("artifact exclusion cannot cover the repository")
        if value.resolve().is_dir():
            tracked = subprocess.check_output(
                ["git", "ls-files", "--", relative.as_posix()], cwd=repo, text=True)
            if tracked.strip():
                raise ValueError("artifact exclusion directory contains tracked source")
        excluded.append(relative.as_posix())
    diff_args = ["git", "diff", "--binary", "HEAD", "--", "."]
    diff_args.extend(f":(exclude){value}" for value in excluded)
    diff = subprocess.check_output(diff_args, cwd=repo)
    untracked_raw = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=repo)
    untracked = []
    for raw in sorted(value for value in untracked_raw.split(b"\0") if value):
        relative = Path(os.fsdecode(raw))
        if any(relative == Path(root) or Path(root) in relative.parents for root in excluded):
            continue
        untracked.append((raw, repo / relative))
    dirty = bool(diff or untracked)
    if dirty and not allow_dirty:
        raise ValueError("working tree is dirty; commit changes or pass --allow-dirty")
    identity = {"commit": commit, "dirty": dirty}
    if dirty:
        digest = hashlib.sha256(diff)
        for raw, path in untracked:
            body = path.read_bytes()
            digest.update(len(raw).to_bytes(4, "big") + raw)
            digest.update(len(body).to_bytes(8, "big") + body)
        identity["dirty_sha256"] = digest.hexdigest()
    return identity


def discover_agents(root: Path) -> tuple[str, ...]:
    return tuple(sorted(path.name for path in Path(root).iterdir()
                        if (path / "main.py").is_file() and (path / "deck.csv").is_file()))


def discover_opponents(root: Path, focal: str) -> tuple[str, ...]:
    return tuple(name for name in discover_agents(root) if name != focal)
