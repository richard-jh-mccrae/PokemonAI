"""Import hygiene for the test tree itself — a guard CI structurally cannot supply.

``tests/`` has no ``__init__.py``, so it is a PEP 420 **namespace** package, and a *regular* package
found at ANY later ``sys.path`` entry wins outright. ``kaleido`` ships one, so an import through the
package path raises ``ModuleNotFoundError`` on a dev box that has it installed while a clean CI
runner passes — CI is the one place the bug is invisible by construction.

**The idiom instead**: `tests/conftest.py` puts `tests/` on `sys.path` and pytest's `prepend` import
mode adds each module's own directory, so a repo-root helper and a same-directory helper both import
bare and neither can be shadowed.

**The scan is driven by git, not a filesystem walk.** `REPO.rglob("*.py")` walked 21,259 files to
reach 555 and was wrong both ways: `.venv/` and vendored `node_modules/` cost 643 s of third-party
reading, and `.claude/worktrees/` made the guard fail on `main` over another branch's file.
"""
from __future__ import annotations

import re
import ast
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: The banned package-path import, at any indent (these imports are usually function-local, which
#: is where an eye slides past them). Anchored to line start so prose NAMING the form is not a hit.
_TESTS_PACKAGE_IMPORT = re.compile(r"^\s*(?:from\s+tests[.\s]|import\s+tests[.\s])", re.MULTILINE)


def _repo_python_files() -> list[Path]:
    """Every ``.py`` file belonging to THIS checkout — tracked, or new and not gitignored. ``-z`` keeps
    paths intact when they contain spaces or non-ASCII, on either OS."""
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.py"],
        cwd=REPO, capture_output=True)
    if proc.returncode != 0:                           # no git, or not a repo (a source tarball)
        pytest.skip("git unavailable; cannot enumerate this checkout's own files")
    paths = [REPO / p for p in proc.stdout.decode("utf-8").split("\0") if p]
    # A scan set that quietly came back empty would make every assertion below vacuously true — the
    # exact way a guard dies without anyone noticing. Anchor it on the one file guaranteed present.
    assert Path(__file__).resolve() in {p.resolve() for p in paths}, (
        "git listed no .py files for this checkout — the scan would pass vacuously")
    return [p for p in paths if p.is_file()]           # `--cached` lists staged-but-deleted paths


@pytest.mark.req("REQ-IMPORTHYG-0001")
def test_no_test_imports_through_the_tests_package_path():
    """Ban the shadowable package path across this checkout: any installed distribution shipping a
    top-level ``tests`` package wins, and the failure is invisible to CI. Import the helper bare."""
    offenders = []
    for path in _repo_python_files():
        if _TESTS_PACKAGE_IMPORT.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(REPO)).replace("\\", "/"))
    assert offenders == [], (
        "these import through the shadowable `tests.` package path; import the helper bare "
        f"(`from _accel_fixture import ...`) instead — {offenders}")


@pytest.mark.req("REQ-IMPORTHYG-0001")
def test_the_tests_tree_stays_a_namespace_package_so_the_bare_idiom_is_the_only_one():
    """The ban above is only coherent while ``tests/`` has no ``__init__.py``: adding one makes the
    package path resolvable again, so the absence is asserted rather than assumed."""
    inits = sorted(str(p.relative_to(REPO)).replace("\\", "/")
                   for p in (REPO / "tests").rglob("__init__.py"))
    assert inits == [], (
        "tests/ is deliberately a PEP 420 namespace tree — adding __init__.py makes `tests.*` "
        f"imports resolvable again and re-opens the shadowing trap — {inits}")


@pytest.mark.req("REQ-IMPORTHYG-0001")
def test_the_scan_stays_inside_this_checkout():
    """Both ways the ``rglob`` version failed, pinned: a walk reaching a sibling worktree or a virtualenv
    still passes until one of those foreign files contains the banned line, which no branch can fix."""
    scanned = {str(p.relative_to(REPO)).replace("\\", "/") for p in _repo_python_files()}

    foreign = sorted(p for p in scanned
                     if p.startswith((".venv/", ".claude/worktrees/", "data/submissions/"))
                     or "/node_modules/" in p or "/.src/" in p)
    assert foreign == [], (
        "the scan reached files outside this checkout's source — a sibling worktree, a virtualenv, "
        f"or vendored dependency code — {foreign[:10]}")

    # ...and it must still reach the tree the ban is actually about.
    assert any(p.startswith("tests/ledger/") for p in scanned), (
        "the scan no longer covers the primary policy suite")


