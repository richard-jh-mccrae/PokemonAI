"""Turn Planner (ADR-0031): the eager whole-turn optimizer that generalizes the Lethal Solver to a
Goal Ladder. Behaviour through the Pilot's PUBLIC interface (``decide`` / ``explain``): when a
multi-step Turn Line reaches a valuable outcome the greedy per-option scorer would miss,
``explain(obs).planned`` names the line and ``decide`` takes its next step.

Lib-free (the closed-form layers); the engine-sim slices live in the engine-backed suite
(``test_planner_engine.py``). The Planner is layer-on-top: it commits ONLY when a line beats what the
tuned scoring would already play, so a decision the existing machinery handles leaves ``planned`` None.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.telemetry import to_record
from pilot_helpers import ACTIVE, ATTACH, HAND, PLAY, attack_opt, make_select, opt, poke, state

END = 14        # OptionType.END (not exported by pilot_helpers)
EVOLVE = 9      # OptionType.EVOLVE
RETREAT = 12    # OptionType.RETREAT

WINCON = 900    # my Active attacker / win-condition (Mega Starmie ex shape)
PREEVO = 800    # Staryu — Line base (evolves into WINCON), weak attacker alone
OPENER = 850    # spent opener Basic (can't KO, no evolution) — retreat OUT of this
OPP = 678       # opponent's Active (1 prize)
EXOPP = 679     # opponent's Active: a Pokémon ex (2 prizes)
BENCHIE = 700   # opponent's benched body (1 prize, harmless)
BIGATK = 701    # opponent's benched body that KOs my Mega next turn (survival threat)
THREAT = 680    # opponent's Active: KO-able now (70 HP) but 210-dmg glass cannon that dooms me next turn
WALLYS = 1229   # Wally's Compassion — clutch_heal (heals Mega ex to full, bounces Energy to hand)
HILDA = 1225    # Hilda — Supporter that searches an Energy (+ Evolution) into hand (tutor_energy)
JETTING = 11    # attack id: cost 1, 120 damage
NEBULA = 10     # attack id: cost 3, 210 damage (big attack an extra Energy unlocks)
STARYU = 12     # Staryu's own attack: cost 1, 20 damage (can't KO)
OPEN_ATK = 13   # opener's own attack: cost 1, 30 damage (can't KO)
WATER = 3       # Basic {W} Energy card in hand (reusable attach)


def _stats():
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, name="Mega Starmie ex", hp=330, energyType=3, minAttackCost=1,
                         minCostDamage=120, maxDamage=210, maxDamageCost=3,
                         attacks=(JETTING, NEBULA), evolvesFrom="Staryu", megaEx=True),
        PREEVO: CardStat(PREEVO, name="Staryu", hp=70, energyType=3, minAttackCost=1,
                         minCostDamage=20, maxDamage=20, attacks=(STARYU,)),
        OPENER: CardStat(OPENER, name="opener", hp=110, energyType=3, minAttackCost=1,
                         minCostDamage=30, maxDamage=30, attacks=(OPEN_ATK,)),
        OPP: CardStat(OPP, name="opp active", hp=180, energyType=7),
        EXOPP: CardStat(EXOPP, name="opp ex", hp=210, energyType=7, ex=True),
        BENCHIE: CardStat(BENCHIE, name="opp benchie", hp=100, energyType=7),
        BIGATK: CardStat(BIGATK, name="big hitter", hp=200, energyType=7, minAttackCost=1,
                         minCostDamage=340, maxDamage=340),   # benched threat, KOs my Mega next turn
        THREAT: CardStat(THREAT, name="glass cannon", hp=70, energyType=7, minAttackCost=1,
                         minCostDamage=210, maxDamage=210),   # KO-able now, dooms my Active next turn
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
    }, attacks={JETTING: AttackStat(JETTING, damage=120, cost=1),
                NEBULA: AttackStat(NEBULA, damage=210, cost=3),
                STARYU: AttackStat(STARYU, damage=20, cost=1),
                OPEN_ATK: AttackStat(OPEN_ATK, damage=30, cost=1)})


def _pilot(functions=None, **kw):
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]})
    default = CardFunctions({WALLYS: ["heal", "clutch_heal"], HILDA: ["search", "tutor_energy"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=default if functions is None else functions, **kw)


@pytest.mark.req("REQ-PLANNER-0001")
def test_retreat_then_attach_unlocks_an_otherwise_missed_ko_is_planned_and_taken():
    """Tracer bullet (corpus 7f48 shape): my Active is a spent opener that can't KO. A benched Mega
    Starmie at 2 Energy can't KO the 180-HP Active either (Jetting Blow 120). But retreating into it
    and attaching the 3rd Energy unlocks Nebula Beam (210) = a 1-prize KO. No existing hook sees this
    two-step enabling line (retreat alone doesn't reach the KO), so the greedy scorer would waste the
    turn. The Planner recognises the ``ko_for_prizes`` line and takes the retreat now."""
    pilot = _pilot()
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                  opp_active=poke(OPP, hp=180), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[WATER], prizes=2, opp_prizes=2)
    obs = make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=board)

    d = pilot.explain(obs)
    assert d.planned is not None                      # KO-for-prizes line found
    assert d.planned.next_step == [0]                 # next step = the enabling retreat
    assert d.planned.goal == "ko_for_prizes"
    assert pilot.decide(obs) == [0]                   # Pilot takes it


@pytest.mark.req("REQ-PLANNER-0002")
def test_planner_stands_down_when_the_tuned_scoring_already_reaches_the_ko():
    """Layer-on-top (ADR-0031 decision 6): the same board, but the benched Mega is at 3 Energy — retreat
    ALONE unlocks Nebula, which the existing ``_retreat_to_lethal_tactical`` hook already scores
    KO_SCORE-class. The tuned machinery reaches the KO, so the Planner defers (``planned is None``) — it
    never duplicates or fights what the greedy scorer would already play."""
    pilot = _pilot()
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=3, hp=330)],
                  opp_active=poke(OPP, hp=180), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[WATER], prizes=2, opp_prizes=2)
    obs = make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=board)
    assert pilot.explain(obs).planned is None


@pytest.mark.req("REQ-PLANNER-0003")
def test_evolve_then_attach_unlocks_an_otherwise_missed_ko_is_planned_and_taken():
    """The evolve sibling of the tracer (corpus a211 shape, generalised to a non-winning KO): my Active
    is a bare Staryu whose 20-damage attack can't KO. Evolving to Mega Starmie (the Energy carries
    through) and attaching the 3rd Energy unlocks Nebula (210) = a 1-prize KO. No hook scores an
    evolve-unlock, so the Planner does the lookahead and takes the evolve now."""
    pilot = _pilot()
    evolve = opt(EVOLVE, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)   # Staryu -> Mega (hand[0])
    board = state(active=poke(PREEVO, energy=2, hp=70), opp_active=poke(OPP, hp=180),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[WINCON, WATER], prizes=2, opp_prizes=2)
    obs = make_select([evolve, attack_opt(STARYU), opt(END)], current=board)
    d = pilot.explain(obs)
    assert d.planned is not None and d.planned.next_step == [0]   # lock the evolve unlocking the KO
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-PLANNER-0004")
def test_no_planned_line_when_no_enabling_step_reaches_a_ko():
    """Soundness: the opponent's Active is too healthy (330 HP) — even the retreat-into-Mega + attach
    tops out at Nebula 210, short of a KO. There is no KO-for-prizes line, so the Planner produces
    nothing and defers to the tuned scoring (``planned is None``)."""
    pilot = _pilot()
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                  opp_active=poke(OPP, hp=330), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[WATER], prizes=2, opp_prizes=2)
    obs = make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=board)
    assert pilot.explain(obs).planned is None


@pytest.mark.req("REQ-PLANNER-0005")
def test_planner_only_acts_at_the_single_pick_main_menu():
    """Guard: like the Lethal Solver, the Planner acts only at the single-pick MAIN menu. A multi-pick
    MAIN select (maxCount > 1) — a batch context the greedy grab owns — is left untouched."""
    pilot = _pilot()
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                  opp_active=poke(OPP, hp=180), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[WATER], prizes=2, opp_prizes=2)
    obs = make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=board, max_count=2)
    assert pilot.explain(obs).planned is None


@pytest.mark.req("REQ-PLANNER-0006")
def test_no_planned_line_when_the_enabling_attach_is_not_available():
    """Soundness: the retreat→attach→KO line needs this turn's one Energy attach, but the hand holds no
    reusable Energy — so the attach can't happen and the KO isn't actually reachable. The Planner must
    NOT commit a line it can't execute (``planned is None``); the Mega at 2 Energy can't KO on its own."""
    pilot = _pilot()
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                  opp_active=poke(OPP, hp=180), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[], prizes=2, opp_prizes=2)                    # no reusable Energy in hand
    obs = make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=board)
    assert pilot.explain(obs).planned is None


@pytest.mark.req("REQ-PLANNER-0007")
def test_planned_line_is_emitted_in_decision_telemetry():
    """The Planner's committed line rides in the @T Decision Telemetry (ADR-0019) — the SAME
    ``to_record`` feeds the live stderr line, a Correction's ``live_trace``, and the tuner retest — so a
    blunder correction on a planned decision carries the plan for analysis. A committed line surfaces
    its step + goal + rationale; a decision with no plan surfaces ``planned: None`` (the key is always
    present so corrections can filter on it, like the Lethal Solver's verdict)."""
    pilot = _pilot()
    won = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                opp_active=poke(OPP, hp=180), opp_bench=[poke(BENCHIE, hp=100)],
                hand=[WATER], prizes=2, opp_prizes=2)
    rec = to_record(pilot.explain(make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=won)))
    assert rec["planned"] == {"step": [0], "goal": "ko_for_prizes",
                              "why": "plan (ko_for_prizes): retreat unlocks a 1-prize KO"}

    safe = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                 opp_active=poke(OPP, hp=330), opp_bench=[poke(BENCHIE, hp=100)], hand=[WATER],
                 prizes=2, opp_prizes=2)
    rec_none = to_record(pilot.explain(make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=safe)))
    assert "planned" in rec_none and rec_none["planned"] is None


