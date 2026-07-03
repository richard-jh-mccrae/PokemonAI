"""M2.0 — wire the Read onto the Board (Posture-OFF).

The Pilot senses the opponent via an injected Scout and surfaces the Read on its public
`explain()` output, without changing any decision yet (nothing scores off it — that's M2.1b).
See ADR-0026 (the wiring staircase) and docs/scouting.md (the Read).
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.scouting.briefs import Brief
from common.scouting.read import EvoPath, Read
from common.scouting.scout import Scout
from common.strategy import Line, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import BENCH, card_opt, make_select, poke, state
from scouting_helpers import MEGA_LUCARIO, RIOLU, SOLROCK, tiny_artifact

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
    return Pilot(Strategy(params={"my_archetype": "MyDeck"}), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=DictCardStatProvider({}),
                 functions=funcs, attacks={}, scout=Scout(art))


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
