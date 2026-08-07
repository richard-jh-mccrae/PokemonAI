"""A test that scans source BY PATH must keep scanning all of it when the code moves.

Several tests read `src/**.py` as text or AST and assert over what they find. Each already carries a
positive control, so a scan that finds *nothing* fails loudly — that is not the gap. The gap is
narrower and opens only during a refactor: every one names a **hard-coded module list** (`MODULES`,
`CONSUMERS`, `PILOT_SRC`), while `Pilot` is a mixin composition whose methods live across seven files
today and are planned to spread further. Move a method out of `pilot.py` and the list still names a
real file, the control still finds real content, and the scan quietly stops covering the surface it
was written to police — a gate does not become sound by getting quieter.

Two ideas are kept apart deliberately, because conflating them produced a false failure while this
file was being written:

* **The decider surface** — `src/common/*.py` modules contributing `Pilot` methods (today: `pilot.py`
  alone; after the split: the `decide_*.py` siblings). These hold the closed-form deciders.
* **The planner surface** — `src/common/strategy/**`, i.e. `PlannerMixin`, `ObjectivesMixin` and the
  four doctrine mixins. These legitimately compose the leaf, and `planner.py` imports `state_value`
  by design (ADR-0092: the engine leaf IS ``KO_SCORE x state_value(...)``).

The insulation guard below therefore follows the DECIDER surface only. Asserting it over the whole
MRO reports `planner.py` as an offender, which is the instrument being wrong rather than the code.
"""
from __future__ import annotations

import ast
import inspect
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")

#: scan file -> module-level bindings whose literals name the `src/**.py` paths it reads.
REGISTERED: dict[str, tuple[str, ...]] = {
    "tests/strategy/test_combat_bypass_census.py": ("MODULES",),
    "tests/strategy/test_target_rows_damage_context.py": ("CONSUMERS",),
    "tests/strategy/test_value_stack_integration.py": ("PILOT_SRC", "STATE_VALUE_SRC", "STATE_MODEL_SRC"),
}

#: Path-scoped scans that target ONE module on purpose and must not widen, each with the reason.
NARROW_BY_DESIGN: dict[str, str] = {
    "tests/train/test_corpus_readers.py":
        "polices tools/, not src/; its own sweep is a glob over tools/**/*.py, so a move cannot narrow it",
    "tests/test_line_endings_policy.py":
        "names a probe path that never exists on disk — it queries git attributes, not file content",
    "tests/test_retired_rung_ids.py":
        "globs every src/**/*.py from git ls-files; names no fixed module",
    "tests/test_doc_links_resolve.py":
        "the src path is a positive-control fixture for the resolver, not a scan target",
    "tests/strategy/test_state_value.py":
        "reads pilot.py inline (no binding to extend); its insulation claim is re-asserted over the "
        "live decider surface by test_the_pilot_insulation_guard_follows_the_deciders below",
}

_QUOTED = re.compile(r"'([^']+)'|\"([^\"]+)\"")
_READS_SOURCE = re.compile(r"read_text|getsource|ast\.parse")


def _src_paths(expr: str) -> set[str]:
    """`src/common/**.py` paths in an expression, incl. `REPO / 'src' / 'common' / 'pilot.py'` form.
    Restricted to files that EXIST, else joining quoted segments invents paths out of per-deck globs."""
    parts = [a or b for a, b in _QUOTED.findall(expr)]
    found = set(re.findall(r"src/[A-Za-z0-9_/]+\.py", "/".join(parts)))
    found |= set(re.findall(r"src/[A-Za-z0-9_/]+\.py", expr))
    return {p for p in found if p.startswith("src/common/") and (REPO / p).is_file()}


def _decider_surface() -> set[str]:
    """`src/common/*.py` modules contributing Pilot methods — the closed-form decider surface."""
    from common.pilot import Pilot

    out: set[str] = set()
    for klass in Pilot.__mro__:
        if klass is object:
            continue
        file = inspect.getsourcefile(klass)
        if not file:
            continue
        try:
            rel = str(Path(file).resolve().relative_to(REPO)).replace("\\", "/")
        except ValueError:
            continue
        if rel.startswith("src/common/") and "/strategy/" not in rel:
            out.add(rel)
    return out


