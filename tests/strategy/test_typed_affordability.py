"""Typed affordability for the shared KO valuation (`_best_affordable_ko_value` / `_develop_wins`).

The count-only check (`attack_costs[aid] <= energy`) credits a colorless-only provider (Ignition
Energy {C}{C}{C}) with funding SPECIFIC-type cost slots it can never pay (Jetting Blow's {W}) — a
phantom KO/lethal in closed form. `Pilot._attack_type_payable` (AttackStat.energyTypes) closes it
SOUND-OR-SILENT: suppress only on a PROVABLY unmet specific slot; unresolvable attack records,
unresolvable attached Energy, and unknown-type budget (a planned attach) all stay fail-open, so a
count-only fixture (energies=[0]*n) never changes behavior. Lib-free synthetic obs via pilot_helpers.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Board, KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from pilot_helpers import attack_opt, make_select, opt, poke, state

RETREAT = 12
END = 14
WINCON = 900        # Mega Starmie ex shape: Jetting Blow {W}{C}{C} 120
CINDER = 666        # spent opener (1-cost colorless attack)
WATER = 3           # Basic {W} Energy (energyType 3)
IGNITION = 17       # Special Energy, provides {C}{C}{C} only (energyType 0)
OPP = 678

JETTING = 11        # {W}{C}{C} -> energyTypes (3, 0, 0)
TURBO = 20          # {C} -> untyped


def _stats(attacks=None):
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=120,
                         maxDamageCost=3, minAttackCost=3, minCostDamage=120, attacks=(JETTING,),
                         evolvesFrom="Staryu", energyType=3),
        CINDER: CardStat(CINDER, name="Cinderace", hp=160, maxDamage=50, maxDamageCost=1,
                         minAttackCost=1, minCostDamage=50, attacks=(TURBO,), energyType=2),
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
        IGNITION: CardStat(IGNITION, name="Ignition Energy", hp=0, energyType=0),
        OPP: CardStat(OPP, name="opp", hp=100),
    }, attacks=attacks)


# cost/damage-only records (the old legacy-dict synth shape, no energyTypes — fail-open on type)
_SYNTHS = {JETTING: AttackStat(JETTING, damage=120, cost=3),
           TURBO: AttackStat(TURBO, damage=50, cost=1)}
# the full typed records the tests exercise by default
_TYPED = {JETTING: AttackStat(JETTING, damage=120, cost=3, energyTypes=(3, 0, 0)),
          TURBO: AttackStat(TURBO, damage=50, cost=1, energyTypes=(0,))}


def _pilot(attack_stats=None, **kw):
    explicit = _TYPED if attack_stats is None else attack_stats
    merged = {**_SYNTHS, **explicit}       # explicit records win; synths fill the remaining ids
    return Pilot(Strategy(roles={WINCON: ["win_condition", "primary_attacker"]}, lines=[]),
                 deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(merged),
                 functions=CardFunctions({IGNITION: ["discard_eot"]}), **kw)


def _body(energies):
    return {"id": WINCON, "energies": energies}


def _ko(pilot, body=None, energy=3, **kw):
    board = Board(my_active_id=WINCON, my_active_energy=energy)
    return pilot._best_affordable_ko_value({}, board, {"id": OPP, "hp": 100}, WINCON, energy,
                                           body=body, **kw)


# ------------------------------------------------- the phantom: colorless can't fund a {W} slot
@pytest.mark.req("REQ-GEN-0068")
def test_colorless_only_energies_never_fund_a_typed_slot():
    """3x Ignition meets Jetting Blow's COUNT (3) but not its {W} slot — KO value must be 0."""
    assert _ko(_pilot(), body=_body([IGNITION, IGNITION, IGNITION])) == 0.0


@pytest.mark.req("REQ-GEN-0068")
def test_typed_slot_met_keeps_the_real_ko():
    """W + 2x Ignition covers {W}{C}{C} — the genuine KO is untouched."""
    assert _ko(_pilot(), body=_body([WATER, IGNITION, IGNITION])) >= KO_SCORE


# ------------------------------------------------- sound-or-silent: every unprovable case stays open
@pytest.mark.req("REQ-GEN-0068")
def test_no_body_keeps_the_legacy_count_only_check():
    """body=None (legacy callers): count-only, unchanged."""
    assert _ko(_pilot(), body=None) >= KO_SCORE


