"""The Read on the Board, and the Posture levers that consume it (ADR-0026, docs/scouting.md)."""
import pytest

from common.cards import CardFunctions
from common.pilot import KO_SCORE, Board, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.scouting.briefs import Brief
from common.scouting.matchup_plan import build_matchup_plan
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
    }, attacks={11: AttackStat(11, damage=120, cost=1)})


def _pilot(scout=None, my_archetype=None, briefs=None, posture=True):
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition", "primary_attacker"]},
                     params={"my_archetype": my_archetype} if my_archetype else {})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 scout=scout, briefs=briefs, posture=posture)


def _obs_facing_mega_lucario():
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
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)


@pytest.mark.req("REQ-POSTURE-0003")
def test_lever_c_suppresses_a_denied_evolving_threats_forward_rank():
    stats = DictCardStatProvider({
        SNIPER: CardStat(SNIPER, synthetic=True, name="Sniper", maxDamage=120, attacks=(11,)),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=70, maxDamage=0),
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=220, megaEx=True,
                               maxDamage=270, evolvesFrom="Riolu"),
    }, attacks={11: AttackStat(11, damage=120, benchSnipe=50)})
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
# Two DIFFERENT numbers that coincide for Basic Energy — kept apart on purpose (`pilot_helpers.poke`):
FIGHTING = 6      # EnergyType.FIGHTING — the TYPE code (src/cg/api.py `class EnergyType`)
F_ENERGY = 6      # Basic {F} Energy — the CARD ID (EN_Card_Data.csv: `6,Basic {F} Energy,SVE,6,…,{F}`)


def _unfavored_pilot(win_rate, funcs):
    art = tiny_artifact()
    art.dossiers["MyDeck"] = {"matchups": {"Mega Lucario ex": {"win_rate": win_rate, "n": 30.0}}}
    # Aura Jab's cost is typed {F} (`EN_Card_Data.csv` row 678) and the body holds a Basic {F}:
    # untyped, every strip here scores 0 and Lever A would have nothing to scale.
    stats = DictCardStatProvider({
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=340, megaEx=True,
                               attacks=(11,), energyType=FIGHTING),
        F_ENERGY: CardStat(F_ENERGY, name="Basic {F} Energy", hp=0, energyType=FIGHTING),
    }, attacks={11: AttackStat(11, damage=130, cost=1, energyTypes=(FIGHTING,))})
    return Pilot(Strategy(params={"my_archetype": "MyDeck"}), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=stats,
                 # Armed explicitly (Issue #228): OFF is degraded mode — every deny surface stands
                 # down, so a Lever A claim stated OFF would be a claim about nothing.
                 deny_relevance=True,
                 functions=funcs, scout=Scout(art))


def _obs_hammer_vs_energized_mega_lucario():
    # `energies` holds Energy CARD IDS, typed through the Stat Provider: a Basic {F} is card 6, the
    # only Energy that can pay Aura Jab's {F}.
    me = {"active": [{"id": 1, "energies": [], "hp": 100}], "bench": [],
          "hand": [{"id": HAMMER}], "discard": [], "prize": []}
    opp = {"active": [{"id": MEGA_LUCARIO, "energies": [F_ENERGY], "hp": 200}],
           "bench": [{"id": SOLROCK}, {"id": RIOLU}], "discard": [], "prize": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 4},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None}, "logs": []}


@pytest.mark.req("REQ-POSTURE-0004")
def test_lever_a_boosts_useful_disruption_when_unfavored():
    """Lever A SCALES the priced denial oracle rather than adding a flat rung beside it (ADR-0063);
    only a dossier win_rate differs, so the whole Scout -> favorability -> `_unfavored` path is live."""
    funcs = CardFunctions({HAMMER: ["energy_denial"]})
    obs = _obs_hammer_vs_energized_mega_lucario()
    unfavored = _unfavored_pilot(0.3, funcs).explain(obs).options[0].score
    even = _unfavored_pilot(0.5, funcs).explain(obs).options[0].score
    assert unfavored > even > 0, (
        f"an unfavored Read must amplify a denial worth making (unfavored={unfavored}, even={even})")


