"""The preview walk's node arms: chance weighting, adversarial choosers, and the caps.

The decider suite pins the turn policy over Deterministic/Terminal/Refresh scripts; this file
pins the remaining algebra arms — Chance, Choice, RevealChoice — in BOTH actor directions, the
may-end propagation, and the two budgets. Expected values are composed from single-leg runs of
the same scripts, never recomputed by hand, so the assertions read pure arithmetic relations."""
from __future__ import annotations

import math
from types import SimpleNamespace
import pytest

from ledger_helpers import (DRAKLOAK, DRAGAPULT, DREEPY, FIRE_E, ScriptedProvider, action, body,
                            player, printout)

from common.algebra import (Actor, Chance, Choice, Deterministic, Edge, RevealChoice,
                            RevealOutcome, Terminal, WeightedEdge)
from common.decision import EvaluationStatus, SearchConfiguration
from common.ledger import DeckOverlay, EvaluationModel, LedgerDecider
from common.ledger.evaluate import FeatureActivation, FeatureContribution, Valuation, evaluate
from common.ledger.preview import (_body_ability_ready, _body_copy_overflow,
                                   _discard_spend_contributions,
                                   _realized_portfolio_contributions, price_actions)
from common.observation import ObservationStateBuilder
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


def test_prize_transition_emits_realized_knockout_value():
    root_observation = printout(
        me=player(active=body(DRAGAPULT, 1), prizes=6),
        them=player(own=False, active=body(DRAGAPULT, 2), prizes=6))
    landing = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), prizes=5),
        them=player(own=False, active=body(DRAGAPULT, 3), prizes=6)))
    attack, end = action("attack", (0,)), action("end", (1,))
    root = state_of(root_observation)
    provider = ScriptedProvider(
        menus={root.semantic_key: (attack, end)},
        nodes={(root.semantic_key, attack.identity): Terminal(landing, "attack resolved")})
    context = EvaluationModel.build()
    board = ObservationStateBuilder(DECK).root(root_observation)

    price = next(item for item in price_actions(
        root, board, evaluate(board, context).total, provider, context)
                 if item.action is attack)
    realized = [item for item in price.footprint.contributions
                if item.feature == "combat.realized_ko"
                and "continuation.prize_transition" in item.provenance]

    assert [(item.activation, item.value) for item in realized] == [(1.0, 1.0)]


def test_body_ability_readiness_stops_after_the_line_is_fully_developed():
    select = {"context": 0, "minCount": 1, "maxCount": 1,
              "option": [{"cardId": DRAKLOAK, "serial": 800, "type": 7}]}
    developing = ObservationStateBuilder(DECK).root(printout(
        me=player(active=body(DRAKLOAK, 1), hand=[DRAKLOAK]), select=select))
    developed = ObservationStateBuilder(DECK).root(printout(
        me=player(active=body(DRAGAPULT, 1), bench=(body(DRAKLOAK, 2),),
                  hand=[DRAKLOAK]), select=select))
    evolve = action("evolve", (0,))
    context = EvaluationModel.build()

    assert _body_ability_ready(developing, evolve, context)
    assert not _body_ability_ready(developed, evolve, context)


def test_deck_selection_reads_the_deck_card_before_an_overlapping_hand_index():
    select = {"context": 7, "minCount": 0, "maxCount": 1,
              "deck": [{"id": 674, "serial": 800, "playerIndex": 0}],
              "option": [{"area": 1, "index": 0, "playerIndex": 0, "type": 3}]}
    board = ObservationStateBuilder(DECK).root(printout(
        me=player(active=body(673, 1), hand=[DRAKLOAK]), select=select))

    assert _body_ability_ready(
        board, action("card", (0,)), EvaluationModel.build())


def test_compound_fetch_prices_only_copies_above_total_body_capacity():
    select = {"context": 5, "minCount": 1, "maxCount": 2,
              "option": [{"cardId": DREEPY, "serial": 800, "type": 3},
                         {"cardId": DREEPY, "serial": 801, "type": 3}]}
    board = ObservationStateBuilder(DECK).root(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[DREEPY]), select=select))

    assert _body_copy_overflow(board, action("card", (0,)), EvaluationModel.build()) == 0
    assert _body_copy_overflow(board, action("card", (0, 1)), EvaluationModel.build()) == 1


def test_terminal_action_is_priced_against_the_legal_end_successor():
    play, end = action("play", (0,)), action("end", (1,))
    pass_good = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
        them=player(own=False, active=body(DRAGAPULT, 2, hp=80)), turn=3))
    providers = tuple(ScriptedProvider(
        menus={"root": (play, end)},
        nodes={("root", play.identity): Terminal(GOOD, "done"),
               ("root", end.identity): Terminal(pass_state, "passed")})
        for pass_state in (BAD, pass_good))

    swings = []
    for provider in providers:
        decision = LedgerDecider(
            DECK, "test", EvaluationModel.build(),
            provider_factory=lambda _s, **_kw: provider).decide(ROOT_OBS)
        swings.append(next(row["swing"] for row in decision.diagnostics["prices"]
                           if row["action"] == str(play.identity)))

    ctx = EvaluationModel.build()
    builder = ObservationStateBuilder(DECK)
    expected_shift = evaluate(builder.root(BAD.observation), ctx).total - evaluate(
        builder.root(pass_good.observation), ctx).total
    assert swings[1] == pytest.approx(swings[0] + expected_shift)


