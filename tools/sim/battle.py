"""Battle: a local head-to-head between two Builds (tools/sim/CONTEXT.md).

A **Battle** runs N **Matches** between two contestants and prints a **Battle Report** —
a quick comparative read for curiosity, *not* a promotion gate (local self-play is noisy
and mirror-biased; the ladder is the real judge — see data/training-a-model-breakdown.md).

Why this drives `cg.game` directly instead of the cabt env: cabt's `env.run` execs both
agents in *one* interpreter, so two *different* bundles collide in `sys.modules` (and can't
each resolve their cwd-relative `deck.csv`). We instead run each contestant in its own
subprocess (own cwd + `sys.path` + module namespace) and step the same native engine the
cabt env wraps — the obs is per-player and hides the opponent's hand, verified identical.

    python tools/sim/battle.py <A> <B> -n 50      # <X> = build id or agent name (latest build)
"""
from __future__ import annotations

import json
import math
import os
import queue
import subprocess
import sys
from collections import deque
from threading import Thread
from time import monotonic, perf_counter
from uuid import uuid4
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SERVER = Path(__file__).with_name("_agent_server.py")
_WORKER = Path(__file__).with_name("_battle_worker.py")
_MAX_STEPS = 5000          # runaway-game backstop; a real Match resolves in ~100s of steps


@dataclass(frozen=True)
class MatchResult:
    """One engine-seat Match outcome, including process and experiment deadline failures."""
    winner: int | None
    crashed: tuple[int, ...] = ()
    timed_out: tuple[int, ...] = ()
    match_deadline_hit: bool = False
    failure: str | None = None


@dataclass(frozen=True)
class BattleMatch:
    """One seat-balanced Match outcome. ``winner`` is CONTESTANT-relative (0=A, 1=B, None=draw),
    already mapped out of the engine seat; ``a_seat`` keeps seat-balancing auditable (ADR-0021)."""
    a_seat: int
    winner: int | None
    crashed: tuple[int, ...] = ()


def balanced_tally(records: list) -> dict:
    """Aggregate seat-balanced `BattleMatch`es: the overall A/B counts (`tally`) plus a
    per-seat split `by_seat[s] = {n, a_wins}` — the ADR-0021 fairness audit."""
    overall = tally(records)
    by_seat = {
        s: {
            "n": sum(1 for r in records if r.a_seat == s),
            "a_wins": sum(1 for r in records if r.a_seat == s and r.winner == 0),
        }
        for s in (0, 1)
    }
    return {**overall, "by_seat": by_seat}


def to_battle_match(a_seat: int, result: "MatchResult") -> "BattleMatch":
    """Map an engine-relative `MatchResult` (winner/crashed by engine seat) to a contestant-relative
    `BattleMatch`, given which engine seat contestant A occupied. A is contestant 0, B is 1."""
    def contestant(seat: int) -> int:
        return 0 if seat == a_seat else 1
    winner = None if result.winner is None else contestant(result.winner)
    return BattleMatch(a_seat=a_seat, winner=winner,
                       crashed=tuple(contestant(s) for s in result.crashed))


def seat_plan(n: int) -> list[int]:
    """Which engine seat contestant A occupies in each of `n` Matches, ~half each. Deterministic, so
    the first/second-player advantage cancels across the run rather than favouring one (ADR-0021)."""
    half = (n + 1) // 2
    return [0 if i < half else 1 for i in range(n)]


def parse_spec(spec: str) -> tuple[str, str | None]:
    """Split a contestant spec into `(base, overlay_path)`. `name@overlay.json` carries an
    experiment overlay (the config under test, ADR-0021); a bare name/id carries none."""
    base, sep, overlay = spec.partition("@")
    return base, (overlay if sep else None)


