"""Is this engine drive's answer a fact about the board, or a sample? (#178, ADR-0072 amendment C)

A test that pins an exact engine verdict — `engine_confirms(...) is True`, a leaf value, a chosen
option — is only meaningful if the drive that produced it could not have answered differently. ml f24
was pinned that way for weeks and answered `[5]` or `[3]` depending on the shuffle, failing ~2 of 3
full-suite runs through three different tests while passing in isolation every time.

The rule for "could this have answered differently" lives in ONE place, `planner._rng_probe`, and is
imported here rather than restated — a second copy would drift, and a drifted copy of this particular
rule is indistinguishable from not having it. What this module adds is the ability to point that rule
at an arbitrary drive:

    with measure_rng(my_index) as reveals:
        verdict = pilot._engine_confirms_win(obs, [[5]])
    assert not reveals, "this verdict is a sample"

Two knobs, and the difference matters (see `_rng_probe`):

- ``prize=False`` (default) — the VERDICT question. A face-down prize take does not change WHO wins
  (ADR-0050), so it does not disqualify a win/refute claim.
- ``prize=True`` — the BOARD question. A prize reveal puts a predicted card in hand, which can change
  a resulting board and anything scored off it.
"""
from __future__ import annotations

import contextlib


@contextlib.contextmanager
def measure_rng(my_index: int, *, prize: bool = False):
    """Yield a ``set`` that fills with the engine-RNG channels the enclosed drive consumed.

    Empty set == the drive is reproducible under the rule, so an exact assertion on its answer is
    admissible. Non-empty == the answer is one sample; pin something else, or exclude the frame with
    a recorded re-ruling (never by re-running until it lands — ADR-0072 amendment C).

    Wraps `cg.api`'s search entry points for the duration, and restores them even on failure. Works
    on whichever engine is mapped at call time (native, or the cgpy twin under `CG_ENGINE=py`), since
    the probe reads log types off the module it is handed.
    """
    from cg import api as cgapi
    from common.strategy.planner import _rng_probe          # ONE rule, imported not restated

    seen: set[str] = set()
    saw = _rng_probe(cgapi, my_index, prize=prize)
    begin, step = cgapi.search_begin, cgapi.search_step

    def _watch(state):
        if saw(state.observation):
            seen.add(_channel(cgapi, state.observation, my_index, prize=prize))
        return state

    cgapi.search_begin = lambda *a, **kw: _watch(begin(*a, **kw))
    cgapi.search_step = lambda *a, **kw: _watch(step(*a, **kw))
    try:
        yield seen
    finally:
        cgapi.search_begin, cgapi.search_step = begin, step


def _channel(cgapi, ob, my_index: int, *, prize: bool) -> str:
    """Name the channel that fired, so a failure says WHICH kind of randomness got in."""
    logs = getattr(cgapi, "LogType", None)
    areas = getattr(cgapi, "AreaType", None)
    for lg in (getattr(ob, "logs", None) or ()):
        t = getattr(lg, "type", None)
        if t == getattr(logs, "COIN", None):
            return "COIN"
        if getattr(lg, "playerIndex", None) != my_index:
            continue
        if t == getattr(logs, "DRAW", None):
            return "DRAW"
        if t == getattr(logs, "MOVE_CARD", None):
            fr, to = getattr(lg, "fromArea", None), getattr(lg, "toArea", None)
            if prize and fr is not None and int(fr) == int(getattr(areas, "PRIZE", -1)):
                return "PRIZE_REVEAL"
            if fr is not None and to is not None and int(fr) == int(getattr(areas, "DECK", -1)):
                if int(to) == int(getattr(areas, "LOOKING", -1)):
                    return "DECK_TOP_PEEK"
                if int(to) == int(getattr(areas, "DISCARD", -1)):
                    return "DECK_MILL"
    return "UNKNOWN"


def cascade_reveals(fixture: dict, pilot, *, line=None, prize: bool = False) -> set[str]:
    """`measure_rng` around `lethal_helpers.engine_confirms` — the common case.

    Returns the channels the fixture's cascade consumed under THIS pilot and THIS line. Deliberately
    takes a built pilot and an explicit line rather than a fixture name: admissibility is a property
    of the DRIVE, not of the board. Measured 2026-07-27, ml f24 answers it both ways — its
    `[correct]`-only drive lets `decide()` walk into a shuffle-and-draw card and is a sample, while
    its full explicit win line is reveal-free and may be pinned exactly.
    """
    from lethal_helpers import engine_confirms

    yi = ((fixture.get("obs", {}).get("current") or {}).get("yourIndex")) or 0
    with measure_rng(yi, prize=prize) as reveals:
        engine_confirms(fixture, pilot, line=line)
    return reveals
