"""Turn-plan capture: verbatim human evidence plus a deterministic first-divergence grade."""
import pytest

from train.blunder.correction import Correction, build_correction
from train.blunder.decisions import Decision


def _decision(*, frame=9, turn=12, seat=0, episode=100):
    return Decision(episode_id=episode, frame=frame, seat=seat, turn=turn,
                    select_context="Main", select_type="Main",
                    options=[{"type": 12}, {"type": 14}], chosen=[0], current={})


@pytest.mark.req("REQ-BLUNDER-0018")
def test_turn_plan_is_carried_and_round_trips():
    """A planned turn stores verbatim evidence and the exact first divergent menu choices."""
    tp = {"intended_line": " retreat Cinderace, attach {F} to Solrock, KO the Active ",
          "expected_end_board": "Mega Lucario active with 2 {F}, boost line armed"}
    corr = build_correction(_decision(), source="own", agent="mega_lucario", correct=[1],
                            category="sequencing_error", rationale="turn plan", scope="turn",
                            turn_plan=tp)
    assert corr.turn_plan == {
        "schema": "turn-sequence/v1",
        "intended_line": " retreat Cinderace, attach {F} to Solrock, KO the Active ",
        "expected_end_board": "Mega Lucario active with 2 {F}, boost line armed",
        "grade": {
            "status": "mismatch",
            "first_divergence": {
                "frame": 9,
                "expected": [{"position": 1, "option": {"type": 14},
                              "equivalence_fingerprint": None}],
                "observed": [{"position": 0, "option": {"type": 12},
                              "equivalence_fingerprint": None}],
            },
        },
    }
    assert Correction.from_dict(corr.to_dict()).turn_plan == corr.turn_plan


@pytest.mark.req("REQ-BLUNDER-0018")
def test_turn_plan_defaults_none_and_stays_sparse():
    """Sparse invariant: a correction tagged without a turn_plan carries None — legacy records and
    every non-turn-plan tag are byte-identical to the pre-field era."""
    corr = build_correction(_decision(), source="own", agent="x", correct=[1],
                            category="bad_target", rationale="r")
    assert corr.turn_plan is None
    assert Correction.from_dict(corr.to_dict()).turn_plan is None


@pytest.mark.req("REQ-BLUNDER-0018")
def test_legacy_turn_plan_remains_readable():
    """Old prose-only records remain valid evidence; only newly authored plans gain the v1 envelope."""
    corr = build_correction(_decision(), source="own", agent="x", correct=[1],
                            category="sequencing_error", rationale="r")
    record = corr.to_dict()
    record["turn_plan"] = {"intended_line": "attach before attacking", "expected_end_board": "armed"}
    assert Correction.from_dict(record).turn_plan == record["turn_plan"]


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
    recorded = record_correction(replay, frame=5, correct=[1], category="sequencing_error", rationale="tp",
                                 source="own", agent="mega_lucario", store_path=store, scope="turn", turn_plan=tp)
    (stored,) = load_corrections(store)
    assert stored.scope == "turn"
    assert stored.turn_plan == recorded.turn_plan


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
def test_turn_plan_form_keeps_human_evidence_verbatim():
    """Whitespace decides emptiness only; a nonempty ideal line is never rewritten by the shell."""
    from train.blunder.shell import _turn_plan_from_form
    assert _turn_plan_from_form({"scope": "turn", "intended_line": "  attach, then attack  "}) == {
        "intended_line": "  attach, then attack  ", "expected_end_board": ""}


@pytest.mark.req("REQ-BLUNDER-0018")
def test_turn_plan_without_an_anchor_prescription_is_explicitly_ungraded():
    """A prose-only plan cannot invent a divergent action, so its machine grade says ungraded."""
    corr = build_correction(_decision(), source="own", agent="mega_lucario", correct=[],
                            category="sequencing_error", rationale="turn plan", scope="turn",
                            turn_plan={"intended_line": "draw before evolving"})
    assert corr.turn_plan["grade"] == {"status": "ungraded", "first_divergence": None}


@pytest.mark.req("REQ-BLUNDER-0018")
def test_shell_html_exposes_the_turn_plan_fields():
    """The tagging shell renders the two turn-plan inputs and the derived leans-on-rule hint, so the
    human can record an ideal line and see which rule their pick currently fires — without typing it."""
    from train.blunder.shell import _SHELL_HTML
    for token in ("intended_line", "expected_end_board", "turnplan", "firedhint", "turnGrade"):
        assert token in _SHELL_HTML
