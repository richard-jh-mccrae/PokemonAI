"""The blunder-labeler CLI (S3a design §D3/§D4).

Two production modes plus a report:

- ``--mode review`` — the θ-calibration pass (§D3 step 1): detect at a permissive θ (an explicit
  ``--theta`` is allowed ONLY here), write flags to the machine store with a ``mode: "review"``
  manifest, then a human reviews precision in the blunder shell and commits ``thresholds.json``.
- ``--mode emit`` — the production pass (§D4): **requires** a committed ``thresholds.json`` and uses
  its θ; ``--theta`` is rejected. Per-agent caps apply (largest-|ΔV| first). No thresholds file →
  fail-safe to report-only (nothing written), never a guessed θ.
- ``--mode report`` — the played-well-lost view only (§D6), no corrections.

Every mode also writes the played-well-lost report over the same corpus. Integration (the actual θ
number, mass emit) is G1-gated; until then this is run-ready tooling + a dry-run smoke (§Acceptance).

    python tools/train/label/run.py --replays data/replays/corpus --model src/common/value/value_model.json \
        --mode review --theta 0.05
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.value.model import ValueModel                              # noqa: E402
from meta_tracker.parse import load_replay                             # noqa: E402
from train.label import emit as emitmod                                # noqa: E402
from train.label import report as reportmod                            # noqa: E402
from train.label.detect import detect_disagreements                    # noqa: E402
from train.label.vread import agent_name_for_seat                      # noqa: E402

THRESHOLDS_PATH = Path(__file__).with_name("thresholds.json")
DEFAULT_REVIEW_THETA = 0.05
DEFAULT_THETA_TRIAGE = 0.03
DEFAULT_CAP = 200


def load_thresholds(path: Path | str = THRESHOLDS_PATH) -> dict | None:
    """The committed θ file (§D3 step 5), or None if absent/malformed. The single source both this
    labeler and S3b's detector read, so train and runtime can't disagree on θ."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def resolve_gate(mode: str, thresholds: dict | None, theta_arg, theta_triage_arg) -> dict:
    """The emission gate (§D4). Returns ``{emit, theta, theta_triage, reason}``.

    - ``review``: always writes (calibration); θ = ``--theta`` or the permissive default.
    - ``emit``: requires ``thresholds`` (else ``emit=False``, report-only); ``--theta`` is rejected —
      the production θ comes from the committed file, never the command line.
    - ``report``: never writes corrections.
    """
    if mode == "report":
        return {"emit": False, "theta": None, "theta_triage": theta_triage_arg or DEFAULT_THETA_TRIAGE,
                "reason": "report-only mode"}
    if mode == "review":
        return {"emit": True,
                "theta": theta_arg if theta_arg is not None else DEFAULT_REVIEW_THETA,
                "theta_triage": theta_triage_arg or DEFAULT_THETA_TRIAGE,
                "reason": "review calibration run"}
    if mode == "emit":
        if theta_arg is not None:
            raise ValueError("--theta is only permitted with --mode review; emit uses the committed "
                             "thresholds.json θ (the human-reviewed value).")
        if not thresholds or "theta" not in thresholds:
            return {"emit": False, "theta": None,
                    "theta_triage": theta_triage_arg or DEFAULT_THETA_TRIAGE,
                    "reason": "no committed thresholds.json — fail-safe report-only (run --mode review "
                              "and a human precision review first)"}
        return {"emit": True, "theta": thresholds["theta"],
                "theta_triage": thresholds.get("theta_triage", DEFAULT_THETA_TRIAGE),
                "reason": "emit at committed θ"}
    raise ValueError(f"unknown mode {mode!r}")


def _git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                              capture_output=True, text=True).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except Exception:
        return None


def _pilot_cache():
    from train.tune import _build_pilot

    cache: dict = {}

    def get(agent: str):
        if agent not in cache:
            cache[agent] = _build_pilot(agent)[0]
        return cache[agent]

    return get


