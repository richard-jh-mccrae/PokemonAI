"""Card-stat providers (docs/scouting.md). The engine transform is tested lib-free."""
from types import SimpleNamespace

import pytest

from common.scouting.provider import CardStat, DictCardStatProvider, _build_cache


@pytest.mark.req("REQ-SCOUT-0008")
def test_dict_provider_returns_stats_or_none():
    p = DictCardStatProvider({1: CardStat(1, name="x", hp=70)})
    assert p.get(1).hp == 70
    assert p.get(999) is None


@pytest.mark.req("REQ-GEN-0022")
def test_forward_max_damage_reaches_the_evolution_lines_attacker():
    # Riolu (Basic, weak attack) evolves into Mega Lucario ex (270). Forward index reports the
    # damage the LINE eventually reaches, read off the pre-evolution (see ADR-0020).
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
        500: CardStat(500, name="Sunkern", maxDamage=20),          # bare basic, evolves into nothing
    })
    assert stats.forward_max_damage(678) == 0     # final form: descendants only, NOT its own 270
    assert stats.forward_max_damage(500) == 0     # dead-end basic
    assert stats.forward_max_damage(999) == 0     # unknown id -> fail closed


@pytest.mark.req("REQ-GEN-0022")
def test_forward_max_damage_folds_max_over_same_name_printings():
    # 'Riolu' has multiple printings; descendant name 'Eevee-mon' too. Fold MAX over printings.
    stats = DictCardStatProvider({
        333: CardStat(333, name="Riolu", maxDamage=10),
        974: CardStat(974, name="Riolu", maxDamage=30),            # second Riolu printing
        678: CardStat(678, name="Mega Lucario ex", maxDamage=130, evolvesFrom="Riolu"),
        679: CardStat(679, name="Mega Lucario ex", maxDamage=270, evolvesFrom="Riolu"),  # bigger print
    })
    assert stats.forward_max_damage(333) == 270   # folds 130/270 printings -> 270
    assert stats.forward_max_damage(974) == 270   # any printing of pre-evo resolves the same


@pytest.mark.req("REQ-GEN-0022")
def test_forward_max_damage_walks_branching_multihop_and_survives_cycles():
    stats = DictCardStatProvider({
        1: CardStat(1, name="Wurmple", maxDamage=10),
        2: CardStat(2, name="Silcoon", maxDamage=20, evolvesFrom="Wurmple"),
        3: CardStat(3, name="Beautifly", maxDamage=90, evolvesFrom="Silcoon"),
        4: CardStat(4, name="Cascoon", maxDamage=20, evolvesFrom="Wurmple"),
        5: CardStat(5, name="Dustox", maxDamage=160, evolvesFrom="Cascoon"),  # max across all branches
        # malformed self-cycle must not hang the walk
        6: CardStat(6, name="Loop", maxDamage=50, evolvesFrom="Loop"),
    })
    assert stats.forward_max_damage(1) == 160     # max over both 2-hop branches
    assert stats.forward_max_damage(6) == 50      # cycle terminates (descendant 'Loop' folds its own)


@pytest.mark.req("REQ-GEN-0022")
def test_engine_provider_forward_max_damage_triggers_the_lazy_cache_build():
    # Amendment guard: forward_max_damage called BEFORE any .get() must trigger the same lazy
    # build (not crash on a None cache). Riolu (333) -> Mega Lucario ex line (270) off real engine.
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
    """ACE SPEC is a structural fact the runtime reads off CardStat — for 'protect the irreplaceable
    one-of ACE SPEC' rules (e.g. Hero's Cape)."""
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
    """An engine CardData stand-in for a Pokémon Tool whose only datum of interest is its skill text
    (the engine has no structured HP-bonus field — see ``_parse_tool_hp_bonus``)."""
    return SimpleNamespace(cardId=card_id, name=name, hp=0, ex=False, megaEx=False,
                           weakness=None, resistance=None, energyType=0, evolvesFrom=None,
                           attacks=[], aceSpec=ace_spec,
                           skills=[SimpleNamespace(name="", text=text)])


@pytest.mark.req("REQ-GEN-0024")
def test_build_cache_parses_flat_hp_bonus_only_from_unconditional_tool_text():
    """A +HP Tool's bonus lives ONLY in free skill text — parse the UNCONDITIONAL 'gets +N HP' into a
    structured ``CardStat.hpBonus``, the primitive the general breakpoint model reads. Restricted
    variants ('The Cynthia's Pokémon …', 'The {G} Pokémon …') grant the bonus only to a subset, so
    they parse to 0 — the model must never over-credit HP a target might not get. Source text verified
    against data/EN_Card_Data.csv."""
    cards = [
        _tool(1159, "Hero's Cape", "The Pokémon this card is attached to gets +100 HP.", ace_spec=True),
        _tool(1173, "Cynthia's Power Weight",
              "The Cynthia's Pokémon this card is attached to gets +70 HP."),
        _tool(1157, "Rescue Board",
              "The Retreat Cost of the Pokémon this card is attached to is {C} less. If that "
              "Pokémon's remaining HP is 30 or less, it has no Retreat Cost."),
    ]
    cache = _build_cache(cards, [])
    assert cache[1159].hpBonus == 100    # unconditional +100 — the parseable, general case
    assert cache[1173].hpBonus == 0      # restricted to 'Cynthia's Pokémon' — not credited
    assert cache[1157].hpBonus == 0      # no HP bonus at all (a retreat tool)


@pytest.mark.req("REQ-GEN-0024")
def test_build_cache_hp_bonus_defaults_to_zero_without_skills():
    """A card record with no skills (the lib-free test shape, and any non-Tool) parses to 0 — no crash."""
    cards = [SimpleNamespace(cardId=678, name="Mega Lucario ex", hp=220, ex=True, megaEx=True,
                             weakness=6, resistance=None, energyType=6, evolvesFrom="Riolu", attacks=[])]
    assert _build_cache(cards, [])[678].hpBonus == 0


@pytest.mark.req("REQ-GEN-0024")
def test_build_cache_parses_bench_snipe_damage_from_attack_text():
    """A bench-snipe rider (Jetting Blow's 'also does 50 damage to 1 of your opponent's Benched
    Pokémon') lives only in attack text — parse the UNCONDITIONAL single-target snipe into a structured
    ``CardStat.benchSnipeDamage`` (max over the card's attacks), the opponent-incoming-vs-my-Bench
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
