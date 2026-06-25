"""Proposing a new Hypothesis from a missing_hypothesis Correction (assisted authoring)."""
from train.blunder.correction import build_correction
from train.blunder.decisions import Decision
from train.tuner.propose import propose_hypothesis


def _correction():
    options = [{"type": 7}, {"type": 13}]
    dec = Decision(episode_id=99, frame=14, seat=0, turn=2, select_context="Main",
                   select_type="Main", options=options, chosen=[0], current={})
    return build_correction(dec, source="own", agent="mega_starmie", correct=[1],
                            category="missed_win", rationale="had lethal on board, must attack",
                            chosen_label="Play Pokegear 3.0", correct_label="Attack: Hydro Splash")


def test_propose_hypothesis_carries_rationale_seed_and_a_trigger_sketch():
    """REQ-TUNER-0006: a missing_hypothesis Correction yields a proposed Hypothesis — the human
    rationale verbatim, a seed weight in-band, and a trigger sketch naming the two options."""
    p = propose_hypothesis(_correction())
    assert "missed-win" in p.id
    assert p.rationale == "had lethal on board, must attack"
    assert p.seed_weight > 0
    assert "Attack: Hydro Splash" in p.trigger_sketch
    assert "Play Pokegear 3.0" in p.trigger_sketch
