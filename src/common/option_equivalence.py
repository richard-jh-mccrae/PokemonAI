"""The **Option Equivalence Class** — which select-menu options are THE SAME DECISION (ADR-0091).

The fingerprint is ``(type, seat, [(area, card-state-minus-serial) for EVERY zone reference the
option carries])``. "Every" is load-bearing: an ATTACH names the Energy in hand AND the recipient
body, and fingerprinting only the body calls *different Energies onto one Pokémon* one decision.
``serial`` is the ONLY field ignored. A reference the snapshot does not REVEAL makes the WHOLE option
unfingerprintable, so it joins no class — blind implies conservative, structurally.

Pure and lib-free: nothing here imports `cg.api`, because a bare import maps the native library.

Distinct from `gates.option_slot` (*which one identity does this option target*) and from
`transposition_probe._bodykey` (deliberately lossy — it drops ``hp``).
"""
from __future__ import annotations

import json

#: `cg.api.AreaType` owns these numbers, but importing it MAPS THE NATIVE LIBRARY — so they are
#: written literally and pinned by `test_area_constants_match_the_engine_enums`.
AREA_DECK = 1                                       # cg.api.AreaType.DECK
AREA_HAND = 2                                       # cg.api.AreaType.HAND
AREA_DISCARD = 3                                    # cg.api.AreaType.DISCARD
AREA_ACTIVE = 4                                     # cg.api.AreaType.ACTIVE
AREA_BENCH = 5                                      # cg.api.AreaType.BENCH
AREA_STADIUM = 7                                    # cg.api.AreaType.STADIUM
AREA_LOOKING = 12                                   # cg.api.AreaType.LOOKING
OPTION_PLAY = 7                                     # cg.api.OptionType.PLAY

#: Area -> the key holding that zone's cards on a player's snapshot. **Membership IS the reveal
#: test**: DECK and PRIZE are absent because they are face-down — grouping them asserts from ignorance.
_PLAYER_ZONES = {AREA_HAND: "hand", AREA_DISCARD: "discard",
                 AREA_ACTIVE: "active", AREA_BENCH: "bench"}

#: The zone references an option may carry, in a fixed order so the fingerprint is stable.
_ZONE_REFS = (("area", "index"), ("inPlayArea", "inPlayIndex"))

#: A fingerprint's embedded zone reference is exactly ``[area, card]``.
_FINGERPRINT_REFERENCE_LENGTH = 2

#: Non-zone fields that make two same-body options DIFFERENT decisions (``energyIndex`` names
#: WHICH attachment; grouping across it merged physically distinct discards).
_DISCRIMINATOR_FIELDS = ("count", "energyIndex", "number", "specialConditionType", "toolIndex")


def without_engine_serial(obj):
    """Recursive because ``energyCards`` / ``tools`` / ``preEvolution`` carry their own serials —
    two bodies holding the same Energy must still compare equal."""
    if isinstance(obj, dict):
        return {k: without_engine_serial(v) for k, v in sorted(obj.items()) if k != "serial"}
    if isinstance(obj, list):
        return [without_engine_serial(v) for v in obj]
    return obj


_without_serial = without_engine_serial


def _card_at(frame, seat, area, index):
    """None — face-down zone, unknown area, bad index, absent seat — must yield NO CLASS, not a
    guess."""
    if not isinstance(index, int) or index < 0:
        return None
    if area == AREA_LOOKING:                        # a top-level reveal, not a per-player zone
        cards = ((frame or {}).get("current") or {}).get("looking") or []
        return cards[index] if index < len(cards) else None
    zone = _PLAYER_ZONES.get(area)
    if zone is None:
        return None
    players = ((frame or {}).get("current") or {}).get("players") or []
    if not isinstance(seat, int) or not 0 <= seat < len(players):
        return None
    cards = (players[seat] or {}).get(zone) or []
    return cards[index] if index < len(cards) else None


def _is_implicit_play(option: dict) -> bool:
    """Detect Play options whose hand slot is implicit because area is present but None.
    Consumers must normalize this shape; a mapping default cannot."""
    return option.get("type") in (OPTION_PLAY, "Play") and option.get("area") is None


def option_source_card(option: dict, frame: dict | None):
    """Resolve the visible card selected by an option's primary area/index reference."""
    if not isinstance(option, dict):
        return None
    seat = option.get("playerIndex")
    if seat is None:
        seat = ((frame or {}).get("current") or {}).get("yourIndex", 0)
    area = option.get("area", AREA_HAND)
    if area is None and _is_implicit_play(option):
        area = AREA_HAND
    return _card_at(frame, seat, area, option.get("index"))


def option_in_play_source_id(option, frame: dict | None, seat: int | None = None) -> int | None:
    """Resolve the card id an ability, skill, or tool acts through.
    Treat present-but-None keys as absent and fail closed on unresolved references."""
    if not isinstance(option, dict):
        return None
    card_id = option.get("cardId")
    if card_id is not None:                          # SKILL options name the card directly
        return int(card_id)
    if option.get("playerIndex") is not None:
        seat = option["playerIndex"]
    if seat is None:
        seat = ((frame or {}).get("current") or {}).get("yourIndex", 0)
    for area_key, index_key in reversed(_ZONE_REFS):
        area = option.get(area_key)
        if area is None:
            continue
        index = option.get(index_key)
        if area == AREA_STADIUM:
            cards = ((frame or {}).get("current") or {}).get("stadium") or []
            card = (cards[index] if isinstance(index, int) and 0 <= index < len(cards)
                    else None)
        else:
            card = _card_at(frame, seat, area, index)
        return (int(card["id"]) if isinstance(card, dict) and card.get("id") is not None
                else None)
    return None


