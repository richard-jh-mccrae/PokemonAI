"""ADR-0071 — bench survival is a shared-budget Harvest, and the clock accumulates (Issue #163).

Bench damage is a rider and a rider is a SHARED budget: attacking ends their turn (rules.md §5), so
one turn of bench damage is one attack's payload and rescuing a body only picks which body dies.
Seam: `CombatMath` over a `DictCardStatProvider` — DLL-free, no Pilot.
"""
import pytest

from common.strategy.combat import CombatMath, HARVEST_POSSIBLE, HARVEST_UNAVOIDABLE
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider

DREEPY = 601        # 70 HP, 1 prize, KEY
DUNSPARCE = 602     # 70 HP, 1 prize, NO Role
DRAKLOAK = 603      # 90 HP, 1 prize, KEY — what a Dreepy evolves into
TERA_EX = 604       # takes NO attack damage while Benched (rules.md §11)
PLAIN_EX = 605      # 2 prizes, no Role

DRAGAPULT = 610     # Phantom Dive: 60 distributable spread ("in any way you like")
STARMIE = 620       # Jetting Blow: 50 single-target snipe — INDIVISIBLE
WALL = 630          # no attacks; retreatCost 2 — the promotion gate's subject
PHANTOM_DIVE, JETTING_BLOW = 611, 621

KEY_IDS = frozenset({DREEPY, DRAKLOAK})


def _combat():
    stats = DictCardStatProvider(
        {
            DREEPY: CardStat(DREEPY, synthetic=True, name="Dreepy", hp=70),
            DUNSPARCE: CardStat(DUNSPARCE, synthetic=True, name="Dunsparce", hp=70),
            DRAKLOAK: CardStat(DRAKLOAK, synthetic=True, name="Drakloak", hp=90),
            TERA_EX: CardStat(TERA_EX, synthetic=True, name="Tera ex", hp=70, ex=True, tera=True),
            PLAIN_EX: CardStat(PLAIN_EX, synthetic=True, name="Plain ex", hp=70, ex=True),
            DRAGAPULT: CardStat(DRAGAPULT, synthetic=True, name="Dragapult ex", hp=320, ex=True,
                                minAttackCost=2, maxDamage=200, attacks=(PHANTOM_DIVE,)),
            STARMIE: CardStat(STARMIE, synthetic=True, name="Mega Starmie ex", hp=300, megaEx=True,
                              minAttackCost=1, maxDamage=120, attacks=(JETTING_BLOW,)),
            WALL: CardStat(WALL, synthetic=True, name="Wall", hp=200, retreatCost=2, attacks=()),
        },
        attacks={
            PHANTOM_DIVE: AttackStat(PHANTOM_DIVE, damage=200, cost=2, energyTypes=(0, 0),
                                     benchSpread=60),
            JETTING_BLOW: AttackStat(JETTING_BLOW, damage=120, cost=1, energyTypes=(0,),
                                     benchSnipe=50),
        })
    return CombatMath(stats, functions=None, transients=None)


def _body(cid, hp, energies=()):
    """`hp` is REMAINING hp (damage is maxHp - hp)."""
    return {"id": cid, "hp": hp, "energies": list(energies)}


def _spread(n, turns=1):
    """A candidate payload of `turns` divisible spreads — counters persist, so they pool."""
    return ([], n * turns)


def _snipe(n, turns=1):
    """A candidate payload of `turns` INDIVISIBLE single-target snipes."""
    return ([n] * turns, 0)


@pytest.mark.req("REQ-COMBAT-0071")
def test_a_spread_is_one_shared_budget_not_a_threshold_per_body():
    o = _combat()
    # Three bodies at 50 remaining vs Phantom Dive's 60: 50 fits, 50+50=100 does not.
    bench = [_body(DREEPY, 50), _body(DUNSPARCE, 50), _body(DREEPY, 50)]
    possible = o.bench_harvest(bench, [_spread(60)], reading=HARVEST_POSSIBLE, key_ids=KEY_IDS)
    unavoidable = o.bench_harvest(bench, [_spread(60)], reading=HARVEST_UNAVOIDABLE, key_ids=KEY_IDS)
    # Exactly one body dies, and the two KEY bodies are the interchangeable candidates.
    assert possible == {0, 2}          # either Dreepy — the Dunsparce is a strictly worse target
    assert unavoidable == frozenset()  # neither is unavoidable: the counters simply redirect


