"""Energy denial (ADR-0062) through the Pilot — the three ways a Crushing Hammer was wasted.

Crushing Hammer (1120): "Flip a coin. If heads, discard an Energy from 1 of your opponent's Pokémon."
ANY Pokémon — and the engine agrees: `op_trash_energy_enemy` (cgpy/chain.py, trace-pinned to
ms_mirror_1002 f14) builds its DISCARD_ENERGY options from their ACTIVE **and** BENCH, as
OptionType.ENERGY entries carrying (area, index, energyIndex).

Four copies ride in both dragapult_ex and mega_starmie, and all three defects below were live:

  1. GATE TOO NARROW  — `opp_active_has_energy`: we stood down whenever their Active was bare, even
                        with a loaded bench. Against a bench-loading opponent (the standard TCG
                        pattern: power up on the bench, promote later) 4 Hammers sat dead all game.
  2. NO WHIFF MODEL   — fired on SURPLUS Energy. Strip one from a body carrying more than its dearest
                        attack costs and it still affords the same attack: nothing denied.
  3. TARGET UNSCORED  — ZERO rungs fired at DISCARD_ENERGY, so every option scored 0.0 and the argmax
                        fell through to index 0: the OLDEST-attached Energy, wherever it sat.

Mega Lucario ex is the worked example throughout (costs verified at EN_Card_Data.csv):
Aura Jab {F} -> 130, Mega Brave {F}{F} -> 270.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import MAIN, PLAY, make_select, opt, poke, state

ACTIVE, BENCH = 4, 5                # AreaType (cg/api.py)

HAMMER = 1120                       # Crushing Hammer (energy_denial)
LUCARIO = 678                       # Mega Lucario ex: Aura Jab {F} 130 / Mega Brave {F}{F} 270
SUPPORT = 675                       # a benched body with no attack worth paying for
DISCARD_ENERGY, ENERGY = 30, 6      # SelectContext / OptionType (cg/api.py)


def _pilot():
    stats = DictCardStatProvider({
        HAMMER: CardStat(HAMMER, hp=0),
        LUCARIO: CardStat(LUCARIO, hp=340, attacks=[1, 2]),
        SUPPORT: CardStat(SUPPORT, hp=110, attacks=[]),
    })
    p = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
              functions=CardFunctions({HAMMER: ["energy_denial"]}))
    p._attack_cost = lambda aid, default=0: {1: 1, 2: 2}.get(aid, default)   # Aura Jab / Mega Brave
    p._attack_damage = lambda aid: {1: 130, 2: 270}.get(aid, 0)
    return p


def _hammer_obs(*, opp_active, opp_bench=()):
    return make_select([opt(PLAY, index=0), opt(type=9)], context=MAIN,
                       current=state(active=poke(SUPPORT, energy=0, hp=110),
                                     bench=[poke(SUPPORT)], hand=[HAMMER],
                                     opp_active=opp_active, opp_bench=list(opp_bench)))


def _hammer(pilot, obs):
    """The Hammer PLAY's score. ADR-0062 retired the flat `play-energy-denial` rung: the value is now
    a priced TACTICAL term (coin x what the strip takes away, net of keeping the Item), so a whiff
    scores <= 0 and is never played -- a flat positive rung could never decline one, because
    `_finish_turn_last` tiers a free Item ahead of everything."""
    return pilot.explain(obs).options[0].score


# --- defect 1: the gate was narrower than the card -------------------------------------------------

def test_the_hammer_fires_on_a_loaded_BENCH_behind_a_bare_active():
    """The bench-loading opponent. Their Active carries nothing; a benched Mega Lucario ex sits on
    exactly the 2 Energy its Mega Brave needs. The card and the engine both allow that target."""
    obs = _hammer_obs(opp_active=poke(SUPPORT, energy=0, hp=110),
                      opp_bench=[poke(LUCARIO, energy=2, hp=340)])
    pilot = _pilot()
    assert pilot._board(obs, obs["select"]).opp_denial_best > 0
    assert _hammer(pilot, obs) > 0


# --- defect 2: no whiff model ---------------------------------------------------------------------

def test_the_hammer_is_HELD_against_surplus_energy():
    """3 Energy on a Mega Lucario ex: strip one and it STILL affords Mega Brave (270). The Hammer
    denies nothing, so hold it — the old gate fired here purely because Energy was present."""
    obs = _hammer_obs(opp_active=poke(LUCARIO, energy=3, hp=340))
    pilot = _pilot()
    assert pilot._board(obs, obs["select"]).opp_denial_best == 0
    assert _hammer(pilot, obs) <= 0


def test_the_hammer_fires_when_the_strip_actually_turns_the_nuke_off():
    """Exactly 2 Energy: one Hammer drops them from Mega Brave (270) to Aura Jab (130)."""
    obs = _hammer_obs(opp_active=poke(LUCARIO, energy=2, hp=340))
    pilot = _pilot()
    assert pilot._board(obs, obs["select"]).opp_denial_best == 140      # 270 - 130
    assert _hammer(pilot, obs) > 0


def test_the_hammer_is_HELD_when_nobody_can_pay_an_attack():
    """A body with no affordable attack denies 0 — there is no damage to take away. This subsumes
    the old `opp_active_can_damage_us` premise (dragapult f6: Kyogre off an empty discard)."""
    obs = _hammer_obs(opp_active=poke(SUPPORT, energy=2, hp=110))       # SUPPORT has no attacks
    pilot = _pilot()
    assert pilot._board(obs, obs["select"]).opp_denial_best == 0
    assert _hammer(pilot, obs) <= 0


# --- defect 3: the target select was unscored ------------------------------------------------------

def _discard_energy_obs(opp_active, opp_bench, options):
    return make_select(options, context=DISCARD_ENERGY,
                       current=state(active=poke(SUPPORT, hp=110), hand=[],
                                     opp_active=opp_active, opp_bench=list(opp_bench)))


def test_the_won_flip_strips_the_energy_that_actually_denies_the_most():
    """The literal waste. The engine orders the options OLDEST-ATTACHED FIRST, so index 0 here is a
    Basic on a benched support mon; their Active sits on exactly the 2 Energy its Mega Brave needs.
    Unscored, the argmax took index 0. Now it takes the Active's."""
    opts = [
        {"type": ENERGY, "area": BENCH, "index": 0, "playerIndex": 1, "energyIndex": 0},   # oldest
        {"type": ENERGY, "area": ACTIVE, "index": 0, "playerIndex": 1, "energyIndex": 0},
        {"type": ENERGY, "area": ACTIVE, "index": 0, "playerIndex": 1, "energyIndex": 1},
    ]
    obs = _discard_energy_obs(poke(LUCARIO, energy=2, hp=340), [poke(SUPPORT, energy=1)], opts)
    dec = _pilot().explain(obs)
    assert dec.chosen != [0], "still stripping the oldest Energy off a support mon"
    assert dec.chosen[0] in (1, 2), f"expected the Active's Energy, chose {dec.chosen}"


def test_the_target_pick_prefers_the_active_over_an_equally_denied_bench_body():
    """Same denial on both, but the Active is the body that attacks us NEXT turn; a benched one must
    still be promoted. `_DENIAL_BENCH` discounts, it does not ignore."""
    opts = [
        {"type": ENERGY, "area": BENCH, "index": 0, "playerIndex": 1, "energyIndex": 0},
        {"type": ENERGY, "area": ACTIVE, "index": 0, "playerIndex": 1, "energyIndex": 0},
    ]
    obs = _discard_energy_obs(poke(LUCARIO, energy=1, hp=340), [poke(LUCARIO, energy=1, hp=340)], opts)
    assert _pilot().explain(obs).chosen == [1]
