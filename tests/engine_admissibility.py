"""Is this engine drive's answer a fact about the board, or a sample? (ADR-0072 amendment C)

Pinning an exact engine verdict is only meaningful if the drive could not have answered differently.
The rule for that lives in ONE place, `planner._rng_probe`, and is imported rather than restated;
this module points it at an arbitrary drive:

    with measure_rng(my_index) as reveals:
        verdict = pilot._engine_confirms_win(obs, [[5]])
    assert not reveals, "this verdict is a sample"

``prize=False`` (default) is the VERDICT question — a face-down prize take does not change WHO wins
(ADR-0050). ``prize=True`` is the BOARD question, where a reveal can change anything scored off it.
"""
from __future__ import annotations

import contextlib


@contextlib.contextmanager
def measure_rng(my_index: int, *, prize: bool = False):
    """Yield a ``set`` that fills with the engine-RNG channels the enclosed drive consumed. Empty ==
    admissible for an exact assertion; non-empty == the answer is one SAMPLE."""
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
    """Takes a built pilot and an explicit line rather than a fixture name, because admissibility
    is a property of the DRIVE, not of the board."""
    from lethal_helpers import engine_confirms

    yi = ((fixture.get("obs", {}).get("current") or {}).get("yourIndex")) or 0
    with measure_rng(yi, prize=prize) as reveals:
        engine_confirms(fixture, pilot, line=line)
    return reveals
