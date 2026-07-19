"""Effect-Clause loader for the Pilot (see common/CONTEXT.md: Effect Clause).

`CardEffects` wraps the shipped, offline-built `card_effects.json`
(`{cardId: [{kind, amount?, restriction?, rider?, …}]}`) produced by
`tools/build_card_effects.py` — the parametric counterpart of `CardFunctions`
(`common/cards.py`): the tag says *that* a card heals/fetches, the clause says *how much*
/ *what predicate*. Same doctrine: **partial and additive** — an unknown card has no
clauses, a missing file degrades to empty, O(1) lookup per decision. Wired into the Pilot
via `Pilot(effects=...)`. Clause kinds:
  - `heal`  (probe-measured + curated): amount/rider/restriction/condition — `planner._heal_candidate` (ADR-0032 4b).
  - `draw`  (probe-measured): the top-deck draw count of a Trainer.
  - `fetch` (curated override-only, `effect_overrides.json`): a tutor/recycle PREDICATE the boolean
    Function Tag can't carry — `{target, zone, energy_type?, no_rule_box?, hp_max?}` (Fighting Gong's
    {F}-lock is `energy_type: 6`). Read by the gamble fetch-closure (`planner._fetch_reaches_slot` /
    `_fetch_reaches_pokemon`, hypergeometric-fetch-closure WP1/WP5) — so the closure never parses text.
"""
from __future__ import annotations

import json
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent / "card_effects.json"


class CardEffects:
    def __init__(self, table: dict):
        self._table = {int(k): tuple(dict(c) for c in v) for k, v in table.items()}

    def clauses(self, card_id: int) -> tuple[dict, ...]:
        """Effect Clauses for a card; () if the card has none (yet)."""
        return self._table.get(card_id, ())

    @classmethod
    def load(cls, path=None) -> "CardEffects":
        p = Path(path) if path is not None else _DEFAULT
        if p.exists():
            return cls(json.loads(p.read_text(encoding="utf-8")))
        return cls({})
