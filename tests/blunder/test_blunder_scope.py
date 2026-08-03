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


def _decision(*, frame=9, turn=12, seat=0, episode=100, min_count=None):
    """The Anchor. ``min_count`` supplies the agent ``obs`` the select's ``minCount`` lives in —
    ``None`` means NO obs at all, the unreadable case a decision-scope decline must fail closed on."""
    obs = None if min_count is None else {
        "select": {"context": 0, "minCount": min_count, "maxCount": 1,
                   "option": [{"type": 12}, {"type": 14}]}}
    return Decision(episode_id=episode, frame=frame, seat=seat, turn=turn,
                    select_context="Main", select_type="Main",
                    options=[{"type": 12}, {"type": 14}], chosen=[0], current={}, obs=obs)


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
    """The atomic contract of ADR-0015 is untouched at `decision` scope, and an unknown scope raises.

    The Anchor here carries NO `obs`, so its `minCount` is unreadable — which is exactly the case
    Issue #229 rules must keep raising (D2a, fail closed). An unverifiable decline is the degenerate
    shape the relaxation exists to stop, not a case of it."""
    with pytest.raises(ValueError):
        build_correction(_decision(), source="own", agent="x", correct=[],
                         category="bad_target", rationale="r")            # decision needs a correct
    with pytest.raises(ValueError, match="scope"):
        build_correction(_decision(), source="own", agent="x", correct=[1],
                         category="bad_target", rationale="r", scope="game")


@pytest.mark.req("REQ-BLUNDER-0021")
def test_a_decision_scope_decline_is_recordable_on_an_optional_select():
    """Issue #229 / D1+D2. `correct: []` at `decision` scope is the ruling *"take none of these"* —
    the answer an OPTIONAL select exists to allow. The READER already speaks this language
    (`gates.satisfies_human` reads an empty `correct` as an exact-match DECLINE at every scope); only
    the writer refused it, so the corpus could not contain the shape its own grader grades."""
    corr = build_correction(_decision(min_count=0), source="own", agent="x", correct=[],
                            category="bad_target", rationale="taking any of these is worse")
    assert corr.scope == "decision" and corr.subject == 9
    assert corr.correct == []


@pytest.mark.req("REQ-BLUNDER-0021")
def test_a_mandatory_select_still_refuses_a_decision_scope_decline():
    """D2 — the narrowness that makes the relaxation safe. At a select the engine forces an answer
    to, "take none" is not a legal answer, so `correct: []` there is a MALFORMED record rather than a
    ruling. Same `minCount == 0` narrowness `records_a_decline_it_cannot_state` was built with."""
    with pytest.raises(ValueError, match="minCount"):
        build_correction(_decision(min_count=1), source="own", agent="x", correct=[],
                         category="bad_target", rationale="r")


@pytest.mark.req("REQ-BLUNDER-0021")
@pytest.mark.parametrize("obs", [None, {}, {"select": {}}, {"select": {"minCount": None}}])
def test_an_unprovable_optional_select_fails_closed(obs):
    """D2a. `Decision` carries no `minCount` field of its own and `snapshot()` omits it, so the only
    route to it is `obs["select"]["minCount"]` — and `obs` is None-able. Where it cannot be READ the
    old behaviour stands, which makes this a *strict* relaxation: a decline is admitted only where
    the optional select is provable, never merely assumed."""
    with pytest.raises(ValueError, match="minCount"):
        build_correction(_decision(), source="own", agent="x", correct=[],
                         category="bad_target", rationale="r", obs=obs)


@pytest.mark.req("REQ-BLUNDER-0021")
def test_the_validated_obs_is_the_obs_the_record_stores():
    """The `obs=` argument OVERRIDES the Anchor's own, and the stored record keeps the override — so
    validating against `decision.obs` while storing the override would let a record be admitted on
    evidence it does not carry. One read, used for both."""
    optional = {"select": {"context": 0, "minCount": 0, "maxCount": 1, "option": [{"type": 12}]}}
    corr = build_correction(_decision(min_count=1), source="own", agent="x", correct=[],
                            category="bad_target", rationale="r", obs=optional)
    assert corr.correct == [] and corr.obs is optional

    with pytest.raises(ValueError, match="minCount"):      # ...and the override can only TIGHTEN too
        build_correction(_decision(min_count=0), source="own", agent="x", correct=[],
                         category="bad_target", rationale="r",
                         obs={"select": {"minCount": 2, "maxCount": 2, "option": []}})


