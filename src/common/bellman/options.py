"""Legal engine-menu enumeration with stable semantic identities; no ranking."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import json
from typing import Mapping

from common.option_equivalence import semantic_option_fingerprint, without_engine_serial

from .api import ActionIdentity


_KIND_NAMES = {
    0: "number", 1: "yes", 2: "no", 3: "card", 4: "tool_card", 5: "energy_card",
    6: "energy", 7: "play", 8: "attach", 9: "evolve", 10: "ability", 11: "discard",
    12: "retreat", 13: "attack", 14: "end", 15: "skill", 16: "special_condition",
}


def _card_from_select(observation: Mapping, option: Mapping, area_key: str, index_key: str):
    area, index = option.get(area_key), option.get(index_key)
    if not isinstance(index, int) or index < 0:
        return None
    select = observation.get("select") or {}
    if area == 1:
        cards = select.get("deck") or []
    elif area == 12:
        cards = ((observation.get("current") or {}).get("looking") or [])
    else:
        return None
    return cards[index] if index < len(cards) else None


def _fingerprint(observation: Mapping, option: Mapping) -> str:
    found = semantic_option_fingerprint(dict(option), dict(observation))
    if found is not None:
        return found
    enriched = []
    referenced = set()
    for area_key, index_key in (("area", "index"), ("inPlayArea", "inPlayIndex")):
        if option.get(area_key) not in (1, 12):
            continue
        card = _card_from_select(observation, option, area_key, index_key)
        if card is not None:
            referenced.update((area_key, index_key))
            enriched.append((int(option[area_key]), without_engine_serial(card)))
    public = {key: without_engine_serial(value) for key, value in sorted(option.items())
              if key not in referenced and not str(key).startswith("_")}
    return json.dumps([public, enriched], sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class LegalAction:
    identity: ActionIdentity
    selection: tuple[int, ...]
    equivalent_selections: tuple[tuple[int, ...], ...]
    options: tuple[tuple, ...]

    @property
    def representative(self) -> int:
        if len(self.selection) != 1:
            raise ValueError("multi-pick actions have no scalar representative")
        return self.selection[0]

    @property
    def menu_indices(self) -> tuple[int, ...]:
        """Compatibility name: the exact engine selection, not an equivalence class."""
        return self.selection


def enumerate_legal_actions(observation: Mapping) -> tuple[LegalAction, ...]:
    """Group semantically interchangeable physical copies; cover every offered index exactly once."""
    options = ((observation.get("select") or {}).get("option") or ())
    select = observation.get("select") or {}
    minimum, maximum = int(select.get("minCount", 1)), int(select.get("maxCount", 1))
    maximum = min(maximum, len(options))
    groups: dict[tuple[str, tuple[str, ...]], list[tuple[int, ...]]] = {}
    for count in range(max(0, minimum), maximum + 1):
        for selection in combinations(range(len(options)), count):
            kinds = tuple(_KIND_NAMES.get(options[index].get("type"),
                                          f"option_{options[index].get('type')}")
                          for index in selection)
            kind = "decline" if not selection else kinds[0] if len(set(kinds)) == 1 else "selection"
            fingerprints = tuple(sorted(_fingerprint(observation, options[index])
                                        for index in selection))
            groups.setdefault((kind, fingerprints), []).append(selection)
    actions = []
    for (kind, fingerprints), selections in groups.items():
        representative = min(selections)
        actions.append(LegalAction(
            identity=ActionIdentity(kind, fingerprints),
            selection=representative,
            equivalent_selections=tuple(sorted(selections)),
            options=tuple(tuple(sorted(without_engine_serial(dict(options[index])).items()))
                          for index in representative),
        ))
    return tuple(sorted(actions, key=lambda action: (action.identity, action.selection)))


def end_action(actions: tuple[LegalAction, ...]) -> LegalAction | None:
    return next((action for action in actions if action.identity.kind == "end"), None)


__all__ = ("LegalAction", "end_action", "enumerate_legal_actions")
