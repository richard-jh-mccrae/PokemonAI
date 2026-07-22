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


@pytest.mark.req("REQ-PILOT-0008")
def test_load_missing_file_degrades_to_empty(tmp_path):
    cf = CardFunctions.load(tmp_path / "absent.json")
    assert cf.tags(1) == []


@pytest.mark.req("REQ-PILOT-0008")
def test_discard_energy_recur_tags_the_self_refuel_attackers():
    # Opponent-discard reading (resource half): an attacker that re-attaches Energy FROM ITS OWN
    # DISCARD isn't as energy-starved as its board shows — the signal the board-clock read needs.
    # Curated in function_overrides.json (opponent cards are never probed). Verify-at-source:
    #   Mega Lucario ex (678) Aura Jab — "Attach up to 3 Basic {F} Energy cards from your discard
    #     pile to your Benched Pokémon"; Archaludon ex (190) Assemble Alloy — attaches Basic {M}
    #     from the discard pile on evolve. (EN_Card_Data.csv)
    cf = CardFunctions.load()
    assert "discard_energy_recur" in cf.tags(678)   # Mega Lucario ex (ours + vs hariyama_mega_lucario)
    assert "discard_energy_recur" in cf.tags(190)   # Archaludon ex (vs archaludon_ex_cinderace)
    # The Pokemon-recovery case REUSES the existing `recycle` tag (no separate tag minted):
    assert "recycle" in cf.tags(162)                # Slowpoke Dangle Tail (Pokemon from discard -> hand)
