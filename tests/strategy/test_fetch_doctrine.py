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


def _ranked(pilot, obs):
    """The doctrine's own ranking of the menu, best-first, as ``[(index, score), ...]``.

    **Why this and not `decide`.** POC-T4/5 (Issue #386) moved the single-pick MAIN decision to the
    sequence composer: the fetch doctrine still SCORES every option, but it no longer picks. A
    `decide(obs) == [0]` line in this file therefore stopped testing the doctrine and started testing
    the composer, on a hand-built board no human ever ruled. The doctrine's ranking is the fact this
    file owns, and it is unchanged — see `test_the_doctrine_still_RANKS_but_no_longer_DECIDES`.
    """
    return [(o.index, o.score) for o in sorted(pilot.explain(obs).options, key=lambda o: -o.score)]


# The fetch doctrine's whiff/redundancy/confirmed-hit signals read a search's FETCH CLAUSES from
# `card_effects.json` (ADR-0032), the tier that REPLACED the tag-keyed `_FETCH_FILTERS`. These synthetic
# fetchers carry TAGS only, so mirror the standard fetcher tags to their clauses (`fetch_effects`).
from pilot_helpers import fetch_effects as _fetch_effects   # noqa: E402


# --- fetch-a-starter: an underdeveloped board wants a Basic body to develop ----------------------
@pytest.mark.req("REQ-GEN-0035")
def test_fetch_a_starter_prefers_a_basic_when_the_board_is_thin():
    """At a search, with a thin bench in SETUP and no higher need, grab a startable Basic over a
    non-startable Stage-1 — develop the board."""
    stats = DictCardStatProvider({BASIC: CardStat(BASIC, synthetic=True, hp=70),
                                  STAGE1: CardStat(STAGE1, synthetic=True, hp=90, evolvesFrom="Basicmon")})
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
    stats = DictCardStatProvider({SUPPORT: CardStat(SUPPORT, synthetic=True, hp=90),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, hp=90)})
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
    stats = DictCardStatProvider({COMBO: CardStat(COMBO, synthetic=True, hp=90, evolvesFrom="X"),
                                  FILLER: CardStat(FILLER, synthetic=True, hp=90, evolvesFrom="Y")})
    strat = Strategy(fetch_priority=[COMBO, FILLER])
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": FILLER}, {"id": COMBO}],
                      current=state(active=poke(900, energy=1), bench=[poke(701), poke(702)]))
    assert pilot.decide(obs) == [1]                                   # COMBO — deck-list top
    assert "fetch-deck-priority" in _fired(pilot.explain(obs).options[1])
    assert "fetch-deck-priority" not in _fired(pilot.explain(obs).options[0])


