"""Probabilistic own-deck content estimate — `common.deck_odds` + the `Board.deck_contains_probability`
signal and the `dont-search-a-probable-whiff` Fetch rung (ADR-0029).

The COMPLEMENT to the certain-or-silent deck tracker: this answers *"is card C probably still in my
deck?"* by splitting the unseen copies over the hidden prize slots hypergeometrically. It never
contradicts the sound oracle and never replaces the sound whiff guard.
"""
import pytest

from common.cards import CardFunctions
from common.deck_odds import contains_odds, p_contains
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import HAND, PLAY, fetch_effects, make_select, opt, poke, state

END = 14  # OptionType.END


def _fired(o):
    return {h.id for h, _ in o.fired}

def _ranked(pilot, obs):
    """The tuned ladder's own ranking, best-first, as ``[(index, score), ...]``. Not `decide`: since
    Issue #386 these rungs SCORE every option but no longer pick — the composer does (ADR-0131)."""
    return [(o.index, o.score) for o in sorted(pilot.explain(obs).options, key=lambda o: -o.score)]



# ============================================================ the pure hypergeometric estimator
@pytest.mark.req("REQ-GEN-0053")
def test_unseen_copies_split_over_hidden_prizes_is_hypergeometric():
    # 2 of 3 unseen, 6 hidden prizes, 30 in deck -> H=36. P(both prized)=C(6,2)/C(36,2)=15/630.
    # ep82524455-f6 shape: "2 of 3 Staryu could sit in 6 prizes" -> still very likely in deck.
    assert p_contains(unseen_copies=2, prizes_hidden=6, deck_count=30) == pytest.approx(1 - 15 / 630)
    assert p_contains(2, 6, 30) > 0.9


@pytest.mark.req("REQ-GEN-0053")
def test_single_unseen_copy_is_the_deck_share_of_the_hidden_pool():
    # One unseen copy lands in a uniform random hidden slot -> P(in deck) = deck_count / (deck+prizes).
    assert p_contains(1, 5, 1) == pytest.approx(1 / 6)     # tiny deck, many prizes -> probably prized
    assert p_contains(1, 2, 6) == pytest.approx(6 / 8)     # big deck, few prizes -> probably in deck


@pytest.mark.req("REQ-GEN-0053")
def test_sound_at_the_extremes_agrees_with_the_sound_oracle():
    assert p_contains(0, 6, 30) == 0.0     # every copy seen outside deck -> sound-EMPTY (P 0)
    assert p_contains(3, 2, 30) == 1.0     # 3 unseen, only 2 prize slots -> pigeonhole: in deck
    assert p_contains(1, 0, 5) == 1.0      # no hidden prizes left -> unseen copy MUST be in deck


@pytest.mark.req("REQ-GEN-0053")
def test_deck_empty_of_hidden_pool_means_all_unseen_are_prized():
    # deck_count 0 with prizes remaining: all unseen copies necessarily prized -> P(in deck) == 0.
    assert p_contains(2, 6, 0) == 0.0
    assert p_contains(1, 4, 0) == 0.0


@pytest.mark.req("REQ-GEN-0053")
def test_more_prizes_or_fewer_deck_cards_lowers_presence_monotonically():
    # Unseen copies fixed: presence falls as deck thins relative to prize pile.
    a = p_contains(1, 6, 20)
    b = p_contains(1, 6, 4)
    c = p_contains(1, 6, 1)
    assert a > b > c
    assert 0.0 <= c <= a <= 1.0


@pytest.mark.req("REQ-GEN-0053")
def test_p_contains_never_raises_and_stays_in_unit_interval():
    # Grader safety: garbage collapses to a float in [0,1] (1.0 = assume present, never suppress).
    for args in [(-1, 6, 30), (1, -5, 3), (2, 6, -9), ("x", 6, 30), (1, None, 3), (10**9, 6, 30)]:
        v = p_contains(*args)
        assert isinstance(v, float) and 0.0 <= v <= 1.0


# ------------------------------------------------- the >= k generalisation (Issue #394 item F4)
# `p_contains` (">=1") must BE the k=1 case of this, never a second spelling of it.

