"""M2.0 — wire the Read onto the Board (Posture-OFF).

The Pilot senses the opponent via an injected Scout and surfaces the Read on its public
`explain()` output, without changing any decision yet (nothing scores off it — that's M2.1b).
See ADR-0026 (the wiring staircase) and docs/scouting.md (the Read).
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Board, Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.scouting.briefs import Brief
from common.scouting.read import EvoPath, Read
from common.scouting.scout import Scout
from common.strategy import Line, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import BENCH, DAMAGE, SWITCH, card_opt, make_select, poke, state
from scouting_helpers import GARDEVOIR, KIRLIA, MEGA_LUCARIO, RIOLU, SHARED, SOLROCK, tiny_artifact

MAIN, PLAY = 0, 7
MEGA, STARYU = 1031, 1030


def _stats():
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True,
                       minAttackCost=1, minCostDamage=120, attacks=(11,), evolvesFrom="Staryu"),
    })


def _pilot(scout=None, my_archetype=None, briefs=None, posture=True):
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition", "primary_attacker"]},
                     params={"my_archetype": my_archetype} if my_archetype else {})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 attacks={11: 120}, attack_costs={11: 1}, scout=scout, briefs=briefs, posture=posture)


def _obs_facing_mega_lucario():
    """A MAIN-phase menu where the opponent's board reveals the Mega Lucario ex line."""
    me = {"active": [{"id": MEGA, "energies": [1], "hp": 330}], "bench": [],
          "hand": [{"id": 1}], "discard": [], "prize": []}
    opp = {"active": [{"id": MEGA_LUCARIO, "energies": [], "hp": 0}],
           "bench": [{"id": SOLROCK, "energies": []}, {"id": RIOLU, "energies": []}],
           "discard": [], "prize": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 4},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None},
            "logs": []}


def _obs_two_option_menu():
    """A 2-option MAIN menu vs the recognized Mega Lucario ex board (ordering can matter)."""
    obs = _obs_facing_mega_lucario()
    obs["current"]["players"][0]["hand"] = [{"id": 1}, {"id": 2}]
    obs["select"]["option"] = [{"type": PLAY, "index": 0}, {"type": PLAY, "index": 1}]
    return obs


@pytest.mark.req("REQ-POSTURE-0001")
def test_explain_surfaces_the_recognized_archetype():
    # Pilot senses via the Scout, exposes the Read on its public explain() output
    decision = _pilot(scout=Scout(tiny_artifact())).explain(_obs_facing_mega_lucario())
    assert decision.read is not None
    assert decision.read.candidates[0][0] == "Mega Lucario ex"


@pytest.mark.req("REQ-POSTURE-0001")
def test_wiring_a_scout_changes_no_decision_or_score():
    # M2.0 is Posture-OFF: Read rides on the Board, nothing scores off it yet. A wired Scout
    # (even confidently recognizing the opponent) must produce byte-identical choices AND scores
    obs = _obs_two_option_menu()
    off, on = _pilot(scout=None), _pilot(scout=Scout(tiny_artifact()))
    assert on.decide(obs) == off.decide(obs)
    assert [o.score for o in on.explain(obs).options] == [o.score for o in off.explain(obs).options]


def _obs_early_unknown():
    """Early game: the opponent has revealed nothing diagnostic (empty board)."""
    me = {"active": [{"id": MEGA, "energies": [1], "hp": 330}], "bench": [],
          "hand": [{"id": 1}], "discard": [], "prize": []}
    opp = {"active": [], "bench": [], "discard": [], "prize": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 1},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None},
            "logs": []}


@pytest.mark.req("REQ-POSTURE-0001")
def test_unrecognized_opponent_yields_low_confidence_read():
    # Unknown/off-meta opponent: Read stays below the recognition bar -> Posture (which will
    # γ-gate on confidence in M2.1b) off by construction. Pilot never crashes (Read never raises)
    decision = _pilot(scout=Scout(tiny_artifact())).explain(_obs_early_unknown())
    assert decision.read is not None
    assert decision.read.confidence[0] < 0.6     # below Scout's recognition threshold -> Posture off


# ---- M2.1b Slice 1: Read-derived Board signals (γ + favorability), behavior-neutral ----

def _board_of(pilot, obs):
    return pilot._board(obs, obs["select"])


@pytest.mark.req("REQ-POSTURE-0002")
def test_posture_confidence_ramps_high_when_recognized():
    # A confidently-recognized opponent yields a high posture-confidence gamma on the Board — the
    # continuous scaling knob the M2.1b levers ride (ADR-0026).
    board = _board_of(_pilot(scout=Scout(tiny_artifact())), _obs_facing_mega_lucario())
    assert board.posture_confidence > 0.5


