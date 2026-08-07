"""Energy denial (ADR-0062) through the Pilot, read off Deny Relevance (ADR-0080, armed by Issue #228).

Crushing Hammer (1120) discards an Energy from ANY opponent Pokémon — Active or bench.
Worked example throughout: Mega Lucario ex, Aura Jab {F} 130 / Mega Brave {F}{F} 270.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import _DENY_RELEVANCE_K, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import MAIN, PLAY, make_select, opt, poke, state

ACTIVE, BENCH = 4, 5                # AreaType (cg/api.py)
FIGHTING = 6                        # EnergyType.FIGHTING (cg/api.py)

HAMMER = 1120                       # Crushing Hammer (energy_denial)
LUCARIO = 678                       # Mega Lucario ex: Aura Jab {F} 130 / Mega Brave {F}{F} 270
SUPPORT = 675                       # Lunatone — a benched body with no attack worth paying for
FIGHTING_ENERGY = 6                 # Basic {F} Energy (SVE 6); id == EnergyType only by coincidence —
                                    # the read resolves the type through the Provider, never the id.
DISCARD_ENERGY, ENERGY = 30, 6      # SelectContext / OptionType (cg/api.py)

AURA_JAB, MEGA_BRAVE = 1, 2


def _pilot():
    stats = DictCardStatProvider({
        HAMMER: CardStat(HAMMER, hp=0),
        LUCARIO: CardStat(LUCARIO, name="Mega Lucario ex", hp=340, attacks=(AURA_JAB, MEGA_BRAVE),
                          maxDamage=270, maxDamageCost=2, minAttackCost=1, minCostDamage=130),
        SUPPORT: CardStat(SUPPORT, name="Lunatone", hp=110, attacks=()),
        FIGHTING_ENERGY: CardStat(FIGHTING_ENERGY, name="Basic {F} Energy", energyType=FIGHTING),
    }, attacks={
        # Verified at data/EN_Card_Data.csv (MEG 77).
        AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,)),
        MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING)),
    })
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({HAMMER: ["energy_denial"]}),
                 deny_relevance=True, deny_strip_delta=True)


def _fpoke(cid: int, *, energy: int = 0, hp: int = 0) -> dict:
    """`poke()` with REAL Basic {F} Energy. `poke()`'s default card id 0 cannot be typed by the
    Provider, and an untyped Energy scores relevance 0 whatever the body is holding."""
    return poke(cid, hp=hp, energy=energy, energy_card=FIGHTING_ENERGY)


def _deny_best(pilot, obs) -> float:
    return pilot._deny_relevance_best(obs, pilot._board(obs, obs["select"]))


def _hammer_obs(*, opp_active, opp_bench=()):
    return make_select([opt(PLAY, index=0), opt(type=9)], context=MAIN,
                       current=state(active=_fpoke(SUPPORT, energy=0, hp=110),
                                     bench=[_fpoke(SUPPORT)], hand=[HAMMER],
                                     opp_active=opp_active, opp_bench=list(opp_bench)))


def _hammer(pilot, obs):
    """A priced TACTICAL term, not a flat rung: a flat positive could never DECLINE a whiff, because
    `_finish_turn_last` tiers a free Item ahead of everything."""
    return pilot.explain(obs).options[0].score


def test_the_hammer_fires_on_a_loaded_BENCH_behind_a_bare_active():
    """ADR-0071's promotion gate weights a bench row 1.0 open / 0.0 shut. Its `switch_enabler` leg
    fails OPEN by design — the gate only ever reduces pessimism, so an unreadable board must not shut it."""
    obs = _hammer_obs(opp_active=_fpoke(SUPPORT, energy=0, hp=110),
                      opp_bench=[_fpoke(LUCARIO, energy=2, hp=340)])
    pilot = _pilot()
    assert _deny_best(pilot, obs) > 0, "a loaded bench behind a bare Active must still read as denial"
    assert _hammer(pilot, obs) > 0


def test_the_hammer_is_HELD_against_surplus_energy():
    obs = _hammer_obs(opp_active=_fpoke(LUCARIO, energy=3, hp=340))
    pilot = _pilot()
    assert _deny_best(pilot, obs) == 0, "surplus Energy must read as a whiff, not as denial"
    assert _hammer(pilot, obs) <= 0


def test_the_hammer_fires_when_the_strip_actually_turns_the_nuke_off():
    """`K x relevance` is the damage of the attack the strip switches OFF, not a before/after
    differential."""
    obs = _hammer_obs(opp_active=_fpoke(LUCARIO, energy=2, hp=340))
    pilot = _pilot()
    assert _DENY_RELEVANCE_K * _deny_best(pilot, obs) == pytest.approx(270), \
        "the strip must be priced by Mega Brave, the attack it puts out of reach"
    assert _hammer(pilot, obs) > 0


def test_the_hammer_is_HELD_when_nobody_can_pay_an_attack():
    obs = _hammer_obs(opp_active=_fpoke(SUPPORT, energy=2, hp=110))     # SUPPORT has no attacks
    pilot = _pilot()
    assert _deny_best(pilot, obs) == 0, "a body with no attack to pay for denies nothing"
    assert _hammer(pilot, obs) <= 0


def _discard_energy_obs(opp_active, opp_bench, options):
    return make_select(options, context=DISCARD_ENERGY,
                       current=state(active=_fpoke(SUPPORT, hp=110), hand=[],
                                     opp_active=opp_active, opp_bench=list(opp_bench)))


def test_the_won_flip_strips_the_energy_that_actually_denies_the_most():
    """The engine orders DISCARD_ENERGY options oldest-attached first, so index 0 is the trap."""
    opts = [
        {"type": ENERGY, "area": BENCH, "index": 0, "playerIndex": 1, "energyIndex": 0},   # oldest
        {"type": ENERGY, "area": ACTIVE, "index": 0, "playerIndex": 1, "energyIndex": 0},
        {"type": ENERGY, "area": ACTIVE, "index": 0, "playerIndex": 1, "energyIndex": 1},
    ]
    obs = _discard_energy_obs(_fpoke(LUCARIO, energy=2, hp=340), [_fpoke(SUPPORT, energy=1)], opts)
    dec = _pilot().explain(obs)
    assert dec.chosen != [0], "still stripping the oldest Energy off a support mon"
    assert dec.chosen[0] in (1, 2), f"expected the Active's Energy, chose {dec.chosen}"


# `test_the_target_pick_prefers_the_active_over_an_equally_denied_bench_body` was RETIRED (Issue #228):
# the armed target pick applies NO area weight (ADR-0080 Amendment B, re-affirmed ADR-0084 decision 2).
