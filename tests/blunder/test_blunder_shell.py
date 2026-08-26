import json
import math
import socket
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen

import pytest

from train.blunder.service import viewer_replay_payload
from train.blunder.shell import (
    _Handler, _SHELL_HTML, _json_body, _viewer_asset, init_state, port_is_taken, serve,
)


def test_shell_json_normalizes_nonfinite_live_diagnostics():
    payload = {"diagnostics": {"lower": -math.inf, "upper": math.inf, "nan": math.nan}}

    assert json.loads(_json_body(payload)) == {
        "diagnostics": {"lower": None, "upper": None, "nan": None},
    }


def test_shell_defaults_to_local_viewer_and_sends_replay_and_selected_step():
    assert 'iframe id="viewer" name="viewer" src="/viewer/"' in _SHELL_HTML
    assert "event.data&&event.data.ready" in _SHELL_HTML
    assert "addEventListener('load',markPlainReady)" in _SHELL_HTML
    assert "contentDocument?.readyState==='complete'" in _SHELL_HTML
    assert "replay:viewerReplayObj" in _SHELL_HTML
    assert "i=Number(viewerReplayObj.viewerOpeningFrame)||0" in _SHELL_HTML
    assert "plainLoaded?{step:i}" in _SHELL_HTML
    assert "step:i" in _SHELL_HTML
    assert "postPlain();" in _SHELL_HTML
    assert "player.hand=Array.from" in _SHELL_HTML
    assert "card.name='Hidden'" in _SHELL_HTML
    assert "!holder.querySelector('canvas')" in _SHELL_HTML


def test_viewer_replay_removes_null_board_slots_from_tool_generated_films():
    frame = {
        "current": {
            "stadium": [None],
            "players": [{
                "active": [None], "bench": [None], "discard": [None],
                "prize": [None] * 6, "hand": None, "handCount": 2,
            }],
        },
    }
    empty = {
        "current": {
            "stadium": [],
            "players": [{
                "active": [], "bench": [], "discard": [], "prize": [], "hand": [],
            }],
        },
    }
    replay = {
        "steps": [[{"visualize": [empty, frame, frame]}]],
    }

    payload = viewer_replay_payload(replay)
    current = payload["steps"][0][0]["visualize"][1]["current"]
    player = current["players"][0]

    assert len(payload["steps"]) == 3
    assert payload["viewerOpeningFrame"] == 1
    assert current["stadium"] == []
    assert player["active"] == []
    assert player["bench"] == []
    assert player["discard"] == []
    assert len(player["prize"]) == 6
    assert player["hand"] == [
        {"name": "Hidden", "energies": []},
        {"name": "Hidden", "energies": []},
    ]


def test_shell_requests_the_board_before_full_ledger_decision_data():
    replay = _SHELL_HTML.index("fetch('/replay.json')")
    games = _SHELL_HTML.index("fetch('/games.json')")
    frames = _SHELL_HTML.index("fetch('/frames.json')")

    assert replay < games < frames
    assert "fetch('/frame.json?frame='+f.frame)" in _SHELL_HTML


def test_switching_matches_does_not_parse_the_next_ledger_before_board_load(tmp_path):
    missing = tmp_path / "slow-ledger-bundle"
    init_state([tmp_path / "first.json", missing], store_path=tmp_path / "corrections.jsonl")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = Request(
        f"http://127.0.0.1:{server.server_address[1]}/game",
        data=json.dumps({"i": 1}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request) as response:
            payload = json.load(response)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert payload == {"ok": True, "count": 2, "current": 1}


def test_viewer_assets_resolve_from_vite_root_or_viewer_prefix(tmp_path):
    asset = tmp_path / "assets" / "viewer.js"
    asset.parent.mkdir()
    asset.write_text("export {}", encoding="utf-8")

    assert _viewer_asset("/assets/viewer.js", str(tmp_path)) == asset
    assert _viewer_asset("/viewer/assets/viewer.js", str(tmp_path)) == asset
    assert _viewer_asset("/viewer/../secret", str(tmp_path)) is None


def test_serve_refuses_a_port_an_older_shell_already_owns(tmp_path):
    # Mirror the older shell exactly -- SO_REUSEADDR is what lets Windows bind the port a SECOND
    # time without error, leaving the first process to answer with ITS replay.
    with socket.socket() as squatter:
        squatter.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        squatter.bind(("127.0.0.1", 0))
        squatter.listen(5)          # room for both probes; a full backlog reads as "refused"
        port = squatter.getsockname()[1]

        assert port_is_taken("127.0.0.1", port)
        with pytest.raises(SystemExit, match=f"port {port} is already serving"):
            serve([], store_path=tmp_path / "corrections.jsonl", port=port)


def test_free_and_ephemeral_ports_are_not_taken():
    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))          # bound but never listening
        assert not port_is_taken("127.0.0.1", free.getsockname()[1])
    assert not port_is_taken("127.0.0.1", 0)
