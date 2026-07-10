"""Correction Scope (ADR-0049): a Correction is about a Decision, a Turn, or a Match.

Scope is orthogonal to Category. Off `decision` scope the record is keyed by its Scope's
subject (not the Anchor frame), `correct` is optional and Anchor-indexed, and the Span of
covered Decisions travels with the record.
"""
import pytest
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.correction import SCOPES, Correction, build_correction
from train.blunder.decisions import Decision
from train.blunder.service import record_correction

REPLAY = FIXTURES / "episode-81364540-replay.json.gz"
# seat 0's turn 1 is 6 Decisions starting at frame 5; turn 0 is the setup phase BOTH seats act in.
ANCHOR, TURN, SEAT, SPAN_LEN = 5, 1, 0, 6


def _decision(*, frame=9, turn=12, seat=0, episode=100):
    return Decision(episode_id=episode, frame=frame, seat=seat, turn=turn,
                    select_context="Main", select_type="Main",
                    options=[{"type": 12}, {"type": 14}], chosen=[0], current={})


@pytest.mark.req("REQ-BLUNDER-0017")
def test_scope_vocabulary_and_decision_is_the_default():
    """A Correction without a scope is a decision Correction, and its subject is the Anchor frame —
    so all 290 pre-ADR-0049 records load with their identity unchanged."""
    assert SCOPES == ("decision", "turn", "match")
    corr = build_correction(_decision(), source="own", agent="x", correct=[1],
                            category="bad_target", rationale="r")
    assert corr.scope == "decision"
    assert corr.subject == 9                       # the Anchor frame
    assert corr.span is None

    legacy = corr.to_dict()
    legacy.pop("scope"), legacy.pop("subject"), legacy.pop("span")
    back = Correction.from_dict(legacy)
    assert back.scope == "decision" and back.subject == 9 and back.span is None


@pytest.mark.req("REQ-BLUNDER-0017")
def test_turn_scope_subject_is_the_turn_and_correct_is_optional():
    """A Turn Correction is keyed by its Turn; `correct` may be silent (the intended line is prose)."""
    span = [{"frame": 8, "chosen_label": "Play Poffin"}, {"frame": 9, "chosen_label": "Attack"}]
    prose = build_correction(_decision(), source="own", agent="x", correct=[],
                             category="sequencing_error", rationale="develop before attacking",
                             scope="turn", span=span)
    assert prose.scope == "turn"
    assert prose.subject == 12                     # the Turn, not the frame
    assert prose.correct == []
    assert prose.span == span
    assert Correction.from_dict(prose.to_dict()) == prose


@pytest.mark.req("REQ-BLUNDER-0017")
def test_turn_scope_correct_indexes_the_anchor_and_must_diverge():
    """When a Turn Correction does name a `correct` option it asserts the Anchor is the first
    divergent Decision — so it must index the Anchor's options and differ from `chosen`."""
    ok = build_correction(_decision(), source="own", agent="x", correct=[1],
                          category="sequencing_error", rationale="r", scope="turn")
    assert ok.correct == [1] and ok.subject == 12

    with pytest.raises(ValueError):                # out of the Anchor's option range
        build_correction(_decision(), source="own", agent="x", correct=[7],
                         category="sequencing_error", rationale="r", scope="turn")
    with pytest.raises(ValueError):                # identical to `chosen` — asserts nothing
        build_correction(_decision(), source="own", agent="x", correct=[0],
                         category="sequencing_error", rationale="r", scope="turn")


@pytest.mark.req("REQ-BLUNDER-0017")
def test_match_scope_has_no_subject_and_forbids_correct():
    """A Match Correction is keyed by (episode, seat) alone, and cannot name a `correct` option:
    no single `select` carries a whole-match verdict. The intended line is `rationale` prose."""
    corr = build_correction(_decision(), source="own", agent="x", correct=[],
                            category="slow_setup", rationale="never developed the Ignition line",
                            scope="match")
    assert corr.scope == "match" and corr.subject is None
    with pytest.raises(ValueError, match="match-scope"):
        build_correction(_decision(), source="own", agent="x", correct=[1],
                         category="slow_setup", rationale="r", scope="match")


@pytest.mark.req("REQ-BLUNDER-0017")
def test_decision_scope_still_requires_correct_and_scope_is_validated():
    """The atomic contract of ADR-0015 is untouched at `decision` scope, and an unknown scope raises."""
    with pytest.raises(ValueError):
        build_correction(_decision(), source="own", agent="x", correct=[],
                         category="bad_target", rationale="r")            # decision needs a correct
    with pytest.raises(ValueError, match="scope"):
        build_correction(_decision(), source="own", agent="x", correct=[1],
                         category="bad_target", rationale="r", scope="game")