def _at_least_by_enumeration(u, hidden, deck, need) -> float:
    """The oracle: positions ``0..deck-1`` are deck slots and the rest face-down prizes, and
    exchangeability makes every size-`u` subset equally likely. No closed form, no simulation."""
    from itertools import combinations
    h = deck + hidden
    if u > h:
        return float("nan")                       # not a board the model describes
    subsets = list(combinations(range(h), u))
    hits = sum(1 for s in subsets if sum(1 for i in s if i < deck) >= need)
    return hits / len(subsets)


@pytest.mark.req("REQ-GEN-0053")
def test_at_least_k_matches_brute_force_over_the_whole_small_parameter_grid():
    """Zero mismatches against the enumeration oracle across every reachable small board."""
    from common.deck_odds import p_contains_at_least
    checked = 0
    for deck in range(0, 8):
        for hidden in range(0, 7):
            for u in range(0, min(5, deck + hidden) + 1):
                for need in range(1, 5):
                    exact = _at_least_by_enumeration(u, hidden, deck, need)
                    got = p_contains_at_least(u, hidden, deck, need)
                    assert got == pytest.approx(exact), (u, hidden, deck, need, got, exact)
                    checked += 1
    assert checked > 500, "the grid collapsed — this assertion is the positive control"


@pytest.mark.req("REQ-GEN-0053")
def test_p_contains_is_exactly_the_k_equals_one_case():
    """The delegation is an IDENTITY, not an approximation: one closed form, not two."""
    from common.deck_odds import p_contains_at_least
    for deck in range(0, 9):
        for hidden in range(0, 8):
            for u in range(0, 6):
                assert p_contains(u, hidden, deck) == p_contains_at_least(u, hidden, deck, 1)


@pytest.mark.req("REQ-GEN-0053")
def test_at_least_k_is_monotone_and_bounded_by_its_own_extremes():
    """Demanding more copies is never more likely; k<=0 asks nothing; k beyond the unseen count or
    beyond the deck's size is impossible."""
    from common.deck_odds import p_contains_at_least
    ladder = [p_contains_at_least(4, 6, 20, k) for k in (1, 2, 3, 4)]
    assert ladder == sorted(ladder, reverse=True)
    assert all(0.0 <= v <= 1.0 for v in ladder)
    assert p_contains_at_least(4, 6, 20, 0) == 1.0        # ">= 0 copies" is vacuously true
    assert p_contains_at_least(2, 6, 20, 3) == 0.0        # only 2 unseen: 3 is unreachable
    assert p_contains_at_least(4, 6, 2, 3) == 0.0         # deck holds 2 cards: 3 cannot fit
    assert p_contains_at_least(4, 0, 20, 4) == 1.0        # no hidden prizes -> every copy in deck
    assert p_contains_at_least(5, 2, 20, 3) == 1.0        # pigeonhole: at most 2 can be prized


@pytest.mark.req("REQ-GEN-0053")
def test_at_least_k_never_raises_and_keeps_the_suppressor_fail_direction():
    """Same grader-safety contract as `p_contains`: garbage -> 1.0 ("assume present"), never a
    raise, never a suppression on bad input."""
    from common.deck_odds import p_contains_at_least
    for args in [(-1, 6, 30, 2), (1, -5, 3, 2), (2, 6, -9, 2), ("x", 6, 30, 2),
                 (1, None, 3, 2), (10**9, 6, 30, 2), (2, 6, 30, "x")]:
        v = p_contains_at_least(*args)
        assert isinstance(v, float) and 0.0 <= v <= 1.0
    assert p_contains_at_least("x", 6, 30, 2) == 1.0


@pytest.mark.req("REQ-GEN-0053")
def test_contains_odds_builds_a_per_card_dict():
    odds = contains_odds(decklist={7: 3, 8: 4}, visible={7: 1}, deck_count=30, prizes_hidden=6)
    assert odds[7] == pytest.approx(p_contains(2, 6, 30))   # 3 - 1 visible = 2 unseen
    assert odds[8] == pytest.approx(p_contains(4, 6, 30))   # none seen -> 4 unseen
    assert set(odds) == {7, 8}