def _end_price(end_node, *, compute=None, valuation_fn=None):
    end = action("end", (1,))
    root = state_of(ROOT_OBS)
    key = root.semantic_key
    provider_type = ScriptedProvider
    if end_node is None:
        class UnavailableProvider(ScriptedProvider):
            def transition(self, _state, _action):
                raise KeyError("pass unavailable")
        provider_type = UnavailableProvider
    provider = provider_type(
        menus={key: (end,)},
        nodes={} if end_node is None else {(key, end.identity): end_node})
    context = EvaluationModel.build()
    board = ObservationStateBuilder(DECK).root(ROOT_OBS)
    prices = price_actions(
        root, board, evaluate(board, context).total, provider,
        context, compute=compute, valuation_fn=valuation_fn)
    return prices[0]


def test_end_counterfactual_reports_complete_estimated_and_unavailable():
    complete = _end_price(Terminal(BAD, "passed"))
    estimated = _end_price(
        Deterministic(BAD), compute=SearchConfiguration(path_node_budget=1))
    unavailable = _end_price(None)

    assert complete.status is EvaluationStatus.COMPLETE
    assert estimated.status is EvaluationStatus.ESTIMATED
    assert estimated.gaps == ("chain capped; scored mid-effect board",)
    assert unavailable.status is EvaluationStatus.UNAVAILABLE
    assert unavailable.gaps == ("end counterfactual unavailable: KeyError",)


def test_unavailable_end_counterfactual_still_returns_the_legal_failsafe():
    end = action("end", (1,))
    class UnavailableProvider(ScriptedProvider):
        def transition(self, _state, _action):
            raise KeyError("pass unavailable")
    provider = UnavailableProvider(menus={"root": (end,)}, nodes={})

    decision = LedgerDecider(
        DECK, "test", EvaluationModel.build(),
        provider_factory=lambda _state, **_kwargs: provider).decide(ROOT_OBS)

    assert decision.chosen == end.selection
    assert decision.complete is False


def test_end_successor_valuation_is_computed_once():
    counts = {}
    context = EvaluationModel.build()

    def counted(board):
        counts[board.position_key] = counts.get(board.position_key, 0) + 1
        return evaluate(board, context)

    price = _end_price(Terminal(BAD, "passed"), valuation_fn=counted)
    end_board = ObservationStateBuilder(DECK).root(BAD.observation)

    assert price.status is EvaluationStatus.COMPLETE
    assert counts[end_board.position_key] == 1


def test_generated_shared_phase_value_cancels_against_end():
    play, end = action("play", (0,)), action("end", (1,))
    root = state_of(ROOT_OBS)
    key = root.semantic_key
    provider = ScriptedProvider(
        menus={key: (play, end)},
        nodes={(key, play.identity): Terminal(GOOD, "played"),
               (key, end.identity): Terminal(BAD, "passed")})
    context = EvaluationModel.build()
    board = ObservationStateBuilder(DECK).root(ROOT_OBS)

    swings = []
    for shared_phase in (0.0, 3.0, 20.0):
        def phased(candidate):
            material = float(bool(candidate.me.active and candidate.me.active.energies))
            activation = material + shared_phase
            feature = "kind.energy"
            coefficient = context.configuration[feature]
            return Valuation(
                activation * coefficient, (), (),
                (FeatureActivation(feature, activation, ("phase",)),),
                (FeatureContribution(feature, activation, coefficient,
                                     activation * coefficient, ("phase",)),))

        prices = price_actions(
            root, board, 0.0, provider, context,
            valuation_fn=phased)
        swings.append(next(price.swing for price in prices if price.action is play))

    assert swings[0] > 0
    assert swings == pytest.approx([swings[0]] * len(swings))


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


def test_root_preview_stops_at_the_first_return_to_main():
    landing = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(2,)), hand=[]),
        them=player(own=False, active=body(DRAGAPULT, 2))))
    beyond = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(2,)), hand=[]),
        them=player(own=False, active=body(DRAGAPULT, 2, hp=0))))
    play, end = action("play", (0,)), action("end", (1,))
    second = action("attack", (2,))
    provider = ScriptedProvider(
        menus={"root": (play, end), landing.semantic_key: (second, end)},
        nodes={("root", play.identity): Deterministic(landing),
               (landing.semantic_key, second.identity): Terminal(beyond, "done")})

    decision = LedgerDecider(
        DECK, "test", EvaluationModel.build(),
        provider_factory=lambda _s, **_kw: provider).decide(ROOT_OBS)
    price = next(row for row in decision.diagnostics["prices"]
                 if row["action"] == str(play.identity))
    assert math.isfinite(price["swing"])
    assert all(str(second.identity) not in tuple(map(str, successor.action_path))
               for successor in decision.decision_result.roster.candidates[0].successors)
    assert {successor.state.position_key
            for successor in decision.decision_result.roster.candidates[0].successors} == {
                ObservationStateBuilder(DECK).root(landing.observation).position_key}


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


