"""The C3 eval report (contract C3 in docs/plans/ml/ml-training-contracts.md): the JSON the eval
harness emits and the G2 adoption gate consumes. This module owns the verdict rule, the
checkpoint regression tripwire, the pure checkpoint-pool resolution, and the report assembler.

Verdict = the grilled ``flips_on`` rule (``sim.paired_ab``): ship only on a demonstrated
non-regression with zero candidate crashes, never on a green suite alone — and never on a run
that did not actually measure the powered matrix (empty pairs or a capped/partial run cap the
verdict at ``inconclusive``). The frozen-checkpoint pool (past submitted builds) is a
**tripwire**, never a delta member: a checkpoint can never make a verdict pass (it isn't in the
paired contrast), but a candidate that regresses against one — the rock-paper-scissors /
non-transitivity drift a raw gauntlet hides — caps the verdict at ``inconclusive`` and names the
culprit.
"""
from __future__ import annotations

import math

from sim.paired_ab import _Z95, flips_on, matchup_delta, paired_delta

REPORT_VERSION = 1


def _cell_n(cell: dict, arm: str) -> int:
    """The arm's own game count in a matchup cell — the per-arm ``candidate_n``/``baseline_n`` when
    present (correct even if a resume left the arms different sizes), else the shared ``n``."""
    return cell.get(f"{arm}_n", cell.get("n", 0))


def checkpoint_regressions(checkpoints: list, *, z: float = _Z95) -> list[dict]:
    """Which frozen checkpoints the candidate REGRESSES against, worst-first: flagged when the
    candidate is worse by MORE than the cell's own CI margin (``delta < −z·√var``), i.e. not noise."""
    flags = []
    for c in checkpoints:
        if c["candidate_n"] <= 0 or c["baseline_n"] <= 0:
            continue                                          # a cell with no games can't regress
        delta, var = matchup_delta(c["candidate_wins"], c["candidate_n"],
                                   c["baseline_wins"], c["baseline_n"])
        margin = z * math.sqrt(var)
        if delta < -margin:
            flags.append({"build_id": c["build_id"], "win_delta": delta, "margin": margin})
    return sorted(flags, key=lambda f: f["win_delta"])


def verdict(paired: dict, *, candidate_crashes: int, regressions: list, complete: bool = True) -> str:
    """Map a raw ``paired_ab.paired_delta`` to G2's read. An empty or INCOMPLETE matrix can never
    PASS whatever its surviving cells say — it is ``inconclusive`` unless the loss is unambiguous."""
    if paired.get("n_matchups", 0) == 0:
        return "inconclusive"                                 # measured nothing -> never a pass
    if paired["ci_hi"] < 0:
        return "fail"
    if complete and flips_on(paired, crashes=candidate_crashes) and not regressions:
        return "pass"
    return "inconclusive"


def checkpoint_pool(history_rows: list, available_artifacts, *, extra_ids=()) -> tuple[list, list]:
    """The frozen-checkpoint pool -> ``(pool, warnings)``: submitted builds whose artifact zip is on
    disk, plus ``extra_ids``, which ADD to the pool and never restrict it. Misses warn, not raise."""
    available = set(available_artifacts)
    extra = {int(i) for i in extra_ids}
    by_id = {row.get("submission_id"): row for row in history_rows}
    pool, warnings, seen = [], [], set()

    def _add(row):
        sid, artifact = row.get("submission_id"), row.get("artifact")
        if sid in seen:
            return
        seen.add(sid)
        if artifact in available:
            pool.append({"submission_id": sid, "agent": row.get("agent"), "artifact": artifact})
        else:
            warnings.append(f"checkpoint #{sid} ({row.get('agent')}) — zip {artifact!r} missing, skipped")

    for row in history_rows:                                  # the standing pool: all submitted builds
        _add(row)
    for sid in extra:                                         # plus the pinned extras (additive)
        if sid in by_id:
            _add(by_id[sid])
        elif sid not in seen:
            warnings.append(f"checkpoint #{sid} — not in agent_history, skipped")
    return pool, warnings


def _raw_paired(pairs: list) -> dict:
    """The raw ``paired_ab.paired_delta`` aggregate. Empty input -> a zero-width interval with
    ``n_matchups`` 0, which the verdict reads as inconclusive, never a pass."""
    if not pairs:
        return {"delta": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "n_matchups": 0}
    return paired_delta(pairs)


def _c3_paired(raw: dict) -> dict:
    """The paired aggregate in C3 field names (``win_delta``/``ci_low``/``ci_high``/``method``)."""
    return {"win_delta": raw["delta"], "ci_low": raw["ci_lo"], "ci_high": raw["ci_hi"],
            "method": "paired-normal"}


def build_report(*, baseline: dict, candidate: dict, matchups: list, h2h: list = (),
                 checkpoints: list = (), strata: list = (), aivat=None,
                 candidate_crashes: int = 0, git_rev: str = "", generated_at: str = "",
                 preset: str = "", per_cell_n: int = 0, status: str = "complete",
                 coverage: dict | None = None) -> dict:
    """Assemble the frozen C3 report (``report_version`` 1). ONLY ``matchups`` feeds the paired
    win-delta — ``h2h`` is emitted tagged ``informational`` and ``checkpoints`` never enters it."""
    pairs = [(c["candidate_wins"], _cell_n(c, "candidate"), c["baseline_wins"], _cell_n(c, "baseline"))
             for c in matchups if _cell_n(c, "candidate") > 0 and _cell_n(c, "baseline") > 0]
    raw = _raw_paired(pairs)
    regressions = checkpoint_regressions(list(checkpoints)) if checkpoints else []
    complete = status == "complete"

    emitted_matchups = [dict(c) for c in matchups]
    for c in h2h:
        emitted_matchups.append({**c, "opponent": c.get("opponent", "h2h"), "informational": True})

    reg_ids = {r["build_id"] for r in regressions}
    c3_checkpoints = [{"build_id": c["build_id"], "n": c["candidate_n"],
                       "candidate_wins": c["candidate_wins"], "baseline_wins": c["baseline_wins"],
                       "regression": c["build_id"] in reg_ids} for c in checkpoints]

    n_games = (sum(_cell_n(c, "candidate") + _cell_n(c, "baseline") for c in matchups)
               + sum(c.get("n", 0) for c in h2h)
               + sum(c["candidate_n"] + c["baseline_n"] for c in checkpoints))

    return {
        "report_version": REPORT_VERSION,
        "generated_at": generated_at,
        "git_rev": git_rev,
        "baseline": baseline,
        "candidate": candidate,
        "preset": preset,
        "per_cell_n": per_cell_n,
        "status": status,
        "coverage": coverage or {},
        "n_games": n_games,
        "matchups": emitted_matchups,
        "paired_delta": _c3_paired(raw),
        "strata": list(strata),
        "checkpoints": c3_checkpoints,
        "regressions": regressions,
        "aivat": aivat,
        "verdict": verdict(raw, candidate_crashes=candidate_crashes, regressions=regressions,
                           complete=complete),
    }
