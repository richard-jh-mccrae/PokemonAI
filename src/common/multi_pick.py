"""One-ply leaf differencing for ordered multi-select menus."""
from __future__ import annotations

from common.state_value import state_value


def leaf_pick_indices(model, *, minimum: int, maximum: int, keys: list[str], project) -> list[int]:
    """Pick iteratively by the marginal leaf delta; decline optional non-positive additions."""
    if minimum < 0 or maximum < minimum or minimum > len(keys):
        raise ValueError("multi-pick bounds cannot produce a legal selection")
    maximum = min(maximum, len(keys))
    chosen: list[int] = []
    remaining = set(range(len(keys)))
    current = model
    current_value = state_value(current)
    while remaining and len(chosen) < maximum:
        scored = []
        for index in remaining:
            after = project(tuple((*chosen, index)))
            after_value = state_value(after)
            scored.append((after_value - current_value, index, after, after_value))
        delta, index, after, after_value = min(
            scored, key=lambda row: (-round(row[0], 8), keys[row[1]], row[1]))
        if len(chosen) >= minimum and round(delta, 8) <= 0:
            break
        chosen.append(index)
        remaining.remove(index)
        current, current_value = after, after_value
    return chosen
