"""Tier 3 — Match Objectives (ADR-0040): KO Race, Prize Path, Path Denial, derived phases.

The KO Race is closed-form turns-to-KO arithmetic over attack SEQUENCES
(docs/architecture/tiers.md): against a standing wall no affordable attack
KOs this turn, so the biggest single hit is fake value — every min-turn sequence fells the wall
in the same number of turns, and the real differentiator is the incidental chip (bench-snipe /
spread riders) the sequence banks along the way. The Tactical layer prices a wall attack as
per-turn wall progress (hp / t_min) plus the face-value chip of the best min-turn sequence
STARTING with that attack — the `a21472` class: 2×Jetting+Nebula = 450 ≥ 440 in the same three
turns as Nebula-first, but banks 100 chip onto the benched Riolu.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent="mega_starmie"):
    """The agent's real Pilot, built exactly like ``main.py`` (the canonical retest builder)."""
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot(agent)
    return pilot


@pytest.mark.req("REQ-OBJ-0001")
def test_critical_a21472_wall_race_picks_jetting_on_its_real_replay_state():
    """A wall that takes three turns under EVERY ordering makes the biggest-hit pick free of charge:
    the KO Race re-prices wall attacks by SEQUENCE, so the on-tempo chip is banked (ADR-0040)."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_a21472.json")
                    .read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.chosen == fx["correct"]        # Jetting Blow [1], not Nebula Beam [2]


# ---------------------------------------------------------------- the pure KO-Race math (race_values)

@pytest.mark.req("REQ-OBJ-0002")
def test_race_values_prices_the_a21472_shape():
    """Both openers start 3-turn sequences, so it is the CALLER's tempo discount on later chip that
    breaks the tie toward chipping now."""
    from common.strategy.objectives import race_values
    vals = race_values({1487: (120, 50), 1488: (210, 0)}, 440)
    assert vals[1487] == (3, 50)     # Jetting-first: rem 320, 2 hits ≥ 320 → J+N (chip 50)
    assert vals[1488] == (3, 100)    # Nebula-first: rem 230, 2 hits ≥ 230 → J+J (chip 100)


@pytest.mark.req("REQ-OBJ-0002")
def test_race_values_t_star_is_ceil_over_the_hardest_hitter():
    """t_star = 1 + ceil((hp − own damage) / max damage) — the follow-up is the hardest hitter."""
    from common.strategy.objectives import race_values
    vals = race_values({1: (60, 0), 2: (200, 0)}, 400)
    assert vals[1] == (3, 0)         # 60 first → 340 left → two 200s
    assert vals[2] == (2, 0)         # 200 first → 200 left → one 200


@pytest.mark.req("REQ-OBJ-0002")
def test_race_values_one_shot_kill_has_no_rest_chip():
    from common.strategy.objectives import race_values
    assert race_values({1: (500, 30)}, 440)[1] == (1, 0)


@pytest.mark.req("REQ-OBJ-0002")
def test_race_values_drops_beyond_horizon_and_zero_damage():
    """An attack that cannot start a within-horizon KO is absent, and zero-damage attacks never
    enter at all."""
    from common.strategy.objectives import race_values
    vals = race_values({1: (10, 99), 2: (0, 50)}, 1000, horizon=4)
    assert vals == {}                              # 10/turn vs 1000 = 100 turns; 0-dmg excluded
    assert race_values({}, 300) == {}


# --------------------------------------------------------------- per-option Path consumers (Context)

def _obs(me: dict, opp: dict, turn: int = 6) -> dict:
    return {"current": {"yourIndex": 0, "turn": turn, "players": [me, opp]}}


@pytest.mark.req("REQ-OBJ-0005")
def test_snipe_target_on_my_path_sets_target_on_path():
    """The kill-switch zeroes the consumer signal rather than changing the path."""
    from common.strategy.context import _DAMAGE
    pilot = _shipped_pilot()
    me = {"active": [{"id": 1031, "hp": 330, "energies": [6] * 6}],
          "bench": [], "hand": [], "prize": [None] * 5}
    opp = {"active": [{"id": 678, "hp": 440, "energies": []}],
           "bench": [{"id": 676, "hp": 70}, {"id": 676, "hp": 70}, {"id": 676, "hp": 70}],
           "prize": [None] * 6, "hand": []}
    obs = _obs(me, opp)
    select = {"context": _DAMAGE, "option": [{"area": 5, "index": 0, "playerIndex": 1}]}
    board = pilot._board(obs, select)
    assert 676 in board.path_target_ids and 678 in board.path_target_ids
    ctx = pilot._context(obs, select, board, select["option"][0])
    assert ctx.target_on_path is True
    pilot.objectives_path = False                       # the kill-switch zeroes the consumer signal
    ctx_off = pilot._context(obs, select, board, select["option"][0])
    pilot.objectives_path = True
    assert ctx_off.target_on_path is False


@pytest.mark.req("REQ-OBJ-0006")
def test_benching_the_body_that_completes_their_path_is_flagged():
    """Path Denial: benching a body that COMPLETES their exact remaining prize count is flagged;
    the same play stays silent when what is already in play suffices."""
    from common.strategy.context import _PLAY
    pilot = _shipped_pilot()
    me = {"active": [{"id": 666, "hp": 210, "energies": []}],
          "bench": [], "hand": [{"id": 272}], "prize": [None] * 6}
    opp = {"active": [{"id": 678, "hp": 440, "energies": []}],
           "bench": [], "prize": [None] * 3, "hand": []}
    obs = _obs(me, opp)
    select = {"context": 0, "option": [{"type": _PLAY, "index": 0}]}
    board = pilot._board(obs, select)
    assert board.their_path_turns is None               # 1 visible prize < the 3 they need
    ctx = pilot._context(obs, select, board, select["option"][0])
    assert ctx.bench_shortens_their_path is True
    opp_close = dict(opp, prize=[None])                 # they need 1: Cinderace already completes it
    obs2 = _obs(me, opp_close)
    board2 = pilot._board(obs2, select)
    assert board2.their_path_turns is not None
    ctx2 = pilot._context(obs2, select, board2, select["option"][0])
    assert ctx2.bench_shortens_their_path is False


# ------------------------------------------------------ the γ-gated opponent overlay (Tier 4 → their-side)

@pytest.mark.req("REQ-OBJ-0009")
def test_predicted_attacker_overlay_shortens_their_path_gamma_gated():
    """A PREDICTED (unseen) attacker joins their-side turns-to-KO behind a deploy lead of
    ceil(2/γ); at γ=0 or with no Read the math is byte-identical to the visible-only read."""
    from common.scouting.read import Intel, Read
    pilot = _shipped_pilot()
    me = {"active": [{"id": 666, "hp": 210, "energies": []}], "bench": [],
          "hand": [], "prize": [None] * 6}
    opp = {"active": [{"id": 676, "hp": 70, "energies": []}], "bench": [], "prize": [None]}
    obs = {"current": {"yourIndex": 0, "turn": 6, "players": [me, opp]}}
    read = Read(threats=[Intel(cardId=678, role="attacker", seen=False)])
    base = pilot._path_signals(obs, me, opp, me["active"][0], opp["active"][0], 6, 1)
    laid = pilot._path_signals(obs, me, opp, me["active"][0], opp["active"][0], 6, 1, read, 1.0)
    off = pilot._path_signals(obs, me, opp, me["active"][0], opp["active"][0], 6, 1, read, 0.0)
    assert off["their_path_turns"] == base["their_path_turns"]        # γ→0 ⇒ overlay inert
    assert laid["their_path_turns"] is not None                       # the predicted Mega counts …
    if base["their_path_turns"] is not None:                          # … and only ever SHORTENS
        assert laid["their_path_turns"] <= base["their_path_turns"]


# -------------------------------------------------- derived advisory phases (ADR-0040, phase grilling)

@pytest.mark.req("REQ-OBJ-0007")
def test_phase_derivation_stabilize_hysteresis_and_close():
    """A Schmitt trigger: enter STABILIZE only clearly behind, hold inside the band, leave only
    clearly ahead. Backwards transitions are free — the base is memoryless each derivation."""
    from common.strategy.strategy import Plan
    pilot = _shipped_pilot()
    pilot._phase_prev = None
    assert pilot._derive_phase(Plan.SETUP, -2.0, True, 5) is Plan.STABILIZE   # clearly behind → enter
    assert pilot._derive_phase(Plan.SETUP, 0.0, True, 5) is Plan.STABILIZE    # inside band → hold
    assert pilot._derive_phase(Plan.SETUP, 1.5, True, 5) is Plan.SETUP        # clearly ahead → exit
    assert pilot._derive_phase(Plan.SETUP, 0.0, True, 5) is Plan.SETUP        # band from BELOW → no enter
    assert pilot._derive_phase(Plan.RACE, None, False, 2) is Plan.CLOSE       # payoff online, ≤2 prizes
    assert pilot._derive_phase(Plan.RACE, None, False, 3) is Plan.RACE        # 3 prizes → not yet
    assert pilot._derive_phase(Plan.SETUP, None, False, 2) is Plan.SETUP      # payoff offline → no CLOSE
    pilot.objectives_phases = False
    assert pilot._derive_phase(Plan.SETUP, -5.0, True, 1) is Plan.SETUP       # kill-switch → base
    pilot.objectives_phases = True


@pytest.mark.req("REQ-OBJ-0008")
def test_phase_bands_fire_and_gate_ban_holds():
    """The gate ban (ADR-0040): no strategy rule may key on `c.plan`, enforced by scanning every
    rule module. The two phase bands stay SMALL because they are advisory."""
    import re
    from common.pilot import Board, Context
    from common.strategy.context import _PLAY
    from common.strategy.strategy import Plan
    from common.strategy.baseline.baseline_phases import HYPOTHESES

    class _Stat:                     # a Pokémon-shaped stat (hp > 0) for the CLOSE develop band
        hp = 70

    stab = Context(plan=Plan.STABILIZE, select_context=0, option_type=_PLAY, card_id=1,
                   board=Board(phase=Plan.STABILIZE), tags=["heal"])
    close = Context(plan=Plan.CLOSE, select_context=0, option_type=_PLAY, card_id=1,
                    board=Board(phase=Plan.CLOSE), stat=_Stat(), tags=[])
    by_id = {h.id: h for h in HYPOTHESES}
    assert by_id["phase-stabilize-prefer-heal"].when(stab)
    assert not by_id["phase-stabilize-prefer-heal"].when(close)
    assert by_id["phase-close-stop-developing"].when(close)
    assert not by_id["phase-close-stop-developing"].when(stab)
    assert abs(by_id["phase-stabilize-prefer-heal"].weight) <= 10   # bands stay SMALL (advisory)
    assert abs(by_id["phase-close-stop-developing"].weight) <= 10

    rule_files = (list((REPO / "src" / "common" / "strategy").rglob("*.py"))
                  + list((REPO / "src" / "agents").rglob("strategy.py")))
    offenders = [p.name for p in rule_files
                 if re.search(r"c\.plan\b", p.read_text(encoding="utf-8"))]
    assert offenders == [], f"gate ban (ADR-0040): rules must not key on c.plan — {offenders}"


# ------------------------------------------------------------- the two-sided Prize Path (prize_paths)

@pytest.mark.req("REQ-OBJ-0003")
def test_prize_paths_picks_the_fewest_turn_subset():
    """One big body plus small ones can beat two big ones on turns, so the second wall is avoided."""
    from common.strategy.objectives import prize_paths
    keys, turns = prize_paths(
        [("mega1", 3, 6.0), ("mega2", 3, 9.0), ("s1", 1, 1.0), ("s2", 1, 1.0), ("s3", 1, 1.0)], 6)
    assert keys == {"mega1", "s1", "s2", "s3"} and turns == 9.0


@pytest.mark.req("REQ-OBJ-0003")
def test_prize_paths_tie_prefers_fewer_bodies():
    from common.strategy.objectives import prize_paths
    keys, turns = prize_paths([("ex", 2, 4.0), ("a", 1, 2.0), ("b", 1, 2.0)], 2)
    assert keys == {"ex"} and turns == 4.0


@pytest.mark.req("REQ-OBJ-0003")
def test_prize_paths_edge_cases():
    """Too few visible prizes returns (empty, None): the path would run through bodies not yet in
    play, so consumers stay silent."""
    from common.strategy.objectives import prize_paths
    assert prize_paths([("a", 1, 1.0)], 0) == (frozenset(), 0.0)
    keys, turns = prize_paths([("a", 1, 1.0)], 3)
    assert keys == frozenset() and turns is None


@pytest.mark.req("REQ-OBJ-0004")
def test_board_carries_the_two_sided_path_on_the_real_a21472_state():
    """`race_ahead` is their path total minus mine."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_a21472.json")
                    .read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    board = pilot._board(fx["obs"], fx["obs"].get("select"))
    assert board.my_path_turns is not None and board.my_path_turns > 0
    assert board.path_target_ids                      # concrete opp card ids on my path
    assert board.their_path_turns is None or board.race_ahead == board.their_path_turns - board.my_path_turns


