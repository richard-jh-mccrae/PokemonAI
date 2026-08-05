"""The apply-seam's **choice nodes** (`common/board_choice.py`, POC-T4/5, Issue #392, under the seam
contract ADR-0098 froze at POC-T0; ruling ADR-TEMP-392).

Its two siblings are already covered: `test_apply_transitions.py` asserts the DETERMINISTIC
transitions (one option, one board) and `test_board_expectation.py` the STOCHASTIC ones (one option, a
distribution nature draws from). This file asserts the third shape — one option, a set of boards the
**player** chooses between, because the engine defers the target to a follow-up select.

Four properties carry the file:

* **Both of a retreat's dimensions expand.** `docs/rulebook.txt` L142 puts no type restriction on the
  Retreat Cost discard, so WHICH Energy to shed is a real second choice beside WHICH body to promote,
  and the space is their product. It collapses to one member when ``attached == cost`` or the cost is
  0 — structurally, because ``C(n, n)`` and ``C(n, 0)`` are both 1.
* **Truncation is never silent.** ``Expectation.truncated`` counts the dropped classes and
  ``total_probability`` falls below 1.0 by exactly the dropped share, because the probability
  denominator is the FULL enumeration rather than the kept one.
* **The seam is not widened.** `board_delta._retreat` stays allowance-only and parity-honest;
  everything here lives beside it. `test_apply_transitions.py`'s `_retreat` cases are unchanged and
  are expected to stay green — if they go red the implementation widened the seam.
* **A registered-but-unappliable member refuses, and names WHY.** `gust` has a target space and a
  Target Ranker and no board synthesis, because no issue owns the apply-seam transition for it.

The D7 combination — one sort key over an opponent-target menu — is asserted next door in
`test_deferred_target_rank.py`: it is a property of an ordering rather than of a board, and nothing
there builds one.

Card facts VERIFIED at source (`data/EN_Card_Data.csv`), never recalled — quoted at each constant.
Same primary seam as both sibling files: a dict-backed Stat Provider and hand-built zone dicts, no
Pilot and no engine boot, so this runs DLL-free on both platforms.
"""
from __future__ import annotations

import pytest

from common import apply_option as ao
from common import board_choice as bc
from common import board_delta as bd
from common import board_expectation as be
from common import snapshot_coverage as sc
from common.cards import CardFunctions
from common.effects import CardEffects
from common.scouting import matchup_plan
from common.scouting.provider import CardStat, DictCardStatProvider
from common.state_model import StateModel
from common.strategy.combat import CombatMath
from common.strategy.context import _PLAY, _RETREAT

MAIN = bd.CONTEXT_MAIN
FIGHTING, PSYCHIC, DARKNESS = 6, 5, 7

# ── the pool, every row quoted from `data/EN_Card_Data.csv` ───────────────────────────────────────
#
#   677 Riolu             Basic, HP 80, Retreat 2  — the standing single-hop worked example
#   678 Mega Lucario ex   Stage 1, HP 340, Retreat 2, Previous stage **Riolu** (`docs/rulebook.txt`
#                         Appendix 1: *"Mega Lucario ex doesn't evolve from Lucario or Lucario ex—
#                         just Riolu"*)
#   112 Munkidori         Basic, HP 110, Retreat 1
#   1182 Boss’s Orders    Supporter, *"Switch in 1 of your opponent's Benched Pokémon to the Active
#                         Spot."* — clause `{"kind": "gust", "target": "any"}`, verbatim from the
#                         committed `card_effects.json`
#   1229 Wally's Compassion  Supporter, *"Heal all damage from 1 of your Mega Evolution Pokémon
#                         {ex}…"* — clause kind `heal`, a declared census member with no resolver
RIOLU, MEGA_LUC, MUNKIDORI = 677, 678, 112
BOSS, WALLY = 1182, 1229
E_F, E_P, E_D = 6, 5, 7                 # Basic {F} / {P} / {D} Energy

_BASIC_ENERGY, _SUPPORTER = 5, 3

_STATS = {
    RIOLU: CardStat(RIOLU, name="Riolu", hp=80, energyType=FIGHTING, retreatCost=2),
    MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, ex=True,
                       energyType=FIGHTING, evolvesFrom="Riolu", retreatCost=2),
    MUNKIDORI: CardStat(MUNKIDORI, name="Munkidori", hp=110, energyType=PSYCHIC, retreatCost=1),
    E_F: CardStat(E_F, name="Basic {F} Energy", cardType=_BASIC_ENERGY, energyType=FIGHTING),
    E_P: CardStat(E_P, name="Basic {P} Energy", cardType=_BASIC_ENERGY, energyType=PSYCHIC),
    E_D: CardStat(E_D, name="Basic {D} Energy", cardType=_BASIC_ENERGY, energyType=DARKNESS),
    BOSS: CardStat(BOSS, name="Boss’s Orders", cardType=_SUPPORTER),   # U+2019 in the CSV
    WALLY: CardStat(WALLY, name="Wally's Compassion", cardType=_SUPPORTER),
}

