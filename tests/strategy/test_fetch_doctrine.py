"""Fetch Doctrine (ADR-0023): the need-gated grab / discard comparator that generalises the shipped
fetch rules (tests/test_search_discipline.py). Each behaviour is one need-gated Hypothesis on the
grab side or its keep-value mirror on the discard side, verified through the PUBLIC Pilot interface
(`decide` picks the option; `explain(...).fired` names the rules that fired). Importance is derived
(Lines / Function Tags / CardStat) and gated by a gap (what I currently lack); see
docs/general-strategy.md "Fetch (Search) doctrine".
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


# The fetch doctrine's whiff/redundancy/confirmed-hit signals read a search's FETCH CLAUSES from
# `card_effects.json` (ADR-0032), the tier that REPLACED the tag-keyed `_FETCH_FILTERS`. These synthetic
# fetchers carry TAGS only, so mirror the standard fetcher tags to their clauses (`fetch_effects`).
from pilot_helpers import fetch_effects as _fetch_effects   # noqa: E402


# --- fetch-a-starter: an underdeveloped board wants a Basic body to develop ----------------------
@pytest.mark.req("REQ-GEN-0035")
def test_fetch_a_starter_prefers_a_basic_when_the_board_is_thin():
    """At a search, with a thin bench in SETUP and no higher need, grab a startable Basic over a
    non-startable Stage-1 — develop the board."""
    stats = DictCardStatProvider({BASIC: CardStat(BASIC, hp=70),
                                  STAGE1: CardStat(STAGE1, hp=90, evolvesFrom="Basicmon")})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # SETUP (no win-condition Line), bench empty, Active already powered (not energy-starved).
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": STAGE1}, {"id": BASIC}],
                      current=state(active=poke(900, energy=1), bench=[]))
    assert pilot.decide(obs) == [1]                                   # Basic, not Stage-1
    assert "fetch-a-starter" in _fired(pilot.explain(obs).options[1])
    assert "fetch-a-starter" not in _fired(pilot.explain(obs).options[0])


# --- fetch-the-support: no engine piece in play -> grab one --------------------------------------
@pytest.mark.req("REQ-GEN-0036")
def test_fetch_the_support_grabs_an_engine_piece_when_none_is_in_play():
    """At a search, with the Bench developed (no starter need) but NO engine Pokémon in play, grab a
    support piece (a Pokémon with a draw / accel / search ability) over a vanilla body."""
    stats = DictCardStatProvider({SUPPORT: CardStat(SUPPORT, hp=90),
                                  PLAINMON: CardStat(PLAINMON, hp=90)})
    funcs = CardFunctions({SUPPORT: ["energy_accel"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    # bench developed (2 vanilla bodies -> no starter need); none of my Pokémon is an engine piece.
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": PLAINMON}, {"id": SUPPORT}],
                      current=state(active=poke(900, energy=1), bench=[poke(701), poke(702)]))
    assert pilot.decide(obs) == [1]                                   # engine piece, not vanilla
    assert "fetch-the-support" in _fired(pilot.explain(obs).options[1])
    assert "fetch-the-support" not in _fired(pilot.explain(obs).options[0])


# --- fetch-deck-priority: the deck's explicit Tier-3 grab order overrides the derived rungs -------
@pytest.mark.req("REQ-GEN-0037")
def test_fetch_deck_priority_grabs_the_decks_top_listed_candidate():
    """A deck declares an explicit ordered `fetch_priority`; among the candidates present, grab the
    one earliest in that list (the combo deck's escape hatch). Candidates are Stage-1s so no derived
    rung fires — the deck's list is the only signal."""
    stats = DictCardStatProvider({COMBO: CardStat(COMBO, hp=90, evolvesFrom="X"),
                                  FILLER: CardStat(FILLER, hp=90, evolvesFrom="Y")})
    strat = Strategy(fetch_priority=[COMBO, FILLER])
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": FILLER}, {"id": COMBO}],
                      current=state(active=poke(900, energy=1), bench=[poke(701), poke(702)]))
    assert pilot.decide(obs) == [1]                                   # COMBO — deck-list top
    assert "fetch-deck-priority" in _fired(pilot.explain(obs).options[1])
    assert "fetch-deck-priority" not in _fired(pilot.explain(obs).options[0])


