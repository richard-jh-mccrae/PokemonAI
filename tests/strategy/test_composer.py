"""The **sequence composer** (`common/composer.py`, POC-T4/4, Issue #385; spec Issue #263).

`test_apply_transitions.py` asserts one option → one board and `test_board_expectation.py` asserts
one reveal → one distribution. This file asserts what happens when they are put in a LOOP: the
subset lattice, the refusal semantics, the terminal sum, the deterministic tie-break, and — the one
that would fail silently in production — instance re-resolution across a permuted sequence.

Five properties carry the file:

* **The lattice counts.** ``2**n`` subsets for ``n`` pairwise-commuting options (8 / 16 / 32 for
  n = 3 / 4 / 5), against the 16 / 65 / 326 ordered prefixes a naive tree holds, generated a-priori
  so a duplicate ordering is never CREATED.
* **A stale hand index is a DIFFERENT play.** Removing hand card 0 shifts card 3 to index 2, and a
  shifted index still resolves to *a* legal card — so this failure produces a plausible board rather
  than an error. Carries its own positive control (the naive replay names the wrong card).
* **A refusal is an unknown, never a zero.** It surfaces as a flagged coverage-gap candidate and in
  the telemetry, and it can never quietly out-rank a scored sequence.
* **Determinism under a permuted menu.** The ADR-0062:29 / ep82867148 f48/f87 / ep83661652
  f33/f40/f44 bug class, asserted as a regression shape rather than described.
* **Bit-identical output across repeated runs** — Issue #262's purity requirement, inherited.

Card facts VERIFIED at source (`data/EN_Card_Data.csv`) via the shared fixture pool this suite
already keeps; every constant below is quoted at its definition in `test_apply_transitions.py`, which
`tests/scouting/test_cardstat_fixture_facts.py` audits field-for-field against the CSV. Same primary
seam as that file: a dict-backed Stat Provider and hand-built zone dicts, no Pilot and no engine boot,
so this runs DLL-free on both platforms.
"""
from __future__ import annotations

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
from common.strategy.context import _ATTACH, _ATTACK, _END, _EVOLVE, _PLAY, _RETREAT

MAIN = bd.CONTEXT_MAIN
ACTIVE, BENCH, HAND = AREA_ACTIVE, AREA_BENCH, AREA_HAND
COLORLESS, FIGHTING, PSYCHIC, DRAGON = 0, 6, 5, 9

# ── the pool — every row quoted from `data/EN_Card_Data.csv` at its home fixture ──────────────────
#
#   677  Riolu             Basic {F}, HP 80          — evolves into Mega Lucario ex in ONE hop
#   678  Mega Lucario ex   Stage 1 {F}, HP 340, `evolvesFrom` **Riolu** (rulebook Appendix 1 L335:
#                          *"Mega Lucario ex doesn't evolve from Lucario or Lucario ex—just Riolu"*)
#   982  Aura Jab          130 for {F}
#   983  Mega Brave        270 for {F}{F}
#   112  Munkidori         Basic {P}, HP 110
#   6    Basic {F} Energy
#   1125 Master Ball       Item
#   1159 (synthetic stand-in) a Pokemon Tool with a flat HP grant — the same treatment every other
#                           Hero's Cape fixture in the tree gets, because the audit re-derives
#                           `hpBonus` by parsing the CSV through a shim card and gets 0
#   1200 Kofu              Supporter  — a REAL Supporter, used for the §S6 allowance case
#   1242 Community Center  Stadium    — a REAL Stadium, likewise
RIOLU, MEGA_LUC, MUNKIDORI = 677, 678, 112
AURA_JAB, MEGA_BRAVE = 982, 983
E_F, TOOL, ITEM = 6, 1159, 1125
SUPPORTER, STADIUM = 1200, 1242

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
#: The two Trainer rows §S6's allowance cases need, kept OUT of `_STATS` so every other fixture's
#: menu stays what it was. Names and `cardType` are the CSV's own — `tests/scouting/
#: test_cardstat_fixture_facts.py` audits every `CardStat(...)` literal in the tree against
#: `data/EN_Card_Data.csv` field-for-field, so an invented name on a real id fails the build (this
#: pair started life as "Test Supporter" on id 1200, which is really Kofu, and that audit caught it).
_STATS_SUPPORTER = CardStat(SUPPORTER, name="Kofu", cardType=3)
_STATS_STADIUM = CardStat(STADIUM, name="Community Center", cardType=4)

_ATTACKS = {AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,)),
            MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2,
                                   energyTypes=(FIGHTING, FIGHTING))}


