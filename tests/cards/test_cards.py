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
def test_parametric_tags_fail_closed_on_malformed_or_missing_values():
    cf = CardFunctions({1: ["dig:3"], 2: ["dig:x"], 3: ["dig:-2"], 4: ["draw"],
                        5: ["provides:1", "provides_evo:3"]})
    assert cf.dig_depth(1) == 3
    assert cf.dig_depth(2) == 0          # unreadable number reads as no claim
    assert cf.dig_depth(3) == 0          # negative clamps to nothing
    assert cf.dig_depth(4) == 0          # untagged
    assert cf.energy_provision(5) == 1
    assert cf.energy_provision(5, evolution=True) == 3
    assert cf.energy_provision(4) == 0


@pytest.mark.req("REQ-PILOT-0008")
def test_reserved_keys_are_skipped_not_crashed_on():
    cf = CardFunctions({"_note": ["free text"], "66": ["draw"]})
    assert cf.tags(66) == ["draw"]


@pytest.mark.req("REQ-PILOT-0008")
def test_discard_energy_recur_tags_the_self_refuel_attackers():
    # An attacker that re-attaches Energy FROM ITS OWN DISCARD is not as energy-starved as its board
    # shows. Curated in function_overrides.json, because opponent cards are never probed.
    cf = CardFunctions.load()
    assert "discard_energy_recur" in cf.tags(678)   # Mega Lucario ex (ours + vs hariyama_mega_lucario)
    assert "discard_energy_recur" in cf.tags(190)   # Archaludon ex (vs archaludon_ex_cinderace)
    # The Pokemon-recovery case REUSES the existing `recycle` tag (no separate tag minted):
    assert "recycle" in cf.tags(162)                # Slowpoke Dangle Tail (Pokemon from discard -> hand)
