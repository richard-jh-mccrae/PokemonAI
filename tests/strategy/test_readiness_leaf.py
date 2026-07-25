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
AIR_BALLOON = 1174       # retreat-reduction Tool ("{C}{C} less" -> retreatReduction=2, parsed at source)
SWITCH = 1123            # Switch Item ("Switch your Active Pokémon with 1 of your Benched Pokémon")
_STATS = {
    # retreat costs mirror the REAL cards (EN_Card_Data.csv: Riolu 2, Mega Lucario ex 2, Lunatone 1,
    # Solrock 1) — the promotion-ease lift reads them, so the fixture must carry them.
    RIOLU: CardStat(RIOLU, name="riolu", hp=70, energyType=F, evolvesFrom=None, attacks=(3330,),
                    minAttackCost=1, maxDamage=30, retreatCost=2),
    MEGA: CardStat(MEGA, name="mega lucario ex", hp=340, energyType=F, evolvesFrom="riolu",
                   attacks=(6780, 6781), minAttackCost=1, maxDamage=270, megaEx=True, retreatCost=2),
    LUNATONE: CardStat(LUNATONE, name="lunatone", hp=110, energyType=F, attacks=(6750,),
                       minAttackCost=2, maxDamage=50, hasAbility=True, retreatCost=1),
    SOLROCK: CardStat(SOLROCK, name="solrock", hp=110, energyType=F, attacks=(6760,),
                      minAttackCost=1, maxDamage=70, retreatCost=1),
    JUNK: CardStat(JUNK, name="junk", hp=60, energyType=F, attacks=(), retreatCost=1),
    ENERGY_F: CardStat(ENERGY_F, name="fighting energy", hp=0, cardType=5, energyType=F),
    ENERGY_P: CardStat(ENERGY_P, name="psychic energy", hp=0, cardType=5, energyType=P),
    AIR_BALLOON: CardStat(AIR_BALLOON, name="air balloon", hp=0, cardType=2, retreatReduction=2),
    SWITCH: CardStat(SWITCH, name="switch", hp=0, cardType=1),
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
    vs the flat bench discount — the promotion-ease lift lives in `_readiness`, never per-body here)."""
    p = _pilot()
    me = {"active": [_body(SOLROCK, [ENERGY_F])], "bench": [_body(SOLROCK, [ENERGY_F])]}
    active = p._attack_readiness(_body(SOLROCK, [ENERGY_F]), me, is_active=True)
    bench = p._attack_readiness(_body(SOLROCK, [ENERGY_F]), me, is_active=False)
    assert active > bench > 0.0


# --- promotion-ease position_w (the who's-Active term, v2 2026-07-20) ------------------------------
@pytest.mark.req("REQ-PLANNER-0011")
def test_bench_weight_lifts_when_active_retreats_free():
    """A free-retreat Active (a retreat-reduction Tool covers its whole cost: Air Balloon −2 on a
    retreat-2 Mega Lucario) lifts the bench weight to the `_READINESS_PROMO_MAX` ceiling — a loaded
    benched attacker is NEARLY Active when the spot can be vacated for free (the retreat-tool →
    position routing), but never fully equal (the ceiling stays < 1.0)."""
    p = _pilot()
    stuck = {"active": [_body(MEGA)], "bench": [_body(SOLROCK, [ENERGY_F])]}          # retreat 2, E0
    free = {"active": [_body(MEGA, tools=[{"id": AIR_BALLOON}])],
            "bench": [_body(SOLROCK, [ENERGY_F])]}                                    # eff retreat 0
    assert p._bench_position_w(stuck) == pytest.approx(0.45)
    assert p._bench_position_w(free) == pytest.approx(0.5)    # the measured < 1.0 ceiling
    assert p._readiness(free) > p._readiness(stuck)       # the lift reaches the board value


@pytest.mark.req("REQ-PLANNER-0011")
def test_bench_weight_not_lifted_by_a_merely_payable_retreat():
    """A retreat merely PAYABLE at k>0 is NOT ease — paying DISCARDS the attached Energy (rulebook
    L142), so the bench weight stays at the flat floor (measured: crediting payable-at-a-cost promoted
    chip-loaded rival benches over the human's attacker-in-front boards)."""
    p = _pilot()
    payable = {"active": [_body(SOLROCK, [ENERGY_F])], "bench": []}                   # retreat 1, E1
    unpayable = {"active": [_body(RIOLU, [ENERGY_F])], "bench": []}                   # retreat 2, E1
    assert p._bench_position_w(payable) == pytest.approx(0.45)
    assert p._bench_position_w(unpayable) == pytest.approx(0.45)


@pytest.mark.req("REQ-PLANNER-0011")
def test_bench_weight_reads_switch_in_visible_hand_only():
    """A `switch`-tagged card in my VISIBLE hand lifts a stuck Active's bench weight (promotion via the
    Item, no retreat needed); an absent hand claims nothing — the graceful degrade to the flat floor."""
    p = _pilot(functions={SWITCH: ["switch"]})
    stuck = {"active": [_body(RIOLU)], "bench": [_body(SOLROCK, [ENERGY_F])]}
    with_switch = {**stuck, "hand": [{"id": SWITCH}]}
    assert p._bench_position_w(stuck) == pytest.approx(0.45)
    assert p._bench_position_w(with_switch) == pytest.approx(0.45 + (0.5 - 0.45) * 0.9)
    assert p._promotion_ease(with_switch) == pytest.approx(0.9)


@pytest.mark.req("REQ-PLANNER-0011")
def test_active_quality_credit_is_hand_armed_and_scenario1_gated():
    """The who's-Active micro-credit rides the hand-visibility arm (`leaf_hand_value`) — flag OFF the
    readiness of a mobile-Active board equals the flat sum (shipped behavior byte-stable); flag ON it
    earns `_READINESS_MOBILITY_W`. The energized-pre-evo half is SCENARIO-1 gated: it credits ONLY
    with the forward evolution REACHABLE (in hand/play) — an energized Riolu whose Mega is out of
    reach earns nothing (the grill's flagship: that attach is ~0, its Energy is Lunar-Cycle fuel)."""
    p = _pilot()
    mobile = {"active": [_body(MEGA, tools=[{"id": AIR_BALLOON}])], "bench": [_body(JUNK)]}
    stuck = {"active": [_body(MEGA)], "bench": [_body(JUNK)]}
    assert p._readiness(mobile) == p._readiness(stuck)        # flag OFF: no credit (bench unloaded too)
    p.leaf_hand_value = True
    assert p._readiness(mobile) - p._readiness(stuck) == pytest.approx(2.5)
    # scenario-1 gate: energized line pre-evo front credits ONLY with the payoff reachable
    unreachable = {"active": [_body(RIOLU, [ENERGY_F])], "bench": [_body(JUNK)], "hand": []}
    reachable = {"active": [_body(RIOLU, [ENERGY_F])], "bench": [_body(JUNK)], "hand": [{"id": MEGA}]}
    assert p._active_quality(unreachable) == 0.0
    assert p._active_quality(reachable) == 1.0
    bare = {"active": [_body(RIOLU)], "bench": [_body(JUNK)], "hand": [{"id": MEGA}]}
    assert p._active_quality(bare) == 0.0                     # a bare base up front is not development


@pytest.mark.req("REQ-PLANNER-0011")
def test_lift_lands_on_the_single_best_benched_attacker_only():
    """One retreat per turn (rules.md §3): the lift raises the board by the single BEST benched
    attacker's delta, not per-body — two loaded benched attackers gain exactly what one gains."""
    p = _pilot()
    free_active = _body(MEGA, tools=[{"id": AIR_BALLOON}])
    one = {"active": [free_active], "bench": [_body(SOLROCK, [ENERGY_F])]}
    two = {"active": [free_active], "bench": [_body(SOLROCK, [ENERGY_F]), _body(SOLROCK, [ENERGY_F])]}
    stuck_one = {"active": [_body(MEGA)], "bench": [_body(SOLROCK, [ENERGY_F])]}
    stuck_two = {"active": [_body(MEGA)], "bench": [_body(SOLROCK, [ENERGY_F]), _body(SOLROCK, [ENERGY_F])]}
    lift_one = p._readiness(one) - p._readiness(stuck_one)
    lift_two = p._readiness(two) - p._readiness(stuck_two)
    assert lift_one > 0.0
    assert lift_two == pytest.approx(lift_one)            # the 2nd benched attacker earns NO extra lift


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


@pytest.mark.req("REQ-PLANNER-0011")
def test_no_declared_roles_ability_precondition_fails_open():
    """A deck that declares no roles: a non-engine body's ability precondition fails OPEN (a self-
    sufficient ability is always ready), so the leaf never silently zeroes an ability for lack of a Role."""
    p = _pilot(roles={}, lines=[], functions={LUNATONE: ["draw"]})
    assert p._ability_precondition_met(LUNATONE, {"active": [_body(LUNATONE)]}) is True
