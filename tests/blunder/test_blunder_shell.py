import json
import math

from train.blunder.shell import _SHELL_HTML, _json_body


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
