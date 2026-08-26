"""The preview walk's node arms: chance weighting, adversarial choosers, and the caps.

The decider suite pins the turn policy over Deterministic/Terminal/Refresh scripts; this file
pins the remaining algebra arms — Chance, Choice, RevealChoice — in BOTH actor directions, the
may-end propagation, and the two budgets. Expected values are composed from single-leg runs of
the same scripts, never recomputed by hand, so the assertions read pure arithmetic relations."""
from __future__ import annotations

import math
import pytest

from ledger_helpers import (DRAGAPULT, FIRE_E, ScriptedProvider, action, body, player,
                            printout)

from common.algebra import (Actor, Chance, Choice, Deterministic, Edge, RevealChoice,
                            RevealOutcome, Terminal, WeightedEdge)
from common.ledger import DeckOverlay, EvaluationModel, LedgerDecider
from deprecated.bellman.state import DecisionState

DECK = (DRAGAPULT, FIRE_E) * 20
INFORMATION_VALUE = EvaluationModel.build().configuration["continuation.information_value"]


def state_of(observation):
    return DecisionState.from_observation(observation, deck=DECK, deck_name="test",
                                          value_registry_identity="preview-tests")


ROOT_OBS = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
                    them=player(own=False, active=body(DRAGAPULT, 2)))
#: A clearly better and a clearly worse successor: energy attached vs energy burned away.
GOOD = state_of(printout(me=player(active=body(DRAGAPULT, 1, energies=(2,)), hand=[]),
                         them=player(own=False, active=body(DRAGAPULT, 2))))
BAD = state_of(printout(me=player(active=body(DRAGAPULT, 1), hand=[], discard=[FIRE_E]),
                        them=player(own=False, active=body(DRAGAPULT, 2))))


def price_of(node):
    """The scripted play's swing and ends flag under the standard root."""
    play, end = action("play", (0,)), action("end", (1,))
    provider = ScriptedProvider(menus={"root": (play, end)},
                                nodes={("root", play.identity): node})
    decision = LedgerDecider(DECK, "test", EvaluationModel.build(),
                             provider_factory=lambda _s, **_kw: provider).decide(ROOT_OBS)
    entry = next(row for row in decision.diagnostics["prices"]
                 if row["action"] == str(play.identity))
    return entry["swing"], entry["ends_turn"], decision


def test_chance_weights_its_legs_by_probability():
    good_swing, _, _ = price_of(Deterministic(GOOD))
    bad_swing, _, _ = price_of(Deterministic(BAD))
    assert good_swing > bad_swing
    mixed, _, _ = price_of(Chance((WeightedEdge(0.25, "good", Deterministic(GOOD)),
                                   WeightedEdge(0.75, "bad", Deterministic(BAD)))))
    assert mixed == pytest.approx(0.25 * good_swing + 0.75 * bad_swing, abs=1e-9)


def test_chance_activations_are_independent_of_valuation_coefficients():
    play, end = action("play", (0,)), action("end", (1,))
    node = Chance((WeightedEdge(0.25, "good", Deterministic(GOOD)),
                   WeightedEdge(0.75, "bad", Deterministic(BAD))))
    provider = ScriptedProvider(menus={"root": (play, end)},
                                nodes={("root", play.identity): node})

    def activations(context):
        decision = LedgerDecider(
            DECK, "test", context,
            provider_factory=lambda _s, **_kw: provider).decide(ROOT_OBS)
        price = next(row for row in decision.diagnostics["prices"]
                     if row["action"] == str(play.identity))
        return {item["feature"]: item["activation"]
                for item in price["continuation"]["contributions"]}

    general = EvaluationModel.build()
    bent = EvaluationModel.build(overlay=DeckOverlay({"kind.energy": 9.0}))
    assert activations(general) == activations(bent)


