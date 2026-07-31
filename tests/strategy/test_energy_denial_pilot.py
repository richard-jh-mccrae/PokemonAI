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

**The instrument moved (ADR-0080 / Issue #187, armed and the incumbent DELETED by Issue #228).**
The three defects above are ADR-0062's, and they are still the subject of this file — but the value
they are read off is now **Deny Relevance** (`_deny_relevance_best`, a `[0, 1]` scalar), not the
`opp_denial_best` damage magnitude, which no longer exists. Every claim below is therefore stated
against the armed read. Two consequences worth naming rather than discovering:

  * The read needs the card facts the magnitude oracle never asked for — the Energy's **type**
    (resolved through the Stat Provider, so a body must carry real Basic ``{F}`` Energy cards rather
    than the helper's untyped placeholder) and each attack's **per-slot cost types**
    (``AttackStat.energyTypes``). Without them relevance is 0 everywhere and the fixture stops
    meaning what it says.
  * ``K x relevance`` is the damage of the attack the strip puts **out of reach**, not the
    ``before - after`` differential the magnitude oracle reported. Same sign, same decision, and
    strictly better informed where the two diverge (ADR-0080 Amendment B) — the numbers below are
    the armed instrument's own.
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
FIGHTING_ENERGY = 6                 # Basic {F} Energy (SVE 6). Card id and EnergyType coincide here
                                    # and ONLY by coincidence in the data — the read resolves the
                                    # type through the Provider, never from the card id.
DISCARD_ENERGY, ENERGY = 30, 6      # SelectContext / OptionType (cg/api.py)

AURA_JAB, MEGA_BRAVE = 1, 2         # attack ids for Mega Lucario ex's two attacks


def _pilot():
    stats = DictCardStatProvider({
        HAMMER: CardStat(HAMMER, hp=0),
        LUCARIO: CardStat(LUCARIO, name="Mega Lucario ex", hp=340, attacks=(AURA_JAB, MEGA_BRAVE),
                          maxDamage=270, maxDamageCost=2, minAttackCost=1, minCostDamage=130),
        SUPPORT: CardStat(SUPPORT, name="Lunatone", hp=110, attacks=()),
        FIGHTING_ENERGY: CardStat(FIGHTING_ENERGY, name="Basic {F} Energy", energyType=FIGHTING),
    }, attacks={
        # Verified at data/EN_Card_Data.csv (MEG 77): Aura Jab {F} 130, Mega Brave {F}{F} 270.
        # These REPLACE the old `p._attack_cost` / `p._attack_damage` monkeypatches: the relevance
        # read wants the cost's per-slot TYPES, which a bare cost count cannot carry, and one record
        # per attack keeps the two readings of the same fact from drifting.
        AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,)),
        MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING)),
    })
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({HAMMER: ["energy_denial"]}),
                 deny_relevance=True, deny_strip_delta=True)


def _fpoke(cid: int, *, energy: int = 0, hp: int = 0) -> dict:
    """`poke()` with REAL Basic {F} Energy cards attached. The helper's default fills `energies` with
    the unresolvable card id 0, which the Provider cannot type — and an untyped Energy is on no plan's
    typed critical path, so under the armed read such a body scores relevance 0 no matter what it is
    holding. Typed Energy is what makes these boards mean what their docstrings say.

    Kept as a named wrapper (rather than spelling `energy_card=` at ~20 call sites) so the reason for
    the typed Energy is stated ONCE, where it can be read."""
    return poke(cid, hp=hp, energy=energy, energy_card=FIGHTING_ENERGY)


def _deny_best(pilot, obs) -> float:
    """The armed deny read for this board — `Board.deny_relevance_best` through its cache-or-compute
    ladder. This is the value the fire rung prices; it REPLACES `Board.opp_denial_best`, deleted with
    the rest of the ADR-0062 magnitude oracle by Issue #228."""
    return pilot._deny_relevance_best(obs, pilot._board(obs, obs["select"]))