#: The committed `card_effects.json` rows for the two Trainers, copied verbatim.
_CLAUSES = {
    BOSS: [{"kind": "gust", "target": "any"}],
    WALLY: [{"kind": "heal", "amount": "all", "restriction": "mega_only",
             "rider": "bounce_energy_to_hand"}],
}


def _combat():
    return CombatMath(DictCardStatProvider(_STATS), functions=CardFunctions({}), transients=None,
                      effects=CardEffects(_CLAUSES))


def _body(cid, *, serial=1, seat=0, energies=(), hp=None):
    full = _STATS[cid].hp
    return {"id": cid, "serial": serial, "playerIndex": seat, "hp": full if hp is None else hp,
            "maxHp": full, "appearThisTurn": False,
            "energies": [_STATS[e].energyType for e in energies],
            "energyCards": [{"id": e, "serial": 300 + serial * 10 + i, "playerIndex": seat}
                            for i, e in enumerate(energies)],
            "tools": [], "preEvolution": []}


def _player(*, active=None, bench=(), hand=(), discard=(), prize=4, seat=0, **flags):
    state = {"active": [active] if active else [], "bench": list(bench), "benchMax": 5,
             "hand": [{"id": c, "serial": 700 + i, "playerIndex": seat} for i, c in enumerate(hand)],
             "handCount": len(hand),
             "discard": [{"id": c, "serial": 600 + i, "playerIndex": seat}
                         for i, c in enumerate(discard)],
             "prize": [None] * prize, "deckCount": 30,
             **{f: False for f in bd.CONDITION_FLAGS}}
    state.update(flags)
    return state


def _obs(me, *, opp=None, context=MAIN, **current):
    opp = opp if opp is not None else _player(active=_body(MUNKIDORI, serial=50, seat=1), seat=1)
    state = {"players": [me, opp], "yourIndex": 0, "turn": 5,
             "energyAttached": False, "supporterPlayed": False, "retreated": False,
             "stadiumPlayed": False, "stadium": []}
    state.update(current)
    return {"current": state, "logs": [], "select": {"context": context, "option": []}}


def _model(obs, deck=()):
    return StateModel.build(obs, combat=_combat(), deck=list(deck))


RETREAT = {"type": _RETREAT}


def _board(*, active_energies=(E_F, E_F, E_P), bench=None, hand=(), **kw):
    """Mega Lucario ex Active (Retreat Cost **2**) over a Bench of two identical Riolu and one
    Munkidori — the shape that makes both collapses observable at once."""
    bench = bench if bench is not None else [_body(RIOLU, serial=2), _body(RIOLU, serial=3),
                                             _body(MUNKIDORI, serial=4)]
    me = _player(active=_body(MEGA_LUC, serial=1, energies=active_energies), bench=bench, hand=hand)
    return _model(_obs(me, **kw))


# ── the target space: both dimensions ─────────────────────────────────────────────────────────────


def test_a_retreat_expands_BOTH_of_its_deferred_dimensions():
    """The product, not one leg of it. Mega Lucario ex at Retreat Cost **2** holding {F}{F}{P} can
    shed ``{F,F}`` or ``{F,P}`` — two distinct Energy multisets — and can promote any of 3 benched
    bodies, so the space is 2 x 3 = 6.

    `docs/rulebook.txt` L142 is why the first dimension exists at all: *"you must discard 1 Energy from
    your Active Pokémon for each [C] listed in its Retreat Cost"*, with **no type restriction**, so
    which Energy goes is genuinely the player's choice and the engine poses it as `_DISCARD_ENERGY`
    (context 30)."""
    space = bc.target_space(_board(), RETREAT, seat_index=0)
    assert len(space) == 6
    assert {d for d, _j in space} == {(0, 1), (0, 2)}          # {F,F} and {F,P}; (1,2) is {F,P} again
    assert {j for _d, j in space} == {0, 1, 2}


def test_identical_ENERGY_CARDS_are_one_choice_and_the_fingerprint_provably_cannot_say_so():
    """The Energy leg's collapse is on card ids, and it is **not** merely an optimisation.

    `option_fingerprint` compares a body's card lists by VALUE **including their order**, so removing
    entries 0 and 1 versus 0 and 6 from eight attached Energy leaves the same multiset in a different
    order and fingerprints differently — measured on the committed corpus at `boomer_9001` f39 (Mega
    Zygarde ex, eight Energy, Retreat Cost 2). No canonical removal repairs it either: the ENGINE's
    own pick among identical cards is arbitrary and lands in that same order.

    Hence :func:`board_choice.candidate_class`, the second vocabulary. Here it is asserted directly:
    four identical {F} at cost 2 pose exactly ONE Energy decision, and every index pair keys to it."""
    model = _board(active_energies=(E_F, E_F, E_F, E_F))
    space = bc.target_space(model, RETREAT, seat_index=0)
    assert {d for d, _j in space} == {(0, 1)}                   # C(4,2) = 6 index pairs, ONE choice
    for pair in ((0, 1), (0, 3), (2, 3)):
        assert bc.candidate_class(model, RETREAT, (pair, 0), seat_index=0) == ((E_F, E_F), 0)


