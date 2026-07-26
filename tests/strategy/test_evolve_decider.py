"""Evolve decider (common/evolve_value.py) — ADR-0070. The PURE-FUNCTION seam.

The equation as one expression, in the DAMAGE currency #139 established:

    deploy(X) = max( this_turn(X), payoff_damage(X) x p_arrive(X) x p_survive(X) )
    value     = deploy(R) - deploy(B) + income_gain - income_loss

`this_turn` is typed, certain and immediate (the #137 reachability read). The forward term is the
LINE PAYOFF discounted by when the line arms (`turns_to_afford`, hop-aware) and whether the body
survives to use it (`turns_to_ko_me`). Because both bodies build toward the SAME line payoff, the
payoff damage cancels in the difference and the deploy delta is driven purely by the two clocks —
which is the point: evolving is worth exactly what it does to those clocks.

Card facts VERIFIED at source (data/EN_Card_Data.csv, docs/rules.md), never recalled:
  * Drakloak (120) HP 90, Dragon Headbutt {R}{P} 70; Ability Recon Directive "look at the top 2
    cards of your deck and put 1 of them into your hand", once per turn, persistent.
  * Dragapult ex (121) HP 320, Phantom Dive {R}{P} 200 (+6 counters). Tera: no attack damage while
    Benched. IDENTICAL attack cost to its pre-evolution's -- so the evolve decision collapses to
    "can I pay {R}{P}?", and the doctrine derives with no threshold.
  * Staryu (1030) HP 70, Water Gun {W} 20. Mega Starmie ex (1031) HP 330, Jetting Blow {W} 120,
    Nebula Beam (3 colourless) 210. One hop.
"""
from common.evolve_value import EvolveBody, EvolveInputs, evolve_value

PHANTOM_DIVE, DRAGON_HEADBUTT = 200.0, 70.0
NEBULA, JETTING, WATER_GUN = 210.0, 120.0, 20.0
SAFE = 9                                     # turns_to_ko_me horizon: nothing threatens it


def _v(body, result, **kw):
    return evolve_value(EvolveInputs(body=body, result=result, **kw))


# ── deploy: the two clocks drive the delta ─────────────────────────────────────────────────────

def test_evolve_and_swing_when_the_shared_cost_is_payable():
    """The Dragapult doctrine, half one. Drakloak and Dragapult ex both cost {R}{P}; with it paid,
    evolving converts a 70 into a 200. Drakloak still owes the HOP, so its forward credit is halved
    while the evolved form's is whole."""
    got = _v(EvolveBody(this_turn=DRAGON_HEADBUTT, payoff_damage=PHANTOM_DIVE, arm=1, ko=SAFE),
             EvolveBody(this_turn=PHANTOM_DIVE, payoff_damage=PHANTOM_DIVE, arm=0, ko=SAFE))
    assert got.deploy == 100.0                # 200 - max(70, 200 x 0.5)
    assert got.total > 0                      # evolve


def test_hold_when_the_shared_cost_is_unpayable_and_the_engine_is_persistent():
    """The Dragapult doctrine, half two. Neither body can attack, so the clocks read identically and
    deploy is ZERO -- the hop buys nothing while the energy leg dominates. The Recon stream is then
    the only term left, and it says hold."""
    got = _v(EvolveBody(this_turn=0.0, payoff_damage=PHANTOM_DIVE, arm=2, ko=SAFE),
             EvolveBody(this_turn=0.0, payoff_damage=PHANTOM_DIVE, arm=2, ko=SAFE),
             ready_loss=0.5, hold_turns=2)
    assert got.deploy == 0.0
    assert got.income_loss > 0
    assert got.total < 0                      # hold and keep digging


def test_a_free_hop_is_worth_nothing_and_says_so():
    """Attaching and evolving run in PARALLEL, so a hop only costs time when hops OUTNUMBER the
    energy turns owed. A bare Staryu is 3 Energy and 1 hop from Nebula Beam: the hop is free, both
    clocks read 3, and the honest deploy is zero (tier-0 sequencing takes the free evolve)."""
    got = _v(EvolveBody(payoff_damage=NEBULA, arm=3, ko=SAFE),
             EvolveBody(payoff_damage=NEBULA, arm=3, ko=SAFE))
    assert got.deploy == 0.0
    assert got.total == 0.0


def test_a_binding_hop_is_worth_a_measured_turn():
    """When the hops DO bind -- Energy already down, two hops owed -- evolving buys a real turn and
    the clock prices it."""
    got = _v(EvolveBody(payoff_damage=PHANTOM_DIVE, arm=2, ko=SAFE),
             EvolveBody(payoff_damage=PHANTOM_DIVE, arm=1, ko=SAFE))
    assert got.deploy == 50.0                 # 200 x 0.5 - 200 x 0.25


def test_this_turn_is_undiscounted_and_can_carry_the_evolve_alone():
    """Gap 2's frame. A 2-Energy Staryu cannot fire Nebula Beam and the hop is free, so the forward
    legs cancel -- but Jetting Blow {W} 120 IS payable on the evolved form where Water Gun's 20 is
    all the pre-evolution has. The immediate, typed term carries it."""
    got = _v(EvolveBody(this_turn=WATER_GUN, payoff_damage=NEBULA, arm=1, ko=SAFE),
             EvolveBody(this_turn=JETTING, payoff_damage=NEBULA, arm=1, ko=SAFE))
    assert got.deploy == 15.0                 # max(120, 105) - max(20, 105)


