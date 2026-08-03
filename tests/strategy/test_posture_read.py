"""M2.0 — wire the Read onto the Board (Posture-OFF).

The Pilot senses the opponent via an injected Scout and surfaces the Read on its public
`explain()` output, without changing any decision yet (nothing scores off it — that's M2.1b).
See ADR-0026 (the wiring staircase) and docs/scouting.md (the Read).
"""
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
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)


@pytest.mark.req("REQ-POSTURE-0003")
def test_lever_c_suppresses_a_denied_evolving_threats_forward_rank():
    # Benched Riolu's generic threat rank is its forward-evolution damage (Mega Lucario ex 270). When
    # Read CONFIRMS that line (on an evolution_path) rank is unchanged; when a recognized
    # archetype runs NO such line, lever C suppresses the forward signal (γ-scaled); unknown -> generic
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
    # Mega Lucario ex with an affordable attack (Aura Jab {F} 130) so `opp_active_can_damage_us` sees a
    # real threat at its 1 Energy — the energy-denial gate needs the opp to be able to hurt us, and an
    # empty stat provider would mask that (2026-07-09).
    #
    # Aura Jab's cost is TYPED, and saying so records a card fact rather than inventing one:
    # `data/EN_Card_Data.csv` row 678 reads `Mega Lucario ex,…,{F},…,Aura Jab,{F},130`. The typed cost
    # plus the Basic {F} the body actually holds are what let Deny Relevance (armed below) read this
    # board at all — untyped, every strip here scores 0 and Lever A would have nothing to scale.
    stats = DictCardStatProvider({
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=340, megaEx=True,
                               attacks=(11,), energyType=FIGHTING),
        F_ENERGY: CardStat(F_ENERGY, name="Basic {F} Energy", hp=0, energyType=FIGHTING),
    }, attacks={11: AttackStat(11, damage=130, cost=1, energyTypes=(FIGHTING,))})
    return Pilot(Strategy(params={"my_archetype": "MyDeck"}), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=stats,
                 # Armed EXPLICITLY: OFF is documented DEGRADED MODE since Issue #228 deleted the
                 # ADR-0062 magnitude oracle — every deny surface stands down, so a Lever A claim
                 # stated OFF would be a claim about nothing. Set here rather than inherited from
                 # PROFILE so these tests keep meaning the same thing whichever way the flag ships
                 # (guarding the shipped value is `test_runtime`'s job). `deny_strip_delta` stays off:
                 # it only orders a DISCARD_ENERGY target pick, and this menu has none.
                 deny_relevance=True,
                 functions=funcs, scout=Scout(art))


def _obs_hammer_vs_energized_mega_lucario():
    # `energies` holds attached Energy CARD IDS, resolved to their type through the Stat Provider
    # (`combat.attached_type_counts`) — so a Basic {F} is card 6, and it is the only Energy that can
    # pay Aura Jab's {F}. The old board attached card id 1 (Basic {G}), which the provider did not
    # know and which could not have paid the cost the same fixture claims makes this body a threat.
    me = {"active": [{"id": 1, "energies": [], "hp": 100}], "bench": [],
          "hand": [{"id": HAMMER}], "discard": [], "prize": []}
    opp = {"active": [{"id": MEGA_LUCARIO, "energies": [F_ENERGY], "hp": 200}],
           "bench": [{"id": SOLROCK}, {"id": RIOLU}], "discard": [], "prize": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 4},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None}, "logs": []}


