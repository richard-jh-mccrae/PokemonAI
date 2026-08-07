"""Turn Planner (ADR-0031): the eager whole-turn optimizer that generalizes the Lethal Solver to a
Goal Ladder, through the Pilot's PUBLIC interface.

Lib-free; the engine-sim slices live in ``test_planner_engine.py``. Read every "stands down"
assertion through `rung()` below: it strips a `goal="compose"` line, which is what these tests mean
by "the planner did not commit".
"""
from dataclasses import dataclass, field

import pytest

from card_facts import ignition_tags                    # the committed Ignition Energy tags, ONE copy
from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.telemetry import to_record
from pilot_helpers import ACTIVE, ATTACH, HAND, PLAY, attack_opt, make_select, opt, poke, state

def rung(planned):
    """The HEURISTIC rung's committed line, or None when only the COMPOSER answered — the bottom rung
    always has an opinion, so "the planner stands down" means "no rung ABOVE the composer committed"."""
    return None if (planned is not None and planned.goal == "compose") else planned


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
_ENERGY_SEARCH = 1119   # a `tutor_energy` ITEM sibling — the generalisation test's non-Hilda tutor
JETTING = 11    # attack id: cost 1, 120 damage
NEBULA = 10     # attack id: cost 3, 210 damage (big attack an extra Energy unlocks)
STARYU = 12     # Staryu's own attack: cost 1, 20 damage (can't KO)
OPEN_ATK = 13   # opener's own attack: cost 1, 30 damage (can't KO)
WATER = 3       # Basic {W} Energy card in hand (reusable attach)


def _stats():
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, synthetic=True, name="Mega Starmie ex", hp=330, energyType=3, minAttackCost=1,
                         minCostDamage=120, maxDamage=210, maxDamageCost=3,
                         attacks=(JETTING, NEBULA), evolvesFrom="Staryu", megaEx=True),
        PREEVO: CardStat(PREEVO, synthetic=True, name="Staryu", hp=70, energyType=3, minAttackCost=1,
                         minCostDamage=20, maxDamage=20, attacks=(STARYU,)),
        OPENER: CardStat(OPENER, synthetic=True, name="opener", hp=110, energyType=3, minAttackCost=1,
                         minCostDamage=30, maxDamage=30, attacks=(OPEN_ATK,)),
        OPP: CardStat(OPP, synthetic=True, name="opp active", hp=180, energyType=7),
        EXOPP: CardStat(EXOPP, synthetic=True, name="opp ex", hp=210, energyType=7, ex=True),
        BENCHIE: CardStat(BENCHIE, synthetic=True, name="opp benchie", hp=100, energyType=7),
        BIGATK: CardStat(BIGATK, synthetic=True, name="big hitter", hp=200, energyType=7, minAttackCost=1,
                         minCostDamage=340, maxDamage=340),   # benched threat, KOs my Mega next turn
        THREAT: CardStat(THREAT, synthetic=True, name="glass cannon", hp=70, energyType=7, minAttackCost=1,
                         minCostDamage=210, maxDamage=210),   # KO-able now, dooms my Active next turn
        # cardType 5 = Basic Energy. Without it `is_typed_basic_energy` is False and the Attach
        # Budget sees no manual-attach source at all (ADR-0075).
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, cardType=5, energyType=3),
        # A tutor needs a stat as well as a tag: `_attach_contribution` rejects an unknown card BEFORE
        # it reads tags (fail-CLOSED, ADR-0067), so a statless tutor's KO line vanishes.
        HILDA: CardStat(HILDA, name="Hilda", hp=0, cardType=3),              # 3 = Supporter
        _ENERGY_SEARCH: CardStat(_ENERGY_SEARCH, name="Energy Search", hp=0, cardType=1),  # 1 = Item
    }, attacks={JETTING: AttackStat(JETTING, damage=120, cost=1),
                NEBULA: AttackStat(NEBULA, damage=210, cost=3),
                STARYU: AttackStat(STARYU, damage=20, cost=1),
                OPEN_ATK: AttackStat(OPEN_ATK, damage=30, cost=1)})


