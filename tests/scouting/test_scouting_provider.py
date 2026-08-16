"""Card-stat providers (docs/scouting.md). The engine transform is tested lib-free."""
from types import SimpleNamespace

import pytest

from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider, _build_cache


# --- the attack-record half of the Stat Provider seam (ADR-0051) ------------------------

@pytest.mark.req("REQ-STAT-0002")
def test_dict_provider_serves_injected_attack_records_or_none():
    p = DictCardStatProvider({}, attacks={10: AttackStat(10, damage=120, cost=1)})
    assert p.attack(10).damage == 120
    assert p.attack(999) is None
    assert DictCardStatProvider({}).attack(10) is None    # no attack table injected


@pytest.mark.req("REQ-STAT-0002")
def test_dict_provider_warm_is_a_safe_no_op():
    # warm() is the pregame-window build hook; every adapter must accept the call.
    DictCardStatProvider({}).warm()


@pytest.mark.req("REQ-STAT-0002")
def test_engine_provider_serves_attack_records_with_the_audited_facts():
    # Nebula Beam (1488) is the full-ignore triple — it pierces Crustle's ex-damage immunity.
    pytest.importorskip("cg")
    from common.scouting.provider import EngineCardStatProvider
    p = EngineCardStatProvider()
    nebula = p.attack(1488)               # first call ever — must self-build (lazy guard)
    assert (nebula.ignoresWeakness, nebula.ignoresResistance, nebula.ignoresEffects) \
        == (True, True, True)
    assert p.attack(-1) is None           # unknown attack id -> None, never a crash
    assert p.get(333).name == "Riolu"     # cache shared with the card half


@pytest.mark.req("REQ-STAT-0002")
def test_engine_provider_warm_prebuilds_and_is_idempotent():
    pytest.importorskip("cg")
    from common.scouting.provider import EngineCardStatProvider
    p = EngineCardStatProvider()
    p.warm()
    p.warm()                              # idempotent — second call must not rebuild/crash
    assert p.attack(1488) is not None


@pytest.mark.req("REQ-SCOUT-0008")
def test_dict_provider_returns_stats_or_none():
    p = DictCardStatProvider({1: CardStat(1, synthetic=True, name="x", hp=70)})
    assert p.get(1).hp == 70
    assert p.get(999) is None


@pytest.mark.req("REQ-POSTURE-0005")
def test_ids_for_name_reverse_lookups_card_ids_by_name():
    # The Matchup Brief consumer resolves card NAMES -> ids; the provider is the reverse index.
    p = DictCardStatProvider({677: CardStat(677, name="Riolu"),
                              678: CardStat(678, name="Mega Lucario ex"),
                              679: CardStat(679, synthetic=True, name="Riolu")})   # a reprint under the same name
    assert p.ids_for_name("Riolu") == frozenset({677, 679})
    assert p.ids_for_name("Mega Lucario ex") == frozenset({678})
    assert p.ids_for_name("Nonexistent") == frozenset()


@pytest.mark.req("REQ-GEN-0022")
def test_forward_max_damage_reaches_the_evolution_lines_attacker():
    # The damage the LINE eventually reaches, read off the pre-evolution (ADR-0020).
    stats = DictCardStatProvider({
        333: CardStat(333, name="Riolu", maxDamage=10),
        678: CardStat(678, name="Mega Lucario ex", maxDamage=270, evolvesFrom="Riolu"),
    })
    assert stats.forward_max_damage(333) == 270


@pytest.mark.req("REQ-GEN-0022")
def test_forward_max_damage_is_zero_for_dead_ends_and_final_forms():
    stats = DictCardStatProvider({
        333: CardStat(333, name="Riolu", maxDamage=10),
        678: CardStat(678, name="Mega Lucario ex", maxDamage=270, evolvesFrom="Riolu"),
        500: CardStat(500, synthetic=True, name="Sunkern", maxDamage=20),          # bare basic, evolves into nothing
    })
    assert stats.forward_max_damage(678) == 0     # final form: descendants only, NOT its own 270
    assert stats.forward_max_damage(500) == 0     # dead-end basic
    assert stats.forward_max_damage(999) == 0     # unknown id -> fail closed


@pytest.mark.req("REQ-GEN-0022")
def test_forward_max_damage_folds_max_over_same_name_printings():
    stats = DictCardStatProvider({
        333: CardStat(333, name="Riolu", maxDamage=10),
        974: CardStat(974, name="Riolu", maxDamage=30),            # second Riolu printing
        678: CardStat(678, synthetic=True, name='Mega Lucario ex', maxDamage=130, evolvesFrom="Riolu"),
        679: CardStat(679, synthetic=True, name="Mega Lucario ex", maxDamage=270, evolvesFrom="Riolu"),  # bigger print
    })
    assert stats.forward_max_damage(333) == 270   # folds 130/270 printings -> 270
    assert stats.forward_max_damage(974) == 270   # any printing of pre-evo resolves the same


