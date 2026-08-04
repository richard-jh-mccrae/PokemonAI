"""Arena deck funnel: Deck Text -> 60 ids or a problem list; the Preset gallery.

Offline (pool data only). The Visitor-facing contract: a valid Limitless export
resolves whole; anything wrong rejects whole with every problem listed (ADR-0013).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from arena import decks  # noqa: E402

req = pytest.mark.req("REQ-ARENA-0001")

REPO = Path(__file__).resolve().parents[2]
MEGA_STARMIE_TXT = REPO / "src" / "agents" / "mega_starmie" / "deck.txt"


@req
def test_valid_deck_text_resolves_to_60_ids():
    res = decks.resolve_deck_text(MEGA_STARMIE_TXT.read_text(encoding="utf-8"))
    assert res.ok
    assert len(res.ids) == 60
    assert not res.problems


@req
def test_unknown_card_rejects_whole_deck_and_names_it():
    text = MEGA_STARMIE_TXT.read_text(encoding="utf-8").replace(
        "3 Staryu", "2 Staryu", 1) + "\n1 Special Red Card CRI 82\n"
    res = decks.resolve_deck_text(text)
    assert not res.ok
    assert not res.ids                       # never a silently-partial deck
    assert any("Special Red Card" in p for p in res.problems)


@req
def test_illegal_count_rejects_with_legality_problem():
    text = MEGA_STARMIE_TXT.read_text(encoding="utf-8").replace(
        "3 Staryu", "2 Staryu", 1)           # 59 cards, names all fine
    res = decks.resolve_deck_text(text)
    assert not res.ok and not res.ids
    assert any("60" in p for p in res.problems)


# --- Preset gallery ---------------------------------------------------------

@req
def test_preset_gallery_lists_only_ready_to_play_decks():
    presets = decks.list_presets()
    assert any(p.id == "mega_starmie" for p in presets)
    for p in presets:                        # every listed preset is playable as-is
        res = decks.load_preset(p.id)
        assert res.ok and len(res.ids) == 60
        assert p.title                       # something for the gallery card


@req
def test_unknown_preset_is_a_key_error():
    with pytest.raises(KeyError):
        decks.load_preset("no_such_preset")


@req
def test_broken_preset_file_is_excluded_not_fatal(tmp_path):
    (tmp_path / "good.txt").write_text(
        MEGA_STARMIE_TXT.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "broken.txt").write_text("4 Special Red Card CRI 82\n", encoding="utf-8")
    presets = decks.list_presets(root=tmp_path)
    assert [p.id for p in presets] == ["good"]


@req
def test_undecodable_preset_file_is_excluded_not_fatal(tmp_path):
    (tmp_path / "good.txt").write_text(
        MEGA_STARMIE_TXT.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "latin.txt").write_bytes(b"3 M\xe9ga Something XXX 1\n")   # not UTF-8
    presets = decks.list_presets(root=tmp_path)
    assert [p.id for p in presets] == ["good"]
    res = decks.load_preset("latin", root=tmp_path)
    assert not res.ok and res.problems                 # rejected, never a crash


# --- builder: pool catalog + id validation -----------------------------------

@req
def test_pool_catalog_carries_what_the_builder_renders():
    catalog = decks.pool_catalog()
    assert len(catalog) > 1000
    by_name = {c["name"]: c for c in catalog}
    staryu = by_name["Staryu"]
    assert staryu["category"] == "pokemon" and staryu["stage"] == "basic"
    assert staryu["hp"] == 70
    atk = staryu["attacks"][0]
    assert atk["name"] == "Water Gun" and atk["damage"] == 20
    assert atk["cost"] == ["Water"]
    ultra = by_name["Ultra Ball"]
    assert ultra["category"] == "item"
    assert "discard 2" in ultra["effect"].lower()
    water = by_name["Basic {W} Energy"]
    assert water["category"] == "basic_energy"          # the unlimited-count flag


@req
def test_validate_ids_enforces_the_construction_rules():
    base = list(decks.load_preset("mega_starmie").ids)
    assert decks.validate_ids(base).ok
    res = decks.validate_ids(base[:59])
    assert not res.ok and any("60" in p for p in res.problems)
    res = decks.validate_ids(base[:59] + [999999])
    assert not res.ok and any("unknown" in p.lower() for p in res.problems)


@req
def test_validate_ids_counts_copies_by_name_across_printings():
    from deck_convert import _indexes
    eevee = _indexes()[0]["eevee"]
    assert len(eevee) > 1                               # guard: several printings
    base = list(decks.load_preset("mega_starmie").ids)[:52]
    res = decks.validate_ids(base + [eevee[0]] * 4 + [eevee[1]] * 4)
    assert not res.ok and any("max 4" in p for p in res.problems)


@req
def test_preset_cards_expose_the_clone_source():
    cards = decks.preset_cards("mega_starmie")
    assert sum(c["count"] for c in cards) == 60
    assert all(c["count"] >= 1 for c in cards)
    with pytest.raises(KeyError):
        decks.preset_cards("no_such_preset")


# --- hostile input ----------------------------------------------------------

@req
def test_absurd_counts_are_rejected_before_expansion():
    res = decks.resolve_deck_text("999999 Psychic Energy MEE 5\n")
    assert not res.ok and not res.ids
    huge = "9" * 5000                                  # digit bomb: int() would raise
    res = decks.resolve_deck_text(f"{huge} Psychic Energy MEE 5\n")
    assert not res.ok and not res.ids
