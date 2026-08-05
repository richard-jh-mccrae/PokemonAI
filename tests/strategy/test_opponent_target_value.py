"""Opponent-Value-Equation S3a — the two-term opponent-target marginal (design:
docs/plans/opponent-value-equation-unification.md; O1 = Option B).

The Layer-2 currency, ruled: value(remove opponent body b) = prize_advance + survival_shift × phase
(ruling 1 two-term sum; ruling 5 phase-scaled by the KO-race margin). The survival term is grounded
in the S1a curve — `survival_shift` = Δ `turns_to_ko_me` from removing the body — and stays sub-prize
(the gust-marginal discipline: a bought turn breaks ties, never overrides a real prize). These are
pure primitives + a shadow, DECIDING NOTHING; the live snipe/gust/deny picks are unchanged.
"""
import types

import pytest

from common import needs
from common.strategy.combat import CombatMath
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider

MY = 500
A = 501             # reaches my HP at t=1 (cheap attack, 0 energy)
B = 502             # reaches my HP at t=3 (3-cost attack)
C60 = 503           # 60 a turn — crosses my 100 HP DURING t=2
D90 = 504           # 90 a turn — also crosses during t=2, but far earlier within it
EARLY = 505         # cost 1, 100 a turn — leads the per-turn MAX at t=1 and t=2
LATE = 506          # cost 3, 250 a turn — takes the lead from t=3
FAST_ATK, SLOW_ATK, SIXTY_ATK, NINETY_ATK = 511, 512, 513, 514
EARLY_ATK, LATE_ATK = 515, 516


def _combat():
    stats = DictCardStatProvider({
        MY: CardStat(MY, synthetic=True, name="Me", hp=100, minAttackCost=1, attacks=()),
        A: CardStat(A, synthetic=True, name="Fast", hp=120, minAttackCost=1, minCostDamage=100, maxDamage=100,
                    attacks=(FAST_ATK,)),
        B: CardStat(B, synthetic=True, name="Slow", hp=120, minAttackCost=3, minCostDamage=100, maxDamage=100,
                    attacks=(SLOW_ATK,)),
        C60: CardStat(C60, synthetic=True, name="Sixty", hp=120, minAttackCost=1, minCostDamage=60,
                      maxDamage=60, attacks=(SIXTY_ATK,)),
        D90: CardStat(D90, synthetic=True, name="Ninety", hp=120, minAttackCost=1, minCostDamage=90,
                      maxDamage=90, attacks=(NINETY_ATK,)),
    }, attacks={FAST_ATK: AttackStat(FAST_ATK, damage=100, cost=1, energyTypes=(0,)),
                SLOW_ATK: AttackStat(SLOW_ATK, damage=100, cost=3, energyTypes=(0, 0, 0)),
                SIXTY_ATK: AttackStat(SIXTY_ATK, damage=60, cost=1, energyTypes=(0,)),
                NINETY_ATK: AttackStat(NINETY_ATK, damage=90, cost=1, energyTypes=(0,))})
    return CombatMath(stats, functions=None, transients=None)


MY_BODY = {"id": MY, "hp": 100}


def _b(cid):
    return {"id": cid, "energies": []}


# ---- phase_scale (ruling 5) ------------------------------------------------------------------
def test_phase_scale_is_bounded_and_monotonic():
    # Bounded [0,1] everywhere.
    for ra in (-10, -2, 0, 3, 10):
        for op in (0, 1, 3, 6):
            s = needs.phase_scale(race_ahead=ra, opp_prizes_remaining=op)
            assert 0.0 <= s <= 1.0
    # Being further BEHIND (more negative race_ahead) sharpens every survival turn → higher.
    assert needs.phase_scale(race_ahead=-3, opp_prizes_remaining=3) > \
           needs.phase_scale(race_ahead=0, opp_prizes_remaining=3)
    # The opponent nearer their last prize → higher stakes → higher.
    assert needs.phase_scale(race_ahead=0, opp_prizes_remaining=1) > \
           needs.phase_scale(race_ahead=0, opp_prizes_remaining=5)
    # Clamps at the extremes.
    assert needs.phase_scale(race_ahead=99, opp_prizes_remaining=6) == 0.0
    assert needs.phase_scale(race_ahead=-99, opp_prizes_remaining=1) == 1.0


