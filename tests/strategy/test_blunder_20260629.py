"""Blunder round 2026-06-29 (mega_starmie) — the Hypotheses + signals authored by /blunder-buster.

Each test pins ONE new rule to the doctrine it encodes (ADR-0018). Lib-free: synthetic obs dicts
via pilot_helpers + DictCardStatProvider, so the fast suite needs no native engine.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Hypothesis, Line, Plan, Strategy
from pilot_helpers import (
    ACTIVE, BENCH, CARD, DAMAGE, HAND, PLAY, attack_opt, card_opt, fetch_effects, make_select, opt,
    poke, state)

ATTACH = 8
END = 14                # OptionType.END — end turn
DISCARD_SEL = 8         # SelectContext.DISCARD — cost-discard select (NB pilot_helpers.DISCARD is the AreaType)
WINCON = 900            # Mega-ex win-condition (evolves from pre-evo, like Mega Starmie)
PREEVO = 800            # its pre-evolution (Staryu-like)
WATER = 3               # reusable Basic Energy
IGNITION = 17           # discard-at-EOT burst energy (CCC on an Evolution)
CRUSH = 1120            # Crushing Hammer — energy-denial Item (Function Tag `energy_denial`)
OPP = 678               # energized opponent attacker (Mega Lucario ex shape)


def _fired(o):
    return {h.id for h, _ in o.fired}


def _stats(attacks=None):
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                         maxDamageCost=3, minAttackCost=1, minCostDamage=120, attacks=(10, 11),
                         evolvesFrom="Staryu", energyType=3),
        PREEVO: CardStat(PREEVO, name="Staryu", hp=70, maxDamage=20, maxDamageCost=1,
                         minAttackCost=1, attacks=(12,), evolvesFrom=None),
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
        IGNITION: CardStat(IGNITION, name="Ignition Energy", hp=0, energyType=0),
    }, attacks=attacks)


# Attack records (ADR-0051): the facts the legacy attacks=/attack_costs= Pilot dicts used to carry.
_ATTACK_STATS = {10: AttackStat(10, damage=210, cost=3),      # Nebula Beam
                 11: AttackStat(11, damage=120, cost=1),      # Jetting Blow
                 12: AttackStat(12, damage=20, cost=1)}       # Staryu chip


def _pilot(**kw):
    return Pilot(Strategy(roles={WINCON: ["win_condition", "primary_attacker"]}), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=_stats(attacks=_ATTACK_STATS),
                 functions=CardFunctions({IGNITION: ["discard_eot"], 1223: ["draw", "shuffle_hand"],
                                          1227: ["draw", "shuffle_hand"], 1189: ["search", "rush_evolve"]}),
                 effects=fetch_effects({1189: ["search", "rush_evolve"]}), **kw)


# ---------------------------------------------------------------- build-active-wincon
@pytest.mark.req("REQ-GEN-0025")
def test_build_active_wincon_keeps_loading_the_active_toward_its_big_attack():
    pilot = _pilot()
    # Active win-con at 1 Energy: online for cheap attack (minAttackCost 1) but short of
    # max-damage attack (maxDamageCost 3) -> keep building it.
    attach = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)
    obs = make_select([attach], current=state(active=poke(WINCON, energy=1, hp=330), hand=[WATER]))
    # `build-active-wincon` is DELETED (#139, ADR-0069): "keep loading toward the BIGGEST attack" is
    # what the convex typed build says by construction — the k-th Energy is worth more than the
    # (k-1)-th, so a body short of its payoff keeps earning. Assert that, not the rung.
    assert next(r for r in pilot.explain(obs).attach_working["eq"] if r["i"] == 0)["build"] > 0

    # Already at max-damage cost (3) -> fully online -> stands down (no needless over-stack).
    full = make_select([attach], current=state(active=poke(WINCON, energy=3, hp=330), hand=[WATER]))
    assert "build-active-wincon" not in _fired(pilot.explain(full).options[0])


@pytest.mark.req("REQ-GEN-0025")
def test_build_active_wincon_stands_down_for_a_discard_energy_when_the_cheap_attack_kos():
    """Carve-out (refactor audit 2026-06-29): don't burn a finite discard-EOT Energy (Ignition) to
    build toward the big attack when the Active win-condition's CHEAP attack already KOs the opponent —
    Nebula isn't needed this turn, so the build endorsement would only partially cancel the deck's
    `conserve-discard-energy-prefer-basic` penalty (the two used to co-fire with opposite signs on the SAME
    Ignition attach). Scoped to `discard_eot`: a reusable Water still builds toward the payoff."""
    pilot = _pilot()
    ign = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)   # attach Ignition (hand idx 1)
    # Active wincon at 1 W (short of Nebula CCC=3); cheap attack (120) KOs the 120-HP opp Active.
    obs = make_select([ign], current=state(active=poke(WINCON, energy=1, hp=330),
                                           opp_active=poke(OPP, hp=120), hand=[WATER, IGNITION]))
    assert "build-active-wincon" not in _fired(pilot.explain(obs).options[0])

    # Control A — reusable Water attach (no `discard_eot`) still builds toward payoff, even on KO.
    wat = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)   # attach Water (hand idx 0)
    obs_w = make_select([wat], current=state(active=poke(WINCON, energy=1, hp=330),
                                             opp_active=poke(OPP, hp=120), hand=[WATER, IGNITION]))
    assert next(r for r in pilot.explain(obs_w).attach_working["eq"] if r["i"] == 0)["build"] > 0

    # Control B — a LATER correction (83116501 f70, `conserve-burst-when-no-ko`) refined this: when
    # even the fully-powered big attack cannot KO either, the burst buys nothing worth its one-shot.
    # The decider states both facts at once — the no-KO cap holds tonight's credit to what the
    # reusable Basic would have bought, and a burst earns NO forward build (it is discarded at end of
    # turn) — so the Ignition scores BELOW doing nothing here.
    obs_n = make_select([ign], current=state(active=poke(WINCON, energy=1, hp=330),
                                             opp_active=poke(OPP, hp=300), hand=[WATER, IGNITION]))
    assert pilot.explain(obs_n).options[0].tactical < 0


@pytest.mark.req("REQ-GEN-0025")
def test_build_active_wincon_prefers_active_over_a_bench_copy():
    pilot = _pilot()
    # Active win-con (1 E) vs bench copy (0 E): build the ATTACKER, not the idle bench piece.
    to_active = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)
    to_bench = opt(ATTACH, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)
    obs = make_select([to_bench, to_active],
                      current=state(active=poke(WINCON, energy=1, hp=330),
                                    bench=[poke(WINCON, energy=0, hp=330)], hand=[WATER]))
    assert pilot.decide(obs) == [1]                       # active attach wins


# ---------------------------------------------------------------- attach-before-hand-shuffle
@pytest.mark.req("REQ-GEN-0026")
def test_attach_before_hand_shuffle_demotes_a_hand_shuffle_while_holding_energy():
    pilot = _pilot()
    play_shuffle = opt(PLAY, area=HAND, index=0)          # Harlequin (shuffle_hand) in hand[0]
    attach = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)   # a W in hand[1]
    obs = make_select([play_shuffle, attach],
                      current=state(active=poke(WINCON, energy=1, hp=330), hand=[1223, WATER]))
    assert "attach-before-hand-shuffle" in _fired(pilot.explain(obs).options[0])
    assert pilot.decide(obs) == [1]                       # attach first; shuffle sequenced last

    # No reusable Energy in hand -> nothing to attach first -> rule stands down.
    no_energy = make_select([play_shuffle],
                            current=state(active=poke(WINCON, energy=1, hp=330), hand=[1223]))
    assert "attach-before-hand-shuffle" not in _fired(pilot.explain(no_energy).options[0])


# ---------------------------------------------------------------- dont-rush-evolve-without-target
@pytest.mark.req("REQ-GEN-0027")
def test_dont_rush_evolve_without_a_preevolution_in_play():
    pilot = _pilot()
    play_salvatore = opt(PLAY, area=HAND, index=0)        # rush_evolve tutor in hand[0]
    # Active is the already-evolved win-con, no pre-evolution anywhere -> Salvatore whiffs.
    obs = make_select([play_salvatore], current=state(active=poke(WINCON, hp=330), hand=[1189]))
    assert "dont-rush-evolve-without-target" in _fired(pilot.explain(obs).options[0])

    # A pre-evolution IS in play (a Line path piece) -> Salvatore can evolve it -> stands down.
    pilot2 = Pilot(Strategy(roles={WINCON: ["win_condition"]},
                            lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)]),
                   deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                   functions=CardFunctions({1189: ["search", "rush_evolve"]}),
                   effects=fetch_effects({1189: ["search", "rush_evolve"]}))
    has_preevo = make_select([play_salvatore],
                             current=state(active=poke(WINCON, hp=330), bench=[poke(PREEVO, hp=70)], hand=[1189]))
    assert "dont-rush-evolve-without-target" not in _fired(pilot2.explain(has_preevo).options[0])


# ---------------------------------------------------------------- snipe-the-top-threat (unified rank)
# `test_snipe_the_top_threat_breaks_the_evolving_tie_on_the_strongest_line` was DELETED by ADR-0085's deletion pass:
# it asserted a snipe TARGET rung that no longer exists. The requirement survives and is
# carried by `test_a_pre_evo_carrying_a_wincon_outranks_one_carrying_nothing` and
# `test_the_forward_leg_stands_down_once_the_evolved_wincon_is_already_in_play`
# (test_snipe_relevance.py) — the forward leg plus its ADR-0044 discriminator.

# `test_top_threat_picks_the_energized_body_over_a_bigger_latent_line` was DELETED by ADR-0085's deletion pass:
# it asserted a snipe TARGET rung that no longer exists. The requirement survives and is
# carried by `test_imminence_subsumes_the_energized_tier_without_a_tier_constant` (test_snipe_relevance.py).

@pytest.mark.req("REQ-GEN-0029")
def test_keep_key_cards_at_discard_protects_the_burst_energy():
    pilot = _pilot()
    # Ultra Ball cost: discard 2 of {Ignition, redundant Supporter A, redundant Supporter B}.
    opts = [card_opt(HAND, 0), card_opt(HAND, 1), card_opt(HAND, 2)]
    obs = make_select(opts, min_count=2, max_count=2, context=DISCARD_SEL,
                      current=state(hand=[IGNITION, 1182, 1229]))
    assert "keep-key-cards-at-discard" in _fired(pilot.explain(obs).options[0])   # Ignition guarded
    assert 0 not in pilot.decide(obs)                    # Ignition NOT among the discards


# ---------------------------------------------------------------- lethal-attach lookahead
@pytest.mark.req("REQ-GEN-0030")
def test_attach_lethal_unlocks_a_ko_via_ignition_ccc():
    pilot = _pilot()
    # Active win-con at 1 W vs 200-HP Active: Jetting Blow (120) can't KO, but attaching Ignition
    # (CCC on an Evolution) unlocks Nebula Beam (210) -> lethal.
    attach_ign = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)   # Ignition hand[0]
    attach_w = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)     # Water hand[1]
    obs = make_select([attach_ign, attach_w],
                      current=state(active=poke(WINCON, energy=1, hp=330), hand=[IGNITION, WATER],
                                    opp_active=poke(678, hp=200)))
    traces = pilot.explain(obs).options
    assert traces[0].tactical >= KO_SCORE               # Ignition attach is lethal
    assert traces[1].tactical < KO_SCORE                # plain Water (->2 E) is not
    assert pilot.decide(obs) == [0]                      # take the lethal attach


@pytest.mark.req("REQ-GEN-0030")
def test_attach_lethal_stands_down_when_the_active_can_already_ko():
    pilot = _pilot()
    # Cheap attack already KOs (120 >= 100) -> no attach needed -> no lethal-attach credit.
    attach_ign = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)
    obs = make_select([attach_ign],
                      current=state(active=poke(WINCON, energy=1, hp=330), hand=[IGNITION],
                                    opp_active=poke(678, hp=100)))
    assert pilot.explain(obs).options[0].tactical < KO_SCORE


# ---------------------------------------------------------------- play-energy-denial
def _denial_pilot(**kw):
    """A Pilot that knows Crushing Hammer (Function Tag `energy_denial`) plus the win-con line — for
    the `play-energy-denial` doctrine: strip the opponent's Energy BEFORE the turn-ending attack."""
    stats = DictCardStatProvider({
        WINCON: CardStat(WINCON, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                         maxDamageCost=3, minAttackCost=1, minCostDamage=120, attacks=(10, 11),
                         evolvesFrom="Staryu", energyType=3),
        PREEVO: CardStat(PREEVO, name="Staryu", hp=70, maxDamage=20, maxDamageCost=1,
                         minAttackCost=1, minCostDamage=20, attacks=(12,)),
        CRUSH: CardStat(CRUSH, name="Crushing Hammer", hp=0),
        OPP: CardStat(OPP, name="Mega Lucario ex", hp=440, megaEx=True, maxDamage=270, energyType=7,
                      attacks=(13,)),                    # Aura Jab {F} 130 — an affordable threat at 1 Energy
    }, attacks={**_ATTACK_STATS, 13: AttackStat(13, damage=130, cost=1)})   # + Aura Jab
    return Pilot(Strategy(roles={WINCON: ["win_condition", "primary_attacker"]},
                          lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)]),
                 deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({CRUSH: ["energy_denial"]}), **kw)


