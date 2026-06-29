"""Deck-specific Strategy hypotheses for mega_starmie (deck-genie Phase B).

Trigger tests through the Pilot's PUBLIC interface (`decide`/`explain`): each hypothesis fires on
its intended decision and stays silent on an obvious counter-case. Loads the SHIPPED
`src/agents/mega_starmie/strategy.py` (the real doctrine), not the test fixture, so these verify the
artifact that actually plays. Lib-free: observations built by hand via `pilot_helpers`.
"""
import importlib.util
from pathlib import Path

import pytest

from common.cards import CardFunctions
from common.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from pilot_helpers import (
    ACTIVE, ATTACH, ATTACK, DECK, HAND, NO, PLAY, SETUP_ACTIVE, TO_HAND, YES,
    card_opt, make_select, opt, poke, state,
)

# Load the shipped deck Strategy (pure data; imports only common.strategy).
_REAL = Path(__file__).resolve().parents[1] / "src" / "agents" / "mega_starmie" / "strategy.py"
_spec = importlib.util.spec_from_file_location("ms_real_strategy", _REAL)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STRATEGY = _mod.STRATEGY

STARYU, MEGA_STARMIE, CINDERACE = 1030, 1031, 666
WATER, FIRE, LIGHTNING = 3, 2, 4
IS_FIRST = 41  # SelectContext.IS_FIRST — "Would you like to go first?" (cg/api.py)

_STATS = DictCardStatProvider({
    STARYU: CardStat(STARYU, energyType=WATER, weakness=LIGHTNING, hp=70),
    MEGA_STARMIE: CardStat(MEGA_STARMIE, energyType=WATER, weakness=LIGHTNING, megaEx=True, hp=330),
    CINDERACE: CardStat(CINDERACE, energyType=FIRE, weakness=WATER, hp=160),
})
_TAGS = CardFunctions({CINDERACE: ["opener"]})


def _pilot(functions=_TAGS, stats=_STATS):
    return Pilot(STRATEGY, deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=stats, functions=functions)


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


@pytest.mark.req("REQ-MS-0001")
def test_prefer_going_second_declines_the_coin_toss():
    """Turbo deck: at the coin toss, choose to go SECOND (the player going first can't attack T1)."""
    p = _pilot()
    obs = make_select([opt(YES), opt(NO)], context=IS_FIRST, current=state())
    assert p.decide(obs) == [1]                                          # NO = go second
    assert "prefer-going-second" in _fired(p.explain(obs).options[0])    # fired on the YES (go-first) option


@pytest.mark.req("REQ-MS-0002")
def test_never_fetch_cinderace_penalises_grabbing_the_opener_at_a_search():
    """A search must not pull Cinderace — it can only enter via Explosiveness at game start, so a
    fetched copy is dead. Penalise the `opener` candidate; prefer the line piece (Staryu)."""
    p = _pilot()
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": CINDERACE}, {"id": STARYU}], current=state(hand=[]))
    opts = p.explain(obs).options
    assert "never-fetch-cinderace" in _fired(opts[0])        # Cinderace (opener) — penalised
    assert "never-fetch-cinderace" not in _fired(opts[1])    # Staryu (line piece) — not the opener
    assert p.decide(obs) == [1]                              # take Staryu, never Cinderace


@pytest.mark.req("REQ-MS-0002")
def test_never_fetch_cinderace_silent_when_choosing_the_opening_active():
    """Choosing Cinderace as the opening Active (Explosiveness) is correct — the rule is about
    FETCHING (TO_HAND), so it must stay silent at the setup-Active choice."""
    p = _pilot()
    obs = make_select([card_opt(HAND, 0)], context=SETUP_ACTIVE, current=state(hand=[CINDERACE]))
    assert "never-fetch-cinderace" not in _fired(p.explain(obs).options[0])