def resolve_contestant(spec: str, rows: list[dict]) -> dict:
    """Resolve a CLI contestant `spec` to a Build row. All-digit is a Build id; anything else is an
    agent NAME, resolved to that agent's latest build. Raises ValueError naming the miss."""
    if spec.isdigit():
        sid = int(spec)
        match = [r for r in rows if r.get("submission_id") == sid]
        if not match:
            raise ValueError(f"no build #{sid} in the ledger")
        return match[-1]
    of_agent = [r for r in rows if r.get("agent") == spec]
    if not of_agent:
        raise ValueError(f"no builds for agent {spec!r} (pass a build id, or `build {spec}` first)")
    return max(of_agent, key=lambda r: r.get("submission_id", 0))


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """The Wilson score interval for a win-rate of `wins`/`n` — the honesty knob the Report
    prints. Wide at low `n` (correctly says 'don't trust this'); (0,0) for an empty Battle."""
    if n <= 0:
        return (0.0, 0.0)
    p = wins / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def tally(results: list[MatchResult]) -> dict:
    """Aggregate Match outcomes into the Report's counts (crashes counted, not double-scored)."""
    return {
        "n": len(results),
        "a_wins": sum(1 for r in results if r.winner == 0),
        "b_wins": sum(1 for r in results if r.winner == 1),
        "draws": sum(1 for r in results if r.winner is None),
        "a_crashes": sum(1 for r in results if 0 in r.crashed),
        "b_crashes": sum(1 for r in results if 1 in r.crashed),
    }


def _short_hash(h: str) -> str:
    """Shorten the hex of a git hash to 7 while keeping any suffix (e.g. `f1cd9bf-dirty`)."""
    head, _, suffix = (h or "").partition("-")
    return head[:7] + (f"-{suffix}" if suffix else "")


def _tag(row: dict) -> str:
    """`#3 mega_starmie (tuned, ccc)` — the contestant's provenance, one line."""
    sid = row.get("submission_id", "?")
    bits = [b for b in (row.get("label"), _short_hash(row.get("git_hash"))) if b]
    suffix = f" ({', '.join(bits)})" if bits else ""
    return f"#{sid} {row.get('agent', '?')}{suffix}"


def format_report(a: dict, b: dict, t: dict, *, elapsed: float, jobs: int, mode: str) -> str:
    """Render the Battle Report — header provenance, W/D, win-rate + Wilson CI, crashes."""
    n = t["n"]
    rate = t["a_wins"] / n if n else 0.0
    lo, hi = wilson_ci(t["a_wins"], n)
    sid_a, sid_b = f"#{a.get('submission_id', '?')}", f"#{b.get('submission_id', '?')}"
    rate_s = elapsed and f"{n / elapsed:.1f} games/s" or "-- games/s"
    lines = [
        f"Battle -- {_tag(a)}  vs  {_tag(b)}",
        f"  {n} games | {jobs} jobs | {elapsed:.1f}s | {rate_s} | mode={mode}",
        "",
        f"  {sid_a} wins {t['a_wins']}   {sid_b} wins {t['b_wins']}   draws {t['draws']}",
        f"  {sid_a} win-rate {rate * 100:.0f}%   (95% CI {lo * 100:.0f}-{hi * 100:.0f}%)"
        "  -- ladder is the real judge",
    ]
    if "by_seat" in t:                                  # seat-balanced run: keep seat effect visible (ADR-0021)
        s = t["by_seat"]
        lines.append(f"  seat split  {sid_a} as seat 0: {s[0]['a_wins']}/{s[0]['n']}   "
                     f"as seat 1: {s[1]['a_wins']}/{s[1]['n']}")
    if t["a_crashes"] or t["b_crashes"]:
        lines.append(f"  crashes {t['a_crashes'] + t['b_crashes']}  "
                     f"({sid_a}: {t['a_crashes']}, {sid_b}: {t['b_crashes']})"
                     "  -- counted as losses for the crashing build")
    else:
        lines.append("  crashes 0")
    return "\n".join(lines)


def read_deck(bundle: Path) -> list[int]:
    """The 60 card ids of a Bundle's `deck.csv` — what the engine seats this contestant with."""
    rows = [ln for ln in (Path(bundle) / "deck.csv").read_text(encoding="utf-8").split() if ln]
    return [int(x) for x in rows[:60]]


