"""The shared agent config loader (common/config): (overrides, params) for the Pilot, with an
optional offline experiment overlay layered over the shipped tuned.json (ADR-0021 amendment)."""
import pytest

from common.config import load_overrides_and_params


@pytest.mark.req("REQ-SIM-0008")
def test_reads_tuned_json_for_overrides_when_no_overlay(tmp_path):
    (tmp_path / "tuned.json").write_text('{"snipe-the-weakest": 15}', encoding="utf-8")
    overrides, params = load_overrides_and_params({"search_budget": 0}, env={}, root=tmp_path)
    assert overrides == {"snipe-the-weakest": 15}     # shipped weights, as today
    assert params == {"search_budget": 0}             # params untouched without an overlay


@pytest.mark.req("REQ-SIM-0008")
def test_overlay_overrides_tuned_weights_and_merges_params(tmp_path):
    (tmp_path / "tuned.json").write_text('{"a": 1, "b": 2}', encoding="utf-8")
    overlay = tmp_path / "exp.json"
    overlay.write_text('{"overrides": {"b": 9, "c": 3}, "params": {"search_budget": 50}}',
                       encoding="utf-8")
    overrides, params = load_overrides_and_params(
        {"search_budget": 0}, env={"AGENT_OVERLAY": str(overlay)}, root=tmp_path)
    assert overrides == {"a": 1, "b": 9, "c": 3}      # overlay wins on b, adds c, keeps a
    assert params == {"search_budget": 50}            # overlay param over Strategy default


@pytest.mark.req("REQ-SIM-0008")
def test_no_tuned_and_no_overlay_is_empty_overrides(tmp_path):
    overrides, params = load_overrides_and_params({"search_budget": 0}, env={}, root=tmp_path)
    assert overrides == {} and params == {"search_budget": 0}   # grader default: nothing to apply