def test_a_chance_that_may_continue_is_not_hidden_by_an_end_risk_branch():
    _, ends, _ = price_of(Chance((WeightedEdge(0.5, "resolves", Terminal(GOOD, "done")),
                                  WeightedEdge(0.5, "continues", Deterministic(BAD)))))
    assert ends is False
    _, still_open, _ = price_of(Chance((WeightedEdge(0.5, "a", Deterministic(GOOD)),
                                        WeightedEdge(0.5, "b", Deterministic(BAD)))))
    assert still_open is False
    _, certain_end, _ = price_of(Chance((WeightedEdge(0.5, "a", Terminal(GOOD, "done")),
                                         WeightedEdge(0.5, "b", Terminal(BAD, "done")))))
    assert certain_end is True


def test_mixed_chance_prices_continuation_and_allowances_by_probability():
    spent_obs = printout(me=player(active=body(DRAGAPULT, 1, energies=(2,)), hand=[]),
                         them=player(own=False, active=body(DRAGAPULT, 2)))
    spent_obs["current"]["energyAttached"] = True
    spent = state_of(spent_obs)
    play, end = action("play", (0,)), action("end", (1,))
    node = Chance((WeightedEdge(0.25, "spent", Deterministic(spent)),
                   WeightedEdge(0.75, "ended", Terminal(BAD, "done"))))
    provider = ScriptedProvider(menus={"root": (play, end)},
                                nodes={("root", play.identity): node})
    decision = LedgerDecider(
        DECK, "test", EvaluationModel.build(),
        provider_factory=lambda _s, **_kw: provider).decide(ROOT_OBS)
    price = next(row for row in decision.diagnostics["prices"]
                 if row["action"] == str(play.identity))
    activations = {item["feature"]: item["activation"]
                   for item in price["continuation"]["contributions"]}

    assert activations["action.opportunity_cost"] == pytest.approx(-0.25)
    assert activations["continuation.allowance_consumed"] == pytest.approx(0.25)


def test_choice_takes_the_best_leg_for_us_and_the_worst_when_theirs():
    good_swing, _, _ = price_of(Deterministic(GOOD))
    bad_swing, _, _ = price_of(Deterministic(BAD))
    legs = (Edge("good", Deterministic(GOOD)), Edge("bad", Deterministic(BAD)))
    ours, _, _ = price_of(Choice(Actor.OURS, legs))
    theirs, _, _ = price_of(Choice(Actor.OPPONENT, legs))
    assert ours == pytest.approx(good_swing, abs=1e-9)
    assert theirs == pytest.approx(bad_swing, abs=1e-9)


def test_reveal_choice_honors_its_actor_in_both_directions():
    """Our chooser takes our best continuation; theirs takes our worst."""
    good_swing, _, _ = price_of(Deterministic(GOOD))
    bad_swing, _, _ = price_of(Deterministic(BAD))
    choices = (Edge("good", Deterministic(GOOD)), Edge("bad", Deterministic(BAD)))
    outcomes = (RevealOutcome(1.0, ("good", "bad")),)
    ours, _, _ = price_of(RevealChoice(Actor.OURS, choices, outcomes))
    theirs, _, _ = price_of(RevealChoice(Actor.OPPONENT, choices, outcomes))
    assert ours == pytest.approx(good_swing + INFORMATION_VALUE, abs=1e-9)
    assert theirs == pytest.approx(bad_swing + INFORMATION_VALUE, abs=1e-9)


def test_reveal_choice_weights_outcomes_and_chooses_within_each():
    good_swing, _, _ = price_of(Deterministic(GOOD))
    bad_swing, _, _ = price_of(Deterministic(BAD))
    choices = (Edge("good", Deterministic(GOOD)), Edge("bad", Deterministic(BAD)))
    outcomes = (RevealOutcome(0.5, ("bad",)),            # the reveal offered only the bad leg
                RevealOutcome(0.5, ("good", "bad")))     # both on offer: we take the good one
    swing, _, _ = price_of(RevealChoice(Actor.OURS, choices, outcomes))
    assert swing == pytest.approx(
        0.5 * bad_swing + 0.5 * good_swing + 0.5 * INFORMATION_VALUE, abs=1e-9)


def test_a_reveal_whose_chosen_leg_resolves_the_turn_counts_as_an_ender():
    choices = (Edge("resolves", Terminal(GOOD, "done")),)
    _, ends, _ = price_of(RevealChoice(Actor.OURS, choices,
                                       (RevealOutcome(1.0, ("resolves",)),)))
    assert ends is True


