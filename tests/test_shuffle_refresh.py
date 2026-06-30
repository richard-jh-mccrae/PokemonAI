"""Shuffle-Refresh Doctrine (ADR-0024): a Hand-Refresh Supporter that shuffles your hand into your
deck then draws (Lillie's Determination, Judge, Harlequin, Lacey; Function Tag `shuffle_hand`). It is
the Fetch comparator's decision (A) only — a *dead-hand fallback*: play it only when no other card in
hand yields a positive play this turn and the deck still holds a card I lack. Verified through the
PUBLIC Pilot interface (`decide` picks the option; `explain(...).fired` names the rules that fired).
See docs/general-strategy.md "Shuffle-Refresh doctrine".
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from pilot_helpers import MAIN, PLAY, attack_opt, make_select, opt, poke, state

END = 14
LILLIES = 1227        # a Shuffle-Refresh (shuffle hand into deck, draw 6)
WINC = 1031           # the win-condition payoff (a Mega ex)
BASIC = 700
PLAINMON = 900        # a vanilla Active body (not the win-condition)
ULTRA = 2001          # a cost_discard tutor (Ultra Ball: keep-value 0, no dig-before-commit bonus)
PLAINDRAW = 950       # a plain draw Supporter (draw, NOT shuffle_hand) — the contrast card


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


# --- refresh-when-hand-is-dead: a dead hand + a deck that still holds a need -> refresh ------------
@pytest.mark.req("REQ-GEN-0042")
def test_refresh_when_hand_is_dead_plays_the_refresh_over_end():
    """A Shuffle-Refresh alone in a dead hand (no other card to play), with the deck still holding a
    card I lack (the unfound win-condition), fires `refresh-when-hand-is-dead` and is played over End."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  BASIC: CardStat(BASIC, hp=70),
                                  PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[WINC, BASIC, BASIC], general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    # hand = just the refresh (dead — no other play); win-condition NOT in play -> deck holds a need.
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)], hand=[LILLIES]))
    assert "refresh-when-hand-is-dead" in _fired(pilot.explain(obs).options[0])
    assert pilot.explain(obs).options[0].score > 0
    assert pilot.decide(obs) == [0]                                   # refresh, not End


# --- a playable Pokémon is a development out -> the hand is NOT dead (use key cards first) ----------
@pytest.mark.req("REQ-GEN-0043")
def test_a_playable_pokemon_keeps_the_hand_live_so_the_refresh_stands_down():
    """A spare Basic in hand is a development out — even in SETUP with a developed bench (where benching
    it isn't positively scored), the hand is NOT dead, so `refresh-when-hand-is-dead` does not fire.
    Don't shuffle away a card you could play (pillar: use your key cards first)."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  BASIC: CardStat(BASIC, hp=70),
                                  PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[WINC, BASIC, BASIC], general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    # SETUP, bench already developed (keep-a-bench won't fire); the hand also holds a benchable Basic.
    obs = make_select([opt(PLAY, index=0), opt(PLAY, index=1), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, BASIC]))
    assert "refresh-when-hand-is-dead" not in _fired(pilot.explain(obs).options[0])


# --- a playable tutor that fills a need keeps the hand live (full-scan vs keep-value distinction) --
@pytest.mark.req("REQ-GEN-0044")
def test_a_playable_tutor_that_fills_a_need_keeps_the_hand_live():
    """The reason the gate is a full play-scan, not a keep-value floor: a `cost_discard` tutor (Ultra
    Ball) has keep-value 0 AND gets no `dig-before-commit` bonus, yet it is a LIVE play —
    `fetch-when-it-fills-a-need` endorses it (it can grab the unfound win-condition). So the hand is not
    dead, the refresh stands down, and the tutor is played instead."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0), ULTRA: CardStat(ULTRA, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  BASIC: CardStat(BASIC, hp=70), PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"],
                           ULTRA: ["search", "tutor_pokemon", "cost_discard"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[WINC, BASIC, BASIC], general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(PLAY, index=1), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, ULTRA]))
    assert "refresh-when-hand-is-dead" not in _fired(pilot.explain(obs).options[0])
    assert "fetch-when-it-fills-a-need" in _fired(pilot.explain(obs).options[1])
    assert pilot.decide(obs) == [1]                                  # play the tutor, not the refresh


