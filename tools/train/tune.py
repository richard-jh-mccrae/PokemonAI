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
from train.tuner.io import authored_seeds, sparse_overrides, write_meta, write_overrides, write_proposals  # noqa: E402
from train.tuner.propose import believed_archetype  # noqa: E402  (posture belief, ADR-0041)
from train.tuner.report_md import render_run_report  # noqa: E402
from train.tuner.run import tune  # noqa: E402


def _build_pilot(agent: str):
    """The agent's real (engine-backed) Pilot + its authored seed weights, mirroring main.py."""
    from cg.api import all_attack
    from common.cards import CardFunctions
    from common.effects import CardEffects
    from common.strategy.general_strategy import GENERAL_STRATEGY
    from common.pilot import Pilot
    from common.value import ValueModel
    from common.scouting.provider import (
        EngineCardStatProvider, build_attack_stats, load_attack_overrides,
        parse_attack_bench_snipe, parse_attack_ignores_active_effects, parse_attack_recoil)
    from common.scouting.artifact import load_artifact
    from common.scouting.briefs import load_briefs
    from common.scouting.scout import Scout

    agent_dir = REPO / "src" / "agents" / agent
    spec = importlib.util.spec_from_file_location(f"{agent}_strategy", agent_dir / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    strategy = mod.STRATEGY
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text().splitlines()[:60] if x.strip()]
    attacks = all_attack()
    seeds = authored_seeds(GENERAL_STRATEGY, strategy)   # incl. weight_overrides (ADR-0035)
    provider = EngineCardStatProvider()            # shared by Pilot stats + Scout, exactly as main.py
    pilot = Pilot(                                 # mirror main.py EXACTLY -- incl. recoil + bench_snipe,
        strategy, deck, general_strategy=GENERAL_STRATEGY,   # else W-route featurizes a pilot whose
        stats=provider, functions=CardFunctions.load(),  # snipe rider / draw-guard differ
        attacks={a.attackId: a.damage for a in attacks},     # from runtime (snipe-for-the-ko never fires)
        attack_costs={a.attackId: len(a.energies) for a in attacks},
        recoil={a.attackId: parse_attack_recoil(a.text) for a in attacks},
        bench_snipe={a.attackId: parse_attack_bench_snipe(a.text) for a in attacks},
        ignores_active_effects={a.attackId: parse_attack_ignores_active_effects(a.text) for a in attacks},
        effects=CardEffects.load(),                            # ADR-0032 Effect Clauses (mirror main.py)
        attack_stats=build_attack_stats(attacks, load_attack_overrides()),  # ADR-0032 per-attack records
                                                              # incl. energyTypes — the type-aware attach reads them
        # the wiring-pass kill-switches at main.py's shipped defaults (A/B-cleared 2026-07-02) — a
        # retest must decide with the same backstops the live agent runs
        lethal_verify=strategy.params.get("lethal_verify", True),
        planner_engine_rank=strategy.params.get("planner_engine_rank", True),
        planner_key_threat=strategy.params.get("planner_key_threat", True),
        lethal_family=strategy.params.get("lethal_family", True),
        lethal_veto=strategy.params.get("lethal_veto", True),
        objectives_race=strategy.params.get("objectives_race", True),  # ADR-0040 Tier-3 KO Race
        objectives_path=strategy.params.get("objectives_path", True),  # ADR-0040 Prize-Path consumers
        objectives_phases=strategy.params.get("objectives_phases", True),  # ADR-0040 derived phases
        gamble_lines=strategy.params.get("gamble_lines", True),  # ADR-0039 Tier-2 Gamble rung
        snipe_prize_redundant=strategy.params.get("snipe_prize_redundant", True),  # ADR-0044 (DEFAULT ON 2026-07-06)
        forced_promotion=strategy.params.get("forced_promotion", True),  # ADR-0044 (DEFAULT ON 2026-07-06)
        match_planner_steer=strategy.params.get("match_planner_steer", True),  # ADR-0045 S3 (DEFAULT ON 2026-07-07)
        forgo_ko=strategy.params.get("forgo_ko", True),  # ADR-0045 S4 forgo-KO (DEFAULT ON 2026-07-07, ladder-matured)
        value_model=(ValueModel.load() if strategy.params.get("value_model", False) else None),  # ADR-0042
        escalation=strategy.params.get("escalation", False),  # ADR-0043 Tier-6 (needs search_budget>0)
        search_budget=strategy.params.get("search_budget", 0),
        scout=Scout(load_artifact(), provider=provider),  # the Read — main.py wires it; without it
        briefs=load_briefs(),                             # favorability/γ are dead in every retest AND in
        posture=strategy.params.get("posture", True),     # value-feature extraction (fixed 2026-07-05)
    )
    return pilot, seeds