@pytest.mark.req("REQ-POSTURE-0004")
def test_lever_a_boosts_useful_disruption_when_unfavored():
    """Lever A still up-weights a USEFUL energy denial when the Read says the race is lost — but it
    now does so by SCALING the priced denial oracle, not by adding a flat rung beside it (ADR-0063).

    The rung `disrupt-when-unfavored` used to carry the `energy_denial` half and was retired: after
    ADR-0062 made denial a signed tactical, a flat +18 riding the coarse `opp_denial_best > 0` gate
    could OVERRIDE the oracle's own hold and play a Hammer into a KO turn (ms 83968638 f17, CRITICAL).
    So the assertion moves off "which rung fired" and onto the thing that actually matters: an
    unfavored Read must make a real strip score strictly MORE.

    Stated against DENY RELEVANCE since Issue #228 (armed in `_unfavored_pilot`), the ADR-0062
    magnitude instrument this used to score on having been deleted. Lever A survived deny's move by
    re-expression rather than retirement (ADR-0080 Amendment B), and the property is scale-invariant,
    so the assertion below reads verbatim as it did against the magnitude.

    An earlier revision of this docstring held that arming the fixture "would mean inventing a typed
    cost". That was wrong on the facts, and the objection is withdrawn: this body IS Mega Lucario ex
    (`scouting_helpers.MEGA_LUCARIO` == the real card id 678) and `data/EN_Card_Data.csv` prints Aura
    Jab's cost as `{F}` — writing `energyTypes=(FIGHTING,)` RECORDS that fact where the fixture had
    silently dropped it. What was invented was the OLD board: a {F}-costed attacker holding a Basic
    {G} it could never pay with. Nothing here is hand-fitted to produce a result.

    What this test carries that `test_energy_denial_guards.py` does not: that file's
    `test_the_unfavored_read_scales_the_denial_and_can_never_flip_its_sign[relevance]` monkeypatches
    `_unfavored` outright, so it pins the MULTIPLIER's arithmetic on real frames but never the READ
    that decides to apply it. Here the only thing that differs between the two Pilots is a dossier
    win_rate (0.3 vs 0.5), so the whole Scout -> favorability -> coverage -> `_unfavored` path is
    under test — which is what REQ-POSTURE-0004 is about.
    """
    funcs = CardFunctions({HAMMER: ["energy_denial"]})
    obs = _obs_hammer_vs_energized_mega_lucario()
    unfavored = _unfavored_pilot(0.3, funcs).explain(obs).options[0].score
    even = _unfavored_pilot(0.5, funcs).explain(obs).options[0].score
    assert unfavored > even > 0, (
        f"an unfavored Read must amplify a denial worth making (unfavored={unfavored}, even={even})")


@pytest.mark.req("REQ-POSTURE-0004")
def test_lever_a_cannot_make_a_worthless_disruption_worth_playing():
    """The multiplier's whole point (ADR-0063): scaling cannot flip a sign. Their Active is a Mega
    Lucario ex on 3 {F} — SURPLUS for the one {F} Aura Jab costs, so the strip still leaves it
    affording the same attack and denies nothing. However badly the matchup reads, the Hammer must
    stay held: 0 x anything is 0.

    Armed (Issue #228) the whiff now arrives STRUCTURALLY, through Deny Relevance's surplus clause
    (`type_count <= needed` fails at 3 <= 1), which is the shape ADR-0080 wanted: the hold is derived
    rather than gated. The three Energy are typed for exactly that reason — left as unresolvable card
    ids they would read 0 for the wrong reason and this test would pass while asserting nothing.
    """
    funcs = CardFunctions({HAMMER: ["energy_denial"]})
    obs = _obs_hammer_vs_energized_mega_lucario()
    obs["current"]["players"][1]["active"][0]["energies"] = [F_ENERGY] * 3   # surplus for a 1-{F} cost
    assert _unfavored_pilot(0.3, funcs).explain(obs).options[0].score <= 0, (
        "the unfavored Read resurrected a Hammer that denies nothing — that is an override, not a boost")


# ---- M2 lever A, favored half: don't gift the losing opponent a fresh hand (ADR-0026 amendment) ----

JUDGE_SUP = 1213


def _obs_judge_vs_mega_lucario(opp_hand=8):
    """A symmetric refresh (Judge) as the only play, facing a recognized Mega Lucario ex. Pre-anchor
    (no own_prizes), so the Layer-B post-anchor veto stays out of frame — the lever-A rung is
    isolated.

    `handCount` added 2026-07-14 (ADR-0060). It was absent — i.e. 0 — which made these boards
    describe an opponent with an EMPTY hand. Judge is a symmetric REFILL, so playing it there would
    hand them 4 cards for nothing (and, in the hand-size-attacker test below, arm the very attacker
    the test claims to be disrupting: 0 cards = 0 damage, 4 cards = 80). The swing oracle prices that
    gift at −8/card and correctly refuses. Give them a hand actually worth shrinking."""
    me = {"active": [{"id": 1, "energies": [1], "hp": 100}], "bench": [{"id": 2}],
          "hand": [{"id": JUDGE_SUP}], "discard": [], "prize": []}
    opp = {"active": [{"id": MEGA_LUCARIO, "energies": [1], "hp": 200}],
           "bench": [{"id": SOLROCK}, {"id": RIOLU}], "handCount": opp_hand,
           "discard": [], "prize": []}
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
                 functions=funcs, scout=Scout(art))


