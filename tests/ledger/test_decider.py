"""The decider's turn policy over a scripted transition seam: spend, then end best.

A fake provider returns prepared algebra nodes, so these pin the POLICY (turn split, forced
argmax, chain resolution, refresh sampling determinism) without an engine in the loop."""
from __future__ import annotations

from dataclasses import replace

from ledger_helpers import (DARK_E, DARKNESS, DRAGAPULT, DRAKLOAK, DREEPY, FIRE, FIRE_E,
                            HARLEQUIN, LILLIES, PSYCHIC, PSYCHIC_E, ScriptedProvider, action, body,
                            player, printout)

import pytest

from common.algebra import Deterministic, Refresh, Terminal, Unknown
from common.decision import (CandidateDisposition, CandidateRoster, DecisionDelta,
                             ComputeConfiguration, EvaluationStatus, SearchConfiguration,
                             ValuedCandidate)
from common.ledger import EvaluationModel, LedgerDecider, PrizeMap
from common.ledger.decider import LedgerUnavailable
from common.ledger.decision import LEDGER_VALUE_SCALE
from common.ledger.search import GreedyDecisionPolicy
from common.ledger.preview import ContinuationFootprint
from common.scouting.provider import CardStat, DictCardStatProvider
from deprecated.bellman.state import DecisionState


def make_decider(provider, deck=(DRAGAPULT, FIRE_E, DARK_E) * 20, sink=None):
    return LedgerDecider(deck, "test", EvaluationModel.build(),
                         provider_factory=lambda _state, **_kw: provider, gap_sink=sink)


def choose_prices(decider, prices, *, forced=False):
    candidates = tuple(ValuedCandidate(
        price.action,
        DecisionDelta(price.swing, LEDGER_VALUE_SCALE),
        (CandidateDisposition.FORCED if forced else
         CandidateDisposition.ENDS_TURN if price.ends_turn
         else CandidateDisposition.CONTINUES_TURN),
        EvaluationStatus.COMPLETE,
        continuation=price.footprint,
        policy_tie_break=(() if price.prize_map is None
                          else price.prize_map.plan_rank_key()),
        policy_evidence=price.prize_map,
    ) for price in prices)
    chosen = GreedyDecisionPolicy().choose(
        CandidateRoster(candidates, forced), decider.compute.policy).action
    return next(price for price in prices if price.action is chosen)


def state_of(observation, deck):
    identity = f"ledger:{EvaluationModel.build().identity}"
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
    assert decision.decision_result.chosen is decision.decision_result.roster.candidates[0].action


def test_main_phase_preview_does_not_price_a_second_independent_action():
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    attached = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE,)), hand=[]),
        them=player(own=False, active=body(DRAGAPULT, 2))), DECK)
    weak = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
        them=player(own=False, active=body(DRAGAPULT, 2, hp=30))), DECK)
    strong = state_of(printout(
        me=player(active=body(DRAGAPULT, 1, energies=(FIRE,)), hand=[]),
        them=player(own=False, active=body(DRAGAPULT, 2, hp=0))), DECK)

    attach = action("attach", (0,))
    weak_attack = action("attack", (1,))
    follow_attack = action("attack", (2,))
    end = action("end", (3,))
    provider = ScriptedProvider(
        menus={"root": (attach, weak_attack, end),
               attached.semantic_key: (follow_attack, end)},
        nodes={("root", attach.identity): Deterministic(attached),
               ("root", weak_attack.identity): Terminal(weak, "attack resolved"),
               (attached.semantic_key, follow_attack.identity):
                   Terminal(strong, "attack resolved")})

    decision = LedgerDecider(
        DECK, "test", EvaluationModel.build(),
        provider_factory=lambda _state, **_kw: provider,
    ).decide(root_obs)
    prices = {row["action"]: row["swing"] for row in decision.diagnostics["prices"]}
    assert prices[str(weak_attack.identity)] > prices[str(attach.identity)]
    attach_candidate = decision.decision_result.roster.candidates[0]
    assert all(follow_attack.identity not in successor.action_path
               for successor in attach_candidate.successors)