@pytest.mark.req("REQ-BLUNDER-0021")
def test_a_decision_scope_decline_round_trips_and_grades_exactly():
    """Acceptance 4. The shape must survive the store AND mean the same thing on the way out: an
    empty `correct` is matched EXACTLY, never by subset. Subset would be catastrophic here — the
    empty set is a subset of everything, so every frame would vacuously agree."""
    import sys
    from pathlib import Path
    sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "tools")]
    from train.gates import satisfies_human

    corr = build_correction(_decision(min_count=0), source="own", agent="x", correct=[],
                            category="bad_target", rationale="r")
    assert Correction.from_dict(corr.to_dict()) == corr
    assert Correction.from_dict(corr.to_dict()).correct == []
    assert satisfies_human([], []) is True                 # the agent declined too — satisfied
    assert satisfies_human([0], []) is False               # it took one anyway — NOT satisfied


@pytest.mark.req("REQ-BLUNDER-0021")
def test_the_other_two_scopes_contracts_are_untouched():
    """Acceptance 2 + 3. The relaxation is `decision`-only: `turn` still refuses a `correct` equal to
    `chosen`, and `match` still forbids a non-empty `correct` outright."""
    with pytest.raises(ValueError, match="first DIVERGENT"):
        build_correction(_decision(min_count=0), source="own", agent="x", correct=[0],
                         category="sequencing_error", rationale="r", scope="turn")
    with pytest.raises(ValueError, match="match-scope"):
        build_correction(_decision(min_count=0), source="own", agent="x", correct=[1],
                         category="slow_setup", rationale="r", scope="match")
    silent = build_correction(_decision(), source="own", agent="x", correct=[],
                              category="sequencing_error", rationale="r", scope="turn")
    assert silent.correct == []            # turn-scope silence never needed a readable `minCount`


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


@pytest.mark.req("REQ-BLUNDER-0021")
def test_the_tagging_pane_lets_a_human_record_a_decision_scope_decline():
    """The SECOND writer-side refusal, and the one that decides whether the shape is writable *by a
    human*. `build_correction` is the validator; this pane is the only thing that calls it for a
    ruling. It refused an empty `correct` at decision scope unconditionally, so relaxing the
    validator alone would leave the corpus exactly as unable to hold a decline as before — and a
    ruling nobody can type is not a ruling.

    Gated on the payload's `min_count`, so the pane's rule IS the validator's rule (D2), and a frame
    whose `min_count` is unknown keeps the old message (D2a)."""
    from train.blunder.shell import _SHELL_HTML
    # The save guard: an empty `correct` at decision scope is refused only where the select is NOT
    # provably optional — `!==0` so an unknown `min_count` keeps refusing, matching D2a exactly.
    assert "scope==='decision'&&!correct.length&&f.min_count!==0" in _SHELL_HTML
    # ...and the affordance is legible: a decline nobody knows they can type is not writable either.
    assert "FR[i].min_count===0" in _SHELL_HTML
    assert "<b>decline</b>" in _SHELL_HTML


@pytest.mark.req("REQ-BLUNDER-0020")
def test_shell_ui_offers_the_scope_selector_and_a_12px_pane():
    """The tagging pane defaults to 12px text, and a Scope selector picks what the tag is about —
    `correct` being optional off decision scope is the whole point of ADR-0049."""
    from train.blunder.shell import _SHELL_HTML
    assert "#right{width:400px;padding:14px;overflow:auto;font-size:12px}" in _SHELL_HTML
    assert 'id="scope"' in _SHELL_HTML
    assert "this decision" in _SHELL_HTML and "whole match" in _SHELL_HTML
    assert "scope:$('scope').value" in _SHELL_HTML          # posted with the tag
