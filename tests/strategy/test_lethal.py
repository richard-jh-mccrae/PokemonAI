"""Lethal Solver (ADR-0030/0037): the eager, sound, this-turn win-detector — the Turn Planner's top rung.

Behaviour through the Pilot's PUBLIC interface (``decide`` / ``explain``): when a guaranteed win
exists THIS turn, ``explain(obs).planned`` carries the ``goal="win"`` line (ADR-0037's one line type)
and ``decide`` takes its next step. Lib-free (the closed-form layer); the engine-verified slices live
in the engine-backed suite.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
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
        WINCON: CardStat(WINCON, synthetic=True, name="Mega Starmie ex", hp=330, energyType=3, minAttackCost=1,
                         minCostDamage=120, maxDamage=210, maxDamageCost=3,
                         attacks=(JETTING, NEBULA, SNIPE), evolvesFrom="Staryu"),
        PREEVO: CardStat(PREEVO, synthetic=True, name="Staryu", hp=70, energyType=3, minAttackCost=1,
                         minCostDamage=20, maxDamage=20, attacks=(STARYU,)),
        OPP: CardStat(OPP, synthetic=True, name="opp active", hp=120, energyType=7),
        EXOPP: CardStat(EXOPP, synthetic=True, name="opp ex", hp=330, energyType=7, ex=True),
        BENCHIE: CardStat(BENCHIE, synthetic=True, name="opp benchie", hp=100, energyType=7),
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
    }, attacks={JETTING: AttackStat(JETTING, damage=120, cost=1),
                NEBULA: AttackStat(NEBULA, damage=210, cost=3),
                STARYU: AttackStat(STARYU, damage=20, cost=1),
                SNIPE: AttackStat(SNIPE, damage=50, cost=1, benchSnipe=100)})


def _pilot(**kw):
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_stats(), functions=CardFunctions({WALLYS: ["heal", "clutch_heal"], BOSS: ["gust"]}),
                 **kw)


def _win(decision):
    p = decision.planned
    return p if (p is not None and p.goal == "win") else None


@pytest.mark.req("REQ-LETHAL-0001")
def test_immediate_prize_out_ko_is_a_locked_lethal_line_taken_now():
    pilot = _pilot()
    # Active powered for Jetting Blow (1 W); opp Active at 120 HP (a KO); my last prize (1 left).
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                prizes=1, opp_prizes=2)
    obs = make_select([attack_opt(JETTING), opt(END)], current=won)

    d = pilot.explain(obs)
    assert _win(d) is not None                     # guaranteed winning line found + locked
    assert _win(d).next_step == [0]                # next step: the finishing attack
    assert pilot.decide(obs) == [0]                # ... Pilot takes it


@pytest.mark.req("REQ-LETHAL-0002")
def test_empty_bench_ko_is_lethal_even_when_prizes_are_not_last():
    """A KO with their Bench EMPTY wins outright — they have no Pokémon left to promote."""
    pilot = _pilot()
    # 3 prizes left (not prize-out), but opponent's Bench empty: KO their Active = they lose.
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                opp_bench=[], prizes=3, opp_prizes=2)
    obs = make_select([attack_opt(JETTING), opt(END)], current=won)
    d = pilot.explain(obs)
    assert _win(d) is not None and _win(d).next_step == [0]     # empty-bench win detected + taken
    assert pilot.decide(obs) == [0]

    # Control — opponent has a benched Pokémon, so KO is NOT a win (they promote); prizes not last ->
    # no lethal to lock.
    not_won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                    opp_bench=[poke(OPP, hp=120)], prizes=3, opp_prizes=2)
    obs_c = make_select([attack_opt(JETTING), opt(END)], current=not_won)
    assert _win(pilot.explain(obs_c)) is None


@pytest.mark.req("REQ-LETHAL-0003")
def test_enabling_attach_is_locked_and_the_breaker_is_vetoed():
    """Wally's Compassion (`clutch_heal`) BOUNCES the Energy the KO needs, so it is vetoed; the
    enabling step, not the finishing attack, is this decision's next step."""
    pilot = _pilot()
    play_wallys = opt(PLAY, area=HAND, index=0)                              # the breaker
    attach_water = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)
    # Active at 2 Energy (Jetting 120 can't KO 180); attaching 3rd unlocks Nebula 210 = the win.
    won = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=180),
                opp_bench=[poke(OPP, hp=180)], hand=[WALLYS, WATER], prizes=1, opp_prizes=2)
    obs = make_select([play_wallys, attach_water, attack_opt(JETTING), opt(END)], current=won)
    d = pilot.explain(obs)
    assert _win(d) is not None and _win(d).next_step == [1]     # lock the enabling attach
    assert pilot.decide(obs) == [1]                             # take it, NOT Wally's (index 0)

    # Control — opponent's Active too healthy (330): attaching doesn't unlock a KO -> no line to
    # lock, Solver stands down.
    safe = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=330),
                 opp_bench=[poke(OPP, hp=180)], hand=[WALLYS, WATER], prizes=1, opp_prizes=2)
    obs_c = make_select([play_wallys, attach_water, attack_opt(JETTING), opt(END)], current=safe)
    assert _win(pilot.explain(obs_c)) is None


