"""Agent Check: gated verification of one agent before submission.

contents -> legality -> playability -> deployability, short-circuiting at the first
failure. `cg` and `kaggle_environments` are imported lazily inside the stages that need
them, so contents/legality stay dependency-light. See ADR-0010.

Usage:
    python tools/sim/check_agent.py <name> [--matches 5] [--no-deployability]
    python tools/sim/check_agent.py slowking --matches 2 --no-deployability
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import logging
import os
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MS = REPO / "src"

# Kaggle caps submission archive at 197.7 MiB.
MAX_SUBMISSION_MIB = 197.7
MAX_SUBMISSION_BYTES = int(MAX_SUBMISSION_MIB * 1024 * 1024)


@dataclass
class StageResult:
    ok: bool
    stage: str
    detail: str = ""

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class Report:
    name: str
    stages: list

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.stages)

    @property
    def failed_stage(self):
        for s in self.stages:
            if not s.ok:
                return s.stage
        return None


def check_contents(agent_dir: Path, required=("main.py", "deck.csv")) -> StageResult:
    """Required files/dirs are present (source passes the default; the Bundle passes more)."""
    agent_dir = Path(agent_dir)
    missing = [f for f in required if not (agent_dir / f).exists()]
    if missing:
        return StageResult(False, "contents", f"missing: {', '.join(missing)}")
    return StageResult(True, "contents")


def _read_deck(deck_path: Path) -> list[int]:
    lines = [ln for ln in Path(deck_path).read_text().splitlines() if ln.strip()]
    return [int(x) for x in lines]


# Engine deck-legality codes (cg StartData.errorType); see ADR-0010
_DECK_ERRORS = {
    1: "invalid card ID in deck",
    2: "more than 4 cards share a name (excluding basic Energy)",
    3: "no Basic Pokémon in deck",
    4: "more than one ACE SPEC card",
}


def check_legality(deck_path: Path) -> StageResult:
    """Structural pre-check (exactly 60 integer rows), then the engine's verdict."""
    try:
        deck = _read_deck(deck_path)
    except (OSError, ValueError) as e:
        return StageResult(False, "legality", f"unreadable deck.csv: {e}")
    if len(deck) != 60:
        return StageResult(False, "legality", f"expected 60 integer rows, got {len(deck)}")
    from cg.game import battle_finish, battle_start  # lazy: loads native engine

    _, start = battle_start(deck, list(deck))
    if start.errorPlayer >= 0:
        detail = _DECK_ERRORS.get(start.errorType, f"engine deck error {start.errorType}")
        return StageResult(False, "legality", detail)
    battle_finish()
    return StageResult(True, "legality")


@contextlib.contextmanager
def _syspath(roots):
    added = [str(Path(r)) for r in roots]
    sys.path[:0] = added
    try:
        yield
    finally:
        for p in added:
            if p in sys.path:
                sys.path.remove(p)


@contextlib.contextmanager
def _chdir(target):
    old = os.getcwd()
    os.chdir(target)
    try:
        yield
    finally:
        os.chdir(old)


