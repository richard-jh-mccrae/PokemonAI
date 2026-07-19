"""detect + emit — θ-disagreement → machine Corrections (S3a design §D2/§D4).

The labeler IS the disagreement detector (s3b unifies WP3+WP4): where the expert's best option beats
the chosen one by ≥ θ in P(win), emit a machine Correction (source=own, provenance=machine,
category=value_delta) into the gitignored machine store — the same rails every human correction rides.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


def _a_main_decision(replay):
    from train.blunder.decisions import iter_decisions

    for d in iter_decisions(replay):
        if d.select_context == 0 and len(d.options) > 1 and d.chosen:
            return d
    raise AssertionError("no multi-option MAIN decision in the fixture replay")


# --- pure disagreement logic (no engine) ---

@pytest.mark.req("REQ-LABEL-0005")
def test_option_disagreement_fires_only_above_theta_and_when_best_differs():
    from train.label.detect import option_disagreement

    vals = {0: 0.40, 1: 0.75, 2: 0.50}                          # best is option 1
    assert option_disagreement(vals, chosen_index=0, theta=0.20)["correct"] == 1   # ΔV=0.35 ≥ θ
    assert option_disagreement(vals, chosen_index=0, theta=0.40) is None           # ΔV=0.35 < θ
    assert option_disagreement(vals, chosen_index=1, theta=0.0) is None            # chose the best
    assert option_disagreement(vals, chosen_index=9, theta=0.0) is None            # chosen not scored
    d = option_disagreement(vals, chosen_index=2, theta=0.10)
    assert d["chosen"] == 2 and d["correct"] == 1 and d["delta"] == pytest.approx(0.25)


@pytest.mark.req("REQ-LABEL-0005")
def test_a_tie_is_not_a_disagreement_even_at_theta_zero():
    """A chosen option co-equal with the best (ΔV=0) must never flag — else a θ=0 review run emits
    zero-signal 'blunders' where the played move was actually best."""
    from train.label.detect import option_disagreement

    tie = {0: 0.6, 1: 0.6, 2: 0.3}                              # options 0 and 1 tie for best
    assert option_disagreement(tie, chosen_index=0, theta=0.0) is None
    assert option_disagreement(tie, chosen_index=1, theta=0.0) is None


@pytest.mark.req("REQ-LABEL-0005")
def test_recorded_provider_returns_the_played_move(one_replay, ms_pilot):
    from train.label.detect import recorded_choice

    d = _a_main_decision(one_replay)
    assert recorded_choice(ms_pilot, d, d.obs) == d.chosen[0]   # the move the build actually played


# --- emission onto the correction rails ---

@pytest.mark.req("REQ-LABEL-0005")
def test_to_correction_is_a_valid_machine_record(one_replay):
    from train.label.emit import to_correction

    d = _a_main_decision(one_replay)
    chosen, best = d.chosen[0], (d.chosen[0] + 1) % len(d.options)   # force best ≠ chosen
    dis = {"decision": d, "chosen": chosen, "correct": best, "delta": 0.42,
           "v_best": 0.80, "v_chosen": 0.38, "v_table": {chosen: 0.38, best: 0.80}}
    corr = to_correction(dis, agent="mega_starmie")

    assert corr.provenance == "machine"                         # C2: distinguishable from human
    assert corr.source == "own"                                 # flows through tune.py's own-filter
    assert corr.category == "value_delta"
    assert corr.correct == [best] and corr.chosen == [chosen]   # chosen reflects the provider's pick
    assert corr.agent == "mega_starmie"
    assert "CRITICAL" not in corr.rationale                     # never trips the human must-fix marker
    assert corr.is_critical is False


@pytest.mark.req("REQ-LABEL-0005")
def test_machine_store_round_trips_and_passes_the_own_filter(one_replay, tmp_path):
    from train.blunder.store import load_corrections
    from train.label.emit import to_correction, write_machine_store

    d = _a_main_decision(one_replay)
    best = (d.chosen[0] + 1) % len(d.options)
    dis = {"decision": d, "chosen": d.chosen[0], "correct": best, "delta": 0.30,
           "v_best": 0.7, "v_chosen": 0.4, "v_table": {}}
    corr = to_correction(dis, agent="mega_starmie")

    store = tmp_path / "machine" / "corrections.jsonl"
    write_machine_store([corr], dest=store)
    loaded = load_corrections(store)
    assert len(loaded) == 1 and loaded[0].provenance == "machine"
    own = [c for c in loaded if c.source == "own"]               # tune.py:118 filter
    assert own and own[0].category == "value_delta"


@pytest.mark.req("REQ-LABEL-0005")
def test_write_machine_store_is_wholesale_not_append(one_replay, tmp_path):
    """Regenerable artifact: a re-run REPLACES the store (no append-compact, no duplicate blowup)."""
    from train.blunder.store import load_corrections
    from train.label.emit import to_correction, write_machine_store

    d = _a_main_decision(one_replay)
    best = (d.chosen[0] + 1) % len(d.options)
    corr = to_correction({"decision": d, "chosen": d.chosen[0], "correct": best, "delta": 0.3,
                          "v_best": 0.7, "v_chosen": 0.4, "v_table": {}}, agent="mega_starmie")
    store = tmp_path / "machine" / "corrections.jsonl"
    write_machine_store([corr, corr], dest=store)
    write_machine_store([corr], dest=store)                      # re-run
    assert len(load_corrections(store, dedup=False)) == 1        # replaced, not appended


@pytest.mark.req("REQ-LABEL-0005")
def test_detect_over_real_film_yields_wellformed_disagreements(ms_pilot, one_replay, seed_model):
    """End-to-end at θ=0: whatever fires must be structurally sound (best≠chosen, Δ≥0, real Decision)."""
    from train.label.detect import detect_disagreements

    found = list(detect_disagreements(ms_pilot, one_replay, seed_model, theta=0.0))
    for dis in found:
        assert dis["correct"] != dis["chosen"]
        assert dis["delta"] >= 0.0
        assert dis["decision"].select_context == 0              # single-pick MAIN only
        assert dis["agent"] == "mega_starmie"
