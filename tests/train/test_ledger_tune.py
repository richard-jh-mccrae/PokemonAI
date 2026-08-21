"""The tuner's adoption gate: keep-best-so-far, and a nudge that breaks ANY previously-right
frame is rejected no matter how much it gains elsewhere."""
from __future__ import annotations

import train.ledger_tune as tune


def _result(agree_ids, miss_ids, deck="a_deck"):
    rows = ([{"deck": deck, "id": rid, "graded": True, "agrees": True} for rid in agree_ids]
            + [{"deck": deck, "id": rid, "graded": True, "agrees": False}
               for rid in miss_ids])
    graded = len(rows)
    return {"rows": rows, "generality_floor": len(agree_ids) / graded if graded else None}


def test_a_gain_that_regresses_one_frame_is_rejected(monkeypatch):
    outcomes = {
        None: _result(["a", "b"], ["c", "d"]),                # baseline: 2 of 4
        0.9: _result(["a", "c", "d"], ["b"]),                 # +1 total but loses "b"
        0.7: _result(["a", "b", "c"], ["d"]),                 # +1 total, keeps everything
    }

    def fake_sweep(*, store, decks, workers, weight_overrides=None):
        key = None if not weight_overrides else weight_overrides["zone.in_hand"]
        return outcomes[key]

    monkeypatch.setattr(tune, "sweep", fake_sweep)
    monkeypatch.setattr(tune.ValuationConfiguration, "with_values",
                        lambda self, replacements: self, raising=True)
    outcome = tune.run(levers={"zone.in_hand": [0.9, 0.7]}, store="unused",
                       decks=("a_deck",), workers=1, log=lambda *_: None)
    assert outcome["adopted"] == {"zone.in_hand": 0.7}
    verdicts = {(t["lever"], t["value"]): t["verdict"] for t in outcome["trials"]}
    assert verdicts[("zone.in_hand", 0.9)] == "rejected"     # the regression gate fired
    assert verdicts[("zone.in_hand", 0.7)] == "ADOPTED"
    assert tune._score(outcome["best"]) == (0.75, 3)


def test_an_unknown_lever_name_fails_before_any_sweep(monkeypatch):
    import pytest

    def exploding_sweep(**_kw):                              # must never be reached
        raise AssertionError("sweep ran before the lever names were validated")

    monkeypatch.setattr(tune, "sweep", exploding_sweep)
    with pytest.raises(KeyError):
        tune.run(levers={"zone.in_hnad": [0.5]}, store="unused", decks=("a_deck",),
                 workers=1, log=lambda *_: None)