# ---- opponent_target_value (ruling 1) --------------------------------------------------------
def test_two_term_value_prize_plus_capped_survival():
    # No survival shift → pure prize.
    assert needs.opponent_target_value(prize_advance=2, survival_shift=0, phase=0.7) == 2.0
    # The survival term is SUB-PRIZE (capped < 1) so it never overrides a real prize difference.
    assert needs.opponent_target_value(prize_advance=0, survival_shift=100, phase=1.0) < 1.0
    v = needs.opponent_target_value(prize_advance=1, survival_shift=4, phase=1.0)
    assert 1.0 < v < 2.0                                        # a prize + a capped survival tie-break
    # Monotonic: more turns bought (at equal phase) is worth at least as much.
    assert (needs.opponent_target_value(prize_advance=0, survival_shift=2, phase=0.5)
            >= needs.opponent_target_value(prize_advance=0, survival_shift=1, phase=0.5))


# ---- turns_to_ko_me (the S1a curve inversion) ------------------------------------------------
def test_turns_to_ko_me_and_the_survival_shift():
    c = _combat()
    # A one-shots me next turn (t=1); B needs 3 turns of energy.
    #
    # RE-DERIVED by hand for ADR-0071 decision 10, when `turns_to_ko_me` became an ACCUMULATING
    # read (`min{t : Σᵢ₌₁..ᵗ incoming(i) >= hp}`). Both numbers are unchanged, and NOT by luck:
    # my HP is 100, A pays its 1-cost attack on the first attach and deals the whole 100 at t=1,
    # while B is cost-3 off 0 Energy so it deals literally 0 at t=1 and t=2 — the running sum is
    # 0 + 0 + 100, which still first reaches 100 at t=3. Accumulation only moves a pin when some
    # earlier turn contributes non-zero damage.
    assert c.turns_to_ko_me(MY_BODY, [_b(A)]) == 1
    assert c.turns_to_ko_me(MY_BODY, [_b(B)]) == 3
    both = [_b(A), _b(B)]
    base = c.turns_to_ko_me(MY_BODY, both)                      # = 1 (A dominates)
    assert base == 1
    # Removing A buys 2 turns of survival; removing B buys none — A is the valuable removal.
    assert c.turns_to_ko_me(MY_BODY, [_b(B)]) - base == 2
    assert c.turns_to_ko_me(MY_BODY, [_b(A)]) - base == 0


# ---- the FRACTIONAL survival clock (ADR-TEMP-398, amending ADR-0071 decision 4) ---------------
def test_the_integer_clock_is_unchanged_by_the_fractional_reading():
    """The byte-identical guarantee, asserted literally rather than inferred from the diff.

    Every shipped consumer (`survival`, `readiness`, `threat`, both deny surfaces) reads the
    INTEGER. The fractional reading is additive, so these are the same numbers this file has
    asserted since ADR-0071 decision 10 — restated here against the new code path so that a future
    change to the accumulation cannot quietly move them while only the fractional tests are read."""
    c = _combat()
    assert c.turns_to_ko_me(MY_BODY, [_b(A)]) == 1
    assert c.turns_to_ko_me(MY_BODY, [_b(B)]) == 3
    assert c.turns_to_ko_me(MY_BODY, [_b(C60)]) == 2
    assert c.turns_to_ko_me(MY_BODY, [_b(D90)]) == 2
    # ...and the clock's own `.turns` is that same integer, so the two readings cannot drift.
    for bodies in ([_b(A)], [_b(B)], [_b(C60)], [_b(D90)], [_b(C60), _b(D90)]):
        assert c.survival_clock(MY_BODY, bodies).turns == c.turns_to_ko_me(MY_BODY, bodies)
        assert isinstance(c.turns_to_ko_me(MY_BODY, bodies), int)


