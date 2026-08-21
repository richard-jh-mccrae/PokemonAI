"""Merge the measured and authored effect-clause sources for the record builder (ADR-0153).

The merged table no longer ships anywhere: `build_pokemon_cards.py` bakes it into the card
record modules, the one definition per card. The teacher's frozen copy lives at
`deprecated/bellman/card_effects.json` and is deliberately never regenerated."""
from __future__ import annotations

import json
from pathlib import Path

from meta_tracker.card_effects import apply_overrides


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OVERRIDES = REPO / "tools" / "meta_tracker" / "effect_overrides.json"
DEFAULT_MEASURED = REPO / "tools" / "meta_tracker" / "measured_effects.json"


def load_effects(measured_path=None, overrides_path=None) -> tuple[dict, dict]:
    """(clauses by card id, covers verdict by card id), merged measured-then-authored."""
    measured = json.loads(Path(measured_path or DEFAULT_MEASURED).read_text(encoding="utf-8"))
    overrides = json.loads(Path(overrides_path or DEFAULT_OVERRIDES).read_text(encoding="utf-8"))
    table = {int(key): value for key, value in measured.items() if str(key).isdigit()}
    authored = {int(key): value for key, value in overrides.items() if str(key).isdigit()}
    merged = apply_overrides(table, authored)
    verdicts = overrides.get("_covers", measured.get("_covers", {}))
    covers = {int(key): row["covers"] for key, row in verdicts.items()
              if str(key).isdigit() and isinstance(row, dict) and row.get("covers")}
    return merged, covers


__all__ = ("DEFAULT_MEASURED", "DEFAULT_OVERRIDES", "load_effects")