@pytest.mark.req("REQ-POSTURE-0002")
def test_posture_confidence_is_zero_when_unknown_or_no_scout():
    # Unrecognized opponent (or no Scout wired) -> γ = 0, levers contribute nothing
    # (no regression vs unknown opponent is structural, ADR-0026)
    assert _board_of(_pilot(scout=Scout(tiny_artifact())), _obs_early_unknown()).posture_confidence == 0.0
    assert _board_of(_pilot(scout=None), _obs_facing_mega_lucario()).posture_confidence == 0.0


@pytest.mark.req("REQ-POSTURE-0002")
def test_favorability_reflects_the_matchup_table():
    # With my_archetype declared + a compiled matchup cell vs the recognized opponent, Board
    # carries that favorability (lever-A signal); coverage says how much posterior backs it
    art = tiny_artifact()
    art.dossiers["Cinderace / Mega Starmie ex"] = {
        "matchups": {"Mega Lucario ex": {"win_rate": 0.7, "n": 20.0}}}
    board = _board_of(_pilot(scout=Scout(art), my_archetype="Cinderace / Mega Starmie ex"),
                      _obs_facing_mega_lucario())
    assert board.favorability > 0.6        # the 0.7 matchup cell dominates the posterior
    assert board.matchup_coverage > 0.9    # nearly all posterior mass lands on a real cell


@pytest.mark.req("REQ-POSTURE-0002")
def test_favorability_defaults_neutral_without_my_archetype():
    # No my_archetype declared -> neutral favorability, zero coverage (lever A off, safe default)
    board = _board_of(_pilot(scout=Scout(tiny_artifact())), _obs_facing_mega_lucario())
    assert board.favorability == 0.5 and board.matchup_coverage == 0.0


# ---- M2.1b Slice 2: lever C (accurate-dev) — Read-modulated forward-evolution snipe rank ----

SNIPER = 700


def _snipe_pilot(stats):
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 attacks={11: 120}, bench_snipe={11: 50})


@pytest.mark.req("REQ-POSTURE-0003")
def test_lever_c_suppresses_a_denied_evolving_threats_forward_rank():
    # Benched Riolu's generic threat rank is its forward-evolution damage (Mega Lucario ex 270). When
    # Read CONFIRMS that line (on an evolution_path) rank is unchanged; when a recognized
    # archetype runs NO such line, lever C suppresses the forward signal (γ-scaled); unknown -> generic
    stats = DictCardStatProvider({
        SNIPER: CardStat(SNIPER, name="Sniper", maxDamage=120, attacks=(11,)),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=70, maxDamage=0),
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=220, megaEx=True,
                               maxDamage=270, evolvesFrom="Riolu"),
    })
    pilot = _snipe_pilot(stats)
    obs = make_select([card_opt(BENCH, 0, player=1)], context=15,
                      current=state(active=poke(SNIPER), opp_bench=[poke(RIOLU, hp=70)]))
    opt, select = obs["select"]["option"][0], obs["select"]

    generic = pilot._target_threat_rank(obs, select, opt, read=None, gamma=0.0)
    assert generic >= 270                                  # forward to Mega Lucario ex (M0 generic signal)
    confirmed = Read(candidates=[("ML", 0.9)], confidence=(0.9, 0.5), unknown_mass=0.0,
                     evolution_paths=[EvoPath(RIOLU, [RIOLU, MEGA_LUCARIO], MEGA_LUCARIO)])
    denied = Read(candidates=[("G", 0.9)], confidence=(0.9, 0.5), unknown_mass=0.0)
    assert pilot._target_threat_rank(obs, select, opt, read=confirmed, gamma=1.0) == generic   # confirmed
    assert pilot._target_threat_rank(obs, select, opt, read=denied, gamma=1.0) < generic        # denied -> suppressed


# ---- M2.1b Slice 3: lever A (favorability) — up-weight useful disruption when unfavored ----

HAMMER = 555


def _unfavored_pilot(win_rate, funcs):
    art = tiny_artifact()
    art.dossiers["MyDeck"] = {"matchups": {"Mega Lucario ex": {"win_rate": win_rate, "n": 30.0}}}
    # Mega Lucario ex with an affordable attack (Aura Jab {F} 130) so `opp_active_can_damage_us` sees a
    # real threat at its 1 Energy — the energy-denial gate needs the opp to be able to hurt us, and an
    # empty stat provider would mask that (2026-07-09).
    stats = DictCardStatProvider({
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=340, megaEx=True, attacks=(11,)),
    })
    return Pilot(Strategy(params={"my_archetype": "MyDeck"}), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=funcs, attacks={11: 130}, attack_costs={11: 1}, scout=Scout(art))