# --- covered-in-play (ADR-0066): a forced discard sheds a copy whose job is already carried ------
@pytest.mark.req("REQ-GEN-0038")
def test_discard_the_redundant_sheds_a_duplicate_already_in_play():
    """The equation's cover discount (was `discard-the-redundant`): among two same-worth engine
    bodies, the copy already in play carries the job — its hand duplicate pitches FREE (bracket 0)
    while the still-lacking one keeps its full floor (ep83686860 f18's inverse)."""
    stats = DictCardStatProvider({DUP: CardStat(DUP, hp=90), NEEDED: CardStat(NEEDED, hp=90)})
    funcs = CardFunctions({DUP: ["draw"], NEEDED: ["draw"]})          # same worth band for both
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  functions=funcs)
    # forced to discard one of {DUP, NEEDED}: DUP already benched (covered); NEEDED not in play.
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=DISCARD_SEL,
                      current=state(bench=[poke(DUP)], hand=[DUP, NEEDED]))
    dec = pilot.explain(obs)
    assert dec.options[0].score == 0                                  # covered: pitches free
    assert dec.options[1].score < 0                                   # uncovered: floored
    assert pilot.decide(obs) == [0]                                   # pitch the covered duplicate


# --- fetch the deployable base over a payoff you can't yet evolve --------------------------------
BASEP, PAYP = 1030, 1031