def test_the_crossing_is_interpolated_within_the_turn_it_falls_in():
    """`t* = (t_cross - 1) + (hp - dealt(t_cross - 1)) / incoming(t_cross)`, hand-derived.

    My HP is 100 and `incoming` is the per-turn MAXIMUM over their forms (not a sum), so a lone
    60-damage body accumulates 60 then 120: it crosses DURING t=2, four-sixths of the way in. The
    integer clock rounds that to 2 and the precision is gone — which is the whole defect."""
    c = _combat()
    # 60 a turn: dealt(1) = 60, incoming(2) = 60  ->  1 + (100 - 60)/60 = 1.6667
    assert c.survival_clock(MY_BODY, [_b(C60)]).exact == pytest.approx(1 + 40 / 60)
    # 90 a turn: dealt(1) = 90, incoming(2) = 90  ->  1 + (100 - 90)/90 = 1.1111
    assert c.survival_clock(MY_BODY, [_b(D90)]).exact == pytest.approx(1 + 10 / 90)
    # A crossing at t=1 has no prior turn: dealt(0) = 0, so it reduces to hp/incoming(1), in (0, 1].
    assert c.survival_clock(MY_BODY, [_b(A)]).exact == pytest.approx(1.0)
    # ...and B's 0-damage first two turns leave the crossing exactly ON t=3, nothing to interpolate.
    assert c.survival_clock(MY_BODY, [_b(B)]).exact == pytest.approx(3.0)
    # The fractional reading never leaves the turn the integer named.
    for bodies in ([_b(A)], [_b(B)], [_b(C60)], [_b(D90)]):
        clock = c.survival_clock(MY_BODY, bodies)
        assert clock.turns - 1 < clock.exact <= clock.turns


def test_no_crossing_within_the_horizon_reads_the_same_both_ways():
    """There is no crossing to interpolate, so the fractional reading must not invent one beyond
    the horizon — it repeats `max_t + 1` exactly, the shipped "survives the window" answer."""
    c = _combat()
    clock = c.survival_clock(MY_BODY, [_b(B)], max_t=2)      # B deals 0 at t=1 and t=2
    assert clock.turns == 3 and clock.exact == pytest.approx(3.0)
    empty = c.survival_clock(MY_BODY, [], max_t=4)
    assert empty.turns == 5 and empty.exact == pytest.approx(5.0)
    dead = c.survival_clock({"id": MY, "hp": 0}, [_b(A)], max_t=4)   # no HP: no clock at all
    assert dead.turns == 5 and dead.exact == pytest.approx(5.0)


def test_a_flat_tie_the_integer_clock_cannot_see_and_the_fractional_one_can():
    """THE defect Issue #398 measured, reproduced at the size of two bodies.

    Both opponents cross my HP during t=2, so the integer `survival_shift` for removing EITHER is
    0 — a Flat Tie, and at equal prize value the pick falls to list order. They are not equally
    dangerous: removing the 90 leaves me facing 60 a turn and genuinely buys survival, while
    removing the 60 changes nothing because the 90 was already the per-turn maximum."""
    c = _combat()
    both = [_b(C60), _b(D90)]
    base = c.turns_to_ko_me(MY_BODY, both)
    # INTEGER: removing either body buys exactly nothing. This is the Flat Tie.
    assert c.turns_to_ko_me(MY_BODY, [_b(D90)]) - base == 0
    assert c.turns_to_ko_me(MY_BODY, [_b(C60)]) - base == 0
    # FRACTIONAL: removing the 90 buys 0.556 of a turn; removing the 60 still buys nothing, and
    # that ZERO is correct — the 60 was never the binding constraint.
    exact_base = c.survival_clock(MY_BODY, both).exact
    assert c.survival_clock(MY_BODY, [_b(C60)]).exact - exact_base == pytest.approx(40 / 60 - 10 / 90)
    assert c.survival_clock(MY_BODY, [_b(D90)]).exact - exact_base == pytest.approx(0.0)
    # And the currency downstream carries the distinction through, where before it saw two equals.
    val = needs.opponent_target_value
    assert val(prize_advance=2, survival_shift=0, phase=0.7) == \
           val(prize_advance=2, survival_shift=0, phase=0.7)        # the tie, as it shipped
    assert val(prize_advance=2, survival_shift=40 / 60 - 10 / 90, phase=0.7) > \
           val(prize_advance=2, survival_shift=0.0, phase=0.7)