@pytest.mark.req("REQ-GEN-0031")
def test_play_energy_denial_sequences_the_strip_before_a_higher_value_attack():
    """RACE: the Active win-con can attack for 120 (tactical 119.9), but a Crushing Hammer strip is
    free — `_finish_turn_last` sequences the Item (tier 0) ahead of the turn-ending attack (tier 4),
    so the agent disrupts AND still attacks the same turn (the ep82525101 fr92/fr102 shape).

    Opponent Energy dropped 2 -> 1 (ADR-0062). Their only attack is Aura Jab at cost {F}: on 2 Energy
    the second one is SURPLUS, so discarding it leaves them still able to Aura Jab for 130 and the
    Hammer denies NOTHING. The old gate played it anyway — it asked only whether Energy was present,
    which is the whole reason Hammers were being burned for zero effect. At 1 Energy the strip turns
    the attacker off (130 -> 0) and the rung fires on merit. The SEQUENCING claim under test is
    unchanged; only the board now describes a strip worth making."""
    pilot = _denial_pilot()
    play_crush = opt(PLAY, area=HAND, index=0)            # Crushing Hammer in hand[0]
    attack = attack_opt(11)                               # Jetting Blow, 120
    obs = make_select([play_crush, attack, opt(END)],
                      current=state(active=poke(WINCON, energy=3, hp=330),
                                    opp_active=poke(OPP, energy=1, hp=440), hand=[CRUSH]))
    traces = pilot.explain(obs)
    assert traces.options[0].score > 0        # ADR-0062: priced tactical, not the retired flat rung
    assert traces.options[1].tactical > traces.options[0].score   # attack scores higher on tactical
    assert pilot.decide(obs) == [0]                       # yet strip taken first (attack-last)
    assert traces.options[1].deferred                     # attack held one slot, not dropped


