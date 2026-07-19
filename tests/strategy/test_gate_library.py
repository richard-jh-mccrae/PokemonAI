"""The deadline gate library (ADR-0065; grill Rounds 8-9, `docs/plans/gate-library-scope.md`).

`keep_cost = role_value × [P(need met by deadline | keep) − P(met | shuffle)]`. The gate supplies the
first factor of that difference as ``deploy_odds`` — P(the card's ROLE is realisable by its deadline) —
so a held evolution whose base is provably gone (a dead card) is cheap to shuffle/gamble away, while a
deployable one keeps its full worth. A PARAMETER of the one keep-value equation, never a new rung.
"""
import pytest

from common import gate_library


class _Stat:
    def __init__(self, evolvesFrom=None, name=None):
        self.evolvesFrom = evolvesFrom
        self.name = name


@pytest.mark.req("REQ-GATE-0001")
def test_is_evolution_reads_evolves_from():
    assert gate_library.is_evolution(_Stat(evolvesFrom="Staryu")) is True
    assert gate_library.is_evolution(_Stat(evolvesFrom=None)) is False
    assert gate_library.is_evolution(None) is False


@pytest.mark.req("REQ-GATE-0001")
def test_deploy_odds_is_one_for_a_non_evolution():
    """A Basic / Trainer / Energy realises its role by being held — no evolution deadline, full worth."""
    basic = _Stat(evolvesFrom=None, name="Cinderace")
    assert gate_library.deploy_odds(basic) == 1.0
    assert gate_library.deploy_odds(None) == 1.0


@pytest.mark.req("REQ-GATE-0001")
def test_deploy_odds_is_one_when_the_base_is_reachable_anywhere():
    """A held evolution is deployable — worth keeping — when its base is on board, in hand, or still
    reachable in the deck. Any one of the three suffices."""
    mega = _Stat(evolvesFrom="Riolu", name="Mega Lucario ex")
    assert gate_library.deploy_odds(mega, base_in_play=True) == 1.0
    assert gate_library.deploy_odds(mega, base_in_hand=True) == 1.0
    assert gate_library.deploy_odds(mega, base_reachable_in_deck=True) == 1.0


@pytest.mark.req("REQ-GATE-0001")
def test_deploy_odds_is_zero_when_the_base_is_provably_gone():
    """The undeployable case (ep83966336 f44): a Mega Lucario ex with NO Riolu in play, hand, OR deck is
    a dead card — its role can never be realised, so its keep-value collapses (shuffle it to dig)."""
    mega = _Stat(evolvesFrom="Riolu", name="Mega Lucario ex")
    assert gate_library.deploy_odds(mega, base_in_play=False, base_in_hand=False,
                                    base_reachable_in_deck=False) == 0.0


@pytest.mark.req("REQ-GATE-0002")
def test_fetch_deploy_odds_gates_a_dead_fetcher():
    """The fetcher gate (searcher/recycler leg — acceptance pin ep83457493 f31): a fetch Trainer whose
    every target is PROVABLY dead realises no role (0.0 → sheds freely, Ultra-Ball fodder); anything
    less than proven deadness keeps full worth (1.0 — errs toward keep, like the evolution gate)."""
    assert gate_library.fetch_deploy_odds(targets_exhausted=True) == 0.0
    assert gate_library.fetch_deploy_odds(targets_exhausted=False) == 1.0
    assert gate_library.fetch_deploy_odds() == 1.0


@pytest.mark.req("REQ-GATE-0002")
def test_pilot_deploy_odds_collapses_a_dead_searcher_and_recycler():
    """The Pilot resolver (`planner._deploy_odds`) mirrors the play-side rungs' SOUND predicates:
    a Buddy-Buddy Poffin whose whole deck whiff-set sits in `Board.deck_empty_ids` prices 0
    (`dont-search-an-empty-deck`'s premise), a Night Stretcher on an all-dead recycle pool prices 0
    (`dont-recycle-the-dead`'s premise) — and both keep FULL worth when any target is live. The gate
    then collapses `_keep_cost` so the dead fetcher no longer props up the refresh SHED
    (the ep83457493 f31 pin: shed the dead hand into Harlequin)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from train.tune import _build_pilot
    from common.pilot import Board
    ms = _build_pilot("mega_starmie")[0]
    poffin, stretcher = 1086, 1097
    fetch_set = ms._search_deck_set(poffin)
    assert fetch_set, "Poffin must have a deck whiff-set for this test to mean anything"
    live, counts = Board(), {cid: 1 for cid in fetch_set}
    dead_search = Board(deck_empty_ids=frozenset(fetch_set))
    assert ms._deploy_odds(poffin, live, counts) == 1.0
    assert ms._deploy_odds(poffin, dead_search, counts) == 0.0
    assert ms._keep_cost(poffin, counts, 40, 6, dead_search) == 0.0     # the SHED sees a free shed
    assert ms._keep_cost(poffin, counts, 40, 6, live) > 0.0
    dead_pool = Board(recycle_dead_only=True)
    assert ms._deploy_odds(stretcher, dead_pool, counts) == 0.0
    assert ms._deploy_odds(stretcher, Board(), counts) == 1.0