# --- conserve-ignition-prefer-water (needs the minCostDamage + active_cheap_attack_kos signals) ---
WATER_ENERGY, IGNITION = 3, 17
_IGN_STATS = DictCardStatProvider({
    MEGA_STARMIE: CardStat(MEGA_STARMIE, energyType=WATER, weakness=LIGHTNING, megaEx=True,
                           hp=330, minCostDamage=120),   # Jetting Blow (cheap) prints 120
    WATER_ENERGY: CardStat(WATER_ENERGY, hp=0, energyType=WATER),   # a reusable Basic
    IGNITION: CardStat(IGNITION, hp=0, energyType=0),              # special discard-EOT Energy
    9999: CardStat(9999),                                          # generic opp body (HP set via poke)
})
_IGN_TAGS = CardFunctions({IGNITION: ["discard_eot"], CINDERACE: ["opener"]})


def _ign_pilot():
    return Pilot(STRATEGY, deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_IGN_STATS, functions=_IGN_TAGS)


def _attach_ignition_onto_active_wincon(opp_hp, hand):
    # ATTACH option: the Ignition card (hand index 1) onto my Active wincon (inPlay ACTIVE/0).
    return make_select([opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)],
                       current=state(active=poke(MEGA_STARMIE, energy=0),
                                     opp_active=poke(9999, hp=opp_hp), hand=hand))


@pytest.mark.req("REQ-MS-0003")
def test_conserve_ignition_fires_when_the_cheap_attack_already_kos():
    """Cheap Jetting Blow (120) KOs the 120-HP Active and a reusable Water is in hand → don't burn the
    finite Ignition (CCC→Nebula); prefer the Water. (dont-waste-discard-energy exempts the wincon,
    so this deck rule is what covers it.)"""
    obs = _attach_ignition_onto_active_wincon(opp_hp=120, hand=[WATER_ENERGY, IGNITION])
    assert "conserve-ignition-prefer-water" in _fired(_ign_pilot().explain(obs).options[0])


@pytest.mark.req("REQ-MS-0003")
def test_conserve_ignition_silent_when_nebula_is_actually_needed():
    """Cheap attack (120) does NOT KO the 200-HP Active → you need Nebula (CCC via Ignition) → the
    rule must stay silent so the Ignition attach isn't penalised."""
    obs = _attach_ignition_onto_active_wincon(opp_hp=200, hand=[WATER_ENERGY, IGNITION])
    assert "conserve-ignition-prefer-water" not in _fired(_ign_pilot().explain(obs).options[0])


@pytest.mark.req("REQ-MS-0003")
def test_conserve_ignition_silent_without_a_reusable_water_alternative():
    """No reusable Water in hand → there's no cheaper alternative, so don't penalise the Ignition."""
    obs = _attach_ignition_onto_active_wincon(opp_hp=120, hand=[STARYU, IGNITION])  # no Water; Ignition at idx 1
    assert "conserve-ignition-prefer-water" not in _fired(_ign_pilot().explain(obs).options[0])


# --- Hero's Cape deploy, end-to-end in the deck (the GENERAL `deploy-hp-tool-on-breakpoint` rule) ---
# Hero's Cape's +100 is no longer hardcoded in the deck: the general rule reads it off the parsed
# `CardStat.hpBonus` (= 100). These confirm the wiring fires through the real mega_starmie Pilot —
# ACE SPEC Cape, real deck roles, the weakness-aware `Board.incoming_active_damage`.
HEROS_CAPE, FIRE = 1159, 2
_CAPE_STATS = DictCardStatProvider({
    MEGA_STARMIE: CardStat(MEGA_STARMIE, energyType=WATER, weakness=LIGHTNING, megaEx=True,
                           hp=330, minCostDamage=120),
    HEROS_CAPE: CardStat(HEROS_CAPE, hp=0, aceSpec=True, hpBonus=100),  # ACE SPEC Tool, +100 parsed
    8888: CardStat(8888, energyType=FIRE, maxDamage=400),       # opp hits 400: doomed (>330), +100 saves (<430)
    7777: CardStat(7777, energyType=FIRE, maxDamage=500),       # opp hits 500: +100 (430) does NOT save
    6666: CardStat(6666, energyType=FIRE, maxDamage=200),       # opp hits 200: not doomed at all
})
_CAPE_TAGS = CardFunctions({HEROS_CAPE: ["tool"], CINDERACE: ["opener"]})