@pytest.mark.req("REQ-GEN-0031")
def test_play_energy_denial_fires_in_setup_against_a_developing_attacker():
    """SETUP (payoff not yet in play): strip the opponent's developing Active before chipping — the
    ep82523811 fr15 shape (deny a Riolu its Energy before it can become a Mega Lucario ex)."""
    pilot = _denial_pilot()
    play_crush = opt(PLAY, area=HAND, index=0)
    chip = attack_opt(12)                                 # Staryu's 20 chip
    obs = make_select([play_crush, chip, opt(END)],
                      current=state(active=poke(PREEVO, energy=1, hp=70),
                                    opp_active=poke(OPP, energy=1, hp=440), hand=[CRUSH]))
    traces = pilot.explain(obs)
    assert traces.options[0].plan == Plan.SETUP           # payoff not in play -> still SETUP
    assert traces.options[0].score > 0        # ADR-0062: priced tactical, not the retired flat rung
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-GEN-0031")
def test_play_energy_denial_stands_down_when_the_opponent_has_no_energy():
    """No Energy in play -> the coin-flip strip whiffs -> hold the Item and just attack."""
    pilot = _denial_pilot()
    play_crush = opt(PLAY, area=HAND, index=0)
    attack = attack_opt(11)
    obs = make_select([play_crush, attack, opt(END)],
                      current=state(active=poke(WINCON, energy=3, hp=330),
                                    opp_active=poke(OPP, energy=0, hp=440), hand=[CRUSH]))
    assert "play-energy-denial" not in _fired(pilot.explain(obs).options[0])
    assert pilot.decide(obs) == [1]                       # nothing to strip -> attack wins


