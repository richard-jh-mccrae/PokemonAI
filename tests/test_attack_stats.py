"""AttackStat — the attack-keyed effect record (ADR-0032). `parse_attack_ignores` reads the
"isn't affected by …" damage-modifier phrases off `Attack.text` (the 27-attack ignore family:
Nebula Beam, Shred, Telekinesis, Rock Hurl, …); `build_attack_stats` folds them with the existing
rider parsers into one `{attackId: AttackStat}` table. Samples are real engine text.

Requirements: REQ-DMG-0001 (ignore-phrase parse, damage-scoped only), REQ-DMG-0002 (AttackStat
build folds damage/cost/riders/flags), REQ-DMG-0003 (hand-authored overrides beat parsed values).
"""
import pytest

from common.scouting.provider import (
    AttackStat, build_attack_stats, parse_attack_damage_bounds, parse_attack_ignores,
    parse_attack_scaling, parse_card_defense)


@pytest.mark.req("REQ-DMG-0001")
@pytest.mark.parametrize("text,expected", [
    # Nebula Beam (1488) / Demolish — full triple: Weakness + Resistance + effects
    ("This attack's damage isn't affected by Weakness or Resistance, or by any effects on your "
     "opponent's Active Pokémon.", (True, True, True)),
    # Shred / Sonic Edge / Superb Scissors / Spiky Hopper — effects only
    ("This attack's damage isn't affected by any effects on your opponent's Active Pokémon.",
     (False, False, True)),
    # Sigilyph Telekinesis / Sawk Rising Chop — Weakness + Resistance
    ("This attack does 70 damage to 1 of your opponent's Pokémon. This attack's damage isn't "
     "affected by Weakness or Resistance.", (True, True, False)),
    # Iron Crown ex Twin Shotels — snipe variant: "effects on those Pokémon"
    ("This attack does 50 damage to 2 of your opponent's Pokémon. This attack's damage isn't "
     "affected by Weakness or Resistance, or by any effects on those Pokémon.", (True, True, True)),
    # Sandy Shocks Magnetic Burst — Weakness only
    ("If you have 3 or more Energy in play, this attack does 70 more damage. This attack's damage "
     "isn't affected by Weakness.", (True, False, False)),
    # Cynthia's Gible / Naclstack / Landorus Rock Tumble — Resistance only
    ("This attack's damage isn't affected by Resistance.", (False, True, False)),
    # Conkeldurr Gutsy Swing — ignores Energy COST not damage -> no damage flag
    ("If this Pokémon is affected by a Special Condition, ignore all Energy in this attack's cost.",
     (False, False, False)),
    # no ignore phrasing
    ("This attack also does 50 damage to 1 of your opponent's Benched Pokémon.", (False, False, False)),
    ("", (False, False, False)),
])
def test_parse_attack_ignores(text, expected):
    assert parse_attack_ignores(text) == expected


class _Attack:
    """Minimal engine-Attack stand-in (attackId / damage / energies / text)."""

    def __init__(self, attack_id, damage=0, cost=0, text=""):
        self.attackId = attack_id
        self.damage = damage
        self.energies = [1] * cost
        self.text = text


@pytest.mark.req("REQ-DMG-0002")
def test_build_attack_stats_folds_damage_cost_riders_and_flags():
    attacks = [
        _Attack(1487, 120, 1, "This attack also does 50 damage to 1 of your opponent's Benched "
                              "Pokémon. (Don't apply Weakness and Resistance for Benched Pokémon.)"),
        _Attack(1488, 210, 3, "This attack's damage isn't affected by Weakness or Resistance, or "
                              "by any effects on your opponent's Active Pokémon."),
        _Attack(7, 90, 2, "This Pokémon also does 30 damage to itself."),
        _Attack(1072, 0, 1, "Place 2 damage counters on your opponent's Active Pokémon for each "
                            "card in your hand."),
    ]
    stats = build_attack_stats(attacks)
    jetting, nebula, recoiler, powerful = stats[1487], stats[1488], stats[7], stats[1072]
    assert isinstance(nebula, AttackStat)
    # Jetting Blow: plain damage + bench rider, no ignore flags
    assert (jetting.damage, jetting.cost, jetting.benchSnipe) == (120, 1, 50)
    assert (jetting.ignoresWeakness, jetting.ignoresResistance, jetting.ignoresEffects) == (False, False, False)
    # Nebula Beam: full ignore triple
    assert (nebula.damage, nebula.cost) == (210, 3)
    assert (nebula.ignoresWeakness, nebula.ignoresResistance, nebula.ignoresEffects) == (True, True, True)
    # riders fold in via existing parsers
    assert recoiler.recoil == 30
    assert powerful.handSizeDamage == 20


