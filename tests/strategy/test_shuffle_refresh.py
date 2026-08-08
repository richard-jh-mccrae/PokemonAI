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

def _ranked(pilot, obs):
    """The tuned ladder's own ranking, best-first. Not `decide`: Issue #386 moved the single-pick MAIN
    decision to the composer, so a `decide` assertion here would test the composer, not these rungs."""
    return [(o.index, o.score) for o in sorted(pilot.explain(obs).options, key=lambda o: -o.score)]


def _sequenced(pilot, obs):
    """The ladder's final ORDER — `_finish_turn_last` applied to its score order. A ranking cannot
    express a SEQUENCING claim, whose whole point is that it holds regardless of raw scores."""
    select = obs["select"]
    dec = pilot.explain(obs)
    board = pilot._board(obs, select)
    options = select["option"]
    traces = list(dec.options)
    by_score = pilot._score_order(obs, options, traces)
    return pilot._finish_turn_last(obs, board, options, traces, by_score,
                                   select.get("maxCount", 0), select.get("context"))



# --- a dead-hand refresh still plays over End (the +20 endorsement, no dead-hand rung needed) ------
@pytest.mark.req("REQ-GEN-0042")
def test_a_dead_hand_refresh_is_still_played_over_end():
    """A Shuffle-Refresh alone in a dead hand, with the deck still holding a card I lack, plays over
    End. The `refresh-when-hand-is-dead` rung is retired (ADR-0024 amendment) as behaviour-neutral."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  BASIC: CardStat(BASIC, synthetic=True, hp=70),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[WINC, BASIC, BASIC], general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    # hand = just the refresh (dead - no other play); win-condition NOT in play -> deck holds a need.
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)], hand=[LILLIES]))
    assert pilot.explain(obs).options[0].score > 0
    assert _ranked(pilot, obs)[0][0] == 0                                   # refresh, not End


# --- a live tutor is sequenced before the refresh (tier 2 vs tier 3) --------------------------------
@pytest.mark.req("REQ-GEN-0044")
def test_a_playable_tutor_is_played_before_the_refresh():
    """`_finish_turn_last` tiers the costly search (tier 2) before the hand-nuking shuffle (tier 3),
    so the tutor plays first regardless of raw scores."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0), ULTRA: CardStat(ULTRA, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  BASIC: CardStat(BASIC, synthetic=True, hp=70), PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90)})
    _fm = {LILLIES: ["draw", "shuffle_hand"], ULTRA: ["search", "tutor_pokemon", "cost_discard"]}
    funcs = CardFunctions(_fm)
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[WINC, BASIC, BASIC], general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs, effects=fetch_effects(_fm))
    obs = make_select([opt(PLAY, index=0), opt(PLAY, index=1), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, ULTRA]))
    assert "fetch-when-it-fills-a-need" in _fired(pilot.explain(obs).options[1])
    # A SEQUENCING claim, so it is asserted at the sequencer: the ladder's RANKING no longer puts
    # the tutor top, and the tiering is what "regardless of raw scores" means.
    assert _sequenced(pilot, obs)[0] == 1                                # play the tutor, not the refresh


