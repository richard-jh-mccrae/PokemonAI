"""Per-build correction tree: corrections filed under data/corrections/<agent_build>/ for
competition-long traceability of which build had which corrections."""
from train.blunder.correction import build_correction
from train.blunder.decisions import Decision
from train.blunder.store import (append_correction, corrections_path_for, delete_correction,
                                 load_corrections)


def _c(*, build="mega_starmie_20260625_bde590c", episode=100, frame=9, correct=(1,)):
    d = Decision(episode_id=episode, frame=frame, seat=0, turn=1, select_context="Main",
                 select_type="Main", options=[{"type": 12}, {"type": 14}], chosen=[0], current={})
    return build_correction(d, source="own", agent="mega_starmie", correct=list(correct),
                            category="bad_retreat", rationale="r", agent_build=build)


def test_append_routes_to_the_build_subdir(tmp_path):
    """A correction lands in <root>/<agent_build>/corrections.jsonl (the dir name = the build)."""
    append_correction(_c(build="agentX_20260101_abc"), tmp_path)
    assert (tmp_path / "agentX_20260101_abc" / "corrections.jsonl").exists()
    assert corrections_path_for("agentX_20260101_abc", tmp_path) == \
        tmp_path / "agentX_20260101_abc" / "corrections.jsonl"


def test_no_build_goes_to_unfiled(tmp_path):
    """A correction with no parseable build identity is kept under _unfiled/."""
    append_correction(_c(build=None), tmp_path)
    assert (tmp_path / "_unfiled" / "corrections.jsonl").exists()


def test_load_unions_the_whole_tree(tmp_path):
    """Reading the root dir unions every build's log (the post-competition view)."""
    append_correction(_c(build="a_20260101_x", episode=1), tmp_path)
    append_correction(_c(build="b_20260102_y", episode=2), tmp_path)
    out = load_corrections(tmp_path)
    assert {c.episode_id for c in out} == {1, 2}
    assert {c.agent_build for c in out} == {"a_20260101_x", "b_20260102_y"}


def test_file_mode_is_still_supported(tmp_path):
    """An explicit .jsonl path addresses a single file (back-compat for callers/tests)."""
    f = tmp_path / "c.jsonl"
    append_correction(_c(episode=1), f)
    assert f.exists()
    assert len(load_corrections(f)) == 1


def test_delete_finds_the_correction_across_the_tree(tmp_path):
    """Deleting by id locates the right build file in the tree and rewrites it."""
    a = _c(build="a_20260101_x", episode=1)
    append_correction(a, tmp_path)
    append_correction(_c(build="b_20260102_y", episode=2), tmp_path)
    assert delete_correction(a.id, tmp_path) == 1
    assert {c.episode_id for c in load_corrections(tmp_path)} == {2}
