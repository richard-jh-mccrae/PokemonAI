"""Fetch Doctrine (ADR-0023): the need-gated grab / discard comparator.

Verified through the PUBLIC Pilot interface. Importance is derived (Lines / Function Tags /
CardStat) and gated by a gap; see docs/general-strategy.md "Fetch (Search) doctrine".
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from pilot_helpers import DECK, HAND, MAIN, PLAY, TO_HAND, card_opt, make_select, opt, poke, state

DISCARD_SEL = 8         # SelectContext.DISCARD — cost-discard select (pilot_helpers.DISCARD is the AreaType)
TO_BENCH = 5            # SelectContext.TO_BENCH — fetch Basics straight to Bench (Buddy-Buddy Poffin)
BASIC, STAGE1 = 700, 800
SUPPORT, PLAINMON = 850, 860
COMBO, FILLER = 950, 960
DUP, NEEDED = 770, 790
HANDDUP, HSINGLE, DUPENERGY = 771, 772, 773
SUPPORTER_CT, BASIC_ENERGY_CT = 3, 5       # CardType.SUPPORTER / CardType.BASIC_ENERGY
FODDER, KEEPCARD = 780, 781
WINC = 1031
ULTRA = 2001


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


def _ranked(pilot, obs):
    """The doctrine's ranking, best-first, as ``[(index, score), ...]``. Not `decide`: since
    Issue #386 the single-pick MAIN decision is the composer's, so `decide` would test that instead."""
    return [(o.index, o.score) for o in sorted(pilot.explain(obs).options, key=lambda o: -o.score)]


# The whiff/redundancy/confirmed-hit signals read FETCH CLAUSES (ADR-0032); these synthetic fetchers
# carry TAGS only, so `fetch_effects` mirrors the standard fetcher tags to clauses.
from pilot_helpers import fetch_effects as _fetch_effects   # noqa: E402


# --- fetch-a-starter: an underdeveloped board wants a Basic body to develop ----------------------


# --- fetch-the-support: no engine piece in play -> grab one --------------------------------------


# --- fetch-deck-priority: the deck's explicit Tier-3 grab order overrides the derived rungs -------