@pytest.mark.req("REQ-GEN-0039")
def test_fetch_prefers_the_base_when_the_payoff_is_not_yet_deployable():
    """At a search revealing BOTH the evolved payoff and its own pre-evolution, with NO base for the
    payoff in play OR hand, grab the deployable base — fetching a payoff you have nothing to evolve
    from just strands it (and a bench-accelerator like Cinderace gets no recipient). `fetch-the-wincon`
    otherwise pulls the un-evolvable payoff (the verified mega_starmie trap)."""
    stats = DictCardStatProvider({BASEP: CardStat(BASEP, hp=70),
                                  PAYP: CardStat(PAYP, megaEx=True, hp=330, evolvesFrom="Basep")})
    strat = Strategy(lines=[Line(path=[BASEP, PAYP], payoff=PAYP, role="win_condition")],
                     roles={PAYP: ["win_condition", "primary_attacker"], BASEP: ["starter"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # Active powered (not energy-starved); bench empty; hand empty -> no base in play or in hand.
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": BASEP}, {"id": PAYP}],
                      current=state(active=poke(666, energy=1), bench=[], hand=[]))
    assert pilot.decide(obs) == [0]                                   # deployable base, not payoff


@pytest.mark.req("REQ-GEN-0039")
def test_fetch_takes_the_payoff_once_a_base_is_in_hand():
    """The inverse guard: with a base already in HAND the payoff IS deployable, so prefer the payoff
    (`fetch-the-wincon`) — `fetch-base-before-stranded-payoff` stands down (don't over-correct)."""
    stats = DictCardStatProvider({BASEP: CardStat(BASEP, hp=70),
                                  PAYP: CardStat(PAYP, megaEx=True, hp=330, evolvesFrom="Basep")})
    strat = Strategy(lines=[Line(path=[BASEP, PAYP], payoff=PAYP, role="win_condition")],
                     roles={PAYP: ["win_condition", "primary_attacker"], BASEP: ["starter"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": BASEP}, {"id": PAYP}],
                      current=state(active=poke(666, energy=1), bench=[], hand=[BASEP]))
    assert pilot.decide(obs) == [1]                                   # payoff — base is in hand
    assert "fetch-base-before-stranded-payoff" not in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0039")
def test_fetch_base_rule_never_zeroes_the_payoff():
    """Additive guard: with NO base deployable but the base absent from the reveal, the payoff is still
    the best grab over an off-need filler — `fetch-base-before-stranded-payoff` lifts the base, it never
    suppresses the payoff, so when only the payoff is on offer you still take it."""
    stats = DictCardStatProvider({PAYP: CardStat(PAYP, megaEx=True, hp=330, evolvesFrom="Basep"),
                                  860: CardStat(860, hp=90, evolvesFrom="Z")})   # off-need Stage-1 filler
    strat = Strategy(lines=[Line(path=[BASEP, PAYP], payoff=PAYP, role="win_condition")],
                     roles={PAYP: ["win_condition", "primary_attacker"], BASEP: ["starter"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": PAYP}, {"id": 860}],
                      current=state(active=poke(666, energy=1), bench=[], hand=[]))
    assert pilot.decide(obs) == [0]                                   # still grabs payoff


# --- hand-duplicate cover (ADR-0066): a second held copy pitches free, the singleton is floored --
@pytest.mark.req("REQ-GEN-0038")
def test_discard_the_hand_duplicate_pitches_a_duplicate_effect_card_over_a_singleton():
    """The hand-internal cover (was `discard-the-hand-duplicate`, now the equation's marginal): a
    card held in 2+ copies pitches its spare FREE (the kept copy carries the job), while the same-
    band SINGLETON keeps its floor — so a lone engine card is never discarded over a duplicate."""
    stats = DictCardStatProvider({HANDDUP: CardStat(HANDDUP, hp=0, cardType=SUPPORTER_CT),
                                  HSINGLE: CardStat(HSINGLE, hp=0, cardType=SUPPORTER_CT)})
    funcs = CardFunctions({HANDDUP: ["draw"], HSINGLE: ["draw"]})     # same worth band for both
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  functions=funcs)
    # forced to discard one of {HANDDUP, HANDDUP, HSINGLE}: pitch a dup copy, keep the singleton.
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1), card_opt(HAND, 2)], context=DISCARD_SEL,
                      current=state(hand=[HANDDUP, HANDDUP, HSINGLE]))
    dec = pilot.explain(obs)
    assert dec.options[0].score == 0 and dec.options[1].score == 0    # spares: free
    assert dec.options[2].score < 0                                   # singleton: floored
    assert pilot.decide(obs) in ([0], [1])                            # dup copy, not singleton


@pytest.mark.req("REQ-GEN-0038")
def test_discard_the_hand_duplicate_excludes_fungible_energy():
    """A spare Basic Energy is fungible — always a future attach, never a redundant pitch — so the
    cover discount never distinguishes two held copies (both price identically; on a board with no
    starved Active they cycle free)."""
    stats = DictCardStatProvider({DUPENERGY: CardStat(DUPENERGY, hp=0, cardType=BASIC_ENERGY_CT)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=DISCARD_SEL,
                      current=state(hand=[DUPENERGY, DUPENERGY]))
    dec = pilot.explain(obs)
    assert dec.options[0].score == dec.options[1].score               # fungible: no dup penalty


# --- the fodder zone sign (ADR-0066): a deck redirects the pitch to its discard-synergy fodder ----
@pytest.mark.req("REQ-GEN-0039")
def test_prefer_good_in_discard_pitches_the_decks_fodder_card():
    """The zone sign (was `prefer-good-in-discard`): a recursion / discard-fed deck flags a card
    `discard_fodder` (its value is realised IN the bin); at a forced discard it scores POSITIVE —
    pitched ahead of any merely-free card."""
    stats = DictCardStatProvider({FODDER: CardStat(FODDER, hp=90), KEEPCARD: CardStat(KEEPCARD, hp=90)})
    strat = Strategy(roles={FODDER: ["discard_fodder"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=DISCARD_SEL,
                      current=state(hand=[FODDER, KEEPCARD]))
    dec = pilot.explain(obs)
    assert dec.options[0].score > 0                                   # the bin is an asset
    assert pilot.decide(obs) == [0]                                   # pitch deck's discard-synergy card


# --- multi-pick (greedy gap-update): a single max>1 grab dedups a satisfied need -----------------
@pytest.mark.req("REQ-GEN-0040")
def test_multi_pick_grab_dedups_a_satisfied_need():
    """A TO_HAND grab of up to 2 (one select, maxCount=2): revealing two win-condition copies plus a
    Basic, grab ONE wincon (its need is met after the first pick) and then the Basic — not two dead
    wincon copies, which static top-N would take."""
    stats = DictCardStatProvider({WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  BASIC: CardStat(BASIC, hp=70)})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1), card_opt(DECK, 2)],
                      min_count=0, max_count=2, context=TO_HAND,
                      deck=[{"id": WINC}, {"id": WINC}, {"id": BASIC}],
                      current=state(active=poke(900, energy=1), bench=[]))
    assert sorted(pilot.decide(obs)) == [0, 2]                        # one wincon + Basic, not [0, 1]


# --- multi-pick (take-fewer): with minCount 0, stop grabbing once nothing is still needed ---------
@pytest.mark.req("REQ-GEN-0040")
def test_multi_pick_grab_takes_fewer_than_max_when_no_need_remains():
    """A TO_HAND grab of up to 2 with minCount 0: one Basic fills the lone starter need; the remaining
    off-need Stage-1s are worth nothing, so grab ONLY the Basic — don't take a second dead card just
    because maxCount allows it (static top-N would)."""
    stats = DictCardStatProvider({BASIC: CardStat(BASIC, hp=70),
                                  STAGE1: CardStat(STAGE1, hp=90, evolvesFrom="Basicmon")})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1), card_opt(DECK, 2)],
                      min_count=0, max_count=2, context=TO_HAND,
                      deck=[{"id": BASIC}, {"id": STAGE1}, {"id": STAGE1}],
                      current=state(active=poke(900, energy=1), bench=[]))
    assert pilot.decide(obs) == [0]                                   # only Basic; no dead 2nd grab


