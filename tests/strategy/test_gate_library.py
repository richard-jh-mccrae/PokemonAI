"""The deadline gate library (ADR-0065 §Round 8-9, `docs/plans/gate-library-scope.md`).

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
