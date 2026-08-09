"""The ATTACH DECIDER (Issue #139, ADR-0069) — the axes-sum marginal behind every energy attach.

Everything asserted here is EXTERNAL behaviour: the decision at a select, the axes on the decision's
working record, the order picks come out in. Style A builds boards by hand; Style B replays corpus
frames.
"""
import importlib.util
from pathlib import Path

import pytest

from card_facts import ignition_tags
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
WATER, PSYCHIC, FIGHTING, DARK = 3, 5, 6, 7     # EnergyType codes, src/cg/api.py

MEGA, STARYU, MEOWTH, IGNITION, CAPE = 1031, 1030, 1071, 17, 1100
W_ENERGY, P_ENERGY, F_ENERGY, D_ENERGY = 3, 5, 6, 7
LUNATONE, SOLROCK = 675, 676        # the co-dependent engine pair (deck-declared partners)
MUNKIDORI, DUNSPARCE = 112, 65      # the Ability-fuel body / the free-retreat draw engine
SHUFFLE = 1200                      # a `shuffle_hand` Supporter
BALL = 1201                         # a free Item dig

# Attack ids — card facts at data/EN_Card_Data.csv.
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


#: Staryu is the win-condition Line's base, which makes it the ATTACKER ALTERNATIVE the role gate
#: reads. Tests needing the gate to STAND DOWN put no alternative in play.
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
    p = _pilot()
    bench = [{"id": MEGA, "energies": [W_ENERGY, W_ENERGY], "hp": 330},
             {"id": STARYU, "energies": [], "hp": 70}]
    dec = p.explain(_obs(bench, [{"id": W_ENERGY}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)]))
    w = dec.attach_working
    assert w is not None and set(w) == {"eq", "abstained"}
    assert "agree" not in w and "eq_pick" not in w
    assert set(w["eq"][0]) >= {"marginal", "tactical", "attack_axis", "this_turn", "build",
                               "accel_value", "retreat_equity", "ability_fuel", "evaporation_loss"}
    assert to_record(dec).get("attach_working") == w
    assert dec.chosen == [0]


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