@pytest.mark.req("REQ-GEN-0031")
def test_energy_denial_stands_down_when_you_can_already_ko_the_active():
    """Don't burn the energy-denial Item on a body you're about to KO — stripping the Energy off an
    Active your cheapest attack already Knocks Out is worthless, so HOLD the Item and just take the KO
    (ep82748422 f26: Crushing Hammer is wasted when Jetting Blow will KO the Active anyway)."""
    pilot = _denial_pilot()
    play_crush = opt(PLAY, area=HAND, index=0)
    lethal = attack_opt(11)                               # 120 vs 100-HP Active -> KO (active_cheap_attack_kos)
    obs = make_select([play_crush, lethal, opt(END)],
                      current=state(active=poke(WINCON, energy=3, hp=330),
                                    opp_active=poke(OPP, energy=2, hp=100), hand=[CRUSH]))
    traces = pilot.explain(obs)
    assert traces.options[1].tactical >= KO_SCORE         # attack is genuinely lethal
    assert "play-energy-denial" not in _fired(traces.options[0])  # strip is moot -> hold Item
    assert pilot.decide(obs) == [1]                       # take the KO, save the Crushing Hammer


@pytest.mark.req("REQ-GEN-0031")
def test_energy_denial_stands_down_on_a_best_affordable_ko_not_just_the_cheapest():
    """fix (a), 2026-07-09: the KO stand-down keys on `active_can_ko` (BEST affordable attack), not only
    `active_cheap_attack_kos` (cheapest). Opp at 150 HP, carrying Energy AND a live threat (so the Item
    isn't held for the harmless-attacker reason): my cheapest Jetting Blow (120) does NOT KO, but my
    affordable Nebula Beam (210, cost 3) does — so the strip is moot and the Item is held. Under the old
    cheapest-only gate this wrongly fired (the dragapult Phantom-Dive / Mega Starmie Nebula-Beam shape)."""
    pilot = _denial_pilot()
    obs = make_select([opt(PLAY, area=HAND, index=0), attack_opt(10), attack_opt(11), opt(END)],
                      current=state(active=poke(WINCON, energy=3, hp=330),
                                    opp_active=poke(OPP, energy=1, hp=150), hand=[CRUSH]))
    board = pilot._board(obs, obs["select"])
    assert board.opp_active_can_damage_us                 # opp CAN hurt us -> not the harmless-strip case
    assert not board.active_cheap_attack_kos              # cheapest (120) misses the 150-HP body
    assert board.active_can_ko                            # best affordable (210) reaches it
    assert "play-energy-denial" not in _fired(pilot.explain(obs).options[0])   # so hold the Item (fix a)


