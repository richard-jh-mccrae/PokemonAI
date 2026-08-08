"""Opponent-Value-Equation S3a — the two-term opponent-target marginal (design:
docs/plans/ADR-0078; O1 = Option B).

The Layer-2 currency, ruled: value(remove opponent body b) = prize_advance + survival_shift × phase
(ruling 1 two-term sum; ruling 5 phase-scaled by the KO-race margin). The survival term is grounded
in the S1a curve — `survival_shift` = Δ `turns_to_ko_me` from removing the body — and stays sub-prize
(the gust-marginal discipline: a bought turn breaks ties, never overrides a real prize). These are
primitives whose rows are now a LIVE decision input: `Pilot._board` resolves and caches
`_opponent_target_rows` once per decision, and the shipped gust/deny picks read it.
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

# `forward_line_prize`'s hop distance is NOT `ForwardPayoff.hops`, which measures the distance to the
# best-DAMAGE form (Issue #285); `MID` below is arranged so the two diverge.
STARYU, MEGA = 507, 508          # Staryu -> Mega Starmie ex, 1 hop, prize 1 -> 3
PIP, MID, BIGEX = 509, 510, 517  # Pip -> Mid -> Big ex, 2 hops, prize 1 -> 1 -> 2
DEADEND = 518                    # a 1-prize Basic whose line goes nowhere
MID_ATK = 519                    # MID hits hardest in its line; BIGEX carries the prize


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
        # 1 hop, 1 prize -> 3 prizes.
        STARYU: CardStat(STARYU, synthetic=True, name="Staryu", hp=60, maxDamage=10, attacks=()),
        MEGA: CardStat(MEGA, synthetic=True, name="Mega Starmie ex", evolvesFrom="Staryu", hp=310,
                       megaEx=True, maxDamage=200, attacks=()),
        # 2 hops, 1 prize -> 2 prizes, and the BIGGEST DAMAGE sits at hop 1 rather than hop 2.
        PIP: CardStat(PIP, synthetic=True, name="Pip", hp=60, maxDamage=10, attacks=()),
        MID: CardStat(MID, synthetic=True, name="Mid", evolvesFrom="Pip", hp=100, maxDamage=250,
                      minAttackCost=1, minCostDamage=250, attacks=(MID_ATK,)),
        BIGEX: CardStat(BIGEX, synthetic=True, name="Big ex", evolvesFrom="Mid", hp=200, ex=True,
                        maxDamage=90, attacks=()),
        DEADEND: CardStat(DEADEND, synthetic=True, name="Deadend", hp=60, maxDamage=10, attacks=()),
    }, attacks={FAST_ATK: AttackStat(FAST_ATK, damage=100, cost=1, energyTypes=(0,)),
                SLOW_ATK: AttackStat(SLOW_ATK, damage=100, cost=3, energyTypes=(0, 0, 0)),
                SIXTY_ATK: AttackStat(SIXTY_ATK, damage=60, cost=1, energyTypes=(0,)),
                NINETY_ATK: AttackStat(NINETY_ATK, damage=90, cost=1, energyTypes=(0,)),
                MID_ATK: AttackStat(MID_ATK, damage=250, cost=1, energyTypes=(0,))})
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
    # `turns_to_ko_me` ACCUMULATES: `min{t : Σᵢ₌₁..ᵗ incoming(i) >= hp}` (ADR-0071 decision 10), so
    # accumulation only moves a number when an earlier turn contributes non-zero damage.
    assert c.turns_to_ko_me(MY_BODY, [_b(A)]) == 1
    assert c.turns_to_ko_me(MY_BODY, [_b(B)]) == 3
    both = [_b(A), _b(B)]
    base = c.turns_to_ko_me(MY_BODY, both)                      # = 1 (A dominates)
    assert base == 1
    # Removing A buys 2 turns of survival; removing B buys none — A is the valuable removal.
    assert c.turns_to_ko_me(MY_BODY, [_b(B)]) - base == 2
    assert c.turns_to_ko_me(MY_BODY, [_b(A)]) - base == 0


# ---- the FRACTIONAL survival clock (ADR-0117, amending ADR-0071 decision 4) ---------------
def test_the_integer_clock_is_unchanged_by_the_fractional_reading():
    """Every shipped consumer reads the INTEGER, so the fractional reading is additive; restated
    against the new path so a change to the accumulation cannot move it unseen."""
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
    """`t* = (t_cross - 1) + (hp - dealt(t_cross - 1)) / incoming(t_cross)`, and `incoming` is the
    per-turn MAXIMUM over their forms, not a sum."""
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
    """With no crossing the fractional reading must not invent one: it repeats `max_t + 1` exactly,
    the shipped "survives the window" answer."""
    c = _combat()
    clock = c.survival_clock(MY_BODY, [_b(B)], max_t=2)      # B deals 0 at t=1 and t=2
    assert clock.turns == 3 and clock.exact == pytest.approx(3.0)
    empty = c.survival_clock(MY_BODY, [], max_t=4)
    assert empty.turns == 5 and empty.exact == pytest.approx(5.0)
    dead = c.survival_clock({"id": MY, "hp": 0}, [_b(A)], max_t=4)   # no HP: no clock at all
    assert dead.turns == 5 and dead.exact == pytest.approx(5.0)
    # NEGATIVE hp is already past dead, so there is no crossing and the divisor would be that turn's
    # zero damage — this regressed to a ZeroDivisionError once.
    past = c.survival_clock({"id": MY, "hp": -5}, [_b(A)], max_t=4)
    assert past.turns == 1 and past.exact == pytest.approx(1.0)
    assert c.turns_to_ko_me({"id": MY, "hp": -5}, [_b(A)], max_t=4) == 1


def test_a_flat_tie_the_integer_clock_cannot_see_and_the_fractional_one_can():
    """Both bodies cross my HP inside the same turn, so the INTEGER shift is 0 for either and at
    equal prize value the pick falls to list order — Issue #398's Flat Tie."""
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


