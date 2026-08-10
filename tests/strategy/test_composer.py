"""The sequence composer (`common/composer.py`, Issue #385; spec Issue #263).

Where `test_apply_transitions.py` asserts one option -> one board, this file asserts the LOOP: the
subset lattice, refusal semantics, the terminal sum, the tie-break, and instance re-resolution across
a permuted sequence. Same seam as that file — a dict-backed Stat Provider and hand-built zone dicts,
no engine boot, so it runs DLL-free on both platforms.
"""
from __future__ import annotations

import copy
import os
import subprocess
import sys
import pytest

from common import apply_option as ao
from common import board_delta as bd
from common import composer as cp
from common import sound_rules
from common.board_delta import Unmodellable
from common.cards import CardFunctions
from common.effects import CardEffects
from common.option_equivalence import AREA_ACTIVE, AREA_BENCH, AREA_HAND
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.state_model import StateModel
from common.state_value import state_value
from common.strategy.combat import CombatMath
from common.strategy.context import _ABILITY, _ATTACH, _ATTACK, _END, _EVOLVE, _PLAY, _RETREAT

MAIN = bd.CONTEXT_MAIN
ACTIVE, BENCH, HAND = AREA_ACTIVE, AREA_BENCH, AREA_HAND
COLORLESS, FIGHTING, PSYCHIC, DRAGON, DARKNESS = 0, 6, 5, 9, 7

# ── the pool — every row quoted from `data/EN_Card_Data.csv`; 1159 is a synthetic flat-HP Tool ────
RIOLU, MEGA_LUC, MUNKIDORI = 677, 678, 112
AURA_JAB, MEGA_BRAVE = 982, 983
E_F, TOOL, ITEM = 6, 1159, 1125
SUPPORTER, STADIUM = 1200, 1242
# Ultra Ball — the REAL costed search ("discard 2 other cards"). Kept OUT of `_STATS`, like the two
# Trainer rows below, so every other fixture's menu stays what it was.
ULTRA_BALL = 1121
_STATS_ULTRA = CardStat(ULTRA_BALL, name="Ultra Ball", cardType=1)

_STATS = {
    RIOLU: CardStat(RIOLU, name="Riolu", hp=80, energyType=FIGHTING),
    MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, ex=True,
                       energyType=FIGHTING, evolvesFrom="Riolu", attacks=(AURA_JAB, MEGA_BRAVE),
                       minAttackCost=1, minCostDamage=130, maxDamage=270, maxDamageCost=2),
    MUNKIDORI: CardStat(MUNKIDORI, name="Munkidori", hp=110, energyType=PSYCHIC),
    E_F: CardStat(E_F, name="Basic {F} Energy", cardType=5, energyType=FIGHTING),
    TOOL: CardStat(TOOL, synthetic=True, name="Flat-HP Tool", cardType=2, hpBonus=100),
    ITEM: CardStat(ITEM, name="Master Ball", cardType=1),
}
# Names and `cardType` are the CSV's own — `tests/scouting/test_cardstat_fixture_facts.py` audits
# every `CardStat(...)` literal field-for-field, so an invented name on a real id fails the build.
_STATS_SUPPORTER = CardStat(SUPPORTER, name="Kofu", cardType=3)
_STATS_STADIUM = CardStat(STADIUM, name="Community Center", cardType=4)

_ATTACKS = {AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,)),
            MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2,
                                   energyTypes=(FIGHTING, FIGHTING))}


def _combat(clauses=None, *, extra_stats=None):
    return CombatMath(DictCardStatProvider({**_STATS, **(extra_stats or {})}, attacks=_ATTACKS),
                      functions=CardFunctions({}), transients=None,
                      effects=CardEffects(clauses or {}))


def _body(cid, *, serial=1, energy=(), tools=(), appeared=False, damage=0, seat=0):
    max_hp = _STATS[cid].hp
    return {"id": cid, "serial": serial, "playerIndex": seat,
            "hp": max_hp - damage, "maxHp": max_hp, "appearThisTurn": appeared,
            "energies": list(energy),
            "energyCards": [{"id": E_F, "serial": 900 + i, "playerIndex": seat}
                            for i, _ in enumerate(energy)],
            "tools": [{"id": t, "serial": 800 + i, "playerIndex": seat} for i, t in enumerate(tools)],
            "preEvolution": []}


def _player(*, active=None, bench=(), hand=(), prize=4, deck_count=30, seat=0):
    return {"active": [active] if active else [], "bench": list(bench), "benchMax": 5,
            "hand": [{"id": c, "serial": 700 + i, "playerIndex": seat} for i, c in enumerate(hand)],
            "handCount": len(hand), "discard": [], "prize": [None] * prize,
            "deckCount": deck_count, **{f: False for f in bd.CONDITION_FLAGS}}


def _obs(me, opp=None, *, options=(), **current):
    opp = opp if opp is not None else _player(active=_body(MUNKIDORI, serial=50, seat=1), seat=1)
    state = {"players": [me, opp], "yourIndex": 0, "turn": 5,
             "energyAttached": False, "supporterPlayed": False, "retreated": False,
             "stadiumPlayed": False, "stadium": []}
    state.update(current)
    return {"current": state, "logs": [], "select": {"context": MAIN, "option": list(options)}}


def _model(obs, clauses=None):
    return StateModel.build(obs, combat=_combat(clauses), deck=[E_F] * 8)


# ── the subset lattice ───────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0001")
@pytest.mark.parametrize("n, subsets, ordered", [(3, 8, 16), (4, 16, 65), (5, 32, 326)])
def test_the_lattice_emits_SUBSETS_not_ORDERED_PREFIXES(n, subsets, ordered):
    import math

    members = tuple(range(n))
    lattice = cp.subset_lattice(members)
    assert len(lattice) == subsets == 2 ** n
    assert len(set(lattice)) == len(lattice)          # duplicates are never CREATED, not merged
    assert sum(math.perm(n, k) for k in range(n + 1)) == ordered


@pytest.mark.req("REQ-COMPOSER-0001")
def test_every_lattice_member_is_in_ONE_canonical_order():
    lattice = cp.subset_lattice(("a", "b", "c", "d"))
    assert all(list(s) == sorted(s) for s in lattice)
    assert len({frozenset(s) for s in lattice}) == len(lattice)


@pytest.mark.req("REQ-COMPOSER-0001")
def test_the_lattice_rule_and_the_beams_rule_are_the_SAME_rule():
    """A second spelling is the drift ADR-0087 charges for one store over."""
    members = ("a", "b", "c")
    grown = [()]
    for m in members:
        grown = grown + [p + (m,) for p in grown if cp._admissible_in_block(m, p)]
    assert sorted(grown) == sorted(cp.subset_lattice(members))


# ── instance re-resolution: the silent failure ───────────────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0002")
def test_a_stored_option_replayed_from_a_permuted_position_names_a_DIFFERENT_CARD():
    """**The positive control for the next test**: the naive replay lands on a card that is genuinely
    there and genuinely wrong, which is why this failure is silent rather than loud."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F, TOOL, ITEM, MEGA_LUC]))
    before = _model(obs)
    assert before.source_obs["current"]["players"][0]["hand"][3]["id"] == MEGA_LUC
    after = ao.apply_option(before, {"type": _ATTACH, "area": HAND, "index": 0,
                                     "inPlayArea": ACTIVE, "inPlayIndex": 0})
    naive = after.source_obs["current"]["players"][0]["hand"][3] if len(
        after.source_obs["current"]["players"][0]["hand"]) > 3 else None
    assert naive is None                          # index 3 no longer exists at all
    assert after.source_obs["current"]["players"][0]["hand"][2]["id"] == MEGA_LUC


@pytest.mark.req("REQ-COMPOSER-0002")
def test_re_resolution_follows_the_SERIAL_not_the_index():
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F, TOOL, ITEM, MEGA_LUC]))
    before = _model(obs)
    stamped = cp.stamp_origin(before, {"type": _PLAY, "index": 3})
    after = ao.apply_option(before, {"type": _ATTACH, "area": HAND, "index": 0,
                                     "inPlayArea": ACTIVE, "inPlayIndex": 0})
    again = cp.resolve_against(after, stamped)
    assert again["index"] == 2                    # NOT the stored 3
    hand = after.source_obs["current"]["players"][0]["hand"]
    assert hand[again["index"]]["id"] == MEGA_LUC   # the same CARD the option originally named


@pytest.mark.req("REQ-COMPOSER-0002")
def test_re_resolution_disambiguates_a_reused_serial_by_card_id():
    """Fixture serials can repeat, so a serial-only stamp must not turn a later attach into a play."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F, TOOL]))
    for card in obs["current"]["players"][0]["hand"]:
        card["serial"] = 7
    before = _model(obs)
    stamped = cp.stamp_origin(before, {"type": _PLAY, "index": 1})
    after = ao.apply_option(before, {"type": _ATTACH, "area": HAND, "index": 0,
                                     "inPlayArea": ACTIVE, "inPlayIndex": 0})
    again = cp.resolve_against(after, stamped)
    assert again["index"] == 0
    assert after.source_obs["current"]["players"][0]["hand"][again["index"]]["id"] == TOOL


