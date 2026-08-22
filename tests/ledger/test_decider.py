"""The decider's turn policy over a scripted transition seam: spend, then end best.

A fake provider returns prepared algebra nodes, so these pin the POLICY (turn split, forced
argmax, chain resolution, refresh sampling determinism) without an engine in the loop."""
from __future__ import annotations

from ledger_helpers import (DARK_E, DARKNESS, DRAGAPULT, DRAKLOAK, DREEPY, FIRE, FIRE_E,
                            HARLEQUIN, LILLIES, PSYCHIC, PSYCHIC_E, ScriptedProvider, action, body,
                            player, printout)

import pytest

from common.algebra import Deterministic, Refresh, Terminal, Unknown
from common.ledger import EvaluationModel, LedgerDecider, PrizeMap
from common.ledger.decider import LedgerUnavailable
from deprecated.bellman.state import DecisionState


def make_decider(provider, deck=(DRAGAPULT, FIRE_E, DARK_E) * 20, sink=None):
    return LedgerDecider(deck, "test", EvaluationModel.build(),
                         provider_factory=lambda _state, **_kw: provider, gap_sink=sink)


def state_of(observation, deck):
    identity = f"ledger:{EvaluationModel.build().behavior_identity}"
    return DecisionState.from_observation(observation, deck=tuple(deck), deck_name="test",
                                          value_registry_identity=identity)


DECK = (DRAGAPULT, FIRE_E, DARK_E) * 20


def test_positive_develop_beats_a_bigger_turn_ender():
    """The attack swings more, but attaching first keeps the turn alive: spend, then end."""
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    attached = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE,)), hand=[]),
        them=player(own=False, active=body(DRAGAPULT, 2))), DECK)
    struck = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
        them=player(own=False, active=body(DRAGAPULT, 2, hp=30))), DECK)

    attach, attack, end = action("attach", (0,)), action("attack", (1,)), action("end", (2,))
    provider = ScriptedProvider(
        menus={"root": (attach, attack, end)},
        nodes={("root", attach.identity): Deterministic(attached),
               ("root", attack.identity): Terminal(struck, "attack resolved")})
    decision = make_decider(provider).decide(root_obs)
    assert decision.action.kind == "attach"


def test_with_nothing_worth_doing_the_best_ender_wins():
    root_obs = printout(me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC)),
                                  hand=[DARK_E]),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    dark_attached = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC, DARKNESS)), hand=[]),
        them=player(own=False, active=body(DRAGAPULT, 2))), DECK)
    struck = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC)), hand=[DARK_E]),
        them=player(own=False, active=body(DRAGAPULT, 2, hp=0))), DECK)

    attach, attack, end = action("attach", (0,)), action("attack", (1,)), action("end", (2,))
    provider = ScriptedProvider(
        menus={"root": (attach, attack, end)},
        nodes={("root", attach.identity): Deterministic(dark_attached),
               ("root", attack.identity): Terminal(struck, "attack resolved")})
    decision = make_decider(provider).decide(root_obs)
    assert decision.action.kind == "attack"
    prices = {entry["action"]: entry["swing"] for entry in decision.diagnostics["prices"]}
    assert prices[str(attach.identity)] < 0


def test_forced_menu_is_a_straight_argmax():
    """No End exists mid-effect: the least-bad discard is taken even though every swing < 0."""
    select = {"type": 1, "context": 7, "minCount": 1, "maxCount": 1,
              "option": [{"type": 3, "index": 0}, {"type": 3, "index": 1}],
              "deck": None, "contextCard": None, "effect": None,
              "remainDamageCounter": 0, "remainEnergyCost": 0}
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E, DARK_E]),
                        select=select)
    lost_fire = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[DARK_E], discard=[FIRE_E])), DECK)
    lost_dark = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E], discard=[DARK_E])), DECK)

    toss_fire, toss_dark = action("discard", (0,)), action("discard", (1,))
    provider = ScriptedProvider(
        menus={"root": (toss_fire, toss_dark)},
        nodes={("root", toss_fire.identity): Deterministic(lost_fire),
               ("root", toss_dark.identity): Deterministic(lost_dark)})
    decision = make_decider(provider).decide(root_obs)
    assert decision.action == toss_dark.identity


