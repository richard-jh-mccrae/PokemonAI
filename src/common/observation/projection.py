from __future__ import annotations

from copy import deepcopy
from collections import Counter
from dataclasses import dataclass
from enum import Enum

from common.options import enumerate_legal_actions
from common.strategy.context import _BENCH, _CARD, _HAND, _MAIN, _TO_ACTIVE
from .event_visibility import EVENT_FIELDS, visible_event


class ProjectionError(ValueError):
    pass


class SelectionVisibility(str, Enum):
    FOCAL = "focal"
    PUBLIC = "public"
    PRIVATE = "private"
    BOUNDARY = "boundary"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class SelectionControl:
    actor_seat: int | None
    context: int | None
    visibility: SelectionVisibility
    actions: tuple = ()


def selection_control(raw, seat, actor):
    current = raw.get("current") or {}
    if current.get("result") not in (None, -1):
        return SelectionControl(None, None, SelectionVisibility.TERMINAL)
    select = raw.get("select")
    if actor not in (0, 1) or not isinstance(select, dict):
        raise ProjectionError("pending selection actor unavailable")
    context = select.get("context")
    if context is None:
        raise ProjectionError("pending selection context unavailable")
    if actor == seat:
        return SelectionControl(actor, int(context), SelectionVisibility.FOCAL)
    if context == _MAIN:
        return SelectionControl(actor, int(context), SelectionVisibility.BOUNDARY)
    actions = _promotion_actions(raw, actor) if context == _TO_ACTIVE else ()
    visibility = SelectionVisibility.PUBLIC if actions else SelectionVisibility.PRIVATE
    return SelectionControl(actor, int(context), visibility, actions)


def _promotion_actions(raw, actor):
    select = raw["select"]
    player = raw["current"]["players"][actor]
    bench = player.get("bench") or ()
    options = select.get("option") or ()
    if (player.get("active") or not bench or any(not card or not card.get("id") for card in bench)
            or select.get("minCount") != 1 or select.get("maxCount") != 1
            or len(options) != len(bench)):
        return ()
    expected = [{"type": _CARD, "area": _BENCH, "index": index, "playerIndex": actor}
                for index in range(len(bench))]
    offered = [{key: value for key, value in option.items() if value is not None}
               for option in options]
    if any(option not in expected for option in offered) or len({o["index"] for o in offered}) != len(bench):
        return ()
    public = {"current": {**raw["current"], "yourIndex": actor}, "select": {
        "type": 1, "context": _TO_ACTIVE, "minCount": 1, "maxCount": 1, "option": offered}}
    return enumerate_legal_actions(public)


def _public_cards(raw):
    current = raw.get("current") or {}
    cards = list(current.get("stadium") or ())
    for player in current.get("players") or ():
        for zone in ("active", "bench", "discard"):
            cards.extend(player.get(zone) or ())
    found = set()
    while cards:
        card = cards.pop()
        if not isinstance(card, dict):
            continue
        if card.get("serial") is not None and card.get("id") is not None:
            found.add((card["serial"], card["id"]))
        for zone in ("preEvolution", "energyCards", "tools"):
            cards.extend(card.get(zone) or ())
    return found


def _taken_known_prizes(raw, parent, seat, known_prizes):
    known = Counter(dict(known_prizes))
    before = parent["current"]["players"][seat].get("prize") or ()
    after = raw["current"]["players"][seat].get("prize") or ()
    if sum(known.values()) != len(before) or any(not card or not card.get("id") for card in after):
        return []
    remaining = Counter(card["id"] for card in after)
    taken = known - remaining
    if remaining - known or sum(taken.values()) != len(before) - len(after):
        return []
    return [{"id": card_id} for card_id in sorted(taken.elements())]