def fingerprint_source_card_id(part, frame: dict | None) -> int | None:
    """Resolve a source card id from one ActionIdentity part.
    Semantic identities embed the card; fallback identities retain raw area/index keys."""
    if not isinstance(part, str):
        return None
    try:
        decoded = json.loads(part)
    except (TypeError, ValueError):
        return None
    if not isinstance(decoded, list) or not decoded:
        return None
    head = decoded[0]
    if isinstance(head, dict):                       # fallback shape: [public, enriched]
        return option_in_play_source_id(head, frame)
    fields = decoded[1] if len(decoded) > 1 and isinstance(decoded[1], dict) else {}
    if fields.get("cardId") is not None:
        return int(fields["cardId"])
    cards = decoded[2] if len(decoded) > 2 and isinstance(decoded[2], list) else []
    for reference in cards:
        if (isinstance(reference, list) and len(reference) == _FINGERPRINT_REFERENCE_LENGTH
                and isinstance(reference[1], dict) and reference[1].get("id") is not None):
            return int(reference[1]["id"])
    return None


def option_fingerprint(option: dict, frame: dict | None) -> str | None:
    """None = "joins no class", returned whenever ANY zone reference fails to resolve — never a
    partial fingerprint over the references that happened to work. An option naming no zone is None."""
    if not isinstance(option, dict):
        return None
    seat = option.get("playerIndex")
    if seat is None:
        seat = ((frame or {}).get("current") or {}).get("yourIndex", 0)
    cards = []
    # The implicit Play's bare index is still a visible zone reference; normalize it so physical
    # copies of one card remain one semantic decision everywhere, including correction retests.
    if _is_implicit_play(option):
        card = _card_at(frame, seat, AREA_HAND, option.get("index"))
        if card is None:
            return None
        cards.append([AREA_HAND, without_engine_serial(card)])
    for area_key, index_key in _ZONE_REFS:
        area = option.get(area_key)
        if area is None:
            continue
        card = _card_at(frame, seat, area, option.get(index_key))
        if card is None:
            return None                             # unresolvable ANYWHERE -> no class, whole option
        cards.append([area, without_engine_serial(card)])
    if not cards:
        return None
    discriminators = [[field, option[field]] for field in _DISCRIMINATOR_FIELDS
                      if option.get(field) is not None]
    return json.dumps([option.get("type"), seat, cards, discriminators], sort_keys=True)


def semantic_option_fingerprint(option: dict, frame: dict | None) -> str | None:
    """Exact serial-free action key; hidden references fail closed, while non-target actions key themselves."""
    if not isinstance(option, dict):
        return None
    seat = option.get("playerIndex")
    if seat is None:
        seat = ((frame or {}).get("current") or {}).get("yourIndex", 0)
    cards = []
    referenced = set()
    if _is_implicit_play(option):
        card = _card_at(frame, seat, AREA_HAND, option.get("index"))
        if card is None:
            return None
        referenced.add("index")
        cards.append([AREA_HAND, without_engine_serial(card)])
    for area_key, index_key in _ZONE_REFS:
        area = option.get(area_key)
        if area is None:
            continue
        card = _card_at(frame, seat, area, option.get(index_key))
        if card is None:
            return None
        referenced.update((area_key, index_key))
        cards.append([area, without_engine_serial(card)])
    fields = {k: without_engine_serial(v) for k, v in sorted(option.items())
              if k not in referenced and k != "_composer_origin" and not str(k).startswith("_")}
    try:
        return json.dumps([seat, fields, cards], sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return None


def option_equivalence(options, frame: dict | None) -> dict:
    """``{option index: frozenset(interchangeable indices)}`` — NON-TRIVIAL classes only, so a
    singleton is absent rather than mapped to itself. Depends only on the snapshot."""
    groups: dict = {}
    for i, option in enumerate(options or []):
        fp = option_fingerprint(option, frame)
        if fp is not None:
            groups.setdefault(fp, []).append(i)
    return {i: frozenset(members)
            for members in groups.values() if len(members) > 1
            for i in members}


def classes(equiv: dict) -> list:
    """One frame's classes as a sorted list of sorted index lists."""
    return sorted(sorted(members) for members in {frozenset(v) for v in (equiv or {}).values()})


def class_of(equiv: dict, index: int) -> frozenset:
    """The class ``index`` belongs to — itself alone when it is in none."""
    return (equiv or {}).get(index) or frozenset({index})


def class_representatives(equiv: dict, count: int) -> list:
    """One index per class plus every unclassed option, ascending. The representative is the LOWEST
    index in its class so the choice is a pure function of the menu (Issue #178 reproducibility)."""
    return [i for i in range(count) if min(class_of(equiv, i)) == i]


def fan_out(values, equiv: dict) -> list:
    """Spread each representative's value across its class — the class MAXIMUM, index-aligned. Sound
    by isomorphism; the minimum was rejected for discarding a line the simulator proved attainable."""
    out = []
    for i in range(len(values)):
        scored = [values[m] for m in class_of(equiv, i)
                  if m < len(values) and values[m] is not None]
        out.append(max(scored) if scored else None)
    return out
