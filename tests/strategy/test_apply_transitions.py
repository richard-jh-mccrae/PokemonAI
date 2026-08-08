"""The apply-seam TRANSITIONS (`common/board_delta.py` + `common/apply_option.py`, POC-T4/1,
Issue #382, under ADR-0098's frozen contract).

`test_apply_option.py` asserts the CONTRACT; this asserts what the seam DOES — each modelled kind's
board writes, the refusals that keep an unmodellable option from pricing at 0.0, the ENGINE-RESOLVED
path, and the purity the differencing composer rests on. The parity lane answers the other question
(*does the engine agree?*) over recorded traces; these units answer *is each write the one the rules
print?* on boards small enough that a failure names a RULE rather than a frame.

Card facts VERIFIED at source (`data/EN_Card_Data.csv`, `docs/rules.md`, `docs/rulebook.txt`), never
recalled. Dict-backed Stat Provider and hand-built zones: no Pilot, no engine boot, DLL-free.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from card_facts import ignition_tags                    # the committed Ignition Energy tags, ONE copy
from common import apply_option as ao
from common import board_delta as bd
from common import state_value as sv
from common.cards import CardFunctions
from common.effects import CardEffects
from common.option_equivalence import AREA_ACTIVE, AREA_BENCH, AREA_HAND
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.state_model import StateModel
from common.strategy.combat import CombatMath
from common.strategy.context import _ATTACH, _EVOLVE, _PLAY, _RETREAT

# AreaType numbers come from `option_equivalence`, the one module holding them DLL-free with a test
# pinning them to the engine enum.
COLORLESS, FIGHTING, PSYCHIC, DARKNESS, DRAGON = 0, 6, 5, 7, 9
HAND, ACTIVE, BENCH = AREA_HAND, AREA_ACTIVE, AREA_BENCH
MAIN = bd.CONTEXT_MAIN

RIOLU, MEGA_LUC, MUNKIDORI = 677, 678, 112
AURA_JAB, MEGA_BRAVE = 982, 983
E_F, IGNITION = 6, 17
# Two Stadiums with NO Effect Clauses and two with a WRITING clause, so a displacement can be
# tested both ways round.
CAPE, BOSS, GRAVITY_MOUNTAIN = 1159, 1182, 1252
BATTLE_CAGE, JAMMING_TOWER, RISKY_RUINS = 1264, 1246, 1260
# `applies_to: stage2` needs a real Stage 2 and the Stage 1 it evolves from.
DRAKLOAK, DRAGAPULT_EX = 120, 121
# A {D} Basic, for Risky Ruins' `unlessEnergyType` control — the case that must stay UNTAXED.
ZORUA = 136

#: Every row is a SOURCE claim, checked field-for-field against `data/EN_Card_Data.csv`. The
#: flat-HP Tool is ``synthetic`` because that audit cannot confirm a parsed `hpBonus`.
_STATS = {
    RIOLU: CardStat(RIOLU, name="Riolu", hp=80, energyType=FIGHTING, stage="basic"),
    MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, ex=True,
                       energyType=FIGHTING, evolvesFrom="Riolu", stage="stage1",
                       attacks=(AURA_JAB, MEGA_BRAVE),
                       minAttackCost=1, minCostDamage=130, maxDamage=270, maxDamageCost=2),
    MUNKIDORI: CardStat(MUNKIDORI, name="Munkidori", hp=110, energyType=PSYCHIC, stage="basic"),
    # `stage` is the canonical string and `stage2` the engine's separate `CardData.stage2` boolean;
    # both are declared, since `_is_basic` reads the former and `_admits_stage2` the latter.
    DRAKLOAK: CardStat(DRAKLOAK, name="Drakloak", hp=90, energyType=DRAGON, evolvesFrom="Dreepy",
                       stage="stage1"),
    DRAGAPULT_EX: CardStat(DRAGAPULT_EX, name="Dragapult ex", hp=320, energyType=DRAGON, ex=True,
                           evolvesFrom="Drakloak", stage2=True, stage="stage2"),
    ZORUA: CardStat(ZORUA, name="Zorua", hp=70, energyType=DARKNESS, stage="basic"),
    E_F: CardStat(E_F, name="Basic {F} Energy", cardType=5, energyType=FIGHTING),
    IGNITION: CardStat(IGNITION, name="Ignition Energy", cardType=6, energyType=COLORLESS),
    CAPE: CardStat(CAPE, synthetic=True, name="Flat-HP Tool", cardType=2, hpBonus=100),
    BOSS: CardStat(BOSS, name="Boss’s Orders", cardType=3),
    GRAVITY_MOUNTAIN: CardStat(GRAVITY_MOUNTAIN, name="Gravity Mountain", cardType=4),
    BATTLE_CAGE: CardStat(BATTLE_CAGE, name="Battle Cage", cardType=4),
    JAMMING_TOWER: CardStat(JAMMING_TOWER, name="Jamming Tower", cardType=4),
    RISKY_RUINS: CardStat(RISKY_RUINS, name="Risky Ruins", cardType=4),
}
_ATTACKS = {AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,)),
            MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2,
                                   energyTypes=(FIGHTING, FIGHTING))}
#: Ignition's two provisions, the pair `CardFunctions.energy_provision` reads (Issue #142).
_TAGS = {IGNITION: ignition_tags()}
#: The two Stadium clauses are `card_effects.json`'s own entries, key for key: dropping `applies_to`
#: would make the fixture answer a question the shipped compendium does not ask.
_CLAUSES = {
    BOSS: [{"kind": "gust"}],
    GRAVITY_MOUNTAIN: [{"kind": "stadium_static", "effect": "hp_delta", "amount": -30,
                        "applies_to": "stage2", "symmetric": True}],
    RISKY_RUINS: [{"kind": "stadium_trigger", "on": "bench_play", "effect": "damage_counters",
                   "amount": 2, "applies_to": "basic_non_dark", "symmetric": True}],
}


def _combat():
    return CombatMath(DictCardStatProvider(_STATS, attacks=_ATTACKS),
                      functions=CardFunctions(_TAGS), transients=None,
                      effects=CardEffects(_CLAUSES))


def _body(cid, *, hp=None, serial=1, energy=(), tools=(), pre=(), appeared=False, damage=0):
    """``energy`` is a sequence of ``(card id, units)`` pairs — `common/board_cards.py`'s split."""
    max_hp = _STATS[cid].hp
    return {"id": cid, "serial": serial, "playerIndex": 0,
            "hp": (max_hp if hp is None else hp) - damage, "maxHp": max_hp,
            "appearThisTurn": appeared,
            "energies": [u for _c, units in energy for u in units],
            "energyCards": [{"id": c, "serial": 900 + i, "playerIndex": 0}
                            for i, (c, _u) in enumerate(energy)],
            "tools": [{"id": t, "serial": 800 + i, "playerIndex": 0} for i, t in enumerate(tools)],
            "preEvolution": list(pre)}


