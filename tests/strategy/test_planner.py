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
from common.scouting.provider import CardStat, DictCardStatProvider
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
    })


def _pilot(functions=None, **kw):
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]})
    default = CardFunctions({WALLYS: ["heal", "clutch_heal"], HILDA: ["search", "tutor_energy"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=default if functions is None else functions,
                 attacks={JETTING: 120, NEBULA: 210, STARYU: 20, OPEN_ATK: 30},
                 attack_costs={JETTING: 1, NEBULA: 3, STARYU: 1, OPEN_ATK: 1}, **kw)


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
