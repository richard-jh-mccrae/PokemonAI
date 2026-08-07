"""Opponent role-sheet sweep (Issue #395). **Not a gate.**

Does the ORDINAL role sheet reorder the agent's removal targets, or does it merely break Flat Ties?
OFF patches the SHIPPED `MatchupPlan.priority` — the ONE call every consumer goes through. D8's three
corrections to ADR-0118's bar: measure the FULL gust path, SPARSITY-match each sham to the candidates
the real leg lifted, and count ties on the field the ranking SORTS.

**The pre-registration stands rather than being edited into agreement with the result**: the sheet
SHOULD clear its sparsity-matched shams. Only the widened derived tier rests on this sweep.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.probes._corpus import replay_agent                  # noqa: E402
from train.probes._sham import (ArmPatch, READING, SHAMS, argmax,  # noqa: E402
                                legs, tune as _tune)               # THE shared probe seam
from train.gates import keyed_corrections                      # noqa: E402
from common.scouting.matchup_plan import MatchupPlan           # noqa: E402
from common.strategy.context import _BENCH, _CARD, _SWITCH     # noqa: E402


class _NoRoleSignal(ArmPatch):
    """Collapses every role priority to 0. Patched at `MatchupPlan.priority` — the ONE call every
    consumer goes through, so patching the derivation would leave the tiers above it still signalling."""

    target, name = MatchupPlan, "priority"

    @classmethod
    def collapse(cls, value):
        return 0.0


def _gust_menu(obs: dict):
    """A synthetic SWITCH select over every opponent BENCH body — the only shape the gust path is reachable through."""
    state = obs.get("current") or {}
    players = state.get("players") or []
    yi = state.get("yourIndex", 0)
    opp = players[1 - yi] if 0 <= 1 - yi < len(players) else None
    bench = [p for p in ((opp or {}).get("bench") or []) if p]
    if len(bench) < 2:
        return None, []                     # fewer than two candidates cannot express an ordering
    options = [{"type": _CARD, "area": _BENCH, "index": i, "playerIndex": 1 - yi}
               for i in range(len(bench))]
    return {"context": _SWITCH, "option": options, "minCount": 1}, bench


def _scores(pilot, obs, select, options) -> list[float]:
    """`doctrine_gust._gust_target_tactical` per candidate — the SHIPPED composition, called rather than
    re-derived. Its KO-oracle gate is measured too: an un-KO-able body scores 0 however its role reads."""
    board = pilot._board(obs, select)
    return [float(pilot._gust_target_tactical(obs, select, board, o) or 0.0) for o in options]


def _tie_population(scores, values) -> tuple[int, int, int]:
    """``(equal-prize groups, tied on the SORTED field, tied on row value)``. The ranking sorts the
    composed gust score, so that is where a Flat Tie is counted; row value is kept BESIDE, not instead."""
    by_prize: dict = {}
    for score, (prize, value) in zip(scores, values):
        by_prize.setdefault(prize, []).append((score, value))
    groups = [g for g in by_prize.values() if len(g) >= 2]
    return (len(groups),
            sum(1 for g in groups if len({round(s, 12) for s, _ in g}) == 1),
            sum(1 for g in groups if len({round(x, 12) for _, x in g}) == 1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--band", type=float, default=0.0,
                    help="override the sham band (default: ON's own measured max effect)")
    args = ap.parse_args(argv)
    tune = _tune()
    frames = sorted(keyed_corrections(REPO / "data" / "corrections",
                                      predicate=lambda c: bool(c.obs and c.agent)))

    captured, errors, scanned = [], Counter(), 0
    ties = {"OFF": [0, 0, 0], "ON": [0, 0, 0]}
    band, roled, lifted_seen, bodies_seen = 0.0, 0, 0, 0
    for _key, rec in frames:
        try:
            obs = rec.obs
            select, bench = _gust_menu(obs)
            if select is None:
                continue
            # A FRESH stateful Pilot per arm: the two must not share a per-decision memo or board
            # cache, or the second would answer with the first's numbers and prove nothing.
            with _NoRoleSignal():
                p_off = tune._build_pilot(replay_agent(rec))[0]
                p_off._planning = False
                before = _scores(p_off, obs, select, select["option"])
            p_on = tune._build_pilot(replay_agent(rec))[0]
            p_on._planning = False
            after = _scores(p_on, obs, select, select["option"])
            # The prize + row-value readings the tie population is grouped and reported on, taken
            # from the SAME shipped call the live gust slot reads.
            rows = p_on._opponent_target_rows(obs, p_on._board(obs, select))
            by_id = {r["id"]: r for r in (rows[1] if rows else [])}
            keys = [(int((by_id.get(b.get("id")) or {}).get("prize", 1) or 1),
                     float((by_id.get(b.get("id")) or {}).get("value", 0.0) or 0.0))
                    for b in bench]
            plan = getattr(p_on._board(obs, select), "matchup_plan", None)
        except Exception as e:                              # noqa: BLE001 — a probe reports, never fails
            errors[type(e).__name__] += 1
            continue
        scanned += 1
        for name, sc in (("OFF", before), ("ON", after)):
            for i, n in enumerate(_tie_population(sc, keys)):
                ties[name][i] += n
        # HOW MANY BODIES THE LEG CAN EVEN SPEAK ABOUT. A movement number is uninterpretable without
        # it: if the sheet roles almost nothing, a leg that moves little has not failed.
        for b, a0, b0 in zip(bench, after, before):
            bodies_seen += 1
            roled += 1 if (plan is not None and plan.role(b.get("id"))) else 0
            lifted_seen += 1 if abs(a0 - b0) > 1e-12 else 0
        band = max(band, max((abs(a - b) for a, b in zip(after, before)), default=0.0))
        captured.append((before, after, bench))

    band = args.band or band or 1e-6
    moved: Counter = Counter()
    counts = 0
    for before, after, bench in captured:
        if len(before) < 2:
            continue
        counts += 1
        base = argmax(before)
        if argmax(after) != base:
            moved["ON"] += 1
        lifted = [abs(a - b) > 1e-12 for a, b in zip(after, before)]
        for k, _label in SHAMS:
            shammed = [b + legs(k, band=band, card_id=bd.get("id"), hp=bd.get("hp"),
                                index=i, of=len(before))
                       for i, (b, bd) in enumerate(zip(before, bench))]
            if argmax(shammed) != base:
                moved[k] += 1
            masked = [b + (legs(k, band=band, card_id=bd.get("id"), hp=bd.get("hp"),
                               index=i, of=len(before)) if lifted[i] else 0.0)
                      for i, (b, bd) in enumerate(zip(before, bench))]
            if argmax(masked) != base:
                moved[k + "_spr"] += 1

    print(f"corpus                              : {len(frames)} replayable corrections")
    print(f"frames posing a 2+ body gust menu   : {scanned}")
    if errors:
        print(f"replay errors                       : {dict(errors)}")
    print()
    pct = f"{100 * roled / bodies_seen:.1f}%" if bodies_seen else "n/a"
    lpct = f"{100 * lifted_seen / bodies_seen:.1f}%" if bodies_seen else "n/a"
    print("WHAT THE SHEET CAN SPEAK ABOUT (a movement number is uninterpretable without it)")
    print(f"  opponent bench bodies ranked      : {bodies_seen}")
    print(f"  ...carrying ANY role              : {roled}  ({pct})")
    print(f"  ...whose GUST SCORE it moved      : {lifted_seen}  ({lpct})  <- the real sparsity:")
    print("      `_gust_target_tactical` returns 0 for a body the Active cannot KO, in BOTH arms,")
    print("      so the sheet is silent there however the role reads. That gate is D7's design, not")
    print("      a limitation of the measurement — and it is what the [sparsity] arms match.")
    print()
    print("THE FLAT TIE POPULATION — counted on the field the ranking SORTS (D8 correction 3)")
    print("  (equal-prize groups; `gust score` is the sorted field, `row value` the sub-population")
    print("   the earlier probes on this seam reported — printed beside it, never in place of it.)")
    for name in ("OFF", "ON"):
        g, s, v = ties[name]
        spct = f"{100 * s / g:.1f}%" if g else "n/a"
        vpct = f"{100 * v / g:.1f}%" if g else "n/a"
        print(f"  {name:<4} equal-prize groups {g:>4}   tied on GUST SCORE {s:>4} ({spct:>6})"
              f"   tied on row value {v:>4} ({vpct:>6})")
    print()
    print(f"sham band (ON's own max effect on the gust score): {band:.6f}")
    print()
    arms = ((("ON", "role sheet"),)
            + tuple((k + "_spr", label + " [sparsity]") for k, label in SHAMS)
            + SHAMS)
    print(f"{'arm':<28} bench argmax moved")
    for k, label in arms:
        cell = f"{moved[k]}/{counts} ({100 * moved[k] / counts:.1f}%)" if counts else "-"
        print(f"{label:<28} {cell}")
        if k == "ON":
            print("  [sparsity] = same band AND same candidates perturbed as the real leg — the "
                  "matched control.\n  The unmasked shams below perturb EVERY candidate and are "
                  "reported for continuity, not as the bar.")
            print(f"{'':-<28} {'':-<20}")

    print()
    print(READING)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
