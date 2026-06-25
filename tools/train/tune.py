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

from train.blunder.store import DEFAULT_PATH, load_corrections  # noqa: E402
from train.tuner.io import sparse_overrides, write_meta, write_overrides, write_proposals  # noqa: E402
from train.tuner.run import tune  # noqa: E402


def _build_pilot(agent: str):
    """The agent's real (engine-backed) Pilot + its authored seed weights, mirroring main.py."""
    from cg.api import all_attack
    from common.cards import CardFunctions
    from common.general_strategy import GENERAL_STRATEGY
    from common.pilot import Pilot
    from common.scouting.provider import EngineCardStatProvider

    agent_dir = REPO / "src" / "agents" / agent
    spec = importlib.util.spec_from_file_location(f"{agent}_strategy", agent_dir / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    strategy = mod.STRATEGY
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text().splitlines()[:60] if x.strip()]
    attacks = all_attack()
    seeds = {h.id: h.weight for h in (*GENERAL_STRATEGY.hypotheses, *strategy.hypotheses)}
    pilot = Pilot(
        strategy, deck, general_strategy=GENERAL_STRATEGY,
        stats=EngineCardStatProvider(), functions=CardFunctions.load(),
        attacks={a.attackId: a.damage for a in attacks},
        attack_costs={a.attackId: len(a.energies) for a in attacks},
    )
    return pilot, seeds


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compile Corrections -> tuned.json + proposals")
    ap.add_argument("--agent", help="only this agent (default: every agent in the log)")
    ap.add_argument("--store", default=str(DEFAULT_PATH))
    args = ap.parse_args(argv)

    corrections = [c for c in load_corrections(args.store) if c.source == "own"]
    agents = {c.agent for c in corrections}
    if args.agent:
        agents &= {args.agent}
    if not agents:
        print("no own-source corrections to tune")
        return

    for agent in sorted(agents):
        corrs = [c for c in corrections if c.agent == agent]
        try:
            pilot, seeds = _build_pilot(agent)
        except Exception as exc:  # engine/strategy not available
            print(f"[{agent}] could not build Pilot: {exc}")
            continue
        result = tune(corrs, pilot, seeds)
        changed = sparse_overrides(result.overrides, seeds)   # only genuine deltas reach tuned.json
        agent_dir = REPO / "src" / "agents" / agent
        out = write_overrides(changed, agent_dir / "tuned.json")
        write_meta(agent_dir / "tuned.meta.json", corrections=corrs, when=datetime.now())  # ADR-0019
        print(f"[{agent}] {len(corrs)} corrections -> {out} "
              f"| {len(changed)} weight change(s), {len(result.proposals)} proposals, "
              f"{len(result.skipped)} skipped")
        for hid, new in sorted(changed.items()):
            print(f"  WEIGHT {hid}: {seeds[hid]} -> {new}")
        if not changed:
            print("  (no weight changes from authored defaults - leverage is in the proposals below)")
        prop_out = write_proposals(
            REPO / "data" / "proposals" / f"{agent}.json", agent, result.proposals,
            result.skipped, generated_at=datetime.now().isoformat(timespec="seconds"))
        print(f"  proposals -> {prop_out} (durable; /blunder-buster reads this)")
        for p in result.proposals:
            print(f"  PROPOSE {p.id} (seed {p.seed_weight}): {p.trigger_sketch}")
            print(f"    rationale: {p.rationale}")
        for c, why in result.skipped:
            print(f"  SKIP frame {c.decision.get('frame')}: {why}")


if __name__ == "__main__":
    main()