def test_forced_chain_resolves_to_the_best_leaf():
    """play -> forced pick -> main: the play's price is the best sub-choice's resolved board."""
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    mid_select = {"type": 1, "context": 7, "minCount": 1, "maxCount": 1,
                  "option": [{"type": 3, "index": 0}], "deck": None, "contextCard": None,
                  "effect": None, "remainDamageCounter": 0, "remainEnergyCost": 0}
    mid = state_of(printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
                            select=mid_select), DECK)
    good_leaf = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE,)), hand=[])), DECK)
    bad_leaf = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[], discard=[FIRE_E])), DECK)

    play, end = action("play", (0,)), action("end", (1,))
    pick_good, pick_bad = action("card", (0,)), action("card", (1,))
    provider = ScriptedProvider(
        menus={"root": (play, end),
               mid.semantic_key: (pick_good, pick_bad)},
        nodes={("root", play.identity): Deterministic(mid),
               (mid.semantic_key, pick_good.identity): Deterministic(good_leaf),
               (mid.semantic_key, pick_bad.identity): Deterministic(bad_leaf)})
    decision = make_decider(provider).decide(root_obs)
    assert decision.action.kind == "play"
    assert decision.value > 0


def test_refresh_pricing_is_deterministic_and_reports_missing_successor_inventory():
    """Lillie's through the sampled-hand chance model: same frame, same price, every time —
    and an incomplete scripted successor inventory reports its coverage gap."""
    hand = [LILLIES, DARK_E, DARK_E]
    root_obs = printout(me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC)),
                                  hand=hand, deck_count=40),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    deck = tuple([DRAGAPULT] * 10 + [FIRE_E] * 20 + [DARK_E] * 10 + hand)
    play, end = action("play", (0,)), action("end", (1,))
    provider = ScriptedProvider(
        menus={"root": (play, end)},
        nodes={("root", play.identity): Refresh(LILLIES, ((6, 0),), False)})
    decider = LedgerDecider(deck, "test", EvaluationModel.build(),
                            provider_factory=lambda _state, **_kw: provider)
    first = decider.decide(root_obs)
    second = decider.decide(root_obs)
    prices = {entry["action"]: entry["swing"] for entry in first.diagnostics["prices"]}
    again = {entry["action"]: entry["swing"] for entry in second.diagnostics["prices"]}
    assert prices == again
    assert "continuation action inventory unavailable: KeyError" in first.diagnostics["gaps"]


def test_lillies_prices_higher_when_the_hand_it_shuffles_away_is_dead():
    """The supporter-decision handoff's core demand: the play is judged by the states it
    produces, so trading a dead hand for six draws beats trading a live one. Both hands are
    two basic energies of EQUAL base worth (pinned below) and the shuffle pool is the same
    multiset either way, so demand liveness is the ONLY thing separating the two swings —
    with the demand system deleted, this fails."""
    deck = tuple([LILLIES] + [DARK_E] * 2 + [FIRE_E] * 42)

    def swing_of(extra_hand):
        hand = [LILLIES] + extra_hand
        root_obs = printout(me=player(active=body(DREEPY, 1), hand=hand, deck_count=40),
                            them=player(own=False, active=body(DRAGAPULT, 2)))
        play, end = action("play", (0,)), action("end", (1,))
        provider = ScriptedProvider(
            menus={"root": (play, end)},
            nodes={("root", play.identity): Refresh(LILLIES, ((6, 0),), False)})
        decision = LedgerDecider(deck, "test", EvaluationModel.build(),
                                 provider_factory=lambda _s, **_kw: provider).decide(root_obs)
        return {entry["action"]: entry["swing"]
                for entry in decision.diagnostics["prices"]}[str(play.identity)]

    context = EvaluationModel.build()
    assert context.facts(DARK_E).kind == context.facts(FIRE_E).kind
    dead_hand = [DARK_E, DARK_E]        # Dreepy has no dark or colorless slot: dead cards
    live_hand = [FIRE_E, FIRE_E]        # fire fills Bite's typed partner slot on Dreepy
    assert swing_of(dead_hand) > swing_of(live_hand) + 0.05


