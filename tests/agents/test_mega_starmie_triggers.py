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
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from pilot_helpers import (
    ACTIVE, ATTACH, ATTACK, DECK, HAND, NO, PLAY, SETUP_ACTIVE, TO_HAND, YES,
    attack_opt, card_opt, make_select, opt, poke, state,
)

# Load the shipped deck Strategy (pure data; imports only common.strategy).
_REAL = Path(__file__).resolve().parents[2] / "src" / "agents" / "mega_starmie" / "strategy.py"
_spec = importlib.util.spec_from_file_location("ms_real_strategy", _REAL)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STRATEGY = _mod.STRATEGY

STARYU, MEGA_STARMIE, CINDERACE, RABOOT = 1030, 1031, 666, 665
WATER, FIRE, LIGHTNING = 3, 2, 4
IS_FIRST = 41  # SelectContext.IS_FIRST -- "Would you like to go first?" (cg/api.py)

_STATS = DictCardStatProvider({
    STARYU: CardStat(STARYU, energyType=WATER, weakness=LIGHTNING, hp=70),
    MEGA_STARMIE: CardStat(MEGA_STARMIE, energyType=WATER, weakness=LIGHTNING, megaEx=True, hp=330),
    # Stage 2, evolvesFrom Raboot (none in deck -> stranded, dead in hand).
    CINDERACE: CardStat(CINDERACE, energyType=FIRE, weakness=WATER, hp=160,
                        name="Cinderace", evolvesFrom="Raboot"),
    # Raboot is PRINTED but never on the deck list — which is what strands the Cinderace. ADR-0104
    # fails OPEN on a previous stage the pool holds no printing of, so the printing must exist here.
    RABOOT: CardStat(RABOOT, synthetic=True, energyType=FIRE, weakness=WATER, hp=90, name='Raboot'),
})
_TAGS = CardFunctions({CINDERACE: ["opener"]})


def _pilot(functions=_TAGS, stats=_STATS):
    # deck list carries the real members these tests exercise — stranded-evolution
    # check (`dont-fetch-the-setup-only-opener`) reads it: Cinderace with no Raboot on list.
    return Pilot(STRATEGY, deck=[CINDERACE] * 4 + [STARYU] * 3 + [MEGA_STARMIE] * 3 + [1] * 50,
                 general_strategy=GENERAL_STRATEGY, stats=stats, functions=functions)


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


@pytest.mark.req("REQ-MS-0001")
def test_preferred_start_second_declines_the_coin_toss():
    """Turbo deck: at the coin toss, choose to go SECOND (the player going first can't attack T1).
    Declared via params["preferred_start"]="second"; the general `honor-preferred-start` honors it."""
    p = _pilot()
    obs = make_select([opt(YES), opt(NO)], context=IS_FIRST, current=state())
    assert p.decide(obs) == [1]                                          # NO = go second
    assert "honor-preferred-start" in _fired(p.explain(obs).options[0])  # fires on YES (go-first) option


@pytest.mark.req("REQ-MS-0002")
def test_never_fetch_cinderace_silent_when_choosing_the_opening_active():
    """Choosing Cinderace as the opening Active (Explosiveness) is correct — the rule is about
    FETCHING (TO_HAND), so it must stay silent at the setup-Active choice."""
    p = _pilot()
    obs = make_select([card_opt(HAND, 0)], context=SETUP_ACTIVE, current=state(hand=[CINDERACE]))
    assert "dont-fetch-the-setup-only-opener" not in _fired(p.explain(obs).options[0])


# --- Hero's Cape deploy, end-to-end in the deck (Tool Doctrine, ADR-0028) ----------------------
# The +100 is read off the parsed `CardStat.hpBonus`; deploy is PROACTIVE by survival-turns math.
HEROS_CAPE, FIRE = 1159, 2
_CAPE_STATS = DictCardStatProvider({
    MEGA_STARMIE: CardStat(MEGA_STARMIE, energyType=WATER, weakness=LIGHTNING, megaEx=True,
                           hp=330, minCostDamage=120),
    HEROS_CAPE: CardStat(HEROS_CAPE, synthetic=True, hp=0, aceSpec=True, hpBonus=100),  # ACE SPEC Tool, +100 parsed
    8888: CardStat(8888, energyType=FIRE, maxDamage=400),       # opp hits 400: +100 (430) buys survival turn
    7777: CardStat(7777, energyType=FIRE, maxDamage=500),       # opp hits 500: doomed even at 430 -> wasted
    6666: CardStat(6666, energyType=FIRE, maxDamage=200),       # opp hits 200: +100 still banks survival turn
})
_CAPE_TAGS = CardFunctions({HEROS_CAPE: ["tool"], CINDERACE: ["opener"]})


def _cape_pilot():
    return Pilot(STRATEGY, deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_CAPE_STATS, functions=_CAPE_TAGS)


def _attach_cape_vs(opp_attacker):
    # ATTACH Hero's Cape (hand idx 0) onto full-HP Active Mega Starmie ex, facing `opp_attacker`.
    return make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)],
                       current=state(active=poke(MEGA_STARMIE, hp=330),
                                     opp_active=poke(opp_attacker), hand=[HEROS_CAPE]))


# The whole Tool Doctrine is DELETED (Issue #386); a Cape that buys a survival turn is now
# `survival` on the composed end board. `tests/strategy/test_tool_doctrine.py` holds the audit.


