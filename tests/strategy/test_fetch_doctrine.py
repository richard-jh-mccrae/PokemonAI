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

DISCARD_SEL = 8         # SelectContext.DISCARD — a cost-discard select (pilot_helpers.DISCARD is the AreaType)
TO_BENCH = 5            # SelectContext.TO_BENCH — fetch Basics straight onto the Bench (Buddy-Buddy Poffin)
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
    assert pilot.decide(obs) == [1]                                   # the Basic, not the Stage-1
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
    assert pilot.decide(obs) == [1]                                   # the engine piece, not the vanilla
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
    assert pilot.decide(obs) == [1]                                   # COMBO — top of the deck's list
    assert "fetch-deck-priority" in _fired(pilot.explain(obs).options[1])
    assert "fetch-deck-priority" not in _fired(pilot.explain(obs).options[0])


# --- discard-the-redundant: at a forced discard, shed a need-already-met card (keep-value floor) --
@pytest.mark.req("REQ-GEN-0038")
def test_discard_the_redundant_sheds_a_duplicate_already_in_play():
    """The discard side of the comparator: among cards you must pitch, shed the one whose need is
    already satisfied — here a duplicate of a Pokémon already in play — over one you still lack."""
    stats = DictCardStatProvider({DUP: CardStat(DUP, hp=90), NEEDED: CardStat(NEEDED, hp=90)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # forced to discard one of {DUP, NEEDED}: DUP is already benched (redundant); NEEDED is not in play.
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=DISCARD_SEL,
                      current=state(bench=[poke(DUP)], hand=[DUP, NEEDED]))
    assert pilot.decide(obs) == [0]                                   # pitch the redundant duplicate
    assert "discard-the-redundant" in _fired(pilot.explain(obs).options[0])
    assert "discard-the-redundant" not in _fired(pilot.explain(obs).options[1])


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
    assert pilot.decide(obs) == [0]                                   # the deployable base, not the payoff


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
    assert pilot.decide(obs) == [1]                                   # the payoff — a base is in hand
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
    assert pilot.decide(obs) == [0]                                   # still grab the payoff


# --- discard-the-hand-duplicate: shed a hand-internal duplicate before a singleton disruptor ------
@pytest.mark.req("REQ-GEN-0038")
def test_discard_the_hand_duplicate_pitches_a_duplicate_effect_card_over_a_singleton():
    """The hand-internal mirror of `discard-the-redundant`: among cards you must pitch, shed one you
    hold 2+ copies of in hand (keep one) before a SINGLETON — so a lone disruptor (which the flat
    keep-floors miss, scoring 0) is never discarded over a duplicate engine card."""
    stats = DictCardStatProvider({HANDDUP: CardStat(HANDDUP, hp=0, cardType=SUPPORTER_CT),
                                  HSINGLE: CardStat(HSINGLE, hp=0, cardType=SUPPORTER_CT)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # forced to discard one of {HANDDUP, HANDDUP, HSINGLE}: pitch a duplicate copy, keep the singleton.
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1), card_opt(HAND, 2)], context=DISCARD_SEL,
                      current=state(hand=[HANDDUP, HANDDUP, HSINGLE]))
    assert pilot.decide(obs) in ([0], [1])                            # a duplicate copy, not the singleton
    assert "discard-the-hand-duplicate" in _fired(pilot.explain(obs).options[0])
    assert "discard-the-hand-duplicate" not in _fired(pilot.explain(obs).options[2])


@pytest.mark.req("REQ-GEN-0038")
def test_discard_the_hand_duplicate_excludes_fungible_energy():
    """A spare Basic Energy is fungible — always a future attach, never a redundant pitch — so the
    hand-duplicate floor excludes it even when several are held."""
    stats = DictCardStatProvider({DUPENERGY: CardStat(DUPENERGY, hp=0, cardType=BASIC_ENERGY_CT)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=DISCARD_SEL,
                      current=state(hand=[DUPENERGY, DUPENERGY]))
    assert "discard-the-hand-duplicate" not in _fired(pilot.explain(obs).options[0])


# --- prefer-good-in-discard: a deck redirects the pitch to its discard-synergy fodder ------------
@pytest.mark.req("REQ-GEN-0039")
def test_prefer_good_in_discard_pitches_the_decks_fodder_card():
    """The deck-override term: a recursion / discard-fed deck flags a card `discard_fodder` (good to
    have in the bin); at a forced discard, prefer pitching it over a generic card."""
    stats = DictCardStatProvider({FODDER: CardStat(FODDER, hp=90), KEEPCARD: CardStat(KEEPCARD, hp=90)})
    strat = Strategy(roles={FODDER: ["discard_fodder"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=DISCARD_SEL,
                      current=state(hand=[FODDER, KEEPCARD]))
    assert pilot.decide(obs) == [0]                                   # pitch the deck's discard-synergy card
    assert "prefer-good-in-discard" in _fired(pilot.explain(obs).options[0])
    assert "prefer-good-in-discard" not in _fired(pilot.explain(obs).options[1])


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
    assert sorted(pilot.decide(obs)) == [0, 2]                        # one wincon + the Basic, not [0, 1]


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
    assert pilot.decide(obs) == [0]                                   # only the Basic; no dead second grab


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
    # TO_BENCH, up to 2, minCount 0: two Basics + a non-Basic Stage-1 revealed from the deck.
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1), card_opt(DECK, 2)],
                      min_count=0, max_count=2, context=TO_BENCH,
                      deck=[{"id": BASIC}, {"id": BASIC}, {"id": STAGE1}],
                      current=state(active=poke(900, energy=1), bench=[]))
    assert sorted(pilot.decide(obs)) == [0, 1]                        # bench both Basics, not [] (no whiff)
    assert "bench-fill-a-basic" in _fired(pilot.explain(obs).options[0])
    assert "bench-fill-a-basic" not in _fired(pilot.explain(obs).options[2])  # the Stage-1 isn't a starter


