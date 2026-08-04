"""Ruling records must agree with the reviewed-corrections ledger.

The Markdown files in ``data/leaf_lab/*-rulings.md`` are ruling records. The effects that change
grading live in ``data/corrections/reviewed.json``. This test guards that handoff.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.gates import VOIDING_DISPOSITIONS  # noqa: E402

RULING_RECORDS = sorted((REPO / "data" / "leaf_lab").glob("*-rulings.md"))
REVIEWED = REPO / "data" / "corrections" / "reviewed.json"
VOCABULARY = frozenset({"REFUTED", "TRANSPOSITION", "UN-VOID", "REVERT", "CONFORM"})


@dataclass(frozen=True)
class RecordedVerdict:
    path: Path
    line_no: int
    frame_key: str
    review_key: str
    verdicts: tuple[str, ...]


@dataclass(frozen=True)
class Extraction:
    entries: tuple[RecordedVerdict, ...]
    skipped_key_rows: int
    malformed_key_rows: tuple[tuple[Path, int, str], ...]


def _split_markdown_row(line: str) -> list[str]:
    if not line.startswith("|"):
        return []
    protected = line.replace("\\|", "<<PIPE>>").strip()
    cells = protected.strip("|").split("|")
    return [c.replace("<<PIPE>>", "\\|").strip() for c in cells]


def _normalise_review_key(raw: str) -> tuple[str, str] | None:
    frame_key = raw.replace("\\|", "|")
    parts = frame_key.split("|")
    if len(parts) != 4:
        return None
    episode, seat, scope, subject = parts
    if not (episode.isdigit() and seat.isdigit()):
        return None
    if scope == "decision" and subject.isdigit():
        return frame_key, f"{episode}-{subject}"
    if scope == "turn" and subject.isdigit():
        return frame_key, f"{episode}-t{subject}s{seat}"
    if scope == "match" and subject == "":
        return frame_key, f"{episode}-m{seat}"
    return None


def _key_from_cells(cells: list[str]) -> tuple[str, str] | None:
    for cell in cells:
        for raw in re.findall(r"`([^`]+)`", cell):
            if "\\|" not in raw and "|" not in raw:
                continue
            hit = _normalise_review_key(raw)
            if hit is not None:
                return hit
    return None


def _malformed_key(cells: list[str]) -> str | None:
    for cell in cells:
        for raw in re.findall(r"`([^`]+)`", cell):
            if "\\|" in raw or "|" in raw:
                return raw
    return None


def _verdicts_from_cell(cell: str) -> tuple[str, ...] | None:
    if "**" not in cell:
        return None
    plain = cell.replace("**", "").strip()
    tokens = tuple(part.strip() for part in plain.split("+"))
    if tokens and all(t in VOCABULARY for t in tokens):
        return tokens
    return None


def extract_verdicts(paths: list[Path]) -> Extraction:
    entries: list[RecordedVerdict] = []
    malformed: list[tuple[Path, int, str]] = []
    skipped = 0
    for path in paths:
        verdict_col: int | None = None
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            cells = _split_markdown_row(line)
            if not cells:
                continue
            lowered = [cell.strip().lower() for cell in cells]
            if "verdict" in lowered:
                verdict_col = lowered.index("verdict")
                continue
            if set(cells[0]) <= {"-", ":"}:
                continue
            key = _key_from_cells(cells)
            if key is None:
                bad = _malformed_key(cells)
                if bad is not None:
                    malformed.append((path, line_no, bad))
                continue
            verdicts = (_verdicts_from_cell(cells[verdict_col])
                        if verdict_col is not None and verdict_col < len(cells) else None)
            if verdicts is None:
                skipped += 1
                continue
            entries.append(RecordedVerdict(path, line_no, key[0], key[1], verdicts))
    return Extraction(tuple(entries), skipped, tuple(malformed))


def ledger_violations(extraction: Extraction, reviewed: dict) -> list[str]:
    out = []
    for entry in extraction.entries:
        disposition = (reviewed.get(entry.review_key) or {}).get("disposition")
        where = f"{entry.path.name}:{entry.line_no} {entry.frame_key}"
        if "REFUTED" in entry.verdicts and disposition != "refuted":
            out.append(f"{where}: REFUTED verdict has ledger disposition {disposition!r}")
        if "TRANSPOSITION" in entry.verdicts and disposition != "transposition":
            out.append(f"{where}: TRANSPOSITION verdict has ledger disposition {disposition!r}")
        if "UN-VOID" in entry.verdicts and disposition in VOIDING_DISPOSITIONS:
            out.append(f"{where}: UN-VOID verdict still has voiding disposition {disposition!r}")
    return out


@pytest.mark.req("REQ-TUNE-0038")
def test_ruling_record_parser_controls(tmp_path):
    record = tmp_path / "fixture-rulings.md"
    record.write_text(
        "\n".join([
            "| frame | packet rec | verdict |",
            "|---|---|---|",
            "| `1\\|0\\|decision\\|2` | CONFORM | **REFUTED** |",
            "| `1\\|0\\|decision\\|3` | **CONFORM** | **REFUTED** |",
            "| frame | verdict |",
            "|---|---|",
            "| `3\\|1\\|turn\\|4` | **REVERT** + UN-VOID |",
            "| frame | agent | verdict |",
            "|---|---|---|",
            "| `4\\|1\\|match\\|` | x | **TRANSPOSITION** |",
            "| `5\\|0\\|decision\\|6` | CONFORM | no bold verdict |",
            "| `6\\|0\\|decision\\|nope` | x | **REFUTED** |",
        ]) + "\n",
        encoding="utf-8",
    )

    extracted = extract_verdicts([record])

    assert [(e.review_key, e.verdicts) for e in extracted.entries] == [
        ("1-2", ("REFUTED",)),
        ("1-3", ("REFUTED",)),
        ("3-t4s1", ("REVERT", "UN-VOID")),
        ("4-m1", ("TRANSPOSITION",)),
    ]
    assert extracted.skipped_key_rows == 1
    assert [(line_no, bad) for _path, line_no, bad in extracted.malformed_key_rows] == [
        (12, "6\\|0\\|decision\\|nope")
    ]


@pytest.mark.req("REQ-TUNE-0038")
def test_real_ruling_records_extract_the_known_spot_controls():
    extracted = extract_verdicts(RULING_RECORDS)
    by_key = {e.review_key: e for e in extracted.entries}

    assert by_key["81785223-32"].verdicts == ("REFUTED",)
    assert by_key["86090164-t2s1"].verdicts == ("REVERT",)
    assert extracted.skipped_key_rows > 0
    assert extracted.malformed_key_rows == ()


@pytest.mark.req("REQ-TUNE-0038")
def test_every_recorded_voiding_verdict_is_applied_to_the_reviewed_ledger():
    extracted = extract_verdicts(RULING_RECORDS)
    reviewed = json.loads(REVIEWED.read_text(encoding="utf-8"))

    assert ledger_violations(extracted, reviewed) == []


@pytest.mark.req("REQ-TUNE-0038")
def test_the_guard_catches_the_81785223_44_downgrade_regression():
    extracted = extract_verdicts(RULING_RECORDS)
    reviewed = json.loads(REVIEWED.read_text(encoding="utf-8"))
    reviewed["81785223-44"] = {
        "disposition": "covered",
        "reason": "Current Pilot exactly matches the human ruling (Play Pokegear 3.0).",
        "round": "2026-08-03",
    }

    assert ledger_violations(extracted, reviewed) == [
        "wave3-rulings.md:36 81785223|0|decision|44: "
        "REFUTED verdict has ledger disposition 'covered'"
    ]
