"""Turn Planner — the Tier-1 Engine-Search rank (ADR-0031 phase 3), on the committed native engine.

Engine-backed (imports ``cg``), offline on Windows + Linux like ``test_lethal_engine.py``. Proves the
``_simulate_line`` / ``_engine_leaf_value`` primitives drive the simulator's own forward search from a
REAL observation to the end of my turn — stepping a candidate first move, then re-running the Pilot's
policy on each intermediate SearchState — and read a leaf value off the resulting board.
"""
import json
from pathlib import Path

import pytest

from cg.game import battle_finish, battle_select, battle_start
from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import EngineCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.telemetry import to_record

REPO = Path(__file__).resolve().parents[2]
MEGA = REPO / "tests" / "fixtures" / "agents" / "mega_starmie"


def _deck():
    return [int(x) for x in (MEGA / "deck.csv").read_text(encoding="utf-8").split("\n")[:60]]


def _engine_pilot(deck, **kw):
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    # attack facts flow through the provider's audit-overridden table (ADR-0051)
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY, stats=EngineCardStatProvider(),
                 functions=fns, **kw)


def _first_open_menu(pilot, obs, limit=80):
    """Drive a real mirror game to the first open MAIN menu that carries a ``search_begin_input``."""
    for _ in range(limit):
        cur = obs.get("current") or {}
        if cur.get("result", -1) != -1:
            return None
        sel = obs.get("select")
        if sel is not None and sel.get("context") == 0 and obs.get("search_begin_input"):
            return obs
        obs = battle_select(pilot.decide(obs))
    return None


@pytest.mark.req("REQ-PLANNER-0011")
def test_engine_leaf_value_round_trips_the_search_on_a_real_observation():
    """Drive a real mirror game to its first open turn menu, then evaluate the live first move through
    the engine sim: the primitive must return a concrete FINITE leaf value (not None), proving
    ``search_begin`` → step the move → re-run the policy to end-of-turn round-trips from a live
    observation and the resulting board is read (prizes taken + survival). The engine, not our
    closed-form math, produced the board it scored. NB the value may be NEGATIVE: the ADR-0064 loss
    rung prices a bench-empty-doomed end board at ``-KO_SCORE`` (a predicted game loss is a legitimate
    leaf outcome), so this asserts finiteness, not sign."""
    import math
    deck = _deck()
    pilot = _engine_pilot(deck)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0                           # a legal deck loaded
    try:
        menu = _first_open_menu(pilot, obs)
        assert menu is not None                            # reached an open turn menu with a search input
        value = pilot._engine_leaf_value(menu, pilot.decide(menu))
        assert value is not None and math.isfinite(value)  # search round-tripped to an end-of-turn board
    finally:
        battle_finish()


@pytest.mark.req("REQ-PLANNER-0012")
def test_simulate_line_reaches_a_board_and_ends_my_turn():
    """``_simulate_line`` returns a real end-of-turn board (not None) and stops on MY side: the returned
    tuple carries my player index and the prize count I started the turn with, and the resulting State
    is either the opponent's turn, a later board, or a finished game — never left mid-decision on my
    turn. Proves the policy-driven stepping terminates cleanly."""
    deck = _deck()
    pilot = _engine_pilot(deck)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    try:
        menu = _first_open_menu(pilot, obs)
        assert menu is not None
        sim = pilot._simulate_line(menu, pilot.decide(menu))
        assert sim is not None
        end, my_index, start_prizes, result, line_val, coins = sim   # 5th = the signed line account;
        assert isinstance(coins, bool)                               # 6th = sim consumed coin flips
        assert my_index in (0, 1) and start_prizes >= 1
        cur = end.get("current") or {}
        # my turn's over: game finished, or menu is no longer mine to act on
        assert result != -1 or cur.get("yourIndex") != my_index or cur.get("select") is None \
            or (end.get("select") is None)
    finally:
        battle_finish()


@pytest.mark.req("REQ-PLANNER-0034")
def test_engine_ranking_survives_a_live_drive():
    """Live smoke for multi-candidate ranking (`planner_engine_rank=True`): a real mirror drive with
    the switch ON must never crash, and any line it commits carries the ranking provenance
    (``ranked_by`` set — the engine valued it, or the closed form did when a sim fork failed). The
    ranking-vs-closed pick equivalences are unit-gated; this proves the seam holds on live engine
    observations end to end."""
    deck = _deck()
    pilot = _engine_pilot(deck, planner_engine_rank=True)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    committed = []
    try:
        for _ in range(120):
            cur = obs.get("current") or {}
            if cur.get("result", -1) != -1:
                break
            d = pilot.explain(obs)
            if d.planned is not None and d.planned.goal != "win":   # win locks preempt ranking
                committed.append(d.planned)                         # (ADR-0037), no provenance to carry
            obs = battle_select(d.chosen)
        assert all(ln.ranked_by in ("engine", "closed") for ln in committed)
    finally:
        battle_finish()


# ---------------------------------------- the CRITICAL that literally asked for a turn planner (7f48)
def _shipped_pilot():
    """The real mega_starmie Pilot, built exactly like ``main.py`` (the canonical retest builder), so a
    replayed correction decides the way the shipped agent would."""
    import sys
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_starmie")
    return pilot


