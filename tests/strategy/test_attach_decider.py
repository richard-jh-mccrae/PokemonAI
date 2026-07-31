"""The ATTACH DECIDER (#139, ADR-0069) — the axes-sum marginal that DECIDES every energy attach.

Successor to `test_attach_shadow.py`. The oracle it pins no longer shadows anything: the 19 rungs it
replaced are deleted, so every assertion here is about EXTERNAL BEHAVIOUR — the decision made at a
select, the axes values on the decision's working record, and the order picks come out in. Nothing
asserts a helper's internals, a matcher's call pattern, or suppressed-rung bookkeeping.

Two styles:
  * Style A — synthetic hand-built boards pin the ruled TERMS deterministically (including the four
    grill synthetics, the burst family, the ordering deferral and degraded mode).
  * Style B — replay committed correction frames and assert the DECISION, on decider semantics.
"""
import importlib.util
from pathlib import Path

import pytest

from common.cards import CardFunctions
from common.pilot import (Pilot, _ATTACH_ABILITY_FUEL, _ATTACH_RETREAT_EQUITY, _ATTACH_VALUE_SCALE)
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.strategy.strategy import Line
from common.telemetry import to_record

REPO = Path(__file__).resolve().parents[2]

ATTACH, HAND, ACTIVE, BENCH, MAIN = 8, 2, 4, 5, 0
END, RETREAT, PLAY = 14, 12, 7
_TOOL, _BASIC_ENERGY, _SPECIAL_ENERGY = 2, 5, 6
# EnergyType codes (src/cg/api.py): 3 = WATER, 5 = PSYCHIC, 6 = FIGHTING, 7 = DARKNESS.
WATER, PSYCHIC, FIGHTING, DARK = 3, 5, 6, 7

MEGA, STARYU, IGNITION, CAPE = 1031, 1030, 17, 1100
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
GNAW = 107                          # TEF Dunsparce: ● 10, NO retreat cost


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
        DUNSPARCE: CardStat(DUNSPARCE, name="Dunsparce", hp=60, maxDamage=10, minCostDamage=10,
                            minAttackCost=1, maxDamageCost=1, retreatCost=0, attacks=(GNAW,)),
        W_ENERGY: CardStat(W_ENERGY, name="Water", cardType=_BASIC_ENERGY, energyType=WATER),
        P_ENERGY: CardStat(P_ENERGY, name="Psychic", cardType=_BASIC_ENERGY, energyType=PSYCHIC),
        F_ENERGY: CardStat(F_ENERGY, name="Fighting", cardType=_BASIC_ENERGY, energyType=FIGHTING),
        D_ENERGY: CardStat(D_ENERGY, name="Darkness", cardType=_BASIC_ENERGY, energyType=DARK),
        IGNITION: CardStat(IGNITION, name="Ignition", cardType=_SPECIAL_ENERGY, energyType=0),
        CAPE: CardStat(CAPE, name="Hero's Cape", cardType=_TOOL, aceSpec=True, hpBonus=100),
        SHUFFLE: CardStat(SHUFFLE, name="Iono", cardType=4),
        BALL: CardStat(BALL, name="Ultra Ball", cardType=3),
    }, attacks={
        JETTING: AttackStat(JETTING, damage=120, cost=1, energyTypes=(WATER,)),
        NEBULA: AttackStat(NEBULA, damage=210, cost=3, energyTypes=(0, 0, 0)),
        WATER_GUN: AttackStat(WATER_GUN, damage=20, cost=1, energyTypes=(WATER,)),
        POWER_GEM: AttackStat(POWER_GEM, damage=50, cost=2, energyTypes=(FIGHTING, FIGHTING)),
        COSMIC_BEAM: AttackStat(COSMIC_BEAM, damage=70, cost=1, energyTypes=(FIGHTING,)),
        MIND_BEND: AttackStat(MIND_BEND, damage=60, cost=2, energyTypes=(PSYCHIC, 0)),
        GNAW: AttackStat(GNAW, damage=10, cost=1, energyTypes=(0,)),
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
        {IGNITION: ["discard_eot"], SHUFFLE: ["shuffle_hand"]})
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
    """Grill synthetic 1 — the tempo case the rung layer structurally lost: its arm exemption was
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
    """Grill synthetic 2 — the desperation floor. A lone Lunatone (engine-only Role, partner absent)
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
    """Grill synthetic 3 — Munkidori: Mind Bend costs {P}●, Adrena-Brain wants a {D}. The {D} fills
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
    """Grill synthetic 4 — the f21 lesson survives the mobility channel. TEF Dunsparce has NO printed
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
    p = _pilot(functions=CardFunctions({IGNITION: ["discard_eot"], SHUFFLE: ["shuffle_hand"],
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
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-TEMP-243)."""
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
    ("86089638", 18): None,              # on-type onto the Dreepy line — assert against `correct`
    ("83037962", 48): None,              # doomed-DON'T-feed: 2 on a body needing 3 that dies = 0
                                         #   (an endorsed development PLAY correctly precedes it)
    ("82749168", 61): None,              # concentrate on the started (2-Energy) carrier
    ("82523811", 59): (ACTIVE, 0),       # build the survivable 400-HP ACTIVE carrier (ruled FIX)
    ("83664340", 45): (ACTIVE, 0),       # arm the doomed Active with the attack it unlocks TONIGHT
    ("82750161", 59): (BENCH, 0),        # overkill cap -> develop the benched second threat
    ("83037962", 70): None,              # feed the accelerator (Turbo Flare routes 3)
    ("84889539", 87): None,              # route to the Riolu line, not a partnerless Solrock
    ("82525101", 69): (ACTIVE, 0),       # go down swinging: the bench Mega cannot pay its retreat
    ("83007714", 65): "none",            # ... but here it CAN: retreat into it, don't feed the doomed
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