@pytest.mark.req("REQ-DMG-0002")
def test_build_attack_stats_tolerates_missing_text():
    stats = build_attack_stats([_Attack(5, 40, 1, None)])
    assert stats[5].damage == 40 and stats[5].ignoresEffects is False


@pytest.mark.req("REQ-DMG-0007")
@pytest.mark.parametrize("text,printed,expected", [
    # Best Punch (142) — "If tails, does nothing": sound floor is 0
    ("Flip a coin. If tails, this attack does nothing.", 40, (0, 40)),
    # Cosmic Beam (980) / Sawk — a NON-coin does-nothing condition floors to 0 too
    ("If you don't have Lunatone on your Bench, this attack does nothing. This attack's damage "
     "isn't affected by Weakness or Resistance.", 70, (0, 70)),
    # Tumbling Attack (114) — heads bonus: floor = printed, ceiling = printed + N
    ("Flip a coin. If heads, this attack does 20 more damage.", 10, (10, 30)),
    # Superpower (144) — optional bonus: declining keeps printed; ceiling includes it
    ("You may do 30 more damage. If you do, this Pokémon also does 30 damage to itself.", 50, (50, 80)),
    # deterministic attacks carry NO bounds (None -> printed damage is exact)
    ("This attack also does 50 damage to 1 of your opponent's Benched Pokémon.", 120, None),
    ("", 210, None),
])
def test_parse_attack_damage_bounds(text, printed, expected):
    assert parse_attack_damage_bounds(text, printed) == expected


@pytest.mark.req("REQ-DMG-0007")
def test_build_folds_damage_bounds():
    stats = build_attack_stats([
        _Attack(142, 40, 2, "Flip a coin. If tails, this attack does nothing."),
        _Attack(1488, 210, 3, "This attack's damage isn't affected by Weakness or Resistance, or "
                              "by any effects on your opponent's Active Pokémon."),
    ])
    assert (stats[142].damageMin, stats[142].damageMax) == (0, 40)
    assert (stats[1488].damageMin, stats[1488].damageMax) == (None, None)   # deterministic


@pytest.mark.req("REQ-DMG-0009")
@pytest.mark.parametrize("text,expected", [
    # Mind Ruler (123) — damage per card in OPPONENT's hand
    ("This attack does 30 damage for each card in your opponent's hand.",
     ("def_hand", 30, False, None)),
    # Psychic (339) — bonus damage per Energy on opponent's Active
    ("This attack does 50 more damage for each Energy attached to your opponent's Active Pokémon.",
     ("def_active_energy", 50, False, None)),
    # own-Energy family (13 attacks) — per Energy attached to THIS Pokémon
    ("This attack does 40 damage for each Energy attached to this Pokémon.",
     ("atk_active_energy", 40, False, None)),
    # Powerful Hand (1072) — COUNTERS per card in MY hand: counters bypass W/R AND prevention
    ("Place 2 damage counters on your opponent's Active Pokémon for each card in your hand.",
     ("atk_hand", 20, True, None)),
    # Riptide (1042) — per Basic {W} Energy in ATTACKER's discard (visible for BOTH players)
    ("This attack does 20 damage for each Basic {W} Energy card in your discard pile. Then, "
     "shuffle those cards into your deck.", ("atk_discard_energy", 20, False, 3)),
    # 446 — per ANY Energy card in attacker's discard (no type filter)
    ("This attack does 20 more damage for each Energy card in your discard pile.",
     ("atk_discard_energy", 20, False, None)),
    # 15 — COUNTERS per Basic {G} Energy in attacker's discard
    ("Put 2 damage counters on 1 of your opponent's Pokémon for each Basic {G} Energy card in "
     "your discard pile. Then, shuffle those Energy cards into your deck.",
     ("atk_discard_energy", 20, True, 1)),
    # not scalers
    ("This attack also does 50 damage to 1 of your opponent's Benched Pokémon.", None),
    ("", None),
])
def test_parse_attack_scaling(text, expected):
    assert parse_attack_scaling(text) == expected