# --- discard-the-redundant: at a forced discard, shed a need-already-met card (keep-value floor) --
@pytest.mark.req("REQ-GEN-0038")
def test_discard_the_redundant_sheds_a_duplicate_already_in_play():
    """Graded on the DECISION since Issue #261 deleted the `_DISCARD` ladder: keep-value v2
    reproduces the pick without the rung, which is the evidence the rung was redundant."""
    stats = DictCardStatProvider({DUP: CardStat(DUP, synthetic=True, hp=90), NEEDED: CardStat(NEEDED, synthetic=True, hp=90)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # forced to discard one of {DUP, NEEDED}: DUP already benched (redundant); NEEDED not in play.
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=DISCARD_SEL,
                      current=state(bench=[poke(DUP)], hand=[DUP, NEEDED]))
    assert pilot.decide(obs) == [0]                                   # pitch redundant duplicate


# --- fetch the deployable base over a payoff you can't yet evolve --------------------------------
BASEP, PAYP = 1030, 1031


@pytest.mark.req("REQ-GEN-0039")
def test_fetch_prefers_the_base_when_the_payoff_is_not_yet_deployable():
    """Fetching a payoff with nothing to evolve from strands it; `fetch-the-wincon` would otherwise
    pull the un-evolvable payoff."""
    stats = DictCardStatProvider({BASEP: CardStat(BASEP, hp=70),
                                  PAYP: CardStat(PAYP, synthetic=True, megaEx=True, hp=330, evolvesFrom="Basep")})
    strat = Strategy(lines=[Line(path=[BASEP, PAYP], payoff=PAYP, role="win_condition")],
                     roles={PAYP: ["win_condition", "primary_attacker"], BASEP: ["starter"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # Active powered (not energy-starved); bench empty; hand empty -> no base in play or in hand.
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": BASEP}, {"id": PAYP}],
                      current=state(active=poke(666, energy=1), bench=[], hand=[]))
    assert pilot.decide(obs) == [0]                                   # deployable base, not payoff




@pytest.mark.req("REQ-GEN-0039")
def test_fetch_base_rule_never_zeroes_the_payoff():
    """`fetch-base-before-stranded-payoff` lifts the base; it never suppresses the payoff."""
    stats = DictCardStatProvider({PAYP: CardStat(PAYP, synthetic=True, megaEx=True, hp=330, evolvesFrom="Basep"),
                                  860: CardStat(860, synthetic=True, hp=90, evolvesFrom="Z")})   # off-need Stage-1 filler
    strat = Strategy(lines=[Line(path=[BASEP, PAYP], payoff=PAYP, role="win_condition")],
                     roles={PAYP: ["win_condition", "primary_attacker"], BASEP: ["starter"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": PAYP}, {"id": 860}],
                      current=state(active=poke(666, energy=1), bench=[], hand=[]))
    assert pilot.decide(obs) == [0]                                   # still grabs payoff


# --- discard-the-hand-duplicate: shed a hand-internal duplicate before a singleton disruptor ------
@pytest.mark.req("REQ-GEN-0038")
def test_discard_the_hand_duplicate_pitches_a_duplicate_effect_card_over_a_singleton():
    """A lone disruptor scores 0 under the flat keep-floors, so it must never be pitched over a
    duplicate engine card."""
    stats = DictCardStatProvider({HANDDUP: CardStat(HANDDUP, synthetic=True, hp=0, cardType=SUPPORTER_CT),
                                  HSINGLE: CardStat(HSINGLE, synthetic=True, hp=0, cardType=SUPPORTER_CT)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # forced to discard one of {HANDDUP, HANDDUP, HSINGLE}: pitch a dup copy, keep the singleton.
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1), card_opt(HAND, 2)], context=DISCARD_SEL,
                      current=state(hand=[HANDDUP, HANDDUP, HSINGLE]))
    assert pilot.decide(obs) in ([0], [1])                            # dup copy, not singleton


@pytest.mark.req("REQ-GEN-0038")
def test_discard_the_hand_duplicate_excludes_fungible_energy():
    """A spare Basic Energy is fungible — always a future attach, never a redundant pitch — so the
    hand-duplicate floor excludes it even when several are held."""
    stats = DictCardStatProvider({DUPENERGY: CardStat(DUPENERGY, synthetic=True, hp=0, cardType=BASIC_ENERGY_CT)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=DISCARD_SEL,
                      current=state(hand=[DUPENERGY, DUPENERGY]))


# --- prefer-good-in-discard: a deck redirects the pitch to its discard-synergy fodder ------------
@pytest.mark.req("REQ-GEN-0039")
def test_prefer_good_in_discard_pitches_the_decks_fodder_card():
    """The deck-override term: a recursion / discard-fed deck flags a card `discard_fodder` (good to
    have in the bin); at a forced discard, prefer pitching it over a generic card."""
    stats = DictCardStatProvider({FODDER: CardStat(FODDER, synthetic=True, hp=90), KEEPCARD: CardStat(KEEPCARD, synthetic=True, hp=90)})
    strat = Strategy(roles={FODDER: ["discard_fodder"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=DISCARD_SEL,
                      current=state(hand=[FODDER, KEEPCARD]))
    assert pilot.decide(obs) == [0]                                   # pitch deck's discard-synergy card


# --- multi-pick (greedy gap-update): a single max>1 grab dedups a satisfied need -----------------


# --- multi-pick (take-fewer): with minCount 0, stop grabbing once nothing is still needed ---------


# --- bench-fill grab (TO_BENCH): a min0 bench placement must bench the Basics, not whiff to [] -------
@pytest.mark.req("REQ-GEN-0035")
def test_bench_fill_grab_benches_basics_at_to_bench_for_deferred_decks():
    """Issue #388 decks retain the doctrine fallback and do not waste an optional search."""
    stats = DictCardStatProvider({BASIC: CardStat(BASIC, synthetic=True, hp=70),
                                  STAGE1: CardStat(STAGE1, synthetic=True, hp=90,
                                                   evolvesFrom="Basicmon")})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1), card_opt(DECK, 2)],
                      min_count=0, max_count=2, context=TO_BENCH,
                      deck=[{"id": BASIC}, {"id": BASIC}, {"id": STAGE1}],
                      current=state(active=poke(900, energy=1), bench=[]))
    assert sorted(pilot.decide(obs)) == [0, 1]
    assert not any("bench-fill-a-basic" in _fired(option) for option in pilot.explain(obs).options)


@pytest.mark.req("REQ-GEN-0035")
def test_poffin_leaf_pick_benches_mega_starmies_line_base_and_may_stop_above_minimum():
    """Issue #387: a useful Staryu has a positive leaf delta; the optional second pick may decline."""
    cinderace, staryu, mega = 666, 1030, 1031
    stats = DictCardStatProvider({cinderace: CardStat(cinderace, synthetic=True, name="Test Cinderace", hp=170),
                                  staryu: CardStat(staryu, synthetic=True, name="Test Staryu", hp=70),
                                  mega: CardStat(mega, synthetic=True, name="Test Mega", hp=330,
                                                 evolvesFrom="Test Staryu", megaEx=True)})
    strategy = Strategy(roles={cinderace: ["accel_source"], mega: ["win_condition", "primary_attacker"]},
                        lines=[Line(path=[staryu, mega], payoff=mega, role="win_condition")])
    pilot = Pilot(strategy, deck=[cinderace, staryu, mega] + [1] * 57,
                  general_strategy=GENERAL_STRATEGY, stats=stats, leaf_followups=True)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)],
                      min_count=0, max_count=2, context=TO_BENCH,
                      deck=[{"id": staryu}, {"id": cinderace}],
                      current=state(active=poke(cinderace, energy=1), bench=[], hand=[mega]))
    obs["search_begin_input"] = "seeded-poffin"
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-GEN-0035")
def test_mega_starmie_required_non_poffin_grab_keeps_a_legal_fallback():
    """A required TO_HAND menu belongs to Issue #388; unknown cards can never yield an illegal []."""
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  leaf_followups=True)
    obs = make_select([card_opt(DECK, i) for i in range(6)],
                      min_count=3, max_count=3, context=TO_HAND,
                      deck=[{} for _ in range(6)],
                      current=state(active=poke(900), bench=[]))
    chosen = pilot.decide(obs)
    assert len(chosen) == 3 and len(set(chosen)) == 3


