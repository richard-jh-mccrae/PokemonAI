"""The spend/ability LINE ACCOUNT — `planner._line_account` (`docs/plans/t0-planner-disposition.md`).

This module used to carry the readiness leaf as well: `_readiness` was the engine-sim leaf's
positional term (MY-side "how close am I to executing my win"), and `_line_account` its path term, in
`turn_value = readiness(end) + Σ ability-fire credits − Σ spend costs`. **POC-T4/5 (Issue #386)
deleted the readiness half** along with the develop rung whose leaf it was; `state_value`'s
`readiness` family is the successor, and the block below the imports is the fact-by-fact audit of
where each of the sixteen deleted tests went — including the one gap that has no successor and is
declared rather than lost.

`_line_account` itself is untouched. It survives with a live caller in `_simulate_line`, which is
retired as a RUNTIME rollout but kept as the offline engine primitive `family_diag`, the cgpy↔native
agreement lane and the determinism backstop all drive. What it asserts is unchanged: the account
credits USING a beneficial setup ability and subtracts a wasteful spend, reusing the live tuned
weights (`OptionTrace.fired`), and the sign filter drops a positive spend-id or a negative
ability-id.
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


# --- attack readiness: the gate, progress, position, type-awareness -------------------------------
# ── the readiness LEAF's internals — DELETED (POC-T4/5, Issue #386) ──────────────────────────────
#
# Sixteen tests lived here, over `planner._readiness` and its helpers (`_attack_readiness`,
# `_ability_readiness`, `_readiness_saturation`, `_bench_position_w`, `_promotion_ease`,
# `_active_quality`, `_ability_precondition_met`). Every one of those symbols is deleted with the
# develop rung whose leaf they composed. `state_value`'s `readiness` family is the successor, and its
# own registry entry names the incumbent it ports (`planner._READINESS_ATTACK_W`,
# `planner._ability_readiness`, `_READINESS_ABILITY_VALUE`) — so this is a re-home, not a loss.
#
# WHERE EACH FACT WENT — the audit, not a hand-wave:
#
#   the reachable-attack GATE ................. `_may_attack_now`, asserted in test_state_value.py
#                                               (Issue #351 took the legality half: a benched body no
#                                               longer claims it can attack this turn)
#   Active-out readies the same body benched .. test_state_value.py, funded_successor/funded_active
#   type-awareness, off-type earns nothing .... test_state_value.py, the Ignition/water pair
#   a weak pre-evo credits its REACHABLE payoff  `StateModel.attack_payoff` — the best attack the body
#                                               can pay off ON THIS BOARD, not printed `maxDamage`
#                                               (ADR-0109), asserted in test_state_value.py
#   ability readiness needs its partner ....... test_state_value.py, the Lunatone companion trio
#   capped below one prize .................... test_state_value.py, the readiness scale band
#
# WHAT HAS NO SUCCESSOR, AND IS DECLARED RATHER THAN LOST:
#
#   the bench-POSITION weight, `_promotion_ease`, and the active-quality credit priced the WORTH of
#   the Active slot. `readiness.blind_to` names exactly that as unpriced — *"what stays unpriced is
#   the slot's WORTH"* — with `promote_retreat_value` named as the instrument that carries it and
#   `survival` as where it composes. The guard below asserts the declaration is still there, so the
#   gap can neither close silently nor widen silently.
#
# The `_line_account` tests below are NOT affected: that method survives, with a live caller in
# `_simulate_line` (planner.py), which is retired as a RUNTIME rollout but kept as the offline
# engine primitive the instruments drive.


@pytest.mark.req("REQ-PLANNER-0011")
def test_the_active_slot_worth_gap_is_still_DECLARED_by_the_successor_family():
    """The one thing the sixteen deleted tests leave behind that nothing else would catch.

    Three of them priced the Active slot's worth (bench position, promotion ease, active quality).
    `state_value`'s `readiness` does not, by decision rather than by oversight, and says so in
    `blind_to`. A declared gap is a ruling; an undeclared one is a regression, and the difference is
    invisible unless something reads the declaration."""
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
    """`_line_account` is the signed path term: a fired ability-USE rule (`fire-lunar-cycle`) adds its
    positive weight; a fired spend rule (`dont-waste-clutch-heal`) subtracts its magnitude; a rule
    NOT in either set is ignored; the sign filter drops a positive spend-id / negative ability-id."""
    p = _pilot()
    traces = [
        _Trace([(_Hyp("fire-lunar-cycle"), 15.0)]),                 # ability fire → +15
        _Trace([(_Hyp("dont-waste-clutch-heal"), -60.0)]),          # spend → -60
        _Trace([(_Hyp("hold-position-in-setup"), 15.0)]),           # not a line rule → 0
    ]
    assert p._line_account(traces, [0]) == 15.0
    assert p._line_account(traces, [1]) == -60.0
    assert p._line_account(traces, [2]) == 0.0
    assert p._line_account(traces, [0, 1]) == pytest.approx(-45.0)


@pytest.mark.req("REQ-PLANNER-0011")
def test_line_account_subtracts_the_attach_deciders_evaporation_spend():
    """The five `discard_eot` rungs the spend account used to read are DELETED (#139, ADR-0069): a
    one-shot Energy attached where it buys nothing before end of turn is now the decider's EVAPORATION
    LOSS, carried on `OptionTrace.attach_spend`. Same referent (a consumed card, invisible on the end
    board), same account — so a line that torches an Ignition still costs what it spent."""
    p = _pilot()
    traces = [_Trace([]), _Trace([])]
    traces[1].attach_spend = -30.0
    assert p._line_account(traces, [0]) == 0.0
    assert p._line_account(traces, [1]) == -30.0
    assert p._line_account(traces, [0, 1]) == -30.0


@pytest.mark.req("REQ-PLANNER-0011")
def test_line_account_ignores_wrong_sign():
    """The classification guard: only NEGATIVE spend weights and POSITIVE ability-fire weights count — a
    positive spend-id firing (a correct 'hold') and a negative ability-id are both ignored."""
    p = _pilot()
    traces = [_Trace([(_Hyp("dont-waste-discard-energy"), 5.0),      # positive spend-id → ignored
                      (_Hyp("fire-lunar-cycle"), -3.0)])]            # negative ability-id → ignored
    assert p._line_account(traces, [0]) == 0.0
