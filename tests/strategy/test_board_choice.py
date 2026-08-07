"""The apply-seam's **choice nodes** (`common/board_choice.py`, Issue #392, ruling ADR-0121) — one
option, a set of boards the PLAYER chooses between.

Siblings: `test_apply_transitions.py` (deterministic) and `test_board_expectation.py` (stochastic).
`board_delta._retreat` stays allowance-only, so if its cases there go red the seam was widened.

Card facts VERIFIED at source (`data/EN_Card_Data.csv`), quoted at each constant. Dict-backed Stat
Provider and hand-built zone dicts: no Pilot, no engine boot, DLL-free on both platforms.
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
# 677 Riolu Basic | 678 Mega Lucario ex Stage 1 from **Riolu** (NOT Lucario) | 112 Munkidori Basic
RIOLU, MEGA_LUC, MUNKIDORI = 677, 678, 112
#   1182 Boss's Orders  Supporter, clause `gust` | 1229 Wally's Compassion  Supporter, clause `heal`
BOSS, WALLY = 1182, 1229
#   1097 Night Stretcher  *"a Pokemon **or** a Basic Energy card"* from discard — a UNION, cap 1
#   1118 Energy Retrieval  *"up to 2 Basic Energy"* from discard | 1125 Master Ball  a DECK search
NIGHT_STRETCHER, ENERGY_RETRIEVAL, MASTER_BALL = 1097, 1118, 1125
E_F, E_P, E_D = 6, 5, 7                 # Basic {F} / {P} / {D} Energy

_BASIC_ENERGY, _SUPPORTER, _ITEM = 5, 3, 1

_STATS = {
    RIOLU: CardStat(RIOLU, name="Riolu", hp=80, energyType=FIGHTING, retreatCost=2,
                    stage="basic"),
    MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, ex=True,
                       energyType=FIGHTING, evolvesFrom="Riolu", retreatCost=2, stage="stage1"),
    MUNKIDORI: CardStat(MUNKIDORI, name="Munkidori", hp=110, energyType=PSYCHIC, retreatCost=1,
                        stage="basic"),
    E_F: CardStat(E_F, name="Basic {F} Energy", cardType=_BASIC_ENERGY, energyType=FIGHTING),
    E_P: CardStat(E_P, name="Basic {P} Energy", cardType=_BASIC_ENERGY, energyType=PSYCHIC),
    E_D: CardStat(E_D, name="Basic {D} Energy", cardType=_BASIC_ENERGY, energyType=DARKNESS),
    BOSS: CardStat(BOSS, name="Boss’s Orders", cardType=_SUPPORTER),   # U+2019 in the CSV
    WALLY: CardStat(WALLY, name="Wally's Compassion", cardType=_SUPPORTER),
    NIGHT_STRETCHER: CardStat(NIGHT_STRETCHER, name="Night Stretcher", cardType=_ITEM),
    ENERGY_RETRIEVAL: CardStat(ENERGY_RETRIEVAL, name="Energy Retrieval", cardType=_ITEM),
    MASTER_BALL: CardStat(MASTER_BALL, name="Master Ball", cardType=_ITEM),
}

#: The committed `card_effects.json` rows for the two Trainers, copied verbatim.
_CLAUSES = {
    BOSS: [{"kind": "gust", "target": "any"}],
    WALLY: [{"kind": "heal", "amount": "all", "restriction": "mega_only",
             "rider": "bounce_energy_to_hand"}],
    NIGHT_STRETCHER: [{"kind": "fetch", "target": "basic_energy", "zone": "discard",
                       "choice": True},
                      {"kind": "fetch", "target": "pokemon", "zone": "discard", "choice": True}],
    ENERGY_RETRIEVAL: [{"kind": "fetch", "target": "basic_energy", "zone": "discard", "amount": 2}],
    MASTER_BALL: [{"kind": "fetch", "target": "pokemon", "zone": "deck"}],
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
    """Retreat Cost **2** Active over a Bench of two IDENTICAL Riolu and one Munkidori — the shape
    that makes both collapses observable at once."""
    bench = bench if bench is not None else [_body(RIOLU, serial=2), _body(RIOLU, serial=3),
                                             _body(MUNKIDORI, serial=4)]
    me = _player(active=_body(MEGA_LUC, serial=1, energies=active_energies), bench=bench, hand=hand)
    return _model(_obs(me, **kw))


def test_a_retreat_expands_BOTH_of_its_deferred_dimensions():
    """The PRODUCT, not one leg. `docs/rulebook.txt` L142 puts **no type restriction** on the Retreat
    Cost discard, so WHICH Energy to shed is a real second choice beside WHICH body to promote."""
    space = bc.target_space(_board(), RETREAT, seat_index=0)
    assert len(space) == 6
    assert {d for d, _j in space} == {(0, 1), (0, 2)}          # {F,F} and {F,P}; (1,2) is {F,P} again
    assert {j for _d, j in space} == {0, 1, 2}


def test_identical_ENERGY_CARDS_are_one_choice_and_the_fingerprint_provably_cannot_say_so():
    """`option_fingerprint` compares card lists by VALUE INCLUDING ORDER, so two removals leaving the same
    multiset in different order differ — hence `candidate_class`; no canonical removal repairs it."""
    model = _board(active_energies=(E_F, E_F, E_F, E_F))
    space = bc.target_space(model, RETREAT, seat_index=0)
    assert {d for d, _j in space} == {(0, 1)}                   # C(4,2) = 6 index pairs, ONE choice
    for pair in ((0, 1), (0, 3), (2, 3)):
        assert bc.candidate_class(model, RETREAT, (pair, 0), seat_index=0) == ((E_F, E_F), 0)


@pytest.mark.parametrize("energies", [(), (E_F, E_F)])
def test_the_energy_leg_collapses_to_one_member_when_there_is_nothing_to_choose(energies):
    """STRUCTURAL, not a special case: ``C(n, n)`` and ``C(n, 0)`` are both 1, so it is a property of
    the enumeration rather than a branch that could drift from it."""
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
    """A refusal, NOT a zero-class Expectation: `expected()` raises on empty mass, which would surface
    inside the ordering loop rather than on the telemetry line where it can be acted on."""
    model = _board(bench=[])
    with pytest.raises(bd.Unmodellable, match="Bench is empty"):
        bc.target_space(model, RETREAT, seat_index=0)


def test_two_identical_benched_bodies_collapse_to_ONE_outcome_class():
    """ADR-0091: the branching factor is the number of decisions actually posed. `serial` is the only
    field the two Riolu differ on."""
    exp = bc.deferred_target(_board(), RETREAT)
    assert len(bc.target_space(_board(), RETREAT, seat_index=0)) == 6
    assert len(exp.classes) == 4
    assert len({c.fingerprint for c in exp.classes}) == 4


def test_the_class_identity_is_a_PAIR_because_the_active_alone_would_erase_a_whole_dimension():
    """A fingerprint over the new Active ALONE is identical for two candidates that promote the same
    body with different payments, so it would erase the Energy-discard dimension entirely."""
    model = _board()
    seat = 0
    first = bc.realise(model, RETREAT, ((0, 1), 0), seat_index=seat)[1]
    second = bc.realise(model, RETREAT, ((0, 2), 0), seat_index=seat)[1]
    assert first != second
    assert first[0] == second[0]                    # the promoted body — identical
    assert first[1] != second[1]                    # the retreating body's remaining Energy — not


def test_every_class_is_equally_probable_and_a_complete_enumeration_sums_to_one():
    """A uniform prior over decisions the PLAYER makes. The mean is not the value (`Expectation.expected`
    rules the max is), but `total_probability` must read 1.0 or truncation could not be detected."""
    exp = bc.deferred_target(_board(), RETREAT)
    assert exp.truncated == 0
    assert exp.total_probability == pytest.approx(1.0)
    assert [c.probability for c in exp.classes] == pytest.approx([1.0 / len(exp.classes)] * 4)


def test_truncation_past_the_cap_is_reported_TWICE_and_the_probability_gap_IS_the_truncation():
    """The probability denominator is the FULL enumeration: normalising over survivors would sum to 1.0
    while classes were dropped, and an under-explored line would read as confidently valued."""
    full = bc.deferred_target(_board(), RETREAT)
    capped = bc.deferred_target(_board(), RETREAT, cap=2)
    assert len(capped.classes) == 2
    assert capped.truncated == len(full.classes) - 2
    assert capped.total_probability == pytest.approx(2.0 / len(full.classes))


def test_the_cap_is_board_expectations_own_constant_and_never_a_second_one():
    """A choice node and a chance node cost the same thing — leaf evaluations on one option."""
    import inspect
    assert inspect.signature(bc.deferred_target).parameters["cap"].default is be.BRANCH_CAP


def test_a_cap_below_one_is_a_CALLER_error_and_raises_where_a_modelling_gap_refuses():
    """A caller asking for a zero-class Expectation is a bug in the CALLER, not a gap in the board —
    hence a raise where a modelling gap refuses (mirrors `board_expectation.expectation`)."""
    with pytest.raises(ValueError, match="at least one class"):
        bc.deferred_target(_board(), RETREAT, cap=0)


def test_the_node_never_mutates_the_model_it_was_given_MEMO_INCLUDED():
    """The memo is the sharp half: `state_value` caches under `("state_value",)` and NOTHING
    invalidates that key, so the scalar is read FIRST here to warm it before the node runs."""
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
    """The ordering must be a pure function of the board, or two processes truncate to different sets
    and the ADR-0072 gates stop being replayable."""
    first = bc.deferred_target(_board(), RETREAT, cap=2)
    second = bc.deferred_target(_board(), RETREAT, cap=2)
    assert [c.fingerprint for c in first.classes] == [c.fingerprint for c in second.classes]


def test_the_swap_keeps_the_retreating_bodys_damage_and_sheds_only_the_paid_energy():
    """`docs/rulebook.txt` L143 *"Keep all damage counters and all attached cards … when they switch"*
    against L142's *"discard 1 Energy … for each [C]"*. The Bench placement is a swap IN PLACE."""
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
    """`docs/rulebook.txt` L143. The flags live on `PlayerState`, not the body (`docs/rules.md` §8:
    only the Active can carry one), which is why clearing them is a side write with its own zone."""
    me = _player(active=_body(MUNKIDORI, serial=1, energies=(E_P,)),
                 bench=[_body(RIOLU, serial=2)], poisoned=True, confused=True)
    model = _model(_obs(me))
    after, writes = bc.CHOICE_REGISTRY[_RETREAT].apply(model, ((0,), 0), seat_index=0)
    side = after["current"]["players"][0]
    assert not any(side[f] for f in bd.CONDITION_FLAGS)
    assert "special_conditions" in writes
    assert model.source_obs["current"]["players"][0]["poisoned"] is True   # the pre-state is intact