# --------------------- deck-knowledge (sound): dont-search-an-empty-deck + dont-tutor-the-held-wincon
POFFIN = 1086           # Buddy-Buddy Poffin — bench-fill (fetches Basic Pokémon onto Bench)
MEGA_SIGNAL = 1145      # Mega Signal — tutor_mega (fetches ONLY a Mega Evolution ex = wincon)
ULTRA_BALL = 1121       # Ultra Ball — tutor_pokemon (fetches ANY Pokémon)
FILLER = 99             # non-Pokémon deck filler (absent from stats -> not a Pokémon)
_FNS = {POFFIN: ["search", "bench_fill"], MEGA_SIGNAL: ["search", "tutor_mega"],
        ULTRA_BALL: ["search", "tutor_pokemon", "cost_discard"], IGNITION: ["discard_eot"]}


def _search_pilot(deck):
    """A Pilot over `deck` knowing the deck's searches' fetch-filters (PREEVO is the only Basic;
    WINCON the only Mega ex)."""
    return Pilot(Strategy(roles={WINCON: ["win_condition", "primary_attacker"]}), deck=deck,
                 general_strategy=GENERAL_STRATEGY, stats=_stats(attacks=_ATTACK_STATS),
                 functions=CardFunctions(_FNS), effects=fetch_effects(_FNS))