def _obs_hammer_vs_energized_mega_lucario():
    me = {"active": [{"id": 1, "energies": [], "hp": 100}], "bench": [],
          "hand": [{"id": HAMMER}], "discard": [], "prize": []}
    opp = {"active": [{"id": MEGA_LUCARIO, "energies": [1], "hp": 200}],
           "bench": [{"id": SOLROCK}, {"id": RIOLU}], "discard": [], "prize": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 4},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None}, "logs": []}


@pytest.mark.req("REQ-POSTURE-0004")
def test_lever_a_boosts_useful_disruption_when_unfavored():
    # Recognized Mega Lucario ex, an UNFAVORABLE matchup (win-rate 0.3) -> up-weight the useful energy
    # denial (opp Active carries Energy to strip). Stands down at an EVEN matchup (favorability 0.5)
    funcs = CardFunctions({HAMMER: ["energy_denial"]})
    obs = _obs_hammer_vs_energized_mega_lucario()
    unfavored = {h.id for h, _ in _unfavored_pilot(0.3, funcs).explain(obs).options[0].fired}
    even = {h.id for h, _ in _unfavored_pilot(0.5, funcs).explain(obs).options[0].fired}
    assert "disrupt-when-unfavored" in unfavored
    assert "disrupt-when-unfavored" not in even


# ---- M2 lever A, favored half: don't gift the losing opponent a fresh hand (ADR-0026 amendment) ----

JUDGE_SUP = 1213


def _obs_judge_vs_mega_lucario():
    """A symmetric refresh (Judge) as the only play, facing a recognized Mega Lucario ex. Pre-anchor
    (no own_prizes), so the Layer-B post-anchor veto stays out of frame — the lever-A rung is
    isolated."""
    me = {"active": [{"id": 1, "energies": [1], "hp": 100}], "bench": [{"id": 2}],
          "hand": [{"id": JUDGE_SUP}], "discard": [], "prize": []}
    opp = {"active": [{"id": MEGA_LUCARIO, "energies": [1], "hp": 200}],
           "bench": [{"id": SOLROCK}, {"id": RIOLU}], "discard": [], "prize": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 4},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None}, "logs": []}


def _favored_pilot(win_rate, funcs):
    """`_unfavored_pilot` with a deck of startable Basics (id 77) — a realistic pull pool for the
    refresh play under test."""
    art = tiny_artifact()
    art.dossiers["MyDeck"] = {"matchups": {"Mega Lucario ex": {"win_rate": win_rate, "n": 30.0}}}
    return Pilot(Strategy(params={"my_archetype": "MyDeck"}), deck=[77] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=DictCardStatProvider({77: CardStat(77, hp=70)}),
                 functions=funcs, attacks={}, scout=Scout(art))


@pytest.mark.req("REQ-POSTURE-0006")
def test_favored_half_downweights_the_symmetric_refresh_gift():
    """Lever A's favored half (ADR-0026 amendment): favorability ≥ 0.55 fires
    `dont-gift-a-refresh-when-favored` on a `hand_disruption` play (refilling a losing opponent's
    hand gifts outs); the rung stays silent at even AND at unfavored (structural exclusion with the
    shipped half)."""
    funcs = CardFunctions({JUDGE_SUP: ["draw", "hand_disruption", "shuffle_hand"]})
    obs = _obs_judge_vs_mega_lucario()
    favored = {h.id for h, _ in _favored_pilot(0.7, funcs).explain(obs).options[0].fired}
    even = {h.id for h, _ in _favored_pilot(0.5, funcs).explain(obs).options[0].fired}
    unfavored = {h.id for h, _ in _favored_pilot(0.3, funcs).explain(obs).options[0].fired}
    assert "dont-gift-a-refresh-when-favored" in favored
    assert "dont-gift-a-refresh-when-favored" not in even
    assert "dont-gift-a-refresh-when-favored" not in unfavored


@pytest.mark.req("REQ-POSTURE-0006")
def test_favored_half_never_kills_genuinely_triggered_disruption():
    """Favored + the opponent runs a hand-size attacker: the targeted disruption endorsement (+25)
    outweighs the gift rung (−15) — favored kills the gift, not the counterplay."""
    HSATK = 4321
    funcs = CardFunctions({JUDGE_SUP: ["draw", "hand_disruption", "shuffle_hand"],
                           HSATK: ["hand_size_attacker"]})
    obs = _obs_judge_vs_mega_lucario()
    obs["current"]["players"][1]["bench"].append({"id": HSATK})   # benched; ML stays recognized
    trace = _favored_pilot(0.7, funcs).explain(obs).options[0]
    fired = {h.id for h, _ in trace.fired}
    assert "dont-gift-a-refresh-when-favored" in fired
    assert "play-harlequin-vs-hand-size" in fired
    assert trace.score > 0                                 # still played as targeted disruption


# ---- Brief-consumer wiring: the matched Matchup Brief on the Board (ADR-0027), behavior-neutral ----