@pytest.mark.req("REQ-BLUNDER-0018")
def test_turn_span_is_the_turns_decisions_carrying_obs_and_no_board(tmp_path):
    """ADR-0049: a Turn Correction embeds every Decision that seat made in the Turn, each with the
    agent `obs` that makes it re-drivable — but no per-Decision `current` (the Anchor carries one
    board; a full board per Decision would be ~10 KB each for a human view nothing reads)."""
    corr = record_correction(load_replay(REPLAY), frame=ANCHOR, correct=[], scope="turn",
                             category="sequencing_error", rationale="develop before attacking",
                             source="own", agent="mega_starmie", store_path=tmp_path / "c.jsonl")
    assert corr.scope == "turn" and corr.subject == TURN
    assert len(corr.span) == SPAN_LEN
    assert [s["frame"] for s in corr.span] == sorted(s["frame"] for s in corr.span)
    assert corr.span[0]["frame"] == ANCHOR and corr.span[0]["select_context"] == "Main"
    assert all(s["obs"] is not None for s in corr.span)          # re-drivable
    assert all(s["chosen_label"] for s in corr.span)             # the played line, legible
    assert all("current" not in s for s in corr.span)            # no per-Decision board
    assert corr.decision["current"]["players"]                   # ...the Anchor still carries one


@pytest.mark.req("REQ-BLUNDER-0018")
def test_match_span_is_per_turn_headers_for_both_seats_without_obs(tmp_path):
    """A Match Correction is doctrine, not a re-drivable line: its Span is per-Turn headers — both
    seats, so the opponent's turns are legible — and carries no `obs`."""
    corr = record_correction(load_replay(REPLAY), frame=ANCHOR, correct=[], scope="match",
                             category="slow_setup", rationale="never developed the wincon",
                             source="own", agent="mega_starmie", store_path=tmp_path / "c.jsonl")
    assert corr.scope == "match" and corr.subject is None
    assert [(s["seat"], s["turn"]) for s in corr.span] == [(0, 0), (1, 0), (0, 1), (1, 2), (0, 3)]
    assert all("obs" not in s for s in corr.span)
    own = next(s for s in corr.span if s["seat"] == SEAT and s["turn"] == TURN)
    assert len(own["chosen_labels"]) == SPAN_LEN and own["frames"][0] == ANCHOR
    assert "game_plan" in own                                    # None here: no live trace supplied


@pytest.mark.req("REQ-BLUNDER-0019")
def test_one_correction_per_subject_not_per_frame(tmp_path):
    """The guard keys on the Scope's subject: a second Turn Correction on the same Turn is refused
    even from a different Anchor, while a Decision Correction inside that Turn is a distinct blunder."""
    replay, store = load_replay(REPLAY), tmp_path / "c.jsonl"
    kw = dict(source="own", agent="mega_starmie", store_path=store)
    record_correction(replay, frame=ANCHOR, correct=[], scope="turn",
                      category="sequencing_error", rationale="first", **kw)
    with pytest.raises(ValueError, match="already exists at this turn"):
        record_correction(replay, frame=ANCHOR + 1, correct=[], scope="turn",   # different Anchor
                          category="slow_setup", rationale="second", **kw)

    record_correction(replay, frame=ANCHOR, correct=[4], category="missed_win",  # decision scope
                      rationale="inside the same turn", **kw)
    record_correction(replay, frame=ANCHOR, correct=[], scope="match",
                      category="slow_setup", rationale="whole match", **kw)
    with pytest.raises(ValueError, match="already exists at this match"):
        record_correction(replay, frame=ANCHOR + 1, correct=[], scope="match",
                          category="overextension", rationale="again", **kw)


@pytest.mark.req("REQ-BLUNDER-0020")
def test_list_corrections_reports_each_tags_scope_and_subject(tmp_path):
    """The inspector's logged-blunders list must distinguish a Turn Correction from the Decision
    Corrections inside that Turn — otherwise the two read as duplicate rows on the same step."""
    from train.blunder.service import list_corrections
    replay, store = load_replay(REPLAY), tmp_path / "c.jsonl"
    kw = dict(source="own", agent="mega_starmie", store_path=store)
    record_correction(replay, frame=ANCHOR, correct=[], scope="turn",
                      category="sequencing_error", rationale="t", **kw)
    record_correction(replay, frame=ANCHOR, correct=[4], category="missed_win", rationale="d", **kw)

    listed = {(it["scope"], it["subject"]) for it in list_corrections(replay, store)}
    assert listed == {("turn", TURN), ("decision", ANCHOR)}


@pytest.mark.req("REQ-BLUNDER-0020")
def test_shell_ui_offers_the_scope_selector_and_a_12px_pane():
    """The tagging pane defaults to 12px text, and a Scope selector picks what the tag is about —
    `correct` being optional off decision scope is the whole point of ADR-0049."""
    from train.blunder.shell import _SHELL_HTML
    assert "#right{width:400px;padding:14px;overflow:auto;font-size:12px}" in _SHELL_HTML
    assert 'id="scope"' in _SHELL_HTML
    assert "this decision" in _SHELL_HTML and "whole match" in _SHELL_HTML
    assert "scope:$('scope').value" in _SHELL_HTML          # posted with the tag
