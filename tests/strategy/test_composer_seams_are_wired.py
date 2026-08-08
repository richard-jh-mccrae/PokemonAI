"""`_composer_line` must hand the composer every seam it cannot reach for itself (Issue #386).

`common.composer` holds no `Pilot`, so `search_api`, the per-option determinism proof and **`shed`**
(the hand indices a costed search pays) are passed IN. Left unwired, `shed` defaults to None,
`board_expectation` REFUSES the costed search, and the composer has no opinion about Ultra Ball — no
exception, no failing test, no score change. `tools/train/composer_lab.py` passes it, so an unwired
production seam means every corpus measurement described an agent that did not exist.
"""
import inspect

import pytest

from common.pilot import Pilot


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_planner_passes_the_shed_oracle_to_the_composer():
    src = inspect.getsource(Pilot._composer_line)
    assert "shed=" in src, (
        "`_composer_line` no longer passes `shed`, so every costed search (every Ultra Ball) REFUSES "
        "unpriced and the composer abstains on it — silently, because a refusal is telemetry rather "
        "than an error")
    assert "cost_shed_indices" in src, (
        "`shed` is passed but not from `Pilot.cost_shed_indices` — that method is the live decider's "
        "own answer to WHICH cards a cost takes, and any second answer beside it is a divergence "
        "between what the composer prices and what the agent would actually pay")


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_shed_oracle_has_the_shape_the_seam_calls_it_with():
    """`board_expectation` calls `shed(model, option, picks)`. A drift surfaces as a `TypeError`
    swallowed by `_composer_line`'s bare `except` — the silent abstention this file is about."""
    sig = inspect.signature(Pilot.cost_shed_indices)
    assert [p for p in sig.parameters][:4] == ["self", "model", "option", "picks"], sig


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_signature_check_actually_looks_at_something():
    """Positive control: both assertions above would pass vacuously against the wrong object, so
    point them at a method that is definitely NOT the composer call site."""
    other = inspect.getsource(Pilot.cost_shed_indices)
    assert "shed=" not in other, (
        "the source-substring check cannot discriminate — it matches a method that does not call "
        "`compose` at all, so its passing above proves nothing")
