"""Aggregating Corrections into trend summaries."""
import json
from types import SimpleNamespace

from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.correction import build_correction
from train.blunder.decisions import iter_decisions
from train.blunder.report import _disposition, avg_blunders_per_game, build_report, summarize
from train.blunder.reviewed import review_key
from train.blunder.store import append_correction

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def _main():
    return next(d for d in iter_decisions(load_replay(FIXTURE)) if d.select_context == "Main")


def _c(source="own", category="missed_win", submission_id=100, rationale="r",
       agent_build=None, built_at=None):
    return build_correction(_main(), source=source, agent="mega_starmie",
                            submission_id=submission_id, agent_build=agent_build, built_at=built_at,
                            correct=[4], category=category, rationale=rationale)


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


def test_summarize_groups_own_by_build():
    """REQ-TUNER-0010: own corrections group by agent build (the over-time evolution view)."""
    s = summarize([
        _c("own", "missed_win", agent_build="mega_starmie_20260601_aaa", built_at="2026-06-01T00:00:00"),
        _c("own", "bad_target", agent_build="mega_starmie_20260601_aaa", built_at="2026-06-01T00:00:00"),
        _c("own", "missed_win", agent_build="mega_starmie_20260610_bbb", built_at="2026-06-10T00:00:00"),
    ])
    by_build = s["own"]["by_build"]
    assert by_build["mega_starmie_20260601_aaa"]["total"] == 2
    assert by_build["mega_starmie_20260601_aaa"]["built_at"] == "2026-06-01T00:00:00"
    assert by_build["mega_starmie_20260610_bbb"]["by_category"]["missed_win"] == 1


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
    assert "had exact lethal, passed" in txt              # drill-down shows rationale
    assert "<details>" in txt and "<summary>" in txt      # expandable
    assert "http" not in txt                              # offline: no CDN / external refs