@pytest.mark.req("REQ-PLANNER-0016")
def test_critical_7f48_is_fixed_on_its_real_replay_state():
    """CRITICAL 7f48 ('another multi decision example showing that we need a turn planner system'): on the
    ACTUAL captured blunder state, the agent played a card ([1]) instead of retreating the spent Cinderace
    into the powered Mega Starmie — the first step of retreat → attach → KO Fezandipiti for 2 prizes. No
    single option scores that KO, so the greedy scorer missed it. Replayed through the shipped Pilot, the
    Turn Planner now commits the ``ko_for_prizes`` line and the agent takes the human's ``correct`` move
    (the retreat). A hard regression gate on the real state, like the Lethal Solver's CRITICALs."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_7f48.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None and decision.planned.goal == "ko_for_prizes"   # Planner acted
    assert "2-prize KO" in decision.planned.rationale                                   # via multi-step line
    assert decision.chosen == fx["correct"]        # agent now takes human's correct move (the retreat)


@pytest.mark.req("REQ-PLANNER-0020")
def test_critical_0cbc_stabilize_then_ko_is_fixed_on_its_real_replay_state():
    """CRITICAL 0cbc: on the ACTUAL captured state, the agent's Mega ex was at 160/330 and could KO the
    opponent's Active (Jetting Blow), but the `active_can_ko` suppressor dropped the heal — so it played
    a filler card ([3]) instead of Wally's Compassion ([5]). Wally heals to full and bounces the Energy;
    one re-attach still affords the KO, so the agent both survives and takes the prize. Replayed through
    the shipped Pilot, the stabilize-then-KO goal commits Wally's — the human's ``correct`` move."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_0cbc.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None and decision.planned.goal == "stabilize_then_ko"
    assert decision.chosen == fx["correct"]        # agent now heals-and-KOs (plays Wally's) as human marked


@pytest.mark.req("REQ-PLANNER-0035")
def test_critical_a212_evolution_tutor_line_is_fixed_on_its_real_replay_state():
    """CRITICAL a212 ('we know the deck contains Mega Starmie Exs … played Salvatore, evolved Staryu,
    retreated Cinderace, attached energy, attacked, won the game — such sequences MUST be discoverable
    by the turn planner'): on the ACTUAL captured state the agent played Crushing Hammer ([1]) instead
    of Salvatore ([6]) — the enabling first step of evolve-from-deck → free retreat → attach → Jetting
    Blow, which KOs the opponent's LAST body (empty bench = the win). No hook scores a Supporter first
    step, so the greedy scorer missed it. Replayed through the shipped Pilot, the evolution-tutor line
    commits Salvatore — the human's ``correct`` move. (Tracker-cold here, so the rank-grade rung
    carries it; live, the anchored deck tracker upgrades the same line to the win rung's sound lock.)"""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_a212.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None                                    # Planner acted
    assert "evolution tutor" in decision.planned.rationale                 # via the Salvatore line
    assert decision.chosen == fx["correct"]        # agent now plays Salvatore as human marked


@pytest.mark.req("REQ-PLANNER-0035")
def test_f41_prefers_the_free_direct_evolve_over_the_tutor_enabler():
    """f41 (planner-prefer-cheapest-evolution-enabler): on the ACTUAL captured state a benched Staryu is
    evolvable this turn AND Mega Starmie ex is already in hand, so the FREE direct-evolve ([4]: evolve →
    retreat → attach → KO) reaches the SAME 1-prize KO as the Salvatore evolution-tutor ([0]) but spends
    no card and no scarce Supporter slot. Both enabler lines tie on prizes+survival, so the cheapest-
    enabler cost tier must break the tie toward the free-evolve — the agent commits [4], not the tutor."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections"
                     / "ms_prefer_cheap_evolution_enabler_f41.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None and decision.planned.goal == "ko_for_prizes"   # Planner acted
    assert "free evolve" in decision.planned.rationale                                 # via the free-evolve line
    assert decision.chosen == fx["correct"]        # agent now direct-evolves ([4]), not the tutor


@pytest.mark.req("REQ-PLANNER-0036")
def test_critical_6858_heal_before_attach_is_fixed_on_its_real_replay_state():
    """CRITICAL 6858 ('heal first, then attach Ignition, then attack for KO'): on the ACTUAL captured
    state my Mega Starmie (210/330, one {W}) faced the mirror's 190-HP Active. The agent attached
    Ignition FIRST ([1]) — Nebula KOs, but the Mega stays at 210 and eats the mirror's own 210 next
    turn. Wally's Compassion FIRST ([3]) heals to 330 and bounces the {W}; the Ignition attach still
    lands after ({C}{C}{C} on the Evolution -> Nebula 210 ≥ 190), so the agent heals AND takes the
    3-prize KO. The stabilize-then-KO rung now sees the attach-CARRIED KO (no ATTACK on the menu
    reaches one) and commits the heal ahead of the attach."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_6858.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None and decision.planned.goal == "stabilize_then_ko"
    assert decision.chosen == fx["correct"]        # agent now plays Wally's first, as human marked


