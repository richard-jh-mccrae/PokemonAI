"""The **Option Equivalence Class** — which select-menu options are THE SAME DECISION (ADR-0091).

Two options are one decision when the board cannot tell them apart: two identical undamaged Riolu on
the bench, the same Energy card onto either of two identical Basics. Picking one is picking the
other, and four consumers need to agree on that:

* `satisfies_human` (`tools/train/gates.py`) — a ruling naming one member is satisfied by any member,
  so an indistinguishable-options ruling can be satisfied ON PURPOSE rather than merely excused as a
  ``transposition`` (ADR-0088 decision 6, whose deferral this closes);
* the Leaf Lab — a tie between options that are the same decision is not a discrimination failure,
  and a class whose members score DIFFERENTLY is a defect worth reporting (**Class Asymmetry**);
* the develop rung — sim ONE representative per class and give every member its value, which removes
  a measured 1167.0-vs-95.4 split on three byte-identical bodies;
* the greedy policy's own ordering (`_score_order`, `_greedy_grab`) — an EXACT score tie breaks on
  class identity rather than on the engine's menu index, so the policy is a pure function of the
  board and two isomorphic positions explore the same line (ADR-0103, Issue #254 — the CAUSE of the
  split the develop rung's fan-out corrects downstream).

This module is where that meaning lives, ONCE. Two implementations would drift invisibly, because the
agent and the instrument grading it would each stay internally consistent while disagreeing.

## Why it is here, and pure

`tools/train/gates.py` imports this, and that module must stay loadable with **no DLL** — the offline
cross-platform suite depends on it. So nothing here imports `cg.api` (a bare import maps the native
library), nothing imports a Pilot, and everything is a pure function over plain dicts.

## The fingerprint, and the one thing it ignores

``(type, seat, [(area, card-state-minus-serial) for EVERY zone reference the option carries])``.

**"Every" is load-bearing.** An ATTACH names TWO cards — ``area``/``index`` is the Energy in hand,
``inPlayArea``/``inPlayIndex`` the recipient body. Fingerprinting only the body called *different
Energies onto one Pokémon* the same decision, measured at **6 false equivalences** over the committed
corpus. A grading oracle that is wrong in that direction is worse than none.

``serial`` — the engine's instance number — is the ONLY field ignored. Everything else the snapshot
carries is game-visible and splits the class: hp, attached energy, tools, pre-evolution,
``appearThisTurn``, card id.

**A reference the snapshot does not reveal makes the WHOLE option unfingerprintable**, so it joins no
class. The face-down deck (262 corpus options) exposes only a count, so deck options group with
nothing. Blind implies conservative, structurally — not by an exclusion list somebody has to
maintain, and not by a partial fingerprint falling back to the rejected body-only one.

Distinct from `gates.option_slot`, which answers *"which one identity does this option target"* and
is load-bearing for three decider sweeps and every committed Axis Claim. Distinct too from
`tools/train/probes/transposition_probe.py`'s ``_bodykey``, a search transposition-table key that is
deliberately lossy (it drops ``hp``) because collapsing near-identical states is its job — reusing it
to GRADE would equate a damaged Pokémon with a fresh one.
"""
from __future__ import annotations

import json

#: `cg.api.AreaType` owns these numbers (CLAUDE.md: engine vocabulary comes from `src/cg/api.py`),
#: but importing it MAPS THE NATIVE LIBRARY. Same treatment `gates.py` gives its lane constants:
#: written literally, **pinned to the enums by a test** (`test_area_constants_match_the_engine_enums`),
#: which is what makes them sourced rather than remembered.
AREA_DECK = 1                                       # cg.api.AreaType.DECK
AREA_HAND = 2                                       # cg.api.AreaType.HAND
AREA_DISCARD = 3                                    # cg.api.AreaType.DISCARD
AREA_ACTIVE = 4                                     # cg.api.AreaType.ACTIVE
AREA_BENCH = 5                                      # cg.api.AreaType.BENCH
AREA_LOOKING = 12                                   # cg.api.AreaType.LOOKING

#: Area -> the key holding that zone's cards on a player's snapshot. **Membership IS the reveal
#: test**: an area absent here is one the snapshot does not expose as a card list, so an option
#: naming it cannot be fingerprinted. `AREA_DECK` and `AREA_PRIZE` are deliberately absent — the
#: snapshot carries `deckCount` and a face-down prize list, and grouping cards nobody can see would
#: be an equivalence asserted from ignorance rather than from the board.
_PLAYER_ZONES = {AREA_HAND: "hand", AREA_DISCARD: "discard",
                 AREA_ACTIVE: "active", AREA_BENCH: "bench"}

#: The zone references an option may carry, in a fixed order so the fingerprint is stable. An ATTACH
#: carries both; a plain CARD pick carries only the first.
_ZONE_REFS = (("area", "index"), ("inPlayArea", "inPlayIndex"))


def _without_serial(obj):
    """A card's state minus the engine's instance number, recursively.

    Recursive because ``energyCards``, ``tools`` and ``preEvolution`` are themselves lists of card
    dicts carrying their own serials — two bodies holding the same Energy differ in those serials and
    must still compare equal."""
    if isinstance(obj, dict):
        return {k: _without_serial(v) for k, v in sorted(obj.items()) if k != "serial"}
    if isinstance(obj, list):
        return [_without_serial(v) for v in obj]
    return obj


def _card_at(frame, seat, area, index):
    """The card an ``(area, index)`` reference names, or None when the snapshot cannot resolve it.

    None is the answer for a face-down zone, an unknown area, an out-of-range index, or a seat the
    snapshot has no player for — every one of which must yield *no class* rather than a guess."""
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


