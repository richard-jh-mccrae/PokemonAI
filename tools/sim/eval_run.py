"""Eval harness (ADR-0053 WP2): the offline instrument G2 is measured on. A candidate vs a baseline
`battle.py` spec, compared **common-opponent** — both arms play the SAME opponent field, seat
schedule and games-per-cell — never head-to-head as the measurement. The paired difference subtracts
out the raw deck matchup, leaving only the candidate-vs-baseline effect (`sim.paired_ab`).

Power math + cell plan are pure and stdlib-only; the runner and CLI import the engine lazily.

The runner is **serial** (one server pair per cell): `battle.run_battle`'s worker fan-out emits only
win/crash lines, no film channel, and every eval game must be filmed for strata/AIVAT.
"""
from __future__ import annotations

# z_{0.025} (1.96, 95% two-sided confidence) + z_{0.20} (0.84, 80% power) — the standard
# "detect a difference of size d" constant. Per-arm games scale as (z/d)².
_Z_POWER = 2.80

# Detectable win-rate delta per preset (the sensitivity a standard run is powered for).
PRESETS = {"quick": 0.05, "default": 0.03, "fine": 0.02}
DEFAULT_PRESET = "default"


def per_arm_games(delta: float) -> int:
    """Total games ONE arm plays across all cells to detect a win-rate difference of ``delta`` at
    95%/80%: ``n = 0.5·(z/d)²`` — halved because the paired arms share the field."""
    if delta <= 0:
        raise ValueError(f"delta must be positive, got {delta}")
    return round(0.5 * (_Z_POWER / delta) ** 2)


def preset_delta(preset: str) -> float:
    """The detectable delta for a named preset (``quick``/``default``/``fine``). Raises on unknown."""
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r} (choose from {sorted(PRESETS)})")
    return PRESETS[preset]


