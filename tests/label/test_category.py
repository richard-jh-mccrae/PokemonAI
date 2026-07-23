"""The machine-only `value_delta` category (S3a design §D4) — a real member of the closed vocab so
`build_correction` accepts machine labels, kept distinct so reports can filter them and the humans'
`other` vocab-gap signal stays clean."""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


@pytest.mark.req("REQ-LABEL-0003")
def test_value_delta_is_a_valid_category():
    from train.blunder.categories import CATEGORIES, is_valid_category

    assert is_valid_category("value_delta")
    assert "value_delta" in CATEGORIES


@pytest.mark.req("REQ-LABEL-0003")
def test_machine_store_path_is_gitignored():
    """The machine store must be regenerable-and-ignored so it never lands in the committed gold tree."""
    out = subprocess.run(["git", "check-ignore", "data/corrections/machine/corrections.jsonl"],
                         cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, "data/corrections/machine/ must be gitignored (regenerable artifact)"