@pytest.mark.req("REQ-LETHAL-0004")
def test_evolve_that_unlocks_the_ko_is_a_locked_lethal_line():
    """Evolving carries the attached Energy through, so the evolved body's attack reaches a KO the
    pre-evolution's own attack cannot. No other hook sees an evolve-unlock."""
    pilot = _pilot()
    evolve = opt(EVOLVE, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)  # Staryu -> Mega (hand[0])
    staryu_attack = attack_opt(STARYU)                                          # 20 dmg — no KO
    won = state(active=poke(PREEVO, energy=1, hp=70), opp_active=poke(OPP, hp=120),
                opp_bench=[poke(OPP, hp=120)], hand=[WINCON], prizes=1, opp_prizes=2)
    obs = make_select([evolve, staryu_attack, opt(END)], current=won)
    d = pilot.explain(obs)
    assert _win(d) is not None and _win(d).next_step == [0]     # lock the evolve unlocking the KO
    assert pilot.decide(obs) == [0]

    # Control — evolving still doesn't reach the KO (opp Active 330 > Jetting's 120): no lethal.
    safe = state(active=poke(PREEVO, energy=1, hp=70), opp_active=poke(OPP, hp=330),
                 opp_bench=[poke(OPP, hp=120)], hand=[WINCON], prizes=1, opp_prizes=2)
    obs_c = make_select([evolve, staryu_attack, opt(END)], current=safe)
    assert _win(pilot.explain(obs_c)) is None


@pytest.mark.req("REQ-LETHAL-0005")
def test_snipe_that_does_not_take_enough_prizes_is_not_lethal():
    """A false lethal that committed the turn is the one catastrophic direction."""
    pilot = _pilot()
    snipe = attack_opt(SNIPE)                                    # 50 to Active (survives) + 100 snipe KO
    looks_won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(EXOPP, hp=330),
                      opp_bench=[poke(BENCHIE, hp=100)], prizes=2, opp_prizes=2)
    obs = make_select([snipe, opt(END)], current=looks_won)
    assert _win(pilot.explain(obs)) is None                     # only 1 prize taken -> not a win

    # Control — need only 1 prize: same snipe-KO now takes my last -> lethal, locks.
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(EXOPP, hp=330),
                opp_bench=[poke(BENCHIE, hp=100)], prizes=1, opp_prizes=2)
    obs_c = make_select([snipe, opt(END)], current=won)
    assert _win(pilot.explain(obs_c)) is not None and pilot.decide(obs_c) == [0]


@pytest.mark.req("REQ-LETHAL-0006")
def test_simultaneous_double_ko_is_a_draw_not_a_locked_win():
    """Both players taking their last prize at the same Checkup is scored a DRAW by the competition
    deltas (ADR-0022 #2), not a win."""
    RECOILER, ROPP, RECOIL_ATK = 950, 951, 20
    stats = DictCardStatProvider({
        RECOILER: CardStat(RECOILER, synthetic=True, name="recoiler", hp=70, energyType=3, minAttackCost=1,
                           minCostDamage=210, maxDamage=210, attacks=(RECOIL_ATK,)),
        ROPP: CardStat(ROPP, synthetic=True, name="ropp", hp=200, energyType=7),
    }, attacks={RECOIL_ATK: AttackStat(RECOIL_ATK, damage=210, cost=1, recoil=400)})
    pilot = Pilot(Strategy(roles={RECOILER: ["win_condition"]}), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY, stats=stats, functions=CardFunctions({}))
    # recoil 400 self-KOs my 70-HP Active; both players take their last prize at once -> a draw.
    draw = state(active=poke(RECOILER, energy=1, hp=70), opp_active=poke(ROPP, hp=200),
                 opp_bench=[poke(ROPP, hp=200)], prizes=1, opp_prizes=1)
    obs = make_select([attack_opt(RECOIL_ATK), opt(END)], current=draw)
    assert _win(pilot.explain(obs)) is None                     # a draw isn't a win

    # Control — my Active survives recoil (500 HP > 400): KO is a clean win, locks.
    win = state(active=poke(RECOILER, energy=1, hp=500), opp_active=poke(ROPP, hp=200),
                opp_bench=[poke(ROPP, hp=200)], prizes=1, opp_prizes=1)
    obs_c = make_select([attack_opt(RECOIL_ATK), opt(END)], current=win)
    assert _win(pilot.explain(obs_c)) is not None