def _board_of(pilot, current):
    return pilot._board(make_select([opt(END)], current=current))


def _ctx(pilot, obs, i):
    """The per-option Context the Pilot scores — to inspect the deck-knowledge search signals."""
    select = obs["select"]
    return pilot._context(obs, select, pilot._board(obs, select), select["option"][i])


@pytest.mark.req("REQ-GEN-0032")
def test_deck_definitely_empty_of_is_sound_only_when_all_copies_are_accounted():
    # Deck runs 3 PREEVO (the only Basic); rest are non-Basic filler.
    pilot = _search_pilot([PREEVO] * 3 + [FILLER] * 57)

    # All 3 PREEVO seen OUTSIDE the deck (1 Active + 2 discard); 6 prizes hidden but can't
    # hold a 4th copy that doesn't exist -> deck PROVABLY empty of PREEVO.
    all_seen = state(active=poke(PREEVO, hp=70), discard=[PREEVO, PREEVO], prizes=6)
    assert _board_of(pilot, all_seen).deck_definitely_empty_of(PREEVO)

    # Only 2 of 3 seen; 3rd could be in the 6 hidden prizes -> NOT certain (the refuted read).
    one_missing = state(active=poke(PREEVO, hp=70), discard=[PREEVO], prizes=6)
    assert not _board_of(pilot, one_missing).deck_definitely_empty_of(PREEVO)


@pytest.mark.req("REQ-GEN-0032")
def test_deck_empty_counts_revealed_prizes_and_evolution_stacks():
    pilot = _search_pilot([PREEVO] * 3 + [FILLER] * 57)

    # A FACE-UP prize is out of the deck: 1 Active + 1 discard + 1 revealed prize = 3 -> empty.
    revealed = state(active=poke(PREEVO, hp=70), discard=[PREEVO], prizes=6)
    revealed["players"][0]["prize"][0] = {"id": PREEVO, "playerIndex": 0, "serial": 1}
    assert _board_of(pilot, revealed).deck_definitely_empty_of(PREEVO)

    # PREEVO stacked UNDER an evolved win-con (preEvolution) is in play, not in the deck.
    evolved = poke(WINCON, energy=1, hp=330)
    evolved["preEvolution"] = [{"id": PREEVO, "playerIndex": 0, "serial": 2}]
    stacked = state(active=evolved, discard=[PREEVO, PREEVO], prizes=6)
    assert _board_of(pilot, stacked).deck_definitely_empty_of(PREEVO)