@pytest.mark.parametrize("energies", [(), (E_F, E_F)])
def test_the_energy_leg_collapses_to_one_member_when_there_is_nothing_to_choose(energies):
    """*"attached == cost or the Retreat Cost is 0"* — and STRUCTURALLY, not by a special case:
    ``C(n, n)`` and ``C(n, 0)`` are both 1, so the claim is a property of the enumeration rather than
    a branch that could drift from it. Mega Lucario ex at cost 2 holding exactly {F}{F} has one legal
    payment; holding nothing at all it cannot be the cost-2 case, so the free-retreat leg is run
    against Riolu-with-nothing below."""
    bench = [_body(RIOLU, serial=2), _body(MUNKIDORI, serial=4)]
    if energies:
        model = _board(active_energies=energies, bench=bench)
    else:                                     # a body whose cost the board zeroes: nothing to pay
        me = _player(active=_body(MUNKIDORI, serial=1), bench=bench)
        model = _model(_obs(me))
        object.__setattr__(_STATS[MUNKIDORI], "retreatCost", 0)
    try:
        space = bc.target_space(model, RETREAT, seat_index=0)
    finally:
        object.__setattr__(_STATS[MUNKIDORI], "retreatCost", 1)
    assert len({d for d, _j in space}) == 1
    assert len(space) == 2                                     # one payment x two benched bodies


def test_a_retreat_with_an_empty_bench_refuses_rather_than_enumerating_nothing():
    """*"Then, you switch that retreating Pokémon with a Pokémon from your Bench"* (`docs/rulebook.txt`
    L142) — with no Bench there is nothing to switch with, so this is not a legal play. A refusal, not
    a zero-class Expectation: `expected()` raises on empty mass, which would surface inside the
    ordering loop rather than on the telemetry line where it can be acted on."""
    model = _board(bench=[])
    with pytest.raises(bd.Unmodellable, match="Bench is empty"):
        bc.target_space(model, RETREAT, seat_index=0)


# ── the class identity ────────────────────────────────────────────────────────────────────────────


def test_two_identical_benched_bodies_collapse_to_ONE_outcome_class():
    """ADR-0091's own contract, on this node: *"two indistinguishable reveals are ONE outcome, so the
    branching factor is the number of decisions the reveal actually poses"*. Six candidates over a
    Bench of Riolu / Riolu / Munkidori yield **four** classes — the two Riolu are one promotion
    decision, whichever slot they sit in, and `serial` is the only field they differ on."""
    exp = bc.deferred_target(_board(), RETREAT)
    assert len(bc.target_space(_board(), RETREAT, seat_index=0)) == 6
    assert len(exp.classes) == 4
    assert len({c.fingerprint for c in exp.classes}) == 4


def test_the_class_identity_is_a_PAIR_because_the_active_alone_would_erase_a_whole_dimension():
    """The positive control for the pair, and the reason it is a pair.

    Two candidates that promote the SAME body while discarding different Energy reach genuinely
    different boards — the retreating body lands on the Bench carrying different Energy — and a
    fingerprint over the new Active alone is identical for both. So it would collapse them, erasing
    the Energy-discard dimension entirely. Here: same promoted body, different payment, two classes;
    and the Active half of the two fingerprints is the same string, which is what makes this evidence
    about the SECOND element rather than a coincidence."""
    model = _board()
    seat = 0
    first = bc.realise(model, RETREAT, ((0, 1), 0), seat_index=seat)[1]
    second = bc.realise(model, RETREAT, ((0, 2), 0), seat_index=seat)[1]
    assert first != second
    assert first[0] == second[0]                    # the promoted body — identical
    assert first[1] != second[1]                    # the retreating body's remaining Energy — not


# ── the Expectation contract ──────────────────────────────────────────────────────────────────────


def test_every_class_is_equally_probable_and_a_complete_enumeration_sums_to_one():
    """Choice semantics: a uniform prior over decisions the PLAYER makes. The number itself is not the
    value — `Expectation.expected`'s docstring already rules that *"for a choice node the true value is
    the max"* and the composer takes it — but ``total_probability`` must still read 1.0 on a complete
    enumeration, or a truncated one could not be told from it."""
    exp = bc.deferred_target(_board(), RETREAT)
    assert exp.truncated == 0
    assert exp.total_probability == pytest.approx(1.0)
    assert [c.probability for c in exp.classes] == pytest.approx([1.0 / len(exp.classes)] * 4)