# ------------------------------------------------------------------ P2: survival + threat leaf terms
@pytest.mark.req("REQ-PLANNER-0008")
def test_planned_line_value_reflects_post_ko_survival():
    """The leaf-eval sees 1-ply survival (ADR-0031 decision 2): the SAME retreat→attach→KO line is
    assessed higher when my Mega survives next turn than when a benched opponent attacker will KO it
    after I take the prize. Prizes still dominate — the KO is committed either way — but the plan's
    value carries the survival term (Incoming over the opponent's Bench, their predicted next promotion)."""
    pilot = _pilot()
    safe = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                 opp_active=poke(OPP, hp=180), opp_bench=[poke(BENCHIE, hp=100)],
                 hand=[WATER], prizes=2, opp_prizes=2)
    doomed = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                   opp_active=poke(OPP, hp=180), opp_bench=[poke(BIGATK, hp=200)],   # KOs my Mega next turn
                   hand=[WATER], prizes=2, opp_prizes=2)
    p_safe = pilot.explain(make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=safe)).planned
    p_doomed = pilot.explain(make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=doomed)).planned
    assert p_safe is not None and p_doomed is not None
    assert p_safe.next_step == [0] and p_doomed.next_step == [0]   # prizes dominate: KO taken either way
    assert p_safe.value > p_doomed.value                          # survival lifts the safe line


@pytest.mark.req("REQ-PLANNER-0009")
def test_leaf_value_prizes_dominate_positional_terms():
    """The leaf-eval ranking contract (ADR-0031 decision 3), the analog of the Lethal Solver's
    no-false-lethal invariant: the prize term dominates every positional term, so a bigger KO always
    ranks first and no survival/threat combination can outrank a real prize. Survival only breaks ties
    AMONG equal-prize lines."""
    lv = _pilot()._leaf_value
    assert lv(prizes=2, active_survives=False) > lv(prizes=1, active_survives=True)      # more prizes win
    assert lv(prizes=1, active_survives=True) > lv(prizes=1, active_survives=False)       # survival breaks tie
    assert lv(prizes=1, active_survives=False) > lv(prizes=0, active_survives=True, threat_removed=10_000)


# ---------------------------------------------------------- P3: engine-sim rank (fallback, lib-free)
@pytest.mark.req("REQ-PLANNER-0010")
def test_engine_leaf_value_is_none_without_a_search_observation():
    """Fallback (ADR-0031 decision 7): with no ``search_begin_input`` on the observation (the lib-free
    unit path), the engine leaf-eval returns None so the caller keeps its closed-form value — the
    Planner never crashes on a missing engine. The engine round-trip itself is proven on a real
    observation in ``test_planner_engine.py``."""
    pilot = _pilot()
    board = state(active=poke(OPENER, energy=1, hp=110), opp_active=poke(OPP, hp=180),
                  prizes=2, opp_prizes=2)
    obs = make_select([opt(END)], current=board)
    assert pilot._engine_leaf_value(obs, [0]) is None
    assert pilot._simulate_line(obs, [0]) is None


# ------------------------------------------ P4: turn-scoped committed-plan cache + re-plan-on-reveal
def _ko_obs(opp_hp=180):
    return make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)],
                       current=state(active=poke(OPENER, energy=1, hp=110),
                                     bench=[poke(WINCON, energy=2, hp=330)], opp_active=poke(OPP, hp=opp_hp),
                                     opp_bench=[poke(BENCHIE, hp=100)], hand=[WATER], prizes=2, opp_prizes=2))


