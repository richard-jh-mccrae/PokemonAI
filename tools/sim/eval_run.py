"""Eval harness (ADR-0053 WP2, design LOCKED in docs/plans/ml/ml-training-design-s2b.md).

The offline instrument G2 is measured on: a candidate contestant vs a baseline contestant,
each an arbitrary `battle.py` spec, compared **common-opponent** (both arms play the SAME
opponent field, seat schedule, and games-per-cell) — never head-to-head as the measurement,
the protocol the research verifies as misleading (Hearthstone c5-vs-b4, AlphaStar's ~3M
rock-paper-scissors cycles). The paired on−off difference subtracts out the raw deck matchup,
leaving only the candidate-vs-baseline effect (`sim.paired_ab`).

This module owns the run: the power math + cell plan (pure, below), and the live matrix runner
+ CLI (imports the engine lazily inside the functions that need it, like `corpus.py`, so the
pure planning atoms stay stdlib-only and import-cheap). The C3 report itself is assembled by
`sim.eval_report`; strata by `sim.eval_strata`; the AIVAT seam by `sim.eval_aivat`; the
duplicate-position spike by `sim.eval_spike`.
"""
from __future__ import annotations

# z_{0.025} (1.96, 95% two-sided confidence) + z_{0.20} (0.84, 80% power) — the standard
# "detect a difference of size d" constant. Per-arm games scale as (z/d)².
_Z_POWER = 2.80

# Detectable win-rate delta per preset (the sensitivity a standard run is powered for).
PRESETS = {"quick": 0.05, "default": 0.03, "fine": 0.02}
DEFAULT_PRESET = "default"


def per_arm_games(delta: float) -> int:
    """Total games ONE arm plays across all its matchup cells to detect a win-rate difference of
    ``delta`` at 95% confidence / 80% power: ``n = 0.5·(z/d)²`` (the two arms share the field, so
    the paired contrast needs ~half the naive per-proportion N). Quick(5%)≈1568, default(3%)≈4356,
    fine(2%)≈9800 — matched to the design table. Raises on a non-positive delta."""
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
    """The paired matchup cells, one per ``(opponent, seat)`` — each played by BOTH arms so the
    per-cell candidate−baseline delta subtracts out the raw deck matchup. The candidate's own deck
    appearing in ``opponents`` is the mirror cell (self-matchup regressions); the direct
    candidate-vs-baseline head-to-head is a SEPARATE informational block, never a cell here."""
    return [{"opponent": o, "seat": s} for o in opponents for s in (0, 1)]


# ---- the live runner (covered by a live fixture test; the planning atoms above are unit-tested) --

EVAL_DIRNAME = "eval"
MANIFEST_VERSION = 1
_MANIFEST_FLUSH_EVERY = 4


