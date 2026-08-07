"""Batch mode: tag Corrections across a directory of Replays without leaving the tool."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from conftest import FIXTURES

from train.blunder import shell
from train.blunder.batch import discover_replays, load_game
from train.blunder.decisions import iter_decisions
from train.blunder.service import list_corrections, record_correction
from train.blunder.store import load_corrections

TELE = FIXTURES / "replays" / "mega_starmie_20260625_bde590c"


def _own_taggable(game):
    seat = game["live_seat"]
    return next(d for d in iter_decisions(game["replay"])
                if d.seat == seat and len(d.options) >= 2 and all(0 <= c < len(d.options) for c in d.chosen))


def test_discover_replays_orders_a_directory_by_episode_id():
    """A directory yields its Replay files ordered by episode id (logs/other files ignored)."""
    names = [p.name for p in discover_replays(TELE)]
    assert names == ["episode-81903490-replay.json.gz",
                     "episode-81903957-replay.json.gz",
                     "episode-81905063-replay.json.gz"]


def test_discover_replays_single_file_returns_just_that_file_and_skips_logs():
    """A single Replay path is batch-of-one; agent logs are never treated as Replays."""
    one = TELE / "episode-81903490-replay.json.gz"
    assert discover_replays(one) == [one]
    assert all("-logs.json" not in p.name for p in discover_replays(TELE))


def test_load_game_provides_replay_live_trace_own_seat_and_build_identity():
    """A Replay path loads into a self-contained game context: the replay, its parsed live
    telemetry, the per-Replay own-seat (varies across the dir), and the dir-stem build identity."""
    game = load_game(TELE / "episode-81905063-replay.json.gz")
    assert game["replay"]["info"]["EpisodeId"] == 81905063
    assert game["live_seat"] == 1                       # agent-1 log -> we're seat 1 in this Replay
    assert game["live_records"] and "opts" in game["live_records"][0]
    assert game["agent"] == "mega_starmie"              # deck/build name from stem (auto-fill source)
    assert game["agent_build"] == "mega_starmie_20260625_bde590c"
    assert game["agent_version"] == "bde590c"


def test_tag_corrections_across_a_directory_of_replays(tmp_path):
    """Each Correction is stored with its own episode_id + live trace, sharing the one build
    identity; the per-episode review list isolates each Replay."""
    replays = discover_replays(TELE)
    assert len(replays) == 3
    store = tmp_path / "corrections.jsonl"

    for rp in (replays[0], replays[2]):                 # seat-0 Replay and seat-1 Replay
        game = load_game(rp)
        d = _own_taggable(game)
        record_correction(
            game["replay"], frame=d.frame, correct=[next(i for i in range(len(d.options))
                                                          if i not in d.chosen)],
            category="bad_target", rationale="tagged across the batch", source="own",
            agent="mega_starmie", store_path=store, live_records=game["live_records"],
            agent_build=game["agent_build"], agent_version=game["agent_version"],
            built_at=game["built_at"],
        )

    corrs = load_corrections(store)
    assert len(corrs) == 2
    assert {c.episode_id for c in corrs} == {81903490, 81905063}          # one per tagged Replay
    assert all(c.agent_build == "mega_starmie_20260625_bde590c" for c in corrs)  # shared build id
    assert all(c.live_trace is not None for c in corrs)                  # live trace per Replay
    # review list (what panel shows on switch) scoped to current Replay
    first = list_corrections(load_game(replays[0])["replay"], store)
    assert len(first) == 1 and first[0]["seat"] == 0


def _get(port, path):
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}").read())


def _post(port, path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def test_own_tag_auto_fills_agent_from_the_build_folder(tmp_path):
    """SYSTEM (HTTP): with NO --agent, an own blunder's `agent` is auto-filled from the replay's
    build-folder stem (mega_starmie_…) — the UI sends an empty agent and the server resolves it."""
    store = tmp_path / "c.jsonl"
    shell.init_state(discover_replays(TELE), store_path=str(store))   # no agent= passed
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), shell._Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        game = load_game(discover_replays(TELE)[0])      # current (seat-0) replay
        d = _own_taggable(game)
        correct = next(i for i in range(len(d.options)) if i not in d.chosen)
        res = _post(port, "/correction", {
            "frame": d.frame, "correct": [correct], "category": "bad_target",
            "rationale": "auto-fill check", "source": "own", "agent": "",   # UI sends empty with no --agent
        })
        assert res["ok"]
    finally:
        httpd.shutdown()
        httpd.server_close()

    [stored] = load_corrections(store)
    assert stored.agent == "mega_starmie"               # auto-filled from build folder, not blank


def test_shell_serves_and_switches_replays_over_http(tmp_path):
    """SYSTEM (HTTP): the shell serves the batch and ◀/▶ switches which Replay is current —
    each switch re-serves that Replay's frames + live trace + own-seat."""
    shell.init_state(discover_replays(TELE), store_path=str(tmp_path / "c.jsonl"))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), shell._Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        g0 = _get(port, "/games.json")
        assert g0["count"] == 3 and g0["current"] == 0
        assert g0["episode_id"] == 81903490 and g0["own_seat"] == 0

        g2 = _post(port, "/game", {"i": 2})                # switch to seat-1 Replay
        assert g2["ok"] and g2["current"] == 2
        assert g2["episode_id"] == 81905063 and g2["own_seat"] == 1

        frames = _get(port, "/frames.json")["frames"]      # now serving new Replay
        own = [f for f in frames if f["taggable"] and f["seat"] == 1]
        assert own and all(f["live"] is not None for f in own)
    finally:
        httpd.shutdown()
        httpd.server_close()