@pytest.mark.req("REQ-COMPOSER-0002")
def test_a_consumed_card_makes_its_option_UNRESOLVABLE_rather_than_re_pointed():
    """Dropping it is the fail-closed answer; re-pointing it at whatever now sits at that index is
    the bug."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F, TOOL]))
    before = _model(obs)
    stamped = cp.stamp_origin(before, {"type": _ATTACH, "area": HAND, "index": 0,
                                       "inPlayArea": ACTIVE, "inPlayIndex": 0})
    after = ao.apply_option(before, dict(stamped))
    assert cp.resolve_against(after, stamped) is None


@pytest.mark.req("REQ-COMPOSER-0002")
def test_the_stamp_never_leaves_the_module():
    """Asserted on every `Step.option` and `Candidate.terminal` reachable from a real `compose`, not
    on `strip_origin` alone — the helper passes while a construction site forgets to call it."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F]))
    stamped = cp.stamp_origin(_model(obs), {"type": _PLAY, "index": 0})
    assert cp._ORIGIN in stamped                     # positive control: the stamp is really applied
    assert cp.strip_origin(stamped) == {"type": _PLAY, "index": 0}

    menu_obs, options = _menu_obs()
    result = cp.compose(_model(menu_obs), options, k=99, depth=4)
    escaped = [c for c in result.candidates
               if any(cp._ORIGIN in s.option for s in c.steps)
               or (c.terminal is not None and cp._ORIGIN in c.terminal)]
    assert escaped == [], f"the composer's private stamp escaped on {len(escaped)} candidate(s)"


# ── legality re-checked on a synthesized board ───────────────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0003")
def test_the_beam_cannot_sequence_TWO_manual_energy_attaches():
    """`docs/rules.md` §3: 1 manual attach per turn. At depth >= 1 there is no menu and `apply_option`
    models rather than polices, so this gate is all that stands between the beam and two Energy."""
    obs = _obs(_player(active=_body(RIOLU), bench=[_body(MUNKIDORI, serial=2)], hand=[E_F, E_F]))
    model = _model(obs)
    first = {"type": _ATTACH, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0}
    after = ao.apply_option(model, first)
    assert cp._still_legal(model, {"type": _ATTACH, "area": HAND, "index": 1,
                                   "inPlayArea": ACTIVE, "inPlayIndex": 0}) is True
    assert cp._still_legal(after, {"type": _ATTACH, "area": HAND, "index": 0,
                                   "inPlayArea": ACTIVE, "inPlayIndex": 0}) is False


@pytest.mark.req("REQ-COMPOSER-0003")
def test_a_body_benched_this_turn_cannot_be_evolved_in_the_same_sequence():
    """`docs/rules.md` §4, and the reason `_EVOLVE`'s footprint declares `new_in_play` as a READ."""
    obs = _obs(_player(active=_body(RIOLU), hand=[RIOLU, MEGA_LUC]))
    model = _model(obs)
    after = ao.apply_option(model, {"type": _PLAY, "index": 0})
    bench = after.mine.bench
    assert bench and bench[0].new_in_play is True
    assert cp._still_legal(after, {"type": _EVOLVE, "area": HAND, "index": 0,
                                   "inPlayArea": BENCH, "inPlayIndex": 0}) is False
    assert cp._still_legal(after, {"type": _EVOLVE, "area": HAND, "index": 0,
                                   "inPlayArea": ACTIVE, "inPlayIndex": 0}) is True


@pytest.mark.req("REQ-COMPOSER-0003")
def test_a_deploy_onto_a_FULL_bench_is_illegal_rather_than_a_coverage_gap():
    """`board_delta._play` refuses it as an `Unmodellable`, which the composer would turn into a
    COVERAGE GAP — a phantom modelling-backlog entry. Legality catches it first, off ``benchMax``."""
    full = _player(active=_body(RIOLU), bench=[_body(MUNKIDORI, serial=i) for i in range(2, 7)],
                   hand=[RIOLU])
    model = _model(_obs(full))
    deploy = {"type": _PLAY, "index": 0}
    assert len(model.mine.bench) == 5 and cp._still_legal(model, deploy) is False
    assert cp.compose(model, [deploy, {"type": _END}]).gaps == ()

    room = _player(active=_body(RIOLU), bench=[_body(MUNKIDORI, serial=2)], hand=[RIOLU])
    assert cp._still_legal(_model(_obs(room)), deploy) is True   # positive control


@pytest.mark.req("REQ-COMPOSER-0003")
def test_a_beam_that_keeps_no_candidates_is_CALLER_ERROR_and_raises():
    """`_admit` and `_prune_nodes` index the k-th as ``[k - 1]``, so ``k=0`` admits the entire menu.
    A modelling gap refuses; a caller error raises."""
    obs, options = _menu_obs()
    model = _model(obs)
    for bad in ({"k": 0}, {"k": -1}, {"depth": -1}):
        with pytest.raises(ValueError, match="beam must keep at least one candidate"):
            cp.compose(model, options, **bad)


@pytest.mark.req("REQ-COMPOSER-0003")
def test_the_one_supporter_per_turn_is_spent_once():
    """`docs/rules.md` §3. Carries the case that would OTHERWISE PASS — on a fresh board the same
    option is legal — so this asserts the ALLOWANCE, not that the option is unrecognised."""
    stats = {**_STATS, SUPPORTER: _STATS_SUPPORTER}
    combat = CombatMath(DictCardStatProvider(stats, attacks=_ATTACKS),
                        functions=CardFunctions({}), transients=None, effects=CardEffects({}))
    obs = _obs(_player(active=_body(RIOLU), hand=[SUPPORTER]))
    model = StateModel.build(obs, combat=combat, deck=[E_F] * 8)
    play = {"type": _PLAY, "area": HAND, "index": 0}
    assert cp._still_legal(model, play) is True                    # the otherwise-passing case
    spent = _obs(_player(active=_body(RIOLU), hand=[SUPPORTER]), supporterPlayed=True)
    assert cp._still_legal(StateModel.build(spent, combat=combat, deck=[E_F] * 8), play) is False


@pytest.mark.req("REQ-COMPOSER-0003")
def test_the_one_stadium_per_turn_is_spent_once_AND_must_differ_from_the_one_in_play():
    """`docs/rules.md` §3 — 1 per turn *"and only if it differs from the one in play"*: TWO limits, so
    two negative cases. Reading only the allowance lets the composer re-play the Stadium already down."""
    stats = {**_STATS, STADIUM: _STATS_STADIUM}
    combat = CombatMath(DictCardStatProvider(stats, attacks=_ATTACKS),
                        functions=CardFunctions({}), transients=None, effects=CardEffects({}))

    def _m(**current):
        obs = _obs(_player(active=_body(RIOLU), hand=[STADIUM]), **current)
        return StateModel.build(obs, combat=combat, deck=[E_F] * 8)

    play = {"type": _PLAY, "area": HAND, "index": 0}
    assert cp._still_legal(_m(), play) is True                     # the otherwise-passing case
    assert cp._still_legal(_m(stadiumPlayed=True), play) is False   # the per-turn allowance
    same = _m(stadium=[{"id": STADIUM, "serial": 77, "playerIndex": 0}])
    assert cp._still_legal(same, play) is False, (
        "a Stadium identical to the one already in play is not a legal play — reading only the "
        "allowance would let the composer re-play it for a board-neutral, silently wrong step")


@pytest.mark.req("REQ-COMPOSER-0003")
def test_the_one_manual_retreat_is_spent_once():
    """`docs/rules.md` §3 — Retreat (manual) is 1 per turn."""
    obs = _obs(_player(active=_body(RIOLU, energy=[FIGHTING]),
                       bench=[_body(MUNKIDORI, serial=2)], hand=[]))
    model = _model(obs)
    assert cp._still_legal(model, {"type": _RETREAT}) is True
    assert cp._still_legal(ao.apply_option(model, {"type": _RETREAT}), {"type": _RETREAT}) is False


# ── deferred-target expansion (§S7 / ADR-0121 decisions 1, 4 and 6) ──────────────────────────────


def _retreat_board(bench=None):
    """A payable Retreat Cost and a Bench to promote INTO, so `_RETREAT` is a CHOICE node. Two
    distinct bench bodies by default — a one-member space cannot tell `max` from `expected()`."""
    bench = bench if bench is not None else [_body(MEGA_LUC, serial=2, energy=[FIGHTING]),
                                             _body(MUNKIDORI, serial=3)]
    return _model(_obs(_player(active=_body(RIOLU, serial=1, energy=[FIGHTING]), bench=bench)))


@pytest.mark.req("REQ-COMPOSER-0009")
def test_an_UNEXPANDED_retreat_prices_at_EXACTLY_zero_which_is_the_defect():
    """ADR-0121's premise: `_retreat` writes only ``allowance_retreat_used`` and no `state_value`
    family reads it, so the delta is a hard zero. POSITIVE CONTROL for the expansion tests below."""
    model = _retreat_board()
    before = state_value(model)
    after = ao.apply_option(model, {"type": _RETREAT})          # default: expansion OFF
    assert not isinstance(after, ao.Expectation), "the DEFAULT path must stay the point transition"
    assert state_value(after) - before == 0.0


@pytest.mark.req("REQ-COMPOSER-0009")
def test_expansion_turns_that_zero_into_a_REAL_score_over_one_class_per_target():
    """ADR-0121 decision 1: expansion, not admission — one candidate per legal instance."""
    model = _retreat_board()
    choice = cp.choose_target(model, {"type": _RETREAT})
    assert choice is not None and len(choice.scored) == 2, "one class per promotable bench body"
    assert choice.leaf != state_value(model), "expansion must MOVE the score off the flat zero"
    assert [s.rank for s in choice.scored] == [1, 2]
    assert choice.scored[0].leaf >= choice.scored[1].leaf, "ordered best-first"