def _load_agent(agent_dir: Path, name: str):
    """Load `agent_dir/main.py` as a fresh module so each seat owns its globals."""
    spec = importlib.util.spec_from_file_location(name, Path(agent_dir) / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


@contextlib.contextmanager
def _suppressed_output():
    """Silence stdout+stderr at the OS fd level — catches native (C-extension) writes too."""
    sys.stdout.flush()
    sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(1), os.dup(2)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    try:
        yield
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for fd in (devnull, *saved):
            os.close(fd)


def _import_make():
    """Import kaggle_environments.make, muting its env discovery. THREE distinct noise sources, each
    needing its own mechanism: third-party logging, a native stderr fd dump, and Python warnings."""
    prev_disable = logging.root.manager.disable
    # LiteLLM registers models during this import.  Some upstream model IDs are absent from its
    # cost table, producing harmless WARNING records and then handler errors on some installs.
    # Suppress only import-time logging; restore the caller's setting immediately afterwards.
    logging.disable(logging.WARNING)
    try:
        with _suppressed_output(), warnings.catch_warnings():  # fd-level: native open_spiel stderr dump
            warnings.simplefilter("ignore")  # + ke's import-time warnings (pydantic Field deprecations, …)
            from kaggle_environments import make
    finally:
        logging.disable(prev_disable)
        klog = logging.getLogger("kaggle_environments")  # make it inert so nothing chatters/errors later
        klog.handlers[:] = [logging.NullHandler()]
        klog.setLevel(logging.WARNING)
        klog.propagate = False
    return make


def _run_match(agent_dir: Path, syspath_roots):
    """One self-play cabt match; returns (statuses, env)."""
    make = _import_make()  # lazy + quiet: heavy dependency

    # agent_dir first so agent's own sibling modules (e.g. strategy.py) resolve, as on grader
    with _syspath([agent_dir, *syspath_roots]), _chdir(agent_dir):
        seats = [_load_agent(agent_dir, f"_seat{i}") for i in range(2)]
        env = make("cabt")  # debug=False so env records agent errors as status=ERROR
        env.run(seats)
    return [s["status"] for s in env.state], env


def _save_replay(env, reports_dir: Path, label: str, stage: str) -> Path:
    """Save a failed match's replay (JSON always; HTML when the env renders one)."""
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{label}-{stage}-fail"
    json_path = reports_dir / f"{stem}.json"
    json_path.write_text(json.dumps(env.toJSON()), encoding="utf-8")
    try:
        html = env.render(mode="html")
    except Exception:
        html = ""
    if html:
        (reports_dir / f"{stem}.html").write_text(html, encoding="utf-8")
    return json_path


def check_playability(
    agent_dir: Path, syspath_roots, matches: int = 5, reports_dir=None
) -> StageResult:
    """Agent plays itself `matches` times; every seat must finish DONE. The first non-DONE seat
    optionally saves a replay to `reports_dir` for triage."""
    agent_dir = Path(agent_dir)
    for i in range(matches):
        statuses, env = _run_match(agent_dir, syspath_roots)
        if any(s != "DONE" for s in statuses):
            detail = f"match {i}: statuses={statuses}"
            if reports_dir is not None:
                saved = _save_replay(env, reports_dir, agent_dir.name, "playability")
                detail += f"; replay -> {saved}"
            return StageResult(False, "playability", detail)
    return StageResult(True, "playability", f"{matches} matches clean")


def _run_bundle(extracted: Path, reports_dir=None, label: str = "bundle"):
    """Run the extracted Bundle in a clean-room subprocess; return (rc, output, replay)."""
    import subprocess

    runner = Path(__file__).with_name("_run_bundle.py")
    args = [sys.executable, str(runner)]
    replay = None
    if reports_dir is not None:
        Path(reports_dir).mkdir(parents=True, exist_ok=True)
        replay = Path(reports_dir) / f"{label}-deployability-fail.json"
        args.append(str(replay))
    proc = subprocess.run(args, cwd=str(extracted), capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip(), replay


def check_deployability(name: str, work_dir: Path, reports_dir=None, *, agents_root=None) -> StageResult:
    """Package the agent, extract it, verify the Bundle's contents, and run it once."""
    import zipfile

    from submit.package import package  # lazy; tools/ is on sys.path

    work_dir = Path(work_dir)
    zip_path = package(name, work_dir / "dist", agents_root=agents_root)

    size = zip_path.stat().st_size  # archive is what Kaggle receives
    if size > MAX_SUBMISSION_BYTES:
        return StageResult(
            False, "deployability",
            f"bundle {size / 1024 / 1024:.1f} MiB exceeds {MAX_SUBMISSION_MIB} MiB cap",
        )

    extracted = work_dir / "extracted"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extracted)

    contents = check_contents(extracted, required=("main.py", "deck.csv", "cg", "common"))
    if not contents.ok:
        return StageResult(False, "deployability", f"bundle {contents.detail}")

    rc, output, replay = _run_bundle(extracted, reports_dir, name)
    if rc != 0:
        detail = f"bundle match failed: {output}"
        if replay and replay.exists():
            detail += f"; replay -> {replay}"
        return StageResult(False, "deployability", detail)
    return StageResult(True, "deployability", "packaged, extracted, and ran clean")


def _agent_name(raw: str) -> str:
    """Accept a bare agent name or a path to its dir (either separator); return the bare name."""
    # Normalize Windows-style backslashes first: on Linux '\' is valid filename char, not a
    # separator, so Path(r"a\b\c").name would return whole string. Works on both OSes.
    return Path(str(raw).replace("\\", "/")).name or str(raw)


def check_agent(
    name: str, *, agents_root=None, matches: int = 5, reports_dir=None, deployability: bool = True
) -> Report:
    """Run the gated Agent Check for `name`, stopping at the first failed stage."""
    agents_root = Path(agents_root) if agents_root else MS / "agents"
    agent_dir = agents_root / name
    stages: list[StageResult] = []

    stages.append(check_contents(agent_dir))
    if not stages[-1].ok:
        return Report(name, stages)

    stages.append(check_legality(agent_dir / "deck.csv"))
    if not stages[-1].ok:
        return Report(name, stages)

    stages.append(
        check_playability(agent_dir, [agents_root.parent], matches=matches, reports_dir=reports_dir)
    )
    if not stages[-1].ok:
        return Report(name, stages)

    if deployability:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            stages.append(check_deployability(name, work_dir=tmp, reports_dir=reports_dir,
                                              agents_root=agents_root))
    return Report(name, stages)


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Gated Agent Check (see tools/sim/CONTEXT.md, ADR-0010).")
    ap.add_argument("name", help="agent directory under src/agents/")
    ap.add_argument("--matches", type=int, default=5, help="playability self-play matches")
    ap.add_argument("--no-deployability", action="store_true", help="skip the package/extract/run stage")
    ap.add_argument("--reports", default=str(REPO / "reports"), help="dir for failure replays")
    ap.add_argument("--agents-root", default=None,
                    help="dir holding agent subdirs (default src/agents)")
    args = ap.parse_args(argv)
    name = _agent_name(args.name)  # accept a path (e.g. tab-completed) or a bare name

    sys.path.insert(0, str(REPO / "tools"))  # so check_deployability can import submit.package
    sys.path.insert(0, str(MS))  # so in-process stages can import cg / common
    report = check_agent(
        name,
        agents_root=args.agents_root,
        matches=args.matches,
        reports_dir=args.reports,
        deployability=not args.no_deployability,
    )
    for s in report.stages:
        print(f"[{'PASS' if s.ok else 'FAIL'}] {s.stage}: {s.detail}")
    if report.ok:
        print(f"OK: {name} passed all checks")
        return 0
    print(f"FAILED at stage: {report.failed_stage}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
