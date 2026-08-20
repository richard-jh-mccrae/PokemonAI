"""Legal engine-menu enumeration with stable semantic identities; no ranking."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import json
from typing import Mapping

from common.option_equivalence import semantic_option_fingerprint, without_engine_serial
from common.strategy.context import (
    _ABILITY, _ACTIVE, _ATTACH, _ATTACHED_TOOL, _ATTACK, _BENCH, _CARD, _DECK,
    _DISCARD_IN_PLAY, _END, _ENERGY, _ENERGY_CARD, _EVOLVE, _HAND, _LOOKING, _NO, _NUMBER,
    _PLAY, _RETREAT, _SKILL,
    _SPECIAL_CONDITION, _YES,
)

from .api import ActionIdentity


_KIND_NAMES = {
    _NUMBER: "number", _YES: "yes", _NO: "no", _CARD: "card", _ATTACHED_TOOL: "tool_card",
    _ENERGY_CARD: "energy_card", _ENERGY: "energy", _PLAY: "play", _ATTACH: "attach",
    _EVOLVE: "evolve", _ABILITY: "ability", _DISCARD_IN_PLAY: "discard", _RETREAT: "retreat",
    _ATTACK: "attack", _END: "end", _SKILL: "skill", _SPECIAL_CONDITION: "special_condition",
}
DEFAULT_PICK_COUNT = 1

#: Bounds a combinatorial choose-up-to-N menu (largest observed ~400 selections); cheapest
#: counts enumerate first, so the decline/minimum submissions always survive the cap.
SELECTION_ENUMERATION_CAP = 4096


def _card_from_select(observation: Mapping, option: Mapping, area_key: str, index_key: str):
    area, index = option.get(area_key), option.get(index_key)
    if not isinstance(index, int) or index < 0:
        return None
    select = observation.get("select") or {}
    if area == _DECK:
        cards = select.get("deck") or []
    elif area == _LOOKING:
        cards = ((observation.get("current") or {}).get("looking") or [])
    else:
        return None
    return cards[index] if index < len(cards) else None


def _fingerprint(observation: Mapping, option: Mapping) -> str:
    semantic = {key: value for key, value in option.items() if value is not None}
    # MAIN PLAY options identify a card by its hand index but omit the redundant HAND area.  Add
    # that structural reference for identity only, so two physical copies cannot consume two beam
    # slots.  The representative still submits the engine's original index.
    if (semantic.get("type") == _PLAY and "area" not in semantic
            and isinstance(semantic.get("index"), int)):
        semantic["area"] = _HAND
    found = semantic_option_fingerprint(semantic, dict(observation))
    if found is not None:
        return found
    enriched = []
    referenced = set()
    for area_key, index_key in (("area", "index"), ("inPlayArea", "inPlayIndex")):
        if semantic.get(area_key) not in (_DECK, _LOOKING):
            continue
        card = _card_from_select(observation, semantic, area_key, index_key)
        if card is not None:
            referenced.update((area_key, index_key))
            enriched.append((int(semantic[area_key]), without_engine_serial(card)))
    public = {key: without_engine_serial(value) for key, value in sorted(semantic.items())
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
    select = observation.get("select") or {}
    # Junk rows keep their index (every offered index stays covered) but read as typeless;
    # min/max may arrive present-but-None on the deployed dialect — `or` would eat a legal 0.
    options = tuple(entry if isinstance(entry, dict) else {}
                    for entry in select.get("option") or ())
    raw_minimum = select.get("minCount", DEFAULT_PICK_COUNT)
    raw_maximum = select.get("maxCount", DEFAULT_PICK_COUNT)
    minimum = DEFAULT_PICK_COUNT if raw_minimum is None else int(raw_minimum)
    maximum = DEFAULT_PICK_COUNT if raw_maximum is None else int(raw_maximum)
    maximum = min(maximum, len(options))
    minimum = min(minimum, maximum)                  # an impossible ask still submits its closest
    groups: dict[tuple[str, tuple[str, ...]], list[tuple[int, ...]]] = {}
    budget = SELECTION_ENUMERATION_CAP
    for count in range(max(0, minimum), maximum + 1):
        if budget <= 0:
            break
        for selection in combinations(range(len(options)), count):
            if budget <= 0:
                break
            budget -= 1
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


def recycled_card_ids(observation: Mapping, action: LegalAction, registry, root_seat: int):
    carried = tuple(observation.get("bellmanRecycledCardIds") or ())
    if action.identity.kind != "ability" or len(action.selection) != 1 or registry is None:
        return carried
    options = tuple((observation.get("select") or {}).get("option") or ())
    option_index = action.selection[0]
    if not 0 <= option_index < len(options):
        return carried
    option = options[option_index]
    current = observation.get("current") or {}
    players = current.get("players") or ()
    seat = int(observation.get("bellmanActor", root_seat))
    player = players[seat] if 0 <= seat < len(players) else {}
    area, index = option.get("inPlayArea", option.get("area")), option.get(
        "inPlayIndex", option.get("index"))
    bodies = (player.get("active") if area == _ACTIVE else
              player.get("bench") if area == _BENCH else ()) or ()
    body = bodies[index] if isinstance(index, int) and 0 <= index < len(bodies) else None
    card_id = int(body.get("id", 0)) if body else 0
    if "recycle_line" not in registry.functions.get(card_id, ()):
        return carried
    stack = tuple(int(card.get("id", 0)) for card in body.get("preEvolution") or ())
    return tuple(dict.fromkeys((*carried, *stack, card_id)))


__all__ = ("LegalAction", "end_action", "enumerate_legal_actions", "recycled_card_ids")