# --- bench-fill grab (TO_BENCH): a min0 bench placement must bench the Basics, not whiff to [] -------
@pytest.mark.req("REQ-GEN-0035")
def test_bench_fill_grab_benches_basics_at_to_bench():
    """A Buddy-Poffin-style bench placement (`_TO_BENCH`, up to 2, minCount 0) presents CARD candidates
    that the `_PLAY`-gated bench reflexes and the `_TO_HAND`-gated fetch rungs never score. Without a
    bench-context rung every candidate scores 0 and the greedy take-fewer benches NOTHING (returns []);
    `bench-fill-a-basic` scores the startable Basics so the grab benches them (the post-refactor whiff)."""
    stats = DictCardStatProvider({BASIC: CardStat(BASIC, hp=70),
                                  STAGE1: CardStat(STAGE1, hp=90, evolvesFrom="Basicmon")})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # TO_BENCH, up to 2, minCount 0: two Basics + a non-Basic Stage-1 revealed from deck.
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1), card_opt(DECK, 2)],
                      min_count=0, max_count=2, context=TO_BENCH,
                      deck=[{"id": BASIC}, {"id": BASIC}, {"id": STAGE1}],
                      current=state(active=poke(900, energy=1), bench=[]))
    assert sorted(pilot.decide(obs)) == [0, 1]                        # bench both Basics, not [] (no whiff)
    assert "bench-fill-a-basic" in _fired(pilot.explain(obs).options[0])
    assert "bench-fill-a-basic" not in _fired(pilot.explain(obs).options[2])  # Stage-1 isn't a starter


# --- whether-to-play (slice 7): a cost_discard fetch is endorsed when it can grab a needed card ---
@pytest.mark.req("REQ-GEN-0041")
def test_fetch_is_endorsed_when_it_can_grab_a_needed_card():
    """An Ultra Ball-type cost_discard fetch gets NO endorsement from dig-before-commit (which excludes
    cost_discard). The whether-to-play lookahead endorses it when its reachable deck set contains a card
    I currently lack (here the unfound win-condition) — so it's played over End."""
    stats = DictCardStatProvider({ULTRA: CardStat(ULTRA, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  BASIC: CardStat(BASIC, hp=70)})
    fmap = {ULTRA: ["search", "tutor_pokemon", "cost_discard"]}
    funcs = CardFunctions(fmap)
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[WINC, BASIC, BASIC], general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs, effects=_fetch_effects(fmap))
    # the win-condition is NOT in play (active is a plain body) -> the fetch can grab it -> endorse.
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(900, energy=1), bench=[poke(701), poke(702)], hand=[ULTRA]))
    assert "fetch-when-it-fills-a-need" in _fired(pilot.explain(obs).options[0])
    assert pilot.explain(obs).options[0].score > 0                   # the endorsement gives it value
    assert pilot.decide(obs) == [0]                                  # so the fetch is played, not End


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
@pytest.mark.req("REQ-GEN-0058")
def test_play_a_tutor_for_the_unfound_wincon_is_role_keyed_and_gated_on_wincon_in_hand():
    """During SETUP a `tutor`-Roled Trainer is endorsed while the win-condition is unfound; the
    endorsement stands down once the payoff is already in hand."""
    TUTOR = 1145
    strat = Strategy(roles={TUTOR: ["tutor"], WINC: ["win_condition"]},
                     lines=[Line(path=[BASIC, WINC], payoff=WINC, role="win_condition")])
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY)

    digging = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)],
                          current=state(hand=[TUTOR, 111]))
    assert "play-a-tutor-for-the-unfound-wincon" in _fired(pilot.explain(digging).options[0])
    assert "play-a-tutor-for-the-unfound-wincon" not in _fired(pilot.explain(digging).options[1])

    held = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)],
                       current=state(hand=[TUTOR, WINC]))
    assert "play-a-tutor-for-the-unfound-wincon" not in _fired(pilot.explain(held).options[0])