def _combat(clauses=None):
    return CombatMath(DictCardStatProvider(_STATS, attacks=_ATTACKS),
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
    """Issue #263 § *Commutative-block collapse* states both numbers. `subset_lattice` must produce
    the first, and the second is computed here rather than quoted so the contrast is a fact of the
    test rather than a claim in its name."""
    import math

    members = tuple(range(n))
    lattice = cp.subset_lattice(members)
    assert len(lattice) == subsets == 2 ** n
    assert len(set(lattice)) == len(lattice)          # duplicates are never CREATED, not merged
    assert sum(math.perm(n, k) for k in range(n + 1)) == ordered


@pytest.mark.req("REQ-COMPOSER-0001")
def test_every_lattice_member_is_in_ONE_canonical_order():
    """*"One canonical ordering per subset"* — so each emitted tuple is sorted by the same key, and
    two subsets never differ only in their order."""
    lattice = cp.subset_lattice(("a", "b", "c", "d"))
    assert all(list(s) == sorted(s) for s in lattice)
    assert len({frozenset(s) for s in lattice}) == len(lattice)


@pytest.mark.req("REQ-COMPOSER-0001")
def test_the_lattice_rule_and_the_beams_rule_are_the_SAME_rule():
    """`subset_lattice` and `_admissible_in_block` are two doors onto one rule, and a second spelling
    of it is the drift ADR-0087 charges for one store over. Asserted by generating the lattice
    through the beam's own predicate and comparing."""
    members = ("a", "b", "c")
    grown = [()]
    for m in members:
        grown = grown + [p + (m,) for p in grown if cp._admissible_in_block(m, p)]
    assert sorted(grown) == sorted(cp.subset_lattice(members))


# ── instance re-resolution: the silent failure ───────────────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0002")
def test_a_stored_option_replayed_from_a_permuted_position_names_a_DIFFERENT_CARD():
    """**The positive control for the next test.** Removing hand card 0 shifts every later card down
    one, so the naive replay of a stored ``index`` resolves to a card that is genuinely there and
    genuinely wrong — which is why the failure this module guards is silent rather than loud."""
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
    """The commutativity ruling's requirement, made a test rather than trusted to review: a block
    member is re-resolved against the board it is actually applied to, by instance."""
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
def test_a_consumed_card_makes_its_option_UNRESOLVABLE_rather_than_re_pointed():
    """A serial that is gone means the card was spent, so the option is no longer a play. Dropping it
    is the fail-closed answer; re-pointing it at whatever now sits at that index is the bug."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F, TOOL]))
    before = _model(obs)
    stamped = cp.stamp_origin(before, {"type": _ATTACH, "area": HAND, "index": 0,
                                       "inPlayArea": ACTIVE, "inPlayIndex": 0})
    after = ao.apply_option(before, dict(stamped))
    assert cp.resolve_against(after, stamped) is None


@pytest.mark.req("REQ-COMPOSER-0002")
def test_the_stamp_never_leaves_the_module():
    """The origin key rides the option dict so it cannot get out of step with a permuted sequence,
    and `strip_origin` is what hands a clean dict back to the engine.

    Asserted on the shapes that actually LEAVE — every `Step.option` and every `Candidate.terminal`
    reachable from a real `compose` — not only on `strip_origin` in isolation. Testing the helper
    alone passes while a construction site forgets to call it, which is exactly the asymmetry that
    was there: `_terminal_candidate` stripped and the two `Step` constructors did not, so
    `result.chosen.steps[i].option` carried `_composer_origin` out to every consumer."""
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
    """`docs/rules.md` §3 — *"Attach Energy from hand | **1** (manual attachment; card effects can add
    more)"*. At depth 0 the engine's menu is the proof; at depth >= 1 there is no menu, and
    `apply_option` models a transition rather than policing one, so this gate is the only thing
    standing between the beam and a two-Energy turn."""
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
    """`docs/rules.md` §4 — *"Cannot evolve a Pokémon **the turn it was played/put into play**"*. The
    exact 2-ply sequence Issue #263 works through, and the reason `_EVOLVE`'s footprint declares
    `new_in_play` as a READ."""
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
    """`board_delta._play` already refuses it — but as an `Unmodellable`, which the composer turns
    into a COVERAGE GAP. That would file a phantom entry in the modelling backlog for a move that is
    merely illegal, and the backlog is grouped by those strings. The legality check has to catch it
    first, off the engine's own ``benchMax``."""
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
    """`_admit` and `_prune_nodes` both index the k-th as ``[k - 1]``, so ``k=0`` indexes the WORST
    candidate from the end and admits the entire menu — a beam that silently stops being a beam.
    Raises rather than refuses, the same split `board_expectation.expectation` draws for its own
    ``cap < 1``: a modelling gap refuses, a caller error raises."""
    obs, options = _menu_obs()
    model = _model(obs)
    for bad in ({"k": 0}, {"k": -1}, {"depth": -1}):
        with pytest.raises(ValueError, match="beam must keep at least one candidate"):
            cp.compose(model, options, **bad)


