"""`_composer_line` must hand the composer every seam the composer cannot reach for itself.

`common.composer` holds no `Pilot` — deliberately, and its module docstring says so. Three facts it
therefore cannot compute are passed IN by its caller: `search_api`, the per-option determinism proof,
and **`shed`**, the hand indices a costed search would pay. `Pilot.cost_shed_indices` exists for
exactly that call and says so in its own docstring.

**The failure this file exists for is silent in every direction.** Left unwired, `shed` defaults to
`None`, `board_expectation` REFUSES the costed search by name, `compose` records the refusal in
`gaps` — where nobody was reading it — and the composer simply has no opinion about Ultra Ball. No
exception, no failing test, no visible score change: the option just never competes. It was found
from a hand-built fixture whose composer `gaps` named the missing seam in as many words.

What makes it worth a permanent guard is the second half. `tools/train/composer_lab.py` — the
instrument every POC-T4/5 measurement in Issue #386 was taken with — passes `shed`, and records in
its own comment that *"without this an Ultra Ball refuses — 65 of the corpus's 69 cost-refused
steps"*. So for as long as production went unwired, the lab was measuring a composer strictly
better-informed than the one that shipped, and every corpus number described an agent that did not
exist. A seam wired in the lab and not in production is worse than a seam wired in neither, because
the measurement says it works.
"""
import inspect

import pytest

from common.pilot import Pilot


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_planner_passes_the_shed_oracle_to_the_composer():
    """`_composer_line` names `shed` in its `compose` call, and names it with the Pilot's own oracle."""
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
    """`board_expectation` calls `shed(model, option, picks)`. A signature drift here would surface
    as a `TypeError` swallowed by `_composer_line`'s bare `except` — which returns None and falls
    back to the tuned scoring, i.e. exactly the silent abstention this file is about."""
    sig = inspect.signature(Pilot.cost_shed_indices)
    assert [p for p in sig.parameters][:4] == ["self", "model", "option", "picks"], sig


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_signature_check_actually_looks_at_something():
    """Positive control. Both assertions above are `in`-tests against a source string and a parameter
    list; either would pass vacuously against the wrong object. Point them at a method that is
    definitely NOT the composer call site and require them to fail."""
    other = inspect.getsource(Pilot.cost_shed_indices)
    assert "shed=" not in other, (
        "the source-substring check cannot discriminate — it matches a method that does not call "
        "`compose` at all, so its passing above proves nothing")