def test_a_wide_chance_tree_stops_evaluator_calls_at_the_path_budget(monkeypatch):
    from common.ledger import preview

    calls = 0
    actual = preview.evaluate

    def counted(board, context):
        nonlocal calls
        calls += 1
        return actual(board, context)

    monkeypatch.setattr(preview, "evaluate", counted)
    legs = tuple(WeightedEdge(1.0 / 10_000, f"leg{index}", Deterministic(GOOD))
                 for index in range(10_000))
    price_of(Chance(legs))

    assert calls <= 140


def test_information_probe_does_not_materialize_a_wide_chance_roster():
    from common.ledger.preview import _immediate_information_value

    edge = WeightedEdge(1.0, "leg", Deterministic(GOOD))

    class WideChildren:
        inspected = 0

        def __len__(self):
            return 10_000

        def __getitem__(self, key):
            assert isinstance(key, slice)
            count = min(10_000, key.stop or 10_000)
            self.inspected += count
            return (edge,) * count

    node = Chance((edge,))
    children = WideChildren()
    object.__setattr__(node, "children", children)

    _value, capped = _immediate_information_value(node, 8)

    assert capped
    assert children.inspected <= 7


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


@pytest.mark.parametrize("kind", ("play", "attach", "evolve"))
def test_realization_credits_only_the_selected_portfolio_source(kind):
    first = "feasible_option_portfolio:serial:11"
    second = "feasible_option_portfolio:serial:12"
    baseline = Valuation(0.5, (), (), contributions=(
        FeatureContribution("option.draw", 1.0, 0.2, 0.2, (first,)),
        FeatureContribution("option.draw", 1.5, 0.2, 0.3, (second,)),
    ))
    board = SimpleNamespace(select=SimpleNamespace(options=(
        SimpleNamespace(serial=11, cardId=100),
        SimpleNamespace(serial=12, cardId=100),
    )))
    selected = SimpleNamespace(
        identity=SimpleNamespace(kind=kind), selection=(0,))

    realized = _realized_portfolio_contributions(baseline, board, selected)

    assert [(item.activation, item.value) for item in realized] == [(1.0, 0.2)]
    assert first in realized[0].provenance
    assert second not in realized[0].provenance


@pytest.mark.parametrize("kind", ("play", "attach", "evolve"))
def test_realization_resolves_main_options_through_their_hand_index(kind):
    board = ObservationStateBuilder().root(printout(
        me=player(hand=[FIRE_E]),
        select={"context": 0, "minCount": 1, "maxCount": 1,
                "option": [{"area": 2, "index": 0, "type": 7}]}))
    owner = "feasible_option_portfolio:serial:800"
    baseline = Valuation(0.2, (), (), contributions=(
        FeatureContribution("option.energy", 2.0, 0.1, 0.2, (owner,)),))
    selected = SimpleNamespace(
        identity=SimpleNamespace(kind=kind), selection=(0,))

    realized = _realized_portfolio_contributions(baseline, board, selected)

    assert [(item.activation, item.value) for item in realized] == [(2.0, 0.2)]


def test_discard_spend_charges_selected_live_portfolio_sources_only():
    first = "feasible_option_portfolio:serial:11"
    second = "feasible_option_portfolio:serial:12"
    baseline = Valuation(0.5, (), (), contributions=(
        FeatureContribution("option.draw", 1.0, 0.2, 0.2, (first,)),
        FeatureContribution("option.draw", 1.5, 0.2, 0.3, (second,)),
    ))
    board = SimpleNamespace(
        select=SimpleNamespace(context=8, options=(
            SimpleNamespace(serial=11, cardId=100),
            SimpleNamespace(serial=12, cardId=101))),
        me=SimpleNamespace(hand=()))
    selected = SimpleNamespace(
        identity=SimpleNamespace(kind="card"), selection=(0,))

    spent = _discard_spend_contributions(baseline, board, selected)

    assert [(item.activation, item.value) for item in spent] == [(-1.0, -0.2)]
    assert "action.discard_spend" in spent[0].provenance


def test_discard_spend_does_not_charge_a_portfolio_source_with_a_held_replacement():
    owner = "feasible_option_portfolio:serial:11"
    baseline = Valuation(0.2, (), (), contributions=(
        FeatureContribution("option.draw", 1.0, 0.2, 0.2, (owner,)),))
    board = SimpleNamespace(
        select=SimpleNamespace(context=8, options=(
            SimpleNamespace(serial=11, cardId=100),)),
        me=SimpleNamespace(hand=(
            SimpleNamespace(serial=11, card_id=100),
            SimpleNamespace(serial=12, card_id=100))))
    selected = SimpleNamespace(
        identity=SimpleNamespace(kind="card"), selection=(0,))

    assert _discard_spend_contributions(baseline, board, selected) == ()