@pytest.mark.req("REQ-DMG-0009")
def test_build_folds_scaling_and_counter_scalers_get_ignore_flags():
    stats = build_attack_stats([
        _Attack(123, 0, 3, "This attack does 30 damage for each card in your opponent's hand."),
        _Attack(1072, 0, 1, "Place 2 damage counters on your opponent's Active Pokémon for each "
                            "card in your hand."),
    ])
    assert (stats[123].scaleVar, stats[123].scalePerUnit) == ("def_hand", 30)
    assert stats[123].ignoresWeakness is False                  # damage-type scaling: W/R apply
    assert (stats[1072].scaleVar, stats[1072].scalePerUnit) == ("atk_hand", 20)
    # counters aren't damage: bypass Weakness, Resistance AND damage-prevention effects
    assert (stats[1072].ignoresWeakness, stats[1072].ignoresResistance,
            stats[1072].ignoresEffects) == (True, True, True)


@pytest.mark.req("REQ-DMG-0010")
@pytest.mark.parametrize("text,expected", [
    # Crustle 345 / Sylveon 330 — Sylveon carries NO prevent_ex_damage tag: parsed field
    # closes that gap
    ("Prevent all damage done to this Pokémon by attacks from your opponent's Pokémon {ex}.",
     ("ex", 0, 0, None)),
    # Farigiraf ex 83 — narrower Basic-ex variant
    ("Prevent all damage done to this Pokémon by attacks from your opponent's Basic Pokémon {ex}.",
     ("basic_ex", 0, 0, None)),
    # Drednaw 158 — threshold prevention
    ("Prevent all damage done to this Pokémon by attacks from your opponent's Pokémon if that "
     "damage is 200 or more.", (None, 200, 0, None)),
    # Mudsdale 383 / Bouffalant ex 631 / Mega Diancie ex 766 — flat reduction after W/R
    ("This Pokémon takes 30 less damage from attacks (after applying Weakness and Resistance).",
     (None, 0, 30, None)),
    # effects-not-damage prevention is damage-irrelevant
    ("Prevent all effects of attacks used by your opponent's Pokémon done to this Pokémon. "
     "(Damage is not an effect.)", (None, 0, 0, None)),
    ("", (None, 0, 0, None)),
])
def test_parse_card_defense(text, expected):
    class _Card:
        skills = [type("S", (), {"text": text})()]
    assert parse_card_defense(_Card()) == expected


@pytest.mark.req("REQ-DMG-0011")
def test_parse_hidden_deck_discard_scalers():
    from common.scouting.provider import parse_attack_hidden_scale
    # Mega Abomasnow ex Hammer-lanche (1046): top 6 of MY deck, 100 per Basic {W} discarded —
    # {W} filter lets exact deck facts compute a pigeonhole floor / EV
    assert parse_attack_hidden_scale(
        "Discard the top 6 cards of your deck, and this attack does 100 damage for each Basic {W} "
        "Energy card that you discarded in this way.") == (100, 6, 3)
    # Misty's Lapras (501): top 7, 70 per Misty's Pokémon (no Energy filter)
    assert parse_attack_hidden_scale(
        "Discard the top 7 cards of your deck, and this attack does 70 damage for each Misty's "
        "Pokémon that you discarded in this way.") == (70, 7, None)
    # Ground Burn (18): top card of EACH deck, 140 per Energy discarded (2 cards sampled)
    assert parse_attack_hidden_scale(
        "Discard the top card of each player's deck. This attack does 140 more damage for each "
        "Energy card discarded in this way.") == (140, 2, None)
    assert parse_attack_hidden_scale("This attack also does 50 damage to 1 of your opponent's "
                                     "Benched Pokémon.") is None
    assert parse_attack_hidden_scale("") is None


@pytest.mark.req("REQ-DMG-0011")
def test_build_folds_hidden_scale():
    stats = build_attack_stats([
        _Attack(1046, 0, 2, "Discard the top 6 cards of your deck, and this attack does 100 damage "
                            "for each Basic {W} Energy card that you discarded in this way."),
    ])
    assert (stats[1046].hiddenPerUnit, stats[1046].hiddenSample) == (100, 6)


