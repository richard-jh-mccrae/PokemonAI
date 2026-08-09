"""Seeded CARD continuations are engine-owned, never context-score guesses (Issue #464)."""
from __future__ import annotations

import copy
import sys
import types
from dataclasses import dataclass

import pytest

from conftest import needs_live_board_search
from common import apply_engine
from common import apply_option as ao
from common import composer as cp
from common.runtime import build_pilot
from common.strategy.context import _CARD
from common.strategy.planner import TurnLine
from train.continuation_parity import FIXTURES, bind_record, load_records, observable_writes
from train.tune import _build_pilot


_CONTEXTS = frozenset({1, 2, 3, 4, 7, 15, 17, 21, 22})
_NATIVE_CONTEXTS = _CONTEXTS - {2}  # Native cannot restore the opponent Active's play-age bit.
_RUNTIME_CONTEXTS = frozenset({3, 4, 7, 15, 17, 21, 22})


@dataclass
class _EngineObservation:
    """The native API's dataclass-shaped answer, small enough to pin route ownership."""

    current: dict
    logs: list
    select: dict | None = None


class _FreshSearch:
    """One returned native successor per fresh session; reusing one must fail the test."""

    def __init__(self, after: dict, expected_index: int, *, terminal: bool = False,
                 preferred_index: int | None = None):
        self.after = after
        self.expected_indices = {expected_index} if isinstance(expected_index, int) else set(expected_index)
        self.terminal = terminal
        self.preferred_index = preferred_index
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
        assert len(selected) == 1 and selected[0] in self.expected_indices
        current = copy.deepcopy(self.after["current"])
        if self.preferred_index is not None and selected[0] != self.preferred_index:
            my_index = int(current.get("yourIndex") or 0)
            prizes = current["players"][my_index].setdefault("prize", [])
            prizes.extend(copy.deepcopy(prizes[0]) for _ in range(selected[0] + 1))
        return type("Stepped", (), {"observation": _EngineObservation(
            current=current, logs=self.after.get("logs") or [],
            select=None if self.terminal else self.after.get("select"))})()

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
    search = _FreshSearch(binding.successor["obs"], range(len(record["seed_observation"]["select"]["option"])),
                          terminal=True)
    model, option = _model_and_option(pilot, record)
    result = cp.compose(model, [option], search_api=search)

    assert not result.order
    assert any("engine-refused" in gap for gap in result.gaps)
    assert search.begun == 0


def test_planner_arms_the_composer_for_the_seven_runtime_card_contexts(pilot):
    """The planner reaches the single composer route for every reconstructible continuation."""

    records = {record["context"]: record for record in load_records()}
    for context in sorted(_RUNTIME_CONTEXTS):
        record = records[context]
        binding = bind_record(record, trace_root=FIXTURES)
        assert binding.reason is None
        obs = copy.deepcopy(record["seed_observation"])
        select = obs["select"]
        option = select["option"][record["selected"][0]]
        pilot._turn_plan = None
        pilot._composer_trace = None
        pilot._search_api = _FreshSearch(binding.successor["obs"], record["selected"][0])
        board = pilot._board(obs, select)
        traces = [pilot._option_trace(obs, select, board, option, record["selected"][0])]

        pilot.plan_turn(obs, select, board, [option], traces)

        assert pilot._composer_trace is not None, context
        assert not pilot._composer_trace["gaps"], context
        assert pilot._search_api.begun == pilot._search_api.ended == 1

    record = records[2]
    obs = copy.deepcopy(record["seed_observation"])
    select = obs["select"]
    option = select["option"][record["selected"][0]]
    pilot._turn_plan = None
    pilot._composer_trace = None
    pilot._search_api = _FreshSearch({}, record["selected"][0])
    board = pilot._board(obs, select)
    traces = [pilot._option_trace(obs, select, board, option, record["selected"][0])]

    assert pilot.plan_turn(obs, select, board, [option], traces) is None
    assert pilot._composer_trace is None
    assert pilot._search_api.begun == 0