@pytest.mark.req("REQ-COMPOSER-0009")
def test_the_composer_ranks_a_CHOICE_node_by_MAX_and_never_by_expected():
    """§S3. Ranking on the mean under-prices every choice node — a PRUNED option, not a cheap one.
    Asserted against the composer's own delta: a helper-only check passes while `_one_ply` is wrong."""
    model = _retreat_board()
    expectation = __import__("common.board_choice", fromlist=["x"]).deferred_target(
        model, {"type": _RETREAT}, seat_index=0)
    hi = expectation.best(state_value)
    mean = expectation.expected(state_value)
    assert hi > mean, "fixture is vacuous unless the two bounds disagree"

    result = cp.compose(model, [{"type": _RETREAT}, {"type": _END}])
    delta = dict(result.order)[0]
    assert delta == pytest.approx(hi - state_value(model)), "ranked by max"
    assert delta != pytest.approx(mean - state_value(model)), "NOT ranked by the mean"


@pytest.mark.req("REQ-COMPOSER-0009")
def test_rank_targets_leaf_IS_Expectation_best_reached_a_second_way():
    """Two spellings of one rule (ADR-0087). A `min`/`max` slip or an inverted sort key is exactly
    what makes them disagree on a fixture with distinct class values."""
    from common import board_choice

    model = _retreat_board()
    expectation = board_choice.deferred_target(model, {"type": _RETREAT}, seat_index=0)
    assert len({round(state_value(c.model), 12) for c in expectation.classes}) > 1, (
        "fixture is vacuous unless the classes actually differ")
    assert cp.rank_targets(model, expectation).leaf == pytest.approx(
        expectation.best(state_value))


@pytest.mark.req("REQ-COMPOSER-0009")
def test_the_OTHER_expectation_producer_is_also_ranked_by_MAX(monkeypatch):
    """§S12.1: the REVEAL branch; the test above covers the CHOICE dispatch. The producer is STUBBED
    deliberately — a real fetch enumerates classes that score identically, so it would be vacuous."""
    from common import board_expectation as bx

    # Real routing: Master Ball's committed clause shape, so the option genuinely classifies as a
    # reveal rather than being forced down that path.
    clauses = {ITEM: [{"kind": "fetch", "target": "pokemon", "zone": "deck"}]}
    deck = [RIOLU] * 3 + [MEGA_LUC] + [E_F] * 6 + [ITEM]
    obs = _obs(_player(active=_body(RIOLU, energy=[FIGHTING]), hand=[ITEM],
                       deck_count=len(deck)))
    model = StateModel.build(obs, combat=_combat(clauses), deck=deck)
    play = {"type": _PLAY, "area": HAND, "index": 0}
    assert cp._reveal_rides(model, play), "positive control: the option must really route as a reveal"

    # Two classes that DO differ, borrowed from a producer whose outputs are known to separate.
    donor = _retreat_board()
    real = __import__("common.board_choice", fromlist=["x"]).deferred_target(
        donor, {"type": _RETREAT}, seat_index=0)
    stub = ao.Expectation(classes=(ao.OutcomeClass(0.75, model=real.classes[0].model),
                                   ao.OutcomeClass(0.25, model=real.classes[1].model)))
    hi, mean = stub.best(state_value), stub.expected(state_value)
    assert hi != pytest.approx(mean), "fixture is vacuous unless the two bounds disagree"
    monkeypatch.setattr(bx, "expectation", lambda *a, **kw: stub)

    result = cp.compose(model, [play, {"type": _END}])
    delta = dict(result.order)[0]
    assert delta == pytest.approx(hi - state_value(model)), "the reveal branch must rank by MAX"
    assert delta != pytest.approx(mean - state_value(model)), "NOT by the availability-weighted mean"
    assert result.bounds[0].best == pytest.approx(hi)
    assert result.bounds[0].expected == pytest.approx(mean)


@pytest.mark.req("REQ-COMPOSER-0009")
def test_the_reveal_branch_uses_expected_for_a_DEALT_outcome(monkeypatch):
    """The player cannot choose a coin result, so the composer must not price the best outcome."""
    from common import board_expectation as bx

    clauses = {ITEM: [{"kind": "fetch", "target": "pokemon", "zone": "deck"}]}
    deck = [RIOLU] * 3 + [MEGA_LUC] + [E_F] * 6 + [ITEM]
    obs = _obs(_player(active=_body(RIOLU, energy=[FIGHTING]), hand=[ITEM], deck_count=len(deck)))
    model = StateModel.build(obs, combat=_combat(clauses), deck=deck)
    donor = _retreat_board()
    real = __import__("common.board_choice", fromlist=["x"]).deferred_target(
        donor, {"type": _RETREAT}, seat_index=0)
    dealt = ao.Expectation(classes=(ao.OutcomeClass(0.75, model=real.classes[0].model),
                                    ao.OutcomeClass(0.25, model=real.classes[1].model)),
                          resolution=ao.DEALT)
    best, expected = dealt.best(state_value), dealt.expected(state_value)
    assert best != pytest.approx(expected), "fixture is vacuous unless the outcomes differ"
    monkeypatch.setattr(bx, "expectation", lambda *a, **kw: dealt)

    result = cp.compose(model, [{"type": _PLAY, "area": HAND, "index": 0}, {"type": _END}])
    assert dict(result.order)[0] == pytest.approx(expected - state_value(model))
    assert dict(result.order)[0] != pytest.approx(best - state_value(model))
    assert result.bounds[0].best == pytest.approx(best)
    assert result.bounds[0].expected == pytest.approx(expected)


@pytest.mark.req("REQ-COMPOSER-0009")
def test_BOTH_bounds_reach_the_telemetry_with_the_dropped_mass():
    """§S3.4/§S3.5. The max over-reads a 5%-likely target and `expected()` under-reads a free choice;
    the GAP is the exposure. ``total_probability`` catches a capped enumeration reading as complete."""
    model = _retreat_board()
    result = cp.compose(model, [{"type": _RETREAT}, {"type": _END}])
    assert result.bounds, "an expectation node must reach `ComposerResult.bounds`"
    node = result.bounds[0].working()
    assert node["best"] > node["expected"]
    assert node["gap"] == pytest.approx(node["best"] - node["expected"])
    assert node["classes"] == 2 and node["truncated"] == 0
    assert node["total_probability"] == pytest.approx(1.0)
    assert result.stats["expectation_nodes"] == len(result.bounds)


@pytest.mark.req("REQ-COMPOSER-0009")
def test_an_expanded_family_holds_exactly_ONE_beam_slot():
    """ADR-0121 decision 4 — parent-slot beam accounting. Expansion is an EVALUATION-time fan-out:
    score every instance, argmax, emit ONE candidate, so beam width `k` keeps its meaning."""
    model = _retreat_board(bench=[_body(MEGA_LUC, serial=2, energy=[FIGHTING]),
                                  _body(MUNKIDORI, serial=3),
                                  _body(RIOLU, serial=4)])
    options = [{"type": _RETREAT}, {"type": _END}]
    result = cp.compose(model, options)
    assert result.stats["expanded_families"] == 1
    assert result.stats["expansion_children"] >= 2, "the family really did fan out"
    # ONE entry in the depth-0 ordering, not one per instance — `order` is the beam's own view.
    assert [i for i, _d in result.order].count(0) == 1
    assert len(result.order) <= len(options)


@pytest.mark.req("REQ-COMPOSER-0009")
def test_the_chosen_target_travels_on_the_step_and_names_which_instance_won():
    """D4 emits ``(parent_option, chosen_target, score)``; the runner-up is its accepted loss."""
    model = _retreat_board()
    result = cp.compose(model, [{"type": _RETREAT}, {"type": _END}])
    steps = [s for c in result.candidates for s in c.steps if s.index == 0]
    assert steps, "the retreat must appear as a step somewhere in the beam"
    assert steps[0].chosen_target, "the winning instance must be named on the Step"
    assert steps[0].target_classes == 2
    choice = cp.choose_target(model, {"type": _RETREAT})
    assert choice.runner_up is not None and choice.runner_up <= choice.leaf


@pytest.mark.req("REQ-COMPOSER-0009")
def test_the_replan_evaluator_is_ONE_function_shared_by_BOTH_sites():
    """ADR-0121 decision 6 / ADR-0100 §9. Issue #387 wires the identical function at the follow-up
    select, which does not enumerate — so `rank_targets` must take nothing frame-specific."""
    import inspect

    model = _retreat_board()
    expectation = __import__("common.board_choice", fromlist=["x"]).deferred_target(
        model, {"type": _RETREAT}, seat_index=0)
    # Compared on the SCALARS: each call synthesizes fresh `StateModel`s, so object equality would
    # measure identity rather than agreement.
    direct, front = cp.rank_targets(model, expectation), cp.choose_target(model, {"type": _RETREAT})
    assert direct.working() == front.working()
    assert [(s.rank, s.leaf, s.fingerprint) for s in direct.scored] == \
           [(s.rank, s.leaf, s.fingerprint) for s in front.scored]
    params = list(inspect.signature(cp.rank_targets).parameters)
    assert params == ["model", "expectation"], (
        "the evaluator must take a board and an enumeration — anything frame-specific would stop "
        "Issue #387 from calling it at the follow-up select")
    assert "rank_targets" in cp.__all__ and "choose_target" in cp.__all__