@pytest.mark.req("REQ-COMBAT-0071")
def test_a_snipe_is_indivisible_and_cannot_be_split_across_two_bodies():
    o = _combat()
    # 20 + 20 = 40 <= 50, so a FUNGIBLE pool would take both. Jetting Blow's 50 is single-target.
    bench = [_body(DUNSPARCE, 20), _body(DUNSPARCE, 20)]
    possible = o.bench_harvest(bench, [_snipe(50)], reading=HARVEST_POSSIBLE)
    assert possible == {0, 1}          # either could be the target...
    # ...but only ONE dies, so neither is unavoidable.
    assert o.bench_harvest(bench, [_snipe(50)], reading=HARVEST_UNAVOIDABLE) == frozenset()


@pytest.mark.req("REQ-COMBAT-0071")
def test_a_lone_body_in_range_is_unavoidable_under_both_readings():
    o = _combat()
    bench = [_body(DREEPY, 50)]
    assert o.bench_harvest(bench, [_spread(60)], reading=HARVEST_POSSIBLE) == {0}
    assert o.bench_harvest(bench, [_spread(60)], reading=HARVEST_UNAVOIDABLE) == {0}


@pytest.mark.req("REQ-COMBAT-0071")
def test_a_tera_body_is_never_in_the_harvest():
    o = _combat()
    bench = [_body(TERA_EX, 10), _body(DUNSPARCE, 50)]
    # Tera takes NO attack damage while Benched, so the 60 must land on the Dunsparce.
    assert o.bench_harvest(bench, [_spread(60)], reading=HARVEST_UNAVOIDABLE) == {1}


@pytest.mark.req("REQ-COMBAT-0071")
def test_nothing_in_range_harvests_nothing():
    o = _combat()
    bench = [_body(DREEPY, 70), _body(DUNSPARCE, 70)]
    assert o.bench_harvest(bench, [_spread(60)], reading=HARVEST_POSSIBLE) == frozenset()


@pytest.mark.req("REQ-COMBAT-0071")
def test_the_attack_choice_is_solved_not_pre_filtered_by_total_rider():
    """"Largest total rider" would take the 70 snipe over the 60 spread, under-reading their reach —
    the phantom-safety fail direction ADR-0070 §9 refused."""
    o = _combat()
    bench = [_body(DUNSPARCE, 20), _body(DUNSPARCE, 20), _body(DUNSPARCE, 20)]
    picked = o.bench_harvest(bench, [_snipe(70), _spread(60)], reading=HARVEST_UNAVOIDABLE)
    assert picked == {0, 1, 2}, "the spread takes 3 prizes; the bigger snipe takes 1"


@pytest.mark.req("REQ-COMBAT-0071")
def test_an_empty_payload_harvests_nothing():
    """Distinct from out-of-range: here the opponent has NO bench-rider attack, so there is no budget."""
    o = _combat()
    bench = [_body(DREEPY, 10), _body(DUNSPARCE, 10)]
    assert o.bench_harvest(bench, [], reading=HARVEST_POSSIBLE) == frozenset()
    assert o.bench_harvest(bench, [([], 0)], reading=HARVEST_POSSIBLE) == frozenset()


@pytest.mark.req("REQ-COMBAT-0071")
def test_the_wincon_tiebreak_settles_a_prize_tie():
    o = _combat()
    # Both 1-prize; only one can die. The KEY body is the one they take.
    bench = [_body(DUNSPARCE, 50), _body(DREEPY, 50)]
    assert o.bench_harvest(bench, [_spread(60)], reading=HARVEST_UNAVOIDABLE,
                           key_ids=KEY_IDS) == {1}


@pytest.mark.req("REQ-COMBAT-0071")
def test_a_real_prize_difference_outranks_the_wincon_tiebreak():
    o = _combat()
    # The wincon tie-break is SUB-prize, so the 2-prize Role-less ex outranks the 1-prize KEY Dreepy.
    bench = [_body(DREEPY, 50), _body(PLAIN_EX, 50)]
    assert o.bench_harvest(bench, [_spread(60)], reading=HARVEST_UNAVOIDABLE,
                           key_ids=KEY_IDS) == {1}