@pytest.mark.req("REQ-POSTURE-0005")
def test_recognized_opponent_routes_its_matchup_brief_onto_board():
    # A Brief whose `covers` includes the recognized archetype is surfaced on board.brief (variant routing)
    brief = Brief(slug="ml", label="Mega Lucario ex", covers=["Mega Lucario ex"])
    board = _board_of(_pilot(scout=Scout(tiny_artifact()), briefs=[brief]), _obs_facing_mega_lucario())
    assert board.brief is not None and board.brief.slug == "ml"


@pytest.mark.req("REQ-POSTURE-0005")
def test_no_brief_on_board_when_unknown_unmatched_or_posture_off():
    brief = Brief(slug="ml", label="Mega Lucario ex", covers=["Mega Lucario ex"])
    other = Brief(slug="x", label="X", covers=["Some Other Deck"])
    ml = _obs_facing_mega_lucario()
    assert _board_of(_pilot(scout=Scout(tiny_artifact()), briefs=[brief]), _obs_early_unknown()).brief is None
    assert _board_of(_pilot(scout=Scout(tiny_artifact()), briefs=[other]), ml).brief is None   # no cover
    assert _board_of(_pilot(scout=None, briefs=[brief]), ml).brief is None                      # no Scout
    assert _board_of(_pilot(scout=Scout(tiny_artifact()), briefs=[brief], posture=False), ml).brief is None


# ---- Brief-consumer surface: opponent_properties readable off the Board (ADR-0027) ----

@pytest.mark.req("REQ-POSTURE-0005")
def test_opp_property_reads_a_brief_asserted_lever():
    # Surface A: the matched Brief's opponent_properties are readable off the Board by key.
    board = Board(brief=Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                              opponent_properties={"opp_tempo": "midrange"}))
    assert board.opp_property("opp_tempo") == "midrange"


@pytest.mark.req("REQ-POSTURE-0005")
def test_opp_property_omitted_key_returns_default():
    # Assert-true-only Briefs omit their FALSE levers; an omitted key reads as its default.
    board = Board(brief=Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                              opponent_properties={"opp_tempo": "midrange"}))
    assert board.opp_property("opp_is_engine_dependent", False) is False
    assert board.opp_property("opp_donk_vulnerable", False) is False


@pytest.mark.req("REQ-POSTURE-0005")
def test_opp_property_safe_when_no_brief():
    # No matched Brief (unrecognized opponent / Posture off) -> default, never raises.
    assert Board().opp_property("opp_tempo") is None
    assert Board().opp_property("opp_tempo", "x") == "x"


# ---- ADR-0051: the MatchupPlan target-priority spine, built onto the Board ----

def _mp_pilot(matchup_targeting=True, posture=True):
    prov = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True,
                       minAttackCost=1, minCostDamage=120, attacks=(11,), evolvesFrom="Staryu"),
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=280, megaEx=True),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=70),
        SOLROCK: CardStat(SOLROCK, name="Solrock", hp=90, maxDamage=30),
    })
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition"]}, params={})
    brief = Brief(slug="ml", label="Mega Lucario ex", covers=["Mega Lucario ex"],
                  targets=[{"card": "Riolu", "role": "fragile_preevo", "why": ""}])
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=prov,
                 functions=CardFunctions({SOLROCK: ["draw"]}),
                 attacks={11: 120}, attack_costs={11: 1},
                 scout=Scout(tiny_artifact()), briefs=[brief],
                 posture=posture, matchup_targeting=matchup_targeting)


@pytest.mark.req("REQ-POSTURE-0006")
def test_board_carries_a_matchup_plan_from_brief_and_general_tiers():
    # A recognized opponent composes the spine onto the Board: the Brief names Riolu a
    # fragile_preevo (positive target), and Solrock's general `draw`-engine card fact
    # de-prioritizes it (avoid) with no Brief entry needed.
    board = _board_of(_mp_pilot(), _obs_facing_mega_lucario())
    assert board.matchup_plan.priority(RIOLU) > 0
    assert board.matchup_plan.priority(SOLROCK) < 0


@pytest.mark.req("REQ-POSTURE-0006")
def test_matchup_plan_is_inert_when_the_kill_switch_is_off():
    # matchup_targeting=False -> an empty plan, every priority 0 (clean A/B off-switch).
    board = _board_of(_mp_pilot(matchup_targeting=False), _obs_facing_mega_lucario())
    assert board.matchup_plan.priority(RIOLU) == 0.0
    assert board.matchup_plan.priority(SOLROCK) == 0.0


# ---- ADR-0051 consumption: the snipe pick reads the MatchupPlan ----

SNIPER = 700