# ============================================================ the Board signal (pilot wiring)
DECK = [1, 1, 1, 2, 2, 2, 3, 3, 3, 3]   # 3x id1, 3x id2, 4x id3 — same as test_deck_tracker


def _poke(cid):
    return {"id": cid, "energyCards": [], "tools": [], "preEvolution": []}


def _board_obs(*, deck_count, prize_hidden=0, hand=(), discard=(), active=None, bench=(), own_prizes=None):
    me = {
        "hand": [{"id": c} for c in hand],
        "discard": [{"id": c} for c in discard],
        "active": [_poke(active)] if active is not None else [],
        "bench": [_poke(c) for c in bench],
        "prize": [None] * prize_hidden,
        "deckCount": deck_count,
    }
    return {"current": {"turn": 2, "yourIndex": 0, "players": [me, None]}, "own_prizes": own_prizes}


@pytest.mark.req("REQ-GEN-0054")
def test_board_probability_unresolved_matches_the_hypergeometric_split():
    pilot = Pilot(Strategy(), deck=DECK)
    # visible {1:1, 2:1} -> 8 cards unseen; deck 6 + 2 hidden prizes = 8 (consistent split).
    b = pilot._board(_board_obs(deck_count=6, prize_hidden=2, hand=[1], active=2))
    # id3: 4 unseen, only 2 prize slots -> pigeonhole CERTAIN, where SOUND oracle stays silent.
    assert b.deck_contains_probability(3) == 1.0
    assert not b.deck_definitely_has(3)                      # sound makes no positive claim (no reveal)
    # id1: 2 unseen over 2 prize slots of 8-card pool -> P = 1 - C(2,2)/C(8,2).
    assert b.deck_contains_probability(1) == pytest.approx(1 - 1 / 28)


@pytest.mark.req("REQ-GEN-0054")
def test_board_probability_is_low_when_a_card_is_mostly_prized():
    pilot = Pilot(Strategy(), deck=[5] + [9] * 9)            # one copy of id5
    # id5 nowhere visible; 1 in deck, 5 hidden prizes -> P(in deck) = 1/6.
    b = pilot._board(_board_obs(deck_count=1, prize_hidden=5, active=9))
    assert b.deck_contains_probability(5) == pytest.approx(1 / 6)


@pytest.mark.req("REQ-GEN-0054")
def test_board_probability_collapses_to_certainty_when_prizes_are_resolved():
    pilot = Pilot(Strategy(), deck=DECK)
    # Tracker resolved prizes {1:2, 2:1} -> deck = {1:0, 2:1, 3:4}: no randomness left.
    b = pilot._board(_board_obs(deck_count=7, hand=[1], active=2, own_prizes={1: 2, 2: 1}))
    assert b.deck_contains_probability(1) == 0.0             # all id1 accounted (1 visible + 2 prized)
    assert b.deck_contains_probability(2) == 1.0 and b.deck_contains_probability(3) == 1.0
    assert b.deck_definitely_empty_of(1) and b.deck_definitely_has(2)   # agrees with sound oracle


@pytest.mark.req("REQ-GEN-0054")
def test_board_probability_is_zero_for_a_provably_empty_card_agreeing_with_sound():
    pilot = Pilot(Strategy(), deck=[5, 9, 9])
    # id5 has 1 copy, seen in hand -> provably empty even stateless.
    b = pilot._board(_board_obs(deck_count=1, prize_hidden=1, hand=[5], active=9))
    assert b.deck_contains_probability(5) == 0.0
    assert b.deck_definitely_empty_of(5)                     # sound extreme: P 0 <-> definitely-empty


@pytest.mark.req("REQ-GEN-0054")
def test_board_probability_is_silent_without_a_deck_count():
    pilot = Pilot(Strategy(), deck=DECK)
    # No deckCount -> split uncomputable -> signal stays silent (1.0 = assume present, never
    # suppress). Why every existing Pilot test (sets no deckCount) is unaffected.
    me = {"hand": [], "discard": [], "active": [], "bench": [], "prize": [None] * 6}
    b = pilot._board({"current": {"turn": 2, "yourIndex": 0, "players": [me, None]}})
    assert b.deck_contains_odds is None
    assert b.deck_contains_probability(1) == 1.0