def test_only_the_bodies_that_LEAD_the_per_turn_max_can_score():
    """The Structural Zero: `incoming()` is a per-turn MAX, so only a body holding a UNIQUE lead can
    score — two bodies tied for the lead leave the maximum untouched either way (ADR-0117)."""
    c = _combat()
    board = [_b(C60), _b(D90), _b(A)]
    base = c.survival_clock(MY_BODY, board).exact
    assert base == pytest.approx(1.0)
    shifts = [c.survival_clock(MY_BODY, board[:i] + board[i + 1:]).exact - base for i in range(3)]
    assert shifts[0] == pytest.approx(0.0), "C60 never leads — removing it is a Structural Zero"
    assert shifts[1] == pytest.approx(0.0), "D90 never leads either"
    assert shifts[2] == pytest.approx(1 / 9), "A is the lead, so only A's removal moves the clock"

    tied_lead = [_b(A), _b(A)]
    tied_base = c.survival_clock(MY_BODY, tied_lead).exact
    assert [c.survival_clock(MY_BODY, tied_lead[:i] + tied_lead[i + 1:]).exact - tied_base
            for i in (0, 1)] == [pytest.approx(0.0), pytest.approx(0.0)], (
        "two bodies tied for the lead: removing either leaves the maximum untouched, so neither "
        "scores — the case that makes 'unique lead' load-bearing rather than decorative")


def test_more_than_one_body_scores_when_the_lead_changes_across_turns():
    """"At most ONE body per board can carry a non-zero shift" is FALSE: `incoming(t)` grants each
    form `attached + t` energy, so the LEAD can change across turns and every leader scores."""
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


