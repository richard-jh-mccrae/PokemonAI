from types import SimpleNamespace

from common.ledger.search import preservation_frontier


def candidate(kind, value, *, preserved=(), consumed=()):
    return SimpleNamespace(
        action=SimpleNamespace(identity=SimpleNamespace(kind=kind)),
        delta=SimpleNamespace(total=value),
        continuation=SimpleNamespace(
            opportunities_preserved=tuple(preserved),
            opportunities_consumed=tuple(consumed)))


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
