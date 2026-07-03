"""Attack-rider text parsers (ADR-0022 #2/#14): recoil (self-damage) and bench-snipe amounts read
from the free-text `Attack.text`. Both match ONLY the clean UNCONDITIONAL phrasing as a whole
sentence — conditional / variable / spread / own-bench riders parse to 0 (under-credit is the safe
direction). Samples are real card text from `data/EN_Card_Data.csv`.
"""
import pytest

from common.scouting.provider import (
    parse_attack_bench_snipe, parse_attack_bench_spread, parse_attack_hand_size,
    parse_attack_ignores_active_effects, parse_attack_recoil, parse_attack_self_return)


@pytest.mark.req("REQ-GUST-0006")
@pytest.mark.parametrize("text,expected", [
    ("This Pokémon also does 20 damage to itself.", 20),                 # Wiglett Aqua Bomb
    ("This Pokémon also does 50 damage to itself.", 50),                 # Excadrill Wild Tackle
    ("This Pokémon also does 30 damage to itself.", 30),                 # Black Kyurem ex Black Frost
    # conditional / variable / coin-flip recoil -> 0 (decline or can't count it)
    ("You may do 30 more damage. If you do, this Pokémon also does 30 damage to itself.", 0),  # Gurdurr
    ("This Pokémon also does 10 damage to itself for each damage counter on it.", 0),  # Palafin
    ("Flip 2 coins. If both of them are tails, this Pokémon also does 90 damage to itself.", 0),  # Raticate
    ("You may have this Pokémon also do 60 damage to itself and make your opponent's "
     "Active Pokémon Paralyzed.", 0),                                    # Pawmot Voltaic Fist
    ("", 0),
    ("This attack also does 50 damage to 1 of your opponent's Benched Pokémon.", 0),  # not recoil
])
def test_parse_attack_recoil(text, expected):
    assert parse_attack_recoil(text) == expected


@pytest.mark.req("REQ-GUST-0006")
@pytest.mark.parametrize("text,expected", [
    ("Put this Pokémon and all attached cards into your hand.", True),   # Meowth ex Tuck Tail
    ("Put this Pokémon into your hand.", True),                          # bare self-scoop variant
    # not a SELF return -> False (opponent-facing / energy-only / plain)
    ("Put 1 of your opponent's Pokémon and all attached cards into their hand.", False),
    ("Return an Energy attached to this Pokémon to your hand.", False),
    ("This attack does 60 damage.", False),
    ("", False),
])
def test_parse_attack_self_return(text, expected):
    assert parse_attack_self_return(text) is expected


@pytest.mark.req("REQ-GUST-0006")
@pytest.mark.parametrize("text,expected", [
    # Mega Starmie ex Jetting Blow + Farigiraf ex Dirty Beam — clean single-target opponent rider
    ("This attack also does 50 damage to 1 of your opponent's Benched Pokémon. "
     "(Don't apply Weakness and Resistance for Benched Pokémon.)", 50),
    ("This attack also does 30 damage to 1 of your opponent's Benched Pokémon. "
     "(Don't apply Weakness and Resistance for Benched Pokémon.)", 30),
    # spread ("each"), own bench, multi-target, conditional, restricted, no-rider -> 0
    ("This attack also does 40 damage to each Benched Pokémon that has any damage counters on it "
     "(both yours and your opponent's). (Don't apply Weakness and Resistance for Benched Pokémon.)", 0),  # Hippowdon
    ("This attack also does 10 damage to 1 of your Benched Pokémon. "
     "(Don't apply Weakness and Resistance for Benched Pokémon.)", 0),   # Girafarig — OWN bench
    ("Discard 2 Energy from this Pokémon. This attack does 120 damage to 2 of your opponent's "
     "Pokémon. (Don't apply Weakness and Resistance for Benched Pokémon.)", 0),  # Greninja ex — 2 targets
    ("You may shuffle 3 Energy attached to this Pokémon into your deck. If you do, this attack also "
     "does 120 damage to 1 of your opponent's Benched Pokémon. (Don't apply Weakness and Resistance "
     "for Benched Pokémon.)", 0),                                        # Ogerpon — conditional
    ("This attack does 60 damage to 1 of your opponent's Benched Pokémon {ex} or Benched Pokémon {V}. "
     "(Don't apply Weakness and Resistance for Benched Pokémon.)", 0),   # Shaymin — restricted
    ("This attack's damage isn't affected by Weakness or Resistance, or by any effects on your "
     "opponent's Active Pokémon.", 0),                                   # Nebula Beam — no rider
    ("This Pokémon also does 50 damage to itself.", 0),                  # recoil, not a snipe
    ("", 0),
])
def test_parse_attack_bench_snipe(text, expected):
    assert parse_attack_bench_snipe(text) == expected