@pytest.mark.req("REQ-COMPOSER-0009")
def test_expansion_is_UNCONDITIONAL_here_and_still_DEFAULT_OFF_at_the_seam():
    """§S7.4. The composer is *written against* expansion, so it is not switchable here; every OTHER
    caller keeps the seam default. The `PROFILE` flag is RETIRED — see the final assertion."""
    import inspect

    from common import runtime

    assert "deferred_target_expansion" not in runtime.PROFILE, (
        "the flag was an orphan declared to expire with Issue #386, which has landed — a knob the "
        "composer never reads reads as a kill-switch for a capability that is always on")
    assert inspect.signature(ao.apply_option).parameters[
        "expand_deferred_targets"].default is False
    source = inspect.getsource(cp._one_ply)
    assert "expand_deferred_targets=True" in source, "the composer must opt IN at its call site"
    # Parsed, not grepped: the composer's own header discusses `runtime.PROFILE`, and a line-level
    # scan would fire on that prose.
    import ast

    tree = ast.parse(inspect.getsource(cp))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
               for alias in node.names}
    imports |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                for alias in node.names}
    assert not {"runtime", "common.runtime"} & imports, (
        "the composer reads no deployment flag — expansion is intrinsic to its correctness, so it "
        "is unconditional here and may never be gated by one")
    assert "PROFILE" not in {getattr(n, "attr", None) for n in ast.walk(tree)
                             if isinstance(n, ast.Attribute)}


# ── the terminal sum ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0004")
def test_end_turn_is_worth_exactly_zero():
    obs = _obs(_player(active=_body(RIOLU)))
    assert cp.terminal_ev(_model(obs), {"type": _END}) == (0.0, None, "")


@pytest.mark.req("REQ-COMPOSER-0004")
def test_an_attack_is_priced_through_attack_ev_and_reads_TOTAL_not_the_dict_sum():
    """`AttackEV.working()` is FROZEN and ASYMMETRIC — it omits ``total`` and emits ``next_turn_cost``
    POSITIVE while ``total`` subtracts it, so summing the dict gives ``total + 2 x next_turn_cost``."""
    obs = _obs(_player(active=_body(MEGA_LUC, energy=[FIGHTING, FIGHTING])))
    model = _model(obs)
    ev, detail, gap = cp.terminal_ev(model, {"type": _ATTACK, "attackId": MEGA_BRAVE})
    assert gap == "" and detail is not None
    assert ev == pytest.approx(detail.total)
    if detail.next_turn_cost:
        assert ev != pytest.approx(sum(detail.working().values()))


@pytest.mark.req("REQ-COMPOSER-0004")
def test_an_attack_with_no_matching_leg_is_a_COVERAGE_GAP_not_a_zero():
    """A 0 delta is never explored, not undervalued — so an unpriceable attack must say so."""
    obs = _obs(_player(active=_body(MEGA_LUC, energy=[FIGHTING, FIGHTING])))
    ev, detail, gap = cp.terminal_ev(_model(obs), {"type": _ATTACK, "attackId": 999999})
    assert ev == 0.0 and detail is None
    assert "UNKNOWN" in gap and "999999" in gap


# ── the CONTINUATION sum: a line the composer CUT is not one that ENDED (ADR-0129) ────────────────


def _ranked(index, option, *, delta=0.0, after=None, refused=False, gap="", truncated=0):
    """The constructors are tested DIRECTLY because the property is which summand each carries — a
    beam run proves it only on whatever board happened to truncate."""
    return cp._Ranked(index=index, option=option, key=(0, 0, index), delta=delta, after=after,
                      fate="modelled", footprint=None, refused=refused, gap=gap,
                      truncated=truncated)


@pytest.mark.req("REQ-COMPOSER-0004")
def test_a_board_with_no_affordable_attack_continues_at_exactly_zero():
    """``default=0.0`` turns `attack_ev_legs`'s empty return into a real zero, not a `max()` on ()."""
    obs = _obs(_player(active=_body(RIOLU)))          # Riolu carries no attacks in the pool
    assert cp.continuation_ev(_model(obs)) == 0.0


@pytest.mark.req("REQ-COMPOSER-0004")
@pytest.mark.parametrize("blocker, current", [
    ("asleep", {}),
    ("paralyzed", {}),
    # The starting player skips the attack step on turn 1 (`docs/rules.md` §first-turn).
    (None, {"turn": 1}),
])
def test_a_board_the_RULES_forbid_an_attack_on_continues_at_zero(blocker, current):
    me = _player(active=_body(MEGA_LUC, energy=[FIGHTING, FIGHTING]))
    if blocker:
        me[blocker] = True
    assert cp.continuation_ev(_model(_obs(me, **current))) == 0.0
    # Positive control: the SAME board without the blocker prices a non-zero continuation.
    clean = _player(active=_body(MEGA_LUC, energy=[FIGHTING, FIGHTING]))
    assert cp.continuation_ev(_model(_obs(clean))) > 0.0


@pytest.mark.req("REQ-COMPOSER-0004")
def test_the_continuation_IS_terminal_evs_own_answer_for_the_best_attack_on_the_menu():
    """Two spellings of one equation may not drift — the claim that ADR-0129 adds *no new math*."""
    obs = _obs(_player(active=_body(MEGA_LUC, energy=[FIGHTING, FIGHTING])))
    model = _model(obs)
    per_option = [cp.terminal_ev(model, {"type": _ATTACK, "attackId": a})[0]
                  for a in (AURA_JAB, MEGA_BRAVE)]
    assert cp.continuation_ev(model) == max(per_option)
    assert max(per_option) > 0.0                     # the comparison is not two zeros agreeing


@pytest.mark.req("REQ-COMPOSER-0004")
def test_a_TRUNCATED_line_carries_the_continuation_as_its_terminal_summand():
    """ADR-0129: a reveal-terminated candidate scored ``leaf + 0`` against lines carrying a prize."""
    obs = _obs(_player(active=_body(MEGA_LUC, energy=[FIGHTING, FIGHTING]), hand=[ITEM]))
    model = _model(obs)
    node = cp._Node(model=model, leaf=0.25)
    cand = cp._gap_or_reveal_candidate(node, _ranked(0, {"type": _PLAY, "index": 0}, delta=0.5))
    expected = cp.continuation_ev(model)
    assert expected > 0.0                            # the assertion below is not 0 == 0
    assert cand.terminal_ev == expected
    assert cand.score == pytest.approx(cand.leaf + expected)
    assert cand.leaf == pytest.approx(0.75)          # `_Ranked.delta` still enters the LEAF, not here


@pytest.mark.req("REQ-COMPOSER-0004")
def test_a_REFUSED_option_still_carries_EXACTLY_zero_and_keeps_the_nodes_own_leaf():
    """A refusal's board never moved, so its value is UNKNOWN — a different claim from *"the turn
    continues"* — and it keeps the gap flag `selection_key` sorts on."""
    obs = _obs(_player(active=_body(MEGA_LUC, energy=[FIGHTING, FIGHTING]), hand=[ITEM]))
    model = _model(obs)
    assert cp.continuation_ev(model) > 0.0           # there IS a continuation to have been credited
    node = cp._Node(model=model, leaf=0.25)
    cand = cp._gap_or_reveal_candidate(
        node, _ranked(0, {"type": _PLAY, "index": 0}, delta=0.5, refused=True, gap="unmodelled"))
    assert cand.terminal_ev == 0.0
    assert cand.leaf == 0.25 and cand.score == 0.25
    assert cand.coverage_gap == "unmodelled"


@pytest.mark.req("REQ-COMPOSER-0004")
def test_NO_candidate_can_carry_BOTH_terminal_ev_and_the_continuation():
    """`attack_ev` has two call sites — `terminal_ev` for a line that ENDED, `continuation_ev` for one
    CUT — and `test_state_value.py`'s sole-consumer invariant holds only because they are exclusive."""
    obs = _obs(_player(active=_body(MEGA_LUC, energy=[FIGHTING, FIGHTING]), hand=[ITEM]))
    model = _model(obs)
    node = cp._Node(model=model, leaf=0.25)

    # Built through the SHIPPED constructors, so these are the branches `_expand` actually calls.
    attack = {"type": _ATTACK, "attackId": MEGA_BRAVE}
    ev, _detail, _gap = cp.terminal_ev(model, attack)
    ended = cp._terminal_candidate(
        node, cp._Ranked(index=0, option=attack, key=(0, 0, 0), delta=0.0, after=None,
                         fate="modelled", footprint=None, terminal=True, ev=ev))
    cut = cp._gap_or_reveal_candidate(node, _ranked(1, {"type": _PLAY, "index": 0}, delta=0.5))

    assert ended.terminal is not None and cut.terminal is None
    assert ended.terminal_ev == ev and ev > 0.0
    assert cut.terminal_ev == cp.continuation_ev(model)
    # The continuation is the MAX over the board's attacks, so it meets or exceeds any single one —
    # which is why carrying both on one candidate would price one prize twice.
    assert cut.terminal_ev >= ended.terminal_ev


