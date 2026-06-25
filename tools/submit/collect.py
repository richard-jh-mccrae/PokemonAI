"""collect: parse a match's replay + log into a performance sample (ADR-0019).

Reuses the Meta Tracker's replay parsing + Archetype classifier (no new recognition logic).
Works on the artifacts as downloaded from Kaggle (a replay JSON + an agent log) and, identically,
on a local `env.toJSON()` + `env.logs` — so the same code backs the system test and production.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median

from common.telemetry import TAG
from meta_tracker.archetype import classify
from meta_tracker.parse import extract_decks, winner_index
from package_agent import REPO

DEFAULT_PERF = REPO / "data" / "performance.jsonl"


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
    """Flatten a match log to our agent's per-decision entries.

    Handles both shapes: a downloaded single-agent log `[[{...}], ...]` and a local
    `env.logs` `[[seat0, seat1], [], ...]` (self-play — every seat is our agent).
    """
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
    """Many `parse_match` results -> one Performance Log sample (record, matchups, efficiency).

    `efficiency` summarises per-match medians/maxes (a tracking summary, not a pooled
    distribution); `matchups` is the per-Archetype win/loss dropdown.
    """
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


def _to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def kaggle_score(submission_id: int, *, competition: str = COMPETITION) -> dict:
    """Look up a Submission's `ref` + `public_score` from `submissions --csv`, matched by the
    `#<id>` our `-m` message carries in the `description` field."""
    import csv
    import io
    import subprocess
    out = subprocess.run(["kaggle", "competitions", "submissions", competition, "--csv"],
                         capture_output=True, text=True, check=True).stdout
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
    """Score + fetch + parse this Submission's matches, then append one Performance Log sample.

    `score_fn`/`fetch_fn` are injected (default Kaggle CLI / a local dir) so the orchestration is
    testable without the network; `parse_fn` defaults to `parse_match`.
    """
    parse_fn = parse_fn or parse_match
    score = score_fn(submission_id)
    matches = [parse_fn(replay, log, seat=seat, cards=cards)
               for replay, log in fetch_fn(score.get("kaggle_ref") or submission_id)]
    return record_sample(submission_id, matches, kaggle_ref=score.get("kaggle_ref"),
                         public_score=score.get("public_score"), rank=score.get("rank"),
                         when=when, perf_path=perf_path)


def record_sample(submission_id: int, matches: list[dict], *, kaggle_ref=None,
                  public_score=None, rank=None, when=None, perf_path=DEFAULT_PERF) -> dict:
    """Append one time-stamped Performance Log sample for a Submission (append-only, ADR-0019).

    `matches` are `parse_match` results; score/rank/`kaggle_ref` come from `submissions --csv`.
    Keyed by `submission_id` so it joins the Agent History row.
    """
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
