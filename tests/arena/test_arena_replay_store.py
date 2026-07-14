"""Arena replay store: PvC replays saved like the Self-play Corpus (tagged cabt JSON),
with the Arena's metadata in the info block; the Rating patched in post-game.

Offline, pure-dict. The file must stay one self-contained artifact (ADR-0058) so the
SSH pull is a bare rsync.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from arena import replay_store  # noqa: E402

req = pytest.mark.req("REQ-ARENA-0002")


def _fake_replay():
    return {"name": "cabt", "info": {}, "rewards": [1, -1],
            "statuses": ["DONE", "DONE"], "steps": [[{"action": []}, {"action": []}]]}


@req
def test_save_tags_episode_id_team_names_and_pvc_block(tmp_path):
    path = replay_store.save_replay(
        _fake_replay(), tmp_path, agent="mega_starmie", visitor="Rich",
        human_seat=1, stamp="20260702-120000")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert path.parent == tmp_path and path.suffix == ".json"
    assert isinstance(saved["info"]["EpisodeId"], int)
    assert saved["info"]["TeamNames"] == ["mega_starmie", "Rich"]   # seat order
    pvc = saved["info"]["pvc"]
    assert pvc["visitor"] == "Rich" and pvc["agent"] == "mega_starmie"
    assert pvc["human_seat"] == 1 and pvc["rating"] is None
    assert saved["steps"] == _fake_replay()["steps"]                # replay untouched


@req
def test_forfeit_marks_abandoned(tmp_path):
    path = replay_store.save_replay(
        _fake_replay(), tmp_path, agent="mega_starmie", visitor=None,
        human_seat=0, forfeit="timeout", stamp="20260702-120001")
    pvc = json.loads(path.read_text(encoding="utf-8"))["info"]["pvc"]
    assert pvc["forfeit"] == "timeout" and pvc["abandoned"] is True
    assert pvc["visitor"] is None


@req
def test_clean_finish_is_not_abandoned(tmp_path):
    path = replay_store.save_replay(
        _fake_replay(), tmp_path, agent="mega_starmie", visitor="Rich",
        human_seat=0, stamp="20260702-120002")
    pvc = json.loads(path.read_text(encoding="utf-8"))["info"]["pvc"]
    assert pvc["forfeit"] is None and pvc["abandoned"] is False


@req
def test_same_second_saves_never_collide(tmp_path):
    a = replay_store.save_replay(_fake_replay(), tmp_path, agent="mega_starmie",
                                 visitor="A", human_seat=0, stamp="20260702-120010")
    b = replay_store.save_replay(_fake_replay(), tmp_path, agent="mega_starmie",
                                 visitor="B", human_seat=0, stamp="20260702-120010")
    assert a != b                                       # no silent overwrite
    ids = {json.loads(p.read_text(encoding="utf-8"))["info"]["EpisodeId"]
           for p in (a, b)}
    assert len(ids) == 2                                # EpisodeIds stay unique too


@req
def test_patch_rating_lands_in_pvc_and_touches_nothing_else(tmp_path):
    path = replay_store.save_replay(
        _fake_replay(), tmp_path, agent="mega_starmie", visitor="Rich",
        human_seat=0, stamp="20260702-120003")
    before = json.loads(path.read_text(encoding="utf-8"))
    rating = {"misplay": "kept attacking the wall", "phase": "mid", "comments": ""}
    replay_store.patch_rating(path, rating)
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["info"]["pvc"]["rating"] == rating
    after["info"]["pvc"]["rating"] = None
    assert after == before