# --------------------------------------------------------------------- in-scope CRITICAL gate (ADR-0030)
@pytest.mark.req("REQ-LETHAL-0007")
def test_critical_c1e0_winning_attack_vetoes_the_gust_breaker():
    pilot = _pilot()
    boss = opt(PLAY, area=HAND, index=0)                         # the breaker (gust)
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                opp_bench=[poke(BENCHIE, hp=100)], hand=[BOSS], prizes=1, opp_prizes=2)
    obs = make_select([boss, attack_opt(JETTING), opt(END)], current=won)
    d = pilot.explain(obs)
    assert _win(d) is not None and _win(d).next_step == [1]
    assert pilot.decide(obs) == [1]                             # attack for win, NOT Boss's (index 0)


@pytest.mark.req("REQ-LETHAL-0008")
def test_critical_fd5c_retreat_into_the_powered_wincon_is_locked():
    pilot = _pilot()
    retreat = opt(RETREAT)
    won = state(active=poke(PREEVO, energy=1, hp=70),                 # spent opener, can't KO
                bench=[poke(WINCON, energy=1, hp=330)],               # powered wincon that can
                opp_active=poke(OPP, hp=120), opp_bench=[poke(BENCHIE, hp=100)], prizes=1, opp_prizes=2)
    obs = make_select([retreat, attack_opt(STARYU), opt(END)], current=won)
    d = pilot.explain(obs)
    assert _win(d) is not None and _win(d).next_step == [0]     # lock retreat-to-lethal
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-LETHAL-0010")
def test_strict_execute_only_holds_across_the_turns_two_decisions():
    """The Solver re-derives the same line on every decision of the turn and takes its next step:
    strict execute-only, no explicit turn state."""
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
    assert _win(pilot.explain(obs2)) is not None
    assert pilot.decide(obs2) == [1]                            # finishing KO, NOT Wally's


# ------------------------------------------------------------- telemetry: verdict rides in the @T record
@pytest.mark.req("REQ-LETHAL-0011")
def test_lethal_verdict_is_emitted_in_decision_telemetry():
    """One `to_record` feeds the stderr line, a correction's `live_trace` and the tuner's retest
    (ADR-0019); the `lethal` key is always present so corrections can filter on it."""
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
    pilot = _pilot()

    def _boom(*a, **kw):
        raise AssertionError("engine backstop must not be called when lethal_verify is off")

    monkeypatch.setattr(pilot, "_engine_confirms_win", _boom)
    d = pilot.explain(_direct_win_obs())
    assert _win(d) is not None and _win(d).verified is None     # locked, unverified (switch off)
    assert d.lethal_refuted == 0


@pytest.mark.req("REQ-LETHAL-0013")
def test_lethal_verify_confirms_a_direct_lock_and_rides_in_telemetry(monkeypatch):
    pilot = _pilot(lethal_verify=True)
    calls = []

    def _confirm(obs, steps):
        calls.append(steps)
        return True

    monkeypatch.setattr(pilot, "_engine_confirms_win", _confirm)
    obs = _direct_win_obs()
    d = pilot.explain(obs)
    assert _win(d) is not None and _win(d).verified is True
    assert calls == [[[0]]]                                     # one candidate, its exact step list
    assert to_record(d)["lethal"]["verified"] is True


@pytest.mark.req("REQ-LETHAL-0013")
def test_lethal_verify_refutes_a_phantom_direct_lock(monkeypatch):
    """ADR-0030: a false lock is a thrown game, so a refuted candidate is dropped and the refute is
    surfaced for counting."""
    pilot = _pilot(lethal_verify=True)
    monkeypatch.setattr(pilot, "_engine_confirms_win", lambda obs, steps: False)
    d = pilot.explain(_direct_win_obs())
    assert _win(d) is None                                      # the phantom is NOT locked
    assert d.lethal_refuted == 1
    rec = to_record(d)
    assert rec["lethal"] is None and rec["lethal_refuted"] == 1