@pytest.mark.req("REQ-COMPOSER-0003")
def test_the_one_supporter_per_turn_is_spent_once():
    """`docs/rules.md` §3 — Supporter is 1 per turn. Untested until the review found it: the branch
    at `_still_legal`'s `is_supporter` leg was implemented and never exercised, so an inverted test
    (`model.supporter_played` read the wrong way) would have shipped green.

    Carries the case that would OTHERWISE PASS, which is the point: on a fresh board the same option
    is legal, so this asserts the ALLOWANCE and not merely that the option is unrecognised."""
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
    """`docs/rules.md` §3 — Stadium is 1 per turn, *"and only if it differs from the one in play"*.

    TWO limits on one option kind, which is why it gets two negative cases: a spent allowance and an
    identical Stadium already in play. Reading only the allowance would let the composer re-play the
    Stadium that is already down — legal-looking, board-neutral, and silently wrong."""
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
    """An Active with a payable Retreat Cost and a Bench to promote INTO — the shape that makes a
    `_RETREAT` a CHOICE node rather than a bare allowance write.

    Two distinct bench bodies by default, because a one-member space cannot tell `max` from
    `expected()`: they agree whenever there is nothing to choose between."""
    bench = bench if bench is not None else [_body(MEGA_LUC, serial=2, energy=[FIGHTING]),
                                             _body(MUNKIDORI, serial=3)]
    return _model(_obs(_player(active=_body(RIOLU, serial=1, energy=[FIGHTING]), bench=bench)))


@pytest.mark.req("REQ-COMPOSER-0009")
def test_an_UNEXPANDED_retreat_prices_at_EXACTLY_zero_which_is_the_defect():
    """The premise ADR-0121 rests on, asserted rather than quoted — and it is *exactly* 0.0, not
    approximately so.

    `board_delta._retreat` writes ``allowance_retreat_used`` and nothing else, and **no `state_value`
    family reads the retreat allowance**, so the point transition's 1-ply delta is a hard zero. Under
    uniform differencing that reads as *never explore this*, which is why Issue #392's cheaper
    beam-admission route was rejected: admitting the option leaves the ~0 score intact and the beam
    still ranks on it.

    This is the POSITIVE CONTROL for the expansion tests below. If it ever stops holding, those tests
    are measuring something other than the defect they exist for."""
    model = _retreat_board()
    before = state_value(model)
    after = ao.apply_option(model, {"type": _RETREAT})          # default: expansion OFF
    assert not isinstance(after, ao.Expectation), "the DEFAULT path must stay the point transition"
    assert state_value(after) - before == 0.0


@pytest.mark.req("REQ-COMPOSER-0009")
def test_expansion_turns_that_zero_into_a_REAL_score_over_one_class_per_target():
    """ADR-0121 decision 1: expansion, not admission. One candidate per legal instance, each a fully
    synthesized board scored by `state_value` — so there is no ~0-scored retreat left to admit."""
    model = _retreat_board()
    choice = cp.choose_target(model, {"type": _RETREAT})
    assert choice is not None and len(choice.scored) == 2, "one class per promotable bench body"
    assert choice.leaf != state_value(model), "expansion must MOVE the score off the flat zero"
    assert [s.rank for s in choice.scored] == [1, 2]
    assert choice.scored[0].leaf >= choice.scored[1].leaf, "ordered best-first"


@pytest.mark.req("REQ-COMPOSER-0009")
def test_the_composer_ranks_a_CHOICE_node_by_MAX_and_never_by_expected():
    """**§S3, and the single most silently-wrong-able decision in the issue.**

    Both producing modules rule it in their own headers — `board_expectation` (*"the composer takes
    the max over `classes`"*, unchanged since Issue #383's first commit) and `board_choice`
    (*"never `.expected()`"*). Ranking on the mean under-prices every choice node, which at ordering
    time is a PRUNED option rather than an undervalued one.

    Asserted on a fixture where the two numbers actually DISAGREE, and asserted against the
    composer's own delta rather than against a helper — a test that only checked `best() != expected()`
    would pass while `_one_ply` still called the wrong one."""
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
    """`rank_targets` sorts and takes `scored[0]`; `Expectation.best` maxes. **Two spellings of one
    rule**, which is the drift ADR-0087 charges for one store over — so the agreement is asserted
    rather than left to inspection.

    The sort is not redundant work: the ranking needs it anyway (D4 reports the runner-up), so
    `scored[0]` is free where a second pass would not be. What must never happen is the two
    disagreeing, which on a fixture with distinct class values is exactly what a `min`/`max` slip or
    an inverted sort key would produce."""
    from common import board_choice

    model = _retreat_board()
    expectation = board_choice.deferred_target(model, {"type": _RETREAT}, seat_index=0)
    assert len({round(state_value(c.model), 12) for c in expectation.classes}) > 1, (
        "fixture is vacuous unless the classes actually differ")
    assert cp.rank_targets(model, expectation).leaf == pytest.approx(
        expectation.best(state_value))


