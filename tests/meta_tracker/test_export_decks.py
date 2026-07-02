"""Meta-tracker deck export: store -> data/meta/decks/<slug>/ + index.json (ADR-0027).

Offline. Builds a synthetic store of real legal decks, exports, and asserts the
menu (ranking + covers) and the shipped files (legal deck.csv, round-tripping deck.txt).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from deck_convert import _indexes, check_legality, resolve_deck  # noqa: E402
from meta_tracker.export_decks import export_decks, run, slugify  # noqa: E402
from meta_tracker.parse import EpisodeRecord  # noqa: E402
from meta_tracker.store import connect, upsert_episode  # noqa: E402

NOW = "2026-06-23T00:00:00"
BY_NORM = _indexes()[0]
WATER = 3  # Basic {W} Energy (unlimited)


def _legal(basic_name: str) -> list[int]:
    """A legal 60: one real Basic Pokémon + 59 basic Water Energy."""
    return [BY_NORM[basic_name][0]] + [WATER] * 59


DECK_A = _legal("staryu")
DECK_B = _legal("eevee")


def _rec(eid, *, arch, mains, deck, arch1="Other", mains1=("Other",), deck1=None,
         winner_index=None, end_time="2026-06-20T00:00:00", band="Mid") -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=eid, band=band, created_at=end_time, end_time=end_time,
        team0="T0", team1="T1", winner_index=winner_index, sampled_index=0,
        sampled_rating=1000.0, sampled_sub_date=end_time, sampled_episodes=1,
        deck0=deck, deck1=(deck1 if deck1 is not None else deck),
        arch0=arch, arch1=arch1, mains0=list(mains), mains1=list(mains1),
        subs0=[], subs1=[], energy0=[], energy1=[])


def _store(tmp_path, recs) -> Path:
    db = tmp_path / "m.db"
    conn = connect(db)
    for r in recs:
        upsert_episode(conn, r, "2026-06-22")
    conn.close()
    return db


def test_exports_top_cluster_as_legal_deck(tmp_path):
    db = _store(tmp_path, [
        _rec(i, arch="Cinderace / Mega Starmie ex", mains=["Cinderace", "Mega Starmie ex"],
             deck=DECK_A, arch1="Alakazam", mains1=["Alakazam"], deck1=DECK_B)
        for i in range(3)
    ])
    run(db_path=db, out_dir=tmp_path / "decks", top_n=10, now=NOW)

    csv = tmp_path / "decks" / "cinderace_mega_starmie_ex" / "deck.csv"
    ids = [int(x) for x in csv.read_text(encoding="utf-8").split()]
    assert len(ids) == 60 and check_legality(ids) == []


def _mirror(eid, name, n, *, deck=DECK_A, winner_index=None):
    """n mirror episodes of one archetype (it appears on both sides)."""
    return [_rec(eid + i, arch=name, mains=[name], deck=deck,
                 arch1=name, mains1=[name], deck1=deck, winner_index=winner_index)
            for i in range(n)]


def test_deck_txt_round_trips(tmp_path):
    db = _store(tmp_path, _mirror(0, "Alpha", 2))
    run(db_path=db, out_dir=tmp_path / "decks", top_n=10, now=NOW)

    d = tmp_path / "decks" / "alpha"
    csv_ids = sorted(int(x) for x in (d / "deck.csv").read_text(encoding="utf-8").split())
    back, problems = resolve_deck((d / "deck.txt").read_text(encoding="utf-8"))
    assert problems == []
    assert sorted(back) == csv_ids


def test_top_n_cap_and_play_rate_order(tmp_path):
    db = _store(tmp_path, _mirror(0, "Beta", 3) + _mirror(10, "Gamma", 2) + _mirror(20, "Delta", 1))
    idx = run(db_path=db, out_dir=tmp_path / "decks", top_n=2, now=NOW)

    assert [r["label"] for r in idx] == ["Beta", "Gamma"]      # by play-rate, Delta cut
    assert [r["rank"] for r in idx] == [1, 2]
    assert not (tmp_path / "decks" / "delta").exists()


def test_covers_lists_merged_variant_members(tmp_path):
    # "Core" (1-main) and "Core / Tech" (2-main) share primary Core -> one cluster.
    recs = _mirror(0, "Core", 3) + [
        _rec(10, arch="Core / Tech", mains=["Core", "Tech"], deck=DECK_A,
             arch1="Core / Tech", mains1=["Core", "Tech"], deck1=DECK_A)]
    idx = run(db_path=_store(tmp_path, recs), out_dir=tmp_path / "decks", top_n=10, now=NOW)

    assert len(idx) == 1                                       # merged into one cluster
    assert idx[0]["label"] == "Core"                          # most common member labels it
    assert idx[0]["covers"] == ["Core", "Core / Tech"]        # both members routed to the Brief


def test_index_row_schema_and_winrate(tmp_path):
    db = _store(tmp_path, _mirror(0, "Solo", 4, winner_index=0))
    idx = run(db_path=db, out_dir=tmp_path / "decks", top_n=10, now=NOW)

    row = idx[0]
    assert set(row) == {"rank", "slug", "label", "covers", "play_rate", "win_rate", "episodes"}
    assert row["slug"] == "solo" and row["label"] == "Solo"
    assert row["play_rate"] == 1.0 and row["episodes"] == 4
    assert row["win_rate"] == 0.5                             # mirror: 4 wins / 8 decided sides
    assert json.loads((tmp_path / "decks" / "index.json").read_text(encoding="utf-8")) == idx


def test_slugify_normalizes():
    assert slugify("Cinderace / Mega Starmie ex") == "cinderace_mega_starmie_ex"
    assert slugify("Hop's Trevenant") == "hop_s_trevenant"


def test_slug_collision_raises(tmp_path):
    # two distinct labels that slug identically -> hard error, not a silent overwrite
    recs = _mirror(0, "Core Tech", 1) + _mirror(10, "Core/Tech", 1)
    with pytest.raises(ValueError, match="collision"):
        run(db_path=_store(tmp_path, recs), out_dir=tmp_path / "decks", top_n=10, now=NOW)


def test_malformed_deck_is_skipped(tmp_path):
    bad = [BY_NORM["staryu"][0], WATER]                       # 2 cards -> illegal
    recs = _mirror(0, "Good", 2) + [
        _rec(10, arch="Bad", mains=["Bad"], deck=bad, arch1="Bad", mains1=["Bad"], deck1=bad)]
    idx = run(db_path=_store(tmp_path, recs), out_dir=tmp_path / "decks", top_n=10, now=NOW)

    assert [r["label"] for r in idx] == ["Good"]              # Bad skipped
    assert not (tmp_path / "decks" / "bad").exists()


def test_empty_store_writes_empty_index(tmp_path):
    idx = run(db_path=_store(tmp_path, []), out_dir=tmp_path / "decks", top_n=10, now=NOW)
    assert idx == []
    assert json.loads((tmp_path / "decks" / "index.json").read_text(encoding="utf-8")) == []