def _mp_snipe_pilot(matchup_targeting=True):
    prov = DictCardStatProvider({
        SNIPER: CardStat(SNIPER, name="Sniper", maxDamage=120, attacks=(11,)),
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=280, megaEx=True,
                               maxDamage=270, evolvesFrom="Riolu"),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=70, maxDamage=0),
        SOLROCK: CardStat(SOLROCK, name="Solrock", hp=90, maxDamage=30),
    })
    brief = Brief(slug="ml", label="Mega Lucario ex", covers=["Mega Lucario ex"],
                  targets=[{"card": "Riolu", "role": "fragile_preevo", "why": ""}])
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=prov,
                 functions=CardFunctions({SOLROCK: ["draw"]}),
                 attacks={11: 120}, bench_snipe={11: 50},
                 scout=Scout(tiny_artifact()), briefs=[brief],
                 posture=True, matchup_targeting=matchup_targeting)


def _damage_select_over_ml_bench():
    # A bench-snipe (DAMAGE) select vs the recognized Mega Lucario ex board. Rider 50 KOs neither
    # bench body (Solrock 90 / Riolu 70) -> no snipe-KO, so the positional/matchup steer decides.
    cur = state(active=poke(SNIPER), opp_active=poke(MEGA_LUCARIO, hp=280),
                opp_bench=[poke(SOLROCK, hp=90, max_hp=90), poke(RIOLU, hp=70, max_hp=70)], turn=4)
    return make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
                       context=DAMAGE, current=cur)


@pytest.mark.req("REQ-POSTURE-0006")
def test_snipe_shuns_the_draw_engine_and_prefers_the_brief_target():
    dec = _mp_snipe_pilot().explain(_damage_select_over_ml_bench())
    # Solrock's general draw-engine fact -> negative matchup contribution; Riolu (Brief
    # fragile_preevo) -> positive. The pick lands on the wincon line, not the engine.
    assert dec.options[1].tactical > 0 > dec.options[0].tactical
    assert dec.chosen == [1]


@pytest.mark.req("REQ-POSTURE-0006")
def test_snipe_matchup_term_silent_under_kill_switch():
    dec = _mp_snipe_pilot(matchup_targeting=False).explain(_damage_select_over_ml_bench())
    assert dec.options[0].tactical == 0.0 and dec.options[1].tactical == 0.0


@pytest.mark.req("REQ-POSTURE-0005")
def test_brief_target_and_threat_accessors_read_resolved_ids():
    # Surface B: the Brief's threats/targets, resolved to ids, are queryable off the Board by id/role.
    board = Board(brief_threat_ids=frozenset({MEGA_LUCARIO}),
                  brief_target_roles={RIOLU: "fragile_preevo", SOLROCK: "engine"})
    assert board.brief_target_role(RIOLU) == "fragile_preevo"
    assert board.brief_target_role(999) is None
    assert board.brief_is_threat(MEGA_LUCARIO) is True
    assert board.brief_is_threat(999) is False
    assert board.brief_target_ids("engine") == frozenset({SOLROCK})
    assert board.brief_target_ids() == frozenset({RIOLU, SOLROCK})


@pytest.mark.req("REQ-POSTURE-0005")
def test_brief_accessors_safe_when_no_brief():
    # No resolved Brief cards -> every accessor returns an empty/None default, never raises.
    board = Board()
    assert board.brief_target_role(RIOLU) is None
    assert board.brief_is_threat(RIOLU) is False
    assert board.brief_target_ids() == frozenset()
    assert board.brief_target_ids("engine") == frozenset()


def _ml_stats():
    """A provider that knows the Mega Lucario ex line by name (so the Brief's cards resolve to ids)."""
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True,
                       minAttackCost=1, minCostDamage=120, attacks=(11,), evolvesFrom="Staryu"),
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=340, megaEx=True),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=80, evolvesFrom=None),
        SOLROCK: CardStat(SOLROCK, name="Solrock", hp=110),
    })


def _ml_brief_full():
    return Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                 opponent_properties={"opp_tempo": "midrange"},
                 threats=[{"card": "Mega Lucario ex", "why": "270"}],
                 targets=[{"card": "Riolu", "role": "fragile_preevo", "why": "snipe"},
                          {"card": "Solrock", "role": "engine", "why": "draw"}])


def _ml_pilot(briefs):
    """A posture Pilot that recognizes Mega Lucario ex and knows its line by name (so a matched
    Brief's threats/targets resolve to ids)."""
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition", "primary_attacker"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_ml_stats(),
                 attacks={11: 120}, attack_costs={11: 1}, scout=Scout(tiny_artifact()),
                 briefs=briefs, posture=True)