@pytest.mark.req("REQ-POSTURE-0004")
def test_lever_a_cannot_make_a_worthless_disruption_worth_playing():
    """Scaling cannot flip a sign (ADR-0063): 3 {F} is surplus for a 1-{F} cost, so the strip denies
    nothing. The Energy must be TYPED or the score reads 0 for the wrong reason."""
    funcs = CardFunctions({HAMMER: ["energy_denial"]})
    obs = _obs_hammer_vs_energized_mega_lucario()
    obs["current"]["players"][1]["active"][0]["energies"] = [F_ENERGY] * 3   # surplus for a 1-{F} cost
    assert _unfavored_pilot(0.3, funcs).explain(obs).options[0].score <= 0, (
        "the unfavored Read resurrected a Hammer that denies nothing — that is an override, not a boost")


# ---- M2 lever A, favored half: don't gift the losing opponent a fresh hand (ADR-0026 amendment) ----

JUDGE_SUP = 1213


def _obs_judge_vs_mega_lucario(opp_hand=8):
    """Judge as the only play, facing a recognized Mega Lucario ex; pre-anchor, so the Layer-B veto
    stays out of frame. `handCount` must be non-zero or the Judge is a pure gift (ADR-0060)."""
    me = {"active": [{"id": 1, "energies": [1], "hp": 100}], "bench": [{"id": 2}],
          "hand": [{"id": JUDGE_SUP}], "discard": [], "prize": []}
    opp = {"active": [{"id": MEGA_LUCARIO, "energies": [1], "hp": 200}],
           "bench": [{"id": SOLROCK}, {"id": RIOLU}], "handCount": opp_hand,
           "discard": [], "prize": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 4},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None}, "logs": []}


def _favored_pilot(win_rate, funcs):
    """`_unfavored_pilot` with a deck of startable Basics (id 77) — a real pull pool for a refresh."""
    art = tiny_artifact()
    art.dossiers["MyDeck"] = {"matchups": {"Mega Lucario ex": {"win_rate": win_rate, "n": 30.0}}}
    return Pilot(Strategy(params={"my_archetype": "MyDeck"}), deck=[77] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=DictCardStatProvider({77: CardStat(77, hp=70)}),
                 functions=funcs, scout=Scout(art))


@pytest.mark.req("REQ-POSTURE-0006")
def test_favored_half_taxes_the_gift_but_never_the_strip():
    """Lever A's favored half is sign-gated (ADR-0026 amendment): a refresh that REFILLS a losing
    opponent is taxed, one that STRIPS a stacked hand is never taxed, at any favorability."""
    funcs = CardFunctions({JUDGE_SUP: ["draw", "hand_disruption", "shuffle_hand"]})
    gift = _obs_judge_vs_mega_lucario(opp_hand=2)    # Judge redraws them 2 → 4: a GIFT (opp_net +2)
    strip = _obs_judge_vs_mega_lucario(opp_hand=8)   # Judge redraws them 8 → 4: a STRIP (opp_net −4)
    def _score(fav, obs):
        return _favored_pilot(fav, funcs).explain(obs).options[0].score

    assert _score(0.7, strip) > _score(0.7, gift) * 2, (
        f"the swing oracle no longer separates a gift from a strip: "
        f"gift={_score(0.7, gift)} strip={_score(0.7, strip)}")
    assert _score(0.5, strip) > _score(0.5, gift)
    assert _score(0.3, strip) > _score(0.3, gift)