@pytest.mark.req("REQ-OBJ-0002")
def test_race_values_rest_chip_maximizes_within_min_turns():
    """The remainder DP trades damage overkill for chip but never a turn."""
    from common.strategy.objectives import race_values
    vals = race_values({1: (100, 40), 2: (200, 0)}, 300)
    assert vals[1] == (2, 0)         # 100 first → 200 left → ONE 200 (min turns: 2, no chip room)
    assert vals[2] == (2, 40)        # 200 first → 100 left → one chipper (chip 40)


# --------------------------------------------------------------- gap closure (ADR-0040 refinements)

@pytest.mark.req("REQ-OBJ-0011")
def test_path_stickiness_holds_the_previous_path_within_the_band():
    """A still-feasible previous path inside the `_PATH_STICKY` band is kept, for coherent targeting;
    a clearly better path always switches and an infeasible one drops instantly."""
    pilot = _shipped_pilot()
    # two disjoint 1-prize routes, a hair apart: A={10} at 2t, B={20} at 2.4t (within the 0.5 band)
    mine = [(1, 1, 2.4, 20), (2, 1, 2.0, 10)]
    from common.strategy.objectives import prize_paths
    keys, turns = prize_paths([(k, pv, t) for k, pv, t, _c in mine], 1)
    assert keys == {2}                                   # fresh cheapest = the 2.0-turn body (id 10)
    pilot._my_path_prev = frozenset({20})                # but last turn we were on body 20 (2.4t)
    keys2, turns2 = pilot._sticky_path(mine, 1, keys, turns)
    assert keys2 == {1} and turns2 == 2.4               # held — within 0.5 of the new best
    # now a clearly-better path (1.0t) must win over the sticky 2.4t previous
    mine3 = [(1, 1, 2.4, 20), (3, 1, 1.0, 30)]
    k3, t3 = prize_paths([(k, pv, t) for k, pv, t, _c in mine3], 1)
    pilot._my_path_prev = frozenset({20})
    k3s, t3s = pilot._sticky_path(mine3, 1, k3, t3)
    assert k3s == {3} and t3s == 1.0                    # clearly better → switch