# --- discard-the-redundant: at a forced discard, shed a need-already-met card (keep-value floor) --
@pytest.mark.req("REQ-GEN-0038")
def test_discard_the_redundant_sheds_a_duplicate_already_in_play():
    """The discard side of the comparator: among cards you must pitch, shed the one whose need is
    already satisfied — here a duplicate of a Pokémon already in play — over one you still lack.

    Graded on the DECISION since Issue #261 item 2h deleted the `_DISCARD` ladder: the keep-value v2
    needs-assignment reproduces this pick without the rung, which is the evidence that the rung was
    redundant rather than load-bearing."""
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
    """At a search revealing BOTH the evolved payoff and its own pre-evolution, with NO base for the
    payoff in play OR hand, grab the deployable base — fetching a payoff you have nothing to evolve
    from just strands it (and a bench-accelerator like Cinderace gets no recipient). `fetch-the-wincon`
    otherwise pulls the un-evolvable payoff (the verified mega_starmie trap)."""
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
def test_fetch_takes_the_payoff_once_a_base_is_in_hand():
    """The inverse guard: with a base already in HAND the payoff IS deployable, so prefer the payoff
    (`fetch-the-wincon`) — `fetch-base-before-stranded-payoff` stands down (don't over-correct)."""
    stats = DictCardStatProvider({BASEP: CardStat(BASEP, hp=70),
                                  PAYP: CardStat(PAYP, synthetic=True, megaEx=True, hp=330, evolvesFrom="Basep")})
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
    """The hand-internal mirror of `discard-the-redundant`: among cards you must pitch, shed one you
    hold 2+ copies of in hand (keep one) before a SINGLETON — so a lone disruptor (which the flat
    keep-floors miss, scoring 0) is never discarded over a duplicate engine card."""
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
@pytest.mark.req("REQ-GEN-0040")
def test_multi_pick_grab_dedups_a_satisfied_need():
    """A TO_HAND grab of up to 2 (one select, maxCount=2): revealing two win-condition copies plus a
    Basic, grab ONE wincon (its need is met after the first pick) and then the Basic — not two dead
    wincon copies, which static top-N would take."""
    stats = DictCardStatProvider({WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  BASIC: CardStat(BASIC, synthetic=True, hp=70)})
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
    stats = DictCardStatProvider({BASIC: CardStat(BASIC, synthetic=True, hp=70),
                                  STAGE1: CardStat(STAGE1, synthetic=True, hp=90, evolvesFrom="Basicmon")})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1), card_opt(DECK, 2)],
                      min_count=0, max_count=2, context=TO_HAND,
                      deck=[{"id": BASIC}, {"id": STAGE1}, {"id": STAGE1}],
                      current=state(active=poke(900, energy=1), bench=[]))
    assert pilot.decide(obs) == [0]                                   # only Basic; no dead 2nd grab


# --- bench-fill grab (TO_BENCH): a min0 bench placement must bench the Basics, not whiff to [] -------
@pytest.mark.req("REQ-GEN-0035")
def test_bench_fill_grab_benches_basics_at_to_bench():
    """A Buddy-Poffin-style bench placement (`_TO_BENCH`, up to 2, minCount 0) must not whiff to `[]`.

    The rung that used to carry this — `bench-fill-a-basic` (+12) — is DELETED (Issue #261 item 2d):
    the Deploy Marginal prices this entry point now, so a flat weight that tied every candidate is
    exactly the indifference Issue #197 was opened to remove. What keeps the whiff away is the
    take-fewer bar, which at a BENCH grab declines only a candidate priced BELOW zero — ADR-0086
    decision 6's own wording, and correct because the marginal prices the whole cost (the slot it
    displaces, the Prize-Path exposure it hands over) while the search that revealed the body is
    already spent.

    Asserted with the decider at its class DEFAULT (off), which is the degraded path: nothing scores
    these options at all, and the bar alone must still place bodies rather than waste the search."""
    stats = DictCardStatProvider({BASIC: CardStat(BASIC, synthetic=True, hp=70),
                                  STAGE1: CardStat(STAGE1, synthetic=True, hp=90, evolvesFrom="Basicmon")})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # TO_BENCH, up to 2, minCount 0: two Basics + a non-Basic Stage-1 revealed from deck.
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1), card_opt(DECK, 2)],
                      min_count=0, max_count=2, context=TO_BENCH,
                      deck=[{"id": BASIC}, {"id": BASIC}, {"id": STAGE1}],
                      current=state(active=poke(900, energy=1), bench=[]))
    assert sorted(pilot.decide(obs)) == [0, 1]                        # bench both Basics, not [] (no whiff)
    assert not any("bench-fill-a-basic" in _fired(o) for o in pilot.explain(obs).options)