@pytest.mark.req("REQ-COMPOSER-0004")
def test_the_refusal_exclusion_is_INERT_which_is_why_the_narrow_spelling_was_taken():
    """ADR-0129 records the wider arm as equivalent: `selection_key` leads with ``bool(coverage_gap)``
    and sorts every gap candidate behind every scored one whatever its score."""
    obs, _options = _menu_obs()
    model = _model(obs)
    clean = cp.Candidate(leaf=0.0, score=0.0)
    gapped_high = cp.Candidate(leaf=99.0, score=99.0, coverage_gap="unmodelled")
    assert cp.selection_key(model, clean) < cp.selection_key(model, gapped_high)


@pytest.mark.req("REQ-COMPOSER-0004")
def test_STOP_HERE_is_untouched_so_commit_nothing_can_never_out_score_a_real_line():
    """ADR-0129's soundness half: `attack_ev_legs` answers from the BOARD, so it prices an attack the
    engine never offered — credit the root stop-here with that and *"commit nothing"* wins outright."""
    obs = _obs(_player(active=_body(MEGA_LUC, energy=[FIGHTING, FIGHTING])))
    model = _model(obs)
    assert cp.continuation_ev(model) > 0.0           # there IS something it could have inherited
    root = cp._Node(model=model, leaf=0.25)
    cand = cp._stop_here(None, root)
    assert cand.terminal_ev == 0.0
    assert cand.score == 0.25 == cand.leaf
    assert cand.first_index is None


# ── the composer end to end ──────────────────────────────────────────────────────────────────────


def _menu_obs():
    """Issue #263's worked commutative triple — Energy attach, Tool equip, evolution — plus end-turn."""
    me = _player(active=_body(RIOLU, energy=[FIGHTING]),
                 bench=[_body(MUNKIDORI, serial=2)], hand=[E_F, TOOL, MEGA_LUC])
    options = [
        {"type": _ATTACH, "area": HAND, "index": 0, "inPlayArea": BENCH, "inPlayIndex": 0},
        {"type": _ATTACH, "area": HAND, "index": 1, "inPlayArea": BENCH, "inPlayIndex": 0},
        {"type": _EVOLVE, "area": HAND, "index": 2, "inPlayArea": ACTIVE, "inPlayIndex": 0},
        {"type": _END},
    ]
    return _obs(me, options=options), options


@pytest.mark.req("REQ-COMPOSER-0005")
def test_the_worked_triple_forms_ONE_commutative_block():
    """Reachable only since the element-granularity ruling (ADR-0098 Amendment D). Its required
    REJECTION is asserted one test down, so the licence is shown narrow rather than permissive."""
    obs, options = _menu_obs()
    blocks = cp.commutative_blocks(_model(obs), [cp.stamp_origin(_model(obs), o) for o in options])
    assert (0, 1, 2) in blocks


@pytest.mark.req("REQ-COMPOSER-0005")
def test_two_basics_contending_for_the_last_bench_slot_do_NOT_commute():
    """`bench_occupancy` stays whole-zone, so the two deploys collide. **The positive control for the
    test above** — a licence that accepted everything would pass that one vacuously."""
    me = _player(active=_body(RIOLU), bench=[_body(MUNKIDORI, serial=i) for i in range(2, 6)],
                 hand=[RIOLU, RIOLU])
    obs = _obs(me)
    model = _model(obs)
    options = [cp.stamp_origin(model, {"type": _PLAY, "index": i}) for i in (0, 1)]
    assert cp.commutative_blocks(model, options) == ()


@pytest.mark.req("REQ-COMPOSER-0005")
def test_compose_returns_a_chosen_line_a_margin_and_a_value_for_every_menu_option():
    obs, options = _menu_obs()
    model = _model(obs)
    result = cp.compose(model, options)
    assert result.chosen is not None
    assert len(result.fanned) == len(options)
    assert result.margin.k == cp.BEAM_WIDTH
    assert result.stats["leaf_evals"] > 0
    assert result.chosen.score == pytest.approx(result.chosen.leaf + result.chosen.terminal_ev)


@pytest.mark.req("REQ-COMPOSER-0005")
def test_compose_is_BIT_IDENTICAL_across_repeated_runs():
    """Issue #262's purity requirement: no dict/set iteration decides an order, and every tie
    resolves through `selection_key`."""
    obs, options = _menu_obs()
    a = cp.compose(_model(obs), options)
    b = cp.compose(_model(obs), options)
    assert [c.score for c in a.candidates] == [c.score for c in b.candidates]
    assert a.chosen.first_index == b.chosen.first_index
    assert a.margin.working() == b.margin.working()


@pytest.mark.req("REQ-COMPOSER-0005")
def test_the_composer_reaches_the_FULL_subset_lattice_of_a_block_when_the_beam_is_open():
    """Asserted on the SEQUENCES the composer actually built, not on `subset_lattice` in isolation."""
    obs, options = _menu_obs()
    result = cp.compose(_model(obs), options, k=99, depth=4)
    lines = {tuple(s.index for s in c.steps) for c in result.candidates}
    block = {line for line in lines if set(line) <= {0, 1, 2}}
    assert len(block) == 8
    assert all(list(line) == sorted(line, key=lambda i: line.index(i)) for line in block)
    assert all(len(set(line)) == len(line) for line in lines)


@pytest.mark.req("REQ-COMPOSER-0006")
def test_a_refused_option_becomes_a_flagged_one_action_candidate_and_reaches_the_telemetry():
    """A refusal is an unknown, not a zero — it must not price at 0.0 delta and vanish."""
    me = _player(active=_body(RIOLU), hand=[ITEM])
    obs = _obs(me, options=[{"type": _PLAY, "index": 0}, {"type": _END}])
    result = cp.compose(_model(obs), [{"type": _PLAY, "index": 0}, {"type": _END}])
    gapped = [c for c in result.candidates if c.coverage_gap]
    assert gapped and any(c.steps and c.steps[0].index == 0 for c in gapped)
    assert result.gaps and any("kind" in g for g in result.gaps)


@pytest.mark.req("REQ-COMPOSER-0006")
def test_a_refusal_is_unknown_at_the_one_ply_ordering_seam_not_a_priced_zero():
    """The refusal remains reportable and expandable, but it cannot tie a genuinely zero-valued action."""
    me = _player(active=_body(RIOLU), hand=[ITEM])
    result = cp.compose(_model(_obs(me)), [{"type": _PLAY, "index": 0}, {"type": _END}])
    assert result.fanned[0] is None
    assert 0 not in {index for index, _delta in result.order}
    assert 0 in result.always_expanded
    assert result.margin.ranked == len(result.order) == 1
    assert dict(result.order)[1] == pytest.approx(0.0)


@pytest.mark.req("REQ-COMPOSER-0006")
def test_a_coverage_gap_candidate_never_out_ranks_a_scored_sequence_it_merely_tied():
    """`selection_key`'s first leg: a gap is an absence of evidence, so it sorts last in its band."""
    obs, _options = _menu_obs()
    model = _model(obs)
    clean = cp.Candidate(leaf=1.0, score=1.0)
    gapped = cp.Candidate(leaf=1.0, score=1.0, coverage_gap="unmodelled")
    assert cp.selection_key(model, clean) < cp.selection_key(model, gapped)


# ── the beam-quality package: three DISTINCT mechanisms ──────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0007")
def test_the_selection_key_NEVER_falls_through_to_generation_order():
    """ADR-0062:29's bug class: two candidates equal on score must still separate on a BOARD-derived
    leg, never on which one the enumerator happened to build first."""
    obs, options = _menu_obs()
    model = _model(obs)
    stamped = [cp.stamp_origin(model, o) for o in options]
    left = cp.Candidate(steps=(cp.Step(stamped[0], 0, 3, ao.MODELLED),), score=1.0)
    right = cp.Candidate(steps=(cp.Step(stamped[2], 2, 0, ao.MODELLED),), score=1.0)
    assert cp.selection_key(model, left) != cp.selection_key(model, right)


@pytest.mark.req("REQ-COMPOSER-0007")
def test_one_ULP_of_float_noise_never_decides_a_tie_the_worth_leg_should():
    """The float-noise floor on `selection_key`'s score leg (ADR-0128). The two literals below are
    measured scores one ULP apart, so this fails if the rounding is removed."""
    obs, options = _menu_obs()
    model = _model(obs)
    stamped = [cp.stamp_origin(model, o) for o in options]
    worthy = cp.Candidate(steps=(cp.Step(stamped[0], 0, 3, ao.MODELLED),),
                          score=0.9052836100260415)
    noisy = cp.Candidate(score=0.9052836100260416)          # no steps -> no card -> worth 0.0
    assert noisy.score > worthy.score, "the fixture must reproduce the ULP, not assume it"
    assert cp.selection_key(model, worthy) < cp.selection_key(model, noisy), (
        "one ULP of float noise pre-empted the Worth leg — the tie-break fell through to arithmetic")


@pytest.mark.req("REQ-COMPOSER-0007")
def test_the_score_leg_still_separates_a_difference_the_leaf_can_actually_see():
    """A real 1-ply delta runs 1e-5 to 1e-3, and 12 places is six orders below the smallest of those,
    so a genuine separation still decides before Worth is consulted (ADR-0128)."""
    obs, options = _menu_obs()
    model = _model(obs)
    stamped = [cp.stamp_origin(model, o) for o in options]
    better = cp.Candidate(score=1.00001)                     # worth 0.0, but a REAL margin
    worthier = cp.Candidate(steps=(cp.Step(stamped[0], 0, 3, ao.MODELLED),), score=1.0)
    assert cp.selection_key(model, better) < cp.selection_key(model, worthier)


