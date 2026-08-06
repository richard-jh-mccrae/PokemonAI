"""The ATTACH DECIDER (#139, ADR-0069) — the axes-sum marginal that DECIDES every energy attach.

Successor to `test_attach_shadow.py`. The oracle it pins no longer shadows anything: the 19 rungs it
replaced are deleted, so every assertion here is about EXTERNAL BEHAVIOUR — the decision made at a
select, the axes values on the decision's working record, and the order picks come out in. Nothing
asserts a helper's internals, a matcher's call pattern, or suppressed-rung bookkeeping.

Two styles:
  * Style A — hand-built boards pin the ruled TERMS deterministically (including the four
    grill synthetics, the burst family, the ordering deferral and degraded mode).
  * Style B — replay committed correction frames and assert the DECISION, on decider semantics.
"""
import importlib.util
from pathlib import Path

import pytest

from card_facts import ignition_tags                    # the committed Ignition Energy tags, ONE copy
from common.cards import CardFunctions
from common.pilot import (Pilot, _ATTACH_ABILITY_FUEL, _ATTACH_RETREAT_EQUITY, _ATTACH_VALUE_SCALE)
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.strategy.context import _CARD, _DECK
from common.strategy.strategy import Line
from common.telemetry import to_record
from pilot_helpers import parity_selects

REPO = Path(__file__).resolve().parents[2]

ATTACH, HAND, ACTIVE, BENCH, MAIN = 8, 2, 4, 5, 0
END, RETREAT, PLAY = 14, 12, 7
_TOOL, _BASIC_ENERGY, _SPECIAL_ENERGY = 2, 5, 6
# EnergyType codes (src/cg/api.py): 3 = WATER, 5 = PSYCHIC, 6 = FIGHTING, 7 = DARKNESS.
WATER, PSYCHIC, FIGHTING, DARK = 3, 5, 6, 7

MEGA, STARYU, MEOWTH, IGNITION, CAPE = 1031, 1030, 1071, 17, 1100
W_ENERGY, P_ENERGY, F_ENERGY, D_ENERGY = 3, 5, 6, 7
LUNATONE, SOLROCK = 675, 676        # the co-dependent engine pair (deck-declared partners)
MUNKIDORI, DUNSPARCE = 112, 65      # the Ability-fuel body / the free-retreat draw engine
SHUFFLE = 1200                      # a `shuffle_hand` Supporter (hand-nuke finisher)
BALL = 1201                         # a free Item dig (development, no cost)

# Attack ids. Card facts VERIFIED at source (data/EN_Card_Data.csv, 2026-07-25).
JETTING, NEBULA = 101, 102          # Mega Starmie ex: {W} 120 / ●●● 210
WATER_GUN = 103                     # Staryu: {W} 20
POWER_GEM = 104                     # Lunatone: {F}{F} 50
COSMIC_BEAM = 105                   # Solrock: {F} 70
MIND_BEND = 106                     # Munkidori: {P}● 60 (Adrena-Brain wants a {D})
GNAW, TUCK_TAIL = 107, 108          # TEF Dunsparce Gnaw / Meowth ex Tuck Tail


def _attach(hand_idx, area, in_idx):
    return {"type": ATTACH, "area": HAND, "index": hand_idx,
            "inPlayArea": area, "inPlayIndex": in_idx}


def _stats():
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                       minCostDamage=120, minAttackCost=1, maxDamageCost=3, evolvesFrom="Staryu",
                       retreatCost=2, attacks=(JETTING, NEBULA)),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, maxDamage=20, minCostDamage=20,
                         minAttackCost=1, maxDamageCost=1, retreatCost=1, attacks=(WATER_GUN,)),
        LUNATONE: CardStat(LUNATONE, name="Lunatone", hp=110, maxDamage=50, minCostDamage=50,
                           minAttackCost=2, maxDamageCost=2, hasAbility=True, retreatCost=1,
                           attacks=(POWER_GEM,)),
        SOLROCK: CardStat(SOLROCK, name="Solrock", hp=110, maxDamage=70, minCostDamage=70,
                          minAttackCost=1, maxDamageCost=1, retreatCost=1, attacks=(COSMIC_BEAM,)),
        MUNKIDORI: CardStat(MUNKIDORI, name="Munkidori", hp=110, maxDamage=60, minCostDamage=60,
                            minAttackCost=2, maxDamageCost=2, hasAbility=True, retreatCost=1,
                            abilityEnergyTypes=(DARK,), attacks=(MIND_BEND,)),
        DUNSPARCE: CardStat(DUNSPARCE, synthetic=True, name='Dunsparce', hp=60, maxDamage=10, minCostDamage=10,
                            minAttackCost=1, maxDamageCost=1, retreatCost=0, attacks=(GNAW,)),
        MEOWTH: CardStat(MEOWTH, name="Meowth ex", hp=170, ex=True, maxDamage=60,
                         minCostDamage=60, minAttackCost=3, maxDamageCost=3, hasAbility=True,
                         retreatCost=1, attacks=(TUCK_TAIL,)),
        W_ENERGY: CardStat(W_ENERGY, synthetic=True, name="Water", cardType=_BASIC_ENERGY, energyType=WATER),
        P_ENERGY: CardStat(P_ENERGY, synthetic=True, name="Psychic", cardType=_BASIC_ENERGY, energyType=PSYCHIC),
        F_ENERGY: CardStat(F_ENERGY, synthetic=True, name="Fighting", cardType=_BASIC_ENERGY, energyType=FIGHTING),
        D_ENERGY: CardStat(D_ENERGY, synthetic=True, name="Darkness", cardType=_BASIC_ENERGY, energyType=DARK),
        IGNITION: CardStat(IGNITION, synthetic=True, name="Ignition", cardType=_SPECIAL_ENERGY, energyType=0),
        CAPE: CardStat(CAPE, synthetic=True, name="Hero's Cape", cardType=_TOOL, aceSpec=True, hpBonus=100),
        SHUFFLE: CardStat(SHUFFLE, synthetic=True, name="Iono", cardType=4),
        BALL: CardStat(BALL, synthetic=True, name="Ultra Ball", cardType=3),
    }, attacks={
        JETTING: AttackStat(JETTING, damage=120, cost=1, energyTypes=(WATER,)),
        NEBULA: AttackStat(NEBULA, damage=210, cost=3, energyTypes=(0, 0, 0)),
        WATER_GUN: AttackStat(WATER_GUN, damage=20, cost=1, energyTypes=(WATER,)),
        POWER_GEM: AttackStat(POWER_GEM, damage=50, cost=2, energyTypes=(FIGHTING, FIGHTING)),
        COSMIC_BEAM: AttackStat(COSMIC_BEAM, damage=70, cost=1, energyTypes=(FIGHTING,)),
        MIND_BEND: AttackStat(MIND_BEND, damage=60, cost=2, energyTypes=(PSYCHIC, 0)),
        GNAW: AttackStat(GNAW, damage=10, cost=1, energyTypes=(0,)),
        TUCK_TAIL: AttackStat(TUCK_TAIL, damage=60, cost=3, energyTypes=(0, 0, 0)),
    })