@pytest.mark.req("REQ-DEPLOY-0001")
def test_the_deploy_marginal_prices_the_to_bench_entry_point():
    """The third entry point ADR-0086 decision 6 claims is LIVE (Issue #261 item 2d).

    It abstained silently until now: `_deploy_decision` resolved the candidate against hand rows, and
    a `_TO_BENCH` candidate is a DECK card, so the lookup returned `None` for every option. The
    measured cost was that all four options on the corpus's only such frame scored identically and
    the pick fell to menu position.

    Here the win-condition's Line base is on offer beside a body that covers nothing. Only the base
    fills a live slot, so only it carries a marginal — and the working row is attached to the trace,
    which is what makes the decision rulable at the Decision Gate."""
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
def test_the_to_bench_multi_pick_stops_when_the_bench_runs_out():
    """The greedy's virtual board shrinks CAPACITY, and the marginal must answer to it.

    Decision 6 resolves a multi-pick by re-deriving against the board after each take, so the second
    pick is priced on a Bench one slot smaller. With the last slot spent, `needs.deploy_marginal`
    returns 0 — there is no counterfactual for a body that cannot be placed — and a take-fewer bar
    that declined only below zero would otherwise keep grabbing. Here the Bench holds four, one slot
    is free, and two bodies are offered: exactly one is taken."""
    stats = DictCardStatProvider({BASIC: CardStat(BASIC, synthetic=True, name="Basicmon", hp=70),
                                  WINC: CardStat(WINC, synthetic=True, megaEx=True, hp=330, evolvesFrom="Basicmon"),
                                  PLAINMON: CardStat(PLAINMON, synthetic=True, name="Plainmon", hp=60)})
    strat = Strategy(roles={WINC: ["win_condition", "primary_attacker"]},
                     lines=[Line(path=[BASIC, WINC], payoff=WINC, role="win_condition")])
    pilot = Pilot(strat, deck=[BASIC, WINC, PLAINMON] + [PLAINMON] * 57,
                  general_strategy=GENERAL_STRATEGY, stats=stats)
    pilot.deploy_value = True
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)],
                      min_count=0, max_count=2, context=TO_BENCH,
                      deck=[{"id": BASIC}, {"id": PLAINMON}],
                      current=state(active=poke(900, energy=1), bench=[poke(900)] * 4))
    assert pilot.decide(obs) == [0]                                   # the Line base fills the last slot


# --- whether-to-play (slice 7): a cost_discard fetch is endorsed when it can grab a needed card ---
@pytest.mark.req("REQ-GEN-0041")
def test_fetch_is_endorsed_when_it_can_grab_a_needed_card():
    """An Ultra Ball-type cost_discard fetch gets NO endorsement from dig-before-commit (which excludes
    cost_discard). The whether-to-play lookahead endorses it when its reachable deck set contains a card
    I currently lack (here the unfound win-condition) — so it's played over End."""
    stats = DictCardStatProvider({ULTRA: CardStat(ULTRA, hp=0),
                                  WINC: CardStat(WINC, megaEx=True, hp=330, evolvesFrom="Staryu"),
                                  BASIC: CardStat(BASIC, synthetic=True, hp=70)})
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
    assert _ranked(pilot, obs)[0][0] == 0                            # so the fetch leads, not End


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
        RABOOT: CardStat(RABOOT, synthetic=True, name="Raboot", hp=90),                  # a Basic in these stats
        BASIC: CardStat(BASIC, synthetic=True, hp=70)})
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
    OPENER, RABOOT, SCORBUNNY = 666, 667, 668
    stats = DictCardStatProvider({
        OPENER: CardStat(OPENER, name="Cinderace", hp=160, evolvesFrom="Raboot"),
        RABOOT: CardStat(RABOOT, synthetic=True, name="Raboot", hp=90, evolvesFrom="Scorbunny"),
        SCORBUNNY: CardStat(SCORBUNNY, synthetic=True, name="Scorbunny", hp=60),   # POOL only — OFF the deck list,
        #   which is what strands the chain. Printing it keeps the test on its own subject: a pool
        #   with no Scorbunny at all is UNREADABLE data, which ADR-0104 fails open on by design.
        BASIC: CardStat(BASIC, synthetic=True, hp=70)})
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
    assert _ranked(pilot, obs)[0][0] == 0              # the certain hit leads over End

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
    assert _ranked(pilot, obs)[0][0] == 0              # the provable hit leads the turn's digs


