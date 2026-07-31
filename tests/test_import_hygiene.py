"""Import hygiene for the test tree itself — a guard CI structurally cannot supply.

A test helper imported as `from tests.<subdir>._helper import ...` resolves only while THREE things
hold at once: the process CWD is the repo root, `''`/CWD is on `sys.path`, and no installed
distribution ships a top-level `tests` package. The third is the one that breaks, and it breaks
SILENTLY GREEN in CI:

`tests/` has no `__init__.py` anywhere, so the repo's own `tests` is a PEP 420 **namespace** package.
Namespace portions are the last resort of the import scan — a *regular* package (one with
`__init__.py`) found at ANY later `sys.path` entry wins outright, however early the namespace portion
appeared. `kaleido` ships exactly such a package (`site-packages/tests/__init__.py`), so on a dev box
that has it installed, `from tests.strategy._accel_fixture import ...` raises
``ModuleNotFoundError: No module named 'tests.strategy'`` while a clean CI runner passes.

That asymmetry is the whole reason this file exists. A green CI is not evidence here: the failure
needs a *dirtier* environment than CI's, so CI is the one place the bug is invisible by construction.
Found 2026-07-31 on the two `test_deploy_value.py` accel-unlock tests, which had been red locally and
green on `main` since 2026-07-30.

**The idiom instead**: `tests/conftest.py` already puts `tests/` on `sys.path`, and pytest's default
`prepend` import mode puts each test module's own directory there too. So a repo-root helper imports
bare (`from pilot_helpers import ...`) and a same-directory helper imports bare as well
(`from _accel_fixture import ...`) — neither routes through a package path, so neither can be
shadowed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: `from tests.x import y` or `import tests.x` — anywhere, at any indent (these imports are usually
#: function-local, which is exactly where a reviewer's eye slides past them).
_TESTS_PACKAGE_IMPORT = re.compile(r"^\s*(?:from\s+tests[.\s]|import\s+tests[.\s])", re.MULTILINE)


@pytest.mark.req("REQ-IMPORTHYG-0001")
def test_no_test_imports_through_the_tests_package_path():
    """Ban `tests.*` imports across the whole repo — they are shadowable by any installed
    distribution that ships a top-level `tests` package, and the resulting failure is invisible to
    CI (see the module docstring). Import the helper bare instead."""
    offenders = []
    for path in REPO.rglob("*.py"):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if _TESTS_PACKAGE_IMPORT.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(REPO)).replace("\\", "/"))
    assert offenders == [], (
        "these import through the shadowable `tests.` package path; import the helper bare "
        f"(`from _accel_fixture import ...`) instead — {offenders}")


@pytest.mark.req("REQ-IMPORTHYG-0001")
def test_the_tests_tree_stays_a_namespace_package_so_the_bare_idiom_is_the_only_one():
    """The ban above is only coherent while `tests/` has no `__init__.py`. Adding one would make the
    package path resolvable again and quietly re-open the door — so the absence is asserted, not
    assumed. It is also the cheaper half of the fix: `sys.path` already carries both directories a
    bare import needs."""
    inits = sorted(str(p.relative_to(REPO)).replace("\\", "/")
                   for p in (REPO / "tests").rglob("__init__.py"))
    assert inits == [], (
        "tests/ is deliberately a PEP 420 namespace tree — adding __init__.py makes `tests.*` "
        f"imports resolvable again and re-opens the shadowing trap — {inits}")
