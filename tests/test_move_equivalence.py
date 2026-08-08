"""`tools/move_equivalence.py` must answer "is this a pure move of CODE" — and still say no when it is not.

The tool hashed `inspect.getsource` whole, docstring included, so the 2026-08-08 documentation
reduction made it report 416 of 470 methods CHANGED. A tool that reports everything as changed is
indistinguishable from a broken one, and nothing — no test, no CI job, no doc — referenced it, so
nothing noticed.

The relaxation that fixes that is paired here with its positive control. `test_a_real_body_edit_is_
still_changed` is the assert that must never be weakened: without it the fix is vacuously green,
which is the same failure one layer down.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.move_equivalence import (  # noqa: E402
    CODE_ONLY,
    HASHES,
    WITH_DOCSTRINGS,
    compare,
    main,
    surface,
)

BEFORE = '''\
class Thing:
    def prose_only(self):
        """Prose the reduction pass will shorten considerably."""
        return 1 + 1

    def edited(self):
        """Stable."""
        return 1 + 1

    def all_prose(self):
        """One sentence, and no code at all."""

    def nests(self):
        def inner():
            """Inner prose."""
            return 3
        return inner
'''

AFTER = '''\
class Thing:
    def prose_only(self):
        """Short."""
        return 1 + 1

    def edited(self):
        """Stable."""
        return 2 + 2

    def all_prose(self):
        """A different sentence entirely."""

    def nests(self):
        def inner():
            """Different inner prose."""
            return 3
        return inner
'''


@pytest.fixture
def make_module(tmp_path, monkeypatch):
    """Import `source` as a real on-disk module — `inspect.getsource` needs a file to read."""
    monkeypatch.syspath_prepend(str(tmp_path))
    created: list[str] = []

    def _make(name: str, source: str):
        (tmp_path / f"{name}.py").write_text(source, encoding="utf-8", newline="\n")
        importlib.invalidate_caches()
        created.append(name)
        return importlib.import_module(name)

    yield _make
    for name in created:
        sys.modules.pop(name, None)


@pytest.fixture
def surfaces(make_module):
    return (surface(make_module("mve_before", BEFORE).Thing),
            surface(make_module("mve_after", AFTER).Thing))


def test_a_real_body_edit_is_still_changed(surfaces):
    """THE positive control. `1 + 1` -> `2 + 2` under an untouched docstring."""
    before, after = surfaces
    assert "edited" in compare(before, after)["changed"]


def test_a_docstring_edit_alone_is_not_a_code_change(surfaces):
    before, after = surfaces
    assert compare(before, after)["changed"] == ["edited"]


def test_include_docstrings_still_sees_every_prose_edit(surfaces):
    before, after = surfaces
    assert compare(before, after, WITH_DOCSTRINGS)["changed"] == [
        "all_prose", "edited", "nests", "prose_only"]


def test_a_body_that_was_only_prose_survives_the_strip(surfaces):
    """`all_prose` empties out entirely; the `Pass` stand-in keeps it hashable and equal."""
    before, after = surfaces
    assert before["all_prose"][CODE_ONLY] == after["all_prose"][CODE_ONLY]
    assert before["all_prose"][WITH_DOCSTRINGS] != after["all_prose"][WITH_DOCSTRINGS]


def test_a_nested_docstring_is_stripped_too(surfaces):
    """`nests` differs only inside its inner function — the walk has to reach that far."""
    before, after = surfaces
    assert before["nests"][CODE_ONLY] == after["nests"][CODE_ONLY]


def test_identical_code_elsewhere_reads_as_moved_not_changed(make_module):
    before = surface(make_module("mve_here", BEFORE).Thing)
    after = surface(make_module("mve_there", BEFORE).Thing)
    result = compare(before, after)
    assert not result["changed"] and len(result["moved"]) == 4


def test_cli_round_trip_is_a_pure_move(make_module, tmp_path, capsys):
    make_module("mve_cli", BEFORE)
    out = tmp_path / "snap.json"
    assert main(["snapshot", "--target", "mve_cli.Thing", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))[HASHES] == [CODE_ONLY, WITH_DOCSTRINGS]
    assert main(["verify", "--target", "mve_cli.Thing", "--against", str(out)]) == 0
    assert "pure move" in capsys.readouterr().out


def test_a_snapshot_predating_the_split_is_refused(make_module, tmp_path, capsys):
    """A legacy snapshot HAS a `hash` — a different normalization under the same name. Comparing
    against it silently reported 443 changed, so presence cannot be the test and absence must fail."""
    make_module("mve_legacy", BEFORE)
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"target": "mve_legacy.Thing", "surface": {
        "edited": {"hash": "deadbeefdeadbeef", "module": "somewhere.py"}}}), encoding="utf-8")

    assert main(["verify", "--target", "mve_legacy.Thing", "--against", str(legacy)]) == 2
    assert "predates the docstring split" in capsys.readouterr().out