@pytest.mark.req("REQ-LETHAL-0013")
def test_lethal_verify_unavailable_engine_keeps_the_sound_closed_form_lock(monkeypatch):
    """The switch being ON must never LOSE a win the closed-form layer already proves."""
    pilot = _pilot(lethal_verify=True)
    monkeypatch.setattr(pilot, "_engine_confirms_win", lambda obs, steps: None)
    d = pilot.explain(_direct_win_obs())
    assert _win(d) is not None and _win(d).verified is None
    assert d.lethal_refuted == 0


@pytest.mark.req("REQ-LETHAL-0013")
def test_lethal_verify_never_touches_multi_step_unlock_locks(monkeypatch):
    """A 1-step engine sim of a MULTI-step line cannot reach a result — the turn has not ended — so it
    would report False and wrongly refute a good lock; verify applies to DIRECT locks only."""
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
    assert _win(d) is not None and _win(d).kind == "unlock" and _win(d).verified is None


@pytest.mark.req("REQ-LETHAL-0013")
def test_refute_count_survives_the_cascades_policy_reentry(monkeypatch):
    """The verify cascade re-runs decide(), which re-enters plan_turn under ``_planning``; that
    re-entry must not wipe the outer decision's refute count."""
    pilot = _pilot(lethal_verify=True)
    won = state(active=poke(WINCON, energy=3, hp=330), opp_active=poke(OPP, hp=120),
                prizes=1, opp_prizes=2)
    obs = make_select([attack_opt(JETTING), attack_opt(NEBULA), opt(END)], current=won)
    calls = []

    def _verify(o, steps):
        calls.append(tuple(steps[0]))
        if len(calls) == 1:
            return False                               # refute candidate 0 ...
        was = pilot._planning                          # ... then mimic candidate 1's cascade: the
        pilot._planning = True                         # policy re-enters plan_turn in-sim
        try:
            pilot.plan_turn(obs, obs["select"], pilot._board(obs, obs["select"]),
                            obs["select"]["option"], [])
        finally:
            pilot._planning = was
        return True

    monkeypatch.setattr(pilot, "_engine_confirms_win", _verify)
    d = pilot.explain(obs)
    assert _win(d) is not None and _win(d).next_step == [1]
    assert d.lethal_refuted == 1                       # the re-entry did not wipe the outer count


@pytest.mark.req("REQ-LETHAL-0013")
def test_lethal_verify_refute_falls_through_to_a_second_confirmed_candidate(monkeypatch):
    """Candidate-level, not turn-level."""
    pilot = _pilot(lethal_verify=True)
    verdicts = iter([False, True])
    monkeypatch.setattr(pilot, "_engine_confirms_win", lambda obs, steps: next(verdicts))
    won = state(active=poke(WINCON, energy=3, hp=330), opp_active=poke(OPP, hp=120),
                prizes=1, opp_prizes=2)
    obs = make_select([attack_opt(JETTING), attack_opt(NEBULA), opt(END)], current=won)
    d = pilot.explain(obs)
    assert _win(d) is not None and _win(d).next_step == [1]     # the second candidate locks
    assert _win(d).verified is True and d.lethal_refuted == 1


# ═══ the one generator family (ADR-0037 stage 2, `lethal_family`) ═══
@pytest.mark.req("REQ-LETHAL-0015")
def test_family_locks_the_two_develop_retreat_attach_win():
    """The motivating gap (ADR-0037): the win needs TWO develops, and no legacy hook scores it — the
    retreat hook needs an already-READY body."""
    retreat = opt(RETREAT)
    won = state(active=poke(PREEVO, energy=0, hp=70),
                bench=[poke(WINCON, energy=2, hp=330)],           # needs the retreat AND the attach
                opp_active=poke(OPP, hp=200), opp_bench=[poke(BENCHIE, hp=100)],
                hand=[WATER], prizes=1, opp_prizes=2)
    obs = make_select([retreat, attack_opt(STARYU), opt(END)], current=won)
    d = _pilot(lethal_family=True).explain(obs)
    assert _win(d) is not None and _win(d).next_step == [0] and _win(d).kind == "unlock"
    assert _pilot(lethal_family=True).decide(obs) == [0]
    # legacy rungs (switch OFF): no hook fires -> no LOCK (the heuristic planner may still commit
    # the same step rank-grade — exactly the sound-vs-heuristic gap the family closes).
    assert _win(_pilot().explain(obs)) is None