_DEPRECATED_IMPORT = re.compile(r"^\s*(?:from\s+deprecated[.\s]|import\s+deprecated[.\s])",
                                re.MULTILINE)


@pytest.mark.req("REQ-IMPORTHYG-0002")
def test_no_live_source_imports_the_deprecated_quarantine():
    """ADR-0149's boundary: `deprecated/` may ride `src/`, never the reverse — a live module
    importing quarantined code silently un-retires the Bellman brain."""
    offenders = []
    for path in _repo_python_files():
        relative = str(path.relative_to(REPO)).replace("\\", "/")
        if not (relative.startswith("src/") or relative.startswith("tools/submit/")):
            continue
        if _DEPRECATED_IMPORT.search(path.read_text(encoding="utf-8")):
            offenders.append(relative)
    assert offenders == [], (
        f"live source imports the deprecated quarantine — {offenders}")


def test_observation_state_is_the_only_live_legal_view_surface():
    retired = re.compile(r"\b(?:common\.board|BoardState|LedgerContext|OpponentLayer)\b")
    enrichments = ("bellmanActor", "bellmanBeliefKey", "bellmanRecycledCardIds",
                   "bellmanHistoricalMain", "bellmanHistoricalContext")
    offenders = []
    for path in _repo_python_files():
        relative = str(path.relative_to(REPO)).replace("\\", "/")
        if not relative.startswith("src/"):
            continue
        text = path.read_text(encoding="utf-8")
        if retired.search(text) or any(name in text for name in enrichments):
            offenders.append(relative)
    assert offenders == [], f"retired observation surfaces or raw enrichments remain — {offenders}"


def test_retired_opponent_surfaces_are_absent_from_live_source():
    retired = re.compile(
        r"\b(?:common\.scouting\.(?:read|scout|traits)|Read|OpponentBeliefs|OpponentLayer)\b"
    )
    offenders = []
    for path in (REPO / "src").rglob("*.py"):
        relative = path.relative_to(REPO).as_posix()
        if retired.search(path.read_text(encoding="utf-8")):
            offenders.append(relative)
    assert offenders == [], f"retired opponent surfaces remain — {offenders}"


def test_live_decision_contract_has_no_bellman_plan_state():
    from common.api import RootDecision

    decision = RootDecision((), None, 0.0, True, {})

    assert not hasattr(decision, "plan_suffix")


def test_live_runtime_has_no_retired_bellman_or_latch_state():
    text = (REPO / "src/common/runtime.py").read_text(encoding="utf-8")
    retired = (
        "last_decision_limit", "last_deadline_hit", "_fallback_scope", "_fallback_effect",
        "_fallback_pending", "_invalidate_plans",
    )

    assert all(name not in text for name in retired)


def test_policy_consumers_cannot_walk_raw_observations():
    targets = (
        "src/common/runtime.py", "src/common/deck_tracker.py", "src/common/telemetry.py",
        "src/common/opponent/model.py", "src/common/ledger/decider.py",
        "src/common/ledger/evaluate.py", "src/common/ledger/worth.py",
    )
    fallback_functions = {"_crash_report", "_fallback_decision", "_last_resort_selection",
                          "_last_resort_ranked", "agent"}
    offenders = []
    for relative in targets:
        path = REPO / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value in {"current", "select", "logs"}):
                continue
            owner = node
            while owner in parents and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner = parents[owner]
            if relative == "src/common/runtime.py" and getattr(owner, "name", None) in fallback_functions:
                continue
            offenders.append(f"{relative}:{node.lineno}")
    assert offenders == [], f"policy consumers walk raw engine observations — {offenders}"