@pytest.mark.req("REQ-DEPLOY-0001")
def test_the_deploy_marginal_prices_the_to_bench_entry_point():
    """ADR-0086 decision 6's third entry point. A `_TO_BENCH` candidate is a DECK card, so a
    `_deploy_decision` resolving against HAND rows returns `None` for every option."""
    stats = DictCardStatProvider({BASIC: CardStat(BASIC, synthetic=True, name="Basicmon", hp=70),
                                  WINC: CardStat(WINC, synthetic=True, megaEx=True, hp=330, evolvesFrom="Basicmon"),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, name="Plainmon", hp=60)})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[BASIC, WINC], payoff=WINC, role="win_condition")])
    pilot = Pilot(strat, deck=[BASIC, WINC, PLAINMON] + [PLAINMON] * 57,
                  general_strategy=GENERAL_STRATEGY, stats=stats)
    pilot.deploy_value = True
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)],
                      min_count=0, max_count=1, context=TO_BENCH,
                      deck=[{"id": PLAINMON}, {"id": BASIC}],
                      current=state(active=poke(900, energy=1), bench=[poke(900)]))
    traces = pilot.explain(obs).options
    assert traces[1].deploy_working is not None                       # the decider SPEAKS here now
    assert traces[1].deploy_working["cid"] == BASIC
    assert traces[1].score > traces[0].score                          # the Line base, not the filler
    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-DEPLOY-0001")
def test_the_to_bench_multi_pick_respects_the_engine_bench_capacity():
    """The structural capacity filter wins even when the select offers two mandatory candidates."""
    stats = DictCardStatProvider({BASIC: CardStat(BASIC, synthetic=True, name="Basicmon", hp=70),
                                  WINC: CardStat(WINC, synthetic=True, megaEx=True, hp=330, evolvesFrom="Basicmon"),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, name="Plainmon", hp=60)})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[BASIC, WINC], payoff=WINC, role="win_condition")])
    pilot = Pilot(strat, deck=[BASIC, WINC, PLAINMON] + [PLAINMON] * 57,
                  general_strategy=GENERAL_STRATEGY, stats=stats, leaf_followups=True)
    pilot.deploy_value = True
    pilot._greedy_grab = lambda *_args, **_kwargs: pytest.fail("Poffin reached the deferred owner")
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)],
                      min_count=1, max_count=2, context=TO_BENCH,
                      deck=[{"id": BASIC}, {"id": PLAINMON}],
                      current=state(active=poke(900, energy=1), bench=[poke(900)] * 4))
    obs["search_begin_input"] = "seeded-poffin-capacity"
    assert pilot.decide(obs) == [0]                                   # the Line base fills the last slot


