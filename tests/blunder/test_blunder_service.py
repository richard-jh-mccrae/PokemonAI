"""The shell's integration glue: labeled-decision payload + record-a-tag."""
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.service import (
    decisions_payload, frames_payload, list_corrections, record_correction,
)
from train.blunder.store import load_corrections

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def test_decisions_payload_has_labeled_options_and_detected_seat():
    """REQ-BLUNDER-0011: the shell payload lists every Decision with human-readable
    option labels + the chosen positions, and detects our seat from the team name."""
    payload = decisions_payload(load_replay(FIXTURE), our_team="keidroid")
    assert payload["seat"] == 1
    decisions = payload["decisions"]
    assert len(decisions) == 43
    main = next(d for d in decisions if d["context"] == "Main")
    assert "End turn" in [o["label"] for o in main["options"]]
    assert main["chosen"] == [2]      # selection from next film frame (offset +1)


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
    assert corr.correct_label == "End turn"                 # auto-labeled via decoder
    assert corr.chosen_label.startswith(("Play", "Attach", "End"))
    loaded = load_corrections(log)
    assert len(loaded) == 1 and loaded[0] == corr


def test_frames_payload_matches_heroz_film_indexing():
    """REQ-BLUNDER-0012: frames_payload enumerates ALL 44 film frames with HEROZ-style
    1-based step numbers (X/44); taggable frames carry options + a Selected-Action label,
    so the pane lines up 1:1 with the colorful viewer's stepper."""
    p = frames_payload(load_replay(FIXTURE), our_team="keidroid")
    assert p["total"] == 44 and len(p["frames"]) == 44

    f1 = p["frames"][0]
    assert f1["step"] == 1 and f1["frame"] == 0          # 1-based step, 0-based film index
    assert p["frames"][-1]["taggable"] is False          # terminal frame isn't taggable

    main = next(f for f in p["frames"] if f["context"] == "Main")
    assert main["taggable"] is True
    assert main["selected_label"]                        # mirrors HEROZ "Selected Action"
    assert any(o["label"] == "End turn" for o in main["options"])
    assert main["frame"] == main["step"] - 1             # POST uses 0-based frame


def test_a_taggable_frame_carries_the_selects_min_count(tmp_path):
    """REQ-BLUNDER-0021: the panel cannot offer a DECLINE it has no way to know is legal. `minCount`
    lives only in the agent `obs`, so the payload carries it — read from the SAME place
    `build_correction` validates against, so the button and the validator can never disagree.

    `None` on an untaggable or obs-less frame is the fail-closed signal, not a default of 0."""
    p = frames_payload(load_replay(FIXTURE))
    main = next(f for f in p["frames"] if f["context"] == "Main")
    assert main["min_count"] == 1                        # this fixture's MAIN select is mandatory
    assert p["frames"][-1]["min_count"] is None          # terminal frame — nothing to establish
    assert all("min_count" in f for f in p["frames"])     # ...the key is never simply absent


def test_list_corrections_filters_by_episode(tmp_path):
    """REQ-BLUNDER-0013: the review list returns this episode's logged Corrections, with ids."""
    log = tmp_path / "c.jsonl"
    replay = load_replay(FIXTURE)
    main = next(d for d in decisions_payload(replay)["decisions"] if d["context"] == "Main")
    record_correction(replay, frame=main["frame"], correct=[4], category="missed_win",
                      rationale="r", source="own", agent="mega_starmie", store_path=log)
    listed = list_corrections(replay, log)
    assert len(listed) == 1
    assert listed[0]["category"] == "missed_win" and listed[0]["id"]
    assert listed[0]["step"] == main["frame"] + 1