def test_runtime_built_pilot_uses_live_cg_api_for_all_seeded_card_menus(pilot, monkeypatch):
    """Every reconstructible packaged route resolves ``cg.api`` without private injection."""
    records = {record["context"]: record for record in load_records()}
    for context in sorted(_RUNTIME_CONTEXTS):
        record = records[context]
        binding = bind_record(record, trace_root=FIXTURES)
        assert binding.reason is None
        option_count = len(record["seed_observation"]["select"]["option"])
        preferred = None if context in {7, 22} else record["selected"][0]
        search = _FreshSearch(binding.successor["obs"], range(option_count), terminal=True,
                              preferred_index=preferred)
        monkeypatch.setitem(sys.modules, "cg", types.SimpleNamespace(api=search))
        runtime_pilot = build_pilot(pilot.strategy, pilot.deck, stats=pilot.stats,
                                    scout=None, briefs=None)

        decision = runtime_pilot.explain(copy.deepcopy(record["seed_observation"]))

        assert decision.planned and decision.planned.goal == "compose", context
        assert search.begun == search.ended > 0, context


@needs_live_board_search
def test_runtime_built_pilot_commits_all_seven_native_successors(pilot):
    """The packaged constructor and real native seam meet, not merely two separately green proofs."""
    records = {record["context"]: record for record in load_records()}
    for context in sorted(_RUNTIME_CONTEXTS):
        runtime_pilot = build_pilot(pilot.strategy, pilot.deck, stats=pilot.stats,
                                    scout=None, briefs=None)

        decision = runtime_pilot.explain(copy.deepcopy(records[context]["seed_observation"]))

        assert decision.planned and decision.planned.goal == "compose", context
        assert decision.composer and not decision.composer["gaps"], context


def test_mega_starmie_promotion_corrections_are_priced_and_cannot_reuse_a_pre_ko_plan(pilot):
    """All four empty-Active frames are priced; their fingerprint rejects a cached pre-KO line."""
    from corpus_helpers import corpus_index
    frames = [c.obs for c in corpus_index().values()
              if c.agent == "mega_starmie" and (c.obs.get("select") or {}).get("context") == 4]
    assert len(frames) == 4
    for obs in frames:
        select = obs["select"]
        assert not ((obs["current"]["players"][obs["current"]["yourIndex"]].get("active") or [None])[0])
        pre_ko = copy.deepcopy(obs)
        pre_ko["current"]["players"][pre_ko["current"]["yourIndex"]]["active"] = [{"id": 666, "hp": 1}]
        pilot._turn_plan = (pilot._plan_fingerprint(pre_ko, select),
                            TurnLine(next_step=[0], goal="stale"))
        board = pilot._board(obs, select)
        traces = [pilot._option_trace(obs, select, board, option, index)
                  for index, option in enumerate(select["option"])]

        assert all(trace.promote_retreat_working is not None for trace in traces)
        assert pilot.plan_turn(obs, select, board, select["option"], traces) is None
        assert pilot._turn_plan[0] == pilot._plan_fingerprint(obs, select)


@pytest.mark.parametrize(("minimum", "maximum"), ((2, 2), (0, 0), (-1, 1)))
def test_planner_leaves_non_single_pick_seeded_continuations_out_of_scope(pilot, minimum, maximum):
    """Issue #387, not the follow-up composer route, owns invalid or required multi-picks."""

    record = next(record for record in load_records() if record["context"] == 7)
    binding = bind_record(record, trace_root=FIXTURES)
    assert binding.reason is None
    obs = copy.deepcopy(record["seed_observation"])
    select = obs["select"]
    select["minCount"] = minimum
    select["maxCount"] = maximum
    option = select["option"][record["selected"][0]]
    pilot._turn_plan = None
    pilot._composer_trace = None
    pilot._search_api = _FreshSearch(binding.successor["obs"], record["selected"][0])
    board = pilot._board(obs, select)
    traces = [pilot._option_trace(obs, select, board, option, record["selected"][0])]

    assert pilot.plan_turn(obs, select, board, [option], traces) is None
    assert pilot._search_api.begun == 0


def test_planner_does_not_silence_unexpected_composer_errors(pilot, monkeypatch):
    """A programming error must surface; only explicit model refusals may defer."""

    record = next(record for record in load_records() if record["context"] == 7)
    obs = copy.deepcopy(record["seed_observation"])
    select = obs["select"]
    option = select["option"][record["selected"][0]]
    board = pilot._board(obs, select)
    traces = [pilot._option_trace(obs, select, board, option, record["selected"][0])]

    def broken(*_args, **_kwargs):
        raise RuntimeError("unexpected composer fault")

    monkeypatch.setattr(cp, "compose", broken)
    with pytest.raises(RuntimeError, match="unexpected composer fault"):
        pilot._composer_line(obs, select, board, [option], traces)


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
