"""The apply-seam **transitions** (`common/board_delta.py` + `common/apply_option.py`, POC-T4/1,
Issue #382, under ADR-0098's frozen contract).

`test_apply_option.py` asserts the CONTRACT — which fates exist, which kind resolves to which, what
a refusal is. This file asserts what the seam now DOES: the four modelled kinds' board writes, the
refusals that keep an unmodellable option from pricing at 0.0, the ENGINE-RESOLVED execution path,
and the purity the differencing composer's whole correctness rests on.

The parity lane (`tests/parity/test_apply_seam_parity.py`) is the other half and answers a different
question: *"does the engine agree?"* over 377 recorded native traces. These units answer *"is each
write the one the rules print?"* on boards small enough to read, so a failure names a rule rather
than a frame.

Card facts VERIFIED at source (`data/EN_Card_Data.csv`, `docs/rules.md`, `docs/rulebook.txt`) — never
recalled. Same primary seam as `test_state_model.py`: a dict-backed Stat Provider and hand-built zone
dicts, no Pilot and no engine boot, so this runs DLL-free on both platforms.

  * **Riolu (677) Basic HP 80 → Mega Lucario ex (678) HP 340**, a SINGLE hop — the standing worked
    example that this set's evolution lines are not the mainline TCG's (`docs/rulebook.txt`
    Appendix 1: *"Mega Lucario ex doesn't evolve from Lucario or Lucario ex—just Riolu"*).
  * **Hero's Cape (1159), Pokémon Tool** — *"The Pokémon this card is attached to gets +100 HP."*
  * **Ignition Energy (17)** — *"provides {C} Energy… If this card is attached to an Evolution
    Pokémon, it provides {C}{C}{C} Energy instead"*, hence `provides:1` / `provides_evo:3`.
  * **Gravity Mountain (1252), Stadium** — *"Each Stage 2 Pokémon in play (both yours and your
    opponent's) gets -30 HP."*
  * **Boss's Orders (1182), Supporter** — *"Switch in 1 of your opponent's Benched Pokémon to the
    Active Spot."*
  * `docs/rules.md` §3 — one Energy attachment, one Supporter, one Stadium *"(and only if it differs
    from the one in play)"* and one manual Retreat per turn.
  * `docs/rules.md` §4 — *"Evolving keeps attached cards + damage counters; **clears** Special
    Conditions and attack effects."*
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

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

# EnergyType codes (cg.api.EnergyType). The AreaType numbers come from `option_equivalence`, the
# one module that holds them DLL-free with a test pinning them to the engine enum — a fourth spelling
# in this file would be a fourth thing to keep true.
COLORLESS, FIGHTING, PSYCHIC, DARKNESS, DRAGON = 0, 6, 5, 7, 9
HAND, ACTIVE, BENCH = AREA_HAND, AREA_ACTIVE, AREA_BENCH
MAIN = bd.CONTEXT_MAIN

RIOLU, MEGA_LUC, MUNKIDORI = 677, 678, 112
AURA_JAB, MEGA_BRAVE = 982, 983
E_F, IGNITION = 6, 17
# Two Stadiums with NO Effect Clauses (`card_effects.json` returns [] for both) and two with a
# WRITING clause — so a displacement can be tested both ways round, and Issue #410's two appliers
# each have their card.
CAPE, BOSS, GRAVITY_MOUNTAIN = 1159, 1182, 1252
BATTLE_CAGE, JAMMING_TOWER, RISKY_RUINS = 1264, 1246, 1260
# The Dragapult line, for the Stage-2 half of Issue #410: `applies_to: stage2` needs a real Stage 2
# and the Stage 1 it evolves from, and `_EVOLVE` needs the body already in play.
DRAKLOAK, DRAGAPULT_EX = 120, 121
# A {D} Basic, for Risky Ruins' `unlessEnergyType` control — the case that must stay UNTAXED.
ZORUA = 136

#: Every row is a SOURCE claim, checked field-for-field against `data/EN_Card_Data.csv` by
#: `tests/scouting/test_cardstat_fixture_facts.py`. Munkidori is HP **110** and Mega Lucario ex's
#: biggest attack is Mega Brave at **270** for {F}{F}; both were wrong in this file's first draft and
#: that audit caught them, which is the standing rule working (`CLAUDE.md`: verify at source, never
#: from memory).
#:
#: The flat-HP Tool is ``synthetic``, under a NON-POOL name, for the reason every other Hero's Cape
#: fixture in the tree is synthetic (`test_attach_decider`, `test_discard_keep_rows`,
#: `test_tool_holder_facts`): the audit re-derives `hpBonus` by parsing the CSV through a shim card
#: and gets 0, so a declared 100 is not a claim it can confirm — even though *"+100 HP"* is Hero's
#: Cape's printed text. The row therefore stands in for the MECHANISM (a Tool with a flat HP grant)
#: rather than claiming to BE that card, and the real +100 is verified where it counts: against the
#: recorded engine on `ms_mirror_1000` f13, by the parity lane.
_STATS = {
    RIOLU: CardStat(RIOLU, name="Riolu", hp=80, energyType=FIGHTING),
    MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, ex=True,
                       energyType=FIGHTING, evolvesFrom="Riolu", attacks=(AURA_JAB, MEGA_BRAVE),
                       minAttackCost=1, minCostDamage=130, maxDamage=270, maxDamageCost=2),
    MUNKIDORI: CardStat(MUNKIDORI, name="Munkidori", hp=110, energyType=PSYCHIC),
    # The Dragapult line, read at source: Dreepy (Basic) → Drakloak (Stage 1, 90 HP) → Dragapult ex
    # (Stage 2, **320 HP**). `stage2` is the engine's own `CardData.stage2` flag and is what
    # `applies_to: stage2` resolves — `CardStat.stage` is declared but unpopulated on this base.
    DRAKLOAK: CardStat(DRAKLOAK, name="Drakloak", hp=90, energyType=DRAGON, evolvesFrom="Dreepy"),
    DRAGAPULT_EX: CardStat(DRAGAPULT_EX, name="Dragapult ex", hp=320, energyType=DRAGON, ex=True,
                           evolvesFrom="Drakloak", stage2=True),
    ZORUA: CardStat(ZORUA, name="Zorua", hp=70, energyType=DARKNESS),
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
_TAGS = {IGNITION: ["provides:1", "provides_evo:3"]}
#: Boss's Orders' `gust` clause — the reason a Supporter's `_PLAY` refuses rather than pricing its
#: structural floor as the whole play. The two Stadium clauses are `card_effects.json`'s own entries
#: for 1252 and 1260, key for key: `applies_to` is part of each and dropping it here would make the
#: fixture answer a question the shipped compendium does not ask (Issue #410).
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
    """A board body in the engine's real shape. ``energy`` is a sequence of ``(card id, units)``
    pairs — the two-field split `common/board_cards.py` exists for."""
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
    """`docs/rules.md` §3 — one manual Energy attachment per turn. Three writes and no more: the
    card leaves my hand, the CARD lands on `energyCards` while the UNITS it provides land on
    `energies` (`common/board_cards.py`'s split), and the allowance is spent so a second attach
    cannot be priced as if it were legal."""
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
    """The trap `common/board_cards.py` was extracted for. Ignition Energy is card **17** and
    provides {C} on a Basic — so `energies` must read `[0]`, never `[17]`. The coincidence that Basic
    Energy card ids equal their `EnergyType` codes stops at the ninth card, and a reader that walked
    `energies` for card identity would miss card 17 entirely."""
    obs = _obs(_player(active=_body(RIOLU), hand=[IGNITION]))
    after = _apply(obs, {"type": _ATTACH, "area": HAND, "index": 0,
                         "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after.mine.active.energy_key == (COLORLESS,)
    assert after.mine.active.energy_count == 1


@pytest.mark.req("REQ-APPLY-0002")
def test_attaching_a_TOOL_writes_the_tool_zone_its_HP_grant_and_NOT_the_energy_allowance():
    """A Pokémon Tool *"arrives as OptionType.ATTACH exactly like an Energy"* and is nothing like
    one: it writes `attached_tools`, it grants Hero's Cape's printed **+100 HP** on both the current
    and the maximum, and it spends no allowance — a Tool is an ordinary Trainer play, and
    `docs/rules.md` §3 caps only the manual ENERGY attachment."""
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
    """The grant is read through `CardStat.applies_to_holder`, the ONE place every holder condition
    is evaluated (Issue #306) — so a Tool restricted to a no-Rule-Box holder does not silently pump a
    Pokémon ex. Asserted on a fabricated gate rather than on Brave Bangle's card id, because what is
    under test is that the seam CONSULTS the gate."""
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
    """The ordering hot path visits every option on a live menu, and `src/cg/api.py` warns the option
    vocabulary grows during the competition. An `IndexError` there is a forfeited grader match over
    an option we merely could not resolve."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F]))
    r = _apply(obs, {"type": _ATTACH, "area": HAND, "index": 0,
                     "inPlayArea": BENCH, "inPlayIndex": 3})
    assert isinstance(r, ao.Refusal) and r.scope == ao.OPTION_SCOPE and ao.must_expand(r)


# ── _EVOLVE ───────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0002")
def test_evolving_keeps_the_attachments_and_the_damage_and_stacks_the_old_card_underneath():
    """`docs/rules.md` §4 — *"Evolving keeps attached cards + damage counters"*. Damage carries as a
    DELTA, not as an HP number: the new body has a different maximum, so a Riolu at 80−20 evolving
    into a 340 HP Mega Lucario ex arrives at 320, not at 60 and not at 340.

    **Riolu → Mega Lucario ex is a SINGLE hop** in this set (`docs/rulebook.txt` Appendix 1) — the
    standing worked example of why card facts are read rather than recalled."""
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
    """Ignition Energy provides {C} on a Basic and **{C}{C}{C} on an Evolution** — the same attached
    card, a different `energies` rendering before and after. Carrying the old list forward would
    under-report a Mega Starmie ex armed from zero by one attach, which is the false-famine class
    `_special_energy_groups` exists to prevent one zone over."""
    obs = _obs(_player(active=_body(RIOLU, energy=[(IGNITION, (COLORLESS,))]), hand=[MEGA_LUC]))
    after = _apply(obs, {"type": _EVOLVE, "area": HAND, "index": 0,
                         "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after.mine.active.energy_count == 3
    assert after.mine.active.energy_key == (COLORLESS, COLORLESS, COLORLESS)


@pytest.mark.req("REQ-APPLY-0002")
def test_the_EVOLVED_body_is_itself_new_in_play_so_it_cannot_evolve_again_this_turn():
    """The other half of `docs/rules.md` §4, and the one a reader is likelier to miss: the body that
    ARRIVES by evolving is new in play too, so a Stage 1 played this turn cannot become a Stage 2 on
    the same turn. Measured on the engine before it was modelled — `alakazam_9000` f127 shows the
    evolved body carrying ``appearThisTurn: true`` — and undeclared until Issue #391 enumerated the
    zone, which is why the parity lane could not have caught it going missing.

    The precondition is the same rule read forward: the Riolu being evolved must NOT be new in play,
    or the option would not be legal at all."""
    obs = _obs(_player(active=_body(RIOLU), hand=[MEGA_LUC]))
    assert obs["current"]["players"][0]["active"][0].get("appearThisTurn") in (None, False)
    after = _apply(obs, {"type": _EVOLVE, "area": HAND, "index": 0,
                         "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after.mine.active.card_id == MEGA_LUC
    assert after.mine.active.new_in_play is True
    assert after.mine.active_raw["appearThisTurn"] is True


@pytest.mark.req("REQ-APPLY-0002")
def test_evolving_the_ACTIVE_clears_its_special_conditions():
    """`docs/rules.md` §4 and §8 — Special Conditions live on the Active alone and are cleared when
    it leaves the Active spot **or evolves**. The evolve half is the one easy to miss, because the
    rules text puts the leaving half first."""
    obs = _obs(_player(active=_body(RIOLU), hand=[MEGA_LUC], conditions=("asleep", "confused")))
    after = _apply(obs, {"type": _EVOLVE, "area": HAND, "index": 0,
                         "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert after.mine.conditions == frozenset()


# ── _RETREAT ──────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0002")
def test_a_retreat_OPTION_spends_the_allowance_and_moves_nothing_else():
    """**The measurement, not a simplification.** A retreat option is the bare `{"type": 12}` — no
    promoted body, no Energy to pay with — in 5807 of 5807 offered occurrences across the committed
    parity corpus and 146 of 146 in the 372-frame corrections corpus both ADR-0072 gates replay. The
    engine answers it by spending the allowance and posing the cost (`_DISCARD_ENERGY`, context 30)
    and the promotion (`_SWITCH`, context 3) as SEPARATE selects.

    So modelling a swap here would diverge from the engine on the very next frame, and the seam's
    reference is the recorded native trace. What follows from that — that a retreat prices near zero
    at 1 ply and must therefore be admitted to the beam on other grounds — is the composer's
    (Issue #385), and is written where an implementer reads it (`board_delta._retreat`)."""
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
    """A behavioural test would pass on a seam that merely ignored a target it was given. This pins
    the FACT the transition rests on, in the place a later reader meets it — because the natural
    reading of *"model the retreat"* is the whole maneuver, and that reading is what the corpus
    refutes."""
    import inspect
    src = inspect.getsource(bd._retreat)
    assert "5807 of 5807" in src and "146 of 146" in src
    assert "Issue #385" in src


@pytest.mark.req("REQ-APPLY-0002")
def test_the_CHOICE_branch_changes_the_SHAPE_and_leaves_the_point_transition_exactly_as_it_was():
    """**Issue #392's wiring, asserted from this file** — because the acceptance criterion it carries
    is a NEGATIVE one: the two `_retreat` tests above must stay green, and if they go red the
    implementation widened the seam rather than building beside it.

    So the same board is applied twice. Unarmed, the seam returns the allowance-only `StateModel` the
    two tests above pin, byte for byte. Armed with ``expand_deferred_targets=True`` it returns an
    `Expectation` over the boards the deferred target can reach — a shape `apply_option` already
    declares among its four returns — and the FATE is `MODELLED` either way, because what a choice
    node changes is the shape and not the verdict.

    `runtime.PROFILE["deferred_target_expansion"]` ships **False**, which is what keeps the ADR-0098
    parity lane and both ADR-0072 gates seeing the seam Issue #382 verified until Issue #385's
    composer exists to consume the other shape."""
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
def test_the_shipped_PROFILE_leaves_deferred_target_expansion_OFF():
    """The default is the load-bearing half of the test above, and it is pinned where an implementer
    reading the retreat transition will meet it. `tests/agents/test_runtime.py` pins the whole
    profile; this pins the one flag whose ON state would change what every gate in the repo sees."""
    from common.runtime import PROFILE
    assert PROFILE["deferred_target_expansion"] is False
    import inspect
    assert inspect.signature(ao.apply_option).parameters[
        "expand_deferred_targets"].default is False


# ── _PLAY ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-APPLY-0002")
def test_playing_a_basic_benches_it_fresh_and_marks_it_as_new_in_play():
    """A deploy lands a full-HP body on the Bench flagged `appearThisTurn`, which is what makes it
    unevolvable this turn (`docs/rules.md` §4 — *"Cannot evolve a Pokémon the turn it was
    played"*).

    Asserted through the SNAPSHOT (`BodyView.new_in_play`, Issue #391) as well as off the raw dict.
    The raw assertion was here first and was the whole check, which is precisely the gap that issue
    closed: the transition was right and only a reader holding the raw board could tell. The two are
    kept side by side so they cannot drift into disagreeing about one body."""
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
    """*"Each player may have up to 5 Pokémon on the Bench"* (`docs/rulebook.txt` L75). An illegal
    play priced like a legal one is a phantom line, not a small error."""
    obs = _obs(_player(active=_body(RIOLU),
                       bench=[_body(MUNKIDORI, serial=i) for i in range(2, 7)],
                       hand=[MUNKIDORI]))
    r = _apply(obs, {"type": _PLAY, "index": 0})
    assert isinstance(r, ao.Refusal) and "Bench is full" in r.reason


@pytest.mark.req("REQ-APPLY-0005")
def test_playing_a_SUPPORTER_refuses_because_the_effect_IS_the_play():
    """Boss's Orders' clauses write `bodies_in_play`, `special_conditions` and `transient_grants` —
    none of which the structural floor performs. Pricing the floor alone would difference the gust to
    ~0 and hide the whole point of the card, which is the silent zero Issue #300's `_covers` verdict
    exists to refuse. The refusal names the card, so the modelling backlog is readable as work."""
    obs = _obs(_player(active=_body(RIOLU), hand=[BOSS]))
    r = _apply(obs, {"type": _PLAY, "index": 0})
    assert isinstance(r, ao.Refusal) and r.scope == ao.OPTION_SCOPE
    assert "1182" in r.reason and "bodies_in_play" in r.reason
    assert ao.must_expand(r) is True


@pytest.mark.req("REQ-APPLY-0002")
def test_playing_a_stadium_swaps_the_one_in_play_and_discards_it_to_ITS_OWNER():
    """`docs/rulebook.txt` L135-137 — *"Only one Stadium can be in play at a time—if a new one comes
    into play, discard the old one and end its effects."* L78 — *"Each player has their own discard
    pile"*, which is why displacing THEIRS writes THEIR discard and not mine. `docs/rules.md` §3
    spends the one-per-turn allowance.

    Displacing **Jamming Tower**, which has no Effect Clauses — the case the seam can model. A
    Stadium whose effect WRITES refuses, and that is the test below."""
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
    """The caller of the Stadium gate the parity lane could not have found, and the reason it is here
    on the RULE rather than on the measurement.

    *"…discard the old one and **end its effects**"* (`docs/rulebook.txt` L137). Gravity Mountain
    leaving play gives every Stage 2 in play its 30 HP back — verified on the corpus rather than
    reasoned: `ml_dx_2001` carries Dragapult ex at **290/290 at f172 while Gravity Mountain is out,
    and 320/320 at f181 once it is gone**. A structural swap that only moved the `stadium` zone would
    leave every one of those bodies at a stale maximum.

    The committed corpus contains ZERO steps that play a quiet Stadium over a writing one — all four
    displacements in it play a *writing* Stadium, which refuses on its own clause union — so the
    parity lane's clean sweep is not evidence about this path, and this test is."""
    obs = _obs(_player(active=_body(RIOLU), hand=[BATTLE_CAGE]),
               stadium=[{"id": GRAVITY_MOUNTAIN, "serial": 55, "playerIndex": 1}])
    r = _apply(obs, {"type": _PLAY, "index": 0})
    assert isinstance(r, ao.Refusal) and r.scope == ao.OPTION_SCOPE
    assert "1252" in r.reason and "DISPLACING" in r.reason


@pytest.mark.req("REQ-APPLY-0005")
def test_replaying_the_stadium_already_in_play_refuses_as_an_illegal_play():
    """*"You can't play a Stadium card if a Stadium with the same name is already in play"*
    (`docs/rulebook.txt` L137), restated in `docs/rules.md` §3."""
    obs = _obs(_player(active=_body(RIOLU), hand=[BATTLE_CAGE]),
               stadium=[{"id": BATTLE_CAGE, "serial": 55, "playerIndex": 0}])
    r = _apply(obs, {"type": _PLAY, "index": 0})
    assert isinstance(r, ao.Refusal) and "already in play" in r.reason


# ── the board-level modifiers the option's own clauses cannot see ─────────────────────────────────


def _bench(after_obs, index=0):
    """The raw benched body dict off a synthesized observation.

    Read raw rather than through `StateModel`, because the assertions here are about ``hp`` AND
    ``maxHp`` together — a projection that exposed only one of them could not tell a stored damage
    counter (moves ``hp``) from a floating Stadium delta (moves both), which is the exact distinction
    Issue #410 turns on."""
    return after_obs["current"]["players"][0]["bench"][index]


def _active(after_obs):
    return after_obs["current"]["players"][0]["active"][0]


@pytest.mark.req("REQ-APPLY-0005")
def test_a_stadium_that_CANNOT_reach_the_transition_stops_gating_it():
    """Issue #410 R2, and the largest single result in that issue: **73 of the blanket gate's 104
    refused corpus steps needed no clause application whatsoever.**

    Its predecessor `_stadium_gate` asked *"is a Stadium with a non-empty `CLAUSE_WRITES` union in
    play?"* — a question with no reference to the option, the body or the event — so Gravity Mountain
    refused 19 evolutions into a Stage 1 and 15 Basic deploys, and Risky Ruins refused 39 evolutions.
    `stadium_clauses_for` asks whether the clause reaches THIS event and THIS body, so all four of
    these transition normally and write nothing new.

    The rules behind each row, at source: Risky Ruins (1260) is *"Whenever any player puts a Basic
    non-{D} Pokémon onto their **Bench**"* — an evolution is not a bench play. Gravity Mountain
    (1252) is *"Each **Stage 2** Pokémon in play"* — a Basic is not one, and neither is a Stage 1."""
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
    """Issue #410 R3, with its positive control — *"a green suite proves nothing about a gate nobody
    fires"*.

    *"Whenever any player puts a Basic non-{D} Pokémon onto their Bench during their turn, place 2
    damage counters on that Pokémon"* (1260, `data/EN_Card_Data.csv`). A counter is 10 damage, so the
    compendium's ``amount: 2`` and the engine's ``{"onBench": {"damage": 20}}`` are the same tax
    spelled two ways.

    **``hp`` moves and ``maxHp`` does not** — a damage counter does not lower a maximum. That is the
    sharp difference from `_attach`'s Tool grant, which moves both, and getting it backwards is what
    the parity lane's 104 recorded steps would catch.

    Three boards, because two of them are the controls: the same Munkidori deploy under NO Stadium
    lands untaxed, and **Zorua — a {D} Basic** — is untaxed under Risky Ruins itself, which is the
    engine's own ``unlessEnergyType: [7]`` gate (`cgpy/turn.py:_after_benched`)."""
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
    """Issue #410 R4 and its composition order, with the Stage-1 control beside it.

    *"Each Stage 2 Pokémon in play (both yours and your opponent's) gets -30 HP"* (1252). Dragapult
    ex is printed **320 HP** and renders **290** under Gravity Mountain — measured on the corpus, not
    recalled: `ml_dx_2001` carries it at 290/290 at f172 with the Stadium out and 320/320 at f181
    once it is gone.

    **The order is the engine's rather than a choice.** A Tool's flat grant is STORED in `max_hp`
    (`board_delta._evolve` already sums it) and the Stadium delta FLOATS on top at render
    (`cgpy/render.py:pokemon_dict`: ``maxHp = p.max_hp + delta``). So a Tool-carrying Drakloak
    evolving into a Dragapult ex under Gravity Mountain lands at ``320 + 100 - 30 = 390``. Folding
    the delta into the tool sum would give the same number here — which is exactly why the Stage-1
    control matters: it is where a mis-scoped delta shows, since a Stage 1 must land UNCHANGED."""
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
    """`docs/rules.md` §4 — *"Evolving keeps attached cards + damage counters"* — under a Stadium.

    The carry is stated as a DELTA (``taken = maxHp - hp``) precisely so that a floating modifier
    cancels: a damaged Drakloak's rendered `hp` and `maxHp` shift together, so ``taken`` is the same
    number with or without the Stadium and the new body lands at ``290 - taken``. That invariance is
    why R4 was a one-line addition to `max_hp` and needed no re-derivation of the carry."""
    mountain = [{"id": GRAVITY_MOUNTAIN, "serial": 55, "playerIndex": 1}]
    after = bd.transition(
        _obs(_player(active=_body(DRAKLOAK, damage=40), hand=[DRAGAPULT_EX]), stadium=mountain),
        {"type": _EVOLVE, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0},
        seat_index=0, combat=_combat(), context=MAIN)
    assert (_active(after.obs)["hp"], _active(after.obs)["maxHp"]) == (250, 290)


@pytest.mark.req("REQ-APPLY-0005")
def test_an_UNRECOGNISED_stadium_vocabulary_value_makes_the_caller_REFUSE():
    """The fail-closed half of R1, and it needs its own test because nothing else can see it.

    `applies_to` and `on` are `snapshot_coverage` **PARAMETERS** rather than `VOCABULARY_KEYS`, so
    `undeclared_clauses` does not walk their VALUES and drift there is invisible to the compendium
    audit — the one place in this system where a new clause value could arrive unaudited. So
    `stadium_clauses_for` returns an unrecognised clause ANYWAY and the applier refuses on it,
    exactly as `_clause_writes` refuses an undeclared clause VALUE.

    Four synthetic clauses, and the last one is the CONTRAST: ``kind`` is a `VOCABULARY_KEYS` axis,
    so an undeclared value there is already caught one layer down by `_clause_writes` and refuses
    with the registry's own message. The first three are the axes nothing else guards — an unknown
    ``applies_to``, an unknown ``on``, and a DECLARED kind that is simply not a Stadium's."""
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
    """The predicate itself, at the unit level — the four answers the three call sites depend on.

    ``displace`` is the widening one and it is not symmetry for its own sake (R6): ending a Stadium
    re-renders every body it was modifying, on BOTH sides, including bodies the transition never
    touched. There is no per-body question to narrow to, so it returns every writing clause and the
    caller refuses."""
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

    # A Stadium whose effects write NOTHING never reaches anything, and neither does an empty zone —
    # `damage_reduction` / `damage_boost` / `prevent_damage` are read off the `stadium` zone by
    # `CombatMath` when it prices an attack and stored nowhere, so they gate nothing and never did.
    assert bd.stadium_clauses_for(quiet, combat, event="displace") == ()
    assert bd.stadium_clauses_for({}, combat, event="displace") == ()
    assert len(bd.stadium_clauses_for(mountain, combat, event="displace")) == 1
    assert len(bd.stadium_clauses_for(ruins, combat, event="displace")) == 1


@pytest.mark.req("REQ-APPLY-0005")
def test_an_option_posed_inside_a_cards_effect_refuses_because_the_card_writes_too():
    """14 575 of 14 576 modelled steps in the committed parity corpus are posed at
    `SelectContext.MAIN`. The one exception is Rare Candy's `_EVOLVE` at context 37, and answering it
    also puts the Rare Candy in the discard (`trcx_9100` f13) — a write that belongs to the CARD, not
    to the evolve. The seam models the option's kind, so it refuses the leg of a card's resolution."""
    obs = _obs(_player(active=_body(RIOLU), hand=[MEGA_LUC]), context=37)
    r = _apply(obs, {"type": _EVOLVE, "area": HAND, "index": 0,
                     "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert isinstance(r, ao.Refusal) and "MAIN menu" in r.reason


# ── purity: the property the whole differencing scheme rests on ──────────────────────────────────


@pytest.mark.req("REQ-APPLY-0007")
def test_a_transition_never_mutates_the_model_it_was_given_MEMO_INCLUDED():
    """*"The planner holds the pre-state while it evaluates alternatives"* — a transition that edited
    in place would corrupt every sibling branch. **The memo is the sharp half**: `state_value`
    caches its per-family dict on the model under `("state_value",)` and NOTHING invalidates that
    key, so a mutated model would keep returning the pre-state's scalar in silence. Read the scalar
    first, so the memo is warm and would be caught if the transition wrote through it."""
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
    """Purity end to end, which is what makes the deterministic tie-break and both replay gates mean
    anything: a wobbly scorer makes a secondary key meaningless (Issue #262's requirement, consumed
    by Issue #263's beam-quality package)."""
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
    """The copy-on-write dividend, and the reason `Delta` reports it rather than the caller hashing
    the result: their expensive clock derivations survive a hypothetical that never touched them.
    Sharing is never assumed — a Stadium play writes a zone their side READS, so it rebuilds."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F, BATTLE_CAGE]))
    model = _model(obs)
    quiet = ao.apply_option(model, {"type": _ATTACH, "area": HAND, "index": 0,
                                    "inPlayArea": ACTIVE, "inPlayIndex": 0})
    assert quiet.theirs is model.theirs
    loud = ao.apply_option(model, {"type": _PLAY, "index": 1})
    assert loud.theirs is not model.theirs


@pytest.mark.req("REQ-APPLY-0007")
def test_the_post_state_is_a_FRESH_model_with_its_own_memo():
    """Not a patched one. `StateModel.build` is *"cheap, because it computes nothing yet"*, and a
    fresh model owns a fresh memo — which makes the `("state_value",)` staleness hazard impossible by
    construction rather than by discipline."""
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
    """Issue #382's test line asks for *"its declared write-set **and nothing else**"*, and the
    "nothing else" half is what a subset assertion cannot give: `⊆` catches an EXTRA write and lets a
    FORGOTTEN one through, which is the direction that matters (a delta that under-reports is a
    pruned option).

    So each case pins its exact write-set. The `⊆ FOOTPRINTS[kind]` check rides alongside and is a
    different claim — a footprint that under-reports is *"worse than none"* (`apply_option.Footprint`)
    because it would license a reorder that changes the board. **Equality against the FOOTPRINT is
    deliberately NOT asserted**: a footprint is per-KIND and describes the widest board change the
    kind can make, while a delta is per-OPTION — `_RETREAT`'s footprint names the whole maneuver's
    five zones and the retreat OPTION spends one allowance."""
    combat = _combat()
    cases = [
        ("energy attach", _ATTACH, _obs(_player(active=_body(RIOLU), hand=[E_F])),
         {"type": _ATTACH, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0},
         {"my_hand_ids", "attached_energy", "allowance_energy_attached"}),
        ("HP-granting Tool attach", _ATTACH, _obs(_player(active=_body(RIOLU), hand=[CAPE])),
         {"type": _ATTACH, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0},
         {"my_hand_ids", "attached_tools", "damage_counters"}),
        # `new_in_play` on BOTH evolve cases and unconditionally: the evolved body arrives with
        # `appearThisTurn: True` and the body it replaced necessarily had it False, since
        # `docs/rules.md` §4 forbids evolving a body the turn it was played. It went undeclared
        # until Issue #391 enumerated the zone — the write was always real, and nothing in the tree
        # could see it.
        ("evolve the Active under a condition", _EVOLVE,
         _obs(_player(active=_body(RIOLU), hand=[MEGA_LUC], conditions=("asleep",))),
         {"type": _EVOLVE, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0},
         {"my_hand_ids", "bodies_in_play", "special_conditions", "new_in_play"}),
        ("evolve a benched body (no condition to clear)", _EVOLVE,
         _obs(_player(active=_body(MUNKIDORI, serial=9), bench=[_body(RIOLU)], hand=[MEGA_LUC])),
         {"type": _EVOLVE, "area": HAND, "index": 0, "inPlayArea": BENCH, "inPlayIndex": 0},
         {"my_hand_ids", "bodies_in_play", "new_in_play"}),
        # `damage_counters` on the evolve, and ONLY under Gravity Mountain: the Stadium's static
        # `hp_delta` moves the new body's maximum, and `damage_counters` is the zone homing the HP
        # read. Joined at Issue #410, GAINING a case rather than loosening the two above — a `⊆`
        # here would have let a forgotten `damage_counters` through, which is the direction that
        # under-reports a delta and prunes a real option.
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
    """`_PLAY` is declared INCOMPLETE on purpose — a Trainer play writes whatever its Effect Clauses
    write, which is per-card — but the structural zones it names are a floor T4 must at LEAST reach.
    Both structural sub-cases are checked against it."""
    combat = _combat()
    floor = ao.footprint(_PLAY)
    assert floor.complete is False
    deploy = bd.transition(_obs(_player(active=_body(RIOLU), hand=[MUNKIDORI])),
                           {"type": _PLAY, "index": 0}, seat_index=0, combat=combat, context=MAIN)
    assert deploy.writes == frozenset({"my_hand_ids", "bodies_in_play", "bench_occupancy",
                                       "new_in_play"})
    assert deploy.writes <= floor.writes
    # The same deploy under Risky Ruins gains `damage_counters` and NOTHING else — the fifth zone the
    # `_PLAY` floor declares (Issue #410). Pinned EXACTLY, beside the un-taxed case above, so a
    # forgotten write is a failure and not only an extra one.
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
    """The `cg.api`-shaped surface `planner._search_api` injects, over a canned post-step board.

    A fake rather than the native engine deliberately: **0 of 372 gate frames carry
    `search_begin_input`**, so no committed board can drive a real search offline, and the whole
    strategy suite must stay DLL-free. What is under test is the seam's own wiring — one begin, one
    step, always ended — not the engine's arithmetic."""

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
    """A real dataclass, because the seam reads the engine's answer back through `asdict` — the
    engine's Observation IS one, and a duck-typed stand-in would test a different code path."""
    current: dict
    logs: list
    select: dict | None = None


@pytest.mark.req("REQ-APPLY-0008")
def test_an_engine_resolved_option_executes_through_the_seam_and_returns_a_WRAPPER():
    """§3b's bridge, executed. The route is open only at depth 0 with a PROVED determinism and a live
    seam, and it returns `EngineResolved` rather than a bare model so the telemetry cannot be
    forgotten — with a `clause_gap` naming the CARD, because a backlog line reading *"kind 7"* covers
    699 corpus `_PLAY` options at once (Issue #299)."""
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
    """The preceding steps were closed-form applies, so the board is a SYNTHESIZED StateModel and a
    synthesized model cannot be handed back to the native engine. The routing is already pinned in
    `test_apply_option.py`; this is the EXECUTION case — the engine must not be reached at all."""
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
    """The engine answers a select by INDEX. A wrong index is a DIFFERENT legal play silently priced
    as this one, which is worse than no price at all."""
    obs = _obs(_player(active=_body(RIOLU), hand=[BOSS]))
    obs["select"]["option"] = [{"type": _PLAY, "index": 4}]
    obs["search_begin_input"] = {"opaque": True}
    api = _FakeSearchApi(_obs(_player(active=_body(RIOLU), hand=[])))
    r = ao.apply_option(_model(obs), {"type": _PLAY, "index": 0}, clauses_cover=False,
                        deterministic=True, search_api=api)
    assert isinstance(r, ao.Refusal) and r.scope == ao.NO_ENGINE_SCOPE


@pytest.mark.req("REQ-APPLY-0008")
def test_an_engine_that_raises_refuses_instead_of_forfeiting_the_match():
    """This runs once per candidate per decision on the grader. An exception escaping the ordering
    path costs the match; a refusal costs one option's estimate."""
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
    """ADR-0098 decision 4, now with a transition behind it: a kind the parity lane found diverging
    must refuse rather than hand back the board it gets wrong. A parity failure DEGRADES the agent
    visibly (always-expand, named in telemetry) instead of silently mis-playing it."""
    obs = _obs(_player(active=_body(RIOLU), hand=[E_F]))
    option = {"type": _ATTACH, "area": HAND, "index": 0, "inPlayArea": ACTIVE, "inPlayIndex": 0}
    assert ao.apply_option(_model(obs), option).mine.active.energy_count == 1
    monkeypatch.setattr(ao, "quarantined_kinds", lambda: frozenset({_ATTACH}))
    r = ao.apply_option(_model(obs), option)
    assert isinstance(r, ao.Refusal) and r.scope == ao.QUARANTINE_SCOPE


@pytest.mark.req("REQ-APPLY-0004")
def test_the_quarantine_registry_is_a_RULING_RECORD_and_is_empty_by_MEASUREMENT():
    """Empty because the lane over the committed 377-trace corpus replays every modelled kind
    divergence-free — not because nobody has looked. An entry lands only with the divergence filed,
    exactly as a gate baseline is only re-captured on a developer verdict."""
    assert ao.QUARANTINED_KINDS == frozenset()
    assert ao.quarantined_kinds() == ao.QUARANTINED_KINDS