@pytest.mark.req("REQ-LETHAL-0016")
def test_family_locks_the_evolve_plus_attach_win():
    """The legacy evolve rung tests the CURRENT energy only (min-bound), so it misses a win that
    needs the held Energy attached after the evolve."""
    evolve = opt(EVOLVE, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)
    won = state(active=poke(PREEVO, energy=2, hp=70), opp_active=poke(OPP, hp=200),
                opp_bench=[poke(BENCHIE, hp=100)], hand=[WINCON, WATER], prizes=1, opp_prizes=2)
    obs = make_select([evolve, attack_opt(STARYU), opt(END)], current=won)
    d = _pilot(lethal_family=True).explain(obs)
    assert _win(d) is not None and _win(d).next_step == [0] and _win(d).kind == "evolve"
    assert _win(_pilot().explain(obs)) is None        # legacy: evolve at current energy can't KO


@pytest.mark.req("REQ-LETHAL-0017")
def test_family_locks_the_gust_win_and_stands_down_without_a_winning_target():
    """Boss's Orders drags a benched 2-prize ex my Active can KO while their Active itself cannot be
    KO'd (ADR-0022)."""
    boss = opt(PLAY, area=HAND, index=0)
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(EXOPP, hp=330),
                opp_bench=[poke(EXOPP, hp=120)], hand=[BOSS], prizes=2, opp_prizes=2)
    obs = make_select([boss, attack_opt(JETTING), opt(END)], current=won)
    d = _pilot(lethal_family=True).explain(obs)
    assert _win(d) is not None and _win(d).next_step == [0] and _win(d).kind == "gust"
    assert _win(_pilot().explain(obs)) is None        # legacy: a PLAY is never a win lock

    # Controls — no lock when the dragged KO can't WIN: the body is too healthy (no KO), or its
    # prize value falls short of my remaining count.
    healthy = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(EXOPP, hp=330),
                    opp_bench=[poke(EXOPP, hp=330)], hand=[BOSS], prizes=2, opp_prizes=2)
    assert _win(_pilot(lethal_family=True).explain(
        make_select([boss, attack_opt(JETTING), opt(END)], current=healthy))) is None
    short = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(EXOPP, hp=330),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[BOSS], prizes=2, opp_prizes=2)
    assert _win(_pilot(lethal_family=True).explain(
        make_select([boss, attack_opt(JETTING), opt(END)], current=short))) is None


HILDA = 1301   # tutor_energy Supporter (Hilda class): searches an attachable Energy into hand


def _tutor_pilot(deck):
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]})
    return Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=CardFunctions({HILDA: ["search", "tutor_energy"]}),
                 lethal_family=True)


@pytest.mark.req("REQ-LETHAL-0018")
def test_family_tutor_win_is_gated_on_deck_certain_energy():
    """SOUND only under the deck tracker's POSITIVE certainty (`deck_definitely_has`), which needs
    the prize multiset anchored in `obs['own_prizes']`: a probable fetch is never a win."""
    deck = [WATER] * 4 + [1] * 56
    won = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=200),
                opp_bench=[poke(BENCHIE, hp=100)], hand=[HILDA], prizes=1, opp_prizes=2)
    obs = make_select([opt(PLAY, area=HAND, index=0), attack_opt(JETTING), opt(END)], current=won)
    obs["own_prizes"] = {"1": 1}                      # tracker-anchored prizes -> exact deck counts
    d = _tutor_pilot(deck).explain(obs)
    assert _win(d) is not None and _win(d).next_step == [0] and _win(d).kind == "unlock"

    blind = make_select([opt(PLAY, area=HAND, index=0), attack_opt(JETTING), opt(END)], current=won)
    assert _win(_tutor_pilot(deck).explain(blind)) is None   # no anchor -> no certainty -> no lock


def _two_develop_obs():
    """The REQ-LETHAL-0015 shape: the win needs retreat + attach (no direct, no hook coverage)."""
    won = state(active=poke(PREEVO, energy=0, hp=70), bench=[poke(WINCON, energy=2, hp=330)],
                opp_active=poke(OPP, hp=200), opp_bench=[poke(BENCHIE, hp=100)],
                hand=[WATER], prizes=1, opp_prizes=2)
    return make_select([opt(RETREAT), attack_opt(STARYU), opt(END)], current=won)