@pytest.mark.req("REQ-PLANNER-0013")
def test_committed_plan_is_cached_as_turn_scoped_state():
    """Turn-scoped committed-plan state (ADR-0031 decision 5): committing a line records it on the Pilot;
    re-deciding the SAME board returns the cached line object (no re-plan), so the ranking runs once per
    board — not once per decision — beside the match-scoped Scout / deck-tracker state."""
    pilot = _pilot()
    obs = _ko_obs()
    line1 = pilot.explain(obs).planned
    assert line1 is not None and pilot._turn_plan is not None   # plan cached as turn state
    assert pilot.explain(obs).planned is line1                  # same board -> cached object reused


@pytest.mark.req("REQ-PLANNER-0014")
def test_plan_is_recomputed_when_the_board_reveals_new_information():
    """Re-plan on reveal (ADR-0031 decision 5): a changed board (a draw/search reveal, a KO, a new turn)
    changes the plan fingerprint, so the Planner re-plans rather than returning the stale cached line —
    here the opponent's Active is now too healthy to KO, so the plan correctly collapses to None."""
    pilot = _pilot()
    assert pilot.explain(_ko_obs(opp_hp=180)).planned is not None
    assert pilot.explain(_ko_obs(opp_hp=330)).planned is None   # reveal invalidates cached KO line


@pytest.mark.req("REQ-PLANNER-0015")
def test_no_nested_plan_or_cache_while_simulating():
    """Reentrancy guard: while an engine sim re-runs my policy (``_planning`` set), ``plan_turn`` takes
    the closed-form path only — it never launches a nested search from inside a search (which would
    corrupt the shared engine state) and never writes the turn cache. It still returns the closed-form
    KO line, so the simulated continuation stays coherent."""
    pilot = _pilot()
    pilot._planning = True
    try:
        d = pilot.explain(_ko_obs())
    finally:
        pilot._planning = False
    assert d.planned is not None and d.planned.next_step == [0]   # closed-form line still returned
    assert pilot._turn_plan is None                                # not cached (mid-sim)


# ------------------------------------------------------ stabilize-then-KO (0cbc): heal AND take the KO
@pytest.mark.req("REQ-PLANNER-0017")
def test_stabilize_then_ko_heals_to_full_and_keeps_the_ko_when_doomed():
    """0cbc shape: my Mega ex Active can KO the opponent's Active this turn (Jetting Blow 120 vs 70), but
    it is DOOMED — the opponent's 210-damage attacker KOs it next turn. Playing Wally's Compassion
    (clutch_heal) first heals to full and bounces its Energy; one re-attach still affords Jetting Blow, so
    I KO **and** survive. The greedy scorer suppresses the heal (a KO is available — the `active_can_ko`
    trap that caused the blunder), so the Planner commits the heal to combine both goals."""
    pilot = _pilot()
    play_wallys = opt(PLAY, area=HAND, index=0)
    attach_water = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)
    board = state(active=poke(WINCON, energy=2, hp=100), opp_active=poke(THREAT, hp=70),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[WALLYS, WATER], prizes=2, opp_prizes=2)
    obs = make_select([play_wallys, attach_water, attack_opt(JETTING), opt(END)], current=board)
    b = pilot._board(obs)
    assert b.active_doomed and b.active_can_ko          # doomed, yet a KO is on the board (the trap)
    d = pilot.explain(obs)
    assert d.planned is not None and d.planned.goal == "stabilize_then_ko"
    assert d.planned.next_step == [0]                   # play Wally's first (heal, re-power, then KO)
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-PLANNER-0018")
def test_stabilize_stands_down_when_the_heal_would_forfeit_the_ko():
    """Soundness: the ONLY KO here is Nebula Beam (cost 3, 210 vs a 180-HP Active); my Active affords it
    NOW at 3 Energy. But Wally's bounce drops it to 0 and only ONE re-attach is possible this turn — Nebula
    is then unaffordable, so healing would FORFEIT the KO. The Planner must not heal-and-stall: it stands
    down (``planned is None``) and the tuned scoring takes the prize."""
    pilot = _pilot()
    board = state(active=poke(WINCON, energy=3, hp=100), opp_active=poke(THREAT, hp=180),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[WALLYS, WATER], prizes=2, opp_prizes=2)
    obs = make_select([opt(PLAY, area=HAND, index=0),
                       opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                       attack_opt(NEBULA), attack_opt(JETTING), opt(END)], current=board)
    assert pilot._board(obs).active_doomed and pilot._board(obs).active_can_ko
    assert pilot.explain(obs).planned is None           # can't re-power KO -> don't heal


@pytest.mark.req("REQ-PLANNER-0019")
def test_stabilize_stands_down_when_the_active_is_not_doomed():
    """Soundness: with the Active healthy (300 HP vs 210 Incoming) there is nothing to stabilise, so the
    Planner does NOT spend Wally's to top off — it defers and the KO is taken as usual (``planned is
    None``). Keeps the 'take the prize, don't heal-and-stall' default when survival isn't at stake."""
    pilot = _pilot()
    board = state(active=poke(WINCON, energy=2, hp=300), opp_active=poke(THREAT, hp=70),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[WALLYS, WATER], prizes=2, opp_prizes=2)
    obs = make_select([opt(PLAY, area=HAND, index=0),
                       opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                       attack_opt(JETTING), opt(END)], current=board)
    assert not pilot._board(obs).active_doomed
    assert pilot.explain(obs).planned is None


# --------------------------------------- stabilize via Effect Clauses (ADR-0032 4b): any heal with the numbers
SUPER_POTION, POTION = 1112, 1117


def _effects(table):
    from common.effects import CardEffects
    return CardEffects(table)


@pytest.mark.req("REQ-PLANNER-0024")
def test_clause_heal_stabilizes_when_amount_and_rider_math_check_out():
    """ADR-0032 4b: Super Potion's CLAUSE (heal 60, rider discard_own_energy) generalizes the
    Wally-only stabilize: my doomed Mega (160/330, Incoming 210) KOs the 70-HP glass cannon with
    Jetting Blow; heal 60 -> 220 > 210 survives, and after the rider discards one Energy (2 -> 1)
    plus the manual attach, Jetting (cost 1) is still affordable — heal first, still take the KO."""
    pilot = _pilot(effects=_effects({SUPER_POTION: [
        {"kind": "heal", "amount": 60, "rider": "discard_own_energy"}]}))
    board = state(active=poke(WINCON, energy=2, hp=160), opp_active=poke(THREAT, hp=70),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[SUPER_POTION, WATER],
                  prizes=2, opp_prizes=2)
    obs = make_select([opt(PLAY, area=HAND, index=0),
                       opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                       attack_opt(JETTING), opt(END)], current=board)
    b = pilot._board(obs)
    assert b.active_doomed and b.active_can_ko
    d = pilot.explain(obs)
    assert d.planned is not None and d.planned.goal == "stabilize_then_ko"
    assert d.planned.next_step == [0] and pilot.decide(obs) == [0]


