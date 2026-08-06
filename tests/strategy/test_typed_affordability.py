"""Typed affordability for the shared KO valuation (`_best_affordable_ko_value` / `_develop_wins`).

The count-only check (`attack_costs[aid] <= energy`) credits a colorless-only provider (Ignition
Energy {C}{C}{C}) with funding SPECIFIC-type cost slots it can never pay (Jetting Blow's {W}) — a
phantom KO/lethal in closed form. `Pilot._attack_type_payable` (AttackStat.energyTypes) closes it
SOUND-OR-SILENT: suppress only on a PROVABLY unmet specific slot; an unresolvable attack record, a
unit code this build's enum does not know, and unknown-type budget (a planned attach) all stay
fail-open. Lib-free synthetic obs via pilot_helpers.

**The bodies here are written in ENERGY UNITS** (`cg/api.py` `Pokemon.energies` is
`list[EnergyType]`), which is what the engine actually hands the agent — so an attached Ignition
Energy is `[COLORLESS, COLORLESS, COLORLESS]`, not `[17, 17, 17]`. They used to be written as card
ids, and that read as *"three units of type 17"*: outside the enum, therefore WILD, therefore
covering the very {W} slot this file exists to prove is unpayable. It passed only because the
production code made the same mistake in the same direction (Issue #297). The old
`energies=[0]*n` "unresolvable placeholder" is gone with it — 0 is COLORLESS, a specific and
perfectly payable answer for a colourless slot, and the fail-open case is now an unknown CODE.
"""
import pytest

from card_facts import ignition_tags                    # the committed Ignition Energy tags, ONE copy
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
WATER = 3           # Basic {W} Energy — card id 3, and EnergyType.WATER is also 3
IGNITION = 17       # Special Energy, provides {C}{C}{C} only (energyType 0)
OPP = 678

# The UNITS a body reports, per attached card (`cg.api.EnergyType`). The distinction the file rests
# on: `IGNITION` is a CARD id and never appears in `energies`; what appears is what it PROVIDES.
COLORLESS = 0
_W_UNITS = (WATER,)                 # one Basic {W} Energy provides one {W}
_IGNITION_UNITS = (COLORLESS,) * 3  # one Ignition Energy provides {C}{C}{C}
UNKNOWN_UNIT = 99                   # not an EnergyType this build knows — the fail-OPEN case

JETTING = 11        # {W}{C}{C} -> energyTypes (3, 0, 0)
TURBO = 20          # {C} -> untyped


def _stats(attacks=None):
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, synthetic=True, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=120,
                         maxDamageCost=3, minAttackCost=3, minCostDamage=120, attacks=(JETTING,),
                         evolvesFrom="Staryu", energyType=3),
        CINDER: CardStat(CINDER, name="Cinderace", hp=160, maxDamage=50, maxDamageCost=1,
                         minAttackCost=1, minCostDamage=50, attacks=(TURBO,), energyType=2),
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
        IGNITION: CardStat(IGNITION, name="Ignition Energy", hp=0, energyType=0),
        OPP: CardStat(OPP, synthetic=True, name="opp", hp=100),
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
                 functions=CardFunctions({IGNITION: ignition_tags()}), **kw)


def _body(*units):
    """A body carrying these Energy UNITS — the engine's ``Pokemon.energies``, EnergyType codes.

    Stated as units rather than cards because that is what the affordability family reads, and
    because the card→unit expansion is not 1:1: ONE Ignition Energy is the whole of
    ``_IGNITION_UNITS``, three colourless."""
    return {"id": WINCON, "energies": list(units)}


def _ko(pilot, body=None, energy=3, **kw):
    board = Board(my_active_id=WINCON, my_active_energy=energy)
    return pilot._best_affordable_ko_value({}, board, {"id": OPP, "hp": 100}, WINCON, energy,
                                           body=body, **kw)


# ------------------------------------------------- the phantom: colorless can't fund a {W} slot
@pytest.mark.req("REQ-GEN-0068")
def test_colorless_only_energies_never_fund_a_typed_slot():
    """One Ignition meets Jetting Blow's COUNT (its {C}{C}{C} is 3 units) but not its {W} slot —
    KO value must be 0."""
    assert _ko(_pilot(), body=_body(*_IGNITION_UNITS)) == 0.0


@pytest.mark.req("REQ-GEN-0068")
def test_typed_slot_met_keeps_the_real_ko():
    """{W} + two colourless units covers {W}{C}{C} — the genuine KO is untouched."""
    assert _ko(_pilot(), body=_body(*_W_UNITS, COLORLESS, COLORLESS)) >= KO_SCORE


