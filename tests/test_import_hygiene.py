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
    assert any(p.startswith("tests/strategy/") for p in scanned), (
        "the scan no longer covers tests/strategy/, where the shadowing bug was found")