@pytest.mark.req("REQ-PLANNER-0024")
def test_clause_heal_stands_down_when_the_amount_cannot_stabilize():
    # Potion heals 30: 160+30=190 <= 210 Incoming — heal wouldn't save Active, don't spend it
    pilot = _pilot(effects=_effects({POTION: [{"kind": "heal", "amount": 30}]}))
    board = state(active=poke(WINCON, energy=2, hp=160), opp_active=poke(THREAT, hp=70),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[POTION, WATER], prizes=2, opp_prizes=2)
    obs = make_select([opt(PLAY, area=HAND, index=0),
                       opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                       attack_opt(JETTING), opt(END)], current=board)
    assert pilot.explain(obs).planned is None


@pytest.mark.req("REQ-PLANNER-0024")
def test_clause_heal_stands_down_when_its_rider_forfeits_the_ko():
    # ONLY KO is Nebula (cost 3) at exactly 2 Energy + 1 attach = 3 — but Super Potion's rider
    # discards one (2 -> 1 + 1 = 2 < 3): healing would forfeit the prize -> stand down
    pilot = _pilot(effects=_effects({SUPER_POTION: [
        {"kind": "heal", "amount": 60, "rider": "discard_own_energy"}]}))
    board = state(active=poke(WINCON, energy=2, hp=160), opp_active=poke(OPP, hp=180),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[SUPER_POTION, WATER],
                  prizes=2, opp_prizes=2)
    obs = make_select([opt(PLAY, area=HAND, index=0),
                       opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                       attack_opt(NEBULA), opt(END)], current=board)
    assert pilot.explain(obs).planned is None


@pytest.mark.req("REQ-PLANNER-0024")
def test_clause_restriction_gates_the_candidate():
    # mega-only heal clause can't target my non-Mega Active: skipped, no line
    pilot = _pilot(effects=_effects({SUPER_POTION: [
        {"kind": "heal", "amount": 200, "restriction": "mega_only"}]}))
    board = state(active=poke(OPENER, energy=1, hp=100), opp_active=poke(THREAT, hp=30),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[SUPER_POTION, WATER],
                  prizes=2, opp_prizes=2)
    obs = make_select([opt(PLAY, area=HAND, index=0),
                       opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                       attack_opt(OPEN_ATK), opt(END)], current=board)
    b = pilot._board(obs)
    assert b.active_doomed and b.active_can_ko
    assert pilot.explain(obs).planned is None


@pytest.mark.req("REQ-PLANNER-0025")
def test_board_checkable_condition_gates_are_evaluated():
    # Bianca's Devotion: heal ALL, gated on "30 HP or less remaining" — gate is board-checkable,
    # so Planner evaluates it instead of fail-closed skipping. At 20/330 gate passes (heal to
    # full, KO kept); at 160/330 gate fails -> no line.
    BIANCA = 1190
    eff = _effects({BIANCA: [{"kind": "heal", "amount": "all",
                              "condition": "remaining_hp_30_or_less"}]})
    for hp, fires in ((20, True), (160, False)):
        pilot = _pilot(effects=eff)
        board = state(active=poke(WINCON, energy=2, hp=hp), opp_active=poke(THREAT, hp=70),
                      opp_bench=[poke(BENCHIE, hp=100)], hand=[BIANCA, WATER],
                      prizes=2, opp_prizes=2)
        obs = make_select([opt(PLAY, area=HAND, index=0),
                           opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                           attack_opt(JETTING), opt(END)], current=board)
        planned = pilot.explain(obs).planned
        assert (planned is not None) is fires, f"hp={hp}"
        if fires:
            assert planned.goal == "stabilize_then_ko"


@pytest.mark.req("REQ-PLANNER-0025")
def test_energy_gate_is_evaluated():
    # Jumbo Ice Cream: heal 80, gated on the Active having 3+ Energy — checkable off the board
    JUMBO = 1147
    eff = _effects({JUMBO: [{"kind": "heal", "amount": 80, "condition": "energy_3_plus"}]})
    for energy, fires in ((3, True), (2, False)):
        pilot = _pilot(effects=eff)
        board = state(active=poke(WINCON, energy=energy, hp=160), opp_active=poke(THREAT, hp=70),
                      opp_bench=[poke(BENCHIE, hp=100)], hand=[JUMBO, WATER],
                      prizes=2, opp_prizes=2)
        obs = make_select([opt(PLAY, area=HAND, index=0),
                           opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                           attack_opt(JETTING), opt(END)], current=board)
        assert (pilot.explain(obs).planned is not None) is fires, f"energy={energy}"


@pytest.mark.req("REQ-PLANNER-0025")
def test_unknown_condition_still_fails_closed():
    eff = _effects({1242: [{"kind": "heal", "amount": 200, "condition": "played_supporter_this_turn"}]})
    pilot = _pilot(effects=eff)
    board = state(active=poke(WINCON, energy=2, hp=160), opp_active=poke(THREAT, hp=70),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[1242, WATER], prizes=2, opp_prizes=2)
    obs = make_select([opt(PLAY, area=HAND, index=0),
                       opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                       attack_opt(JETTING), opt(END)], current=board)
    assert pilot.explain(obs).planned is None       # not board-checkable -> never plan on it


# ------------------------------------------- Supporter-enabled KO line (4298): the tutor supplies the attach
@pytest.mark.req("REQ-PLANNER-0021")
def test_energy_tutor_supporter_unlocks_an_otherwise_missed_ko_is_planned_and_taken():
    """Tracer (corpus 4298 shape): my Active is a spent opener; a benched Mega Starmie has NO Energy, so
    it can't KO and no retreat-KO line exists — the hand holds no Energy to attach. But it holds Hilda, a
    Supporter that searches an Energy into hand (``tutor_energy``). Playing Hilda supplies the attach, so
    retreat-into-Mega + that attach unlocks Jetting Blow (120) = a 1-prize KO the greedy scorer can't see
    (no single option scores it, and the enabling first step is a Supporter, not a retreat/evolve). The
    Planner recognises the ``ko_for_prizes`` line and plays Hilda now."""
    pilot = _pilot()
    play_hilda = opt(PLAY, area=HAND, index=0)
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=0, hp=330)],
                  opp_active=poke(BENCHIE, hp=100), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[HILDA], prizes=2, opp_prizes=2)                 # no Energy in hand — Hilda fetches it
    obs = make_select([play_hilda, attack_opt(OPEN_ATK), opt(END)], current=board)

    d = pilot.explain(obs)
    assert d.planned is not None                       # KO-for-prizes line found
    assert d.planned.goal == "ko_for_prizes"
    assert d.planned.next_step == [0]                  # next step = playing the energy tutor
    assert pilot.decide(obs) == [0]                    # Pilot takes it