@pytest.mark.req("REQ-POSTURE-0005")
def test_board_resolves_the_matched_briefs_threats_and_targets_to_ids():
    # End-to-end wiring: a recognized opponent -> _board() resolves the matched Brief's name-keyed
    # threats/targets to ids via the provider, so the Board's brief_* accessors answer by id.
    board = _board_of(_ml_pilot([_ml_brief_full()]), _obs_facing_mega_lucario())
    assert board.brief is not None                                 # recognized -> Brief on the Board
    assert board.opp_property("opp_tempo") == "midrange"
    assert board.brief_target_role(RIOLU) == "fragile_preevo"      # resolved from brief.targets
    assert board.brief_target_role(SOLROCK) == "engine"
    assert board.brief_is_threat(MEGA_LUCARIO) is True             # resolved from brief.threats


@pytest.mark.req("REQ-POSTURE-0005")
def test_resolving_the_brief_changes_no_decision_or_score():
    # Kill-switch-OFF neutrality (ADR-0038): the Pilot ctor defaults brief_preevo/brief_engine False,
    # so a resolved Brief on the Board must yield byte-identical choices AND scores vs a Pilot with
    # no Brief — the levers move play only when an agent's main.py opts in.
    obs = _obs_two_option_menu()
    on, off = _ml_pilot([_ml_brief_full()]), _ml_pilot(None)
    assert on.decide(obs) == off.decide(obs)
    assert [o.score for o in on.explain(obs).options] == [o.score for o in off.explain(obs).options]


# ---- ADR-0038 Brief levers: Brief intel sharpens the owning Tactical signal (γ-scaled) ----

BRUISER = 720   # a plain 120-damage attacker body (the energized competitor in rank tests)


def _lever_stats():
    """Provider for the ADR-0038 lever tests: the Mega Lucario line (Riolu's forward-evo damage =
    270), the Solrock engine body, a Gardevoir line (a NON-briefed evolving pre-evolution, for
    denial parity in gust tests) and a plain bruiser."""
    return DictCardStatProvider({
        SNIPER: CardStat(SNIPER, name="Sniper", hp=200, maxDamage=120, minAttackCost=1,
                         minCostDamage=120, attacks=(11,)),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=80, maxDamage=0),
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=340, megaEx=True,
                               maxDamage=270, evolvesFrom="Riolu"),
        SOLROCK: CardStat(SOLROCK, name="Solrock", hp=110, maxDamage=70),
        KIRLIA: CardStat(KIRLIA, name="Kirlia", hp=80, maxDamage=0),
        GARDEVOIR: CardStat(GARDEVOIR, name="Gardevoir ex", hp=310, maxDamage=190,
                            evolvesFrom="Kirlia"),
        BRUISER: CardStat(BRUISER, name="Bruiser", hp=120, maxDamage=120),
    })


def _lever_pilot(**kw):
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_lever_stats(), attacks={11: 120}, attack_costs={11: 1}, **kw)


def _rank_obs(*bench):
    obs = make_select([card_opt(BENCH, i, player=1) for i in range(len(bench))], context=DAMAGE,
                      current=state(active=poke(SNIPER), opp_bench=list(bench)))
    return obs, obs["select"]


@pytest.mark.req("REQ-POSTURE-0007")
def test_briefed_preevo_overtakes_an_energized_attacker_at_full_gamma():
    # The tier-crossing preevo boost (ADR-0038): a bare briefed pre-evolution (Riolu) outranks an
    # ENERGIZED attacker once γ is high — authored payoff-denial beats the generic imminence tier.
    pilot = _lever_pilot(brief_preevo=True)
    obs, select = _rank_obs(poke(RIOLU, hp=80), poke(BRUISER, energy=2, hp=120))
    roles = {RIOLU: "fragile_preevo"}
    riolu = pilot._target_threat_rank(obs, select, select["option"][0], gamma=1.0, brief_roles=roles)
    energized = pilot._target_threat_rank(obs, select, select["option"][1], gamma=1.0, brief_roles=roles)
    assert riolu > energized
    # baseline sanity: without the Brief the energized body owns the tier
    base_r = pilot._target_threat_rank(obs, select, select["option"][0], gamma=1.0)
    base_e = pilot._target_threat_rank(obs, select, select["option"][1], gamma=1.0)
    assert base_e > base_r


@pytest.mark.req("REQ-POSTURE-0007")
def test_preevo_boost_is_gamma_scaled_and_dies_with_the_switch():
    # γ scales the boost continuously (ADR-0026 no-regression is structural: γ=0 → generic rank);
    # the brief_preevo kill-switch (ctor default False) zeroes it outright.
    obs, select = _rank_obs(poke(RIOLU, hp=80))
    opt, roles = select["option"][0], {RIOLU: "fragile_preevo"}
    on = _lever_pilot(brief_preevo=True)
    generic = on._target_threat_rank(obs, select, opt, gamma=0.0)
    assert on._target_threat_rank(obs, select, opt, gamma=0.0, brief_roles=roles) == generic
    mid = on._target_threat_rank(obs, select, opt, gamma=0.5, brief_roles=roles)
    full = on._target_threat_rank(obs, select, opt, gamma=1.0, brief_roles=roles)
    assert full > mid > generic
    off = _lever_pilot()                                   # ctor default: lever OFF
    assert off._target_threat_rank(obs, select, opt, gamma=1.0, brief_roles=roles) == generic


