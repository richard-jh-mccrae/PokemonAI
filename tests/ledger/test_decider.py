"""The decider's turn policy over a scripted transition seam: spend, then end best.

A fake provider returns prepared algebra nodes, so these pin the POLICY (turn split, forced
argmax, chain resolution, refresh sampling determinism) without an engine in the loop."""
from __future__ import annotations

from ledger_helpers import (DARK_E, DARKNESS, DRAGAPULT, DRAKLOAK, DREEPY, FIRE, FIRE_E,
                            HARLEQUIN, LILLIES, PSYCHIC, body, player, printout)

from common.algebra import Actor, Deterministic, Refresh, Terminal, Unknown
from common.api import ActionIdentity
from common.ledger import LedgerContext, LedgerDecider
from common.options import LegalAction
from common.state import DecisionState


def action(kind: str, selection: tuple[int, ...]) -> LegalAction:
    return LegalAction(ActionIdentity(kind, (selection,)), selection, (selection,), ())


class ScriptedProvider:
    """actions/transition/actor from a prepared script keyed by (semantic_key, identity)."""

    available = True

    def __init__(self, menus, nodes):
        self._menus = menus            # semantic_key -> tuple[LegalAction, ...]
        self._nodes = nodes            # (semantic_key, identity) -> node

    def actions(self, state):
        return self._menus[state.semantic_key]

    def transition(self, state, act):
        return self._nodes[(state.semantic_key, act.identity)]

    def actor(self, _state):
        return Actor.OURS

    def close(self):
        pass


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
    root = state_of(root_obs, DECK)
    attached = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE,)), hand=[]),
        them=player(own=False, active=body(DRAGAPULT, 2))), DECK)
    struck = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
        them=player(own=False, active=body(DRAGAPULT, 2, hp=30))), DECK)

    attach, attack, end = action("attach", (0,)), action("attack", (1,)), action("end", (2,))
    provider = ScriptedProvider(
        menus={root.semantic_key: (attach, attack, end)},
        nodes={(root.semantic_key, attach.identity): Deterministic(attached),
               (root.semantic_key, attack.identity): Terminal(struck, "attack resolved")})
    decision = make_decider(provider).decide(root_obs)
    assert decision.action.kind == "attach"


def test_with_nothing_worth_doing_the_best_ender_wins():
    root_obs = printout(me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC)),
                                  hand=[DARK_E]),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    root = state_of(root_obs, DECK)
    dark_attached = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC, DARKNESS)), hand=[]),
        them=player(own=False, active=body(DRAGAPULT, 2))), DECK)
    struck = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC)), hand=[DARK_E]),
        them=player(own=False, active=body(DRAGAPULT, 2, hp=0))), DECK)

    attach, attack, end = action("attach", (0,)), action("attack", (1,)), action("end", (2,))
    provider = ScriptedProvider(
        menus={root.semantic_key: (attach, attack, end)},
        nodes={(root.semantic_key, attach.identity): Deterministic(dark_attached),
               (root.semantic_key, attack.identity): Terminal(struck, "attack resolved")})
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
    root = state_of(root_obs, DECK)
    lost_fire = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[DARK_E], discard=[FIRE_E])), DECK)
    lost_dark = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E], discard=[DARK_E])), DECK)

    toss_fire, toss_dark = action("discard", (0,)), action("discard", (1,))
    provider = ScriptedProvider(
        menus={root.semantic_key: (toss_fire, toss_dark)},
        nodes={(root.semantic_key, toss_fire.identity): Deterministic(lost_fire),
               (root.semantic_key, toss_dark.identity): Deterministic(lost_dark)})
    decision = make_decider(provider).decide(root_obs)
    assert decision.action == toss_dark.identity


def test_forced_chain_resolves_to_the_best_leaf():
    """play -> forced pick -> main: the play's price is the best sub-choice's resolved board."""
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    root = state_of(root_obs, DECK)
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
        menus={root.semantic_key: (play, end),
               mid.semantic_key: (pick_good, pick_bad)},
        nodes={(root.semantic_key, play.identity): Deterministic(mid),
               (mid.semantic_key, pick_good.identity): Deterministic(good_leaf),
               (mid.semantic_key, pick_bad.identity): Deterministic(bad_leaf)})
    decision = make_decider(provider).decide(root_obs)
    assert decision.action.kind == "play"
    assert decision.value > 0