def _literals(rel: str, names: tuple[str, ...]) -> set[str]:
    tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if targets & set(names):
            found |= _src_paths(ast.unparse(node.value))
    return found


def _tracked_tests() -> list[str]:
    if GIT is None:
        pytest.skip("git unavailable; cannot determine the scan set")
    out = subprocess.run(
        [GIT, "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO, check=True, encoding="utf-8", text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    return [p.replace("\\", "/") for p in out.splitlines()
            if p.startswith("tests/") and p.endswith(".py")]


def test_the_probes_actually_find_something() -> None:
    """Positive controls. Either probe returning empty would make every assertion below vacuous."""
    surface = _decider_surface()
    assert "src/common/pilot.py" in surface, (
        f"the decider-surface probe lost pilot.py itself, so it is broken: {sorted(surface)}"
    )
    assert "src/common/strategy/planner.py" not in surface, (
        "the probe is returning the planner surface too; `planner.py` imports state_value by design "
        "(ADR-0092) and including it would make the insulation guard below fire falsely"
    )
    assert _src_paths("REPO / 'src' / 'common' / 'pilot.py'") == {"src/common/pilot.py"}, \
        "the segmented-Path extractor is broken"
    assert _src_paths('("src/common/pilot.py", "src/common/strategy/planner.py")') == {
        "src/common/pilot.py", "src/common/strategy/planner.py"}, "the tuple extractor is broken"


def test_every_registered_scan_covers_the_whole_decider_surface() -> None:
    """A scan naming `pilot.py` must name every module the Pilot's own deciders live in."""
    surface = _decider_surface()
    gaps: list[str] = []
    for rel, names in REGISTERED.items():
        named = _literals(rel, names)
        assert named, f"{rel}: {names} named no src/**.py path — the extractor is broken"
        if "src/common/pilot.py" not in named:
            continue
        missing = sorted(surface - named)
        if missing:
            gaps.append(f"{rel} ({', '.join(names)}) scans pilot.py but not: {', '.join(missing)}")
    assert not gaps, (
        "a path-scoped scan no longer covers the whole decider surface, so it polices a shrinking\n"
        "fraction of the code it was written for. Add the modules to its list:\n  "
        + "\n  ".join(gaps)
    )


def test_the_pilot_insulation_guard_follows_the_deciders() -> None:
    """`state_value` stays unreachable from every module holding a Pilot decider — re-asserted over the
    LIVE surface, because test_state_value.py pins `pilot.py` alone and would not follow a moved decider."""
    offenders = []
    for rel in sorted(_decider_surface()):
        tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("state_value"):
                offenders.append(f"{rel}:{node.lineno}")
            elif isinstance(node, ast.Import) and any(a.name.endswith("state_value") for a in node.names):
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        "a module holding Pilot deciders imports `state_value`; the ADR-0069 attach decider is no "
        f"longer insulated from it: {offenders}"
    )


def test_no_path_scoped_scan_is_unregistered() -> None:
    """A new scan must join the registry, or the coverage check above is bypassable by adding one."""
    unregistered: list[str] = []
    for rel in _tracked_tests():
        if rel in REGISTERED or rel in NARROW_BY_DESIGN or rel == "tests/test_source_scan_coverage.py":
            continue
        text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        if not _READS_SOURCE.search(text):
            continue
        tree = ast.parse(text)
        named: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in ("read_text", "open"):
                named |= _src_paths(ast.unparse(node.func.value))
            elif isinstance(node, ast.Assign):
                named |= _src_paths(ast.unparse(node.value))
        if named:
            unregistered.append(f"{rel}: {', '.join(sorted(named))}")
    assert not unregistered, (
        "these tests read a src/**.py path but are in neither REGISTERED nor NARROW_BY_DESIGN.\n"
        "Add to REGISTERED if the scan should widen as Pilot splits; to NARROW_BY_DESIGN, with the\n"
        "reason, if it deliberately targets one module:\n  " + "\n  ".join(unregistered)
    )