def test_more_than_one_body_scores_when_the_lead_changes_across_turns():
    """The boundary of the **Structural Zero**, pinned because a stronger claim about it was drafted
    into an ADR and was FALSE.

    `incoming()` is a per-turn MAX over their forms, so removing a body that never leads that max
    moves nothing — that much is true and `test_a_flat_tie...` above shows it. The claim that did
    not survive was *"at most ONE body per board can carry a non-zero survival_shift"*. `incoming(t)`
    grants each form `attached + t` energy, so the LEADING form can change across turns, and every
    body that leads at some turn before the crossing scores.

    My 300 HP against `Early` (cost 1, 100 a turn, leads at t=1 and t=2) and `Late` (cost 3, 250 from
    t=3, leads there). Both present: dealt 100, 200, 450 — crossing during t=3 at 2 + (300-200)/250 =
    2.4. Remove Early and `Late` alone deals 0, 0, 250, 500 — crossing during t=4 at 3 + 50/250 = 3.2.
    Remove Late and `Early` alone deals 100, 200, 300 — crossing exactly ON t=3.

    The corpus average (208 non-zero shifts over 359 frames) is consistent with the false form, which
    is exactly why an average must never be read as a bound."""
    stats = DictCardStatProvider({
        MY: CardStat(MY, synthetic=True, name="Me", hp=300, minAttackCost=1, attacks=()),
        EARLY: CardStat(EARLY, synthetic=True, name="Early", hp=120, minAttackCost=1,
                        minCostDamage=100, maxDamage=100, attacks=(EARLY_ATK,)),
        LATE: CardStat(LATE, synthetic=True, name="Late", hp=120, minAttackCost=3,
                       minCostDamage=250, maxDamage=250, attacks=(LATE_ATK,)),
    }, attacks={EARLY_ATK: AttackStat(EARLY_ATK, damage=100, cost=1, energyTypes=(0,)),
                LATE_ATK: AttackStat(LATE_ATK, damage=250, cost=3, energyTypes=(0, 0, 0))})
    c = CombatMath(stats, functions=None, transients=None)
    me = {"id": MY, "hp": 300}
    both = [_b(EARLY), _b(LATE)]

    base = c.survival_clock(me, both)
    assert (base.turns, base.exact) == (3, pytest.approx(2.4))
    early_gone = c.survival_clock(me, [_b(LATE)])
    late_gone = c.survival_clock(me, [_b(EARLY)])
    assert early_gone.exact - base.exact == pytest.approx(0.8)
    assert late_gone.exact - base.exact == pytest.approx(0.6)
    # BOTH non-zero — the refutation. Neither body is redundant, because neither leads at every turn.
    assert min(early_gone.exact - base.exact, late_gone.exact - base.exact) > 0
    # ...and the integer clock sees only ONE of the two, which is the quantization loss on top.
    assert (early_gone.turns - base.turns, late_gone.turns - base.turns) == (1, 0)


def test_the_survival_term_still_never_outranks_a_real_prize():
    """The gust-marginal discipline, re-checked at the new resolution: making the shift continuous
    must not let a tie-break outgrow the thing it is breaking ties among. `_SURVIVAL_CAP` < 1 does
    the work, and it caps the fractional shift exactly as it capped the integer one."""
    val = needs.opponent_target_value
    assert val(prize_advance=1, survival_shift=99.9, phase=1.0) < val(prize_advance=2,
                                                                     survival_shift=0.0, phase=1.0)
    # Monotonic in the fractional shift, not merely in whole turns.
    assert val(prize_advance=1, survival_shift=0.75, phase=1.0) > \
           val(prize_advance=1, survival_shift=0.25, phase=1.0)


