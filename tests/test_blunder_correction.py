"""Building and validating a Correction from a Decision."""
import pytest
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.correction import Correction, build_correction
from train.blunder.decisions import iter_decisions

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def _a_main_decision():
    """The first Main decision: frame 5, 5 options, chosen == [1]."""
    return next(d for d in iter_decisions(load_replay(FIXTURE)) if d.select_context == "Main")


def test_build_correction_embeds_snapshot_and_judgment():
    """REQ-BLUNDER-0004: a valid Correction auto-records `chosen`, takes the better
    legal option as `correct`, and embeds the self-contained Decision snapshot."""
    d = _a_main_decision()
    corr = build_correction(
        d, source="own", agent="mega_starmie",
        correct=[4], category="missed_win",          # position 4 (a different legal option)
        rationale="should have passed to keep the attach",
    )
    assert isinstance(corr, Correction)
    assert corr.chosen == d.chosen                    # auto from the replay
    assert corr.correct == [4]
    assert corr.category == "missed_win"
    assert corr.episode_id == d.episode_id and corr.seat == d.seat
    # embedded, self-contained snapshot
    assert corr.decision["select_context"] == "Main"
    assert corr.decision["current"]["players"]        # full board travels with it
    assert len(corr.decision["options"]) == len(d.options)


def test_correct_must_be_legal_and_differ_from_chosen():
    """REQ-BLUNDER-0004: `correct` must index real option positions and not equal `chosen`."""
    d = _a_main_decision()                             # positions 0..4, chosen [1]
    with pytest.raises(ValueError):
        build_correction(d, source="own", agent="x", correct=[9],
                         category="missed_win", rationale="r")          # out of range
    with pytest.raises(ValueError):
        build_correction(d, source="own", agent="x", correct=list(d.chosen),
                         category="missed_win", rationale="r")          # == chosen


def test_category_must_be_in_vocab():
    """REQ-BLUNDER-0004: category is validated against the closed vocabulary."""
    d = _a_main_decision()
    with pytest.raises(ValueError):
        build_correction(d, source="own", agent="x", correct=[4],
                         category="missed_lethal", rationale="r")       # renamed away


def test_correction_roundtrips_through_dict():
    """REQ-BLUNDER-0005: a Correction serializes to a plain dict and back,
    preserving identity (source / submission_id / agent_version) and judgment."""
    d = _a_main_decision()
    corr = build_correction(
        d, source="own", agent="mega_starmie",
        submission_id=12345, agent_version="abc1234", episode_time="2026-06-20T10:00:00Z",
        correct=[4], category="overextension", rationale="benched a third attacker for nothing",
    )
    back = Correction.from_dict(corr.to_dict())
    assert back == corr
    assert back.source == "own"
    assert back.submission_id == 12345 and back.agent_version == "abc1234"


def test_peer_source_supported_and_bad_source_rejected():
    """REQ-BLUNDER-0005: `source` is own|peer; peer carries an archetype label, bad source rejected."""
    d = _a_main_decision()
    peer = build_correction(d, source="peer", agent="Cinderace / Dragapult",
                            correct=[4], category="bad_target", rationale="hit the wall")
    assert peer.source == "peer" and peer.agent == "Cinderace / Dragapult"
    with pytest.raises(ValueError):
        build_correction(d, source="enemy", agent="x", correct=[4],
                         category="bad_target", rationale="r")