# --- dont-fetch-the-setup-only-opener: folded from mega_starmie `never-fetch-cinderace` ----------
@pytest.mark.req("REQ-GEN-0061")
def test_dont_fetch_the_setup_only_opener_requires_the_stranded_evolution_chain():
    """An `opener`-tagged card is penalised at a search ONLY when its previous-stage chain is
    unreachable from the deck list (dead in hand — e.g. a Stage-2 Explosiveness opener with no
    Stage 1 in the deck). With the chain present the penalty must stand down."""
    OPENER, RABOOT = 666, 667
    stats = DictCardStatProvider({
        OPENER: CardStat(OPENER, name="Cinderace", hp=160, evolvesFrom="Raboot", hasAbility=True),
        RABOOT: CardStat(RABOOT, name="Raboot", hp=90),                  # a Basic in these stats
        BASIC: CardStat(BASIC, hp=70)})
    funcs = CardFunctions({OPENER: ["opener"]})
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": OPENER}, {"id": BASIC}], current=state(hand=[]))

    # no Raboot in deck list -> opener can never deploy from hand -> penalised.
    stranded = Pilot(Strategy(), deck=[OPENER] * 4 + [1] * 56,
                     general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    assert "dont-fetch-the-setup-only-opener" in _fired(stranded.explain(obs).options[0])
    assert "dont-fetch-the-setup-only-opener" not in _fired(stranded.explain(obs).options[1])
    assert stranded.decide(obs) == [1]                    # take line piece, never the opener

    # Raboot (a Basic here) in deck -> opener evolvable from hand -> no penalty.
    fed = Pilot(Strategy(), deck=[OPENER] * 4 + [RABOOT] * 4 + [1] * 52,
                general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    assert "dont-fetch-the-setup-only-opener" not in _fired(fed.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0061")
def test_stranded_chain_check_walks_the_full_previous_stage_chain():
    """Chain reachability is FULL-depth: Stage 1 present but ITS Basic missing -> still stranded."""
    OPENER, RABOOT = 666, 667
    stats = DictCardStatProvider({
        OPENER: CardStat(OPENER, name="Cinderace", hp=160, evolvesFrom="Raboot"),
        RABOOT: CardStat(RABOOT, name="Raboot", hp=90, evolvesFrom="Scorbunny"),  # own base missing
        BASIC: CardStat(BASIC, hp=70)})
    funcs = CardFunctions({OPENER: ["opener"]})
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": OPENER}, {"id": BASIC}], current=state(hand=[]))
    pilot = Pilot(Strategy(), deck=[OPENER] * 4 + [RABOOT] * 4 + [1] * 52,
                  general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    assert "dont-fetch-the-setup-only-opener" in _fired(pilot.explain(obs).options[0])


# --- search-the-confirmed-hit: the POSITIVE complement of the two whiff guards (ADR-0029) --------
END = 14                # OptionType.END (not exported by pilot_helpers)
MEGA, SIGNAL = 555, 556  # a Mega ex payoff and its tutor (Mega Signal shape, tutor_mega)


def _confirmed_stats():
    # FILLER stays stat-LESS on purpose: it must join no fetch-filter set (a pure deck body).
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, hp=330, megaEx=True, evolvesFrom="Riolu"),
        BASIC: CardStat(BASIC, hp=70),
    })


def _confirmed_pilot(deck):
    fmap = {SIGNAL: ["search", "tutor_mega"], ULTRA: ["search", "bench_fill"]}
    funcs = CardFunctions(fmap)
    strat = Strategy(roles={MEGA: ["win_condition"]})
    return Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY,
                 stats=_confirmed_stats(), functions=funcs, effects=_fetch_effects(fmap))


