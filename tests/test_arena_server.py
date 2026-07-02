"""Arena web layer: REST (presets, deck check, tables, rating) + the match WebSocket.

Runs against the fake worker (protocol-faithful, env-free); the real engine path
is covered by test_arena_worker / test_arena_system.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
pytest.importorskip("fastapi")
pytest.importorskip("httpx")               # TestClient needs it; missing = RuntimeError
from fastapi.testclient import TestClient  # noqa: E402

from arena.server import create_app  # noqa: E402

req = pytest.mark.req("REQ-ARENA-0006")

REPO = Path(__file__).resolve().parents[1]
FAKE_WORKER = Path(__file__).resolve().parent / "fixtures" / "arena" / "fake_worker.py"
MEGA_TXT = (REPO / "src" / "agents" / "mega_starmie" / "deck.txt").read_text(encoding="utf-8")


def _client(tmp_path, **kw):
    kw.setdefault("worker_cmd", [sys.executable, str(FAKE_WORKER)])
    kw.setdefault("replay_dir", tmp_path)
    kw.setdefault("images_dir", Path(tmp_path) / "no-images")   # tests: none fetched
    return TestClient(create_app(**kw))


@req
def test_presets_endpoint_lists_the_gallery(tmp_path):
    with _client(tmp_path) as client:
        presets = client.get("/api/presets").json()["presets"]
        assert any(p["id"] == "mega_starmie" for p in presets)


@req
def test_deck_check_reports_problems_whole(tmp_path):
    with _client(tmp_path) as client:
        ok = client.post("/api/deck", json={"text": MEGA_TXT}).json()
        assert ok["ok"] is True and ok["cards"] == 60
        bad = client.post("/api/deck",
                          json={"text": "4 Special Red Card CRI 82\n"}).json()
        assert bad["ok"] is False and bad["problems"]


@req
def test_full_visit_play_rate_flow(tmp_path):
    with _client(tmp_path) as client:
        r = client.post("/api/tables", json={"visitor": "Rich", "preset": "mega_starmie"})
        assert r.status_code == 200, r.text
        table_id = r.json()["table_id"]

        with client.websocket_connect(f"/ws/{table_id}") as ws:
            first = ws.receive_json()
            assert first["type"] == "state" and "view" in first
            ws.send_text(json.dumps({"type": "choose", "indices": [0]}))
            assert ws.receive_json()["type"] == "state"
            ws.send_text(json.dumps({"type": "choose", "indices": [0]}))
            end = ws.receive_json()
            assert end["type"] == "end"

        r = client.post(f"/api/tables/{table_id}/rating", json={
            "misplay": "attacked the wall all game", "phase": "mid", "comments": ""})
        assert r.status_code == 200
        replays = list(Path(tmp_path).glob("*.json"))
        assert replays
        saved = json.loads(replays[0].read_text(encoding="utf-8"))
        assert saved["info"]["pvc"]["rating"]["misplay"] == "attacked the wall all game"


@req
def test_full_tables_turn_visitors_away(tmp_path):
    with _client(tmp_path, cap=1) as client:
        assert client.post("/api/tables",
                           json={"preset": "mega_starmie"}).status_code == 200
        r = client.post("/api/tables", json={"preset": "mega_starmie"})
        assert r.status_code == 409


@req
def test_rating_needs_a_finished_match(tmp_path):
    with _client(tmp_path) as client:
        table_id = client.post("/api/tables",
                               json={"preset": "mega_starmie"}).json()["table_id"]
        r = client.post(f"/api/tables/{table_id}/rating", json={"misplay": "x"})
        assert r.status_code == 409


@req
def test_bad_deck_text_is_rejected_at_table_creation(tmp_path):
    with _client(tmp_path) as client:
        r = client.post("/api/tables", json={"deck_text": "4 Special Red Card CRI 82\n"})
        assert r.status_code == 400
        assert r.json()["problems"]


# --- the in-app builder API ----------------------------------------------------

@req
def test_cards_endpoint_serves_the_pool_catalog(tmp_path):
    with _client(tmp_path) as client:
        cards = client.get("/api/cards").json()["cards"]
        assert len(cards) > 1000
        staryu = next(c for c in cards if c["name"] == "Staryu")
        assert staryu["attacks"][0]["cost"] == ["Water"]


@req
def test_cards_endpoint_flags_available_images_and_serves_them(tmp_path):
    from deck_convert import _indexes
    staryu = _indexes()[0]["staryu"][0]
    imgdir = tmp_path / "imgs"
    imgdir.mkdir()
    (imgdir / f"{staryu}.png").write_bytes(b"fake-png")
    with _client(tmp_path, images_dir=imgdir) as client:
        cards = client.get("/api/cards").json()["cards"]
        by_id = {c["id"]: c for c in cards}
        assert by_id[staryu]["img"] is True
        assert any(c["img"] is False for c in cards)     # unfetched stay flagged off
        assert client.get(f"/cards/{staryu}.png").status_code == 200


@req
def test_preset_detail_is_the_clone_source(tmp_path):
    with _client(tmp_path) as client:
        detail = client.get("/api/presets/mega_starmie").json()
        assert detail["id"] == "mega_starmie"
        assert sum(c["count"] for c in detail["cards"]) == 60
        assert client.get("/api/presets/nope").status_code == 404


@req
def test_builder_deck_ids_start_a_table_and_bad_lists_bounce(tmp_path):
    with _client(tmp_path) as client:
        detail = client.get("/api/presets/mega_starmie").json()["cards"]
        ids = [row["id"] for row in detail for _ in range(row["count"])]
        check = client.post("/api/deck", json={"ids": ids}).json()
        assert check["ok"] is True and check["cards"] == 60
        r = client.post("/api/tables", json={"visitor": "B", "deck_ids": ids})
        assert r.status_code == 200, r.text
        r = client.post("/api/tables", json={"deck_ids": ids[:59]})
        assert r.status_code == 400 and r.json()["problems"]
        bad = client.post("/api/deck", json={"ids": ids[:59] + [999999]}).json()
        assert bad["ok"] is False and any("unknown" in p.lower() for p in bad["problems"])


@req
def test_visitor_faces_a_random_bot_when_none_is_named(tmp_path):
    agents_root = tmp_path / "agents"
    for name in ("bot_a", "bot_b"):
        d = agents_root / name
        d.mkdir(parents=True)
        (d / "main.py").write_text("def agent(o):\n    return []\n", encoding="utf-8")
        (d / "deck.csv").write_text("3\n" * 60, encoding="utf-8")
    with _client(tmp_path / "replays", agents_root=agents_root, cap=50) as client:
        seen = set()
        for _ in range(30):
            r = client.post("/api/tables", json={"preset": "mega_starmie"})
            assert r.status_code == 200, r.text
            seen.add(r.json()["agent"])
        assert seen == {"bot_a", "bot_b"}              # both bots get play time
        r = client.post("/api/tables", json={"preset": "mega_starmie",
                                             "agent": "bot_b"})
        assert r.json()["agent"] == "bot_b"            # explicit pick still honored


# --- hostile / malformed traffic ------------------------------------------------

@req
def test_garbage_on_the_socket_does_not_kill_the_match(tmp_path):
    with _client(tmp_path) as client:
        table_id = client.post("/api/tables",
                               json={"preset": "mega_starmie"}).json()["table_id"]
        with client.websocket_connect(f"/ws/{table_id}") as ws:
            assert ws.receive_json()["type"] == "state"
            ws.send_text("this is not json")
            ws.send_text(json.dumps(["not", "a", "dict"]))
            ws.send_text(json.dumps({"type": "choose", "indices": "nonsense"}))
            ws.send_text(json.dumps({"type": "choose", "indices": [0]}))   # still works
            assert ws.receive_json()["type"] == "state"


@req
def test_unknown_table_socket_gets_an_error_payload(tmp_path):
    with _client(tmp_path) as client:
        with client.websocket_connect("/ws/nope") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"


@req
def test_rating_with_confused_types_still_lands(tmp_path):
    with _client(tmp_path) as client:
        table_id = client.post("/api/tables",
                               json={"preset": "mega_starmie"}).json()["table_id"]
        with client.websocket_connect(f"/ws/{table_id}") as ws:
            ws.receive_json()
            ws.send_text(json.dumps({"type": "concede"}))
            while ws.receive_json()["type"] != "end":
                pass
        r = client.post(f"/api/tables/{table_id}/rating",
                        json={"misplay": 42, "phase": ["mid"], "comments": {"x": 1}})
        assert r.status_code == 200                    # coerced to None, never a 500
        saved = json.loads(next(Path(tmp_path).glob("*.json")).read_text(encoding="utf-8"))
        rating = saved["info"]["pvc"]["rating"]
        assert rating == {"misplay": None, "phase": None, "comments": None}


@req
def test_oversized_body_is_rejected(tmp_path):
    with _client(tmp_path) as client:
        r = client.post("/api/deck", json={"text": "x" * 100_000})
        assert r.status_code == 413