def test_harlequin_two_leg_ev_prices_the_opponents_redraw():
    """Both coin legs average, and shuffling a FAT opponent hand down to a redraw is worth
    more than shuffling a thin one up."""
    deck = tuple([DRAGAPULT] * 10 + [FIRE_E] * 30)

    def swing_against(opponent_hand_count):
        root_obs = printout(
            me=player(active=body(DREEPY, 1), hand=[HARLEQUIN, DARK_E], deck_count=40),
            them=player(own=False, active=body(DRAGAPULT, 2),
                        hand_count=opponent_hand_count))
        play, end = action("play", (0,)), action("end", (1,))
        provider = ScriptedProvider(
            menus={"root": (play, end)},
            nodes={("root", play.identity):
                   Refresh(HARLEQUIN, ((5, 3), (3, 5)), True)})
        decision = LedgerDecider(deck, "test", EvaluationModel.build(),
                                 provider_factory=lambda _s, **_kw: provider).decide(root_obs)
        return {entry["action"]: entry["swing"]
                for entry in decision.diagnostics["prices"]}[str(play.identity)]

    assert swing_against(8) > swing_against(2)


def test_unknown_node_decides_anyway_and_sinks_the_gap():
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]))
    weird, end = action("ability", (0,)), action("end", (1,))
    provider = ScriptedProvider(
        menus={"root": (weird, end)},
        nodes={("root", weird.identity): Unknown("no model", "mystery clause")})
    records = []
    decision = make_decider(provider, sink=records.append).decide(root_obs)
    # The unpriced ability reads swing 0: nothing clears the noise floor, so the End is taken.
    assert decision.chosen == (1,)
    assert records and any("mystery clause" in gap for gap in records[0]["gaps"])


def test_equal_swings_use_a_reproducible_neutral_lottery():
    from common.api import ActionIdentity
    from common.ledger.preview import OptionPrice
    from types import SimpleNamespace

    first = OptionPrice(SimpleNamespace(
        selection=[0], identity=ActionIdentity("attach", ("candidate-a",))), 0.1, False, ())
    second = OptionPrice(SimpleNamespace(
        selection=[1], identity=ActionIdentity("attach", ("candidate-b",))), 0.1, False, ())
    decider = make_decider(provider=None)

    chosen = decider._choose((first, second), forced=False)
    relabeled = (
        OptionPrice(SimpleNamespace(selection=[0], identity=ActionIdentity("play", (999,))),
                    0.1, False, ()),
        OptionPrice(SimpleNamespace(selection=[1], identity=ActionIdentity("attack", (1,))),
                    0.1, False, ()),
    )
    assert decider._choose((first, second), forced=False) is chosen
    assert decider._choose(relabeled, forced=False).action.selection == chosen.action.selection


def test_a_menu_with_no_ender_takes_the_least_bad_option():
    """Main phase, every swing negative, and the script offers no End at all: the fallback
    ranks the full price list instead of refusing to answer."""
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E, DARK_E]))
    lost_fire = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[DARK_E], discard=[FIRE_E])), DECK)
    lost_both = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[], discard=[FIRE_E, DARK_E])), DECK)
    toss_one, toss_two = action("discard", (0,)), action("discard", (1,))
    provider = ScriptedProvider(
        menus={"root": (toss_one, toss_two)},
        nodes={("root", toss_one.identity): Deterministic(lost_fire),
               ("root", toss_two.identity): Deterministic(lost_both)})
    decision = make_decider(provider).decide(root_obs)
    assert decision.action == toss_one.identity
    assert decision.value < 0