# ============================================================ the dont-search-a-probable-whiff rung
BASIC_TUTOR = 1086      # Buddy-Buddy Poffin shape (bench_fill -> Basics)
MEGA, SIGNAL, FILLER, OTHER = 555, 556, 99, 999
STARYU = 800


def _whiff_stats():
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, synthetic=True, hp=330, megaEx=True, evolvesFrom="Riolu"),
        STARYU: CardStat(STARYU, hp=70, evolvesFrom=None),
        OTHER: CardStat(OTHER, synthetic=True, hp=90, evolvesFrom=None),
    })


@pytest.mark.req("REQ-GEN-0055")
def test_probable_whiff_stands_down_a_search_whose_sole_target_is_probably_prized():
    """PROBABLY, not provably, prized: the sole driver is dig-before-commit and the probable-whiff
    penalty drops it below End. NOT the sound guard — the target is still reachable."""
    _fm = {SIGNAL: ["search", "tutor_mega"]}
    funcs = CardFunctions(_fm)
    pilot = Pilot(Strategy(), deck=[MEGA] + [FILLER] * 40, general_strategy=GENERAL_STRATEGY,
                  stats=_whiff_stats(), functions=funcs, effects=fetch_effects(_fm))
    play_signal = opt(PLAY, area=HAND, index=0)
    # MEGA nowhere visible; 1 in deck, 5 hidden prizes -> P(in deck) = 1/6 < threshold.
    cur = state(active=poke(OTHER, energy=1), hand=[SIGNAL], prizes=5, deck_count=1)
    obs = make_select([play_signal, opt(END)], current=cur)
    assert pilot._context(obs, obs["select"], pilot._board(obs, obs["select"]),
                          obs["select"]["option"][0]).search_targets_unlikely
    fired = _fired(pilot.explain(obs).options[0])
    assert "dont-search-a-probable-whiff" in fired
    assert "dont-search-an-empty-deck" not in fired         # NOT sound guard — still reachable
    assert _ranked(pilot, obs)[0][0] == 1                          # End beats probable-whiff dig

    # Control: same board, no deckCount -> estimate silent -> dig is played.
    obs2 = make_select([play_signal, opt(END)],
                       current=state(active=poke(OTHER, energy=1), hand=[SIGNAL], prizes=5))
    assert "dont-search-a-probable-whiff" not in _fired(pilot.explain(obs2).options[0])
    assert _ranked(pilot, obs2)[0][0] == 0


@pytest.mark.req("REQ-GEN-0055")
def test_probable_whiff_stays_silent_when_the_target_is_plausibly_present():
    """2 of 3 Staryu unseen could sit in the 6 hidden prizes, so a 2nd Poffin is a PROBABILISTIC read
    rather than a whiff and the rung must not fire."""
    _fm = {BASIC_TUTOR: ["search", "bench_fill"]}
    funcs = CardFunctions(_fm)
    pilot = Pilot(Strategy(), deck=[STARYU] * 3 + [FILLER] * 57, general_strategy=GENERAL_STRATEGY,
                  stats=_whiff_stats(), functions=funcs, effects=fetch_effects(_fm))
    play_poffin = opt(PLAY, area=HAND, index=0)
    # 1 of 3 Staryu visible (discard); deck 30, 6 hidden prizes -> 2 unseen, P(in deck) ~ 0.98.
    cur = state(discard=[STARYU], hand=[BASIC_TUTOR], prizes=6, deck_count=30)
    obs = make_select([play_poffin, opt(END)], current=cur)
    ctx = pilot._context(obs, obs["select"], pilot._board(obs, obs["select"]),
                         obs["select"]["option"][0])
    assert not ctx.search_targets_unlikely
    assert "dont-search-a-probable-whiff" not in _fired(pilot.explain(obs).options[0])
    assert _ranked(pilot, obs)[0][0] == 0                          # play bench-filler — probably hits


