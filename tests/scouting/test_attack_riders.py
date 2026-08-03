"""Attack-rider text parsers (ADR-0022 #2/#14): recoil (self-damage) and bench-snipe amounts read
from the free-text `Attack.text`. Both match ONLY the clean UNCONDITIONAL phrasing as a whole
sentence — conditional / variable / spread / own-bench riders parse to 0 (under-credit is the safe
direction). Samples are real card text from `data/EN_Card_Data.csv`.
"""
import pytest

from common.scouting.provider import (
    parse_attack_bench_snipe, parse_attack_bench_spread,
    parse_attack_ignores_active_effects, parse_attack_recoil, parse_attack_scaling,
    parse_attack_self_return)


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
def test_hand_size_damage_comes_from_the_one_scaling_parse(text, expected):
    # Issue #213: the dedicated hand-size regex pair is retired. The Damage Formula's scaling
    # term is now the single parse of this sentence, and `AttackStat.handSizeDamage` derives from
    # it — so the two can no longer disagree, and an engine-fitted `atk_hand` override moves both.
    scale = parse_attack_scaling(text)
    assert (scale[1] if scale and scale[0] == "atk_hand" else 0) == expected


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


@pytest.mark.req("REQ-ACCEL-0001")
@pytest.mark.parametrize("text,expected", [
    # DISCARD-source family (the recover riders) — unchanged, now with source="discard".
    ("Attach up to 3 Basic {F} Energy cards from your discard pile to your Benched Pokémon in any "
     "way you like.", (3, 6, "bench", "discard")),                       # Aura Jab
    ("Attach a Basic {W} Energy card from your discard pile to this Pokémon.",
     (1, 3, "self", "discard")),                                         # Regi Charge shape
    # DECK-source family (the search-attach accel — NEW): Turbo Flare, Kaguras, Energy Gift.
    ("Search your deck for up to 3 Basic Energy cards and attach them to your Benched Pokémon in "
     "any way you like. Then, shuffle your deck.", (3, None, "bench", "deck")),   # Turbo Flare
    ("Search your deck for a Basic {F} Energy card and attach it to 1 of your Pokémon. Then, "
     "shuffle your deck.", (1, 6, "any", "deck")),                       # Rock Kagura
    ("Search your deck for a Basic {M} Energy card and attach it to this Pokémon. Then, shuffle "
     "your deck.", (1, 8, "self", "deck")),                              # Steel Armament
    # Deliberately UNPARSED (an endorser under-counts, never over-credits):
    ("Flip 3 coins. For each heads, search your deck for up to 2 Basic Energy cards and attach "
     "them to your Pokémon in any way you like. Then, shuffle your deck.", None),  # coin-gated
    ("Search your deck for up to 2 Basic Energy cards and attach them to your Future Pokémon in "
     "any way you like. Then, shuffle your deck.", None),                # scope-locked target
    ("Search your deck for up to 2 Basic {G} Energy cards and up to 2 Basic {L} Energy cards and "
     "attach them to your Pokémon in any way you like. Then, shuffle your deck.", None),  # twin clause
    ("Search your deck for a Basic Energy card, reveal it, and put it into your hand. Then, "
     "shuffle your deck.", None),                                        # to HAND, not an attach
    ("", None),
])
def test_parse_attack_energy_recover_both_zones(text, expected):
    from common.scouting.card_text import parse_attack_energy_recover
    assert parse_attack_energy_recover(text) == expected


# ---- WHICH record a bench-reach consumer must read (Issue #284) -----------------------------------


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_the_bench_reach_instrument_is_the_ATTACK_record_and_not_the_card_summary():
    """`CardStat.benchSnipeDamage` and `AttackStat.benchSnipe` are NOT two names for one fact, and a
    consumer that picks the wrong one is inert on most of the pool's bench routes.

    `_build_cache` fills the card-level field from `parse_attack_bench_snipe` **alone**, while
    `build_attack_stats` fills the attack-level one from that parser **or** the `free_target_snipe`
    branch — the *"does N damage to 1 of your opponent's Pokémon"* form, which can hit any body
    including a benched one. Everything printed that way therefore has a `benchSnipe` and a
    `benchSnipeDamage` of 0. The card summary also predates the audit-override pass, so an override
    would move one and not the other.

    Measured over the whole pool (1556 attack records, 1061 cards) rather than argued: of the pool's
    bench-snipe attacks, only the *"Benched Pokémon"* phrasings reach the card field, and the two
    routes that carry `dragapult_ex` and `slowking` — Fezandipiti ex's Cruel Arrow and Kyurem's
    Trifrost — are not among them. `state_value._reachable_target_values` reads the ATTACK record
    through `CombatMath.rider_snipe`, and this is why."""
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()

    # Verified at `data/EN_Card_Data.csv`: Mega Starmie ex (1031) Jetting Blow — "This attack also
    # does 50 damage to 1 of your opponent's Benched Pokémon." The phrasing BOTH records read, and
    # the positive control that proves this instrument is not simply returning zeros.
    starmie = stats.get(1031)
    assert starmie.benchSnipeDamage == 50
    assert max(stats.attack(aid).benchSnipe for aid in starmie.attacks) == 50

    # Fezandipiti ex (140) Cruel Arrow — "This attack does 100 damage to 1 of your opponent's
    # Pokémon." — and Kyurem (144) Trifrost — "…110 damage to 3 of your opponent's Pokémon."
    # Both print zero damage, so the free-target branch is the only thing that sees them.
    for cid, rider in ((140, 100), (144, 110)):
        card = stats.get(cid)
        assert card.benchSnipeDamage == 0, f"{card.name}: the CARD summary misses this route"
        assert max(stats.attack(aid).benchSnipe for aid in card.attacks) == rider

    # And the fail-closed doctrine still holds where it should: Zeraora (377) Thunder Raid is
    # restricted to a benched Pokémon {ex} ("…210 damage to 1 of your opponent's Benched Pokémon
    # {ex}"), which `parse_attack_bench_snipe` declines by design, so NEITHER record claims it.
    zeraora = stats.get(377)
    assert zeraora.benchSnipeDamage == 0
    assert max(stats.attack(aid).benchSnipe for aid in zeraora.attacks) == 0


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_no_attack_in_the_pool_prints_both_a_bench_SNIPE_and_a_bench_SPREAD():
    """The sweep behind `CombatMath.best_reachable_bench_damage`'s decision to read the snipe rider
    alone (Issue #284).

    `_bench_rider` SUMS the two as a worst case for a body of mine; an outgoing read cannot, because
    a spread is one shared counter budget across their whole Bench. The split costs nothing on this
    set only if no attack carries both — asserted here, with the two inventories printed alongside so
    a later set that breaks the premise fails loudly rather than silently over-reading.

    Both inventories are non-empty, which is the positive control: a sweep that had stopped seeing
    riders at all would report the same empty intersection."""
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    # The provider exposes `attack(aid)` but no iteration over the table, so a POOL sweep has to
    # reach for the cache — the same way `test_tool_holder_facts.py` reaches for `stats._cache` to
    # pin its card-level inventories. A private reach in a test, and the alternative is no sweep.
    table = stats._attack_stats

    snipes = {aid for aid, a in table.items() if a.benchSnipe}
    spreads = {aid for aid, a in table.items() if a.benchSpread}
    assert snipes and spreads, "the instrument reads nothing — a broken sweep, not a clean pool"
    assert not (snipes & spreads), sorted(snipes & spreads)

    # The three spread attacks the bench leg deliberately does not read, by amount:
    assert sorted(table[aid].benchSpread for aid in spreads) == [20, 40, 60]