@pytest.mark.req("REQ-GEN-0061")
def test_fetch_the_support_never_endorses_a_stranded_support():
    """An engine-tagged Pokémon that is a stranded evolution (energy_accel Cinderace, no Raboot in
    deck) is a dead grab — `fetch-the-support` must not endorse it even with no support in play."""
    OPENER, LIVEMON, PLAINMON = 666, 868, 869
    stats = DictCardStatProvider({
        OPENER: CardStat(OPENER, name="Cinderace", hp=160, evolvesFrom="Raboot"),
        667: CardStat(667, synthetic=True, name="Raboot", hp=90),                    # POOL only — never on the list
        LIVEMON: CardStat(LIVEMON, synthetic=True, name="Livemon", hp=90),           # a Basic support
        PLAINMON: CardStat(PLAINMON, synthetic=True, name="Plainmon", hp=80)})       # non-engine Active
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


@pytest.mark.req("REQ-GEN-0065")
def test_costly_fetch_sheds_junk_boosts_ultra_ball_to_the_free_dig_band():
    """Two provably-junk sheds (hand copies of a benched Pokémon) + a needed grab in deck lift the
    cost_discard fetch into the free-dig band: `costly-fetch-sheds-junk` rides on
    `fetch-when-it-fills-a-need` and the fetch is played."""
    pilot = _netting_pilot(deck=[WINC, JUNKMON])
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(900, energy=1),
                                    bench=[poke(JUNKMON), poke(702)],
                                    hand=[ULTRA, JUNKMON, JUNKMON]))
    fired = _fired(pilot.explain(obs).options[0])
    assert "costly-fetch-sheds-junk" in fired
    assert "fetch-when-it-fills-a-need" in fired
    assert pilot.explain(obs).options[0].score >= 20               # free-dig band
    assert _ranked(pilot, obs)[0][0] == 0


BURST, NEUT_SINGLE, POWERED_ATK = 17, 662, 900


@pytest.mark.req("REQ-GEN-0065")
def test_the_shed_predictor_ranks_by_DEADNESS_like_the_decider_it_predicts():
    """The predictor and the discard DECIDER share one ranking (ADR-0106, `Pilot.
    _removal_ranking_legs`), and this is the shape where that bites — three shed candidates, all
    priced 0 by the assignment, so nothing but the ranking legs can separate them:

      * a SPENT burst — `discard_eot` with the Active already fully powered, so it self-discards at
        end of turn anyway (`83454549-36`). Dead, and carrying catalog worth 30;
      * a hand copy of a BENCHED Pokémon — replaceable, worth 0;
      * a NEUTRAL singleton — worth 0, and a genuine card we would still have.

    Residual worth alone gets it backwards: worth-first preserves the corpse (30) and sheds
    `{duplicate, singleton}`, which is not a junk shed, so `costly-fetch-sheds-junk` goes silent and
    the dig loses its free-dig band. Deadness ranks above residual worth, so the predictor sheds
    `{burst, duplicate}` — every card dead or replaceable — and the band fires.

    The junk band is what makes the miss OBSERVABLE: without a test at this seam the predictor could
    drift off the decider silently, which is the drift ADR-0103 Amendment A re-pointed it to close."""
    pilot = _netting_pilot(
        deck=[WINC, JUNKMON], extra_funcs={BURST: ["discard_eot"]},
        extra_stats={BURST: CardStat(BURST, name="Ignition Energy", cardType=6, energyType=0),
                     NEUT_SINGLE: CardStat(NEUT_SINGLE, synthetic=True, hp=60),
                     POWERED_ATK: CardStat(POWERED_ATK, synthetic=True, hp=200, maxDamageCost=1)})
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(POWERED_ATK, energy=1),
                                    bench=[poke(JUNKMON), poke(STARYU)],
                                    hand=[ULTRA, BURST, JUNKMON, NEUT_SINGLE]))
    board = pilot._board(obs, obs["select"])
    rows = pilot._as_discard_rows(pilot._needs_hand_rows(obs, board, exclude_cid=ULTRA), obs, board)
    burst = next(r for r in rows if r["cid"] == BURST)
    assert burst["spent_burst"] is True and burst["deadness"] == 1 and burst["worth"] == 30.0
    junk, live, key = pilot._shed_signals(obs, obs["select"]["option"][0],
                                          list(pilot.functions.tags(ULTRA)), board, None)
    assert (junk, live, key) == (True, False, False)
    assert "costly-fetch-sheds-junk" in _fired(pilot.explain(obs).options[0])
    assert _ranked(pilot, obs)[0][0] == 0


