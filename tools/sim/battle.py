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
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SERVER = Path(__file__).with_name("_agent_server.py")
_WORKER = Path(__file__).with_name("_battle_worker.py")
_MAX_STEPS = 5000          # a runaway-game backstop; a real Match resolves in ~100s of steps


@dataclass(frozen=True)
class MatchResult:
    """One Match outcome: winner seat (0=A, 1=B, None=draw) and which seats crashed.

    A crash already decides the Match — the crashing seat loses — so `winner` is the other
    seat; `crashed` only carries the flag so the Report can surface it separately.
    """
    winner: int | None
    crashed: tuple[int, ...] = ()


def resolve_contestant(spec: str, rows: list[dict]) -> dict:
    """Resolve a CLI contestant `spec` to a Build row from the ledger `rows`.

    An all-digit `spec` is a **Build id** (`submission_id`); anything else is an **agent
    name**, resolved to that agent's *latest* build. Raises ValueError naming the miss.
    """
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


def _tag(row: dict) -> str:
    """`#3 mega_starmie (tuned, ccc)` — the contestant's provenance, one line."""
    sid = row.get("submission_id", "?")
    bits = [b for b in (row.get("label"), (row.get("git_hash") or "")[:7]) if b]
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
    """A contestant running in its own process: feed it an observation, get back its choice.

    Isolation (own cwd / `sys.path` / `sys.modules`) is the whole point — it lets two
    *different* Bundles play one Match without colliding, which an in-process load cannot.
    """

    def __init__(self, bundle: Path | str, extra_syspath=()):
        env = dict(os.environ, AGENT_NO_TELEMETRY="1", PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, str(_SERVER), *(str(p) for p in extra_syspath)],
            cwd=str(bundle), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def act(self, obs: dict) -> list[int] | None:
        """The contestant's chosen option indices for `obs`, or None if it crashed/died."""
        try:
            self.proc.stdin.write(json.dumps(obs) + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
            return json.loads(line) if line.strip() else None
        except (BrokenPipeError, OSError, ValueError):
            return None

    def close(self) -> None:
        for stream in (self.proc.stdin, self.proc.stdout):
            try:
                stream and stream.close()
            except OSError:
                pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def play_match(server_a: AgentServer, server_b: AgentServer,
               deck_a: list[int], deck_b: list[int]) -> MatchResult:
    """Drive one Match on the native engine: seat A vs B, ask whichever seat is to move, until
    the engine reports a `result`. A crashed/illegal seat loses the Match (and is flagged)."""
    from cg.game import battle_finish, battle_start, battle_select

    obs, start = battle_start(deck_a, deck_b)
    if start.errorPlayer >= 0:                     # an illegal deck never gets to play -> it loses
        battle_finish()
        return MatchResult(winner=1 - start.errorPlayer, crashed=(start.errorPlayer,))

    servers = (server_a, server_b)
    winner: int | None = None
    crashed: tuple[int, ...] = ()
    try:
        for _ in range(_MAX_STEPS):
            cur = obs.get("current") or {}
            res = cur.get("result")
            if res is not None and res != -1:      # engine verdict: 0/1 winner, anything else a draw
                winner = res if res in (0, 1) else None
                break
            if obs.get("select") is None:
                break
            seat = cur.get("yourIndex", 0)
            choice = servers[seat].act(obs)
            if choice is None:                     # the seat crashed -> the other seat wins
                winner, crashed = 1 - seat, (seat,)
                break
            try:
                obs = battle_select(choice)
            except Exception:                      # an illegal selection is a loss, same as a crash
                winner, crashed = 1 - seat, (seat,)
                break
    finally:
        battle_finish()
    return MatchResult(winner=winner, crashed=crashed)


def _split(n: int, jobs: int) -> list[int]:
    """Spread `n` Matches across `jobs` workers as evenly as possible (drops empty shares)."""
    base, extra = divmod(n, jobs)
    return [base + (1 if i < extra else 0) for i in range(jobs) if base + (1 if i < extra else 0)]


def _run_serial(dir_a: Path, dir_b: Path, deck_a, deck_b, n, extra_syspath) -> list[MatchResult]:
    """Run `n` Matches in this process through one persistent pair of servers (import paid once)."""
    a = AgentServer(dir_a, extra_syspath)
    b = AgentServer(dir_b, extra_syspath)
    results = []
    try:
        for _ in range(n):
            results.append(play_match(a, b, deck_a, deck_b))
            if not a.alive():                      # a crash killed the server -> respawn for the next Match
                a = AgentServer(dir_a, extra_syspath)
            if not b.alive():
                b = AgentServer(dir_b, extra_syspath)
    finally:
        a.close()
        b.close()
    return results


def run_battle(dir_a: Path, dir_b: Path, deck_a, deck_b, n, *, jobs=1,
               extra_syspath=()) -> list[MatchResult]:
    """Run a Battle of `n` Matches, fanned across `jobs` worker processes (each with its own
    engine + server pair, since the native engine keeps per-process state). Order-independent."""
    if jobs <= 1 or n <= 1:
        return _run_serial(dir_a, dir_b, deck_a, deck_b, n, extra_syspath)
    procs = []
    for share in _split(n, jobs):
        cmd = [sys.executable, str(_WORKER), str(dir_a), str(dir_b), str(share),
               *(str(p) for p in extra_syspath)]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8"))
    results = []
    for proc in procs:
        out, _ = proc.communicate()
        for line in out.splitlines():
            if line.strip():
                d = json.loads(line)
                results.append(MatchResult(winner=d["winner"], crashed=tuple(d["crashed"])))
    return results


def _bundle_dir(row: dict, *, out: Path, into: Path) -> Path:
    """Extract a Build's artifact zip into `into` and return the Bundle dir (self-contained)."""
    import zipfile

    dest = Path(into) / row["artifact"]
    with zipfile.ZipFile(Path(out) / f"{row['artifact']}.zip") as zf:
        zf.extractall(dest)
    return dest


def _default_jobs() -> int:
    return min(10, os.cpu_count() or 1)


def main(argv=None) -> int:
    import argparse
    import tempfile
    import time

    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]   # standalone CLI: import submit / cg

    from submit.build import DEFAULT_BUILDS, DEFAULT_OUT
    from submit.history import read_history

    ap = argparse.ArgumentParser(
        description="Battle: N Matches between two Builds (a build id or agent name each). "
                    "A curiosity read, not a promotion gate — see tools/sim/CONTEXT.md.")
    ap.add_argument("a", help="contestant A: a build id (e.g. 7) or agent name (its latest build)")
    ap.add_argument("b", help="contestant B: a build id or agent name")
    ap.add_argument("-n", "--games", type=int, default=20, help="number of Matches (default 20)")
    ap.add_argument("-j", "--jobs", type=int, default=_default_jobs(),
                    help="worker processes (default: min(10, cores))")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="dir holding the build artifact zips")
    ap.add_argument("--builds", default=str(DEFAULT_BUILDS), help="the Build Ledger")
    args = ap.parse_args(argv)

    rows = read_history(args.builds)
    try:
        a_row = resolve_contestant(args.a, rows)
        b_row = resolve_contestant(args.b, rows)
    except ValueError as e:
        print(f"error: {e}")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        dir_a = _bundle_dir(a_row, out=Path(args.out), into=Path(tmp))
        dir_b = _bundle_dir(b_row, out=Path(args.out), into=Path(tmp))
        t0 = time.monotonic()
        results = run_battle(dir_a, dir_b, read_deck(dir_a), read_deck(dir_b), args.games,
                             jobs=args.jobs)
        elapsed = time.monotonic() - t0

    print(format_report(a_row, b_row, tally(results), elapsed=elapsed, jobs=args.jobs,
                        mode="curiosity"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
