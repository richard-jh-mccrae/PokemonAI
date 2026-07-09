"""Board.search_deck_ids — the within-frame reachability signal behind the mega_lucario Solrock <->
Lunatone pairing doctrine (`_reachable`). A search's revealed `select.deck` IS the full remaining
deck, so a card absent from it is provably unreachable THIS search (exact, no tracker anchor needed);
off a deck-revealing select the field is None and the consumer falls back to the sound deck oracle.
"""
from common.pilot import Pilot
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import DECK, MAIN, TO_HAND, card_opt, make_select, poke, state


def _pilot():
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY)


def test_search_deck_ids_is_the_revealed_search_pool():
    """At a TO_HAND search, `search_deck_ids` is exactly the revealed `select.deck` id set — a card
    present is reachable, one absent (prized/discarded) is not."""
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": 111}, {"id": 222}, {"id": 333}],
                      current=state(active=poke(900, energy=1)))
    board = _pilot()._board(obs, obs["select"])
    assert board.search_deck_ids == frozenset({111, 222, 333})
    assert 444 not in board.search_deck_ids           # absent from the pool = unreachable this search


def test_search_deck_ids_is_none_without_a_deck_reveal():
    """Off a deck-revealing select (e.g. the MAIN menu), the field is None so `_reachable` falls back
    to the sound `deck_definitely_empty_of` oracle rather than treating an empty reveal as a whiff."""
    obs = make_select([card_opt(DECK, 0)], context=MAIN, current=state(active=poke(900, energy=1)))
    board = _pilot()._board(obs, obs["select"])
    assert board.search_deck_ids is None