@pytest.mark.req("REQ-DMG-0012")
def test_parse_effect_damage_family():
    from common.scouting.provider import parse_attack_effect_damage
    # chosen-target fixed effect damage: printed 0, text carries the number
    assert parse_attack_effect_damage(
        "This attack does 100 damage to 1 of your opponent's Pokémon. (Don't apply Weakness and "
        "Resistance for Benched Pokémon.)") == (100, False)
    assert parse_attack_effect_damage(
        "Discard 2 Energy from this Pokémon. This attack does 120 damage to 2 of your opponent's "
        "Pokémon. (Don't apply Weakness and Resistance for Benched Pokémon.)") == (120, False)
    # counter-puts are counters (x10, bypass W/R/prevention)
    assert parse_attack_effect_damage(
        "Put 4 damage counters on your opponent's Pokémon in any way you like.") == (40, True)
    assert parse_attack_effect_damage(
        "Put 2 damage counters on each of your opponent's Pokémon.") == (20, True)
    # NOT this family: bench-only riders, defender-conditional targets, plain attacks
    assert parse_attack_effect_damage(
        "This attack also does 50 damage to 1 of your opponent's Benched Pokémon.") is None
    assert parse_attack_effect_damage(
        "This attack does 100 damage to each of your opponent's Pokémon {ex} and Pokémon {V}.") is None
    assert parse_attack_effect_damage("") is None


@pytest.mark.req("REQ-DMG-0012")
def test_build_applies_effect_damage_only_to_printed_zero():
    stats = build_attack_stats([
        _Attack(183, 0, 2, "This attack does 100 damage to 1 of your opponent's Pokémon. (Don't "
                           "apply Weakness and Resistance for Benched Pokémon.)"),
        _Attack(342, 0, 1, "Put 2 damage counters on 1 of your opponent's Pokémon."),
        _Attack(1487, 120, 1, "This attack also does 50 damage to 1 of your opponent's Benched "
                              "Pokémon. (Don't apply Weakness and Resistance for Benched Pokémon.)"),
    ])
    assert stats[183].damage == 100
    assert (stats[342].damage, stats[342].ignoresWeakness, stats[342].ignoresEffects) == (20, True, True)
    assert stats[1487].damage == 120 and stats[1487].benchSnipe == 50   # rider untouched


@pytest.mark.req("REQ-DMG-0013")
@pytest.mark.parametrize("text,printed,expected", [
    # generic conditional bonus (19 residual attacks): ceiling includes it, floor keeps printed
    ("If your opponent's Active Pokémon is a Pokémon {ex} or Pokémon {V}, this attack does 110 "
     "more damage.", 110, (110, 220)),
    # optional pay-for-bonus (Raichu-class): "to have this attack do N more damage"
    ("You may put all Energy attached to this Pokémon into your hand to have this attack do 80 "
     "more damage.", 80, (80, 160)),
    # for-each bonus is a SCALER not a flat bonus — must not parse as bounds
    ("This attack does 30 more damage for each card in your opponent's hand.", 0, None),
])
def test_generic_bonus_bounds(text, printed, expected):
    assert parse_attack_damage_bounds(text, printed) == expected


@pytest.mark.req("REQ-DMG-0014")
def test_bench_count_scalers():
    assert parse_attack_scaling(
        "This attack does 30 damage for each of your Benched Pokémon.") == (
        "atk_bench", 30, False, None)
    assert parse_attack_scaling(
        "This attack does 50 more damage for each of your opponent's Benched Pokémon.") == (
        "def_bench", 50, False, None)


@pytest.mark.req("REQ-DMG-0019")
def test_counter_and_prize_scalers_parse():
    assert parse_attack_scaling(
        "This attack does 10 more damage for each damage counter on this Pokémon.") == (
        "atk_self_counters", 10, False, None)
    assert parse_attack_scaling(
        "This attack does 20 damage for each damage counter on your opponent's Active Pokémon.") == (
        "def_counters", 20, False, None)
    assert parse_attack_scaling(
        "This attack does 30 more damage for each Prize card your opponent has taken.") == (
        "def_prizes_taken", 30, False, None)