@pytest.mark.req("REQ-GEN-0022")
def test_forward_max_damage_walks_branching_multihop_and_survives_cycles():
    stats = DictCardStatProvider({
        1: CardStat(1, synthetic=True, name="Wurmple", maxDamage=10),
        2: CardStat(2, synthetic=True, name="Silcoon", maxDamage=20, evolvesFrom="Wurmple"),
        3: CardStat(3, synthetic=True, name="Beautifly", maxDamage=90, evolvesFrom="Silcoon"),
        4: CardStat(4, synthetic=True, name="Cascoon", maxDamage=20, evolvesFrom="Wurmple"),
        5: CardStat(5, synthetic=True, name="Dustox", maxDamage=160, evolvesFrom="Cascoon"),  # max across all branches
        # malformed self-cycle must not hang the walk
        6: CardStat(6, synthetic=True, name="Loop", maxDamage=50, evolvesFrom="Loop"),
    })
    assert stats.forward_max_damage(1) == 160     # max over both 2-hop branches
    assert stats.forward_max_damage(6) == 50      # cycle terminates (descendant 'Loop' folds its own)


@pytest.mark.req("REQ-GEN-0022")
def test_engine_provider_forward_max_damage_triggers_the_lazy_cache_build():
    # Called BEFORE any .get(), so it must build rather than crash on a None cache.
    pytest.importorskip("cg")
    from common.scouting.provider import EngineCardStatProvider
    p = EngineCardStatProvider()
    assert p.forward_max_damage(333) == 270   # first call ever — must self-build
    assert p.get(333).name == "Riolu"         # cache shared, .get() still works


@pytest.mark.req("REQ-SCOUT-0008")
def test_build_cache_maps_engine_objects_to_stats():
    attacks = [SimpleNamespace(attackId=10, damage=270, energies=[0, 0, 0, 0]),   # 4-energy attack
               SimpleNamespace(attackId=11, damage=70, energies=[6])]             # 1-energy attack
    cards = [SimpleNamespace(cardId=678, name="Mega Lucario ex", hp=220, ex=True, megaEx=True,
                             weakness=6, resistance=None, energyType=6, evolvesFrom="Riolu",
                             attacks=[10, 11])]   # single hop Riolu->Mega Lucario ex (no Lucario, this set)

    cache = _build_cache(cards, attacks)

    st = cache[678]
    assert st.maxDamage == 270            # max damage over the card's attacks
    assert st.minAttackCost == 1          # min energy-count over the card's attacks (cheap one)
    assert st.minCostDamage == 70         # damage of cheapest-cost attack (id 11) — not the 270
    assert st.maxDamageCost == 4          # cost of HIGHEST-damage attack (id 10, the 270 at CCCC)
    assert st.attacks == (10, 11)         # card's attack ids (lethal-attach lookahead reads these)
    assert st.megaEx and st.weakness == 6 and st.energyType == 6 and st.evolvesFrom == "Riolu"


@pytest.mark.req("REQ-SCOUT-0008")
def test_build_cache_carries_ace_spec():
    cards = [SimpleNamespace(cardId=1159, name="Hero's Cape", hp=0, ex=False, megaEx=False,
                             weakness=None, resistance=None, energyType=0, evolvesFrom=None,
                             attacks=[], aceSpec=True),
             SimpleNamespace(cardId=3, name="Water Energy", hp=0, ex=False, megaEx=False,
                             weakness=None, resistance=None, energyType=3, evolvesFrom=None,
                             attacks=[], aceSpec=False)]
    cache = _build_cache(cards, [])
    assert cache[1159].aceSpec is True       # Hero's Cape — the ACE SPEC
    assert cache[3].aceSpec is False         # plain Basic Energy


def _tool(card_id, name, text, ace_spec=False):
    """The engine has no structured HP-bonus field — only skill text (see ``_parse_tool_hp_bonus``)."""
    return SimpleNamespace(cardId=card_id, name=name, hp=0, ex=False, megaEx=False,
                           weakness=None, resistance=None, energyType=0, evolvesFrom=None,
                           attacks=[], aceSpec=ace_spec,
                           skills=[SimpleNamespace(name="", text=text)])