@pytest.mark.req("REQ-LETHAL-0019")
def test_family_verifies_every_lock_refute_drops_and_none_keeps(monkeypatch):
    """Family mode widens verify to EVERY win lock. A coin-floor win can never verify True by
    construction, so a None verdict must keep the min-bound closed-form lock."""
    pilot = _pilot(lethal_family=True, lethal_verify=True)
    calls = []

    def _refute(obs, steps, **kw):
        calls.append((steps, kw))
        return False

    monkeypatch.setattr(pilot, "_engine_confirms_win", _refute)
    d = pilot.explain(_two_develop_obs())
    assert _win(d) is None and d.lethal_refuted == 1            # multi-develop phantom dropped
    steps, kw = calls[0]
    assert steps == [[0]] and kw.get("max_cascade") == 40       # cascade-driven, family cap

    pilot2 = _pilot(lethal_family=True, lethal_verify=True)
    monkeypatch.setattr(pilot2, "_engine_confirms_win", lambda obs, steps, **kw: None)
    d2 = pilot2.explain(_two_develop_obs())
    assert _win(d2) is not None and _win(d2).verified is None   # None keeps the sound lock
    assert d2.lethal_refuted == 0

    pilot3 = _pilot(lethal_family=True, lethal_verify=True)
    monkeypatch.setattr(pilot3, "_engine_confirms_win", lambda obs, steps, **kw: True)
    d3 = pilot3.explain(_two_develop_obs())
    assert _win(d3) is not None and _win(d3).verified is True   # confirmed multi-develop lock


@pytest.mark.req("REQ-LETHAL-0020")
def test_family_is_shortest_first_and_never_retries_a_refuted_index(monkeypatch):
    """A candidate refuted at one tier is not retried at a longer one — the verify cascade drives the
    same policy either way, so it is one sim per option index."""
    pilot = _pilot(lethal_family=True)
    # direct win (Jetting 120 vs 120) + a retreat that would also unlock a win via the bench Mega.
    won = state(active=poke(WINCON, energy=1, hp=330), bench=[poke(WINCON, energy=3, hp=330)],
                opp_active=poke(OPP, hp=120), hand=[WATER], prizes=1, opp_prizes=2)
    obs = make_select([opt(RETREAT), attack_opt(JETTING), opt(END)], current=won)
    d = pilot.explain(obs)
    assert _win(d) is not None and _win(d).kind == "direct" and _win(d).next_step == [1]

    # refuted-once = dropped for the turn's plan: the two-develop retreat is refuted at tier 2 and
    # must not come back from a later tier (one sim per option index).
    pilot2 = _pilot(lethal_family=True, lethal_verify=True)
    calls = []

    def _refute(obs, steps, **kw):
        calls.append(steps)
        return False

    monkeypatch.setattr(pilot2, "_engine_confirms_win", _refute)
    pilot2.explain(_two_develop_obs())
    assert calls == [[[0]]]                                     # the retreat simmed exactly once


@pytest.mark.req("REQ-LETHAL-0021")
def test_family_develop_tiers_stand_down_on_turn_one():
    """Turn 1 going first cannot attack (rules.md §first-turn), so no develop can cash a win."""
    won = state(active=poke(PREEVO, energy=0, hp=70), bench=[poke(WINCON, energy=2, hp=330)],
                opp_active=poke(OPP, hp=200), opp_bench=[poke(BENCHIE, hp=100)],
                hand=[WATER], prizes=1, opp_prizes=2, turn=1)
    obs = make_select([opt(RETREAT), attack_opt(STARYU), opt(END)], current=won)
    assert _win(_pilot(lethal_family=True).explain(obs)) is None


@pytest.mark.req("REQ-LETHAL-0022")
def test_family_covers_the_three_critical_shapes():
    """Flipping the switch must never reopen a gated CRITICAL."""
    fam = lambda: _pilot(lethal_family=True)                                    # noqa: E731
    # 040c: enabling attach locked, Wally's vetoed.
    attach = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=180),
                   opp_bench=[poke(OPP, hp=180)], hand=[WALLYS, WATER], prizes=1, opp_prizes=2)
    obs_a = make_select([opt(PLAY, area=HAND, index=0),
                         opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                         attack_opt(JETTING), opt(END)], current=attach)
    d = fam().explain(obs_a)
    assert _win(d) is not None and _win(d).next_step == [1] and fam().decide(obs_a) == [1]
    # c1e0: the winning attack locked, the gust breaker vetoed.
    gustbreak = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                      opp_bench=[poke(BENCHIE, hp=100)], hand=[BOSS], prizes=1, opp_prizes=2)
    obs_c = make_select([opt(PLAY, area=HAND, index=0), attack_opt(JETTING), opt(END)],
                        current=gustbreak)
    assert fam().decide(obs_c) == [1]
    # fd5c: the retreat into the powered wincon locked.
    retreat = state(active=poke(PREEVO, energy=1, hp=70), bench=[poke(WINCON, energy=1, hp=330)],
                    opp_active=poke(OPP, hp=120), opp_bench=[poke(BENCHIE, hp=100)],
                    prizes=1, opp_prizes=2)
    obs_f = make_select([opt(RETREAT), attack_opt(STARYU), opt(END)], current=retreat)
    d = fam().explain(obs_f)
    assert _win(d) is not None and _win(d).next_step == [0] and fam().decide(obs_f) == [0]


