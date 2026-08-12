from __future__ import annotations

from types import SimpleNamespace

from common.bellman import BellmanDeckProfile, BoardPotential, CardFacts, ValueRegistry
from common.strategy import PrizePlan, Strategy


CINDERACE, STARYU, MEGA_STARMIE = 666, 1030, 1031


class _Stats:
    _cards = {
        CINDERACE: SimpleNamespace(prize_value=1),
        STARYU: SimpleNamespace(prize_value=1),
        MEGA_STARMIE: SimpleNamespace(prize_value=3),
    }

    def get(self, card_id):
        return self._cards.get(card_id)


def _body(card_id):
    return {"id": card_id}


def _player(active, bench=(), prizes=6):
    return {"active": [_body(active)], "bench": [_body(card_id) for card_id in bench],
            "hand": [], "prize": [None] * prizes}


def _registry():
    return ValueRegistry(facts={card_id: CardFacts(pokemon=True, prize_value=stat.prize_value)
                                for card_id, stat in _Stats._cards.items()})


def test_prize_plan_prefers_cinderace_between_two_three_prize_attackers():
    profile = BellmanDeckProfile(
        lines=((STARYU, MEGA_STARMIE),),
        prize_routes=((CINDERACE, MEGA_STARMIE, MEGA_STARMIE),
                      (MEGA_STARMIE, CINDERACE, MEGA_STARMIE)),
        prizes_to_win=6,
    )
    potential = BoardPotential(_Stats(), registry=_registry(), profile=profile)
    opponent = {"prize": [None] * 3}  # one Mega Starmie has already fallen
    cinderace_next = _player(CINDERACE, (MEGA_STARMIE, STARYU), prizes=3)
    mega_next = _player(MEGA_STARMIE, (CINDERACE, STARYU), prizes=3)

    assert potential._prize_plan(cinderace_next, opponent) > potential._prize_plan(
        mega_next, opponent)


def test_prize_plan_ignores_routes_that_do_not_exceed_the_win_threshold():
    profile = BellmanDeckProfile(
        prize_routes=((MEGA_STARMIE, MEGA_STARMIE),), prizes_to_win=6)
    potential = BoardPotential(_Stats(), registry=_registry(), profile=profile)

    assert potential._prize_plan(_player(MEGA_STARMIE), {"prize": [None] * 6}) == 0.0


def test_prize_plan_counts_a_directly_held_body_needed_by_the_remaining_route():
    profile = BellmanDeckProfile(
        lines=((STARYU, MEGA_STARMIE),),
        prize_routes=((CINDERACE, MEGA_STARMIE, MEGA_STARMIE),),
        prizes_to_win=6,
    )
    potential = BoardPotential(_Stats(), registry=_registry(), profile=profile)
    opponent = {"prize": [None] * 6}
    without_payoff = _player(CINDERACE, (STARYU,))
    with_payoff = _player(CINDERACE, (STARYU,))
    with_payoff["hand"] = [{"id": MEGA_STARMIE}]

    assert potential._prize_plan(with_payoff, opponent) > potential._prize_plan(
        without_payoff, opponent)


def test_strategy_prize_plan_reaches_the_bellman_deck_profile():
    strategy = Strategy(prize_plan=PrizePlan(routes=(
        (CINDERACE, MEGA_STARMIE, MEGA_STARMIE),
        (MEGA_STARMIE, CINDERACE, MEGA_STARMIE),
    )))
    registry = ValueRegistry.from_strategy(
        strategy=strategy, stats=_Stats(), functions=None,
        deck=(CINDERACE, STARYU, MEGA_STARMIE))

    profile = BellmanDeckProfile.from_registry(registry)
    assert profile.prize_routes == strategy.prize_plan.routes
    assert profile.prizes_to_win == strategy.prize_plan.prizes_to_win
