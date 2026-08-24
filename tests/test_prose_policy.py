from __future__ import annotations

from tools import prose_policy


def _kinds(text: str, path: str = "docs/example.md") -> set[str]:
    return {item.kind for item in prose_policy.scan_text(path, text)}


def test_scanner_accepts_live_references_and_commands() -> None:
    text = "See docs/rulebook.txt. Validate with python -m tools.doc_budget --detail src."
    assert not prose_policy.scan_text("docs/example.md", text)


def test_scanner_rejects_each_policy_failure() -> None:
    assert "retired identifier" in _kinds("The StateModel decides this.")
    assert "missing path" in _kinds("See docs/does-not-exist.md.")
    assert "missing command" in _kinds("Run python -m tools.does_not_exist.")


def test_scanner_rejects_live_bellman_claim_but_allows_offline_teacher() -> None:
    stale = prose_policy.scan_text("docs/live.md", "Bellman stays in the codebase, callable but unplugged.")
    current = prose_policy.scan_text("docs/live.md", "Bellman is quarantined as an offline teacher.")
    assert [item.kind for item in stale] == ["retired claim", "retired claim"]
    assert not current


def test_scanner_ignores_non_prose_python_tokens() -> None:
    text = 'StateModel = "docs/does-not-exist.md"\n# Current prose.\n'
    assert not prose_policy.scan_text("src/example.py", text)


def test_scanner_excludes_historical_generated_fixture_and_vendored_paths() -> None:
    stale = "StateModel; docs/does-not-exist.md; python -m tools.does_not_exist"
    excluded = (
        "docs/adr/0068-state-model.md",
        "docs/plans/ledger-corpus-dashboard.md",
        "tests/fixtures/example.md",
        "tests/common/fixtures/example.py",
        "src/cg/example.py",
        "deprecated/example.md",
    )
    assert all(not prose_policy.scan_text(path, stale) for path in excluded)


def test_tracked_live_prose_has_no_policy_violations() -> None:
    violations = prose_policy.scan_tracked()
    assert not violations, "\n" + "\n".join(str(item) for item in violations)