# ═══ the materialized-replay veto (ADR-0037 stage 3, `lethal_veto`) ═══
TO_HAND = 7    # SelectContext.TO_HAND — the prize-take / search pick select
PRIZE = 6      # AreaType.PRIZE — a hidden-zone pick (sim ids are predictions -> policy-driven)
CARD = 1       # OptionType.CARD


def _veto_pilot(monkeypatch, entries, verdict=True):
    """The fake verify materializes ``entries`` ONCE, on the first verified lock; later re-verifies
    record nothing, like a cascade with no driven selects."""
    pilot = _pilot(lethal_family=True, lethal_verify=True, lethal_veto=True)
    pending = [list(entries)]

    def _confirm(obs, steps, record=None, **kw):
        if record is not None and pending:
            record.extend(pending.pop())
        return verdict

    monkeypatch.setattr(pilot, "_engine_confirms_win", _confirm)
    return pilot


def _after_retreat_menu():
    """The follow-up MAIN menu after the locked retreat+attach: Wally's (a breaker), the finishing
    Nebula Beam at index 1, End."""
    after = state(active=poke(WINCON, energy=3, hp=330), opp_active=poke(OPP, hp=200),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[WALLYS], prizes=1, opp_prizes=2)
    return make_select([opt(PLAY, area=HAND, index=0), attack_opt(NEBULA), opt(END)], current=after)


@pytest.mark.req("REQ-LETHAL-0024")
def test_veto_replays_the_verified_cascade_by_identity(monkeypatch):
    """Replay is by OPTION IDENTITY (type + attackId + card), never by index, so the recorded pick is
    found wherever it sits on the live menu."""
    obs2 = _after_retreat_menu()
    entries = [{"ctx": 0, "max": 1, "drive": False,
                "chosen": [(13, NEBULA, None, None, None, None)]}]   # (ATTACK, Nebula, ...) identity
    pilot = _veto_pilot(monkeypatch, entries)
    d1 = pilot.explain(_two_develop_obs())
    assert _win(d1) is not None and _win(d1).verified is True       # locked + queue materialized
    d2 = pilot.explain(obs2)
    assert d2.chosen == [1] and _win(d2) is not None and _win(d2).kind == "replay"


@pytest.mark.req("REQ-LETHAL-0025")
def test_veto_mismatch_falls_back_and_surfaces_lethal_lost(monkeypatch):
    """A signature mismatch clears the lock and falls back to re-derivation — never a blind index."""
    entries = [{"ctx": 0, "max": 1, "drive": False,
                "chosen": [(13, 999, None, None, None, None)]}]      # an attack that won't exist live
    pilot = _veto_pilot(monkeypatch, entries)
    pilot.explain(_two_develop_obs())
    d2 = pilot.explain(_after_retreat_menu())
    assert d2.lethal_lost is True
    assert _win(d2) is not None and _win(d2).kind == "direct"       # re-derivation still takes the win
    assert d2.chosen == [1]
    rec = to_record(d2)
    assert rec.get("lethal_lost") is True
    d3 = pilot.explain(_after_retreat_menu())                       # lock cleared: no replay, no loss
    assert d3.lethal_lost is False and _win(d3).kind == "direct"


@pytest.mark.req("REQ-LETHAL-0026")
def test_veto_lock_expires_with_the_turn(monkeypatch):
    """The lock is turn-scoped: a new turn clears it silently (natural expiry, not a loss)."""
    entries = [{"ctx": 0, "max": 1, "drive": False,
                "chosen": [(13, NEBULA, None, None, None, None)]}]
    pilot = _veto_pilot(monkeypatch, entries)
    pilot.explain(_two_develop_obs())                               # locks on turn 2
    nxt = state(active=poke(WINCON, energy=3, hp=330), opp_active=poke(OPP, hp=200),
                opp_bench=[poke(BENCHIE, hp=100)], hand=[WALLYS], prizes=1, opp_prizes=2, turn=4)
    obs = make_select([opt(PLAY, area=HAND, index=0), attack_opt(NEBULA), opt(END)], current=nxt)
    d = pilot.explain(obs)
    assert _win(d) is not None and _win(d).kind == "direct"         # re-derived, not replayed
    assert d.lethal_lost is False                                   # expiry is not a loss