@pytest.mark.req("REQ-POSTURE-0006")
def test_favored_half_taxes_the_gift_but_never_the_strip():
    """Lever A's favored half (ADR-0026 amendment), sign-gated (hand-disruption grill ruling 3,
    2026-07-19): favorability ≥ 0.55 fires `dont-gift-a-refresh-when-favored` on a `hand_disruption`
    play ONLY when it actually REFILLS the losing opponent (their hand below the card's redraw count).
    It stays silent when the same play STRIPS a stacked hand (ep83664991 f43), and at even AND at
    unfavored (structural exclusion with the shipped half)."""
    funcs = CardFunctions({JUDGE_SUP: ["draw", "hand_disruption", "shuffle_hand"]})
    gift = _obs_judge_vs_mega_lucario(opp_hand=2)    # Judge redraws them 2 → 4: a GIFT (opp_net +2)
    strip = _obs_judge_vs_mega_lucario(opp_hand=8)   # Judge redraws them 8 → 4: a STRIP (opp_net −4)
    favored_gift = {h.id for h, _ in _favored_pilot(0.7, funcs).explain(gift).options[0].fired}
    favored_strip = {h.id for h, _ in _favored_pilot(0.7, funcs).explain(strip).options[0].fired}
    even = {h.id for h, _ in _favored_pilot(0.5, funcs).explain(gift).options[0].fired}
    unfavored = {h.id for h, _ in _favored_pilot(0.3, funcs).explain(gift).options[0].fired}
    assert "dont-gift-a-refresh-when-favored" in favored_gift
    assert "dont-gift-a-refresh-when-favored" not in favored_strip   # ruling 3: never tax a strip
    assert "dont-gift-a-refresh-when-favored" not in even
    assert "dont-gift-a-refresh-when-favored" not in unfavored


