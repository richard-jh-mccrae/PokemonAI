"""`_incoming_budget` base_attach sweep — does the Crispin finding move the OTHER consumers?

The doom-shadow grill (2026-07-23) proved generic supporter accel (Crispin/Waitress — pool-generic
`energy_accel` Supporters) beats an `attached + 1` affordability read by one in ANY deck, and the
DOOM consumer shipped on the stricter `{base_attach: 2}` accordingly. `_incoming_budget`'s own
consumers still run `{base_attach: 1}` behind a matched Read: the ±50 survival nudge
(`_incoming_worst` / `_survives_after_ko`), the `-KO_SCORE` loss rung (`_predicted_loss`), and the
promote stand-down (`opp_cannot_punish_wincon`). All of them — and none of the doom path — flow
through ONE seam: `combat.reachable_incoming(charged=...)`.

This sweep replays every committed correction TWICE through fresh shipped Pilots (the cross-game
fresh-per-frame discipline): stock, and with `reachable_incoming` wrapped so a matched
`{base_attach: 1}` budget is upgraded to `{base_attach: 2}` (unmatched `None` passes through — the
worst-case ceiling is never touched). Decision flips are adjudicated against the recorded human
`correct`:

  IMPROVED  — the upgraded budget reaches the human pick the stock build missed
  REGRESSED — the upgrade loses a human pick the stock build had
  MOVED     — the pick changed with no label signal (both wrong, or no `correct` recorded)
  SAME      — no decision change (the overwhelming expectation: the budget only prices
              sub-prize survival nudges and two gated vetoes)

    python tools/train/probes/budget_sweep.py            # full corrections corpus
    python tools/train/probes/budget_sweep.py --limit 40

Offline and read-only — a ruling input, not a behavior change.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


# ------------------------------------------------------------------------------ pure core
def upgrade_charged(charged):
    """The budget under study: a matched `{base_attach: 1}` becomes `{base_attach: 2}` (the
    generic-supporter attach the grill proved); None (unmatched → worst-case ceiling) and any
    other budget pass through untouched — the sweep must never move an unmatched read."""
    if isinstance(charged, dict) and charged.get("base_attach") == 1:
        return {**charged, "base_attach": 2}
    return charged


def wrap_reachable(combat) -> None:
    """Monkeypatch ``combat.reachable_incoming`` so its ``charged`` kwarg flows through
    :func:`upgrade_charged` — the one seam every `_incoming_budget` consumer (and no doom
    consumer) crosses. Everything else passes verbatim."""
    inner = combat.reachable_incoming

    def wrapped(my_body, opp_bodies, **kw):
        kw["charged"] = upgrade_charged(kw.get("charged"))
        return inner(my_body, opp_bodies, **kw)

    combat.reachable_incoming = wrapped


def verdict(chosen_stock, chosen_up, *, correct) -> str:
    """Classify one frame's decision pair against the recorded human pick."""
    if chosen_stock == chosen_up:
        return "SAME"
    if correct is not None and chosen_up == correct:
        return "IMPROVED"
    if correct is not None and chosen_stock == correct:
        return "REGRESSED"
    return "MOVED"


# ------------------------------------------------------------------------------ the runner
def _frames():
    index = {}
    for jf in (REPO / "data" / "corrections").glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                index[(str(d.get("episode_id")), d.get("decision", {}).get("frame"))] = d
    return [(k, v) for k, v in sorted(index.items()) if v.get("obs") and v.get("agent")]


def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="base_attach 1→2 sweep over the _incoming_budget seam")
    ap.add_argument("--limit", type=int, default=0, help="max frames (0 = all)")
    args = ap.parse_args(argv)
    tune = _tune()
    frames = _frames()
    if args.limit:
        frames = frames[:args.limit]
    counts = {"SAME": 0, "IMPROVED": 0, "REGRESSED": 0, "MOVED": 0, "SKIP": 0}
    for (ep, fr), rec in frames:
        try:
            stock = tune._build_pilot(rec["agent"])[0]
            d1 = stock.explain(rec["obs"])
            upgraded = tune._build_pilot(rec["agent"])[0]
            wrap_reachable(upgraded.combat)
            d2 = upgraded.explain(rec["obs"])
        except Exception:
            counts["SKIP"] += 1
            continue
        v = verdict(d1.chosen, d2.chosen, correct=rec.get("correct"))
        counts[v] += 1
        if v != "SAME":
            print(f"  {ep}-{fr:<4} {rec['agent']:<14} {v:<9} stock={d1.chosen} up={d2.chosen} "
                  f"correct={rec.get('correct')} ({rec.get('correct_label') or ''})", flush=True)
    total = sum(counts.values())
    print(f"\nBUDGET SWEEP (base_attach 1→2 on the reachable_incoming seam): frames={total}")
    for k, n in counts.items():
        print(f"  {k:<9} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
