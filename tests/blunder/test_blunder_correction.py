"""Building and validating a Correction from a Decision."""
from copy import deepcopy

import pytest
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.correction import Correction, build_correction
from train.blunder.decisions import iter_decisions

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def _a_main_decision():
    """The first Main decision: frame 5, 5 options, chosen == [1]."""
    return next(d for d in iter_decisions(load_replay(FIXTURE)) if d.select_context == "Main")


def test_build_correction_embeds_snapshot_and_judgment():
    """REQ-BLUNDER-0004: a valid Correction auto-records `chosen`, takes the better
    legal option as `correct`, and embeds the self-contained Decision snapshot."""
    d = _a_main_decision()
    corr = build_correction(
        d, source="own", agent="mega_starmie",
        correct=[4], category="missed_win",          # position 4 (a different legal option)
        rationale="should have passed to keep the attach",
    )
    assert isinstance(corr, Correction)
    assert corr.chosen == d.chosen                    # auto from the replay
    assert corr.correct == [4]
    assert corr.category == "missed_win"
    assert corr.episode_id == d.episode_id and corr.seat == d.seat
    # embedded, self-contained snapshot
    assert corr.decision["select_context"] == "Main"
    assert corr.decision["current"]["players"]        # full board travels along
    assert len(corr.decision["options"]) == len(d.options)
    assert corr.decision["decision_seconds"] == d.decision_seconds


def test_correct_must_be_legal_option_positions():
    """REQ-BLUNDER-0004: `correct` must index real option positions (the film's raw
    `selected` is not a reliable option-position, so we don't compare against it)."""
    d = _a_main_decision()                             # positions 0..4
    with pytest.raises(ValueError):
        build_correction(d, source="own", agent="x", correct=[9],
                         category="missed_win", rationale="r")          # out of range
    with pytest.raises(ValueError):
        build_correction(d, source="own", agent="x", correct=[],
                         category="missed_win", rationale="r")          # empty


def test_correct_must_obey_the_anchor_selection_cardinality():
    d = _a_main_decision()
    assert d.obs["select"]["maxCount"] == 1

    with pytest.raises(ValueError, match="requires 1..1 option"):
        build_correction(d, source="own", agent="x", correct=[0, 4],
                         category="missed_win", rationale="sequence is not one decision")
    with pytest.raises(ValueError, match="duplicate"):
        build_correction(d, source="own", agent="x", correct=[4, 4],
                         category="missed_win", rationale="same option twice")


@pytest.mark.parametrize("missing", ("minCount", "maxCount"))
def test_nonempty_correction_write_requires_both_cardinality_bounds(missing):
    d = _a_main_decision()
    obs = deepcopy(d.obs)
    obs["select"].pop(missing)

    with pytest.raises(ValueError, match=r"requires \?\.\.|\.\.\?"):
        build_correction(
            d, source="own", agent="x", correct=[4], obs=obs,
            category="missed_win", rationale="unknown cardinality")


def test_category_must_be_in_vocab():
    """REQ-BLUNDER-0004: category is validated against the closed vocabulary."""
    d = _a_main_decision()
    with pytest.raises(ValueError):
        build_correction(d, source="own", agent="x", correct=[4],
                         category="missed_lethal", rationale="r")       # renamed away


def test_correction_roundtrips_through_dict():
    """REQ-BLUNDER-0005: a Correction serializes to a plain dict and back,
    preserving identity (source / submission_id / agent_version) and judgment."""
    d = _a_main_decision()
    corr = build_correction(
        d, source="own", agent="mega_starmie",
        submission_id=12345, agent_version="abc1234", episode_time="2026-06-20T10:00:00Z",
        correct=[4], category="overextension", rationale="benched a third attacker for nothing",
    )
    back = Correction.from_dict(corr.to_dict())
    assert back == corr
    assert back.source == "own"
    assert back.submission_id == 12345 and back.agent_version == "abc1234"


