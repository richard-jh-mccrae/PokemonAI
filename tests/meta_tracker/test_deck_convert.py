"""deck_convert: Limitless .txt <-> deck.csv, with full legality invalidation (ADR-0013).

Offline. Negative tests assert every illegal build is rejected (and valid boundaries
pass), per the ISTQB negative-testing standard.
"""
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from deck_convert import (  # noqa: E402
    ConvertError, REPO, _indexes, check_legality, convert_to_csv,
    render_txt, resolve_deck,
)
from meta_tracker.cards import load_cards  # noqa: E402

CARDS = load_cards()
BY_NORM = _indexes()[0]
WATER = 3                                                        # Basic {W} Energy (unlimited)
BASIC_POKE = next(c for c, m in CARDS.items()
                  if m.get("category") == "pokemon" and m.get("stage") == "basic")
ACE = next(c for c, m in CARDS.items() if m.get("aceSpec"))
SPECIAL_E = next(c for c, m in CARDS.items() if m.get("category") == "special_energy")
ULTRA = BY_NORM["ultra ball"][0]
EEVEE = BY_NORM["eevee"]                                         # several printings, same name

req = pytest.mark.req("REQ-CONVERT-0001")


def _deck(n, *, basic=True, fill=WATER):
    """An n-card deck: one Basic Pokémon (optional) padded with basic energy."""
    return ([BASIC_POKE] if basic else []) + [fill] * (n - (1 if basic else 0))


# --- forward resolution ---------------------------------------------------

@req
def test_basic_energy_maps_by_element():
    deck, problems = resolve_deck("3 Psychic Energy MEE 5\n2 Fire Energy MEE 2")
    assert problems == [] and Counter(deck) == {5: 3, 2: 2}


@req
def test_apostrophe_is_normalized():
    # straight apostrophe in input; pool stores curly form (id 1182)
    deck, problems = resolve_deck("1 Boss's Orders PAL 172")
    assert problems == [] and deck == [1182]


@req
def test_absent_card_is_a_problem():
    _, problems = resolve_deck("1 Special Red Card CRI 82")
    assert problems and "absent" in problems[0] and "Special Red Card" in problems[0]


@req
def test_ambiguous_card_is_a_problem():
    assert len(EEVEE) > 1                                        # guard: name is really ambiguous
    _, problems = resolve_deck("1 Eevee ZZZ 999")               # printing matches none
    assert problems and "ambiguous" in problems[0]


@req
def test_real_limitless_deck_hard_fails_on_absent_card(tmp_path):
    src = REPO / "data" / "decks" / "limitless_dragpult.txt"
    if not src.exists():
        pytest.skip("needs local Limitless decklist; data/ is gitignored")  # not on clean checkout/CI
    with pytest.raises(ConvertError) as e:
        convert_to_csv(src, "x", dest_root=tmp_path)
    assert any("Special Red Card" in p for p in e.value.problems)
    assert not (tmp_path / "x").exists()                         # nothing written on failure


# --- legality: boundary + every illegal build ----------------------------

@req
def test_card_count_must_be_exactly_60():
    assert check_legality(_deck(60)) == []                       # valid boundary
    assert any("59" in v for v in check_legality(_deck(59)))     # too few
    assert any("61" in v for v in check_legality(_deck(61)))     # too many


@req
def test_max_four_copies_by_name():
    assert check_legality([ULTRA] * 4 + _deck(56)) == []         # 4 is legal
    bad = check_legality([ULTRA] * 5 + _deck(55))                # 5 is not
    assert any("max 4" in v for v in bad)


@req
def test_copy_limit_counts_across_printings_by_name():
    # 4 of one Eevee printing + 1 of another = 5 by name -> illegal
    bad = check_legality([EEVEE[0]] * 4 + [EEVEE[1]] * 1 + [WATER] * 55)
    assert any("max 4" in v and "Eevee" in v for v in bad)


@req
def test_basic_energy_is_exempt_but_special_energy_is_not():
    assert check_legality(_deck(60)) == []                       # 59 basic energy: fine
    bad = check_legality([SPECIAL_E] * 5 + _deck(55))            # 5 special energy: not
    assert any("max 4" in v for v in bad)


@req
def test_at_most_one_ace_spec():
    assert check_legality([ACE] * 1 + _deck(59)) == []           # exactly 1 is legal
    bad = check_legality([ACE] * 2 + _deck(58))                  # 2 is not
    assert any("ACE SPEC" in v for v in bad)


@req
def test_requires_at_least_one_basic_pokemon():
    assert any("Basic Pokémon" in v for v in check_legality(_deck(60, basic=False)))
    assert check_legality(_deck(60, basic=True)) == []


# --- reverse + round trip -------------------------------------------------

@req
def test_render_has_sections_and_totals():
    txt = render_txt(_deck(60))
    assert "Pokémon: 1" in txt and "Energy: 59" in txt


@req
def test_round_trip_preserves_multiset():
    deck = ([BY_NORM["staryu"][0]] * 3 + [BY_NORM["mega starmie ex"][0]] * 3
            + [BY_NORM["cinderace"][0]] * 4 + [ULTRA] * 4 + [WATER] * 46)
    back, problems = resolve_deck(render_txt(deck))
    assert problems == [] and Counter(back) == Counter(deck)


# --- to-csv end to end ----------------------------------------------------

@req
def test_to_csv_writes_sorted_legal_deck(tmp_path):
    src = sorted(int(x) for x in
                 (REPO / "src" / "agents" / "mega_starmie" / "deck.csv")
                 .read_text().split())
    txt = tmp_path / "d.txt"
    txt.write_text(render_txt(src), encoding="utf-8")
    dest = convert_to_csv(txt, "out", dest_root=tmp_path)
    got = [int(x) for x in (dest / "deck.csv").read_text().split()]
    assert got == sorted(got) and got == src                     # sorted, exact round trip


@req
def test_refuses_existing_dir_unless_force(tmp_path):
    (tmp_path / "dup").mkdir()
    txt = tmp_path / "d.txt"
    txt.write_text(render_txt(_deck(60)), encoding="utf-8")
    with pytest.raises(ConvertError):
        convert_to_csv(txt, "dup", dest_root=tmp_path)
    assert (convert_to_csv(txt, "dup", force=True, dest_root=tmp_path) / "deck.csv").exists()
