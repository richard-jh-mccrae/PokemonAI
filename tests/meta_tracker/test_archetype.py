"""Archetype reconstruction: evolution lines, main/sub split, naming."""
from meta_tracker.archetype import classify, evolution_lines
from meta_tracker.cards import load_cards

STARYU, MEGA_STARMIE_EX, CINDERACE, BASIC_W = 1030, 1031, 666, 3


def _deck(*pairs):
    out = []
    for cid, n in pairs:
        out += [cid] * n
    return out


def test_single_evolution_line_groups_basic_and_evo():
    lines = evolution_lines({STARYU: 4, MEGA_STARMIE_EX: 3})
    assert len(lines) == 1
    line = lines[0]
    assert line.top_name == "Mega Starmie ex"      # highest stage present
    assert set(line.members) == {STARYU, MEGA_STARMIE_EX}
    assert line.investment == 3                     # copies of the top stage
    assert line.exclass is True                     # Mega-ex


def test_top_stage_without_pre_evolution_still_a_line():
    # Cinderace (Stage 2) with no Raboot/Scorbunny in deck.
    lines = evolution_lines({CINDERACE: 4})
    assert len(lines) == 1 and lines[0].top_name == "Cinderace"


def test_single_main_archetype():
    a = classify(_deck((STARYU, 4), (MEGA_STARMIE_EX, 3), (BASIC_W, 53)))
    assert a.main_lines == ["Mega Starmie ex"]
    assert a.name == "Mega Starmie ex"
    assert "water" in a.energy


def test_dual_attacker_archetype_names_both_mains():
    a = classify(_deck((CINDERACE, 4), (STARYU, 3), (MEGA_STARMIE_EX, 3), (BASIC_W, 50)))
    assert set(a.main_lines) == {"Cinderace", "Mega Starmie ex"}
    assert a.name == "Cinderace / Mega Starmie ex"   # canonical (sorted) key


def test_archetype_key_is_order_independent():
    d1 = classify(_deck((CINDERACE, 4), (MEGA_STARMIE_EX, 3), (STARYU, 3)))
    d2 = classify(_deck((MEGA_STARMIE_EX, 3), (STARYU, 3), (CINDERACE, 4)))
    assert d1.name == d2.name


def test_low_copy_lines_are_sub_not_main():
    # One-of attacker shouldn't become a main line.
    a = classify(_deck((STARYU, 4), (MEGA_STARMIE_EX, 3), (CINDERACE, 1), (BASIC_W, 52)))
    assert a.main_lines == ["Mega Starmie ex"]
    assert "Cinderace" in a.sub_lines


def _id(name):
    return next(cid for cid, c in load_cards().items() if c["name"] == name)


def test_engine_pokemon_demoted_to_sub():
    # Budew (curated engine) must not name deck even with copies + an attack.
    a = classify(_deck((CINDERACE, 4), (_id("Budew"), 3), (BASIC_W, 53)))
    assert a.main_lines == ["Cinderace"]
    assert "Budew" in a.sub_lines


def test_dudunsparce_engine_demoted():
    a = classify(_deck((STARYU, 4), (MEGA_STARMIE_EX, 3), (_id("Dudunsparce"), 4), (BASIC_W, 49)))
    assert a.main_lines == ["Mega Starmie ex"]
    assert "Dudunsparce" in a.sub_lines


def test_pure_engine_deck_falls_back_not_unknown():
    # If only attacker is an engine, still name it (don't emit "Unknown").
    a = classify(_deck((_id("Budew"), 4), (BASIC_W, 56)))
    assert a.name != "Unknown" and a.main_lines == ["Budew"]


def test_zero_damage_wincon_is_main():
    # Regression: Alakazam attacks via ability (printed damage 0) but is deck's
    # main win-condition; Dudunsparce engine alongside it must not steal the name.
    a = classify(_deck((_id("Alakazam"), 4), (_id("Dudunsparce"), 4), (BASIC_W, 52)))
    assert a.main_lines == ["Alakazam"]
    assert "Dudunsparce" in a.sub_lines


def test_cards_cache_loaded():
    assert len(load_cards()) > 1000