class AgentServer:
    """A contestant in its own process. The isolation (own cwd / `sys.path` / `sys.modules`) is the
    whole point: two DIFFERENT Bundles can play one Match, which an in-process load cannot do."""

    def __init__(self, bundle: Path | str, extra_syspath=(), *, overlay=None,
                 capture_telemetry=False, emit_telemetry=None, decision_seconds=None,
                 strict=False, provenance=None):
        emit_telemetry = capture_telemetry if emit_telemetry is None else bool(emit_telemetry)
        env = dict(os.environ, AGENT_NO_TELEMETRY="0" if emit_telemetry else "1",
                   AGENT_CAPTURE_TELEMETRY="1" if capture_telemetry else "0",
                   AGENT_BRAIN_STRICT="1" if strict else "0",
                   PYTHONIOENCODING="utf-8")
        if decision_seconds is not None:
            env["AGENT_DECISION_SECONDS"] = str(float(decision_seconds))
        else:
            env.pop("AGENT_DECISION_SECONDS", None)
        if provenance is not None:
            env["AGENT_RUNTIME_PROVENANCE"] = json.dumps(
                provenance, sort_keys=True, separators=(",", ":"))
        else:
            env.pop("AGENT_RUNTIME_PROVENANCE", None)
        if overlay:                                   # config under test, as absolute path (cwd=bundle)
            env["AGENT_OVERLAY"] = str(Path(overlay).resolve())
        else:
            env.pop("AGENT_OVERLAY", None)            # baseline contestant must not inherit a stray overlay
        self.proc = subprocess.Popen(
            [sys.executable, str(_SERVER), *(str(p) for p in extra_syspath)],
            cwd=str(bundle), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
        self._responses = queue.Queue()
        self._reader = Thread(target=self._read_responses, daemon=True)
        self._stderr_lines = deque(maxlen=80)
        self._stderr_reader = Thread(target=self._read_stderr, daemon=True)
        self._reader.start()
        self._stderr_reader.start()
        self.last_telemetry = []
        self.last_telemetry_seconds = 0.0
        self.last_timeout = False
        self.last_error = None
        self.last_seconds: float | None = None
        self.episode_key: str | None = None

    def begin_episode(self, episode_key: str) -> None:
        self.episode_key = str(episode_key)

    def _read_responses(self) -> None:
        for line in self.proc.stdout:
            self._responses.put(line)
        self._responses.put(None)

    def _read_stderr(self) -> None:
        for line in self.proc.stderr:
            if not line.startswith("@T "):
                self._stderr_lines.append(line.rstrip())

    def _process_error(self) -> str:
        self._stderr_reader.join(timeout=0.2)
        detail = "\n".join(self._stderr_lines).strip()
        code = self.proc.poll()
        head = f"agent process exited with code {code}" if code is not None else "agent process failed"
        return f"{head}: {detail[-4000:]}" if detail else head

    def alive(self) -> bool:
        return self.proc.poll() is None

    def act(self, obs: dict, timeout=None) -> list[int] | None:
        """Return chosen indices; `last_seconds` is the telemetry-independent round-trip clock."""
        self.last_timeout = False
        self.last_telemetry = []
        self.last_telemetry_seconds = 0.0
        self.last_error = None
        started = monotonic()
        try:
            request = ({"observation": obs, "telemetry_episode_key": self.episode_key}
                       if self.episode_key is not None else obs)
            self.proc.stdin.write(json.dumps(request) + "\n")
            self.proc.stdin.flush()
            line = self._responses.get(timeout=timeout)
            if not line:
                self.last_error = self._process_error()
                return None
            payload = json.loads(line)
            if isinstance(payload, dict):
                self.last_telemetry = list(payload.get("telemetry") or ())
                self.last_telemetry_seconds = float(payload.get("telemetry_seconds") or 0.0)
                return list(payload.get("choice") or ())
            self.last_telemetry = []
            return payload
        except queue.Empty:
            self.last_timeout = True
            self.proc.terminate()
            self.last_error = f"decision timed out after {float(timeout):g}s"
            return None
        except (BrokenPipeError, OSError, ValueError) as exc:
            self.last_error = f"agent protocol failed: {type(exc).__name__}: {exc}"
            return None
        finally:
            self.last_seconds = monotonic() - started

    def telemetry_receipt(self, episode_key: str) -> dict | None:
        if not self.alive():
            return None
        try:
            self.proc.stdin.write(json.dumps({
                "telemetry_control": "receipt", "episode_key": str(episode_key)}) + "\n")
            self.proc.stdin.flush()
            line = self._responses.get(timeout=5)
            return None if not line else json.loads(line).get("receipt")
        except (BrokenPipeError, OSError, ValueError, queue.Empty):
            return None

    def close(self) -> None:
        flushed = False
        if self.alive():
            try:
                self.proc.stdin.write('{"telemetry_control":"flush"}\n')
                self.proc.stdin.flush()
                response = self._responses.get(timeout=5)
                flushed = bool(response) and json.loads(response) == {"flushed": True}
            except (BrokenPipeError, OSError, ValueError, queue.Empty):
                pass
        try:
            self.proc.stdin and self.proc.stdin.close()
        except OSError:
            pass
        if flushed:
            try:
                self.proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
        elif self.alive():
            self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        try:
            self.proc.stdout and self.proc.stdout.close()
        except OSError:
            pass
        try:
            self.proc.stderr and self.proc.stderr.close()
        except OSError:
            pass
        self._reader.join(timeout=1)
        self._stderr_reader.join(timeout=1)


def play_match(server_a: AgentServer, server_b: AgentServer,
               deck_a: list[int], deck_b: list[int], *, recorder=None,
               decision_timeout=None, match_timeout=None, metrics=None,
               telemetry=None, episode_key=None, external_episode_id=None) -> MatchResult:
    """Drive one native Match, optionally capturing decisions and enforcing two deadlines."""
    from cg.game import battle_finish, battle_start, battle_select, visualize_data

    match_started = perf_counter()
    episode_key = str(episode_key or uuid4().hex)
    for server in (server_a, server_b):
        begin_episode = getattr(server, "begin_episode", None)
        if begin_episode is not None:
            begin_episode(episode_key)
    obs, start = battle_start(deck_a, deck_b)
    if start.errorPlayer >= 0:                     # illegal deck never gets to play -> loses
        battle_finish()
        winner = 1 - start.errorPlayer
        if telemetry is not None:
            from common.telemetry import (build_episode_receipt,
                                          build_outcome_record)
            current = obs.get("current") or {}
            players = current.get("players") or ()
            prizes = {seat: len((players[seat] or {}).get("prize") or ())
                      if seat < len(players) else 0 for seat in (0, 1)}
            receipt = build_episode_receipt(episode_key=episode_key, reservations=[])
            telemetry.append(receipt)
            telemetry.append(build_outcome_record(
                episode_key=episode_key,
                decision_records=[],
                telemetry_receipt=receipt,
                winner=winner,
                terminal_reason="illegal_deck",
                public_prizes=prizes,
                rewards={winner: 1.0, start.errorPlayer: -1.0},
                duration_seconds=perf_counter() - match_started,
                external_episode_id=external_episode_id,
            ))
        return MatchResult(winner=winner, crashed=(start.errorPlayer,))

    servers = (server_a, server_b)
    winner: int | None = None
    crashed: tuple[int, ...] = ()
    timed_out: tuple[int, ...] = ()
    match_deadline_hit = False
    failure = None
    deadline = monotonic() + float(match_timeout) if match_timeout is not None else None
    decision_index = 0
    visualizer = None
    try:
        for _ in range(_MAX_STEPS):
            cur = obs.get("current") or {}
            res = cur.get("result")
            if res is not None and res != -1:      # engine verdict: 0/1 winner, else a draw
                winner = res if res in (0, 1) else None
                break
            if obs.get("select") is None:
                break
            if deadline is not None and monotonic() >= deadline:
                match_deadline_hit = True
                break
            seat = cur.get("yourIndex", 0)
            remaining = max(0.0, deadline - monotonic()) if deadline is not None else None
            timeout = (min(float(decision_timeout), remaining)
                       if decision_timeout is not None and remaining is not None
                       else float(decision_timeout) if decision_timeout is not None else remaining)
            choice = servers[seat].act(obs, timeout=timeout)
            if choice is None:                     # seat crashed -> other seat wins
                if (servers[seat].last_timeout and deadline is not None
                        and monotonic() >= deadline):
                    match_deadline_hit = True
                elif servers[seat].last_timeout:
                    winner = 1 - seat
                    timed_out = (seat,)
                else:
                    winner = 1 - seat
                    crashed = (seat,)
                failure = getattr(servers[seat], "last_error", None)
                break
            if telemetry is not None:
                telemetry.extend(servers[seat].last_telemetry)
            if metrics is not None:
                measured = {"engine_seat": seat, "decision_index": decision_index,
                            "round_trip_seconds": servers[seat].last_seconds,
                            "telemetry_seconds": getattr(
                                servers[seat], "last_telemetry_seconds", 0.0)}
                metrics.extend({**record, **measured}
                               for record in servers[seat].last_telemetry)
                if not servers[seat].last_telemetry:   # telemetry off: the clock is the whole row
                    metrics.append(measured)
            decision_index += 1
            if recorder is not None:
                recorder.step(obs, choice)         # (obs shown, choice made) — paired for the +1-offset film
            try:
                obs = battle_select(choice)
            except Exception as exc:               # illegal selection is a loss, same as a crash
                winner, crashed = 1 - seat, (seat,)
                failure = f"engine rejected selection: {type(exc).__name__}: {exc}"
                break
    finally:
        if recorder is not None:
            try:
                visualizer = json.loads(visualize_data())
            except Exception:
                visualizer = None
        battle_finish()
    if recorder is not None:
        recorder.finish(obs, winner, visualizer)   # legal obs for training; god film for viewing
    if telemetry is not None:
        from common.telemetry import (build_episode_receipt, build_outcome_record,
                                      validate_record)

        current = obs.get("current") or {}
        players = current.get("players") or ()
        prizes = {seat: len((players[seat] or {}).get("prize") or ())
                  for seat in range(min(2, len(players)))}
        prizes.update({seat: prizes.get(seat, 0) for seat in (0, 1)})
        reason = ("agent_crash" if crashed else "decision_timeout" if timed_out else
                  "match_deadline" if match_deadline_hit else
                  "engine_win" if winner is not None else "draw")
        decisions = [record for record in telemetry
                     if record.get("record_type") == "decision"]
        journal = {}
        receipt_failures = []
        for seat, server in enumerate(servers):
            query = getattr(server, "telemetry_receipt", None)
            if query is None:
                receipt_failures.append({
                    "record_id": f"missing-agent-receipt-{seat}-{episode_key}",
                    "seat": seat,
                    "index": 0,
                    "status": "delivery_failed",
                    "error_type": "TelemetryReceiptUnavailable",
                })
                continue
            server_receipt = query(episode_key)
            try:
                server_receipt = validate_record(server_receipt)
                if server_receipt["record_type"] != "telemetry_receipt" \
                        or server_receipt["episode"]["key"] != episode_key:
                    raise ValueError("agent telemetry receipt belongs to another episode")
            except (KeyError, TypeError, ValueError):
                receipt_failures.append({
                    "record_id": f"missing-agent-receipt-{seat}-{episode_key}",
                    "seat": seat,
                    "index": 0,
                    "status": "delivery_failed",
                    "error_type": "TelemetryReceiptUnavailable",
                })
                continue
            for row in server_receipt["reservations"]:
                journal[row["record_id"]] = dict(row)
        reservations = []
        for decision in decisions:
            reservations.append(journal.pop(decision["record_id"], {
                "record_id": decision["record_id"],
                "seat": decision["decision"]["seat"],
                "index": decision["decision"]["index"],
                "status": "delivery_failed",
                "error_type": "TelemetryReservationUnavailable",
            }))
        reservations.extend(journal.values())
        reservations.extend(receipt_failures)
        receipt = build_episode_receipt(
            episode_key=episode_key, reservations=reservations)
        telemetry.append(receipt)
        if receipt["certified"]:
            telemetry.append(build_outcome_record(
                episode_key=episode_key,
                decision_records=decisions,
                telemetry_receipt=receipt,
                winner=winner,
                terminal_reason=reason,
                public_prizes=prizes,
                rewards={0: 0.0 if winner is None else 1.0 if winner == 0 else -1.0,
                         1: 0.0 if winner is None else 1.0 if winner == 1 else -1.0},
                duration_seconds=perf_counter() - match_started,
                external_episode_id=external_episode_id,
            ))
    return MatchResult(winner=winner, crashed=crashed, timed_out=timed_out,
                       match_deadline_hit=match_deadline_hit, failure=failure)


def _play_seated(server_a, server_b, deck_a, deck_b, a_seat: int) -> BattleMatch:
    """Play one Match with contestant A in engine seat `a_seat`, returning a CONTESTANT-relative
    `BattleMatch`."""
    if a_seat == 0:
        res = play_match(server_a, server_b, deck_a, deck_b)
    else:
        res = play_match(server_b, server_a, deck_b, deck_a)   # A sits in engine seat 1
    return to_battle_match(a_seat, res)


def _split(n: int, jobs: int) -> list[int]:
    """Spread `n` Matches across `jobs` workers as evenly as possible (drops empty shares)."""
    base, extra = divmod(n, jobs)
    return [base + (1 if i < extra else 0) for i in range(jobs) if base + (1 if i < extra else 0)]


def _run_serial(dir_a: Path, dir_b: Path, deck_a, deck_b, n, extra_syspath,
                overlay_a=None, overlay_b=None) -> list[BattleMatch]:
    """Run `n` seat-balanced Matches through one persistent pair of servers (import paid once).
    Server identity (a=A, b=B) is fixed; only the engine *seat* alternates per `seat_plan`."""
    a = AgentServer(dir_a, extra_syspath, overlay=overlay_a)
    b = AgentServer(dir_b, extra_syspath, overlay=overlay_b)
    results = []
    try:
        for a_seat in seat_plan(n):
            results.append(_play_seated(a, b, deck_a, deck_b, a_seat))
            if not a.alive():                      # crash killed the server -> respawn for next Match
                a = AgentServer(dir_a, extra_syspath, overlay=overlay_a)
            if not b.alive():
                b = AgentServer(dir_b, extra_syspath, overlay=overlay_b)
    finally:
        a.close()
        b.close()
    return results


def run_battle(dir_a: Path, dir_b: Path, deck_a, deck_b, n, *, jobs=1,
               extra_syspath=(), overlay_a=None, overlay_b=None) -> list[BattleMatch]:
    """Run a Battle of `n` seat-balanced Matches across `jobs` worker processes — each needs its own
    engine + server pair, since the native engine keeps PER-PROCESS state. Order-independent."""
    if jobs <= 1 or n <= 1:
        return _run_serial(dir_a, dir_b, deck_a, deck_b, n, extra_syspath, overlay_a, overlay_b)
    procs = []
    plan = seat_plan(n)                            # split seats GLOBALLY, hand each worker its slice,
    i = 0                                          # so odd per-worker shares can't all tilt the same way
    for share in _split(n, jobs):
        seats = ",".join(str(s) for s in plan[i:i + share])
        i += share
        cmd = [sys.executable, str(_WORKER), str(dir_a), str(dir_b), seats,
               str(overlay_a or "-"), str(overlay_b or "-"), *(str(p) for p in extra_syspath)]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8"))
    results = []
    for proc in procs:
        out, _ = proc.communicate()
        for line in out.splitlines():
            if line.strip():
                d = json.loads(line)
                results.append(BattleMatch(a_seat=d["a_seat"], winner=d["winner"],
                                           crashed=tuple(d["crashed"])))
    return results


def _bundle_dir(row: dict, *, out: Path, into: Path) -> Path:
    """Extract a Build's artifact zip into `into` and return the Bundle dir (self-contained)."""
    import zipfile

    dest = Path(into) / row["artifact"]
    with zipfile.ZipFile(Path(out) / f"{row['artifact']}.zip") as zf:
        zf.extractall(dest)
    return dest


def _read_overlay(path):
    """The overlay's contents ({overrides, params}) recorded in the Battle Result, or None."""
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else None


def _git_short() -> str:
    """The current short commit (+`-dirty`) — provenance for a working-tree contestant."""
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                              capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                               capture_output=True, text=True).stdout.strip()
        return (head or "?") + ("-dirty" if dirty else "")
    except OSError:
        return "working"


