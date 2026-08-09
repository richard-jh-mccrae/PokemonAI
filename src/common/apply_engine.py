"""The ENGINE-RESOLVED execution path: drive ONE option through the preserved `_search_api` seam and
read the result back as a board (ADR-0098, Issue #382).

`common.apply_option` decides WHETHER an option takes this route; this module is the HOW. It lives
here rather than in the seam because `apply_option` is asserted engine-free by test, and that
assertion is worth keeping literal.

One step is safe only because apply_option's own gates guarantee depth 0 and provable determinism —
the engine has NO deal-seed, so a shuffle-riding sim returns ONE SAMPLE, not a distribution. Those
gates are deliberately NOT re-checked here: a second copy of a gate is how two copies disagree. The
hidden-zone seeds can be crude for the same reason — an effect that reads a hidden zone is not
provably deterministic and never arrives.

Returns a `StateModel` for the post-step board, or None on any failure. NEVER the pre-state model: a
silently-unchanged board prices the option at exactly 0.0 delta, which reads as "never explore this".
"""
from __future__ import annotations

from collections.abc import Mapping


# These are the only CARD SelectContext values whose continuation is replayed from a seed-paired
# native frame (Issues #463 and #464).  They name an engine route, never a hand-written card transition.
CARD_CONTINUATION_CONTEXTS = frozenset({1, 3, 4, 7, 15, 17, 21, 22})

# Native cannot restore setup-bench's opponent Active ``appearThisTurn``; record the explicit failure,
# never a composer route (Issue #470 closed not planned).
ENGINE_REFUSED_CARD_CONTEXTS = frozenset({2})


_COMPOSER_ORIGIN = "_composer_origin"


def _seed_zones(me: dict, opp: dict, deck) -> tuple:
    """``(your_deck, your_prize, opp_deck, opp_prize, opp_hand)`` for `search_begin`: a decklist
    PREFIX sized to each zone's count. The COUNTS must satisfy the engine; identities cannot matter."""
    cards = list(deck or ())

    def take(n):
        return cards[: max(0, int(n or 0))]

    return (take(me.get("deckCount", 0)), take(len(me.get("prize") or ())),
            take(opp.get("deckCount", 0)), take(len(opp.get("prize") or ())),
            take(opp.get("handCount", 0)))


def _prune_none(value):
    """An ``asdict``-ed engine Observation reshaped to match the LIVE obs: None-valued dict KEYS are
    dropped, None list ELEMENTS are KEPT (a face-down slot is a meaningful None carrying a count)."""
    if isinstance(value, dict):
        return {k: _prune_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_prune_none(v) for v in value]
    return value


def _engine_fields(option: Mapping) -> dict:
    """Drop only the composer's provenance stamp before exact live-menu matching."""
    return {key: value for key, value in option.items() if key != _COMPOSER_ORIGIN}


def option_index(obs: dict, option) -> int | None:
    """Where ``option`` sits on this menu: identity first, then equality without the composer stamp.
    None REFUSES rather than guess — a wrong index prices a different legal play."""
    menu = ((obs or {}).get("select") or {}).get("option") or ()
    for i, candidate in enumerate(menu):
        if candidate is option:
            return i
    public_option = _engine_fields(option) if isinstance(option, Mapping) else option
    equal = [i for i, candidate in enumerate(menu)
             if isinstance(candidate, Mapping) and _engine_fields(candidate) == public_option]
    # A copied option is admissible only when equality identifies ONE offered option.  Two equal
    # candidates still name distinct engine indices; choosing the first would be context fallback.
    return equal[0] if len(equal) == 1 else None


def _seeded_card_selection(model, option, *, card_kind: int, depth: int) -> tuple[int, int] | None:
    """``(SelectContext, exact menu index)`` for one seeded depth-0 CARD answer, else ``None``."""
    if depth != 0 or not isinstance(option, Mapping) or option.get("type") != card_kind:
        return None
    obs = getattr(model, "source_obs", None) or {}
    if not obs.get("search_begin_input"):
        return None
    select = obs.get("select") or {}
    try:
        context = int(select.get("context"))
        minimum = int(select.get("minCount", 0))
        maximum = int(select.get("maxCount", 1))
    except (TypeError, ValueError):
        return None
    # A menu can offer several cards, but an answer requiring two or more selections is multi-pick.
    if not (0 <= minimum <= 1 <= maximum):
        return None
    index = option_index(obs, option)
    return None if index is None else (context, index)


def continuation_index(model, option, *, card_kind: int, depth: int) -> int | None:
    """The exact selected index for an engine-routable seeded CARD continuation, else ``None``."""
    selection = _seeded_card_selection(model, option, card_kind=card_kind, depth=depth)
    if selection is None:
        return None
    context, index = selection
    return index if context in CARD_CONTINUATION_CONTEXTS else None


def engine_refused_context(model, option, *, card_kind: int, depth: int) -> int | None:
    """An exact seeded CARD context whose native successor is documented as unavailable."""
    selection = _seeded_card_selection(model, option, card_kind=card_kind, depth=depth)
    if selection is None:
        return None
    context, _index = selection
    return context if context in ENGINE_REFUSED_CARD_CONTEXTS else None


def resolve(model, option, *, search_api):
    """The post-step `StateModel`, or None when the engine route cannot be taken. `search_end()` is
    in a ``finally`` because a leaked search holds engine state for the rest of the match."""
    obs = getattr(model, "source_obs", None) or {}
    if not obs.get("search_begin_input"):
        return None                       # offline board: no engine handle to fork from
    index = option_index(obs, option)
    if index is None:
        return None
    current = obs.get("current") or {}
    players = current.get("players") or []
    seat = int(current.get("yourIndex", 0))
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    opp = players[1 - seat] if 0 <= 1 - seat < len(players) and players[1 - seat] else {}
    from dataclasses import asdict
    started = False
    try:
        engine_obs = search_api.to_observation_class(obs)
        seeds = _seed_zones(me, opp, getattr(model, "deck", ()))
        state = search_api.search_begin(engine_obs, *seeds, [], manual_coin=False)
        started = True
        state = search_api.search_step(state.searchId, [index])
        after = _prune_none(asdict(state.observation))
    except Exception:                     # noqa: BLE001 — any engine failure refuses, never crashes
        return None                       # the grader forfeits a match on a raised ordering call
    finally:
        if started:
            try:
                search_api.search_end()
            except Exception:             # noqa: BLE001
                pass
    return model.rebuilt(after)


__all__ = ("CARD_CONTINUATION_CONTEXTS", "ENGINE_REFUSED_CARD_CONTEXTS", "continuation_index",
           "engine_refused_context", "option_index", "resolve")