@pytest.mark.req("REQ-COMPOSER-0007")
def test_the_chosen_line_is_the_SAME_under_a_permuted_menu():
    """ADR-0103. Asserted on the CARD the composer commits to — the index is exactly what moved."""
    obs, options = _menu_obs()
    straight = cp.compose(_model(obs), options)
    order = [2, 0, 3, 1]
    permuted_options = [options[i] for i in order]
    permuted = cp.compose(_model(_obs(obs["current"]["players"][0], options=permuted_options)),
                          permuted_options)
    assert straight.chosen is not None and permuted.chosen is not None
    assert options[straight.chosen.first_index] == permuted_options[permuted.chosen.first_index]


@pytest.mark.req("REQ-COMPOSER-0007")
def test_the_epsilon_band_admits_a_near_tie_a_hard_top_k_would_drop():
    """Not LOSING a candidate during search, where `selection_key` chooses among those in hand."""
    run = cp._Run(k=2, epsilon=0.01, depth=1, search_api=None, deterministic=None,
                  clauses_cover=None, canon=[], reps=[], stamped=[])
    ranked = [cp._Ranked(index=i, option={}, key=(0, "", i), delta=d, after=object(),
                         fate=ao.MODELLED, footprint=ao.Footprint())
              for i, d in enumerate([1.0, 0.5, 0.495, 0.2])]
    admitted = [e.index for e in cp._admit(run, ranked)]
    assert admitted == [0, 1, 2]                  # 2 is inside the band; 3 is not
    run.epsilon = 0.0
    assert [e.index for e in cp._admit(run, ranked)] == [0, 1]


@pytest.mark.req("REQ-COMPOSER-0007")
def test_the_margin_telemetry_reports_rank_k_and_the_distance_to_the_cutoff():
    """*"Comfortably in"* vs *"survived on the band"* — the second is the beam-width sizing signal."""
    obs, options = _menu_obs()
    result = cp.compose(_model(obs), options, k=2)
    working = result.margin.working()
    assert set(working) == {"rank", "k", "ranked", "in_beam", "admitted", "always_expand",
                            "chosen_delta", "kth_delta", "margin_to_kth", "immediate_rank",
                            "immediate_delta", "admission_rank", "admission_score",
                            "kth_admission_score", "admission_margin", "admission_reason",
                            "stop_score", "continuation_estimate", "continuation_gain",
                            "continuation_action", "continuation_kind", "changed_admission"}
    assert working["k"] == 2 and working["rank"] is not None


@pytest.mark.req("REQ-COMPOSER-0007")
def test_the_margin_separates_EARNED_a_slot_from_ADMITTED_unconditionally():
    """A terminal or refused option is admitted whatever its rank (`must_expand`) and carries delta
    0.0 because it was never applied — `in_beam` would state a tie at zero as a leaf preference."""
    obs, options = _menu_obs()
    result = cp.compose(_model(obs), options, k=1)
    end_turn = len(options) - 1
    margin = result.margin_for(end_turn)
    assert margin.always_expand is True and margin.admitted is True
    assert margin.in_beam is False               # admitted, but it never EARNED a scored slot
    scored = result.margin_for(result.order[0][0])
    assert scored.in_beam is True and scored.always_expand is False


@pytest.mark.req("REQ-COMPOSER-0007")
def test_terminal_and_refused_options_are_admitted_unconditionally():
    """Dropping either makes an unpriceable option indistinguishable from a worthless one."""
    run = cp._Run(k=1, epsilon=0.0, depth=1, search_api=None, deterministic=None,
                  clauses_cover=None, canon=[], reps=[], stamped=[])
    ranked = [
        cp._Ranked(index=0, option={}, key=(0, "", 0), delta=5.0, after=object(),
                   fate=ao.MODELLED, footprint=ao.Footprint()),
        cp._Ranked(index=1, option={}, key=(0, "", 1), delta=-9.0, after=None, fate=ao.MODELLED,
                   footprint=ao.Footprint(), terminal=True),
        cp._Ranked(index=2, option={}, key=(0, "", 2), delta=0.0, after=None, fate=ao.REFUSED,
                   footprint=ao.Footprint(), refused=True, gap="unmodelled"),
        cp._Ranked(index=3, option={}, key=(0, "", 3), delta=4.9, after=object(),
                   fate=ao.MODELLED, footprint=ao.Footprint()),
    ]
    admitted = sorted(e.index for e in cp._admit(run, ranked))
    assert admitted == [0, 1, 2]                  # 3 is a scored option beyond k with no band


# ── the canonical in-block order ─────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0008")
def test_the_canonical_order_is_the_information_before_commitment_tier_order():
    """ADR-0095 decision 1's bands, over board facts rather than a scored `OptionTrace`: inside a
    commutative block no function of the end state separates any ordering."""
    obs, options = _menu_obs()
    model = _model(obs)
    assert cp.canonical_tier(model, options[2]) == cp.TIER_INFORMATIVE   # evolve
    assert cp.canonical_tier(model, options[0]) == cp.TIER_COMMITMENT    # Energy attach
    assert cp.canonical_tier(model, options[1]) == cp.TIER_COMMITMENT    # a Tool IS an `_ATTACH`
    assert cp.canonical_tier(model, options[3]) == cp.TIER_ENDER         # end turn
    assert cp.canonical_tier(model, {"type": _RETREAT}) == cp.TIER_ENDER


@pytest.mark.req("REQ-COMPOSER-0008")
def test_the_composers_tiers_ARE_the_pilots_tiers():
    """The tier NUMBERS live in `pilot._TIER_*` (ADR-0095 decision 1); the composer re-states them
    because its input differs, and a re-stated constant nobody checks renumbers half-applied."""
    from common import pilot

    assert (cp.TIER_INFORMATIVE, cp.TIER_COMMIT_FREE, cp.TIER_SUPPORTER, cp.TIER_COMMITMENT,
            cp.TIER_SHUFFLE, cp.TIER_ENDER) == (
        pilot._TIER_INFORMATIVE, pilot._TIER_COMMIT_FREE, pilot._TIER_SUPPORTER,
        pilot._TIER_COMMITMENT, pilot._TIER_SHUFFLE, pilot._TIER_ENDER)


@pytest.mark.req("REQ-COMPOSER-0008")
def test_a_revealing_play_takes_the_informative_tier_and_joins_no_block():
    """A revealer changes the OPTION SET, so `footprints_commute` vetoes it whatever its read/write
    sets say — while the tier stays TOTAL, since a None would fall through to menu position."""
    clauses = {ITEM: [{"kind": "fetch", "target": "pokemon"}]}
    me = _player(active=_body(RIOLU), hand=[ITEM, E_F])
    obs = _obs(me)
    model = _model(obs, clauses)
    reveal = {"type": _PLAY, "index": 0}
    assert ao.option_footprint(model, reveal).reveals_information is True
    assert cp.canonical_tier(model, reveal) == cp.TIER_INFORMATIVE
    attach = {"type": _ATTACH, "area": HAND, "index": 1, "inPlayArea": ACTIVE, "inPlayIndex": 0}
    options = [cp.stamp_origin(model, o) for o in (reveal, attach)]
    assert cp.commutative_blocks(model, options) == ()


# ── does a reveal RIDE this option? (the routing question, not the footprint's) ──────────────────
# Both rows verified at `data/EN_Card_Data.csv` + `src/common/card_effects.json`.
DRAKLOAK, TELEPATH = 120, 19
JUDGE = 1213
_RIDE_STATS = {
    **_STATS,
    DRAKLOAK: CardStat(DRAKLOAK, name="Drakloak", hp=90, energyType=DRAGON, evolvesFrom="Dreepy",
                       hasAbility=True),
    TELEPATH: CardStat(TELEPATH, name="Telepath Psychic Energy", cardType=6, energyType=PSYCHIC),
}
_RIDE_CLAUSES = {
    DRAKLOAK: [{"kind": "draw", "amount": 1, "window": 2,
                "allowance": "body", "rider": "other_to_bottom"}],
    TELEPATH: [{"kind": "energy_provide", "amount": 1, "type": "psychic"},
               {"kind": "fetch", "target": "basic_pokemon", "zone": "deck", "amount": 2,
                "energy_type": 5, "target_type": 5, "dest": "bench", "trigger": "on_attach"}],
}


def _ride_model(hand):
    obs = _obs(_player(active=_body(RIOLU), hand=list(hand)))
    combat = CombatMath(DictCardStatProvider(_RIDE_STATS, attacks=_ATTACKS),
                        functions=CardFunctions({}), transients=None,
                        effects=CardEffects(_RIDE_CLAUSES))
    return StateModel.build(obs, combat=combat, deck=[E_F] * 8)


@pytest.mark.req("REQ-COMPOSER-0011")
def test_an_ability_reveal_does_NOT_ride_the_evolve_that_puts_its_body_in_play():
    """Drakloak's clause carries a body allowance and NO ``trigger``: the Ability
    is its own `_ABILITY` option, so evolving into Drakloak reveals nothing (Issue #263)."""
    model = _ride_model([DRAKLOAK])
    evolve = {"type": _EVOLVE, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0}
    assert ao.option_footprint(model, evolve).reveals_information is True   # the CARD can reveal
    assert cp._reveal_rides(model, evolve) is False                         # this OPTION does not


