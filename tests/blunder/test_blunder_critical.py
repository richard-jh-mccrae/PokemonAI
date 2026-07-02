"""CRITICAL marker: a rationale flag that makes /blunder-buster resolve a blunder first.

The human types the uppercase token CRITICAL into a Correction's rationale. The pipeline surfaces
it (proposal flag -> durable snapshot -> dashboard badge) so the skill can partition the must-fix-
first cohort without hand-grepping. See docs/blunder-tuner.md, .claude/skills/blunder-buster.
"""
import json

from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.correction import CRITICAL_MARKER, build_correction, is_critical
from train.blunder.decisions import iter_decisions
from train.blunder.report import build_report
from train.blunder.store import append_correction
from train.tuner.io import write_proposals
from train.tuner.propose import propose_hypothesis

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def _main():
    return next(d for d in iter_decisions(load_replay(FIXTURE)) if d.select_context == "Main")


def _c(rationale, category="missed_win"):
    return build_correction(_main(), source="own", agent="mega_starmie",
                            correct=[4], category=category, rationale=rationale)


def test_is_critical_matches_uppercase_token_only():
    """REQ-BLUNDER-0013: the marker is the uppercase CRITICAL token (word-boundary, case-sensitive);
    lowercase prose and substrings are NOT flags."""
    assert is_critical("CRITICAL: never pass lethal")
    assert is_critical("this one is CRITICAL")
    assert is_critical("CRITICAL.")                      # punctuation is a word boundary
    assert not is_critical("a critical attack")          # lowercase prose, not a marker
    assert not is_critical("CRITICALLY low")             # substring, not the token itself
    assert not is_critical("")
    assert not is_critical(None)
    assert CRITICAL_MARKER == "CRITICAL"


def test_correction_is_critical_property():
    """REQ-BLUNDER-0013: the Correction exposes the flag derived from its rationale."""
    assert _c("CRITICAL do X").is_critical
    assert not _c("do X").is_critical


def test_proposal_carries_critical_flag():
    """REQ-BLUNDER-0013: a missing_hypothesis proposal derives `critical` from the rationale."""
    assert propose_hypothesis(_c("CRITICAL: snipe the threat")).critical
    assert not propose_hypothesis(_c("snipe the threat")).critical


def test_proposals_snapshot_serializes_critical(tmp_path):
    """REQ-BLUNDER-0013: the durable open[]/skipped[] snapshot carries `critical` so
    /blunder-buster reads the must-fix-first cohort straight from it."""
    p = propose_hypothesis(_c("CRITICAL: snipe the threat"))
    out = write_proposals(tmp_path / "mega_starmie.json", "mega_starmie", [p],
                          [(_c("CRITICAL skipped tactical"), "tactical")],
                          generated_at="2026-06-30T00:00:00")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["open"][0]["critical"] is True
    assert data["skipped"][0]["critical"] is True


def test_shell_ui_exposes_critical_checkbox():
    """REQ-BLUNDER-0013: the tagging shell renders a red Critical checkbox that owns the CRITICAL
    token in the rationale (bidirectional), so the human sets it without hand-typing the marker."""
    from train.blunder.shell import _SHELL_HTML
    assert 'id="critical"' in _SHELL_HTML and 'type="checkbox"' in _SHELL_HTML
    assert "class=\"crit\"" in _SHELL_HTML                       # red styling hook
    assert f"'{CRITICAL_MARKER}: '" in _SHELL_HTML               # applyCritical prepends exact token
    assert "syncCrit" in _SHELL_HTML                             # box tracks rationale text


def test_report_badges_critical(tmp_path):
    """REQ-BLUNDER-0013: the offline dashboard badges a CRITICAL blunder (and stays offline)."""
    log = tmp_path / "c.jsonl"
    append_correction(_c("CRITICAL: had lethal, passed"), log)
    append_correction(_c("ordinary miss", category="overextension"), log)  # distinct dedup key
    txt = build_report(log, tmp_path / "r.html").read_text(encoding="utf-8")
    assert txt.count("pill critical") == 2                # header count + one badged row
    assert "&#9888; 1 CRITICAL" in txt                    # header shows exactly one critical
    assert "http" not in txt                              # still fully offline
