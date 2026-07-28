"""Lethal-KO DECIDER sweep — #177's Decision Gate (ADR-0075 decision 5, ADR-0072 decision 2).

Runs the corpus through BOTH KO-pricing paths while both still exist and reports every frame where
the emitted `ko_for_prizes` line disagrees. That report is the whole point: no KO line may change
silently, so the human rules on the WHY — one sitting, one table — BEFORE the deletion commit
retires `_play_accel_extra` and `_composed_budget_units` for good.

The two pilots, built fresh per frame (pilots are stateful; sharing one pollutes verdicts — the
`needs_sweep` lesson):

  * NEW — ``ko_budget_pricing`` ON. Every one of the seven KO builders prices its line by the typed
    Attach Budget built for its OWN attacker: affordability is `_can_pay` per slot over each Budget
    option, and the five `_play_accel_extra` lines join the Probability Leg. That is exactly the
    post-deletion agent.
  * OLD — ``ko_budget_pricing`` OFF: `_play_accel_extra`'s flat wild `+1` on five lines and
    `_composed_budget_units`' `Budget.size` collapse on two, as they decide today.

LANE-PRECISE, not whole-decision (ADR-0075 decision 5). Comparison is on the committed
``Decision.planned`` TurnLine — ``(goal, resolved first-step SLOT, prizes)`` — never the raw option
index, which duplicate-effect options otherwise read as false flips (`attach_decider_sweep`'s
recorded lesson at 82523811-59 / 82750161-59). The fold is strictly NARROWING, so it removes KO
claims that were outranked anyway: those vanish from the line set while the final pick is
unchanged, and a whole-decision sweep would report SAME. That population is exactly where the
silent target-body bugs live (the per-builder `benched` flags and the `supporter_spent` quota), so
it must reach the ruling table. Continuation collateral is the Discrimination Gate's job
(`leaf_lab.py diff`) — the two gates are designed to have complementary blindness.

    python tools/train/probes/lethal_ko_decider_sweep.py            # the flip table + the tally
    python tools/train/probes/lethal_ko_decider_sweep.py --all      # every frame, not only the flips
    python tools/train/probes/lethal_ko_decider_sweep.py --json out.json    # machine-readable

Offline and read-only; two engine-backed Pilot builds per frame.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.gates import option_slot   # noqa: E402

#: The goals this swap can move. `win` is the Lethal Solver's LOCK and is listed deliberately: the
#: fold changes KO affordability, so a line crossing INTO or OUT OF the lock is the single most
#: consequential flip this sweep can surface and must never be filtered out as "not my lane".
KO_GOALS = ("ko_for_prizes", "win", "ko_key_threat")

_PRIZES = re.compile(r"(\d+)-prize")


def _frames():
    index = {}
    for jf in (REPO / "data" / "corrections").glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                index[(str(d.get("episode_id")), d.get("decision", {}).get("frame"))] = d
    return [(k, v) for k, v in sorted(index.items()) if v.get("obs") and v.get("agent")]


def _agent(rec) -> str:
    a = rec.get("agent") or ""
    return a if a in {"dragapult_ex", "mega_lucario", "mega_starmie", "slowking"} else "mega_starmie"


def _strategy_and_deck(agent: str):
    agent_dir = REPO / "src" / "agents" / agent
    spec = importlib.util.spec_from_file_location(f"{agent}_strategy", agent_dir / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text(encoding="utf-8").splitlines()[:60]
            if x.strip()]
    return mod.STRATEGY, deck


def _seams():
    """Build the engine-backed knowledge seams ONCE and inject them into every Pilot — they are
    immutable card knowledge, so sharing them is safe where sharing a Pilot is not."""
    from common.scouting.artifact import load_artifact
    from common.scouting.briefs import load_briefs
    from common.scouting.provider import EngineCardStatProvider
    from common.scouting.scout import Scout
    stats = EngineCardStatProvider()
    stats.warm()
    return {"stats": stats, "scout": Scout(load_artifact(), provider=stats),
            "briefs": load_briefs()}


def _pilot(agent: str, *, new: bool, seams):
    """A fresh shipped Pilot for ``agent`` with the KO-pricing swap ON (new) or OFF (old)."""
    from common.runtime import build_pilot
    strategy, deck = _strategy_and_deck(agent)
    params = dict(strategy.params)
    params["ko_budget_pricing"] = bool(new)
    return build_pilot(strategy, deck, params=params, **seams)


def _line_key(dec, options) -> tuple | None:
    """``(goal, first-step slot, prizes)`` for the committed KO line, or None when this frame
    commits no KO line at all. SLOT-resolved, never the raw index (ADR-0072 decision 3)."""
    line = getattr(dec, "planned", None)
    if line is None or getattr(line, "goal", None) not in KO_GOALS:
        return None
    step = (getattr(line, "next_step", None) or [None])[0]
    slot = None
    if step is not None and isinstance(step, int) and 0 <= step < len(options):
        slot = option_slot(options[step])
    m = _PRIZES.search(getattr(line, "rationale", "") or "")
    return (line.goal, slot, int(m.group(1)) if m else None)


def _cell(key) -> str:
    if key is None:
        return "(no KO line)"
    goal, slot, prizes = key
    return f"{goal}@{slot}" + (f"/{prizes}p" if prizes is not None else "")


def sweep(show_all: bool, json_out: Path | None = None) -> int:
    frames, seams = _frames(), _seams()
    hdr = (f"{'id':<14} {'agent':<13} {'NEW line':<28} {'OLD line':<28} {'verdict':<12}")
    print("LETHAL-KO DECIDER SWEEP — new (typed Attach Budget) vs old (wild +1 / Budget.size)\n")
    print(hdr)
    print("-" * len(hdr))
    tally = defaultdict(int)
    flips = []
    for (ep, fr), rec in frames:
        agent = _agent(rec)
        try:
            dec_new = _pilot(agent, new=True, seams=seams).explain(rec["obs"])
            dec_old = _pilot(agent, new=False, seams=seams).explain(rec["obs"])
        except Exception as exc:                       # a frame the shipped build can't replay
            tally["error"] += 1
            if show_all:
                print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} ERROR {exc}")
            continue
        options = (rec["obs"].get("select") or {}).get("option") or []
        new_key = _line_key(dec_new, options)
        old_key = _line_key(dec_old, options)
        if new_key is None and old_key is None:
            continue                                   # no KO line either side — outside this lane
        tally["frames"] += 1
        if new_key == old_key:
            tally["agree"] += 1
            if not show_all:
                continue
            verdict = "agree"
        else:
            tally["flip"] += 1
            correct = set(rec.get("correct") or [])
            if correct:
                new_hit = bool(set(dec_new.chosen or []) & correct)
                old_hit = bool(set(dec_old.chosen or []) & correct)
                verdict = ("FIX" if new_hit and not old_hit
                           else "REGRESSION" if old_hit and not new_hit else "DIVERGENT")
            elif old_key is not None and new_key is None:
                # The narrowing direction with no human label: the typed Budget REFUSED a KO the
                # wild count claimed. Named rather than lumped into DIVERGENT — a phantom KO
                # removed is this swap's whole purpose, and it still owes a ruling.
                verdict = "NARROWED"
            else:
                verdict = "unlabelled"
            tally[verdict] += 1
            flips.append({"id": f"{ep}-{fr}", "agent": agent, "new": _cell(new_key),
                          "old": _cell(old_key), "verdict": verdict,
                          "correct": sorted(correct), "new_chosen": list(dec_new.chosen or []),
                          "old_chosen": list(dec_old.chosen or [])})
        print(f"{ep + '-' + str(fr):<14} {agent[:12]:<13} {_cell(new_key):<28} "
              f"{_cell(old_key):<28} {verdict:<12}")

    print(f"\nframes with a KO line: {tally['frames']}  agree: {tally['agree']}  "
          f"flips: {tally['flip']}  (FIX {tally['FIX']} · REGRESSION {tally['REGRESSION']} · "
          f"NARROWED {tally['NARROWED']} · DIVERGENT {tally['DIVERGENT']} · "
          f"unlabelled {tally['unlabelled']})  errors: {tally['error']}")
    gate = tally["REGRESSION"] == 0
    print(f"DECISION GATE (ADR-0072): {'PASS' if gate else 'FAIL'}  "
          f"(rule: zero unruled REGRESSION frames; {tally['REGRESSION']} unruled)")
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps({"gate": "decision", "passed": gate,
                                        "tally": dict(tally), "flips": flips}, indent=2),
                            encoding="utf-8")
        print(f"-> {json_out}")
    return 0 if gate else 1


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="every frame, not only the flips")
    ap.add_argument("--json", type=Path, default=None, help="write the flip table as JSON")
    args = ap.parse_args(argv)
    return sweep(args.all, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
