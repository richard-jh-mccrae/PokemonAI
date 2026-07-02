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
    assert data["skipped"][0] == {"episode_id": 81785223, "frame": 32, "reason": "tactical",
                                  "critical": False,
                                  "planner_committed": False, "lethal_locked": False}