def test_report_html_shows_builds_over_time(tmp_path):
    """REQ-TUNER-0010: the offline report lists each agent build (traceability / evolution)."""
    log = tmp_path / "c.jsonl"
    append_correction(_c("own", "missed_win", agent_build="mega_starmie_20260601_aaa",
                         built_at="2026-06-01T00:00:00"), log)
    append_correction(_c("own", "bad_target", agent_build="mega_starmie_20260610_bbb",
                         built_at="2026-06-10T00:00:00"), log)
    txt = build_report(log, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "mega_starmie_20260601_aaa" in txt and "mega_starmie_20260610_bbb" in txt
    assert "http" not in txt


def test_report_empty_is_placeholder(tmp_path):
    """REQ-BLUNDER-0010: an empty log still writes a valid placeholder report."""
    out = build_report(tmp_path / "none.jsonl", tmp_path / "r.html")
    assert out.exists() and "No corrections" in out.read_text(encoding="utf-8")


# --- resolution view: disposition tagging (fixed/covered/refuted/deferred/open/skipped) ---------

def _fake(ep, frame, agent="mega_starmie"):
    return SimpleNamespace(episode_id=ep, decision={"frame": frame}, agent=agent)


def test_disposition_classifies_ledger_then_open_then_skipped_then_fixed():
    """REQ-BLUNDER-0011: precedence ledger > open > skipped > fixed; a deck with no proposals
    snapshot stays open (never wrongly claimed fixed)."""
    reviewed = {"1-5": {"disposition": "covered"}, "1-6": {"disposition": "refuted"}}
    open_keys, skipped_keys, decks = {"2-7"}, {"3-8"}, {"mega_starmie"}

    assert _disposition(_fake(1, 5), reviewed, open_keys, skipped_keys, decks) == "covered"
    assert _disposition(_fake(1, 6), reviewed, open_keys, skipped_keys, decks) == "refuted"
    assert _disposition(_fake(2, 7), reviewed, open_keys, skipped_keys, decks) == "open"
    assert _disposition(_fake(3, 8), reviewed, open_keys, skipped_keys, decks) == "skipped"
    assert _disposition(_fake(9, 9), reviewed, open_keys, skipped_keys, decks) == "fixed"   # deck tuned, not open
    assert _disposition(_fake(9, 9, agent="other"), reviewed, open_keys, skipped_keys, decks) == "open"  # unknown deck


def test_report_enriched_badges_a_refuted_blunder_and_splits_resolved(tmp_path):
    """REQ-BLUNDER-0011: with a ledger, an own blunder is badged with its disposition, the header
    splits resolved vs open, a by-resolution section appears — and the report stays offline."""
    log = tmp_path / "c.jsonl"
    c1 = _c("own", "missed_win", 100, rationale="had exact lethal, passed")
    append_correction(c1, log)
    reviewed = tmp_path / "reviewed.json"
    reviewed.write_text(json.dumps({review_key(c1): {"disposition": "refuted", "reason": "forgoes a KO"}}),
                        encoding="utf-8")

    txt = build_report(log, tmp_path / "r.html", reviewed_path=reviewed).read_text(encoding="utf-8")
    assert "pill refuted" in txt and ">refuted<" in txt   # disposition badge rendered
    assert "by resolution" in txt                         # the new section
    assert "1 resolved" in txt and "0 open" in txt        # header split
    assert "http" not in txt                              # still offline


def test_report_marks_fixed_when_deck_tuned_and_no_longer_open(tmp_path):
    """REQ-BLUNDER-0011: a blunder whose deck has a proposals snapshot but is no longer in open[]
    (reconciliation dropped it — a rule satisfies it) is tagged fixed."""
    log = tmp_path / "c.jsonl"
    append_correction(_c("own", "missed_win", 100), log)
    proposals = tmp_path / "proposals"
    proposals.mkdir()
    (proposals / "mega_starmie.json").write_text(
        json.dumps({"deck": "mega_starmie", "open": [], "skipped": []}), encoding="utf-8")

    txt = build_report(log, tmp_path / "r.html", proposals_dir=proposals).read_text(encoding="utf-8")
    assert "pill fixed" in txt and "1 resolved" in txt


def test_report_unenriched_has_no_resolution_view(tmp_path):
    """REQ-BLUNDER-0011: omit ledger + proposals → legacy tag-trend output, no badges/section."""
    log = tmp_path / "c.jsonl"
    append_correction(_c("own", "missed_win", 100), log)
    txt = build_report(log, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "by resolution" not in txt and "class='pill" not in txt


# --- avg blunders per game (by build) ----------------------------------------------------------

def _fakec(source="own", build="b1", ep=1, built_at=None):
    return SimpleNamespace(source=source, agent_build=build, episode_id=ep, built_at=built_at)


def test_avg_blunders_per_game_normalizes_by_distinct_tagged_game():
    """REQ-BLUNDER-0012: avg = own blunders ÷ distinct tagged episodes, per build; peer excluded;
    two blunders in the same game count as one game (not two)."""
    stats = avg_blunders_per_game([
        _fakec(build="b1", ep=1), _fakec(build="b1", ep=1), _fakec(build="b1", ep=2),  # 3 / 2 games
        _fakec(build="b2", ep=5),                                                       # 1 / 1 game
        _fakec(source="peer", build="b1", ep=9),                                        # peer: ignored
    ])
    assert stats["b1"]["blunders"] == 3 and stats["b1"]["games"] == 2 and stats["b1"]["avg"] == 1.5
    assert stats["b2"]["avg"] == 1.0
    assert "peer" not in stats and stats["b1"]["blunders"] == 3        # peer not folded into b1



def test_report_renders_avg_blunders_per_game_section(tmp_path):
    """REQ-BLUNDER-0012: the offline report shows the avg-blunders-per-game graph with the ratio."""
    log = tmp_path / "c.jsonl"
    append_correction(_c("own", "missed_win", 100), log)
    append_correction(_c("own", "overextension", 100), log)     # same fixture episode → 1 game, 2 blunders
    txt = build_report(log, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "avg blunders per game" in txt
    assert "<b>2.0</b>" in txt                                  # 2 blunders / 1 distinct game
    assert "http" not in txt


# --- scoped corrections in the dashboard (ADR-0049) ---------------------------------------------

def _c_turn(rationale="develop before attacking"):
    return build_correction(_main(), source="own", agent="mega_starmie", submission_id=100,
                            correct=[], category="sequencing_error", rationale=rationale,
                            scope="turn", span=[{"frame": 5, "chosen_label": "Attack"}])


def test_a_still_open_turn_correction_is_not_reported_fixed(tmp_path):
    """ADR-0049: the proposals snapshot keys open blunders by the scope-aware `key`; matching on
    `<ep>-<frame>` would badge an unresolved Turn Correction as `fixed`."""
    log = tmp_path / "c.jsonl"
    turn = _c_turn()
    append_correction(turn, log)
    proposals = tmp_path / "proposals"
    proposals.mkdir()
    (proposals / "mega_starmie.json").write_text(json.dumps({
        "deck": "mega_starmie", "skipped": [],
        "open": [{"key": review_key(turn), "scope": "turn", "episode_id": turn.episode_id,
                  "frame": 5, "subject": 1}],
    }), encoding="utf-8")

    txt = build_report(log, tmp_path / "r.html", proposals_dir=proposals).read_text(encoding="utf-8")
    assert "pill open" in txt and "1 open" in txt
    assert "pill fixed" not in txt


def test_report_details_label_a_scoped_blunder_by_its_scope(tmp_path):
    """A Turn/Match Correction has no `correct` option, so the `chosen → correct` detail line is
    meaningless for it; the drill-down says what the blunder is ABOUT instead."""
    log = tmp_path / "c.jsonl"
    append_correction(_c_turn(rationale="the whole turn was misordered"), log)
    txt = build_report(log, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "turn scope" in txt and "1 decision" in txt      # what it's about + how much it spans
    assert "&rarr;" not in txt                              # no meaningless chosen -> correct arrow
    assert "the whole turn was misordered" in txt
    assert "http" not in txt
