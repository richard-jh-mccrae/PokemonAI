"""Lethal Solver (ADR-0030): the eager, sound, this-turn win-detector.

Behaviour through the Pilot's PUBLIC interface (``decide`` / ``explain``): when a guaranteed win
exists THIS turn, ``explain(obs).lethal`` names the line and ``decide`` takes its next step. Lib-free
(the closed-form layer); the engine-verified slices live in the engine-backed suite.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.telemetry import to_record
from pilot_helpers import ACTIVE, ATTACH, HAND, PLAY, attack_opt, make_select, opt, poke, state

END = 14  # OptionType.END (pilot_helpers doesn't export it)

WINCON = 900   # my Active attacker / win-condition (Mega Starmie ex shape)
PREEVO = 800   # Staryu — Line base (evolves into WINCON), weak attacker alone
OPP = 678      # opponent's Active
JETTING = 11   # attack id: cost 1, 120 dmg
NEBULA = 10    # attack id: cost 3, 210 dmg (big attack, extra Energy unlocks it)
STARYU = 12    # Staryu's own attack: cost 1, 20 dmg (no KO)
SNIPE = 15     # snipe attack: cost 1, 50 to Active + 100 bench-snipe rider
WATER = 3      # Basic {W} Energy card in hand
WALLYS = 1229  # Wally's Compassion — clutch_heal (heals a Mega ex, BOUNCES all its Energy to hand)
BOSS = 1182    # Boss's Orders — gust Supporter (drags a benched Pokémon to Active Spot)
EVOLVE = 9     # OptionType.EVOLVE (pilot_helpers doesn't export it)
RETREAT = 12   # OptionType.RETREAT (pilot_helpers doesn't export it)
EXOPP = 679    # opponent's Active: a Pokémon ex (2 prizes)
BENCHIE = 700  # opponent's benched body (1 prize), KO-able by snipe rider


def _stats():
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, name="Mega Starmie ex", hp=330, energyType=3, minAttackCost=1,
                         minCostDamage=120, maxDamage=210, maxDamageCost=3,
                         attacks=(JETTING, NEBULA, SNIPE), evolvesFrom="Staryu"),
        PREEVO: CardStat(PREEVO, name="Staryu", hp=70, energyType=3, minAttackCost=1,
                         minCostDamage=20, maxDamage=20, attacks=(STARYU,)),
        OPP: CardStat(OPP, name="opp active", hp=120, energyType=7),
        EXOPP: CardStat(EXOPP, name="opp ex", hp=330, energyType=7, ex=True),
        BENCHIE: CardStat(BENCHIE, name="opp benchie", hp=100, energyType=7),
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
    })


def _pilot(**kw):
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_stats(), functions=CardFunctions({WALLYS: ["heal", "clutch_heal"], BOSS: ["gust"]}),
                 attacks={JETTING: 120, NEBULA: 210, STARYU: 20, SNIPE: 50},
                 attack_costs={JETTING: 1, NEBULA: 3, STARYU: 1, SNIPE: 1},
                 bench_snipe={SNIPE: 100}, **kw)


@pytest.mark.req("REQ-LETHAL-0001")
def test_immediate_prize_out_ko_is_a_locked_lethal_line_taken_now():
    """Tracer bullet: my Active can KO the opponent's Active (Jetting Blow 120 vs 120 HP) and it takes
    my LAST prize -> a guaranteed win THIS turn. The Solver locks the 1-step line and the Pilot takes
    the attack; ``explain(obs).lethal`` surfaces the line."""
    pilot = _pilot()
    # Active powered for Jetting Blow (1 W); opp Active at 120 HP (a KO); my last prize (1 left).
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                prizes=1, opp_prizes=2)
    obs = make_select([attack_opt(JETTING), opt(END)], current=won)

    d = pilot.explain(obs)
    assert d.lethal is not None                    # guaranteed winning line found + locked
    assert d.lethal.next_step == [0]               # next step: the finishing attack
    assert pilot.decide(obs) == [0]                # ... Pilot takes it


@pytest.mark.req("REQ-LETHAL-0002")
def test_empty_bench_ko_is_lethal_even_when_prizes_are_not_last():
    """A KO of the opponent's Active while their Bench is EMPTY wins the game (they have no Pokémon
    left to promote) — a win even though it does NOT take my last prize. The Solver locks it."""
    pilot = _pilot()
    # 3 prizes left (not prize-out), but opponent's Bench empty: KO their Active = they lose.
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                opp_bench=[], prizes=3, opp_prizes=2)
    obs = make_select([attack_opt(JETTING), opt(END)], current=won)
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.next_step == [0]   # empty-bench win detected + taken
    assert pilot.decide(obs) == [0]

    # Control — opponent has a benched Pokémon, so KO is NOT a win (they promote); prizes not last ->
    # no lethal to lock.
    not_won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                    opp_bench=[poke(OPP, hp=120)], prizes=3, opp_prizes=2)
    obs_c = make_select([attack_opt(JETTING), opt(END)], current=not_won)
    assert pilot.explain(obs_c).lethal is None


@pytest.mark.req("REQ-LETHAL-0003")
def test_enabling_attach_is_locked_and_the_breaker_is_vetoed():
    """CRITICAL 040c shape: the Active needs ONE more Energy to KO for the win. Attaching it unlocks
    Nebula Beam (210 vs 180); the Solver locks the 2-step line (attach -> KO), takes the attach, and
    VETOES Wally's Compassion (clutch_heal) — which would BOUNCE the Energy the KO needs and blow the
    win. The enabling step, not the finishing attack, is this decision's next step."""
    pilot = _pilot()
    play_wallys = opt(PLAY, area=HAND, index=0)                              # the breaker
    attach_water = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)
    # Active at 2 Energy (Jetting 120 can't KO 180); attaching 3rd unlocks Nebula 210 = the win.
    won = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=180),
                opp_bench=[poke(OPP, hp=180)], hand=[WALLYS, WATER], prizes=1, opp_prizes=2)
    obs = make_select([play_wallys, attach_water, attack_opt(JETTING), opt(END)], current=won)
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.next_step == [1]   # lock the enabling attach
    assert pilot.decide(obs) == [1]                             # take it, NOT Wally's (index 0)

    # Control — opponent's Active too healthy (330): attaching doesn't unlock a KO -> no line to
    # lock, Solver stands down.
    safe = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=330),
                 opp_bench=[poke(OPP, hp=180)], hand=[WALLYS, WATER], prizes=1, opp_prizes=2)
    obs_c = make_select([play_wallys, attach_water, attack_opt(JETTING), opt(END)], current=safe)
    assert pilot.explain(obs_c).lethal is None