@pytest.mark.req("REQ-POSTURE-0006")
@pytest.mark.xfail(strict=True, reason=(
    "POC-T4/5 CAPABILITY LOSS (Issue #386): `dont-gift-a-refresh-when-favored` was deleted with "
    "`baseline_disruption.py`, and it was the ONLY consumer of the Read's favorability lever in the "
    "refresh decision. Measured: the same gift board prices 4.0 at favorability 0.7, 0.5 AND 0.3 — "
    "the number no longer moves at all. An unconsumed Board signal is an unbuilt feature, so this is "
    "recorded as a strict xfail rather than deleted: it turns RED the day something re-wires "
    "favorability into this decision, which is exactly when someone should look at it"))
def test_matchup_favorability_still_reaches_the_refresh_decision():
    """A live tripwire: ADR-0041 built the Read so a matchup fact could steer a decision, and on this
    board it no longer can. That is a RULING nobody has made, so the loss stays visible."""
    funcs = CardFunctions({JUDGE_SUP: ["draw", "hand_disruption", "shuffle_hand"]})
    gift = _obs_judge_vs_mega_lucario(opp_hand=2)
    favored = _favored_pilot(0.7, funcs).explain(gift).options[0].score
    unfavored = _favored_pilot(0.3, funcs).explain(gift).options[0].score
    assert favored < unfavored, (
        f"favorability does not move the gift's price: favored={favored} unfavored={unfavored}")


@pytest.mark.req("REQ-POSTURE-0006")
def test_a_hand_size_attacker_tag_no_longer_buys_the_refresh_a_flat_endorsement():
    """The design-B latent hole, CLOSED (ADR-0102, Issue #261 item 2c): a TAG buys the refresh
    nothing, because the survival term reads the clock."""
    HSATK = 4321
    funcs = CardFunctions({JUDGE_SUP: ["draw", "hand_disruption", "shuffle_hand"],
                           HSATK: ["hand_size_attacker"]})
    obs = _obs_judge_vs_mega_lucario(opp_hand=2)      # a genuine gift, so the tax actually fires
    obs["current"]["players"][1]["bench"].append({"id": HSATK})   # benched; ML stays recognized
    trace = _favored_pilot(0.7, funcs).explain(obs).options[0]
    fired = {h.id for h, _ in trace.fired}
    assert "play-harlequin-vs-hand-size" not in fired      # RETIRED (ADR-0102)
    without = _favored_pilot(0.7, CardFunctions(
        {JUDGE_SUP: ["draw", "hand_disruption", "shuffle_hand"]})).explain(
            _obs_judge_vs_mega_lucario(opp_hand=2)).options[0]
    assert trace.score == without.score, (
        f"the `hand_size_attacker` tag moved the price {without.score} -> {trace.score}; a TAG must "
        "buy nothing, the survival term reads the clock")


# ---- Brief-consumer wiring: the matched Matchup Brief on the Board (ADR-0027), behavior-neutral ----

@pytest.mark.req("REQ-POSTURE-0005")
def test_recognized_opponent_routes_its_matchup_brief_onto_board():
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
    }, attacks={11: AttackStat(11, damage=120, cost=1)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition"]}, params={})
    brief = Brief(slug="ml", label="Mega Lucario ex", covers=["Mega Lucario ex"],
                  pokemon=[{"card": "Riolu", "roles": ["wincon_base"]}])
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=prov,
                 functions=CardFunctions({SOLROCK: ["draw"]}),
                 scout=Scout(tiny_artifact()), briefs=[brief],
                 posture=posture, matchup_targeting=matchup_targeting)


