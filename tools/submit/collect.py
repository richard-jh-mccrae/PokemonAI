"""collect: parse a match's replay + log into a performance sample (ADR-0019).

Reuses the Meta Tracker's replay parsing + Archetype classifier (no new recognition logic).
Works on the artifacts as downloaded from Kaggle (a replay JSON + an agent log) and, identically,
on a local `env.toJSON()` + `env.logs` — so the same code backs the system test and production.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median

from common.telemetry import TAG
from meta_tracker.archetype import classify
from meta_tracker.parse import extract_decks, winner_index
from submit.package import REPO

DEFAULT_PERF = REPO / "data" / "performance.jsonl"
DEFAULT_REPLAYS = REPO / "data" / "replays"


def parse_telemetry(stderr: str) -> list[dict]:
    """The `@T` Decision Telemetry records embedded in a stderr blob (bad lines skipped)."""
    out = []
    for line in (stderr or "").splitlines():
        if line.startswith(TAG):
            try:
                out.append(json.loads(line[len(TAG):].strip()))
            except json.JSONDecodeError:
                pass
    return out


def _log_entries(log) -> list[dict]:
    """Flatten a match log to our agent's per-decision entries. Handles BOTH shapes: a downloaded
    single-agent log and a local `env.logs` (self-play, where every seat is ours)."""
    return [e for step in (log or []) for e in step if e]


def _timing(durations: list[float]) -> dict:
    """Per-decision timing in ms; the first call (import + first decision) is the cold start."""
    ms = [round(d * 1000, 1) for d in durations if d is not None]
    if not ms:
        return {"count": 0}
    steady = ms[1:] or ms      # exclude the cold-start decision from steady-state stats
    return {
        "count": len(ms),
        "cold_start_ms": ms[0],
        "median_ms": round(median(steady), 1),
        "max_ms": max(steady),
    }


def aggregate_matches(matches: list[dict]) -> dict:
    """Many `parse_match` results -> one Performance Log sample. `efficiency` summarises per-match
    medians/maxes — a tracking summary, NOT a pooled distribution."""
    tally = {"wins": 0, "losses": 0, "draws": 0}
    matchups: dict[str, dict] = {}
    tier: Counter = Counter()
    decisions = 0
    for m in matches:
        tally[{"win": "wins", "loss": "losses", "draw": "draws"}[m["result"]]] += 1
        row = matchups.setdefault(m["opponent_archetype"],
                                  {"archetype": m["opponent_archetype"], "wins": 0, "losses": 0})
        if m["result"] == "win":
            row["wins"] += 1
        elif m["result"] == "loss":
            row["losses"] += 1
        decisions += m["telemetry"]["decisions"]
        tier.update(m["telemetry"]["tier_mix"])
    meds = [m["decision_ms"]["median_ms"] for m in matches if m["decision_ms"].get("count")]
    maxes = [m["decision_ms"]["max_ms"] for m in matches if m["decision_ms"].get("count")]
    return {
        "record": tally,
        "matchups": sorted(matchups.values(), key=lambda r: r["archetype"]),
        "efficiency": {"matches": len(matches),
                       "median_ms": round(median(meds), 1) if meds else 0,
                       "max_ms": max(maxes) if maxes else 0},
        "telemetry": {"decisions": decisions, "tier_mix": dict(tier)},
    }


COMPETITION = "pokemon-tcg-ai-battle"

# Shown when the Kaggle CLI/API can't authenticate — `collect` needs Kaggle (scores + replays).
_AUTH_HINT = (
    "Kaggle isn't authenticated. Set KAGGLE_API_TOKEN, or save the token to "
    "%USERPROFILE%\\.kaggle\\access_token (see kaggle_api_token/instructions.txt), then retry."
)


def _looks_like_auth_error(text: str) -> bool:
    t = (text or "").lower()
    return "authentication required" in t or "401" in t or "403" in t or "unauthorized" in t


def _to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _run_kaggle(args: list[str]) -> str:
    """Run a `kaggle` CLI command -> stdout. A non-zero exit raises `SystemExit` carrying the CLI's
    own stderr, which `check=True` + `capture_output` would otherwise swallow."""
    import subprocess
    try:
        proc = subprocess.run(["kaggle", *args], capture_output=True, text=True)
    except FileNotFoundError:
        raise SystemExit("the `kaggle` CLI isn't installed — `pip install kaggle` (or activate the venv).")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise SystemExit(_AUTH_HINT if _looks_like_auth_error(err)
                         else f"`kaggle {' '.join(args)}` failed (exit {proc.returncode}):\n{err}")
    return proc.stdout


def kaggle_score(submission_id: int, *, competition: str = COMPETITION) -> dict:
    """Look up a Submission's `ref` + `public_score` from `submissions --csv`, matched by the
    `#<id>` our `-m` message carries in the `description` field."""
    import csv
    import io
    out = _run_kaggle(["competitions", "submissions", competition, "--csv"])
    for r in csv.DictReader(io.StringIO(out)):
        if (r.get("description") or "").startswith(f"#{submission_id} "):
            return {"kaggle_ref": r.get("ref"), "public_score": _to_float(r.get("publicScore")),
                    "rank": None}
    return {"kaggle_ref": None, "public_score": None, "rank": None}


def fetch_from_dir(replays_dir) -> list[tuple[dict, list]]:
    """Read locally-downloaded `<stem>.replay.json` + `<stem>.log.json` pairs into (replay, log)s."""
    replays_dir = Path(replays_dir)
    pairs = []
    for rp in sorted(replays_dir.glob("*.replay.json")):
        lp = rp.with_name(rp.name.replace(".replay.json", ".log.json"))
        replay = json.loads(rp.read_text(encoding="utf-8"))
        log = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else []
        pairs.append((replay, log))
    return pairs


def collect(submission_id: int, *, score_fn, fetch_fn, parse_fn=None, seat: int = 0,
            when=None, perf_path=DEFAULT_PERF, cards: dict | None = None) -> dict:
    """Score + fetch + parse this Submission's matches, then append one Performance Log sample. The
    `*_fn` keywords are injected so the orchestration is testable without the network."""
    parse_fn = parse_fn or parse_match
    score = score_fn(submission_id)
    matches = [parse_fn(replay, log, seat=seat, cards=cards)
               for replay, log in fetch_fn(score.get("kaggle_ref") or submission_id)]
    return record_sample(submission_id, matches, kaggle_ref=score.get("kaggle_ref"),
                         public_score=score.get("public_score"), rank=score.get("rank"),
                         when=when, perf_path=perf_path)


def record_sample(submission_id: int, matches: list[dict], *, kaggle_ref=None,
                  public_score=None, rank=None, when=None, perf_path=DEFAULT_PERF) -> dict:
    """Append one time-stamped Performance Log sample (append-only, ADR-0019), keyed by
    `submission_id` so it joins the Agent History row."""
    sample = {
        "submission_id": submission_id,
        "kaggle_ref": kaggle_ref,
        "sampled_at": (when or datetime.now()).isoformat(timespec="seconds"),
        "public_score": public_score,
        "rank": rank,
        **aggregate_matches(matches),
    }
    perf_path = Path(perf_path)
    perf_path.parent.mkdir(parents=True, exist_ok=True)
    with perf_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(sample, ensure_ascii=False) + "\n")
    return sample


def parse_match(replay: dict, log, *, seat: int = 0, cards: dict | None = None) -> dict:
    """One match -> {result, opponent_archetype, decision_ms, telemetry} for the Performance Log."""
    winner = winner_index(replay)
    result = "draw" if winner is None else ("win" if winner == seat else "loss")
    decks = extract_decks(replay)
    opponent = classify(decks[1 - seat], cards).name

    entries = _log_entries(log)
    durations = [e.get("duration") for e in entries]
    records = parse_telemetry("\n".join(e.get("stderr", "") for e in entries))
    return {
        "result": result,
        "opponent_archetype": opponent,
        "decision_ms": _timing(durations),
        "telemetry": {
            "decisions": len(records),
            "tier_mix": dict(Counter(str(r.get("tier")) for r in records)),
        },
    }


def _resolve_submitted(history, submission_id):
    """The Agent History row for a *submitted* build — `submission_id`, or the latest."""
    from submit.history import read_history
    rows = [r for r in read_history(history) if r.get("submitted_at")]
    if not rows:
        raise SystemExit("no submitted agents yet — run `submit` first")
    if submission_id is None:
        return rows[-1]
    row = next((r for r in rows if r["submission_id"] == submission_id), None)
    if row is None:
        raise SystemExit(f"no submitted build #{submission_id} in the history")
    return row


def collect_submission(submission_id: int | None = None, *, history=None,
                       replays_root=DEFAULT_REPLAYS, perf_path=DEFAULT_PERF, max_replays: int = 20,
                       download_fn=None, score_fn=None, parse_fn=None, cards=None, when=None) -> dict:
    """Resolve a submitted build, download up to `max_replays` matches, parse them, append a
    Performance Log sample. `download_fn` yields `(replay, log, seat)` — `seat` VARIES per match."""
    if history is None:
        from submit.build import DEFAULT_HISTORY
        history = DEFAULT_HISTORY
    row = _resolve_submitted(history, submission_id)
    dest = Path(replays_root) / row["artifact"]          # data/replays/<same name as the .zip>
    parse = parse_fn or parse_match
    score = (score_fn or kaggle_score)(row["submission_id"])
    triples = (download_fn or _kaggle_download)(row, dest, max_replays,
                                                kaggle_ref=score.get("kaggle_ref"))
    matches = [parse(replay, log, seat=seat, cards=cards) for replay, log, seat in triples]
    return record_sample(row["submission_id"], matches, kaggle_ref=score.get("kaggle_ref"),
                         public_score=score.get("public_score"), rank=score.get("rank"),
                         when=when, perf_path=perf_path)


def _our_seat(episode, sub_id: int) -> int:
    """The 0-based agent index our submission occupied in this episode (0 if undeterminable)."""
    agents = getattr(episode, "agents", None) or getattr(episode, "episode_agents", None) or []
    for a in agents:
        a_sub = getattr(a, "submission_id", None) or getattr(a, "submissionId", None)
        if a_sub == sub_id and getattr(a, "index", None) is not None:
            return int(a.index)
    return 0   # Kaggle serves our own log in slot 0 when ownership can't match


def _kaggle_download(row: dict, dest, max_replays: int, *, kaggle_ref=None, api=None,
                     sleep=None) -> list[tuple[dict, list, int]]:
    """Download up to `max_replays` of OUR episodes into `dest` -> (replay, log, our_seat) triples.
    INCREMENTAL: an episode already on disk is reused. Throttled to <=1/sec on actual fetches."""
    import time

    sleep = sleep or time.sleep
    if kaggle_ref is None:
        raise SystemExit("no Kaggle submission id — is the submission scored yet (submissions --csv)?")
    try:
        sub_id = int(kaggle_ref)
    except (TypeError, ValueError):
        raise SystemExit(f"unexpected Kaggle submission ref {kaggle_ref!r}; expected a numeric id")

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if api is None:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        try:
            api.authenticate()   # reads ~/.kaggle/access_token / KAGGLE_API_TOKEN (never logged)
        except Exception as e:
            raise SystemExit(f"{_AUTH_HINT}\n({e})")

    triples, fetched = [], 0
    for ep in list(api.competition_list_episodes(submission_id=sub_id))[:max_replays]:
        ep_id = getattr(ep, "id", None) or ep["id"]
        seat = _our_seat(ep, sub_id)
        replay_path = dest / f"episode-{ep_id}-replay.json"
        log_path = dest / f"episode-{ep_id}-agent-{seat}-logs.json"
        hit = False
        if not replay_path.exists():                  # only fetch what we don't already have
            api.competition_episode_replay(episode_id=ep_id, path=str(dest))
            hit = True
        if not log_path.exists():
            api.competition_episode_agent_logs(episode_id=ep_id, agent_index=seat, path=str(dest))
            hit = True
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
        triples.append((replay, log, seat))
        if hit:
            fetched += 1
            sleep(1)     # courtesy throttle — Kaggle: <=1/sec, <=3600/day; back off on 429
    print(f"episodes: {len(triples)} total · {fetched} downloaded · {len(triples) - fetched} cached"
          f" -> {dest}", file=sys.stderr)
    return triples