@pytest.mark.req("REQ-GEN-0024")
def test_build_cache_parses_flat_hp_bonus_and_carries_an_owner_gate_with_it():
    """`holderNameFamily` is what keeps an owner-gated +70 from reading as unconditional on every
    body (Issue #306). Source text verified against data/EN_Card_Data.csv."""
    cards = [
        _tool(1159, "Hero's Cape", "The Pokémon this card is attached to gets +100 HP.", ace_spec=True),
        _tool(1173, "Cynthia's Power Weight",
              "The Cynthia's Pokémon this card is attached to gets +70 HP."),
        _tool(1157, "Rescue Board",
              "The Retreat Cost of the Pokémon this card is attached to is {C} less. If that "
              "Pokémon's remaining HP is 30 or less, it has no Retreat Cost."),
    ]
    cache = _build_cache(cards, [])
    assert (cache[1159].hpBonus, cache[1159].holderNameFamily) == (100, None)   # unconditional
    assert (cache[1173].hpBonus, cache[1173].holderNameFamily) == (70, "Cynthia's")  # gated
    assert cache[1157].hpBonus == 0      # no HP bonus at all (a retreat tool)


@pytest.mark.req("REQ-GEN-0024")
@pytest.mark.req("REQ-SCOUT-0008")
def test_build_cache_parses_every_tool_damage_reduction_wording():
    """PR #533 review: the pool's four reduction Tools use holder-scoped and conditional wordings
    that the Pokémon-body patterns never matched. Source text verified against the CSV."""
    cards = [
        _tool(1164, "Payapa Berry",
              "If the Pokémon this card is attached to is damaged by an attack from your "
              "opponent’s {P} Pokémon, it takes 60 less damage (after applying Weakness and "
              "Resistance), and discard this card."),
        _tool(1170, "Haban Berry",
              "If the Pokémon this card is attached to is damaged by an attack from your "
              "opponent’s {N} Pokémon, it takes 60 less damage (after applying Weakness and "
              "Resistance), and discard this card."),
        _tool(1177, "Sacred Charm",
              "The Pokémon this card is attached to takes 30 less damage from attacks from your "
              "opponent’s Pokémon that have an Ability (after applying Weakness and Resistance)."),
        _tool(1179, "Thick Scale",
              "The {N} Pokémon this card is attached to takes 50 less damage from attacks from "
              "your opponent’s {G}, {R}, {W}, or {L} Pokémon (after applying Weakness and "
              "Resistance)."),
        _tool(1159, "Hero's Cape", "The Pokémon this card is attached to gets +100 HP.",
              ace_spec=True),
    ]

    cache = _build_cache(cards, [])

    def gates(card_id):
        stat = cache[card_id]
        return (stat.damageReduction, stat.damageReductionTypes,
                stat.damageReductionHolderTypes, stat.damageReductionRequiresAbility)

    assert gates(1164) == (60, (5,), None, False)      # {P} attackers only
    assert gates(1170) == (60, (9,), None, False)      # {N} attackers only
    assert gates(1177) == (30, None, None, True)       # any attacker WITH an Ability
    assert gates(1179) == (50, (1, 2, 3, 4), (9,), False)  # {N} holder vs {G}{R}{W}{L}
    assert gates(1159) == (0, None, None, False)       # an HP tool grants no reduction


def test_build_cache_hp_bonus_defaults_to_zero_without_skills():
    cards = [SimpleNamespace(cardId=678, name="Mega Lucario ex", hp=220, ex=True, megaEx=True,
                             weakness=6, resistance=None, energyType=6, evolvesFrom="Riolu", attacks=[])]
    assert _build_cache(cards, [])[678].hpBonus == 0


@pytest.mark.req("REQ-GEN-0024")
def test_build_cache_parses_bench_snipe_damage_from_attack_text():
    """Only the UNCONDITIONAL single-target snipe, max over the card's attacks — the incoming-damage
    primitive the Tool survival-turns math reads (ADR-0028)."""
    attacks = [
        SimpleNamespace(attackId=20, damage=120, energies=[6],
                        text="This attack also does 50 damage to 1 of your opponent's Benched Pokémon."),
        SimpleNamespace(attackId=21, damage=20, energies=[6], text=""),   # no snipe rider
    ]
    cards = [SimpleNamespace(cardId=1031, name="Mega Starmie ex", hp=330, ex=False, megaEx=True,
                             weakness=4, resistance=None, energyType=3, evolvesFrom="Staryu",
                             attacks=[20, 21])]
    assert _build_cache(cards, attacks)[1031].benchSnipeDamage == 50
