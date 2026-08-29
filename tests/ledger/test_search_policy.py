from types import SimpleNamespace

from common.ledger.search import preservation_frontier


def candidate(kind, value, *, preserved=(), consumed=(), allowances=(), zones=(), created=()):
    return SimpleNamespace(
        action=SimpleNamespace(identity=SimpleNamespace(kind=kind)),
        delta=SimpleNamespace(total=value),
        continuation=SimpleNamespace(
            opportunities_preserved=tuple(preserved),
            opportunities_consumed=tuple(consumed),
            allowances_consumed=tuple(allowances),
            zones_replaced=tuple(zones),
            opportunities_created=tuple(created)))


def test_preservation_cannot_hide_a_more_valuable_resolved_compound_action():
    fetch = candidate("fetch", 1.2, consumed=("draw",))
    draw = candidate("draw", 1.0, preserved=("fetch",))

    assert preservation_frontier((fetch, draw)) == (fetch, draw)


def test_preservation_defers_a_lower_value_action_when_order_keeps_both():
    fetch = candidate("fetch", 1.0, consumed=("draw",))
    draw = candidate("draw", 1.2, preserved=("fetch",))

    assert preservation_frontier((fetch, draw)) == (draw,)


def test_positive_ability_is_used_before_evolving_away_its_source():
    evolve = candidate("evolve", 1.2, consumed=("ability",))
    ability = candidate("ability", 0.1, preserved=("evolve",))

    assert preservation_frontier((evolve, ability)) == (ability,)


def test_hand_refresh_waits_for_positive_preparation_without_coarse_consumption():
    supporter = candidate(
        "play", 3.0, allowances=("supporter_played",), zones=("hand",))
    evolve = candidate(
        "evolve", 0.2, preserved=("play",), created=("ability",))

    assert preservation_frontier((supporter, evolve)) == (evolve,)


def test_retreat_waits_for_positive_preparation_that_preserves_retreat():
    retreat = candidate("retreat", 1.4)
    evolve = candidate(
        "evolve", 0.5, preserved=("retreat",), created=("ability",))

    assert preservation_frontier((retreat, evolve)) == (evolve,)
