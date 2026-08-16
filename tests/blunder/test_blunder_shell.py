import json
import math
import socket

import pytest

from train.blunder.shell import _SHELL_HTML, _json_body, _viewer_asset, port_is_taken, serve


def test_shell_json_normalizes_nonfinite_live_diagnostics():
    payload = {"diagnostics": {"lower": -math.inf, "upper": math.inf, "nan": math.nan}}

    assert json.loads(_json_body(payload)) == {
        "diagnostics": {"lower": None, "upper": None, "nan": None},
    }


def test_shell_defaults_to_local_viewer_and_sends_replay_and_selected_step():
    assert 'iframe id="viewer" name="viewer" src="/viewer/"' in _SHELL_HTML
    assert "event.data&&event.data.ready" in _SHELL_HTML
    assert "replay:viewerReplayObj" in _SHELL_HTML
    assert "plainLoaded?{step:i}" in _SHELL_HTML
    assert "step:i" in _SHELL_HTML
    assert "postPlain();" in _SHELL_HTML
    assert "player.hand=Array.from" in _SHELL_HTML
    assert "card.name='Hidden'" in _SHELL_HTML


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
