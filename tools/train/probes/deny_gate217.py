"""Issue #217 GO/NO-GO GATES — is deny's flat bench discount replaceable by a derived clock?

Two gates, both of which Issue #217 puts ahead of any code. Offline, read-only, decides nothing.

**GATE 1 — does the boolean promotion gate reproduce f21/f29?**
    The armed fire rung today AREA-WEIGHTS relevance by `_DENIAL_BENCH = 0.25`
    (`pilot.py:6163`). Issue #217's claim: that constant prices a promotion DELAY the rules do not
    impose, because `combat._promotion_open` (ADR-0071 decision 6) models promotion as a boolean
    (retreat-then-attack is legal in ONE turn; a benched attacker owes Energy, never tempo). This
    gate substitutes the boolean for the constant and re-reads the rung's sign on every
    Hammer-ruled frame. f21/f29 must still HOLD.

**GATE 2 — does the derived clock separate f21/f29 from f15 on imminence alone?**
    ADR-0062 records that *"no monotone pricing of magnitude alone can separate them"*: f29's raw
    denial (70) is more than twice f15's (30), yet f29 must HOLD and f15 must PLAY. Replacing two
    hand-set timing terms with one derived term means the separation must now come from the clock
    BY ITSELF. The clock is `_strip_delta_terms`' `strip_shift` — the change in
    `turns_to_ko_me` when one Energy is removed, read under `_DENY_CHARGED`.

    NOTE Issue #217's gate-2 text names **f12** as the frame to separate from, then cites f15's
    numbers. Those are different anchors: f12 is ADR-0062's `_DENIAL_FORWARD` lower bound
    (`> 0.154`), nothing to do with imminence. This probe reports the f29-vs-**f15** pair the ADR
    actually derives, and carries f12/f26 alongside as context.

    python tools/train/probes/deny_gate217.py
    python tools/train/probes/deny_gate217.py --all     # every Hammer-play frame, not just ruled

Forces `deny_strip_delta` ON and `deny_relevance` ON (the shipped armed state for the fire rung).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

HAMMER_NAMES = ("crushing hammer", "enhanced hammer")

#: The ADR-0062 imminence pair, plus the two frames the armed rung's own comment cites as its other
#: sign anchors. Reported separately from the corpus sweep because the gates are ABOUT these.
ANCHORS = {("82749168", 21): "HOLD  ADR-0062 bench anchor (f21)",
           ("82749168", 29): "HOLD  ADR-0062 bench anchor (f29)",
           ("82523811", 15): "PLAY  ADR-0062 Active anchor (f15) — the imminence pair with f29",
           ("82525101", 92): "PLAY  ADR-0062 big-denial anchor (f92)",
           ("82523811", 79): "PLAY  ADR-0062 big-denial anchor (f79)",
           ("82748422", 26): "PLAY  armed-rung comment anchor (f26)"}


def _records():
    out = {}
    for jf in (REPO / "data" / "corrections").glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                out[(str(d.get("episode_id")), (d.get("decision") or {}).get("frame"))] = d
    return [(k, v) for k, v in sorted(out.items()) if v.get("obs") and v.get("agent")]


def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _is_hammer(label) -> bool:
    return any(h in (label or "").lower() for h in HAMMER_NAMES)


def _ruling(rec):
    chosen, correct = rec.get("chosen_label"), rec.get("correct_label")
    if _is_hammer(correct):
        return "PLAY"
    if _is_hammer(chosen):
        return "HOLD"
    return None


def _odds(rec, coin_odds) -> float:
    for _opt, lab in ((rec.get("chosen"), rec.get("chosen_label")),
                      (rec.get("correct"), rec.get("correct_label"))):
        if _is_hammer(lab):
            try:
                return coin_odds(1120 if "crushing" in (lab or "").lower() else 1081)
            except Exception:
                return 0.5
    return 0.5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="include frames with no Hammer ruling")
    args = ap.parse_args()

    tune = _tune()
    from common.strategy.denial import coin_odds
    from common.pilot import (_DENIAL_BENCH, _DENIAL_ITEM_COST, _DENIAL_PLAY_W,
                              _DENY_RELEVANCE_K)

    print(f"Issue #217 gates — _DENIAL_BENCH={_DENIAL_BENCH}  K={_DENY_RELEVANCE_K}  "
          f"W={_DENIAL_PLAY_W}  keep={_DENIAL_ITEM_COST}\n")
    print("GATE 1 — fire-rung sign under the BOOLEAN promotion gate vs the flat 0.25 discount")
    print(f"{'frame':<15} {'ruled':<5} {'gate?':<6} {'rel_a':>6} {'rel_b':>6} "
          f"{'inc$':>7} {'incP':<5} {'bool$':>8} {'boolP':<5} {'':<3}")

    rows = []
    for (ep, fr), rec in _records():
        ruled = _ruling(rec)
        if ruled is None and not args.all:
            continue
        try:
            pilot = tune._build_pilot(rec["agent"])[0]
            pilot.deny_relevance = True
            pilot.deny_strip_delta = True
            board = pilot._board(rec["obs"])
            cache = getattr(pilot, "_opponent_target_cache", None)
        except Exception as e:
            print(f"{ep}-{fr:<10} unreplayable: {type(e).__name__}: {e}")
            continue
        if not cache:
            print(f"{ep}-{fr:<10} {str(ruled):<5} no opponent-target rows")
            continue
        _phase, target_rows = cache

        # Opponent bodies exactly as `_opponent_target_rows` reads them (pilot.py:7414-7422) — the
        # nested `current.players[1 - yourIndex]` shape, NOT a flat `obs["opponent"]`.
        state = rec["obs"].get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) else None
        active_list = [p for p in ((opp or {}).get("active") or []) if p]
        bench = [p for p in ((opp or {}).get("bench") or []) if p]
        opp_active = active_list[0] if active_list else None
        bodies = active_list + bench
        try:
            # The LIVE enabler, not a hardcoded False: `_promotion_open` fails OPEN when a
            # switch-class out cannot be ruled out, and that leg is what decides whether the gate
            # can ever shut. Hardcoding False makes gate 1 pass for the wrong reason.
            gate_open = pilot.combat._promotion_open(
                bodies, opp_active, switch_enabler=pilot._opp_switch_enabler())
        except Exception as e:
            gate_open = None
            print(f"    (promotion gate unreadable on {ep}-{fr}: {type(e).__name__}: {e})")

        rel_active = max((r.get("relevance_fire", 0.0) for r in target_rows
                         if r["area"] == "active"), default=0.0)
        rel_bench = max((r.get("relevance_fire", 0.0) for r in target_rows
                         if r["area"] != "active"), default=0.0)

        odds = _odds(rec, coin_odds)
        w = _DENIAL_PLAY_W * (1.0 + 0.0)               # Lever A is board-dependent; the anchors are
        #                                                all favored, so read the un-boosted weight.

        # INCUMBENT: bench relevance discounted by the flat 0.25 (pilot.py:6163).
        inc_best = max(rel_active, rel_bench * _DENIAL_BENCH)
        inc_v = odds * w * _DENY_RELEVANCE_K * inc_best - _DENIAL_ITEM_COST if inc_best else 0.0
        inc_p = "PLAY" if inc_v > 0 else "HOLD"

        # CANDIDATE: the boolean gate. Bench counts FULLY when promotion is open, not at all when
        # it is shut — Issue #217's "the derived replacement is the gate, not a smaller constant".
        bool_w = 1.0 if gate_open else 0.0
        bool_best = max(rel_active, rel_bench * bool_w)
        bool_v = odds * w * _DENY_RELEVANCE_K * bool_best - _DENIAL_ITEM_COST if bool_best else 0.0
        bool_p = "PLAY" if bool_v > 0 else "HOLD"

        flag = "" if inc_p == bool_p else "CHANGED"
        print(f"{ep}-{fr:<10} {str(ruled):<5} {str(gate_open):<6} {rel_active:>6.3f} "
              f"{rel_bench:>6.3f} {inc_v:>7.2f} {inc_p:<5} {bool_v:>8.2f} {bool_p:<5} {flag:<3}")

        # GATE 2 data: the derived clock, per body.
        shifts = [(r["area"], r.get("bi"), r.get("strip_shift"), r.get("deny_value", 0.0))
                  for r in target_rows]
        rows.append({"ep": ep, "fr": fr, "ruled": ruled, "gate": gate_open,
                     "inc_p": inc_p, "bool_p": bool_p, "inc_v": inc_v, "bool_v": bool_v,
                     "shifts": shifts,
                     "clock": max((v for *_x, v in shifts), default=0.0),
                     "shift_max": max((s for _a, _b, s, _v in shifts if s is not None),
                                      default=None)})

    ruled = [r for r in rows if r["ruled"]]
    changed = [r for r in ruled if r["inc_p"] != r["bool_p"]]
    broke = [r for r in ruled if r["bool_p"] != r["ruled"]]
    inc_broke = [r for r in ruled if r["inc_p"] != r["ruled"]]
    print(f"\nGATE 1 VERDICT — {len(changed)} sign change(s) vs the incumbent; "
          f"boolean misses {len(broke)} ruling(s), incumbent misses {len(inc_broke)}.")
    new_breaks = [r for r in broke if r not in inc_broke]
    if new_breaks:
        print("  GATE 1 FAILS — the boolean gate breaks ruling(s) the 0.25 discount holds:")
        for r in new_breaks:
            print(f"    {r['ep']}-{r['fr']}  ruled {r['ruled']}, boolean says {r['bool_p']} "
                  f"({r['bool_v']:+.2f}); incumbent {r['inc_p']} ({r['inc_v']:+.2f})")
    else:
        print("  GATE 1 PASSES — no ruling held by the 0.25 discount is broken by the boolean gate.")

    print("\nGATE 2 — the derived clock (strip_shift / deny_value) on the ADR-0062 imminence pair")
    print(f"{'frame':<15} {'ruled':<5} {'clock$':>7} {'shiftMax':>9}  per-body (area,bi,shift,val)")
    for r in rows:
        if not (args.all or (r["ep"], r["fr"]) in ANCHORS):
            continue
        per = "  ".join(f"{a}{b}:{'-' if s is None else s}/{v:.2f}"
                        for a, b, s, v in r["shifts"])
        print(f"{r['ep']}-{r['fr']:<10} {str(r['ruled']):<5} {r['clock']:>7.3f} "
              f"{str(r['shift_max']):>9}  {per}")

    print()
    for name, sub in (("ADR-0062 anchors only",
                       [r for r in ruled if (r["ep"], r["fr"]) in ANCHORS]),
                      ("whole ruled corpus", ruled)):
        p = [r["clock"] for r in sub if r["ruled"] == "PLAY"]
        h = [r["clock"] for r in sub if r["ruled"] == "HOLD"]
        if p and h:
            print(f"GATE 2 [{name}]: min(clock | PLAY) = {min(p):.3f}   "
                  f"max(clock | HOLD) = {max(h):.3f}   "
                  f"=> {'SEPARABLE' if min(p) > max(h) else 'NOT SEPARABLE'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
