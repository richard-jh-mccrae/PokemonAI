"""Seeded CARD continuations are engine-owned, never context-score guesses (Issue #464)."""
from __future__ import annotations

import copy
from dataclasses import dataclass

import pytest

from conftest import needs_live_board_search
from common import apply_engine
from common import apply_option as ao
from common import composer as cp
from common.strategy.context import _CARD
from train.continuation_parity import FIXTURES, bind_record, load_records, observable_writes
from train.tune import _build_pilot


_CONTEXTS = frozenset({1, 2, 3, 4, 7, 15, 17, 21, 22})
_NATIVE_CONTEXTS = _CONTEXTS - {2}  # Native cannot restore the opponent Active's play-age bit.


@dataclass
class _EngineObservation:
    """The native API's dataclass-shaped answer, small enough to pin route ownership."""

    current: dict
    logs: list
    select: dict | None = None


class _FreshSearch:
    """One returned native successor per fresh session; reusing one must fail the test."""

    def __init__(self, after: dict, expected_index: int):
        self.after = after
        self.expected_index = expected_index
        self.begun = self.ended = 0
        self.open = False

    def to_observation_class(self, observation):
        return observation

    def search_begin(self, observation, *_zones, **_kwargs):
        assert not self.open
        assert observation.get("search_begin_input")
        self.open = True
        self.begun += 1
        return type("Search", (), {"searchId": self.begun})()

    def search_step(self, search_id, selected):
        assert self.open and search_id == self.begun
        assert selected == [self.expected_index]
        return type("Stepped", (), {"observation": _EngineObservation(
            current=self.after["current"], logs=self.after.get("logs") or [],
            select=self.after.get("select"))})()

    def search_end(self):
        assert self.open
        self.open = False
        self.ended += 1


@pytest.fixture(scope="module")
def pilot():
    return _build_pilot("mega_starmie")[0]


def _model_and_option(pilot, record, *, obs=None):
    obs = copy.deepcopy(record["seed_observation"] if obs is None else obs)
    model = pilot._leaf_state_model(obs, int(obs["current"]["yourIndex"]))
    return model, obs["select"]["option"][record["selected"][0]]


def test_seeded_card_continuations_route_eight_exact_successors_without_reusing_a_session(pilot):
    """Route by exact menu membership; the native parity lane proves the recorded 8+1 outcomes."""

    records = {record["context"]: record for record in load_records()}
    assert set(records) == _CONTEXTS
    for context in sorted(_NATIVE_CONTEXTS):
        record = records[context]
        binding = bind_record(record, trace_root=FIXTURES)
        assert binding.reason is None
        expected = observable_writes(binding.successor["obs"], record["writes"])
        search = _FreshSearch(binding.successor["obs"], record["selected"][0])
        for _ in range(2):
            model, option = _model_and_option(pilot, record)
            # The recorded native continuation, not a per-card assertion, is the proof.
            result = ao.apply_option(model, option, search_api=search)
            assert isinstance(result, ao.EngineResolved)
            assert observable_writes(ao.require_model(result).source_obs, record["writes"]) == expected
        assert (search.begun, search.ended, search.open) == (2, 2, False)


def test_composer_prices_only_the_eight_seeded_card_continuations(pilot):
    """Composer-owned provenance must survive its origin stamp; setup-bench stays a refusal."""

    records = {record["context"]: record for record in load_records()}
    for context in sorted(_NATIVE_CONTEXTS):
        record = records[context]
        binding = bind_record(record, trace_root=FIXTURES)
        assert binding.reason is None
        search = _FreshSearch(binding.successor["obs"], record["selected"][0])
        model, option = _model_and_option(pilot, record)

        result = cp.compose(model, [option], search_api=search)

        assert result.order, context
        assert result.fanned[0] is not None
        assert search.begun == search.ended == 1

    record = records[2]
    binding = bind_record(record, trace_root=FIXTURES)
    assert binding.reason is None
    search = _FreshSearch(binding.successor["obs"], record["selected"][0])
    model, option = _model_and_option(pilot, record)
    result = cp.compose(model, [option], search_api=search)

    assert not result.order
    assert any("engine-refused" in gap for gap in result.gaps)
    assert search.begun == 0


def test_seeded_engine_menu_match_ignores_only_the_composer_origin_stamp():
    """A private field is still exact input unless it is the composer's known provenance stamp."""

    record = next(record for record in load_records() if record["context"] == 7)
    obs = copy.deepcopy(record["seed_observation"])
    option = obs["select"]["option"][record["selected"][0]]

    assert apply_engine.option_index(obs, {**option, "_composer_origin": (None, None)}) == record["selected"][0]
    assert apply_engine.option_index(obs, {**option, "_unrelated": "must-refuse"}) is None


@needs_live_board_search
def test_setup_bench_is_explicitly_engine_refused_without_normalising_play_age(pilot):
    """The sole native exception remains visible; Issue #470 is not resurrected as a fallback."""
    from cg import api as native

    record = next(record for record in load_records() if record["context"] == 2)
    model, option = _model_and_option(pilot, record)
    refused = ao.apply_option(model, option, search_api=native)
    assert isinstance(refused, ao.Refusal)
    assert "engine-refused" in refused.reason


@needs_live_board_search
def test_seeded_card_route_refuses_without_its_exact_single_pick_proof(pilot):
    """No token/menu/depth/multi-pick/order input may borrow a seeded continuation session."""
    from cg import api as native

    record = next(record for record in load_records() if record["context"] == 7)
    base = copy.deepcopy(record["seed_observation"])
    variants = []

    tokenless = copy.deepcopy(base)
    tokenless.pop("search_begin_input")
    variants.append((tokenless, None))

    mismatched = copy.deepcopy(base)
    mismatched["select"]["option"] = [dict(base["select"]["option"][0], index=999)]
    variants.append((mismatched, dict(base["select"]["option"][0])))

    multi_pick = copy.deepcopy(base)
    multi_pick["select"]["minCount"] = 2
    multi_pick["select"]["maxCount"] = 2
    variants.append((multi_pick, None))

    for obs, supplied in variants:
        model, option = _model_and_option(pilot, record, obs=obs)
        result = ao.apply_option(model, option if supplied is None else supplied, search_api=native,
                                 deterministic=True, clauses_cover=True)
        assert isinstance(result, ao.Refusal) and result.scope == ao.OPTION_SCOPE
        assert "unowned CARD" in result.reason

    model, option = _model_and_option(pilot, record)
    assert isinstance(ao.apply_option(model, option, search_api=native, depth=1), ao.Refusal)
    skill_order = copy.deepcopy(base)
    skill_order["select"]["context"] = 34  # SelectContext.SKILL_ORDER
    model, option = _model_and_option(pilot, record, obs=skill_order)
    assert isinstance(ao.apply_option(model, option, search_api=native, deterministic=True,
                                      clauses_cover=True), ao.Refusal)
    assert option["type"] == _CARD  # Fixture provenance really exercises the CARD path.