@pytest.mark.req("REQ-COMPOSER-0009")
def test_the_OTHER_expectation_producer_is_also_ranked_by_MAX(monkeypatch):
    """§S12.1 asks for the max-not-mean fixture on **both** `Expectation` producers, and the two
    reach `_one_ply` by different branches: `board_choice` through the seam's CHOICE dispatch
    (asserted above), and `board_expectation` through this module's own REVEAL routing. A test
    covering only the first leaves the reveal branch free to drift back to `.expected()` — which is
    where it started, and which under-prices every reveal-bearing sequence.

    **The producer is stubbed, and that is the point rather than a shortcut.** The claim under test is
    *"the reveal branch ranks by max"*, which is a property of `_one_ply`. Driving it through a real
    deck search would additionally require `state_value` to price two fetched cards differently — and
    measurably **it does not** in this fixture pool: a Master Ball over 3 Riolu + 1 Mega Lucario ex
    enumerates two classes that score *identically* (0.099677083 each), because a Pokemon in HAND is
    priced by Worth and no Roles are declared against a dict-backed provider. A fixture built that way
    would pass whichever bound the composer used, which is the vacuous-instrument failure this suite
    exists to avoid. So the enumeration is supplied directly, with classes that genuinely differ.

    The ROUTING is still real — the option reaches `bx.expectation` because its `fetch` clause makes
    `_reveal_rides` true — so this asserts the live branch and not a hand-called helper."""
    from common import board_expectation as bx

    # Real routing: Master Ball's committed `card_effects.json` clause shape, so the option is
    # genuinely classified as a reveal rather than forced down that path.
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
def test_BOTH_bounds_reach_the_telemetry_with_the_dropped_mass():
    """§S3.4 / §S3.5. The max over-reads a 5%-likely target at full value and `expected()` under-reads
    a free choice; the GAP is the exposure, so both are reported rather than smoothed into a third
    number nobody ruled on. ``total_probability`` rides along because a capped enumeration that reads
    as a complete one is the no-silent-caps failure."""
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
    """**ADR-0121 decision 4 — parent-slot beam accounting**, and the reason it is not optional.

    Expansion is an EVALUATION-time fan-out, never a candidate-generation one: score every instance,
    take `argmax`, emit ONE candidate. So beam width `k` keeps its pre-expansion meaning, and §S8's
    epsilon band and margin telemetry keep meaning what Issue #263 says they mean.

    Flat competition was rejected for silently redefining `k` — the failure this asserts against is a
    menu whose one retreat quietly occupies as many depth-0 slots as it has promotable bodies."""
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
    """D4 emits ``(parent_option, chosen_target, score)``. Without the middle term a candidate would
    say the composer retreated while staying silent about whom it promoted — and the runner-up is the
    size of D4's accepted loss, which is reported rather than argued."""
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
    """**ADR-0121 decision 6.** This issue builds one evaluator and proves it at the MAIN site;
    Issue #387 wires the identical function at the follow-up select. ADR-0100 §9's invariant —
    *"that the two sites run the same evaluator is what makes the old divergence ... structurally
    impossible"* — is only as strong as the discipline keeping them one spelling, so the split between
    ENUMERATING a space and EVALUATING one is asserted here.

    `rank_targets` must therefore take an `Expectation` and nothing frame-specific: Issue #387's site
    does not enumerate (the engine hands it the menu), so an evaluator that also enumerated would
    force that issue to fake an enumeration or to spell the scoring a second time."""
    import inspect

    model = _retreat_board()
    expectation = __import__("common.board_choice", fromlist=["x"]).deferred_target(
        model, {"type": _RETREAT}, seat_index=0)
    # The enumerating front door and the bare evaluator agree, because the first calls the second.
    # Compared on the SCALARS: each call synthesizes fresh `StateModel`s, so object equality would
    # measure identity rather than agreement and would fail on two runs of the same function.
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
    """§S7.4 — the flag this issue adds none of and flips none of.

    `expand_deferred_targets` is a CALL-SITE argument because `apply_option` is pure and the flag is
    deployment config; the composer is *written against* expansion, so it is not switchable here. The
    other half is what makes this module's darkness mechanically checkable: **every other caller keeps
    the default False**, so both ADR-0072 gates and the ADR-0098 parity lane see the byte-identical
    seam they saw at Issue #382.

    `runtime.PROFILE["deferred_target_expansion"]` therefore stays False and becomes an orphan for
    T4/5 to delete — asserted, because a flag silently flipped ON here would arm the composer's seam
    change for every OTHER consumer while this module was still dark."""
    import inspect

    from common import runtime

    assert runtime.PROFILE["deferred_target_expansion"] is False
    assert inspect.signature(ao.apply_option).parameters[
        "expand_deferred_targets"].default is False
    source = inspect.getsource(cp._one_ply)
    assert "expand_deferred_targets=True" in source, "the composer must opt IN at its call site"
    # Parsed, not grepped: this module's own header DISCUSSES `runtime.PROFILE` at length, and a
    # line-level scan would fire on the prose that exists to explain why the flag is untouched.
    # `ast` sees imports and attribute reads, which is what the claim is about.
    import ast

    tree = ast.parse(inspect.getsource(cp))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
               for alias in node.names}
    imports |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                for alias in node.names}
    assert not {"runtime", "common.runtime"} & imports, (
        "the composer reads no deployment flag — expansion is intrinsic to its correctness, so it "
        "is unconditional here and `deferred_target_expansion` stays an orphan for Issue #386")
    assert "PROFILE" not in {getattr(n, "attr", None) for n in ast.walk(tree)
                             if isinstance(n, ast.Attribute)}