# --- whether-to-play (slice 7): a cost_discard fetch is endorsed when it can grab a needed card ---


# --- whether-to-play: the endorsement is correctly SILENT when nothing is lacking ----------------
@pytest.mark.req("REQ-GEN-0041")
def test_fetch_endorsement_is_silent_when_no_need_remains():
    """The lookahead must not endorse a fetch that fills no need: with the win-condition already in play
    (and a developed board), the reachable set scores 0 -> the rung does not fire."""
    stats = DictCardStatProvider({ULTRA: CardStat(ULTRA, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu")})
    fmap = {ULTRA: ["search", "tutor_pokemon", "cost_discard"]}
    funcs = CardFunctions(fmap)
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[WINC], general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs,
                  effects=_fetch_effects(fmap))
    # win-condition already Active + bench developed -> the only reachable card fills no need.
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(WINC, energy=3),
                                    bench=[poke(701), poke(702), poke(703)], hand=[ULTRA]))
    assert "fetch-when-it-fills-a-need" not in _fired(pilot.explain(obs).options[0])


# --- play-a-tutor-for-the-unfound-wincon: folded from mega_starmie `tutor-the-wincon` ------------


# --- dont-fetch-the-setup-only-opener: folded from mega_starmie `never-fetch-cinderace` ----------




# --- search-the-confirmed-hit: the POSITIVE complement of the two whiff guards (ADR-0029) --------
END = 14                # OptionType.END (not exported by pilot_helpers)
MEGA, SIGNAL = 555, 556  # a Mega ex payoff and its tutor (Mega Signal shape, tutor_mega)


def _confirmed_stats():
    # FILLER stays stat-LESS on purpose: it must join no fetch-filter set (a pure deck body).
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, synthetic=True, hp=330, megaEx=True, evolvesFrom="Riolu"),
        BASIC: CardStat(BASIC, synthetic=True, hp=70),
    })


def _confirmed_pilot(deck):
    fmap = {SIGNAL: ["search", "tutor_mega"], ULTRA: ["search", "bench_fill"]}
    funcs = CardFunctions(fmap)
    strat = Strategy(roles={MEGA: ["win_condition"]})
    return Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY,
                 stats=_confirmed_stats(), functions=funcs, effects=_fetch_effects(fmap))






@pytest.mark.req("REQ-GEN-0063")
def test_search_the_confirmed_hit_stands_aside_for_the_sound_whiff_veto():
    """Provably ABSENT targets belong to `dont-search-an-empty-deck`; the endorsement never co-fires
    with it (deck_definitely_has and deck_definitely_empty_of are exclusive by construction)."""
    pilot = _confirmed_pilot([MEGA] * 2 + [SIGNAL] * 2 + [FILLER] * 56)
    play_signal = opt(PLAY, area=HAND, index=0)
    # both MEGA copies prized -> provably gone from the deck (and NOT in hand/play: still a need).
    cur = state(active=poke(FILLER, energy=1), hand=[SIGNAL], prizes=6, deck_count=20)
    obs = make_select([play_signal, opt(END)], current=cur)
    obs["own_prizes"] = {MEGA: 2, FILLER: 4}
    fired = _fired(pilot.explain(obs).options[0])
    assert "dont-search-an-empty-deck" in fired
    assert "search-the-confirmed-hit" not in fired






# --- cost-netting (ADR-0023 amendment): the shed side prices the discard cost ---------------------
JUNKMON = 660           # a Basic duplicated in play AND hand -> a provably-junk shed


STARYU = 1030           # WINC's base — WITHOUT it in play the wincon is STRANDED, not key


def _netting_pilot(*, deck, extra_funcs=None, extra_stats=None):
    stats = DictCardStatProvider({ULTRA: CardStat(ULTRA, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  STARYU: CardStat(STARYU, name="Staryu", hp=70),
                                  JUNKMON: CardStat(JUNKMON, synthetic=True, hp=70), **(extra_stats or {})})
    fmap = {ULTRA: ["search", "tutor_pokemon", "cost_discard"], **(extra_funcs or {})}
    funcs = CardFunctions(fmap)
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    return Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs,
                 effects=_fetch_effects(fmap))