@pytest.mark.req("REQ-GEN-0063")
def test_search_the_confirmed_hit_fires_only_once_the_tracker_proves_the_needed_target():
    """Once the deck-tracker has anchored the prizes (`own_prizes` -> exact deck counts), a tutor whose
    NEEDED target (positive grab value: the unfound win-condition) is PROVABLY still in the deck is a
    certain hit — the endorsement fires and the search plays. The SAME board without the annotation
    makes no positive claim (sound-or-silent, ADR-0029): the rule stays quiet."""
    pilot = _confirmed_pilot([MEGA] * 2 + [SIGNAL] * 2 + [FILLER] * 56)
    play_signal = opt(PLAY, area=HAND, index=0)
    cur = state(active=poke(FILLER, energy=1), hand=[SIGNAL], prizes=6, deck_count=20)
    obs = make_select([play_signal, opt(END)], current=cur)
    obs["own_prizes"] = {FILLER: 6}                    # anchored: no MEGA prized -> both provably in deck
    fired = _fired(pilot.explain(obs).options[0])
    assert "search-the-confirmed-hit" in fired
    assert pilot.decide(obs) == [0]                    # the certain hit is played over End

    unanchored = make_select([play_signal, opt(END)], current=cur)
    assert "search-the-confirmed-hit" not in _fired(pilot.explain(unanchored).options[0])


@pytest.mark.req("REQ-GEN-0063")
def test_search_the_confirmed_hit_stands_aside_for_the_redundant_wincon_veto():
    """A provably-present target the dig would be REDUNDANT for (the wincon-only tutor with the payoff
    already in hand) is `dont-tutor-the-held-wincon`'s case (-45): the endorsement must not co-fire
    against it — presence alone is not a hit worth digging for."""
    pilot = _confirmed_pilot([MEGA] * 2 + [SIGNAL] * 2 + [FILLER] * 56)
    play_signal = opt(PLAY, area=HAND, index=0)
    cur = state(active=poke(FILLER, energy=1), hand=[SIGNAL, MEGA], prizes=6, deck_count=20)
    obs = make_select([play_signal, opt(END)], current=cur)
    obs["own_prizes"] = {FILLER: 6}                    # a MEGA provably in deck — but one is in hand
    fired = _fired(pilot.explain(obs).options[0])
    assert "dont-tutor-the-held-wincon" in fired
    assert "search-the-confirmed-hit" not in fired


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


@pytest.mark.req("REQ-GEN-0063")
def test_confirmed_hit_prefers_the_provable_search_between_two_digs():
    """Two searches on the menu after the anchor: the Mega-tutor provably hits the needed payoff; the
    bench-filler's every Basic is prized away. The confirmed hit is endorsed, the certain whiff vetoed —
    the Pilot plays the provable dig."""
    pilot = _confirmed_pilot([MEGA] * 2 + [BASIC] * 3 + [SIGNAL] * 2 + [ULTRA] * 2 + [FILLER] * 51)
    play_signal, play_poffin = opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)
    cur = state(active=poke(BASIC, energy=1), hand=[SIGNAL, ULTRA], prizes=6, deck_count=20)
    obs = make_select([play_signal, play_poffin, opt(END)], current=cur)
    obs["own_prizes"] = {BASIC: 2, FILLER: 4}          # the 2 unseen Basics prized; the Megas stay in deck
    d = pilot.explain(obs)
    assert "search-the-confirmed-hit" in _fired(d.options[0])
    assert "search-the-confirmed-hit" not in _fired(d.options[1])
    assert pilot.decide(obs)[0] == 0                   # the provable hit leads the turn's digs