@pytest.mark.req("REQ-POSTURE-0006")
def test_a_hand_size_attacker_tag_no_longer_buys_the_refresh_a_flat_endorsement():
    """The design-B latent hole, CLOSED (ADR-0102, Issue #261 item 2c).

    This test used to assert the opposite: favored + a `hand_size_attacker` anywhere in play meant
    `play-harlequin-vs-hand-size` (+25) fired and OUTWEIGHED the gift tax, so the Pilot played a
    Judge into a 2-card hand — refilling the opponent and arming the very attacker it claimed to be
    disrupting. The grill recorded that as an unbuilt hole; it is unbuildable now, because the flat
    is deleted. A TAG buys nothing: the survival term reads the clock, and on this board shrinking
    nobody's hand shortens nothing (the benched stand-in prints no scaling attack), so all that is
    left is the gift tax and a negative swing."""
    HSATK = 4321
    funcs = CardFunctions({JUDGE_SUP: ["draw", "hand_disruption", "shuffle_hand"],
                           HSATK: ["hand_size_attacker"]})
    obs = _obs_judge_vs_mega_lucario(opp_hand=2)      # a genuine gift, so the tax actually fires
    obs["current"]["players"][1]["bench"].append({"id": HSATK})   # benched; ML stays recognized
    trace = _favored_pilot(0.7, funcs).explain(obs).options[0]
    fired = {h.id for h, _ in trace.fired}
    assert "dont-gift-a-refresh-when-favored" in fired
    assert "play-harlequin-vs-hand-size" not in fired      # RETIRED (ADR-0102)
    assert trace.score < 0                                 # the refill is declined, not endorsed


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
    }, attacks={11: AttackStat(11, damage=120, cost=1)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition"]}, params={})
    brief = Brief(slug="ml", label="Mega Lucario ex", covers=["Mega Lucario ex"],
                  targets=[{"card": "Riolu", "role": "fragile_preevo", "why": ""}])
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=prov,
                 functions=CardFunctions({SOLROCK: ["draw"]}),
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
        SNIPER: CardStat(SNIPER, synthetic=True, name="Sniper", maxDamage=120, minAttackCost=1, minCostDamage=120,
                         attacks=(11,)),
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=280, megaEx=True,
                               maxDamage=270, evolvesFrom="Riolu"),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=70, maxDamage=0),
        SOLROCK: CardStat(SOLROCK, name="Solrock", hp=90, maxDamage=30),
    }, attacks={11: AttackStat(11, damage=120, cost=1, benchSnipe=50)})
    brief = Brief(slug="ml", label="Mega Lucario ex", covers=["Mega Lucario ex"],
                  targets=[{"card": "Riolu", "role": "fragile_preevo", "why": ""}])
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
    # Solrock's general draw-engine fact -> an `avoid` MatchupPlan priority; Riolu (Brief
    # fragile_preevo) -> a positive one. The pick lands on the wincon line, not the engine.
    #
    # ADR-0085 moved WHERE that steer is expressed. It used to be a signed ADDEND in the tactical
    # band (`_snipe_matchup_tactical`, now deleted with the six rungs), so the requirement could be
    # read as "tactical positive on one, negative on the other". Decision 5 folded it into the graded
    # scalar as a MULTIPLIER on `their_plan`, which is why the sign is now asserted on
    # `brief_multiplier` instead: > 1 sharpens the briefed target, < 1 de-prioritises the engine, and
    # only the SIGN crosses the seam (`_BRIEF_THREAT_BOOST` supplies the magnitude, so no rate is
    # invented to map a damage-scale priority into the [0,1] band).
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
    # The ADR-0051 spine's kill-switch: with `matchup_targeting` OFF the Brief cannot steer the pick
    # at all. Asserted on `brief_multiplier` rather than on the retired tactical addend (see the
    # sibling test above) — a flat 1.0 on BOTH targets is what "silent" means for a multiplier, and
    # unlike `tactical == 0.0` it cannot pass merely because the term was deleted.
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
    # Phase 2: the gust target-select reads the SAME MatchupPlan. Two 1-prize KO-able bench bodies;
    # my Active (120 dmg, 1 energy) KOs either → the sub-prize tie-break drags up the briefed Riolu
    # (fragile_preevo), not the draw-engine Solrock.
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
    """A provider that knows the Mega Lucario ex line by name (so the Brief's cards resolve to ids)."""
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
                 threats=[{"card": "Mega Lucario ex", "why": "270"}],
                 targets=[{"card": "Riolu", "role": "fragile_preevo", "why": "snipe"},
                          {"card": "Solrock", "role": "engine", "why": "draw"}])


def _ml_pilot(briefs):
    """A posture Pilot that recognizes Mega Lucario ex and knows its line by name (so a matched
    Brief's threats/targets resolve to ids)."""
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
    # Scope containment: the MatchupPlan steers only bench snipe (DAMAGE) and gust (SWITCH), so a
    # resolved Brief on the Board must yield byte-identical choices AND scores at a MAIN play menu vs
    # a Pilot with no Brief — the spine never leaks into a decision it doesn't own.
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
    """Provider for the ADR-0038 lever tests: the Mega Lucario line (Riolu's forward-evo damage =
    270), the Solrock engine body, a Gardevoir line (a NON-briefed evolving pre-evolution, for
    denial parity in gust tests) and a plain bruiser."""
    return DictCardStatProvider({
        SNIPER: CardStat(SNIPER, synthetic=True, name="Sniper", hp=200, maxDamage=120, minAttackCost=1,
                         minCostDamage=120, attacks=(11,)),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=80, maxDamage=0),
        MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", hp=340, megaEx=True,
                               maxDamage=270, evolvesFrom="Riolu"),
        SOLROCK: CardStat(SOLROCK, name="Solrock", hp=110, maxDamage=70),
        KIRLIA: CardStat(KIRLIA, name="Kirlia", hp=80, maxDamage=0),
        GARDEVOIR: CardStat(GARDEVOIR, name="Gardevoir ex", hp=310, maxDamage=190,
                            evolvesFrom="Kirlia"),
        BRUISER: CardStat(BRUISER, synthetic=True, name="Bruiser", hp=120, maxDamage=120),
        EX_INERT: CardStat(EX_INERT, synthetic=True, name="Inert ex", hp=80, ex=True, maxDamage=120),
        SUPPORT_EX: CardStat(SUPPORT_EX, synthetic=True, name="Support ex", hp=80, ex=True, maxDamage=0),
        TERA_WINCON: CardStat(TERA_WINCON, synthetic=True, name="Tera ex", hp=200, ex=True, maxDamage=200, tera=True,
                              minAttackCost=1, minCostDamage=200),   # a READY attacker (as a real Tera-ex
                              #                                        wincon is) — so the forced-promotion
                              #                                        key can legitimately land on it

    }, attacks=attacks)