@pytest.mark.req("REQ-LETHAL-0004")
def test_evolve_that_unlocks_the_ko_is_a_locked_lethal_line():
    """a211/aae4 shape: my Active is a Staryu (its own 20-damage attack can't KO). Evolving it to Mega
    Starmie ex — the Energy carries through — lets Jetting Blow (120) KO for the win. No existing hook
    sees an evolve-unlock, so the Solver does its own lookahead: it locks `evolve -> KO` and takes the
    evolve."""
    pilot = _pilot()
    evolve = opt(EVOLVE, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)  # Staryu -> Mega (hand[0])
    staryu_attack = attack_opt(STARYU)                                          # 20 dmg — no KO
    won = state(active=poke(PREEVO, energy=1, hp=70), opp_active=poke(OPP, hp=120),
                opp_bench=[poke(OPP, hp=120)], hand=[WINCON], prizes=1, opp_prizes=2)
    obs = make_select([evolve, staryu_attack, opt(END)], current=won)
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.next_step == [0]   # lock the evolve unlocking the KO
    assert pilot.decide(obs) == [0]

    # Control — evolving still doesn't reach the KO (opp Active 330 > Jetting's 120): no lethal.
    safe = state(active=poke(PREEVO, energy=1, hp=70), opp_active=poke(OPP, hp=330),
                 opp_bench=[poke(OPP, hp=120)], hand=[WINCON], prizes=1, opp_prizes=2)
    obs_c = make_select([evolve, staryu_attack, opt(END)], current=safe)
    assert pilot.explain(obs_c).lethal is None


