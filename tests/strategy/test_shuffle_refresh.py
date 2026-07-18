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
from common.strategy import Line, Strategy
from pilot_helpers import MAIN, PLAY, attack_opt, fetch_effects, make_select, opt, poke, state

END = 14
LILLIES = 1227        # a Shuffle-Refresh (shuffle hand into deck, draw 6)
WINC = 1031           # win-condition payoff (a Mega ex)
STARYU = 1030         # win-condition's Line base (pre-evolution to deploy payoff onto)
BASIC = 700
PLAINMON = 900        # vanilla Active body (not the win-condition)
ULTRA = 2001          # cost_discard tutor (Ultra Ball: keep-value 0, no dig-before-commit bonus)
PLAINDRAW = 950       # plain draw Supporter (draw, NOT shuffle_hand) - the contrast card


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


# --- a dead-hand refresh still plays over End (the +20 endorsement, no dead-hand rung needed) ------
@pytest.mark.req("REQ-GEN-0042")
def test_a_dead_hand_refresh_is_still_played_over_end():
    """A Shuffle-Refresh alone in a dead hand, with the deck still holding a card I lack, plays over
    End — carried by `dig-before-commit`'s +20 alone (the `refresh-when-hand-is-dead` rung and its
    full-menu scan retired 2026-07-03, ADR-0024 amendment: nothing else is endorsed on a dead hand,
    so the extra +8 changed no behavior)."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  BASIC: CardStat(BASIC, hp=70),
                                  PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[WINC, BASIC, BASIC], general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    # hand = just the refresh (dead - no other play); win-condition NOT in play -> deck holds a need.
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)], hand=[LILLIES]))
    assert pilot.explain(obs).options[0].score > 0
    assert pilot.decide(obs) == [0]                                   # refresh, not End


# --- a live tutor is sequenced before the refresh (tier 2 vs tier 3) --------------------------------
@pytest.mark.req("REQ-GEN-0044")
def test_a_playable_tutor_is_played_before_the_refresh():
    """A `cost_discard` tutor that fills a need is a LIVE play the refresh must not shuffle away:
    `_finish_turn_last` tiers the costly search (tier 2) before the hand-nuking shuffle (tier 3), so
    the tutor plays first regardless of raw scores."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0), ULTRA: CardStat(ULTRA, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  BASIC: CardStat(BASIC, hp=70), PLAINMON: CardStat(PLAINMON, hp=90)})
    _fm = {LILLIES: ["draw", "shuffle_hand"], ULTRA: ["search", "tutor_pokemon", "cost_discard"]}
    funcs = CardFunctions(_fm)
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[WINC, BASIC, BASIC], general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs, effects=fetch_effects(_fm))
    obs = make_select([opt(PLAY, index=0), opt(PLAY, index=1), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, ULTRA]))
    assert "fetch-when-it-fills-a-need" in _fired(pilot.explain(obs).options[1])
    assert pilot.decide(obs) == [1]                                  # play the tutor, not the refresh


# --- dont-refresh-into-a-probable-miss also owns K=0: a provably-spent deck, post-anchor -----------
@pytest.mark.req("REQ-GEN-0066")
def test_probable_miss_vetoes_a_refresh_into_a_provably_spent_deck():
    """The K=0 case (ADR-0024 amendment, revised at the 2026-07-03 A/B): post-anchor the deck
    provably holds NOTHING I lack — P(hit) = 0 — so the refresh is churn, netted below End. (The
    broader pre-anchor sound veto regressed 47%/43% in the A/B and was deleted; the spent deck is a
    post-anchor situation in practice.)"""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    deck = [WINC, PLAINMON, LILLIES] + [FILLER2] * 27
    pilot = Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    # wincon Active (need met), anchor -> deck = pure statless FILLER: K=0, P(hit)=0.
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(WINC, energy=3),
                                    bench=[poke(PLAINMON), poke(FILLER2)], hand=[LILLIES],
                                    prizes=6, deck_count=20))
    obs["own_prizes"] = {FILLER2: 6}
    trace = pilot.explain(obs).options[0]
    assert "dont-refresh-into-a-probable-miss" in _fired(trace)
    assert trace.score < 0
    assert pilot.decide(obs) == [1]                                   # End — don't churn a spent deck


