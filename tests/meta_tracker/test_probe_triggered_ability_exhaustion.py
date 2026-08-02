"""Pure helpers of `tools/meta_tracker/probe_cards.py` (module docstring: "pure helpers, module
level, unit-tested" vs. the lazy-import lib shell that actually drives the engine).

Two predicates, both the CI-flake fix (Issue #322 follow-up): the triggered-Ability probe
(`probe_triggered_ability.py`) drives a game deck stocked with a BOUNDED search pool
(`_TRIGGER_SUPPORTERS` distinct Supporter lines, or the Basic {D} Energy fill), and nothing bounds
how many turns pass before the target enters play. A long enough drive draws the pool down —
partly into the visible hand, partly into 6 face-down prize cards this harness cannot see — until
a search-based trigger comes up short of what its own printed text promises, at two distinct
boundaries:

* `_accept_capture_is_exhausted` — PARTIAL shortage: the gate is posed normally, but an accepted
  search finds fewer than its own ceiling. Accept-mode only; declining never resolves the search.
* `_gate_was_skipped` — TOTAL shortage (`deckCount == 0`): the trigger's *"you may…"* gate is
  never posed at all. Breaks both modes, since there is no y/n to accept or decline.

Measured: with `deckCount < 10` at play time a search comes up short roughly HALF the time, against
~0.2% otherwise — which is CI's ~1-in-2-runs flake on
`tests/strategy/test_triggered_ability_shape.py`. `probe_triggered_ability`'s retry loop tests both
predicates on every capture before accepting it as a clean measurement.
"""
import pytest

from meta_tracker.probe_cards import (_CTX_ACTIVATE, _CTX_MAIN, _accept_capture_is_exhausted,
                                      _gate_was_skipped)


def _rec(effect_selects):
    return {"effect_selects": effect_selects}


def _select(max_count):
    return {"select_type": 1, "context": 7, "min_count": 0, "max_count": max_count,
            "option_types": [3], "context_card_id": None}


# --- search_ceiling=None: a MANDATORY single find (Last-Ditch Catch: "a Supporter card") --------


@pytest.mark.req("REQ-TRIGGER-0001")
def test_a_posed_select_is_never_exhausted_regardless_of_its_own_max_count():
    """The engine never poses this select with max_count 0 — when it fires at all it always finds
    exactly one card (verified against the live engine: max_count is 1 whenever posed, whatever
    the candidate count). Any posed select is therefore a clean capture."""
    assert not _accept_capture_is_exhausted(_rec([_select(1)]), None)


@pytest.mark.req("REQ-TRIGGER-0001")
def test_no_select_at_all_is_exhausted():
    """The engine SKIPS the select entirely when the deck holds no target — this is the failure
    mode measured directly: 0 targets in deck -> no select posed, not a select with 0 options."""
    assert _accept_capture_is_exhausted(_rec([]), None)


# --- search_ceiling=N: an UP-TO-N search (Punk Up: "up to 5 Basic {D} Energy cards") -------------


@pytest.mark.req("REQ-TRIGGER-0001")
def test_a_search_that_reaches_its_own_ceiling_is_clean():
    assert not _accept_capture_is_exhausted(_rec([_select(5)]), 5)


@pytest.mark.req("REQ-TRIGGER-0001")
def test_a_search_capped_below_its_ceiling_is_exhausted():
    """The card's own text promises "up to 5"; a capture that found only 2 is not a fact about
    Punk Up, it is a fact about how few Basic {D} remained in a depleted deck."""
    assert _accept_capture_is_exhausted(_rec([_select(2)]), 5)


@pytest.mark.req("REQ-TRIGGER-0001")
def test_no_select_at_all_is_exhausted_for_an_up_to_search_too():
    """Total exhaustion (0 remaining) degrades an up-to-N search the same way it degrades a
    mandatory one: no legal target, no select posed at all — not a select with max_count 0."""
    assert _accept_capture_is_exhausted(_rec([]), 5)


@pytest.mark.req("REQ-TRIGGER-0001")
def test_a_ceiling_exactly_at_the_bound_is_not_flagged():
    """No off-by-one: a capture that reaches the printed ceiling EXACTLY must not be rejected —
    a `<` off-by-one here would make the retry loop unable to ever accept the full-search case,
    the one shape the whole probe exists to record."""
    assert not _accept_capture_is_exhausted(_rec([_select(5)]), 5)


# --- _gate_was_skipped: TOTAL exhaustion (deckCount == 0) breaks BOTH modes ----------------------
# Found on the first CI run after the partial-shortage fix landed: at deckCount == 0 the engine
# doesn't offer the trigger's y/n choice at all, so `gate_select` is already a MAIN select — which
# broke a decline-mode capture the search-only check could not see (declining never touches
# `effect_selects` at all, so that check is skipped for decline by design).


def _gate(context):
    return {"gate_select": {"type": 9, "context": context, "minCount": 1, "maxCount": 1,
                            "option": [{"type": 1}, {"type": 2}], "deck": None,
                            "contextCard": {"id": 1071, "playerIndex": 0}, "effect": None}}


@pytest.mark.req("REQ-TRIGGER-0002")
def test_a_posed_ACTIVATE_gate_is_not_skipped():
    assert not _gate_was_skipped(_gate(_CTX_ACTIVATE))


@pytest.mark.req("REQ-TRIGGER-0002")
def test_a_gate_that_is_already_a_MAIN_select_was_skipped():
    """The measured failure mode: `_capture_trigger` captures whatever select immediately follows
    the PLAY/EVOLVE option as `gate_select`. When the trigger fizzles with nothing to search, that
    select is already MAIN — a completely different, unrelated decision — not an ACTIVATE y/n."""
    assert _gate_was_skipped(_gate(_CTX_MAIN))


@pytest.mark.req("REQ-TRIGGER-0002")
def test_skip_detection_is_independent_of_mode():
    """The whole reason this needed its own predicate: `_accept_capture_is_exhausted` is skipped
    for decline mode by design (an empty search there is correct), so it cannot catch a fizzled
    gate on a decline capture. `_gate_was_skipped` reads only `gate_select`, which every capture —
    accept or decline — records identically before the mode-specific branch is ever reached."""
    assert _gate_was_skipped(_gate(_CTX_MAIN))          # would apply the same regardless of mode
