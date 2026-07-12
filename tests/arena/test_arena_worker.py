"""Arena match worker (ADR-0033): one subprocess = one PvC Match on the cabt env.

Drives the real worker process through its stdio protocol — a scripted 'human'
plays the Visitor seat against the real mega_starmie agent. Needs the native
engine + kaggle_environments (both CI-provisioned); skips cleanly without them.
"""
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from conftest import require_kaggle_environments

REPO = Path(__file__).resolve().parents[2]
WORKER = REPO / "tools" / "arena" / "worker.py"
AGENT_DIR = REPO / "src" / "agents" / "mega_starmie"

req = pytest.mark.req("REQ-ARENA-0004")

_READ_TIMEOUT = 300         # a whole scripted match must land well inside this


class _Worker:
    """Minimal parent-side driver for one worker subprocess."""

    def __init__(self, tmp_path, *, human_seat=0, visitor="Tester"):
        deck = [int(x) for x in
                (AGENT_DIR / "deck.csv").read_text(encoding="utf-8").split()[:60]]
        self.proc = subprocess.Popen(
            [sys.executable, str(WORKER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        # two-phase protocol: warm (slow boot) then start (per-match bits)
        self.send({"agent_dir": str(AGENT_DIR), "agent_name": "mega_starmie",
                   "replay_dir": str(tmp_path)})
        assert self.read()["kind"] == "ready"          # the pre-warm seam
        self.send({"kind": "start", "human_seat": human_seat,
                   "human_deck": deck, "visitor": visitor})

    def send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def read(self):
        """One protocol message, or fail the test if the worker goes quiet."""
        box = []
        t = threading.Thread(target=lambda: box.append(self.proc.stdout.readline()),
                             daemon=True)
        t.start()
        t.join(_READ_TIMEOUT)
        if not box or not box[0]:
            self.proc.kill()
            pytest.fail("worker produced no protocol line (crashed or hung)")
        return json.loads(box[0])

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()


@req
def test_concede_ends_match_and_saves_forfeit_replay(tmp_path):
    require_kaggle_environments()
    w = _Worker(tmp_path, human_seat=0, visitor="Rich")
    try:
        first = w.read()
        assert first["kind"] == "obs"
        assert first["obs"]["select"] is not None      # a real decision reached the human
        w.send({"kind": "forfeit", "reason": "concede"})
        end = w.read()
    finally:
        w.close()

    assert end["kind"] == "end"
    path = Path(end["replay_path"])
    assert path.parent == tmp_path and path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    pvc = saved["info"]["pvc"]
    assert pvc["forfeit"] == "concede" and pvc["abandoned"] is False
    assert pvc["visitor"] == "Rich" and pvc["human_seat"] == 0
    assert saved["info"]["TeamNames"] == ["Rich", "mega_starmie"]
    assert saved["steps"]                              # the partial film is kept


@req
def test_played_out_match_saves_clean_replay_with_no_clock(tmp_path):
    require_kaggle_environments()
    w = _Worker(tmp_path, human_seat=0, visitor="Rich")
    end = None
    try:
        for _ in range(500):                           # scripted human: pass every turn
            msg = w.read()
            if msg["kind"] == "end":
                end = msg
                break
            opts = msg["obs"]["select"]["option"]
            pick = next((i for i, o in enumerate(opts) if o.get("type") == 14), None)
            if pick is not None:
                w.send({"kind": "choice", "indices": [pick]})
            else:
                n = msg["obs"]["select"].get("minCount", 1)
                w.send({"kind": "choice", "indices": list(range(max(n, 1)))})
    finally:
        w.close()

    assert end is not None, "match never finished"
    assert end["statuses"] == ["DONE", "DONE"]         # nobody crashed or timed out
    saved = json.loads(Path(end["replay_path"]).read_text(encoding="utf-8"))
    pvc = saved["info"]["pvc"]
    assert pvc["forfeit"] is None and pvc["abandoned"] is False
    assert saved["configuration"]["runTimeout"] >= 7 * 24 * 3600   # humans get no clock
    assert saved["configuration"]["actTimeout"] >= 7 * 24 * 3600