@pytest.mark.req("REQ-LETHAL-0005")
def test_snipe_that_does_not_take_enough_prizes_is_not_lethal():
    """SOUNDNESS: I need 2 prizes. My attack snipes a benched 1-prize body (a KO) but does NOT KO the
    2-prize ex Active — so it takes only ONE prize, not the win. The Solver must NOT lock it: a false
    lethal that committed the turn is the one catastrophic direction."""
    pilot = _pilot()
    snipe = attack_opt(SNIPE)                                    # 50 to Active (survives) + 100 snipe KO
    looks_won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(EXOPP, hp=330),
                      opp_bench=[poke(BENCHIE, hp=100)], prizes=2, opp_prizes=2)
    obs = make_select([snipe, opt(END)], current=looks_won)
    assert pilot.explain(obs).lethal is None                    # only 1 prize taken -> not a win

    # Control — need only 1 prize: same snipe-KO now takes my last -> lethal, locks.
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(EXOPP, hp=330),
                opp_bench=[poke(BENCHIE, hp=100)], prizes=1, opp_prizes=2)
    obs_c = make_select([snipe, opt(END)], current=won)
    assert pilot.explain(obs_c).lethal is not None and pilot.decide(obs_c) == [0]


@pytest.mark.req("REQ-LETHAL-0006")
def test_simultaneous_double_ko_is_a_draw_not_a_locked_win():
    """SOUNDNESS: my KO takes my last prize, but its recoil also KOs my Active and hands the opponent
    their last prize at the same Checkup — the competition scores that a DRAW, not a win (ADR-0022 #2).
    The Solver must NOT lock it. Dedicated fixtures so the recoil attack can't perturb other slices."""
    RECOILER, ROPP, RECOIL_ATK = 950, 951, 20
    stats = DictCardStatProvider({
        RECOILER: CardStat(RECOILER, name="recoiler", hp=70, energyType=3, minAttackCost=1,
                           minCostDamage=210, maxDamage=210, attacks=(RECOIL_ATK,)),
        ROPP: CardStat(ROPP, name="ropp", hp=200, energyType=7),
    })
    pilot = Pilot(Strategy(roles={RECOILER: ["win_condition"]}), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY, stats=stats, functions=CardFunctions({}),
                  attacks={RECOIL_ATK: 210}, attack_costs={RECOIL_ATK: 1}, recoil={RECOIL_ATK: 400})
    # recoil 400 self-KOs my 70-HP Active; both players take their last prize at once -> a draw.
    draw = state(active=poke(RECOILER, energy=1, hp=70), opp_active=poke(ROPP, hp=200),
                 opp_bench=[poke(ROPP, hp=200)], prizes=1, opp_prizes=1)
    obs = make_select([attack_opt(RECOIL_ATK), opt(END)], current=draw)
    assert pilot.explain(obs).lethal is None                    # a draw isn't a win

    # Control — my Active survives recoil (500 HP > 400): KO is a clean win, locks.
    win = state(active=poke(RECOILER, energy=1, hp=500), opp_active=poke(ROPP, hp=200),
                opp_bench=[poke(ROPP, hp=200)], prizes=1, opp_prizes=1)
    obs_c = make_select([attack_opt(RECOIL_ATK), opt(END)], current=win)
    assert pilot.explain(obs_c).lethal is not None


# --------------------------------------------------------------------- in-scope CRITICAL gate (ADR-0030)
@pytest.mark.req("REQ-LETHAL-0007")
def test_critical_c1e0_winning_attack_vetoes_the_gust_breaker():
    """CRITICAL c1e0 ('must never happen again'): the current Active can KO the opponent's Active for
    the win, but the agent played Boss's Orders — gusting up a body it could no longer KO — and threw
    the game. The Solver locks the winning attack and vetoes the gust."""
    pilot = _pilot()
    boss = opt(PLAY, area=HAND, index=0)                         # the breaker (gust)
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                opp_bench=[poke(BENCHIE, hp=100)], hand=[BOSS], prizes=1, opp_prizes=2)
    obs = make_select([boss, attack_opt(JETTING), opt(END)], current=won)
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.next_step == [1]
    assert pilot.decide(obs) == [1]                             # attack for win, NOT Boss's (index 0)