#: Real deck-fetch clauses for the two tutors these tests use. The Attach Budget's YIELD leg fails
#: CLOSED without a clause row (ADR-0067), so every tutor-energy KO line silently vanishes without one.
_TUTOR_CLAUSES = {cid: [{"kind": "fetch", "target": "energy", "zone": "deck"}]
                  for cid in (HILDA, _ENERGY_SEARCH)}


def _pilot(functions=None, deck=None, **kw):
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]})
    default = CardFunctions({WALLYS: ["heal", "clutch_heal"], HILDA: ["search", "tutor_energy"]})
    if "effects" not in kw:
        from common.effects import CardEffects
        kw["effects"] = CardEffects(dict(_TUTOR_CLAUSES))
    return Pilot(strat, deck=[1] * 60 if deck is None else deck,
                 general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=default if functions is None else functions, **kw)


#: A deck the tutors can actually FETCH from. `deck_energy_types` is derived from the decklist, so
#: with the default all-id-1 deck a deck-sourced clause yields nothing and the line cannot exist.
_ENERGY_DECK = [WATER] * 8 + [1] * 52


@pytest.mark.req("REQ-PLANNER-0001")
def test_retreat_then_attach_unlocks_an_otherwise_missed_ko_is_planned_and_taken():
    """No hook sees a TWO-step enabling line — retreat alone does not reach the KO — so the greedy
    scorer would waste the turn."""
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
    """Layer-on-top (ADR-0031 decision 6): the Planner never duplicates or fights what the tuned
    machinery would already play."""
    pilot = _pilot()
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=3, hp=330)],
                  opp_active=poke(OPP, hp=180), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[WATER], prizes=2, opp_prizes=2)
    obs = make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=board)
    assert rung(pilot.explain(obs).planned) is None


@pytest.mark.req("REQ-PLANNER-0003")
def test_evolve_then_attach_unlocks_an_otherwise_missed_ko_is_planned_and_taken():
    """Evolving carries the attached Energy through, and no hook scores an evolve-unlock."""
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
    """With no KO reachable there is no line, so the Planner defers to the tuned scoring."""
    pilot = _pilot()
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                  opp_active=poke(OPP, hp=330), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[WATER], prizes=2, opp_prizes=2)
    obs = make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=board)
    assert rung(pilot.explain(obs).planned) is None


@pytest.mark.req("REQ-PLANNER-0005")
def test_planner_only_acts_at_the_single_pick_main_menu():
    """A multi-pick MAIN select is a batch context the greedy grab owns, and is left untouched."""
    pilot = _pilot()
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                  opp_active=poke(OPP, hp=180), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[WATER], prizes=2, opp_prizes=2)
    obs = make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=board, max_count=2)
    assert rung(pilot.explain(obs).planned) is None


@pytest.mark.req("REQ-PLANNER-0006")
def test_no_planned_line_when_the_enabling_attach_is_not_available():
    """The Planner must NOT commit a line it cannot execute: with no reusable Energy in hand the
    enabling attach cannot happen."""
    pilot = _pilot()
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                  opp_active=poke(OPP, hp=180), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[], prizes=2, opp_prizes=2)                    # no reusable Energy in hand
    obs = make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=board)
    assert rung(pilot.explain(obs).planned) is None


@pytest.mark.req("REQ-PLANNER-0007")
def test_planned_line_is_emitted_in_decision_telemetry():
    """One `to_record` feeds the stderr line, a Correction's `live_trace` and the tuner retest
    (ADR-0019); the `planned` key is always present so corrections can filter on it."""
    pilot = _pilot()
    won = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                opp_active=poke(OPP, hp=180), opp_bench=[poke(BENCHIE, hp=100)],
                hand=[WATER], prizes=2, opp_prizes=2)
    rec = to_record(pilot.explain(make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=won)))
    assert rec["planned"] == {"step": [0], "goal": "ko_for_prizes",
                              "why": "plan (ko_for_prizes): retreat unlocks a 1-prize KO"}

    # No rung reaches a KO here, so the COMPOSER commits and the record says so, with the margin
    # telemetry Issue #263 requires beside it.
    safe = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                 opp_active=poke(OPP, hp=330), opp_bench=[poke(BENCHIE, hp=100)], hand=[WATER],
                 prizes=2, opp_prizes=2)
    rec_c = to_record(pilot.explain(make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=safe)))
    assert "planned" in rec_c and rec_c["planned"]["goal"] == "compose"
    assert rec_c["planned"]["ranked"] == "composer"
    assert set(rec_c["composer"]["margin"]) >= {"rank", "k", "in_beam", "margin_to_kth"}