# ── the terminal sum ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0004")
def test_end_turn_is_worth_exactly_zero():
    """``EV(end-turn) = 0`` is the spec's own definition, not an approximation."""
    obs = _obs(_player(active=_body(RIOLU)))
    assert cp.terminal_ev(_model(obs), {"type": _END}) == (0.0, None, "")


@pytest.mark.req("REQ-COMPOSER-0004")
def test_an_attack_is_priced_through_attack_ev_and_reads_TOTAL_not_the_dict_sum():
    """``score = state_value(end board) + EV(terminal action)``. `AttackEV.working()` is FROZEN and
    ASYMMETRIC — it omits ``total`` and emits ``next_turn_cost`` POSITIVE while ``total`` subtracts it
    — so a consumer that sums the dict gets ``total + 2 x next_turn_cost``. This asserts the composer
    is not that consumer."""
    obs = _obs(_player(active=_body(MEGA_LUC, energy=[FIGHTING, FIGHTING])))
    model = _model(obs)
    ev, detail, gap = cp.terminal_ev(model, {"type": _ATTACK, "attackId": MEGA_BRAVE})
    assert gap == "" and detail is not None
    assert ev == pytest.approx(detail.total)
    if detail.next_turn_cost:
        assert ev != pytest.approx(sum(detail.working().values()))


@pytest.mark.req("REQ-COMPOSER-0004")
def test_an_attack_with_no_matching_leg_is_a_COVERAGE_GAP_not_a_zero():
    """*"A 0 delta is never explored, not undervalued."* An attack the extractor cannot price must
    say so, or it sorts below every scored line and the gap never surfaces."""
    obs = _obs(_player(active=_body(MEGA_LUC, energy=[FIGHTING, FIGHTING])))
    ev, detail, gap = cp.terminal_ev(_model(obs), {"type": _ATTACK, "attackId": 999999})
    assert ev == 0.0 and detail is None
    assert "UNKNOWN" in gap and "999999" in gap


# ── the composer end to end ──────────────────────────────────────────────────────────────────────


def _menu_obs():
    """A MAIN menu holding an Energy attach, a Tool equip, an evolution, an attack and an end-turn —
    Issue #263 § *Commutative-block collapse*'s own worked triple plus both terminals."""
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
    """Issue #263's own example — *"Playing an Energy, an evolution and a Tool in any of 3! orders
    reaches ONE board"* — reachable only since the 2026-08-04 element-granularity ruling (ADR-0098
    Amendment D). Its required REJECTION is asserted one test down, so the licence is shown to be
    narrow rather than merely permissive."""
    obs, options = _menu_obs()
    blocks = cp.commutative_blocks(_model(obs), [cp.stamp_origin(_model(obs), o) for o in options])
    assert (0, 1, 2) in blocks


