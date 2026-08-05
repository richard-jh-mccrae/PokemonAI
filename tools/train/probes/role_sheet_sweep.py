"""Opponent role-sheet sweep. **Not a gate.**

Answers what Issue #395's derived tier owes its own change: does the ORDINAL role sheet actually
reorder the agent's removal targets, or does it merely break Flat Ties the way any number of that
size would?

The bar is ADR-0118's sham policy — **a movement number published without its sham baseline is not
evidence** — and Issue #395 D8 adds three corrections to it, each earned by a specific past failure
on this exact seam:

1. **Measure the FULL gust path, `doctrine_gust` included** — not `_opponent_target_rows`' `value`
   in isolation. The rows carry no role signal at all, while `doctrine_gust._gust_target_tactical`
   already layers `matchup_plan.priority` on top of its own prize reading. A rows-only sweep would
   compare a seam with no role signal against one with a signal and miss that the layer above
   already had one — the same class of error the Issue #398 probe made twice (wrong denominator,
   then wrong field). So the arm patch is at `MatchupPlan.priority`, which is the ONE place every
   consumer of the sheet reads it, and the ranked quantity is the doctrine's own target score.
2. **Sham-controlled and SPARSITY-matched.** A band-matched sham perturbs every candidate; a sparse
   real leg does not, and the sham then wins on volume alone. The `[sparsity]` arms confine each
   sham to exactly the candidates the real leg lifted — same band, same COUNT of perturbed rows,
   meaningless CHOICE of magnitude within them. Those are the honest controls; the unmasked shams
   are printed for continuity, not as the bar.
3. **The tie population counted on the field the ranking sorts** — here the composed gust score —
   with the `row["value"]` population printed BESIDE it rather than in place of it. Issue #398 had
   to correct that error twice.

## Arms

    OFF    every role priority collapsed to 0 — no role signal anywhere, including inside
           `doctrine_gust`. Reconstructed by patching the SHIPPED `MatchupPlan.priority` for the
           duration of the frame, so it is the real code path answering the OLD question rather
           than a hand-rebuilt imitation (ADR-0117's second-oracle rule).
    ON     the sheet as it now ships.
    S_cid  sham — (cid % 7), band-matched to ON's own measured effect. No causal claim.
    S_hp   sham — (hp % 70), same band. No causal claim.
    S_pos  sham — position index. The degenerate case: a leg that cannot beat LIST ORDER is not
           ordering anything, and list order is precisely what a Flat Tie falls back to.

**The pre-registration.** Before the first run this docstring predicts the sheet SHOULD clear its
sparsity-matched shams on the gust path, on the reasoning that it separates bodies by which ROLE
their card facts put them in — a distinction that varies across an opponent's board — rather than by
a removal Δ that is a Structural Zero for every non-leading body. Whatever the run says, **this
paragraph is left standing rather than edited into agreement with the result**, which is the
discipline `line_prize_sweep.py` recorded after its own prediction failed.

**What a null result would and would not mean.** Issue #395's commits 1 and 2 are correctness fixes
standing on measured defects — eleven tag instances a documented command deletes, 530 role
assignments resolving to 0, a −80 steer landing on 2- and 3-prize bodies. None of them needs this
sweep. Only the widened derived tier (commit 3) rests on it. If the sheet moves nothing, that is the
answer and it gets recorded as the answer.

    python tools/train/probes/role_sheet_sweep.py

Reads what SHIPS: a fresh stateful Pilot per arm, deployment profile untouched. Offline, read-only,
always exits 0.
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
    """Collapses every role priority to 0 — the board as it reads with no role sheet at all.

    Patched at `MatchupPlan.priority` rather than at the derivation, and that is the whole of D8
    correction 1: `priority` is the ONE call every consumer of the sheet goes through, so turning it
    off here turns it off in `doctrine_gust`, in the snipe relevance multiplier, in the Brief
    tiebreak and on the target rows at once. Patching the derivation would have left the tiers above
    it still carrying a signal, which is the comparison that reads as a measurement and is not one."""

    target, name = MatchupPlan, "priority"

    @classmethod
    def collapse(cls, value):
        return 0.0


def _gust_menu(obs: dict):
    """A synthetic SWITCH select over every opponent BENCH body, plus the bodies it names.

    The gust path is only reachable through a SWITCH select, and most corpus frames are not one — so
    the frames are re-posed as the question the doctrine answers rather than filtered down to the
    handful that already ask it. The option shape is the engine's own (`type=_CARD`, `area=_BENCH`,
    `playerIndex` = theirs), which is what `_option_pokemon` resolves against; nothing about the
    board is altered."""
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
    """`doctrine_gust._gust_target_tactical` for every candidate — the SHIPPED composition, called
    rather than re-derived. Its KO-oracle gate is part of what is being measured: a body the Active
    cannot knock out scores 0 however its role reads, which is D7's *"the KO oracle keeps refusing
    an impossible gust"* stated as an arithmetic rather than as a hope."""
    board = pilot._board(obs, select)
    return [float(pilot._gust_target_tactical(obs, select, board, o) or 0.0) for o in options]


def _tie_population(scores, values) -> tuple[int, int, int]:
    """``(equal-prize groups, tied on the SORTED field, tied on row value)``.

    D8 correction 3. The first two are the honest count: the ranking sorts the composed gust score,
    so that is the field a Flat Tie has to be counted on. The third is the `row["value"]` population
    the previous probes on this seam reported — kept BESIDE it rather than in place of it, because
    reporting only the sub-population is the error Issue #398 had to correct twice."""
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
            # A FRESH stateful Pilot per arm: the two must not share a per-decision memo or any board
            # cache, or the second would answer with the first's numbers and the comparison would
            # silently be a null control.
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