@pytest.mark.req("REQ-LETHAL-0008")
def test_critical_fd5c_retreat_into_the_powered_wincon_is_locked():
    """CRITICAL fd5c: retreating was right — but into the powered Mega Starmie that KOs for the win, not
    the unpowered opener. My spent Active can't KO; a benched Mega (1 W = Jetting Blow 120) KOs the
    opponent's 120-HP Active. The Solver locks the retreat that brings the winning attacker Active."""
    pilot = _pilot()
    retreat = opt(RETREAT)
    won = state(active=poke(PREEVO, energy=1, hp=70),                 # spent opener, can't KO
                bench=[poke(WINCON, energy=1, hp=330)],               # powered wincon that can
                opp_active=poke(OPP, hp=120), opp_bench=[poke(BENCHIE, hp=100)], prizes=1, opp_prizes=2)
    obs = make_select([retreat, attack_opt(STARYU), opt(END)], current=won)
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.next_step == [0]   # lock retreat-to-lethal
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-LETHAL-0010")
def test_strict_execute_only_holds_across_the_turns_two_decisions():
    """Across the many per-decision calls of ONE turn, the Solver re-derives the same line and takes its
    next step each time — the enabling attach first (Wally's vetoed), then the finishing KO (Wally's
    vetoed again) once the engine re-opens the menu. Strict execute-only, no explicit turn state."""
    pilot = _pilot()
    play_wallys = opt(PLAY, area=HAND, index=0)
    attach_water = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)
    # Decision 1: Active at 2 E (Jetting can't KO 180); attaching 3rd unlocks Nebula 210 = win.
    before = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=180),
                   opp_bench=[poke(OPP, hp=180)], hand=[WALLYS, WATER], prizes=1, opp_prizes=2)
    obs1 = make_select([play_wallys, attach_water, attack_opt(JETTING), opt(END)], current=before)
    assert pilot.decide(obs1) == [1]                            # enabling attach, NOT Wally's

    # Decision 2: engine re-opened menu after attach — Active now at 3 E, Nebula available.
    after = state(active=poke(WINCON, energy=3, hp=330), opp_active=poke(OPP, hp=180),
                  opp_bench=[poke(OPP, hp=180)], hand=[WALLYS], prizes=1, opp_prizes=2)
    obs2 = make_select([play_wallys, attack_opt(NEBULA), opt(END)], current=after)
    assert pilot.explain(obs2).lethal is not None
    assert pilot.decide(obs2) == [1]                            # finishing KO, NOT Wally's


# ------------------------------------------------------------- telemetry: verdict rides in the @T record
@pytest.mark.req("REQ-LETHAL-0011")
def test_lethal_verdict_is_emitted_in_decision_telemetry():
    """The Solver's verdict must ride in the @T Decision Telemetry (ADR-0019) — the SAME `to_record`
    feeds the live stderr line, the correction's `live_trace`, and the tuner's retest — so a blunder
    correction on a lethal decision carries the solver's data for the blunder-buster to analyze. A
    locked line surfaces its step + kind + rationale; a non-lethal decision surfaces `lethal: None`
    (the key is always present so corrections can filter on it)."""
    pilot = _pilot()
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                prizes=1, opp_prizes=2)
    rec = to_record(pilot.explain(make_select([attack_opt(JETTING), opt(END)], current=won)))
    assert rec["lethal"] == {"step": [0], "kind": "direct", "why": "lethal: this KO wins the match",
                             "verified": None}

    safe = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=330),
                 opp_bench=[poke(OPP, hp=120)], prizes=3, opp_prizes=2)
    rec_none = to_record(pilot.explain(make_select([attack_opt(JETTING), opt(END)], current=safe)))
    assert "lethal" in rec_none and rec_none["lethal"] is None

    # an enabling-step lock carries its own kind, so a correction can tell a develop-unlock apart.
    unlock = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=180),
                   opp_bench=[poke(OPP, hp=180)], hand=[WALLYS, WATER], prizes=1, opp_prizes=2)
    obs_u = make_select([opt(PLAY, area=HAND, index=0),
                         opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                         attack_opt(JETTING), opt(END)], current=unlock)
    assert to_record(pilot.explain(obs_u))["lethal"]["kind"] == "unlock"