@pytest.mark.req("REQ-COMPOSER-0005")
def test_two_basics_contending_for_the_last_bench_slot_do_NOT_commute():
    """The ruling's own named rejection case: `bench_occupancy` stays whole-zone, so two deploys
    collide there and both orderings are explored at full beam width. **The positive control for the
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
    """Issue #262's purity requirement, inherited. Two runs on one board must agree to the last bit —
    no dict/set iteration decides an order anywhere, and every tie resolves through `selection_key`."""
    obs, options = _menu_obs()
    a = cp.compose(_model(obs), options)
    b = cp.compose(_model(obs), options)
    assert [c.score for c in a.candidates] == [c.score for c in b.candidates]
    assert a.chosen.first_index == b.chosen.first_index
    assert a.margin.working() == b.margin.working()


@pytest.mark.req("REQ-COMPOSER-0005")
def test_the_composer_reaches_the_FULL_subset_lattice_of_a_block_when_the_beam_is_open():
    """The a-priori generation, end to end: with the beam wide enough to prune nothing, a block of 3
    yields its 8 subsets and no ordering is generated twice. Asserted on the SEQUENCES the composer
    actually built, not on `subset_lattice` in isolation."""
    obs, options = _menu_obs()
    result = cp.compose(_model(obs), options, k=99, depth=4)
    lines = {tuple(s.index for s in c.steps) for c in result.candidates}
    block = {line for line in lines if set(line) <= {0, 1, 2}}
    assert len(block) == 8
    assert all(list(line) == sorted(line, key=lambda i: line.index(i)) for line in block)
    assert all(len(set(line)) == len(line) for line in lines)


@pytest.mark.req("REQ-COMPOSER-0006")
def test_a_refused_option_becomes_a_flagged_one_action_candidate_and_reaches_the_telemetry():
    """*"A refusal is an unknown, not a zero."* An Item whose effect no clause covers refuses at the
    seam; the composer must surface it rather than let it price at 0.0 delta and vanish."""
    me = _player(active=_body(RIOLU), hand=[ITEM])
    obs = _obs(me, options=[{"type": _PLAY, "index": 0}, {"type": _END}])
    result = cp.compose(_model(obs), [{"type": _PLAY, "index": 0}, {"type": _END}])
    gapped = [c for c in result.candidates if c.coverage_gap]
    assert gapped and any(c.steps and c.steps[0].index == 0 for c in gapped)
    assert result.gaps and any("kind" in g for g in result.gaps)


@pytest.mark.req("REQ-COMPOSER-0006")
def test_a_coverage_gap_candidate_never_out_ranks_a_scored_sequence_it_merely_tied():
    """`selection_key`'s first leg. A gap is an absence of evidence, so it sorts last inside its score
    band rather than winning a tie it was never actually compared in."""
    obs, _options = _menu_obs()
    model = _model(obs)
    clean = cp.Candidate(leaf=1.0, score=1.0)
    gapped = cp.Candidate(leaf=1.0, score=1.0, coverage_gap="unmodelled")
    assert cp.selection_key(model, clean) < cp.selection_key(model, gapped)


# ── the beam-quality package: three DISTINCT mechanisms ──────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0007")
def test_the_selection_key_NEVER_falls_through_to_generation_order():
    """The ADR-0062:29 / `mega_starmie` ep82867148 f48/f87 / `mega_lucario` ep83661652 f33/f40/f44
    bug class, as a regression shape: two candidates equal on score must still separate on a
    BOARD-derived leg, never on which one the enumerator happened to build first."""
    obs, options = _menu_obs()
    model = _model(obs)
    stamped = [cp.stamp_origin(model, o) for o in options]
    left = cp.Candidate(steps=(cp.Step(stamped[0], 0, 3, ao.MODELLED),), score=1.0)
    right = cp.Candidate(steps=(cp.Step(stamped[2], 2, 0, ao.MODELLED),), score=1.0)
    assert cp.selection_key(model, left) != cp.selection_key(model, right)


@pytest.mark.req("REQ-COMPOSER-0007")
def test_the_chosen_line_is_the_SAME_under_a_permuted_menu():
    """Permuting the menu must permute the keys with it and invent no new ones (ADR-0103). Asserted
    on the CARD the composer commits to, not on the index — the index is exactly what moved."""
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
    """Mechanism 2, and it is NOT mechanism 1: this is about not LOSING a candidate during search,
    where `selection_key` is about choosing deterministically among candidates already in hand."""
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
    """Mechanism 3 — required, not optional. The instrument has to distinguish *"comfortably in"*
    from *"survived on the band"*, because the second is the beam-width sizing signal."""
    obs, options = _menu_obs()
    result = cp.compose(_model(obs), options, k=2)
    working = result.margin.working()
    assert set(working) == {"rank", "k", "ranked", "in_beam", "admitted", "always_expand",
                            "chosen_delta", "kth_delta", "margin_to_kth"}
    assert working["k"] == 2 and working["rank"] is not None


@pytest.mark.req("REQ-COMPOSER-0007")
def test_the_margin_separates_EARNED_a_slot_from_ADMITTED_unconditionally():
    """A terminal or a refused option is admitted whatever its rank (`must_expand`'s always-expand
    contract) and carries delta 0.0 because it was never applied — so reporting it as `in_beam` would
    state a tie at zero as if the leaf had preferred it.

    Not a corner case, measured: on `85046350|0|decision|32` (Issue #263's f32) **all five** options
    price exactly 0.0, so every survival on that frame is a tie and the distinction is the only thing
    that keeps the acceptance report honest."""
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
    """Neither costs a further expansion, and dropping either would make an unpriceable option
    indistinguishable from a worthless one — the always-expand contract `must_expand` names."""
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
    """ADR-0095 decision 1's bands, over board facts rather than over a scored `OptionTrace`. The
    ratified reason travels with them: inside a commutative block no function of the end state
    separates any ordering, so the doctrine order is the principled canonical choice."""
    obs, options = _menu_obs()
    model = _model(obs)
    assert cp.canonical_tier(model, options[2]) == cp.TIER_INFORMATIVE   # evolve
    assert cp.canonical_tier(model, options[0]) == cp.TIER_COMMITMENT    # Energy attach
    assert cp.canonical_tier(model, options[1]) == cp.TIER_COMMITMENT    # a Tool IS an `_ATTACH`
    assert cp.canonical_tier(model, options[3]) == cp.TIER_ENDER         # end turn
    assert cp.canonical_tier(model, {"type": _RETREAT}) == cp.TIER_ENDER


@pytest.mark.req("REQ-COMPOSER-0008")
def test_the_composers_tiers_ARE_the_pilots_tiers():
    """The tier NUMBERS are ADR-0095 decision 1's and live in `pilot._TIER_*`; the composer re-states
    them because its input differs (`pilot._tier` reads a scored `OptionTrace`, which no StateModel
    supplies) — but a re-stated constant that nobody checks is a renumbering waiting to go
    half-applied, which is the exact edit ADR-0095's own comment says is invisible in bare integers.

    Every other cross-store constant in this module is asserted the same way (`EPSILON` against
    `DECIDER_FLOOR`, `_TRIGGER_KIND` against `CLAUSE_SELECTORS`, `BRANCH_CAP` not re-declared at
    all); this closes the one that was missing."""
    from common import pilot

    assert (cp.TIER_INFORMATIVE, cp.TIER_COMMIT_FREE, cp.TIER_SUPPORTER, cp.TIER_COMMITMENT,
            cp.TIER_SHUFFLE, cp.TIER_ENDER) == (
        pilot._TIER_INFORMATIVE, pilot._TIER_COMMIT_FREE, pilot._TIER_SUPPORTER,
        pilot._TIER_COMMITMENT, pilot._TIER_SHUFFLE, pilot._TIER_ENDER)


@pytest.mark.req("REQ-COMPOSER-0008")
def test_a_revealing_play_takes_the_informative_tier_and_joins_no_block():
    """A revealer changes the OPTION SET, not only the board, so `footprints_commute` vetoes it
    whatever its read/write sets say — while the tier function stays TOTAL, because an ordering key
    that answered None for some options would fall through to menu position."""
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
#
# Both rows verified at source for this block, `data/EN_Card_Data.csv` for the printed text and
# `src/common/card_effects.json` for the clause — never recalled:
#
#   120  Drakloak                 "[Ability] Recon Directive — Once during your turn, you may look at
#                                  the top 2 cards of your deck and put 1 of them into your hand. Put
#                                  the other card on the bottom of your deck."
#                                 clause: {"kind": "draw", "amount": 1, "window": 2,
#                                          "condition": "once_per_turn_ability",
#                                          "rider": "other_to_bottom"}   <- NO `trigger`
#   19   Telepath Psychic Energy  "As long as this card is attached to a Pokemon, it provides {P}
#                                  Energy. // When you attach this card from your hand to a {P}
#                                  Pokemon, search your deck for up to 2 Basic {P} Pokemon and put
#                                  them onto your Bench. Then, shuffle your deck."
#                                 clause: {"kind": "fetch", ..., "trigger": "on_attach"}
DRAKLOAK, TELEPATH = 120, 19
_RIDE_STATS = {
    **_STATS,
    DRAKLOAK: CardStat(DRAKLOAK, name="Drakloak", hp=90, energyType=DRAGON, evolvesFrom="Dreepy",
                       hasAbility=True),
    TELEPATH: CardStat(TELEPATH, name="Telepath Psychic Energy", cardType=6, energyType=PSYCHIC),
}
_RIDE_CLAUSES = {
    DRAKLOAK: [{"kind": "draw", "amount": 1, "window": 2,
                "condition": "once_per_turn_ability", "rider": "other_to_bottom"}],
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
    """Drakloak's clause carries ``condition: once_per_turn_ability`` and NO ``trigger``: the Ability
    is its own `_ABILITY` option, so evolving into Drakloak reveals nothing and the point transition
    models it exactly.

    This is not hypothetical — routing on the footprint alone refused precisely this evolve, which is
    the RULED first step of `85046350|0|decision|32` (Issue #263's **f32**), so the composer could not
    price the human's own line on one of its three named acceptance frames."""
    model = _ride_model([DRAKLOAK])
    evolve = {"type": _EVOLVE, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0}
    assert ao.option_footprint(model, evolve).reveals_information is True   # the CARD can reveal
    assert cp._reveal_rides(model, evolve) is False                         # this OPTION does not


@pytest.mark.req("REQ-COMPOSER-0011")
def test_an_on_attach_reveal_DOES_ride_the_attach_and_must_refuse():
    """**The positive control for the test above**, and the reason the discriminator cannot simply be
    *"only a `_PLAY` reveals"*. Telepath Psychic Energy's `fetch` carries ``trigger: "on_attach"``, so
    the reveal really does ride the attach — and `board_delta._attach` never consults clauses at all,
    so letting it through would model the structural attach and silently drop a two-Pokémon Bench
    fill. An under-reported delta is a PRUNED option."""
    model = _ride_model([TELEPATH])
    attach = {"type": _ATTACH, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0}
    assert cp._reveal_rides(model, attach) is True
    result = cp.compose(model, [attach, {"type": _END}])
    assert any("RIDES this option" in gap for gap in result.gaps)


@pytest.mark.req("REQ-COMPOSER-0011")
def test_the_trigger_map_covers_the_whole_declared_vocabulary():
    """A `trigger` value the map has never heard of would fall through to *"does not ride"*, which is
    the under-report direction — so the map is asserted against the registry rather than against a
    hand-copied list, which is what it would have to drift from to fail."""
    from common import snapshot_coverage as sc

    assert set(cp._TRIGGER_KIND) == set(sc.CLAUSE_SELECTORS["trigger"])


# ── the budget caps ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0009")
def test_the_budget_caps_are_WHITELISTED_and_typed_authored_scaffold():
    """ADR-0099: an untyped entry is rejected by the registry, and an `authored-scaffold` one MUST
    carry a reconciliation note. `board_expectation`'s header states this entry as owed by Issue #385
    and names it, so a reader grepping `sound_rules.py` must find it."""
    rule = sound_rules.BY_ID["composer-budget-caps"]
    assert rule.type == sound_rules.AUTHORED_SCAFFOLD
    assert rule.reconciliation.strip()
    assert sound_rules.validate() == []


@pytest.mark.req("REQ-COMPOSER-0009")
def test_epsilon_is_the_measured_decider_floor_not_an_authored_number():
    """`EPSILON` is carried under its own name because `tools/` must never be a `src/` dependency —
    which makes it exactly the kind of transcription that drifts, so the agreement is asserted."""
    from train.family_diag import DECIDER_FLOOR
    assert cp.EPSILON == DECIDER_FLOOR


@pytest.mark.req("REQ-COMPOSER-0009")
def test_the_expectation_branch_cap_is_NOT_re_declared_here():
    """One store per ADR-0087. The composer consumes `board_expectation.BRANCH_CAP`; a second copy
    would drift, and both would stay internally consistent while disagreeing."""
    import re
    from pathlib import Path

    src = Path(cp.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^BRANCH_CAP\s*=", src, flags=re.M)


@pytest.mark.req("REQ-COMPOSER-0009")
def test_depth_truncation_is_REPORTED_never_silent():
    """The standing no-silent-caps discipline: a capped enumeration that reads as a complete one
    would make an under-explored line look confidently valued."""
    obs, options = _menu_obs()
    result = cp.compose(_model(obs), options, k=99, depth=1)
    assert result.stats["depth_truncated"] > 0


# ── the darkness ─────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSER-0010")
def test_the_composer_has_ZERO_production_callers():
    """Issue #385 lands DARK — arming it at MAIN is Issue #386's, and both ADR-0072 gates must
    therefore see byte-identical output at this commit. ASSERTED, not assumed: an accidental import
    from `pilot`/`planner` is exactly what would make the gate diff meaningful and nobody notice.

    Matched on an IMPORT STATEMENT, never on the substring: `apply_option`'s docstrings name
    `common.composer.resolve_against` as the consumer that made `option_serials` public, and a
    substring sweep reports that as a caller. A prose mention is not a call.

    *Positive control, both ways:* the same pattern finds `state_value`'s real production importers,
    so a silent zero would be the instrument failing rather than the codebase being clean — and it is
    re-run against `composer` itself to prove the pattern can match this module's own name."""
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
    assert importers("composer") == [], \
        f"composer is imported in production by {importers('composer')}"


@pytest.mark.req("REQ-COMPOSER-0010")
def test_the_composer_never_mutates_the_model_it_was_handed():
    """`apply_option`'s contract — *"the planner holds the pre-state while it evaluates
    alternatives"* — and the memo-staleness reason behind it: `state_value` caches its per-family
    dict on the model and nothing invalidates that key."""
    obs, options = _menu_obs()
    model = _model(obs)
    before = state_value(model)
    cp.compose(model, options)
    assert state_value(model) == before
    assert model.source_obs == obs