def _lever_pilot(attack_table=None, **kw):
    table = attack_table or {11: AttackStat(11, damage=120, cost=1)}
    # `snipe_relevance` armed to match the shipped PROFILE. ADR-0085's deletion pass removed the six
    # DAMAGE target rungs, so an unarmed Pilot scores every bench target 0 and the snipe assertions
    # below would pass or fail on option index rather than on the Brief steer under test.
    kw.setdefault("snipe_relevance", True)
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_lever_stats(table), **kw)


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
    # Asserted on the SCORES, not on the pick. Both bodies price relevance 0.0 on this board, so
    # index order alone already returns [0] — a `decide(obs) == [0]` assertion passes with the Brief
    # unwired and witnesses nothing (verified by deleting the tiebreak from the score sum: it stayed
    # green). A strict score ORDERING can only come from the tiebreak, so that is what is asserted.
    scores = {o.index: o.score for o in on.explain(obs).options}
    assert scores[0] > scores[1], "the Brief must ORDER the tie, not merely coincide with index order"
    assert on.decide(obs) == [0]                           # the bare briefed Riolu (fragile_preevo)

    # The kill-switch is asserted as SILENCE, not as a rival pick. It used to read
    # `off.decide(obs) == [1]` — "generic order: the energized Solrock" — which was the deleted
    # `snipe-the-threat` rung (+20 for carrying Energy) doing the work. ADR-0085 Amendment E removed
    # it, so on this board OFF has no signal at all: both bodies price relevance 0.0, and the pick
    # falls to option index, which is [0] — the same answer ON gives, for an entirely different
    # reason. A pick assertion here can no longer distinguish the switch's two states and would pass
    # whether or not the Brief were wired in (the E4 vacuity, one test down). What IS still
    # distinguishable, and is the switch's actual contract, is that the Brief contributes nothing:
    # every option's tiebreak is flat 0.0, so no authored preference reaches the pick.
    sel = obs["select"]
    board = off._board(obs, sel)
    breaks = [off._snipe_brief_tiebreak(obs, sel, board, o, off._context(obs, sel, board, o))
              for o in sel["option"]]
    assert breaks == [0.0, 0.0], "matchup_targeting OFF: the Brief must not order the tie"


@pytest.mark.req("REQ-POSTURE-0007")
def test_briefed_preevo_boost_never_overrides_a_ko():
    # KO supremacy is structural: a KO-able target (snipe-for-the-ko, +60) still beats the MatchupPlan
    # boost on the non-KO-able briefed preevo — the matchup term stands down while a snipe-KO is on offer.
    brief = Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                  targets=[{"card": "Riolu", "role": "fragile_preevo", "why": "snipe"}])
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
    """A benched Tera takes NO damage from attacks (rules.md §185, `CardStat.tera`) — sniping one is
    ALWAYS strictly wasted, in every board, forever. That is a CARD FACT, so it must be a hard
    structural veto, never a tunable preference competing on points.

    The old `dont-snipe-a-benched-tera` was a −60 POSITIONAL weight with `status="assumed"` — i.e.
    tuner-mutable — and its rationale's claim that "−60 cancels the largest positional stack" was only
    ever true by a 10-point margin: `snipe-the-top-threat` (30) + `snipe-the-threat` (20) = 50 held,
    but adding `snipe-on-the-path` (12) reaches 62 and DEFEATS it. The bigger rungs happen to be
    excluded elsewhere (`snipe-for-the-ko` via `target_kos`; `snipe-the-forced-promotion` via
    `_forced_promotion_key`; `snipe-the-evolving-threat` only because no Tera card currently has
    `forward_max_damage > 0` — a DATA accident, not a guarantee). One weight-tune or one new snipe rung
    silently reintroduces the misplay.

    So the veto lives in the TACTICAL layer and dominates any positional stack: no weight can outvote
    it, and a benched Tera can never be preferred over a body that can actually hold the counters.
    """
    p = _tera_snipe_pilot()
    obs = _tera_snipe_obs(poke(TERA_WINCON, hp=200, energy=2), poke(BRUISER, hp=120))
    tera, bruiser = p.explain(obs).options
    assert tera.tactical <= -KO_SCORE          # structural veto — not a −60 preference
    assert tera.score < bruiser.score
    assert p.decide(obs) == [1]                # put the counters on a body that can HOLD them