def _layer_tag(planner: bool, lethal: bool) -> str:
    """Line marks for decisions the live trace shows were Planner/Solver-driven (ADR-0030/0031) —
    scoring didn't choose there, so the fix is planner.py code (the win rung for [LETHAL], the
    heuristic rungs for [PLANNED] — one module since ADR-0037), never a weight/when()."""
    return ("[PLANNED] " if planner else "") + ("[LETHAL] " if lethal else "")


def _live_layers(c) -> tuple[bool, bool]:
    """(planner_committed, lethal_locked) from a Correction's embedded live trace."""
    live = c.live_trace or {}
    return live.get("planned") is not None, live.get("lethal") is not None


def _posture_tag(mismatch: bool, archetype) -> str:
    """Line mark for a correction the human flagged as an opponent-Read miss (ADR-0041): the fix is a
    matchup-doctrine change against ``archetype`` — its Matchup Brief (/matchup-genie) or recognition —
    NOT a generic weight/when(). /blunder-buster routes on this the way it routes [PLANNED]/[LETHAL]."""
    return f"[POSTURE≠ {archetype or '?'}] " if mismatch else ""


def _live_posture(c) -> tuple[bool, object]:
    """(posture_mismatch, believed_archetype) for a raw Correction — the human's Read verdict + who
    the agent thought it faced (live_trace.posture top, ADR-0041)."""
    return bool(getattr(c, "posture_mismatch", False)), believed_archetype(c)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):           # labels carry '->'/curly quotes; cp1252 would crash
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
        n_critical = sum(p.critical for p in result.proposals) + sum(
            c.is_critical for c in result.unsatisfied) + sum(c.is_critical for c, _ in result.skipped)
        if n_critical:
            print(f"  *** {n_critical} CRITICAL correction(s) flagged -- /blunder-buster resolves "
                  f"these FIRST (blocking) before any other cluster ***")
        n_layer = sum(p.planner_committed or p.lethal_locked for p in result.proposals) + sum(
            any(_live_layers(c)) for c in result.unsatisfied) + sum(
            any(_live_layers(c)) for c, _ in result.skipped)
        if n_layer:
            print(f"  *** {n_layer} correction(s) where the live pick was Planner/Solver-driven "
                  f"(live_trace planned/lethal non-null) — scoring didn't choose there; the fix "
                  f"lives in planner.py (win rung vs heuristic rungs), never a weight or when() ***")
        n_posture = sum(p.posture_mismatch for p in result.proposals) + sum(
            _live_posture(c)[0] for c in result.unsatisfied) + sum(
            _live_posture(c)[0] for c, _ in result.skipped)
        if n_posture:
            print(f"  *** {n_posture} correction(s) flagged POSTURE-MISMATCH (opponent Read wrong) — "
                  f"tie each to its believed archetype's Matchup Brief / recognition (/matchup-genie), "
                  f"never a generic weight or when() (ADR-0041) ***")
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
        for c in result.unsatisfied:                  # fit couldn't honour these (conflict / needs a rule)
            mark = ("[CRITICAL] " if c.is_critical else "") + _layer_tag(*_live_layers(c)) \
                + _posture_tag(*_live_posture(c))
            print(f"  {mark}UNSATISFIED ep {c.episode_id} frame {c.decision.get('frame')} "
                  f"({c.category}): contradictory correction or needs a new Hypothesis, not a weight")
            if c.rationale:                            # show it so CRITICAL marker visible here too
                print(f"    rationale: {c.rationale}")
        prop_out = write_proposals(
            REPO / "data" / "corrections" / "tuner" / f"{agent}.json", agent, result.proposals,
            result.skipped, generated_at=datetime.now().isoformat(timespec="seconds"),
            reviewed=dispositioned)
        print(f"  proposals -> {prop_out} (durable; /blunder-buster reads this)")
        for p in result.proposals:
            mark = ("[CRITICAL] " if p.critical else "") + _layer_tag(p.planner_committed, p.lethal_locked) \
                + _posture_tag(p.posture_mismatch, p.believed_archetype)
            print(f"  {mark}PROPOSE {p.id} (seed {p.seed_weight}): {p.trigger_sketch}")
            print(f"    rationale: {p.rationale}")
        for c, why in result.skipped:
            mark = _layer_tag(*_live_layers(c)) + _posture_tag(*_live_posture(c))
            print(f"  {mark}SKIP frame {c.decision.get('frame')}: {why}")
        if dispositioned:                                 # already-assessed blunders, held off fresh work
            from collections import Counter
            by = Counter((e or {}).get("disposition", "?") for _, e in dispositioned)
            print(f"  reviewed (excluded): {len(dispositioned)} already-assessed "
                  f"({', '.join(f'{k} {n}' for k, n in sorted(by.items()))}) -- data/corrections/reviewed.json")
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
