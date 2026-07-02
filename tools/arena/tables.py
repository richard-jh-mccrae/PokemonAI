"""Tables: the Arena's capped live-match slots (CONTEXT.md: Table).

One Table = one worker subprocess hosting one PvC Match. The manager owns the cap,
routes the Visitor's choices to the worker's stdin, and forfeits idle Tables so a
walker-away can't hold a slot (CONTEXT.md: Forfeit).

Consumers read a Table through a seq/snapshot model (`wait_change`): the reader
thread publishes every worker message under a Condition and bumps `seq`; any number
of observers (each WebSocket connection) wait on the seq they last saw and get a
consistent snapshot. State-based, not queue-based — a dropped/reconnected socket
can never steal a message from the next one, and `_pump` is the *only* writer of
`state`, so a late click can't resurrect a finished Table.

Pure threads — no asyncio — so it is testable headless; the web layer bridges with
asyncio.to_thread (wait_change returns on a short timeout, so an abandoned waiter
thread exits promptly instead of blocking forever).
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

_WORKER = Path(__file__).resolve().parent / "worker.py"

_FORFEIT_GRACE = 15         # s between sending forfeit and force-killing the worker
_OVER_RETENTION = 1800      # s a finished Table stays around for its Rating


class TableFull(RuntimeError):
    """All Tables are taken — the Visitor waits."""


class Table:
    def __init__(self, table_id: str, proc: subprocess.Popen, *, visitor: str | None,
                 agent_name: str, clock):
        self.id = table_id
        self.visitor = visitor
        self.agent_name = agent_name
        self.state = "waiting"            # waiting -> acting/thinking -> over
        self.forfeit: str | None = None
        self.replay_path: str | None = None
        self.end_info: dict | None = None
        self.last_obs: dict | None = None
        self.seq = 0
        self.last_activity = clock()
        self.forfeit_sent_at: float | None = None
        self.over_at: float | None = None
        self._proc = proc
        self._clock = clock
        self._cond = threading.Condition()

    # -- the worker protocol, parent side ------------------------------------

    def _pump(self) -> None:
        """Reader thread — the only writer of `state`. Publishes every message."""
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("kind") == "obs":
                self._publish("acting", obs=msg.get("obs"))
            elif msg.get("kind") == "end":
                self._publish("over", end=msg)
                break
        else:                             # EOF without an end line: the worker died
            self._publish("over", end={"kind": "died"})
        try:
            self._proc.stdout.close()
            self._proc.stdin.close()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=30)   # reap — no zombies on the always-on host
        except subprocess.TimeoutExpired:
            self._proc.kill()

    def _publish(self, state: str, *, obs: dict | None = None,
                 end: dict | None = None) -> None:
        with self._cond:
            if self.state == "over":      # end is terminal, never overwritten
                return
            self.state = state
            if obs is not None:
                self.last_obs = obs
            if end is not None:
                self.end_info = end
                self.replay_path = end.get("replay_path")
                self.over_at = self._clock()
            self.last_activity = self._clock()
            self.seq += 1
            self._cond.notify_all()

    def _write(self, msg: dict) -> None:
        try:
            self._proc.stdin.write(json.dumps(msg) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass                          # the reader thread will surface the death

    # -- observers -------------------------------------------------------------

    def snapshot(self) -> dict:
        with self._cond:
            return {"seq": self.seq, "state": self.state, "obs": self.last_obs,
                    "end": self.end_info, "forfeit": self.forfeit}

    def wait_change(self, seen_seq: int, timeout: float | None = None) -> dict | None:
        """Block until seq > seen_seq, then return a snapshot; None on timeout."""
        with self._cond:
            self._cond.wait_for(lambda: self.seq > seen_seq, timeout)
            if self.seq <= seen_seq:
                return None
            return {"seq": self.seq, "state": self.state, "obs": self.last_obs,
                    "end": self.end_info, "forfeit": self.forfeit}

    def touch(self) -> None:
        with self._cond:
            self.last_activity = self._clock()

    @property
    def live(self) -> bool:
        return self.state != "over"

    def kill(self) -> None:
        if self._proc.poll() is None:
            self._proc.kill()


class TableManager:
    def __init__(self, *, replay_dir: Path, cap: int = 4, idle_timeout: float = 600,
                 clock=time.monotonic, worker_cmd: list[str] | None = None,
                 warm_picker=None):
        """warm_picker: () -> (agent_name, agent_dir). When given, one worker is
        kept booted ahead of the next Visitor (its agent chosen at warm time), so
        the click-to-first-frame wait collapses from seconds to instant."""
        self.replay_dir = Path(replay_dir)
        self.cap = cap
        self.idle_timeout = idle_timeout
        self._clock = clock
        self._worker_cmd = worker_cmd or [sys.executable, str(_WORKER)]
        self._tables: dict[str, Table] = {}
        self._lock = threading.Lock()
        self._warm_picker = warm_picker
        self._warm: tuple[str, str, subprocess.Popen] | None = None
        self._maintain_warm()

    # -- the pre-warm pool ------------------------------------------------------

    def _spawn(self) -> subprocess.Popen:
        return subprocess.Popen(
            self._worker_cmd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8")

    def _warm_config(self, agent_name: str, agent_dir) -> dict:
        return {"agent_dir": str(agent_dir), "agent_name": agent_name,
                "replay_dir": str(self.replay_dir)}

    def _maintain_warm(self) -> None:
        """Keep exactly one live standby worker (when a picker is configured)."""
        if self._warm_picker is None:
            return
        with self._lock:
            if self._warm is not None and self._warm[2].poll() is None:
                return
            self._warm = None
            try:
                agent_name, agent_dir = self._warm_picker()
            except Exception:
                return
            proc = self._spawn()
            try:
                proc.stdin.write(json.dumps(self._warm_config(agent_name, agent_dir)) + "\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                proc.kill()
                return
            self._warm = (agent_name, str(agent_dir), proc)

    def warm_agent(self) -> str | None:
        """The agent the standby worker has loaded — the fastest match to offer."""
        with self._lock:
            return self._warm[0] if self._warm else None

    def live_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._tables.values() if t.live)

    def create(self, *, visitor: str | None, deck: list[int], agent_name: str,
               agent_dir: str | Path) -> Table:
        with self._lock:
            if sum(1 for t in self._tables.values() if t.live) >= self.cap:
                raise TableFull(f"all {self.cap} tables are taken")
            table_id = uuid.uuid4().hex[:12]
            proc = None
            if (self._warm is not None and self._warm[0] == agent_name
                    and self._warm[2].poll() is None):
                proc = self._warm[2]                   # adopt the booted standby
                self._warm = None
            cold = proc is None
            if cold:
                proc = self._spawn()
            table = Table(table_id, proc, visitor=visitor, agent_name=agent_name,
                          clock=self._clock)
            self._tables[table_id] = table
        if cold:
            table._write(self._warm_config(agent_name, agent_dir))
        table._write({
            "kind": "start", "human_seat": 0,
            "human_deck": [int(c) for c in deck], "visitor": visitor,
        })
        threading.Thread(target=table._pump, daemon=True,
                         name=f"table-{table_id}").start()
        self._maintain_warm()                          # refill the standby slot
        return table

    def get(self, table_id: str) -> Table:
        with self._lock:
            return self._tables[table_id]

    def choose(self, table_id: str, indices: list[int]) -> bool:
        """Forward the Visitor's pick iff the Table is actually waiting on one."""
        table = self.get(table_id)
        with table._cond:
            if table.state != "acting":   # late/duplicate click: drop, never desync
                return False
            table.state = "thinking"
            table.last_activity = self._clock()
        table._write({"kind": "choice", "indices": [int(i) for i in indices]})
        return True

    def concede(self, table_id: str) -> None:
        table = self.get(table_id)
        if table.live:
            self._forfeit(table, "concede")

    def sweep(self) -> None:
        """Reclaim Tables: idle -> Forfeit; forfeited-but-stuck -> kill;
        long-over -> evict (the Rating window is over)."""
        now = self._clock()
        with self._lock:
            tables = list(self._tables.values())
        for t in tables:
            if t.live and t.forfeit_sent_at is None \
                    and now - t.last_activity > self.idle_timeout:
                self._forfeit(t, "timeout")
            elif t.live and t.forfeit_sent_at is not None \
                    and now - t.forfeit_sent_at > _FORFEIT_GRACE:
                t.kill()                  # _pump sees EOF and publishes the death
        with self._lock:
            for tid in [tid for tid, t in self._tables.items()
                        if t.over_at is not None
                        and now - t.over_at > _OVER_RETENTION]:
                del self._tables[tid]
        self._maintain_warm()                          # respawn a died-while-warm standby

    def _forfeit(self, table: Table, reason: str) -> None:
        table.forfeit = reason
        table.forfeit_sent_at = self._clock()
        table._write({"kind": "forfeit", "reason": reason})

    def shutdown(self) -> None:
        """Forfeit every live match so its partial replay is saved, then reap."""
        with self._lock:
            tables = list(self._tables.values())
            if self._warm is not None:
                if self._warm[2].poll() is None:
                    self._warm[2].kill()
                self._warm = None
        for t in tables:
            if t.live:
                self._forfeit(t, "timeout")
        deadline = time.time() + 5
        for t in tables:
            if t.live:
                t.wait_change(t.seq, timeout=max(0.1, deadline - time.time()))
        for t in tables:
            t.kill()
