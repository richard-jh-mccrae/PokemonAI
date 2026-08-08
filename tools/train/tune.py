"""tune — compile the Correction log into per-deck tuned.json + Hypothesis proposals.

    python tools/train/tune.py [--agent mega_starmie] [--store <log>] [--dry-run]

Engine-backed: builds each agent's real Pilot exactly like its main.py, then routes each of
its `own` Corrections to a weight fit (W) or a Hypothesis proposal (H) — ADR-0017. Corrections
without an embedded `obs` are skipped (backfill from their replay first). `peer` corrections are
deferred (they need mapping to our deck). See docs/blunder-tuner.md.

WRITES (every run, unless `--dry-run`): each deck's `src/agents/<deck>/tuned.json` (+ `.meta.json`),
the durable tuner ledger `data/corrections/tuner/<deck>.json`, and a `docs/tuning/runs/*.md` report.
So a plain run RECOMPILES the committed tuned.json from scratch — use `--dry-run` for any
verification / completion-gate CHECK (prints everything, writes nothing), and the plain form only
when you intend to refresh the ledger + weights as a deliberate, separately-committed step.
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
    """Built by the shared runtime (ADR-0055), never a local kill-switch mirror: a mirror drifts, and
    then retests decide with different backstops than the live agent."""
    from common.runtime import build_pilot
    from common.strategy.general_strategy import GENERAL_STRATEGY

    agent_dir = REPO / "src" / "agents" / agent
    spec = importlib.util.spec_from_file_location(f"{agent}_strategy", agent_dir / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    strategy = mod.STRATEGY
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text().splitlines()[:60] if x.strip()]
    seeds = authored_seeds(GENERAL_STRATEGY, strategy)   # incl. weight_overrides (ADR-0035)
    return build_pilot(strategy, deck), seeds


def _layer_tag(planner: bool, lethal: bool) -> str:
    """Scoring did not choose on a Planner/Solver-driven decision, so the fix is `planner.py` code
    (ADR-0030/0031/0037), never a weight or a `when()`."""
    return ("[PLANNED] " if planner else "") + ("[LETHAL] " if lethal else "")


def _live_layers(c) -> tuple[bool, bool]:
    """(planner_committed, lethal_locked) from a Correction's embedded live trace."""
    live = c.live_trace or {}
    return live.get("planned") is not None, live.get("lethal") is not None


def _posture_tag(mismatch: bool, archetype) -> str:
    """An opponent-Read miss (ADR-0041): the fix is `archetype`'s Matchup Brief or its recognition,
    NOT a generic weight or `when()`."""
    return f"[POSTURE≠ {archetype or '?'}] " if mismatch else ""


def _scope_tag(scope, subject) -> str:
    """A Turn blunder (ADR-0049) is prima facie a `plan_turn` fix. A routing PRIOR, not an auto-route:
    a turn whose `planned` is null throughout means the Planner never committed."""
    if scope == "turn":
        return f"[TURN {subject}] "
    return ""


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
    ap.add_argument("--dry-run", action="store_true",
                    help="READ-ONLY check: compute + print the fit / proposals / UNSATISFIED exactly "
                         "as normal, but write NOTHING (no tuned.json, tuned.meta.json, tuner ledger, "
                         "or report). Use for the completion-gate / verification runs so a check can "
                         "never clobber the committed tuned.json.")
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
    if args.dry_run:
        print("=== DRY-RUN: read-only check, no files written "
              "(tuned.json / tuned.meta.json / tuner ledger / report all skipped) ===")

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
        out = agent_dir / "tuned.json"
        if not args.dry_run:
            write_overrides(changed, out)
            write_meta(agent_dir / "tuned.meta.json", corrections=corrs, when=datetime.now())  # ADR-0019
        dry = " [dry-run: NOT written]" if args.dry_run else ""
        print(f"[{agent}] {len(corrs)} corrections -> {out}{dry} "
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
        prop_out = REPO / "data" / "corrections" / "tuner" / f"{agent}.json"
        if not args.dry_run:
            write_proposals(prop_out, agent, result.proposals, result.skipped,
                            generated_at=datetime.now().isoformat(timespec="seconds"),
                            reviewed=dispositioned)
        print(f"  proposals -> {prop_out}{' [dry-run: NOT written]' if args.dry_run else ''} "
              f"(durable; /blunder-buster reads this)")
        n_scoped = sum(p.scope != "decision" for p in result.proposals)
        if n_scoped:
            print(f"  *** {n_scoped} SCOPED correction(s) (turn, ADR-0049) — never a ranking "
                  f"constraint: the fix is plan-layer code (plan_turn), and the blunder's gate "
                  f"is its Span re-drive ***")
        for p in result.proposals:
            mark = ("[CRITICAL] " if p.critical else "") + _scope_tag(p.scope, p.subject) \
                + _layer_tag(p.planner_committed, p.lethal_locked) \
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

        if not args.no_report and not args.dry_run:       # human-readable per-run report (docs/tuning/runs/)
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