def test_a_free_retreat_writes_no_energy_and_no_discard():
    """The write set is EXACT per case, which is what makes a FORGOTTEN write a failure too."""
    object.__setattr__(_STATS[MUNKIDORI], "retreatCost", 0)
    try:
        me = _player(active=_body(MUNKIDORI, serial=1, energies=(E_P,)),
                     bench=[_body(RIOLU, serial=2)])
        _after, writes = bc.CHOICE_REGISTRY[_RETREAT].apply(_model(_obs(me)), ((), 0), seat_index=0)
    finally:
        object.__setattr__(_STATS[MUNKIDORI], "retreatCost", 1)
    assert writes == {"allowance_retreat_used", "bodies_in_play"}


def test_the_node_refuses_off_the_MAIN_menu():
    """An option posed INSIDE a card's effect resolution is one leg of that CARD's step, and carries
    writes belonging to the card rather than to the option's kind."""
    me = _player(active=_body(MEGA_LUC, serial=1, energies=(E_F, E_F)),
                 bench=[_body(RIOLU, serial=2)])
    with pytest.raises(bd.Unmodellable, match="MAIN menu"):
        bc.deferred_target(_model(_obs(me, context=3)), RETREAT)


def test_an_option_with_no_deferred_target_is_not_a_choice_node():
    """An `_ATTACH` determines its own target, so it is a point transition."""
    model = _board()
    assert bc.has_deferred_target(model, RETREAT, seat_index=0) is True
    assert bc.has_deferred_target(model, {"type": 8, "index": 0}, seat_index=0) is False
    with pytest.raises(bd.Unmodellable, match="no deferred target"):
        bc.choice_key(model, {"type": 8, "index": 0}, seat_index=0)