@pytest.mark.req("REQ-OBJ-0012")
def test_unfavored_read_relaxes_the_stabilize_enter_bar():
    """A sufficiently-covered UNFAVORED Read shifts the STABILIZE enter bar out a turn; below the
    coverage floor the matchup is unknown and nothing shifts."""
    from common.strategy.strategy import Plan
    pilot = _shipped_pilot()
    pilot._phase_prev = None
    # neutral favorability → enter bar stays at −1, so −0.5 is NOT behind enough → RACE
    assert pilot._derive_phase(Plan.RACE, -0.5, True, 5, favorability=0.5, coverage=0.5) is Plan.RACE
    pilot._phase_prev = None
    # unfavored + covered → bar relaxes to 0.0, so −0.5 now enters STABILIZE
    assert pilot._derive_phase(Plan.RACE, -0.5, True, 5,
                               favorability=0.4, coverage=0.5) is Plan.STABILIZE
    pilot._phase_prev = None
    # unfavored but UNKNOWN (coverage below the floor) → no shift → RACE (no regression)
    assert pilot._derive_phase(Plan.RACE, -0.5, True, 5,
                               favorability=0.4, coverage=0.1) is Plan.RACE


@pytest.mark.req("REQ-OBJ-0010")
def test_promote_onto_their_path_is_flagged_and_switched():
    """A promote candidate sitting on the opponent's cheapest path is flagged; the kill-switch and
    the empty-path case both zero it."""
    from common.pilot import Board
    from common.strategy.context import _TO_ACTIVE
    pilot = _shipped_pilot()
    me = {"active": [{"id": 666, "hp": 210, "energies": []}],
          "bench": [{"id": 1031, "hp": 330, "energies": []}], "hand": [], "prize": [None] * 6}
    opp = {"active": [{"id": 678, "hp": 440, "energies": []}], "bench": [], "prize": [None] * 6,
           "hand": []}
    obs = {"current": {"yourIndex": 0, "turn": 8, "players": [me, opp]}}
    select = {"context": _TO_ACTIVE, "option": [{"area": 5, "index": 0, "playerIndex": 0}]}
    board = pilot._board(obs, select)
    on_path = board.their_path_my_ids
    ctx = pilot._context(obs, select, board, select["option"][0])
    assert ctx.promote_target_on_their_path == (1031 in on_path)
    pilot.objectives_path = False
    assert pilot._context(obs, select, board, select["option"][0]).promote_target_on_their_path is False
    pilot.objectives_path = True