def test_truncation_past_the_cap_is_reported_TWICE_and_the_probability_gap_IS_the_truncation():
    """The "no silent caps" rule, which is why the denominator is the FULL enumeration and not the
    kept one: normalising over the survivors would sum to 1.0 while classes were being dropped, and a
    capped enumeration that reads as a complete one would make an under-explored line look confidently
    valued.

    ``cap`` is a parameter for exactly this — `BRANCH_CAP` is 12 and a legal board rarely reaches it,
    so truncation would otherwise be untestable."""
    full = bc.deferred_target(_board(), RETREAT)
    capped = bc.deferred_target(_board(), RETREAT, cap=2)
    assert len(capped.classes) == 2
    assert capped.truncated == len(full.classes) - 2
    assert capped.total_probability == pytest.approx(2.0 / len(full.classes))


def test_the_cap_is_board_expectations_own_constant_and_never_a_second_one():
    """A choice node and a chance node cost the same thing — leaf evaluations on one option — so they
    take the same cap, and the `composer-budget-caps` whitelist entry Issue #385 owes covers both. A
    second constant here would be a second thing to re-derive when that entry lands."""
    import inspect
    assert inspect.signature(bc.deferred_target).parameters["cap"].default is be.BRANCH_CAP


def test_a_cap_below_one_is_a_CALLER_error_and_raises_where_a_modelling_gap_refuses():
    """Mirrors `board_expectation.expectation` exactly: a zero-class Expectation is an un-enumerated
    effect whose `expected()` raises inside the ordering loop, which is the shape the empty-space
    refusal exists to prevent. A caller asking for one is a bug in the caller, not a gap in the
    board."""
    with pytest.raises(ValueError, match="at least one class"):
        bc.deferred_target(_board(), RETREAT, cap=0)


# ── purity ────────────────────────────────────────────────────────────────────────────────────────


def test_the_node_never_mutates_the_model_it_was_given_MEMO_INCLUDED():
    """*"The planner holds the pre-state while it evaluates alternatives"* — a node that edited in
    place would corrupt every sibling branch. **The memo is the sharp half**: `state_value` caches its
    per-family dict on the model under `("state_value",)` and NOTHING invalidates that key, so a
    mutated model would keep returning the pre-state's scalar in silence. Read the scalar first, so
    the memo is warm and would be caught if the node wrote through it.

    Copied from `test_apply_transitions.py`'s own purity test, deliberately: this node forks the same
    observation the same way, and one expansion writes as many boards as the space has members, so it
    has more chances to get it wrong than a point transition does."""
    from common import state_value as sv
    model = _board()
    before = sv.state_value(model)
    exp = bc.deferred_target(model, RETREAT)
    assert len(exp.classes) > 1
    assert model.mine.active.card_id == MEGA_LUC
    assert model.mine.active.energy_count == 3
    assert [b.card_id for b in model.mine.bench] == [RIOLU, RIOLU, MUNKIDORI]
    assert model.retreated is False
    assert model.mine.discard_ids == ()
    assert sv.state_value(model) == before


def test_the_classes_are_ordered_deterministically_so_two_processes_enumerate_one_set():
    """The reproducibility guarantee `option_equivalence.class_representatives` keeps for the same
    reason: the ordering must be a pure function of the board, or two processes handed one frame
    truncate to different sets and the ADR-0072 gates stop being replayable."""
    first = bc.deferred_target(_board(), RETREAT, cap=2)
    second = bc.deferred_target(_board(), RETREAT, cap=2)
    assert [c.fingerprint for c in first.classes] == [c.fingerprint for c in second.classes]


# ── the synthesized board is the rules, read at source ────────────────────────────────────────────


def test_the_swap_keeps_the_retreating_bodys_damage_and_sheds_only_the_paid_energy():
    """`docs/rulebook.txt` L143 — *"Keep all damage counters and all attached cards with each Pokémon
    when they switch"* — against L142's *"discard 1 Energy … for each [C]"*. So a damaged Mega Lucario
    ex arrives on the Bench still damaged, still holding what it did not pay, and the paid cards are in
    my discard.

    The Bench PLACEMENT is a swap in place, read off the committed traces rather than recalled
    (`board_choice`'s header names `alakazam_9001` f7, where bench[2] was promoted and the retreating
    body is bench[2] afterwards) and gated over 2254 steps by `tools/train/choice_parity.py`."""
    me = _player(active=_body(MEGA_LUC, serial=1, energies=(E_F, E_F, E_P), hp=200),
                 bench=[_body(MUNKIDORI, serial=4), _body(RIOLU, serial=2)])
    model = _model(_obs(me))
    after = bc.realise(model, RETREAT, ((0, 2), 1), seat_index=0)[0]
    side = after["current"]["players"][0]
    assert [b["id"] for b in side["active"]] == [RIOLU]
    assert [b["id"] for b in side["bench"]] == [MUNKIDORI, MEGA_LUC]     # swapped IN PLACE, at 1
    landed = side["bench"][1]
    assert landed["hp"] == 200                                          # L143: damage counters keep
    assert [c["id"] for c in landed["energyCards"]] == [E_F]            # paid {F} and {P}, kept {F}
    assert landed["energies"] == [FIGHTING]                             # re-derived from what remains
    assert [c["id"] for c in side["discard"]] == [E_F, E_P]
    assert after["current"]["retreated"] is True