def games_per_matchup(per_arm_total: int, n_opponents: int) -> int:
    """Per-arm games in EACH opponent cell — the per-arm total spread evenly across the opponent
    field (ceil, floored at 1 so a cell is never empty). 0 when there are no opponents."""
    if n_opponents <= 0:
        return 0
    return max(1, -(-per_arm_total // n_opponents))


def matchup_cells(opponents: list[str]) -> list[dict]:
    """The paired cells, one per ``(opponent, seat)``, each played by BOTH arms. The direct
    candidate-vs-baseline head-to-head is a SEPARATE informational block, never a cell here."""
    return [{"opponent": o, "seat": s} for o in opponents for s in (0, 1)]


# ---- the live runner (covered by a live fixture test; the planning atoms above are unit-tested) --

EVAL_DIRNAME = "eval"
MANIFEST_VERSION = 1


def _flush(manifest: dict, path) -> None:
    import json
    from pathlib import Path
    Path(path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _cell_stem(kind: str, arm: str, opponent) -> str:
    """A cell's on-disk / manifest key, namespaced by KIND so an opponent literally named ``h2h`` or
    ``ck12`` cannot collide with the head-to-head or a checkpoint cell."""
    prefix = {"matchup": "m", "checkpoint": "ck", "h2h": "h2h"}[kind]
    return f"{prefix}__{arm}" if kind == "h2h" else f"{prefix}__{arm}__{opponent}"


def run_cell(arm_dir, opp_dir, arm_deck, opp_deck, n, *, film_dir=None, extra_syspath=(),
             run_id: str = "", stem: str = "", start_index: int = 0, arm_overlay=None,
             opp_overlay=None, arm_label: str = "cand", opp_label: str = "opp") -> dict:
    """Run ``n`` seat-balanced games of one ARM vs one opponent (ADR-0021), filming clean games into
    ``film_dir``. ``wins``/``won``/``crashes``/``seat`` in the result are all the ARM's."""
    import gzip
    import json
    from pathlib import Path

    from sim.battle import AgentServer, play_match, seat_plan, to_battle_match
    from sim.corpus import film_name
    from sim.record import MatchRecorder
    from sim.selfplay import episode_id

    by_seat = {"0": {"n": 0, "wins": 0, "draws": 0}, "1": {"n": 0, "wins": 0, "draws": 0}}
    crashes, total_bytes = 0, 0
    films: list[dict] = []
    idx = start_index
    sa = AgentServer(arm_dir, extra_syspath, overlay=arm_overlay)
    sb = AgentServer(opp_dir, extra_syspath, overlay=opp_overlay)
    try:
        for a_seat in seat_plan(n):
            if not sa.alive():
                sa = AgentServer(arm_dir, extra_syspath, overlay=arm_overlay)
            if not sb.alive():
                sb = AgentServer(opp_dir, extra_syspath, overlay=opp_overlay)
            rec = MatchRecorder() if film_dir else None
            if a_seat == 0:
                res = play_match(sa, sb, arm_deck, opp_deck, recorder=rec)
            else:                                            # arm sits in engine seat 1
                res = play_match(sb, sa, opp_deck, arm_deck, recorder=rec)
            bm = to_battle_match(a_seat, res)
            cell = by_seat[str(a_seat)]
            cell["n"] += 1
            if bm.winner == 0:
                cell["wins"] += 1
            elif bm.winner is None:
                cell["draws"] += 1
            if 0 in bm.crashed:
                crashes += 1
            if film_dir is not None and rec is not None and not bm.crashed:
                eid = episode_id(f"{run_id}/{stem}", idx)
                path = Path(film_dir) / film_name(idx, eid)
                names = [None, None]
                names[a_seat] = f"{stem}#{arm_label}"        # the acting arm's seat, correctly labelled
                names[1 - a_seat] = f"{stem}#{opp_label}"
                with gzip.open(path, "wt", encoding="utf-8") as fh:
                    json.dump(rec.replay(episode_id=eid, team_names=names), fh, ensure_ascii=False)
                total_bytes += path.stat().st_size
                films.append({"path": str(path), "seat": a_seat,
                              "won": bm.winner == 0})       # the arm's result at this seat
                idx += 1
    finally:
        sa.close()
        sb.close()
    return {"by_seat": by_seat, "crashes": crashes, "bytes": total_bytes, "films": films}


def _matchup_rows(cand_cell: dict, base_cell: dict, opponent) -> list[dict]:
    """Two C3 rows (seat 0, seat 1) pairing both arms vs the same opponent. Each row carries per-arm
    ``candidate_n``/``baseline_n`` so a resume leaving the arms different sizes stays correct."""
    rows = []
    for s in ("0", "1"):
        c, b = cand_cell["by_seat"][s], base_cell["by_seat"][s]
        if c["n"] == 0 and b["n"] == 0:
            continue                                          # a seat with no games at all isn't a cell
        rows.append({"opponent": opponent, "seat": int(s), "n": min(c["n"], b["n"]),
                     "candidate_wins": c["wins"], "candidate_n": c["n"],
                     "baseline_wins": b["wins"], "baseline_n": b["n"], "draws": c["draws"]})
    return rows


def _work_list(opponents: dict, checkpoints: dict, *, do_h2h: bool) -> list[dict]:
    """The ordered cell work-list: both arms vs every opponent and every checkpoint, plus the
    optional head-to-head."""
    work = []
    for opp in opponents:
        for arm in ("candidate", "baseline"):
            work.append({"arm": arm, "opponent": opp, "kind": "matchup",
                         "stem": _cell_stem("matchup", arm, opp)})
    for ck in checkpoints:
        for arm in ("candidate", "baseline"):
            work.append({"arm": arm, "opponent": ck, "kind": "checkpoint",
                         "stem": _cell_stem("checkpoint", arm, ck)})
    if do_h2h:
        work.append({"arm": "candidate", "opponent": "h2h", "kind": "h2h",
                     "stem": _cell_stem("h2h", "candidate", "h2h")})
    return work


def _strata(films_meta: list, *, agent: str | None) -> list[dict]:
    """Best-effort C3 strata: per-game value-swing sensitivity, median-split into high/low. ``agent``
    is the real agent NAME, not a build-id spec. ``[]`` when unavailable — the block is optional."""
    if not agent or not films_meta:
        return []
    try:
        from common.value.model import ValueModel
        from meta_tracker.parse import load_replay
        from sim.eval_strata import game_sensitivity, strata_cells
        from train.tune import _build_pilot
        pilot, _ = _build_pilot(agent)
        model = ValueModel.load()
    except Exception:
        return []
    games = []
    for fm in films_meta:
        try:
            sens = game_sensitivity(pilot, model, load_replay(fm["path"]), arm_seat=fm["seat"])
        except Exception:
            sens = None
        if sens is None:
            continue
        games.append({"sensitivity": sens, "opponent": fm["opponent"], "seat": fm["seat"],
                      "arm": fm["arm"], "won": fm["won"]})
    return strata_cells(games)


def run_eval(*, run_id: str, created_at: str, git_rev: str, candidate: dict, baseline: dict,
             opponents: dict, out_root, per_cell: int, checkpoints: dict | None = None,
             h2h_n: int = 0, caps: dict | None = None, extra_syspath=(),
             resume: bool = False, preset: str = "") -> dict:
    """Run the matrix into ``<out_root>/eval/<run_id>/`` -> the C3 report. Resume is cell-granular
    and reuses the ORIGINAL run's ``per_cell``/``h2h_n``/``preset``, never a caller's new value."""
    import json
    from pathlib import Path

    from sim.corpus import cap_hit

    checkpoints = checkpoints or {}
    caps = caps or {}
    arms = {"candidate": candidate, "baseline": baseline}
    run_dir = Path(out_root) / EVAL_DIRNAME / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"

    if resume and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "running"
        per_cell = manifest.get("per_cell", per_cell)         # the original plan wins on resume
        h2h_n = manifest.get("h2h_n", h2h_n)
        preset = manifest.get("preset", preset)
    else:
        manifest = {
            "manifest_version": MANIFEST_VERSION, "run_id": run_id, "created_at": created_at,
            "git_rev": git_rev, "candidate": candidate["descriptor"], "baseline": baseline["descriptor"],
            "opponents": list(opponents), "checkpoints": list(checkpoints), "preset": preset,
            "per_cell": per_cell, "h2h_n": h2h_n, "caps": caps, "cells": {},
            "status": "running", "totals": {"games": 0, "bytes": 0},
        }
    cells = manifest["cells"]
    work = _work_list(opponents, checkpoints, do_h2h=h2h_n > 0)

    for w in work:
        stem = w["stem"]
        if cap_hit(manifest["totals"], caps):
            manifest["status"] = "capped"
            break
        if resume and cells.get(stem, {}).get("done"):
            continue                                          # completed cell -> reuse its tally
        cell_dir = run_dir / stem
        if cell_dir.exists():                                 # incomplete/stale -> re-run fresh
            import shutil
            shutil.rmtree(cell_dir)
        cell_dir.mkdir(parents=True)
        arm = arms[w["arm"]]
        opp = baseline if w["kind"] == "h2h" else (
            checkpoints[w["opponent"]] if w["kind"] == "checkpoint" else opponents[w["opponent"]])
        n = h2h_n if w["kind"] == "h2h" else per_cell
        result = run_cell(arm["dir"], opp["dir"], arm["deck"], opp["deck"], n, film_dir=cell_dir,
                          extra_syspath=extra_syspath, run_id=run_id, stem=stem,
                          arm_overlay=arm["overlay"], opp_overlay=opp["overlay"],
                          arm_label=w["arm"], opp_label=str(w["opponent"]))
        cells[stem] = {"arm": w["arm"], "opponent": w["opponent"], "kind": w["kind"],
                       "done": True, "result": result}
        manifest["totals"]["games"] += sum(s["n"] for s in result["by_seat"].values())
        manifest["totals"]["bytes"] += result["bytes"]
        _flush(manifest, manifest_path)                       # flush per cell -> lose at most one cell

    if manifest["status"] != "capped":
        manifest["status"] = "complete"
    _flush(manifest, manifest_path)

    report = _assemble(manifest, opponents, checkpoints, git_rev=git_rev, created_at=created_at,
                       strata_agent=candidate.get("agent"), n_planned=len(work))
    (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _assemble(manifest: dict, opponents: dict, checkpoints: dict, *, git_rev, created_at,
              strata_agent, n_planned) -> dict:
    """Per-cell tallies -> the C3 report. Navigates cells by their STORED ``(kind, arm, opponent)``,
    never by re-deriving stems."""
    from sim.eval_aivat import aivat
    from sim.eval_report import build_report

    cells = manifest["cells"]
    results = {(v["kind"], v["arm"], v["opponent"]): v["result"]
               for v in cells.values() if v.get("result")}

    matchups, films_meta = [], []
    for opp in opponents:
        cand, base = results.get(("matchup", "candidate", opp)), results.get(("matchup", "baseline", opp))
        if cand and base:
            matchups.extend(_matchup_rows(cand, base, opp))
        for arm_name, res in (("candidate", cand), ("baseline", base)):
            for fm in (res or {}).get("films", []):
                films_meta.append({**fm, "arm": arm_name, "opponent": opp})

    checkpoint_cells = []
    for ck in checkpoints:
        cand = results.get(("checkpoint", "candidate", ck))
        base = results.get(("checkpoint", "baseline", ck))
        if not (cand and base):
            continue
        cand_n = sum(s["n"] for s in cand["by_seat"].values())
        base_n = sum(s["n"] for s in base["by_seat"].values())
        checkpoint_cells.append({
            "build_id": ck, "candidate_wins": sum(s["wins"] for s in cand["by_seat"].values()),
            "candidate_n": cand_n, "baseline_wins": sum(s["wins"] for s in base["by_seat"].values()),
            "baseline_n": base_n})
        for arm_name, res in (("candidate", cand), ("baseline", base)):
            for fm in res.get("films", []):
                films_meta.append({**fm, "arm": arm_name, "opponent": f"ck{ck}"})

    h2h_res = results.get(("h2h", "candidate", "h2h"))
    h2h_rows = []
    if h2h_res:
        for s in ("0", "1"):
            c = h2h_res["by_seat"][s]
            if c["n"] == 0:
                continue
            h2h_rows.append({"opponent": "h2h", "seat": int(s), "n": c["n"],
                             "candidate_wins": c["wins"],
                             "baseline_wins": c["n"] - c["wins"] - c["draws"], "draws": c["draws"]})

    candidate_crashes = sum(v["result"]["crashes"] for v in cells.values()
                            if v.get("arm") == "candidate" and v.get("result"))
    strata = _strata(films_meta, agent=strata_agent)
    coverage = {"cells_planned": n_planned, "cells_done": sum(1 for v in cells.values() if v.get("done")),
                "opponents": len(opponents)}

    return build_report(
        baseline=manifest["baseline"], candidate=manifest["candidate"],
        matchups=matchups, h2h=h2h_rows, checkpoints=checkpoint_cells, strata=strata,
        aivat=aivat(films_meta, None), candidate_crashes=candidate_crashes, git_rev=git_rev,
        generated_at=created_at, preset=manifest.get("preset", ""),
        per_cell_n=manifest.get("per_cell", 0), status=manifest["status"], coverage=coverage)


def _descriptor(row: dict, label: str, config) -> dict:
    """The frozen C3 contestant descriptor ``{agent, label, config}``. ``config`` is the overlay's
    BASENAME, never a machine-specific absolute path."""
    return {"agent": row.get("agent", label), "label": row.get("label", label), "config": config}


def _resolve_spec(spec, rows, *, agents_root, out, into):
    """A ``battle.resolve`` contestant -> a resolved-spec dict. A relative ``@overlay.json`` resolves
    against the CWD (like `battle.py`), NOT the bundle dir, which may be an ephemeral tempdir."""
    from pathlib import Path

    from sim.battle import parse_spec, read_deck, resolve
    base, overlay = parse_spec(spec)
    row, bundle = resolve(base, rows, agents_root=agents_root, out=out, into=into)
    overlay_path = str(Path(overlay).resolve()) if overlay else None
    config = Path(overlay).name if overlay else None
    return {"label": base, "dir": bundle, "deck": read_deck(bundle), "overlay": overlay_path,
            "agent": row.get("agent", base), "descriptor": _descriptor(row, base, config)}


def _resolve_checkpoint(entry: dict, *, out, into):
    """Resolve a checkpoint from the HISTORY row's own artifact zip — NOT by re-looking-up the
    submission id in the local builds ledger, whose id space can diverge on a fresh clone."""
    from sim.battle import _bundle_dir, read_deck
    row = {"submission_id": entry["submission_id"], "agent": entry.get("agent"),
           "artifact": entry["artifact"], "label": "checkpoint"}
    bundle = _bundle_dir(row, out=out, into=into)
    return {"label": str(entry["submission_id"]), "dir": bundle, "deck": read_deck(bundle),
            "overlay": None, "agent": entry.get("agent"),
            "descriptor": _descriptor(row, str(entry["submission_id"]), None)}


def main(argv=None) -> int:
    import argparse
    import json
    import tempfile
    from datetime import datetime, timezone
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    import sys
    sys.path[:0] = [str(repo / "tools"), str(repo / "src")]
    from sim.battle import _git_short
    from sim.eval_report import checkpoint_pool
    from submit.build import DEFAULT_BUILDS, DEFAULT_HISTORY, DEFAULT_OUT
    from submit.history import read_history

    ap = argparse.ArgumentParser(
        description="Eval harness (ADR-0053 WP2): common-opponent paired eval of a candidate vs a "
                    "baseline, emitting the C3 report G2 reads. See "
                    "docs/plans/ml/ml-training-build.md.")
    ap.add_argument("candidate", help="candidate spec: agent name / build id / spec@overlay.json")
    ap.add_argument("baseline", help="baseline spec: agent name / build id / spec@overlay.json")
    ap.add_argument("--opponents", nargs="*", default=None,
                    help="opponent field (default: all working-tree agents)")
    ap.add_argument("--preset", default=DEFAULT_PRESET, choices=sorted(PRESETS),
                    help="power preset (detectable win-delta): quick 5%%, default 3%%, fine 2%%")
    ap.add_argument("--per-cell", type=int, default=None,
                    help="games per arm per opponent (default: derived from the preset)")
    ap.add_argument("--h2h", type=int, default=200,
                    help="informational head-to-head games (0 to skip); never enters the verdict")
    ap.add_argument("--checkpoints", nargs="*", type=int, default=[],
                    help="ADDITIONAL build ids to pin into the checkpoint pool (added, not restricted)")
    ap.add_argument("--no-checkpoints", action="store_true",
                    help="skip the submitted-build checkpoint pool entirely")
    ap.add_argument("--max-games", type=int, default=None, help="hard game cap (disk safety valve)")
    ap.add_argument("--max-gb", type=float, default=None, help="hard film-bytes cap in GB")
    ap.add_argument("--resume", default=None, help="run_id to continue (cell-granular resume)")
    ap.add_argument("--out", default=str(repo / "reports"),
                    help="report root (run lands under <out>/eval/<run_id>/)")
    ap.add_argument("--builds", default=str(DEFAULT_BUILDS), help="the Build Ledger")
    ap.add_argument("--history", default=str(DEFAULT_HISTORY), help="submitted-build history")
    ap.add_argument("--agents-root", default=str(repo / "src" / "agents"))
    args = ap.parse_args(argv)

    rows = read_history(args.builds)
    opponents_names = args.opponents
    if opponents_names is None:
        opponents_names = sorted(p.parent.name for p in
                                 (repo / "src" / "agents").glob("*/main.py"))
    if not opponents_names:
        print("error: no opponents (pass --opponents, or populate src/agents/*/main.py)")
        return 1

    if args.per_cell is not None and args.per_cell <= 0:
        print("error: --per-cell must be positive")
        return 1
    delta = preset_delta(args.preset)
    per_cell = (args.per_cell if args.per_cell is not None
                else games_per_matchup(per_arm_games(delta), len(opponents_names)))
    git_rev = _git_short()
    when = datetime.now(timezone.utc)
    run_id = args.resume or f"{when:%Y%m%d-%H%M%S}_{git_rev}"

    caps = {}
    if args.max_games is not None:
        caps["max_games"] = args.max_games
    if args.max_gb is not None:
        caps["max_bytes"] = int(args.max_gb * 1024**3)

    with tempfile.TemporaryDirectory() as tmp:
        into, out_builds = Path(tmp), Path(DEFAULT_OUT)
        try:
            candidate = _resolve_spec(args.candidate, rows, agents_root=args.agents_root,
                                      out=out_builds, into=into)
            baseline = _resolve_spec(args.baseline, rows, agents_root=args.agents_root,
                                     out=out_builds, into=into)
            opponents = {name: _resolve_spec(name, rows, agents_root=args.agents_root,
                                             out=out_builds, into=into)
                         for name in opponents_names}
        except (ValueError, FileNotFoundError, OSError) as e:
            print(f"error resolving contestants: {e}")
            return 1

        checkpoints = {}
        if not args.no_checkpoints:
            available = {p.stem for p in out_builds.glob("*.zip")}
            pool, warnings = checkpoint_pool(read_history(args.history), available,
                                             extra_ids=args.checkpoints)
            for w in warnings:
                print(f"  checkpoint: {w}")
            for entry in pool:
                try:
                    checkpoints[entry["submission_id"]] = _resolve_checkpoint(
                        entry, out=out_builds, into=into)
                except (FileNotFoundError, OSError, ValueError) as e:
                    print(f"  checkpoint #{entry['submission_id']}: {e} — skipped")

        report = run_eval(
            run_id=run_id, created_at=when.isoformat(), git_rev=git_rev, candidate=candidate,
            baseline=baseline, opponents=opponents, out_root=Path(args.out), per_cell=per_cell,
            checkpoints=checkpoints, h2h_n=args.h2h, caps=caps, extra_syspath=[repo / "src"],
            resume=bool(args.resume), preset=args.preset)

    run_dir = Path(args.out) / EVAL_DIRNAME / run_id
    pd = report["paired_delta"]
    tag = "" if report["status"] == "complete" else f"  [{report['status'].upper()}]"
    print(f"eval {run_id}: {args.candidate} vs {args.baseline} over {len(opponents_names)} opponents "
          f"@ {per_cell}/cell{tag}")
    print(f"  win-delta {pd['win_delta'] * 100:+.1f}%  (95% CI {pd['ci_low'] * 100:+.1f}"
          f"..{pd['ci_high'] * 100:+.1f}%)  -> VERDICT: {report['verdict'].upper()}")
    if report["regressions"]:
        print(f"  checkpoint regressions: {[r['build_id'] for r in report['regressions']]}")
    print(f"  report -> {run_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