def _hammer_obs(*, opp_active, opp_bench=()):
    return make_select([opt(PLAY, index=0), opt(type=9)], context=MAIN,
                       current=state(active=_fpoke(SUPPORT, energy=0, hp=110),
                                     bench=[_fpoke(SUPPORT)], hand=[HAMMER],
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
    exactly the 2 Energy its Mega Brave needs. The card and the engine both allow that target.

    Armed, the bench row counts in full because ADR-0071's promotion GATE is open — `_deny_best_of`
    weights a bench row at 1.0 when the gate is open and 0.0 when it is shut, which is what replaced
    the flat `_DENIAL_BENCH` discount. On this fixture the gate's `switch_enabler` leg fails OPEN
    (there is no opponent Read to rule a Switch out), which is the deliberate fail direction: the
    gate can only ever make a threat read LESS pessimistic, so an unreadable board must not shut it."""
    obs = _hammer_obs(opp_active=_fpoke(SUPPORT, energy=0, hp=110),
                      opp_bench=[_fpoke(LUCARIO, energy=2, hp=340)])
    pilot = _pilot()
    assert _deny_best(pilot, obs) > 0, "a loaded bench behind a bare Active must still read as denial"
    assert _hammer(pilot, obs) > 0


# --- defect 2: no whiff model ---------------------------------------------------------------------

def test_the_hammer_is_HELD_against_surplus_energy():
    """3 Energy on a Mega Lucario ex: strip one and it STILL affords Mega Brave (270). The Hammer
    denies nothing, so hold it — the old gate fired here purely because Energy was present."""
    obs = _hammer_obs(opp_active=_fpoke(LUCARIO, energy=3, hp=340))
    pilot = _pilot()
    assert _deny_best(pilot, obs) == 0, "surplus Energy must read as a whiff, not as denial"
    assert _hammer(pilot, obs) <= 0


def test_the_hammer_fires_when_the_strip_actually_turns_the_nuke_off():
    """Exactly 2 Energy: one Hammer puts Mega Brave (270) out of reach and leaves them on Aura Jab.

    The magnitude oracle reported the DIFFERENTIAL (270 - 130 = 140); the armed read reports the
    damage of the attack the strip switches off, so `K x relevance` is Mega Brave's own **270**.
    The reference moved with the instrument (Issue #228 deleted the differential); what is pinned
    here is unchanged — the strip must price the NUKE it turns off, not the poke that survives it,
    which is exactly what separates this frame from the 3-Energy whiff above."""
    obs = _hammer_obs(opp_active=_fpoke(LUCARIO, energy=2, hp=340))
    pilot = _pilot()
    assert _DENY_RELEVANCE_K * _deny_best(pilot, obs) == pytest.approx(270), \
        "the strip must be priced by Mega Brave, the attack it puts out of reach"
    assert _hammer(pilot, obs) > 0


def test_the_hammer_is_HELD_when_nobody_can_pay_an_attack():
    """A body with no affordable attack denies 0 — there is no damage to take away. This subsumes
    the old `opp_active_can_damage_us` premise (dragapult f6: Kyogre off an empty discard)."""
    obs = _hammer_obs(opp_active=_fpoke(SUPPORT, energy=2, hp=110))     # SUPPORT has no attacks
    pilot = _pilot()
    assert _deny_best(pilot, obs) == 0, "a body with no attack to pay for denies nothing"
    assert _hammer(pilot, obs) <= 0


# --- defect 3: the target select was unscored ------------------------------------------------------

def _discard_energy_obs(opp_active, opp_bench, options):
    return make_select(options, context=DISCARD_ENERGY,
                       current=state(active=_fpoke(SUPPORT, hp=110), hand=[],
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
    obs = _discard_energy_obs(_fpoke(LUCARIO, energy=2, hp=340), [_fpoke(SUPPORT, energy=1)], opts)
    dec = _pilot().explain(obs)
    assert dec.chosen != [0], "still stripping the oldest Energy off a support mon"
    assert dec.chosen[0] in (1, 2), f"expected the Active's Energy, chose {dec.chosen}"


# `test_the_target_pick_prefers_the_active_over_an_equally_denied_bench_body` was RETIRED (Issue #228,
# 2026-07-31): its claim is CONTRADICTED by the armed instrument, not merely restated by it, so it is
# recorded here rather than deleted silently — a doctrine reversal must leave a mark.
#
# As written (ADR-0062) the claim was: same denial on both, but the Active is the body that attacks us
# NEXT turn and a benched one must still be promoted, so `_DENIAL_BENCH` DISCOUNTS the bench option
# rather than ignoring it. Both halves have since been ruled against, and both were re-verified at
# source before this retirement:
#
#   * Its PREMISE is refuted by the RULES. `docs/rules.md` §2 puts the turn as "take actions in any
#     order -> (optionally) attack, which ends your turn", and §3 lists Retreat as one ordinary action
#     per turn "pay the Retreat cost in Energy" — so retreat-then-attack is legal in ONE turn and a
#     benched attacker owes ENERGY, never tempo. ADR-0071 decision 6 states exactly that and corrects
#     the CONTEXT.md Threat Clock's old "promotion surcharge" wording.
#   * Its MECHANISM is retired by RULING. ADR-0080 Amendment B ruling 2 (user, 2026-07-30) makes the
#     armed target pick a pure `argmax relevance` with NO area weight — relevance already prices a
#     benched body's slower clock through its own line scan, so discounting it again double-counts —
#     and ADR-0084 decision 2 re-affirms it verbatim ("it correctly dropped `_DENIAL_BENCH`'s area
#     weight from this surface, and that stands") while refining only its no-timing-at-all reading.
#     `_DENIAL_BENCH` itself was the OFF-path weight, deleted with that path by Issue #228.
#
# On the retired board the two bodies were literally interchangeable — the same card holding the same
# Energy — so armed they score EQUAL (270.0 each: 1 {F} short of Mega Brave's {F}{F} on both) and
# stable order takes option 0. ADR-0084's strip Δ cannot break that tie either, correctly: with two
# identical threats, stripping either leaves the other attacking, so neither moves my clock
# (`strip_shift` 0 on both, measured). The requirement survives in two places, both green:
#   * the EQUALITY it now implies —
#     `test_deny_relevance_consumer.py::test_the_target_pick_applies_no_area_weight`;
#   * the surviving reason to prefer an Active — that the strip genuinely buys a turn, which is
#     `test_deny_relevance_consumer.py::test_the_clock_breaks_a_cross_body_relevance_tie`, asserted on
#     REAL captured frames rather than on a hand-built pair of clones.
# Nothing is left uncovered: `test_the_won_flip_strips_the_energy_that_actually_denies_the_most` above
# still pins the defect-3 claim this file exists for (a scored pick, never engine option order).
