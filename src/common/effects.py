"""Effect-Clause loader for the Pilot (see common/CONTEXT.md: Effect Clause).

`CardEffects` wraps the shipped, offline-built `card_effects.json`
(`{cardId: [{kind, amount?, restriction?, rider?, …}]}`) produced by
`tools/build_card_effects.py` — the parametric counterpart of `CardFunctions`
(`common/cards.py`): the tag says *that* a card heals/fetches, the clause says *how much*
/ *what predicate*. Same doctrine: **partial and additive** — an unknown card has no
clauses, a missing file degrades to empty, O(1) lookup per decision. Wired into the Pilot
via `Pilot(effects=...)`. Clause kinds:
  - `heal`  (probe-measured + curated): amount/rider/restriction/condition — `planner._heal_candidate` (ADR-0032 4b).
  - `draw`  (probe-measured): the top-deck draw count of a Trainer. A magnitude may also be
    BOARD-SCALED (Issue #349): `amount_per` multiplies `amount` by the COUNT of a named board set,
    `each_of` applies the full `amount` to EVERY body the clause's `target` names. Why they are two
    keys is ruled in `snapshot_coverage`'s module docstring; why `planner._heal_candidate` reads
    NEITHER is ruled in its own.
  - `fetch` (curated override-only, `effect_overrides.json`): a tutor/recycle PREDICATE the boolean
    Function Tag can't carry — `{target, zone, energy_type?, no_rule_box?, hp_max?}` (Fighting Gong's
    {F}-lock is `energy_type: 6`). Read by the gamble fetch-closure (`planner._fetch_reaches_slot` /
    `_fetch_reaches_pokemon`, hypergeometric-fetch-closure WP1/WP5) — so the closure never parses text.

Beside the numeric entries the file carries ONE reserved key, `_covers`
(`snapshot_coverage.COVERS_KEY`, Issue #300): the per-card verdict on whether the clause SET covers
the card's whole printed effect. It is not a clause and never reaches :meth:`CardEffects.clauses` —
:meth:`CardEffects.clauses_cover` is what the apply seam reads, so a card whose clauses model three
quarters of it REFUSES rather than pricing the missing quarter at 0.
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
        """:meth:`covers` as the tri-state `apply_option.fate` takes for ``clauses_cover``.

        The consumer-facing seam: full → `True`, partial → `False`, unruled → `None`. Both falsey
        answers fail closed, and they stay distinguishable because *nobody has ruled this* is a work
        item while *the clauses are known to be incomplete* is a measured gap."""
        return snapshot_coverage.clauses_cover(self.covers(card_id))

    @classmethod
    def load(cls, path=None) -> "CardEffects":
        p = Path(path) if path is not None else _DEFAULT
        if p.exists():
            return cls(json.loads(p.read_text(encoding="utf-8")))
        return cls({})
