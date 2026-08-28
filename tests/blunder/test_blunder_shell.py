import json
import math
import socket
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen

import pytest

import train.blunder.shell as blunder_shell
from train.blunder.service import viewer_replay_payload
from train.blunder.shell import (
    _Handler, _SHELL_HTML, _frames_index_payload, _games_payload, _json_body, _viewer_asset,
    init_state, port_is_taken, serve,
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
    assert "plainLoaded?state" in _SHELL_HTML
    assert "step:boardStep" in _SHELL_HTML
    assert "postPlain();" in _SHELL_HTML
    assert "player.hand=Array.from" in _SHELL_HTML
    assert "card.name='Hidden'" in _SHELL_HTML
    assert "...player.prize" in _SHELL_HTML
    assert "f.min_count==null||f.max_count==null" in _SHELL_HTML
    assert "correct.length<f.min_count||correct.length>f.max_count" in _SHELL_HTML
    assert "!holder.querySelector('canvas')" in _SHELL_HTML
    assert 'select[aria-label="Playback speed"]' in _SHELL_HTML
    assert "doc.defaultView.MutationObserver" in _SHELL_HTML
    assert "function drawPlainPrizes()" in _SHELL_HTML
    assert 'id="boardprizes"' in _SHELL_HTML
    assert "slot.textContent=known?(card.name||('#'+card.id)):'Face-down'" in _SHELL_HTML


def test_shell_plays_only_the_board_at_one_decision_per_second():
    assert 'button id="play"' in _SHELL_HTML
    assert 'select id="playspeed"' in _SHELL_HTML
    for speed in ("0.3", "0.5", "1", "1.5", "2", "3"):
        assert f'value="{speed}"' in _SHELL_HTML
        assert f'x{speed}</option>' in _SHELL_HTML
    assert "const PLAYBACK_MS=1000;" in _SHELL_HTML
    assert "PLAYBACK_MS/playbackSpeed" in _SHELL_HTML
    assert "let plainReady=false,plainLoaded=false,boardStep=0;" in _SHELL_HTML
    assert "step:boardStep,playing:false,speed:playbackSpeed" in _SHELL_HTML
    assert "boardStep+=1; postPlain();" in _SHELL_HTML
    assert "await show(i+1)" not in _SHELL_HTML
    assert "await show(p.opening_frame||0,false);" in _SHELL_HTML
    assert "startPlayback(); refreshList();" in _SHELL_HTML


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
    assert player["prize"] == [None] * 6
    assert player["hand"] == [
        {"name": "Hidden", "energies": []},
        {"name": "Hidden", "energies": []},
    ]


def test_viewer_replay_recovers_legacy_transition_metadata_for_colorful_playback():
    def player():
        return {"active": [], "bench": [], "discard": [], "prize": [], "hand": []}

    frames = [
        {"obs": {"logs": [{"type": "Draw", "cardId": 7}]},
         "current": {"yourIndex": 1, "players": [player(), player()]},
         "selected": None},
        {"obs": {"logs": [{"type": "MoveCard", "cardId": 7}]},
         "current": {"yourIndex": 0, "players": [player(), player()]},
         "selected": [2]},
    ]
    replay = {"steps": [[{"visualize": frames}]], "info": {"TeamNames": []}}

    payload = viewer_replay_payload(replay, decklists=[[1] * 60, [2] * 60])
    film = payload["steps"][0][0]["visualize"]

    assert film[0]["logs"] == [{"type": "Draw", "cardId": 7}]
    assert film[1]["logs"] == [{"type": "MoveCard", "cardId": 7}]
    assert film[0]["action"] == [[1] * 60, [2] * 60]
    assert film[1]["action"] == [None, [2]]


def test_viewer_replay_supplies_the_colorful_viewers_preload_contract():
    def player():
        return {"active": [], "bench": [], "discard": [], "prize": [], "hand": []}

    later_player = {
        **player(),
        "active": [{"id": 7, "name": "Staryu", "energies": []}],
    }
    replay = {"steps": [[{"visualize": [
        {"current": {"players": [player(), player()]}},
        {"current": {"players": [later_player, player()]}},
    ]}]]}

    payload = viewer_replay_payload(replay)
    film = payload["steps"][0][0]["visualize"]

    assert film[0]["logs"] == []
    assert [card["id"] for card in film[0]["current"]["players"][0]["deck"]] == [7]
    assert all(isinstance(frame["logs"], list) for frame in film)
    assert all(isinstance(p["deck"], list)
               for frame in film for p in frame["current"]["players"])


def test_viewer_replay_keeps_both_last_known_hands_visible_between_seat_observations():
    def player(hand, count):
        return {"active": [], "bench": [], "discard": [], "prize": [],
                "hand": hand, "handCount": count}

    a = [{"id": 666, "serial": 1}, {"id": 1031, "serial": 2}]
    b = [{"id": 678, "serial": 61}, {"id": 1120, "serial": 62}]
    replay = {"steps": [[{"visualize": [
        {"current": {"yourIndex": 0, "players": [player(a, 2), player(None, 2)]}},
        {"current": {"yourIndex": 1, "players": [player(None, 2), player(b, 2)]}},
        {"current": {"yourIndex": 0, "players": [player(a, 2), player(None, 2)]}},
    ]}]]}

    film = viewer_replay_payload(replay)["steps"][0][0]["visualize"]

    assert [[card["id"] for card in frame["current"]["players"][0]["hand"]]
            for frame in film] == [[666, 1031]] * 3
    assert [card["id"] for card in film[2]["current"]["players"][1]["hand"]] == [678, 1120]
    assert replay["steps"][0][0]["visualize"][1]["current"]["players"][0]["hand"] is None


def test_viewer_replay_infers_each_seats_known_prizes_from_full_deck_reveals():
    def player(hand, active, deck_count):
        return {"active": active, "bench": [], "discard": [], "prize": [None] * 4,
                "hand": hand, "handCount": len(hand), "deckCount": deck_count}

    decks = [list(range(1, 9)), list(range(11, 19))]
    frames = [
        {"current": {"yourIndex": 0, "players": [
            player([{"id": 1, "serial": 1}], [{"id": 2, "serial": 2}], 2),
            player([{"id": 11, "serial": 11}], [{"id": 12, "serial": 12}], 2),
        ]}, "select": {"deck": [{"id": 3, "serial": 3}, {"id": 4, "serial": 4}]}},
        {"current": {"yourIndex": 1, "players": [
            player([{"id": 1, "serial": 1}], [{"id": 2, "serial": 2}], 2),
            player([{"id": 11, "serial": 11}], [{"id": 12, "serial": 12}], 2),
        ]}, "select": {"deck": [{"id": 13, "serial": 13}, {"id": 14, "serial": 14}]}},
    ]
    replay = {"steps": [[{"visualize": frames}]]}

    film = viewer_replay_payload(replay, decklists=decks)["steps"][0][0]["visualize"]

    for frame in film:
        assert [card["id"] for card in frame["current"]["players"][0]["prize"]] == [5, 6, 7, 8]
        assert [card["id"] for card in frame["current"]["players"][1]["prize"]] == [15, 16, 17, 18]
        assert all(card["name"] != "Hidden"
                   for player_state in frame["current"]["players"]
                   for card in player_state["prize"])


def test_shell_requests_the_board_before_full_ledger_decision_data():
    replay = _SHELL_HTML.index("fetch('/replay.json'")
    games = _SHELL_HTML.index("fetch('/games.json'")
    frames = _SHELL_HTML.index("fetch('/frames.json'")

    assert replay < games < frames
    assert "fetch('/frame.json?frame='+f.frame)" in _SHELL_HTML
    assert "await loadGame(true);" in _SHELL_HTML
    assert "openPlain(forceViewer);" in _SHELL_HTML
    assert "if(run!==gameLoadRun) return;" in _SHELL_HTML


def test_decision_navigation_repaints_before_lazy_ledger_details_arrive():
    show = _SHELL_HTML.index("async function show(n,withDetails=true)")
    repaint = _SHELL_HTML.index("renderFrame(f,true);", show)
    details = _SHELL_HTML.index("fetch('/frame.json?frame='+f.frame)", show)
    hydration = _SHELL_HTML.index("renderFrame(f,false);", details)

    assert repaint < details < hydration
    assert "if(!resetForm) return;" in _SHELL_HTML


def test_initial_match_index_does_not_load_decision_telemetry(tmp_path, monkeypatch):
    player = {"active": [], "bench": [], "discard": [], "prize": [], "hand": []}
    replay = {
        "info": {"EpisodeId": 123, "TeamNames": ["a", "b"]},
        "steps": [[{"visualize": [{
            "current": {"players": [player, player], "yourIndex": 0, "turn": 0},
        }]}]],
    }
    path = tmp_path / "123.json"
    path.write_text(json.dumps(replay), encoding="utf-8")
    init_state([path], store_path=tmp_path / "corrections.jsonl")

    monkeypatch.setattr(blunder_shell, "load_game", lambda _path: pytest.fail("loaded telemetry"))

    assert _games_payload()["episode_id"] == 123
    assert _frames_index_payload()["total"] == 1


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