def test_a_body_reaching_the_bench_recovers_from_every_special_condition():
    """`docs/rulebook.txt` L143 — *"When your Active Pokémon goes to your Bench (whether it retreated
    or got there some other way), some things do go away—Special Conditions and any effects from
    attacks."*

    Through `board_delta.clear_conditions`, the same function the evolve transition uses, so the two
    cannot disagree about the clause. The flags live on `PlayerState` rather than on the body
    (`docs/rules.md` §8: only the Active can carry one, so the engine has no per-body home), which is
    why clearing them is a side write and gets its own declared zone."""
    me = _player(active=_body(MUNKIDORI, serial=1, energies=(E_P,)),
                 bench=[_body(RIOLU, serial=2)], poisoned=True, confused=True)
    model = _model(_obs(me))
    after, writes = bc.CHOICE_REGISTRY[_RETREAT].apply(model, ((0,), 0), seat_index=0)
    side = after["current"]["players"][0]
    assert not any(side[f] for f in bd.CONDITION_FLAGS)
    assert "special_conditions" in writes
    assert model.source_obs["current"]["players"][0]["poisoned"] is True   # the pre-state is intact


def test_a_free_retreat_writes_no_energy_and_no_discard():
    """The write set is EXACT, per case — the same standard `board_delta.Delta.writes` is held to, and
    what makes a FORGOTTEN write a failure rather than only an extra one. A Retreat Cost of 0 moves
    two bodies and one allowance and touches neither Energy nor the discard."""
    object.__setattr__(_STATS[MUNKIDORI], "retreatCost", 0)
    try:
        me = _player(active=_body(MUNKIDORI, serial=1, energies=(E_P,)),
                     bench=[_body(RIOLU, serial=2)])
        _after, writes = bc.CHOICE_REGISTRY[_RETREAT].apply(_model(_obs(me)), ((), 0), seat_index=0)
    finally:
        object.__setattr__(_STATS[MUNKIDORI], "retreatCost", 1)
    assert writes == {"allowance_retreat_used", "bodies_in_play"}


# ── routing and refusals ──────────────────────────────────────────────────────────────────────────


def test_the_node_refuses_off_the_MAIN_menu():
    """`board_delta.transition`'s own boundary, mirrored: an option posed INSIDE a card's effect
    resolution is one leg of that CARD's step and carries writes belonging to the card rather than to
    the option's kind. Measured at 14 580 of 14 581 modelled steps."""
    me = _player(active=_body(MEGA_LUC, serial=1, energies=(E_F, E_F)),
                 bench=[_body(RIOLU, serial=2)])
    with pytest.raises(bd.Unmodellable, match="MAIN menu"):
        bc.deferred_target(_model(_obs(me, context=3)), RETREAT)


def test_an_option_with_no_deferred_target_is_not_a_choice_node():
    """The routing question, from the other side: an `_ATTACH` determines its own target, so it is a
    point transition. A node that answered *"expand everything"* here would turn every option into a
    product space."""
    model = _board()
    assert bc.has_deferred_target(model, RETREAT, seat_index=0) is True
    assert bc.has_deferred_target(model, {"type": 8, "index": 0}, seat_index=0) is False
    with pytest.raises(bd.Unmodellable, match="no deferred target"):
        bc.choice_key(model, {"type": 8, "index": 0}, seat_index=0)


def test_a_foreign_seat_refuses_because_the_rankers_price_MY_board():
    """A Deferred-Target Option is one *I* am taking. The rankers read my Bench and my Active's build,
    so answering for another seat would rank the wrong side's future — silently, which is the whole
    class of bug this seam's refusals exist to make loud."""
    with pytest.raises(bd.Unmodellable, match="not the model's own"):
        bc.deferred_target(_board(), RETREAT, seat_index=1)


# ── the `gust` registry entry: wired, graded, and REFUSED for a named reason ──────────────────────


def test_the_gust_target_space_resolves_their_bench_from_the_declared_clause():
    """Boss's Orders (1182), *"Switch in 1 of your opponent's Benched Pokémon to the Active Spot"*,
    clause ``{"kind": "gust", "target": "any"}``. The AREA is the clause KIND's — a gust reaches across
    the table, onto their Bench — and the `target` selector narrows within it. Proving the resolver
    runs is what makes the future clause application a wiring change rather than a design."""
    opp = _player(active=_body(MUNKIDORI, serial=50, seat=1),
                  bench=[_body(RIOLU, serial=51, seat=1), _body(MEGA_LUC, serial=52, seat=1)],
                  seat=1)
    me = _player(active=_body(MEGA_LUC, serial=1, energies=(E_F, E_F)), hand=(BOSS,),
                 bench=[_body(RIOLU, serial=2)])
    model = _model(_obs(me, opp=opp))
    option = {"type": _PLAY, "index": 0}
    assert bc.choice_key(model, option, seat_index=0) == "gust"
    assert bc.target_space(model, option, seat_index=0) == (0, 1)