@pytest.mark.req("REQ-POSTURE-0007")
def test_snipe_hunts_the_briefed_preevo_end_to_end():
    # Threading proof: recognized opponent → matched Brief resolves Riolu → _board() threads the
    # roles into the MatchupPlan → the snipe pick flips to the briefed preevo. The ADR-0051 spine
    # (`matchup_targeting`, default ON) is now the switch; OFF reverts to generic order.
    brief = Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                  targets=[{"card": "Riolu", "role": "fragile_preevo", "why": "snipe"}])
    bench = [poke(RIOLU, hp=80), poke(SOLROCK, energy=2, hp=110)]
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(SNIPER), opp_active=poke(MEGA_LUCARIO, hp=340),
                                    opp_bench=bench))
    on = _lever_pilot(scout=Scout(tiny_artifact()), briefs=[brief])                       # default ON
    off = _lever_pilot(scout=Scout(tiny_artifact()), briefs=[brief], matchup_targeting=False)
    assert on.decide(obs) == [0]                           # the bare briefed Riolu (fragile_preevo)
    assert off.decide(obs) == [1]                          # generic order: the energized Solrock


@pytest.mark.req("REQ-POSTURE-0007")
def test_briefed_preevo_boost_never_overrides_a_ko():
    # KO supremacy is structural: a KO-able target (snipe-for-the-ko, +60) still beats the boosted
    # non-KO-able briefed preevo (snipe-the-top-threat +30 / snipe-the-threat +20).
    brief = Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                  targets=[{"card": "Riolu", "role": "fragile_preevo", "why": "snipe"}])
    bench = [poke(RIOLU, hp=80), poke(SOLROCK, energy=1, hp=40)]     # Solrock dies to the 50 rider
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(SNIPER), opp_active=poke(MEGA_LUCARIO, hp=340),
                                    opp_bench=bench))
    on = _lever_pilot(scout=Scout(tiny_artifact()), briefs=[brief], brief_preevo=True,
                      bench_snipe={11: 50})
    assert on.decide(obs) == [1]                           # take the prize, boost notwithstanding


def _gust_obs(*bench):
    obs = make_select([card_opt(BENCH, i, player=1) for i in range(len(bench))], context=SWITCH,
                      current=state(active=poke(SNIPER, energy=1), opp_bench=list(bench)))
    return obs, obs["select"]


@pytest.mark.req("REQ-POSTURE-0007")
def test_gust_target_prefers_the_briefed_preevo_sub_prize():
    # The matching γ-scaled gust tie-break: among equal-prize KO-able evolving preevos, drag up the
    # BRIEFED one (Riolu over Kirlia); sub-prize, so it never overrides a real prize difference.
    obs, select = _gust_obs(poke(RIOLU, hp=80), poke(KIRLIA, hp=80))
    board = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,
                  opp_bench=((RIOLU, 80), (KIRLIA, 80)), posture_confidence=1.0,
                  brief_target_roles={RIOLU: "fragile_preevo"})
    on = _lever_pilot(brief_preevo=True)
    riolu = on._gust_target_tactical(obs, select, board, select["option"][0])
    kirlia = on._gust_target_tactical(obs, select, board, select["option"][1])
    assert riolu > kirlia
    assert riolu - kirlia < 1                              # sub-prize tie-break
    off = _lever_pilot()                                   # switch off → parity restored
    assert (off._gust_target_tactical(obs, select, board, select["option"][0])
            == off._gust_target_tactical(obs, select, board, select["option"][1]))
    cold = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,
                 opp_bench=((RIOLU, 80), (KIRLIA, 80)), posture_confidence=0.0,
                 brief_target_roles={RIOLU: "fragile_preevo"})
    assert (on._gust_target_tactical(obs, select, cold, select["option"][0])
            == on._gust_target_tactical(obs, select, cold, select["option"][1]))