@pytest.mark.req("REQ-POSTURE-0013")
def test_the_tera_veto_never_freezes_a_forced_snipe_select():
    """EDGE CASE: our attack REQUIRES a snipe and the opponent's ONLY benched body is a Tera. The veto
    must ORDER the Tera last, never REMOVE it — the agent has to answer a forced select or the engine
    stalls. Safe by construction: the take-fewer trims only `while len(chosen) > min_count`, so it can
    never return fewer picks than the select demands, and DAMAGE is not in `_GRAB_CONTEXTS` (so the
    multi-pick greedy path never applies to a snipe).

    Three variants, all forced (minCount=1): one Tera; several Teras (every option vetoed, so the veto
    can't act as a tiebreak — it must still commit); and the Tera alongside the opponent's ACTIVE, which
    is NOT immune (the immunity is bench-ONLY, so the Active must remain freely choosable)."""
    p = _tera_snipe_pilot()

    only = _tera_snipe_obs(poke(TERA_WINCON, hp=200, energy=2))
    assert p.decide(only) == [0]                      # forced: still selectable, just never preferred

    all_tera = _tera_snipe_obs(poke(TERA_WINCON, hp=200, energy=2), poke(TERA_WINCON, hp=200))
    assert p.decide(all_tera) == [0]                  # every option vetoed → still commits, no freeze
    assert len(p.decide(all_tera)) == 1               # never returns an empty (illegal) selection


@pytest.mark.req("REQ-POSTURE-0013")
def test_the_tera_veto_declines_only_when_the_snipe_is_OPTIONAL():
    """The mirror: at an OPTIONAL select (minCount=0) whose only target is an immune benched Tera, the
    take-fewer correctly DECLINES rather than placing a counter that provably does nothing. Legal by
    definition (minCount=0) and strictly better than wasting the placement — and it is the ONLY case in
    which the veto yields an empty selection."""
    p = _tera_snipe_pilot()
    obs = make_select([card_opt(BENCH, 0, player=1)], context=DAMAGE, min_count=0,
                      current=state(active=poke(SNIPER, energy=1), opp_active=poke(MEGA_LUCARIO, hp=340),
                                    opp_bench=[poke(TERA_WINCON, hp=200, energy=2)]))
    assert p.decide(obs) == []                        # optional + provably useless → decline