# --- Boss's Orders gust, end-to-end through the REAL mega_starmie Pilot (ADR-0022) -------------
# The deck runs ONE gust card (Boss's Orders, id 1182, Function Tag `gust`).
BOSS_ORDERS = 1182
WALL_810, KO_BENCH_811 = 810, 811
_A_JET_GUST = 52   # Jetting Blow as a real record (the minCostDamage fallback is retired, ADR-0052)
_GUST_STATS = DictCardStatProvider({
    MEGA_STARMIE: CardStat(MEGA_STARMIE, energyType=WATER, weakness=LIGHTNING, megaEx=True,
                           hp=330, minAttackCost=1, minCostDamage=120,   # Jetting Blow 120 at 1 W
                           attacks=(_A_JET_GUST,)),
    BOSS_ORDERS: CardStat(BOSS_ORDERS, hp=0),
    WALL_810: CardStat(WALL_810, synthetic=True, hp=330),       # opp Active wall -- Jetting Blow can't KO it
    KO_BENCH_811: CardStat(KO_BENCH_811, synthetic=True, hp=60),  # opp benched mon -- Jetting Blow KOs it after gust
}, attacks={_A_JET_GUST: AttackStat(_A_JET_GUST, damage=120, cost=1)})
_GUST_TAGS = CardFunctions({BOSS_ORDERS: ["gust"], CINDERACE: ["opener"]})


def _gust_pilot():
    return Pilot(STRATEGY, deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_GUST_STATS, functions=_GUST_TAGS)


# `gust-for-the-ko` is DELETED (Issue #386); the gust TARGET side is untouched.

# --- GENERAL: the deck-source accel rider (Turbo Flare) is DERIVED, not declared ---------------
# The attack fact lives in `AttackStat.recoverSource="deck"`; the Role declaration is the confirm.

def _shipped():
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from train.tune import _build_pilot
    return _build_pilot("mega_starmie")[0]


@pytest.mark.req("REQ-ACCEL-0002")
def test_turbo_flare_rider_is_in_the_attack_stat_and_derives_the_accel_body():
    """Cinderace joins the DERIVED bench-accelerator set from the parsed attack fact alone."""
    sp = _shipped()
    st = sp._attack_stat(965)
    assert (st.recoverN, st.recoverEnergyType, st.recoverTarget, st.recoverSource) == (
        3, None, "bench", "deck")
    assert sp._derived_accel_body_ids() == frozenset({CINDERACE})
    aura = _shipped_lucario_attack_stat()
    assert aura.recoverSource == "discard"          # the discard family is untouched


def _shipped_lucario_attack_stat():
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from train.tune import _build_pilot
    return _build_pilot("mega_lucario")[0]._attack_stat(982)   # Aura Jab


def _turbo_flare_obs(*, bench=(STARYU,), discard=(), prize=6):
    """A mega_starmie board with Cinderace Active, driven through the real `_board()`: ADR-0077
    retired the hand-injectable `Board(deck_known_counts=...)` path."""
    me = {"active": [{"id": CINDERACE, "hp": 160, "energies": []}],
          "bench": [{"id": c, "hp": 70, "energies": []} for c in bench],
          "hand": [], "discard": [{"id": c} for c in discard],
          "prize": [None] * prize,
          "deckCount": 60 - 1 - len(bench) - len(discard) - prize}
    return {"current": {"yourIndex": 0, "turn": 5,
                        "players": [me, {"active": [], "bench": [], "prize": []}]}}


def _turbo_flare_units(sp, obs):
    board = sp._board(obs, obs.get("select"), carried=sp.carried())
    return sp._recover_units(965, {}, board, obs)


@pytest.mark.req("REQ-ACCEL-0002")
def test_turbo_flare_credit_is_need_and_fuel_gated():
    """`_recover_units` reads the fuel bound from the DECK: 0 on an empty bench, and 0 once the deck
    is provably dry of Basic Energy — which the expectation must NOT resurrect."""
    sp = _shipped()
    assert _turbo_flare_units(sp, _turbo_flare_obs()) == 3
    assert _turbo_flare_units(sp, _turbo_flare_obs(bench=())) == 0
    # all 9 Water accounted for outside the deck — sound-empty, so no leg may claim a copy
    assert _turbo_flare_units(sp, _turbo_flare_obs(discard=(WATER,) * 9)) == 0


@pytest.mark.req("REQ-ACCEL-0002")
def test_turbo_flare_keeps_its_credit_when_the_pigeonhole_floor_would_zero_it():
    """ADR-0077 at the shipped-agent seam: the retired pigeonhole floor zeroed the rider outright,
    while the expectation stays fractional, strictly positive and bounded by `recoverN`."""
    sp = _shipped()
    obs = _turbo_flare_obs(discard=(WATER,) * 6, prize=5)
    board = sp._board(obs, obs.get("select"), carried=sp.carried())
    water = sp._state_model.mine.deck_energy_counts[WATER]
    assert water.floor == 0                                      # nothing PROVABLE behind 5 prizes
    units = sp._recover_units(965, {}, board, obs)
    assert 0.0 < units <= 3.0
    assert units != int(units)                                   # genuinely fractional, not re-floored


@pytest.mark.req("REQ-ACCEL-0002")
def test_accel_machinery_derives_without_any_role_declaration():
    """A Strategy with NO roles at all still derives `accel_source` and the bench-fill trigger."""
    from common.strategy import Strategy
    sp = _shipped()
    bare = Strategy(lines=STRATEGY.lines)                        # lines only, no roles
    p = Pilot(bare, deck=list(sp.deck), general_strategy=GENERAL_STRATEGY,
              stats=sp.stats, functions=sp.functions)
    assert "accel_source" in p._roles_of(CINDERACE)
    me = {"active": [{"id": CINDERACE, "hp": 160, "energies": []}], "bench": []}
    assert p._accel_recipient_missing(me) is True
    me2 = {**me, "bench": [{"id": STARYU, "hp": 70, "energies": []}]}
    assert p._accel_recipient_missing(me2) is False