# ------------------------------------------------------------------ P2: survival + threat leaf terms
@pytest.mark.req("REQ-PLANNER-0008")
def test_planned_line_value_reflects_post_ko_survival():
    """Prizes still dominate — the KO is committed either way — but the plan's VALUE carries a 1-ply
    survival term over the opponent's Bench (ADR-0031 decision 2)."""
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
    """The prize term DOMINATES every positional term, so survival only breaks ties among equal-prize
    lines and no threat combination can outrank a real prize (ADR-0031 decision 3)."""
    lv = _pilot()._leaf_value
    assert lv(prizes=2, active_survives=False) > lv(prizes=1, active_survives=True)      # more prizes win
    assert lv(prizes=1, active_survives=True) > lv(prizes=1, active_survives=False)       # survival breaks tie
    assert lv(prizes=1, active_survives=False) > lv(prizes=0, active_survives=True, threat_removed=10_000)


# ------------------------------------------ P4: turn-scoped committed-plan cache + re-plan-on-reveal
def _ko_obs(opp_hp=180):
    return make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)],
                       current=state(active=poke(OPENER, energy=1, hp=110),
                                     bench=[poke(WINCON, energy=2, hp=330)], opp_active=poke(OPP, hp=opp_hp),
                                     opp_bench=[poke(BENCHIE, hp=100)], hand=[WATER], prizes=2, opp_prizes=2))


@pytest.mark.req("REQ-PLANNER-0013")
def test_committed_plan_is_cached_as_turn_scoped_state():
    """The ranking runs once per BOARD, not once per decision (ADR-0031 decision 5)."""
    pilot = _pilot()
    obs = _ko_obs()
    line1 = pilot.explain(obs).planned
    assert line1 is not None and pilot._turn_plan is not None   # plan cached as turn state
    assert pilot.explain(obs).planned is line1                  # same board -> cached object reused


@pytest.mark.req("REQ-PLANNER-0014")
def test_plan_is_recomputed_when_the_board_reveals_new_information():
    """A changed board changes the plan fingerprint, so the Planner re-plans rather than returning a
    stale cached line."""
    pilot = _pilot()
    assert pilot.explain(_ko_obs(opp_hp=180)).planned is not None
    assert rung(pilot.explain(_ko_obs(opp_hp=330)).planned) is None   # reveal invalidates cached KO line


@pytest.mark.req("REQ-PLANNER-0015")
def test_no_nested_plan_or_cache_while_simulating():
    """A nested search from inside a search would corrupt the shared engine state, so mid-sim
    `plan_turn` takes the closed-form path only and never writes the turn cache."""
    pilot = _pilot()
    pilot._planning = True
    try:
        d = pilot.explain(_ko_obs())
    finally:
        pilot._planning = False
    assert d.planned is not None and d.planned.next_step == [0]   # closed-form line still returned
    assert pilot._turn_plan is None                                # not cached (mid-sim)


