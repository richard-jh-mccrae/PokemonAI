"""Horizon-2 lock oracle (ADR-0061) — a locking attack's value includes its FORCED follow-up.

42 attacks in the pool carry a next-turn lock, and they split into two structurally different kinds
that `_LOCK_COST = 40` treated identically:

  SAME-ATTACK lock   "During your next turn, this Pokemon can't use Mega Brave."
                     Mega Lucario ex: Mega Brave 270 ({F}{F}) / Aura Jab 130 ({F}).
                     270 + 130 == 130 + 270. The alternation binds BOTH orderings, so the lock
                     costs no damage at all -- the flat 40 was a phantom charge.

  FULL lock          "During your next turn, this Pokemon can't use attacks."
                     Bloodmoon Ursaluna ex: Blood Moon 240. 240 + 0 = 240, which LOSES to a
                     lock-free 130/turn attacker's 260 -- the lock is worth 130-280, not 40.

When an attack locks, next turn's option set is not a branching space to search: it is forced and
known. So the follow-up is evaluated, not explored. All damage numbers below come from
data/EN_Card_Data.csv.
"""
import pytest

from common.strategy.sequence import followup_damage, sequence_damage

AURA_JAB, MEGA_BRAVE = 1500, 1501       # Mega Lucario ex: 130 (no lock) / 270 (same-attack lock)
BLOOD_MOON = 1502                        # Bloodmoon Ursaluna ex: 240 (FULL lock)
QUICK = 1503                             # a lock-free 130 chip

ML_ATTACKS = {AURA_JAB: 130, MEGA_BRAVE: 270}


# --- the follow-up an attack leaves behind ---------------------------------------------------------

def test_a_same_attack_lock_leaves_the_pokemons_OTHER_attack():
    """Mega Brave locks only ITSELF, so next turn Aura Jab (130) is still there."""
    assert followup_damage(MEGA_BRAVE, affordable=ML_ATTACKS,
                           full_lock=False, same_attack_lock=True) == 130


def test_a_lock_free_attack_leaves_everything_including_the_nuke():
    """Aura Jab locks nothing, so next turn Mega Brave (270) is available."""
    assert followup_damage(AURA_JAB, affordable=ML_ATTACKS,
                           full_lock=False, same_attack_lock=False) == 270


def test_a_full_lock_leaves_nothing():
    """'can't use attacks' -- this Pokemon deals ZERO next turn, whatever else it knows."""
    assert followup_damage(BLOOD_MOON, affordable={BLOOD_MOON: 240, QUICK: 130},
                           full_lock=True, same_attack_lock=False) == 0


def test_the_follow_up_is_bounded_by_what_the_active_can_actually_pay_for():
    """`affordable` is the Energy-gated menu: an attack we cannot pay for is not a follow-up."""
    assert followup_damage(AURA_JAB, affordable={AURA_JAB: 130},   # only 1 Energy: no Mega Brave
                           full_lock=False, same_attack_lock=False) == 130


def test_a_lone_locking_attack_still_leaves_no_follow_up_but_is_not_thereby_forbidden():
    """A same-attack lock with NO other attack leaves 0 -- the sequence term says so honestly, and
    the caller must still let the lone chip beat passing."""
    assert followup_damage(MEGA_BRAVE, affordable={MEGA_BRAVE: 270},
                           full_lock=False, same_attack_lock=True) == 0


# --- the two-turn sequence, which is what the pick actually turns on --------------------------------

def test_the_same_attack_lock_costs_no_damage_over_two_turns():
    """The load-bearing fact. You can never Mega Brave twice in a row WHICHEVER you open with, so the
    lock forbids nothing that the other ordering would have got. `_LOCK_COST = 40` charged Mega Brave
    for a constraint that binds both lines equally."""
    brave = sequence_damage(270, followup_damage(MEGA_BRAVE, affordable=ML_ATTACKS,
                                                 full_lock=False, same_attack_lock=True), weight=1.0)
    jab = sequence_damage(130, followup_damage(AURA_JAB, affordable=ML_ATTACKS,
                                               full_lock=False, same_attack_lock=False), weight=1.0)
    assert brave == jab == 400


def test_the_full_lock_really_does_cost_a_whole_turn():
    """Blood Moon 240 then NOTHING loses to a lock-free 130 twice -- exactly the case the flat 40
    under-charged by an order of magnitude."""
    moon = sequence_damage(240, followup_damage(BLOOD_MOON, affordable={BLOOD_MOON: 240, QUICK: 130},
                                                full_lock=True, same_attack_lock=False), weight=1.0)
    chip = sequence_damage(130, followup_damage(QUICK, affordable={BLOOD_MOON: 240, QUICK: 130},
                                                full_lock=False, same_attack_lock=False), weight=1.0)
    assert moon == 240
    assert chip == 370          # 130 now + Blood Moon still available next turn
    assert chip > moon


def test_the_follow_up_is_discounted_so_damage_now_still_wins_a_tie():
    """Two turns of 400 either way -- but damage THIS turn is certain and next turn's is not (they
    get a move in between). At weight < 1 the front-loaded nuke edges the alternation, which is the
    right default when nothing else separates them."""
    brave = sequence_damage(270, 130, weight=0.5)
    jab = sequence_damage(130, 270, weight=0.5)
    assert brave > jab


def test_a_doomed_active_has_no_next_turn_so_the_lock_is_free():
    """`active_doomed`: the follow-up never materialises, so a lock costs nothing and the sequence
    collapses to this turn's damage. Front-load."""
    assert sequence_damage(270, followup=0, weight=0.5) == 270
    assert sequence_damage(240, followup=0, weight=0.5) == 240
