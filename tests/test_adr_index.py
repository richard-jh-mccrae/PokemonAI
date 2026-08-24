from __future__ import annotations

import re
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


def test_adr_index_matches_disk_and_next_free_number() -> None:
    text = INDEX.read_text(encoding="utf-8")
    index = text.split("## Index", 1)[1]
    rows = re.findall(r"^\| (\d{4}|\[(\d{4})\]\(([^)]+)\)) \|", index, re.MULTILINE)
    numbers = [plain or linked for plain, linked, _ in rows]
    companion_numbers = re.findall(
        r"^\| (\d{4}) \| .*companion vocabulary doc", index, re.MULTILINE,
    )
    adr_numbers = numbers.copy()
    for number in companion_numbers:
        adr_numbers.remove(number)
    assert len(adr_numbers) == len(set(adr_numbers)), "duplicate ADR number in index"
    linked_numbers = [linked for _, linked, _ in rows if linked]
    assert len(linked_numbers) == len(set(linked_numbers)), "duplicate linked ADR number in index"

    files = list(INDEX.parent.glob("[0-9][0-9][0-9][0-9]-*.md"))
    disk_numbers = [path.name[:4] for path in files]
    assert len(disk_numbers) == len(set(disk_numbers)), "duplicate ADR number on disk"
    linked_targets = {target for _, _, target in rows if target}
    assert linked_targets == {path.name for path in files}
    for _, number, target in rows:
        if target:
            assert target.startswith(f"{number}-")
            assert (INDEX.parent / target).is_file()

    next_free = int(re.search(r"\*\*Next free number: (\d{4})\.\*\*", text).group(1))
    assert next_free == max(map(int, disk_numbers)) + 1
    assert f"{next_free:04d}" not in numbers
