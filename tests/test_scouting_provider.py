"""Card-stat providers (docs/scouting.md). The engine transform is tested lib-free."""
from types import SimpleNamespace

import pytest

from common.scouting.provider import CardStat, DictCardStatProvider, _build_cache


@pytest.mark.req("REQ-SCOUT-0008")
def test_dict_provider_returns_stats_or_none():
    p = DictCardStatProvider({1: CardStat(1, name="x", hp=70)})
    assert p.get(1).hp == 70
    assert p.get(999) is None


@pytest.mark.req("REQ-SCOUT-0008")
def test_build_cache_maps_engine_objects_to_stats():
    attacks = [SimpleNamespace(attackId=10, damage=270, energies=[0, 0, 0, 0]),   # 4-energy attack
               SimpleNamespace(attackId=11, damage=70, energies=[6])]             # 1-energy attack
    cards = [SimpleNamespace(cardId=678, name="Mega Lucario ex", hp=220, ex=True, megaEx=True,
                             weakness=6, resistance=None, energyType=6, evolvesFrom="Lucario",
                             attacks=[10, 11])]

    cache = _build_cache(cards, attacks)

    st = cache[678]
    assert st.maxDamage == 270            # max damage over the card's attacks
    assert st.minAttackCost == 1          # min energy-count over the card's attacks (the cheap one)
    assert st.megaEx and st.weakness == 6 and st.energyType == 6 and st.evolvesFrom == "Lucario"