def _player(*, active=None, bench=(), hand=(), discard=(), prize=4, deck_count=30, conditions=(),
            seat=0):
    return {"active": [active] if active else [], "bench": list(bench), "benchMax": 5,
            "hand": [{"id": c, "serial": 700 + i, "playerIndex": seat}
                     for i, c in enumerate(hand)],
            "handCount": len(hand),
            "discard": [{"id": c, "serial": 600 + i, "playerIndex": seat} for i, c in enumerate(discard)],
            "prize": [None] * prize, "deckCount": deck_count,
            **{f: (f in conditions) for f in bd.CONDITION_FLAGS}}


def _obs(me, opp=None, *, context=MAIN, stadium=(), **current):
    opp = opp if opp is not None else _player(active=_body(MUNKIDORI, serial=50), seat=1)
    state = {"players": [me, opp], "yourIndex": 0, "turn": 5,
             "energyAttached": False, "supporterPlayed": False, "retreated": False,
             "stadiumPlayed": False, "stadium": list(stadium)}
    state.update(current)
    return {"current": state, "logs": [], "select": {"context": context, "option": []}}


def _model(obs):
    return StateModel.build(obs, combat=_combat(), deck=[E_F] * 8)


def _apply(obs, option, **kw):
    return ao.apply_option(_model(obs), option, **kw)


# ── _ATTACH ───────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0002")
def test_attaching_an_energy_moves_the_card_adds_its_units_and_spends_the_allowance():
    """The CARD lands on `energyCards` while the UNITS it provides land on `energies`, and the
    allowance is spent so a second attach cannot be priced as if it were legal."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F]))
    after = _apply(obs, {"type": _ATTACH, "area": HAND, "index": 0,
                         "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after.mine.hand_ids == ()
    assert after.mine.active.energy_count == 1
    assert after.mine.active.attached_types == {FIGHTING: 1}
    assert after.energy_attached is True
    assert after.retreated is False and after.supporter_played is False


@pytest.mark.req("REQ-APPLY-0002")
def test_a_special_energy_attaches_the_UNITS_IT_PROVIDES_not_its_card_id():
    """Basic Energy card ids coincide with their `EnergyType` codes only up to the ninth card, so
    Ignition (17) providing {C} must render `energies` as `[0]` and never `[17]`."""
    obs = _obs(_player(active=_body(RIOLU), hand=[IGNITION]))
    after = _apply(obs, {"type": _ATTACH, "area": HAND, "index": 0,
                         "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after.mine.active.energy_key == (COLORLESS,)
    assert after.mine.active.energy_count == 1


@pytest.mark.req("REQ-APPLY-0002")
def test_attaching_a_TOOL_writes_the_tool_zone_its_HP_grant_and_NOT_the_energy_allowance():
    """A Tool arrives as ATTACH and is nothing like an Energy: it grants HP on BOTH current and
    maximum, and spends no allowance — `docs/rules.md` §3 caps only the manual ENERGY attachment."""
    obs = _obs(_player(active=_body(RIOLU, damage=20), hand=[CAPE]))
    after = _apply(obs, {"type": _ATTACH, "area": HAND, "index": 0,
                         "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after.mine.active.tool_ids == (CAPE,)
    assert after.mine.active.hp_remaining == 160          # 80 - 20 damage + 100
    assert after.mine.active.damage_counters == 2         # the damage RIDES, it is not healed
    assert after.mine.active.energy_count == 0
    assert after.energy_attached is False


@pytest.mark.req("REQ-APPLY-0002")
def test_a_tool_whose_holder_gate_fails_grants_nothing():
    """Read through `CardStat.applies_to_holder`, the ONE place a holder condition is evaluated. A
    fabricated gate, because what is under test is that the seam CONSULTS it."""
    stats = dict(_STATS)
    stats[CAPE] = CardStat(CAPE, synthetic=True, name="Flat-HP Tool", cardType=2,
                           hpBonus=100, holderNoRuleBox=True)
    combat = CombatMath(DictCardStatProvider(stats, attacks=_ATTACKS),
                        functions=CardFunctions(_TAGS), transients=None, effects=CardEffects({}))
    obs = _obs(_player(active=_body(MEGA_LUC), hand=[CAPE]))
    model = StateModel.build(obs, combat=combat, deck=[])
    after = ao.apply_option(model, {"type": _ATTACH, "area": HAND, "index": 0,
                                    "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after.mine.active.tool_ids == (CAPE,)
    assert after.mine.active.hp_remaining == 340          # Mega Lucario ex HAS a Rule Box


@pytest.mark.req("REQ-APPLY-0005")
def test_an_attach_naming_a_body_that_is_not_there_refuses_rather_than_raising():
    """An `IndexError` on the ordering hot path is a forfeited grader match over an option we merely
    could not resolve."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F]))
    r = _apply(obs, {"type": _ATTACH, "area": HAND, "index": 0,
                     "inPlayArea": BENCH, "inPlayIndex": 3})
    assert isinstance(r, ao.Refusal) and r.scope == ao.OPTION_SCOPE and ao.must_expand(r)


