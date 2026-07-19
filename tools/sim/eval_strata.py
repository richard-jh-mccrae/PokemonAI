"""Skill-sensitivity stratification (ADR-0053 WP2 design D5): label every filmed eval game by how
much decisions mattered, so the C3 ``strata`` block can surface the candidate−baseline delta on
the games where hidden information and choice actually swing the result — the ISMCTS finding that
real algorithm differences appear on the sensitive stratum while aggregate winrates mask them.

v1 signal = the **value-swing proxy** (no forks): replay each film through a value model and take
the max−min of P(win-for-seat-0) across the game's decision frames. A blowout barely moves;
a knife-edge game swings wide. Cheap enough to run on every eval game, and it upgrades for free
when WP1's G1 net replaces the committed seed model. The per-stratum delta reuses the same paired
contrast as the headline number (``sim.paired_ab``), so a stratum reads exactly like the whole
run, restricted to its games.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median

from common.value.features import features_from_board
from sim.paired_ab import paired_delta
from train.blunder.decisions import _film


def seat0_winprob(pilot, model, replay) -> list[float]:
    """P(win for seat 0) at each of the game's decision frames. Each frame's obs is seat-relative
    to its actor, so ``model.predict`` gives P(win for the actor); frames where seat 1 acts are
    flipped to seat 0's view (``1 − p``) to build ONE consistent trajectory. Mirrors the extractor's
    frame walk (``train.value.extract``): the choice for frame ``i`` and its aligned obs live in
    frame ``i+1``. Pure on the film — never touches the live engine, never raises."""
    film = _film(replay)
    traj: list[float] = []
    for i, frame in enumerate(film):
        select = frame.get("select")
        if not isinstance(select, dict) or not select.get("option"):
            continue
        nxt = film[i + 1] if i + 1 < len(film) else None
        obs = nxt.get("obs") if nxt else None
        if not obs:
            continue
        seat = (obs.get("current") or {}).get("yourIndex")
        if seat is None:
            continue
        try:
            board = pilot._board(obs, obs.get("select"))
            p = model.predict(features_from_board(board))
        except Exception:
            continue                                   # a malformed frame is skipped, not fatal
        traj.append(p if seat == 0 else 1.0 - p)
    return traj


def game_sensitivity(pilot, model, replay) -> float | None:
    """The value-swing sensitivity of one game: ``max − min`` of the seat-0 win-prob trajectory.
    ``None`` when the film yields no scorable decision (excluded from stratification, not counted
    as zero — a hole is not a blowout)."""
    traj = seat0_winprob(pilot, model, replay)
    if not traj:
        return None
    return max(traj) - min(traj)


def sensitivity_split(scores: list[float]) -> tuple[float, list[str]]:
    """Median-threshold each score into ``high-swing`` / ``low-swing``. The split is STRICT
    (``score > median`` is high) so a degenerate run where every game scores the same — e.g. the
    null model, which predicts 0.5 everywhere → swing 0 — lands entirely in ``low-swing`` rather
    than splitting noise. Returns ``(threshold, labels)`` aligned to ``scores``."""
    if not scores:
        return 0.0, []
    thr = median(scores)
    return thr, ["high-swing" if s > thr else "low-swing" for s in scores]


def _paired_pairs(games: list) -> list:
    """Per shared ``(opponent, seat)`` cell, the ``(cand_wins, cand_n, base_wins, base_n)`` tuple —
    only cells where BOTH arms played (an unpaired cell carries no candidate−baseline signal)."""
    tally = defaultdict(lambda: {"candidate": [0, 0], "baseline": [0, 0]})   # [wins, n] per arm
    for g in games:
        cell = tally[(g["opponent"], g["seat"])][g["arm"]]
        cell[1] += 1
        cell[0] += 1 if g["won"] else 0
    pairs = []
    for t in tally.values():
        c, b = t["candidate"], t["baseline"]
        if c[1] and b[1]:
            pairs.append((c[0], c[1], b[0], b[1]))
    return pairs


def strata_cells(games: list) -> list[dict]:
    """The C3 ``strata`` block: split ``games`` at the median sensitivity, then within each stratum
    compute the paired candidate−baseline win-delta + CI over shared cells (same contrast as the
    headline). ``games`` are dicts ``{sensitivity, opponent, seat, arm, won}``. A stratum with no
    paired cell reports a null-delta zero-width interval (its games didn't pair up). Empty in →
    empty out (C3 allows ``strata: []``)."""
    if not games:
        return []
    _, labels = sensitivity_split([g["sensitivity"] for g in games])
    buckets: dict[str, list] = {"high-swing": [], "low-swing": []}
    for g, label in zip(games, labels):
        buckets[label].append(g)
    cells = []
    for name in ("high-swing", "low-swing"):
        gs = buckets[name]
        pairs = _paired_pairs(gs)
        agg = paired_delta(pairs) if pairs else None
        cells.append({
            "name": name,
            "n": len(gs),
            "win_delta": agg["delta"] if agg else 0.0,
            "ci_low": agg["ci_lo"] if agg else 0.0,
            "ci_high": agg["ci_hi"] if agg else 0.0,
        })
    return cells