def test_refresh_pricing_is_deterministic_and_reports_no_false_gaps():
    """Lillie's through the sampled-hand chance model: same frame, same price, every time."""
    hand = [LILLIES, DARK_E, DARK_E]
    root_obs = printout(me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC)),
                                  hand=hand, deck_count=40),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    deck = tuple([DRAGAPULT] * 10 + [FIRE_E] * 20 + [DARK_E] * 10 + hand)
    root = state_of(root_obs, deck)
    play, end = action("play", (0,)), action("end", (1,))
    provider = ScriptedProvider(
        menus={root.semantic_key: (play, end)},
        nodes={(root.semantic_key, play.identity): Refresh(LILLIES, ((6, 0),), False)})
    decider = LedgerDecider(deck, "test", LedgerContext.build(),
                            provider_factory=lambda _state, **_kw: provider)
    first = decider.decide(root_obs)
    second = decider.decide(root_obs)
    prices = {entry["action"]: entry["swing"] for entry in first.diagnostics["prices"]}
    again = {entry["action"]: entry["swing"] for entry in second.diagnostics["prices"]}
    assert prices == again


def test_lillies_prices_higher_when_the_hand_it_shuffles_away_is_dead():
    """The supporter-decision handoff's core demand: the play is judged by the states it
    produces, so trading a dead hand for six draws beats trading a live one."""
    deck = tuple([DRAGAPULT] * 10 + [FIRE_E] * 30)

    def swing_of(extra_hand):
        hand = [LILLIES] + extra_hand
        root_obs = printout(me=player(active=body(DREEPY, 1), hand=hand, deck_count=40),
                            them=player(own=False, active=body(DRAGAPULT, 2)))
        root = state_of(root_obs, deck)
        play, end = action("play", (0,)), action("end", (1,))
        provider = ScriptedProvider(
            menus={root.semantic_key: (play, end)},
            nodes={(root.semantic_key, play.identity): Refresh(LILLIES, ((6, 0),), False)})
        decision = LedgerDecider(deck, "test", LedgerContext.build(),
                                 provider_factory=lambda _s, **_kw: provider).decide(root_obs)
        return {entry["action"]: entry["swing"]
                for entry in decision.diagnostics["prices"]}[str(play.identity)]

    dead_hand = [DARK_E, DARK_E]        # Dreepy has no dark or colorless slot: dead cards
    live_hand = [DRAKLOAK, DRAKLOAK]    # live evolutions of the in-play Dreepy
    assert swing_of(dead_hand) > swing_of(live_hand)


def test_harlequin_two_leg_ev_prices_the_opponents_redraw():
    """Both coin legs average, and shuffling a FAT opponent hand down to a redraw is worth
    more than shuffling a thin one up."""
    deck = tuple([DRAGAPULT] * 10 + [FIRE_E] * 30)

    def swing_against(opponent_hand_count):
        root_obs = printout(
            me=player(active=body(DREEPY, 1), hand=[HARLEQUIN, DARK_E], deck_count=40),
            them=player(own=False, active=body(DRAGAPULT, 2),
                        hand_count=opponent_hand_count))
        root = state_of(root_obs, deck)
        play, end = action("play", (0,)), action("end", (1,))
        provider = ScriptedProvider(
            menus={root.semantic_key: (play, end)},
            nodes={(root.semantic_key, play.identity):
                   Refresh(HARLEQUIN, ((5, 3), (3, 5)), True)})
        decision = LedgerDecider(deck, "test", LedgerContext.build(),
                                 provider_factory=lambda _s, **_kw: provider).decide(root_obs)
        return {entry["action"]: entry["swing"]
                for entry in decision.diagnostics["prices"]}[str(play.identity)]

    assert swing_against(8) > swing_against(2)


def test_unknown_node_decides_anyway_and_sinks_the_gap():
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]))
    root = state_of(root_obs, DECK)
    weird, end = action("ability", (0,)), action("end", (1,))
    provider = ScriptedProvider(
        menus={root.semantic_key: (weird, end)},
        nodes={(root.semantic_key, weird.identity): Unknown("no model", "mystery clause")})
    records = []
    decision = make_decider(provider, sink=records.append).decide(root_obs)
    assert decision.chosen == (1,)  # the unpriced ability reads 0, the end tie-break wins
    assert records and any("mystery clause" in gap for gap in records[0]["gaps"])