@pytest.mark.req("REQ-GEN-0068")
def test_unresolvable_attached_energy_is_wild():
    """A fixture-style body (energies=[0]*3, unresolvable ids) MIGHT hold the {W} — fail-open."""
    assert _ko(_pilot(), body=_body([0, 0, 0])) >= KO_SCORE


@pytest.mark.req("REQ-GEN-0068")
def test_unknown_type_budget_is_wild():
    """Energy budget beyond the attached cards (a planned attach of unknown type) covers the one
    missing {W} — fail-open (the hand might hold it)."""
    assert _ko(_pilot(), body=_body([IGNITION, IGNITION]), energy=3) >= KO_SCORE


@pytest.mark.req("REQ-GEN-0068")
def test_unresolvable_attack_record_is_silent():
    """No energyTypes on the attack record (the legacy-synth shape) -> the count check stays the
    sole authority."""
    pilot = _pilot(attack_stats={})
    assert _ko(pilot, body=_body([IGNITION, IGNITION, IGNITION])) >= KO_SCORE


# ------------------------------------------------- known-type extras (the modelled attach)
@pytest.mark.req("REQ-GEN-0068")
def test_ignition_modelled_as_the_attach_cannot_fund_the_typed_slot():
    """The develop-tier shape: bare body + Ignition's CCC=3 as the planned attach reaches the
    count but provably not the {W} — suppressed (extra_type=0 pays colourless slots only)."""
    assert _ko(_pilot(), body=_body([]), extra_type=0, extra_units=3) == 0.0


@pytest.mark.req("REQ-GEN-0068")
def test_water_modelled_as_the_attach_funds_the_typed_slot():
    """Same shape with the {W} as the planned attach — the KO stands."""
    assert _ko(_pilot(), body=_body([IGNITION, IGNITION]), extra_type=3, extra_units=1) >= KO_SCORE


@pytest.mark.req("REQ-GEN-0068")
def test_unknown_type_extra_stays_wild():
    """An extra whose card can't be resolved (extra_type=None) MIGHT be the {W} — it must stay
    wild (fail-open), unlike a provably-colourless extra_type=0."""
    assert _ko(_pilot(), body=_body([IGNITION, IGNITION]), extra_type=None, extra_units=1) >= KO_SCORE


# ------------------------------------------------- behavioral: the retreat lookahead
@pytest.mark.req("REQ-GEN-0068")
def test_retreat_lethal_stands_down_on_a_colorless_funded_wincon():
    """A benched wincon 'ready' by COUNT (3x Ignition) cannot actually pay Jetting Blow's {W}:
    the retreat carries no KO-class value. The spent Active (Turbo 50 vs 100 HP) can't KO either,
    so only a GENUINELY payable wincon justifies the retreat-lethal."""
    pilot = _pilot()
    bench_wincon = poke(WINCON, energy=0, hp=330)
    bench_wincon["energies"] = [IGNITION, IGNITION, IGNITION]     # resolvable, colorless-only
    cur = state(active=poke(CINDER, energy=1, hp=160), bench=[bench_wincon],
                opp_active=poke(OPP, hp=100))
    obs = make_select([attack_opt(TURBO), opt(RETREAT), opt(END)], context=0, current=cur)
    assert pilot.explain(obs).options[1].tactical < KO_SCORE      # no phantom retreat-lethal

    # Control: swap one Ignition for the {W} -> the retreat-lethal is genuine again.
    bench_wincon["energies"] = [WATER, IGNITION, IGNITION]
    obs = make_select([attack_opt(TURBO), opt(RETREAT), opt(END)], context=0, current=cur)
    assert pilot.explain(obs).options[1].tactical >= KO_SCORE
    assert pilot.decide(obs) == [1]                               # retreat into the payable wincon


# ------------------------------------------------- behavioral: the win rung's develop tier
@pytest.mark.req("REQ-GEN-0068")
def test_develop_wins_rejects_the_type_unpayable_ko():
    """`_develop_wins` (the family's shared develop-tier win test) forwards the body: a last-prize
    KO that the attacker provably can't type-pay is no win line."""
    pilot = _pilot()
    board = Board(my_active_id=WINCON, my_active_energy=3, my_prizes_remaining=1, opp_bench=())
    opp = {"id": OPP, "hp": 100}
    assert not pilot._develop_wins({}, board, opp, WINCON, 3,
                                   body=_body([IGNITION, IGNITION, IGNITION]))
    assert pilot._develop_wins({}, board, opp, WINCON, 3,
                               body=_body([WATER, IGNITION, IGNITION]))