@pytest.mark.req("REQ-GEN-0061")
def test_fetch_the_support_never_endorses_a_stranded_support():
    """An engine-tagged Pokémon that is a stranded evolution (energy_accel Cinderace, no Raboot in
    deck) is a dead grab — `fetch-the-support` must not endorse it even with no support in play."""
    OPENER, LIVEMON, PLAINMON = 666, 868, 869
    stats = DictCardStatProvider({
        OPENER: CardStat(OPENER, name="Cinderace", hp=160, evolvesFrom="Raboot"),
        LIVEMON: CardStat(LIVEMON, name="Livemon", hp=90),           # a Basic support
        PLAINMON: CardStat(PLAINMON, name="Plainmon", hp=80)})       # non-engine Active
    funcs = CardFunctions({OPENER: ["opener", "energy_accel"], LIVEMON: ["energy_accel"]})
    pilot = Pilot(Strategy(), deck=[OPENER] * 4 + [LIVEMON] * 2 + [PLAINMON] + [1] * 53,
                  general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": OPENER}, {"id": LIVEMON}],
                      current=state(active=poke(PLAINMON, energy=1), hand=[]))  # powered: not the famine case
    stranded, live = pilot.explain(obs).options
    assert "fetch-the-support" not in _fired(stranded)   # dead grab, engine tag notwithstanding
    assert "fetch-the-support" in _fired(live)           # deployable support keeps the rung


# --- cost-netting (ADR-0023 amendment): the shed side prices the discard cost ---------------------
JUNKMON = 660           # a Basic duplicated in play AND hand -> a provably-junk shed


STARYU = 1030           # WINC's base — in the decklist so the wincon is DEPLOYABLE (its keep floor
                        # is live; without it the Stage-1 gate prices an undeployable evolution free)


def _netting_pilot(*, deck, extra_funcs=None, extra_stats=None, extra_roles=None):
    stats = DictCardStatProvider({ULTRA: CardStat(ULTRA, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  STARYU: CardStat(STARYU, name="Staryu", hp=70),
                                  JUNKMON: CardStat(JUNKMON, hp=70), **(extra_stats or {})})
    fmap = {ULTRA: ["search", "tutor_pokemon", "cost_discard"], **(extra_funcs or {})}
    funcs = CardFunctions(fmap)
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"], **(extra_roles or {})})
    return Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs,
                 effects=_fetch_effects(fmap))


@pytest.mark.req("REQ-GEN-0065")
def test_costly_fetch_sheds_junk_boosts_ultra_ball_to_the_free_dig_band():
    """Two actively-wanted sheds (the deck's `discard_fodder` — the zone sign, ADR-0066) + a needed
    grab in deck lift the cost_discard fetch into the free-dig band: `costly-fetch-sheds-junk` rides
    on `fetch-when-it-fills-a-need` and the fetch is played. (Merely-FREE sheds — covered duplicates
    — are neutral, not junk: the pessimism-baseline test below.)"""
    pilot = _netting_pilot(deck=[WINC, JUNKMON], extra_roles={JUNKMON: ["discard_fodder"]})
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(900, energy=1),
                                    bench=[poke(JUNKMON), poke(702)],
                                    hand=[ULTRA, JUNKMON, JUNKMON]))
    fired = _fired(pilot.explain(obs).options[0])
    assert "costly-fetch-sheds-junk" in fired
    assert "fetch-when-it-fills-a-need" in fired
    assert pilot.explain(obs).options[0].score >= 20               # free-dig band
    assert pilot.decide(obs) == [0]


ENGINE_SUP = 661        # a draw Supporter — live at a forced discard (keep-engine floor)


@pytest.mark.req("REQ-GEN-0065")
def test_dont_shed_a_live_card_suppresses_the_fetch_below_end():
    """When a LIVE card (a draw Supporter, negative keep-value at the discard) is forced into the
    predicted top-2 sheds, `dont-shed-a-live-card` nets the fetch below End — the ep83007714-f8
    'tossing the supporters is a poor trade' shape."""
    pilot = _netting_pilot(deck=[WINC, JUNKMON], extra_funcs={ENGINE_SUP: ["draw"]},
                           extra_stats={ENGINE_SUP: CardStat(ENGINE_SUP, hp=0, cardType=SUPPORTER_CT)})
    # only two shed candidates: one junk (benched duplicate), one LIVE engine Supporter.
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(900, energy=1),
                                    bench=[poke(JUNKMON), poke(702)],
                                    hand=[ULTRA, JUNKMON, ENGINE_SUP]))
    trace = pilot.explain(obs).options[0]
    assert "dont-shed-a-live-card" in _fired(trace)
    assert "costly-fetch-sheds-junk" not in _fired(trace)          # one live shed kills the junk band
    assert trace.score < 0
    assert pilot.decide(obs) == [1]                                # End over the bad trade