# ---- the LINE PRIZE (ADR-0119 decision 2) -------------------------------------------------
def test_forward_line_prize_reads_the_lines_best_prize_and_the_hops_to_IT():
    """`(prize, hops)` over the forward closure INCLUDING itself, where hops is the distance to the
    best-PRIZE form — which is why it cannot reuse the best-DAMAGE `ForwardPayoff.hops`."""
    c = _combat()
    assert c.forward_line_prize(STARYU) == (3, 1)      # 1-prize Basic, 3-prize Mega ex one hop up
    assert c.forward_line_prize(MEGA) == (3, 0)        # already the best form: no hops
    assert c.forward_line_prize(PIP) == (2, 2)         # best PRIZE is 2 hops up...
    assert c.forward_payoff_terms(PIP)[1] == 1         # ...while best DAMAGE is 1. They differ.
    assert c.forward_line_prize(DEADEND) == (1, 0)     # a line going nowhere is worth its own prize
    assert c.forward_line_prize(None) == (0, 0)        # unknown: no claim, no phantom credit
    assert c.forward_line_prize(999999) == (0, 0)


def test_line_prize_advance_is_the_hop_discounted_line_prize():
    """`own + (max_line_prize - own) x halve(hops)` — the `p_arrive` convention of ADR-0070 §6."""
    adv = needs.line_prize_advance
    assert adv(own_prize=1, max_line_prize=3, hops=1) == pytest.approx(1 + 2 * 0.5)      # 2.0
    assert adv(own_prize=1, max_line_prize=3, hops=2) == pytest.approx(1 + 2 * 0.25)     # 1.5
    assert adv(own_prize=1, max_line_prize=2, hops=2) == pytest.approx(1 + 1 * 0.25)     # 1.25
    # Already the best form, or a dead-end line: the own prize, undiscounted and unchanged.
    assert adv(own_prize=3, max_line_prize=3, hops=0) == 3.0
    assert adv(own_prize=1, max_line_prize=1, hops=0) == 1.0
    # A forward form worth FEWER prizes owes nothing — floored, never negative (the same direction
    # `forward_payoff_terms` floors owed damage).
    assert adv(own_prize=2, max_line_prize=1, hops=1) == 2.0
    # An absent supplier (0) must not read as "this line is worthless" and drag the body below its
    # own prize — the fail-closed direction.
    assert adv(own_prize=2, max_line_prize=0, hops=0) == 2.0


def test_the_line_prize_never_breaches_the_ceiling_the_whole_equation_is_normalised_against():
    """`TARGET_VALUE_CEILING` normalises `_THREAT_W` AND `GUST_TARGET_WORTH_RATE`, so a leg exceeding
    `MAX_PRIZE_VALUE` would silently rescale two derived rates in other modules."""
    adv = needs.line_prize_advance
    for own in (1, 2, 3):
        for best in (1, 2, 3):
            for hops in (0, 1, 2, 3, 8):
                v = adv(own_prize=own, max_line_prize=best, hops=hops)
                assert own <= v <= needs.MAX_PRIZE_VALUE
    assert needs.TARGET_VALUE_CEILING == float(needs.MAX_PRIZE_VALUE) + 0.9


def test_the_survival_term_still_never_outranks_a_real_prize():
    """`_SURVIVAL_CAP` < 1 keeps a tie-break from outgrowing the thing it breaks ties among, and it
    caps the fractional shift exactly as it capped the integer one."""
    val = needs.opponent_target_value
    assert val(prize_advance=1, survival_shift=99.9, phase=1.0) < val(prize_advance=2,
                                                                     survival_shift=0.0, phase=1.0)
    # Monotonic in the fractional shift, not merely in whole turns.
    assert val(prize_advance=1, survival_shift=0.75, phase=1.0) > \
           val(prize_advance=1, survival_shift=0.25, phase=1.0)


def test_the_live_rows_break_a_flat_tie_the_integer_clock_could_not():
    """Both bodies are 1 prize, so `prize_advance` ties by construction and the whole ranking rests
    on `survival_shift`; card facts come off the live provider, never recalled."""
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
    """A `_planning` early-return here would make the agent evaluate a DIFFERENT policy inside its
    own rollout than outside it (ADR-0093 decision 3); nothing in the rows starts a nested search."""
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