@pytest.mark.req("REQ-PLANNER-0021")
def test_energy_tutor_line_generalizes_to_any_tutor_energy_supporter():
    """The Supporter-enabled KO line is driven by the ``tutor_energy`` *tag*, not by Hilda's id: the
    same 4298-shape line fires for any of the nine deck-search-Energy Trainers now carrying the tag
    (Energy Search, Colress's Tenacity, Crispin, …). Same board, a different tutor id — the Planner
    still plays it to supply the attach that unlocks the retreat→attach→KO. Guards against a
    regression that hardcodes a single card."""
    energy_search = 1119                               # tutor_energy sibling (Item) — not Hilda
    pilot = _pilot(functions=CardFunctions({energy_search: ["search", "tutor_energy"]}))
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=0, hp=330)],
                  opp_active=poke(BENCHIE, hp=100), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[energy_search], prizes=2, opp_prizes=2)   # no Energy in hand — tutor fetches it
    obs = make_select([opt(PLAY, area=HAND, index=0), attack_opt(OPEN_ATK), opt(END)], current=board)

    d = pilot.explain(obs)
    assert d.planned is not None and d.planned.goal == "ko_for_prizes"
    assert d.planned.next_step == [0]                  # play the (non-Hilda) energy tutor
    assert pilot.decide(obs) == [0]


# ------------------------------- multi-candidate ENGINE RANKING (ADR-0031 P3 completion, item 2a)
def _two_candidate_obs():
    """A board with TWO viable ko_for_prizes candidates: retreat into the benched 2-Energy Mega
    (option 0, + attach -> Nebula 210 KOs 180) OR evolve the Active Staryu to Mega (option 1, the 2
    Energy carry through, + attach -> Nebula). Equal closed-form leaf values -> the closed-form pick
    is the first (the retreat)."""
    board = state(active=poke(PREEVO, energy=2, hp=70), bench=[poke(WINCON, energy=2, hp=330)],
                  opp_active=poke(OPP, hp=180), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[WINCON, WATER], prizes=2, opp_prizes=2)
    evolve = opt(EVOLVE, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)
    return make_select([opt(RETREAT), evolve, attack_opt(STARYU), opt(END)], current=board)


@pytest.mark.req("REQ-PLANNER-0026")
def test_engine_rank_off_by_default_keeps_the_closed_form_pick():
    """Kill-switch (ADR-0021 pattern): without ``planner_engine_rank=True`` a multi-candidate board
    commits the closed-form best (ties break to the first generated) and the line is not marked
    engine-ranked — byte-identical to the shipped behavior."""
    pilot = _pilot()
    d = pilot.explain(_two_candidate_obs())
    assert d.planned is not None and d.planned.next_step == [0]   # the closed-form (first) candidate
    assert d.planned.ranked_by is None                            # no ranking ran (switch off)


@pytest.mark.req("REQ-PLANNER-0027")
def test_engine_rank_commits_the_engine_best_candidate(monkeypatch):
    """Multi-candidate ranking (the ADR-0031 deferred phase, built): with the switch ON, every
    closed-form candidate is engine-simmed and the ENGINE's leaf value picks the committed line —
    here the engine values the evolve line above the retreat the closed form would take. The
    divergence is recorded for the A/B fire/divergence count."""
    pilot = _pilot(planner_engine_rank=True)
    values = {(0,): KO_SCORE + 60.0, (1,): KO_SCORE + 160.0}
    monkeypatch.setattr(pilot, "_engine_leaf_value",
                        lambda obs, step: values[tuple(step)])
    d = pilot.explain(_two_candidate_obs())
    assert d.planned is not None and d.planned.next_step == [1]   # the engine's pick, not closed-form's
    assert d.planned.ranked_by == "engine" and d.planned.diverged is True
    assert to_record(d)["planned"]["ranked"] == "engine"
    assert to_record(d)["planned"]["diverged"] is True


@pytest.mark.req("REQ-PLANNER-0027")
def test_engine_rank_result_is_cached_per_reveal():
    """Plan-once-cache (decision 5) holds for the ranked plan: the N candidate sims run once per
    board fingerprint — the same board returns the cached line object without re-simulating."""
    pilot = _pilot(planner_engine_rank=True)
    calls = []
    pilot._engine_leaf_value = lambda obs, step: calls.append(tuple(step)) or (KO_SCORE + 50.0)
    obs = _two_candidate_obs()
    line1 = pilot.explain(obs).planned
    n = len(calls)
    assert line1 is not None and n >= 2                           # every candidate was simmed once
    assert pilot.explain(obs).planned is line1                    # cache hit ...
    assert len(calls) == n                                        # ... no re-simulation


@pytest.mark.req("REQ-PLANNER-0028")
def test_engine_rank_defers_when_every_candidate_collapses(monkeypatch):
    """The natural veto: when the engine end-boards show NO candidate actually takes a prize (every
    ranked value below KO_SCORE — the rung's premise failed in sim), the Planner defers to the tuned
    scoring instead of committing a refuted line. The proven default decides the turn."""
    pilot = _pilot(planner_engine_rank=True)
    monkeypatch.setattr(pilot, "_engine_leaf_value", lambda obs, step: 50.0)
    d = pilot.explain(_two_candidate_obs())
    assert d.planned is None                                      # refuted premise -> defer
    assert d.chosen                                               # the tuned scoring still decided


@pytest.mark.req("REQ-PLANNER-0029")
def test_engine_rank_falls_back_per_candidate_when_a_sim_is_unavailable(monkeypatch):
    """Fail-safe (decision 7, per candidate): a None sim keeps that candidate's closed-form value on
    the SAME leaf scale, so an unavailable engine (or one failed fork) never loses the line — with
    every sim unavailable the pick degrades exactly to the closed-form choice, marked unranked."""
    pilot = _pilot(planner_engine_rank=True)
    monkeypatch.setattr(pilot, "_engine_leaf_value", lambda obs, step: None)
    d = pilot.explain(_two_candidate_obs())
    assert d.planned is not None and d.planned.next_step == [0]   # closed-form pick survives
    assert d.planned.ranked_by == "closed" and d.planned.diverged is False

    # mixed: candidate 0 unavailable (keeps closed-form value >= KO_SCORE), candidate 1 engine-refuted
    # (collapsed) -> the unrefuted closed-form line wins; the engine's refute of [1] still counted.
    pilot2 = _pilot(planner_engine_rank=True)
    monkeypatch.setattr(pilot2, "_engine_leaf_value",
                        lambda obs, step: None if tuple(step) == (0,) else 50.0)
    d2 = pilot2.explain(_two_candidate_obs())
    assert d2.planned is not None and d2.planned.next_step == [0]
    assert d2.planned.ranked_by == "closed"