@pytest.mark.req("REQ-GEN-0065")
def test_dont_shed_a_key_card_stacks_the_fetch_unliftably_negative():
    """A KEY card (the win-condition, worth ≥ the key band and floored) forced into the predicted
    sheds fires `dont-shed-a-key-card` ON TOP of the live suppressor (−45 total): never pitch the
    wincon to dig — no normal-band endorsement stack can lift it back. Staryu rides in the decklist
    so the wincon is DEPLOYABLE — an undeployable one pitches free by design (the Stage-1 gate)."""
    pilot = _netting_pilot(deck=[WINC, JUNKMON, STARYU])
    # only two shed candidates: one covered/free, one the WIN-CONDITION (the key floor).
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(900, energy=1),
                                    bench=[poke(JUNKMON), poke(702)],
                                    hand=[ULTRA, JUNKMON, WINC]))
    trace = pilot.explain(obs).options[0]
    assert "dont-shed-a-key-card" in _fired(trace)
    assert "dont-shed-a-live-card" in _fired(trace)                # the key shed is also a live shed
    assert trace.score <= -30
    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0065")
def test_neutral_sheds_leave_the_fetch_at_the_pessimism_baseline():
    """Two NEUTRAL sheds (singletons, not in play, no floors) fire no netting rung — the fetch keeps
    exactly `fetch-when-it-fills-a-need`'s +8 (today's behavior, the corpus-fit middle band)."""
    NEUT1, NEUT2 = 662, 663
    pilot = _netting_pilot(deck=[WINC, JUNKMON],
                           extra_stats={NEUT1: CardStat(NEUT1, hp=60), NEUT2: CardStat(NEUT2, hp=60)})
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(900, energy=1), bench=[poke(701), poke(702)],
                                    hand=[ULTRA, NEUT1, NEUT2]))
    trace = pilot.explain(obs).options[0]
    fired = _fired(trace)
    assert {"costly-fetch-sheds-junk", "dont-shed-a-live-card", "dont-shed-a-key-card"} & fired == set()
    assert "fetch-when-it-fills-a-need" in fired
    assert pilot.decide(obs) == [0]                                # +8 still beats End


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
LIVEMON = 764          # a Basic Pokémon: always a live recycle target
WENERGY = 3            # a Basic {W} Energy: never dead


def _recycle_pilot(deck):
    stats = DictCardStatProvider({
        NIGHTS: CardStat(NIGHTS, hp=0),
        STRANDED: CardStat(STRANDED, name="Cinderace", hp=160, evolvesFrom="Raboot"),
        LIVEMON: CardStat(LIVEMON, name="Staryu", hp=70),
        WENERGY: CardStat(WENERGY, name="Basic {W} Energy", hp=0, energyType=3),
    })
    return Pilot(Strategy(), deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({NIGHTS: ["recycle"]}))


@pytest.mark.req("REQ-GEN-0066")
def test_dont_recycle_the_dead_holds_the_recycler_when_every_target_is_stranded():
    """ep83457493 f33: the only recycle target is the setup-only Explosiveness opener — a card this
    deck can never play from hand (no previous stage on the deck list). Fetching it back just burns
    the Item and jams the hand: End turn beats the recycler."""
    pilot = _recycle_pilot(deck=[STRANDED] * 2 + [1] * 58)      # no Raboot in deck -> stranded
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(900, energy=1), hand=[NIGHTS],
                                    discard=[STRANDED]))
    assert "dont-recycle-the-dead" in _fired(pilot.explain(obs).options[0])
    assert pilot.decide(obs) == [1]                             # End turn, not the dead recycle


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