def _flush(manifest: dict, path) -> None:
    import json
    from pathlib import Path
    Path(path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def run_cell(arm_dir, opp_dir, arm_deck, opp_deck, n, *, film_dir=None, extra_syspath=(),
             run_id: str = "", stem: str = "", start_index: int = 0) -> dict:
    """Run ``n`` seat-balanced games of one ARM (candidate or baseline) vs one opponent, the arm as
    contestant A alternating engine seats (ADR-0021). Captures a clean-game film per game into
    ``film_dir`` (crashed games are skipped from the film corpus, as in ``corpus.py``). Returns
    ``{by_seat: {0/1: {n, wins, draws}}, crashes, films: [{path, seat, won}]}`` — ``wins``/``won``
    are the ARM's, ``crashes`` the arm's crash count (a crashed arm game is a loss AND a flag)."""
    import gzip
    import json
    from pathlib import Path

    from sim.battle import AgentServer, play_match, seat_plan, to_battle_match
    from sim.corpus import film_name
    from sim.record import MatchRecorder
    from sim.selfplay import episode_id

    by_seat = {0: {"n": 0, "wins": 0, "draws": 0}, 1: {"n": 0, "wins": 0, "draws": 0}}
    crashes = 0
    films: list[dict] = []
    idx = start_index
    sa = AgentServer(arm_dir, extra_syspath)
    sb = AgentServer(opp_dir, extra_syspath)
    try:
        for a_seat in seat_plan(n):
            if not sa.alive():
                sa = AgentServer(arm_dir, extra_syspath)
            if not sb.alive():
                sb = AgentServer(opp_dir, extra_syspath)
            rec = MatchRecorder() if film_dir else None
            if a_seat == 0:
                res = play_match(sa, sb, arm_deck, opp_deck, recorder=rec)
            else:                                            # arm sits in engine seat 1
                res = play_match(sb, sa, opp_deck, arm_deck, recorder=rec)
            bm = to_battle_match(a_seat, res)
            cell = by_seat[a_seat]
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
                names = [f"{stem}#{'cand' if a_seat == 0 else 'opp'}",
                         f"{stem}#{'opp' if a_seat == 0 else 'cand'}"]
                with gzip.open(path, "wt", encoding="utf-8") as fh:
                    json.dump(rec.replay(episode_id=eid, team_names=names), fh, ensure_ascii=False)
                films.append({"path": str(path), "seat": a_seat,
                              "won": bm.winner == 0})       # the arm's result at this seat
                idx += 1
    finally:
        sa.close()
        sb.close()
    return {"by_seat": by_seat, "crashes": crashes, "films": films}


def _cell_stem(arm: str, opponent: str) -> str:
    return f"{arm}__{opponent}"


def _seat_bucket(by_seat: dict, s: int) -> dict:
    """One seat's ``{n, wins, draws}`` — tolerant of int keys (a fresh run) or str keys (a run
    reloaded from the manifest, where JSON stringified the seat index)."""
    return by_seat[s] if s in by_seat else by_seat[str(s)]


def _matchup_rows(cand_cell: dict, base_cell: dict, opponent: str) -> list[dict]:
    """Two C3 matchup rows (seat 0, seat 1) pairing the candidate arm's and baseline arm's results
    vs the same opponent — the common-opponent paired contrast, per seat (ADR-0021 audit kept)."""
    rows = []
    for s in (0, 1):
        c, b = _seat_bucket(cand_cell["by_seat"], s), _seat_bucket(base_cell["by_seat"], s)
        n = min(c["n"], b["n"])
        if n == 0:
            continue                                          # a seat with no paired games isn't a cell
        rows.append({"opponent": opponent, "seat": s, "n": n,
                     "candidate_wins": c["wins"], "baseline_wins": b["wins"],
                     "draws": c["draws"]})
    return rows


def _work_list(opponents: dict, checkpoints: dict, *, do_h2h: bool) -> list[dict]:
    """The ordered cell work-list: both arms vs every opponent, both arms vs every checkpoint, and
    (optionally) the candidate-arm head-to-head vs the baseline. Each entry names the arm it runs,
    the opponent key, and its kind (``matchup``/``checkpoint``/``h2h``)."""
    work = []
    for opp in opponents:
        for arm in ("candidate", "baseline"):
            work.append({"arm": arm, "opponent": opp, "kind": "matchup",
                         "stem": _cell_stem(arm, opp)})
    for ck in checkpoints:
        for arm in ("candidate", "baseline"):
            work.append({"arm": arm, "opponent": ck, "kind": "checkpoint",
                         "stem": _cell_stem(arm, f"ck{ck}")})
    if do_h2h:
        work.append({"arm": "candidate", "opponent": "h2h", "kind": "h2h",
                     "stem": _cell_stem("candidate", "h2h")})
    return work


def _strata(films_meta: list, *, agent: str | None, extra_syspath) -> list[dict]:
    """Best-effort C3 strata over the clean eval films: value-swing sensitivity per game (the
    committed seed model over the candidate agent's `_board`), median-split into high/low-swing.
    Returns ``[]`` if no agent pilot is available or no film scores — the block is optional (C3
    allows ``strata: []``); it upgrades for free when a better value model ships."""
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
            sens = game_sensitivity(pilot, model, load_replay(fm["path"]))
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
             strata_agent: str | None = None, resume: bool = False, preset: str = "") -> dict:
    """Run the common-opponent matrix and write ``<out_root>/eval/<run_id>/`` (corpus-pattern:
    manifest header + gzip films + resume + caps), returning the C3 report (also written to
    ``report.json``). ``candidate``/``baseline`` are ``{label, dir, deck}``; ``opponents`` and
    ``checkpoints`` map a key to ``{dir, deck, ...}``. Resume is cell-granular: a completed cell's
    tally is reused from the manifest; an incomplete cell is re-run fresh."""
    import json
    from pathlib import Path

    from sim.corpus import cap_hit

    checkpoints = checkpoints or {}
    caps = caps or {}
    arms = {"candidate": candidate, "baseline": baseline}
    run_dir = Path(out_root) / EVAL_DIRNAME / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"

    work = _work_list(opponents, checkpoints, do_h2h=h2h_n > 0)
    if resume and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "running"
    else:
        manifest = {
            "manifest_version": MANIFEST_VERSION, "run_id": run_id, "created_at": created_at,
            "git_rev": git_rev, "candidate": candidate.get("label", candidate.get("dir")),
            "baseline": baseline.get("label", baseline.get("dir")),
            "opponents": list(opponents), "checkpoints": list(checkpoints), "preset": preset,
            "per_cell": per_cell, "h2h_n": h2h_n, "caps": caps, "cells": {},
            "status": "running", "totals": {"games": 0},
        }
    cells = manifest["cells"]
    flushed = 0

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
        result = run_cell(arm["dir"], opp["dir"], arm["deck"], opp["deck"], n,
                          film_dir=cell_dir, extra_syspath=extra_syspath, run_id=run_id, stem=stem)
        cells[stem] = {"arm": w["arm"], "opponent": w["opponent"], "kind": w["kind"],
                       "done": True, "result": result}
        manifest["totals"]["games"] += sum(s["n"] for s in result["by_seat"].values())
        flushed += 1
        if flushed >= _MANIFEST_FLUSH_EVERY:
            _flush(manifest, manifest_path)
            flushed = 0

    if manifest["status"] != "capped":
        manifest["status"] = "complete"
    _flush(manifest, manifest_path)

    report = _assemble(manifest, candidate, baseline, opponents, checkpoints,
                       git_rev=git_rev, created_at=created_at, preset=preset, per_cell=per_cell,
                       strata_agent=strata_agent, extra_syspath=extra_syspath)
    (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _assemble(manifest: dict, candidate: dict, baseline: dict, opponents: dict, checkpoints: dict,
              *, git_rev, created_at, preset, per_cell, strata_agent, extra_syspath) -> dict:
    """Turn the run's per-cell tallies into the C3 report: paired matchup rows, the informational
    H2H block, checkpoint cells (regression tripwire), strata, and the verdict."""
    from sim.eval_aivat import aivat
    from sim.eval_report import build_report

    cells = manifest["cells"]

    def cell(arm, opp):
        return cells.get(_cell_stem(arm, opp), {}).get("result")

    matchups, films_meta = [], []
    for opp in opponents:
        cand, base = cell("candidate", opp), cell("baseline", opp)
        if cand and base:
            matchups.extend(_matchup_rows(cand, base, opp))
        for arm_name, res in (("candidate", cand), ("baseline", base)):
            for fm in (res or {}).get("films", []):
                films_meta.append({**fm, "arm": arm_name, "opponent": opp})

    checkpoint_cells = []
    for ck in checkpoints:
        cand = cell("candidate", f"ck{ck}")
        base = cell("baseline", f"ck{ck}")
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

    h2h_res = cell("candidate", "h2h")
    h2h_rows = []
    if h2h_res:
        for s in (0, 1):
            c = _seat_bucket(h2h_res["by_seat"], s)
            h2h_rows.append({"opponent": "h2h", "seat": s, "n": c["n"],
                             "candidate_wins": c["wins"], "baseline_wins": c["n"] - c["wins"]
                             - c["draws"], "draws": c["draws"]})

    candidate_crashes = sum(v["result"]["crashes"] for v in cells.values()
                            if v.get("arm") == "candidate" and v.get("result"))
    strata = _strata(films_meta, agent=strata_agent, extra_syspath=extra_syspath)

    return build_report(
        baseline=baseline.get("label_row", {"agent": baseline.get("label")}),
        candidate=candidate.get("label_row", {"agent": candidate.get("label")}),
        matchups=matchups, h2h=h2h_rows, checkpoints=checkpoint_cells, strata=strata,
        aivat=aivat(films_meta, None), candidate_crashes=candidate_crashes, git_rev=git_rev,
        generated_at=created_at, preset=preset, per_cell_n=per_cell)


def _resolve_spec(spec, rows, *, agents_root, out, into):
    """A ``battle.resolve`` contestant -> ``{label, dir, deck, label_row}``: a name is a working-tree
    agent, a digit is a Build-Ledger zip extracted under ``into`` (arbitrary-spec pairing, D1)."""
    from sim.battle import parse_spec, read_deck, resolve
    base, _overlay = parse_spec(spec)
    row, bundle = resolve(base, rows, agents_root=agents_root, out=out, into=into)
    return {"label": base, "dir": bundle, "deck": read_deck(bundle), "label_row": row}


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
                    "docs/plans/ml/ml-training-design-s2b.md.")
    ap.add_argument("candidate", help="candidate spec: agent name or build id")
    ap.add_argument("baseline", help="baseline spec: agent name or build id")
    ap.add_argument("--opponents", nargs="*", default=None,
                    help="opponent field (default: all working-tree agents)")
    ap.add_argument("--preset", default=DEFAULT_PRESET, choices=sorted(PRESETS),
                    help="power preset (detectable win-delta): quick 5%%, default 3%%, fine 2%%")
    ap.add_argument("--per-cell", type=int, default=None,
                    help="games per arm per opponent (default: derived from the preset)")
    ap.add_argument("--h2h", type=int, default=200,
                    help="informational head-to-head games (0 to skip); never enters the verdict")
    ap.add_argument("--checkpoints", nargs="*", type=int, default=[],
                    help="extra build ids for the frozen-checkpoint regression pool")
    ap.add_argument("--no-checkpoints", action="store_true",
                    help="skip the submitted-build checkpoint pool entirely")
    ap.add_argument("--max-games", type=int, default=None, help="hard game cap (disk safety valve)")
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

    delta = preset_delta(args.preset)
    per_cell = args.per_cell or games_per_matchup(per_arm_games(delta), len(opponents_names))
    git_rev = _git_short()
    when = datetime.now(timezone.utc)
    run_id = f"{when:%Y%m%d-%H%M%S}_{git_rev}"

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
        except ValueError as e:
            print(f"error: {e}")
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
                    checkpoints[entry["submission_id"]] = _resolve_spec(
                        str(entry["submission_id"]), rows, agents_root=args.agents_root,
                        out=out_builds, into=into)
                except ValueError as e:
                    print(f"  checkpoint #{entry['submission_id']}: {e}")

        report = run_eval(
            run_id=run_id, created_at=when.isoformat(), git_rev=git_rev, candidate=candidate,
            baseline=baseline, opponents=opponents, out_root=Path(args.out), per_cell=per_cell,
            checkpoints=checkpoints, h2h_n=args.h2h,
            caps={"max_games": args.max_games} if args.max_games else {},
            extra_syspath=[repo / "src"], strata_agent=candidate["label"], preset=args.preset)

    run_dir = Path(args.out) / EVAL_DIRNAME / run_id
    pd = report["paired_delta"]
    print(f"eval {run_id}: {args.candidate} vs {args.baseline} over {len(opponents_names)} opponents "
          f"@ {per_cell}/cell")
    print(f"  win-delta {pd['win_delta'] * 100:+.1f}%  (95% CI {pd['ci_low'] * 100:+.1f}"
          f"..{pd['ci_high'] * 100:+.1f}%)  -> VERDICT: {report['verdict'].upper()}")
    if report["regressions"]:
        print(f"  checkpoint regressions: {[r['build_id'] for r in report['regressions']]}")
    print(f"  report -> {run_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