def test_one_ply_prefers_an_immediate_gain_over_an_unchanged_landing():
    root_obs = printout(me=player(active=body(DRAGAPULT, 1)),
                        them=player(own=False, active=body(DRAGAPULT, 2)))
    waiting = state_of(root_obs, DECK)
    developed = state_of(printout(
        me=player(active=body(DRAGAPULT, 1)),
        them=player(own=False, active=body(DRAGAPULT, 2, hp=30))), DECK)

    develop = action("play", (0,))
    wait = action("retreat", (1,))
    late_develop = action("play", (2,))
    end = action("end", (3,))
    provider = ScriptedProvider(
        menus={"root": (develop, wait, end),
               waiting.semantic_key: (late_develop, end),
               developed.semantic_key: (end,)},
        nodes={("root", develop.identity): Deterministic(developed),
               ("root", wait.identity): Deterministic(waiting),
               (waiting.semantic_key, late_develop.identity): Deterministic(developed)})

    decision = LedgerDecider(
        DECK, "test", EvaluationModel.build(),
        provider_factory=lambda _state, **_kw: provider,
    ).decide(root_obs)
    prices = {row["action"]: row["swing"] for row in decision.diagnostics["prices"]}

    assert decision.action == develop.identity
    assert prices[str(develop.identity)] > prices[str(wait.identity)]


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


def test_forced_singleton_still_reports_its_successor_delta():
    select = {"type": 1, "context": 7, "minCount": 1, "maxCount": 1,
              "option": [{"type": 3, "index": 0}], "deck": None,
              "contextCard": None, "effect": None,
              "remainDamageCounter": 0, "remainEnergyCost": 0}
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
                        select=select)
    discarded = state_of(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[], discard=[FIRE_E])), DECK)
    forced = action("discard", (0,))
    provider = ScriptedProvider(
        menus={"root": (forced,)},
        nodes={("root", forced.identity): Deterministic(discarded)})

    decision = make_decider(provider).decide(root_obs)
    price = decision.diagnostics["prices"][0]

    assert price["swing"] != 0
    assert decision.decision_result.roster.candidates[0].successors


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


def test_refresh_pricing_is_deterministic_without_expanding_another_main_menu():
    """Lillie's sampled-hand price repeats without multiplying every sample by MAIN."""
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
    assert "continuation action inventory unavailable: KeyError" \
        not in first.diagnostics["gaps"]


def test_lillies_prices_higher_when_the_hand_it_shuffles_away_is_dead():
    """Equal base worth isolates demand liveness as the only swing difference."""
    deck = tuple([LILLIES] + [DARK_E] * 2 + [FIRE_E] * 42)

    def swing_of(extra_hand):
        hand = [LILLIES] + extra_hand
        root_obs = printout(me=player(active=body(DREEPY, 1), hand=hand, deck_count=40),
                            them=player(own=False, active=body(DRAGAPULT, 2)))
        play, end = action("play", (0,)), action("end", (1,))
        provider = ScriptedProvider(
            menus={"root": (play, end)},
            nodes={("root", play.identity): Refresh(LILLIES, ((4, 0),), False)})
        decision = LedgerDecider(deck, "test", EvaluationModel.build(),
                                 provider_factory=lambda _s, **_kw: provider).decide(root_obs)
        return {entry["action"]: entry["swing"]
                for entry in decision.diagnostics["prices"]}[str(play.identity)]

    context = EvaluationModel.build()
    assert context.facts(DARK_E).kind == context.facts(FIRE_E).kind
    dead_hand = [DARK_E, DARK_E]        # Dreepy has no dark or colorless slot: dead cards
    live_hand = [FIRE_E, FIRE_E]        # fire fills Bite's typed partner slot on Dreepy
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

    chosen = choose_prices(decider, (first, second))
    relabeled = (
        OptionPrice(SimpleNamespace(selection=[0], identity=ActionIdentity("play", (999,))),
                    0.1, False, ()),
        OptionPrice(SimpleNamespace(selection=[1], identity=ActionIdentity("attack", (1,))),
                    0.1, False, ()),
    )
    assert choose_prices(decider, (first, second)) is chosen
    assert choose_prices(decider, relabeled).action.selection == chosen.action.selection


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


