"""Turn-plan capture (develop-rung Phase 3, `ADR-0037 (the develop rung it tooled is deleted)`).

A turn-scope Correction can carry the human's ideal-line note — `turn_plan = {intended_line,
expected_end_board}` — so blunder-buster can drive develop-rung rule retirement from it. One sparse,
backward-compatible field: absent on every non-turn-plan correction, so legacy records are unchanged.
"""
import pytest

from train.blunder.correction import Correction, build_correction
from train.blunder.decisions import Decision


def _decision(*, frame=9, turn=12, seat=0, episode=100):
    return Decision(episode_id=episode, frame=frame, seat=seat, turn=turn,
                    select_context="Main", select_type="Main",
                    options=[{"type": 12}, {"type": 14}], chosen=[0], current={})


@pytest.mark.req("REQ-BLUNDER-0018")
def test_turn_plan_is_carried_and_round_trips():
    """A turn-scope Correction carries `turn_plan`, and it survives the to_dict/from_dict round-trip
    (the on-disk JSONL form) unchanged — so a tagged ideal line reaches blunder-buster intact."""
    tp = {"intended_line": "retreat Cinderace, attach {F} to Solrock, KO the Active",
          "expected_end_board": "Mega Lucario active with 2 {F}, boost line armed"}
    corr = build_correction(_decision(), source="own", agent="mega_lucario", correct=[1],
                            category="sequencing_error", rationale="turn plan", scope="turn",
                            turn_plan=tp)
    assert corr.turn_plan == tp
    assert Correction.from_dict(corr.to_dict()).turn_plan == tp


@pytest.mark.req("REQ-BLUNDER-0018")
def test_turn_plan_defaults_none_and_stays_sparse():
    """Sparse invariant: a correction tagged without a turn_plan carries None — legacy records and
    every non-turn-plan tag are byte-identical to the pre-field era."""
    corr = build_correction(_decision(), source="own", agent="x", correct=[1],
                            category="bad_target", rationale="r")
    assert corr.turn_plan is None
    assert Correction.from_dict(corr.to_dict()).turn_plan is None


@pytest.mark.req("REQ-BLUNDER-0018")
def test_record_correction_threads_turn_plan_into_the_store(tmp_path):
    """End-to-end capture: `record_correction` on a turn tag persists the `turn_plan` note, so a
    reload (what blunder-buster reads) sees the ideal-line note intact."""
    from conftest import FIXTURES
    from meta_tracker.parse import load_replay
    from train.blunder.service import record_correction
    from train.blunder.store import load_corrections

    replay = load_replay(FIXTURES / "episode-81364540-replay.json.gz")
    tp = {"intended_line": "attach {F} to Solrock first", "expected_end_board": "boost line armed"}
    store = tmp_path / "corrections.jsonl"
    record_correction(replay, frame=5, correct=[1], category="sequencing_error", rationale="tp",
                      source="own", agent="mega_lucario", store_path=store, scope="turn", turn_plan=tp)
    (stored,) = load_corrections(store)
    assert stored.scope == "turn"
    assert stored.turn_plan == tp


@pytest.mark.req("REQ-BLUNDER-0018")
def test_turn_plan_from_form_builds_only_on_turn_scope_with_content():
    """The shell assembles turn_plan from the form ONLY on a turn tag that has content — a decision tag
    or an empty note yields None, so the field stays sparse and never rides on a non-turn-plan tag."""
    from train.blunder.shell import _turn_plan_from_form
    assert _turn_plan_from_form({"scope": "turn", "intended_line": "retreat then attach",
                                 "expected_end_board": "boost armed"}) == {
        "intended_line": "retreat then attach", "expected_end_board": "boost armed"}
    assert _turn_plan_from_form({"scope": "turn", "intended_line": " ", "expected_end_board": ""}) is None
    assert _turn_plan_from_form({"scope": "decision", "intended_line": "x"}) is None       # wrong scope
    assert _turn_plan_from_form({"scope": "turn", "intended_line": "only the line"}) == {
        "intended_line": "only the line", "expected_end_board": ""}                        # partial ok


@pytest.mark.req("REQ-BLUNDER-0018")
def test_shell_html_exposes_the_turn_plan_fields():
    """The tagging shell renders the two turn-plan inputs and the derived leans-on-rule hint, so the
    human can record an ideal line and see which rule their pick currently fires — without typing it."""
    from train.blunder.shell import _SHELL_HTML
    for token in ("intended_line", "expected_end_board", "turnplan", "firedhint"):
        assert token in _SHELL_HTML