# --- deck_holds_a_need gate: a dead hand but a deck with nothing left to want -> don't refresh ------
@pytest.mark.req("REQ-GEN-0045")
def test_refresh_stands_down_when_the_deck_holds_no_need():
    """Even with a dead hand, don't refresh into a deck that can't give you anything you lack — the
    win-condition is already in play (and the bench developed), so the only deck card fills no need and
    `deck_holds_a_need` is false. Refreshing would just churn a fresh hand from a spent deck."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu")})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[WINC], general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    # win-condition Active + bench developed -> no need anywhere; hand is the lone refresh (dead).
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(WINC, energy=3),
                                    bench=[poke(701), poke(702), poke(703)], hand=[LILLIES]))
    assert "refresh-when-hand-is-dead" not in _fired(pilot.explain(obs).options[0])


# --- a Shuffle-Refresh IS a hand-cycling draw -> dig-before-commit endorses it (ADR-0024 reversal) --
@pytest.mark.req("REQ-GEN-0046")
def test_dig_before_commit_endorses_a_shuffle_refresh_as_a_draw():
    """A Shuffle-Refresh carries the `draw` tag and refills the hand — playing it to cycle is the strong
    line, so `dig-before-commit` endorses it like any other draw Supporter. ADR-0024's 'only when the
    hand is dead' premise was REFUTED 2026-06-30: hoarding the refresh cost ~3:1 in the mega_starmie
    mirror vs the pre-refactor build. `_finish_turn_last` still tiers it after the Energy attach, and
    `hold-wincon-dont-shuffle` / `attach-before-hand-shuffle` guard the genuinely-bad shuffles."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0), PLAINDRAW: CardStat(PLAINDRAW, hp=0),
                                  PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"], PLAINDRAW: ["draw"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    # SETUP (no win-condition Line) — dig-before-commit is eligible to fire on a draw card here.
    obs = make_select([opt(PLAY, index=0), opt(PLAY, index=1), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, PLAINDRAW]))
    assert "dig-before-commit" in _fired(pilot.explain(obs).options[0])       # the Shuffle-Refresh now endorsed
    assert "dig-before-commit" in _fired(pilot.explain(obs).options[1])       # the plain draw card too


# --- the regression fix: a Shuffle-Refresh is played BEFORE the turn-ending attack (cycle, then KO) -
@pytest.mark.req("REQ-GEN-0046")
def test_shuffle_refresh_is_sequenced_before_the_turn_ending_attack():
    """The post-refactor mirror loss: the agent ATTACKED instead of playing its draw Supporter, forgoing
    the refill. With the endorsement restored, the Shuffle-Refresh scores positive -> `_finish_turn_last`
    tiers it (tier 3) BEFORE the attack (tier 4), so the agent cycles its hand THEN attacks the same turn
    (the engine re-presents the menu after the non-ending refresh)."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0), PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    # a live attack and the refresh on the same menu; no held Energy / wincon -> the guards stay silent.
    obs = make_select([opt(PLAY, index=0), attack_opt(1)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)], hand=[LILLIES]))
    assert pilot.decide(obs) == [0]                                  # play the refresh, not attack first


# --- hold-wincon-dont-shuffle: don't shuffle a held win-condition back into the deck ---------------
@pytest.mark.req("REQ-GEN-0047")
def test_hold_wincon_dont_shuffle_fires_when_the_held_wincon_would_be_shuffled_away():
    """A Shuffle-Refresh shuffles the WHOLE hand into the deck — including a win-condition you are
    holding. The reluctance fires (negative) so the agent doesn't bury the piece it just found. Closes
    the behavioral coverage gap flagged by the 2026-06-29 refactor audit."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[BASIC], general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    # hand holds BOTH the refresh and the win-condition -> shuffling would bury the wincon.
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, WINC]))
    trace = pilot.explain(obs).options[0]
    assert "hold-wincon-dont-shuffle" in _fired(trace)


@pytest.mark.req("REQ-GEN-0047")
def test_hold_wincon_dont_shuffle_silent_when_the_wincon_is_not_in_hand():
    """No win-condition in hand -> nothing precious to shuffle away -> the reluctance stays silent
    (the refresh is then judged purely on the dead-hand fallback)."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[BASIC], general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)], hand=[LILLIES]))
    assert "hold-wincon-dont-shuffle" not in _fired(pilot.explain(obs).options[0])