#: The default board vocabulary mirrors a real deck: Staryu is the win-condition Line's base, which
#: is what makes it an ATTACKER ALTERNATIVE for the board-evaluated role gate. Tests that need the
#: gate to STAND DOWN (the desperation floor) simply put no alternative in play.
_LINES = (Line(path=[STARYU, MEGA], payoff=MEGA),)


def _pilot(*, roles=None, partners=None, lines=_LINES, attach_value=True, functions=None):
    strat = Strategy(roles=roles if roles is not None
                     else {MEGA: ["win_condition", "primary_attacker"], STARYU: ["starter"],
                           LUNATONE: ["engine"], SOLROCK: ["secondary_attacker", "engine"]},
                     partners=partners if partners is not None
                     else {SOLROCK: [LUNATONE], LUNATONE: [SOLROCK]},
                     lines=list(lines))
    funcs = functions if functions is not None else CardFunctions(
        {MEOWTH: ["search", "supporter_tutor"], IGNITION: ignition_tags(),
         SHUFFLE: ["shuffle_hand"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=funcs, attach_value=attach_value)


def _obs(bench, hand, options, active=None, turn=6, opp_active=None, opp_bench=()):
    me = {"active": [active], "bench": bench, "hand": hand}
    opp = {"active": [opp_active], "bench": list(opp_bench)}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": turn},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1, "option": options}}


def _row_for(working, index):
    return next((r for r in working["eq"] if r["i"] == index), None)


# ---------------------------------------------------------------- Style A: the ruled axes

@pytest.mark.req("REQ-ATTACH-DECIDER-0001")
def test_working_rides_the_decision_and_the_wire():
    """The per-option axes rows ARE the decider's legible working (ADR-0069 §9) — on the decision
    record and on the telemetry wire, with no agreement bit (there is nothing to agree with)."""
    p = _pilot()
    bench = [{"id": MEGA, "energies": [W_ENERGY, W_ENERGY], "hp": 330},
             {"id": STARYU, "energies": [], "hp": 70}]
    dec = p.explain(_obs(bench, [{"id": W_ENERGY}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)]))
    w = dec.attach_working
    assert w is not None and set(w) == {"eq", "abstained"}
    assert "agree" not in w and "eq_pick" not in w          # the shadow's self-reference is gone
    assert set(w["eq"][0]) >= {"marginal", "tactical", "attack_axis", "this_turn", "build",
                               "accel_value", "retreat_equity", "ability_fuel", "evaporation_loss"}
    assert to_record(dec).get("attach_working") == w
    assert dec.chosen == [0]                                # concentrate on the started Mega


@pytest.mark.req("REQ-ATTACH-DECIDER-0002")
def test_a_tool_abstains_and_is_never_priced():
    """A Pokémon Tool rides OptionType.ATTACH but carries no Energy — never priced, only counted."""
    p = _pilot()
    active = {"id": MEGA, "energies": [W_ENERGY, W_ENERGY], "hp": 330}
    obs = _obs([], [{"id": CAPE}, {"id": W_ENERGY}],
               [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0)], active=active)
    w = _pilot().explain(obs).attach_working
    assert _row_for(w, 0) is None and w["abstained"] == 1
    assert _row_for(w, 1) is not None
    assert p.explain(obs).chosen == [1]


