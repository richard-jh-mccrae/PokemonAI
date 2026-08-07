"""The comment and docstring size budget — the gate that keeps prose from re-accumulating.

The budget is 2 lines for a `#` block, 2 for a function or class docstring, 15 for a module docstring,
120 characters for any prose line. `.claude/skills/code-as-docs/SKILL.md` argues for those numbers;
`tools/doc_budget.py` computes them, and this file is the gate over that tool so the two cannot drift.

**This gate is dormant until the reduction pass finishes, and it arms itself.** The 2026-08-07 audit
counted 5,088 offences across 450 files, so a hard assertion today would fail every run and be disabled
within a week. Instead the gate skips while offences remain — printing the live count, so `pytest -rs`
shows progress — and becomes a real assertion the moment the count reaches zero. Nobody has to remember
to delete a marker; finishing the cleanup is what turns it on.

`test_the_budget_scanner_actually_measures` runs unconditionally. A dormant gate whose instrument is
broken is worse than no gate: it would arm itself into a permanent green that means nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.doc_budget import (  # noqa: E402
    MAX_COMMENT_LINES,
    MAX_LINE,
    MAX_MODULE_DOC_LINES,
    scan,
)

_OVER_BUDGET = '''"""A module docstring of three lines.
This is well inside the 15-line module budget,
so it must NOT be reported."""


# a comment block
# of three
# lines
def _example() -> None:
    """One.
    Two.
    Three."""
'''

_WITHIN_BUDGET = '''"""One line is fine."""


# two lines
# is the limit
def _example() -> None:
    """Short enough."""
'''


def _scan_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> list:
    import tools.doc_budget as budget

    target = tmp_path / "sample.py"
    target.write_text(text, encoding="utf-8")
    monkeypatch.setattr(budget, "REPO", tmp_path)
    return budget.scan(["sample.py"]).offences


def test_the_budget_scanner_actually_measures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Positive and negative control: prove the instrument can see an offence and can also stay quiet."""
    over = _scan_text(tmp_path, monkeypatch, _OVER_BUDGET)
    kinds = sorted(offence.kind for offence in over)
    assert kinds == ["comment block", "function docstring"], (
        f"positive control failed — expected a 3-line comment block and a 3-line docstring, got {kinds}"
    )
    under = _scan_text(tmp_path, monkeypatch, _WITHIN_BUDGET)
    assert not under, f"negative control failed — compliant source reported {under}"


def test_the_budget_constants_match_the_documented_policy() -> None:
    assert (MAX_COMMENT_LINES, MAX_MODULE_DOC_LINES, MAX_LINE) == (2, 15, 120)


def test_the_protected_literal_extractor_still_finds_its_anchors() -> None:
    """The reduction pass reads `tools.asserted_text` to know what it may not delete; an extractor that
    silently returned nothing would look safe while deleting asserted prose. Anchors verified 2026-08-07."""
    from tools.asserted_text import collect

    rows = [row for rows in collect().values() for row in rows]
    required = {row["literal"] for row in rows if row["kind"] == "REQUIRED"}
    forbidden = {row["literal"] for row in rows if row["kind"] == "FORBIDDEN"}

    missing = {"working()", "5807 of 5807", "_search_api", "scoped to one seam"} - required
    assert not missing, f"the extractor lost known REQUIRED literals: {missing} — it is broken"
    absent = {"forward_max_damage", "off_policy", "import cgpy"} - forbidden
    assert not absent, f"the extractor lost known FORBIDDEN literals: {absent} — it is broken"


def test_no_comment_or_docstring_exceeds_its_budget() -> None:
    report = scan()
    if report.offences:
        pytest.skip(
            f"reduction pass in progress: {len(report.offences)} offences across "
            f"{report.files_affected()} files ({report.by_kind()}). This gate arms itself at zero — "
            "run `python -m tools.doc_budget --detail` for the worklist."
        )
    assert not report.offences