@pytest.mark.req("REQ-COMPOSER-0011")
def test_an_ability_reveal_routes_its_body_not_the_same_index_in_hand():
    """The closed-form dispatcher checks kind first: hand[0]=Judge cannot hijack Drakloak's option."""
    drakloak = {**_body(RIOLU), "id": DRAKLOAK, "hp": 90, "maxHp": 90}
    obs = _obs(_player(active=drakloak, hand=[JUDGE]))
    stats = {**_RIDE_STATS, JUDGE: CardStat(JUDGE, name="Judge", cardType=3)}
    effects = {
        **_RIDE_CLAUSES,
        JUDGE: [{"kind": "draw", "amount": 4, "rider": "shuffle_both_hands"}],
        "_covers": {
            str(DRAKLOAK): {"covers": "full", "reason": "test verdict"},
            str(JUDGE): {"covers": "full", "reason": "test verdict"},
        },
    }
    combat = CombatMath(DictCardStatProvider(stats, attacks=_ATTACKS),
                        functions=CardFunctions({}), transients=None,
                        effects=CardEffects(effects))
    model = StateModel.build(obs, combat=combat, deck=[E_F] * 8)
    result = cp.compose(model, [{"type": _ABILITY, "area": ACTIVE, "index": 0}])
    assert result.fanned[0] is not None
    assert not any("revealing `_ABILITY` is an in-play source" in gap for gap in result.gaps)
    assert not any("source index" in gap or "occupied hand" in gap for gap in result.gaps)


@pytest.mark.req("REQ-COMPOSER-0011")
def test_ability_legality_reads_per_body_and_global_usage_markers():
    fez = 140
    stats = {**_RIDE_STATS,
             fez: CardStat(fez, name="Fezandipiti ex", hp=210, ex=True, energyType=DARKNESS,
                           hasAbility=True)}
    clauses = {
        **_RIDE_CLAUSES,
        fez: [{"kind": "draw", "amount": 3, "condition": "pokemon_ko_last_turn",
               "allowance": "card"}],
    }
    drak = {**_body(RIOLU, serial=11), "id": DRAKLOAK, "hp": 90, "maxHp": 90}
    fez_a = {**_body(RIOLU, serial=21), "id": fez, "hp": 210, "maxHp": 210}
    fez_b = {**fez_a, "serial": 22}
    obs = _obs(_player(active=drak, bench=(fez_a, fez_b)),
               abilityUsedBodies=[11], abilityUsedCards=[fez])
    combat = CombatMath(DictCardStatProvider(stats, attacks=_ATTACKS),
                        functions=CardFunctions({}), transients=None, effects=CardEffects(clauses))
    model = StateModel.build(obs, combat=combat, deck=[E_F] * 8)
    assert cp._still_legal(model, {"type": _ABILITY, "area": ACTIVE, "index": 0}) is False
    assert cp._still_legal(model, {"type": _ABILITY, "area": BENCH, "index": 0}) is False
    assert cp._still_legal(model, {"type": _ABILITY, "area": BENCH, "index": 1}) is False


def test_ability_footprint_carries_the_whole_usage_allowance_zone():
    drakloak = {**_body(RIOLU), "id": DRAKLOAK, "hp": 90, "maxHp": 90}
    obs = _obs(_player(active=drakloak))
    combat = CombatMath(DictCardStatProvider(_RIDE_STATS, attacks=_ATTACKS),
                        functions=CardFunctions({}), transients=None,
                        effects=CardEffects(_RIDE_CLAUSES))
    model = StateModel.build(obs, combat=combat, deck=[E_F] * 8)
    fp = ao.option_footprint(model, {"type": _ABILITY, "area": ACTIVE, "index": 0},
                             clauses_cover=True)
    assert "allowance_ability_used" in fp.reads == fp.writes
    assert not [key for key in fp.write_elements if key[0] == "allowance_ability_used"]


@pytest.mark.req("REQ-COMPOSER-0011")
def test_an_on_attach_reveal_DOES_ride_the_attach_and_must_refuse():
    """**The positive control for the test above.** `board_delta._attach` never consults clauses, so
    letting this through would model the attach and silently drop a two-Pokémon Bench fill."""
    model = _ride_model([TELEPATH])
    attach = {"type": _ATTACH, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0}
    assert cp._reveal_rides(model, attach) is True
    result = cp.compose(model, [attach, {"type": _END}])
    assert any("RIDES this option" in gap for gap in result.gaps)


@pytest.mark.req("REQ-COMPOSER-0011")
def test_the_trigger_map_covers_the_whole_declared_vocabulary():
    """An unknown `trigger` falls through to *"does not ride"*, the under-report direction — so the
    map is asserted against the registry, not a hand-copied list."""
    from common import snapshot_coverage as sc

    assert set(cp._TRIGGER_KIND) == set(sc.CLAUSE_SELECTORS["trigger"])


# ── the budget caps ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0009")
def test_the_budget_caps_are_WHITELISTED_and_typed_authored_scaffold():
    """ADR-0099: an untyped entry is rejected, and an `authored-scaffold` one must reconcile."""
    rule = sound_rules.BY_ID["composer-budget-caps"]
    assert rule.type == sound_rules.AUTHORED_SCAFFOLD
    assert rule.reconciliation.strip()
    assert sound_rules.validate() == []


@pytest.mark.req("REQ-COMPOSER-0009")
def test_epsilon_is_the_measured_decider_floor_not_an_authored_number():
    """`EPSILON` is re-spelled because `tools/` must never be a `src/` dependency."""
    from train.family_diag import DECIDER_FLOOR
    assert cp.EPSILON == DECIDER_FLOOR