# ------------------------------------------------- the engine-verify backstop wiring (ADR-0030, item 1)
def _direct_win_obs():
    """A board whose only win is a 1-step direct KO (the REQ-LETHAL-0001 shape)."""
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                prizes=1, opp_prizes=2)
    return make_select([attack_opt(JETTING), opt(END)], current=won)


@pytest.mark.req("REQ-LETHAL-0013")
def test_lethal_verify_is_off_by_default_and_never_calls_the_engine(monkeypatch):
    """Kill-switch (ADR-0021 pattern): without `lethal_verify=True` the Solver locks on closed-form
    math alone — byte-identical to the shipped behavior — and NEVER invokes the engine backstop."""
    pilot = _pilot()

    def _boom(*a, **kw):
        raise AssertionError("engine backstop must not be called when lethal_verify is off")

    monkeypatch.setattr(pilot, "_engine_confirms_win", _boom)
    d = pilot.explain(_direct_win_obs())
    assert d.lethal is not None and d.lethal.verified is None   # locked, unverified (switch off)
    assert d.lethal_refuted == 0


@pytest.mark.req("REQ-LETHAL-0013")
def test_lethal_verify_confirms_a_direct_lock_and_rides_in_telemetry(monkeypatch):
    """With the switch ON, a DIRECT lock is confirmed through `_engine_confirms_win` with exactly the
    lock's one step; the verdict rides on the line (and in the @T record) so the blunder-buster can
    filter on it (ADR-0019)."""
    pilot = _pilot(lethal_verify=True)
    calls = []

    def _confirm(obs, steps):
        calls.append(steps)
        return True

    monkeypatch.setattr(pilot, "_engine_confirms_win", _confirm)
    obs = _direct_win_obs()
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.verified is True
    assert calls == [[[0]]]                                     # one candidate, its exact step list
    assert to_record(d)["lethal"]["verified"] is True


@pytest.mark.req("REQ-LETHAL-0013")
def test_lethal_verify_refutes_a_phantom_direct_lock(monkeypatch):
    """The backstop's whole point (ADR-0030: false-lock = thrown game): when the ENGINE says the
    closed-form 'win' does not actually win, the candidate is dropped — no lock, defer to the normal
    machinery — and the refute is surfaced (Decision + @T) so a live divergence is countable."""
    pilot = _pilot(lethal_verify=True)
    monkeypatch.setattr(pilot, "_engine_confirms_win", lambda obs, steps: False)
    d = pilot.explain(_direct_win_obs())
    assert d.lethal is None                                     # the phantom is NOT locked
    assert d.lethal_refuted == 1
    rec = to_record(d)
    assert rec["lethal"] is None and rec["lethal_refuted"] == 1


@pytest.mark.req("REQ-LETHAL-0013")
def test_lethal_verify_unavailable_engine_keeps_the_sound_closed_form_lock(monkeypatch):
    """Fail-safe (never commit-degraded, ADR-0030): a None verdict — no `search_begin_input`, lib-free
    suite, or any search error — keeps the sound closed-form lock, unverified. The switch being ON must
    never LOSE wins the closed-form layer already proves."""
    pilot = _pilot(lethal_verify=True)
    monkeypatch.setattr(pilot, "_engine_confirms_win", lambda obs, steps: None)
    d = pilot.explain(_direct_win_obs())
    assert d.lethal is not None and d.lethal.verified is None
    assert d.lethal_refuted == 0