def test_an_empty_menu_raises_ledger_unavailable():
    provider = ScriptedProvider(menus={"root": ()}, nodes={})
    with pytest.raises(LedgerUnavailable):
        make_decider(provider).decide(printout(me=player(active=body(DRAGAPULT, 1))))


def test_an_unavailable_provider_raises_ledger_unavailable():
    class DeadProvider:
        available = False
        _error = "engine session refused"

        def __init__(self, *_args, **_kwargs):
            pass

    decider = LedgerDecider(DECK, "test", EvaluationModel.build(),
                            provider_factory=lambda _s, **_kw: DeadProvider())
    with pytest.raises(LedgerUnavailable):
        decider.decide(printout(me=player(active=body(DRAGAPULT, 1))))


def test_harlequin_legs_average_exactly_on_a_uniform_pool():
    """With every card in the shuffle pool identical, sampling is exact, so the two-leg price
    must equal the average of the single-leg prices — dropping a coin leg fails loudly."""
    deck = tuple([HARLEQUIN] + [FIRE_E] * 44)

    def price(draws):
        root_obs = printout(
            me=player(active=body(DREEPY, 1), hand=[HARLEQUIN], deck_count=40),
            them=player(own=False, active=body(DRAGAPULT, 2), hand_count=5))
        play, end = action("play", (0,)), action("end", (1,))
        provider = ScriptedProvider(
            menus={"root": (play, end)},
            nodes={("root", play.identity): Refresh(HARLEQUIN, draws, True)})
        decision = LedgerDecider(deck, "test", EvaluationModel.build(),
                                 provider_factory=lambda _s, **_kw: provider).decide(root_obs)
        return {entry["action"]: entry["swing"]
                for entry in decision.diagnostics["prices"]}[str(play.identity)]

    both_legs = price(((5, 3), (3, 5)))
    assert both_legs == pytest.approx(
        (price(((5, 3),)) + price(((3, 5),))) / 2, abs=1e-9)


def test_a_refresh_for_a_card_not_in_hand_logs_the_gap_and_decides_anyway():
    root_obs = printout(me=player(active=body(DREEPY, 1), hand=[FIRE_E], deck_count=40),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    play, end = action("play", (0,)), action("end", (1,))
    provider = ScriptedProvider(
        menus={"root": (play, end)},
        nodes={("root", play.identity): Refresh(LILLIES, ((6, 0),), False)})
    decision = make_decider(provider).decide(root_obs)
    assert decision.chosen
    assert any("not visible in hand" in gap for gap in decision.diagnostics["gaps"])


def _price(kind, index, swing, *, ends=False, refresh=False, prize_map=None):
    from types import SimpleNamespace

    from common.ledger.preview import OptionPrice

    return OptionPrice(
        SimpleNamespace(selection=[index], identity=SimpleNamespace(kind=kind)),
        swing, ends, (), prize_map=prize_map)


def test_prize_plan_does_not_preempt_the_neutral_lottery_for_near_equal_prices():
    decider = make_decider(provider=None)
    preferred = PrizeMap(3, (1,), 1, 0, (1,))
    ordinary = PrizeMap(3, (2,), 1, 0, (0,))
    prices = (_price("play", 0, 1.0, prize_map=preferred),
              _price("play", 1, 1.0 - 5e-10, prize_map=ordinary))

    assert decider._ranked(prices)[0].action.selection == [1]


def test_continuing_options_rank_only_by_configured_price():
    decider = make_decider(provider=None)
    prices = (_price("attach", 0, 0.05), _price("play", 1, 0.40, refresh=True),
              _price("end", 2, 0.0, ends=True))
    assert decider._choose(prices, forced=False).action.identity.kind == "play"


def test_a_positive_hand_shuffle_alone_still_gets_played():
    decider = make_decider(provider=None)
    prices = (_price("play", 0, 0.40, refresh=True), _price("end", 1, 0.0, ends=True))
    assert decider._choose(prices, forced=False).action.identity.kind == "play"


def test_price_actions_has_no_mechanic_specific_ordering_flags():
    from common.observation import KnownOwnPrizes, ObservationStateBuilder
    from common.ledger import PreviewState, evaluate
    from common.ledger.preview import price_actions

    hand = [FIRE_E, LILLIES]
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=hand),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    attached = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE,)), hand=[LILLIES]),
        them=player(own=False, active=body(DRAGAPULT, 2))), DECK)
    attach, play, end = action("attach", (0,)), action("play", (1,)), action("end", (2,))
    provider = ScriptedProvider(
        menus={"root": (attach, play, end)},
        nodes={("root", attach.identity): Deterministic(attached),
               ("root", play.identity): Refresh(LILLIES, ((6, 0),), False)})
    ctx = EvaluationModel.build()
    board = ObservationStateBuilder(DECK).root(root_obs)
    state = PreviewState(root_obs, board, "root", deck=DECK,
                         deck_counts=board.deck_counts or (),
                         prize_counts=(board.knowledge.own_prizes.cards
                                       if isinstance(board.knowledge.own_prizes,
                                                     KnownOwnPrizes) else ()))
    prices = price_actions(state, board, evaluate(board, ctx).total, provider, ctx)
    assert all(not hasattr(price, "refresh") and not hasattr(price, "restocks")
               for price in prices)
    assert all(sum(item.value for item in price.footprint.contributions)
               == pytest.approx(price.swing) for price in prices)