def test_the_target_CLASS_resolver_is_driven_by_the_compendium_and_is_CLOSED_over_it():
    """**ADR-TEMP-392 decision 2, as a test**: *"Expansion is data-driven off the compendium's target
    vocabulary, never per-card. The class resolver reads `CLAUSE_SELECTORS["target"]` … a hand-written
    expander per card hardcodes what is already data."*

    So every one of the **24** values `snapshot_coverage` declares must route somewhere named — and
    the three destinations are three different pieces of work, which is why they are three different
    refusals rather than one:

    * a **predicate** — 14 of them, the body classes a board can evaluate;
    * a **category error** — 10 of them (`basic_energy`, `item`, `supporter`, …) name a CARD class,
      and a space over bodies in play cannot evaluate one. Not work owed; a backlog that conflated
      this with the next bucket would size work that does not exist;
    * a **scoped gap** — declared vocabulary with no board predicate yet. Currently empty, which is
      why the assertion is on the PARTITION rather than on a list: a value added to the compendium
      lands here and says so, instead of raising `KeyError` inside an ordering loop.

    The vacuity guard is the partition being exhaustive over a non-empty declared set."""
    declared = sc.CLAUSE_SELECTORS["target"]
    assert declared, "vacuity guard: an empty vocabulary would pass everything below"
    buckets = {"predicate": set(), "category": set(), "gap": set()}
    for value in declared:
        try:
            bc.target_predicate({"kind": "gust", "target": value})
            buckets["predicate"].add(value)
        except bd.Unmodellable as gap:
            buckets["category" if "category error" in str(gap) else "gap"].add(value)
    assert set().union(*buckets.values()) == set(declared)       # exhaustive: nothing raises KeyError
    assert set(bc.BODY_PREDICATES) <= set(declared), sorted(set(bc.BODY_PREDICATES) - set(declared))
    assert buckets["predicate"] == set(bc.BODY_PREDICATES)
    assert "basic_energy" in buckets["category"] and "any" in buckets["predicate"]


def test_the_resolver_fails_CLOSED_on_vocabulary_drift_in_BOTH_directions():
    """A selector value the compendium never declared, and a clause KEY this resolver has not heard
    of, are both drift — someone minted vocabulary nobody registered — and both refuse rather than
    reading as *"everything"*. Same discipline `board_expectation._check_clause` keeps for its own
    handled-key set, and the reason is the same: an unknown narrowing read as no narrowing is the one
    failure that silently widens a target space."""
    with pytest.raises(bd.Unmodellable, match="declares"):
        bc.target_predicate({"kind": "gust", "target": "a_value_nobody_declared"})
    with pytest.raises(bd.Unmodellable, match="handled set"):
        bc.target_predicate({"kind": "gust", "target": "any", "unheard_of_key": 1})


def test_the_predicates_read_CardStat_as_the_ENGINE_populates_it_not_as_the_CSV_prints_it():
    """The trap this test exists for: the shipped provider leaves `CardStat.stage` **None** — verified
    against the engine-backed provider, where Riolu, Mega Lucario ex and Munkidori all read
    ``stage=None`` while `evolvesFrom` / `stage2` / `megaEx` are populated. A `basic` predicate keyed
    on `stage == "Basic Pokémon"` would therefore match NOTHING and fail silently, in the widening
    direction for a class the caller believed it had narrowed.

    So Basic is *"a Pokémon that evolves from nothing"* and Stage 1 *"evolves from something and is
    not Stage 2"*. Asserted against the fixture's own rows, whose facts
    `tests/scouting/test_cardstat_fixture_facts.py` audits field-for-field against
    `data/EN_Card_Data.csv`."""
    place = bc._BodyPlace(active=False, mine=True)
    riolu, mega = _STATS[RIOLU], _STATS[MEGA_LUC]
    assert bc.BODY_PREDICATES["basic"](riolu, place) is True
    assert bc.BODY_PREDICATES["basic"](mega, place) is False
    assert bc.BODY_PREDICATES["evolution"](mega, place) is True
    assert bc.BODY_PREDICATES["mega"](mega, place) is True and \
        bc.BODY_PREDICATES["mega"](riolu, place) is False
    # Mega Lucario ex evolves from Riolu and is NOT a Stage 2 (`docs/rulebook.txt` Appendix 1 — the
    # single-hop line), so it is the Stage 1 predicate's positive case.
    assert bc.BODY_PREDICATES["stage1"](mega, place) is True
    assert bc.BODY_PREDICATES["stage2"](mega, place) is False
    # Place, not card: the same body is `benched` or not depending on where it sits.
    assert bc.BODY_PREDICATES["benched"](riolu, place) is True
    assert bc.BODY_PREDICATES["benched"](riolu, bc._BodyPlace(active=True, mine=True)) is False


