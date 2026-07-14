"""Energy-denial oracle (ADR-0062) — what a Crushing Hammer actually takes away.

  Crushing Hammer (1120, Item): "Flip a coin. If heads, discard an Energy from 1 of your
                                 opponent's Pokemon."          <- ANY Pokemon, Active OR Bench
  Enhanced Hammer  (1081, Item): "Discard a Special Energy from 1 of your opponent's Pokemon."

Stripping one Energy is worth exactly what it stops them doing: the damage their best AFFORDABLE
attack loses. Mega Lucario ex is the clean worked example (costs verified at EN_Card_Data.csv):

    Aura Jab   {F}    -> 130
    Mega Brave {F}{F} -> 270

    2 Energy: best 270 -> strip one -> best 130   ... denies 140   (turns the nuke off)
    1 Energy: best 130 -> strip one -> best   0   ... denies 130   (turns it off entirely)
    3 Energy: best 270 -> strip one -> best 270   ... denies   0   (SURPLUS -- the Hammer is wasted)

That last row is the whole point. The shipped rung fired whenever the opponent's Active merely
CARRIED Energy, so it burned Hammers on bodies holding more than they needed.
"""
from common.strategy.denial import best_affordable_damage, denial_value

# {attack_id: (energy cost, damage)}
MEGA_LUCARIO = {1: (1, 130), 2: (2, 270)}          # Aura Jab / Mega Brave
SOLROCK = {3: (1, 70)}                              # Cosmic Beam {F} -> 70
UNAFFORDABLE = {4: (3, 200)}                        # a 3-cost attack


def test_best_affordable_damage_is_energy_gated():
    assert best_affordable_damage(0, MEGA_LUCARIO) == 0
    assert best_affordable_damage(1, MEGA_LUCARIO) == 130     # only Aura Jab is payable
    assert best_affordable_damage(2, MEGA_LUCARIO) == 270     # Mega Brave comes online
    assert best_affordable_damage(9, MEGA_LUCARIO) == 270     # ... and caps there


def test_stripping_the_second_energy_turns_the_nuke_off():
    """Exactly 2 Energy on a Mega Lucario ex: one Hammer drops it from Mega Brave to Aura Jab."""
    assert denial_value(2, MEGA_LUCARIO) == 140               # 270 -> 130


def test_stripping_the_last_energy_turns_the_attacker_off_entirely():
    assert denial_value(1, MEGA_LUCARIO) == 130               # 130 -> 0
    assert denial_value(1, SOLROCK) == 70                     # 70 -> 0


def test_stripping_SURPLUS_energy_denies_nothing_and_the_hammer_is_wasted():
    """THE defect. A body carrying more Energy than its dearest attack costs loses NOTHING to a
    Hammer -- yet `play-energy-denial` fired on it, because it asked only whether Energy was
    present."""
    assert denial_value(3, MEGA_LUCARIO) == 0                 # 270 -> 270
    assert denial_value(4, MEGA_LUCARIO) == 0
    assert denial_value(2, SOLROCK) == 0                      # 70 -> 70


def test_a_body_that_cannot_pay_any_attack_denies_nothing():
    """Energy present, but not enough to reach ANY attack -- there is no damage to take away.
    (dragapult f6: a Kyogre whose attack is unaffordable off an empty discard.)"""
    assert denial_value(1, UNAFFORDABLE) == 0                 # 0 -> 0, it could not attack anyway
    assert denial_value(2, UNAFFORDABLE) == 0


def test_a_body_with_no_attacks_at_all_denies_nothing():
    assert denial_value(3, {}) == 0


def test_denial_never_goes_negative():
    """Removing Energy can only ever reduce what they can pay for."""
    for e in range(0, 6):
        assert denial_value(e, MEGA_LUCARIO) >= 0
