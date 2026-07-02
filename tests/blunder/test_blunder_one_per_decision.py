"""One Correction per decision: the inspector refuses a second tag on the same (episode, seat, frame)."""
import pytest
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.decisions import iter_decisions
from train.blunder.service import record_correction

REPLAY = FIXTURES / "replays" / "mega_starmie_20260625_bde590c" / "episode-81903490-replay.json.gz"


def _taggable(replay):
    return next(d for d in iter_decisions(replay)
                if len(d.options) >= 2 and all(0 <= c < len(d.options) for c in d.chosen))


def _other(d):
    return next(i for i in range(len(d.options)) if i not in d.chosen)


def test_second_correction_on_the_same_decision_is_rejected(tmp_path):
    """A different judgment on a decision already tagged raises — the conflict can't be created."""
    replay = load_replay(REPLAY)
    d = _taggable(replay)
    store = tmp_path / "c.jsonl"
    record_correction(replay, frame=d.frame, correct=[_other(d)], category="bad_target",
                      rationale="first", source="own", agent="x", store_path=store)
    with pytest.raises(ValueError, match="already exists at this decision"):
        record_correction(replay, frame=d.frame, correct=[_other(d)], category="sequencing_error",
                          rationale="second", source="own", agent="x", store_path=store)


def test_editing_the_same_decision_is_allowed_via_replace_id(tmp_path):
    """The edit flow passes the id being replaced, so refining an existing tag is not blocked."""
    replay = load_replay(REPLAY)
    d = _taggable(replay)
    store = tmp_path / "c.jsonl"
    first = record_correction(replay, frame=d.frame, correct=[_other(d)], category="bad_target",
                              rationale="first", source="own", agent="x", store_path=store)
    record_correction(replay, frame=d.frame, correct=[_other(d)], category="bad_target",
                      rationale="edited", source="own", agent="x", store_path=store,
                      replace_id=first.id)        # no raise — replacing the one being edited