# --------------------------------------------- the KO-the-key-threat rung (ADR-0031 ladder, item 2b)
SNIPE = 15      # attack id: cost 1, 50 to the Active + a 100 bench-snipe rider
THREATB = 702   # opponent's benched KEY threat: a 340-damage glass cannon at 90 HP (snipe-KO-able)


def _snipe_stats():
    base = {
        WINCON: CardStat(WINCON, name="Mega Starmie ex", hp=330, energyType=3, minAttackCost=1,
                         minCostDamage=50, maxDamage=210, maxDamageCost=3,
                         attacks=(JETTING, NEBULA, SNIPE), evolvesFrom="Staryu", megaEx=True),
        OPENER: CardStat(OPENER, name="opener", hp=110, energyType=3, minAttackCost=1,
                         minCostDamage=30, maxDamage=30, attacks=(OPEN_ATK,)),
        OPP: CardStat(OPP, name="opp active", hp=330, energyType=7),
        BENCHIE: CardStat(BENCHIE, name="opp benchie", hp=100, energyType=7),
        THREATB: CardStat(THREATB, name="benched glass cannon", hp=90, energyType=7,
                          minAttackCost=1, minCostDamage=340, maxDamage=340),
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
    }
    return DictCardStatProvider(base, attacks={
        JETTING: AttackStat(JETTING, damage=120, cost=1),
        NEBULA: AttackStat(NEBULA, damage=210, cost=3),
        SNIPE: AttackStat(SNIPE, damage=50, cost=1, benchSnipe=100),
        OPEN_ATK: AttackStat(OPEN_ATK, damage=30, cost=1)})


def _snipe_pilot(**kw):
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_snipe_stats(),
                 functions=CardFunctions({}), **kw)


def _key_threat_obs():
    """No KO reachable vs the 330-HP Active (even Nebula 210 after retreat+attach falls short), and
    my spent opener can't do anything — but retreating into the benched Mega brings its SNIPE online,
    whose 100 bench rider KOs the opponent's benched 340-damage glass cannon (90 HP), the bench's top
    threat. A snipe-KO ON the menu is the Tactical layer's turf (it credits the prize KO_SCORE-class);
    the RETREAT that reaches one is scored by no hook — the rung's gap."""
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                  opp_active=poke(OPP, hp=330),
                  opp_bench=[poke(THREATB, energy=1, hp=90), poke(BENCHIE, hp=100)],
                  hand=[WATER], prizes=3, opp_prizes=3)
    return make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=board)


@pytest.mark.req("REQ-PLANNER-0031")
def test_key_threat_rung_commits_the_retreat_that_unlocks_the_threat_snipe():
    """The `KO the opponent's key threat` rung (the Goal Ladder's unbuilt middle rung, CONTEXT.md):
    with no KO on the menu and no Active-KO enabling line, the retreat that brings the sniper online
    against the benched TOP-threat body (by the shared threat rank) is committed — the KO-for-prizes
    generators test the opponent's ACTIVE only, so this line is otherwise invisible. Kill-switched
    (`planner_key_threat`): OFF (the default) leaves the board to the tuned scoring."""
    on = _snipe_pilot(planner_key_threat=True)
    d = on.explain(_key_threat_obs())
    assert d.planned is not None and d.planned.goal == "ko_key_threat"
    assert d.planned.next_step == [0]                  # the enabling retreat
    assert on.decide(_key_threat_obs()) == [0]

    off = _snipe_pilot()
    assert off.explain(_key_threat_obs()).planned is None   # default OFF: byte-identical behavior


@pytest.mark.req("REQ-PLANNER-0031")
def test_key_threat_rung_counts_a_forward_damage_only_threat():
    """The review-caught basis mismatch: the top threat is RANKED by max(own, forward) damage, so
    the magnitude gate must use the same basis — a 0-printed benched base whose evolution line
    reaches a monster attack (the Evolving-Threat case the rank exists for) is still a key threat
    worth the snipe, not a silent skip."""
    DREEPY, DRAGA = 704, 705
    stats = _snipe_stats()
    stats._stats[DREEPY] = CardStat(DREEPY, name="Dreepy", hp=60, energyType=7, maxDamage=0)
    stats._stats[DRAGA] = CardStat(DRAGA, name="Dragapult ex", hp=320, energyType=7,
                                   evolvesFrom="Dreepy", minAttackCost=1, minCostDamage=200,
                                   maxDamage=200, attacks=(16,))
    pilot = _snipe_pilot(planner_key_threat=True)
    pilot.stats = stats
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                  opp_active=poke(OPP, hp=330), opp_bench=[poke(DREEPY, hp=60)],
                  hand=[WATER], prizes=3, opp_prizes=3)
    obs = make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=board)
    d = pilot.explain(obs)
    assert d.planned is not None and d.planned.goal == "ko_key_threat"
    assert d.planned.next_step == [0]                  # snipe the base before the monster comes online


@pytest.mark.req("REQ-PLANNER-0032")
def test_key_threat_rung_is_layer_on_top_and_needs_a_snipe_koable_top_threat():
    """(a) Layer-on-top: a status-quo KO on the menu (the 120-HP Active — Jetting KOs, and the
    on-menu SNIPE itself banks the benched KO) stands the rung down: the greedy scorer already takes
    a prize. (b) No benched body that actually THREATENS (a 0-damage fat wall): the rung stays
    silent — it never snipes a non-threat just because it can."""
    pilot = _snipe_pilot(planner_key_threat=True)
    ko_on_menu = state(active=poke(WINCON, energy=3, hp=330), opp_active=poke(OPP, hp=120),
                       opp_bench=[poke(THREATB, energy=1, hp=90)], prizes=3, opp_prizes=3)
    d = pilot.explain(make_select([attack_opt(SNIPE), attack_opt(JETTING), opt(END)], current=ko_on_menu))
    assert d.planned is None                           # the KO on the menu owns the turn

    FATB = 703                                         # a harmless fat benched body (no threat rank)
    stats = _snipe_stats()
    stats._stats[FATB] = CardStat(FATB, name="fat benchie", hp=150, energyType=7)
    pilot2 = _snipe_pilot(planner_key_threat=True)
    pilot2.stats = stats
    no_threat = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                      opp_active=poke(OPP, hp=330), opp_bench=[poke(FATB, hp=150)],
                      hand=[WATER], prizes=3, opp_prizes=3)
    d2 = pilot2.explain(make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=no_threat))
    assert d2.planned is None                          # nothing benched threatens -> no rung