def test_a_foreign_seat_refuses_because_the_rankers_price_MY_board():
    """The rankers read MY Bench and MY Active's build, so another seat would rank the wrong side."""
    with pytest.raises(bd.Unmodellable, match="not the model's own"):
        bc.deferred_target(_board(), RETREAT, seat_index=1)


def test_the_gust_target_space_resolves_their_bench_from_the_declared_clause():
    """The AREA is the clause KIND's — a gust reaches across the table, onto THEIR Bench — and the
    `target` selector narrows within it."""
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
    """ADR-0121 d2: expansion is data-driven off the compendium's target vocabulary, never per-card.
    Three destinations = three DIFFERENT refusals: a predicate, a category error, a scoped gap."""
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
    """An unknown narrowing read as NO narrowing is the one failure that silently widens a space."""
    with pytest.raises(bd.Unmodellable, match="declares"):
        bc.target_predicate({"kind": "gust", "target": "a_value_nobody_declared"})
    with pytest.raises(bd.Unmodellable, match="handled set"):
        bc.target_predicate({"kind": "gust", "target": "any", "unheard_of_key": 1})


def test_the_stage_predicates_read_the_CANONICAL_stage_field_not_a_second_reading():
    """The stage legs read `CardStat.stage`, the canonical field — never a second reading derived from
    `evolvesFrom`. Riolu is **Basic**, Mega Lucario ex **Stage 1** (a single hop, no Stage 2)."""
    place = bc._BodyPlace(active=False, mine=True)
    riolu, mega = _STATS[RIOLU], _STATS[MEGA_LUC]
    assert bc.BODY_PREDICATES["basic"](riolu, place) is True
    assert bc.BODY_PREDICATES["basic"](mega, place) is False
    assert bc.BODY_PREDICATES["evolution"](mega, place) is True
    assert bc.BODY_PREDICATES["stage1"](mega, place) is True
    assert bc.BODY_PREDICATES["stage2"](mega, place) is False
    assert bc.BODY_PREDICATES["mega"](mega, place) is True and \
        bc.BODY_PREDICATES["mega"](riolu, place) is False
    # FAIL-CLOSED on an unreadable stage: a widening default would hand a clause every body on board.
    # 999_999 is OUTSIDE the shipped pool, so this is not a source claim about any real card.
    stageless = CardStat(999_999, name="Unstaged Test Body", hp=80, energyType=FIGHTING)
    assert bc.BODY_PREDICATES["basic"](stageless, place) is False
    assert bc.BODY_PREDICATES["evolution"](stageless, place) is False
    # Place, not card: the same body is `benched` or not depending on where it sits.
    assert bc.BODY_PREDICATES["benched"](riolu, place) is True
    assert bc.BODY_PREDICATES["benched"](riolu, bc._BodyPlace(active=True, mine=True)) is False


