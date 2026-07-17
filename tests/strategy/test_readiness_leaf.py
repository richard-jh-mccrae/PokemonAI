"""The readiness leaf + spend/ability line account (board-state-valuation-grill.md /
t0-planner-disposition.md, decided 2026-07-16).

The engine-sim leaf's positional term is now `_readiness` (MY-side "how close am I to executing my
win"), replacing `_board_development`, and its line term is `_line_account` (`turn_value =
readiness(end) + Σ ability-fire credits − Σ spend costs`). These tracers pin the leaf's contract as
pure functions over a simmed `me` dict + the fixed Strategy/stats — no engine:

- attack_readiness GATES on a reachable attack (kills "energy anywhere"), is type-aware, position-
  weighted, and evolution-hop-discounted; a WEAK win-condition pre-evo credits only its reachable payoff;
- ability_readiness is CO-EQUAL, precondition-gated (a partner-gated engine needs its partner in play);
- saturation zeroes a 2nd utility/engine body but never an attacker;
- the floor is a binary bench-exists credit; the whole sum stays capped below one prize (KO_SCORE);
- the line account credits USING a beneficial setup ability and subtracts a wasteful spend, reusing the
  live tuned weights (`OptionTrace.fired`).
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
_STATS = {
    RIOLU: CardStat(RIOLU, name="riolu", hp=70, energyType=F, evolvesFrom=None, attacks=(3330,),
                    minAttackCost=1, maxDamage=30),
    MEGA: CardStat(MEGA, name="mega lucario ex", hp=340, energyType=F, evolvesFrom="riolu",
                   attacks=(6780, 6781), minAttackCost=1, maxDamage=270, megaEx=True),
    LUNATONE: CardStat(LUNATONE, name="lunatone", hp=110, energyType=F, attacks=(6750,),
                       minAttackCost=2, maxDamage=50, hasAbility=True),
    SOLROCK: CardStat(SOLROCK, name="solrock", hp=110, energyType=F, attacks=(6760,),
                      minAttackCost=1, maxDamage=70),
    JUNK: CardStat(JUNK, name="junk", hp=60, energyType=F, attacks=()),
    ENERGY_F: CardStat(ENERGY_F, name="fighting energy", hp=0, cardType=5, energyType=F),
    ENERGY_P: CardStat(ENERGY_P, name="psychic energy", hp=0, cardType=5, energyType=P),
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
    def __init__(self, fired):
        self.fired = fired


# --- attack readiness: the gate, progress, position, type-awareness -------------------------------
@pytest.mark.req("REQ-PLANNER-0011")
def test_attack_readiness_gate_zero_without_reachable_attack():
    """A body with NO reachable attack (a role-less Basic with an empty attack list) scores 0 on the
    attack term — THE gate that kills "energy anywhere"."""
    p = _pilot()
    assert p._attack_readiness(_body(JUNK, energy=[ENERGY_F]), {"active": [_body(JUNK)]},
                               is_active=True) == 0.0


@pytest.mark.req("REQ-PLANNER-0011")
def test_active_out_readies_the_same_body_benched():
    """position_w: the SAME attacker with the SAME energy reads higher Active than benched (Active 1.0
    vs the flat bench discount)."""
    p = _pilot()
    me = {"active": [_body(SOLROCK, [ENERGY_F])], "bench": [_body(SOLROCK, [ENERGY_F])]}
    active = p._attack_readiness(_body(SOLROCK, [ENERGY_F]), me, is_active=True)
    bench = p._attack_readiness(_body(SOLROCK, [ENERGY_F]), me, is_active=False)
    assert active > bench > 0.0


@pytest.mark.req("REQ-PLANNER-0011")
def test_progress_is_type_aware_off_type_earns_nothing():
    """Only PAYABLE (type-matched) energy advances progress: a {P} Energy on Solrock (whose Cosmic Beam
    costs {F}) earns zero progress, so a wrong-colour attach is not readiness."""
    p = _pilot()
    on_type = p._attack_readiness(_body(SOLROCK, [ENERGY_F]), {"active": [_body(SOLROCK)]}, is_active=True)
    off_type = p._attack_readiness(_body(SOLROCK, [ENERGY_P]), {"active": [_body(SOLROCK)]}, is_active=True)
    assert on_type > 0.0
    assert off_type == 0.0


@pytest.mark.req("REQ-PLANNER-0011")
def test_weak_preevo_credits_only_a_reachable_payoff():
    """A weak win-condition pre-evo (Riolu 30 << Mega Lucario) credits ONLY its reachable payoff's attack,
    not its own throwaway chip: with the Mega in hand the energized Riolu reads > 0 (progress toward Aura
    Jab); with the payoff undeployable (not in hand/play) it reads 0 — the attach's ~0 gain (scenario 1)."""
    p = _pilot()
    riolu = _body(RIOLU, [ENERGY_F])
    with_payoff = p._attack_readiness(riolu, {"active": [riolu], "hand": [{"id": MEGA}]}, is_active=True)
    without = p._attack_readiness(riolu, {"active": [riolu], "hand": []}, is_active=True)
    assert with_payoff > 0.0
    assert without == 0.0


# --- ability readiness: co-equal, precondition-gated ----------------------------------------------
@pytest.mark.req("REQ-PLANNER-0011")
def test_ability_readiness_engine_role_needs_its_partner():
    """A pure `engine`-Role body's Ability (Lunatone, role-declared/untagged) is precondition-gated: it
    reads 0 alone (a lone engine is inert) and its value with a DISTINCT engine/attacker partner in play
    (Solrock) — Lunar Cycle "if you have Solrock in play"."""
    p = _pilot()
    alone = {"active": [_body(LUNATONE)], "bench": []}
    with_partner = {"active": [_body(LUNATONE)], "bench": [_body(SOLROCK)]}
    assert p._ability_readiness(_body(LUNATONE), alone, is_active=True) == 0.0
    assert p._ability_readiness(_body(LUNATONE), with_partner, is_active=True) > 0.0


