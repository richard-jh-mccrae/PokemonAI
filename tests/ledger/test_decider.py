"""The decider's turn policy over a scripted transition seam: spend, then end best.

A fake provider returns prepared algebra nodes, so these pin the POLICY (turn split, forced
argmax, chain resolution, refresh sampling determinism) without an engine in the loop."""
from __future__ import annotations

from ledger_helpers import (DARK_E, DARKNESS, DRAGAPULT, DRAKLOAK, DREEPY, FIRE, FIRE_E,
                            HARLEQUIN, LILLIES, PSYCHIC, ScriptedProvider, action, body,
                            player, printout)

import pytest

from common.algebra import Deterministic, Refresh, Terminal, Unknown
from common.ledger import LedgerContext, LedgerDecider
from common.ledger.decider import LedgerUnavailable
from common.state import DecisionState


def make_decider(provider, deck=(DRAGAPULT, FIRE_E, DARK_E) * 20, sink=None):
    return LedgerDecider(deck, "test", LedgerContext.build(),
                         provider_factory=lambda _state, **_kw: provider, gap_sink=sink)


def state_of(observation, deck):
    identity = f"ledger:{LedgerContext.build().weights.identity}"
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


def test_refresh_pricing_is_deterministic_and_reports_no_false_gaps():
    """Lillie's through the sampled-hand chance model: same frame, same price, every time —
    and a fully-modelled frame reports an empty gap list."""
    hand = [LILLIES, DARK_E, DARK_E]
    root_obs = printout(me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC)),
                                  hand=hand, deck_count=40),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    deck = tuple([DRAGAPULT] * 10 + [FIRE_E] * 20 + [DARK_E] * 10 + hand)
    play, end = action("play", (0,)), action("end", (1,))
    provider = ScriptedProvider(
        menus={"root": (play, end)},
        nodes={("root", play.identity): Refresh(LILLIES, ((6, 0),), False)})
    decider = LedgerDecider(deck, "test", LedgerContext.build(),
                            provider_factory=lambda _state, **_kw: provider)
    first = decider.decide(root_obs)
    second = decider.decide(root_obs)
    prices = {entry["action"]: entry["swing"] for entry in first.diagnostics["prices"]}
    again = {entry["action"]: entry["swing"] for entry in second.diagnostics["prices"]}
    assert prices == again
    assert first.diagnostics["gaps"] == []


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
        decision = LedgerDecider(deck, "test", LedgerContext.build(),
                                 provider_factory=lambda _s, **_kw: provider).decide(root_obs)
        return {entry["action"]: entry["swing"]
                for entry in decision.diagnostics["prices"]}[str(play.identity)]

    context = LedgerContext.build()
    from common.ledger.worth import base_worth
    assert (base_worth(DARK_E, context.facts(DARK_E), context)
            == base_worth(FIRE_E, context.facts(FIRE_E), context))
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
        decision = LedgerDecider(deck, "test", LedgerContext.build(),
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


def test_equal_swings_break_to_the_lowest_engine_selection():
    """Two plays land on the SAME successor: identical swings, so the replayable total order
    must pick the lower selection no matter how the menu lists them."""
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E, FIRE_E]),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    attached = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE,)), hand=[FIRE_E]),
        them=player(own=False, active=body(DRAGAPULT, 2))), DECK)
    first, second, end = action("attach", (0,)), action("attach", (1,)), action("end", (2,))
    nodes = {("root", first.identity): Deterministic(attached),
             ("root", second.identity): Deterministic(attached)}
    for menu in ((first, second, end), (second, first, end)):
        provider = ScriptedProvider(menus={"root": menu}, nodes=nodes)
        assert make_decider(provider).decide(root_obs).chosen == (0,)


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

    decider = LedgerDecider(DECK, "test", LedgerContext.build(),
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
        decision = LedgerDecider(deck, "test", LedgerContext.build(),
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