def test_an_unreadable_body_matches_NO_class_rather_than_every_class():
    """A card the compendium never heard of resolves to `None`; treating that as "unconstrained" would
    widen a narrowed target space to the whole board."""
    match = bc.target_predicate({"kind": "gust", "target": "any"})
    assert match(_STATS[RIOLU], bc._BodyPlace(active=False, mine=False)) is True
    assert match(None, bc._BodyPlace(active=False, mine=False)) is False


def test_the_gust_entry_is_currently_UNREACHABLE_and_the_test_names_why():
    """`gust` has a target space and a Target Ranker and NO board synthesis, so `deferred_target`
    refuses it. **No issue currently owns landing it** — the gap is real and unfiled."""
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
    """`heal` is in `CHOICE_CLAUSES` with no target-space resolver; the refusal names the boundary."""
    me = _player(active=_body(MEGA_LUC, serial=1, energies=(E_F, E_F)), hand=(WALLY,),
                 bench=[_body(RIOLU, serial=2)])
    model = _model(_obs(me))
    with pytest.raises(bd.Unmodellable, match="no target SPACE resolver is built"):
        bc.target_space(model, {"type": _PLAY, "index": 0}, seat_index=0)


def test_the_declared_vocabulary_is_CLOSED_over_the_registries_that_consume_it():
    """A member misspelled into a registry would be dead code no refusal and no test could tell from
    an absent one. The `CLAUSE_WRITES` assertion is the positive control on the same walk."""
    declared = set(bc.CHOICE_KEYS)
    assert declared, "vacuity guard: an empty vocabulary would pass every assertion below"
    assert declared == set(bc.CHOICE_KINDS) | set(bc.CHOICE_CLAUSES) | {bc.FETCH_DISCARD}
    assert set(bc.CHOICE_REGISTRY) <= declared, sorted(set(bc.CHOICE_REGISTRY) - declared)
    assert set(bc.TARGET_RANKERS) <= set(bc.CHOICE_REGISTRY)
    assert set(bc.CHOICE_CLAUSES) <= set(sc.CLAUSE_WRITES)          # the positive control
    # `FETCH_DISCARD` is a ZONE-QUALIFIED family name, NOT a clause kind, and must never be added to
    # `CLAUSE_WRITES` — the clause kind is `fetch`, and only the ZONE says which node resolves it.
    assert bc.FETCH_DISCARD not in sc.CLAUSE_WRITES
    assert bc.FETCH_DISCARD not in bc.CHOICE_CLAUSES
    assert "fetch" in sc.REVEALING_CLAUSES and "fetch" not in bc.CHOICE_CLAUSES
    # ONE record per key, asserted here as well as in `ChoiceKind.__post_init__` so a half-filled
    # record fails a reading and not only a construction.
    for key, entry in bc.CHOICE_REGISTRY.items():
        assert entry.space is not None and entry.canonical is not None, key
        assert (entry.apply is None) == (entry.fingerprint is None), key
        assert entry.apply is not None or entry.no_applier.strip(), key


