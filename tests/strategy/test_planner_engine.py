"""Turn Planner on the committed native engine — the LIVE-OBSERVATION half of the planner's tests.

Engine-backed (imports ``cg``), offline on Windows + Linux like ``test_lethal_engine.py``.

**What is proved here changed at POC-T4/5 (Issue #386).** This module used to prove that the
``_simulate_line`` / ``_engine_leaf_value`` pair drove the simulator's own forward search from a REAL
observation to the end of my turn — stepping a candidate first move, then re-running the Pilot's
policy on each intermediate SearchState — and read a leaf value off the resulting board. That
rollout is deleted: nothing in a live decision sims a line any more, and ranking end states is the
sequence composer's job, done closed-form off ``apply_option``.

So the live-observation question is re-pointed rather than dropped, and it is the same question:
does the scorer that DECIDES round-trip from a real engine observation? It is now asked of
``_leaf_state_model`` → ``composer.compose``. ``_simulate_line`` keeps its own test because the
OFFLINE primitive survives for the instruments that measure the engine (``family_diag``, the
cgpy↔native agreement lane, the determinism backstop).
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
from conftest import needs_live_board_search

REPO = Path(__file__).resolve().parents[2]
MEGA = REPO / "tests" / "fixtures" / "agents" / "mega_starmie"


# Cinderace (Explosiveness opener + Turbo Flare accel) / Staryu (the wincon Line base).
CINDERACE, STARYU = 666, 1030


def _deck():
    return [int(x) for x in (MEGA / "deck.csv").read_text(encoding="utf-8").split("\n")[:60]]


def _engine_pilot(deck, **kw):
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    # attack facts flow through the provider's audit-overridden table (ADR-0051).
    #
    # `starter_priority` is DECLARED rather than left bare (ADR-0079), for the same reason as in
    # `test_lethal_engine.py`: these drives play whole games, so the pregame Active pick sets the
    # trajectory. Until 2026-07-28 a bare `Strategy()` opened Cinderace by ACCIDENT, via a DERIVED
    # `accel_source` feeding the now-deleted `open-the-accelerator`; the declaration-keyed successor
    # is silent on an undeclared pilot, which would drop the pick to the engine's option index and
    # make every drive below wander. Declaring it keeps the trajectory AND states it outright.
    return Pilot(Strategy(starter_priority=[CINDERACE, STARYU]), deck,
                 general_strategy=GENERAL_STRATEGY, stats=EngineCardStatProvider(),
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
@needs_live_board_search
def test_the_shipped_leaf_round_trips_from_a_real_observation():
    """Drive a real mirror game to its first open turn menu, then score it with the leaf that DECIDES:
    build the StateModel off the live observation and run the composer over the live menu. It must
    return a concrete FINITE score for a real menu option, proving the whole path — engine
    observation → ``_leaf_state_model`` → ``apply_option`` → ``state_value`` — round-trips on a board
    the engine produced rather than one a fixture wrote.

    This replaces the ``_engine_leaf_value`` round-trip (POC-T4/5): that primitive answered the same
    question about a scorer that no longer decides anything. NB the score may be NEGATIVE — the
    ADR-0064 loss term prices a bench-empty-doomed end board at ``-KO_SCORE``, a legitimate leaf
    outcome — so this asserts finiteness, not sign. A ``chosen is None`` is likewise legitimate (the
    seam refusing to price a menu is an honest answer, not a failure), so the finiteness bar is put
    on whatever the composer DID price."""
    import math

    from common import composer as cp
    deck = _deck()
    pilot = _engine_pilot(deck)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0                           # a legal deck loaded
    try:
        menu = _first_open_menu(pilot, obs)
        assert menu is not None                            # reached an open turn menu with a search input
        options = (menu.get("select") or {}).get("option") or []
        my_index = int((menu.get("current") or {}).get("yourIndex") or 0)
        result = cp.compose(pilot._leaf_state_model(menu, my_index), options,
                            search_api=getattr(pilot, "_search_api", None))
        scored = [v for v in result.fanned if v is not None]
        assert scored, "the composer priced no option at all on a live opening menu"
        assert all(math.isfinite(v) for v in scored)       # every priced option is a real number
    finally:
        battle_finish()


@pytest.mark.req("REQ-PLANNER-0012")
@needs_live_board_search
def test_simulate_line_reaches_a_board_and_ends_my_turn():
    """``_simulate_line`` returns a real end-of-turn board (not None) and stops on MY side: the returned
    tuple carries my player index and the prize count I started the turn with, and the resulting State
    is either the opponent's turn, a later board, or a finished game — never left mid-decision on my
    turn. Proves the policy-driven stepping terminates cleanly.

    The tuple is SIX-wide since POC-T4/5, not seven. Issue #178's ``stream`` bit ("this line also
    rode the shuffle") was read by exactly one caller — the develop rollout, which refused an
    unreproducible ranking outright — and died with it; a bit that exists to demote a ranking has
    nothing to demote once no rung ranks a simmed board. ``coins`` stays, because the win rung's own
    verdict driver still speaks in it (``_rng_probe(prize=False)``)."""
    deck = _deck()
    pilot = _engine_pilot(deck)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    try:
        menu = _first_open_menu(pilot, obs)
        assert menu is not None
        sim = pilot._simulate_line(menu, pilot.decide(menu))
        assert sim is not None
        end, my_index, start_prizes, result, line_val, coins = sim    # 5th = signed line account
        assert isinstance(coins, bool)                               # 6th = the line flipped a coin
        assert my_index in (0, 1) and start_prizes >= 1
        cur = end.get("current") or {}
        # my turn's over: game finished, or menu is no longer mine to act on
        assert result != -1 or cur.get("yourIndex") != my_index or cur.get("select") is None \
            or (end.get("select") is None)
    finally:
        battle_finish()


@pytest.mark.req("REQ-PLANNER-0034")
def test_the_composer_decides_a_live_drive_and_its_committed_step_is_the_pick():
    """Live smoke for the DECIDER (POC-T4/5). A real mirror drive must never crash, the composer must
    actually reach the wheel on ordinary turns, and every sequence line it commits must be
    well-formed: its ``next_step`` IS the option the agent played, so the first action of the scored
    sequence and the pick can never drift apart.

    This replaces two tests at once, and for one reason — their subjects merged. The engine-ranking
    drive (`planner_engine_rank=True`) and the develop-rung drive (`develop_rollout=True`) each drove
    a live mirror to prove a rung's seam held; both rungs are deleted, and the composer is the single
    mechanism that now answers for the boards they covered. Asserting the STEP IS THE PICK is the
    part worth keeping — it is a decision-level property that survives the next swap, where
    ``ranked_by in ("engine", "closed")`` pinned which rung did the valuing.

    ``committed`` deliberately excludes win lines: the Lethal Solver's engine-verified lock preempts
    the composer (ADR-0037), so it carries no composer provenance and never should."""
    deck = _deck()
    pilot = _engine_pilot(deck)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    committed = []
    try:
        for _ in range(120):
            cur = obs.get("current") or {}
            if cur.get("result", -1) != -1:
                break
            d = pilot.explain(obs)
            if d.planned is not None and d.planned.goal != "win":   # win locks preempt the composer
                committed.append(d.planned)                         # (ADR-0037), no provenance to carry
                if d.planned.kind == "sequence":
                    assert d.planned.next_step == list(d.chosen)    # the scored line's first action IS the pick
            obs = battle_select(d.chosen)
        assert any(ln.kind == "sequence" for ln in committed), (
            "the composer never committed a line across a whole mirror drive — it is the DEFAULT "
            "decider, so a drive where it never fires means the ladder above it is swallowing "
            "every board")
        assert all(ln.ranked_by in ("composer", None) for ln in committed)
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


# ── CRITICAL 0cbc — MOVED (POC-T4/5, Issue #386) ─────────────────────
#
# `test_critical_0cbc_stabilize_then_ko_is_fixed_on_its_real_replay_state`
# now lives in `tests/strategy/test_heal_refusal_ceiling.py`, as a pair: the seam refusal
# asserted positively, and the human's ruled ACTION kept verbatim under `xfail(strict=True)`.
#
# It moved rather than being rewritten in place because it turned out not to be its own
# problem. All three clutch-heal CRITICALs fail for ONE reason — `apply_option` refuses to
# model Wally's Compassion (Issue #300 `_covers`), so the ruled play is never a candidate the
# beam can commit — and three scattered xfails would have hidden that they are one finding.
# The `planned.goal == "stabilize_then_ko"` assertion is not carried over at all: that rung is
# deleted, and it pinned which mechanism fired rather than what the agent played.

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


# ── CRITICAL 6858 — MOVED (POC-T4/5, Issue #386) ─────────────────────
#
# `test_critical_6858_heal_before_attach_is_fixed_on_its_real_replay_state`
# now lives in `tests/strategy/test_heal_refusal_ceiling.py`, as a pair: the seam refusal
# asserted positively, and the human's ruled ACTION kept verbatim under `xfail(strict=True)`.
#
# It moved rather than being rewritten in place because it turned out not to be its own
# problem. All three clutch-heal CRITICALs fail for ONE reason — `apply_option` refuses to
# model Wally's Compassion (Issue #300 `_covers`), so the ruled play is never a candidate the
# beam can commit — and three scattered xfails would have hidden that they are one finding.
# The `planned.goal == "stabilize_then_ko"` assertion is not carried over at all: that rung is
# deleted, and it pinned which mechanism fired rather than what the agent played.

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


# ── the develop-rung live drives — DELETED (POC-T4/5, Issue #386) ────────────────────────────────
#
# `test_develop_rung_commits_a_well_formed_line_on_a_live_drive` and
# `test_flag_off_never_commits_develop_and_emits_no_candidates` (both REQ-PLANNER-0012) drove a real
# mirror to prove the rung fired the sim from live observations and emitted `plan_candidates`, and
# that OFF was byte-identical. The rung, its `_engine_leaf_value` scorer, the `plan_candidates`
# stream and the `develop_rollout` switch are all gone, so neither has a subject left: there is no
# OFF state to be byte-identical to when the mechanism is deleted rather than disarmed.
#
# What they were REALLY guarding — a committed line is well-formed and its step IS the pick, proved
# against live engine observations rather than fixtures — is asserted for the composer by
# `test_the_composer_decides_a_live_drive_and_its_committed_step_is_the_pick` above, which also
# fails if the composer never reaches the wheel at all.

# ── ep82227388 f43 — MOVED (POC-T4/5, Issue #386) ─────────────────────
#
# `test_82227388_43_opens_the_clutch_heal_turn_without_the_attack_blunder`
# now lives in `tests/strategy/test_heal_refusal_ceiling.py`, as a pair: the seam refusal
# asserted positively, and the human's ruled ACTION kept verbatim under `xfail(strict=True)`.
#
# It moved rather than being rewritten in place because it turned out not to be its own
# problem. All three clutch-heal CRITICALs fail for ONE reason — `apply_option` refuses to
# model Wally's Compassion (Issue #300 `_covers`), so the ruled play is never a candidate the
# beam can commit — and three scattered xfails would have hidden that they are one finding.
# The `planned.goal == "stabilize_then_ko"` assertion is not carried over at all: that rung is
# deleted, and it pinned which mechanism fired rather than what the agent played.

# ── #138 Leaf Profile — the ENGINE-DRIVEN halves (ADR-0068 decision 1) ─────────────────────────
#
# These live here rather than beside the rest of the pin in `test_leaf_profile.py` for a reason that
# is now HISTORICAL, and the placement is kept only because moving them back buys nothing. That
# module collects immediately before `test_lethal_helpers` / `test_lethal_recover`, and starting a
# native battle ahead of those pins shifted the process's engine-RNG position and fired the ml f24
# heisenbug (it did, in CI, on this branch). #178 removed the sensitivity at its source — the develop
# rung no longer ranks on a sim that consumed engine randomness — so no test's position in the suite
# decides f24's answer any more. Do NOT re-introduce an ordering workaround if a frame goes unstable:
# a frame whose answer depends on where it sits in the run is a defect in what decides it.

@pytest.mark.req("REQ-PLANNER-0011")
def test_the_leaf_profile_is_bounded_as_the_145_tripwire():
    """A real engine drive to a live turn menu, then a leaf evaluation, probed.

    The leaf's StateModel field set must stay WITHIN the ordinary per-decision profile: reading
    anything the ordinary decision path does not is the signal that a new consumer (#145) has arrived
    with its per-leaf cost unmeasured. The probe must also see at least one build, so a green result
    can't mean "measured nothing".

    Probed through the composer since POC-T4/5. The reasoning is UNCHANGED in kind but not in detail:
    the leaf used to read the model only through the policy re-run inside `_simulate_line`, so the
    profile was the ordinary decision path's by construction. The composer reads it directly, off
    `_leaf_state_model` and the `apply_option` transitions — which is exactly why the bound now has
    teeth it did not have before, and why it is worth keeping."""
    import math

    from common import composer as cp
    from test_leaf_profile import LEAF_PROFILE, _Probe   # sibling module, not a `tests.` package
    deck = _deck()
    pilot = _engine_pilot(deck)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    try:
        menu = _first_open_menu(pilot, obs)
        assert menu is not None
        options = (menu.get("select") or {}).get("option") or []
        my_index = int((menu.get("current") or {}).get("yourIndex") or 0)
        with _Probe() as probe:
            result = cp.compose(pilot._leaf_state_model(menu, my_index), options,
                                search_api=getattr(pilot, "_search_api", None))
        value = None if result.chosen is None else result.chosen.score
        assert value is None or math.isfinite(value)          # the leaf still evaluates
        assert probe.fields, "the probe measured nothing — a leaf builds at least one model"
        assert probe.fields <= LEAF_PROFILE, (
            "a planner leaf now reads a StateModel field the ordinary decision path does not — "
            "measure the per-leaf cost per side against the 2-vCPU grader bank, then re-pin\n"
            f"  added: {sorted(probe.fields - LEAF_PROFILE)}")
    finally:
        battle_finish()


@pytest.mark.req("REQ-PLANNER-0011")
def test_a_whole_turns_composition_costs_a_bounded_number_of_model_builds():
    """The sizing fact #145 and #150 need, re-measured for the mechanism that now decides.

    It used to read: a leaf's model cost is NOT one build, because the simulated line re-ran my
    policy to end-of-turn and paid one per-decision build per decision it made (N = 4 on a real
    turn-1 drive; the engine sim dominated the leaf's ~12.7 ms and the model's share was under 1%).

    That sizing is GONE with the rollout, and the replacement has the opposite shape: the composer
    never re-runs the policy, so the whole beam over a whole turn is priced from ONE root model plus
    whatever `apply_option` derives per transition. The cost driver moved from *how many decisions
    does the sim make* to *how many transitions does the beam expand*, and the engine sim no longer
    dominates — the composer IS the wall-clock now (median ~31 ms/decision, max 1448 ms; Issue #273).
    So the bound is asserted as a BOUND rather than as an exact N: pinning the number would make this
    a beam-width tripwire wearing a cost test's name."""
    from common import composer as cp
    from common.state_model import StateModel
    deck = _deck()
    pilot = _engine_pilot(deck)
    obs, start = battle_start(deck, list(deck))
    try:
        menu = _first_open_menu(pilot, obs)
        assert menu is not None
        options = (menu.get("select") or {}).get("option") or []
        my_index = int((menu.get("current") or {}).get("yourIndex") or 0)
        model = pilot._leaf_state_model(menu, my_index)
        descriptor, orig, builds = StateModel.__dict__["build"], StateModel.build, []

        def counting(o, **kw):
            builds.append(1)
            return orig(o, **kw)
        StateModel.build = staticmethod(counting)
        try:
            cp.compose(model, options, search_api=getattr(pilot, "_search_api", None))
        finally:
            StateModel.build = descriptor          # the descriptor, not the bound method
        # The root build happens OUTSIDE the probe (above), so a count of 0 here is the honest
        # reading of "the beam derived its states rather than rebuilding them", not a broken probe —
        # which is why the upper bound carries the assertion and the lower one is >= 0.
        assert len(builds) <= cp.BEAM_WIDTH * cp.SEQUENCE_DEPTH * max(1, len(options)), (
            f"the beam built {len(builds)} StateModels over one turn's composition — more than one "
            f"per expanded transition, so something is rebuilding instead of deriving")
    finally:
        battle_finish()