def test_survival_weighting_prices_the_escape_into_bench_immunity():
    """The user's posture frame: a threatened benched Drakloak evolving into a Tera Dragapult ex,
    which takes NO attack damage while Benched. The KO clock jumps, and the forward credit with it."""
    threatened = _v(EvolveBody(payoff_damage=PHANTOM_DIVE, arm=1, ko=1),
                    EvolveBody(payoff_damage=PHANTOM_DIVE, arm=0, ko=SAFE))
    safe = _v(EvolveBody(payoff_damage=PHANTOM_DIVE, arm=1, ko=SAFE),
              EvolveBody(payoff_damage=PHANTOM_DIVE, arm=0, ko=SAFE))
    assert threatened.deploy > safe.deploy    # rescue is worth more than the same evolve when safe


def test_doomed_both_ways_earns_nothing_from_the_evolve():
    """ADR-0070 §5: the doom override is deleted because survival weighting says this outright. If
    the evolved form dies just as fast, the rescue is fiction and deploy collapses."""
    got = _v(EvolveBody(payoff_damage=PHANTOM_DIVE, arm=2, ko=1),
             EvolveBody(payoff_damage=PHANTOM_DIVE, arm=2, ko=1))
    assert got.deploy == 0.0


def test_an_unknown_armed_clock_fails_closed():
    """ADR-0067's fail direction: an unreadable clock makes NO claim rather than a generous one."""
    got = _v(EvolveBody(payoff_damage=PHANTOM_DIVE, arm=None, ko=SAFE),
             EvolveBody(payoff_damage=PHANTOM_DIVE, arm=None, ko=SAFE))
    assert got.deploy == 0.0


# ── income: an odds read with a SPLIT horizon ──────────────────────────────────────────────────

def test_income_gain_is_immediate_when_the_result_ability_is_usable_now():
    """Evolve -> use the evolved form's Ability is ONE legal turn (rules.md:91; the menu re-presents),
    so the gain is undiscounted."""
    b = EvolveBody(payoff_damage=PHANTOM_DIVE, arm=1, ko=SAFE)
    now = _v(b, b, ready_gain=0.5, result_ability_now=True)
    later = _v(b, b, ready_gain=0.5, result_ability_now=False)
    assert now.income_gain == 100.0           # 200 x 0.5, undiscounted
    assert later.income_gain < now.income_gain


def test_income_loss_excludes_this_turn_once_the_ability_is_off_the_menu():
    """The sequencer takes the free Ability at tier 0, so evolving does not forfeit THIS turn's
    Recon. The fact is READ off the menu, never inferred from an assumed ordering."""
    b = EvolveBody(payoff_damage=PHANTOM_DIVE, arm=1, ko=SAFE)
    used = _v(b, b, ready_loss=0.5, hold_turns=2, body_ability_on_menu=False)
    unused = _v(b, b, ready_loss=0.5, hold_turns=2, body_ability_on_menu=True)
    assert unused.income_loss - used.income_loss == 100.0     # exactly one undiscounted use


def test_the_future_stream_is_halved_per_turn_out():
    """`deny_slot`'s shipped halving, reused rather than a new decay rate: the stream over n turns is
    the geometric sum, so a longer hold is worth more but with diminishing weight."""
    b = EvolveBody(payoff_damage=PHANTOM_DIVE, arm=1, ko=SAFE)
    one = _v(b, b, ready_loss=1.0, hold_turns=1, body_ability_on_menu=False)
    two = _v(b, b, ready_loss=1.0, hold_turns=2, body_ability_on_menu=False)
    assert one.income_loss == 100.0                      # 200 x (1 - 2^-1)
    assert two.income_loss == 150.0                      # 200 x (1 - 2^-2)


def test_the_hold_collapses_to_zero_the_moment_the_body_is_ready():
    """Ruling 1 DERIVED: an engine on an armed body buys no readiness, so `ready_loss` is 0 and the
    hold pressure vanishes -- no `turns_to_ready` gate, no -46 rung."""
    b = EvolveBody(this_turn=DRAGON_HEADBUTT, payoff_damage=PHANTOM_DIVE, arm=0, ko=SAFE)
    r = EvolveBody(this_turn=PHANTOM_DIVE, payoff_damage=PHANTOM_DIVE, arm=0, ko=SAFE)
    assert _v(b, r, ready_loss=0.0, hold_turns=0).income_loss == 0.0


def test_a_one_shot_engine_forfeits_one_use_never_a_stream():
    """The recycle card-fact splits the HORIZON, not the magnitude: a self-shuffling one-shot is a
    single deadline-0 burst, so no future stream is lost by evolving."""
    b = EvolveBody(payoff_damage=PHANTOM_DIVE, arm=2, ko=SAFE)
    one_shot = _v(b, b, ready_loss=0.5, hold_turns=3, body_ability_oneshot=True,
                  body_ability_on_menu=True)
    stream = _v(b, b, ready_loss=0.5, hold_turns=3, body_ability_oneshot=False,
                body_ability_on_menu=True)
    assert one_shot.income_loss == 100.0                 # the single unused burst, nothing more
    assert stream.income_loss > one_shot.income_loss


def test_total_is_the_sum_of_the_three_terms():
    b = EvolveBody(this_turn=DRAGON_HEADBUTT, payoff_damage=PHANTOM_DIVE, arm=1, ko=SAFE)
    r = EvolveBody(this_turn=PHANTOM_DIVE, payoff_damage=PHANTOM_DIVE, arm=0, ko=SAFE)
    got = _v(b, r, ready_gain=0.25, result_ability_now=True, ready_loss=0.5, hold_turns=2)
    assert got.total == got.deploy + got.income_gain - got.income_loss