# ── _EVOLVE ───────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0002")
def test_evolving_keeps_the_attachments_and_the_damage_and_stacks_the_old_card_underneath():
    """Damage carries as a DELTA, not as an HP number: the new body has a different maximum. Riolu
    to Mega Lucario ex is a SINGLE hop in this set (`docs/rulebook.txt` Appendix 1)."""
    obs = _obs(_player(active=_body(RIOLU, damage=20, energy=[(E_F, (FIGHTING,))], tools=[CAPE]),
                       hand=[MEGA_LUC]))
    after = _apply(obs, {"type": _EVOLVE, "area": HAND, "index": 0,
                         "inPlayArea": ACTIVE, "inPlayIndex": 0})
    body = after.mine.active
    assert body.card_id == MEGA_LUC
    assert body.damage_counters == 2                      # the 20 rides across the evolution
    assert body.hp_remaining == 340 + 100 - 20            # …and the Cape's grant re-applies
    assert body.energy_key == (FIGHTING,) and body.tool_ids == (CAPE,)
    assert after.mine.hand_ids == ()
    assert after.mine.active_raw["preEvolution"] == [
        {"id": RIOLU, "serial": 1, "playerIndex": 0}]     # the CARD, stripped of the body's state


@pytest.mark.req("REQ-APPLY-0002")
def test_evolving_RE_EVALUATES_a_special_energys_provision_against_the_new_stage():
    """Ignition provides {C} on a Basic and {C}{C}{C} on an Evolution: the SAME attached card, a
    different rendering. Carrying the old list forward is the false-famine class."""
    obs = _obs(_player(active=_body(RIOLU, energy=[(IGNITION, (COLORLESS,))]), hand=[MEGA_LUC]))
    after = _apply(obs, {"type": _EVOLVE, "area": HAND, "index": 0,
                         "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after.mine.active.energy_count == 3
    assert after.mine.active.energy_key == (COLORLESS, COLORLESS, COLORLESS)


@pytest.mark.req("REQ-APPLY-0002")
def test_the_EVOLVED_body_is_itself_new_in_play_so_it_cannot_evolve_again_this_turn():
    """The body that ARRIVES by evolving is new in play too, so a Stage 1 played this turn cannot
    become a Stage 2 on the same turn. Measured on the engine before it was modelled."""
    obs = _obs(_player(active=_body(RIOLU), hand=[MEGA_LUC]))
    assert obs["current"]["players"][0]["active"][0].get("appearThisTurn") in (None, False)
    after = _apply(obs, {"type": _EVOLVE, "area": HAND, "index": 0,
                         "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after.mine.active.card_id == MEGA_LUC
    assert after.mine.active.new_in_play is True
    assert after.mine.active_raw["appearThisTurn"] is True


@pytest.mark.req("REQ-APPLY-0002")
def test_evolving_the_ACTIVE_clears_its_special_conditions():
    """`docs/rules.md` §4/§8: cleared when the Active LEAVES the spot or EVOLVES — and the rules text
    puts the leaving half first, so the evolve half is the one that gets missed."""
    obs = _obs(_player(active=_body(RIOLU), hand=[MEGA_LUC], conditions=("asleep", "confused")))
    after = _apply(obs, {"type": _EVOLVE, "area": HAND, "index": 0,
                         "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after.mine.conditions == frozenset()


# ── _RETREAT ──────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0002")
def test_a_retreat_OPTION_spends_the_allowance_and_moves_nothing_else():
    """A MEASUREMENT, not a simplification: the engine poses the cost and the promotion as SEPARATE
    selects, so modelling a swap here would diverge on the very next frame (`board_delta._retreat`)."""
    obs = _obs(_player(active=_body(RIOLU, energy=[(E_F, (FIGHTING,))]),
                       bench=[_body(MUNKIDORI, serial=2)]))
    after = _apply(obs, {"type": _RETREAT})
    assert after.retreated is True
    assert after.mine.active.card_id == RIOLU             # still Active — the swap is a later select
    assert after.mine.active.energy_count == 1            # the cost is a later select too
    assert after.mine.discard_ids == ()
    assert [b.card_id for b in after.mine.bench] == [MUNKIDORI]


@pytest.mark.req("REQ-APPLY-0009")
def test_the_retreat_option_carries_no_target_and_the_module_says_so_where_it_is_read():
    """A behavioural test would pass on a seam that merely IGNORED a target it was given, so this
    pins the corpus fact where a later reader meets it."""
    import inspect
    src = inspect.getsource(bd._retreat)
    assert "5807 of 5807" in src and "146 of 146" in src
    assert "Issue #385" in src


@pytest.mark.req("REQ-APPLY-0002")
def test_the_CHOICE_branch_changes_the_SHAPE_and_leaves_the_point_transition_exactly_as_it_was():
    """A NEGATIVE criterion: the two `_retreat` tests above must stay green, or the seam widened
    rather than being built beside. A choice node changes the SHAPE, not the verdict."""
    obs = _obs(_player(active=_body(RIOLU, energy=[(E_F, (FIGHTING,))]),
                       bench=[_body(MUNKIDORI, serial=2)]))
    plain = _apply(obs, {"type": _RETREAT})
    assert not isinstance(plain, ao.Expectation)
    assert plain.retreated is True and plain.mine.active.card_id == RIOLU

    expanded = _apply(obs, {"type": _RETREAT}, expand_deferred_targets=True)
    assert isinstance(expanded, ao.Expectation)
    assert [c.model.mine.active.card_id for c in expanded.classes] == [MUNKIDORI]
    assert expanded.total_probability == pytest.approx(1.0)
    assert ao.fate({"type": _RETREAT}) == ao.MODELLED
    assert ao.fate({"type": _RETREAT}, deferred_target=True) == ao.MODELLED


@pytest.mark.req("REQ-APPLY-0002")
def test_expansion_is_OPT_IN_at_the_seam_and_carries_no_deployment_flag():
    """Asserted where an implementer reading the retreat transition will meet it. The `PROFILE` flag
    is RETIRED (Issue #446): the composer opts in unconditionally, so a knob it never read misled."""
    import inspect

    from common.runtime import PROFILE
    assert "deferred_target_expansion" not in PROFILE
    assert inspect.signature(ao.apply_option).parameters[
        "expand_deferred_targets"].default is False


# ── _PLAY ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0002")
def test_playing_a_basic_benches_it_fresh_and_marks_it_as_new_in_play():
    """`appearThisTurn` is what makes the body unevolvable this turn. Asserted through the SNAPSHOT
    as well as the raw dict, so the two cannot drift into disagreeing about one body."""
    obs = _obs(_player(active=_body(RIOLU), hand=[MUNKIDORI]))
    after = _apply(obs, {"type": _PLAY, "index": 0})
    assert [b.card_id for b in after.mine.bench] == [MUNKIDORI]
    assert after.mine.bench[0].hp_remaining == 110
    assert after.mine.bench[0].new_in_play is True
    assert after.mine.bench_raws[0]["appearThisTurn"] is True
    assert after.mine.hand_ids == ()
    # The body it was benched BESIDE has been in play since before this turn and stays that way — a
    # deploy writes the bit on ONE body, which is what the zone means.
    assert after.mine.active.new_in_play is False


@pytest.mark.req("REQ-APPLY-0005")
def test_a_deploy_onto_a_FULL_bench_refuses_rather_than_inventing_a_sixth_slot():
    """An illegal play priced like a legal one is a phantom LINE, not a small error."""
    obs = _obs(_player(active=_body(RIOLU),
                       bench=[_body(MUNKIDORI, serial=i) for i in range(2, 7)],
                       hand=[MUNKIDORI]))
    r = _apply(obs, {"type": _PLAY, "index": 0})
    assert isinstance(r, ao.Refusal) and "Bench is full" in r.reason


@pytest.mark.req("REQ-APPLY-0005")
def test_playing_a_SUPPORTER_refuses_because_the_effect_IS_the_play():
    """Pricing the structural floor alone would difference the gust to ~0 — the silent zero Issue
    Issue #300's `_covers` verdict exists to refuse. The refusal NAMES the card, so the backlog is work."""
    obs = _obs(_player(active=_body(RIOLU), hand=[BOSS]))
    r = _apply(obs, {"type": _PLAY, "index": 0})
    assert isinstance(r, ao.Refusal) and r.scope == ao.OPTION_SCOPE
    assert "1182" in r.reason and "bodies_in_play" in r.reason
    assert ao.must_expand(r) is True


@pytest.mark.req("REQ-APPLY-0002")
def test_playing_a_stadium_swaps_the_one_in_play_and_discards_it_to_ITS_OWNER():
    """Each player has their OWN discard pile, which is why displacing theirs writes their discard.
    Jamming Tower has no Effect Clauses — a Stadium whose effect WRITES refuses, one test below."""
    theirs = _player(active=_body(MUNKIDORI, serial=50), seat=1)
    obs = _obs(_player(active=_body(RIOLU), hand=[BATTLE_CAGE]), theirs,
               stadium=[{"id": JAMMING_TOWER, "serial": 55, "playerIndex": 1}])
    after = _apply(obs, {"type": _PLAY, "index": 0})
    assert after.stadium_id == BATTLE_CAGE
    assert after.stadium_played is True
    assert after.theirs.discard_ids == (JAMMING_TOWER,)
    assert after.mine.discard_ids == ()


@pytest.mark.req("REQ-APPLY-0005")
def test_DISPLACING_a_stadium_whose_effect_writes_refuses_because_the_effect_ENDS():
    """A structural swap moving only the `stadium` zone leaves every body the Stadium modified at a
    stale maximum. No committed corpus step reaches this path, so the parity lane cannot see it."""
    obs = _obs(_player(active=_body(RIOLU), hand=[BATTLE_CAGE]),
               stadium=[{"id": GRAVITY_MOUNTAIN, "serial": 55, "playerIndex": 1}])
    r = _apply(obs, {"type": _PLAY, "index": 0})
    assert isinstance(r, ao.Refusal) and r.scope == ao.OPTION_SCOPE
    assert "1252" in r.reason and "DISPLACING" in r.reason


@pytest.mark.req("REQ-APPLY-0005")
def test_replaying_the_stadium_already_in_play_refuses_as_an_illegal_play():
    """`docs/rulebook.txt` L137, restated in `docs/rules.md` §3."""
    obs = _obs(_player(active=_body(RIOLU), hand=[BATTLE_CAGE]),
               stadium=[{"id": BATTLE_CAGE, "serial": 55, "playerIndex": 0}])
    r = _apply(obs, {"type": _PLAY, "index": 0})
    assert isinstance(r, ao.Refusal) and "already in play" in r.reason


# ── the board-level modifiers the option's own clauses cannot see ─────────────────────────────────


def _bench(after_obs, index=0):
    """Read RAW, because the assertions are about ``hp`` and ``maxHp`` together: a counter moves one,
    a floating Stadium delta moves both."""
    return after_obs["current"]["players"][0]["bench"][index]


def _active(after_obs):
    return after_obs["current"]["players"][0]["active"][0]


@pytest.mark.req("REQ-APPLY-0005")
def test_a_stadium_that_CANNOT_reach_the_transition_stops_gating_it():
    """`stadium_clauses_for` asks whether the clause reaches THIS event and THIS body: an evolution
    is not a bench play, and neither a Basic nor a Stage 1 is a Stage 2 (Issue #410 R2)."""
    ruins = [{"id": RISKY_RUINS, "serial": 55, "playerIndex": 1}]
    mountain = [{"id": GRAVITY_MOUNTAIN, "serial": 55, "playerIndex": 1}]

    # Risky Ruins + an evolution: `on: bench_play` cannot see a stage change, into either stage.
    for stadium in (ruins,):
        into_stage1 = _obs(_player(active=_body(RIOLU), hand=[MEGA_LUC]), stadium=stadium)
        after = _apply(into_stage1, {"type": _EVOLVE, "area": HAND, "index": 0,
                                     "inPlayArea": ACTIVE, "inPlayIndex": 0})
        assert after.mine.active.card_id == MEGA_LUC
        into_stage2 = _obs(_player(active=_body(DRAKLOAK), hand=[DRAGAPULT_EX]), stadium=stadium)
        after = _apply(into_stage2, {"type": _EVOLVE, "area": HAND, "index": 0,
                                     "inPlayArea": ACTIVE, "inPlayIndex": 0})
        assert after.mine.active.card_id == DRAGAPULT_EX
        assert after.mine.active.hp_remaining == 320          # untaxed: the trigger never fired

    # Gravity Mountain + a Stage 1 body, and + a Basic deploy: `applies_to: stage2` admits neither.
    into_stage1 = _obs(_player(active=_body(RIOLU), hand=[MEGA_LUC]), stadium=mountain)
    after = _apply(into_stage1, {"type": _EVOLVE, "area": HAND, "index": 0,
                                 "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after.mine.active.card_id == MEGA_LUC
    assert after.mine.active.hp_remaining == 340              # the printed maximum, undelta'd

    deploy = _obs(_player(active=_body(RIOLU), hand=[MUNKIDORI]), stadium=mountain)
    delta = bd.transition(deploy, {"type": _PLAY, "index": 0}, seat_index=0, combat=_combat(),
                          context=MAIN)
    assert _bench(delta.obs) == {"id": MUNKIDORI, "serial": 700, "playerIndex": 0,
                                 "hp": 110, "maxHp": 110, "appearThisTurn": True,
                                 "energies": [], "energyCards": [], "tools": [], "preEvolution": []}
    assert delta.writes == frozenset({"my_hand_ids", "bodies_in_play", "bench_occupancy",
                                      "new_in_play"})


@pytest.mark.req("REQ-APPLY-0005")
def test_RISKY_RUINS_taxes_a_benched_basic_and_spares_a_DARK_one():
    """``hp`` moves and ``maxHp`` does NOT — the sharp difference from a Tool grant, which moves both.
    Two of the three boards are controls: no Stadium, and a {D} Basic under Risky Ruins itself."""
    ruins = [{"id": RISKY_RUINS, "serial": 55, "playerIndex": 1}]

    taxed = bd.transition(_obs(_player(active=_body(RIOLU), hand=[MUNKIDORI]), stadium=ruins),
                          {"type": _PLAY, "index": 0}, seat_index=0, combat=_combat(), context=MAIN)
    assert (_bench(taxed.obs)["hp"], _bench(taxed.obs)["maxHp"]) == (90, 110)
    assert "damage_counters" in taxed.writes

    clear = bd.transition(_obs(_player(active=_body(RIOLU), hand=[MUNKIDORI])),
                          {"type": _PLAY, "index": 0}, seat_index=0, combat=_combat(), context=MAIN)
    assert (_bench(clear.obs)["hp"], _bench(clear.obs)["maxHp"]) == (110, 110)
    assert "damage_counters" not in clear.writes

    dark = bd.transition(_obs(_player(active=_body(RIOLU), hand=[ZORUA]), stadium=ruins),
                         {"type": _PLAY, "index": 0}, seat_index=0, combat=_combat(), context=MAIN)
    assert (_bench(dark.obs)["hp"], _bench(dark.obs)["maxHp"]) == (70, 70)
    assert "damage_counters" not in dark.writes


@pytest.mark.req("REQ-APPLY-0005")
def test_GRAVITY_MOUNTAIN_lowers_a_STAGE_2_body_and_composes_AFTER_the_tool_sum():
    """The order is the ENGINE's: a Tool's grant is STORED in `max_hp`, the Stadium delta FLOATS on
    top at render. The Stage-1 control is where a mis-scoped delta shows."""
    mountain = [{"id": GRAVITY_MOUNTAIN, "serial": 55, "playerIndex": 1}]

    into_stage2 = bd.transition(
        _obs(_player(active=_body(DRAKLOAK), hand=[DRAGAPULT_EX]), stadium=mountain),
        {"type": _EVOLVE, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0},
        seat_index=0, combat=_combat(), context=MAIN)
    assert (_active(into_stage2.obs)["hp"], _active(into_stage2.obs)["maxHp"]) == (290, 290)
    assert "damage_counters" in into_stage2.writes

    into_stage1 = bd.transition(
        _obs(_player(active=_body(RIOLU), hand=[MEGA_LUC]), stadium=mountain),
        {"type": _EVOLVE, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0},
        seat_index=0, combat=_combat(), context=MAIN)
    assert (_active(into_stage1.obs)["hp"], _active(into_stage1.obs)["maxHp"]) == (340, 340)
    assert "damage_counters" not in into_stage1.writes

    with_tool = bd.transition(
        _obs(_player(active=_body(DRAKLOAK, tools=(CAPE,)), hand=[DRAGAPULT_EX]), stadium=mountain),
        {"type": _EVOLVE, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0},
        seat_index=0, combat=_combat(), context=MAIN)
    assert (_active(with_tool.obs)["hp"], _active(with_tool.obs)["maxHp"]) == (390, 390)


@pytest.mark.req("REQ-APPLY-0005")
def test_the_stadium_delta_carries_DAMAGE_ALREADY_TAKEN_across_the_evolution():
    """The carry is a DELTA (``taken = maxHp - hp``) precisely so a floating modifier cancels: both
    shift together, so ``taken`` is the same number with or without the Stadium."""
    mountain = [{"id": GRAVITY_MOUNTAIN, "serial": 55, "playerIndex": 1}]
    after = bd.transition(
        _obs(_player(active=_body(DRAKLOAK, damage=40), hand=[DRAGAPULT_EX]), stadium=mountain),
        {"type": _EVOLVE, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0},
        seat_index=0, combat=_combat(), context=MAIN)
    assert (_active(after.obs)["hp"], _active(after.obs)["maxHp"]) == (250, 290)


@pytest.mark.req("REQ-APPLY-0005")
def test_an_UNRECOGNISED_stadium_vocabulary_value_makes_the_caller_REFUSE():
    """`applies_to` and `on` are `snapshot_coverage` PARAMETERS, not `VOCABULARY_KEYS`, so
    `undeclared_clauses` never walks their values and drift there is invisible to the audit."""
    drifted = {
        "unknown applies_to": ({"kind": "stadium_trigger", "on": "bench_play",
                                "effect": "damage_counters", "amount": 2,
                                "applies_to": "a_body_class_nobody_declared"}, "Stadium clause"),
        "unknown on": ({"kind": "stadium_trigger", "on": "an_event_nobody_declared",
                        "effect": "damage_counters", "amount": 2,
                        "applies_to": "basic_non_dark"}, "Stadium clause"),
        "a declared kind that is not a Stadium's": ({"kind": "gust"}, "Stadium clause"),
        "an UNDECLARED kind": ({"kind": "stadium_something_new", "effect": "damage_counters",
                                "amount": 2, "applies_to": "basic_non_dark"},
                               "vocabulary moved underneath the seam"),
    }
    for name, (clause, expected) in drifted.items():
        combat = CombatMath(DictCardStatProvider(_STATS, attacks=_ATTACKS),
                            functions=CardFunctions(_TAGS),
                            transients=None, effects=CardEffects({**_CLAUSES,
                                                                  RISKY_RUINS: [clause]}))
        obs = _obs(_player(active=_body(RIOLU), hand=[MUNKIDORI]),
                   stadium=[{"id": RISKY_RUINS, "serial": 55, "playerIndex": 1}])
        r = ao.apply_option(StateModel.build(obs, combat=combat, deck=[E_F] * 8),
                            {"type": _PLAY, "index": 0})
        assert isinstance(r, ao.Refusal), name
        assert expected in r.reason, (name, r.reason)


@pytest.mark.req("REQ-APPLY-0005")
def test_stadium_clauses_for_narrows_by_EVENT_and_BODY_and_widens_for_a_DISPLACEMENT():
    """``displace`` is the WIDENING answer: ending a Stadium re-renders every body it was modifying
    on BOTH sides, so there is no per-body question to narrow to and the caller refuses."""
    combat = _combat()
    ruins = {"stadium": [{"id": RISKY_RUINS, "serial": 55, "playerIndex": 1}]}
    mountain = {"stadium": [{"id": GRAVITY_MOUNTAIN, "serial": 55, "playerIndex": 1}]}
    quiet = {"stadium": [{"id": BATTLE_CAGE, "serial": 55, "playerIndex": 1}]}
    basic, stage1, stage2 = _STATS[MUNKIDORI], _STATS[MEGA_LUC], _STATS[DRAGAPULT_EX]

    reaches = bd.stadium_clauses_for(ruins, combat, event="bench_play", stat=basic)
    assert len(reaches) == 1 and reaches[0]["effect"] == "damage_counters"
    assert bd.stadium_clauses_for(ruins, combat, event="bench_play", stat=_STATS[ZORUA]) == ()
    assert bd.stadium_clauses_for(ruins, combat, event="stage_change",
                                  stat=(stage1, stage2)) == ()
    assert bd.stadium_clauses_for(mountain, combat, event="bench_play", stat=basic) == ()
    assert bd.stadium_clauses_for(mountain, combat, event="stage_change",
                                  stat=(basic, stage1)) == ()
    assert len(bd.stadium_clauses_for(mountain, combat, event="stage_change",
                                      stat=(stage1, stage2))) == 1

    # `damage_reduction` / `damage_boost` / `prevent_damage` are read off the `stadium` zone when
    # `CombatMath` prices an attack and stored nowhere, so they gate nothing and never did.
    assert bd.stadium_clauses_for(quiet, combat, event="displace") == ()
    assert bd.stadium_clauses_for({}, combat, event="displace") == ()
    assert len(bd.stadium_clauses_for(mountain, combat, event="displace")) == 1
    assert len(bd.stadium_clauses_for(ruins, combat, event="displace")) == 1


@pytest.mark.req("REQ-APPLY-0005")
def test_an_option_posed_inside_a_cards_effect_refuses_because_the_card_writes_too():
    """Answering an option posed inside a card's resolution also performs writes belonging to the
    CARD, not to the option's kind — so the seam refuses the leg."""
    obs = _obs(_player(active=_body(RIOLU), hand=[MEGA_LUC]), context=37)
    r = _apply(obs, {"type": _EVOLVE, "area": HAND, "index": 0,
                     "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert isinstance(r, ao.Refusal) and "MAIN menu" in r.reason


# ── purity: the property the whole differencing scheme rests on ──────────────────────────────────


@pytest.mark.req("REQ-APPLY-0007")
def test_a_transition_never_mutates_the_model_it_was_given_MEMO_INCLUDED():
    """The MEMO is the sharp half: nothing invalidates `("state_value",)`, so a mutated model keeps
    returning the pre-state's scalar in silence. The scalar is read first to warm it."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F, E_F]))
    model = _model(obs)
    before = sv.state_value(model)
    ao.apply_option(model, {"type": _ATTACH, "area": HAND, "index": 0,
                            "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert model.mine.hand_ids == (E_F, E_F)
    assert model.mine.active.energy_count == 0
    assert model.energy_attached is False
    assert sv.state_value(model) == before


@pytest.mark.req("REQ-APPLY-0007")
def test_the_same_transition_scores_the_same_twice_and_the_pre_state_is_unchanged_between():
    """A wobbly scorer makes the deterministic tie-break and both replay gates meaningless."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F]))
    model = _model(obs)
    option = {"type": _ATTACH, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0}
    first = sv.state_value(ao.apply_option(model, option))
    middle = sv.state_value(model)
    second = sv.state_value(ao.apply_option(model, option))
    assert first == second
    assert sv.state_value(model) == middle


@pytest.mark.req("REQ-APPLY-0007")
def test_the_post_state_shares_the_opponent_half_when_the_transition_never_crossed_the_table():
    """Their expensive clock derivations survive a hypothetical that never touched them — but sharing
    is never ASSUMED: a Stadium play writes a zone their side reads, so it rebuilds."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F, BATTLE_CAGE]))
    model = _model(obs)
    quiet = ao.apply_option(model, {"type": _ATTACH, "area": HAND, "index": 0,
                                    "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert quiet.theirs is model.theirs
    loud = ao.apply_option(model, {"type": _PLAY, "index": 1})
    assert loud.theirs is not model.theirs


@pytest.mark.req("REQ-APPLY-0007")
def test_the_post_state_is_a_FRESH_model_with_its_own_memo():
    """A fresh model owns a fresh memo, which makes the `("state_value",)` staleness hazard
    impossible by construction rather than by discipline."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F]))
    model = _model(obs)
    sv.state_value(model)
    after = ao.apply_option(model, {"type": _ATTACH, "area": HAND, "index": 0,
                                    "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after is not model and after.mine is not model.mine
    assert "state_value" not in after._memo


# ── the declared write-sets ───────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0009")
def test_every_transition_writes_exactly_its_declared_set():
    """EXACT, not `⊆`: a subset catches an EXTRA write and lets a FORGOTTEN one through, and a delta
    that under-reports prunes a real option. Not equality against the per-KIND FOOTPRINT."""
    combat = _combat()
    cases = [
        ("energy attach", _ATTACH, _obs(_player(active=_body(RIOLU), hand=[E_F])),
         {"type": _ATTACH, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0},
         {"my_hand_ids", "attached_energy", "allowance_energy_attached"}),
        ("HP-granting Tool attach", _ATTACH, _obs(_player(active=_body(RIOLU), hand=[CAPE])),
         {"type": _ATTACH, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0},
         {"my_hand_ids", "attached_tools", "damage_counters"}),
        # `new_in_play` on BOTH evolve cases and unconditionally: the evolved body arrives with
        # `appearThisTurn: True` and the body it replaced necessarily had it False.
        ("evolve the Active under a condition", _EVOLVE,
         _obs(_player(active=_body(RIOLU), hand=[MEGA_LUC], conditions=("asleep",))),
         {"type": _EVOLVE, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0},
         {"my_hand_ids", "bodies_in_play", "special_conditions", "new_in_play"}),
        ("evolve a benched body (no condition to clear)", _EVOLVE,
         _obs(_player(active=_body(MUNKIDORI, serial=9), bench=[_body(RIOLU)], hand=[MEGA_LUC])),
         {"type": _EVOLVE, "area": HAND, "index": 0, "inPlayArea": BENCH, "inPlayIndex": 0},
         {"my_hand_ids", "bodies_in_play", "new_in_play"}),
        # `damage_counters` ONLY under Gravity Mountain: the static `hp_delta` moves the new
        # body's maximum, and `damage_counters` is the zone homing the HP read.
        ("evolve into a Stage 2 under Gravity Mountain", _EVOLVE,
         _obs(_player(active=_body(DRAKLOAK), hand=[DRAGAPULT_EX]),
              stadium=[{"id": GRAVITY_MOUNTAIN, "serial": 55, "playerIndex": 1}]),
         {"type": _EVOLVE, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0},
         {"my_hand_ids", "bodies_in_play", "new_in_play", "damage_counters"}),
        ("retreat", _RETREAT,
         _obs(_player(active=_body(RIOLU), bench=[_body(MUNKIDORI, serial=2)])),
         {"type": _RETREAT}, {"allowance_retreat_used"}),
    ]
    for name, kind, obs, option, expected in cases:
        delta = bd.transition(obs, option, seat_index=0, combat=combat, context=MAIN)
        assert delta.writes == frozenset(expected), (name, sorted(delta.writes))
        declared = ao.footprint(kind)
        assert declared.complete, name
        assert delta.writes <= declared.writes, (name, sorted(delta.writes - declared.writes))


@pytest.mark.req("REQ-APPLY-0009")
def test_the_PLAY_footprint_is_a_FLOOR_and_the_real_writes_stay_inside_it():
    """`_PLAY` is INCOMPLETE on purpose, but the structural zones it names are a FLOOR."""
    combat = _combat()
    floor = ao.footprint(_PLAY)
    assert floor.complete is False
    deploy = bd.transition(_obs(_player(active=_body(RIOLU), hand=[MUNKIDORI])),
                           {"type": _PLAY, "index": 0}, seat_index=0, combat=combat, context=MAIN)
    assert deploy.writes == frozenset({"my_hand_ids", "bodies_in_play", "bench_occupancy",
                                       "new_in_play"})
    assert deploy.writes <= floor.writes
    # The same deploy under Risky Ruins gains `damage_counters` and NOTHING else. Pinned EXACTLY
    # beside the un-taxed case, so a FORGOTTEN write fails and not only an extra one.
    taxed = bd.transition(
        _obs(_player(active=_body(RIOLU), hand=[MUNKIDORI]),
             stadium=[{"id": RISKY_RUINS, "serial": 55, "playerIndex": 1}]),
        {"type": _PLAY, "index": 0}, seat_index=0, combat=combat, context=MAIN)
    assert taxed.writes == frozenset({"my_hand_ids", "bodies_in_play", "bench_occupancy",
                                      "new_in_play", "damage_counters"})
    assert taxed.writes <= floor.writes
    stadium = bd.transition(
        _obs(_player(active=_body(RIOLU), hand=[BATTLE_CAGE]),
             stadium=[{"id": JAMMING_TOWER, "serial": 55, "playerIndex": 1}]),
        {"type": _PLAY, "index": 0}, seat_index=0, combat=combat, context=MAIN)
    assert stadium.writes == frozenset({"my_hand_ids", "stadium", "allowance_stadium_played",
                                        "their_discard_contents"})
    assert stadium.writes <= floor.writes


# ── the ENGINE-RESOLVED execution path ────────────────────────────────────────────────────────────


class _FakeSearchApi:
    """A fake rather than the native engine deliberately: no committed board carries
    `search_begin_input`, and what is under test is the seam's WIRING, not the engine's arithmetic."""

    def __init__(self, after: dict):
        self.after, self.calls, self.ended = after, [], 0

    def to_observation_class(self, obs):
        return ("obs", obs)

    def search_begin(self, ob, yd, yp, od, op, oh, extra, manual_coin=False):
        self.calls.append(("begin", ob, manual_coin))
        return type("S", (), {"searchId": 7})()

    def search_step(self, search_id, choice):
        self.calls.append(("step", search_id, tuple(choice)))
        obs = _EngineObservation(current=self.after["current"], logs=self.after.get("logs") or [],
                                 select=self.after.get("select"))
        return type("S", (), {"observation": obs})()

    def search_end(self):
        self.ended += 1


@dataclass
class _EngineObservation:
    """A real dataclass: the seam reads the answer back through `asdict`."""
    current: dict
    logs: list
    select: dict | None = None


@pytest.mark.req("REQ-APPLY-0008")
def test_an_engine_resolved_option_executes_through_the_seam_and_returns_a_WRAPPER():
    """Open only at depth 0 with PROVED determinism and a live seam, and returning a wrapper so the
    telemetry cannot be forgotten."""
    obs = _obs(_player(active=_body(RIOLU), hand=[BOSS]))
    option = {"type": _PLAY, "index": 0}
    obs["select"]["option"] = [option]
    obs["search_begin_input"] = {"opaque": True}
    after = _obs(_player(active=_body(RIOLU), hand=[]))
    api = _FakeSearchApi(after)
    result = ao.apply_option(_model(obs), option, clauses_cover=False,
                             deterministic=True, search_api=api)
    assert isinstance(result, ao.EngineResolved)
    assert result.kind == _PLAY
    assert result.clause_gap.startswith(f"{BOSS} {_STATS[BOSS].name}")
    assert ao.require_model(result).mine.hand_ids == ()
    assert api.ended == 1                                 # one search, always closed
    assert ("step", 7, (0,)) in api.calls                 # answered by INDEX, off this menu


@pytest.mark.req("REQ-APPLY-0008")
def test_the_engine_route_refuses_at_depth_1_because_the_board_is_synthesized():
    """The routing is pinned in `test_apply_option.py`; this is the EXECUTION case, so the engine
    must not be reached at all."""
    obs = _obs(_player(active=_body(RIOLU), hand=[BOSS]))
    option = {"type": _PLAY, "index": 0}
    obs["select"]["option"] = [option]
    obs["search_begin_input"] = {"opaque": True}
    api = _FakeSearchApi(_obs(_player(active=_body(RIOLU), hand=[])))
    r = ao.apply_option(_model(obs), option, clauses_cover=False, deterministic=True,
                        search_api=api, depth=1)
    assert isinstance(r, ao.Refusal) and r.scope == ao.DEPTH_SCOPE
    assert api.calls == [] and api.ended == 0


@pytest.mark.req("REQ-APPLY-0008")
def test_an_option_that_is_not_on_the_menu_refuses_rather_than_guessing_an_index():
    """The engine answers a select by INDEX, so a wrong one prices a DIFFERENT legal play as this."""
    obs = _obs(_player(active=_body(RIOLU), hand=[BOSS]))
    obs["select"]["option"] = [{"type": _PLAY, "index": 4}]
    obs["search_begin_input"] = {"opaque": True}
    api = _FakeSearchApi(_obs(_player(active=_body(RIOLU), hand=[])))
    r = ao.apply_option(_model(obs), {"type": _PLAY, "index": 0}, clauses_cover=False,
                        deterministic=True, search_api=api)
    assert isinstance(r, ao.Refusal) and r.scope == ao.NO_ENGINE_SCOPE


@pytest.mark.req("REQ-APPLY-0008")
def test_an_engine_that_raises_refuses_instead_of_forfeiting_the_match():
    """An exception escaping the ordering path costs the MATCH; a refusal costs one estimate."""
    obs = _obs(_player(active=_body(RIOLU), hand=[BOSS]))
    option = {"type": _PLAY, "index": 0}
    obs["select"]["option"] = [option]
    obs["search_begin_input"] = {"opaque": True}

    class _Boom(_FakeSearchApi):
        def search_step(self, search_id, choice):
            raise RuntimeError("engine said no")

    api = _Boom(None)
    r = ao.apply_option(_model(obs), option, clauses_cover=False, deterministic=True, search_api=api)
    assert isinstance(r, ao.Refusal)
    assert api.ended == 1                                 # ...and the search is still closed


# ── the quarantine wiring ─────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0004")
def test_a_quarantined_kind_refuses_instead_of_transitioning(monkeypatch):
    """A kind the parity lane found diverging must refuse rather than hand back a board it gets
    wrong: the agent degrades VISIBLY instead of silently mis-playing (ADR-0098 decision 4)."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F]))
    option = {"type": _ATTACH, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0}
    assert ao.apply_option(_model(obs), option).mine.active.energy_count == 1
    monkeypatch.setattr(ao, "quarantined_kinds", lambda: frozenset({_ATTACH}))
    r = ao.apply_option(_model(obs), option)
    assert isinstance(r, ao.Refusal) and r.scope == ao.QUARANTINE_SCOPE


@pytest.mark.req("REQ-APPLY-0004")
def test_the_quarantine_registry_is_a_RULING_RECORD_and_is_empty_by_MEASUREMENT():
    """Empty by MEASUREMENT, not because nobody looked: an entry lands only with the divergence
    filed, exactly as a gate baseline is only re-captured on a developer verdict."""
    assert ao.QUARANTINED_KINDS == frozenset()
    assert ao.quarantined_kinds() == ao.QUARANTINED_KINDS
