"""The closed Category vocabulary (the human axis of a Correction)."""
from train.blunder.categories import CATEGORIES, is_valid_category


def test_category_vocab_is_closed_and_includes_agreed_terms():
    """REQ-BLUNDER-0003: Category is a closed vocabulary; the agreed starter terms
    are members and unknown strings (incl. the renamed-away `missed_lethal`) are rejected."""
    assert "missed_win" in CATEGORIES                       # renamed from missed_lethal
    assert {"overextension", "misattachment", "bad_retreat", "other"} <= set(CATEGORIES)
    # added by process when sequencing_error was found to swallow these distinct kinds
    assert {"missed_evolution", "missed_disruption"} <= set(CATEGORIES)

    assert is_valid_category("missed_win")
    assert is_valid_category("missed_evolution")
    assert is_valid_category("missed_disruption")
    assert not is_valid_category("missed_lethal")           # old name is gone
    assert not is_valid_category("nonsense")
