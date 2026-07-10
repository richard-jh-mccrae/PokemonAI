"""Deduplicating the Correction log: collapse exact duplicates, keep conflicts and patterns."""
from train.blunder.correction import build_correction
from train.blunder.decisions import Decision
from train.blunder.store import (append_correction, dedup_corrections, find_conflicts,
                                 load_corrections)


def _c(*, frame=9, category="bad_retreat", correct=(1,), rationale="r", episode=100, seat=0,
       turn=1, scope="decision"):
    d = Decision(episode_id=episode, frame=frame, seat=seat, turn=turn, select_context="Main",
                 select_type="Main", options=[{"type": 12}, {"type": 14}], chosen=[0], current={})
    return build_correction(d, source="own", agent="mega_starmie", correct=list(correct),
                            category=category, rationale=rationale, scope=scope)


def test_dedup_collapses_exact_duplicates_keeping_the_latest():
    """Same episode/seat/frame/chosen/correct/category = one blunder; keep the latest (refined rationale)."""
    out = dedup_corrections([_c(rationale="first"), _c(rationale="refined")])
    assert len(out) == 1
    assert out[0].rationale == "refined"


def test_dedup_keeps_a_conflict_same_decision_different_judgment():
    """Same decision tagged with a different category/correct is a CONFLICT, not a duplicate."""
    assert len(dedup_corrections([_c(category="bad_retreat"), _c(category="misattachment")])) == 2
    assert len(dedup_corrections([_c(correct=(1,)), _c(correct=(0,) if False else (1,))])) == 1  # same -> 1


def test_dedup_keeps_the_same_pattern_in_different_episodes():
    """The same frame in a different game is a distinct blunder (the valuable, generalizing signal)."""
    assert len(dedup_corrections([_c(episode=100), _c(episode=200)])) == 2


def test_find_conflicts_flags_one_decision_tagged_two_ways():
    """A decision with two different judgments (category/correct) is a conflict to resolve, not a dup."""
    conflicts = find_conflicts([_c(category="bad_retreat"), _c(category="misattachment"),
                                _c(episode=200)])          # the ep-200 one is unrelated
    assert len(conflicts) == 1
    (_key, members), = conflicts
    assert {m.category for m in members} == {"bad_retreat", "misattachment"}


def test_dedup_keys_a_turn_correction_by_its_turn_not_its_anchor_frame():
    """ADR-0049: the same Turn tagged from two different Anchor frames is ONE Turn Correction —
    identity is the Scope's subject. A Decision Correction inside that Turn is a different blunder."""
    from_f9 = _c(scope="turn", turn=4, frame=9, rationale="first")
    from_f14 = _c(scope="turn", turn=4, frame=14, rationale="refined")
    assert len(dedup_corrections([from_f9, from_f14])) == 1                 # one Turn, one blunder
    assert dedup_corrections([from_f9, from_f14])[0].rationale == "refined"

    inside = _c(scope="decision", turn=4, frame=9)                          # coexists with the Turn
    assert len(dedup_corrections([from_f9, inside])) == 2
    assert len(dedup_corrections([_c(scope="turn", turn=4), _c(scope="turn", turn=6)])) == 2


def test_dedup_keys_a_match_correction_by_episode_and_seat():
    """A Match Correction has no subject: one per (episode, seat), regardless of where it was tagged."""
    a = _c(scope="match", correct=(), frame=3, rationale="first")
    b = _c(scope="match", correct=(), frame=40, rationale="refined")
    assert len(dedup_corrections([a, b])) == 1
    assert len(dedup_corrections([a, _c(scope="match", correct=(), seat=1)])) == 2   # other seat


def test_load_corrections_dedups_by_default_with_raw_opt_out(tmp_path):
    """Every consumer reads a deduped log by default; dedup=False yields the raw append history."""
    p = tmp_path / "c.jsonl"
    append_correction(_c(rationale="first"), p)
    append_correction(_c(rationale="refined"), p)
    assert len(load_corrections(p)) == 1
    assert load_corrections(p)[0].rationale == "refined"
    assert len(load_corrections(p, dedup=False)) == 2