def test_the_deleted_pilot_duplicate_read_the_same_number_on_every_real_card():
    """`CombatMath.prize_value` answers 1 for a card it does not know, so the deleted duplicate and
    its replacement agree on every real card and diverge only on an unknown id."""
    from train.tune import _build_pilot
    p = _build_pilot("mega_lucario")[0]

    def old(cid):
        ids = {cid} | p._forward_card_ids(cid)
        return max((p.combat.prize_value({"id": i}) for i in ids), default=0)

    known = [cid for cid in range(1, 1300) if p.stats.get(cid)]
    assert len(known) > 200, "positive control: the pool really is loaded, so a clean sweep means something"
    assert [cid for cid in known if old(cid) != p.combat.forward_line_prize(cid)[0]] == []

    # ...and the one place they differ, stated rather than left to be discovered.
    assert old(999999) == 1 and p.combat.forward_line_prize(999999)[0] == 0
    assert 999999 not in p._recognized_line_preevo_set(), "so the consumer's gate never reaches it"


# --- the role sheet as its OWN row leg (Issue #395 D7) -----------------------------------------


def test_the_row_carries_the_role_priority_as_its_own_leg():
    """`role_priority` is an ORDINAL priority, not a worth, so it rides beside `value` and is never
    summed into it (Issue #395 D7)."""
    from common.scouting.matchup_plan import build_matchup_plan
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
    plan = build_matchup_plan(brief_roles={alakazam: "prize_liability"}, gamma=1.0)
    board = types.SimpleNamespace(race_ahead=-1.0, opp_prizes_remaining=3, matchup_plan=plan)
    p._snapshot(obs)
    p._opp_attack_context = p._damage_context(obs, attacker_is_me=False)

    _phase, rows = p._opponent_target_rows(obs, board)
    by_id = {r["id"]: r for r in rows}
    assert set(by_id) == {dunsparce, alakazam}
    assert by_id[alakazam]["role_priority"] > 0
    assert by_id[dunsparce]["role_priority"] == 0.0     # unroled falls through, as it always did
    # …and the leg does NOT leak into the prize-denominated currency: `value` is still exactly the
    # two-term equation over the row's own `prize_advance` and `survival_shift`.
    for r in rows:
        assert r["value"] == pytest.approx(needs.opponent_target_value(
            prize_advance=r["prize_advance"], survival_shift=r["survival_shift"], phase=_phase))


def test_a_board_with_no_matchup_plan_still_produces_rows():
    """Fail-open: an inert plan or a `Board` predating the field degrades to 0.0, never to a crash
    and never to a missing key a consumer would special-case."""
    from train.tune import _build_pilot
    p = _build_pilot("mega_lucario")[0]
    p._planning = False
    obs = {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": 999999, "hp": 200, "energies": []}], "bench": [], "handCount": 1,
         "hand": []},
        {"active": [{"id": 305, "hp": 70, "energies": [5]}], "bench": [], "handCount": 6},
    ]}}
    board = types.SimpleNamespace(race_ahead=-1.0, opp_prizes_remaining=3)   # no matchup_plan at all
    p._snapshot(obs)
    p._opp_attack_context = p._damage_context(obs, attacker_is_me=False)
    _phase, rows = p._opponent_target_rows(obs, board)
    assert rows and all(r["role_priority"] == 0.0 for r in rows)


def test_the_ceiling_and_both_rates_derived_from_it_are_unchanged():
    """If any of these moves, the sheet drifted from an ordinal priority into a WORTH — the response
    is to re-read Issue #395 D1, not to update the number."""
    from common import currency, state_value
    assert needs.TARGET_VALUE_CEILING == pytest.approx(3.9)
    assert currency.GUST_TARGET_BAND == pytest.approx(10.0)
    assert currency.GUST_TARGET_WORTH_RATE == pytest.approx(10.0 / 3.9)
    assert state_value._THREAT_W == pytest.approx(state_value._THREAT_CAP / 3.9)
    # …and both rates are still DERIVED from the ceiling rather than re-authored beside it, which is
    # what makes the three numbers above one fact instead of three.
    assert currency.GUST_TARGET_WORTH_RATE == pytest.approx(
        currency.GUST_TARGET_BAND / needs.TARGET_VALUE_CEILING)
    assert state_value._THREAT_W == pytest.approx(
        state_value._THREAT_CAP / needs.TARGET_VALUE_CEILING)