def run_label(replays, model_path, *, mode="review", theta=None, theta_triage=None,
              cap=DEFAULT_CAP, choice="recorded", out_dir=None, reports_dir=None,
              run_id=None, get_pilot=None) -> dict:
    """Drive the labeler over ``replays`` (paths). Returns a summary dict; writes the machine store +
    manifest (when the gate emits) and the played-well-lost report."""
    from train.label.detect import recorded_choice, replayed_choice

    model = ValueModel.load(model_path)
    if not model.present:
        raise ValueError(f"value model at {model_path} is null/absent — the labeler needs a trained, "
                         "G1-passed model (offline tools fail loud).")
    thresholds = load_thresholds()
    gate = resolve_gate(mode, thresholds, theta, theta_triage)
    # Played-well-lost confirmation θ: real even when the gate emits nothing (report mode / fail-safe),
    # so a triage hit can be confirmed instead of every loss reading vacuously "clean".
    pwl_theta = gate["theta"] if gate["theta"] is not None else DEFAULT_REVIEW_THETA
    run_id = run_id or datetime.now(timezone.utc).strftime("label-%Y%m%dT%H%M%SZ")
    get_pilot = get_pilot or _pilot_cache()
    chooser = replayed_choice if choice == "replayed" else recorded_choice

    # NOTE (v2 optimization): emission (detect) and the played-well-lost screen (assess) each fork the
    # engine over their frames independently, so overlapping frames are forked twice. Acceptable at the
    # design's frame-sampled scale; share the per-option evaluations if forks become the bottleneck.
    replays = [Path(p) for p in replays]
    per_agent: dict[str, list] = {}
    assessments: list[dict] = []
    for rp in replays:
        replay = load_replay(rp)
        seats = [s for s in (0, 1) if agent_name_for_seat(replay, s) is not None]
        if gate["emit"]:
            for seat in seats:
                agent = agent_name_for_seat(replay, seat)
                pilot = get_pilot(agent)
                for dis in detect_disagreements(pilot, replay, model, gate["theta"],
                                                choose=chooser, seat=seat):
                    per_agent.setdefault(agent, []).append(dis)
        assessments.extend(reportmod.assess_replay(get_pilot, replay, model, pwl_theta,
                                                   gate["theta_triage"]))

    emitted: dict[str, int] = {}
    dropped: dict[str, int] = {}
    corrections = []
    for agent, dis_list in per_agent.items():
        kept, n_dropped = emitmod.cap_by_delta(dis_list, cap)
        emitted[agent], dropped[agent] = len(kept), n_dropped
        corrections.extend(emitmod.to_correction(d, agent=agent) for d in kept)

    machine_dir = Path(out_dir) if out_dir else emitmod.MACHINE_DIR
    store_written = False
    if gate["emit"]:
        emitmod.write_machine_store(corrections, dest=machine_dir / "corrections.jsonl")
        store_written = True
        manifest = {
            "run_id": run_id, "mode": mode, "git_rev": _git_rev(),
            "model": {"path": str(model_path), "sha256": _sha256(Path(model_path)),
                      "meta": getattr(model, "meta", {})},
            "theta": gate["theta"], "theta_triage": gate["theta_triage"],
            "choice_provider": choice, "cap": cap,
            "replays": len(replays), "emitted": emitted, "dropped": dropped,
            "thresholds_present": thresholds is not None,
        }
        emitmod.write_manifest(manifest, dest=machine_dir / "manifest.json")

    reports_dir = Path(reports_dir) if reports_dir else (REPO / "reports" / "played_well_lost")
    reports_dir.mkdir(parents=True, exist_ok=True)
    pwl = {"run_id": run_id, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "theta": pwl_theta, "theta_triage": gate["theta_triage"],
           "assessments": assessments, "aggregate": reportmod.aggregate(assessments)}
    (reports_dir / f"{run_id}.json").write_text(json.dumps(pwl, indent=2, ensure_ascii=False) + "\n",
                                                encoding="utf-8")

    return {"run_id": run_id, "mode": mode, "gate": gate, "store_written": store_written,
            "emitted": emitted, "dropped": dropped, "n_corrections": len(corrections),
            "played_well_lost": len(assessments), "reason": gate["reason"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Automatic blunder labeler (ADR-0053 WP3)")
    ap.add_argument("--replays", nargs="+", required=True,
                    help="corpus film paths or dirs (globbed for *.json.gz)")
    ap.add_argument("--model", default=str(REPO / "src" / "common" / "value" / "value_model.json"))
    ap.add_argument("--mode", choices=("review", "emit", "report"), default="review")
    ap.add_argument("--theta", type=float, default=None, help="review-mode override only")
    ap.add_argument("--theta-triage", type=float, default=None)
    ap.add_argument("--choice", choices=("recorded", "replayed"), default="recorded")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP)
    ap.add_argument("--out-dir", default=None, help="machine store dir (default data/corrections/machine)")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)

    films: list[Path] = []
    for r in args.replays:
        p = Path(r)
        films.extend(sorted(p.rglob("*.json.gz")) if p.is_dir() else [p])
    if not films:
        print("no replay films found", file=sys.stderr)
        return 2

    summary = run_label(films, args.model, mode=args.mode, theta=args.theta,
                        theta_triage=args.theta_triage, choice=args.choice, cap=args.cap,
                        out_dir=args.out_dir, run_id=args.run_id)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not summary["gate"]["emit"] and args.mode == "emit":
        print(f"\n[fail-safe] {summary['reason']} — no corrections written.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
