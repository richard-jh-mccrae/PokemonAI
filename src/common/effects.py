"""Effect-Clause loader for the Pilot (see common/CONTEXT.md: Effect Clause).

`CardEffects` wraps the offline-built `card_effects.json` — the PARAMETRIC counterpart of
`CardFunctions`: the tag says *that* a card heals/fetches, the clause says *how much* / *what
predicate*. Partial and additive: an unknown card has no clauses, a missing file degrades to empty.

Beside the clauses the file carries ONE reserved key, `_covers` (Issue #300) — the per-card verdict
on whether the clause SET covers the whole printed effect. It never reaches :meth:`clauses`; the
apply seam reads :meth:`clauses_cover`, so a partially-modelled card REFUSES rather than pricing the
missing part at 0.
"""
from __future__ import annotations

import json
from pathlib import Path

from common import snapshot_coverage

_DEFAULT = Path(__file__).resolve().parent / "card_effects.json"


class CardEffects:
    def __init__(self, table: dict):
        self._table = {cid: tuple(dict(c) for c in cls)
                       for cid, cls in snapshot_coverage.clause_lists(table).items()}
        self._covers = snapshot_coverage.covers_table(table)

    def clauses(self, card_id: int) -> tuple[dict, ...]:
        """Effect Clauses for a card; () if the card has none (yet)."""
        return self._table.get(card_id, ())

    def covers(self, card_id: int) -> str | None:
        """``"full"`` / ``"partial"`` / `None` — does this card's clause set cover the whole printed
        effect? `None` is *unruled*, which is a different fact from *ruled incomplete*."""
        entry = self._covers.get(int(card_id))
        return entry.get("covers") if entry else None

    def clauses_cover(self, card_id: int) -> bool | None:
        """:meth:`covers` as the tri-state `apply_option.fate` takes. Both falsey answers fail closed but
        stay DISTINCT: unruled is a work item, partial is a measured gap."""
        return snapshot_coverage.clauses_cover(self.covers(card_id))

    @classmethod
    def load(cls, path=None) -> "CardEffects":
        p = Path(path) if path is not None else _DEFAULT
        if p.exists():
            return cls(json.loads(p.read_text(encoding="utf-8")))
        return cls({})
