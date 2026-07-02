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