def resolve(spec: str, rows: list[dict], *, agents_root: Path, out: Path, into: Path) -> tuple:
    """Resolve a CLI contestant to a (provenance row, Bundle dir): an **integer** is a Build id
    (its zip is extracted under `into`); a **name** is the working-tree agent under `agents_root`."""
    if spec.isdigit():
        row = resolve_contestant(spec, rows)
        return row, _bundle_dir(row, out=out, into=into)
    agent_dir = Path(agents_root) / spec
    if not (agent_dir / "main.py").exists():
        raise ValueError(f"no working-tree agent {spec!r} under {agents_root} (or pass a build id)")
    row = {"submission_id": "src", "agent": spec, "label": "working-tree", "git_hash": _git_short()}
    return row, agent_dir


def _default_jobs() -> int:
    return min(10, os.cpu_count() or 1)


def main(argv=None) -> int:
    import argparse
    import tempfile
    import time

    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]   # standalone CLI: needs submit / cg

    if os.environ.get("CG_ENGINE") == "py":            # ADR-0050 M3: drive the cgpy twin
        from cgpy.alias import install
        install()

    from submit.build import DEFAULT_BUILDS, DEFAULT_OUT
    from submit.history import read_history

    ap = argparse.ArgumentParser(
        description="Battle: N Matches between two contestants. A curiosity read, not a "
                    "promotion gate — see tools/sim/CONTEXT.md.")
    ap.add_argument("a", help="contestant A: a build id / agent name, optionally `@overlay.json`")
    ap.add_argument("b", help="contestant B: a build id / agent name, optionally `@overlay.json`")
    ap.add_argument("-n", "--games", type=int, default=20, help="number of Matches (default 20)")
    ap.add_argument("-j", "--jobs", type=int, default=_default_jobs(),
                    help="worker processes (default: min(10, cores))")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="dir holding the build artifact zips")
    ap.add_argument("--builds", default=str(DEFAULT_BUILDS), help="the Build Ledger")
    ap.add_argument("--agents-root", default=str(REPO / "src" / "agents"),
                    help="dir of working-tree agents (for a name contestant)")
    ap.add_argument("--note", default="", help="experiment intent recorded in the Battle Result")
    ap.add_argument("--mode", default=None, choices=["pre-filter", "curiosity"],
                    help="default: pre-filter if an overlay is given, else curiosity")
    args = ap.parse_args(argv)

    from datetime import datetime, timezone

    from sim.result import DEFAULT_LOG, append_battle, build_battle_result, next_battle_id

    base_a, overlay_a = parse_spec(args.a)
    base_b, overlay_b = parse_spec(args.b)
    mode = args.mode or ("pre-filter" if (overlay_a or overlay_b) else "curiosity")

    rows = read_history(args.builds)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            a_row, dir_a = resolve(base_a, rows, agents_root=args.agents_root,
                                   out=Path(args.out), into=Path(tmp))
            b_row, dir_b = resolve(base_b, rows, agents_root=args.agents_root,
                                   out=Path(args.out), into=Path(tmp))
        except ValueError as e:
            print(f"error: {e}")
            return 1
        deck_a, deck_b = read_deck(dir_a), read_deck(dir_b)
        t0 = time.monotonic()
        results = run_battle(dir_a, dir_b, deck_a, deck_b, args.games, jobs=args.jobs,
                             extra_syspath=[REPO / "src"], overlay_a=overlay_a, overlay_b=overlay_b)
        elapsed = time.monotonic() - t0

    bt = balanced_tally(results)
    print(format_report(a_row, b_row, bt, elapsed=elapsed, jobs=args.jobs, mode=mode))

    result = build_battle_result(
        battle_id=next_battle_id(), ran_at=datetime.now(timezone.utc).isoformat(),
        run_git_hash=_git_short(), mode=mode, hypothesis=args.note,
        contestants=[{"row": a_row, "deck_ids": deck_a, "overlay": _read_overlay(overlay_a)},
                     {"row": b_row, "deck_ids": deck_b, "overlay": _read_overlay(overlay_b)}],
        records=results,
        params={"n_requested": args.games, "jobs": args.jobs, "max_steps": _MAX_STEPS,
                "seat_balanced": True, "n_as_deck0": sum(1 for r in results if r.a_seat == 0),
                "n_as_deck1": sum(1 for r in results if r.a_seat == 1)},
    )
    append_battle(DEFAULT_LOG, result)
    print(f"  -> Battle Result #{result['battle_id']} appended to {DEFAULT_LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