def _cape_pilot():
    return Pilot(STRATEGY, deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_CAPE_STATS, functions=_CAPE_TAGS)


def _attach_cape_vs(opp_attacker):
    # ATTACH Hero's Cape (hand idx 0) onto my full-HP Active Mega Starmie ex, facing `opp_attacker`.
    return make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)],
                       current=state(active=poke(MEGA_STARMIE, hp=330),
                                     opp_active=poke(opp_attacker), hand=[HEROS_CAPE]))


@pytest.mark.req("REQ-MS-0004")
def test_deploy_heros_cape_fires_when_plus_100_dodges_the_incoming_ko():
    """Active wincon is doomed (incoming 400 >= 330) but +100 (-> 430) survives it → deploy the Cape now."""
    assert "deploy-hp-tool-on-breakpoint" in _fired(_cape_pilot().explain(_attach_cape_vs(8888)).options[0])


@pytest.mark.req("REQ-MS-0004")
def test_deploy_heros_cape_silent_when_plus_100_would_not_save():
    """Incoming 500 still KOs even at 430 → the Cape is wasted, so don't deploy it."""
    assert "deploy-hp-tool-on-breakpoint" not in _fired(_cape_pilot().explain(_attach_cape_vs(7777)).options[0])


@pytest.mark.req("REQ-MS-0004")
def test_deploy_heros_cape_silent_when_not_doomed():
    """Incoming 200 < 330 → not under threat → hold the irreplaceable Cape, don't equip early."""
    assert "deploy-hp-tool-on-breakpoint" not in _fired(_cape_pilot().explain(_attach_cape_vs(6666)).options[0])


# --- Boss's Orders gust, end-to-end through the REAL mega_starmie Pilot (general doctrine, ADR-0022) ---
# The deck runs ONE gust card (Boss's Orders, id 1182, Function Tag `gust`). These confirm the GENERAL
# gust rules fire through the shipped deck Pilot — real roles (Mega Starmie ex = win_condition), the
# `_can_ko` oracle, and the SWITCH target-select.
BOSS_ORDERS = 1182
WALL_810, KO_BENCH_811 = 810, 811
_GUST_STATS = DictCardStatProvider({
    MEGA_STARMIE: CardStat(MEGA_STARMIE, energyType=WATER, weakness=LIGHTNING, megaEx=True,
                           hp=330, minAttackCost=1, minCostDamage=120),   # Jetting Blow 120 at 1 W
    BOSS_ORDERS: CardStat(BOSS_ORDERS, hp=0),
    WALL_810: CardStat(WALL_810, hp=330),       # opp Active wall — Jetting Blow can't KO it
    KO_BENCH_811: CardStat(KO_BENCH_811, hp=60),  # opp benched mon — Jetting Blow KOs it after a gust
})
_GUST_TAGS = CardFunctions({BOSS_ORDERS: ["gust"], CINDERACE: ["opener"]})


def _gust_pilot():
    return Pilot(STRATEGY, deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_GUST_STATS, functions=_GUST_TAGS)


@pytest.mark.req("REQ-MS-0005")
def test_real_pilot_plays_bosss_orders_to_reach_a_benched_ko():
    """Through the real deck: Mega Starmie ex online, opp Active is a wall it can't KO, but a benched
    mon is KO-able — play Boss's Orders (gust-for-the-ko) to drag it up. Options: [Jetting Blow chip,
    play Boss's, End]."""
    obs = make_select(
        [opt(ATTACK, attackId=1), opt(PLAY, area=HAND, index=0), opt(14)],   # 14 = OptionType.END
        context=0,                                                           # MAIN
        current=state(active=poke(MEGA_STARMIE, energy=1, hp=330),
                      opp_active=poke(WALL_810, hp=330),
                      opp_bench=[poke(KO_BENCH_811, hp=60)], hand=[BOSS_ORDERS]))
    p = _gust_pilot()
    assert "gust-for-the-ko" in _fired(p.explain(obs).options[1])
    assert p.decide(obs) == [1]