@pytest.mark.req("REQ-LETHAL-0027")
def test_veto_policy_drives_the_hidden_prize_pick_and_keeps_the_lock(monkeypatch):
    """A recorded pick from a HIDDEN zone is policy-driven at replay — the sim's ids there are
    predictions — so the entry is consumed and the lock survives whatever the policy picks."""
    entries = [{"ctx": TO_HAND, "max": 1, "drive": True, "chosen": [(CARD, None, 42, None, None, None)]},
               {"ctx": 0, "max": 1, "drive": False,
                "chosen": [(13, NEBULA, None, None, None, None)]}]
    pilot = _veto_pilot(monkeypatch, entries)
    pilot.explain(_two_develop_obs())
    prize_state = state(active=poke(WINCON, energy=3, hp=330), opp_active=poke(OPP, hp=200),
                        opp_bench=[poke(BENCHIE, hp=100)], prizes=1, opp_prizes=2)
    prize_sel = make_select([{"type": CARD, "area": PRIZE, "index": 0},
                             {"type": CARD, "area": PRIZE, "index": 1}],
                            context=TO_HAND, current=prize_state)
    d_prize = pilot.explain(prize_sel)
    assert d_prize.lethal_lost is False and len(d_prize.chosen) == 1   # policy chose, lock kept
    d_next = pilot.explain(_after_retreat_menu())
    assert _win(d_next) is not None and _win(d_next).kind == "replay" and d_next.chosen == [1]


@pytest.mark.req("REQ-LETHAL-0028")
def test_veto_off_never_stores_a_lock(monkeypatch):
    """`lethal_veto=False` (default) is byte-identical stage-2: verified locks re-derive per
    decision, nothing is materialized."""
    pilot = _pilot(lethal_family=True, lethal_verify=True)
    monkeypatch.setattr(pilot, "_engine_confirms_win",
                        lambda obs, steps, record=None, **kw: True)
    pilot.explain(_two_develop_obs())
    d2 = pilot.explain(_after_retreat_menu())
    assert _win(d2) is not None and _win(d2).kind == "direct"       # re-derived, never "replay"


@pytest.mark.req("REQ-LETHAL-0012")
def test_ignore_effects_attack_bypasses_a_prevent_damage_ability_for_the_win():
    """An attack that "isn't affected by any effects on your opponent's Active Pokémon" lands THROUGH
    a `prevent_ex_damage` Ability; without `ignoresEffects` both ex attacks read as walled."""
    EX_ATTACKER, CRUSTLE = 901, 345
    cards = {
        EX_ATTACKER: CardStat(EX_ATTACKER, synthetic=True, name="Mega Starmie ex", hp=330, energyType=3, ex=True,
                              megaEx=True, minAttackCost=1, minCostDamage=120, maxDamage=210,
                              maxDamageCost=3, attacks=(JETTING, NEBULA)),
        CRUSTLE: CardStat(CRUSTLE, synthetic=True, name='Crustle', hp=150, energyType=7),
    }
    funcs = CardFunctions({CRUSTLE: ["prevent_ex_damage"]})

    def build(ignore):
        recs = {JETTING: AttackStat(JETTING, damage=120, cost=1,
                                    ignoresEffects=bool(ignore.get(JETTING))),
                NEBULA: AttackStat(NEBULA, damage=210, cost=3,
                                   ignoresEffects=bool(ignore.get(NEBULA)))}
        return Pilot(Strategy(roles={EX_ATTACKER: ["win_condition", "primary_attacker"]}),
                     deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                     stats=DictCardStatProvider(cards, attacks=recs), functions=funcs)

    # 4 Energy -> both attacks affordable; opp Crustle 150 HP, empty Bench (KO = win); prizes not last.
    won = state(active=poke(EX_ATTACKER, energy=4, hp=330), opp_active=poke(CRUSTLE, hp=150),
                opp_bench=[], prizes=3, opp_prizes=2)
    obs = make_select([attack_opt(JETTING), attack_opt(NEBULA), opt(END)], current=won)

    assert _win(build({}).explain(obs)) is None         # no signal: both ex attacks walled, no win seen
    d = build({NEBULA: True}).explain(obs)              # with it: Nebula bypasses Ability -> empty-bench win
    assert _win(d) is not None and _win(d).next_step == [1]
    assert build({NEBULA: True}).decide(obs) == [1]     # ... Pilot takes Nebula Beam, not Jetting Blow