def _recover_hand(raw, parent, seat, known_prizes):
    player = raw["current"]["players"][seat]
    count = player.get("handCount", 0)
    hand = player.get("hand")
    if isinstance(hand, list) and len(hand) == count:
        return hand
    previous = parent["current"]["players"][seat].get("hand")
    logs = raw.get("logs") or ()
    if not isinstance(previous, list) or not logs:
        raise ProjectionError("focal hand cannot be recovered faithfully")
    hand = deepcopy(previous)
    known_taken = _taken_known_prizes(raw, parent, seat, known_prizes)
    public_before = _public_cards(parent)
    removed = set()
    for row in logs:
        if not isinstance(row, dict) or row.get("type") not in EVENT_FIELDS:
            raise ProjectionError("focal hand update has unknown events")
        if row.get("playerIndex") != seat:
            continue
        kind = row.get("type")
        enters = kind == 4 or kind == 6 and row.get("toArea") == _HAND
        leaves = kind in (10, 11, 12) or kind == 6 and row.get("fromArea") == _HAND
        if kind == 7 and row.get("fromArea") == 6 and row.get("toArea") == _HAND and known_taken:
            hand.append(known_taken.pop(0))
            continue
        if kind == 5 or kind == 7 and _HAND in (row.get("fromArea"), row.get("toArea")):
            raise ProjectionError("focal hand update is hidden from the source viewer")
        if not enters and not leaves:
            continue
        serial, card_id = row.get("serial"), row.get("cardId")
        if serial is None or card_id is None:
            raise ProjectionError("focal hand update lacks card identity")
        matches = [card for card in hand if card.get("serial") == serial and card.get("id") == card_id]
        if leaves:
            if matches:
                hand.remove(matches[0])
                removed.add(serial)
            elif kind == 6 and serial not in removed and (serial, card_id) not in public_before:
                raise ProjectionError("focal hand removal cannot be reconciled")
        if enters and not matches:
            hand.append({"id": card_id, "serial": serial, "playerIndex": seat})
    if len(hand) != count:
        raise ProjectionError("focal hand count cannot be reconciled")
    return hand


def _event_stamp(row):
    if not isinstance(row, dict):
        return None
    kind = row.get("type")
    if kind in (4, 5):
        return 5, row.get("playerIndex")
    if kind in (6, 7):
        return 7, row.get("playerIndex"), row.get("fromArea"), row.get("toArea")
    return kind, tuple(sorted((key, value) for key, value in row.items() if value is not None))


def _fresh_logs(raw, parent):
    logs = raw.get("logs") or ()
    parent_logs = parent.get("logs") or ()
    anchors = {tuple(sorted((key, value) for key, value in row.items() if value is not None))
               for row in parent_logs if isinstance(row, dict) and row.get("serial") is not None
               and row.get("type") not in (4, 5)}
    if not any(tuple(sorted((key, value) for key, value in row.items() if value is not None)) in anchors
               for row in logs if isinstance(row, dict)):
        return logs
    previous = tuple(_event_stamp(row) for row in parent_logs)
    if not previous or None in previous:
        return logs
    stamps = tuple(_event_stamp(row) for row in logs)
    matches = [index + len(previous) for index in range(len(stamps) - len(previous) + 1)
               if stamps[index:index + len(previous)] == previous]
    return logs[matches[0]:] if len(matches) == 1 else logs


def project_successor(raw, parent, seat, *, source_seat, actor_seat, known_prizes=()):
    if source_seat not in (0, 1):
        raise ProjectionError("source viewer unavailable")
    control = selection_control(raw, seat, actor_seat)
    observation = deepcopy(raw)
    if source_seat != parent["current"].get("yourIndex"):
        observation["logs"] = _fresh_logs(raw, parent)
    current = observation["current"]
    current["players"][seat]["hand"] = _recover_hand(observation, parent, seat, known_prizes)
    public_cards = _public_cards(parent) | _public_cards(observation)
    logs = []
    for row in observation.get("logs") or ():
        if (source_seat != seat and isinstance(row, dict) and row.get("type") == 6
                and (not {row.get("fromArea"), row.get("toArea")} & {3, 4, 5, 7, 8, 9, 10}
                     or (row.get("serial"), row.get("cardId")) not in public_cards)):
            raise ProjectionError("cross-view movement visibility unavailable")
        kind, fields, _recognized = visible_event(row, seat)
        logs.append({"type": kind, **dict(fields)})
    observation["logs"] = logs
    for index, player in enumerate(current["players"]):
        player["prize"] = [None] * len(player.get("prize") or ())
        player.pop("deck", None)
        if index != seat:
            player["hand"] = None
    if source_seat != seat and current.get("looking") is not None:
        current["looking"] = [None] * len(current["looking"])
    current["yourIndex"] = seat
    if control.visibility is not SelectionVisibility.FOCAL:
        observation["select"] = None
    return observation, control