@pytest.mark.req("REQ-OBJ-0014")
def test_soft_83661649_30_ko_race_prices_jetting_over_nebula_on_its_real_state():
    """An EMPTY Prize Path here, so this exercises the no-path race-credit branch. The gate is the
    ORDERING invariant, not `chosen` — the Pilot correctly develops first (attack is the turn-ender)."""
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_83661649_30.json")
                    .read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    obs = fx["obs"]
    opts = obs["select"]["option"]
    jetting = next(i for i, o in enumerate(opts) if o.get("attackId") == 1487)   # Jetting Blow (correct)
    nebula = next(i for i, o in enumerate(opts) if o.get("attackId") == 1488)    # Nebula Beam (blunder)
    d = pilot.explain(obs)
    assert d.options[jetting].tactical > d.options[nebula].tactical    # KO Race ranks the sequence
    pilot.objectives_race = False                                      # kill-switch: greedy biggest-hit
    d_off = pilot.explain(obs)
    pilot.objectives_race = True
    assert d_off.options[nebula].tactical > d_off.options[jetting].tactical   # the old Nebula blunder


@pytest.mark.req("REQ-OBJ-0013")
def test_objectives_trace_rides_the_decision_and_telemetry():
    """None, and absent from the record, on an empty early board where no path resolves."""
    from common.telemetry import to_record
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_a21472.json")
                    .read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.objectives is not None and "my" in decision.objectives   # path resolved on this board
    rec = to_record(decision, tier=0)
    assert rec["objectives"] == decision.objectives