def test_an_unreadable_body_matches_NO_class_rather_than_every_class():
    """Fail CLOSED, the direction `combat._accel_target_ok` also takes: a card the compendium has
    never heard of resolves to `None`, and a predicate that treated that as *"unconstrained"* would
    widen a narrowed target space to the whole board."""
    match = bc.target_predicate({"kind": "gust", "target": "any"})
    assert match(_STATS[RIOLU], bc._BodyPlace(active=False, mine=False)) is True
    assert match(None, bc._BodyPlace(active=False, mine=False)) is False


def test_the_gust_entry_is_currently_UNREACHABLE_and_the_test_names_why():
    """**The acceptance criterion, as a test.** `gust` is a declared member of the deferred-target
    census with a built target space and a built Target Ranker, and `deferred_target` still refuses it
    — because no apply-seam transition writes the zones a gust writes.

    The CAUSE is asserted rather than described: ``CLAUSE_WRITES["gust"]`` is non-empty, and
    `board_delta._play` refuses any card whose clause write-set is non-empty. So the two facts that
    make the refusal correct are checked here, and a future issue landing the clause application will
    turn this test red at exactly the line that stops being true.

    **No issue currently owns landing it.** `board_delta._play`'s docstring forward-references
    *"Expectation / choice nodes in POC-T4/2 (Issue #383)"*, but #383 shipped chance nodes gated on
    `REVEALING_CLAUSES = {"draw", "fetch"}`, and Issue #303 minted the clause KIND in the compendium
    rather than the transition. That gap is real and unfiled — recorded in `board_choice`'s header."""
    assert sc.CLAUSE_WRITES["gust"]                        # non-empty: `_play` refuses the card
    assert "gust" not in sc.REVEALING_CLAUSES              # so `board_expectation` never sees it
    opp = _player(active=_body(MUNKIDORI, serial=50, seat=1),
                  bench=[_body(RIOLU, serial=51, seat=1)], seat=1)
    me = _player(active=_body(MEGA_LUC, serial=1, energies=(E_F, E_F)), hand=(BOSS,),
                 bench=[_body(RIOLU, serial=2)])
    model = _model(_obs(me, opp=opp))
    with pytest.raises(bd.Unmodellable, match="NO ISSUE CURRENTLY OWNS IT"):
        bc.deferred_target(model, {"type": _PLAY, "index": 0})


def test_a_declared_census_member_with_no_resolver_says_so_rather_than_going_quiet():
    """`heal` is in `CHOICE_CLAUSES` — Wally's Compassion ×14 is part of the 63-step census — and has
    no target-space resolver. The refusal names it as a scope boundary, so the backlog groups by an
    actionable sentence instead of by "not implemented"."""
    me = _player(active=_body(MEGA_LUC, serial=1, energies=(E_F, E_F)), hand=(WALLY,),
                 bench=[_body(RIOLU, serial=2)])
    model = _model(_obs(me))
    with pytest.raises(bd.Unmodellable, match="no target SPACE resolver is built"):
        bc.target_space(model, {"type": _PLAY, "index": 0}, seat_index=0)


def test_the_declared_vocabulary_is_CLOSED_over_the_registries_that_consume_it():
    """The vacuity guard and its positive control, copied from `test_snapshot_coverage.py`'s pattern.

    Every registry key must be a declared member of `CHOICE_KINDS` or `CHOICE_CLAUSES`, and every
    declared clause kind must be one `snapshot_coverage` has heard of — a member misspelled into a
    registry would otherwise be dead code that no refusal and no test could distinguish from an
    absent one. The positive control is the second assertion: the same walk finds `gust`/`heal`/`accel`
    present in `CLAUSE_WRITES`, so a silent empty comparison would not pass it."""
    declared = set(bc.CHOICE_KINDS) | set(bc.CHOICE_CLAUSES)
    assert declared, "vacuity guard: an empty vocabulary would pass every assertion below"
    assert set(bc.CHOICE_REGISTRY) <= declared, sorted(set(bc.CHOICE_REGISTRY) - declared)
    assert set(bc.TARGET_RANKERS) <= set(bc.CHOICE_REGISTRY)
    assert set(bc.CHOICE_CLAUSES) <= set(sc.CLAUSE_WRITES)          # the positive control
    # ONE record per key is what makes the sync obligation structural rather than prose: every entry
    # carries a space and a canonical form, and `apply`/`fingerprint` are one capability in two halves
    # that `ChoiceKind.__post_init__` refuses to let drift apart. Asserted here as well as in the
    # constructor so a key added with a half-filled record fails a reading, not only a construction.
    for key, entry in bc.CHOICE_REGISTRY.items():
        assert entry.space is not None and entry.canonical is not None, key
        assert (entry.apply is None) == (entry.fingerprint is None), key
        assert entry.apply is not None or entry.no_applier.strip(), key


# ── the seam wiring ───────────────────────────────────────────────────────────────────────────────