def test_the_seam_returns_the_POINT_transition_until_expansion_is_ARMED():
    """`runtime.PROFILE["deferred_target_expansion"]` ships False. Armed, the SHAPE changes and the
    fate does not — `apply_option` already declares an `Expectation` among its return shapes."""
    model = _board()
    off = ao.apply_option(model, RETREAT)
    assert isinstance(off, StateModel)
    assert off.retreated is True and off.mine.active.card_id == MEGA_LUC   # nothing else moved
    on = ao.apply_option(model, RETREAT, expand_deferred_targets=True)
    assert isinstance(on, ao.Expectation)
    assert len(on.classes) == 4
    assert ao.fate(RETREAT, deferred_target=True) == ao.MODELLED


def test_the_armed_seam_REFUSES_rather_than_falling_back_to_the_point_transition():
    """An option with no ESTIMATE must never be handed back as one with no VALUE: a 0 delta at
    ordering time means NEVER EXPLORED, not undervalued (Issue #263)."""
    model = _board(bench=[])
    result = ao.apply_option(model, RETREAT, expand_deferred_targets=True)
    assert ao.must_expand(result)
    assert "Bench is empty" in result.reason


def test_an_unexpanded_retreat_prices_at_EXACTLY_zero_and_expansion_gives_the_leaf_a_choice():
    """⚠️ Deliberately does NOT assert the expanded delta is POSITIVE — these `CardStat`s carry no attacks,
    so the leaf cannot discriminate; `tests/train/test_choice_beam.py` makes that claim instead."""
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
    """The composer takes the ARGMAX over an expanded family, so a cap dropping the best target changes
    the answer. Asserted against the RANKER: rankers prefilter, `state_value` decides (D3)."""
    model = _board()
    space = bc.target_space(model, RETREAT, seat_index=0)
    best = max(space, key=lambda c: (bc.rank_retreat(model, c), tuple(-x for x in (c[1],))))
    expected = bc.realise(model, RETREAT, best, seat_index=0)[1]
    capped = bc.deferred_target(model, RETREAT, cap=1)
    assert capped.truncated == len(bc.deferred_target(model, RETREAT).classes) - 1
    assert capped.classes[0].fingerprint == expected


