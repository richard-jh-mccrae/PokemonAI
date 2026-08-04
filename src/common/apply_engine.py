"""**The ENGINE-RESOLVED execution path** — one option, driven through the preserved `_search_api`
seam and read back as a board (POC-T4/1, Issue #382; the fate itself is Issue #259 §3b, ADR-0098).

`common.apply_option` decides WHETHER an option takes this route (depth 0, ``deterministic is True``,
a live ``search_api``, and no closed-form answer available). This module is the HOW, and it lives
here rather than in the seam for one blunt reason: `apply_option` is asserted to be engine-free
(`test_the_module_never_reaches_for_an_engine`), and that assertion is worth keeping literal. The
seam stays a pure contract over plain data; the engine drive is one import away, behind a seam the
caller injects.

## Why the route exists at all, and why it is a bridge rather than a home

Issue #269's coverage census found the seam's fallback resolving **zero** of the live options it was
built for while 46 refused sites sat on MODELLED kinds carrying no RNG, no hidden-zone read and no
opponent choice — the exact shape §3b calls ENGINE-RESOLVED. Issue #299 opened the route to every
declared non-terminal kind. What lands here is therefore *"the clause vocabulary cannot say this
yet"*, and every resolution emits `apply_option.EngineResolved(clause_gap=…)` naming the CARD, so the
modelling backlog is readable as work rather than as *"kind 7"*.

## The three properties that make one step safe

* **Depth 0 only.** At depth ≥ 1 the board is a synthesized `StateModel` from a prior closed-form
  apply, and a synthesized model cannot be handed back to the native engine. `apply_option` refuses
  before reaching here; this module re-checks nothing, because a second copy of a gate is how two
  copies disagree.
* **Provably deterministic only.** The engine has **no deal-seed**, so a shuffle-riding sim returns
  ONE SAMPLE rather than a distribution — measured on ml f24, 2026-07-27: the same first step scored
  7000 / 162 / 129 / 122 / 89 / 57.5 across processes. Again `apply_option`'s gate, not this
  module's.
* **The hidden-zone seeds cannot change the answer, which is what makes the simple seeding sound.**
  `search_begin` must be handed a plausible multiset for every face-down zone or it will not start.
  The planner's `_seed_zones` builds a careful one because the Lethal Solver's verdict can depend on
  it; here it cannot, by the determinism gate's own definition — an effect that reads a hidden zone
  is not provably deterministic and never reaches this module. So the seeds are the same sound
  FALLBACK `_seed_zones` documents (a decklist prefix, sized to each zone's count), and the
  simplification is a consequence of the gate rather than a corner cut.

## What it returns, and what it never does

A `StateModel` for the post-step board, built through :meth:`StateModel.rebuilt` so it carries the
same knowledge seams the pre-state did. On any failure — no `search_begin_input` on the observation
(**0 of 372 gate frames carry one**, so this is the ordinary offline case rather than an error), an
option the menu does not contain, an engine that raises — it returns None and `apply_option` refuses.
It never returns the pre-state model: a silently-unchanged board prices the option at exactly 0.0
delta, which at ordering time reads as *never explore this*.
"""
from __future__ import annotations


def _seed_zones(me: dict, opp: dict, deck) -> tuple:
    """``(your_deck, your_prize, opp_deck, opp_prize, opp_hand)`` for `search_begin`.

    A decklist PREFIX sized to each zone's count — the sound fallback branch of
    `planner._seed_zones`, and sound here for the reason the module docstring gives: an effect whose
    answer could depend on a hidden zone is not provably deterministic, so it never reaches this
    route. The counts must satisfy the engine; the identities cannot matter."""
    cards = list(deck or ())

    def take(n):
        return cards[: max(0, int(n or 0))]

    return (take(me.get("deckCount", 0)), take(len(me.get("prize") or ())),
            take(opp.get("deckCount", 0)), take(len(opp.get("prize") or ())),
            take(opp.get("handCount", 0)))


def _prune_none(value):
    """An ``asdict``-ed engine Observation in the shape the LIVE obs has.

    ``asdict`` keeps optional dataclass fields as ``None`` keys (``option.playerIndex``) where the
    engine's live JSON omits them, and the difference is not cosmetic: an
    ``option.get("playerIndex", yourIndex)`` read gets ``None`` instead of the default and crashes.
    **None-valued dict keys are dropped; None list ELEMENTS are kept** — a face-down Active or prize
    slot is a meaningful None carrying the zone's count.

    Five pure lines that `planner._prune_none` also has. Not shared, and the honest reason is a
    judgement rather than a constraint: importing the planner from here would pull in the world, and
    a third module holding one five-line function would be a module whose entire content is this
    docstring. What it normalises is a fact about `dataclasses.asdict` meeting the engine's own
    Observation, so the two copies cannot drift on anything but that — if a third caller ever appears,
    that is when the shared home earns its keep."""
    if isinstance(value, dict):
        return {k: _prune_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_prune_none(v) for v in value]
    return value


def option_index(obs: dict, option) -> int | None:
    """Where ``option`` sits on this observation's select menu, or None.

    The engine answers a select by INDEX (`search_step(searchId, [i])`), while the apply seam speaks
    in option dicts, so somebody has to bridge the two and it must be the side holding the menu.
    Matched by identity first and by equality second: the composer normally hands back the very dict
    it read off the menu, but an Option-Equivalence representative may have been copied on the way.

    None when the menu does not contain it — which refuses rather than guessing an index, because a
    wrong index is a DIFFERENT legal play silently priced as this one."""
    menu = ((obs or {}).get("select") or {}).get("option") or ()
    for i, candidate in enumerate(menu):
        if candidate is option:
            return i
    for i, candidate in enumerate(menu):
        if candidate == option:
            return i
    return None


def resolve(model, option, *, search_api):
    """The post-step `StateModel`, or None when the engine route cannot be taken.

    One step, one search, always closed: the `search_end()` is in a ``finally`` because a leaked
    search holds engine state for the rest of the match, and the ordering path calls this once per
    candidate per decision."""
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


__all__ = ("option_index", "resolve")
