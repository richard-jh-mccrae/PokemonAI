"""Aggregating Corrections into trend summaries."""
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.correction import build_correction
from train.blunder.decisions import iter_decisions
from train.blunder.report import build_report, summarize
from train.blunder.store import append_correction

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def _main():
    return next(d for d in iter_decisions(load_replay(FIXTURE)) if d.select_context == "Main")


def _c(source="own", category="missed_win", submission_id=100, rationale="r"):
    return build_correction(_main(), source=source, agent="mega_starmie",
                            submission_id=submission_id, correct=[4], category=category, rationale=rationale)


def test_summarize_counts_own_pile_by_category():
    """REQ-BLUNDER-0009: own pile bucketed by category; peer excluded from the
    'my agent' view but counted separately."""
    s = summarize([
        _c("own", "missed_win", 100),
        _c("own", "missed_win", 100),
        _c("own", "overextension", 101),
        _c("peer", "bad_target", None),
    ])
    assert s["own"]["total"] == 3
    assert s["own"]["by_category"]["missed_win"] == 2
    assert s["own"]["by_category"]["overextension"] == 1
    assert "bad_target" not in s["own"]["by_category"]     # peer not mixed into own
    assert s["peer"]["total"] == 1
    assert s["peer"]["by_category"]["bad_target"] == 1


def test_summarize_groups_own_by_submission_timeline():
    """REQ-BLUNDER-0009: own corrections group by submission_id (the trend timeline)."""
    s = summarize([
        _c("own", "missed_win", 100),
        _c("own", "overextension", 100),
        _c("own", "missed_win", 101),
    ])
    assert s["own"]["by_submission"][100]["total"] == 2
    assert s["own"]["by_submission"][100]["by_category"]["missed_win"] == 1
    assert s["own"]["by_submission"][101]["by_category"]["missed_win"] == 1


def test_report_html_is_offline_and_lists_categories_with_drilldown(tmp_path):
    """REQ-BLUNDER-0010: the report is self-contained (no external refs) and lists the
    own-pile categories with an expandable drill-down showing the rationale."""
    log = tmp_path / "corrections.jsonl"
    append_correction(_c("own", "missed_win", 100, rationale="had exact lethal, passed"), log)
    append_correction(_c("own", "overextension", 101), log)
    append_correction(_c("peer", "bad_target", None), log)

    out = build_report(log, tmp_path / "report.html")
    txt = out.read_text(encoding="utf-8")

    assert out.exists()
    assert "missed_win" in txt and "overextension" in txt
    assert "had exact lethal, passed" in txt              # drill-down shows the rationale
    assert "<details>" in txt and "<summary>" in txt      # expandable
    assert "http" not in txt                              # offline: no CDN / external refs


def test_report_empty_is_placeholder(tmp_path):
    """REQ-BLUNDER-0010: an empty log still writes a valid placeholder report."""
    out = build_report(tmp_path / "none.jsonl", tmp_path / "r.html")
    assert out.exists() and "No corrections" in out.read_text(encoding="utf-8")