def test_an_unavailable_provider_returns_a_typed_fail_safe_decision():
    class DeadProvider:
        available = False
        _error = "engine session refused"

        def __init__(self, *_args, **_kwargs):
            pass

    decider = LedgerDecider(DECK, "test", EvaluationModel.build(),
                            provider_factory=lambda _s, **_kw: DeadProvider())
    decision = decider.decide(printout(me=player(active=body(DRAGAPULT, 1))))

    assert decision.diagnostics["policy_reason"] == "fail_safe_provider_failure"
    assert decision.diagnostics["failure"]["stage"] == "provider"
    assert decision.complete is False


def test_provider_effective_options_change_behavior_identity():
    plain = LedgerDecider(DECK, "test", EvaluationModel.build(),
                          provider_factory=lambda _state, **_kwargs: None)
    configured = LedgerDecider(
        DECK, "test", EvaluationModel.build(),
        provider_factory=plain.provider_factory, provider_kwargs={"world_count": 2})

    assert plain.behavior_identity.provider != configured.behavior_identity.provider


def test_provider_fact_source_content_changes_behavior_identity():
    left = DictCardStatProvider({1: CardStat(1, maxDamage=10)})
    right = DictCardStatProvider({1: CardStat(1, maxDamage=20)})
    factory = lambda _state, **_kwargs: None
    first = LedgerDecider(DECK, "test", EvaluationModel.build(),
                          provider_factory=factory, provider_kwargs={"stats": left})
    second = LedgerDecider(DECK, "test", EvaluationModel.build(),
                           provider_factory=factory, provider_kwargs={"stats": right})

    assert first.behavior_identity.provider != second.behavior_identity.provider


def test_opaque_provider_inputs_cannot_share_a_behavior_identity():
    with pytest.raises(TypeError, match="must expose an identity"):
        LedgerDecider(
            DECK, "test", EvaluationModel.build(),
            provider_factory=lambda _state, **_kwargs: None,
            provider_kwargs={"registry": object()})


def test_presentation_failure_returns_one_typed_fail_safe_result():
    root_obs = printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]))
    weird, end = action("ability", (0,)), action("end", (1,))
    provider = ScriptedProvider(
        menus={"root": (weird, end)},
        nodes={("root", weird.identity): Unknown("no model", "forces gap sink")})

    def broken_sink(_record):
        raise RuntimeError("presentation sink failed")

    decision = make_decider(provider, sink=broken_sink).decide(root_obs)

    assert decision.decision_result is not None
    assert decision.diagnostics["policy_reason"] == "fail_safe_presentation_failure"
    assert decision.diagnostics["failure"]["stage"] == "presentation"


def test_fail_safe_policy_failure_returns_one_typed_last_resort_result():
    class DeadProvider:
        available = False
        _error = "engine session refused"

        def __init__(self, *_args, **_kwargs):
            pass

    class BrokenFailSafe:
        def choose(self, *_args, **_kwargs):
            raise RuntimeError("fail-safe policy failed")

    decider = LedgerDecider(
        (DRAGAPULT, FIRE_E, DARK_E) * 20, "test", EvaluationModel.build(),
        provider_factory=lambda _state, **_kwargs: DeadProvider())
    decider.coordinator = replace(
        decider.coordinator, fail_safe_policy=BrokenFailSafe())

    decision = decider.decide(
        printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E])))

    assert decision.decision_result is not None
    assert decision.diagnostics["policy_reason"] == "fail_safe_policy_failure"
    assert decision.diagnostics["failure"]["stage"] == "policy"


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


def _price(kind, index, swing, *, ends=False, refresh=False, prize_map=None,
           footprint=None):
    from types import SimpleNamespace

    from common.ledger.preview import OptionPrice

    return OptionPrice(
        SimpleNamespace(selection=[index],
                        identity=SimpleNamespace(kind=kind, parts=(index,))),
        swing, ends, (),
        footprint=(ContinuationFootprint(0.0, 0.0, False)
                   if footprint is None else footprint),
        prize_map=prize_map)