BURST, NEUT_SINGLE, POWERED_ATK = 17, 662, 900




ENGINE_SUP = 661        # a draw Supporter — live at a forced discard (keep-engine floor)








@pytest.mark.req("REQ-GEN-0065")
def test_junk_boost_is_gated_on_a_real_need():
    """Junk sheds WITHOUT a needed grab get no boost: `costly-fetch-sheds-junk` is a modifier of the
    endorsement, not a standalone reason to burn two cards."""
    pilot = _netting_pilot(deck=[WINC, JUNKMON])
    # wincon already IN PLAY + developed bench -> the reachable set fills no need; sheds are junk.
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(WINC, energy=3),
                                    bench=[poke(JUNKMON), poke(702), poke(703)],
                                    hand=[ULTRA, JUNKMON, JUNKMON]))
    fired = _fired(pilot.explain(obs).options[0])
    assert "costly-fetch-sheds-junk" not in fired
    assert "fetch-when-it-fills-a-need" not in fired


# --- dont-recycle-the-dead: a discard-recycler with only dead targets is a wasted card -----------
NIGHTS = 1097          # Night Stretcher-like recycler (Function Tag `recycle`)
STRANDED = 666         # a Stage-2 setup-only opener (Cinderace): hand-unplayable in this deck
RABOOT_POOL = 667      # its previous stage — printed in the pool, absent from the deck list
LIVEMON = 764          # a Basic Pokémon: always a live recycle target
WENERGY = 3            # a Basic {W} Energy: never dead


def _recycle_pilot(deck):
    stats = DictCardStatProvider({
        NIGHTS: CardStat(NIGHTS, hp=0),
        STRANDED: CardStat(STRANDED, name="Cinderace", hp=160, evolvesFrom="Raboot"),
        RABOOT_POOL: CardStat(RABOOT_POOL, synthetic=True, name="Raboot", hp=90),   # in the POOL, never on the deck
        #   list. "Stranded" is a claim about the DECK; `common.playability` (ADR-0104) fails OPEN on
        #   a previous stage with no printing at all, because that is unreadable data, not a dead card.
        LIVEMON: CardStat(LIVEMON, synthetic=True, name="Staryu", hp=70),
        WENERGY: CardStat(WENERGY, name="Basic {W} Energy", hp=0, energyType=3),
    })
    return Pilot(Strategy(), deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({NIGHTS: ["recycle"]}))




@pytest.mark.req("REQ-GEN-0066")
def test_dont_recycle_the_dead_stays_silent_on_a_live_target():
    """A Basic Energy (or any deployable Pokémon) in the discard keeps the rule silent — recycling
    stays a normal option."""
    pilot = _recycle_pilot(deck=[STRANDED] * 2 + [1] * 58)
    live_energy = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                              current=state(active=poke(900, energy=1), hand=[NIGHTS],
                                            discard=[STRANDED, WENERGY]))
    assert "dont-recycle-the-dead" not in _fired(pilot.explain(live_energy).options[0])
    live_mon = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                           current=state(active=poke(900, energy=1), hand=[NIGHTS],
                                         discard=[LIVEMON]))
    assert "dont-recycle-the-dead" not in _fired(pilot.explain(live_mon).options[0])


# ── the DIG class: a fetcher whose target class is exhausted (ADR-0073, issue #164) ───────────────
GEAR = 2002            # a Pokégear-3.0-shaped Supporter fetcher: `target: supporter`, `dig: 7`
SUPP = 2003            # the Supporter it digs for


def _dig_pilot(deck):
    """A Pilot holding a DIG-class Supporter fetcher: `fetch_target_matches` rejects a ``dig`` clause
    for REACH, so `_search_deck_set` is empty and only the deadness reading can see it (ADR-0073)."""
    from common.effects import CardEffects
    fmap = {GEAR: ["search", "dig"]}
    stats = DictCardStatProvider({
        GEAR: CardStat(GEAR, hp=0, cardType=1),                 # CardType.ITEM
        SUPP: CardStat(SUPP, hp=0, cardType=SUPPORTER_CT),
        MEGA: CardStat(MEGA, synthetic=True, hp=330, megaEx=True, evolvesFrom="Riolu"),
    })
    effects = CardEffects({GEAR: [{"kind": "fetch", "target": "supporter",
                                   "zone": "deck", "dig": 7}]})
    return Pilot(Strategy(roles={MEGA: ["win_condition"]}), deck=deck,
                 general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions(fmap), effects=effects)


