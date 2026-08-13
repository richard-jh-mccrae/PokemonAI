"""CardFunctions: the Function Tag lookup the Pilot reads (partial/additive)."""
import pytest

from common.cards import CardFunctions


@pytest.mark.req("REQ-PILOT-0008")
def test_tags_returns_assigned_tags():
    cf = CardFunctions({666: ["energy_accel"], 1145: ["tutor"]})
    assert cf.tags(666) == ["energy_accel"]


@pytest.mark.req("REQ-PILOT-0008")
def test_unknown_card_has_no_tags():
    # Partial/additive: a card the table hasn't tagged yet has none.
    assert CardFunctions({}).tags(99999) == []


def test_partner_tags_expose_printed_card_dependencies():
    cards = CardFunctions({675: ["draw", "partner:676"], 676: ["partner:675"],
                           1: ["partner:nope"], 2: ["partner:2"]})
    assert cards.partners(675) == (676,)
    assert cards.partners(676) == (675,)
    assert cards.partners(1) == ()
    assert cards.partners(2) == ()


def test_shared_role_and_evolution_tags_are_parsed_as_card_facts():
    cards = CardFunctions({675: ["role:engine"], 677: ["evolves:678"],
                           1: ["role:"], 2: ["evolves:nope"], 3: ["evolves:3"]})
    assert cards.roles(675) == ("engine",)
    assert cards.evolves_to(677) == (678,)
    assert cards.roles(1) == ()
    assert cards.evolves_to(2) == ()
    assert cards.evolves_to(3) == ()


@pytest.mark.req("REQ-PILOT-0008")
def test_load_missing_file_degrades_to_empty(tmp_path):
    cf = CardFunctions.load(tmp_path / "absent.json")
    assert cf.tags(1) == []


@pytest.mark.req("REQ-PILOT-0008")
def test_discard_energy_recur_tags_the_self_refuel_attackers():
    # An attacker that re-attaches Energy FROM ITS OWN DISCARD is not as energy-starved as its board
    # shows. Curated in function_overrides.json, because opponent cards are never probed.
    cf = CardFunctions.load()
    assert "discard_energy_recur" in cf.tags(678)   # Mega Lucario ex (ours + vs hariyama_mega_lucario)
    assert "discard_energy_recur" in cf.tags(190)   # Archaludon ex (vs archaludon_ex_cinderace)
    # The Pokemon-recovery case REUSES the existing `recycle` tag (no separate tag minted):
    assert "recycle" in cf.tags(162)                # Slowpoke Dangle Tail (Pokemon from discard -> hand)
