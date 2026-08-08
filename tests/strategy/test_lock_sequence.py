"""Horizon-2 lock oracle (ADR-0061) — a locking attack's value includes its FORCED follow-up.

A SAME-ATTACK lock ("can't use Mega Brave") binds both orderings and so costs no damage; a FULL lock
("can't use attacks") costs a whole turn. When an attack locks, next turn's option set is forced and
known, so the follow-up is evaluated rather than explored. Damage numbers: data/EN_Card_Data.csv.
"""
import pytest

from common.strategy.sequence import followup_damage, sequence_damage

AURA_JAB, MEGA_BRAVE = 1500, 1501       # Mega Lucario ex: 130 (no lock) / 270 (same-attack lock)
BLOOD_MOON = 1502                        # Bloodmoon Ursaluna ex: 240 (FULL lock)
QUICK = 1503                             # a lock-free 130 chip

ML_ATTACKS = {AURA_JAB: 130, MEGA_BRAVE: 270}


# --- the follow-up an attack leaves behind ---------------------------------------------------------

def test_a_same_attack_lock_leaves_the_pokemons_OTHER_attack():
    assert followup_damage(MEGA_BRAVE, affordable=ML_ATTACKS,
                           full_lock=False, same_attack_lock=True) == 130


def test_a_lock_free_attack_leaves_everything_including_the_nuke():
    assert followup_damage(AURA_JAB, affordable=ML_ATTACKS,
                           full_lock=False, same_attack_lock=False) == 270


def test_a_full_lock_leaves_nothing():
    assert followup_damage(BLOOD_MOON, affordable={BLOOD_MOON: 240, QUICK: 130},
                           full_lock=True, same_attack_lock=False) == 0


def test_the_follow_up_is_bounded_by_what_the_active_can_actually_pay_for():
    """`affordable` is the Energy-gated menu: an attack we cannot pay for is not a follow-up."""
    assert followup_damage(AURA_JAB, affordable={AURA_JAB: 130},   # only 1 Energy: no Mega Brave
                           full_lock=False, same_attack_lock=False) == 130


def test_a_lone_locking_attack_still_leaves_no_follow_up_but_is_not_thereby_forbidden():
    """The caller must still let the lone chip beat passing."""
    assert followup_damage(MEGA_BRAVE, affordable={MEGA_BRAVE: 270},
                           full_lock=False, same_attack_lock=True) == 0


# --- the two-turn sequence, which is what the pick actually turns on --------------------------------

def test_the_same_attack_lock_costs_no_damage_over_two_turns():
    """You can never Mega Brave twice in a row WHICHEVER you open with, so the lock forbids nothing
    the other ordering would have got."""
    brave = sequence_damage(270, followup_damage(MEGA_BRAVE, affordable=ML_ATTACKS,
                                                 full_lock=False, same_attack_lock=True), weight=1.0)
    jab = sequence_damage(130, followup_damage(AURA_JAB, affordable=ML_ATTACKS,
                                               full_lock=False, same_attack_lock=False), weight=1.0)
    assert brave == jab == 400


def test_the_full_lock_really_does_cost_a_whole_turn():
    moon = sequence_damage(240, followup_damage(BLOOD_MOON, affordable={BLOOD_MOON: 240, QUICK: 130},
                                                full_lock=True, same_attack_lock=False), weight=1.0)
    chip = sequence_damage(130, followup_damage(QUICK, affordable={BLOOD_MOON: 240, QUICK: 130},
                                                full_lock=False, same_attack_lock=False), weight=1.0)
    assert moon == 240
    assert chip == 370          # 130 now + Blood Moon still available next turn
    assert chip > moon


def test_the_follow_up_is_discounted_so_damage_now_still_wins_a_tie():
    """Damage THIS turn is certain and next turn's is not (they move in between), so at weight < 1
    the front-loaded nuke edges an otherwise equal alternation."""
    brave = sequence_damage(270, 130, weight=0.5)
    jab = sequence_damage(130, 270, weight=0.5)
    assert brave > jab


def test_a_doomed_active_has_no_next_turn_so_the_lock_is_free():
    assert sequence_damage(270, followup=0, weight=0.5) == 270
    assert sequence_damage(240, followup=0, weight=0.5) == 240
