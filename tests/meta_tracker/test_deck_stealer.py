"""deck_stealer copies a named team's exact 60-card deck out of a replay (ADR-0005).

Offline: drives the gzipped keidroid-vs-Jaga sample replay; no Kaggle network.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from deck_stealer import StealError, steal  # noqa: E402
from meta_tracker.parse import parse_replay  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "episode-81364540-replay.json.gz"


def _expected(team: str) -> list[int]:
    """That team's deck as parse.py reads it, sorted -- the ground truth to match."""
    rec = parse_replay(FIXTURE, sampled_team=team)
    idx = [rec.team0, rec.team1].index(team)
    return sorted(rec.deck0 if idx == 0 else rec.deck1)


@pytest.mark.req("REQ-STEAL-0001")
def test_writes_named_teams_exact_sorted_60(tmp_path):
    p = steal(FIXTURE, "keidroid", "stolen", dest_root=tmp_path)
    ids = [int(x) for x in (p["dest"] / "deck.csv").read_text().split()]
    assert len(ids) == 60
    assert ids == sorted(ids)            # canonical order
    assert ids == _expected("keidroid")  # correct side, exact list


@pytest.mark.req("REQ-STEAL-0001")
def test_selects_the_right_side(tmp_path):
    # Each team's stolen file must match *its own* deck, not the opponent's.
    k = steal(FIXTURE, "keidroid", "k", dest_root=tmp_path)["dest"] / "deck.csv"
    j = steal(FIXTURE, "Jaga", "j", dest_root=tmp_path)["dest"] / "deck.csv"
    assert [int(x) for x in k.read_text().split()] == _expected("keidroid")
    assert [int(x) for x in j.read_text().split()] == _expected("Jaga")


@pytest.mark.req("REQ-STEAL-0001")
def test_unknown_team_lists_available_names(tmp_path):
    with pytest.raises(StealError) as e:
        steal(FIXTURE, "Nobody", "x", dest_root=tmp_path)
    assert "keidroid" in str(e.value) and "Jaga" in str(e.value)


@pytest.mark.req("REQ-STEAL-0001")
def test_refuses_existing_dir_unless_force(tmp_path):
    (tmp_path / "dup").mkdir()
    with pytest.raises(StealError):
        steal(FIXTURE, "keidroid", "dup", dest_root=tmp_path)
    p = steal(FIXTURE, "keidroid", "dup", force=True, dest_root=tmp_path)
    assert (p["dest"] / "deck.csv").exists()


@pytest.mark.req("REQ-STEAL-0001")
def test_missing_replay_errors(tmp_path):
    with pytest.raises(StealError):
        steal(tmp_path / "nope.json", "keidroid", "x", dest_root=tmp_path)
