"""tune — compile the Correction log into per-deck tuned.json + Hypothesis proposals.

    python tools/train/tune.py [--agent mega_starmie] [--store <log>]

Engine-backed: builds each agent's real Pilot exactly like its main.py, then routes each of
its `own` Corrections to a weight fit (W) or a Hypothesis proposal (H) — ADR-0017. Corrections
without an embedded `obs` are skipped (backfill from their replay first). `peer` corrections are
deferred (they need mapping to our deck). See docs/blunder-tuner.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.blunder.reviewed import DEFAULT_REVIEWED, load_reviewed, partition_reviewed  # noqa: E402
from train.blunder.store import DEFAULT_PATH, load_corrections  # noqa: E402
from train.tuner.fit import DEFAULT_REG  # noqa: E402
from train.tuner.io import sparse_overrides, write_meta, write_overrides, write_proposals  # noqa: E402
from train.tuner.report_md import render_run_report  # noqa: E402
from train.tuner.run import tune  # noqa: E402


def _build_pilot(agent: str):
    """The agent's real (engine-backed) Pilot + its authored seed weights, mirroring main.py."""
    from cg.api import all_attack
    from common.cards import CardFunctions
    from common.strategy.general_strategy import GENERAL_STRATEGY
    from common.pilot import Pilot
    from common.scouting.provider import (
        EngineCardStatProvider, parse_attack_bench_snipe, parse_attack_recoil)

    agent_dir = REPO / "src" / "agents" / agent
    spec = importlib.util.spec_from_file_location(f"{agent}_strategy", agent_dir / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    strategy = mod.STRATEGY
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text().splitlines()[:60] if x.strip()]
    attacks = all_attack()
    seeds = {h.id: h.weight for h in (*GENERAL_STRATEGY.hypotheses, *strategy.hypotheses)}
    pilot = Pilot(                                 # mirror main.py EXACTLY — incl. recoil + bench_snipe,
        strategy, deck, general_strategy=GENERAL_STRATEGY,   # else the W-route featurizes a pilot whose
        stats=EngineCardStatProvider(), functions=CardFunctions.load(),  # snipe rider / draw-guard differ
        attacks={a.attackId: a.damage for a in attacks},     # from runtime (snipe-for-the-ko never fires)
        attack_costs={a.attackId: len(a.energies) for a in attacks},
        recoil={a.attackId: parse_attack_recoil(a.text) for a in attacks},
        bench_snipe={a.attackId: parse_attack_bench_snipe(a.text) for a in attacks},
    )
    return pilot, seeds


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):           # labels carry '→'/curly quotes; cp1252 would crash
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Compile Corrections -> tuned.json + proposals")
    ap.add_argument("--agent", help="only this agent (default: every agent in the log)")
    ap.add_argument("--store", default=str(DEFAULT_PATH))
    ap.add_argument("--reg", type=float, default=DEFAULT_REG,
                    help="weight-fit conservatism (higher = stay near authored seeds; "
                         f"default {DEFAULT_REG}). Lower it to let clean corrections move weights more.")
    ap.add_argument("--report-dir", default=str(REPO / "docs" / "tuning" / "runs"),
                    help="where to write the human-readable per-run Markdown report")
    ap.add_argument("--no-report", action="store_true", help="skip writing the per-run report")
    ap.add_argument("--reviewed", default=str(DEFAULT_REVIEWED),
                    help="the reviewed-corrections ledger (already-assessed blunders to exclude)")
    args = ap.parse_args(argv)

    reviewed = load_reviewed(args.reviewed)
    corrections = [c for c in load_corrections(args.store) if c.source == "own"]
    agents = {c.agent for c in corrections}
    if args.agent:
        agents &= {args.agent}
    if not agents:
        print("no own-source corrections to tune")
        return

    for agent in sorted(agents):
        corrs_all = [c for c in corrections if c.agent == agent]
        corrs, dispositioned = partition_reviewed(corrs_all, reviewed)  # drop already-assessed blunders
        try:
            pilot, seeds = _build_pilot(agent)
        except Exception as exc:  # engine/strategy not available
            print(f"[{agent}] could not build Pilot: {exc}")
            continue
        result = tune(corrs, pilot, seeds, reg=args.reg)
        changed = sparse_overrides(result.overrides, seeds)   # only genuine deltas reach tuned.json
        agent_dir = REPO / "src" / "agents" / agent
        out = write_overrides(changed, agent_dir / "tuned.json")
        write_meta(agent_dir / "tuned.meta.json", corrections=corrs, when=datetime.now())  # ADR-0019
        print(f"[{agent}] {len(corrs)} corrections -> {out} "
              f"| {len(changed)} weight change(s), {len(result.proposals)} proposals, "
              f"{len(result.skipped)} skipped")
        sat = result.n_constraints - len(result.unsatisfied)
        if result.n_constraints:
            verb = "fit adopted" if result.fit_adopted else "seeds kept"
            print(f"  W-route: {sat}/{result.n_constraints} ranking constraints satisfied "
                  f"({verb}; seeds alone satisfy {result.base_satisfied})")
        for hid, new in sorted(changed.items()):
            print(f"  WEIGHT {hid}: {seeds[hid]} -> {new}")
        if not changed and result.n_constraints:
            print("  (no weight changes: the fit satisfied no more corrections than the authored "
                  "seeds - leverage is in the proposals / unsatisfied list below)")
        elif not changed:
            print("  (no weight changes from authored defaults - leverage is in the proposals below)")
        for c in result.unsatisfied:                  # the fit couldn't honour these (conflict / needs a rule)
            print(f"  UNSATISFIED ep {c.episode_id} frame {c.decision.get('frame')} "
                  f"({c.category}): contradictory correction or needs a new Hypothesis, not a weight")
        prop_out = write_proposals(
            REPO / "data" / "proposals" / f"{agent}.json", agent, result.proposals,
            result.skipped, generated_at=datetime.now().isoformat(timespec="seconds"),
            reviewed=dispositioned)
        print(f"  proposals -> {prop_out} (durable; /blunder-buster reads this)")
        for p in result.proposals:
            print(f"  PROPOSE {p.id} (seed {p.seed_weight}): {p.trigger_sketch}")
            print(f"    rationale: {p.rationale}")
        for c, why in result.skipped:
            print(f"  SKIP frame {c.decision.get('frame')}: {why}")
        if dispositioned:                                 # already-assessed blunders, held off fresh work
            from collections import Counter
            by = Counter((e or {}).get("disposition", "?") for _, e in dispositioned)
            print(f"  reviewed (excluded): {len(dispositioned)} already-assessed "
                  f"({', '.join(f'{k} {n}' for k, n in sorted(by.items()))}) — data/corrections/reviewed.json")
            for c, e in dispositioned:
                print(f"    SEEN ep {c.episode_id} frame {c.decision.get('frame')} "
                      f"[{(e or {}).get('disposition', '?')}]: {(e or {}).get('reason', '')}")

        if not args.no_report:                            # human-readable per-run report (docs/tuning/runs/)
            now = datetime.now()
            build = next((c.agent_build for c in corrs if c.agent_build), None)
            md = render_run_report(agent, result, seeds, changed, reg=args.reg,
                                   when_iso=now.isoformat(timespec="seconds"), build=build,
                                   n_corrections=len(corrs), reviewed=dispositioned)
            report_dir = Path(args.report_dir)
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / f"{agent}_{now:%Y%m%d-%H%M%S}.md"
            report_path.write_text(md, encoding="utf-8")
            print(f"  report -> {report_path} (human-readable; /blunder-buster appends to it)")


if __name__ == "__main__":
    main()
