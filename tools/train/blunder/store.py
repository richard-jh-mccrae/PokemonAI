"""Per-build JSONL store for Corrections — the "correction log" (ADR-0009, ADR-0015).

Filed by the build that played the game; unparseable build identity goes to ``_unfiled/``. A
``.jsonl`` path addresses one file, a directory the whole tree.

Reads are deduplicated by Scope subject (ADR-0049), because a duplicate otherwise amplifies the
weight fit; a differing category/correct on the same subject is a *conflict* and is kept. The
on-disk file stays append-only.
"""
from __future__ import annotations

import json
from pathlib import Path

from .correction import Correction, identity_key


def _dedup_key(c: Correction):
    """Keyed by the Scope subject (ADR-0049), never the Anchor frame, so the same Turn tagged from
    two frames is one blunder."""
    return (*identity_key(c), tuple(c.chosen), tuple(c.correct), c.category)


def dedup_corrections(corrections) -> list[Correction]:
    """Keeps the LATEST per key. Differing category/correct on one decision is a conflict, not a
    duplicate, and all of those are kept."""
    seen: dict = {}
    for c in corrections:
        seen[_dedup_key(c)] = c          # last occurrence wins; dict keeps first-seen order
    return list(seen.values())


def find_conflicts(corrections) -> list:
    """``[(key, [corrections])]`` for subjects carrying >1 distinct judgment after dedup — genuine
    disagreements for a human to resolve."""
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


def jsonl_files(source: Path | str) -> list[Path]:
    """Public because the store owns where the logs LIVE (ADR-0087 decision 1): a caller needing
    per-file provenance asks here rather than re-deriving the layout with its own glob."""
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
    for f in jsonl_files(source):
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
    for f in jsonl_files(source):
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(Correction.from_dict(json.loads(line)))
    return dedup_corrections(out) if dedup else out
