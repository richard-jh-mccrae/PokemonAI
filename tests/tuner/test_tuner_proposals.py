"""missing_hypothesis proposals are durable: a snapshot file (not just stdout) carrying each
open proposal's source provenance, so the /blunder-buster skill reads it and the committed file
gives a per-build timeline of how the agent's open blunders shrink over time (ADR-0018)."""
import json

from train.blunder.correction import build_correction
from train.blunder.decisions import Decision
from train.tuner.io import write_proposals
from train.tuner.propose import propose_hypothesis

BUILD = "mega_starmie_20260625-034931_623a009-dirty"


def _corr(category="bad_target", frame=28, episode=81785223):
    dec = Decision(episode_id=episode, frame=frame, seat=0, turn=3, select_context="Damage",
                   select_type="Damage", options=[{"type": 7}, {"type": 13}], chosen=[0],
                   current={})
    return build_correction(dec, source="own", agent="mega_starmie", correct=[1],
                            category=category, rationale="snipe the highest-threat benched attacker",
                            chosen_label="Latias ex", correct_label="Clefairy ex",
                            agent_build=BUILD, built_at="2026-06-25T03:49:31")


def test_proposal_carries_source_provenance():
    """REQ-TUNER-0012: a proposal knows which Correction (category/episode/frame) and which build
    produced it — so the snapshot is self-describing and build-traceable."""
    p = propose_hypothesis(_corr())
    assert p.category == "bad_target"
    assert p.episode_id == 81785223
    assert p.frame == 28
    assert p.agent_build == BUILD
    assert p.built_at == "2026-06-25T03:49:31"


def test_write_proposals_snapshot_is_durable_and_traceable(tmp_path):
    """REQ-TUNER-0012: the snapshot records open proposals + skips with provenance and a
    generated_at stamp (overwritten each run; git history is the timeline)."""
    proposals = [propose_hypothesis(_corr())]
    skipped = [(_corr(category="other", frame=32), "tactical")]
    out = write_proposals(tmp_path / "mega_starmie.json", "mega_starmie", proposals, skipped,
                          generated_at="2026-06-25T12:00:00")
    data = json.loads(out.read_text(encoding="utf-8"))

    assert data["deck"] == "mega_starmie"
    assert data["generated_at"] == "2026-06-25T12:00:00"
    assert data["open"][0]["category"] == "bad_target"
    assert data["open"][0]["frame"] == 28
    assert data["open"][0]["seed_weight"] == 20.0
    assert data["open"][0]["agent_build"] == BUILD
    assert data["open"][0]["critical"] is False          # no CRITICAL marker in this rationale
    assert data["skipped"][0] == {"key": "81785223-32", "scope": "decision", "subject": 32,
                                  "episode_id": 81785223, "frame": 32, "reason": "tactical",
                                  "critical": False,
                                  "planner_committed": False, "lethal_locked": False,
                                  "posture_mismatch": False, "believed_archetype": None}


def _corr_posture(mismatch=True):
    """A correction whose live trace carries a Scouting posture (ADR-0041), flagged an opponent-Read
    miss — the shape /blunder-buster routes to the believed archetype's matchup doctrine."""
    dec = Decision(episode_id=81785223, frame=40, seat=0, turn=5, select_context="Damage",
                   select_type="Damage", options=[{"type": 7}, {"type": 13}], chosen=[0], current={})
    return build_correction(dec, source="own", agent="mega_starmie", correct=[1],
                            category="bad_target", rationale="vs Mega Lucario ex, snipe Riolu",
                            chosen_label="Solrock", correct_label="Riolu", agent_build=BUILD,
                            live_trace={"posture": {"cands": [["Mega Lucario ex", 0.9]], "gamma": 0.8}},
                            posture_mismatch=mismatch)


def test_proposal_carries_posture_mismatch_and_believed_archetype(tmp_path):
    """ADR-0041: /blunder-buster routes a posture-flagged correction to the matchup layer, not a weight."""
    p = propose_hypothesis(_corr_posture())
    assert p.posture_mismatch is True
    assert p.believed_archetype == "Mega Lucario ex"

    out = write_proposals(tmp_path / "m.json", "mega_starmie", [p], [(_corr_posture(), "tactical")],
                          generated_at="2026-07-05T00:00:00")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["open"][0]["posture_mismatch"] is True
    assert data["open"][0]["believed_archetype"] == "Mega Lucario ex"
    assert data["skipped"][0]["posture_mismatch"] is True
    assert data["skipped"][0]["believed_archetype"] == "Mega Lucario ex"


def _corr_turn():
    """A Turn Correction (ADR-0049): prose-only, spanning the turn's decisions."""
    dec = Decision(episode_id=81785223, frame=28, seat=1, turn=12, select_context="Main",
                   select_type="Main", options=[{"type": 7}, {"type": 13}], chosen=[0], current={})
    return build_correction(dec, source="own", agent="mega_starmie", correct=[],
                            category="sequencing_error", rationale="develop before attacking",
                            chosen_label="Attack", scope="turn", agent_build=BUILD,
                            span=[{"chosen_label": "Attack"}, {"chosen_label": "End turn"}])


def test_scoped_proposal_carries_its_scope_subject_and_ledger_key(tmp_path):
    """ADR-0049: the `key` is scope-aware, so disposing of a Turn Correction cannot retire the
    Decision Corrections inside that Turn."""
    p = propose_hypothesis(_corr_turn())
    assert p.id == "sequencing-error-81785223-t12"
    assert p.scope == "turn" and p.subject == 12 and p.seat == 1
    assert p.key == "81785223-t12s1"
    assert p.span_len == 2 and p.seed_weight == 0.0
    assert "played: Attack -> End turn" in p.trigger_sketch

    out = write_proposals(tmp_path / "m.json", "mega_starmie", [p], [(_corr(frame=32), "tactical")],
                          generated_at="2026-07-10T00:00:00")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["open"][0]["scope"] == "turn"
    assert data["open"][0]["subject"] == 12
    assert data["open"][0]["key"] == "81785223-t12s1"
    assert data["skipped"][0]["key"] == "81785223-32"        # decision scope: the report id, unchanged
    assert data["skipped"][0]["scope"] == "decision"