@pytest.mark.req("REQ-COMBAT-0071")
def test_with_no_roles_declared_the_objective_is_pure_prize_max():
    o = _combat()
    bench = [_body(DUNSPARCE, 50), _body(DREEPY, 50)]
    # key_ids empty (a deck declaring no Roles) -> the two 1-prize bodies tie and neither is forced.
    assert o.bench_harvest(bench, [_spread(60)], reading=HARVEST_UNAVOIDABLE) == frozenset()


def _opp(*bodies):
    return list(bodies)


@pytest.mark.req("REQ-COMBAT-0071")
def test_the_bench_clock_accumulates_instead_of_reading_one_swing():
    o = _combat()
    me = _body(DREEPY, 70)
    they = _opp(_body(DRAGAPULT, 320, energies=[1, 1]))
    # 60 on a 70-HP body: survives the swing, not the second turn.
    assert o.turns_to_ko_me(me, they, my_benched=True, my_bench=[me],
                            reading=HARVEST_UNAVOIDABLE) == 2


@pytest.mark.req("REQ-COMBAT-0071")
def test_the_active_clock_accumulates_too():
    o = _combat()
    # Jetting Blow deals 120 to the Active. A 200-HP Active survives one swing, falls on the second.
    me = _body(WALL, 200)
    they = _opp(_body(STARMIE, 300, energies=[1]))
    assert o.turns_to_ko_me(me, they) == 2


@pytest.mark.req("REQ-COMBAT-0071")
def test_f82_the_rescue_only_picks_which_body_dies():
    """Evolving one Dreepy out of the spread's range buys nothing: the counters land on the other."""
    o = _combat()
    they = _opp(_body(DRAGAPULT, 320, energies=[1, 1]))

    before = [_body(DREEPY, 50), _body(DUNSPARCE, 50), _body(DREEPY, 50)]
    after = [_body(DRAKLOAK, 70), _body(DUNSPARCE, 50), _body(DREEPY, 50)]

    ko_pre = o.turns_to_ko_me(before[0], they, my_benched=True, my_bench=before,
                              key_ids=KEY_IDS, reading=HARVEST_UNAVOIDABLE)
    ko_post = o.turns_to_ko_me(after[0], they, my_benched=True, my_bench=after,
                               key_ids=KEY_IDS, reading=HARVEST_UNAVOIDABLE)
    assert ko_post - ko_pre == 0, "evolving out of the spread's range bought no survival"


@pytest.mark.req("REQ-COMBAT-0071")
def test_the_possible_reading_still_sees_the_threat_the_rescue_reading_discounts():
    """`POSSIBLE` must keep calling a redirectable body threatened, or a doom read grants the whole
    bench phantom safety."""
    o = _combat()
    they = _opp(_body(DRAGAPULT, 320, energies=[1, 1]))
    bench = [_body(DREEPY, 50), _body(DUNSPARCE, 50), _body(DREEPY, 50)]
    threat = o.turns_to_ko_me(bench[0], they, my_benched=True, my_bench=bench,
                              key_ids=KEY_IDS, reading=HARVEST_POSSIBLE)
    rescue = o.turns_to_ko_me(bench[0], they, my_benched=True, my_bench=bench,
                              key_ids=KEY_IDS, reading=HARVEST_UNAVOIDABLE)
    assert threat == 1 and rescue > threat


@pytest.mark.req("REQ-COMBAT-0071")
def test_an_undeclared_caller_gets_the_conservative_reading_and_a_solo_bench():
    """An undeclared caller must never be handed the optimistic answer (ADR-0070 §9)."""
    o = _combat()
    they = _opp(_body(DRAGAPULT, 320, energies=[1, 1]))
    me = _body(DREEPY, 50)
    assert o.turns_to_ko_me(me, they, my_benched=True) == 1


@pytest.mark.req("REQ-COMBAT-0071")
def test_a_bodys_survival_depends_on_the_company_it_keeps():
    """Why the evolve decider must SUBSTITUTE the evolved form into the bench rather than read it
    alone: a juicier bench-mate soaks the shared budget and genuinely buys my body time."""
    o = _combat()
    they = _opp(_body(DRAGAPULT, 320, energies=[1, 1]))
    lone = _body(DRAKLOAK, 70)
    crowd = [lone, _body(PLAIN_EX, 70)]
    alone = o.turns_to_ko_me(lone, they, my_benched=True, my_bench=[lone],
                             key_ids=KEY_IDS, reading=HARVEST_UNAVOIDABLE)
    among = o.turns_to_ko_me(lone, they, my_benched=True, my_bench=crowd,
                             key_ids=KEY_IDS, reading=HARVEST_UNAVOIDABLE)
    assert alone == 2                 # 60 + 60 >= 70 on the second turn
    assert among == 3                 # at t=2 the 2-prize ex is the better target; both fall at t=3


