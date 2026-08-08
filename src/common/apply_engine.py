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
# native frame (Issue #464).  They name an engine route, never a hand-written card transition.
CARD_CONTINUATION_CONTEXTS = frozenset({1, 2, 3, 4, 7, 15, 17, 21, 22})


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


def option_index(obs: dict, option) -> int | None:
    """Where ``option`` sits on this observation's select menu, or None. Identity first, equality
    second. None REFUSES rather than guess — a wrong index is a different legal play priced as this."""
    menu = ((obs or {}).get("select") or {}).get("option") or ()
    for i, candidate in enumerate(menu):
        if candidate is option:
            return i
    equal = [i for i, candidate in enumerate(menu) if candidate == option]
    # A copied option is admissible only when equality identifies ONE offered option.  Two equal
    # candidates still name distinct engine indices; choosing the first would be context fallback.
    return equal[0] if len(equal) == 1 else None


def continuation_index(model, option, *, card_kind: int, depth: int) -> int | None:
    """The exact selected index for a seed-backed depth-0 CARD continuation, else ``None``."""
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
    if context not in CARD_CONTINUATION_CONTEXTS or not (0 <= minimum <= 1 <= maximum):
        return None
    return option_index(obs, option)


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


__all__ = ("CARD_CONTINUATION_CONTEXTS", "continuation_index", "option_index", "resolve")
