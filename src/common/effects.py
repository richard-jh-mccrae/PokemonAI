"""Effect-clause data consumed by Bellman transition reconstruction."""
from __future__ import annotations

import json
from pathlib import Path

from .card_tags import is_card_key


_DEFAULT = Path(__file__).with_name("card_effects.json")


class CardEffects:
    def __init__(self, table: dict):
        table = table or {}
        self._table = {
            int(card_id): tuple(dict(clause) for clause in clauses)
            for card_id, clauses in table.items()
            if is_card_key(card_id) and isinstance(clauses, list)
        }
        coverage = table.get("_covers") or {}
        self._full = frozenset(
            int(card_id) for card_id, verdict in coverage.items()
            if is_card_key(card_id) and isinstance(verdict, dict)
            and verdict.get("covers") == "full"
        )

    def clauses(self, card_id: int) -> tuple[dict, ...]:
        return self._table.get(int(card_id), ())

    def fully_covers(self, card_id: int) -> bool:
        return int(card_id) in self._full

    @classmethod
    def load(cls, path=None) -> "CardEffects":
        source = Path(path) if path is not None else _DEFAULT
        return cls(json.loads(source.read_text(encoding="utf-8")) if source.exists() else {})


def terminal_effects_supported(state, action, *, card_id, recipient_id, effects, stats) -> bool:
    """Whether this action's effects are modelled exactly enough for sound reasoning."""
    kind = action.identity.kind
    stat = stats.get(card_id) if stats is not None and card_id is not None else None
    clauses = effects.clauses(card_id) if effects is not None and card_id is not None else ()
    fully_covered = bool(
        effects is not None and card_id is not None and hasattr(effects, "fully_covers")
        and effects.fully_covers(card_id))
    if kind in {"play", "evolve", "ability", "skill"}:
        if card_id is None:
            return False
        pokemon_without_ability = bool(
            kind in {"play", "evolve"} and stat is not None
            and getattr(stat, "is_pokemon", False)
            and not getattr(stat, "hasAbility", False))
        if not pokemon_without_ability and not fully_covered:
            return False
    if kind == "attach":
        if stat is None or not (getattr(stat, "is_basic_energy", False) or fully_covered):
            return False
        recipient_stat = (stats.get(recipient_id)
                          if stats is not None and recipient_id is not None else None)
        if recipient_stat is not None and getattr(recipient_stat, "hasAbility", False):
            if (effects is None or not hasattr(effects, "fully_covers")
                    or not effects.fully_covers(recipient_id)):
                return False
            clauses = (*clauses, *effects.clauses(recipient_id))
    if any(clause.get("kind") == "draw" or clause.get("dig") for clause in clauses):
        return False
    if (any(clause.get("kind") == "fetch" and clause.get("zone") == "deck"
            for clause in clauses) and "own_prizes" not in state.obs):
        return False
    if kind == "attack" and len(action.selection) == 1:
        options = tuple((state.obs.get("select") or {}).get("option") or ())
        index = action.selection[0]
        option = options[index] if 0 <= index < len(options) else {}
        attack = (stats.attack(option.get("attackId"))
                  if stats is not None and hasattr(stats, "attack") else None)
        if attack is None or int(getattr(attack, "hiddenPerUnit", 0) or 0) > 0:
            return False
    return True


__all__ = ("CardEffects", "terminal_effects_supported")