@pytest.mark.req("REQ-ATTACH-DECIDER-0003")
def test_over_attach_scores_zero_build_on_a_maxed_body():
    p = _pilot()
    bench = [{"id": MEGA, "energies": [W_ENERGY] * 3, "hp": 330},
             {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": W_ENERGY}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    w = p.explain(obs).attach_working
    assert _row_for(w, 0)["build"] == 0.0
    assert _row_for(w, 1)["build"] > 0.0


@pytest.mark.req("REQ-ATTACH-DECIDER-0004")
def test_off_type_waste_is_an_emergent_zero_not_a_flag():
    """Solrock's only attack costs {F}, so a {P} fills no slot: the typed slot-fraction is the flag."""
    p = _pilot()
    bench = [{"id": SOLROCK, "energies": [], "hp": 110}]
    w = p.explain(_obs(bench, [{"id": P_ENERGY}, {"id": F_ENERGY}],
                       [_attach(0, BENCH, 0), _attach(1, BENCH, 0)])).attach_working
    assert _row_for(w, 0)["build"] == 0.0
    assert _row_for(w, 1)["build"] > 0.0


@pytest.mark.req("REQ-ATTACH-DECIDER-0005")
def test_a_colourless_slot_absorbs_any_type():
    """Nebula Beam is ●●●, so an off-colour Energy is real build."""
    p = _pilot()
    bench = [{"id": MEGA, "energies": [W_ENERGY], "hp": 330}]
    w = p.explain(_obs(bench, [{"id": P_ENERGY}], [_attach(0, BENCH, 0)])).attach_working
    assert _row_for(w, 0)["build"] > 0.0


@pytest.mark.req("REQ-ATTACH-DECIDER-0006")
def test_doomed_active_arms_a_non_biggest_attack_over_a_bench_build():
    """ANY attack the attach unlocks tonight counts, not only the biggest."""
    p = _pilot(lines=[Line(path=[STARYU, MEGA], payoff=MEGA)])
    active = {"id": MEGA, "energies": [], "hp": 20}          # doomed: one hit finishes it
    bench = [{"id": MEGA, "energies": [W_ENERGY, W_ENERGY], "hp": 330}]
    obs = _obs(bench, [{"id": W_ENERGY}], [_attach(0, ACTIVE, 0), _attach(0, BENCH, 0)],
               active=active, opp_active={"id": MEGA, "hp": 330})
    w = p.explain(obs).attach_working
    assert _row_for(w, 0)["this_turn"] == 120.0              # Jetting Blow, not Nebula Beam
    assert _row_for(w, 0)["marginal"] > _row_for(w, 1)["marginal"]


@pytest.mark.req("REQ-ATTACH-DECIDER-0007")
def test_lone_utility_body_desperation_attach_beats_ending_the_turn():
    """The desperation floor: a lone engine body is the ONLY legal home, so Retreat Equity floors it."""
    p = _pilot()
    active = {"id": LUNATONE, "energies": [], "hp": 110}
    obs = _obs([], [{"id": W_ENERGY}], [_attach(0, ACTIVE, 0), {"type": END}], active=active)
    w = p.explain(obs).attach_working
    row = _row_for(w, 0)
    assert row["role_gated"] is False
    assert row["retreat_equity"] == _ATTACH_RETREAT_EQUITY   # Lunatone's printed Retreat is 1
    assert row["tactical"] > 0.0
    assert p.explain(obs).chosen == [0]


@pytest.mark.req("REQ-ATTACH-DECIDER-0008")
def test_the_double_duty_colour_beats_the_same_build_alternative_outright():
    """Munkidori: Mind Bend costs {P}●, Adrena-Brain wants a {D}. The {D} fills the colourless slot AND
    wakes the Ability — under a `max` combiner they would TIE; only the additive channel ranks {D} first."""
    p = _pilot(roles={MUNKIDORI: ["counter_mover"]}, partners={}, lines=())
    active = {"id": MUNKIDORI, "energies": [], "hp": 110}
    obs = _obs([], [{"id": D_ENERGY}, {"id": P_ENERGY}],
               [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0)], active=active)
    w = p.explain(obs).attach_working
    dark, psy = _row_for(w, 0), _row_for(w, 1)
    assert dark["build"] == psy["build"]
    assert dark["ability_fuel"] == _ATTACH_ABILITY_FUEL and psy["ability_fuel"] == 0.0
    assert dark["marginal"] > psy["marginal"]


@pytest.mark.req("REQ-ATTACH-DECIDER-0009")
def test_free_retreat_draw_engine_scores_zero_across_every_channel():
    """TEF Dunsparce has NO printed Retreat cost, so Retreat Equity is structurally zero on it; the role
    gate zeroes its attack axis while a real attacker is in play; its Ability wants nothing."""
    p = _pilot(roles={DUNSPARCE: ["engine"], MUNKIDORI: ["counter_mover"],
                      SOLROCK: ["secondary_attacker"]}, partners={}, lines=())
    active = {"id": MUNKIDORI, "energies": [], "hp": 110}
    bench = [{"id": DUNSPARCE, "energies": [], "hp": 60},
             {"id": SOLROCK, "energies": [], "hp": 110}]
    obs = _obs(bench, [{"id": D_ENERGY}], [_attach(0, BENCH, 0), _attach(0, ACTIVE, 0)],
               active=active)
    w = p.explain(obs).attach_working
    dunsparce = _row_for(w, 0)
    assert dunsparce["role_gated"] is True
    assert (dunsparce["attack_axis"], dunsparce["retreat_equity"],
            dunsparce["ability_fuel"], dunsparce["marginal"]) == (0.0, 0.0, 0.0, 0.0)
    assert p.explain(obs).chosen == [1]


@pytest.mark.req("REQ-ATTACH-DECIDER-0010")
def test_the_role_gate_zeros_the_attack_axis_only():
    """The gates land per-axis (ADR-0069 §4): a role-gated body still BANKS mobility and fuel."""
    p = _pilot()
    bench = [{"id": LUNATONE, "energies": [], "hp": 110}, {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": F_ENERGY}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    w = p.explain(obs).attach_working
    lunatone = _row_for(w, 0)
    assert lunatone["role_gated"] is True and lunatone["attack_axis"] == 0.0
    assert lunatone["retreat_equity"] > 0.0
    assert p.explain(obs).chosen == [1]


@pytest.mark.req("REQ-ATTACH-DECIDER-0010")
def test_spent_supporter_tutor_liability_banks_no_mobility_when_an_attacker_exists():
    """Meowth ex's Last-Ditch Catch is an ON-PLAY Bench ability (id 1071), so once the body is in play
    its utility is spent and must not compete with a real attacker for the Energy."""
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


@pytest.mark.req("REQ-ATTACH-DECIDER-0010")
def test_spent_supporter_tutor_desperation_floor_still_exists_when_no_attacker_can_take_it():
    p = _pilot(roles={MEOWTH: []}, partners={}, lines=())
    active = {"id": MEOWTH, "energies": [], "hp": 170}
    obs = _obs([], [{"id": W_ENERGY}], [_attach(0, ACTIVE, 0), {"type": END}], active=active)
    row = _row_for(p.explain(obs).attach_working, 0)
    assert row["spent_utility_gated"] is False
    assert row["tactical"] > 0.0


@pytest.mark.req("REQ-ATTACH-DECIDER-0011")
def test_partnerless_engine_is_gated_and_a_partnered_one_is_not():
    """Board-evaluated: Cosmic Beam does nothing without a benched Lunatone, so Solrock is inert alone."""
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
    assert _row_for(live, 0)["attack_axis"] > 0.0
    assert p.explain(live_obs).chosen == [0]


@pytest.mark.req("REQ-ATTACH-DECIDER-0012")
def test_evolution_escape_keeps_build_on_a_doomed_line_preevolution():
    """Energy carries through evolution, and a Mega evolving does not end the turn."""
    p = _pilot(lines=[Line(path=[STARYU, MEGA], payoff=MEGA)])
    active = {"id": STARYU, "energies": [], "hp": 10}         # doomed
    obs = _obs([], [{"id": W_ENERGY}], [_attach(0, ACTIVE, 0)], active=active,
               opp_active={"id": MEGA, "hp": 330})
    row = _row_for(p.explain(obs).attach_working, 0)
    assert row["doomed"] is True and row["build"] > 0.0


@pytest.mark.req("REQ-ATTACH-DECIDER-0013")
def test_burst_units_are_the_printed_provision_and_a_lethal_unlock_is_spent():
    """Ignition provides {C}{C}{C} on an EVOLUTION — 3 units, never bent by opponent HP. At 200 HP the
    burst reaches Nebula 210 where the Basic reaches only Jetting 120, so the no-KO cap lifts."""
    p = _pilot()
    active = {"id": MEGA, "energies": [W_ENERGY], "hp": 330}
    obs = _obs([], [{"id": IGNITION}, {"id": W_ENERGY}],
               [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0)], active=active,
               opp_active={"id": MEGA, "hp": 200})
    w = p.explain(obs).attach_working
    assert _row_for(w, 0)["units"] == 3
    assert _row_for(w, 0)["this_turn"] > _row_for(w, 1)["this_turn"]


@pytest.mark.req("REQ-ATTACH-DECIDER-0014")
def test_the_no_ko_cap_conserves_the_burst_when_the_basic_does_the_same_job():
    """A 300-HP wall neither attack can KO: the burst's tonight-credit is capped at the Basic's."""
    p = _pilot()
    active = {"id": MEGA, "energies": [W_ENERGY], "hp": 330}
    obs = _obs([], [{"id": IGNITION}, {"id": W_ENERGY}],
               [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0)], active=active,
               opp_active={"id": MEGA, "hp": 300})
    w = p.explain(obs).attach_working
    assert _row_for(w, 0)["units"] == 3
    assert _row_for(w, 0)["this_turn"] == _row_for(w, 1)["this_turn"]
    assert _row_for(w, 0)["tactical"] < _row_for(w, 1)["tactical"]


@pytest.mark.req("REQ-ATTACH-DECIDER-0015")
def test_an_uncashable_burst_scores_below_ending_the_turn():
    """Turn 1 going first cannot attack, so the Ignition is discarded having powered nothing."""
    p = _pilot()
    active = {"id": MEGA, "energies": [], "hp": 330}
    obs = _obs([], [{"id": IGNITION}], [_attach(0, ACTIVE, 0), {"type": END}],
               active=active, turn=1)
    row = _row_for(p.explain(obs).attach_working, 0)
    assert row["evaporates"] is True and row["marginal"] < 0 and row["tactical"] < 0


@pytest.mark.req("REQ-ATTACH-DECIDER-0016")
def test_a_benched_burst_evaporates_and_banks_no_channel():
    """The evaporation gate is GLOBAL: a card leaving play at end of turn banks nothing durable."""
    p = _pilot()
    bench = [{"id": MEGA, "energies": [], "hp": 330}]
    row = _row_for(_pilot().explain(_obs(bench, [{"id": IGNITION}],
                                         [_attach(0, BENCH, 0)])).attach_working, 0)
    assert row["evaporates"] is True
    assert (row["attack_axis"], row["retreat_equity"], row["ability_fuel"]) == (0.0, 0.0, 0.0)
    assert row["marginal"] < 0
    assert p is not None




@pytest.mark.req("REQ-ATTACH-DECIDER-0018")
def test_the_kill_switch_off_is_degraded_mode_not_a_rollback():
    """The rungs it replaced are DELETED, so OFF falls back to nothing: an incident lever, not a baseline."""
    off = _pilot(attach_value=False)
    bench = [{"id": MEGA, "energies": [W_ENERGY, W_ENERGY], "hp": 330},
             {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": W_ENERGY}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    dec = off.explain(obs)
    assert all(t.tactical == 0.0 and t.score == 0.0 for t in dec.options)
    assert dec.attach_working is not None
    assert all(r["tactical"] != 0 for r in dec.attach_working["eq"])


@pytest.mark.req("REQ-ATTACH-DECIDER-0019")
def test_the_working_is_silent_off_an_attach_menu_and_mid_sim():
    p = _pilot()
    obs = _obs([{"id": STARYU, "energies": [], "hp": 70}], [{"id": W_ENERGY}],
               [{"type": RETREAT}, {"type": END}])
    assert p.explain(obs).attach_working is None
    attach_obs = _obs([{"id": STARYU, "energies": [], "hp": 70}], [{"id": W_ENERGY}],
                      [_attach(0, BENCH, 0)])
    assert p.explain(attach_obs).attach_working is not None
    p._planning = True
    assert p.explain(attach_obs).attach_working is None


@pytest.mark.req("REQ-ATTACH-DECIDER-0020")
def test_the_counterfactual_credits_only_what_the_attach_uniquely_adds():
    """The delta of two reachable-damage reads, not a flat readiness bump."""
    p = _pilot()
    active = {"id": MEGA, "energies": [W_ENERGY], "hp": 330}   # Jetting Blow already payable
    obs = _obs([], [{"id": P_ENERGY}], [_attach(0, ACTIVE, 0)], active=active,
               opp_active={"id": MEGA, "hp": 330})
    row = _row_for(p.explain(obs).attach_working, 0)
    assert row["this_turn"] == 0.0
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
    """The shared replay fallback, for the corpus's one `SkiChu` record, which has no agent dir."""
    from corpus_helpers import replay_agent
    return replay_agent(rec)


# The ATTACH the decider must RANK first at each frame; "none" = it declines to attach at all.
# Targets compare by resolved SLOT — raw option indexes read as false disagreements on duplicates.
_CORPUS = {
    ("82227388", 7): "none",             # an all-Tool menu: nothing here is Energy
    ("86088989", 63): (BENCH, 2),        # no 3rd Energy on a 2-cost Lucario (Aura Jab ctx 21)
    ("86089638", 18): None,              # on-type onto the Dreepy line — assert against `correct`
    ("83037962", 48): None,              # doomed-DON'T-feed: 2 on a body needing 3 that dies = 0
    ("82749168", 61): None,              # concentrate on the started (2-Energy) carrier
    ("82523811", 59): (ACTIVE, 0),       # build the survivable 400-HP ACTIVE carrier
    ("83664340", 45): (ACTIVE, 0),       # arm the doomed Active with the attack it unlocks TONIGHT
    ("82750161", 59): (BENCH, 0),        # overkill cap -> develop the benched second threat
    ("83037962", 70): None,              # feed the accelerator (Turbo Flare routes 3)
    ("84889539", 87): None,              # route to the Riolu line, not a partnerless Solrock
    ("82525101", 69): (ACTIVE, 0),       # go down swinging: the bench Mega cannot pay its retreat
    ("83007714", 65): "none",            # ... but here it CAN: retreat into it, don't feed the doomed
    ("83007714", 22): None,              # spread to the EMPTY Mega ex, not the started Staryu ...
    ("83116081", 21): None,              # ... but CONCENTRATE onto the started Staryu: convexity
    ("82224509", 31): None,              # don't over-attach a body that is already 3/3
}


@pytest.mark.req("REQ-ATTACH-DECIDER-0021")
@pytest.mark.parametrize("ep,fr", list(_CORPUS))
def test_corpus_decision(ep, fr):
    expected = _CORPUS[(ep, fr)]
    rec = _frame(ep, fr)
    dec = _tune()._build_pilot(_agent(rec))[0].explain(rec.obs)
    # Through the working rows, so an ATTACH_FROM pick (type-3 _CARD) compares as a type-8 ATTACH does.
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
    """Turbo Flare ROUTES ~3 Basic onto the survivable bench carrier; Cinderace's own 50 attack is not why."""
    rec = _frame("83037962", 70)
    dec = _tune()._build_pilot(_agent(rec))[0].explain(rec.obs)
    picked = max(dec.attach_working["eq"], key=lambda r: r["tactical"])
    assert picked["target"] == 666
    assert picked["accel_value"] > picked["this_turn"]


@pytest.mark.req("REQ-ATTACH-DECIDER-0023")
def test_the_working_is_silent_on_a_supporter_selection_frame():
    rec = _frame("85786096", 70)
    assert _tune()._build_pilot(_agent(rec))[0].explain(rec.obs).attach_working is None


# --- Turbo Flare's two selects (Issue #417 B): Cinderace (666) poses `ATTACH_TO` (22, WHICH Energy)
# then, per card, `ATTACH_FROM` (21, WHICH bench body); `_attach_value`'s `is_from` prices ctx 21.

CINDERACE, TURBO_FLARE_CTX = 666, 22
# `W_ENERGY`/`F_ENERGY` are Style A synthetics that happen to carry the REAL card ids (Water 3,
# Basic {F} 6). Reused deliberately — but the coincidence does NOT hold for every Energy.


def test_the_82224509_31_legs_are_the_convexity_and_not_a_coincidence():
    """Record re-ruled 2026-08-06 (Issue #417 B1). ⚠️ `correct == chosen` was NOT the defect — that
    shape is deliberately supported on a MANDATORY select; only the rationale conflict made this differ."""
    _rec, _dec, rows = _replay_rows("82224509", 31)
    assert rows, "the decider priced nothing at a ctx-21 select"
    assert max(rows.values(), key=lambda r: r["tactical"])["i"] == 1
    assert rows[0]["tactical"] == 0.0
    assert rows[1]["tactical"] > 0.0


def test_every_real_turbo_flare_attach_to_menu_is_copies_of_one_basic_energy():
    """Nothing to rank, so taking the first `min(3, offered)` is correct by construction. TRIPWIRE: a
    capture posing a mixed-colour Turbo Flare menu fails here — the moment ctx 22 stops being moot."""
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
    """A real board with its ctx-21 select swapped for the ctx-22 one posed a step earlier: the corpus's
    only real ctx-22 Turbo Flare boards belong to a foreign Fire deck."""
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
    """`ATTACH_TO` is not in `_GRAB_CONTEXTS`, so `_greedy_grab` never fires and ``order[:max_count]``
    takes the first `min(3, offered)`. A future rung that starts scoring here has to say so out loud."""
    rec = _frame("83007714", 22)
    obs = _turbo_flare_attach_to(rec, energy_id=W_ENERGY, offered=offered)
    assert _tune()._build_pilot(_agent(rec))[0].explain(obs).chosen == expected


def test_global_retirement_keeps_no_off_colour_attach_valuation():
    """Issue #459 globally retires fixed-recipient colour valuations."""
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
    assert "attach-off-color-at-fixed-recipient" not in off_colour and off_score == 0.0


@pytest.mark.req("REQ-ATTACH-DECIDER-0001")
def test_the_decider_still_RANKS_but_no_longer_DECIDES():
    """At a single-pick MAIN menu the sequence composer decides and `attach_value` only prices (Issue
    Issue #386 §9 item 11). Asserted so a change putting the decider back in charge cannot pass silently."""
    p = _pilot()
    active = {"id": MEGA, "energies": [W_ENERGY], "hp": 330}
    obs = _obs([], [{"id": IGNITION}, {"id": W_ENERGY}],
               [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0)], active=active,
               opp_active={"id": MEGA, "hp": 200})
    d = p.explain(obs)
    rows = sorted(d.attach_working["eq"], key=lambda r: -r["tactical"])
    assert rows, "the decider priced nothing — this test is no longer about what it says"
    assert d.planned is not None and d.planned.goal == "compose", (
        "the MAIN pick did not come from the composer; the decider may be back in charge")
    assert d.planned.next_step == list(d.chosen)
# --- Aura Jab's bench-load (Issue #425): 678 poses the SAME `ATTACH_FROM` (21) select as Turbo Flare.
# `_AURAJAB_RUNGS` below are RETIRED — the equation already computed what they encoded.

RIOLU = 677                         # Basic; Mega Lucario ex's ONLY previous stage. Retreat 2
MEGA_LUCARIO_EX = 678               # Stage 1 from Riolu; Aura Jab {F} 130 / Mega Brave {F}{F} 270
HARIYAMA = 674                      # Stage 1 from Makuhita, HP 150; Wild Press {F}{F}{F} 210 (70 self)
_AURAJAB_RUNGS = {"aurajab-skip-partnerless-solrock", "aurajab-load-the-wincon-line"}


def _replay_rows(ep, fr):
    """`(record, decision, {option index: working row})` for a replayed corpus frame."""
    rec = _frame(ep, fr)
    dec = _tune()._build_pilot(_agent(rec))[0].explain(rec.obs)
    return rec, dec, {r["i"]: r for r in (dec.attach_working or {}).get("eq", ())}


def test_both_aurajab_rungs_are_retired_from_the_deck_strategy():
    ids = {h.id for h in _tune()._build_pilot("mega_lucario")[0].strategy.hypotheses}
    assert not (_AURAJAB_RUNGS & ids), f"retired rungs are back: {sorted(_AURAJAB_RUNGS & ids)}"
    assert "attach-solrock-over-line-base" in ids, "the deck strategy did not load — control failed"


def test_aura_jab_routes_to_the_wincon_line_over_a_partnerless_solrock():
    """Cosmic Beam is *"If you don't have Lunatone on your Bench, this attack does nothing"* (676), and
    no Lunatone is in play, so both Solrocks are inert with no rung in the sum (Issue #425 AC 5)."""
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
    """The corpus POSITIVE CONTROL for the frame above: same card, same select, Lunatone present."""
    _, dec, rows = _replay_rows("86088989", 63)
    solrock = rows[2]
    assert solrock["target"] == SOLROCK
    assert solrock["role_gated"] is False and solrock["attack_axis"] > 0.0
    assert max(rows.values(), key=lambda r: r["tactical"])["i"] == 2
    assert dec.chosen == [2]


def test_aura_jab_does_not_hand_a_third_energy_to_a_two_cost_riolu():
    """Mega Brave costs `{F}{F}` and the Riolu already carries 2, so `_build_standing` is at `(2/2)**2`
    and a third Energy buys exactly 0.0; Retreat Equity is 0.0 too (printed Retreat 2, already funded)."""
    _, _, rows = _replay_rows("86088989", 63)
    riolu = rows[3]
    assert riolu["target"] == RIOLU
    assert riolu["build"] == 0.0 and riolu["retreat_equity"] == 0.0 and riolu["tactical"] == 0.0


def test_the_678_validation_base_is_three_of_three_and_the_decider_misses_one():
    """The retirement's validation base (Issue #442); the `85058574-121` miss is PRE-EXISTING and filed
    as Issue #443. Three absences are asserted here, so three positive controls follow them."""
    from train.blunder import off_policy as op
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

    base = {f"{c.episode_id}-{(c.decision or {}).get('frame')}": c
            for c in corrs if c.obs and _ctx(c) == 21 and _effect(c) == MEGA_LUCARIO_EX}
    assert set(base) == {"84889539-87", "85058574-121", "86088989-63"}, f"base moved: {sorted(base)}"
    for key, c in sorted(base.items()):
        assert _off_policy(c, by_ep) == [], f"{key} left the gradeable base — re-rule it"

    # CONTROL 1: GRADEABLE here is a developer RULING over a live candidate, not an empty scan.
    disputed = base["85058574-121"]
    assert [x.frame for x in op.candidates(disputed, by_ep)] == [114], "f114 stopped scanning"
    assert op.RULINGS[op.ruling_key(disputed)].verdict == op.GRADEABLE

    replays = {f"{ep}-{fr}": _replay_rows(ep, fr)
               for ep, fr in (("84889539", 87), ("86088989", 63), ("85058574", 121))}
    agree = {k: sorted(d.chosen or []) == sorted(r.correct or [])
             for k, (r, d, _rows) in replays.items()}
    assert agree == {"84889539-87": True, "86088989-63": True, "85058574-121": False}, agree

    # CONTROL 2: the detector still fires on the ctx-7 population ADR-0121 ruled it on.
    control = op.control(corrs)
    assert control["healthy"], f"CONTROL FAILED: the detector is silent at ctx 7 — {control}"

    # The one miss — Solrock over the ruled Hariyama, no rung in the sum (Issue #443).
    rec, dec, rows = replays["85058574-121"]
    assert dec.chosen == [1] and rec.correct == [3]
    assert rows[1]["target"] == SOLROCK and rows[3]["target"] == HARIYAMA
    assert rows[1]["tactical"] > rows[3]["tactical"]
    # Lunatone IS in play (option 0's own recipient), so `skip-partnerless-solrock` could never fire.
    assert rows[0]["target"] == LUNATONE
    assert RIOLU not in {r["target"] for r in rows.values()}   # ... nor `load-the-wincon-line`
    assert len(dec.options) == 5, "option arity moved — 'no rung fired' would be vacuous"
    assert not any(t.fired for t in dec.options), "a rung fired — the miss is not the equation's"

    # CONTROL 3: the `fired` channel is LIVE — same episode, same agent, same `explain()`.
    _rec114, dec114, _rows114 = _replay_rows("85058574", 114)
    assert any(t.fired for t in dec114.options), \
        "CONTROL FAILED: no rung fires at 85058574-114 either — `fired` is not being populated"