# --- whether-to-play (slice 7): a cost_discard fetch is endorsed when it can grab a needed card ---
@pytest.mark.req("REQ-GEN-0041")
def test_fetch_is_endorsed_when_it_can_grab_a_needed_card():
    """An Ultra Ball-type cost_discard fetch gets NO endorsement from dig-before-commit (which excludes
    cost_discard). The whether-to-play lookahead endorses it when its reachable deck set contains a card
    I currently lack (here the unfound win-condition) — so it's played over End."""
    stats = DictCardStatProvider({ULTRA: CardStat(ULTRA, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  BASIC: CardStat(BASIC, hp=70)})
    funcs = CardFunctions({ULTRA: ["search", "tutor_pokemon", "cost_discard"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[WINC, BASIC, BASIC], general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
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
    funcs = CardFunctions({ULTRA: ["search", "tutor_pokemon", "cost_discard"]})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[WINC], general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
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

    # no Raboot in the deck list -> the opener can never be deployed from hand -> penalised.
    stranded = Pilot(Strategy(), deck=[OPENER] * 4 + [1] * 56,
                     general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    assert "dont-fetch-the-setup-only-opener" in _fired(stranded.explain(obs).options[0])
    assert "dont-fetch-the-setup-only-opener" not in _fired(stranded.explain(obs).options[1])
    assert stranded.decide(obs) == [1]                    # take the line piece, never the opener

    # Raboot (a Basic here) in the deck -> the opener is evolvable from hand -> no penalty.
    fed = Pilot(Strategy(), deck=[OPENER] * 4 + [RABOOT] * 4 + [1] * 52,
                general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    assert "dont-fetch-the-setup-only-opener" not in _fired(fed.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0061")
def test_stranded_chain_check_walks_the_full_previous_stage_chain():
    """Chain reachability is FULL-depth: Stage 1 present but ITS Basic missing -> still stranded."""
    OPENER, RABOOT = 666, 667
    stats = DictCardStatProvider({
        OPENER: CardStat(OPENER, name="Cinderace", hp=160, evolvesFrom="Raboot"),
        RABOOT: CardStat(RABOOT, name="Raboot", hp=90, evolvesFrom="Scorbunny"),  # its own base missing
        BASIC: CardStat(BASIC, hp=70)})
    funcs = CardFunctions({OPENER: ["opener"]})
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": OPENER}, {"id": BASIC}], current=state(hand=[]))
    pilot = Pilot(Strategy(), deck=[OPENER] * 4 + [RABOOT] * 4 + [1] * 52,
                  general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    assert "dont-fetch-the-setup-only-opener" in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0061")
def test_fetch_the_support_never_endorses_a_stranded_support():
    """An engine-tagged Pokémon that is a stranded evolution (energy_accel Cinderace, no Raboot in
    deck) is a dead grab — `fetch-the-support` must not endorse it even with no support in play."""
    OPENER, LIVEMON = 666, 868
    stats = DictCardStatProvider({
        OPENER: CardStat(OPENER, name="Cinderace", hp=160, evolvesFrom="Raboot"),
        LIVEMON: CardStat(LIVEMON, name="Livemon", hp=90)})          # a Basic support
    funcs = CardFunctions({OPENER: ["opener", "energy_accel"], LIVEMON: ["energy_accel"]})
    pilot = Pilot(Strategy(), deck=[OPENER] * 4 + [LIVEMON] * 2 + [1] * 54,
                  general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": OPENER}, {"id": LIVEMON}], current=state(hand=[]))
    stranded, live = pilot.explain(obs).options
    assert "fetch-the-support" not in _fired(stranded)   # dead grab, engine tag notwithstanding
    assert "fetch-the-support" in _fired(live)           # a deployable support keeps the rung
