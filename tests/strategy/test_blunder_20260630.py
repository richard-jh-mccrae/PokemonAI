"""Blunder round 2026-06-30 (mega_starmie) — the rules + signals authored by /blunder-buster.

Four fixes, each pinned to the correction it resolves (ADR-0018). Lib-free: synthetic obs dicts via
pilot_helpers + DictCardStatProvider, so the fast suite needs no native engine.

  - dont-waste-discard-energy (new branch)  ep82717711-fr18: don't burn Ignition on an already-powered
                                            non-wincon (covered end-to-end in test_discard_energy.py too)
  - _attach_lethal_tactical turn<=1 guard   ep82226116-fr7 : no phantom lethal on turn 1 going first
  - _retreat_to_lethal_tactical             ep82717711-fr37: retreat the spent opener into the ready
                                            wincon to TAKE the KO with the right attacker
  - spread-attach-to-the-needy              ep82224509-fr31: at ATTACH_FROM (Turbo Flare's bench attach),
                                            put the Energy on the bare body, not an already-powered one
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from pilot_helpers import (
    ACTIVE, ATTACH_FROM, BENCH, HAND, attack_opt, card_opt, make_select, opt, poke, state)

ATTACH = 8
RETREAT = 12
END = 14
WINCON = 900        # Mega Starmie ex shape: Jetting Blow {W} 120 (+50 snipe), Nebula CCC 210
PREEVO = 800        # Staryu shape (bare bench body, needs Energy)
CINDER = 666        # an opener/accelerator (Cinderace shape): Stage-2 Evolution, 1-cost 50-dmg attack
WATER = 3
IGNITION = 17
OPP = 678


def _fired(o):
    return {h.id for h, _ in o.fired}


def _stats():
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                         maxDamageCost=3, minAttackCost=1, minCostDamage=120, attacks=(10, 11),
                         evolvesFrom="Staryu", energyType=3),
        PREEVO: CardStat(PREEVO, name="Staryu", hp=70, maxDamage=20, maxDamageCost=1,
                         minAttackCost=1, minCostDamage=20, attacks=(12,)),
        CINDER: CardStat(CINDER, name="Cinderace", hp=160, maxDamage=50, maxDamageCost=1,
                         minAttackCost=1, minCostDamage=50, attacks=(20,), evolvesFrom="Raboot",
                         energyType=2),                      # {R} — needed for turn-1 weakness test
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
        IGNITION: CardStat(IGNITION, name="Ignition Energy", hp=0, energyType=0),
        OPP: CardStat(OPP, name="opp", hp=60, weakness=2),  # weak to {R} -> Cinderace doubles into it
    }, attacks={
        # Jetting Blow (11) carries a 50-dmg bench-snipe rider; Nebula (10) doesn't.
        10: AttackStat(10, damage=210, cost=3),
        11: AttackStat(11, damage=120, cost=1, benchSnipe=50),
        12: AttackStat(12, damage=20, cost=1),
        20: AttackStat(20, damage=50, cost=1),
    })


def _pilot(**kw):
    return Pilot(Strategy(roles={WINCON: ["win_condition", "primary_attacker"]},
                          lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)]),
                 deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=CardFunctions({IGNITION: ["discard_eot"]}), **kw)


# ----------------------------------------------- dont-waste-discard-energy: already-powered non-wincon
@pytest.mark.req("REQ-GEN-0048")
def test_dont_waste_ignition_on_an_already_powered_cinderace():
    """ep82717711-fr18: Cinderace Active already holds a {W} for its 1-cost Turbo Flare. Attaching
    Ignition adds nothing (it discards at end of turn) — so the agent should just attack, not attach."""
    pilot = _pilot()
    attach_ign = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)   # Ignition hand[0]
    attack = attack_opt(20)                                                          # Turbo Flare, 50
    obs = make_select([attach_ign, attack, opt(END)],
                      current=state(active=poke(CINDER, energy=1, hp=160),
                                    opp_active=poke(OPP, hp=60), hand=[IGNITION]))
    traces = pilot.explain(obs)
    # the wasteful Ignition attach: it evaporates uncashed, so it costs its own worth (ADR-0069 §5a)
    assert next(r for r in traces.attach_working["eq"] if r["i"] == 0)["evaporates"] is True
    assert traces.options[0].tactical < 0
    assert traces.options[0].score <= 0                               # sunk -> sequenced last (tier 4)
    assert pilot.decide(obs) == [1]                                   # attack, don't waste it


# ----------------------------------------------- _attach_lethal_tactical: turn-1-going-first guard
@pytest.mark.req("REQ-GEN-0049")
def test_lethal_attach_stands_down_on_turn_one_going_first():
    """ep82226116-fr7: on turn 1 the first player CANNOT attack (rules.md §first-turn), so attaching
    a burst Energy that would 'unlock' a KO is illusory — the lethal-attach lookahead must return 0
    (else it tiers the attach as 'take the win' and the Energy is discarded for nothing)."""
    pilot = _pilot()
    attach_ign = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)
    # Cinderace 0 Energy; opp 60 HP weak to {R} -> +Ignition lets Turbo Flare (50x2=100) KO.
    cur = state(active=poke(CINDER, energy=0, hp=160), opp_active=poke(OPP, hp=60), hand=[IGNITION], turn=1)
    obs = make_select([attach_ign, opt(END)], current=cur)
    # no phantom lethal on turn 1 — and the burst is scored BELOW doing nothing, which is the whole
    # of `dont-attach-discard-energy-turn1` without a −60 rung (ADR-0069 §5a).
    assert pilot.explain(obs).options[0].tactical < 0
    assert pilot.decide(obs) == [1]                                  # End beats the wasted attach

    # Control: same board, later turn -> lethal attach is real (CAN attack) -> KO-class.
    later = state(active=poke(CINDER, energy=0, hp=160), opp_active=poke(OPP, hp=60), hand=[IGNITION], turn=3)
    assert pilot.explain(make_select([attach_ign, opt(END)], current=later)).options[0].tactical >= KO_SCORE


# ----------------------------------------------- _retreat_to_lethal_tactical
@pytest.mark.req("REQ-GEN-0050")
def test_retreat_into_ready_wincon_to_take_the_ko():
    """ep82717711-fr37: a spent Cinderace Active can KO the 10-HP opponent, but the fully-powered
    benched Mega Starmie ex can take the SAME KO (and snipe the bench). Retreat into the wincon —
    same prize, the tanky win-condition ends up Active — instead of chipping with the spent opener."""
    pilot = _pilot()
    attack = attack_opt(20)                                          # Cinderace Turbo Flare 50 -> KO (opp 10)
    cur = state(active=poke(CINDER, energy=1, hp=160),
                bench=[poke(WINCON, energy=3, hp=330)],             # ready wincon (Jetting Blow affordable)
                opp_active=poke(OPP, hp=10), opp_bench=[poke(PREEVO, hp=60)])  # bench target -> snipe rider
    obs = make_select([attack, opt(RETREAT), opt(END)], context=0, current=cur)
    traces = pilot.explain(obs)
    assert traces.options[0].tactical >= KO_SCORE                    # Active's own attack is a KO ...
    assert traces.options[1].tactical >= KO_SCORE                    # ... and so is retreat->wincon KO
    assert traces.options[1].tactical > traces.options[0].tactical   # wincon's KO (snipe) is better
    assert pilot.decide(obs) == [1]                                  # retreat into it



def _lethal_only(trace) -> float:
    """The RETREAT-to-lethal layer's own contribution, with the promote/retreat decider's residual
    netted out.

    `OptionTrace.tactical` is a SUM across layers (ADR-0069 §1: `max` within an axis, sum across),
    and since ADR-0100 (#141) a RETREAT option also carries the promote/retreat decider's Sub-lethal
    Residual. These frames are about whether the LETHAL lookahead fires, so pinning the total would
    now assert two claims at once and fail on the one it never meant to make."""
    row = trace.promote_retreat_working
    return trace.tactical - (row["tactical"] if row is not None else 0.0)

@pytest.mark.req("REQ-GEN-0050")
def test_retreat_lethal_stands_down_when_no_benched_wincon_can_ko():
    """The lookahead never forfeits a KO: when no ready benched wincon can KO the opponent's Active,
    the retreat carries no KO-class value (so a genuine Active KO is still taken)."""
    pilot = _pilot()
    attack = attack_opt(20)
    cur = state(active=poke(CINDER, energy=1, hp=160),
                bench=[poke(WINCON, energy=0, hp=330)],             # NOT ready -> can't KO after retreat
                opp_active=poke(OPP, hp=10))
    obs = make_select([attack, opt(RETREAT), opt(END)], context=0, current=cur)
    traces = pilot.explain(obs)
    assert _lethal_only(traces.options[1]) == 0                      # retreat carries no lethal value
    assert pilot.decide(obs) == [0]                                  # take the Active's KO instead


@pytest.mark.req("REQ-GEN-0050")
def test_retreat_lethal_does_not_fire_when_the_active_is_the_wincon():
    """Don't retreat the win-condition itself — the lookahead is for swapping a SPENT opener in."""
    pilot = _pilot()
    cur = state(active=poke(WINCON, energy=3, hp=330),
                bench=[poke(WINCON, energy=3, hp=330)], opp_active=poke(OPP, hp=10))
    obs = make_select([attack_opt(11), opt(RETREAT), opt(END)], context=0, current=cur)
    assert _lethal_only(pilot.explain(obs).options[1]) == 0


@pytest.mark.req("REQ-GEN-0050")
def test_retreat_lethal_stands_down_when_the_active_already_takes_an_equal_ko():
    """ep82867148 f62: the Active (a Cinderace) ALREADY KOs the opponent, and a benched body would take
    only the SAME single-prize KO — so retreat-to-lethal stands down (it fires ONLY for a STRICTLY
    BETTER KO). Don't waste the Active's attack and strand an energised base you would rather evolve."""
    pilot = _pilot()
    attack = attack_opt(20)                                          # Cinderace Turbo Flare 50 -> KO (opp 10)
    cur = state(active=poke(CINDER, energy=1, hp=160),
                bench=[poke(PREEVO, energy=4, hp=70)],               # energised Staryu: also KOs, but only
                opp_active=poke(OPP, hp=10))                          # the SAME 1-prize KO (no snipe edge)
    obs = make_select([attack, opt(RETREAT), opt(END)], context=0, current=cur)
    traces = pilot.explain(obs)
    assert traces.options[0].tactical >= KO_SCORE                    # Active's own attack is a KO
    assert _lethal_only(traces.options[1]) == 0                      # no EXTRA value -> stand down
    assert pilot.decide(obs) == [0]                                  # just attack with the Active


# ----------------------------------------------- spread-attach-to-the-needy (ATTACH_FROM)
@pytest.mark.req("REQ-GEN-0051")
def test_spread_attach_to_the_needy_at_attach_from():
    """ep82224509-fr31: Turbo Flare's 'attach a Basic to a Benched Pokémon' (SelectContext ATTACH_FROM)
    offers an already-powered Mega Starmie ex (3 E) and a bare Staryu (0 E). Put it on the bare body
    that still needs Energy, not the one already online."""
    pilot = _pilot()
    powered = card_opt(BENCH, 0)        # bench[0] = Mega Starmie ex, 3 Energy (doesn't need)
    bare = card_opt(BENCH, 1)           # bench[1] = Staryu, 0 Energy (needs)
    cur = state(active=poke(CINDER, energy=1, hp=160),
                bench=[poke(WINCON, energy=3, hp=330), poke(PREEVO, energy=0, hp=70)])
    obs = make_select([powered, bare], context=ATTACH_FROM, current=cur)
    traces = pilot.explain(obs)
    assert "spread-attach-to-the-needy" not in _fired(traces.options[0])   # already powered
    assert next(r for r in traces.attach_working["eq"] if r["i"] == 1)["build"] > 0  # bare body needs it
    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0051")
def test_attach_from_target_needs_signal_is_off_outside_attach_from():
    """The signal is scoped to ATTACH_FROM — a CARD option in another context carries no spread nudge."""
    pilot = _pilot()
    bare = card_opt(BENCH, 1)
    cur = state(active=poke(CINDER, energy=1, hp=160),
                bench=[poke(WINCON, energy=3, hp=330), poke(PREEVO, energy=0, hp=70)])
    obs = make_select([bare], context=0, current=cur)        # MAIN, not ATTACH_FROM
    assert "spread-attach-to-the-needy" not in _fired(pilot.explain(obs).options[0])


# ----------------------------------------------- concentrate-accel-on-one-line-body (ATTACH_FROM)
@pytest.mark.req("REQ-GEN-0051")
def test_concentrate_accel_on_one_line_body_at_attach_from():
    """ep83116081-fr21: Turbo Flare offers two Staryu recipients — one already carrying 1 Energy, one
    bare. `spread-attach-to-the-needy` reads the 1-Energy Staryu as 'done' (it clears Staryu's own
    1-cost attack), but the deck's payoff is the 3-Energy Mega — so CONCENTRATE the accelerated Energy
    on the started Staryu to bring ONE body online, don't spread onto the bare one."""
    pilot = _pilot()
    started = card_opt(BENCH, 0)     # bench[0] = Staryu, 1 Energy (closest to the Mega payoff)
    bare = card_opt(BENCH, 1)        # bench[1] = Staryu, 0 Energy
    cur = state(active=poke(CINDER, energy=1, hp=160),
                bench=[poke(PREEVO, energy=1, hp=70), poke(PREEVO, energy=0, hp=70)])
    obs = make_select([started, bare], context=ATTACH_FROM, current=cur)
    traces = pilot.explain(obs)
    rows = {r["i"]: r for r in traces.attach_working["eq"]}
    assert rows[0]["build"] > rows[1]["build"]                          # convexity concentrates
    assert "concentrate-accel-on-one-line-body" not in _fired(traces.options[1])   # bare body
    assert pilot.decide(obs) == [0]

    # EVOLVED win-condition (Mega) beats a MORE-energised pre-evo — it's the actual attacker
    # (no evolution step left), so concentrate on it (ep83007714-fr22 wants Mega, not Staryu).
    cur2 = state(active=poke(CINDER, energy=1, hp=160),
                 bench=[poke(WINCON, energy=1, hp=330), poke(PREEVO, energy=2, hp=70)])
    obs2 = make_select([card_opt(BENCH, 0), card_opt(BENCH, 1)], context=ATTACH_FROM, current=cur2)
    assert pilot.decide(obs2) == [0]     # Mega, though Staryu carries more Energy


# ----------------------------------------------- conserve-burst-when-no-ko (discard_eot vs un-KO-able Active)
@pytest.mark.req("REQ-GEN-0051")
def test_conserve_burst_when_the_opponent_cannot_be_koed_even_maxed():
    """ep83116501-fr70: the Active Mega Starmie can't KO the opponent's Active even fully powered
    (Nebula Beam 210 < 300 HP). Don't burn the one-shot Ignition to reach Nebula — attach the reusable
    Basic (Jetting Blow 120 + a snipe is as useful and KEEPS the Ignition for a turn it can finish)."""
    pilot = _pilot()
    ign = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)     # Ignition -> Active
    water = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)   # Basic {W} -> Active
    cur = state(active=poke(WINCON, energy=0, hp=330), opp_active=poke(OPP, hp=300),
                hand=[IGNITION, WATER])
    obs = make_select([ign, water, opt(END)], context=0, current=cur)
    traces = pilot.explain(obs)
    rows = {r["i"]: r for r in traces.attach_working["eq"]}
    assert rows[0]["tactical"] < rows[1]["tactical"]     # the burst is capped + costs the tie-break
    assert "conserve-burst-when-no-ko" not in _fired(traces.options[1])   # not the reusable Basic
    assert pilot.decide(obs) == [1]                                       # attach the Basic, keep Ignition

    # Control: KO-able Active (60 HP < 210 maxed) — burst DOES buy the KO, exemption holds.
    cur2 = state(active=poke(WINCON, energy=0, hp=330), opp_active=poke(OPP, hp=60), hand=[IGNITION, WATER])
    obs2 = make_select([ign, water, opt(END)], context=0, current=cur2)
    assert "conserve-burst-when-no-ko" not in _fired(pilot.explain(obs2).options[0])