@pytest.mark.req("REQ-POSTURE-0006")
def test_board_carries_a_matchup_plan_from_brief_and_general_tiers():
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
        SNIPER: CardStat(SNIPER, synthetic=True, name="Sniper", maxDamage=120, minAttackCost=1, minCostDamage=120,
                         attacks=(11,)),
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=280, megaEx=True,
                               maxDamage=270, evolvesFrom="Riolu"),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=70, maxDamage=0),
        SOLROCK: CardStat(SOLROCK, name="Solrock", hp=90, maxDamage=30),
    }, attacks={11: AttackStat(11, damage=120, cost=1, benchSnipe=50)})
    brief = Brief(slug="ml", label="Mega Lucario ex", covers=["Mega Lucario ex"],
                  pokemon=[{"card": "Riolu", "roles": ["wincon_base"]}])
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=prov,
                 functions=CardFunctions({SOLROCK: ["draw"]}),
                 scout=Scout(tiny_artifact()), briefs=[brief], snipe_relevance=True,
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
    # ADR-0085 folded the steer into a MULTIPLIER on `their_plan`, so the sign is asserted on
    # `brief_multiplier`: > 1 sharpens the briefed target, < 1 de-prioritises the engine.
    pilot = _mp_snipe_pilot()
    obs = _damage_select_over_ml_bench()
    select = obs["select"]
    board = pilot._board(obs, select)
    terms = [pilot._snipe_relevance_terms(obs, select, board, o,
                                          pilot._context(obs, select, board, o))
             for o in select["option"]]
    assert terms[1]["brief_multiplier"] > 1.0 > terms[0]["brief_multiplier"]
    assert pilot.explain(obs).chosen == [1]


@pytest.mark.req("REQ-POSTURE-0006")
def test_snipe_matchup_term_silent_under_kill_switch():
    # A flat 1.0 on BOTH targets is what "silent" means for a multiplier; unlike `tactical == 0.0` it
    # cannot pass merely because the term was deleted.
    pilot = _mp_snipe_pilot(matchup_targeting=False)
    obs = _damage_select_over_ml_bench()
    select = obs["select"]
    board = pilot._board(obs, select)
    mults = [pilot._snipe_relevance_terms(obs, select, board, o,
                                          pilot._context(obs, select, board, o))["brief_multiplier"]
             for o in select["option"]]
    assert mults == [1.0, 1.0]


@pytest.mark.req("REQ-POSTURE-0006")
def test_gust_target_drags_up_the_briefed_preevo_over_the_draw_engine():
    cur = state(active=poke(SNIPER, energy=1), opp_active=poke(MEGA_LUCARIO, hp=280),
                opp_bench=[poke(SOLROCK, hp=90, max_hp=90), poke(RIOLU, hp=70, max_hp=70)], turn=4)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
                      context=SWITCH, current=cur)
    dec = _mp_snipe_pilot().explain(obs)
    assert dec.options[1].tactical > dec.options[0].tactical   # Riolu edges Solrock on the tie-break
    assert dec.chosen == [1]


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
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True,
                       minAttackCost=1, minCostDamage=120, attacks=(11,), evolvesFrom="Staryu"),
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=340, megaEx=True),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=80, evolvesFrom=None),
        SOLROCK: CardStat(SOLROCK, name="Solrock", hp=110),
    }, attacks={11: AttackStat(11, damage=120, cost=1)})


def _ml_brief_full():
    return Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                 opponent_properties={"opp_tempo": "midrange"},
                 pokemon=[{"card": "Mega Lucario ex", "roles": ["wincon", "primary_attacker"]},
                          {"card": "Riolu", "roles": ["wincon_base"]},
                          {"card": "Solrock", "roles": ["support"]}])


def _ml_pilot(briefs):
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition", "primary_attacker"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_ml_stats(),
                 scout=Scout(tiny_artifact()), briefs=briefs, posture=True)


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
    # The MatchupPlan steers only bench snipe (DAMAGE) and gust (SWITCH); it must not leak into a
    # MAIN play menu.
    obs = _obs_two_option_menu()
    on, off = _ml_pilot([_ml_brief_full()]), _ml_pilot(None)
    assert on.decide(obs) == off.decide(obs)
    assert [o.score for o in on.explain(obs).options] == [o.score for o in off.explain(obs).options]


# ---- ADR-0038 Brief levers: Brief intel sharpens the owning Tactical signal (γ-scaled) ----