# --- dont-refresh-into-a-probable-miss also owns K=0: a provably-spent deck, post-anchor -----------
@pytest.mark.req("REQ-GEN-0066")
def test_probable_miss_vetoes_a_refresh_into_a_provably_spent_deck():
    """The K=0 case (ADR-0024 amendment): post-anchor the deck provably holds NOTHING I lack, so the
    refresh is churn. The broader PRE-anchor veto was A/B-refuted and deleted."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90)})
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
    """The veto is deliberately CLEARABLE. The stand-in attacker must carry a real `handSizeDamage`
    and the opponent a hand worth shrinking, or there is no disruption value to survive it."""
    HSATK = 640
    stats = DictCardStatProvider({JUDGE: CardStat(JUDGE, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90),
                                  HSATK: CardStat(HSATK, synthetic=True, hp=90, handSizeDamage=20)})
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
    assert "play-harlequin-vs-hand-size" not in _fired(trace)         # RETIRED (ADR-0102) — the
    assert trace.score > 0                                            # disruption value is now the
    #                                                                   priced survival, in `tactical`
    assert _ranked(pilot, obs)[0][0] == 0                                   # played as disruption


# --- dont-refresh-into-a-probable-miss (Layer B, post-anchor): the N-card draw likely whiffs -------
JUDGE, FILLER2 = 1213, 4242


def _anchored_refresh_pilot(refresh_id, refresh_tags, *, opp_prizes=0):
    """40-card deck, prizes anchored: 1 needed WINC + 29 FILLER left in deck (D=30). The refresh is
    the lone hand card, so the pull pool stays 30 and P(hit in N) = N/30."""
    stats = DictCardStatProvider({refresh_id: CardStat(refresh_id, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90)})
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
    """POST-ANCHOR probabilistic veto (ADR-0024 amendment): one needed card among 30 is below the
    0.20 bar, so the refresh is a probable re-roll of dregs."""
    pilot, obs = _anchored_refresh_pilot(JUDGE, ["draw", "shuffle_hand"])
    trace = pilot.explain(obs).options[0]
    assert "dont-refresh-into-a-probable-miss" in _fired(trace)
    assert trace.score < 0
    assert pilot.decide(obs) == [1]                                   # End


@pytest.mark.req("REQ-GEN-0067")
def test_laceys_8_draw_window_lifts_the_probable_miss():
    """The conditional draw windows fold into N: Lacey draws 4, or 8 at opp prizes ≤ 3, which crosses
    the 0.20 bar and stands the veto down."""
    LACEY = 1199
    pilot, obs = _anchored_refresh_pilot(LACEY, ["draw", "shuffle_hand"], opp_prizes=6)
    assert "dont-refresh-into-a-probable-miss" in _fired(pilot.explain(obs).options[0])
    pilot, obs = _anchored_refresh_pilot(LACEY, ["draw", "shuffle_hand"], opp_prizes=3)
    trace = pilot.explain(obs).options[0]
    assert "dont-refresh-into-a-probable-miss" not in _fired(trace)   # the 8-draw window opens
    assert _ranked(pilot, obs)[0][0] == 0                                   # refresh plays again


# --- Shuffle-Refresh IS still a hand-cycling draw -- but the SWING ORACLE owns it (ADR-0060) --------
@pytest.mark.req("REQ-GEN-0046")
def test_the_swing_oracle_owns_the_shuffle_refresh_and_a_plain_draw_gets_nothing():
    """ADR-0060 moved the cycling endorsement out of a hand-size-BLIND rung and into the swing
    oracle, preserving `_REFRESH_CYCLE` exactly. The oracle stays SILENT on a plain draw."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, synthetic=True, hp=0), PLAINDRAW: CardStat(PLAINDRAW, synthetic=True, hp=0),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"], PLAINDRAW: ["draw"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    # SETUP (no win-condition Line).
    obs = make_select([opt(PLAY, index=0), opt(PLAY, index=1), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, PLAINDRAW]))
    refresh, plain = pilot.explain(obs).options[0], pilot.explain(obs).options[1]

    assert refresh.tactical == 20.0                     # the cycling credit is preserved, exactly
    assert refresh.score > 0                            # ... so the refresh is still the strong line
    assert plain.tactical == 0.0                        # ... and the oracle stays SILENT on a plain draw
    assert refresh.tactical > plain.tactical, (         # the contrast, stated as one comparison so a
        "the swing oracle no longer separates a hand-nuking refresh from a plain draw")


# --- regression fix: Shuffle-Refresh played BEFORE the turn-ending attack (cycle, then KO) ----------
@pytest.mark.req("REQ-GEN-0046")
def test_shuffle_refresh_is_sequenced_before_the_turn_ending_attack():
    """`_finish_turn_last` tiers a positive refresh (tier 3) BEFORE the attack (tier 4), so the agent
    cycles its hand THEN attacks the same turn — the engine re-presents the menu after the refresh."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, synthetic=True, hp=0), PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90),
                                  BASIC: CardStat(BASIC, synthetic=True, hp=70)})
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
    """The graded SHED (ADR-0065) prices a held wincon at its role value × how UN-recoverable it is,
    so the refresh scores NEGATIVE — the retired `hold-wincon-dont-shuffle` guard, in one currency."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, synthetic=True, megaEx=True, hp=330, evolvesFrom="Staryu",
                                                 name="Mega Lucario ex"),
                                  STARYU: CardStat(STARYU, hp=70, name="Staryu"),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    # deck still holds the Staryu base -> the wincon is DEPLOYABLE (the evolution gate keeps its worth).
    pilot = Pilot(strat, deck=[BASIC] * 39 + [STARYU], general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    # hand holds BOTH refresh and win-condition -> shuffling would bury the wincon.
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, WINC]))
    trace = pilot.explain(obs).options[0]
    assert trace.score < 0, f"held wincon must make the refresh reluctant, scored {trace.score:+.1f}"
    assert trace.index not in pilot.explain(obs).chosen, "shuffled the held wincon away anyway"