@pytest.mark.req("REQ-ATTACH-DECIDER-0003")
def test_over_attach_scores_zero_build_on_a_maxed_body():
    p = _pilot()
    bench = [{"id": MEGA, "energies": [W_ENERGY] * 3, "hp": 330},
             {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": W_ENERGY}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    w = p.explain(obs).attach_working
    assert _row_for(w, 0)["build"] == 0.0                   # every slot already filled
    assert _row_for(w, 1)["build"] > 0.0
    assert p.explain(obs).chosen == [1]


@pytest.mark.req("REQ-ATTACH-DECIDER-0004")
def test_off_type_waste_is_an_emergent_zero_not_a_flag():
    """A {P} onto Solrock, whose only attack costs {F}, fills no slot and so buys ZERO build — the
    typed slot-fraction subsumes the deleted `dont-waste-off-type-energy` boolean."""
    p = _pilot()
    bench = [{"id": SOLROCK, "energies": [], "hp": 110}]
    w = p.explain(_obs(bench, [{"id": P_ENERGY}, {"id": F_ENERGY}],
                       [_attach(0, BENCH, 0), _attach(1, BENCH, 0)])).attach_working
    assert _row_for(w, 0)["build"] == 0.0                   # {P} pays no {F} slot
    assert _row_for(w, 1)["build"] > 0.0


@pytest.mark.req("REQ-ATTACH-DECIDER-0005")
def test_a_colourless_slot_absorbs_any_type():
    """Nebula Beam is ●●●, so an off-colour Energy is real build — the old colourless-blind boolean
    could not see this and the typed fraction must."""
    p = _pilot()
    bench = [{"id": MEGA, "energies": [W_ENERGY], "hp": 330}]
    w = p.explain(_obs(bench, [{"id": P_ENERGY}], [_attach(0, BENCH, 0)])).attach_working
    assert _row_for(w, 0)["build"] > 0.0


# --- the four grill synthetics --------------------------------------------------------------

@pytest.mark.req("REQ-ATTACH-DECIDER-0006")
def test_doomed_active_arms_a_non_biggest_attack_over_a_bench_build():
    """Grill 1 — the tempo case the rung layer structurally lost: its arm exemption was
    biggest-attack-only, so a doomed Mega Starmie whose attach unlocks Jetting Blow (120, NOT its
    biggest) lost the Energy to a bench build worth ~70. Pure arithmetic now: ANY attack the attach
    unlocks tonight counts."""
    p = _pilot(lines=[Line(path=[STARYU, MEGA], payoff=MEGA)])
    active = {"id": MEGA, "energies": [], "hp": 20}          # doomed: one hit finishes it
    bench = [{"id": MEGA, "energies": [W_ENERGY, W_ENERGY], "hp": 330}]
    obs = _obs(bench, [{"id": W_ENERGY}], [_attach(0, ACTIVE, 0), _attach(0, BENCH, 0)],
               active=active, opp_active={"id": MEGA, "hp": 330})
    w = p.explain(obs).attach_working
    assert _row_for(w, 0)["this_turn"] == 120.0              # Jetting Blow, not Nebula Beam
    assert _row_for(w, 0)["marginal"] > _row_for(w, 1)["marginal"]
    assert p.explain(obs).chosen == [0]


@pytest.mark.req("REQ-ATTACH-DECIDER-0007")
def test_lone_utility_body_desperation_attach_beats_ending_the_turn():
    """Grill 2 — the desperation floor. A lone Lunatone (engine-only Role, partner absent)
    is the ONLY legal home; the board-evaluated role gate stands down because no attacker
    alternative is in play, and Retreat Equity floors the attach above End regardless."""
    p = _pilot()
    active = {"id": LUNATONE, "energies": [], "hp": 110}
    obs = _obs([], [{"id": W_ENERGY}], [_attach(0, ACTIVE, 0), {"type": END}], active=active)
    w = p.explain(obs).attach_working
    row = _row_for(w, 0)
    assert row["role_gated"] is False                        # no alternative in play -> gate stands down
    assert row["retreat_equity"] == _ATTACH_RETREAT_EQUITY   # Lunatone's printed Retreat is 1
    assert row["tactical"] > 0.0
    assert p.explain(obs).chosen == [0]                      # ... and that beats End


@pytest.mark.req("REQ-ATTACH-DECIDER-0008")
def test_the_double_duty_colour_beats_the_same_build_alternative_outright():
    """Grill 3 — Munkidori: Mind Bend costs {P}●, Adrena-Brain wants a {D}. The {D} fills
    the colourless slot AND wakes the Ability: two INDEPENDENT card features on one Energy. Under a
    `max` combiner they would TIE with a plain {P}; only the additive channel ranks {D} first."""
    p = _pilot(roles={MUNKIDORI: ["counter_mover"]}, partners={}, lines=())
    active = {"id": MUNKIDORI, "energies": [], "hp": 110}
    obs = _obs([], [{"id": D_ENERGY}, {"id": P_ENERGY}],
               [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0)], active=active)
    w = p.explain(obs).attach_working
    dark, psy = _row_for(w, 0), _row_for(w, 1)
    assert dark["build"] == psy["build"]                     # both fill exactly one slot
    assert dark["ability_fuel"] == _ATTACH_ABILITY_FUEL and psy["ability_fuel"] == 0.0
    assert dark["marginal"] > psy["marginal"]
    assert p.explain(obs).chosen == [0]


@pytest.mark.req("REQ-ATTACH-DECIDER-0009")
def test_free_retreat_draw_engine_scores_zero_across_every_channel():
    """Grill 4 — the f21 lesson survives the mobility channel. TEF Dunsparce has NO printed
    Retreat cost, so Retreat Equity is structurally zero on it; the role gate zeroes its attack axis
    while a real attacker is in play; its Ability wants nothing. Every channel reads zero, so the
    deck's only {D} never goes there."""
    p = _pilot(roles={DUNSPARCE: ["engine"], MUNKIDORI: ["counter_mover"],
                      SOLROCK: ["secondary_attacker"]}, partners={}, lines=())
    active = {"id": MUNKIDORI, "energies": [], "hp": 110}
    bench = [{"id": DUNSPARCE, "energies": [], "hp": 60},
             {"id": SOLROCK, "energies": [], "hp": 110}]      # the attacker alternative in play
    obs = _obs(bench, [{"id": D_ENERGY}], [_attach(0, BENCH, 0), _attach(0, ACTIVE, 0)],
               active=active)
    w = p.explain(obs).attach_working
    dunsparce = _row_for(w, 0)
    assert dunsparce["role_gated"] is True
    assert (dunsparce["attack_axis"], dunsparce["retreat_equity"],
            dunsparce["ability_fuel"], dunsparce["marginal"]) == (0.0, 0.0, 0.0, 0.0)
    assert p.explain(obs).chosen == [1]                      # the {D} goes to the body that uses it


@pytest.mark.req("REQ-ATTACH-DECIDER-0010")
def test_the_role_gate_zeros_the_attack_axis_only():
    """A role-gated body still BANKS mobility and fuel — the gates land per-axis (ADR-0069 §4)."""
    p = _pilot()
    bench = [{"id": LUNATONE, "energies": [], "hp": 110}, {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": F_ENERGY}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    w = p.explain(obs).attach_working
    lunatone = _row_for(w, 0)
    assert lunatone["role_gated"] is True and lunatone["attack_axis"] == 0.0
    assert lunatone["retreat_equity"] > 0.0                  # mobility survives the attack-axis gate
    assert p.explain(obs).chosen == [1]                      # the Staryu attacker still wins


@pytest.mark.req("REQ-ATTACH-DECIDER-0010")
def test_spent_supporter_tutor_liability_banks_no_mobility_when_an_attacker_exists():
    """Meowth ex's Last-Ditch Catch is an on-play Bench ability, verified at source
    (`data/EN_Card_Data.csv` id 1071). Once the body is already in play, its utility value is spent:
    funding its 3-Energy / 60-damage Tuck Tail or its 1-Retreat mobility must not compete with a real
    attacker that can use the Energy."""
    p = _pilot(roles={STARYU: ["starter"]}, partners={}, lines=_LINES)
    bench = [{"id": MEOWTH, "energies": [], "hp": 170},
             {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": W_ENERGY}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    w = p.explain(obs).attach_working
    meowth, staryu = _row_for(w, 0), _row_for(w, 1)
    assert meowth["spent_utility_gated"] is True
    assert (meowth["attack_axis"], meowth["retreat_equity"],
            meowth["ability_fuel"], meowth["marginal"]) == (0.0, 0.0, 0.0, 0.0)
    assert staryu["build"] > 0.0
    assert p.explain(obs).chosen == [1]


@pytest.mark.req("REQ-ATTACH-DECIDER-0010")
def test_spent_supporter_tutor_desperation_floor_still_exists_when_no_attacker_can_take_it():
    """The ruling is not a veto. If the spent utility body is the only legal Energy home, the
    existing desperation floor still lets the decider attach rather than pretend the card cannot be
    spent."""
    p = _pilot(roles={MEOWTH: []}, partners={}, lines=())
    active = {"id": MEOWTH, "energies": [], "hp": 170}
    obs = _obs([], [{"id": W_ENERGY}], [_attach(0, ACTIVE, 0), {"type": END}], active=active)
    row = _row_for(p.explain(obs).attach_working, 0)
    assert row["spent_utility_gated"] is False
    assert row["tactical"] > 0.0
    assert p.explain(obs).chosen == [0]


@pytest.mark.req("REQ-ATTACH-DECIDER-0011")
def test_partnerless_engine_is_gated_and_a_partnered_one_is_not():
    """Board-evaluated: a Solrock with no Lunatone in play is a dead attacker; with one it is live."""
    p = _pilot()
    gated = _pilot().explain(_obs(
        [{"id": SOLROCK, "energies": [], "hp": 110}, {"id": STARYU, "energies": [], "hp": 70}],
        [{"id": F_ENERGY}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])).attach_working
    assert _row_for(gated, 0)["attack_axis"] == 0.0
    live_obs = _obs([{"id": SOLROCK, "energies": [], "hp": 110},
                     {"id": STARYU, "energies": [], "hp": 70},
                     {"id": LUNATONE, "energies": [], "hp": 110}],
                    [{"id": F_ENERGY}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    live = p.explain(live_obs).attach_working
    assert _row_for(live, 0)["attack_axis"] > 0.0            # partner present -> Cosmic Beam is live
    assert p.explain(live_obs).chosen == [0]


@pytest.mark.req("REQ-ATTACH-DECIDER-0012")
def test_evolution_escape_keeps_build_on_a_doomed_line_preevolution():
    """The survival gate zeroes build for a doomed Active — EXCEPT a wincon-Line pre-evolution, whose
    Energy carries through evolution (and a Mega evolving does not end the turn)."""
    p = _pilot(lines=[Line(path=[STARYU, MEGA], payoff=MEGA)])
    active = {"id": STARYU, "energies": [], "hp": 10}         # doomed
    obs = _obs([], [{"id": W_ENERGY}], [_attach(0, ACTIVE, 0)], active=active,
               opp_active={"id": MEGA, "hp": 330})
    row = _row_for(p.explain(obs).attach_working, 0)
    assert row["doomed"] is True and row["build"] > 0.0


# --- the burst family -----------------------------------------------------------------------

@pytest.mark.req("REQ-ATTACH-DECIDER-0013")
def test_burst_units_are_the_printed_provision_and_a_lethal_unlock_is_spent():
    """Ignition provides {C}{C}{C} on an EVOLUTION — a card fact, counted honestly at 3 units and
    never bent by opponent HP. Against a 200-HP Active the burst reaches Nebula Beam 210 where the
    reusable Basic reaches only Jetting Blow 120, so the no-KO cap lifts and the burst is spent."""
    p = _pilot()
    active = {"id": MEGA, "energies": [W_ENERGY], "hp": 330}
    obs = _obs([], [{"id": IGNITION}, {"id": W_ENERGY}],
               [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0)], active=active,
               opp_active={"id": MEGA, "hp": 200})
    w = p.explain(obs).attach_working
    assert _row_for(w, 0)["units"] == 3
    assert _row_for(w, 0)["this_turn"] > _row_for(w, 1)["this_turn"]
    assert p.explain(obs).chosen == [0]


@pytest.mark.req("REQ-ATTACH-DECIDER-0014")
def test_the_no_ko_cap_conserves_the_burst_when_the_basic_does_the_same_job():
    """Same board, a 300-HP wall neither attack can KO: the burst's tonight-credit is capped at the
    reusable Basic's, so the resource tie-break sends the Basic in and keeps the one-shot."""
    p = _pilot()
    active = {"id": MEGA, "energies": [W_ENERGY], "hp": 330}
    obs = _obs([], [{"id": IGNITION}, {"id": W_ENERGY}],
               [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0)], active=active,
               opp_active={"id": MEGA, "hp": 300})
    w = p.explain(obs).attach_working
    assert _row_for(w, 0)["units"] == 3                       # units stay HONEST — only credit is capped
    assert _row_for(w, 0)["this_turn"] == _row_for(w, 1)["this_turn"]
    assert _row_for(w, 0)["tactical"] < _row_for(w, 1)["tactical"]   # the resource tie-break
    assert p.explain(obs).chosen == [1]


@pytest.mark.req("REQ-ATTACH-DECIDER-0015")
def test_an_uncashable_burst_scores_below_ending_the_turn():
    """Turn 1 going first cannot attack, so the Ignition is discarded having powered nothing: the
    evaporation gate makes the marginal MINUS the burst's worth — End wins, with no −60 rung."""
    p = _pilot()
    active = {"id": MEGA, "energies": [], "hp": 330}
    obs = _obs([], [{"id": IGNITION}], [_attach(0, ACTIVE, 0), {"type": END}],
               active=active, turn=1)
    row = _row_for(p.explain(obs).attach_working, 0)
    assert row["evaporates"] is True and row["marginal"] < 0 and row["tactical"] < 0
    assert p.explain(obs).chosen != [0]


@pytest.mark.req("REQ-ATTACH-DECIDER-0016")
def test_a_benched_burst_evaporates_and_banks_no_channel():
    """The evaporation gate is GLOBAL: a card leaving play at end of turn banks nothing durable —
    not build, not mobility — even on a body whose slots it would have filled."""
    p = _pilot()
    bench = [{"id": MEGA, "energies": [], "hp": 330}]
    row = _row_for(_pilot().explain(_obs(bench, [{"id": IGNITION}],
                                         [_attach(0, BENCH, 0)])).attach_working, 0)
    assert row["evaporates"] is True
    assert (row["attack_axis"], row["retreat_equity"], row["ability_fuel"]) == (0.0, 0.0, 0.0)
    assert row["marginal"] < 0
    assert p is not None


# --- ordering, degraded mode, sparsity -------------------------------------------------------

@pytest.mark.req("REQ-ATTACH-DECIDER-0017")
def test_development_sequences_before_the_attach_and_the_attach_before_a_hand_shuffle():
    """`attach-energy-last` is now a decide()-only ORDERING deferral (ADR-0069 §7), tier-aware: free
    development first (it may reveal a better target), then the irreversible attach, then the
    hand-nuke that would otherwise shuffle the held Energy away. Score-invisible — the attach keeps
    its full marginal, which is what freed the desperation floor from out-scoring a −5."""
    active = {"id": MEGA, "energies": [W_ENERGY, W_ENERGY], "hp": 330}
    # The attach out-SCORES the hand-nuke, and is still taken FIRST rather than instead: the tiers
    # order, they do not suppress.
    shuffle_obs = _obs([], [{"id": W_ENERGY}, {"id": SHUFFLE}],
                       [_attach(0, ACTIVE, 0), {"type": PLAY, "area": HAND, "index": 1}],
                       active=active)
    assert _pilot().explain(shuffle_obs).chosen == [0]
    # ... and an endorsed free development step is taken BEFORE the irreversible attach, even though
    # the attach scores far higher — the deferral is ORDERING, not weight.
    accel_obs = _obs([], [{"id": W_ENERGY}, {"id": BALL}],
                     [_attach(0, ACTIVE, 0), {"type": PLAY, "area": HAND, "index": 1}],
                     active=active)
    p = _pilot(functions=CardFunctions({IGNITION: ignition_tags(), SHUFFLE: ["shuffle_hand"],
                                        BALL: ["energy_accel"]}))
    dec = p.explain(accel_obs)
    assert dec.options[0].score > dec.options[1].score > 0    # the attach scores higher …
    assert dec.chosen == [1]                                  # … and the development still goes first


@pytest.mark.req("REQ-ATTACH-DECIDER-0018")
def test_the_kill_switch_off_is_degraded_mode_not_a_rollback():
    """OFF, the attach tactical contributes exactly zero and no attach endorsement fires — the rungs
    it replaced are DELETED, so there is nothing to fall back to. An incident lever, not a baseline."""
    off = _pilot(attach_value=False)
    bench = [{"id": MEGA, "energies": [W_ENERGY, W_ENERGY], "hp": 330},
             {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": W_ENERGY}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    dec = off.explain(obs)
    assert all(t.tactical == 0.0 and t.score == 0.0 for t in dec.options)
    assert dec.attach_working is not None                    # the working still emits (reporting)
    assert all(r["tactical"] != 0 for r in dec.attach_working["eq"])   # ... priced, but not scored


@pytest.mark.req("REQ-ATTACH-DECIDER-0019")
def test_the_working_is_silent_off_an_attach_menu_and_mid_sim():
    p = _pilot()
    obs = _obs([{"id": STARYU, "energies": [], "hp": 70}], [{"id": W_ENERGY}],
               [{"type": RETREAT}, {"type": END}])
    assert p.explain(obs).attach_working is None
    attach_obs = _obs([{"id": STARYU, "energies": [], "hp": 70}], [{"id": W_ENERGY}],
                      [_attach(0, BENCH, 0)])
    assert p.explain(attach_obs).attach_working is not None   # ONE option still gets a working row
    p._planning = True
    assert p.explain(attach_obs).attach_working is None


@pytest.mark.req("REQ-ATTACH-DECIDER-0020")
def test_the_counterfactual_credits_only_what_the_attach_uniquely_adds():
    """A body that already reaches its attack on the Energy it holds earns no tonight-credit for one
    more — the delta of two reachable-damage reads, not a flat readiness bump."""
    p = _pilot()
    active = {"id": MEGA, "energies": [W_ENERGY], "hp": 330}   # Jetting Blow already payable
    obs = _obs([], [{"id": P_ENERGY}], [_attach(0, ACTIVE, 0)], active=active,
               opp_active={"id": MEGA, "hp": 330})
    row = _row_for(p.explain(obs).attach_working, 0)
    assert row["this_turn"] == 0.0                            # a {P} unlocks nothing Jetting can't do
    assert _ATTACH_VALUE_SCALE > 0


# ---------------------------------------------------------------- Style B: corpus replay

def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _frame(ep, fr):
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089)."""
    from corpus_helpers import corpus_record
    return corpus_record(ep, fr)


def _agent(rec) -> str:
    """The shared replay fallback. It is no longer papering over a missing `agent` — `from_dict`
    backfills that from `agent_build`, and `('82227388', 7)` below is one of the 40 records the raw
    walk dropped. It survives for the corpus's one `SkiChu` record, which has no agent dir."""
    from corpus_helpers import replay_agent
    return replay_agent(rec)


# The ATTACH the decider must rank first at each frame, on decider semantics — its own lane, which is
# what this family owns. WHEN in the turn that attach is taken is the ordering deferral's business and
# turn planning's beyond it (at 83037962-48 an endorsed development PLAY is correctly taken first and
# the attach follows on a later frame), so pinning "is it in `chosen` HERE" would pin the sequencer,
# not the decider. "none" means the decider declines to attach at all: no priced option is worth
# taking, and none is.
#
# Targets are compared by resolved SLOT (area, position), never the raw option index: duplicate
# energy-source options and identical-effect target copies otherwise read as false disagreements
# (82523811-59, 82750161-59). Every entry either AGREED with the retired pile in the decider-mode
# sweep or is a ruled FIX — the migrated pin corpus, re-asserted on what the decider DOES rather than
# on an agreement bit it no longer has.
_CORPUS = {
    ("82227388", 7): "none",             # an all-Tool menu: nothing here is Energy
    ("86088989", 63): (BENCH, 2),        # over-attach: no 3rd Energy on a 2-cost Lucario (ruled FIX)
                                         #   — Aura Jab ctx 21; see the Issue #425 family below
    ("86089638", 18): None,              # on-type onto the Dreepy line — assert against `correct`
    ("83037962", 48): None,              # doomed-DON'T-feed: 2 on a body needing 3 that dies = 0
                                         #   (an endorsed development PLAY correctly precedes it)
    ("82749168", 61): None,              # concentrate on the started (2-Energy) carrier
    ("82523811", 59): (ACTIVE, 0),       # build the survivable 400-HP ACTIVE carrier (ruled FIX)
    ("83664340", 45): (ACTIVE, 0),       # arm the doomed Active with the attack it unlocks TONIGHT
    ("82750161", 59): (BENCH, 0),        # overkill cap -> develop the benched second threat
    ("83037962", 70): None,              # feed the accelerator (Turbo Flare routes 3)
    ("84889539", 87): None,              # route to the Riolu line, not a partnerless Solrock
                                         #   — Aura Jab ctx 21; see the Issue #425 family below
    ("82525101", 69): (ACTIVE, 0),       # go down swinging: the bench Mega cannot pay its retreat
    ("83007714", 65): "none",            # ... but here it CAN: retreat into it, don't feed the doomed
    # Turbo Flare's recipient pick (ctx 21) on a bench of SAME-SPECIES bodies at different charge
    # levels — the accel shape `is_from` was built for, and no ruled test covered it (Issue #417 B3).
    ("83007714", 22): None,              # spread to the EMPTY Mega ex, not the started Staryu ...
    ("83116081", 21): None,              # ... but CONCENTRATE onto the started Staryu over a fresh
                                         #   one: convexity, and the harder of the two directions
    ("82224509", 31): None,              # don't over-attach a body that is already 3/3 — ruled
                                         #   2026-08-06 (Issue #417 B1), see the module note below
}


@pytest.mark.req("REQ-ATTACH-DECIDER-0021")
@pytest.mark.parametrize("ep,fr", list(_CORPUS))
def test_corpus_decision(ep, fr):
    expected = _CORPUS[(ep, fr)]
    rec = _frame(ep, fr)
    dec = _tune()._build_pilot(_agent(rec))[0].explain(rec.obs)
    # Read the decision through the decider's OWN working rows, so an ATTACH_FROM recipient pick (a
    # type-3 _CARD option) is compared exactly as a type-8 ATTACH is.
    rows = (dec.attach_working or {}).get("eq", ())
    by_index = {r["i"]: tuple(r["slot"]) for r in rows}
    if expected == "none":
        assert all(r["tactical"] <= 0 for r in rows), \
            f"{ep}-{fr}: expected the decider to decline, got {[r['tactical'] for r in rows]}"
        assert not {i for i in dec.chosen if i in by_index}, f"{ep}-{fr}: attached anyway"
        return
    assert rows, f"{ep}-{fr}: the decider priced nothing"
    top = max(rows, key=lambda r: r["tactical"])
    assert top["tactical"] > 0, f"{ep}-{fr}: the decider declined, expected {expected}"
    if expected is None:
        expected = {by_index[i] for i in (rec.correct or []) if i in by_index}
        assert tuple(top["slot"]) in expected, f"{ep}-{fr}: {top['slot']} not in correct {expected}"
    else:
        assert tuple(top["slot"]) == expected, f"{ep}-{fr}: {top['slot']} != {expected}"


@pytest.mark.req("REQ-ATTACH-DECIDER-0022")
def test_accel_routing_drives_the_feed_not_the_accelerators_own_attack():
    """83037962-70: feeding the Active Cinderace wins because Turbo Flare ROUTES ~3 Basic onto the
    survivable bench carrier (a full Nebula build) — NOT because of Cinderace's own 50 attack."""
    rec = _frame("83037962", 70)
    dec = _tune()._build_pilot(_agent(rec))[0].explain(rec.obs)
    picked = max(dec.attach_working["eq"], key=lambda r: r["tactical"])
    assert picked["target"] == 666                            # Cinderace, the accelerator
    assert picked["accel_value"] > picked["this_turn"]


@pytest.mark.req("REQ-ATTACH-DECIDER-0023")
def test_the_working_is_silent_on_a_supporter_selection_frame():
    """85786096-70: a WHICH-SUPPORTER decision. Every option is _PLAY; there is no ATTACH, so the
    decider prices nothing and stays silent rather than pretending to own the frame."""
    rec = _frame("85786096", 70)
    assert _tune()._build_pilot(_agent(rec))[0].explain(rec.obs).attach_working is None


# ------------------------------------------------- Turbo Flare's two selects (Issue #417, Part B)
#
# Cinderace's Turbo Flare — *"Search your deck for up to 3 Basic Energy cards and attach them to
# your Benched Pokémon in any way you like"* (`data/EN_Card_Data.csv` 666, read at source) — poses
# `ATTACH_TO` (22, WHICH Energy cards) and then, per card, `ATTACH_FROM` (21, WHICH bench body).
#
# Issue #417 set out to build a decider for both and found ctx 21 ALREADY BUILT: `_attach_value`'s
# `is_from` branch (ADR-0069) prices the recipient by convex, typed slot-fraction progress, live and
# unconditional. Its correctness on this exact accel shape — several same-species bench recipients
# at different charge levels — had never been asserted, only observed. The two `_CORPUS` entries
# above are that assertion; what follows is the part the `_CORPUS` table cannot carry.

CINDERACE, TURBO_FLARE_CTX = 666, 22
# `W_ENERGY`/`F_ENERGY` above are Style A synthetics that happen to carry the REAL card ids these
# tests need — Water Energy is card id 3 and Basic {F} Energy is card id 6 (`data/EN_Card_Data.csv`,
# checked at source). Reused deliberately rather than re-spelled, but noted because the coincidence
# is the exact one `pilot_helpers.poke` warns about and it does NOT hold for every Energy.


def test_the_82224509_31_legs_are_the_convexity_and_not_a_coincidence():
    """`82224509-31`, the frame whose record was RE-RULED on 2026-08-06 (Issue #417 B1).

    As committed it contradicted itself: the ``rationale`` — *"dont attach more energy on a pokemon
    than it needs. Mega Starmie already had 3 basic energy, therefor should have attached on the
    other benched mon without any energy"* — names index 1, the only bench body with no Energy,
    while `correct` recorded index 0, the already-3/3 Mega Starmie ex. Three independent facts said
    `correct` was the stale field (the embedded ``live_trace`` records ``chosen: [0]``; the
    rationale resolves only to index 1; the shipped decider already picks index 1), and the
    developer ruled it `[1]`. The `_CORPUS` entry above now asserts the ranking.

    ⚠️ **`correct == chosen` was NOT the defect**, recorded because the tempting shortcut is wrong
    and would break a shipped ruling: that shape is deliberately supported on a MANDATORY select
    here — `tests/train/test_unstatable_decline_records.py::test_a_mandatory_select_is_never_
    excluded_even_when_chosen_equals_correct` reads it as *the pick was right*, and 13 committed
    records still rely on it. Only the rationale conflict made this frame different.

    What this test adds beyond the `_CORPUS` ranking is the WORKING: the pick is the convex build
    delta doing its job, not a tie broken by luck. The already-3/3 Mega ex prices at exactly 0.0 —
    there is no build progress left to buy — so the margin is structural."""
    _rec, _dec, rows = _replay_rows("82224509", 31)
    assert rows, "the decider priced nothing at a ctx-21 select"
    assert max(rows.values(), key=lambda r: r["tactical"])["i"] == 1
    assert rows[0]["tactical"] == 0.0        # the already-3/3 Mega ex: no build left to buy
    assert rows[1]["tactical"] > 0.0


def test_every_real_turbo_flare_attach_to_menu_is_copies_of_one_basic_energy():
    """B4's premise, MEASURED. Both real Turbo Flare `ATTACH_TO` steps in the committed corpus are
    `minCount`/`maxCount` 0/3 over `area=DECK` options that resolve to copies of a SINGLE Basic
    Energy card — so the menu holds nothing to rank and taking the first `min(3, offered)` is
    correct by construction rather than by a rule.

    The tripwire half: a capture that ever poses a mixed-colour Turbo Flare menu makes this fail,
    which is the moment ctx 22 stops being moot for this card."""
    steps = parity_selects(TURBO_FLARE_CTX, effect_id=CINDERACE)
    assert len(steps) == 2
    for name, index, sel in steps:
        assert (sel["minCount"], sel["maxCount"]) == (0, 3), f"{name} f{index}"
        deck = sel.get("deck") or []
        ids = {(deck[o["index"]] or {}).get("id") for o in sel["option"]
               if o.get("area") == _DECK and 0 <= o["index"] < len(deck)}
        assert {o.get("area") for o in sel["option"]} == {_DECK}, f"{name} f{index}"
        assert len(ids) == 1, f"{name} f{index}: mixed-colour Turbo Flare menu {sorted(ids)}"


def _turbo_flare_attach_to(rec, *, energy_id, offered):
    """`83007714`'s REAL Turbo Flare board with the ctx-21 recipient select replaced by the ctx-22
    Energy select the engine poses one step earlier — the two real ctx-22 Turbo Flare boards in the
    corpus belong to a foreign Fire deck, so the mono-colour claim has to be posed on ours."""
    import copy
    obs = copy.deepcopy(rec.obs)
    yi = obs["current"]["yourIndex"]
    obs["select"] = {
        "type": _CARD, "context": TURBO_FLARE_CTX, "minCount": 0, "maxCount": 3,
        "option": [{"type": _CARD, "area": _DECK, "index": i, "playerIndex": yi}
                   for i in range(offered)],
        "deck": [{"id": energy_id, "serial": 900 + i, "playerIndex": yi} for i in range(offered)],
        "remainDamageCounter": 0, "remainEnergyCost": 0, "contextCard": None,
        "effect": {"id": CINDERACE, "serial": 1, "playerIndex": yi},
    }
    return obs


@pytest.mark.parametrize("offered,expected", [(2, [0, 1]), (5, [0, 1, 2])])
def test_turbo_flare_takes_min_three_and_remaining_at_the_energy_select(offered, expected):
    """B4. `ATTACH_TO` is not in `_GRAB_CONTEXTS`, so `_greedy_grab` never fires and the ordinary
    ``order[:max_count]`` path takes the first `min(3, offered)`. With every option an
    interchangeable Water Energy and nothing scoring negative, taking all of them is what a free,
    no-downside search should do — asserted so a future rung that starts scoring here has to say
    so out loud."""
    rec = _frame("83007714", 22)
    obs = _turbo_flare_attach_to(rec, energy_id=W_ENERGY, offered=offered)
    assert _tune()._build_pilot(_agent(rec))[0].explain(obs).chosen == expected


def test_the_off_colour_demotion_is_silent_on_this_mono_colour_deck_and_fires_when_it_should():
    """B4's second half, WITH ITS POSITIVE CONTROL. `attach-off-color-at-fixed-recipient` is the one
    surviving `_ATTACH_TO` rung and its own rationale says it is *"silent for a mono-colour deck
    (every colour on-board)"*. mega_starmie's only Basic Energy is Water (`deck.txt`: *9 Water
    Energy SVE 3*; Ignition is a Special and no Turbo Flare target), so it can never fire here.

    A silence assertion alone would pass against a rung that had been deleted, so the same board is
    posed a second time with a Fighting Energy: the rung then fires at its full −8. That is the
    control that makes the silence mean something (CLAUDE.md)."""
    rec = _frame("83007714", 22)
    pilot = _tune()._build_pilot(_agent(rec))[0]

    def _fired(energy_id):
        obs = _turbo_flare_attach_to(rec, energy_id=energy_id, offered=3)
        board = pilot._board(obs)
        trace = pilot._option_trace(obs, obs["select"], board, obs["select"]["option"][0], 0)
        return [h.id for h, _w in trace.fired], trace.score

    on_colour, on_score = _fired(W_ENERGY)
    off_colour, off_score = _fired(F_ENERGY)
    assert "attach-off-color-at-fixed-recipient" not in on_colour and on_score == 0.0
    assert "attach-off-color-at-fixed-recipient" in off_colour and off_score == -8.0


# --------------------------------- Aura Jab's bench-load (Issue #425, sub-issue of epic Issue #421)
#
# Mega Lucario ex's Aura Jab — *"Attach up to 3 Basic {F} Energy cards from your discard pile to your
# Benched Pokémon in any way you like"* (`data/EN_Card_Data.csv` 678, read at source) — poses the
# SAME `ATTACH_FROM` (21) recipient select as Cinderace's Turbo Flare above, differing only in source
# zone (discard, a visible zone, so no odds machinery) and in `target: bench_only` (which the engine
# encodes in the menu it offers, so no gate reads it).
#
# Two `assumed` deck rungs used to decide this select, both authored off `ml` f87 and both claiming a
# tie broken by option index:
#
#   `aurajab-skip-partnerless-solrock` (−20) — *"all bench targets tied at `spread-attach-to-the-needy`
#                                              +15 → index picked Solrock"*
#   `aurajab-load-the-wincon-line`     (+10) — *"`concentrate-accel-on-one-line-body` did not resolve
#                                              to the bare 0-Energy Riolu here"*
#
# **Both are RETIRED**, measured 2026-08-06 against `origin/main` @ `e8141b8` before any edit.
#
# The validation base is **2/2 gradeable, 3 raw**. ADR-0121 Decision 0 binds here — *a follow-up
# select is only gradeable if the MAIN decision that opened it was correct* — so the base was run
# through `train.grab_sweep._off_policy` FIRST: of the three ruled 678 ctx-21 frames, `85058574-121`
# is off-policy (two earlier ruled blunders on the same turn) and is excluded, while `84889539-87`
# and `86088989-63` are clean. Excluding it costs the argument nothing: it is also the one frame
# where neither rung ever fired.
#
# On that base, all 70 committed mega_lucario Corrections replayed through the shipped Pilot and
# through the same Pilot with the two ids filtered out of `strategy.hypotheses` moved **zero**
# decisions; agreement was identical on both arms at 50/64 by `satisfies_human` (49/64 strict) — 64,
# not 70, because six records are prose-only and carry no `correct` to grade. The two rungs were
# observed FIRING in the shipped arm on exactly the two gradeable frames, which is the positive
# control that makes "nothing moved" mean something. The facts they encoded were already computed:
# `_partner_absent` for the inert Solrock, and `_line_payoff_stat` + `_build_standing`'s convex
# `(matched/slots)**2` for the line preference.
#
# `src/common/pilot.py` is UNCHANGED by that retirement — this family covers the equation that was
# already there, on the frames the rungs were written for.

# Card facts VERIFIED at source (data/EN_Card_Data.csv, 2026-08-06).
RIOLU = 677                         # Basic; Mega Lucario ex's ONLY previous stage. Retreat 2
MEGA_LUCARIO_EX = 678               # Stage 1 from Riolu; Aura Jab {F} 130 / Mega Brave {F}{F} 270
_AURAJAB_RUNGS = {"aurajab-skip-partnerless-solrock", "aurajab-load-the-wincon-line"}


def _replay_rows(ep, fr):
    """`(record, decision, {option index: working row})` for a replayed corpus frame.

    The decider's own working rows, keyed by option index — the same read the four `ATTACH_FROM`
    assertions below and `test_the_82224509_31_legs_...` above all need."""
    rec = _frame(ep, fr)
    dec = _tune()._build_pilot(_agent(rec))[0].explain(rec.obs)
    return rec, dec, {r["i"]: r for r in (dec.attach_working or {}).get("eq", ())}


def test_both_aurajab_rungs_are_retired_from_the_deck_strategy():
    """The retirement itself, so nothing re-adds either id quietly.

    POSITIVE CONTROL (CLAUDE.md): the same harvest is asserted to still find
    `attach-solrock-over-line-base` — the deck's OTHER attach rung, which survives because it breaks a
    benched Solrock-vs-Line-base tie at a type-8 `ATTACH`, a seam this ctx-21 work never touched. An
    absence assertion against a strategy that failed to load would otherwise pass for the wrong
    reason."""
    ids = {h.id for h in _tune()._build_pilot("mega_lucario")[0].strategy.hypotheses}
    assert not (_AURAJAB_RUNGS & ids), f"retired rungs are back: {sorted(_AURAJAB_RUNGS & ids)}"
    assert "attach-solrock-over-line-base" in ids, "the deck strategy did not load — control failed"


def test_aura_jab_routes_to_the_wincon_line_over_a_partnerless_solrock():
    """`84889539-87` (**ml f87**, CRITICAL) — the board BOTH retired rungs cite, decided by the
    equation alone. *"Solrock is worthless without a Lunatone in play."*

    My bench is Solrock / Makuhita / Solrock / Riolu, all at 0 Energy, and there is no Lunatone
    anywhere in play — Cosmic Beam is *"If you don't have Lunatone on your Bench, this attack does
    nothing"* (`data/EN_Card_Data.csv` 676, read at source), so both Solrocks are inert.

    `_partner_absent` is read on the RECIPIENT leg of `_attach_value` — it is one disjunct of
    `non_attacking`, keyed on the target's card id, and `role_gated = non_attacking and
    attacker_alternative` (so it is necessary here, not sufficient in general: the Riolu is the
    alternative that lets the gate close at all). Each Solrock therefore comes back `role_gated`, its
    honestly-computed `build` of 70.0 zeroed out of the attack axis with only Retreat Equity
    surviving. The Riolu keeps its build: `_line_payoff_stat` resolves it to Mega Lucario ex, whose
    Mega Brave is `{F}{F}` for 270 (source), so one Energy is (1/2)**2 * 270 * the pre-evo discount.

    This is acceptance criterion 5 of Issue #425: the partnerless Solrock prices **strictly below** the
    wincon-line pre-evolution, with no rung in the sum."""
    rec, dec, rows = _replay_rows("84889539", 87)
    assert dec.chosen == rec.correct == [3]
    solrock = [r for r in rows.values() if r["target"] == SOLROCK]
    riolu = rows[3]
    assert len(solrock) == 2 and riolu["target"] == RIOLU
    for r in solrock:
        assert r["role_gated"] is True                  # `_partner_absent`: no Lunatone in play
        assert r["attack_axis"] == 0.0 and r["build"] > 0.0   # computed, then gated — not unseen
        assert r["tactical"] < riolu["tactical"]
    assert riolu["role_gated"] is False and riolu["build"] > 0.0


def test_a_solrock_with_its_lunatone_is_the_top_pick_the_control_for_f87s_zero():
    """The POSITIVE CONTROL for the frame above, taken from the corpus rather than synthesised.

    `86088989-63` puts the SAME card (Solrock, 676) at the same ctx-21 select on a bench that DOES
    hold a Lunatone. The role gate stands down, the identical Cosmic Beam build of 70.0 reaches the
    attack axis, and that body becomes the decider's pick. So f87's zero is `_partner_absent` doing
    its job, not Solrock being priced at zero everywhere."""
    _, dec, rows = _replay_rows("86088989", 63)
    solrock = rows[2]
    assert solrock["target"] == SOLROCK
    assert solrock["role_gated"] is False and solrock["attack_axis"] > 0.0
    assert max(rows.values(), key=lambda r: r["tactical"])["i"] == 2
    assert dec.chosen == [2]


def test_aura_jab_does_not_hand_a_third_energy_to_a_two_cost_riolu():
    """`86088989-63` (CRITICAL) — *"Why give a third energy to Riolu/Lucario who need only 2??"*

    The Riolu on this bench already carries 2 Energy and Mega Brave costs `{F}{F}` (source), so
    `_build_standing` is already at `(2/2)**2` of the payoff and the delta a third Energy buys is
    **exactly 0.0** — the same structural zero as the already-3/3 Mega Starmie ex at `82224509-31`.
    Retreat Equity is 0.0 too (Riolu's printed Retreat is 2 and is already funded), so the whole row
    is 0.0.

    The retired `aurajab-load-the-wincon-line` was actively WRONG here: it fired `+10` on this option
    and lifted a correctly-computed 0.0 to 10.0. Removing it widened the correct answer's margin from
    63.0 to 64.0."""
    _, _, rows = _replay_rows("86088989", 63)
    riolu = rows[3]
    assert riolu["target"] == RIOLU
    assert riolu["build"] == 0.0 and riolu["retreat_equity"] == 0.0 and riolu["tactical"] == 0.0


def test_the_678_validation_base_is_two_of_three_and_names_which_one_is_off_policy():
    """The base this retirement rests on, measured rather than assumed — **2/2 gradeable, 3 raw**.

    ADR-0121 Decision 0: *a follow-up select is only gradeable if the MAIN decision that opened it
    was correct*. An `ATTACH_FROM` menu exists only because the agent attacked with Aura Jab, so if
    that turn's earlier play was itself ruled a blunder, the board is one the agent should never have
    reached and a Correction filed on it is not evidence about the recipient pick.

    `85058574-121` is exactly that: two earlier ruled Corrections on the SAME turn 10 (`f114`
    wrong_attack, `f109` other, both MAIN). Its own rationale says the same thing from the other
    direction — *"TURN-PLANNER scope, NOT the single-turn energy oracle"* — and the record is
    `scope="turn"`. It is EXCLUDED, not failed, and excluding it costs the retirement nothing: it is
    also the one frame of the three where neither retired rung ever fired.

    POSITIVE CONTROL, required because this test's headline is an absence: the same detector is
    pointed at the ctx-7 base, where ADR-0121 measured 15 of 31 off-policy. A detector that has gone
    quiet would otherwise certify every frame as clean.

    A test asserting the two survivors' DECISIONS is above; this one asserts only who is in the base
    and who is not. Delete it the day the Turn Planner reaches `85058574-121` and the record stops
    being off-policy — do NOT relax it into grading that frame."""
    from train.blunder.store import load_corrections
    from train.grab_sweep import _off_policy

    corrs = load_corrections(str(REPO / "data" / "corrections"))
    by_ep: dict = {}
    for c in corrs:
        by_ep.setdefault((c.agent, c.episode_id), []).append(c)

    def _ctx(c):
        return ((c.obs or {}).get("select") or {}).get("context")

    def _effect(c):
        return (((c.obs or {}).get("select") or {}).get("effect") or {}).get("id")

    base = {f"{c.episode_id}-{(c.decision or {}).get('frame')}": _off_policy(c, by_ep)
            for c in corrs if c.obs and _ctx(c) == 21 and _effect(c) == MEGA_LUCARIO_EX}
    assert set(base) == {"84889539-87", "85058574-121", "86088989-63"}, f"base moved: {sorted(base)}"
    assert not base["84889539-87"] and not base["86088989-63"]        # the two the equation is graded on
    assert base["85058574-121"], "the off-policy frame stopped being flagged — re-rule the base"

    flagged7 = [c for c in corrs if c.obs and _ctx(c) == 7 and _off_policy(c, by_ep)]
    assert flagged7, "CONTROL FAILED: the detector flags nothing at ctx 7 either — it is broken"