@pytest.mark.req("REQ-GEN-0032")
def test_dont_search_stands_down_a_bench_fill_whose_only_target_is_gone():
    pilot = _search_pilot([PREEVO] * 3 + [FILLER] * 57)
    play_poffin = opt(PLAY, area=HAND, index=0)              # Buddy-Buddy Poffin in hand[0]
    # All 3 Staryu accounted outside deck -> 2nd Poffin would fetch nothing.
    exhausted = state(active=poke(PREEVO, hp=70), discard=[PREEVO, PREEVO], hand=[POFFIN], prizes=6)
    obs = make_select([play_poffin, opt(END)], current=exhausted)
    assert _ctx(pilot, obs, 0).search_targets_exhausted
    assert "dont-search-an-empty-deck" in _fired(pilot.explain(obs).options[0])
    assert pilot.decide(obs) == [1]                          # End beats guaranteed-whiff Poffin

    # One Staryu unaccounted (could be in hidden prizes) -> rule stays silent; Poffin fine.
    maybe = state(active=poke(PREEVO, hp=70), discard=[PREEVO], hand=[POFFIN], prizes=6)
    obs2 = make_select([play_poffin, opt(END)], current=maybe)
    assert not _ctx(pilot, obs2, 0).search_targets_exhausted
    assert "dont-search-an-empty-deck" not in _fired(pilot.explain(obs2).options[0])
    assert pilot.decide(obs2) == [0]                         # play the bench-filler (sound doctrine)


@pytest.mark.req("REQ-GEN-0032")
def test_dont_search_stands_down_mega_signal_when_all_megas_are_gone():
    # 3 Mega ex (only tutor_mega target), all accounted OUTSIDE deck (discard) -> Mega Signal whiffs.
    pilot = _search_pilot([WINCON] * 3 + [PREEVO] * 3 + [FILLER] * 54)
    play_signal = opt(PLAY, area=HAND, index=0)
    gone = state(active=poke(PREEVO, hp=70), discard=[WINCON, WINCON, WINCON], hand=[MEGA_SIGNAL], prizes=6)
    obs = make_select([play_signal, opt(END)], current=gone)
    c = _ctx(pilot, obs, 0)
    assert c.search_targets_exhausted and not c.search_redundant_wincon   # whiff, not in-hand case
    assert "dont-search-an-empty-deck" in _fired(pilot.explain(obs).options[0])
    assert pilot.decide(obs) == [1]

    # One Mega unaccounted (deck may still hold it) -> NOT certain -> rule stays silent.
    maybe = state(active=poke(PREEVO, hp=70), discard=[WINCON, WINCON], hand=[MEGA_SIGNAL], prizes=6)
    assert not _ctx(pilot, make_select([play_signal, opt(END)], current=maybe), 0).search_targets_exhausted


@pytest.mark.req("REQ-GEN-0032")
def test_dont_tutor_the_held_wincon_for_a_wincon_only_tutor():
    # Mega Signal fetches ONLY the wincon; with a Mega already in hand a 2nd is redundant — even
    # though the deck still holds Megas (so it does NOT whiff). The ep82228017-fr4 shape.
    pilot = _search_pilot([WINCON] * 3 + [PREEVO] * 3 + [FILLER] * 54)
    play_signal = opt(PLAY, area=HAND, index=0)
    held = state(active=poke(PREEVO, hp=70), hand=[MEGA_SIGNAL, WINCON], prizes=6)
    obs = make_select([play_signal, opt(END)], current=held)
    c = _ctx(pilot, obs, 0)
    assert c.search_redundant_wincon and not c.search_targets_exhausted   # redundant, not a whiff
    assert "dont-tutor-the-held-wincon" in _fired(pilot.explain(obs).options[0])
    assert pilot.decide(obs) == [1]                          # don't dig a 2nd dead Mega — End/develop


@pytest.mark.req("REQ-GEN-0032")
def test_flexible_tutor_is_not_redundant_when_the_wincon_is_in_hand():
    # Ultra Ball fetches ANY Pokémon, so a held wincon does NOT make it redundant — can still
    # pull a pre-evolution / opener. Rule must stay silent (only a wincon-ONLY tutor is redundant).
    pilot = _search_pilot([WINCON] * 3 + [PREEVO] * 3 + [FILLER] * 54)
    play_ball = opt(PLAY, area=HAND, index=0)
    held = state(active=poke(PREEVO, hp=70), hand=[ULTRA_BALL, WINCON], prizes=6)
    obs = make_select([play_ball, opt(END)], current=held)
    assert not _ctx(pilot, obs, 0).search_redundant_wincon
    assert "dont-tutor-the-held-wincon" not in _fired(pilot.explain(obs).options[0])

    # Ultra Ball whiffs only when deck is empty of EVERY Pokémon (all Megas + Staryu accounted).
    none_left = state(active=poke(PREEVO, hp=70),
                      discard=[WINCON, WINCON, WINCON, PREEVO, PREEVO], hand=[ULTRA_BALL], prizes=6)
    obs2 = make_select([play_ball, opt(END)], current=none_left)
    assert _ctx(pilot, obs2, 0).search_targets_exhausted
    assert "dont-search-an-empty-deck" in _fired(pilot.explain(obs2).options[0])