BRUISER = 720   # a plain 120-damage attacker body (the energized competitor in rank tests)
EX_INERT = 721  # a 2-prize ex body with no Energy — the "bigger inert prize" the wincon-denial bump beats
SUPPORT_EX = 723  # a 2-prize SUPPORT ex (never attacks) — the equal-prize body the WINCON must outrank
TERA_WINCON = 722  # a Tera ex WINCON — takes NO damage from attacks while BENCHED (CardStat.tera):
                   # un-snipable there, but KO-able once a gust drags it Active (immunity is bench-only)


def _lever_stats(attacks=None):
    return DictCardStatProvider({
        SNIPER: CardStat(SNIPER, synthetic=True, name="Sniper", hp=200, maxDamage=120, minAttackCost=1,
                         minCostDamage=120, attacks=(11,)),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=80, maxDamage=0),
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=340, megaEx=True,
                               maxDamage=270, evolvesFrom="Riolu"),
        SOLROCK: CardStat(SOLROCK, name="Solrock", hp=110, maxDamage=70),
        KIRLIA: CardStat(KIRLIA, name="Kirlia", hp=80, maxDamage=0),
        # A STAND-IN, not the pool card: modelled on Mega Gardevoir ex (747, evolvesFrom Kirlia,
        # 3 prizes) so both lines reach a 3-prize Mega ex — at 2 prizes the tests pass for the wrong reason.
        GARDEVOIR: CardStat(GARDEVOIR, name="Mega Gardevoir ex", hp=310, maxDamage=190,
                            evolvesFrom="Kirlia", megaEx=True),
        BRUISER: CardStat(BRUISER, synthetic=True, name="Bruiser", hp=120, maxDamage=120),
        EX_INERT: CardStat(EX_INERT, synthetic=True, name="Inert ex", hp=80, ex=True, maxDamage=120),
        SUPPORT_EX: CardStat(SUPPORT_EX, synthetic=True, name="Support ex", hp=80, ex=True, maxDamage=0),
        TERA_WINCON: CardStat(TERA_WINCON, synthetic=True, name="Tera ex", hp=200, ex=True, maxDamage=200, tera=True,
                              minAttackCost=1, minCostDamage=200),   # READY, so the forced-promotion
                                                                     # key can land on it

    }, attacks=attacks)


def _lever_pilot(attack_table=None, **kw):
    table = attack_table or {11: AttackStat(11, damage=120, cost=1)}
    # `snipe_relevance` armed to match the shipped PROFILE: unarmed, every bench target scores 0 and
    # the snipe assertions below turn on option index rather than the Brief steer (ADR-0085).
    kw.setdefault("snipe_relevance", True)
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_lever_stats(table), **kw)


@pytest.mark.req("REQ-POSTURE-0007")
def test_snipe_hunts_the_briefed_preevo_end_to_end():
    brief = Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                  pokemon=[{"card": "Riolu", "roles": ["wincon_base"]}])
    bench = [poke(RIOLU, hp=80), poke(SOLROCK, energy=2, hp=110)]
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(SNIPER), opp_active=poke(MEGA_LUCARIO, hp=340),
                                    opp_bench=bench))
    on = _lever_pilot(scout=Scout(tiny_artifact()), briefs=[brief])                       # default ON
    off = _lever_pilot(scout=Scout(tiny_artifact()), briefs=[brief], matchup_targeting=False)
    # Asserted on the SCORES, not the pick: both bodies price relevance 0.0, so index order alone
    # returns [0] and a `decide(obs) == [0]` assertion would witness nothing.
    scores = {o.index: o.score for o in on.explain(obs).options}
    assert scores[0] > scores[1], "the Brief must ORDER the tie, not merely coincide with index order"
    assert on.decide(obs) == [0]                           # the bare briefed Riolu (fragile_preevo)

    # The kill-switch is asserted as SILENCE, not a rival pick: OFF has no signal on this board, so a
    # pick assertion could not distinguish its two states (ADR-0085 Amendment E).
    sel = obs["select"]
    board = off._board(obs, sel)
    breaks = [off._snipe_brief_tiebreak(obs, sel, board, o, off._context(obs, sel, board, o))
              for o in sel["option"]]
    assert breaks == [0.0, 0.0], "matchup_targeting OFF: the Brief must not order the tie"