@pytest.mark.req("REQ-OBJ-0006")
def test_the_path_delta_survives_as_a_MAGNITUDE_not_only_its_sign():
    """Completing a previously UNCOMPLETABLE route is the biggest case, so it cannot report as a bare
    1-turn improvement: `their_path_turns is None` grades against the shared `HORIZON` (ADR-0086)."""
    from common.grading import HORIZON
    from common.strategy.context import _PLAY
    pilot = _shipped_pilot()
    me = {"active": [{"id": 666, "hp": 210, "energies": []}],
          "bench": [], "hand": [{"id": 272}], "prize": [None] * 6}
    opp = {"active": [{"id": 678, "hp": 440, "energies": []}],
           "bench": [], "prize": [None] * 3, "hand": []}
    obs = _obs(me, opp)
    select = {"context": 0, "option": [{"type": _PLAY, "index": 0}]}
    board = pilot._board(obs, select)
    assert board.their_path_turns is None                    # uncompletable before the bench play
    ctx = pilot._context(obs, select, board, select["option"][0])
    assert ctx.bench_path_delta > 0                          # ...and completing it is a real gift
    assert ctx.bench_path_delta <= HORIZON                   # graded, never unbounded
    assert ctx.bench_shortens_their_path is (ctx.bench_path_delta > 0)   # the boolean is derived

    opp_close = dict(opp, prize=[None])                      # they need 1: the play improves nothing
    ctx2 = pilot._context(obs, select, pilot._board(_obs(me, opp_close), select),
                          select["option"][0])
    assert ctx2.bench_path_delta == 0.0
    assert ctx2.bench_shortens_their_path is False


