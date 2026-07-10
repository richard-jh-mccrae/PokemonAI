"""Per-build JSONL store for Corrections -- the "correction log" (ADR-0009, ADR-0015).

Corrections are filed by the **build that played the game**, mirroring ``data/replays/<stem>/``:
``data/corrections/<agent_build>/corrections.jsonl`` (e.g. ``mega_starmie_20260625_bde590c/``),
so at competition end you can track which agent/build had which corrections over time. Routing is
automatic -- a Correction carries its ``agent_build`` (ADR-0015), so ``append_correction`` files it
in the right subdir; corrections with no parseable build identity go to ``_unfiled/``. Each file is
append-only JSONL (gold, committed). A ``.jsonl`` path addresses one file; a directory addresses the
whole tree (``load_corrections`` unions + dedups every ``<build>/corrections.jsonl`` under it).

Reads are **deduplicated** by default (``load_corrections``): the same *subject* tagged twice
(same episode/seat/scope/subject/chosen/correct/category) is one blunder, so consumers (Tuner, report,
``/blunder-buster``, the inspector list) see it once -- duplicates otherwise amplify the weight
fit and inflate counts. A different category/correct on the same subject is a *conflict*, kept.
The subject is the Anchor frame for a decision Correction and the Turn / seat for a scoped one
(ADR-0049), so a Turn Correction never collides with the Decision Corrections inside that Turn.
The on-disk file stays append-only; ``tools/train/dedup_corrections.py`` physically compacts it.
"""
from __future__ import annotations

import json
from pathlib import Path

from .correction import Correction, identity_key


def _dedup_key(c: Correction):
    """What makes two Corrections 'identical in nature' (one blunder, not two).

    Keyed by the Scope's subject (ADR-0049), never the Anchor frame — so the same Turn tagged
    from two frames is one blunder. For a decision-scope record the subject *is* the frame, so
    this is byte-identical to the pre-Scope key.
    """
    return (*identity_key(c), tuple(c.chosen), tuple(c.correct), c.category)


def dedup_corrections(corrections) -> list[Correction]:
    """Collapse exact-duplicate Corrections, keeping the LATEST per key (its refined rationale /
    identity). Corrections that differ in category or correct on the same decision are conflicts,
    not duplicates -- all are kept. The same frame in a different episode is a distinct blunder."""
    seen: dict = {}
    for c in corrections:
        seen[_dedup_key(c)] = c          # last occurrence wins; dict keeps first-seen order
    return list(seen.values())


def find_conflicts(corrections) -> list:
    """Subjects (episode, seat, scope, subject) tagged with >1 distinct judgment (category/correct)
    after dedup -- genuine disagreements for a human to resolve, not duplicates. Returns
    [(key, [corr])]."""
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for c in dedup_corrections(corrections):
        groups[identity_key(c)].append(c)
    return [(k, v) for k, v in groups.items()
            if len({(c.category, tuple(c.correct)) for c in v}) > 1]

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "corrections"
DEFAULT_PATH = DEFAULT_ROOT          # back-compat alias; default store is now the tree root
_UNFILED = "_unfiled"


def corrections_path_for(agent_build: str | None, root: Path | str = DEFAULT_ROOT) -> Path:
    """The per-build correction log for ``agent_build`` (``_unfiled/`` when None/empty)."""
    return Path(root) / (agent_build or _UNFILED) / "corrections.jsonl"


def _is_file(source: Path | str) -> bool:
    return str(source).endswith(".jsonl")


def _jsonl_files(source: Path | str) -> list[Path]:
    """Log file(s) a source denotes: a ``.jsonl`` path -> itself; a directory -> every
    ``<build>/corrections.jsonl`` under it (plus a legacy root-level ``corrections.jsonl``)."""
    source = Path(source)
    if _is_file(source):
        return [source] if source.exists() else []
    if not source.is_dir():
        return []
    legacy = source / "corrections.jsonl"
    return ([legacy] if legacy.exists() else []) + sorted(source.glob("*/corrections.jsonl"))


def append_correction(correction: Correction, dest: Path | str = DEFAULT_ROOT) -> Path:
    """Append one Correction. ``dest`` may be an exact ``.jsonl`` file, or a root directory --
    then it routes to ``<root>/<agent_build>/corrections.jsonl`` for per-build traceability."""
    file = Path(dest) if _is_file(dest) else corrections_path_for(correction.agent_build, dest)
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(correction.to_dict(), ensure_ascii=False) + "\n")
    return file


def delete_correction(corr_id: str, source: Path | str = DEFAULT_ROOT) -> int:
    """Remove the Correction with ``corr_id`` wherever it lives (file or tree). Returns count removed."""
    removed = 0
    for f in _jsonl_files(source):
        items = load_corrections(f, dedup=False)
        keep = [c for c in items if c.id != corr_id]
        if len(keep) != len(items):
            with f.open("w", encoding="utf-8") as fh:
                for c in keep:
                    fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
            removed += len(items) - len(keep)
    return removed


def load_corrections(source: Path | str = DEFAULT_ROOT, *, dedup: bool = True) -> list[Correction]:
    """Load Corrections from a ``.jsonl`` file or an entire correction tree (directory). Dedup by
    default (see module docstring); ``dedup=False`` for the raw append history. Missing -> []."""
    out: list[Correction] = []
    for f in _jsonl_files(source):
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(Correction.from_dict(json.loads(line)))
    return dedup_corrections(out) if dedup else out