@pytest.mark.req("REQ-GEN-0050")
@pytest.mark.parametrize("text,expected", [
    # Dragapult ex Phantom Dive — distributable bench spread ("in any way you like") = N*10 total.
    ("Put 6 damage counters on your opponent's Benched Pokémon in any way you like.", 60),
    ("Put 4 damage counters on your opponent's Pokémon in any way you like.", 40),  # non-"Benched" variant
    # single-target snipe / own bench / "each" / restricted / no-spread -> 0 (not distributable)
    ("This attack also does 50 damage to 1 of your opponent's Benched Pokémon. "
     "(Don't apply Weakness and Resistance for Benched Pokémon.)", 0),
    ("Put 2 damage counters on 1 of your opponent's Benched Pokémon.", 0),          # single target, no distribution
    ("Put 3 damage counters on your Benched Pokémon in any way you like.", 0),       # OWN bench
    ("Put 2 damage counters on each of your opponent's Benched Pokémon.", 0),        # forced spread ("each"), not chosen
    ("This attack does 100 damage to 1 of your opponent's Pokémon.", 0),             # Cruel Arrow — not counters
    ("", 0),
])
def test_parse_attack_bench_spread(text, expected):
    assert parse_attack_bench_spread(text) == expected


@pytest.mark.req("REQ-GUST-0006")
@pytest.mark.parametrize("text,expected", [
    # Alakazam (743) Powerful Hand — 2 counters/card = 20 dmg/card (counters ignore Weakness/Resistance)
    ("Place 2 damage counters on your opponent's Active Pokémon for each card in your hand.", 20),
    ("Place 1 damage counter on your opponent's Active Pokémon for each card in your hand.", 10),
    # direct "damage for each card in your hand" -> the printed per-card damage
    ("This attack does 20 damage for each card in your hand.", 20),
    ("This attack does 30 more damage for each card in your hand.", 30),
    # NOT a hand-size attacker: per-Energy / per-counter scaling, or no rider -> 0
    ("This attack does 50 more damage for each Energy attached to your opponent's Active Pokémon.", 0),  # Alakazam(245)
    ("Place 2 damage counters on your opponent's Active Pokémon for each Energy attached to it.", 0),
    ("This Pokémon also does 50 damage to itself.", 0),                  # recoil, not a hand-size rider
    ("", 0),
])
def test_parse_attack_hand_size(text, expected):
    assert parse_attack_hand_size(text) == expected


@pytest.mark.req("REQ-LETHAL-0012")
@pytest.mark.parametrize("text,expected", [
    # Mega Starmie ex Nebula Beam — bypasses effects on opp's Active (Crustle's prevent Ability)
    ("This attack's damage isn't affected by Weakness or Resistance, or by any effects on your "
     "opponent's Active Pokémon.", True),
    # Crustle Superb Scissors — shorter phrasing, same clause
    ("This attack's damage isn't affected by any effects on your opponent's Active Pokémon.", True),
    # NOT the clause: Weakness/Resistance only, bench-snipe, recoil, no rider -> False (Ability still walls it)
    ("This attack's damage isn't affected by Weakness or Resistance.", False),      # W/R only, not effects
    ("This attack also does 50 damage to 1 of your opponent's Benched Pokémon.", False),  # Jetting Blow
    ("This Pokémon also does 50 damage to itself.", False),                         # recoil
    ("", False),
])
def test_parse_attack_ignores_active_effects(text, expected):
    assert parse_attack_ignores_active_effects(text) == expected
