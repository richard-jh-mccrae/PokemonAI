"""Pure helpers of `tools/meta_tracker/probe_cards.py` — the CI-flake fix (Issue #322 follow-up).

The triggered-Ability probe drives a BOUNDED search pool and nothing bounds how many turns pass
before the target enters play, so a long drive can draw the pool down past two distinct boundaries:

* `_accept_capture_is_exhausted` — PARTIAL shortage: posed normally, but the accepted search finds
  fewer than its own ceiling. Accept-mode only; declining never resolves the search.
* `_gate_was_skipped` — TOTAL shortage (`deckCount == 0`): the *"you may…"* gate is never posed.
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
    """Verified against the live engine: max_count is 1 whenever posed, whatever the candidate
    count, so any posed select is a clean capture."""
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


# --- _gate_was_skipped: TOTAL exhaustion (deckCount == 0) breaks BOTH modes --------------------
# At deckCount == 0 the engine offers no y/n at all, so `gate_select` is already a MAIN select.


def _gate(context):
    return {"gate_select": {"type": 9, "context": context, "minCount": 1, "maxCount": 1,
                            "option": [{"type": 1}, {"type": 2}], "deck": None,
                            "contextCard": {"id": 1071, "playerIndex": 0}, "effect": None}}


@pytest.mark.req("REQ-TRIGGER-0002")
def test_a_posed_ACTIVATE_gate_is_not_skipped():
    assert not _gate_was_skipped(_gate(_CTX_ACTIVATE))


@pytest.mark.req("REQ-TRIGGER-0002")
def test_a_gate_that_is_already_a_MAIN_select_was_skipped():
    """`_capture_trigger` takes whatever select follows the PLAY/EVOLVE option as `gate_select`, so
    a fizzled trigger leaves an unrelated MAIN decision sitting there instead of an ACTIVATE y/n."""
    assert _gate_was_skipped(_gate(_CTX_MAIN))