@pytest.mark.req("REQ-POSTURE-0007")
def test_briefed_preevo_boost_never_overrides_a_ko():
    brief = Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                  pokemon=[{"card": "Riolu", "roles": ["wincon_base"]}])
    bench = [poke(RIOLU, hp=80), poke(SOLROCK, energy=1, hp=40)]     # Solrock dies to the 50 rider
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(SNIPER), opp_active=poke(MEGA_LUCARIO, hp=340),
                                    opp_bench=bench))
    on = _lever_pilot(scout=Scout(tiny_artifact()), briefs=[brief],
                      attack_table={11: AttackStat(11, damage=120, cost=1, benchSnipe=50)})
    assert on.decide(obs) == [1]                           # take the prize, boost notwithstanding


def _tera_snipe_obs(*bench):
    return make_select([card_opt(BENCH, i, player=1) for i in range(len(bench))], context=DAMAGE,
                       current=state(active=poke(SNIPER, energy=1),
                                     opp_active=poke(MEGA_LUCARIO, hp=340), opp_bench=list(bench)))


def _tera_snipe_pilot():
    return _lever_pilot(attack_table={11: AttackStat(11, damage=120, cost=1, benchSnipe=50)})


@pytest.mark.req("REQ-POSTURE-0013")
def test_a_benched_tera_carries_a_structural_snipe_veto_not_a_tunable_weight():
    """A benched Tera takes NO damage from attacks (rules.md §185, `CardStat.tera`) — a CARD FACT, so
    the veto lives in the TACTICAL layer and dominates any positional stack, never competing on points."""
    p = _tera_snipe_pilot()
    obs = _tera_snipe_obs(poke(TERA_WINCON, hp=200, energy=2), poke(BRUISER, hp=120))
    tera, bruiser = p.explain(obs).options
    assert tera.tactical <= -KO_SCORE          # structural veto — not a −60 preference
    assert tera.score < bruiser.score
    assert p.decide(obs) == [1]                # put the counters on a body that can HOLD them


@pytest.mark.req("REQ-POSTURE-0013")
def test_a_positive_role_priority_cannot_erode_the_tera_veto_through_the_tiebreak(monkeypatch):
    """Issue #395: the Brief Tiebreak read the RAW priority rather than `brief_boost_gated()`, so a
    Tera carrying a strict-maximum role won a bonus and lifted the veto off `-KO_SCORE`."""
    from common.scouting.matchup_plan import build_matchup_plan
    p = _tera_snipe_pilot()
    obs = _tera_snipe_obs(poke(TERA_WINCON, hp=200, energy=2), poke(BRUISER, hp=120))
    # A strict maximum among the relevance-tied peers is the shape the tiebreak fires on.
    plan = build_matchup_plan(read_roles={TERA_WINCON: "prize_liability"}, gamma=1.0)
    real_board = p._board
    monkeypatch.setattr(p, "_board",
                        lambda *a, **kw: _with_plan(real_board(*a, **kw), plan))

    tera, bruiser = p.explain(obs).options
    assert plan.priority(TERA_WINCON) > 0, "the fixture must express a positive role, or this is vacuous"
    assert tera.tactical <= -KO_SCORE
    assert tera.score < bruiser.score
    assert p.decide(obs) == [1]


def _with_plan(board, plan):
    board.matchup_plan = plan
    return board


@pytest.mark.req("REQ-POSTURE-0013")
def test_the_tera_veto_never_freezes_a_forced_snipe_select():
    """At a forced select (minCount=1) the veto must ORDER the Tera last, never REMOVE it — the agent
    has to answer or the engine stalls, even when every option is vetoed."""
    p = _tera_snipe_pilot()

    only = _tera_snipe_obs(poke(TERA_WINCON, hp=200, energy=2))
    assert p.decide(only) == [0]                      # forced: still selectable, just never preferred

    all_tera = _tera_snipe_obs(poke(TERA_WINCON, hp=200, energy=2), poke(TERA_WINCON, hp=200))
    assert p.decide(all_tera) == [0]                  # every option vetoed → still commits, no freeze
    assert len(p.decide(all_tera)) == 1               # never returns an empty (illegal) selection