@pytest.mark.req("REQ-GEN-0063")
def test_the_dig_class_fetcher_is_vetoed_once_its_supporters_are_provably_gone():
    """The dig cannot find what is not there, so deadness is sound on a clause REACH must reject."""
    pilot = _dig_pilot([SUPP] * 2 + [GEAR] * 2 + [FILLER] * 56)
    play_gear = opt(PLAY, area=HAND, index=0)
    cur = state(active=poke(FILLER, energy=1), hand=[GEAR], prizes=6, deck_count=20)
    obs = make_select([play_gear, opt(END)], current=cur)
    obs["own_prizes"] = {SUPP: 2, FILLER: 4}            # both Supporters prized -> provably gone
    assert "dont-search-an-empty-deck" in _fired(pilot.explain(obs).options[0])
    assert pilot.decide(obs) != [0]                     # ...and the dead dig is not played


@pytest.mark.req("REQ-GEN-0063")
def test_the_dig_class_fetcher_is_left_alone_while_a_supporter_remains():
    """The other half of soundness: with a Supporter still reachable the veto stays silent — the
    widening suppresses nothing that could still be found."""
    pilot = _dig_pilot([SUPP] * 2 + [GEAR] * 2 + [FILLER] * 56)
    play_gear = opt(PLAY, area=HAND, index=0)
    cur = state(active=poke(FILLER, energy=1), hand=[GEAR], prizes=6, deck_count=20)
    obs = make_select([play_gear, opt(END)], current=cur)
    obs["own_prizes"] = {FILLER: 6}                     # no Supporter prized -> both still in deck
    assert "dont-search-an-empty-deck" not in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0063")
def test_the_dig_class_fetcher_never_claims_to_fill_a_need():
    """A dig-7 can only PROBABLY reach a Supporter, which is why the reach and deadness sets stay
    distinct rather than becoming one widened set (ADR-0073)."""
    pilot = _dig_pilot([SUPP] * 2 + [GEAR] * 2 + [FILLER] * 56)
    play_gear = opt(PLAY, area=HAND, index=0)
    cur = state(active=poke(FILLER, energy=1), hand=[GEAR], prizes=6, deck_count=20)
    obs = make_select([play_gear, opt(END)], current=cur)
    obs["own_prizes"] = {FILLER: 6}
    assert "fetch-when-it-fills-a-need" not in _fired(pilot.explain(obs).options[0])


# ── the cost oracle's coordinates ─────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-GEN-0065")
def test_cost_shed_indices_are_HAND_positions_not_row_ordinals():
    """`_needs_hand_rows` drops the played card before enumerating, so a row ordinal is one short of
    the hand position for every card after it. The played card sits MID-hand or the two coincide."""
    pilot = _netting_pilot(deck=[WINC, JUNKMON])
    obs = make_select([opt(PLAY, index=1), opt(14)], context=MAIN,
                      current=state(active=poke(900, energy=1),
                                    bench=[poke(JUNKMON), poke(702)],
                                    hand=[JUNKMON, ULTRA, JUNKMON, JUNKMON]))
    model = pilot._leaf_state_model(obs, 0)
    taken = pilot.cost_shed_indices(model, {"type": PLAY, "index": 1}, 2)

    hand = obs["current"]["players"][0]["hand"]
    assert len(taken) == 2, taken
    assert 1 not in taken, "the played card is never its own payment (the engine's `handOthers`)"
    assert all(0 <= i < len(hand) for i in taken), (taken, len(hand))
    assert [hand[i]["id"] for i in taken] == [JUNKMON, JUNKMON]
    # the row ordinals it came from must be DIFFERENT numbers, or this hand proves nothing
    plan = pilot._cost_shed(obs, exclude_cid=ULTRA, picks=2)
    assert plan.row_indices != plan.hand_indices or 1 in plan.row_indices, (
        "fixture is vacuous unless the two coordinate systems actually diverge here")
    assert plan.hand_indices == taken


# --- the doctrine's ROLE after POC-T4/5 (Issue #386) ---------------------------------------------