# ------------------------------------------------ the development leaf term (ADR-0031 decision 4, item 2c)
@pytest.mark.req("REQ-PLANNER-0033")
def test_readiness_term_breaks_engine_rank_ties_and_stays_below_a_prize(monkeypatch):
    """The engine-sim leaf's positional term (`_readiness`, replacing `_board_development`) gets its
    input (engine-rank phase, `P3 on`): two candidate lines with EQUAL engine prizes + survival are split
    by the simmed end-board's MY-side readiness — the line that leaves a more developed, attack-readier
    board wins. The hard-rung invariant holds: no positional term can ever outrank a prize."""
    pilot = _pilot(planner_engine_rank=True)

    def fake_sim(obs, first_step, max_steps=40, *, opponent_reply=False):
        me_bare = {"active": [poke(WINCON, energy=1, hp=330)], "bench": [], "prize": [None]}
        me_dev = {"active": [poke(WINCON, energy=1, hp=330)],
                  "bench": [poke(PREEVO, energy=2, hp=70), poke(OPENER, energy=1, hp=110)],
                  "prize": [None]}
        opp = {"active": [poke(BENCHIE, hp=100)], "bench": [], "prize": [None] * 2}
        me = me_dev if first_step == [1] else me_bare
        end = {"current": {"turn": 3, "yourIndex": 0, "players": [me, opp]}}
        return (end, 0, 2, -1, 0.0, False)              # both lines banked 1 prize (2 -> 1), no result;
                                                        # 0 line account; coin-free (the win-trust bit)

    monkeypatch.setattr(pilot, "_simulate_line", fake_sim)
    d = pilot.explain(_two_candidate_obs())
    assert d.planned is not None and d.planned.next_step == [1]   # the readier end-board wins the tie
    assert d.planned.ranked_by == "engine"

    lv = pilot._leaf_value
    # both the legacy development term AND the new readiness term stay capped below a prize
    assert lv(prizes=1, active_survives=False) > lv(prizes=0, active_survives=True,
                                                    threat_removed=10_000, development=10_000)
    assert lv(prizes=1, active_survives=False) > lv(prizes=0, active_survives=True,
                                                    threat_removed=10_000, readiness=10_000, line=10_000)


@pytest.mark.req("REQ-PLANNER-0037")
def test_a_coin_dependent_simmed_win_is_never_the_dominant_short_circuit(monkeypatch):
    """The f24 phantom-win regression (CI, 2026-07-20): `_simulate_line` auto-resolves coins, so a
    line can sim to an outright \"win\" on one lucky RNG stream (7000) and to an ordinary board on
    another (162) — and the dominant win short-circuit let that mirage preempt the tuned scoring.
    The 6th sim-tuple element (``coins``) demotes it: a simmed win is dominant ONLY when the line
    consumed no coin flips; a coin-dependent one ranks as its ordinary end board (prizes banked
    still count), so only the SOUND win rung may claim wins."""
    pilot = _pilot()
    me = {"active": [poke(WINCON, energy=3, hp=330)], "bench": [], "prize": [None] * 2}
    opp = {"active": [poke(BENCHIE, hp=100)], "bench": [], "prize": [None] * 3}
    end = {"current": {"turn": 5, "yourIndex": 0, "players": [me, opp], "result": 0}}

    def fake_sim(coins):
        return lambda obs, first_step, max_steps=40, **kw: (end, 0, 2, 0, 0.0, coins)

    monkeypatch.setattr(pilot, "_simulate_line", fake_sim(False))
    clean = pilot._engine_leaf_value({}, [0])
    monkeypatch.setattr(pilot, "_simulate_line", fake_sim(True))
    coined = pilot._engine_leaf_value({}, [0])
    from common.strategy.context import KO_SCORE
    assert clean == KO_SCORE * 3                        # coin-free win: dominant (prizes+1)
    assert coined < KO_SCORE * 3                        # coin-won "win": ordinary board ranking
    assert coined < clean


@pytest.mark.req("REQ-PLANNER-0037")
def test_develop_rollout_never_ranks_a_coin_contaminated_sim(monkeypatch):
    """The other half of the f24 heisenbug: the develop rollout's OVERRIDE authority comes from a
    reproducible end-board — a coin-riding sim's value swings across RNG streams (162 vs a phantom
    win on the same line), so it is excluded from the ranking like a failed fork. All-coined →
    defer (the tuned scoring keeps the turn); a coin-free line still ranks and commits."""
    pilot = _pilot()
    values = {0: (50.0, True), 1: (40.0, False), 2: (45.0, True)}   # [0]/[2] coined, [1] clean

    def fake_leaf(obs, first_step, spend_account=True, with_coins=False):
        val, coined = values[first_step[0]]
        return (val, coined) if with_coins else val

    monkeypatch.setattr(pilot, "_engine_leaf_value", fake_leaf)
    traces = [type("T", (), {"score": 0.0, "card_id": None})() for _ in range(3)]
    line = pilot._develop_rollout_line({}, {}, None, [{}, {}, {}], traces)
    assert line is not None and line.next_step == [1]   # the clean 40 beats the coined 50/45
    values.update({1: (40.0, True)})                    # now everything is coin-noise
    line = pilot._develop_rollout_line({}, {}, None, [{}, {}, {}], traces)
    assert line is None                                 # all-coined -> defer to the tuned scoring


# --------------------------------- heal-before-attach (corpus 6858 shape): the attach-carried KO
IGNITION = 17   # discard-at-end-of-turn special Energy — {C}, or {C}{C}{C} on an Evolution
BRUISER = 681   # opponent's Active: 180 HP, hits for 210 (dooms my damaged Mega)


def _ignition_pilot(**kw):
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]})
    stats = _stats()
    stats._stats[IGNITION] = CardStat(IGNITION, name="Ignition Energy", hp=0, energyType=0)
    stats._stats[BRUISER] = CardStat(BRUISER, name="bruiser", hp=180, energyType=7,
                                     minAttackCost=1, minCostDamage=210, maxDamage=210)
    fns = CardFunctions({WALLYS: ["heal", "clutch_heal"], IGNITION: ["discard_eot"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=fns,
                 **kw)


@pytest.mark.req("REQ-PLANNER-0036")
def test_stabilize_fires_when_the_ko_rides_the_attach_and_the_burst_survives_the_bounce():
    """6858 shape: my Mega (200/330, 0 Energy) is doomed to the opponent's 210 hit, and the only KO
    is attach-CARRIED — Ignition's {C}{C}{C} on the Evolution unlocks Nebula Beam (210 ≥ 180); no
    ATTACK option is even on the menu. Healing FIRST (Wally's bounces nothing it needs — the burst
    attach lands after) keeps both: the stabilize-then-KO rung must see the attach-carried KO and
    commit the heal ahead of the attach."""
    pilot = _ignition_pilot()
    play_wallys = opt(PLAY, area=HAND, index=0)
    attach_ign = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)
    board = state(active=poke(WINCON, energy=0, hp=200), opp_active=poke(BRUISER, hp=180),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[WALLYS, IGNITION],
                  prizes=6, opp_prizes=6)
    obs = make_select([play_wallys, attach_ign, opt(END)], current=board)
    d = pilot.explain(obs)
    assert d.planned is not None and d.planned.goal == "stabilize_then_ko"
    assert d.planned.next_step == [0]                  # Wally's FIRST; the Ignition attach follows
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-PLANNER-0036")
def test_stabilize_stands_down_when_no_re_attach_exists_after_the_bounce():
    """Soundness: same doom, but the hand holds NO Energy — after Wally's bounce nothing re-powers
    the Mega, so the KO is genuinely forfeited by healing. The rung must not commit (no candidate
    KO on the menu or the attach), leaving the decision to the tuned scoring."""
    pilot = _ignition_pilot()
    board = state(active=poke(WINCON, energy=0, hp=200), opp_active=poke(BRUISER, hp=180),
                  opp_bench=[poke(BENCHIE, hp=100)], hand=[WALLYS], prizes=6, opp_prizes=6)
    obs = make_select([opt(PLAY, area=HAND, index=0), opt(END)], current=board)
    assert pilot.explain(obs).planned is None


# ------------------------------------------- the evolution-tutor line (Salvatore, corpus a212 shape)
SALV = 1189     # Salvatore — Supporter that evolves an in-play Pokémon straight from the deck
ABIL = 902      # an ability-bearing evolution (Salvatore's own filter excludes it)


def _salvatore_pilot(deck=None, stats=None, **kw):
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]})
    fns = CardFunctions({SALV: ["search", "rush_evolve"]})
    return Pilot(strat, deck=deck or ([WINCON] * 3 + [1] * 57), general_strategy=GENERAL_STRATEGY,
                 stats=stats or _stats(), functions=fns, **kw)


