"""The spend/ability LINE ACCOUNT — `planner._line_account`.

The account credits USING a beneficial setup ability and subtracts a wasteful spend, reusing the live
tuned weights (`OptionTrace.fired`); the sign filter drops a positive spend-id or a negative
ability-id. The readiness LEAF this module also carried was deleted with the develop rung (Issue
Issue #386); `state_value`'s `readiness` family is the successor.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.context import KO_SCORE
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.strategy.strategy import Line

F = 6                    # a specific Energy type code ({F}-like); non-zero so it is "typed"
P = 7                    # a different specific type (for the off-type test)

# --- a small mega_lucario-shaped fixture: Riolu -> Mega Lucario ex, Solrock/Lunatone engine ----------
RIOLU = 333              # weak win-condition pre-evo (own 30 chip << the Mega it becomes)
MEGA = 678               # the payoff (Stage 1 ex)
LUNATONE = 675           # pure draw engine (Ability, `engine` Role, untagged — role-declared)
SOLROCK = 676            # engine + secondary attacker (the Lunar-Cycle partner)
JUNK = 800               # a role-less filler Basic with NO attack
ENERGY_F = 6             # a Basic {F} Energy card id
ENERGY_P = 7             # a Basic {P} Energy card id (off-type for the Riolu/Mega line)

_ATTACKS = {
    3330: AttackStat(3330, damage=30, cost=1, energyTypes=(F,)),      # Riolu's weak self-chip
    6780: AttackStat(6780, damage=130, cost=1, energyTypes=(F,)),     # Mega Lucario Aura Jab
    6781: AttackStat(6781, damage=270, cost=2, energyTypes=(F, F)),   # Mega Lucario Mega Brave
    6760: AttackStat(6760, damage=70, cost=1, energyTypes=(F,)),      # Solrock Cosmic Beam
    6750: AttackStat(6750, damage=50, cost=2, energyTypes=(F, F)),    # Lunatone Power Gem
}
AIR_BALLOON = 1174       # retreat-reduction Tool ("{C}{C} less" -> retreatReduction=2, parsed at source)
SWITCH = 1123            # Switch Item ("Switch your Active Pokémon with 1 of your Benched Pokémon")
_STATS = {
    # retreat costs mirror the REAL cards (EN_Card_Data.csv: Riolu 2, Mega Lucario ex 2, Lunatone 1,
    # Solrock 1) — the promotion-ease lift reads them, so the fixture must carry them.
    RIOLU: CardStat(RIOLU, synthetic=True, name="riolu", hp=70, energyType=F, evolvesFrom=None, attacks=(3330,),
                    minAttackCost=1, maxDamage=30, retreatCost=2),
    MEGA: CardStat(MEGA, synthetic=True, name="mega lucario ex", hp=340, energyType=F, evolvesFrom="riolu",
                   attacks=(6780, 6781), minAttackCost=1, maxDamage=270, megaEx=True, retreatCost=2),
    LUNATONE: CardStat(LUNATONE, synthetic=True, name="lunatone", hp=110, energyType=F, attacks=(6750,),
                       minAttackCost=2, maxDamage=50, hasAbility=True, retreatCost=1),
    SOLROCK: CardStat(SOLROCK, synthetic=True, name="solrock", hp=110, energyType=F, attacks=(6760,),
                      minAttackCost=1, maxDamage=70, retreatCost=1),
    JUNK: CardStat(JUNK, synthetic=True, name="junk", hp=60, energyType=F, attacks=(), retreatCost=1),
    ENERGY_F: CardStat(ENERGY_F, synthetic=True, name="fighting energy", hp=0, cardType=5, energyType=F),
    ENERGY_P: CardStat(ENERGY_P, synthetic=True, name="psychic energy", hp=0, cardType=5, energyType=P),
    AIR_BALLOON: CardStat(AIR_BALLOON, synthetic=True, name="air balloon", hp=0, cardType=2, retreatReduction=2),
    SWITCH: CardStat(SWITCH, synthetic=True, name="switch", hp=0, cardType=1),
}
_ROLES = {MEGA: ["win_condition", "primary_attacker"], RIOLU: ["win_condition_base"],
          SOLROCK: ["secondary_attacker", "engine"], LUNATONE: ["engine"]}
_LINES = [Line(path=[RIOLU, MEGA], payoff=MEGA, role="win_condition")]


def _pilot(roles=None, lines=None, functions=None):
    stats = DictCardStatProvider(dict(_STATS), dict(_ATTACKS))
    return Pilot(Strategy(roles=roles if roles is not None else dict(_ROLES),
                          lines=lines if lines is not None else list(_LINES)),
                 deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions(functions if functions is not None else {}))


def _body(cid, energy=(), **kw):
    return {"id": cid, "energies": list(energy), "hp": _STATS[cid].hp, **kw}


class _Hyp:
    def __init__(self, hid):
        self.id = hid


class _Trace:
    def __init__(self, fired, attach_spend=0.0):
        self.fired = fired
        self.attach_spend = attach_spend


# The readiness LEAF's sixteen tests are DELETED with `planner._readiness` and its helpers (Issue
# Issue #386); every fact they carried is re-homed in test_state_value.py, except the one guarded below.


@pytest.mark.req("REQ-PLANNER-0011")
def test_the_active_slot_worth_gap_is_still_DECLARED_by_the_successor_family():
    """Three deleted tests priced the Active slot's worth; `readiness` does not, by decision, and
    says so in `blind_to`. A declared gap is a ruling — but only if something reads the declaration."""
    from common.state_value import REGISTRY
    readiness = next(f for f in REGISTRY if f.name == "readiness")
    blind = " ".join(readiness.blind_to)
    assert "VALUE of the Active slot" in blind
    assert "promote_retreat_value" in blind, (
        "the Active-slot worth gap no longer names the instrument that carries it — either the gap "
        "closed (delete this test and assert the new behaviour) or the pointer rotted")


# --- the line account (spend / ability-fire), reusing the live tuned weights ----------------------
@pytest.mark.req("REQ-PLANNER-0011")
def test_line_account_credits_ability_fire_and_subtracts_spend():
    """A fired ability-USE rule adds its positive weight, a fired spend rule subtracts its magnitude,
    a rule in neither set is ignored. Every id here must be a LIVE member — `_Hyp` accepts any string."""
    p = _pilot()
    traces = [
        _Trace([(_Hyp("fire-lunar-cycle"), 15.0)]),                 # ability fire → +15
        _Trace([(_Hyp("dont-rush-evolve-without-target"), -60.0)]),  # spend → -60
        _Trace([(_Hyp("attach-before-hand-shuffle"), 15.0)]),       # LIVE, in neither set → 0
    ]
    assert p._line_account(traces, [0]) == 15.0
    assert p._line_account(traces, [1]) == -60.0
    assert p._line_account(traces, [2]) == 0.0
    assert p._line_account(traces, [0, 1]) == pytest.approx(-45.0)


@pytest.mark.req("REQ-PLANNER-0011")
def test_line_account_subtracts_the_attach_deciders_evaporation_spend():
    """ADR-0069: a one-shot Energy attached where it buys nothing before end of turn is the decider's
    EVAPORATION LOSS on `OptionTrace.attach_spend`, replacing the five deleted `discard_eot` rungs."""
    p = _pilot()
    traces = [_Trace([]), _Trace([])]
    traces[1].attach_spend = -30.0
    assert p._line_account(traces, [0]) == 0.0
    assert p._line_account(traces, [1]) == -30.0
    assert p._line_account(traces, [0, 1]) == -30.0


@pytest.mark.req("REQ-PLANNER-0011")
def test_line_account_ignores_wrong_sign():
    """Only NEGATIVE spend weights and POSITIVE ability-fire weights count. Both legs must name ids
    that ARE members, or the zero is attributable to the SET rather than to the sign (ADR-0132)."""
    p = _pilot()
    from common.strategy.planner import _ABILITY_FIRE_IDS, _CLASS_B_SPEND_IDS
    assert "dont-search-a-probable-whiff" in _CLASS_B_SPEND_IDS      # the premise, not decoration
    assert "fire-lunar-cycle" in _ABILITY_FIRE_IDS
    traces = [_Trace([(_Hyp("dont-search-a-probable-whiff"), 5.0),   # positive spend-id → ignored
                      (_Hyp("fire-lunar-cycle"), -3.0)])]            # negative ability-id → ignored
    assert p._line_account(traces, [0]) == 0.0