@pytest.mark.req("REQ-GEN-0066")
def test_disruption_value_survives_the_probable_miss_veto():
    """−25 is deliberately clearable: a SYMMETRIC refresh with a live disruption trigger (opponent
    runs a hand-size attacker AND a stacked hand to shrink) still nets positive and plays AS
    disruption even though my own pull is provably dead.

    `opp_hand_count=8` added 2026-07-14 (ADR-0060). It used to default to 0 — an Alakazam-class
    attacker holding ZERO cards, which deals zero damage. Judging it would have REFILLED them to 4
    and ARMED the very attacker we were claiming to disrupt. The swing oracle prices that gift
    (−8/card) and correctly refuses, so the old board no longer plays the Judge. The board, not the
    assertion, was wrong: this test's own docstring describes a hand worth shrinking, so give it one.
    """
    HSATK = 640
    stats = DictCardStatProvider({JUDGE: CardStat(JUDGE, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  PLAINMON: CardStat(PLAINMON, hp=90),
                                  HSATK: CardStat(HSATK, hp=90)})
    funcs = CardFunctions({JUDGE: ["draw", "hand_disruption", "shuffle_hand"],
                           HSATK: ["hand_size_attacker"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    deck = [WINC, PLAINMON, JUDGE] + [FILLER2] * 27
    pilot = Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(WINC, energy=3),
                                    bench=[poke(PLAINMON), poke(FILLER2)], hand=[JUDGE],
                                    prizes=6, deck_count=20, opp_active=poke(HSATK),
                                    opp_hand_count=8))   # a hand worth shrinking (see docstring)
    obs["own_prizes"] = {FILLER2: 6}
    trace = pilot.explain(obs).options[0]
    assert "dont-refresh-into-a-probable-miss" in _fired(trace)       # my pull IS dead
    assert "play-harlequin-vs-hand-size" in _fired(trace)             # but the disruption is live
    assert trace.score > 0
    assert pilot.decide(obs) == [0]                                   # played as disruption


# --- dont-refresh-into-a-probable-miss (Layer B, post-anchor): the N-card draw likely whiffs -------
JUDGE, FILLER2 = 1213, 4242


def _anchored_refresh_pilot(refresh_id, refresh_tags, *, opp_prizes=0):
    """40-card deck, prizes anchored: 1 needed WINC + 29 FILLER left in deck (D=30). The refresh is
    the lone hand card, so the pull pool stays 30 and P(hit in N) = N/30."""
    stats = DictCardStatProvider({refresh_id: CardStat(refresh_id, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({refresh_id: refresh_tags})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    deck = [PLAINMON, refresh_id, WINC] + [FILLER2] * 37
    pilot = Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1),
                                    bench=[poke(FILLER2), poke(FILLER2)],
                                    hand=[refresh_id], prizes=6, deck_count=30,
                                    opp_prizes=opp_prizes))
    obs["own_prizes"] = {FILLER2: 6}                     # anchor: exact deck counts known
    return pilot, obs


@pytest.mark.req("REQ-GEN-0067")
def test_dont_refresh_into_a_probable_miss_vetoes_a_diluted_draw():
    """POST-ANCHOR probabilistic veto (ADR-0024 amendment): one needed card among 30 (P(hit in
    Judge's 4) ≈ 0.13 < 0.20) — the refresh is a probable re-roll of dregs, netted below End."""
    pilot, obs = _anchored_refresh_pilot(JUDGE, ["draw", "shuffle_hand"])
    trace = pilot.explain(obs).options[0]
    assert "dont-refresh-into-a-probable-miss" in _fired(trace)
    assert trace.score < 0
    assert pilot.decide(obs) == [1]                                   # End


@pytest.mark.req("REQ-GEN-0067")
def test_laceys_8_draw_window_lifts_the_probable_miss():
    """The conditional draw windows fold into N: Lacey draws 4 (P(hit) = 4/30 < 0.20 → vetoed) — but
    at opp prizes ≤ 3 she draws 8 (P = 8/30 ≥ 0.20), the veto stands down and the refresh plays.
    Draw-counts verified at data/EN_Card_Data.csv."""
    LACEY = 1199
    pilot, obs = _anchored_refresh_pilot(LACEY, ["draw", "shuffle_hand"], opp_prizes=6)
    assert "dont-refresh-into-a-probable-miss" in _fired(pilot.explain(obs).options[0])
    pilot, obs = _anchored_refresh_pilot(LACEY, ["draw", "shuffle_hand"], opp_prizes=3)
    trace = pilot.explain(obs).options[0]
    assert "dont-refresh-into-a-probable-miss" not in _fired(trace)   # the 8-draw window opens
    assert pilot.decide(obs) == [0]                                   # refresh plays again


# --- Shuffle-Refresh IS still a hand-cycling draw -- but the SWING ORACLE owns it (ADR-0060) --------
@pytest.mark.req("REQ-GEN-0046")
def test_the_swing_oracle_owns_the_shuffle_refresh_and_dig_owns_the_plain_draw():
    """A Shuffle-Refresh is still endorsed as a hand-cycle — ADR-0024's 'only when the hand is dead'
    premise stays REFUTED (hoarding cost ~3:1 in the mega_starmie mirror). But ADR-0060 moves that
    endorsement OUT of `dig-before-commit`, which is hand-size-BLIND and so endorsed Judge just as
    warmly when we held 8 cards and the opponent held 1 (ml f111, CRITICAL).

    The cycling credit is preserved EXACTLY (`_REFRESH_CYCLE` = 20, the same +20 dig used to give)
    and now arrives as a tactical term that also prices what the shuffle actually moves. A plain
    draw card is untouched: `dig-before-commit` still owns it."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0), PLAINDRAW: CardStat(PLAINDRAW, hp=0),
                                  PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"], PLAINDRAW: ["draw"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    # SETUP (no win-condition Line) - dig-before-commit is eligible to fire on a draw card here.
    obs = make_select([opt(PLAY, index=0), opt(PLAY, index=1), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, PLAINDRAW]))
    refresh, plain = pilot.explain(obs).options[0], pilot.explain(obs).options[1]

    assert "dig-before-commit" not in _fired(refresh)   # the hand-BLIND rung no longer reaches it
    assert refresh.tactical == 20.0                     # ... the cycling credit is preserved, exactly
    assert refresh.score > 0                            # ... so the refresh is still the strong line

    assert "dig-before-commit" in _fired(plain)         # a plain draw card is unaffected
    assert plain.tactical == 0.0                        # ... and the oracle stays silent on it


# --- regression fix: Shuffle-Refresh played BEFORE the turn-ending attack (cycle, then KO) ----------
@pytest.mark.req("REQ-GEN-0046")
def test_shuffle_refresh_is_sequenced_before_the_turn_ending_attack():
    """The post-refactor mirror loss: the agent ATTACKED instead of playing its draw Supporter, forgoing
    the refill. With the endorsement restored, the Shuffle-Refresh scores positive -> `_finish_turn_last`
    tiers it (tier 3) BEFORE the attack (tier 4), so the agent cycles its hand THEN attacks the same turn
    (the engine re-presents the menu after the non-ending refresh)."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0), PLAINMON: CardStat(PLAINMON, hp=90),
                                  BASIC: CardStat(BASIC, hp=70)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    # pre-anchor: the post-anchor Layer-B veto is silent by construction.
    pilot = Pilot(Strategy(), deck=[BASIC] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    # live attack and the refresh on same menu; no held Energy / wincon -> guards stay silent.
    obs = make_select([opt(PLAY, index=0), attack_opt(1)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)], hand=[LILLIES]))
    assert pilot.decide(obs) == [0]                                  # play the refresh, not attack first


# --- hold-wincon-dont-shuffle: don't shuffle a held win-condition back into the deck -----------------
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
    # hand holds BOTH refresh and win-condition -> shuffling would bury the wincon.
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


# --- hold-wincon-with-base-dont-shuffle: benched base to evolve held wincon -> hold firmly ----------
@pytest.mark.req("REQ-GEN-0047")
def test_hold_wincon_with_base_dont_shuffle_fires_when_a_base_is_benched():
    """The held win-condition has its Line BASE already on the Bench (deploy-soon), so the shuffle
    would bury an imminent evolution — the stronger hold fires (stacks on the moderate base hold) so
    the agent takes a board action this turn instead of refilling. ep82867148 f52."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  STARYU: CardStat(STARYU, hp=70), PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[STARYU, WINC], payoff=WINC)])
    pilot = Pilot(strat, deck=[BASIC], general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(STARYU)],
                                    hand=[LILLIES, WINC]))
    assert "hold-wincon-with-base-dont-shuffle" in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0047")
def test_hold_wincon_with_base_silent_when_no_base_is_in_play():
    """No Line base IN PLAY (but the base is in HAND, so the wincon is still deployable) -> the stronger
    base-in-PLAY hold stays silent; only the moderate `hold-wincon-dont-shuffle` fires, so a genuinely
    dead hand can still refill (the base hold is NOT absolute)."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  STARYU: CardStat(STARYU, hp=70), PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[STARYU, WINC], payoff=WINC)])
    pilot = Pilot(strat, deck=[BASIC], general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,          # bench body is NOT the base;
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, WINC, STARYU]))            # base sits in HAND (deployable)
    fired = _fired(pilot.explain(obs).options[0])
    assert "hold-wincon-with-base-dont-shuffle" not in fired
    assert "hold-wincon-dont-shuffle" in fired


@pytest.mark.req("REQ-GEN-0047")
def test_hold_wincon_stands_down_when_the_held_wincon_is_undeployable():
    """The moderate `hold-wincon-dont-shuffle` ALSO stands down when the held win-condition is an
    UNDEPLOYABLE evolution — no base anywhere (not in play AND not in hand) to evolve it onto — so it's
    a dead card worth shuffling away to dig for the base, not a piece to hold. ep83966336 f44 (CRITICAL,
    blunder round 2026-07-05): Mega Lucario ex held with no Riolu in play or hand while the agent ended
    the turn instead of refilling — `wincon_in_hand_undeployable` now frees the refresh."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  STARYU: CardStat(STARYU, hp=70), PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[STARYU, WINC], payoff=WINC)])
    pilot = Pilot(strat, deck=[BASIC], general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,          # no Staryu in play OR hand:
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, WINC]))                    # the Mega is a dead hand card
    dec = pilot.explain(obs)
    fired = _fired(dec.options[0])
    assert "hold-wincon-dont-shuffle" not in fired                           # the dead wincon is not held
    assert "hold-wincon-with-base-dont-shuffle" not in fired
    assert dec.chosen == [0]                                                  # Lillie's refresh, not End
