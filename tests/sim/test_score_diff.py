"""score_diff — the behavior-neutrality gate (replay a corpus through the Pilot, diff vs a capture).

The refactor guard behind the fold-into-general work: per-frame per-option SCORES must not move
(mode "scores"), or at minimum the CHOSEN option must not move (mode "choice"). Fired rule IDS are
deliberately NOT compared — folding renames ids without changing scores.
"""
from pathlib import Path

from sim.score_diff import (capture_corpus, corrections_corpus, diff_records, replay_corpus,
                            slim)

REPO = Path(__file__).resolve().parents[2]


def _record(chosen=(0,), scores=(10.0, 5.0), plan="SETUP"):
    return {
        "plan": plan, "tier": 0, "chosen": list(chosen), "margin": 5.0,
        "opts": [{"i": i, "cid": 100 + i, "score": s, "tac": 0.0,
                  "fired": [["some-rule", s]]} for i, s in enumerate(scores)],
        "lethal": None, "planned": None,
    }


# --- diff_records ---------------------------------------------------------

def test_identical_records_diff_clean_in_both_modes():
    a, b = _record(), _record()
    assert diff_records(a, b, mode="scores") == []
    assert diff_records(a, b, mode="choice") == []


def test_renamed_fired_ids_do_not_diff():
    """The fold case: same scores, different rule ids -> clean."""
    a = _record()
    b = _record()
    b["opts"][0]["fired"] = [["renamed-general-rule", 10.0]]
    assert diff_records(a, b, mode="scores") == []


def test_score_shift_flags_in_scores_mode_only_when_choice_holds():
    a = _record(scores=(10.0, 5.0))
    b = _record(scores=(10.0, 6.0))          # same winner, shifted runner-up
    assert diff_records(a, b, mode="scores") != []
    assert diff_records(a, b, mode="choice") == []


def test_chosen_change_flags_in_both_modes():
    a = _record(chosen=(0,))
    b = _record(chosen=(1,))
    assert diff_records(a, b, mode="scores") != []
    assert diff_records(a, b, mode="choice") != []


def test_option_count_change_flags():
    a, b = _record(), _record(scores=(10.0, 5.0, 1.0))
    assert diff_records(a, b, mode="scores") != []


def test_missing_record_flags():
    assert diff_records(_record(), None, mode="scores") != []
    assert diff_records(None, _record(), mode="choice") != []


# --- slim -----------------------------------------------------------------

def test_slim_keeps_comparable_fields_only():
    s = slim(_record())
    assert s["chosen"] == [0]
    assert s["opts"] == [(0, 10.0), (1, 5.0)]
    assert "fired" not in str(s)


# --- corpora --------------------------------------------------------------

def test_corrections_corpus_yields_committed_obs():
    items = list(corrections_corpus(REPO / "data" / "corrections"))
    assert len(items) >= 200                       # the committed correction rounds
    key, obs = items[0]
    assert key.startswith("corr:")
    assert isinstance(obs, dict) and "select" in obs


def test_replay_corpus_walks_decision_frames():
    replay = {
        "info": {"EpisodeId": 42},
        "steps": [[{"visualize": [
            {"select": {"option": [{"type": 1}, {"type": 2}]}, "current": {}},
            {"selected": [0], "obs": {"select": {"option": [{"type": 1}, {"type": 2}]},
                                      "current": {}, "step": 0},
             "select": None},
        ]}]],
    }
    items = list(replay_corpus([replay]))
    assert len(items) == 1
    key, obs = items[0]
    assert key == "replay:42:0"
    assert "select" in obs


def test_replay_corpus_skips_frames_without_obs_or_selection():
    replay = {"info": {"EpisodeId": 7},
              "steps": [[{"visualize": [
                  {"select": {"option": [{"type": 1}]}, "current": {}},
                  {"selected": None, "obs": None, "select": None},
              ]}]]}
    assert list(replay_corpus([replay])) == []


# --- capture --------------------------------------------------------------

class _StubTrace:
    def __init__(self, index, score):
        from common.strategy import Plan
        self.index, self.score, self.plan = index, score, Plan.SETUP
        self.card_id, self.tactical, self.fired = None, 0.0, []


class _StubPilot:
    def explain(self, obs):
        from common.pilot import Decision
        return Decision(chosen=[0], options=[_StubTrace(0, 12.0), _StubTrace(1, 3.0)])


def test_capture_corpus_records_per_key():
    corpus = [("corr:1:0", {"select": {}}), ("corr:1:1", {"select": {}})]
    cap = capture_corpus(_StubPilot(), corpus)
    assert set(cap) == {"corr:1:0", "corr:1:1"}
    assert cap["corr:1:0"]["chosen"] == [0]
    assert [o["score"] for o in cap["corr:1:0"]["opts"]] == [12.0, 3.0]