# ------------------------------------------ cost_discard: a discard-cost search isn't a free dig
def _endorse_ultra_pilot():
    """A Pilot that strongly endorses Ultra Ball (a test stand-in for any rule that wants it) — so the
    only thing deciding its sequence is the cost_discard commitment tiering, not its score."""
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]},
                     hypotheses=[Hypothesis(id="t-endorse-ultra", rationale="test", weight=50,
                                            when=lambda c: c.card_id == ULTRA_BALL)])
    return Pilot(strat, deck=[WINCON] * 3 + [PREEVO] * 3 + [FILLER] * 54,
                 general_strategy=GENERAL_STRATEGY, stats=_stats(attacks=_ATTACK_STATS),
                 functions=CardFunctions(_FNS), effects=fetch_effects(_FNS))


@pytest.mark.req("REQ-GEN-0033")
def test_dig_before_commit_skips_a_cost_discard_search():
    # Ultra Ball pays 2 cards to play -> NOT a free dig -> no dig-before-commit bonus; plain search keeps it.
    pilot = _search_pilot([WINCON] * 3 + [PREEVO] * 3 + [FILLER] * 54)
    obs = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1), opt(END)],
                      current=state(active=poke(PREEVO, hp=70), hand=[ULTRA_BALL, MEGA_SIGNAL], prizes=6))
    traces = pilot.explain(obs).options
    assert "dig-before-commit" not in _fired(traces[0])     # Ultra Ball (cost_discard): not free
    assert "dig-before-commit" in _fired(traces[1])         # Mega Signal (plain search): free dig


@pytest.mark.req("REQ-GEN-0033")
def test_cost_discard_search_is_sequenced_after_a_free_dig_even_when_it_scores_higher():
    # Ultra Ball endorsed (+50) over free search (Mega Signal, +20), yet discard-cost play is a
    # COMMITMENT — `_finish_turn_last` holds it to tier 2, so FREE dig (tier 0) taken first.
    pilot = _endorse_ultra_pilot()
    obs = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1), opt(END)],
                      current=state(active=poke(PREEVO, hp=70), hand=[ULTRA_BALL, MEGA_SIGNAL], prizes=6))
    traces = pilot.explain(obs).options
    assert traces[0].score > traces[1].score                # Ultra Ball outscores free search ...
    assert pilot.decide(obs) == [1]                         # ... yet free dig is sequenced first


@pytest.mark.req("REQ-GEN-0033")
def test_attach_beats_a_cost_discard_search_the_ep82228640_fr7_shape():
    # ep82228640-fr7 shape: free Energy attach vs 2-card-discard Ultra Ball. With Ultra Ball no
    # longer treated as free dig, attach (needed, free development) taken first.
    pilot = _search_pilot([WINCON] * 3 + [PREEVO] * 3 + [FILLER] * 54)
    attach = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)   # W -> Staryu (needs energy)
    play_ball = opt(PLAY, area=HAND, index=2)                                    # Ultra Ball (cost_discard)
    cur = state(active=poke(PREEVO, energy=0, hp=70), hand=[WINCON, WATER, ULTRA_BALL], prizes=6)
    obs = make_select([attach, play_ball, opt(END)], current=cur)
    assert "dig-before-commit" not in _fired(pilot.explain(obs).options[1])      # Ultra Ball not free
    assert pilot.decide(obs) == [0]                          # attach first; discard-cost dig waits
