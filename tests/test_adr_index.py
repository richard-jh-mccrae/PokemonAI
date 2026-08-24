from __future__ import annotations

from pathlib import Path


INDEX = Path(__file__).resolve().parents[1] / "docs" / "adr" / "README.md"

EXPECTED = {
    "0027": "Intent retained; consumption superseded by ADR-0175 and ADR-0180.",
    "0034": "Superseded by ADR-0155, ADR-0156, ADR-0164, and ADR-0165.",
    "0035": "Superseded by ADR-0155, ADR-0156, ADR-0164, and ADR-0165.",
    "0036": "Original skill implementation retired; no live owner.",
    "0046": "Original skill implementation retired; no live owner.",
    "0047": "Original files retired; ownership intent restored by ADR-0175 and ADR-0180.",
    "0051": "MatchupPlan retired; superseded by ADR-0162, ADR-0163, ADR-0175, and ADR-0180.",
    "0068": "StateModel retired; replaced by ObservationState under ADR-0154.",
    "0087": "Original correction gate retired; corpus architecture superseded by ADR-0185–ADR-0192.",
    "0089": "Original correction gate retired; corpus architecture superseded by ADR-0185–ADR-0192.",
    "0120": "MatchupPlan retired; superseded by ADR-0162, ADR-0163, ADR-0175, and ADR-0180.",
}


def test_historical_index_rows_name_their_current_successors() -> None:
    lines = INDEX.read_text(encoding="utf-8").splitlines()
    rows = {line.split("|", 2)[1].strip(): line for line in lines if line.startswith("| ")}
    for number, status in EXPECTED.items():
        assert status in rows[number]


def test_index_declares_the_unlinked_archive_rows_historical() -> None:
    text = " ".join(INDEX.read_text(encoding="utf-8").split())
    assert "Rows 0001–0142 are historical summaries, not a current file or implementation map." in text
