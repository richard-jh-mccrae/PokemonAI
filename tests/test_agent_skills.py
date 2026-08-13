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