@pytest.mark.req("REQ-GEN-0055")
def test_probable_whiff_is_mutually_exclusive_with_the_sound_empty_guard():
    """When EVERY target is provably gone, the sound `dont-search-an-empty-deck` owns the suppression;
    the probabilistic rung stays silent (it requires a still-reachable target), so they never double-count."""
    _fm = {SIGNAL: ["search", "tutor_mega"]}
    funcs = CardFunctions(_fm)
    pilot = Pilot(Strategy(), deck=[MEGA] * 2 + [FILLER] * 58, general_strategy=GENERAL_STRATEGY,
                  stats=_whiff_stats(), functions=funcs, effects=fetch_effects(_fm))
    play_signal = opt(PLAY, area=HAND, index=0)
    # Both Mega ex in discard -> provably gone (sound), regardless of prizes/deck.
    cur = state(discard=[MEGA, MEGA], hand=[SIGNAL], prizes=6, deck_count=10)
    obs = make_select([play_signal, opt(END)], current=cur)
    fired = _fired(pilot.explain(obs).options[0])
    assert "dont-search-an-empty-deck" in fired              # sound guard fires
    assert "dont-search-a-probable-whiff" not in fired       # probabilistic rung stands aside


# ── WP4: the Stage-2 draw-engine two-window closed form (hypergeometric-fetch-closure §Stage 2) ──
# Outs and engines are DISJOINT classes, so at depth 1 the form is EXACT — enumerated, not simulated.

@pytest.mark.req("REQ-GAMBLE-0011")
def test_two_window_form_matches_exhaustive_enumeration_at_depth_one():
    """Universe: pool 9 = 2 outs, 2 engines, 5 blanks; refresh n=3, one engine window m=2. The oracle
    enumerates both windows exhaustively — the exact expectation the closed form must reproduce."""
    from itertools import combinations
    from math import comb
    from common.deck_odds import draw_hit_with_engines
    cards = ["O", "O", "E", "E", "b", "b", "b", "b", "b"]
    n, m = 3, 2
    total = hit = 0
    for w1 in combinations(range(len(cards)), n):
        total += 1
        kinds = [cards[i] for i in w1]
        if "O" in kinds:
            hit += 1                                        # window 1 finds the out
            continue
        if "E" not in kinds:
            continue                                        # missed, no engine: the chain ends
        rest = [cards[i] for i in range(len(cards)) if i not in w1]
        sub_hit = sum(1 for w2 in combinations(range(len(rest)), m)
                      if any(rest[i] == "O" for i in w2))
        hit += sub_hit / comb(len(rest), m)                 # engine window over the thinned pool
    exact = hit / total
    assert draw_hit_with_engines(2, 9, 3, 2, (2,)) == pytest.approx(exact)


@pytest.mark.req("REQ-GAMBLE-0011")
def test_two_window_form_degenerates_bounds_and_fails_closed():
    """No engines / no windows → the plain window draw; engines only ever ADD; a deeper chain ≥ a
    shallower one; garbage → 0.0, because an endorser fails closed."""
    from common.deck_odds import draw_hit_probability, draw_hit_with_engines
    base = draw_hit_probability(3, 30, 6)
    assert draw_hit_with_engines(3, 30, 6, 0, (2,)) == pytest.approx(base)
    assert draw_hit_with_engines(3, 30, 6, 2, ()) == pytest.approx(base)
    one = draw_hit_with_engines(3, 30, 6, 2, (2,))
    two = draw_hit_with_engines(3, 30, 6, 2, (2, 2))
    assert base < one <= two <= 1.0
    assert draw_hit_with_engines(3, 30, 6, 2, (3,)) > one   # a wider engine window digs deeper
    assert draw_hit_with_engines(0, 30, 6, 2, (2,)) == 0.0  # no outs: nothing to assemble
    assert draw_hit_with_engines("x", 30, 6, 2, (2,)) == 0.0
    assert draw_hit_with_engines(3, 30, 6, "x", (2,)) == 0.0