# ── the VISIBLE-zone search: a discard fetch is a choice node (Issue #394) ────────────────────────
# A `discard`-zone search carries NO chance — that zone is visible — so it is a pure CHOICE node.


def _discard_board(hand, discard, *, deck=()):
    return _model(_obs(_player(active=_body(MEGA_LUC, serial=1), hand=hand, discard=discard)), deck)


def _delivered(exp, *, kept=0):
    """The card ids each outcome class put in my hand, as sorted tuples."""
    out = []
    for cls in exp.classes:
        hand = ((cls.model.source_obs.get("current") or {}).get("players") or [{}])[0].get("hand")
        out.append(tuple(sorted(c.get("id") for c in (hand or ())[kept:])))
    return sorted(out)


def test_a_discard_search_is_routed_to_the_CHOICE_node_not_the_chance_node():
    """The ZONE decides, not the clause kind: `fetch` is deliberately NOT a `CHOICE_CLAUSES` member
    because a DECK fetch is the chance node's."""
    model = _discard_board((NIGHT_STRETCHER,), (RIOLU, E_F))
    play = {"type": _PLAY, "index": 0}
    assert bc.choice_key(model, play, seat_index=0) == bc.FETCH_DISCARD
    assert bc.has_deferred_target(model, play, seat_index=0) is True
    # Positive control: a DECK search of the same clause kind refuses rather than going quiet.
    deck_model = _discard_board((MASTER_BALL,), (RIOLU,))
    with pytest.raises(bd.Unmodellable, match="no clause with a deferred target"):
        bc.choice_key(deck_model, play, seat_index=0)
    assert bc.has_deferred_target(deck_model, play, seat_index=0) is False


def test_a_discard_UNION_enumerates_one_card_over_both_legs():
    """One card from the UNION of two legs, and the source card lands in the discard as it resolves
    (`docs/rulebook.txt` L78)."""
    exp = bc.deferred_target(_discard_board((NIGHT_STRETCHER,), (RIOLU, E_F)),
                             {"type": _PLAY, "index": 0}, seat_index=0)
    assert _delivered(exp) == [(E_F,), (RIOLU,)]
    for cls in exp.classes:
        me = (cls.model.source_obs["current"]["players"])[0]
        assert NIGHT_STRETCHER in [c.get("id") for c in me["discard"]]     # spent, not vanished
        assert len(me["hand"]) == 1 and me["handCount"] == 1


def test_a_discard_search_takes_NO_deck_odds_because_the_zone_is_face_up():
    """The cards are THERE, so the probabilities are the uniform placeholder and no `deck_odds` runs."""
    exp = bc.deferred_target(_discard_board((NIGHT_STRETCHER,), (RIOLU, E_F)),
                             {"type": _PLAY, "index": 0}, seat_index=0)
    assert [c.probability for c in exp.classes] == [0.5, 0.5]
    assert exp.total_probability == pytest.approx(1.0)


def test_duplicate_copies_in_the_discard_are_ONE_class():
    """Enumerated over CARD IDS up front, so the class count is real choices not physical cards."""
    exp = bc.deferred_target(_discard_board((NIGHT_STRETCHER,), (RIOLU, RIOLU, RIOLU, E_F)),
                             {"type": _PLAY, "index": 0}, seat_index=0)
    assert _delivered(exp) == [(E_F,), (RIOLU,)]


def test_the_classes_are_invariant_to_DISCARD_ORDER():
    """A resolver keyed on physical indices would fail this."""
    play = {"type": _PLAY, "index": 0}
    a = bc.deferred_target(_discard_board((NIGHT_STRETCHER,), (RIOLU, E_F, MUNKIDORI)), play,
                           seat_index=0)
    b = bc.deferred_target(_discard_board((NIGHT_STRETCHER,), (MUNKIDORI, E_F, RIOLU)), play,
                           seat_index=0)
    assert _delivered(a) == _delivered(b)
    assert len(a.classes) == len(b.classes) == 3