# ------------------------------------------- Supporter-enabled KO line (4298): the tutor supplies the attach
@pytest.mark.req("REQ-PLANNER-0021")
def test_energy_tutor_supporter_unlocks_an_otherwise_missed_ko_is_planned_and_taken():
    """The enabling first step is a SUPPORTER rather than a retreat or evolve, and no single option
    scores it, so the greedy scorer cannot see this line at all."""
    pilot = _pilot(deck=_ENERGY_DECK)
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
    """The line is driven by the ``tutor_energy`` TAG, never by a card id, so it fires for any
    deck-search-Energy Trainer carrying it."""
    energy_search = _ENERGY_SEARCH                     # tutor_energy sibling (Item) — not Hilda
    pilot = _pilot(functions=CardFunctions({energy_search: ["search", "tutor_energy"]}),
                   deck=_ENERGY_DECK)
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=0, hp=330)],
                  opp_active=poke(BENCHIE, hp=100), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[energy_search], prizes=2, opp_prizes=2)   # no Energy in hand — tutor fetches it
    obs = make_select([opt(PLAY, area=HAND, index=0), attack_opt(OPEN_ATK), opt(END)], current=board)

    d = pilot.explain(obs)
    assert d.planned is not None and d.planned.goal == "ko_for_prizes"
    assert d.planned.next_step == [0]                  # play the (non-Hilda) energy tutor
    assert pilot.decide(obs) == [0]


# --------------------------------------------- the KO-the-key-threat rung (ADR-0031 ladder, item 2b)
SNIPE = 15      # attack id: cost 1, 50 to the Active + a 100 bench-snipe rider
THREATB = 702   # opponent's benched KEY threat: a 340-damage glass cannon at 90 HP (snipe-KO-able)


def _snipe_stats():
    base = {
        WINCON: CardStat(WINCON, synthetic=True, name="Mega Starmie ex", hp=330, energyType=3, minAttackCost=1,
                         minCostDamage=50, maxDamage=210, maxDamageCost=3,
                         attacks=(JETTING, NEBULA, SNIPE), evolvesFrom="Staryu", megaEx=True),
        OPENER: CardStat(OPENER, synthetic=True, name="opener", hp=110, energyType=3, minAttackCost=1,
                         minCostDamage=30, maxDamage=30, attacks=(OPEN_ATK,)),
        OPP: CardStat(OPP, synthetic=True, name="opp active", hp=330, energyType=7),
        BENCHIE: CardStat(BENCHIE, synthetic=True, name="opp benchie", hp=100, energyType=7),
        THREATB: CardStat(THREATB, synthetic=True, name="benched glass cannon", hp=90, energyType=7,
                          minAttackCost=1, minCostDamage=340, maxDamage=340),
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, cardType=5, energyType=3),  # 5 = Basic
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
    """A snipe-KO ON the menu is the Tactical layer's turf; the RETREAT that reaches one is scored by
    no hook, which is the rung's gap."""
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                  opp_active=poke(OPP, hp=330),
                  opp_bench=[poke(THREATB, energy=1, hp=90), poke(BENCHIE, hp=100)],
                  hand=[WATER], prizes=3, opp_prizes=3)
    return make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=board)


@pytest.mark.req("REQ-PLANNER-0031")
def test_key_threat_rung_commits_the_retreat_that_unlocks_the_threat_snipe():
    """The KO-for-prizes generators test the opponent's ACTIVE only, so a benched-threat line is
    otherwise invisible. `planner_key_threat` defaults OFF."""
    on = _snipe_pilot(planner_key_threat=True)
    d = on.explain(_key_threat_obs())
    assert d.planned is not None and d.planned.goal == "ko_key_threat"
    assert d.planned.next_step == [0]                  # the enabling retreat
    assert on.decide(_key_threat_obs()) == [0]

    off = _snipe_pilot()
    assert rung(off.explain(_key_threat_obs()).planned) is None   # default OFF: no rung fires


