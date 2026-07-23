"""The labeler CLI: the emission gate (§D4) and an end-to-end review run over the fixture corpus."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

MODEL = REPO / "src" / "common" / "value" / "value_model.json"


@pytest.mark.req("REQ-LABEL-0007")
def test_gate_review_allows_theta_override():
    from train.label.run import resolve_gate

    g = resolve_gate("review", thresholds=None, theta_arg=0.07, theta_triage_arg=None)
    assert g["emit"] is True and g["theta"] == 0.07


@pytest.mark.req("REQ-LABEL-0007")
def test_gate_emit_without_thresholds_is_failsafe_report_only():
    from train.label.run import resolve_gate

    g = resolve_gate("emit", thresholds=None, theta_arg=None, theta_triage_arg=None)
    assert g["emit"] is False and "thresholds" in g["reason"]      # nothing written without a reviewed θ


@pytest.mark.req("REQ-LABEL-0007")
def test_gate_emit_uses_committed_theta_and_rejects_override():
    from train.label.run import resolve_gate

    thr = {"theta": 0.22, "theta_triage": 0.04}
    g = resolve_gate("emit", thresholds=thr, theta_arg=None, theta_triage_arg=None)
    assert g["emit"] is True and g["theta"] == 0.22 and g["theta_triage"] == 0.04
    with pytest.raises(ValueError):
        resolve_gate("emit", thresholds=thr, theta_arg=0.1, theta_triage_arg=None)   # override banned


@pytest.mark.req("REQ-LABEL-0007")
def test_null_model_fails_loud(tmp_path):
    from train.label.run import run_label

    with pytest.raises(ValueError):
        run_label([], REPO / "no_such_model.json", mode="review", out_dir=tmp_path,
                  reports_dir=tmp_path)


@pytest.mark.req("REQ-LABEL-0007")
def test_review_run_end_to_end_writes_store_manifest_and_report(corpus_films, ms_pilot, tmp_path):
    """A review run over the real fixture corpus writes a valid machine store (loadable, all
    provenance=machine), a mode=review manifest, and a played-well-lost report."""
    from train.blunder.store import load_corrections
    from train.label.run import run_label

    out = tmp_path / "machine"
    reports = tmp_path / "reports"
    summary = run_label(corpus_films, MODEL, mode="review", theta=0.0, theta_triage=0.03,
                        out_dir=out, reports_dir=reports, run_id="t_review",
                        get_pilot=lambda _a: ms_pilot)

    assert summary["store_written"] is True and summary["gate"]["emit"] is True
    corrs = load_corrections(out / "corrections.jsonl")
    assert all(c.provenance == "machine" and c.category == "value_delta" and c.source == "own"
               for c in corrs)

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "review" and manifest["choice_provider"] == "recorded"
    assert manifest["model"]["sha256"] and manifest["theta"] == 0.0

    pwl = json.loads((reports / "t_review.json").read_text(encoding="utf-8"))
    assert "assessments" in pwl and "aggregate" in pwl


@pytest.mark.req("REQ-LABEL-0007")
def test_emit_mode_failsafe_writes_no_store(corpus_films, ms_pilot, tmp_path):
    """With no committed thresholds.json, emit mode writes the report but NO corrections (fail-safe)."""
    from train.label.run import run_label

    out = tmp_path / "machine"
    summary = run_label(corpus_films, MODEL, mode="emit", out_dir=out, reports_dir=tmp_path / "r",
                        run_id="t_emit", get_pilot=lambda _a: ms_pilot)
    assert summary["store_written"] is False and summary["gate"]["emit"] is False
    assert not (out / "corrections.jsonl").exists()