@pytest.mark.req("REQ-PLANNER-0011")
def test_ability_readiness_via_function_tag_is_self_sufficient():
    """A body whose Ability the Function Tags DO name (a `draw` tag) is self-sufficient — it reads its
    tag value with no partner needed (Drakloak's Recon Directive)."""
    p = _pilot(functions={LUNATONE: ["draw"]})
    assert p._ability_readiness(_body(LUNATONE), {"active": [_body(LUNATONE)]}, is_active=True) > 0.0


@pytest.mark.req("REQ-PLANNER-0011")
def test_ability_and_attack_are_co_equal_via_max():
    """contribution = max(attack, ability): a body's readiness is the BETTER of its attack and ability
    lines, so an ability-only body still contributes (setup is ability-driven in these decks)."""
    p = _pilot()
    me = {"active": [_body(SOLROCK)], "bench": [_body(LUNATONE)]}
    # Lunatone (0 energy → attack 0) still contributes its ability value with Solrock present
    total = p._readiness(me)
    assert total > 0.0


# --- saturation: a 2nd engine is fodder, a 2nd attacker is not ------------------------------------
@pytest.mark.req("REQ-PLANNER-0011")
def test_saturation_zeroes_a_second_engine_but_not_an_attacker():
    """A 2nd in-play body of the same utility/engine card contributes ~0 (a 2nd Lunatone is fodder);
    two ATTACKERS both accumulate (a 2nd attacker advances the prize race)."""
    p = _pilot()
    seen: set = set()
    first = p._readiness_saturation(_body(LUNATONE), seen)
    second = p._readiness_saturation(_body(LUNATONE), seen)
    assert first == 1.0 and second < 0.2
    seen2: set = set()
    assert p._readiness_saturation(_body(SOLROCK), seen2) == 1.0
    assert p._readiness_saturation(_body(SOLROCK), seen2) == 1.0     # attacker never saturates


# --- floor + the hard-rung invariant --------------------------------------------------------------
@pytest.mark.req("REQ-PLANNER-0011")
def test_floor_credits_a_bench_exists():
    """A bench-exists floor: a board WITH a bench reads a small credit above the same board with none —
    a KO doesn't lose the game outright."""
    p = _pilot()
    with_bench = p._readiness({"active": [_body(JUNK)], "bench": [_body(JUNK)]})
    no_bench = p._readiness({"active": [_body(JUNK)], "bench": []})
    assert with_bench > no_bench


@pytest.mark.req("REQ-PLANNER-0011")
def test_readiness_stays_capped_below_one_prize():
    """The hard-rung invariant: a maximal positional board's readiness stays below one prize (KO_SCORE),
    so no positional score can ever outrank a real KO."""
    p = _pilot()
    stacked = {"active": [_body(MEGA, [ENERGY_F, ENERGY_F])],
               "bench": [_body(SOLROCK, [ENERGY_F]), _body(LUNATONE), _body(MEGA, [ENERGY_F, ENERGY_F])]}
    assert 0.0 < p._readiness(stacked) < KO_SCORE


# --- the line account (spend / ability-fire), reusing the live tuned weights ----------------------
@pytest.mark.req("REQ-PLANNER-0011")
def test_line_account_credits_ability_fire_and_subtracts_spend():
    """`_line_account` is the signed path term: a fired ability-USE rule (`fire-lunar-cycle`) adds its
    positive weight; a fired spend rule (`dont-waste-discard-energy`) subtracts its magnitude; a rule
    NOT in either set is ignored; the sign filter drops a positive spend-id / negative ability-id."""
    p = _pilot()
    traces = [
        _Trace([(_Hyp("fire-lunar-cycle"), 15.0)]),                 # ability fire → +15
        _Trace([(_Hyp("dont-waste-discard-energy"), -60.0)]),       # spend → -60
        _Trace([(_Hyp("power-up-attacker"), 15.0)]),                # not a line rule → 0
    ]
    assert p._line_account(traces, [0]) == 15.0
    assert p._line_account(traces, [1]) == -60.0
    assert p._line_account(traces, [2]) == 0.0
    assert p._line_account(traces, [0, 1]) == pytest.approx(-45.0)


@pytest.mark.req("REQ-PLANNER-0011")
def test_line_account_ignores_wrong_sign():
    """The classification guard: only NEGATIVE spend weights and POSITIVE ability-fire weights count — a
    positive spend-id firing (a correct 'hold') and a negative ability-id are both ignored."""
    p = _pilot()
    traces = [_Trace([(_Hyp("dont-waste-discard-energy"), 5.0),      # positive spend-id → ignored
                      (_Hyp("fire-lunar-cycle"), -3.0)])]            # negative ability-id → ignored
    assert p._line_account(traces, [0]) == 0.0


@pytest.mark.req("REQ-PLANNER-0011")
def test_no_declared_roles_ability_precondition_fails_open():
    """A deck that declares no roles: a non-engine body's ability precondition fails OPEN (a self-
    sufficient ability is always ready), so the leaf never silently zeroes an ability for lack of a Role."""
    p = _pilot(roles={}, lines=[], functions={LUNATONE: ["draw"]})
    assert p._ability_precondition_met(LUNATONE, {"active": [_body(LUNATONE)]}) is True