def _forced_select():
    return {"type": 1, "context": 7, "minCount": 1, "maxCount": 1,
            "option": [{"type": 3, "index": 0}], "deck": None, "contextCard": None,
            "effect": None, "remainDamageCounter": 0, "remainEnergyCost": 0}


def test_a_two_menu_forced_chain_is_walked_to_its_leaf():
    """Ultra Ball's shape — play, then a forced discard pick, then a forced fetch pick: the
    root price is the LEAF's swing with no cap gap, which requires walking two menus deep."""
    first_menu = state_of(printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E],
                                             deck_count=39), select=_forced_select()))
    second_menu = state_of(printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E],
                                              deck_count=38), select=_forced_select()))
    leaf_swing, _, _ = price_of(Deterministic(GOOD))

    play, end = action("play", (0,)), action("end", (1,))
    pick_one, pick_two = action("card", (0,)), action("card", (1,))
    provider = ScriptedProvider(
        menus={"root": (play, end), first_menu.semantic_key: (pick_one,),
               second_menu.semantic_key: (pick_two,)},
        nodes={("root", play.identity): Deterministic(first_menu),
               (first_menu.semantic_key, pick_one.identity): Deterministic(second_menu),
               (second_menu.semantic_key, pick_two.identity): Deterministic(GOOD)})
    decision = LedgerDecider(DECK, "test", EvaluationModel.build(),
                             provider_factory=lambda _s, **_kw: provider).decide(ROOT_OBS)
    entry = next(row for row in decision.diagnostics["prices"]
                 if row["action"] == str(play.identity))
    assert entry["swing"] == pytest.approx(leaf_swing, abs=1e-9)
    assert not any("chain capped" in gap for gap in decision.diagnostics["gaps"])


def test_a_chain_past_the_depth_cap_scores_mid_board_and_keeps_the_root():
    """The end-chain lesson: a cap logs its gap and scores the last seen board — it must never
    veto the option carrying the turn (the root still gets a finite price)."""
    mids = [state_of(printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E],
                                        deck_count=40 - index), select=_forced_select()))
            for index in range(20)]
    play, end = action("play", (0,)), action("end", (1,))
    step = action("card", (0,))
    menus = {"root": (play, end)}
    nodes = {("root", play.identity): Deterministic(mids[0])}
    for here, there in zip(mids, mids[1:]):
        menus[here.semantic_key] = (step,)
        nodes[(here.semantic_key, step.identity)] = Deterministic(there)
    menus[mids[-1].semantic_key] = (step,)
    nodes[(mids[-1].semantic_key, step.identity)] = Deterministic(GOOD)
    provider = ScriptedProvider(menus=menus, nodes=nodes)
    decision = LedgerDecider(DECK, "test", EvaluationModel.build(),
                             provider_factory=lambda _s, **_kw: provider).decide(ROOT_OBS)
    entry = next(row for row in decision.diagnostics["prices"]
                 if row["action"] == str(play.identity))
    assert math.isfinite(entry["swing"])           # priced, not dropped
    assert any("chain capped" in gap for gap in decision.diagnostics["gaps"])


def test_a_tree_past_the_node_budget_caps_instead_of_running_away():
    legs = tuple(WeightedEdge(1.0 / 200, f"leg{index}", Deterministic(GOOD))
                 for index in range(200))
    _, _, decision = price_of(Chance(legs))
    assert any("chain capped" in gap for gap in decision.diagnostics["gaps"])


def test_an_empty_forced_menu_logs_its_gap_and_scores_the_mid_board():
    starved = state_of(printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
                                select=_forced_select()))
    play, end = action("play", (0,)), action("end", (1,))
    provider = ScriptedProvider(
        menus={"root": (play, end), starved.semantic_key: ()},
        nodes={("root", play.identity): Deterministic(starved)})
    decision = LedgerDecider(DECK, "test", EvaluationModel.build(),
                             provider_factory=lambda _s, **_kw: provider).decide(ROOT_OBS)
    assert any("forced menu offered no actions" in gap
               for gap in decision.diagnostics["gaps"])
