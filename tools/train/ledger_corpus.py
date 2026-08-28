"""The Ledger's training dashboard: every correction frame, every deck, one sweep.

Replays each human-ruled frame through the LIVE runtime (the Ledger brain) with the offline
cgpy provider and reports, per deck: agreement with the ruling, every miss WITH ITS RATIONALE
beside the Ledger's own price list (the rationale is context — some old rulings deserve a
second look, not a weight nudge), a coverage-gap census counted per affected decision, and —
against a prior baseline file — the frames that used to agree and no longer do. Frames with no
`correct` ruling assert nothing and are counted `ungraded`, never as misses. A sweep is only
sound within one deck (a frame replayed through another decklist is off-policy), so frames are
grouped by their recording agent throughout. Honesty rules (ADR-0147): frames archived without
the live shell's `own_prizes` anchor get one stamped before replay, and rulings dispositioned
in `reviewed.json` are RETIRED — listed in their own section, never graded.

    python tools/train/ledger_corpus.py [--decks mega_starmie ...] [--workers N]
        [--baseline data/ledger-corpus-dashboard.json] [--limit N]
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "src")]

from common.option_equivalence import class_of, option_equivalence  # noqa: E402
from functools import partial

from common.engine import (CgpyTransitionProvider,
                           determinized_prize_knowledge)  # noqa: E402 - offline replay only
from deprecated.bellman.effects import CardEffects  # noqa: E402 - replay coverage facts (ADR-0147)
from common.runtime import build_runtime  # noqa: E402
from common.cards import card_store  # noqa: E402
from common.decision import (ComputeConfiguration, PolicyConfiguration,
                             SearchConfiguration, correction_compute_profile)  # noqa: E402
from common.ledger import (EvaluationModel, LedgerDecider, OpponentProfile,
                           ValuationConfiguration)  # noqa: E402
from common.opponent import OpponentMechanic, OpponentTrait  # noqa: E402
from common.strategy import PrizePlan  # noqa: E402
from train.blunder.store import dedup_corrections, jsonl_files, load_corrections  # noqa: E402
from train.blunder.correction import correction_selection_error  # noqa: E402
from train.blunder.decode import option_label  # noqa: E402
from train.blunder.reviewed import load_reviewed, partition_reviewed  # noqa: E402
from train.ledger_parity import assert_runtime_parity  # noqa: E402


DECKS = ("mega_starmie", "mega_lucario", "dragapult_ex")
DEFAULT_OUTPUT = REPO / "data" / "ledger-corpus-dashboard.json"
SEMANTIC_DECISIONS = frozenset({
    "additive_marginal_valuation", "continuation_persistence",
    "legal_development_reach", "neutral_tie_lottery",
})


def _build_runtime(deck_name: str, weight_overrides=None, *, provider_backend="cgpy-ledger"):
    agent_dir = REPO / "src" / "agents" / deck_name
    spec = importlib.util.spec_from_file_location("_ledger_corpus_strategy",
                                                  agent_dir / "strategy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    deck = [int(value) for value in (agent_dir / "deck.csv").read_text().splitlines()
            if value.strip()]
    valuation_configuration = None
    if weight_overrides:
        from common.ledger import ValuationConfiguration

        valuation_configuration = ValuationConfiguration.general().with_values(weight_overrides)
    if provider_backend == "cgpy-ledger":
        replay_provider = partial(CgpyTransitionProvider, effects=CardEffects.load())
    elif provider_backend == "native-cg-ledger":
        replay_provider = None
    else:
        raise ValueError(f"unsupported replay provider {provider_backend!r}")
    return build_runtime(module.STRATEGY, deck, provider_factory=replay_provider,
                         valuation_configuration=valuation_configuration,
                         compute_configuration=correction_compute_profile(),
                         decision_parity_oracle=assert_runtime_parity)


def _recorded_model(configuration: dict) -> EvaluationModel:
    def pairs(value):
        return value.items() if isinstance(value, dict) else value

    saved = configuration["evaluation_model"]
    valuation = saved["valuation"]
    model = EvaluationModel(
        ValuationConfiguration(valuation["values"],
                               schema_version=valuation["schema_version"]),
        card_store(),
        PrizePlan(tuple(saved["prize_plan"]["protect"]),
                  tuple(saved["prize_plan"]["offer"])),
        {name: OpponentProfile(
            {int(card_id): tuple(roles) for card_id, roles in pairs(profile["roles"])},
            tuple(OpponentTrait(*trait) for trait in profile["traits"]),
            tuple(OpponentMechanic(*mechanic) for mechanic in profile["mechanics"]),
            {int(card_id): float(value) for card_id, value in pairs(profile["resources"])},
        ) for name, profile in saved["opponent_profiles"].items()},
    )
    if model.store_identity != saved["card_store_identity"] \
            or model.configuration.identity != valuation["identity"] \
            or model.prize_plan.identity != saved["prize_plan"]["identity"] \
            or model.identity != saved["identity"]:
        raise ValueError("recorded Evaluation Model identity cannot be resolved")
    return model


def _recorded_compute(configuration: dict) -> ComputeConfiguration:
    saved = configuration["compute"]
    search = {key: value for key, value in saved["search"].items() if key != "identity"}
    if search.get("schema_version") not in {1, 4, 5}:
        raise ValueError("unsupported recorded Search Configuration schema version")
    if saved.get("schema_version") not in {1, 2}:
        raise ValueError("unsupported recorded Compute Configuration schema version")
    legacy_search = search.get("schema_version", 0) < 5
    legacy_compute = saved.get("schema_version") < 2
    search.pop("main_depth_budget", None)
    search.pop("main_continuation_discount", None)
    if legacy_search:
        search["schema_version"] = 5
    policy = {key: value for key, value in saved["policy"].items() if key != "identity"}
    policy["accepted_statuses"] = tuple(policy["accepted_statuses"])
    compute = ComputeConfiguration(
        schema_version=2,
        search=SearchConfiguration(**search), policy=PolicyConfiguration(**policy),
        profile=saved.get("profile", "deployment"))
    if (not legacy_search and not legacy_compute and (
            compute.search.identity != saved["search"]["identity"]
            or compute.policy.identity != saved["policy"]["identity"]
            or compute.identity != saved["identity"])):
        raise ValueError("recorded Compute Configuration identity cannot be resolved")
    return compute


def _build_replay_ledger(deck_name: str, configuration: dict, *, provider_backend: str,
                         deck) -> LedgerDecider:
    shell = _build_runtime(deck_name, provider_backend=provider_backend)
    return LedgerDecider(
        deck, deck_name, _recorded_model(configuration),
        provider_factory=shell.ledger.provider_factory,
        provider_kwargs=shell.ledger.provider_kwargs,
        compute=_recorded_compute(configuration),
        parity_oracle=shell.ledger.parity_oracle,
    )


def _satisfies_one(chosen, correct, equivalence) -> bool:
    if chosen is None or correct is None:
        return False
    if not correct:
        return not chosen
    picked = frozenset(chosen)
    return all(bool(class_of(equivalence, wanted) & picked) for wanted in correct)


def _satisfies_human(chosen, correction, equivalence) -> bool:
    """The primary ruling OR any recorded equally-acceptable alternative satisfies."""
    rulings = [list(correction.correct or ())]
    rulings += [list(alt or ()) for alt in (correction.correct_alternatives or ())]
    return any(_satisfies_one(chosen, ruling, equivalence) for ruling in rulings)


def _runtime_equivalence(decision) -> dict:
    result = getattr(decision, "decision_result", None)
    roster = getattr(result, "roster", None)
    classes = {}
    for candidate in getattr(roster, "candidates", ()):
        selections = getattr(candidate.action, "equivalent_selections", ())
        singleton_indices = {selection[0] for selection in selections if len(selection) == 1}
        if len(singleton_indices) > 1:
            group = frozenset(singleton_indices)
            classes.update((index, group) for index in group)
    return classes


def _training_candidates(decision) -> list[dict]:
    result = getattr(decision, "decision_result", None)
    roster = getattr(result, "roster", None)
    rows = []
    for candidate in getattr(roster, "candidates", ()):
        delta = getattr(candidate, "delta", None)
        rows.append({
            "action": str(candidate.action.identity),
            "selection": list(candidate.action.selection),
            "status": candidate.status.value,
            "decision_delta": None if delta is None else delta.total,
            "search_value": (None if candidate.search_value is None
                             else candidate.search_value.total),
            "features": {component.key: component.activation
                         for component in (() if delta is None else delta.components)},
            "components": [{
                "feature": component.key,
                "activation": component.activation,
                "coefficient": component.coefficient,
                "contribution": component.value,
                "provenance": list(component.provenance),
            } for component in (() if delta is None else delta.components)],
            "successors": [{
                "probability": successor.probability,
                "ended": successor.ended,
                "status": successor.status.value,
                "position_key": successor.state.position_key,
                "action_path": [str(action) for action in successor.action_path],
                "gaps": list(successor.valuation.gaps),
            } for successor in candidate.successors],
            "gaps": list(candidate.gaps),
        })
    return rows


def _grading_eligibility(has_ruling: bool, candidates,
                         structural_error: str | None = None) -> tuple[bool, str | None]:
    if structural_error is not None:
        return False, structural_error
    if not has_ruling:
        return False, "no_ruling"
    candidates = tuple(candidates)
    if not candidates or any(candidate.get("status") != "complete"
                             for candidate in candidates):
        return False, "search_incomplete"
    return True, None


def _labels(obs, indices) -> str:
    select = obs.get("select") or {}
    options = select.get("option") or []
    current = obs.get("current") or {}
    return ", ".join(option_label(options[index], current, select=select)
                     for index in indices or () if 0 <= index < len(options))


def _replay_one(deck_name: str, correction, weight_overrides=None) -> dict:
    """One frame through a fresh runtime: isolation, matching the live shell exactly —
    including the own-prize anchor the live shell stamps before every decide."""
    runtime = _build_runtime(deck_name, weight_overrides)
    obs = correction.obs
    knowledge = determinized_prize_knowledge(obs, runtime.deck)
    stamped = knowledge is not None
    if knowledge is not None:
        runtime.knowledge = knowledge
    started = time.perf_counter()
    decision = runtime.decide(obs)
    elapsed = time.perf_counter() - started
    chosen = list(decision.chosen)
    correct = list(correction.correct or ())
    has_ruling = bool(correction.correct) or correction.correct == []
    equivalence = (_runtime_equivalence(decision) or
                   option_equivalence(((obs.get("select") or {}).get("option") or []), obs))
    candidates = _training_candidates(decision)
    graded, excluded_reason = _grading_eligibility(
        has_ruling, candidates, correction_selection_error(correction))
    agrees = _satisfies_human(chosen, correction, equivalence) if graded else None
    diagnostics = decision.diagnostics or {}
    row = {
        "deck": deck_name,
        "episode_id": correction.episode_id,
        "key": f"{correction.episode_id}-{(correction.decision or {}).get('frame', -1)}",
        "id": correction.id,
        # Not always "ledger": a shell fallback (exception, forced selection) names itself
        # here, so brainless answers stay visible in the dashboard instead of hiding as misses.
        "backend": diagnostics.get("backend"),
        "scope": correction.scope,
        "context": (correction.decision or {}).get("select_context"),
        "category": correction.category,
        "graded": graded,
        "chosen": chosen,
        "recorded_chosen": list(correction.chosen),
        "correct": correct,
        "acceptable": [correct, *[list(value or ())
                                   for value in correction.correct_alternatives or ()]],
        "candidates": candidates,
        "grading_exclusion": excluded_reason,
        "exact": bool(graded and chosen == correct),
        "agrees": agrees,
        "chosen_label": _labels(obs, chosen),
        "correct_label": _labels(obs, correct),
        "rationale": correction.rationale,
        "gaps": sorted(set(diagnostics.get("gaps", ()))),
        "stamped_prizes": stamped,
        "decision_parity": diagnostics.get("decision_parity", False),
        "elapsed_seconds": elapsed,
    }
    if diagnostics.get("fallback"):                # a crashed brain must be visible, not a miss
        row["fallback"] = diagnostics["fallback"]
    if graded and not agrees:
        row["ledger"] = {"value": decision.value, "backend": diagnostics.get("backend"),
                         "valuation": diagnostics.get("valuation"),
                         "prices": list(diagnostics.get("prices", ()))[:5]}
    return row


def _deck_summary(rows: list[dict]) -> dict:
    graded = [row for row in rows if row["graded"]]
    agrees = sum(1 for row in graded if row["agrees"])
    gap_census: Counter = Counter()
    for row in rows:
        for gap in set(row["gaps"]):
            gap_census[gap] += 1                    # decisions affected, never mentions
    return {
        "records": len(rows),
        "graded": len(graded),
        "agrees": agrees,
        "misses": len(graded) - agrees,
        "agreement": round(agrees / len(graded), 4) if graded else None,
        "ungraded": len(rows) - len(graded),
        "incomplete": sum(row.get("grading_exclusion") == "search_incomplete"
                          for row in rows),
        "decision_seconds": round(sum(row["elapsed_seconds"] for row in rows), 2),
        "gap_decisions": sum(1 for row in rows if row["gaps"]),
        "gap_census": dict(gap_census.most_common()),
        # A crashed brain that happened to pick the ruled action is NOT a success.
        "fallbacks": sum(1 for row in rows if row.get("fallback")),
    }


def payload(rows: list[dict], *, retired: list[dict] | None = None,
            baseline: dict | None = None, semantic_flips: dict | None = None) -> dict:
    reasons = set((semantic_flips or {}).get("flips", {}).values())
    unknown_reasons = reasons - SEMANTIC_DECISIONS
    if unknown_reasons:
        raise ValueError(f"semantic flip lacks an issue decision: {sorted(unknown_reasons)[0]}")
    rows.sort(key=lambda row: (row["deck"], row["key"], row["id"]))
    retired = sorted(retired or (), key=lambda row: (row["deck"], row["key"]))
    decks = {}
    for deck_name in sorted({row["deck"] for row in rows}
                            | {row["deck"] for row in retired}):
        decks[deck_name] = _deck_summary([row for row in rows if row["deck"] == deck_name])
        decks[deck_name]["retired"] = sum(1 for row in retired if row["deck"] == deck_name)
    agreements = [summary["agreement"] for summary in decks.values()
                  if summary["agreement"] is not None]
    regressions = []
    if baseline is not None:
        held = {(row["deck"], row["id"]) for row in baseline.get("rows", ())
                if row.get("agrees")}
        regressions = [row["id"] for row in rows
                       if (row["deck"], row["id"]) in held and row["agrees"] is False]
    allowed = set((semantic_flips or {}).get("flips", ()))
    unexplained = sorted(set(regressions) - allowed)
    preserved = []
    if baseline is not None:
        for deck_name in decks:
            expected = {(row["deck"], row["id"]) for row in baseline.get("rows", ())
                        if row.get("deck") == deck_name and row.get("agrees")
                        and row.get("id") not in allowed}
            kept = {(row["deck"], row["id"]) for row in rows
                    if row.get("deck") == deck_name and row.get("agrees")}
            if expected:
                preserved.append(len(expected & kept) / len(expected))
    return {
        "schema": 1,
        "git_rev": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                           text=True).strip(),
        # An empty regressions list only means something beside the baseline it was measured
        # against; None here says "never compared", not "zero regressions".
        "baseline_git_rev": (baseline or {}).get("git_rev"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decks": decks,
        # The general configuration must clear every deck, so the headline is
        # the worst deck, never the average.
        "generality_floor": min(agreements) if agreements else None,
        "baseline_generality_floor": (baseline or {}).get("generality_floor"),
        "raw_generality_floor_retained": (
            baseline is None or not agreements
            or min(agreements) >= float(baseline.get("generality_floor") or 0.0)),
        "regressions": regressions,
        "unexplained_regressions": unexplained,
        "migration_generality_floor": round(min(preserved), 4) if preserved else None,
        "generality_floor_retained": (
            baseline is None or not preserved or min(preserved) >= 1.0),
        "retired": retired,
        "rows": rows,
    }


def render_markdown(result: dict) -> str:
    lines = ["# Ledger corpus dashboard", "",
             f"Generated {result['generated_at']} at `{result['git_rev'][:12]}`.", ""]
    lines.append("| deck | graded | agrees | agreement | ungraded | retired | "
                 "gap-affected decisions | fallbacks |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for deck_name, summary in result["decks"].items():
        agreement = ("-" if summary["agreement"] is None
                     else f"{summary['agreement'] * 100:.1f}%")
        lines.append(f"| {deck_name} | {summary['graded']} | {summary['agrees']} | "
                     f"{agreement} | {summary['ungraded']} | {summary.get('retired', 0)} | "
                     f"{summary['gap_decisions']} | {summary.get('fallbacks', 0)} |")
    floor = result["generality_floor"]
    lines += ["", f"**Generality floor (worst deck): "
                  f"{'-' if floor is None else f'{floor * 100:.1f}%'}**", ""]
    if result["regressions"]:
        lines += [f"## Regressions ({len(result['regressions'])})", ""]
        lines += [f"- `{row_id}`" for row_id in result["regressions"]] + [""]
    if result.get("retired"):
        lines += [f"## Retired rulings ({len(result['retired'])}) — dispositioned in "
                  "reviewed.json, not graded", ""]
        lines += [f"- {row['deck']} `{row['key']}`: {row['disposition']}"
                  + (f" ({row['round']})" if row.get("round") else "")
                  for row in result["retired"]] + [""]
    crashed = [row for row in result["rows"] if row.get("fallback")]
    if crashed:
        lines += [f"## Crashed decisions ({len(crashed)}) — fix the bug, ignore the grade", ""]
        for row in crashed:
            error = (row["fallback"].get("error") or {})
            lines.append(f"- {row['deck']} `{row['key']}`: {row['fallback'].get('cause')}"
                         + (f" — {error.get('type')}: {error.get('message')}"
                            if error else ""))
        lines.append("")
    incomplete = [row for row in result["rows"]
                  if row.get("grading_exclusion") == "search_incomplete"]
    if incomplete:
        lines += [f"## Incomplete searches ({len(incomplete)}) — played, not graded", ""]
        lines += [f"- {row['deck']} `{row['key']}`: "
                  + (", ".join(row.get("gaps", ())) or "non-complete candidate")
                  for row in incomplete] + [""]
    lines += ["## Misses (the triage queue: read the rationale first)", ""]
    for row in result["rows"]:
        if not row["graded"] or row["agrees"]:
            continue
        lines += [f"### {row['deck']} `{row['key']}` ({row['context']}, {row['category']})",
                  "",
                  f"- Ledger chose `{row['chosen']}` {row['chosen_label']}",
                  f"- ruling was `{row['correct']}` {row['correct_label']}",
                  f"- rationale: {row['rationale']}"]
        for price in (row.get("ledger") or {}).get("prices", ())[:3]:
            swing = price["swing"]
            rendered = "unavailable" if swing is None else f"{swing:+.4f}"
            lines.append(f"- priced {rendered} {price['action']}")
        lines.append("")
    return "\n".join(lines)


def _retired_row(correction, entry) -> dict:
    return {"deck": correction.agent,
            "key": f"{correction.episode_id}-{(correction.decision or {}).get('frame', -1)}",
            "id": correction.id,
            "disposition": entry.get("disposition"),
            "round": entry.get("round")}


def sweep(*, store, decks=DECKS, limit=None, workers: int = 1,
          baseline: dict | None = None, reviewed: dict | None = None,
          weight_overrides: dict | None = None,
          semantic_flips: dict | None = None) -> dict:
    sources = (store,) if isinstance(store, (str, Path)) else tuple(store)
    files = sorted({path for source in sources for path in jsonl_files(source)},
                   key=lambda value: str(value))
    loaded = ([correction for path in files
               for correction in load_corrections(path, dedup=False)] if files else
              [correction for source in sources for correction in load_corrections(source)])
    corpus = dedup_corrections(loaded) if files else loaded
    swept = [correction for correction in corpus
             if correction.agent in decks and correction.obs is not None]
    # A ruling the owner already dispositioned (refuted, fixed, covered…) is retired: grading
    # it would score the brain against a verdict that no longer stands (the ADR-0082 drift).
    active, dispositioned = partition_reviewed(
        swept, load_reviewed() if reviewed is None else reviewed)
    retired = [_retired_row(correction, entry) for correction, entry in dispositioned]
    tasks = [(correction.agent, correction) for correction in active]
    tasks.sort(key=lambda pair: (pair[0], pair[1].id))
    if limit is not None:
        tasks = tasks[:limit]
    rows = []
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_replay_one, deck_name, correction, weight_overrides)
                       for deck_name, correction in tasks]
            for completed, future in enumerate(as_completed(futures), start=1):
                rows.append(future.result())
                print(f"[{completed}/{len(tasks)}]", flush=True)
    else:
        for completed, (deck_name, correction) in enumerate(tasks, start=1):
            rows.append(_replay_one(deck_name, correction, weight_overrides))
            print(f"[{completed}/{len(tasks)}] {deck_name} {correction.id}", flush=True)
    return payload(rows, retired=retired, baseline=baseline, semantic_flips=semantic_flips)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"stage", "build", "view"}:
        return _corpus_main(argv)
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", action="append")
    parser.add_argument("--decks", nargs="+", default=list(DECKS))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--semantic-flips", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    baseline = (json.loads(args.baseline.read_text(encoding="utf-8"))
                if args.baseline and args.baseline.exists() else None)
    semantic_flips = (json.loads(args.semantic_flips.read_text(encoding="utf-8"))
                      if args.semantic_flips and args.semantic_flips.exists() else None)
    if (semantic_flips and baseline
            and semantic_flips.get("baseline_git_rev") != baseline.get("git_rev")):
        raise ValueError("semantic-flip allowlist names a different frozen baseline")
    result = sweep(store=args.store or [REPO / "data" / "corrections"],
                   decks=tuple(args.decks), limit=args.limit,
                   workers=max(1, args.workers), baseline=baseline,
                   semantic_flips=semantic_flips)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    from train.value_audit import build_value_audit
    audit_path = args.output.with_name(f"{args.output.stem}.value-audit.json")
    audit_path.write_text(json.dumps(
        build_value_audit(result["rows"]), indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    args.output.with_suffix(".md").write_text(render_markdown(result) + "\n",
                                              encoding="utf-8")
    floor = result["generality_floor"]
    print(f"generality floor {floor} | regressions {len(result['regressions'])} "
          f"| written to {args.output}")
    return 1 if (result["unexplained_regressions"]
                 or not result["generality_floor_retained"]) else 0


def _corpus_main(argv) -> int:
    from train.corpus import (build_snapshot, build_training_view, certify_replay,
                              stage_episode_bundle)

    parser = argparse.ArgumentParser(description="Publish lossless Ledger Corpus Snapshots")
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage", help="close one replay and telemetry stream into a bundle")
    stage.add_argument("--replay", type=Path, required=True)
    stage.add_argument("--telemetry", type=Path, required=True)
    stage.add_argument("--out", type=Path, required=True)
    build = commands.add_parser("build", help="publish audited Episode Bundles")
    build.add_argument("--bundles", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    view = commands.add_parser("view", help="materialize a pinned machine-readable view")
    view.add_argument("--snapshot", type=Path, required=True)
    view.add_argument("--out", type=Path, required=True)
    view.add_argument("--name", default="ledger_diagnostics")
    view.add_argument("--profile", type=Path)
    args = parser.parse_args(argv)
    if args.command == "stage":
        result = stage_episode_bundle(replay_path=args.replay, telemetry_path=args.telemetry,
                                      output_root=args.out)
    elif args.command == "build":
        result = build_snapshot(bundles_root=args.bundles, output_root=args.out,
                                replay_certifier=certify_replay)
    else:
        result = build_training_view(snapshot_path=args.snapshot, output_root=args.out,
                                     name=args.name, **({"profile_path": args.profile}
                                                        if args.profile else {}))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