@pytest.mark.req("REQ-POSTURE-0008")
def test_engine_boost_needs_the_dependence_property_and_stays_sub_tier():
    # The engine lever is HARD-GATED on opp_is_engine_dependent (the shipped Lucario Brief judged it
    # FALSE → must not fire) and sub-tier (an energized live attacker still outranks the engine).
    pilot = _lever_pilot(brief_engine=True)
    obs, select = _rank_obs(poke(SOLROCK, hp=110), poke(BRUISER, energy=2, hp=120))
    roles = {SOLROCK: "engine"}
    base = pilot._target_threat_rank(obs, select, select["option"][0], gamma=1.0, brief_roles=roles)
    gated = pilot._target_threat_rank(obs, select, select["option"][0], gamma=1.0, brief_roles=roles,
                                      engine_dependent=True)
    assert base == pilot._target_threat_rank(obs, select, select["option"][0], gamma=1.0)  # bool absent → silent
    assert gated > base                                    # gate open → boost
    energized = pilot._target_threat_rank(obs, select, select["option"][1], gamma=1.0,
                                          brief_roles=roles, engine_dependent=True)
    assert energized > gated                               # sub-tier: imminence keeps priority
    off = _lever_pilot()
    assert (off._target_threat_rank(obs, select, select["option"][0], gamma=1.0, brief_roles=roles,
                                    engine_dependent=True) == base)


@pytest.mark.req("REQ-POSTURE-0008")
def test_engine_dependence_threads_from_the_brief_to_the_board_rank():
    # Construction threading: a matched Brief ASSERTING opp_is_engine_dependent lifts the engine
    # body's strongest_threat_rank; the shipped assert-true-only Lucario Brief (property omitted)
    # leaves the rank byte-identical to a no-Brief Pilot.
    dependent = Brief(slug="dep", label="DEP", covers=["Mega Lucario ex"],
                      opponent_properties={"opp_is_engine_dependent": True},
                      targets=[{"card": "Solrock", "role": "engine", "why": "draw"}])
    lucario_like = Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                         targets=[{"card": "Solrock", "role": "engine", "why": "draw"}])
    bench = [poke(SOLROCK, hp=110)]
    obs = make_select([card_opt(BENCH, 0, player=1)], context=DAMAGE,
                      current=state(active=poke(MEGA_LUCARIO), opp_active=poke(MEGA_LUCARIO, hp=340),
                                    opp_bench=bench))
    rank = lambda briefs: _lever_pilot(scout=Scout(tiny_artifact()), briefs=briefs,
                                       brief_engine=True)._board(obs, obs["select"]).strongest_threat_rank
    assert rank([dependent]) > rank(None)                  # asserted → boost reaches the Board rank
    assert rank([lucario_like]) == rank(None)              # omitted (assert-true-only) → silent


@pytest.mark.req("REQ-POSTURE-0008")
def test_gust_target_prefers_the_dependent_engine_sub_prize():
    # The engine half of the gust tie-break: same gate, same sub-prize ceiling.
    obs, select = _gust_obs(poke(SOLROCK, hp=110), poke(BRUISER, hp=120))
    dep = Brief(slug="dep", label="DEP", covers=["X"],
                opponent_properties={"opp_is_engine_dependent": True})
    board = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,
                  opp_bench=((SOLROCK, 110), (BRUISER, 120)), posture_confidence=1.0,
                  brief=dep, brief_target_roles={SOLROCK: "engine"})
    on = _lever_pilot(brief_engine=True)
    solrock = on._gust_target_tactical(obs, select, board, select["option"][0])
    bruiser = on._gust_target_tactical(obs, select, board, select["option"][1])
    assert solrock > bruiser and solrock - bruiser < 1
    ungated = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,
                    opp_bench=((SOLROCK, 110), (BRUISER, 120)), posture_confidence=1.0,
                    brief_target_roles={SOLROCK: "engine"})   # no property asserted
    assert (on._gust_target_tactical(obs, select, ungated, select["option"][0])
            == on._gust_target_tactical(obs, select, ungated, select["option"][1]))


# ---- ADR-0041: the posture record on the Decision -> Decision Telemetry (stderr) ----

@pytest.mark.req("REQ-POSTURE-0009")
def test_explain_emits_a_posture_record_that_telemetry_serialises():
    # The Decision carries a compact posture summary (who we think we face + how strongly Posture
    # acted); telemetry emits it verbatim so every Correction's live_trace records the matchup.
    from common.telemetry import to_record
    decision = _pilot(scout=Scout(tiny_artifact())).explain(_obs_facing_mega_lucario())
    p = decision.posture
    assert p is not None
    assert p["cands"][0][0] == "Mega Lucario ex"       # believed archetype (top candidate)
    assert p["gamma"] > 0.5                             # recognized -> Posture acted
    assert set(p) >= {"cands", "conf", "unknown", "gamma", "fav", "cov", "brief"}
    assert to_record(decision)["posture"] == p          # rides into the @T record unchanged


@pytest.mark.req("REQ-POSTURE-0009")
def test_no_scout_means_no_posture_record_and_a_sparse_wire():
    # No Scout wired -> Posture structurally off -> no posture on the Decision, and telemetry omits
    # the sparse key entirely (byte-unchanged wire for a non-posture agent).
    from common.telemetry import to_record
    decision = _pilot(scout=None).explain(_obs_facing_mega_lucario())
    assert decision.posture is None
    assert "posture" not in to_record(decision)