def test_the_live_rows_break_a_flat_tie_the_integer_clock_could_not():
    """The behavioural claim, at the seam that actually decides: `_opponent_target_rows`.

    Card facts read off the live provider `_build_pilot` hands the Pilot, never recalled — both
    bodies are **1 prize**, so `prize_advance` ties by construction and the whole ranking rests on
    `survival_shift`. Their Dunsparce Active's line reaches 150/turn into my 200 HP; their benched
    Alakazam's Powerful Hand is `20 x their hand`, so at a hand of six it reaches 120/turn.

    Both crossings land in turn 2, which is exactly why the INTEGER clock reports 0 turns bought for
    removing either — a perfect Flat Tie, the shape 251 of 343 equal-prize corpus groups are in, and
    the pick falls to list order. They are not equally worth removing: taking the Active drops the
    per-turn maximum from 150 to 120 and genuinely pushes my crossing later, while taking the Bench
    changes nothing because it was never the binding constraint. The fractional reading says so."""
    from train.tune import _build_pilot
    p = _build_pilot("mega_lucario")[0]
    p._planning = False
    dunsparce, alakazam, psychic = 305, 743, 5
    obs = {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": 999999, "hp": 200, "energies": []}], "bench": [],
         "handCount": 1, "hand": []},
        {"active": [{"id": dunsparce, "hp": 70, "energies": [psychic]}],
         "bench": [{"id": alakazam, "hp": 140, "energies": [psychic]}],
         "handCount": 6},
    ]}}
    board = types.SimpleNamespace(race_ahead=-1.0, opp_prizes_remaining=3)
    p._snapshot(obs)
    p._opp_attack_context = p._damage_context(obs, attacker_is_me=False)
    model, ma = p._state_model, obs["current"]["players"][0]["active"][0]
    bodies = [obs["current"]["players"][1]["active"][0],
              obs["current"]["players"][1]["bench"][0]]
    assert [model.theirs.view_of(b).prize_value for b in bodies] == [1, 1], (
        "the fixture must be an EQUAL-PRIZE group, or this tests nothing about tie-breaking")

    # The pre-fix reading, on this same board: whole turns, and both removals buy zero.
    clock = dict(bodies=bodies, charged=None, opp_active=bodies[0],
                 switch_enabler=p._opp_switch_enabler(), context=p._opp_attack_context)
    base = model.theirs.turns_to_ko_me(ma, **clock)
    integer_shifts = [model.theirs.turns_to_ko_me(ma, **dict(clock, bodies=bodies[:i] + bodies[i + 1:]))
                      - base for i in (0, 1)]
    assert integer_shifts == [0, 0], "the integer clock must still flat-tie — that is the defect"

    _phase, rows = p._opponent_target_rows(obs, board)
    active = next(r for r in rows if r["area"] == "active")
    bench = next(r for r in rows if r["area"] == "bench")
    assert active["prize"] == bench["prize"], "equal prize, so only the survival term can order them"
    # 1 + (200-120)/120 = 5/3 without the Active, against 1 + (200-150)/150 = 4/3 with it.
    assert active["survival_shift"] == pytest.approx(5 / 3 - 4 / 3)
    assert bench["survival_shift"] == pytest.approx(0.0)
    assert active["value"] > bench["value"], (
        "the body whose removal actually buys survival must now outrank the one whose removal "
        "buys nothing — where before this change the two were identical and list order decided")


def test_the_live_rows_run_mid_sim():
    """ADR-0093 decision 3 — where the `_planning` guard belongs.

    `_opponent_target_rows` is the LIVE per-body computation that both the deny fire rung and the
    `gust_target` slot emission read. It used to early-return `None` mid-sim alongside the three
    diagnostics, which made the agent evaluate a different policy inside its own rollout than
    outside it — the third confirmed source of continuation collateral here (ADR-0072 finding 2,
    ADR-0070 amendment H, Issue #228). Measured cost of that: the armed deny rung returned 0.00
    mid-sim where the incumbent returned -5.00 / +22.50 / +74.50.

    The guard was a COST decision, not a correctness one — nothing in the rows starts a nested
    engine search, so it moved onto `_opponent_target_shadow`, the caller that actually wanted no
    shadow work in rollouts. Issue #261 item 2h then deleted that shadow, and with it the last
    caller the guard was protecting — so what survives is the half that was always the point: the
    live rows value each body identically inside the rollout and outside it."""
    from train.tune import _build_pilot
    p = _build_pilot("mega_lucario")[0]
    obs = {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": 999999, "hp": 100, "energies": []}]},
        {"active": [{"id": 678, "hp": 340, "energies": []}],
         "bench": [{"id": 677, "hp": 70, "energies": []}]},
    ]}}
    board = types.SimpleNamespace(race_ahead=-1.0, opp_prizes_remaining=3)

    p._snapshot(obs)                  # the per-decision StateModel the rows now read (POC-T1)
    p._planning = False
    root = p._opponent_target_rows(obs, board)
    assert root is not None and root[1], "the fixture must produce rows at the root"

    p._planning = True
    mid = p._opponent_target_rows(obs, board)
    assert mid is not None, "the LIVE rows must survive the rollout"
    assert [r["value"] for r in mid[1]] == [r["value"] for r in root[1]], (
        "and must value each body identically inside the rollout and outside it")
