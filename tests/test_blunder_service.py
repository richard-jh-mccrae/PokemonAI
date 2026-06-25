"""The shell's integration glue: labeled-decision payload + record-a-tag."""
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.service import decisions_payload, record_correction
from train.blunder.store import load_corrections

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def test_decisions_payload_has_labeled_options_and_detected_seat():
    """REQ-BLUNDER-0011: the shell payload lists every Decision with human-readable
    option labels + the chosen positions, and detects our seat from the team name."""
    payload = decisions_payload(load_replay(FIXTURE), our_team="keidroid")
    assert payload["seat"] == 1
    decisions = payload["decisions"]
    assert len(decisions) == 42
    main = next(d for d in decisions if d["context"] == "Main")
    assert "End turn" in [o["label"] for o in main["options"]]
    assert main["chosen"] == [1]


def test_record_correction_from_posted_form_appends_labeled_correction(tmp_path):
    """REQ-BLUNDER-0011: a posted tag (frame + correct + category + rationale) becomes a
    validated, auto-labeled Correction appended to the log."""
    log = tmp_path / "c.jsonl"
    replay = load_replay(FIXTURE)
    main = next(d for d in decisions_payload(replay)["decisions"] if d["context"] == "Main")

    corr = record_correction(
        replay, frame=main["frame"], correct=[4], category="missed_win",
        rationale="had lethal on board", source="own", agent="mega_starmie",
        submission_id=123, store_path=log,
    )
    assert corr.category == "missed_win" and corr.correct == [4]
    assert corr.correct_label == "End turn"                 # auto-labeled via the decoder
    assert corr.chosen_label.startswith(("Play", "Attach", "End"))
    loaded = load_corrections(log)
    assert len(loaded) == 1 and loaded[0] == corr