@pytest.mark.req("REQ-COMBAT-0071")
def test_a_benched_attacker_waits_on_energy_their_active_does_not_have():
    o = _combat()
    me = _body(DUNSPARCE, 70)
    wall = _body(WALL, 200)                       # retreatCost 2, holding nothing
    they = _opp(wall, _body(STARMIE, 300, energies=[1]))
    # Retreat is paid in Energy discard (rules.md:89), so the Starmie cannot come up this turn.
    assert o.incoming(me, they, 1, opp_active=wall) == 0
    # ...and with the retreat cost payable it can.
    wall_funded = _body(WALL, 200, energies=[1, 1])
    they_funded = _opp(wall_funded, _body(STARMIE, 300, energies=[1]))
    assert o.incoming(me, they_funded, 1, opp_active=wall_funded) == 120


@pytest.mark.req("REQ-COMBAT-0071")
def test_the_gate_opens_when_their_active_is_gone():
    """After a knockout the new Active is promoted for FREE (rulebook.txt:176), so the gate fails open."""
    o = _combat()
    me = _body(DUNSPARCE, 70)
    they = _opp(_body(STARMIE, 300, energies=[1]))   # their Active was removed from the list
    assert o.incoming(me, they, 1, opp_active=None) == 120


@pytest.mark.req("REQ-COMBAT-0071")
def test_a_switch_enabler_reopens_the_gate():
    """The gate can only make a threat read LESS pessimistic, so every leg fails open."""
    o = _combat()
    me = _body(DUNSPARCE, 70)
    wall = _body(WALL, 200)                       # retreatCost 2, holding nothing
    they = _opp(wall, _body(STARMIE, 300, energies=[1]))
    assert o.incoming(me, they, 1, opp_active=wall) == 0
    assert o.incoming(me, they, 1, opp_active=wall, switch_enabler=True) == 120


@pytest.mark.req("REQ-COMBAT-0071")
def test_their_own_active_is_never_gated():
    o = _combat()
    me = _body(DUNSPARCE, 70)
    starmie = _body(STARMIE, 300, energies=[1])
    assert o.incoming(me, _opp(starmie), 1, opp_active=starmie) == 120


class _Fn:
    def __init__(self, tags):
        self._t = tags

    def tags(self, cid):
        return self._t.get(cid, [])


class _Opp:
    def __init__(self, odds):
        self._o = odds

    def copies_left_odds(self, card_id=None):
        return self._o


def _pilot_stub(opponent, functions):
    from common.pilot import Pilot
    p = Pilot.__new__(Pilot)
    p.opponent, p.functions = opponent, functions
    return p


@pytest.mark.req("REQ-COMBAT-0071")
def test_the_switch_predicate_fails_open_on_every_unknown():
    """Opposite fail direction from `_opp_hand_strip_odds`: this OPENS a threat gate, that fires a veto."""
    assert _pilot_stub(None, _Fn({}))._opp_switch_enabler() is True
    assert _pilot_stub(_Opp({1: 1.0}), None)._opp_switch_enabler() is True
    assert _pilot_stub(_Opp({}), _Fn({}))._opp_switch_enabler() is True      # no confident Read


@pytest.mark.req("REQ-COMBAT-0071")
def test_the_switch_predicate_closes_only_when_provably_gone():
    """`copies_left_odds` returns 0 only when every copy is on board or in discard, so p > 0 is
    ADR-0067's not-provably-absent test."""
    fn = _Fn({7: ["switch"], 8: ["draw"]})
    assert _pilot_stub(_Opp({7: 0.4, 8: 1.0}), fn)._opp_switch_enabler() is True    # may hold one
    assert _pilot_stub(_Opp({7: 0.0, 8: 1.0}), fn)._opp_switch_enabler() is False   # all accounted
    # No switch-class card in the deck at all: nothing to rule out.
    assert _pilot_stub(_Opp({8: 1.0}), fn)._opp_switch_enabler() is False