def _salvatore_obs(options=None, *, anchored=False):
    """The a212 shape: spent opener Active, a bare benched Staryu, Salvatore + a {W} Energy in hand,
    the opponent's last body (70 HP) Active with an EMPTY bench — Salvatore evolves the Staryu into
    the deck's Mega Starmie, the free retreat + attach bring Jetting Blow (120) online: KO empties
    their board. ``anchored=True`` rides the deck-tracker's exact prize resolution (`own_prizes`)."""
    board = state(active=poke(OPENER, energy=0, hp=110), bench=[poke(PREEVO, energy=0, hp=70)],
                  opp_active=poke(THREAT, hp=70), opp_bench=[],
                  hand=[SALV, WATER], prizes=6, opp_prizes=6, deck_count=44)
    obs = make_select(options or [opt(PLAY, area=HAND, index=0), opt(RETREAT), opt(END)],
                      current=board)
    if anchored:
        obs["own_prizes"] = {}                         # prizes resolved: nothing relevant is prized
    return obs


@pytest.mark.req("REQ-PLANNER-0035")
def test_evolution_tutor_win_lock_on_deck_certainty():
    """The win rung's tier-4 (a212): with the deck-tracker ANCHORED (`own_prizes`) the Mega Starmie
    is PROVABLY still in the deck, so Salvatore -> evolve the benched Staryu -> retreat -> attach ->
    Jetting Blow empties the opponent's board — a sound, guaranteed win. The Lethal Solver locks the
    Supporter as the line's first step."""
    pilot = _salvatore_pilot(lethal_family=True)
    obs = _salvatore_obs(anchored=True)
    d = pilot.explain(obs)
    assert d.planned is not None and d.planned.goal == "win"
    assert d.planned.next_step == [0]                  # play Salvatore now
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-PLANNER-0035")
def test_evolution_tutor_win_needs_positive_deck_certainty():
    """Soundness: without the tracker's positive certainty (no `own_prizes` anchor) the evolution
    could be prized — the win rung must NOT lock it (the heuristic ko_for_prizes rung may still
    rank-commit the line, but never as a guaranteed win)."""
    pilot = _salvatore_pilot(lethal_family=True)
    d = pilot.explain(_salvatore_obs())
    assert d.planned is None or d.planned.goal != "win"


@pytest.mark.req("REQ-PLANNER-0035")
def test_evolution_tutor_excludes_ability_bearing_evolutions():
    """Salvatore's own filter: it can only fetch a card with NO Abilities. A deck whose only
    evolution of the benched Staryu carries an Ability yields no line — neither the win rung nor
    the heuristic rung may plan on an ineligible fetch."""
    stats = _stats()
    stats._stats[ABIL] = CardStat(ABIL, name="Abil Starmie ex", hp=330, energyType=3,
                                  minAttackCost=1, minCostDamage=120, maxDamage=120,
                                  attacks=(JETTING,), evolvesFrom="Staryu", hasAbility=True)
    pilot = _salvatore_pilot(deck=[ABIL] * 3 + [1] * 57, stats=stats, lethal_family=True)
    obs = _salvatore_obs(anchored=True)
    assert pilot.explain(obs).planned is None


@pytest.mark.req("REQ-PLANNER-0035")
def test_evolution_tutor_benched_target_needs_the_retreat_on_the_menu():
    """Soundness: the winning attacker evolves on the BENCH, so the line needs this turn's retreat
    to bring it Active. With no retreat offered (e.g. already spent), the line can't execute —
    nothing is planned."""
    pilot = _salvatore_pilot(lethal_family=True)
    obs = _salvatore_obs(options=[opt(PLAY, area=HAND, index=0), opt(END)], anchored=True)
    assert pilot.explain(obs).planned is None


@pytest.mark.req("REQ-PLANNER-0035")
def test_evolution_tutor_heuristic_commits_the_ko_line_without_certainty():
    """The rank-grade half (the retest path — tracker cold): no `own_prizes`, but the Mega is
    majority-LIKELY still in the deck (deck odds), so the KO-for-prizes rung commits Salvatore as
    the enabling first step of the evolve -> retreat -> attach -> KO line the greedy scorer can't
    see."""
    pilot = _salvatore_pilot()
    obs = _salvatore_obs()
    d = pilot.explain(obs)
    assert d.planned is not None and d.planned.goal == "ko_for_prizes"
    assert "evolution tutor" in d.planned.rationale
    assert d.planned.next_step == [0]
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-PLANNER-0022")
def test_energy_tutor_stands_down_when_the_turns_attach_is_already_spent():
    """Soundness: the tutor-energy line only works because the fetched Energy can be attached THIS turn.
    If the turn's one Energy attach is already spent (``energyAttached``), Hilda's Energy can't reach the
    Mega and the KO isn't reachable this turn — so the Planner must NOT commit a line it can't execute.
    Same board as the tracer, but the attach is gone: ``planned is None`` and the tuned scoring decides."""
    pilot = _pilot()
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=0, hp=330)],
                  opp_active=poke(BENCHIE, hp=100), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[HILDA], prizes=2, opp_prizes=2)
    board["energyAttached"] = True                     # this turn's one Energy attach already spent
    obs = make_select([opt(PLAY, area=HAND, index=0), attack_opt(OPEN_ATK), opt(END)], current=board)
    assert pilot.explain(obs).planned is None
