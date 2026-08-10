"""Deferred targets rank on their complete reachable turn value."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from common import apply_option as ao
from common import board_choice, composer
from corpus_helpers import corpus_record, replay_agent


REPO = Path(__file__).resolve().parents[2]
BOSS = 1182
DURALUDON = 992
RELICANTH = 57


@pytest.fixture(scope="module")
def cases():
    spec = importlib.util.spec_from_file_location("continuation_tune", REPO / "tools/train/tune.py")
    tune = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tune)
    out = {}
    for key in (("82753102", 109), ("86091435", 119), ("85163079", 30)):
        record = corpus_record(*key)
        pilot = tune._build_pilot(replay_agent(record))[0]
        seat = int(record.obs["current"]["yourIndex"])
        model = pilot._leaf_state_model(record.obs, seat)
        hand = record.obs["current"]["players"][seat]["hand"]
        options = record.obs["select"]["option"]
        boss_index = next(
            i for i, option in enumerate(options)
            if option.get("type") == 7 and hand[option["index"]]["id"] == BOSS)
        out[key] = record, pilot, model, options, boss_index
    return out


def _active_id(target, seat=0):
    return target.model.source_obs["current"]["players"][1 - seat]["active"][0]["id"]


def _choice(case):
    _record, _pilot, model, options, boss_index = case
    expectation = board_choice.deferred_target(model, options[boss_index], seat_index=model.my_index)
    return composer.rank_targets(model, expectation)


@pytest.mark.req("REQ-COMPOSER-0009")
def test_f119_complete_target_value_overturns_the_immediate_relicanth_order(cases):
    case = cases[("86091435", 119)]
    choice = _choice(case)
    relicanth = next(target for target in choice.scored if _active_id(target) == RELICANTH)
    duraludon = max(
        (target for target in choice.scored if _active_id(target) == DURALUDON),
        key=lambda target: target.score)

    assert relicanth.leaf > duraludon.leaf
    assert duraludon.terminal_ev > relicanth.terminal_ev
    assert duraludon.score > relicanth.score
    assert _active_id(choice.best) == DURALUDON
    assert choice.score == pytest.approx(choice.leaf + choice.terminal_ev)

    _record, pilot, _model, _options, boss_index = case
    assert pilot.explain(_record.obs).chosen == [boss_index] == [3]


@pytest.mark.req("REQ-COMPOSER-0009")
def test_f119_candidate_adds_the_terminal_exactly_once(cases):
    _record, pilot, model, options, boss_index = cases[("86091435", 119)]
    choice = _choice(cases[("86091435", 119)])
    menu = [options[boss_index]] + [
        option for option in options if option.get("type") in (13, 14)]
    result = composer.compose(model, menu, shed=pilot.cost_shed_indices)
    candidate = result.chosen

    assert candidate is not None and candidate.first_index == 0
    assert candidate.leaf == pytest.approx(choice.leaf)
    assert candidate.terminal_ev == pytest.approx(choice.terminal_ev)
    assert candidate.score == pytest.approx(choice.score)
    assert candidate.score == pytest.approx(candidate.leaf + candidate.terminal_ev)


@pytest.mark.req("REQ-COMPOSER-0009")
def test_f119_followup_replan_uses_the_same_complete_target_value(cases, monkeypatch):
    case = cases[("86091435", 119)]
    _record, _pilot, model, _options, _boss_index = case
    choice = _choice(case)
    relicanth = next(target for target in choice.scored if _active_id(target) == RELICANTH)
    duraludon = max(
        (target for target in choice.scored if _active_id(target) == DURALUDON),
        key=lambda target: target.score)
    target_options = [
        {"type": 3, "area": 4, "index": 0, "playerIndex": 1},
        {"type": 3, "area": 4, "index": 1, "playerIndex": 1},
    ]

    def resolve(_model, option, **_kwargs):
        target = relicanth if option["index"] == 0 else duraludon
        return ao.EngineResolved(target.model, kind=3)

    monkeypatch.setattr(ao, "apply_option", resolve)
    result = composer.compose(
        model, target_options, continuation_boundary=True, required_pick=True)

    assert result.chosen is not None and result.chosen.first_index == 1
    assert result.chosen.leaf == pytest.approx(duraludon.leaf)
    assert result.chosen.terminal_ev == pytest.approx(duraludon.terminal_ev)
    assert result.chosen.score == pytest.approx(duraludon.score)


@pytest.mark.req("REQ-COMPOSER-0009")
def test_f30_loaded_threat_boss_remains_the_cross_deck_pick(cases):
    case = cases[("85163079", 30)]
    record, pilot, model, options, boss_index = case
    choice = _choice(case)
    result = composer.compose(model, options, shed=pilot.cost_shed_indices)

    assert boss_index == 0 and pilot.explain(record.obs).chosen == [boss_index]
    assert result.chosen is not None and result.chosen.first_index == boss_index
    assert choice.best is not None and choice.best.terminal_ev > 0.0
    assert result.chosen.score == pytest.approx(
        result.chosen.leaf + result.chosen.terminal_ev)


@pytest.mark.req("REQ-COMPOSER-0009")
def test_f109_transient_gust_leaf_cannot_replace_an_equal_or_better_root_terminal(cases):
    """Boss loses; a genuinely positive Hilda may precede the same threat-removing KO."""
    record, pilot, model, options, boss_index = cases[("82753102", 109)]
    choice = _choice(cases[("82753102", 109)])
    result = composer.compose(model, options, shed=pilot.cost_shed_indices)
    nebula = next(candidate for candidate in result.candidates
                  if not candidate.steps and candidate.terminal_index == 5)
    hilda = next(candidate for candidate in result.candidates
                 if candidate.first_index == 2 and len(candidate.steps) == 1
                 and candidate.terminal is None and candidate.terminal_ev > 0.0)

    assert choice.best is not None and choice.leaf > result.root_value
    assert choice.terminal_ev < nebula.terminal_ev
    assert all(candidate.first_index != boss_index for candidate in result.selection_candidates)
    assert hilda.leaf - result.root_value == pytest.approx(0.2625)
    assert hilda.terminal_ev == pytest.approx(nebula.terminal_ev)
    assert hilda.score == pytest.approx(hilda.leaf + nebula.terminal_ev)
    retreat_index = next(i for i, option in enumerate(options) if option.get("type") == 12)
    retreat_reveals = [candidate for candidate in result.candidates
                       if candidate.steps and candidate.first_index == retreat_index
                       and len(candidate.steps) > 1 and candidate.terminal is None]

    assert retreat_reveals and all(candidate.terminal_ev == 0.0
                                   for candidate in retreat_reveals)
    assert pilot.explain(record.obs).chosen == [2]