def test_action_opportunity_cost_hands_a_small_positive_turn_to_the_ender():
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    attached = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE,)), hand=[]),
        them=player(own=False, active=body(DRAGAPULT, 2))), DECK)
    attach, end = action("attach", (0,)), action("end", (1,))
    provider = ScriptedProvider(
        menus={"root": (attach, end)},
        nodes={("root", attach.identity): Deterministic(attached)})
    from common.ledger import DeckOverlay
    lifted = LedgerDecider(DECK, "test", EvaluationModel.build(
        overlay=DeckOverlay({"action.opportunity_cost": 5.0})),
                           provider_factory=lambda _s, **_kw: provider).decide(root_obs)
    assert lifted.action.kind == "end"
    default = make_decider(provider).decide(root_obs)
    assert default.action.kind == "attach"


def test_continuation_footprint_compares_successor_legal_actions():
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]))
    successor = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE,)), hand=[])), DECK)
    attach, attack, end = action("attach", (0,)), action("attack", (1,)), action("end", (2,))
    provider = ScriptedProvider(
        menus={"root": (attach, end), successor.semantic_key: (attack, end)},
        nodes={("root", attach.identity): Deterministic(successor)})

    decision = make_decider(provider).decide(root_obs)
    price = next(row for row in decision.diagnostics["prices"]
                 if row["action"] == str(attach.identity))
    footprint = price["continuation"]
    assert "attack" in footprint["opportunities_created"]
    assert "end" in footprint["opportunities_preserved"]
    assert "attach" in footprint["opportunities_consumed"]


def test_no_card_or_mechanic_specific_ordering_branch_remains():
    decider = make_decider(provider=None)
    attach = _price("attach", 0, 0.05)
    fetch = _price("play", 1, 0.10)
    shuffle = _price("play", 2, 0.40, refresh=True)
    end = _price("end", 3, 0.0, ends=True)

    assert decider._choose((attach, fetch, shuffle, end),
                           forced=False).action.selection == [2]
    assert decider._choose((fetch, shuffle, end),
                           forced=False).action.selection == [2]   # shuffle before fetch
    assert decider._choose((fetch, end),
                           forced=False).action.selection == [1]   # no shuffle: fetch normal


def test_decider_has_no_restock_classifier():
    decider = make_decider(provider=None)
    assert not hasattr(decider, "_restocks_hand")
