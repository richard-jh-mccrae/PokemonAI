"""Turn Planner on the committed native engine — the LIVE-OBSERVATION half of the planner's tests.

Engine-backed (imports ``cg``), offline on Windows + Linux. The question: does the scorer that
DECIDES round-trip from a real engine observation? Asked of ``_leaf_state_model`` →
``composer.compose``. ``_simulate_line`` keeps its own test because the OFFLINE primitive survives
for the instruments that measure the engine (Issue #386).
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
    # `starter_priority` is DECLARED (ADR-0079): these drives play whole games, and the
    # declaration-keyed pick is silent on an undeclared pilot, so every drive below would wander.
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
    """The whole path — engine observation → ``_leaf_state_model`` → ``apply_option`` → ``state_value``
    — on a board the engine produced. A NEGATIVE score and a ``chosen is None`` are both legitimate."""
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
    """The policy-driven stepping terminates cleanly on MY side. The tuple is SIX-wide since Issue
    Issue #386: ``stream`` died with the develop rollout; ``coins`` stays for the win rung's verdict driver."""
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


#: Independent drives the *fires at all* claim may take. The engine has no deal-seed, so ONE drive is
#: a sample: 3 of 60 measured ended inside 17 steps with every planned line a win lock or ko_for_prizes.
_COMPOSER_DRIVES = 5


def _drive_committed(deck):
    """One live mirror drive's non-``win`` committed lines. The per-decision invariants are asserted on
    the way past, so every drive checks them and only the existential claim is retried."""
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
        assert all(ln.ranked_by in ("composer", None) for ln in committed)
        return committed
    finally:
        battle_finish()


@pytest.mark.req("REQ-PLANNER-0034")
def test_the_composer_decides_a_live_drive_and_its_committed_step_is_the_pick():
    """Live smoke for the DECIDER: every committed sequence's ``next_step`` IS the pick, so the scored
    line and the play cannot drift. ``committed`` excludes win lines — the Lethal lock preempts (ADR-0037)."""
    deck = _deck()
    for _ in range(_COMPOSER_DRIVES):
        if any(ln.kind == "sequence" for ln in _drive_committed(deck)):
            return                       # existential over drives, so the first one that fires settles it
    pytest.fail(
        f"the composer committed no line across {_COMPOSER_DRIVES} independent mirror drives — it is "
        f"the DEFAULT decider, so never firing means the ladder above it is swallowing every board")


def _shipped_pilot():
    """The real mega_starmie Pilot, built exactly like ``main.py``, so a replayed correction decides
    the way the shipped agent would."""
    import sys
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_starmie")
    return pilot


@pytest.mark.req("REQ-PLANNER-0016")
def test_critical_7f48_is_fixed_on_its_real_replay_state():
    """CRITICAL 7f48: the agent played a card instead of retreating the spent Cinderace into the
    powered Mega Starmie — no single option scores the 2-prize KO the line reaches."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_7f48.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None and decision.planned.goal == "ko_for_prizes"   # Planner acted
    assert "2-prize KO" in decision.planned.rationale                                   # via multi-step line
    assert decision.chosen == fx["correct"]        # agent now takes human's correct move (the retreat)


# CRITICAL 0cbc MOVED to `tests/strategy/test_heal_refusal_ceiling.py` (Issue #386): all three
# clutch-heal CRITICALs fail for ONE reason — `apply_option` refuses to model Wally's Compassion.

@pytest.mark.req("REQ-PLANNER-0035")
def test_critical_a212_evolution_tutor_line_is_fixed_on_its_real_replay_state():
    """CRITICAL a212: the enabling first step is a Supporter (Salvatore), which no hook scores, so the
    greedy scorer missed evolve-from-deck → free retreat → attach → Jetting Blow for the win."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_a212.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None                                    # Planner acted
    assert "evolution tutor" in decision.planned.rationale                 # via the Salvatore line
    assert decision.chosen == fx["correct"]        # agent now plays Salvatore as human marked


@pytest.mark.req("REQ-PLANNER-0035")
def test_f41_prefers_the_free_direct_evolve_over_the_tutor_enabler():
    """f41: both enabler lines reach the same 1-prize KO and tie on prizes+survival, so the cheapest-
    enabler cost tier must break the tie toward the FREE direct-evolve, not the Salvatore tutor."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections"
                     / "ms_prefer_cheap_evolution_enabler_f41.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None and decision.planned.goal == "ko_for_prizes"   # Planner acted
    assert "free evolve" in decision.planned.rationale                                 # via the free-evolve line
    assert decision.chosen == fx["correct"]        # agent now direct-evolves ([4]), not the tutor


# CRITICAL 6858 MOVED to `tests/strategy/test_heal_refusal_ceiling.py` (Issue #386), for the same
# Wally's Compassion reason as 0cbc above.

@pytest.mark.req("REQ-PLANNER-0023")
def test_critical_4298_supporter_enabled_ko_is_fixed_on_its_real_replay_state():
    """CRITICAL 4298: no single option scores a KO and the enabling first step is a Supporter (Hilda
    tutors an Energy into hand), which the retreat/evolve generator never produced."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_4298.json").read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.planned is not None and decision.planned.goal == "ko_for_prizes"   # Planner acted
    assert "energy tutor" in decision.planned.rationale                                # via Supporter line
    assert decision.chosen == fx["correct"]        # agent now plays Hilda (energy grab) as human marked


# The develop-rung live drives are DELETED with the rung, its `_engine_leaf_value` scorer, the
# `plan_candidates` stream and the `develop_rollout` switch (Issue #386): no OFF state survives.

# ep82227388 f43 MOVED to `tests/strategy/test_heal_refusal_ceiling.py` (Issue #386), same reason.

# The Issue #138 Leaf Profile engine halves live here rather than in `test_leaf_profile.py` only because
# moving them back buys nothing. Do NOT re-introduce an ordering workaround if a frame goes unstable.

@pytest.mark.req("REQ-PLANNER-0011")
def test_the_leaf_profile_is_bounded_as_the_145_tripwire():
    """The leaf's StateModel field set must stay WITHIN the ordinary per-decision profile — reading
    more means a new consumer (Issue #145) arrived with its per-leaf cost unmeasured."""
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
    """The sizing fact Issue #145 / Issue #150 need: the composer never re-runs the policy, so a whole turn
    is priced from ONE root model plus per-transition derivation. A BOUND, not an exact N."""
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
        # The root build happens OUTSIDE the probe, so a count of 0 is the honest reading of "the
        # beam derived its states rather than rebuilding them" — the upper bound carries the claim.
        assert len(builds) <= cp.BEAM_WIDTH * cp.SEQUENCE_DEPTH * max(1, len(options)), (
            f"the beam built {len(builds)} StateModels over one turn's composition — more than one "
            f"per expanded transition, so something is rebuilding instead of deriving")
    finally:
        battle_finish()
