"""The promote/retreat CLOSURE term, driven above zero (ADR-0100 §5, #141).

The fixture ADR-0100 asks for by name, and the one term in the equation that had never been
exercised above zero on any board. Its build entailment: *"The missing fixture is authored as a
**SWITCH/whether** frame, one attach short with hand accel, driving `closure(B) > 0`."*

**Why it had to be a whether frame, not a forced promote.** The handoff recorded an open puzzle —
no corpus frame drove `fetch_enables_p` above 0 — and §5 explains it: the term was structurally
inert wherever it was mostly being asked. Per `docs/rulebook.txt` L173-176/L183 the replacement
Active is chosen immediately after the Knock-Out'ing attack resolves, or at Checkup, and attacking
ends your turn (`docs/rules.md` §5). So at a TO_ACTIVE promote **no play window remains** and the
draw window is ZERO by the rules, not by a policy choice. A voluntary retreat at MAIN is the only
site where a dig can still happen before the swap matters.

Both halves of that ruling are pinned below: the term fires at the whether site, and is exactly zero
at the forced promote on an otherwise identical board.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from common.strategy.context import _BASIC_ENERGY
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import MAIN, card_opt, make_select, opt, poke, state

TO_ACTIVE, RETREAT, END, BENCH = 4, 12, 14, 5
ABILITY = 10     # cg.api.OptionType.ABILITY — use an in-play Ability at the MAIN menu
WATER = 3
WINCON, DIGGER, OPENER, WATER_ENERGY, WALL = 1031, 1035, 666, 3, 900
A_PAYOFF, A_CHIP, A_WALL = 61, 62, 63


def _pilot():
    """A board one attach short: the win-condition holds 2 Energy toward a 3-Energy attack, my hand
    holds NO Energy, and the deck still holds Water Energy. A `dig:2` Ability is in play and still on
    the menu, so this turn can still draw the enabler — which is exactly the probabilistic MIDDLE
    `readiness_p` exists to price, between "already reaches" (1.0) and "cannot" (0.0)."""
    stats = DictCardStatProvider({
        WINCON: CardStat(WINCON, name="Wincon", hp=330, megaEx=True, minAttackCost=3,
                         maxDamage=210, maxDamageCost=3, energyType=WATER, attacks=(A_PAYOFF,)),
        DIGGER: CardStat(DIGGER, name="Digger", hp=90, hasAbility=True),
        OPENER: CardStat(OPENER, name="Opener", hp=160, minAttackCost=1, maxDamage=20,
                         maxDamageCost=1, attacks=(A_CHIP,)),
        WALL: CardStat(WALL, name="Wall", hp=400, minAttackCost=2, maxDamage=60,
                       maxDamageCost=2, attacks=(A_WALL,)),
        WATER_ENERGY: CardStat(WATER_ENERGY, name="Water Energy", hp=0, energyType=WATER,
                               cardType=_BASIC_ENERGY),
    }, attacks={A_PAYOFF: AttackStat(A_PAYOFF, damage=210, cost=3, energyTypes=(WATER, WATER, WATER)),
                A_CHIP: AttackStat(A_CHIP, damage=20, cost=1),
                A_WALL: AttackStat(A_WALL, damage=60, cost=2)})
    strat = Strategy(lines=[Line(path=[WINCON], payoff=WINCON, role="win_condition")],
                     roles={WINCON: ["win_condition", "primary_attacker"]})
    deck = [WATER_ENERGY] * 12 + [WINCON] * 4 + [OPENER] * 4 + [DIGGER] * 4 + [1] * 36
    return Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({DIGGER: ["dig:2"], OPENER: ["opener"]}))


def _board(*, one_short=True):
    """My Active is the spent Opener; the Bench holds the win-condition (one attach short of its
    payoff, or already armed) and the Digger whose Ability is still unused.

    The wincon's attached Energy is Basic {W} by CARD, because the payoff costs ``{W}{W}{W}`` and a
    body's attached colour is now read off the units the engine reports (Issue #297). The old
    `energy=N` default attaches COLORLESS units, which pay colourless slots only — against a fully
    typed cost that is a board one short of nothing, and the term under test reads zero for a reason
    that has nothing to do with what it measures."""
    energy = 2 if one_short else 3
    return state(active=poke(OPENER, energy=1, hp=160),
                 bench=[poke(WINCON, energy=energy, hp=330, energy_card=WATER_ENERGY),
                        poke(DIGGER, hp=90)],
                 opp_active=poke(WALL, hp=400), turn=6, prizes=4, opp_prizes=4, deck_count=40)


def _whether_obs(**kw):
    """A MAIN menu carrying a native RETREAT — and the Digger's ABILITY still on the menu, which is
    what makes the draw window non-zero (the menu is the fact about whether a use is left)."""
    return make_select([opt(RETREAT), opt(ABILITY, area=BENCH, index=1), opt(END)],
                       context=MAIN, current=_board(**kw))


def _forced_promote_obs(**kw):
    return make_select([card_opt(BENCH, 0), card_opt(BENCH, 1)],
                       context=TO_ACTIVE, current=_board(**kw))


def _row(pilot, obs, index=0):
    return pilot.explain(obs).options[index].promote_retreat_working


def test_closure_is_positive_at_the_whether_site_when_the_body_is_one_attach_short():
    """The term, alive. The win-condition cannot pay its 210-damage payoff right now, but the
    Energy that would pay it is still in the deck and this turn can still dig two cards deep — so the
    retreat is credited `damage x Δreadiness_p`, a real partial rather than the interim 1.0/0.0."""
    p = _pilot()
    row = _row(p, _whether_obs())
    assert row is not None and row["site"] == "whether"
    assert row["closure"] > 0.0


def test_closure_is_bounded_by_the_damage_it_unlocks():
    """`Δ <= 1` bounds the term below `damage(a)` BY CONSTRUCTION, which is what let §5 delete the
    shipped interim `min(1.0, p) x _READY` clamp: "closure can never beat actually being ready"
    becomes structural rather than clamped. A strict inequality, because the enabler is only
    probable — the body is not ready, it might become ready."""
    p = _pilot()
    row = _row(p, _whether_obs())
    assert 0.0 < row["closure"] < 210.0


def test_an_already_armed_body_earns_no_closure_credit():
    """Δ is ZERO on a body that already reaches, so being ready is never paid twice. This is the
    property that makes a redundant engine worth exactly nothing without a saturation rule — the same
    argument ADR-0070 decision 3 makes for the evolve decider's income term."""
    p = _pilot()
    armed = _row(p, _whether_obs(one_short=False))
    assert armed["closure"] == 0.0
    assert armed["my_yield"] > 0                      # …because it is simply READY instead


def test_the_forced_promote_earns_no_closure_because_no_play_window_remains():
    """§5's rulebook finding, as an executable assertion. On the SAME board, a TO_ACTIVE promote
    prices the identical body with the draw window at zero: the replacement Active is chosen right
    after the Knock-Out'ing attack resolves or at Checkup, and attacking ends the turn, so there is
    no dig left to find the enabler with.

    This is the whole explanation for the handoff's open puzzle — the term was inert wherever it was
    mostly being asked, which is why the fixture above had to be a whether frame."""
    p = _pilot()
    rows = [t.promote_retreat_working for t in p.explain(_forced_promote_obs()).options]
    assert all(r["site"] == "pick" for r in rows)
    assert all(r["closure"] == 0.0 for r in rows)


@pytest.mark.parametrize("one_short", [True, False])
def test_the_term_never_goes_negative(one_short):
    """A body whose odds get WORSE is not a thing the term can express: `Δ` is floored at 0, so
    closure is an endorsement channel only — fail-closed, per ADR-0067."""
    p = _pilot()
    assert _row(p, _whether_obs(one_short=one_short))["closure"] >= 0.0