@pytest.mark.req("REQ-OBJ-0006")
def test_a_benched_body_is_reached_by_the_bench_harvest_not_only_by_being_promoted():
    """PRINTED damage lands on the Active, so it can only describe a benched body being dragged up;
    riders reach the Bench directly out of ONE shared per-turn budget (ADR-0071)."""
    pilot = _shipped_pilot()
    bench = [{"id": 272, "hp": 70, "energies": []}]          # Lillie's Clefairy ex, chipped to 70
    me = {"active": [{"id": 666, "hp": 210, "energies": []}],
          "bench": bench, "hand": [], "prize": [None] * 6}
    opp = {"active": [{"id": 140, "hp": 210, "energies": [8] * 3}],   # Fezandipiti ex, Cruel Arrow up
           "bench": [], "prize": [None] * 6, "hand": []}
    obs, select = _obs(me, opp), {"context": 0, "option": []}
    pilot._board(obs, select)                                 # builds the snapshot the clock reads
    assert pilot._their_turns_to_ko(opp, bench[0]) is None    # printed damage reaches nothing
    assert pilot._their_harvest_clock(bench) == {0: 1}        # ...the rider reaches it this turn
    items = pilot._their_path_items(opp, me["active"][0], bench)
    assert [(pv, t) for _k, pv, t, _cid in items] == [(2, 1.0)]   # on their path, no promote surcharge


@pytest.mark.req("REQ-OBJ-0006")
def test_the_path_delta_is_zero_when_the_objectives_kill_switch_is_off():
    """With the Prize-Path machinery dark the exposure is a DEFINED zero, never an estimate."""
    from common.strategy.context import _PLAY
    pilot = _shipped_pilot()
    me = {"active": [{"id": 666, "hp": 210, "energies": []}],
          "bench": [], "hand": [{"id": 272}], "prize": [None] * 6}
    opp = {"active": [{"id": 678, "hp": 440, "energies": []}],
           "bench": [], "prize": [None] * 3, "hand": []}
    obs, select = _obs(me, opp), {"context": 0, "option": [{"type": _PLAY, "index": 0}]}
    pilot.objectives_path = False
    try:
        ctx = pilot._context(obs, select, pilot._board(obs, select), select["option"][0])
        assert ctx.bench_path_delta == 0.0
    finally:
        pilot.objectives_path = True