@pytest.mark.req("REQ-POSTURE-0013")
def test_the_tera_veto_declines_only_when_the_snipe_is_OPTIONAL():
    """At minCount=0 the take-fewer DECLINES rather than placing a counter that provably does nothing
    — the ONLY case in which the veto yields an empty selection."""
    p = _tera_snipe_pilot()
    obs = make_select([card_opt(BENCH, 0, player=1)], context=DAMAGE, min_count=0,
                      current=state(active=poke(SNIPER, energy=1), opp_active=poke(MEGA_LUCARIO, hp=340),
                                    opp_bench=[poke(TERA_WINCON, hp=200, energy=2)]))
    assert p.decide(obs) == []                        # optional + provably useless → decline


@pytest.mark.req("REQ-POSTURE-0012")
def test_snipe_matchup_boost_stands_down_on_a_benched_tera():
    """The ADR-0051 matchup boost must stand down on a benched Tera, as it does on a redundant/mirage
    body. The GUST is unaffected: dragging a Tera Active removes the immunity (it is bench-only)."""
    brief = Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                  pokemon=[{"card": "Tera ex", "roles": ["wincon"]}])
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(SNIPER), opp_active=poke(MEGA_LUCARIO, hp=340),
                                    opp_bench=[poke(TERA_WINCON, hp=200), poke(BRUISER, hp=120)]))
    p = _lever_pilot(scout=Scout(tiny_artifact()), briefs=[brief])
    assert p.decide(obs) == [1]      # chip the damageable Bruiser — NEVER the immune benched Tera


def _gust_obs(*bench):
    obs = make_select([card_opt(BENCH, i, player=1) for i in range(len(bench))], context=SWITCH,
                      current=state(active=poke(SNIPER, energy=1), opp_bench=list(bench)))
    return obs, obs["select"]


@pytest.mark.req("REQ-POSTURE-0007")
def test_gust_target_prefers_the_briefed_wincon_preevo():
    # ADR-0051 Phase 3b gives a wincon-line role the denial bump, above the bare sub-prize tie-break a
    # non-wincon role gets; γ=0 → inert plan.
    obs, select = _gust_obs(poke(RIOLU, hp=80), poke(KIRLIA, hp=80))
    board = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,
                  opp_bench=((RIOLU, 80), (KIRLIA, 80)),
                  matchup_plan=build_matchup_plan(brief_roles={RIOLU: "fragile_preevo"}, gamma=1.0))
    p = _lever_pilot()
    riolu = p._gust_target_tactical(obs, select, board, select["option"][0])
    kirlia = p._gust_target_tactical(obs, select, board, select["option"][1])
    assert riolu > kirlia                                  # briefed wincon-line pre-evo preferred
    cold = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,   # γ=0 → inert plan
                 opp_bench=((RIOLU, 80), (KIRLIA, 80)),
                 matchup_plan=build_matchup_plan(brief_roles={RIOLU: "fragile_preevo"}, gamma=0.0))
    assert (p._gust_target_tactical(obs, select, cold, select["option"][0])
            == p._gust_target_tactical(obs, select, cold, select["option"][1]))