def option_fingerprint(option: dict, frame: dict | None) -> str | None:
    """The option's identity as a hashable string, or **None when it cannot be fingerprinted**.

    None means "joins no class", and it is returned whenever ANY zone reference the option carries
    fails to resolve — never a partial fingerprint over the references that happened to work. That
    fallback is exactly the rejected body-only design: an ATTACH whose hand index is unresolvable
    would otherwise be compared on its recipient alone.

    An option naming no zone at all (END, YES/NO) is also None — two of those are not one *targeting*
    decision, they are not a targeting decision at all."""
    if not isinstance(option, dict):
        return None
    seat = option.get("playerIndex")
    if seat is None:
        seat = ((frame or {}).get("current") or {}).get("yourIndex", 0)
    cards = []
    for area_key, index_key in _ZONE_REFS:
        area = option.get(area_key)
        if area is None:
            continue
        card = _card_at(frame, seat, area, option.get(index_key))
        if card is None:
            return None                             # unresolvable ANYWHERE -> no class, whole option
        cards.append([area, _without_serial(card)])
    if not cards:
        return None
    return json.dumps([option.get("type"), seat, cards], sort_keys=True)


def option_equivalence(options, frame: dict | None) -> dict:
    """``{option index: frozenset(indices it is interchangeable with)}`` — NON-TRIVIAL classes only.

    A singleton is absent rather than mapped to itself, so an empty result means "nothing to
    canonicalise" and a caller can test membership with a plain truthiness check.

    Deterministic: the result depends only on the snapshot, never on iteration order or identity, so
    two processes handed one frame produce one map — which is what lets the develop rung's ranking
    stay reproducible (#178)."""
    groups: dict = {}
    for i, option in enumerate(options or []):
        fp = option_fingerprint(option, frame)
        if fp is not None:
            groups.setdefault(fp, []).append(i)
    return {i: frozenset(members)
            for members in groups.values() if len(members) > 1
            for i in members}


def classes(equiv: dict) -> list:
    """One frame's classes as a sorted list of sorted index lists.

    The de-duplicating walk over an ``equiv`` map, which three callers had each written for
    themselves — a capture row's JSON shape, the Leaf Lab's asymmetry scan, and this module. Same
    reason the fingerprint lives here: a second copy is a second definition of "these are one
    decision", and it drifts silently because each copy stays internally consistent."""
    return sorted(sorted(members) for members in {frozenset(v) for v in (equiv or {}).values()})


def class_of(equiv: dict, index: int) -> frozenset:
    """The class ``index`` belongs to — itself alone when it is in none.

    The other operation three call sites had inlined (`class_representatives`, the Leaf Lab's tie
    count, `satisfies_human`), each spelling the singleton default slightly differently."""
    return (equiv or {}).get(index) or frozenset({index})


def class_representatives(equiv: dict, count: int) -> list:
    """The option indices worth evaluating — one per class, plus every unclassed option.

    **The representative is the LOWEST index in its class**, deliberately: the choice must be a pure
    function of the menu, or two processes rank differently and the develop rung's reproducibility
    guarantee (#178, all-or-nothing) is worth nothing.

    Returned in ascending order, so a caller iterating them walks the menu in its natural order."""
    return [i for i in range(count) if min(class_of(equiv, i)) == i]


def canonical_keys(options, frame: dict | None) -> list:
    """Per-option ORDERING key — the fingerprint, or ``""`` when the option has none (ADR-0103).

    The one thing about an option that is not a board fact is its position in the menu, and that is
    exactly what a stable sort falls back on when two options score the same. After an identical
    first step onto interchangeable bodies the resulting boards are isomorphic but their menus are
    *permutations* of each other, so a positional tie-break resolves the same tie toward a different
    body on each — the search incompleteness `fan_out` corrects downstream and Issue #254 names at
    its source. Keying the tie-break on the fingerprint instead makes the ordering a pure function of
    the board: permuting the menu permutes these keys with it and invents no new ones.

    ``""`` for an unfingerprintable option (a face-down DECK reference, END, YES/NO) rather than a
    guessed identity — blind ⇒ conservative, the same rule `option_fingerprint` keeps. Since a stable
    sort preserves menu order among equal keys, those options keep exactly the ordering they had, and
    their *relative* order is itself permutation-invariant (nothing about which bench slot holds what
    reorders the deck).

    List in, list out, index-aligned — the shape `fan_out` already established, so a caller holding a
    per-option list indexes it directly instead of writing its own adapter."""
    return [option_fingerprint(o, frame) or "" for o in (options or [])]


def fan_out(values, equiv: dict) -> list:
    """Spread each representative's value across its whole class — the **class maximum**, index-aligned.

    Sound by isomorphism: after an identical first step onto interchangeable bodies the resulting
    boards differ only in which instance holds what, so any line reachable from one member is
    reachable from all. Raising the others to the representative's value corrects an OMISSION (a
    greedy rollout that found a KO from bench 0 and missed the isomorphic one from bench 1), it does
    not invent optimism. The class *minimum* was rejected for discarding a line the simulator proved
    attainable.

    ``max`` rather than a bare copy so the function stays correct if a caller ever evaluates more
    than one member of a class — the value assigned is then the best DEMONSTRATED one, never a
    silently-chosen arbitrary member.

    List in, list out, index-aligned: both callers hold a per-option list, and taking a dict here
    made each of them write the same ``{i: v for i, v ...}`` adapter at its own call site."""
    out = []
    for i in range(len(values)):
        scored = [values[m] for m in class_of(equiv, i)
                  if m < len(values) and values[m] is not None]
        out.append(max(scored) if scored else None)
    return out