def test_the_seam_returns_the_POINT_transition_until_expansion_is_ARMED():
    """`runtime.PROFILE["deferred_target_expansion"]` ships False, so the ADR-0098 parity lane and both
    ADR-0072 gates keep seeing the seam Issue #382 verified: a retreat resolves through
    `board_delta._retreat` to the allowance-only board the recorded native trace shows.

    Armed, the SHAPE changes and the fate does not — `apply_option` already declares an `Expectation`
    among its four return shapes."""
    model = _board()
    off = ao.apply_option(model, RETREAT)
    assert isinstance(off, StateModel)
    assert off.retreated is True and off.mine.active.card_id == MEGA_LUC   # nothing else moved
    on = ao.apply_option(model, RETREAT, expand_deferred_targets=True)
    assert isinstance(on, ao.Expectation)
    assert len(on.classes) == 4
    assert ao.fate(RETREAT, deferred_target=True) == ao.MODELLED


def test_the_armed_seam_REFUSES_rather_than_falling_back_to_the_point_transition():
    """The fallback is the whole defect this node exists to delete: a retreat's point delta is the
    allowance bit alone, which prices at ~0.0 and reads at ordering time as *never explore this*
    (Issue #263: *"a 0 delta at ordering time means never explored, not undervalued"*). So a refusal —
    the always-expand path — is the honest answer, and an option with no ESTIMATE must never be handed
    back as an option with no VALUE."""
    model = _board(bench=[])
    result = ao.apply_option(model, RETREAT, expand_deferred_targets=True)
    assert ao.must_expand(result)
    assert "Bench is empty" in result.reason


# ── the defect, as an assertion ───────────────────────────────────────────────────────────────────


def test_an_unexpanded_retreat_prices_at_EXACTLY_zero_and_expansion_gives_the_leaf_a_choice():
    """**Half of the acceptance criterion, and the half this seam can honestly carry.**

    Issue #392 calls a retreat's 1-ply delta a *near*-zero. It is **exactly 0.0**:
    `board_delta._retreat` writes ``allowance_retreat_used`` alone and no `state_value` family reads
    the retreat allowance, so the delta is not small — there is nothing there. Issue #263's amendment
    rules what that means: *"a 0 delta at ordering time means **never explored**, not undervalued."*

    ⚠️ **What this test deliberately does NOT assert**, because the fixture cannot support it: that
    the expanded delta is POSITIVE. These `CardStat`s carry no attacks, so `state_value`'s families
    read almost nothing off them and the leaf scores every promotion identically — the expansion
    supplies the information and this board has no instrument that consumes it. Asserting a positive
    delta here would need attack fixtures rich enough to make the leaf discriminate, at which point
    the test would be measuring the fixture. The claim is made where it can be measured instead:
    `tests/train/test_choice_beam.py` runs the real f32 / f35 acceptance frames through a built,
    engine-backed Pilot and pins **+0.00075** and **+0.00186** prizes.

    What IS asserted here is the structural half: the expansion produces several genuinely distinct
    boards, each a different promoted body, where the point transition produced one board with the
    Active unmoved. That is the information the leaf is given, independent of whether this stripped
    fixture's leaf can use it."""
    from common import state_value as sv
    me = _player(active=_body(MUNKIDORI, serial=1, energies=(E_P,), hp=20),
                 bench=[_body(RIOLU, serial=2), _body(MEGA_LUC, serial=3)])
    model = _model(_obs(me))
    base = sv.state_value(model)

    point = ao.apply_option(model, RETREAT)
    assert sv.state_value(point) - base == 0.0
    assert point.mine.active.card_id == MUNKIDORI          # the swap is a later select

    expanded = ao.apply_option(model, RETREAT, expand_deferred_targets=True)
    assert {c.model.mine.active.card_id for c in expanded.classes} == {RIOLU, MEGA_LUC}
    assert len({c.fingerprint for c in expanded.classes}) == len(expanded.classes)


def test_the_expansion_is_ranked_before_it_is_capped_so_truncation_keeps_the_best_target():
    """Parent-slot beam accounting makes the composer take the ARGMAX over an expanded family, so a cap
    that dropped the best target would silently change the answer rather than merely narrow it. The
    guarantee is that the cap is applied to a RANKED enumeration, and the ranker is
    `TARGET_RANKERS[_RETREAT]` — ADR-0100's own retreat equation read as a ranking.

    Asserted against the ranker rather than against the leaf, because those are different instruments
    on purpose (D3: *"the rankers prefilter; `state_value` decides"*) and this fixture's leaf does not
    discriminate. At ``cap=1`` the single surviving class must be the ranker's own argmax."""
    model = _board()
    space = bc.target_space(model, RETREAT, seat_index=0)
    best = max(space, key=lambda c: (bc.rank_retreat(model, c), tuple(-x for x in (c[1],))))
    expected = bc.realise(model, RETREAT, best, seat_index=0)[1]
    capped = bc.deferred_target(model, RETREAT, cap=1)
    assert capped.truncated == len(bc.deferred_target(model, RETREAT).classes) - 1
    assert capped.classes[0].fingerprint == expected
