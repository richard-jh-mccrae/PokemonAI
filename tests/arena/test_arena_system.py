"""Arena end-to-end: browser-shaped traffic through the real stack.

HTTP + WebSocket -> TableManager -> worker subprocess -> cabt env -> replay on
disk -> Rating patched in. The scripted Visitor just passes every turn (prefers
End turn), so the agent closes the game out quickly. Engine + kaggle_environments
required (CI-provisioned); skips cleanly without them.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
pytest.importorskip("fastapi")
pytest.importorskip("httpx")               # TestClient needs it; missing = RuntimeError
from fastapi.testclient import TestClient  # noqa: E402

from conftest import require_kaggle_environments  # noqa: E402
from arena.server import create_app  # noqa: E402

req = pytest.mark.req("REQ-ARENA-0007")

_END = 14


@req
def test_visitor_plays_rates_and_the_replay_is_tuner_shaped(tmp_path):
    require_kaggle_environments()
    with TestClient(create_app(replay_dir=tmp_path)) as client:
        # Pin the HOUSE agent too: unnamed -> random.choice over every playable agent dir, so the
        # TeamNames assertion below was only deterministic while mega_starmie was the sole agent.
        r = client.post("/api/tables",
                        json={"visitor": "E2E", "preset": "mega_starmie",
                              "agent": "mega_starmie"})
        assert r.status_code == 200, r.text
        table_id = r.json()["table_id"]

        end = None
        with client.websocket_connect(f"/ws/{table_id}") as ws:
            for _ in range(500):
                msg = ws.receive_json()
                if msg["type"] == "end":
                    end = msg
                    break
                sel = msg["view"]["select"]
                assert sel is not None and sel["options"]
                pick = next((o["i"] for o in sel["options"] if o["kind"] == _END), None)
                indices = ([pick] if pick is not None
                           else [o["i"] for o in sel["options"][:max(sel["min"], 1)]])
                ws.send_text(json.dumps({"type": "choose", "indices": indices}))
        assert end is not None, "match never ended"
        assert end["forfeit"] is None

        r = client.post(f"/api/tables/{table_id}/rating",
                        json={"misplay": "none seen", "phase": "late"})
        assert r.status_code == 200

    replays = list(tmp_path.glob("*.json"))
    assert len(replays) == 1
    saved = json.loads(replays[0].read_text(encoding="utf-8"))
    assert saved["info"]["pvc"]["rating"]["phase"] == "late"
    assert saved["info"]["TeamNames"] == ["E2E", "mega_starmie"]
    assert isinstance(saved["info"]["EpisodeId"], int)
    # Tuner-shaped: per-frame agent obs present in the film (ADR-0022/0033)
    assert any(fr.get("observation", {}).get("select")
               for step in saved["steps"] for fr in step)