ENGINE_SUP = 661        # a draw Supporter — live at a forced discard (keep-engine floor)


@pytest.mark.req("REQ-GEN-0065")
def test_dont_shed_a_live_card_suppresses_the_fetch_below_end():
    """When a LIVE card (a draw Supporter, negative keep-value at the discard) is forced into the
    predicted top-2 sheds, `dont-shed-a-live-card` nets the fetch below End — the ep83007714-f8
    'tossing the supporters is a poor trade' shape."""
    pilot = _netting_pilot(deck=[WINC, JUNKMON], extra_funcs={ENGINE_SUP: ["draw"]},
                           extra_stats={ENGINE_SUP: CardStat(ENGINE_SUP, synthetic=True, hp=0, cardType=SUPPORTER_CT)})
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
    """A KEY card (the win-condition) forced into the predicted sheds fires `dont-shed-a-key-card`
    ON TOP of the live suppressor (−45 total): never pitch the wincon to dig — no normal-band
    endorsement stack can lift it back.

    The Staryu on the bench is load-bearing since the predictor moved onto the v2 keep-value
    equation (Issue #261 item 2h): WITHOUT a base in play the Mega is STRANDED — it can never be
    put into play this game — so v2 prices it keep 0 with a positive pitch term and correctly
    declines to call it key. The retired ladder's flat `keep-key-cards-at-discard` −30 could not
    see that, and this fixture was relying on the blindness."""
    pilot = _netting_pilot(deck=[WINC, JUNKMON])
    # only two shed candidates: one junk, one the WIN-CONDITION (the keep floor fires on it).
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(900, energy=1),
                                    bench=[poke(JUNKMON), poke(STARYU)],
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
                           extra_stats={NEUT1: CardStat(NEUT1, synthetic=True, hp=60), NEUT2: CardStat(NEUT2, synthetic=True, hp=60)})
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(900, energy=1), bench=[poke(701), poke(702)],
                                    hand=[ULTRA, NEUT1, NEUT2]))
    trace = pilot.explain(obs).options[0]
    fired = _fired(trace)
    assert {"costly-fetch-sheds-junk", "dont-shed-a-live-card", "dont-shed-a-key-card"} & fired == set()
    assert "fetch-when-it-fills-a-need" in fired
    assert _ranked(pilot, obs)[0][0] == 0                          # +8 still leads End


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


# ── the DIG class: a fetcher whose target class is exhausted (ADR-0073, issue #164) ───────────────
GEAR = 2002            # a Pokégear-3.0-shaped Supporter fetcher: `target: supporter`, `dig: 7`
SUPP = 2003            # the Supporter it digs for


def _dig_pilot(deck):
    """A Pilot holding a DIG-class Supporter fetcher — the shape that was invisible to the whiff
    question before ADR-0073 (`fetch_target_matches` rejects a ``dig`` clause for REACH, and the
    doctrine's reach set is Pokémon-only, so `_search_deck_set` was empty and the search could never
    be read as dead however empty the deck was of Supporters)."""
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
    """END TO END: a dig-7 Supporter fetcher over a deck PROVABLY empty of Supporters is dead, and
    `dont-search-an-empty-deck` fires on it. The dig cannot find what is not there — deadness is
    sound on a clause reach must reject. This is the #164 hole made behavioural: before ADR-0073 the
    veto could not fire on this shape at all."""
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
    """The endorser stays on the REACH set: a dig-7 can only PROBABLY reach a Supporter, so it must
    never claim `fetch-when-it-fills-a-need`, even with the class provably in deck. This is why the
    two sets are distinct rather than one widened set (ADR-0073)."""
    pilot = _dig_pilot([SUPP] * 2 + [GEAR] * 2 + [FILLER] * 56)
    play_gear = opt(PLAY, area=HAND, index=0)
    cur = state(active=poke(FILLER, energy=1), hand=[GEAR], prizes=6, deck_count=20)
    obs = make_select([play_gear, opt(END)], current=cur)
    obs["own_prizes"] = {FILLER: 6}
    assert "fetch-when-it-fills-a-need" not in _fired(pilot.explain(obs).options[0])


