from __future__ import annotations

from pathlib import Path

from tools import doc_budget


def test_budget_constants_match_code_as_docs_policy() -> None:
    assert (doc_budget.MAX_COMMENT_LINES, doc_budget.MAX_DOCSTRING_LINES) == (2, 2)
    assert (doc_budget.MAX_MODULE_DOC_LINES, doc_budget.MAX_LINE) == (15, 120)


def test_budget_scanner_has_positive_and_negative_controls(tmp_path, monkeypatch) -> None:
    (tmp_path / "clean.py").write_text('"""Small module."""\n\ndef clean():\n    """Small function."""\n', encoding="utf-8")
    (tmp_path / "long.py").write_text('def long():\n    """one\n    two\n    three\n    """\n', encoding="utf-8")
    monkeypatch.setattr(doc_budget, "REPO", tmp_path)

    assert not doc_budget.scan(["clean.py"]).offences
    offences = doc_budget.scan(["long.py"]).offences
    assert [(item.kind, item.lines) for item in offences] == [("function docstring", 4)]


def test_budget_scope_includes_cgpy_and_excludes_vendored_and_deprecated() -> None:
    paths = doc_budget.python_files()
    assert any(path.startswith("src/cgpy/") for path in paths)
    assert not any(path.startswith("src/cg/") for path in paths)
    assert not any(path.startswith("deprecated/") for path in paths)


def test_tracked_python_stays_within_the_prose_budget() -> None:
    offences = doc_budget.scan().offences
    assert not offences, "\n" + "\n".join(str(item) for item in offences)