def test_peer_source_supported_and_bad_source_rejected():
    """REQ-BLUNDER-0005: `source` is own|peer; peer carries an archetype label, bad source rejected."""
    d = _a_main_decision()
    peer = build_correction(d, source="peer", agent="Cinderace / Dragapult",
                            correct=[4], category="bad_target", rationale="hit the wall")
    assert peer.source == "peer" and peer.agent == "Cinderace / Dragapult"
    with pytest.raises(ValueError):
        build_correction(d, source="enemy", agent="x", correct=[4],
                         category="bad_target", rationale="r")


def test_correction_carries_build_identity():
    """REQ-BLUNDER-0015: a Correction records the agent build it was made against (traceability),
    and it round-trips through the log."""
    d = _a_main_decision()
    corr = build_correction(
        d, source="own", agent="mega_starmie",
        agent_build="mega_starmie_20260625-034931_623a009-dirty",
        agent_version="623a009-dirty", built_at="2026-06-25T03:49:31",
        correct=[4], category="missed_win", rationale="r",
    )
    assert corr.agent_build == "mega_starmie_20260625-034931_623a009-dirty"
    assert corr.agent_version == "623a009-dirty"
    assert corr.built_at == "2026-06-25T03:49:31"
    assert Correction.from_dict(corr.to_dict()) == corr


def test_posture_mismatch_flag_roundtrips_and_defaults_false():
    """ADR-0041: the human's 'opponent read was wrong' verdict rides on the Correction, round-trips
    through the log, and legacy records saved before the field default it to False."""
    d = _a_main_decision()
    flagged = build_correction(d, source="own", agent="mega_starmie", correct=[4],
                               category="bad_target", rationale="vs Mega Lucario ex, snipe Riolu",
                               posture_mismatch=True)
    assert flagged.posture_mismatch is True
    assert Correction.from_dict(flagged.to_dict()).posture_mismatch is True   # survives the JSONL round-trip
    plain = build_correction(d, source="own", agent="x", correct=[4], category="bad_target", rationale="r")
    assert plain.posture_mismatch is False                                    # default off
    legacy = plain.to_dict(); legacy.pop("posture_mismatch")                  # pre-field record
    assert Correction.from_dict(legacy).posture_mismatch is False


def test_provenance_distinguishes_machine_labels_and_defaults_human():
    """Contract C2 (ADR-0053 WP3): `source` stays "own"/"peer" (whose GAME it was), so every
    existing filter is unchanged; a record saved before the field defaults to "human"."""
    d = _a_main_decision()
    machine = build_correction(d, source="own", agent="mega_starmie", correct=[4],
                               category="missed_win", rationale="ΔP(win) 0.31", provenance="machine")
    assert machine.provenance == "machine" and machine.source == "own"        # orthogonal axes
    assert Correction.from_dict(machine.to_dict()).provenance == "machine"     # survives the round-trip
    human = build_correction(d, source="own", agent="x", correct=[4], category="missed_win", rationale="r")
    assert human.provenance == "human"                                        # default
    legacy = human.to_dict(); legacy.pop("provenance")                        # pre-field record
    assert Correction.from_dict(legacy).provenance == "human"                 # old JSONL loads unchanged


def test_corrections_have_unique_ids_and_legacy_records_get_stable_ids():
    """REQ-BLUNDER-0013: every Correction has a unique id; records saved before ids
    existed get a stable, deterministic id on load (so they can be edited/removed)."""
    d = _a_main_decision()
    a = build_correction(d, source="own", agent="x", correct=[4], category="missed_win", rationale="r")
    b = build_correction(d, source="own", agent="x", correct=[4], category="missed_win", rationale="r")
    assert a.id and b.id and a.id != b.id

    legacy = a.to_dict(); legacy.pop("id")                 # simulate pre-id record
    assert Correction.from_dict(dict(legacy)).id == Correction.from_dict(dict(legacy)).id  # stable
    assert Correction.from_dict(dict(legacy)).id           # non-empty
