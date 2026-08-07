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


def own_winprob(pilot, model, replay, arm_seat: int) -> list[float]:
    """P(win for ``arm_seat``) at the arm's OWN decision frames only. The obs is seat-relative to the
    actor, so no flipping. The choice for frame ``i`` and its aligned obs live in frame ``i+1``."""
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
        if seat != arm_seat:
            continue                                   # only the arm's own decisions
        try:
            board = pilot._board(obs, obs.get("select"))
            p = model.predict(features_from_board(board))
        except Exception:
            continue                                   # a malformed frame is skipped, not fatal
        traj.append(p)
    return traj


def game_sensitivity(pilot, model, replay, *, arm_seat: int = 0) -> float | None:
    """``max − min`` of the arm's own-decision win-prob trajectory. ``None`` when nothing scored —
    EXCLUDED from stratification rather than counted as zero, because a hole is not a blowout."""
    traj = own_winprob(pilot, model, replay, arm_seat)
    if not traj:
        return None
    return max(traj) - min(traj)


def sensitivity_split(scores: list[float]) -> tuple[float, list[str]]:
    """Median-threshold into ``high-swing`` / ``low-swing`` -> ``(threshold, labels)``. STRICT
    (``score > median``), so an all-equal run lands entirely in ``low-swing`` rather than split."""
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
    """The C3 ``strata`` block: split ``{sensitivity, opponent, seat, arm, won}`` games at the median,
    then take the headline's paired contrast within each. An unpaired stratum reports a null delta."""
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
