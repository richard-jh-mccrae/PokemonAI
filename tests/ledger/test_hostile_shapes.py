"""Every probe-proven crash shape from the audit, fed through the fixed code.

Each test is one input that used to raise on the live path. The contract everywhere is the
same: degrade the way unknown ids already do, keep the decision, and where the degradation is
pricing-relevant, SAY SO as a gap — never absorb silently, never die."""
from __future__ import annotations

from observation_builders import build_observation, advance_observation

import math
from dataclasses import replace

import pytest

from ledger_helpers import (DRAGAPULT, FIRE_E, LILLIES, ScriptedProvider, action, body,
                            player, printout)

from common.algebra import Terminal
from common.observation import ObservationConstructionError, ObservationState
from common.ledger import EvaluationModel, LedgerDecider, LedgerWeights, evaluate
from common.ledger.chance import refresh_value
from common.ledger.decider import LedgerUnavailable
from common.options import enumerate_legal_actions
from common.runtime import _last_resort_selection
from deprecated.bellman.state import DecisionState


def test_non_finite_weight_overrides_refuse_at_resolve_time():
    """One NaN in a deck's ledger_overrides used to poison every swing into an unrankable
    number and crash `_ranked` on every decision, all match long."""
    for hostile in (float("nan"), float("inf"), "-inf"):
        with pytest.raises(ValueError):
            LedgerWeights().resolve({"prize_race": hostile})
        with pytest.raises(ValueError):
            LedgerWeights().resolve({"card.121": hostile})


def test_a_non_finite_swing_scores_zero_and_logs_the_gap():
    """Belt behind the weights guard: if a NaN/inf ever reaches a price anyway, the option
    reads neutral and the gap names it — visible, never silently absorbed."""
    weights = replace(LedgerWeights(), win_value=math.inf)   # bypasses resolve on purpose
    won = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]))
    won["current"]["result"] = 0
    struck = DecisionState.from_observation(won, deck=(DRAGAPULT,) * 60, deck_name="test",
                                            value_registry_identity="hostile")
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]))
    play, end = action("play", (0,)), action("end", (1,))
    provider = ScriptedProvider(menus={"root": (play, end)},
                                nodes={("root", play.identity): Terminal(struck, "won")})
    decider = LedgerDecider((DRAGAPULT,) * 60, "test",
                            EvaluationModel.build(weights=weights),
                            provider_factory=lambda _s, **_kw: provider)
    decision = decider.decide(root_obs)
    assert any("non-finite price" in gap for gap in decision.diagnostics["gaps"])
    prices = {entry["action"]: entry["swing"] for entry in decision.diagnostics["prices"]}
    assert prices[str(play.identity)] == 0.0     # the promised NEUTRAL score, exactly


def test_refresh_tolerates_idless_hand_rows():
    """The Bellman twin of this read filters id-less rows deliberately; the Ledger port had
    dropped the guard and died on `{"id": None}`."""
    obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[LILLIES, FIRE_E]))
    obs["current"]["players"][0]["hand"].extend([{"id": None, "serial": 9}, {"serial": 10}])
    board = build_observation(obs, decklist=(DRAGAPULT,) * 30)
    value, _gaps = refresh_value(board, LILLIES, ((6, 0),), False,
                                 lambda synthetic: evaluate(synthetic, EvaluationModel.build()))
    assert math.isfinite(value)


def test_observation_rejects_a_single_entry_players_list():
    obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[LILLIES]))
    obs["current"]["players"] = [obs["current"]["players"][0]]
    with pytest.raises(ObservationConstructionError):
        build_observation(obs, decklist=(DRAGAPULT,) * 30)


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


def test_observation_construction_rejects_a_structurally_malformed_zone():
    me = player(active=body(DRAGAPULT, 1), hand=[FIRE_E])
    me["hand"].extend([{"id": None, "serial": 8}, {"serial": 9}])
    me["discard"] = [{"id": None}, {"id": FIRE_E, "serial": 900}]
    me["active"][0]["energies"] = [None, 5]
    obs = printout(me=me, select={
        "type": 1, "context": 0, "minCount": 1, "maxCount": 1,
        "option": [None, {"type": 14}], "deck": None, "contextCard": None, "effect": None,
        "remainDamageCounter": 0, "remainEnergyCost": 0})
    obs["current"]["players"][1]["active"] = {"id": DRAGAPULT}     # dict where a list belongs
    obs["own_prizes"] = {FIRE_E: None, DRAGAPULT: 1, None: 2}
    with pytest.raises(ObservationConstructionError, match="player.active"):
        build_observation(obs, decklist=(DRAGAPULT,) * 30)


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


def test_an_unavailable_provider_is_closed_before_the_refusal():
    closed = []

    class HalfOpenProvider:
        available = False
        _error = "session refused"

        def close(self):
            closed.append(True)

    decider = LedgerDecider((DRAGAPULT,) * 60, "test", EvaluationModel.build(),
                            provider_factory=lambda _s, **_kw: HalfOpenProvider())
    with pytest.raises(LedgerUnavailable):
        decider.decide(printout(me=player(active=body(DRAGAPULT, 1))))
    assert closed == [True]


def test_the_last_resort_shell_is_total():
    """The final shell before a forfeit used to crash on the exact shape that had just
    crashed the layer above it (a present-but-None context)."""
    garbage = {"select": {"context": None, "minCount": None, "maxCount": None,
                          "option": ["junk", {"type": 14}]}, "current": None}
    assert _last_resort_selection(garbage) == []       # minCount None reads 0: decline legally
    garbage["select"]["minCount"] = 2
    assert _last_resort_selection(garbage) == [0, 1]   # a demanded count is still met
    assert _last_resort_selection({"select": None}) == []


def test_a_corrupt_bench_max_cannot_stall_the_evaluator():
    obs = printout(me=player(active=body(DRAGAPULT, 1)))
    obs["current"]["players"][0]["benchMax"] = 10 ** 9
    valuation = evaluate(build_observation(obs), EvaluationModel.build())
    assert math.isfinite(valuation.total)
