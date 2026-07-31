"""Import hygiene for the test tree itself — a guard CI structurally cannot supply.

A test helper imported as ``from tests.<subdir>._helper import ...`` resolves only while THREE things
hold at once: the process CWD is the repo root, ``''``/CWD is on ``sys.path``, and no installed
distribution ships a top-level ``tests`` package. The third is the one that breaks, and it breaks
SILENTLY GREEN in CI:

``tests/`` has no ``__init__.py`` anywhere, so the repo's own ``tests`` is a PEP 420 **namespace**
package. Namespace portions are the last resort of the import scan — a *regular* package (one with
``__init__.py``) found at ANY later ``sys.path`` entry wins outright, however early the namespace
portion appeared. ``kaleido`` ships exactly such a package (``site-packages/tests/__init__.py``), so
on a dev box that has it installed, importing through the ``tests.`` package path raises
``ModuleNotFoundError: No module named 'tests.strategy'`` while a clean CI runner passes.

That asymmetry is the whole reason this file exists. A green CI is not evidence here: the failure
needs a *dirtier* environment than CI's, so CI is the one place the bug is invisible by construction.
Found 2026-07-31 on the two ``test_deploy_value.py`` accel-unlock tests, which had been red locally
and green on ``main`` since 2026-07-30.

**The idiom instead**: ``tests/conftest.py`` already puts ``tests/`` on ``sys.path``, and pytest's
default ``prepend`` import mode puts each test module's own directory there too. So a repo-root
helper imports bare (``from pilot_helpers import ...``) and a same-directory helper imports bare as
well (``from _accel_fixture import ...``) — neither routes through a package path, so neither can be
shadowed.

**Why the scan is driven by git, not by a filesystem walk.** The first version of this guard walked
``REPO.rglob("*.py")``, skipping only ``.git`` and ``__pycache__``. On the primary checkout that
walked 21,259 files to reach the repo's own 555, and it was wrong in both directions:

* ``.venv/`` (17,709 files) and ``tools/train/blunder/viewer/.src/node_modules/`` (vendored node-gyp
  and ``kaggle_environments`` Python) are gitignored build/dependency output, not this repo's code.
  A third-party file's imports are none of this guard's business, and reading them cost **643 s** for
  these two tests alone.
* ``.claude/worktrees/`` holds live git worktrees — full checkouts of *other branches*. The guard
  flagged a stale worktree's copy of ``test_deploy_value.py`` and failed on ``main``, reporting a
  foreign branch's file as this tree's offender. That failure is unfixable from ``main``: the
  offending line does not exist in ``main``.

So the scan set is ``git ls-files --cached --others --exclude-standard`` — tracked files plus
new-but-not-yet-added ones, minus everything ``.gitignore`` excludes. It is exactly this checkout's
own Python, it honours worktree boundaries, and it needs no skip-list to maintain.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: `from tests.x import y` or `import tests.x` — anywhere, at any indent (these imports are usually
#: function-local, which is exactly where a reviewer's eye slides past them). Anchored to the start
#: of a line so prose that *names* the banned form, as this module's own docstring does, is not a hit.
_TESTS_PACKAGE_IMPORT = re.compile(r"^\s*(?:from\s+tests[.\s]|import\s+tests[.\s])", re.MULTILINE)


def _repo_python_files() -> list[Path]:
    """Every ``.py`` file belonging to THIS checkout — tracked, or new and not gitignored.

    ``--cached`` covers committed files; ``--others --exclude-standard`` adds files a dev has just
    written but not yet staged, which is precisely when a bad import gets typed. ``-z`` keeps paths
    intact when they contain spaces or non-ASCII, on either OS.
    """
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
    """Ban ``tests.*`` imports across this checkout — they are shadowable by any installed
    distribution that ships a top-level ``tests`` package, and the resulting failure is invisible to
    CI (see the module docstring). Import the helper bare instead."""
    offenders = []
    for path in _repo_python_files():
        if _TESTS_PACKAGE_IMPORT.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(REPO)).replace("\\", "/"))
    assert offenders == [], (
        "these import through the shadowable `tests.` package path; import the helper bare "
        f"(`from _accel_fixture import ...`) instead — {offenders}")


@pytest.mark.req("REQ-IMPORTHYG-0001")
def test_the_tests_tree_stays_a_namespace_package_so_the_bare_idiom_is_the_only_one():
    """The ban above is only coherent while ``tests/`` has no ``__init__.py``. Adding one would make
    the package path resolvable again and quietly re-open the door — so the absence is asserted, not
    assumed. It is also the cheaper half of the fix: ``sys.path`` already carries both directories a
    bare import needs."""
    inits = sorted(str(p.relative_to(REPO)).replace("\\", "/")
                   for p in (REPO / "tests").rglob("__init__.py"))
    assert inits == [], (
        "tests/ is deliberately a PEP 420 namespace tree — adding __init__.py makes `tests.*` "
        f"imports resolvable again and re-opens the shadowing trap — {inits}")


@pytest.mark.req("REQ-IMPORTHYG-0001")
def test_the_scan_stays_inside_this_checkout():
    """The scan must never reach outside this checkout's own source.

    Both ways the ``rglob`` version failed are pinned here, because neither is visible from the
    guard's own result — a walk that reaches a sibling worktree or a virtualenv still *passes* right
    up until one of those foreign files happens to contain the banned line, at which point it fails
    on a file the branch under test cannot edit.
    """
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
