"""WP7 — `common.fetch_closure`: the tutor/recycle/search graph + clause predicates lifted OUT of
the Pilot into one pure, Pilot-independent module (ADR-0065). The gamble gain side and the card-worth
keep-cost read ONE implementation; these tests pin the extraction as behaviour-preserving by asserting
PARITY between the pure functions and the ground-truth Pilot delegators on the real shipped decks.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(agent)[0]


def _accessors(pilot):
    stat_of = lambda c: pilot.stats.get(c) if pilot.stats else None
    clauses_of = lambda c: pilot.effects.clauses(c) if pilot.effects else ()
    return stat_of, clauses_of


@pytest.mark.req("REQ-WORTH-0002")
def test_fetch_target_matches_is_the_one_clause_predicate():
    """`fetch_closure.fetch_target_matches(clause, stat)` is the SAME predicate the Pilot exposes as
    `_fetch_target_matches` — Mega Lucario ex (678) matches a `mega` clause and NOT a `basic_pokemon`
    one; a {F} Basic Energy (6) matches a {F}-locked `basic_energy` clause and not a {W}-locked one."""
    from common import fetch_closure
    ml = _shipped_pilot("mega_lucario")
    ml_ex = ml.stats.get(678)
    energy = ml.stats.get(6)
    assert fetch_closure.fetch_target_matches({"target": "mega"}, ml_ex) is True
    assert fetch_closure.fetch_target_matches({"target": "basic_pokemon"}, ml_ex) is False
    assert fetch_closure.fetch_target_matches({"target": "basic_energy", "energy_type": 6}, energy) is True
    assert fetch_closure.fetch_target_matches({"target": "basic_energy", "energy_type": 5}, energy) is False
    assert fetch_closure.fetch_target_matches({"target": "mega"}, None) is False
    # parity with the Pilot delegator on every card of the deck, every target class
    for cid in set(ml.deck):
        st = ml.stats.get(cid)
        for target in ("basic_energy", "energy", "mega", "evolution", "pokemon", "basic_pokemon"):
            clause = {"target": target}
            assert fetch_closure.fetch_target_matches(clause, st) == ml._fetch_target_matches(clause, st)


@pytest.mark.req("REQ-WORTH-0002")
def test_reaccess_outs_pure_function_matches_the_pilot():
    """`fetch_closure.reaccess_outs(cid, counts, stat_of, clauses_of)` == the Pilot's
    `_card_reaccess_outs(cid, counts)` — the closure pointed backwards, now Pilot-free."""
    from common import fetch_closure
    ml = _shipped_pilot("mega_lucario")
    stat_of, clauses_of = _accessors(ml)
    counts = {678: 1, 1121: 4, 1145: 2, 1152: 4, 6: 10}
    assert (fetch_closure.reaccess_outs(678, counts, stat_of, clauses_of)
            == ml._card_reaccess_outs(678, counts) == 1 + 4 + 2)
    assert (fetch_closure.reaccess_outs(6, {6: 10, 1142: 4}, stat_of, clauses_of)
            == ml._card_reaccess_outs(6, {6: 10, 1142: 4}) == 10 + 4)
    assert fetch_closure.reaccess_outs(999999, counts, stat_of, clauses_of) == 0
    # exhaustive parity over the deck as its own sole copy
    for cid in set(ml.deck):
        c = {cid: 2, 1121: 4, 1145: 2}
        assert (fetch_closure.reaccess_outs(cid, c, stat_of, clauses_of)
                == ml._card_reaccess_outs(cid, c))


@pytest.mark.req("REQ-WORTH-0002")
def test_fetch_reaches_pokemon_pure_function_matches_the_pilot():
    """`fetch_closure.fetch_reaches_pokemon(target, cid, counts, ...)` == the Pilot's
    `_fetch_reaches_pokemon` — Poké Pad's `no_rule_box` never reaches the Rule-Box Mega ex."""
    from common import fetch_closure
    ml = _shipped_pilot("mega_lucario")
    stat_of, clauses_of = _accessors(ml)
    counts = {678: 1, 1145: 2, 1152: 4}
    # Mega Signal (1145, mega tutor) reaches 678; Poké Pad (1152, no-Rule-Box) does not
    assert (fetch_closure.fetch_reaches_pokemon(678, 1145, counts, stat_of, clauses_of)
            == ml._fetch_reaches_pokemon(678, 1145, counts))
    assert (fetch_closure.fetch_reaches_pokemon(678, 1152, counts, stat_of, clauses_of)
            == ml._fetch_reaches_pokemon(678, 1152, counts) is False)
    # exhaustive parity: every (tutor, target) pair over the deck
    for tid in set(ml.deck):
        for target in set(ml.deck):
            c = {target: 1}
            assert (fetch_closure.fetch_reaches_pokemon(target, tid, c, stat_of, clauses_of)
                    == ml._fetch_reaches_pokemon(target, tid, c)), (tid, target)