def test_a_multi_card_discard_delivery_takes_the_cap_and_clamps_to_the_pile():
    """*"up to 2"*: the delivery CLAMPS to what the pile holds rather than being padded."""
    play = {"type": _PLAY, "index": 0}
    two = bc.deferred_target(_discard_board((ENERGY_RETRIEVAL,), (E_F, E_P, RIOLU)), play,
                             seat_index=0)
    assert _delivered(two) == [(E_P, E_F)]            # Riolu is not an Energy; the pair is the only class
    assert all(len(c.fingerprint) == 2 for c in two.classes)
    one = bc.deferred_target(_discard_board((ENERGY_RETRIEVAL,), (E_F, RIOLU)), play, seat_index=0)
    assert _delivered(one) == [(E_F,)]                # clamped to the single Energy in the pile


def test_an_empty_discard_refuses_rather_than_returning_a_zero_class_node():
    """A zero-class Expectation is one whose `expected()` raises inside the ordering loop."""
    # A pile holding only an Item: Night Stretcher reaches neither a Pokemon nor a Basic Energy.
    with pytest.raises(bd.Unmodellable, match="no legal instance"):
        bc.deferred_target(_discard_board((NIGHT_STRETCHER,), (MASTER_BALL,)),
                           {"type": _PLAY, "index": 0}, seat_index=0)
    # Positive control: the SAME board with one reachable card enumerates.
    ok = bc.deferred_target(_discard_board((NIGHT_STRETCHER,), (MASTER_BALL, MUNKIDORI)),
                            {"type": _PLAY, "index": 0}, seat_index=0)
    assert _delivered(ok) == [(MUNKIDORI,)]


def test_the_discard_rank_is_ORDERING_ONLY_and_never_a_magnitude():
    """The rank is `MySide.role_worth` and must stay a SORT KEY: it enters no score and adds to no
    delta, so changing it reorders classes but never changes what a surviving class is worth."""
    model = _discard_board((NIGHT_STRETCHER,), (RIOLU, E_F))
    play = {"type": _PLAY, "index": 0}
    space = bc.target_space(model, play, seat_index=0)
    ranked = sorted(space, key=lambda c: (-bc._rank_discard(model, c), c))
    exp = bc.deferred_target(model, play, seat_index=0)
    # The classes appear in rank order...
    assert _delivered(exp) == sorted(tuple(sorted(k)) for _i, k in ranked)
    # ...and every class still carries the same uniform probability, i.e. the rank priced nothing.
    assert len({c.probability for c in exp.classes}) == 1


def test_a_discard_fetch_carrying_an_UNHANDLED_key_fails_closed():
    """This node's applier writes a plain hand delivery, so a discard fetch that grew a `cost`, `dest`
    or `trigger` would be applied as though it had none. No shipped card carries one — hence synthetics."""
    from common.effects import CardEffects
    for extra in ({"cost": "discard_2"}, {"dest": "bench"}, {"trigger": "on_bench_play"}):
        clauses = {NIGHT_STRETCHER: [{"kind": "fetch", "target": "pokemon", "zone": "discard",
                                      **extra}]}
        obs = _obs(_player(active=_body(MEGA_LUC, serial=1), hand=(NIGHT_STRETCHER,),
                           discard=(RIOLU,)))
        model = StateModel.build(
            obs, deck=[],
            combat=CombatMath(DictCardStatProvider(_STATS), functions=CardFunctions({}),
                              transients=None, effects=CardEffects(clauses)))
        with pytest.raises(bd.Unmodellable, match="not in this node's handled set"):
            bc.choice_key(model, {"type": _PLAY, "index": 0}, seat_index=0)

    # Positive control: every SHIPPED discard fetch's keys are already inside the handled set.
    shipped = CardEffects.load()
    seen = 0
    for cid in (1097, 1109, 1110, 1118, 1184, 1238):
        legs = [c for c in shipped.clauses(cid)
                if c.get("kind") == "fetch" and c.get("zone") == "discard"]
        assert legs, cid
        for leg in legs:
            assert set(leg) <= bc._HANDLED_DISCARD_KEYS, (cid, sorted(set(leg) - bc._HANDLED_DISCARD_KEYS))
            seen += 1
    assert seen >= 9, f"the walk reached only {seen} shipped discard legs"