@pytest.mark.req("REQ-POSTURE-0008")
def test_gust_target_prefers_a_disruption_target_sub_prize():
    # ADR-0051 replaces the old engine+dependence gate: a curated `disruption_target` gets the gust
    # sub-prize tie-break directly, while a plain `engine` role stays NEUTRAL (a poor gust target).
    obs, select = _gust_obs(poke(SOLROCK, hp=110), poke(BRUISER, hp=120))
    p = _lever_pilot()
    dis = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,
                opp_bench=((SOLROCK, 110), (BRUISER, 120)),
                matchup_plan=build_matchup_plan(brief_roles={SOLROCK: "disruption_target"}, gamma=1.0))
    solrock = p._gust_target_tactical(obs, select, dis, select["option"][0])
    bruiser = p._gust_target_tactical(obs, select, dis, select["option"][1])
    assert solrock > bruiser and solrock - bruiser < 1
    eng = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,   # plain engine → neutral
                opp_bench=((SOLROCK, 110), (BRUISER, 120)),
                matchup_plan=build_matchup_plan(brief_roles={SOLROCK: "engine"}, gamma=1.0))
    assert (p._gust_target_tactical(obs, select, eng, select["option"][0])
            == p._gust_target_tactical(obs, select, eng, select["option"][1]))


@pytest.mark.req("REQ-POSTURE-0014")
def test_gust_prefers_the_damaged_wincon_over_an_equal_prize_support_ex():
    """Card facts cannot break an equal-prize tie (a support Latias ex hits as hard as the Dragapult ex
    wincon): the ROLE discriminates — `prize_liability` gets +1.5 prizes, `disruption_target` does not."""
    obs, select = _gust_obs(poke(EX_INERT, hp=80), poke(SUPPORT_EX, hp=80))   # both 2-prize, both KO-able
    p = _lever_pilot()
    board = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,
                  opp_bench=((EX_INERT, 80), (SUPPORT_EX, 80)),
                  matchup_plan=build_matchup_plan(
                      brief_roles={EX_INERT: "prize_liability",        # THE wincon
                                   SUPPORT_EX: "disruption_target"},   # a support/enabler ex
                      gamma=1.0))
    wincon = p._gust_target_tactical(obs, select, board, select["option"][0])
    support = p._gust_target_tactical(obs, select, board, select["option"][1])
    assert wincon > support                      # equal prizes → break the tie toward the win condition


@pytest.mark.req("REQ-POSTURE-0011")
def test_gust_wincon_denial_drags_the_preevo_over_a_bigger_inert_prize():
    """A 1-prize wincon pre-evo outranks a 2-prize INERT ex. ADR-0119 replaced the γ-gated constant
    with the LINE's own prize (`needs.line_prize_advance`), so this now holds on an unrecognised board."""
    obs, select = _gust_obs(poke(RIOLU, hp=80), poke(EX_INERT, hp=80))
    p = _lever_pilot()
    hot = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,
                opp_bench=((RIOLU, 80), (EX_INERT, 80)),
                matchup_plan=build_matchup_plan(brief_roles={RIOLU: "fragile_preevo"}, gamma=1.0))
    preevo = p._gust_target_tactical(obs, select, hot, select["option"][0])
    inert_ex = p._gust_target_tactical(obs, select, hot, select["option"][1])
    assert preevo > inert_ex                                   # denial lift overrides the +1 prize gap

    cold = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,
                 opp_bench=((RIOLU, 80), (EX_INERT, 80)),
                 matchup_plan=build_matchup_plan(brief_roles={RIOLU: "fragile_preevo"}, gamma=0.0))
    cold_preevo = p._gust_target_tactical(obs, select, cold, select["option"][0])
    cold_inert = p._gust_target_tactical(obs, select, cold, select["option"][1])
    assert cold_preevo > cold_inert, (
        "the line reading is a CARD fact — it must survive an unrecognised opponent, which is "
        "exactly what the γ-gated constant it replaced could not do")
    assert p._gust_matchup_priority(cold, {"id": RIOLU}) == 0   # inert plan: the derivation survives
    # The advance ties; only the card-fact denial separates them, so the margin stays sub-prize.
    assert cold_preevo - cold_inert < 1.0


# `strip-the-stacked-engine-hand` RETIRED with its three tests (ADR-0102, Issue #261 2c): ADR-0060
# narrowed it to a one-sided strip and no such card is in the pool, so it never fired on a real board.


def _fired(trace):
    return {h.id for h, _ in trace.fired}


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