# ------------------------------------------------- sound-or-silent: every unprovable case stays open
@pytest.mark.req("REQ-GEN-0068")
def test_no_body_keeps_the_legacy_count_only_check():
    """body=None (legacy callers): count-only, unchanged."""
    assert _ko(_pilot(), body=None) >= KO_SCORE


@pytest.mark.req("REQ-GEN-0068")
def test_an_unknown_unit_code_is_wild():
    """A unit code outside this build's `EnergyType` — a later set's enum member — MIGHT be the {W},
    so it stays fail-open. This is the whole of the wild case now: `energies=[0]*3` used to be read
    as "unresolvable, therefore wild" and is really three COLORLESS units, which are resolvable and
    provably cannot pay a {W} (Issue #297) — that board is the test above."""
    assert _ko(_pilot(), body=_body(UNKNOWN_UNIT, UNKNOWN_UNIT, UNKNOWN_UNIT)) >= KO_SCORE


@pytest.mark.req("REQ-GEN-0068")
def test_unknown_type_budget_is_wild():
    """Energy budget beyond the attached cards (a planned attach of unknown type) covers the one
    missing {W} — fail-open (the hand might hold it)."""
    assert _ko(_pilot(), body=_body(COLORLESS, COLORLESS), energy=3) >= KO_SCORE


@pytest.mark.req("REQ-GEN-0068")
def test_unresolvable_attack_record_is_silent():
    """No energyTypes on the attack record (the legacy-synth shape) -> the count check stays the
    sole authority."""
    pilot = _pilot(attack_stats={})
    assert _ko(pilot, body=_body(*_IGNITION_UNITS)) >= KO_SCORE


# ------------------------------------------------- known-type extras (the modelled attach)
@pytest.mark.req("REQ-GEN-0068")
def test_ignition_modelled_as_the_attach_cannot_fund_the_typed_slot():
    """The develop-tier shape: bare body + Ignition's CCC=3 as the planned attach reaches the
    count but provably not the {W} — suppressed (extra_type=0 pays colourless slots only)."""
    assert _ko(_pilot(), body=_body(), extra_type=0, extra_units=3) == 0.0


@pytest.mark.req("REQ-GEN-0068")
def test_water_modelled_as_the_attach_funds_the_typed_slot():
    """Same shape with the {W} as the planned attach — the KO stands."""
    assert _ko(_pilot(), body=_body(COLORLESS, COLORLESS), extra_type=3, extra_units=1) >= KO_SCORE


@pytest.mark.req("REQ-GEN-0068")
def test_unknown_type_extra_stays_wild():
    """An extra whose card can't be resolved (extra_type=None) MIGHT be the {W} — it must stay
    wild (fail-open), unlike a provably-colourless extra_type=0."""
    assert _ko(_pilot(), body=_body(COLORLESS, COLORLESS), extra_type=None,
               extra_units=1) >= KO_SCORE


# ------------------------------------------------- behavioral: the retreat lookahead
@pytest.mark.req("REQ-GEN-0068")
def test_retreat_lethal_stands_down_on_a_colorless_funded_wincon():
    """A benched wincon 'ready' by COUNT (one Ignition, {C}{C}{C}) cannot actually pay Jetting
    Blow's {W}: the retreat carries no KO-class value. The spent Active (Turbo 50 vs 100 HP) can't
    KO either, so only a GENUINELY payable wincon justifies the retreat-lethal."""
    pilot = _pilot()
    bench_wincon = poke(WINCON, hp=330, attached_energy=[(IGNITION, _IGNITION_UNITS)])
    cur = state(active=poke(CINDER, energy=1, hp=160), bench=[bench_wincon],
                opp_active=poke(OPP, hp=100))
    obs = make_select([attack_opt(TURBO), opt(RETREAT), opt(END)], context=0, current=cur)
    assert pilot.explain(obs).options[1].tactical < KO_SCORE      # no phantom retreat-lethal

    # Control: swap the Ignition for a Basic {W} plus two colourless -> the lethal is genuine again.
    bench_wincon["energies"] = [WATER, COLORLESS, COLORLESS]
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
                                   body=_body(*_IGNITION_UNITS))
    assert pilot._develop_wins({}, board, opp, WINCON, 3,
                               body=_body(*_W_UNITS, COLORLESS, COLORLESS))
