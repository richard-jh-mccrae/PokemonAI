"""Engine-backed ideal-turn recording and proved adjacent-action commutativity."""
from __future__ import annotations

import gzip
import json
from copy import deepcopy

from train.blunder.counterfactual import (CounterfactualRecorder, choice_reference,
                                          grade_counterfactual, resolve_choice)


class _FakeEngine:
    def __init__(self, *, legal, done=()):
        self.legal = legal
        self.done = tuple(done)


class _FakeBackend:
    name = "fake"

    def fork(self, engine):
        return deepcopy(engine)

    def observation(self, engine, seat):
        offered = [a for a in engine.legal(engine.done) if a not in engine.done]
        select = ({"context": 0, "type": 0, "minCount": 1, "maxCount": 1,
                   "option": [{"type": 7, "action": action} for action in offered]}
                  if offered else None)
        return {"current": {"yourIndex": seat, "turn": 1, "result": -1, "players": [{}, {}]},
                "select": select}

    def step(self, engine, choice):
        obs = self.observation(engine, 0)
        action = obs["select"]["option"][choice[0]]["action"]
        engine.done += (action,)

    def signature(self, engine, seat):
        return json.dumps(sorted(engine.done))

    def randomness(self, engine):
        return ()


class _RandomFakeBackend(_FakeBackend):
    def randomness(self, engine):
        return (("shuffle", 0),) if "shuffle" in engine.done else ()


def _choose(recorder, action):
    view = recorder.view()
    pos = next(row["position"] for row in view["options"] if row["option"]["action"] == action)
    recorder.choose([pos])


def test_independent_actions_are_proved_commutative_by_both_execution_orders():
    rec = CounterfactualRecorder(_FakeEngine(legal=lambda _done: ("attach", "evolve")),
                                 _FakeBackend(), seat=0, turn=1)
    _choose(rec, "attach")
    _choose(rec, "evolve")
    assert rec.payload()["adjacent_relations"] == [{
        "left_block": 0, "right_block": 1, "status": "commutes",
        "left": "Play", "right": "Play", "reason": "both orders reach the same engine state"}]


def test_a_newly_enabled_action_remains_ordered():
    legal = lambda done: ("attach", "attack") if "attach" in done else ("attach",)
    rec = CounterfactualRecorder(_FakeEngine(legal=legal), _FakeBackend(), seat=0, turn=1)
    _choose(rec, "attach")
    _choose(rec, "attack")
    relation = rec.payload()["adjacent_relations"][0]
    assert relation["status"] == "ordered"
    assert relation["reason"].startswith("right action is unavailable before left")


def test_random_action_order_is_explicitly_branch_dependent():
    rec = CounterfactualRecorder(_FakeEngine(legal=lambda _done: ("shuffle", "attach")),
                                 _RandomFakeBackend(), seat=0, turn=1)
    _choose(rec, "shuffle")
    _choose(rec, "attach")
    relation = rec.payload()["adjacent_relations"][0]
    assert relation == {"left_block": 0, "right_block": 1, "status": "branch-dependent",
                        "left": "Play", "right": "Play", "reason": "an order consumed randomness"}


def test_undo_restores_the_exact_prior_fork():
    rec = CounterfactualRecorder(_FakeEngine(legal=lambda _done: ("attach", "evolve")),
                                 _FakeBackend(), seat=0, turn=1)
    _choose(rec, "attach")
    _choose(rec, "evolve")
    rec.undo()
    assert [row["option"]["action"] for row in rec.view()["options"]] == ["evolve"]
    assert [step["label"] for step in rec.payload()["steps"]] == ["Play"]


def test_full_line_grader_accepts_a_proved_reorder_and_rejects_a_different_end_state():
    backend = _FakeBackend()
    ideal = CounterfactualRecorder(_FakeEngine(legal=lambda _done: ("attach", "evolve")),
                                   backend, seat=0, turn=1)
    _choose(ideal, "attach")
    _choose(ideal, "evolve")
    reordered = CounterfactualRecorder(_FakeEngine(legal=lambda _done: ("attach", "evolve")),
                                       backend, seat=0, turn=1)
    _choose(reordered, "evolve")
    _choose(reordered, "attach")
    verdict = grade_counterfactual(ideal.payload(), reordered.payload())
    assert verdict == {"status": "match", "ordering": "equivalent-reorder",
                       "basis": "deterministic",
                       "end_state_match": True, "first_divergence": None}

    partial = CounterfactualRecorder(_FakeEngine(legal=lambda _done: ("attach", "evolve")),
                                     backend, seat=0, turn=1)
    _choose(partial, "attach")
    miss = grade_counterfactual(ideal.payload(), partial.payload())
    assert miss["status"] == "ungradeable"

    different = CounterfactualRecorder(_FakeEngine(legal=lambda _done: ("attach",)),
                                       backend, seat=0, turn=1)
    _choose(different, "attach")
    miss = grade_counterfactual(ideal.payload(), different.payload())
    assert miss["status"] == "mismatch" and miss["first_divergence"]["block"] == 1


def test_choice_resolution_follows_card_identity_when_hand_positions_move():
    before = {"current": {"yourIndex": 0, "players": [{"hand": [
        {"id": 100, "serial": 3}, {"id": 200, "serial": 4}]}, {}]},
              "select": {"option": [{"type": 7, "index": 1}]}}
    after = {"current": {"yourIndex": 0, "players": [{"hand": [
        {"id": 200, "serial": 4}]}, {}]},
             "select": {"option": [{"type": 7, "index": 0}]}}
    ref = choice_reference(before["select"]["option"][0], before, position=0)
    assert resolve_choice(after, [ref]) == [0]


def test_deck_search_choice_uses_the_selected_card_name():
    obs = {"current": {"yourIndex": 0, "players": [{}, {}]},
           "select": {"deck": [{"id": 1122, "serial": 8}],
                      "option": [{"type": 3, "area": 1, "index": 0}]}}
    assert choice_reference(obs["select"]["option"][0], obs, position=0)["label"] == "Pokégear 3.0"


def test_real_replay_can_fork_the_first_counterfactual_step_through_cgpy():
    with gzip.open("tests/fixtures/episode-81364540-replay.json.gz", "rt", encoding="utf-8") as fh:
        replay = json.load(fh)
    rec = CounterfactualRecorder.from_replay(replay, frame=5, rng_seed=0)
    view = rec.choose([3])
    assert rec.backend.name == "cgpy"
    assert len(rec.payload()["steps"]) == 1
    assert view["status"] in {"recording", "complete"}


def test_real_multi_action_line_reaches_turn_end_and_groups_effect_choices():
    with gzip.open("tests/fixtures/episode-81364540-replay.json.gz", "rt", encoding="utf-8") as fh:
        replay = json.load(fh)
    rec = CounterfactualRecorder.from_replay(replay, frame=5, rng_seed=0)
    for choice in ([3], [0], [0], [5]):
        view = rec.choose(choice)
    proof = rec.payload()
    assert view["status"] == proof["status"] == "complete"
    assert [step["block"] for step in proof["steps"]] == [0, 1, 1, 2]
    assert [relation["status"] for relation in proof["adjacent_relations"]] == ["ordered", "ordered"]
