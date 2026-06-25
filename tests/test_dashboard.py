"""Dashboard renders a self-contained HTML file from the store."""
from meta_tracker.dashboard import _merge_map, build_dashboard
from meta_tracker.store import connect, upsert_episode
from test_store import _rec


def _ep(a0, m0, a1="X", m1=("X",)):
    return {"arch0": a0, "mains0": list(m0), "arch1": a1, "mains1": list(m1)}


def test_subset_merge_folds_into_fullest():
    eps = [_ep("A / B", ["A", "B"]), _ep("A / B / C", ["A", "B", "C"])]
    m = _merge_map(eps)
    assert m["A / B"] == "A / B / C"          # subset sharing primary A -> fullest
    assert m["A / B / C"] == "A / B / C"      # superset maps to itself
    assert m["X"] == "X"


def test_no_merge_when_primary_differs():
    # {B} is a subset of {A,B,C} but its primary (B) != the superset's primary (A).
    eps = [_ep("B", ["B"]), _ep("A / B / C", ["A", "B", "C"])]
    assert _merge_map(eps)["B"] == "B"


def test_empty_store_writes_placeholder(tmp_path):
    out = build_dashboard(db_path=tmp_path / "e.db", out_path=tmp_path / "d.html")
    assert out.exists() and "No episodes" in out.read_text(encoding="utf-8")


def test_dashboard_self_contained(tmp_path):
    db = tmp_path / "m.db"
    conn = connect(db)
    for i in range(1, 6):
        r = _rec(i)
        r.winner_index = i % 2
        upsert_episode(conn, r, "2026-06-22")
    conn.close()
    out = build_dashboard(db_path=db, out_path=tmp_path / "d.html")
    txt = out.read_text(encoding="utf-8")
    assert "Mega Starmie ex" in txt
    assert "Plotly" in txt                         # plotly.js inlined -> offline-capable
    assert '<script src="https://cdn.plot' not in txt  # not loaded from a CDN
    assert "<details>" in txt and "<summary>" in txt   # expandable decklists
    assert "Pokémon (" in txt and "Staryu" in txt      # full card list rendered