@pytest.mark.req("REQ-DMG-0017")
def test_build_folds_discard_scaler_type():
    stats = build_attack_stats([
        _Attack(1042, 0, 1, "This attack does 20 damage for each Basic {W} Energy card in your "
                            "discard pile. Then, shuffle those cards into your deck."),
    ])
    assert (stats[1042].scaleVar, stats[1042].scalePerUnit, stats[1042].scaleEnergyType) == (
        "atk_discard_energy", 20, 3)


@pytest.mark.req("REQ-DMG-0015")
def test_dewgong_type_conditional_reduction():
    class _Card:
        skills = [type("S", (), {"text": "This Pokémon takes 30 less damage from attacks from your "
                                         "opponent's {R} or {W} Pokémon (after applying Weakness "
                                         "and Resistance)."})()]
    prevents, threshold, reduction, types = parse_card_defense(_Card())
    assert (prevents, threshold, reduction) == (None, 0, 30)
    assert types == (2, 3)                              # {R}=FIRE, {W}=WATER (EnergyType enum)


@pytest.mark.req("REQ-TRANS-0001")
def test_parse_attack_transients():
    from common.scouting.provider import parse_attack_transients
    # Frost Barrier (1047): defender-side -30 during the opponent's next turn
    assert parse_attack_transients(
        "During your opponent's next turn, this Pokémon takes 30 less damage from attacks (after "
        "applying Weakness and Resistance).", "Frost Barrier") == {"reduction": 30}
    # prevent-all family (6)
    assert parse_attack_transients(
        "During your opponent's next turn, prevent all damage done to this Pokémon by attacks.",
        "Wall") == {"prevent_all": True}
    # self-lock ALL attacks (23)
    assert parse_attack_transients(
        "During your next turn, this Pokémon can't attack.", "Big Swing") == {"self_lock": True}
    assert parse_attack_transients(
        "During your next turn, this Pokémon can't use attacks.", "Slam") == {"self_lock": True}
    # self-referential named lock (18): the named attack IS this attack
    assert parse_attack_transients(
        "During your next turn, this Pokémon can't use Giant Wave.", "Giant Wave") == {"same_lock": True}
    # a DIFFERENT named attack -> not representable, ledger (no field)
    assert parse_attack_transients(
        "During your next turn, this Pokémon can't use Giant Wave.", "Other Move") == {}
    # self next-turn bonus (their incoming rises)
    assert parse_attack_transients(
        "During your next turn, this Pokémon's Big Beam attack does 120 more damage.",
        "Big Beam") == {"self_bonus": 120}
    # defender retreat-lock (22): tracked for Board signals
    assert parse_attack_transients(
        "During your opponent's next turn, the Defending Pokémon can't retreat.",
        "Bind") == {"retreat_lock": True}
    # coin-gated transients NOT tracked (can't know the flip): ledger
    assert parse_attack_transients(
        "Flip a coin. If heads, during your opponent's next turn, prevent all damage done to this "
        "Pokémon by attacks.", "Gamble") == {}
    assert parse_attack_transients("", "X") == {}


@pytest.mark.req("REQ-TRANS-0001")
def test_build_folds_transients():
    stats = build_attack_stats([
        _Attack(1047, 200, 3, "During your opponent's next turn, this Pokémon takes 30 less damage "
                              "from attacks (after applying Weakness and Resistance)."),
    ])
    assert stats[1047].nextTurnReduction == 30 and stats[1047].nextTurnPreventAll is False


@pytest.mark.req("REQ-DMG-0003")
def test_overrides_beat_parsed_values():
    # audit / a human corrects a parse miss: override wins, untouched fields survive
    attacks = [_Attack(70, 130, 3, "This attack's damage isn't affected by any effects on your "
                                   "opponent's Active Pokémon.")]
    stats = build_attack_stats(attacks, overrides={70: {"ignoresEffects": False, "recoil": 20},
                                                   999: {"damage": 50}})   # unknown id ignored
    assert stats[70].ignoresEffects is False          # override beats parsed True
    assert stats[70].recoil == 20                     # override sets field text lacked
    assert stats[70].damage == 130                    # untouched fields survive
    assert 999 not in stats                           # overrides never invent attacks