# ── the cost oracle's coordinates ─────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-GEN-0065")
def test_cost_shed_indices_are_HAND_positions_not_row_ordinals():
    """**The two coordinate systems are not interchangeable, and conflating them is a live defect.**

    `_needs_hand_rows` drops one copy of the played card BEFORE it enumerates, so each row's ``i`` —
    the ordinal `_resolve_needs` eligibility and `needs.cheapest_removal`'s picks are aligned to — is
    one short of that card's real hand position for every card sitting AFTER the excluded one.

    `Pilot.cost_shed_indices` is consumed by `board_expectation._paid`, which pops the indices it
    returns out of the REAL hand. Reading ``i`` there made the picks collide with the played card's
    own index, and `_paid` — which drops the played index by design (the engine's `handOthers` gate)
    — then reported the payment short and refused a legal Ultra Ball as *"not legal on this board"*.

    The board here puts the played card in the MIDDLE of the hand, which is the only arrangement
    that separates the two numbers: with it last, every row ordinal happens to equal its hand
    position and the bug is invisible. That is why nothing caught this."""
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
    # Every index names a card that is really there, and never the Ultra Ball itself.
    assert [hand[i]["id"] for i in taken] == [JUNKMON, JUNKMON]
    # The row ordinals it came from are DIFFERENT numbers — the assertion that makes this a
    # measurement rather than a coincidence of this particular hand.
    plan = pilot._cost_shed(obs, exclude_cid=ULTRA, picks=2)
    assert plan.row_indices != plan.hand_indices or 1 in plan.row_indices, (
        "fixture is vacuous unless the two coordinate systems actually diverge here")
    assert plan.hand_indices == taken


# --- the doctrine's ROLE after POC-T4/5 (Issue #386) ---------------------------------------------
@pytest.mark.req("REQ-PLANNER-0012")
def test_the_doctrine_still_RANKS_but_no_longer_DECIDES():
    """The fetch doctrine survived the swap intact. What it lost is the last word.

    Six tests in this file used to end `assert pilot.decide(obs) == [0]`. Every one of their
    mechanism assertions still passes — the rung fires, the band is right, the shed predictor picks
    the same cards — and only the DECISION moved, because a single-pick MAIN decision now comes from
    the sequence composer rather than from the rung total. So those six now assert `_ranked(...)`,
    which is the doctrine's own output and the thing this file is about.

    This test is what stops that re-pointing from being a quiet climbdown. It records the role in
    one place: on a board where the doctrine ranks the fetch top by a wide margin, the agent is
    free to play something else, and that is not a regression. If a future change puts the ladder
    back in charge at MAIN, the composer's disagreement disappears and this turns red — which is
    exactly when someone should be made to look at the six re-pointed assertions again."""
    pilot = _netting_pilot(deck=[WINC, JUNKMON])
    obs = make_select([opt(PLAY, index=0), opt(14)], context=MAIN,
                      current=state(active=poke(900, energy=1),
                                    bench=[poke(JUNKMON), poke(702)],
                                    hand=[ULTRA, JUNKMON, JUNKMON]))
    ranking = _ranked(pilot, obs)
    assert ranking[0][0] == 0 and ranking[0][1] >= 20, ranking   # the doctrine's verdict: play it
    assert pilot.decide(obs) != [0], (
        "the composer now agrees with the rung total here, so this test no longer demonstrates that "
        "the two are separate mechanisms — re-point it at a board where they still differ, or "
        "promote the six `_ranked` assertions in this file back to `decide`")