@pytest.mark.req("REQ-GEN-0047")
def test_hold_wincon_dont_shuffle_silent_when_the_wincon_is_not_in_hand():
    """Nothing precious to shuffle away, so the reluctance stays silent."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[BASIC], general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)], hand=[LILLIES]))
    assert "hold-wincon-dont-shuffle" not in _fired(pilot.explain(obs).options[0])


# --- hold-wincon-with-base-dont-shuffle: benched base to evolve held wincon -> hold firmly ----------
@pytest.mark.req("REQ-GEN-0047")
def test_hold_wincon_with_base_dont_shuffle_fires_when_a_base_is_benched():
    """The held wincon's Line BASE is already benched, so the shuffle would bury an imminent
    evolution — the retired `hold-wincon-with-base-dont-shuffle` stack, folded into ADR-0065."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  WINC: CardStat(WINC, synthetic=True, megaEx=True, hp=330, evolvesFrom="Staryu",
                                                 name="Mega Lucario ex"),
                                  STARYU: CardStat(STARYU, hp=70, name="Staryu"),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[STARYU, WINC], payoff=WINC)])
    pilot = Pilot(strat, deck=[BASIC] * 40, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,          # the Staryu base is benched
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(STARYU)],
                                    hand=[LILLIES, WINC]))
    assert pilot.explain(obs).options[0].score < 0, "a held wincon (base benched) must make refresh negative"


@pytest.mark.req("REQ-GEN-0047")
def test_hold_wincon_is_cheap_to_shuffle_when_the_hand_is_dregs():
    """The mirror: with no high-role card in hand the graded SHED is ~0, so a genuinely dead hand
    still refills freely — the shed is not a blanket anti-refresh (ADR-0065)."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0),
                                  STARYU: CardStat(STARYU, synthetic=True, hp=70), PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[STARYU, WINC], payoff=WINC)])
    pilot = Pilot(strat, deck=[BASIC] * 40, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,       # hand: refresh + a role-less basic
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, BASIC]))
    assert pilot.explain(obs).options[0].score > 0, "a dreg hand must still refresh freely"


def _undeployable_pilot(base_in_deck: bool):
    """``base_in_deck`` toggles whether the base is still reachable — the ONE difference the evolution
    gate reads. The base's STAT is always known, so only its presence in the DECK changes."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0, name="Lillie's Determination"),
                                  WINC: CardStat(WINC, synthetic=True, megaEx=True, hp=330, evolvesFrom="Staryu",
                                                 name="Mega Lucario ex"),
                                  STARYU: CardStat(STARYU, hp=70, name="Staryu"),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90, name="Plainmon"),
                                  BASIC: CardStat(BASIC, synthetic=True, hp=0, name="Basic Energy")})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[STARYU, WINC], payoff=WINC)])
    deck = [BASIC] * 39 + ([STARYU] if base_in_deck else [BASIC])
    pilot = Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,          # no Staryu in play OR hand
                      current=state(active=poke(PLAINMON, energy=1), bench=[poke(701)],
                                    hand=[LILLIES, WINC]))
    return pilot.explain(obs).options[0]


@pytest.mark.req("REQ-GATE-0001")
def test_undeployable_wincon_is_cheap_to_shuffle_but_a_deployable_one_is_not():
    """The evolution gate (ADR-0065 Stage 1): only the base's reachability differs, and a flat
    keep-value cannot tell these two boards apart — the gate is exactly that discriminator."""
    deployable = _undeployable_pilot(base_in_deck=True)
    undeployable = _undeployable_pilot(base_in_deck=False)
    assert deployable.score < 0, f"a deployable wincon must make the refresh reluctant ({deployable.score:+.1f})"
    assert undeployable.score > 0, f"a dead (undeployable) wincon must not ({undeployable.score:+.1f})"