@pytest.mark.req("REQ-POSTURE-0012")
def test_snipe_matchup_boost_stands_down_on_a_benched_tera():
    """A Tera Pokémon takes NO damage from attacks while BENCHED (`CardStat.tera`, rules.md §185), so a
    snipe aimed there does literally nothing. A Brief will NATURALLY role a Tera-ex win-condition
    `prize_liability` — it IS the wincon — and the ADR-0051 matchup boost is TACTICAL (priority ×5 =
    +500 at γ=1). `_snipe_tera_veto` already orders a benched Tera last structurally, but the boost must
    ALSO stand down so it never credits an immune body (belt to the veto's suspenders), exactly as it
    does on an ADR-0044 redundant/mirage body.

    The GUST is deliberately unaffected: dragging a Tera Active REMOVES the immunity (it is bench-only),
    so `_can_ko` may still take it there — which is what makes it safe for a Brief to role a Tera wincon
    at all."""
    brief = Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                  targets=[{"card": "Tera ex", "role": "prize_liability", "why": "the wincon"}])
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
    # ADR-0051: among equal-prize KO-able evolving pre-evos, the gust drags up the briefed WINCON-line
    # pre-evo (Riolu, fragile_preevo) over a non-wincon one (Kirlia). Phase 3b gives a wincon-line role
    # the denial bump, so this preference is deliberate and above the bare sub-prize tie-break that a
    # non-wincon role gets (that pure-sub-prize path is covered by the disruption-target test). Sourced
    # from the one spine, not the retired _gust_brief_denial lever; γ=0 → inert plan, perfectly neutral.
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
    """GENERAL rule (nothing to do with Tera): among EQUAL-prize KO-able gust targets, drag up the
    opponent's WIN CONDITION, not a support ex. Both bodies here are 2-prize ex's my Active can KO —
    prize value alone TIES them, so the tie must break toward the body whose loss actually ends their
    game.

    Card facts CANNOT make this call: in the real Dragapult deck the support Latias ex hits for 200,
    exactly as hard as the Dragapult ex wincon. Only the Brief knows which is the payoff — so the
    discriminator is the ROLE: `prize_liability` (the wincon → `_gust_wincon_denial` +1.5 prizes) vs
    `disruption_target` (an enabler → sub-prize tie-break only).

    "Damaged" is implicit: the gust is KO-gated (`_can_ko`), so the wincon only becomes a candidate once
    it is actually finishable — a full-HP wincon we cannot kill simply never enters this comparison, and
    the support prize is correctly taken instead."""
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
    # ADR-0051 Phase 3b: a fragile-wincon matchup is won by denying the LINE, not prize count. The
    # denial bump lifts a 1-prize wincon pre-evo (fragile_preevo) ABOVE a 2-prize inert ex in the gust
    # target pick — drag up the crib wincon over the fatter inert prize. γ-scaled and role-scoped; a
    # moderate ~1.5-prize nudge (not the ×5 snipe override), so it stays below the live-threat term.
    obs, select = _gust_obs(poke(RIOLU, hp=80), poke(EX_INERT, hp=80))
    p = _lever_pilot()
    hot = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,
                opp_bench=((RIOLU, 80), (EX_INERT, 80)),
                matchup_plan=build_matchup_plan(brief_roles={RIOLU: "fragile_preevo"}, gamma=1.0))
    preevo = p._gust_target_tactical(obs, select, hot, select["option"][0])
    inert_ex = p._gust_target_tactical(obs, select, hot, select["option"][1])
    assert preevo > inert_ex                                   # denial bump overrides the +1 prize gap
    cold = Board(my_active_id=SNIPER, my_active_energy=1, energy_attached=True,   # γ=0 → bump vanishes
                 opp_bench=((RIOLU, 80), (EX_INERT, 80)),
                 matchup_plan=build_matchup_plan(brief_roles={RIOLU: "fragile_preevo"}, gamma=0.0))
    assert (p._gust_target_tactical(obs, select, cold, select["option"][1])         # prize-first restored:
            > p._gust_target_tactical(obs, select, cold, select["option"][0]))       # the 2-prize ex wins


# ---- ADR-0051 Phase 3b `strip-the-stacked-engine-hand` (+22): RETIRED (ADR-0102, Issue #261 2c) ---
#
# Its three tests are DELETED with it, and deliberately not re-pointed onto a successor, because
# there is none and inventing one would misrecord what happened. The rung was narrowed by ADR-0060 to
# a ONE-SIDED strip (a card that empties the opponent's hand without refilling it); no such card is
# in the pool, so it never fired on a real board, and every one of those tests had to mint a
# `PROBE_CARD` that does not exist to exercise it. What the POC changes is the standard, not the
# analysis: a live weight behind an unfired gate is an untested rung waiting for a future set, and
# `disrupt-the-tailored-hand` (weight 0) already carries the same forward contract inertly. The
# doctrine is recorded in docs/plans/hand-disruption-grill-spec.md's fold list.
#
# `_fired` stays — the tests above it use the helper.


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