@pytest.mark.req("REQ-PLANNER-0031")
def test_key_threat_rung_counts_a_forward_damage_only_threat():
    """The top threat is RANKED by max(own, forward) damage, so the magnitude gate must use the same
    basis or a 0-printed base with a monster evolution is silently skipped."""
    DREEPY, DRAGA = 704, 705
    stats = _snipe_stats()
    stats._stats[DREEPY] = CardStat(DREEPY, synthetic=True, name="Dreepy", hp=60, energyType=7, maxDamage=0)
    stats._stats[DRAGA] = CardStat(DRAGA, synthetic=True, name="Dragapult ex", hp=320, energyType=7,
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
    """A KO already on the menu stands the rung down, and nothing benched that actually THREATENS
    keeps it silent — it never snipes a non-threat just because it can."""
    pilot = _snipe_pilot(planner_key_threat=True)
    ko_on_menu = state(active=poke(WINCON, energy=3, hp=330), opp_active=poke(OPP, hp=120),
                       opp_bench=[poke(THREATB, energy=1, hp=90)], prizes=3, opp_prizes=3)
    d = pilot.explain(make_select([attack_opt(SNIPE), attack_opt(JETTING), opt(END)], current=ko_on_menu))
    assert rung(d.planned) is None                           # the KO on the menu owns the turn

    FATB = 703                                         # a harmless fat benched body (no threat rank)
    stats = _snipe_stats()
    stats._stats[FATB] = CardStat(FATB, synthetic=True, name="fat benchie", hp=150, energyType=7)
    pilot2 = _snipe_pilot(planner_key_threat=True)
    pilot2.stats = stats
    no_threat = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=2, hp=330)],
                      opp_active=poke(OPP, hp=330), opp_bench=[poke(FATB, hp=150)],
                      hand=[WATER], prizes=3, opp_prizes=3)
    d2 = pilot2.explain(make_select([opt(RETREAT), attack_opt(OPEN_ATK), opt(END)], current=no_threat))
    assert rung(d2.planned) is None                          # nothing benched threatens -> no rung


# Driven through the injectable `_search_api` seam so this stays lib-free: a bare `import cg.api`
# maps the native library (ADR-0072 amendment B).

@dataclass
class _FakeLog:
    type: int
    playerIndex: int | None = None
    fromArea: int | None = None
    toArea: int | None = None


@dataclass
class _FakeCurrent:
    turn: int = 3
    yourIndex: int = 0
    result: int = -1
    players: list = field(default_factory=list)


@dataclass
class _FakeObservation:
    current: _FakeCurrent | None = None
    select: dict | None = None          # None -> the sim stops after one step (my turn passed)
    logs: list = field(default_factory=list)


@dataclass
class _FakeState:
    searchId: int
    observation: _FakeObservation


class _FakeSearchApi:
    """A `cg.api`-shaped surface that replays ONE canned log list, with the real enum values."""

    class LogType:
        SHUFFLE, DRAW, DRAW_REVERSE, MOVE_CARD, COIN = 0, 4, 5, 6, 22

    class AreaType:
        DECK, HAND, DISCARD, BENCH, PRIZE, LOOKING = 1, 2, 3, 5, 6, 12

    def __init__(self, logs):
        self._logs = logs

    def to_observation_class(self, obs):
        return obs

    def search_begin(self, *a, **kw):
        return _FakeState(1, _FakeObservation(current=_FakeCurrent(), select={}))

    def search_step(self, search_id, select):
        return _FakeState(1, _FakeObservation(current=_FakeCurrent(yourIndex=1), logs=self._logs))

    def search_end(self):
        return None


L = _FakeSearchApi.LogType
A = _FakeSearchApi.AreaType


@pytest.mark.req("REQ-PLANNER-0037")
def test_the_verdict_probe_ignores_a_prize_take_the_board_probe_counts():
    """A face-down prize's id is our own prediction, so revealing it can change a resulting BOARD but
    not a WIN VERDICT, which is invariant to which prize is taken (ADR-0050)."""
    from common.strategy.planner import _rng_probe

    take = _FakeObservation(logs=[_FakeLog(L.MOVE_CARD, playerIndex=0,
                                           fromArea=A.PRIZE, toArea=A.HAND)])
    draw = _FakeObservation(logs=[_FakeLog(L.DRAW, playerIndex=0)])
    api = _FakeSearchApi([])
    assert _rng_probe(api, 0, prize=True)(take) is True      # the board question
    assert _rng_probe(api, 0, prize=False)(take) is False    # the verdict question
    assert _rng_probe(api, 0, prize=False)(draw) is True     # a DRAW demotes either way


# ------------------------------------------- the evolution-tutor line (Salvatore, corpus a212 shape)
SALV = 1189     # Salvatore — Supporter that evolves an in-play Pokémon straight from the deck
ABIL = 902      # an ability-bearing evolution (Salvatore's own filter excludes it)


