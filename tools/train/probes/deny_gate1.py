"""#199 GATE 1 — can the shared marginal reproduce ADR-0062's play/hold discrimination? (ADR-0077)

The go/no-go ADR-0077 puts ahead of any code in #187. The question, precisely:

    Deny's play rung today is  `coin_odds * _DENIAL_PLAY_W * opp_denial_best - _DENIAL_ITEM_COST`,
    denominated in DAMAGE. ADR-0077 decision 2 repoints it at the shared per-body marginal, which is
    denominated in PRIZE-EQUIVALENTS and converted by the derived `PRIZE_DAMAGE_RATE` (100). With
    `coin_odds = 0.5` for Crushing Hammer and `_DENIAL_ITEM_COST = 10`, the rung fires iff

        0.5 * 100 * m  -  10  >  0      i.e.      m > 0.2  prize-equivalents

    so every frame the corpus rules PLAY needs `m > 0.2` and every frame it rules HOLD needs
    `m <= 0.2`. `k` is FIXED at the derived rate, so this is a falsifiable prediction, not a fit.

**ADR-0062 gives real reason to doubt it.** That ADR records *"no monotone pricing of magnitude alone
can separate them"* — its f29 (bench, denial 70) must HOLD while f15 (Active, denial 30) must PLAY, so
raw magnitude orders them backwards and only imminence discriminates. The shared marginal IS
imminence-aware, which is why the swap is plausible at all. This probe measures whether that is
enough.

    python tools/train/probes/deny_gate1.py            # the ruled Hammer frames
    python tools/train/probes/deny_gate1.py --all      # every frame that offers a Hammer play

Forces `deny_strip_delta` ON (it ships OFF — nothing reads it yet). Offline and read-only; decides
nothing and writes nothing.
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
    """PLAY when the human's correction picks a Hammer; HOLD when it picks something ELSE while the
    agent played one. None when the frame is not about a Hammer at all."""
    chosen, correct = rec.get("chosen_label"), rec.get("correct_label")
    if _is_hammer(correct):
        return "PLAY"
    if _is_hammer(chosen):
        return "HOLD"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="also report frames with no Hammer ruling (context only, never gated)")
    args = ap.parse_args()

    tune = _tune()
    from common.currency import PRIZE_DAMAGE_RATE
    from common.strategy.denial import coin_odds
    from common.pilot import _DENIAL_ITEM_COST, _DENIAL_PLAY_W

    threshold = _DENIAL_ITEM_COST / (0.5 * _DENIAL_PLAY_W * PRIZE_DAMAGE_RATE)
    print(f"gate 1 — PRIZE_DAMAGE_RATE={PRIZE_DAMAGE_RATE}  _DENIAL_ITEM_COST={_DENIAL_ITEM_COST}  "
          f"=> PLAY iff m > {threshold:.3f} prize-eq (at coin_odds 0.5)\n")
    print(f"{'frame':<16} {'agent':<14} {'ruled':<5} {'m_all':>6} {'m_grd':>6} {'play$':>7} "
          f"{'pred':<5} {'ok':<3} incumbent")

    rows, agree, total = [], 0, 0
    for (ep, fr), rec in _records():
        ruled = _ruling(rec)
        if ruled is None and not args.all:
            continue
        try:
            pilot = tune._build_pilot(rec["agent"])[0]
            pilot.deny_strip_delta = True
            board = pilot._board(rec["obs"])
            cache = getattr(pilot, "_opponent_target_cache", None)
        except Exception as e:
            print(f"{ep}-{fr:<10} {rec['agent']:<14} {'?':<5} unreplayable: {type(e).__name__}")
            continue
        if not cache:
            print(f"{ep}-{fr:<10} {rec['agent']:<14} {str(ruled):<5} no opponent-target rows")
            continue
        _phase, target_rows = cache

        vals = [(r.get("deny_value", 0.0), r) for r in target_rows]
        m_all = max((v for v, _ in vals), default=0.0)
        # The ADR-0063 guard is NOT subsumed by the marginal (ADR-0077's re-audit): `turns_to_ko_me`
        # cannot see that I am about to KO their Active, so it would price a strip on a corpse.
        guarded = [v for v, r in vals if not (r["area"] == "active" and board.active_can_ko)]
        m_grd = max(guarded, default=0.0)

        odds = 0.5
        cid = None
        for opt, lab in ((rec.get("chosen"), rec.get("chosen_label")),
                         (rec.get("correct"), rec.get("correct_label"))):
            if _is_hammer(lab):
                cid = 1120 if "crushing" in (lab or "").lower() else 1081
        if cid is not None:
            try:
                odds = coin_odds(cid)
            except Exception:
                pass
        play_value = odds * _DENIAL_PLAY_W * PRIZE_DAMAGE_RATE * m_grd - _DENIAL_ITEM_COST
        pred = "PLAY" if play_value > 0 else "HOLD"
        ok = "" if ruled is None else ("ok" if pred == ruled else "XX")
        if ruled is not None:
            total += 1
            agree += pred == ruled
        print(f"{ep}-{fr:<10} {rec['agent']:<14} {str(ruled):<5} {m_all:>6.3f} {m_grd:>6.3f} "
              f"{play_value:>7.2f} {pred:<5} {ok:<3} {board.opp_denial_best:>6.1f}")
        rows.append((ep, fr, ruled, m_grd, pred))

    print(f"\nruled frames: {total}   agree: {agree}   disagree: {total - agree}")
    plays = [r for r in rows if r[2] == "PLAY"]
    holds = [r for r in rows if r[2] == "HOLD"]
    if plays and holds:
        lo_play, hi_hold = min(r[3] for r in plays), max(r[3] for r in holds)
        print(f"separation: min(m | PLAY) = {lo_play:.3f}   max(m | HOLD) = {hi_hold:.3f}   "
              f"=> {'SEPARABLE' if lo_play > hi_hold else 'NOT SEPARABLE'}")
        if lo_play > hi_hold:
            print(f"            any k in ({_DENIAL_ITEM_COST / (0.5 * lo_play):.1f}, "
                  f"{_DENIAL_ITEM_COST / (0.5 * hi_hold):.1f}) separates them"
                  if hi_hold > 0 else
                  f"            any k > {_DENIAL_ITEM_COST / (0.5 * lo_play):.1f} separates them")
        else:
            print("            NO exchange rate separates these frames — the marginal as built does "
                  "not carry ADR-0062's discrimination. Gate 1 FAILS; #187 needs a design fix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