@pytest.mark.req("REQ-LETHAL-0013")
def test_lethal_verify_never_touches_multi_step_unlock_locks(monkeypatch):
    """A 1-step engine sim of a MULTI-step line cannot reach a result (the turn hasn't ended), so
    `_engine_confirms_win` would report False and wrongly refute a good lock. Until the multi-step
    drive-to-terminal is built (ADR-0030 remaining follow-up), verify applies to DIRECT locks only —
    unlock/evolve locks stay closed-form even with the switch ON."""
    pilot = _pilot(lethal_verify=True)

    def _boom(*a, **kw):
        raise AssertionError("a multi-step (unlock) lock must not be engine-verified one step deep")

    monkeypatch.setattr(pilot, "_engine_confirms_win", _boom)
    unlock = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=180),
                   opp_bench=[poke(OPP, hp=180)], hand=[WALLYS, WATER], prizes=1, opp_prizes=2)
    obs = make_select([opt(PLAY, area=HAND, index=0),
                       opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                       attack_opt(JETTING), opt(END)], current=unlock)
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.kind == "unlock" and d.lethal.verified is None


@pytest.mark.req("REQ-LETHAL-0013")
def test_lethal_verify_refute_falls_through_to_a_second_confirmed_candidate(monkeypatch):
    """Candidate-level, not turn-level: an engine-refuted direct candidate drops, but a LATER direct
    candidate the engine confirms still locks (the refute count records the drop)."""
    pilot = _pilot(lethal_verify=True)
    verdicts = iter([False, True])
    monkeypatch.setattr(pilot, "_engine_confirms_win", lambda obs, steps: next(verdicts))
    won = state(active=poke(WINCON, energy=3, hp=330), opp_active=poke(OPP, hp=120),
                prizes=1, opp_prizes=2)
    obs = make_select([attack_opt(JETTING), attack_opt(NEBULA), opt(END)], current=won)
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.next_step == [1]   # the second candidate locks
    assert d.lethal.verified is True and d.lethal_refuted == 1


@pytest.mark.req("REQ-LETHAL-0012")
def test_ignore_effects_attack_bypasses_a_prevent_damage_ability_for_the_win():
    """ep83054602 f17: the opponent's Active has a 'prevent all damage from your {ex} Pokémon' Ability
    (Crustle's Mysterious Rock Inn, Function Tag `prevent_ex_damage`). My cheap Jetting Blow is walled,
    but Nebula Beam "isn't affected by any effects on your opponent's Active Pokémon" — so it lands its
    210 THROUGH the Ability and KOs the 150-HP Active. The opponent's Bench is empty, so that KO WINS.
    The Solver must see it ONLY because Nebula Beam carries `ignores_active_effects`; without the signal
    both ex attacks read as walled and the win is invisible (the missed-win blunder)."""
    EX_ATTACKER, CRUSTLE = 901, 345
    stats = DictCardStatProvider({
        EX_ATTACKER: CardStat(EX_ATTACKER, name="Mega Starmie ex", hp=330, energyType=3, ex=True,
                              megaEx=True, minAttackCost=1, minCostDamage=120, maxDamage=210,
                              maxDamageCost=3, attacks=(JETTING, NEBULA)),
        CRUSTLE: CardStat(CRUSTLE, name="Crustle", hp=150, energyType=7),
    })
    funcs = CardFunctions({CRUSTLE: ["prevent_ex_damage"]})

    def build(ignore):
        return Pilot(Strategy(roles={EX_ATTACKER: ["win_condition", "primary_attacker"]}),
                     deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs,
                     attacks={JETTING: 120, NEBULA: 210}, attack_costs={JETTING: 1, NEBULA: 3},
                     ignores_active_effects=ignore)

    # 4 Energy -> both attacks affordable; opp Crustle 150 HP, empty Bench (KO = win); prizes not last.
    won = state(active=poke(EX_ATTACKER, energy=4, hp=330), opp_active=poke(CRUSTLE, hp=150),
                opp_bench=[], prizes=3, opp_prizes=2)
    obs = make_select([attack_opt(JETTING), attack_opt(NEBULA), opt(END)], current=won)

    assert build({}).explain(obs).lethal is None        # no signal: both ex attacks walled, no win seen
    d = build({NEBULA: True}).explain(obs)              # with it: Nebula bypasses Ability -> empty-bench win
    assert d.lethal is not None and d.lethal.next_step == [1]
    assert build({NEBULA: True}).decide(obs) == [1]     # ... Pilot takes Nebula Beam, not Jetting Blow