def _salvatore_pilot(deck=None, stats=None, **kw):
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]})
    fns = CardFunctions({SALV: ["search", "rush_evolve"]})
    return Pilot(strat, deck=deck or ([WINCON] * 3 + [1] * 57), general_strategy=GENERAL_STRATEGY,
                 stats=stats or _stats(), functions=fns, **kw)


def _salvatore_obs(options=None, *, anchored=False):
    """Salvatore evolves the benched pre-evolution straight from the deck; the retreat + attach then
    bring the attacker online against their last body. ``anchored=True`` sets `own_prizes`."""
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
    """ANCHORED, the evolution is PROVABLY still in the deck, so the line is a guaranteed win."""
    pilot = _salvatore_pilot(lethal_family=True)
    obs = _salvatore_obs(anchored=True)
    d = pilot.explain(obs)
    assert d.planned is not None and d.planned.goal == "win"
    assert d.planned.next_step == [0]                  # play Salvatore now
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-PLANNER-0035")
def test_evolution_tutor_win_needs_positive_deck_certainty():
    """Unanchored, the evolution could be PRIZED, so the heuristic rung may still rank-commit the
    line but the win rung must never lock it."""
    pilot = _salvatore_pilot(lethal_family=True)
    d = pilot.explain(_salvatore_obs())
    assert rung(d.planned) is None or d.planned.goal != "win"


@pytest.mark.req("REQ-PLANNER-0035")
def test_evolution_tutor_excludes_ability_bearing_evolutions():
    """Salvatore's own filter fetches only a card with NO Abilities, and neither rung may plan on an
    ineligible fetch."""
    stats = _stats()
    stats._stats[ABIL] = CardStat(ABIL, synthetic=True, name="Abil Starmie ex", hp=330, energyType=3,
                                  minAttackCost=1, minCostDamage=120, maxDamage=120,
                                  attacks=(JETTING,), evolvesFrom="Staryu", hasAbility=True)
    pilot = _salvatore_pilot(deck=[ABIL] * 3 + [1] * 57, stats=stats, lethal_family=True)
    obs = _salvatore_obs(anchored=True)
    assert rung(pilot.explain(obs).planned) is None


@pytest.mark.req("REQ-PLANNER-0035")
def test_evolution_tutor_benched_target_needs_the_retreat_on_the_menu():
    """The attacker evolves on the BENCH, so with no retreat offered the line cannot execute."""
    pilot = _salvatore_pilot(lethal_family=True)
    obs = _salvatore_obs(options=[opt(PLAY, area=HAND, index=0), opt(END)], anchored=True)
    assert rung(pilot.explain(obs).planned) is None


@pytest.mark.req("REQ-PLANNER-0035")
def test_evolution_tutor_heuristic_commits_the_ko_line_without_certainty():
    """Tracker cold: majority-LIKELY (deck odds) is enough for the rank-grade KO-for-prizes rung,
    though not for a win lock."""
    pilot = _salvatore_pilot()
    obs = _salvatore_obs()
    d = pilot.explain(obs)
    assert d.planned is not None and d.planned.goal == "ko_for_prizes"
    assert "evolution tutor" in d.planned.rationale
    assert d.planned.next_step == [0]
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-PLANNER-0022")
def test_energy_tutor_stands_down_when_the_turns_attach_is_already_spent():
    """The line only works because the fetched Energy can be attached THIS turn, so a spent
    `energyAttached` quota makes the KO unreachable and the Planner must not commit."""
    pilot = _pilot()
    board = state(active=poke(OPENER, energy=1, hp=110), bench=[poke(WINCON, energy=0, hp=330)],
                  opp_active=poke(BENCHIE, hp=100), opp_bench=[poke(BENCHIE, hp=100)],
                  hand=[HILDA], prizes=2, opp_prizes=2)
    board["energyAttached"] = True                     # this turn's one Energy attach already spent
    obs = make_select([opt(PLAY, area=HAND, index=0), attack_opt(OPEN_ATK), opt(END)], current=board)
    assert rung(pilot.explain(obs).planned) is None
