"""The C3 eval report (contract C3 in docs/plans/ml/ml-training-contracts.md): the JSON the eval
harness emits and the G2 adoption gate consumes. This module owns the verdict rule, the
checkpoint regression tripwire, the pure checkpoint-pool resolution, and the report assembler.

Verdict = the grilled ``flips_on`` rule (``sim.paired_ab``): ship only on a demonstrated
non-regression with zero candidate crashes, never on a green suite alone. The frozen-checkpoint
pool (past submitted builds) is a **tripwire**, never a delta member: a checkpoint can never make
a verdict pass (it isn't in the paired contrast), but a candidate that regresses against one —
the rock-paper-scissors / non-transitivity drift a raw gauntlet hides — caps the verdict at
``inconclusive`` and names the culprit.
"""
from __future__ import annotations

import math

from sim.paired_ab import flips_on, matchup_delta, paired_delta

REPORT_VERSION = 1
_Z95 = 1.959964            # matches paired_ab: the CI a checkpoint cell's margin is read against


def checkpoint_regressions(checkpoints: list, *, z: float = _Z95) -> list[dict]:
    """Which frozen checkpoints the candidate REGRESSES against vs the baseline. Per checkpoint
    cell (``build_id``, candidate wins/n, baseline wins/n) compute the on−off delta and its
    variance; flag it when the candidate is worse by MORE than the cell's own CI margin
    (``delta < −z·√var``) — a real drop, not noise. Ordered worst-first."""
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


def verdict(paired: dict, *, candidate_crashes: int, regressions: list) -> str:
    """Map the paired win-delta CI to G2's read. ``paired`` is the raw ``paired_ab.paired_delta``
    dict (keys ``delta``/``ci_lo``/``ci_hi``), which is also what ``flips_on`` reads:

    - ``fail``  — the CI upper bound is below 0 (the candidate is provably worse overall).
    - ``pass``  — the ``flips_on`` rule holds (delta ≥ 0, CI lower bound ≥ −1%, zero candidate
      crashes) AND no checkpoint regression tripped.
    - ``inconclusive`` — everything else: a straddling CI, a crash, or a checkpoint regression
      capping an otherwise-clean pass.
    """
    if paired["ci_hi"] < 0:
        return "fail"
    if flips_on(paired, crashes=candidate_crashes) and not regressions:
        return "pass"
    return "inconclusive"


def checkpoint_pool(history_rows: list, available_artifacts, *, extra_ids=()) -> tuple[list, list]:
    """Resolve the frozen-checkpoint opponent pool (pure). Pool = the SUBMITTED builds recorded in
    ``agent_history.jsonl`` (``history_rows``) whose artifact zip is actually on disk
    (``available_artifacts`` = the set of present artifact stems), plus any ``extra_ids`` pinned by
    ``--checkpoints``. A submitted build with no local zip is skipped with a named warning (a
    checkpoint you can't run is reported, not silently dropped). Returns ``(pool, warnings)`` where
    each pool entry is ``{"submission_id", "agent", "artifact"}``."""
    available = set(available_artifacts)
    want = list(history_rows)
    ids = {int(i) for i in extra_ids}
    pool, warnings = [], []
    seen = set()
    for row in want:
        sid = row.get("submission_id")
        # extra_ids restrict to a pinned subset when given; empty = all submitted builds.
        if ids and sid not in ids:
            continue
        artifact = row.get("artifact")
        if sid in seen:
            continue
        seen.add(sid)
        if artifact in available:
            pool.append({"submission_id": sid, "agent": row.get("agent"), "artifact": artifact})
        else:
            warnings.append(f"checkpoint #{sid} ({row.get('agent')}) — zip {artifact!r} missing, skipped")
    for sid in ids:
        if sid not in seen:
            warnings.append(f"checkpoint #{sid} — not in agent_history, skipped")
    return pool, warnings


def _raw_paired(pairs: list) -> dict:
    """The raw ``paired_ab.paired_delta`` aggregate (keys ``delta``/``ci_lo``/``ci_hi``) — what the
    verdict and ``flips_on`` read. Empty input -> a null-delta zero-width interval (nothing
    measured), which reads as inconclusive (never a pass)."""
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
                 preset: str = "", per_cell_n: int = 0) -> dict:
    """Assemble the frozen C3 report (``report_version`` 1).

    ``matchups`` are the paired cells (C3 shape ``{opponent, seat, n, candidate_wins,
    baseline_wins, draws}``) — the ONLY input to the paired win-delta. ``h2h`` cells (same shape,
    the informational candidate-vs-baseline block) are emitted in ``matchups`` tagged
    ``informational`` but excluded from the delta and the verdict. ``checkpoints`` (raw cells with
    both arms' wins) drive the regression tripwire and are emitted as the C3 ``checkpoints`` block;
    they never enter the delta. ``aivat`` is ``eval_aivat.aivat(...)``'s return (None in v1)."""
    pairs = [(c["candidate_wins"], c["n"], c["baseline_wins"], c["n"])
             for c in matchups if c["n"] > 0]
    raw = _raw_paired(pairs)
    regressions = checkpoint_regressions(list(checkpoints)) if checkpoints else []

    emitted_matchups = [dict(c) for c in matchups]
    for c in h2h:
        emitted_matchups.append({**c, "opponent": c.get("opponent", "h2h"), "informational": True})

    reg_ids = {r["build_id"] for r in regressions}
    c3_checkpoints = [{"build_id": c["build_id"], "n": c["candidate_n"],
                       "candidate_wins": c["candidate_wins"], "baseline_wins": c["baseline_wins"],
                       "regression": c["build_id"] in reg_ids} for c in checkpoints]

    n_games = (sum(c["n"] * 2 for c in matchups) + sum(c.get("n", 0) for c in h2h)
               + sum(c["candidate_n"] + c["baseline_n"] for c in checkpoints))

    return {
        "report_version": REPORT_VERSION,
        "generated_at": generated_at,
        "git_rev": git_rev,
        "baseline": baseline,
        "candidate": candidate,
        "preset": preset,
        "per_cell_n": per_cell_n,
        "n_games": n_games,
        "matchups": emitted_matchups,
        "paired_delta": _c3_paired(raw),
        "strata": list(strata),
        "checkpoints": c3_checkpoints,
        "regressions": regressions,
        "aivat": aivat,
        "verdict": verdict(raw, candidate_crashes=candidate_crashes, regressions=regressions),
    }