@pytest.mark.req("REQ-COMPOSER-0009")
def test_the_expectation_branch_cap_is_NOT_re_declared_here():
    """One store per ADR-0087: a second copy would drift while both stayed internally consistent."""
    import re
    from pathlib import Path

    src = Path(cp.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^BRANCH_CAP\s*=", src, flags=re.M)


@pytest.mark.req("REQ-COMPOSER-0009")
def test_depth_truncation_is_REPORTED_never_silent():
    """No silent caps: an enumeration that reads as complete makes an under-explored line look sure."""
    obs, options = _menu_obs()
    result = cp.compose(_model(obs), options, k=99, depth=1)
    assert result.stats["depth_truncated"] > 0


# ── the arming (was: the darkness) ─────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0010")
def test_the_composer_has_EXACTLY_ONE_production_caller():
    """The caller set is DECLARED, so a second entry point cannot appear silently: two routes means
    two sets of seams, the divergence `test_composer_seams_are_wired.py` exists for (Issue #386)."""
    import re
    from pathlib import Path

    src = Path(cp.__file__).resolve().parents[1]

    def importers(module: str) -> list:
        pattern = re.compile(rf"^\s*(?:from\s+[\w.]*\b{module}\b\s+import|"
                             rf"from\s+[\w.]+\s+import\s+.*\b{module}\b|"
                             rf"import\s+[\w.]*\b{module}\b)", flags=re.M)
        return sorted(p.name for p in src.rglob("*.py")
                      if p.name != f"{module}.py" and "cg" not in p.parts[-2:-1]
                      and pattern.search(p.read_text(encoding="utf-8")))

    assert importers("state_value"), "the sweep found no `state_value` importer — instrument broken"
    assert importers("apply_option"), "the sweep found no `apply_option` importer — instrument broken"
    assert importers("composer") == ["planner.py"], (
        f"the composer's production caller set has changed: {importers('composer')}. It is armed at "
        "ONE seam — `planner._composer_line`, which is also the only place the per-option seams "
        "(`shed`, `search_api`, the determinism proof) are supplied. A second caller reaching it "
        "without them prices a different composer under the same name")


@pytest.mark.req("REQ-COMPOSER-0010")
def test_the_composer_never_mutates_the_model_it_was_handed():
    """`apply_option`'s contract, and the memo-staleness reason behind it: `state_value` caches its
    per-family dict on the model and nothing invalidates that key."""
    obs, options = _menu_obs()
    model = _model(obs)
    before = state_value(model)
    cp.compose(model, options)
    assert state_value(model) == before
    assert model.source_obs == obs


@pytest.mark.req("REQ-COMPOSER-0009")
def test_a_costed_search_needs_the_shed_seam_and_REFUSES_without_it():
    """The third caller-supplied seam, beside `deterministic` and `clauses_cover`. Left unset the
    option is REFUSED — pricing the cost unpaid would over-value every Ultra Ball by two cards."""
    ULTRA = ULTRA_BALL
    clauses = {ULTRA: [{"kind": "fetch", "target": "pokemon", "zone": "deck",
                        "cost": "discard_2", "cost_required": True}]}
    deck = [RIOLU] * 3 + [MEGA_LUC] + [E_F] * 6 + [ULTRA]
    obs = _obs(_player(active=_body(RIOLU, energy=[FIGHTING]), hand=[ULTRA, RIOLU, RIOLU],
                       deck_count=len(deck)))
    model = StateModel.build(obs, combat=_combat(clauses, extra_stats={ULTRA: _STATS_ULTRA}),
                             deck=deck)
    play = {"type": _PLAY, "area": HAND, "index": 0}

    without = cp.compose(model, [play, {"type": _END}])
    assert any("shed" in gap for gap in without.gaps), without.gaps

    # The oracle here is deliberately dumb — the real one is `Pilot.cost_shed_indices`; this node's
    # contract is only that it APPLIES the set it is handed.
    def shed(_model, option, picks):
        return [i for i in (1, 2, 3, 4) if i != option.get("index")][:picks]

    with_seam = cp.compose(model, [play, {"type": _END}], shed=shed)
    assert not any("shed" in gap for gap in with_seam.gaps), with_seam.gaps
    assert with_seam.bounds, "the costed search should now reach the expectation-node telemetry"


# ── exact frontier identity and continuation-aware admission (Issue #496) ───────────────────────


def _rename_serials(value, offset):
    if isinstance(value, dict):
        return {k: (_rename_serials(v, offset) if k != "serial" else v + offset)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_rename_serials(v, offset) for v in value]
    return value


def _run(*, k=1):
    return cp._Run(k=k, epsilon=0.0, depth=4, search_api=None, deterministic=None,
                   clauses_cover=None, canon=[], reps=[], stamped=[])


@pytest.mark.req("REQ-COMPOSER-0011")
def test_semantic_state_key_alpha_renames_visible_serials_but_keeps_relationships():
    obs = _obs(_player(active=_body(RIOLU, serial=11),
                       bench=[_body(MUNKIDORI, serial=12)], hand=[E_F]))
    obs["current"]["firstBodySerial"] = 11
    obs["current"]["secondBodySerial"] = 11
    renamed = _rename_serials(copy.deepcopy(obs), 100)
    renamed["current"]["firstBodySerial"] = 111
    renamed["current"]["secondBodySerial"] = 111
    assert cp.semantic_state_key(_model(obs)) == cp.semantic_state_key(_model(renamed))

    split = copy.deepcopy(obs)
    split["current"]["secondBodySerial"] = 12
    assert cp.semantic_state_key(_model(obs)) != cp.semantic_state_key(_model(split))


@pytest.mark.req("REQ-COMPOSER-0011")
def test_semantic_state_key_keeps_damage_order_allowances_and_unknown_current_keys():
    obs = _obs(_player(active=_body(RIOLU, serial=11), hand=[E_F, TOOL]))
    baseline = cp.semantic_state_key(_model(obs))
    variants = []
    damaged = copy.deepcopy(obs)
    damaged["current"]["players"][0]["active"][0]["hp"] -= 10
    variants.append(damaged)
    reordered = copy.deepcopy(obs)
    reordered["current"]["players"][0]["hand"].reverse()
    variants.append(reordered)
    spent = copy.deepcopy(obs)
    spent["current"]["energyAttached"] = True
    variants.append(spent)
    unknown = copy.deepcopy(obs)
    unknown["current"]["futureEngineFact"] = {"x": 1}
    variants.append(unknown)
    assert all(cp.semantic_state_key(_model(v)) != baseline for v in variants)


@pytest.mark.req("REQ-COMPOSER-0011")
def test_unresolved_identity_fails_closed_and_frontier_includes_remaining_actions():
    obs = _obs(_player(active=_body(RIOLU, serial=11), hand=[E_F]))
    unresolved = copy.deepcopy(obs)
    unresolved["current"]["targetBodySerial"] = 999
    assert cp.semantic_state_key(_model(unresolved)) is None

    model = _model(obs)
    options = ({"type": _ATTACH, "area": HAND, "index": 0,
                "inPlayArea": ACTIVE, "inPlayIndex": 0}, {"type": _END})
    stamped = tuple((i, cp.stamp_origin(model, option)) for i, option in enumerate(options))
    available = cp._Node(model=model, root_options=stamped)
    consumed = cp._Node(model=model, used=frozenset({0}), root_options=stamped)
    assert cp.frontier_key(available, remaining_depth=2) != cp.frontier_key(consumed, remaining_depth=2)


@pytest.mark.req("REQ-COMPOSER-0011")
def test_semantic_state_key_is_identical_across_python_hash_seeds():
    script = """
from types import SimpleNamespace
from common.state_model import CarriedState, semantic_state_key
obs={'current': {'yourIndex': 0, 'players': [
    {'active': [{'id': 1, 'serial': 91}], 'bench': [], 'hand': [], 'discard': []},
    {'active': [{'id': 2, 'serial': 37}], 'bench': [], 'hand': [], 'discard': []}],
    'abilityUsedBodies': [91], 'unknown': {'b': 2, 'a': 1}}}
side=SimpleNamespace(_turn_boosts=())
model=SimpleNamespace(source_obs=obs, carried=CarriedState(), mine=side, theirs=side,
                      _transient_generation=None)
print(repr(semantic_state_key(model)))
"""
    outputs = []
    for seed in ("1", "7", "123"):
        env = {**os.environ, "PYTHONHASHSEED": seed,
               "PYTHONPATH": str(__import__("pathlib").Path(cp.__file__).resolve().parents[1])}
        outputs.append(subprocess.check_output([sys.executable, "-c", script], env=env, text=True))
    assert len(set(outputs)) == 1


@pytest.mark.req("REQ-COMPOSER-0012")
def test_exact_dedup_happens_before_width_and_resets_conflicting_block_history():
    obs = _obs(_player(active=_body(RIOLU, serial=11)))
    same_a = cp._Node(model=_model(obs), leaf=1.0, origins=(("a",),),
                      origin_indices=((0,),), block=((0,),))
    same_b = cp._Node(model=_model(copy.deepcopy(obs)), leaf=1.0, origins=(("b",),),
                      origin_indices=((1,),), block=((1,),))
    distinct_obs = copy.deepcopy(obs)
    distinct_obs["current"]["players"][0]["active"][0]["hp"] -= 10
    distinct = cp._Node(model=_model(distinct_obs), leaf=0.9, origins=(("c",),),
                        origin_indices=((2,),))
    unique, row = cp._deduplicate_nodes(_run(), [same_a, same_b, distinct], remaining_depth=1)
    assert row["generated"] == 3 and row["unique"] == 2 and row["merged"] == 1
    merged = next(node for node in unique if len(node.origins) == 2)
    assert merged.origins == (("a",), ("b",))
    assert merged.block == () and merged.block_prints == ()


@pytest.mark.req("REQ-COMPOSER-0012")
def test_full_frontier_tuple_not_hash_collision_decides_equality(monkeypatch):
    monkeypatch.setattr(cp.FrontierKey, "__hash__", lambda _self: 1)
    first_obs = _obs(_player(active=_body(RIOLU, damage=0)))
    second_obs = _obs(_player(active=_body(RIOLU, damage=10)))
    nodes = [cp._Node(model=_model(first_obs), origins=(("a",),)),
             cp._Node(model=_model(second_obs), origins=(("b",),))]
    unique, row = cp._deduplicate_nodes(_run(), nodes, remaining_depth=1)
    assert len(unique) == 2 and row["merged"] == 0


@pytest.mark.req("REQ-COMPOSER-0013")
def test_one_action_estimate_can_admit_a_low_immediate_high_second_value_node(monkeypatch):
    model = _model(_obs(_player(active=_body(RIOLU))))
    immediate = cp._Node(model=model, leaf=1.0, origins=(("immediate",),),
                         origin_indices=((0,),))
    enabler = cp._Node(model=model, leaf=0.9, origins=(("enabler",),),
                       origin_indices=((1,),))
    terminal = cp._Ranked(index=9, option={"type": _END}, key=(0, "", 9), delta=0.4,
                          after=None, fate=ao.TERMINAL, footprint=ao.Footprint(), terminal=True,
                          ev=0.4, semantic_key="payoff")

    monkeypatch.setattr(cp, "_rank", lambda _state, node, **_kw: [terminal] if node is enabler else [])
    without = cp._retain_nodes(_run(), [immediate, enabler], remaining_depth=2,
                               continuation=False, exhaustive=False)
    with_estimate = cp._retain_nodes(_run(), [immediate, enabler], remaining_depth=2,
                                     continuation=True, exhaustive=False)
    assert without == [immediate]
    assert with_estimate == [enabler]


@pytest.mark.req("REQ-COMPOSER-0013")
def test_admission_rank_cache_reuses_the_transition_when_the_child_expands():
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F]))
    model = _model(obs)
    options = [{"type": _ATTACH, "area": HAND, "index": 0,
                "inPlayArea": ACTIVE, "inPlayIndex": 0}, {"type": _END}]
    stamped = [cp.stamp_origin(model, option) for option in options]
    state = cp._Run(k=4, epsilon=0.005, depth=4, search_api=None, deterministic=None,
                    clauses_cover=None, canon=cp.canonical_keys(options, obs),
                    reps=[0, 1], stamped=stamped)
    node = cp._Node(model=model, leaf=state_value(model),
                    root_options=tuple(enumerate(stamped)))
    first = cp._rank(state, node, remaining_depth=3)
    evaluations = state.transition_evals
    second = cp._rank(state, node, remaining_depth=3)
    assert second is first
    assert state.transition_evals == evaluations > 0


@pytest.mark.req("REQ-COMPOSER-0014")
def test_reference_mode_shares_the_production_core_and_reports_caps_unknown():
    obs, options = _menu_obs()
    model = _model(obs)
    wide = cp.compose(model, options, k=99, depth=4)
    reference = cp.compose_reference(
        model, options, budget=cp.ReferenceBudget(max_depth=4,
                                                  max_transition_evals=10000,
                                                  max_unique_nodes=10000))
    assert reference.composer.chosen.semantic_path == wide.chosen.semantic_path
    capped = cp.compose_reference(
        model, options, budget=cp.ReferenceBudget(max_depth=4,
                                                  max_transition_evals=1,
                                                  max_unique_nodes=10000))
    assert capped.status == cp.REFERENCE_UNKNOWN
    assert capped.cap_reason == "max_transition_evals"
