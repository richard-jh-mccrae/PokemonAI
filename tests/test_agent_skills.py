"""Claude and Codex discover one maintained set of project skills."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.req("REQ-AUTHORING-0001")
def test_codex_skill_adapters_match_the_canonical_claude_skills():
    result = subprocess.run(
        [sys.executable, "tools/sync_agent_skills.py", "--check"],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.req("REQ-AUTHORING-0001")
def test_every_canonical_skill_is_natively_discoverable_by_both_agents():
    claude = {path.name for path in (REPO / ".claude" / "skills").iterdir() if path.is_dir()}
    codex = {path.name for path in (REPO / ".agents" / "skills").iterdir() if path.is_dir()}
    assert codex == claude
    assert all((REPO / ".agents" / "skills" / name / "SKILL.md").is_file() for name in codex)


@pytest.mark.req("REQ-AUTHORING-0001")
def test_auto_grill_with_docs_preserves_its_protocol_invariants():
    canonical = REPO / ".claude" / "skills" / "auto-grill-with-docs" / "SKILL.md"
    adapter = REPO / ".agents" / "skills" / "auto-grill-with-docs" / "SKILL.md"
    policy = adapter.parent / "agents" / "openai.yaml"

    assert canonical.is_file()
    text = canonical.read_text(encoding="utf-8")
    assert "name: auto-grill-with-docs" in text
    assert "disable-model-invocation: true" in text
    assert adapter.is_file()
    assert "allow_implicit_invocation: false" in policy.read_text(encoding="utf-8")
    for value in (
        "/domain-modeling",
        "/caveman",
        "/to-spec",
        "correctness and robustness",
        "Hard stop only",
        "one review",
        "Reply `approve` to accept all recommended decisions and testing seams and continue to `/to-spec`, or name any decision ID to change.",
        "status:1-grilling",
        "docs/adr/temp-issue<N>-<slug>.md",
    ):
        assert value in text
