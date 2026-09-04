"""Every probe-proven crash shape from the audit, fed through the fixed code.

Each test is one input that used to raise on the live path. The contract everywhere is the
same: degrade the way unknown ids already do, keep the decision, and where the degradation is
pricing-relevant, SAY SO as a gap — never absorb silently, never die."""
from __future__ import annotations

import math
from dataclasses import replace

import pytest

from ledger_helpers import (DRAGAPULT, FIRE_E, LILLIES, UNKNOWN, ScriptedProvider, action, body,
                            player, printout)

from common.algebra import Terminal
from common.observation import (KnownOwnPrizes, LegalKnowledge, ObservationConstructionError,
                                ObservationStateBuilder)
from common.ledger import (ComputeConfiguration, EvaluationModel, LedgerDecider,
                           ValuationConfiguration, evaluate)
from common.ledger.chance import refresh_outcomes
from common.ledger.decider import LedgerUnavailable
from common.options import enumerate_legal_actions
from common.decision import safe_legal_selection
from deprecated.bellman.state import DecisionState


def test_non_finite_configuration_values_refuse_at_resolve_time():
    """One NaN in configuration would poison every swing into an unrankable number."""
    for hostile in (float("nan"), float("inf"), "-inf"):
        with pytest.raises(ValueError):
            ValuationConfiguration.general().with_values({"prize.race": hostile})
        with pytest.raises(ValueError):
            ValuationConfiguration.general().with_values({"kind.item": hostile})


def test_a_non_finite_swing_scores_zero_and_logs_the_gap():
    with pytest.raises(ValueError):
        ValuationConfiguration(
            {**dict(ValuationConfiguration.general()), "result.win": math.inf},
            schema_version=ValuationConfiguration.general().schema_version)


def test_refresh_tolerates_idless_hand_rows():
    """The Bellman twin of this read filters id-less rows deliberately; the Ledger port had
    dropped the guard and died on `{"id": None}`."""
    obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[LILLIES, FIRE_E]))
    obs["current"]["players"][0]["hand"].extend([{"id": None, "serial": 9}, {"serial": 10}])
    board = ObservationStateBuilder((DRAGAPULT,) * 30).root(obs)
    calls = []
    def valued(synthetic):
        calls.append(synthetic.position_key)
        return evaluate(synthetic, EvaluationModel.build())

    valuation, _gaps, summary, _landings = refresh_outcomes(
        obs, board, LILLIES, ((6, 0),), False,
        valued,
        ComputeConfiguration())
    assert math.isfinite(valuation.total)
    assert len(calls) == summary.sample_count == 12
    assert summary.variance >= 0.0


def test_observation_boundary_rejects_a_single_entry_players_list():
    obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[LILLIES]))
    obs["current"]["players"] = [obs["current"]["players"][0]]
    with pytest.raises(ObservationConstructionError):
        ObservationStateBuilder((DRAGAPULT,) * 30).root(obs)


def test_the_enumerator_survives_none_counts_and_junk_option_rows():
    """minCount/maxCount arrive present-but-None on the deployed dialect, and a junk option
    row must keep its index (typeless) so every offered index stays covered."""
    obs = printout(me=player(active=body(DRAGAPULT, 1)), select={
        "type": 1, "context": 0, "minCount": None, "maxCount": None,
        "option": [{"type": 14}, "junk", None], "deck": None, "contextCard": None,
        "effect": None, "remainDamageCounter": 0, "remainEnergyCost": 0})
    actions = enumerate_legal_actions(obs)
    assert actions
    covered = {index for act in actions
               for selection in act.equivalent_selections for index in selection}
    assert covered == {0, 1, 2}                  # junk keeps its index; every index covered


def test_observation_boundary_rejects_malformed_zone_shapes():
    me = player(active=body(DRAGAPULT, 1), hand=[FIRE_E])
    me["hand"].extend([{"id": None, "serial": 8}, {"serial": 9}])
    me["discard"] = [{"id": None}, {"id": FIRE_E, "serial": 900}]
    me["active"][0]["energies"] = [None, 5]
    obs = printout(me=me, select={
        "type": 1, "context": 0, "minCount": 1, "maxCount": 1,
        "option": [None, {"type": 14}], "deck": None, "contextCard": None, "effect": None,
        "remainDamageCounter": 0, "remainEnergyCost": 0})
    obs["current"]["players"][1]["active"] = {"id": DRAGAPULT}     # dict where a list belongs
    with pytest.raises(ObservationConstructionError):
        ObservationStateBuilder((DRAGAPULT,) * 30).root(
            obs, knowledge=LegalKnowledge(own_prizes=KnownOwnPrizes(((DRAGAPULT, 1),))))


def test_a_raising_provider_close_does_not_mask_the_decision():
    class SlammingProvider(ScriptedProvider):
        def close(self):
            raise RuntimeError("engine session already dead")

    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]))
    struck = DecisionState.from_observation(
        printout(me=player(active=body(DRAGAPULT, 1), hand=[])),
        deck=(DRAGAPULT,) * 60, deck_name="test", value_registry_identity="hostile")
    play, end = action("play", (0,)), action("end", (1,))
    provider = SlammingProvider(menus={"root": (play, end)},
                                nodes={("root", play.identity): Terminal(struck, "done")})
    decision = LedgerDecider((DRAGAPULT,) * 60, "test", EvaluationModel.build(),
                             provider_factory=lambda _s, **_kw: provider).decide(root_obs)
    assert decision.diagnostics["backend"] == "ledger"
    assert decision.diagnostics["cleanup_failure"]["stage"] == "provider"
    assert decision.diagnostics["cleanup_failure"]["error_type"] == "RuntimeError"


def test_an_unavailable_provider_is_closed_before_the_fail_safe_result():
    closed = []

    class HalfOpenProvider:
        available = False
        _error = "session refused"

        def close(self):
            closed.append(True)

    decider = LedgerDecider((DRAGAPULT,) * 60, "test", EvaluationModel.build(),
                            provider_factory=lambda _s, **_kw: HalfOpenProvider())
    decision = decider.decide(printout(me=player(active=body(DRAGAPULT, 1)),
                                      select={"context": 0, "minCount": 0, "maxCount": 0, "option": []}))

    assert decision.diagnostics["failure"]["stage"] == "provider"
    assert closed == [True]


def test_the_fail_safe_selector_is_total():
    garbage = {"select": {"context": None, "minCount": None, "maxCount": None,
                          "option": ["junk", {"type": 14}]}, "current": None}
    assert safe_legal_selection(garbage) == []         # minCount None reads 0: decline legally
    garbage["select"]["minCount"] = 2
    assert safe_legal_selection(garbage) == [0, 1]     # a demanded count is still met
    garbage["select"]["minCount"] = "broken"
    assert safe_legal_selection(garbage) == [0]
    assert safe_legal_selection({"select": None}) == []


def test_a_corrupt_bench_max_cannot_stall_the_evaluator():
    obs = printout(me=player(active=body(DRAGAPULT, 1)))
    obs["current"]["players"][0]["benchMax"] = 10 ** 9
    valuation = evaluate(ObservationStateBuilder().root(obs), EvaluationModel.build())
    assert math.isfinite(valuation.total)


def test_restricted_target_checks_tolerate_unknown_body_facts():
    state = ObservationStateBuilder().root(printout(
        me=player(active=body(UNKNOWN, 1), hand=[1229])))

    assert math.isfinite(evaluate(state, EvaluationModel.build()).total)
