"""Arena pull: fetch PvC replays off the Arena host into this repo over SSH."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from arena import pull  # noqa: E402

req = pytest.mark.req("REQ-ARENA-0008")


@req
def test_command_pulls_the_pvc_dir_into_the_local_replay_dir(tmp_path):
    cmd = pull.build_command("rich@workbox", "/srv/PokemonAI", dest=tmp_path)
    assert cmd[0] == "scp"
    assert cmd[-2] == "rich@workbox:/srv/PokemonAI/data/replays/PvC/*.json"
    assert cmd[-1] == str(tmp_path)
    assert tmp_path.exists()                 # dest is created up front