@pytest.mark.req("REQ-PLANNER-0023")
def test_critical_4298_supporter_enabled_ko_is_fixed_on_its_real_replay_state():
    """CRITICAL 4298 ('our agent needs to start planning its turn ahead of time … it can KO opponent's
    Active via Hilda for energy grab, attach to Mega Starmie, retreat to Mega Starmie, and Jetting Blow'):
    on the ACTUAL captured state, the agent played Crushing Hammer ([1]) instead of Hilda ([2]). Cinderace
    is Active with no Energy and two benched Mega Starmie ex sit at 0 Energy — no single option scores a
    KO, and the enabling first step is a *Supporter* (Hilda tutors an Energy into hand), which the
    retreat/evolve generator never produced. Replayed through the shipped Pilot, the Turn Planner's
    tutor-energy line commits Hilda — the human's ``correct`` move — so the fetched Energy can then power
    the retreat→Jetting-Blow KO. A hard regression gate on the real state, like 7f48 and 0cbc."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_4298.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None and decision.planned.goal == "ko_for_prizes"   # Planner acted
    assert "energy tutor" in decision.planned.rationale                                # via Supporter line
    assert decision.chosen == fx["correct"]        # agent now plays Hilda (energy grab) as human marked


@pytest.mark.req("REQ-PLANNER-0012")
def test_develop_rung_commits_a_well_formed_line_on_a_live_drive():
    """End-to-end on the committed engine: with `develop_rollout=True`, a real mirror drive engages the
    develop rung on its setup turns (no KO to aim at, greedy weak/indifferent). Every develop line it
    commits is well-formed — `goal="develop"`, engine-ranked, its step IS the chosen pick — and its
    telemetry carries the leaf value plus the non-empty ranked `plan_candidates` with the committed pick
    flagged. Proves the rung fires the real sim from live observations and emits the ranking."""
    deck = _deck()
    pilot = _engine_pilot(deck, develop_rollout=True)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    develop_seen = 0
    try:
        for _ in range(120):
            cur = obs.get("current") or {}
            if cur.get("result", -1) != -1:
                break
            d = pilot.explain(obs)
            if d.planned is not None and d.planned.goal == "develop":
                develop_seen += 1
                assert d.planned.ranked_by == "engine"
                assert d.planned.next_step == list(d.chosen)
                rec = to_record(d)
                assert rec["planned"]["goal"] == "develop" and "value" in rec["planned"]
                assert rec["plan_candidates"]                        # non-empty ranking emitted
                assert any(c.get("committed") for c in rec["plan_candidates"])
            obs = battle_select(d.chosen)
        assert develop_seen > 0                                      # the rung engaged on the setup turns
    finally:
        battle_finish()


@pytest.mark.req("REQ-PLANNER-0012")
def test_flag_off_never_commits_develop_and_emits_no_candidates():
    """The default-OFF invariant on a live drive: with the rung off, no committed line is a develop
    line and no record carries `plan_candidates` — byte-identical to the pre-rung agent."""
    deck = _deck()
    pilot = _engine_pilot(deck)                                      # develop_rollout defaults False
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    try:
        for _ in range(120):
            cur = obs.get("current") or {}
            if cur.get("result", -1) != -1:
                break
            d = pilot.explain(obs)
            assert d.planned is None or d.planned.goal != "develop"
            rec = to_record(d)
            if rec is not None:
                assert "plan_candidates" not in rec
            obs = battle_select(d.chosen)
    finally:
        battle_finish()


@pytest.mark.req("REQ-PLANNER-0036")
def test_82227388_43_opens_the_clutch_heal_turn_without_the_attack_blunder():
    """ep82227388 f43 ('play Wally's to fully heal, then Ignition, then Nebula again'): my Mega Starmie
    (210/330, fully powered) faces the mirror's 280-HP Active. Their Nebula Beam (210) == my HP, so I
    die next turn; my Nebula (210) does NOT KO their 280, so this is the NO-KO variant of the heal-line
    — heal to survive + chip, not stabilize-then-KO. The human's whole-turn sequence OPENS with
    Pokégear 3.0 (dig), then Wally's, then the Ignition re-attach, then Nebula. The old agent instead
    committed the turn-ending Attack ([12]) and skipped the heal entirely.

    This is a SINGLE-FRAME guard, not a full-turn playout: no committed correction carries
    ``search_begin_input`` (0/372), so the engine cannot fork this captured mid-turn state and the
    downstream heal→re-power→attack cannot be simulated here. We assert only what is verifiable — the
    shipped Pilot opens with the Pokégear dig (step 1 of the human's line) and never regresses to the
    Attack blunder. The no-KO 'survive-and-chip' planner rung that would PROVE the heal follows does
    not exist yet (contrast 6858, the KO variant, which ``stabilize_then_ko`` owns)."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_82227388_43.json")
                    .read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    chosen = decision.options[decision.chosen[0]]
    assert getattr(chosen, "card_id", None) == 1122          # opens with Pokégear 3.0 (the human's step 1)
    assert decision.chosen != fx["chosen"]                   # NOT the old turn-ending Attack blunder ([12])