def test_prize_plan_does_not_preempt_the_neutral_lottery_for_near_equal_prices():
    decider = make_decider(provider=None)
    preferred = PrizeMap(3, (1,), 1, 0, (1,))
    ordinary = PrizeMap(3, (2,), 1, 0, (0,))
    prices = (_price("play", 0, 1.0, prize_map=preferred),
              _price("play", 1, 1.0 - 5e-10, prize_map=ordinary))

    assert choose_prices(decider, prices).action.selection == [1]


def test_continuing_options_rank_only_by_configured_price():
    decider = make_decider(provider=None)
    prices = (_price("attach", 0, 0.05), _price("play", 1, 0.40, refresh=True),
              _price("end", 2, 0.0, ends=True))
    assert choose_prices(decider, prices).action.identity.kind == "play"


def test_a_positive_hand_shuffle_alone_still_gets_played():
    decider = make_decider(provider=None)
    prices = (_price("play", 0, 0.40, refresh=True), _price("end", 1, 0.0, ends=True))
    assert choose_prices(decider, prices).action.identity.kind == "play"


def test_negative_continuation_does_not_hide_the_best_turn_ender():
    decider = make_decider(provider=None)
    prices = (_price("play", 0, -0.212),
              _price("attack", 1, 0.735, ends=True),
              _price("end", 2, -0.274, ends=True))

    assert choose_prices(decider, prices).action.identity.kind == "attack"


def test_unrelated_grossly_negative_body_does_not_block_hand_refresh():
    refresh = ContinuationFootprint(
        0.0, 0.0, True, zones_replaced=("hand",),
        allowances_consumed=("supporter_played",))
    body_play = ContinuationFootprint(
        0.0, 0.0, True, immediately_usable_outputs=("in_play",),
        opportunities_preserved=("play",))
    prices = (
        _price("play", 0, 0.4, footprint=refresh),
        _price("play", 1, -100.0, footprint=body_play),
        _price("end", 2, 0.0, ends=True))

    assert choose_prices(make_decider(provider=None), prices).action.selection == [0]


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
    refresh_price = next(price for price in prices if price.action is play)
    assert refresh_price.successors
    assert len(refresh_price.chance_summaries) == 1
    assert refresh_price.chance_summaries[0].sample_count > 0
    assert refresh_price.chance_summaries[0].method == "sampled"
    assert sum(successor.probability for successor in refresh_price.successors) == pytest.approx(1)
    assert all(sum(item.value for item in price.footprint.contributions)
               == pytest.approx(price.swing) for price in prices)


def test_action_opportunity_cost_changes_policy_without_changing_canonical_delta():
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
    default = make_decider(provider).decide(root_obs)
    lifted_price = next(row for row in lifted.diagnostics["prices"]
                        if row["action"] == str(attach.identity))
    default_price = next(row for row in default.diagnostics["prices"]
                         if row["action"] == str(attach.identity))

    assert lifted.action.kind == "end"
    assert default.action.kind == "attach"
    assert lifted_price["swing"] == pytest.approx(default_price["swing"])


def test_continuation_footprint_is_policy_telemetry_not_ledger_delta():
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
    accounted = [item for item in footprint["contributions"]
                 if item["feature"].startswith("continuation.")
                 or item["feature"] == "action.opportunity_cost"]
    assert footprint["action_opportunity"] != 0.0
    assert accounted == []
    assert footprint["state_delta"] == pytest.approx(price["swing"])
    assert sum(item["value"] for item in footprint["contributions"]) == pytest.approx(
        price["swing"])
    assert sum(item["value"] for item in footprint["policy_contributions"]) \
        == pytest.approx(footprint["action_opportunity"])


def test_no_card_or_mechanic_specific_ordering_branch_remains():
    decider = make_decider(provider=None)
    attach = _price("attach", 0, 0.05)
    fetch = _price("play", 1, 0.10)
    shuffle = _price("play", 2, 0.40, refresh=True)
    end = _price("end", 3, 0.0, ends=True)

    assert choose_prices(decider, (attach, fetch, shuffle, end)).action.selection == [2]
    assert choose_prices(decider, (fetch, shuffle, end)).action.selection == [2]
    assert choose_prices(decider, (fetch, end)).action.selection == [1]


def test_decider_has_no_restock_classifier():
    decider = make_decider(provider=None)
    assert not hasattr(decider, "_restocks_hand")
