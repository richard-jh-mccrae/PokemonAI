"""Tier 6 — Escalation Search (ADR-0043): the budgeted depth-2 tree for the opponent-CHOICE residue.

The trigger (`_close_attack_tie`) and the gating are pure and unit-tested here; the two-ply engine
sim is exercised end-to-end by the engine-backed planner suite (it shares `_simulate_line`).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


def _shipped_pilot(agent="mega_starmie"):
    from train.tune import _build_pilot
    pilot, _ = _build_pilot(agent)
    return pilot


class _Trace:
    def __init__(self, tactical):
        self.tactical = tactical


@pytest.mark.req("REQ-ESCALATE-0001")
def test_close_attack_tie_detects_only_genuine_ties():
    """Two attacks within _ESCALATE_EPS are a tie to break; a clear leader, a lone attack, and a
    KO-on-the-menu (KO_SCORE-class — nothing to escalate) all yield no tie."""
    from common.strategy.context import _ATTACK, _PLAY, KO_SCORE
    pilot = _shipped_pilot()
    opts = [{"type": _ATTACK}, {"type": _ATTACK}, {"type": _PLAY}]
    # within ε → both attacks tied
    assert set(pilot._close_attack_tie(opts, [_Trace(200), _Trace(190), _Trace(0)])) == {0, 1}
    # clear leader (> ε apart) → no tie
    assert pilot._close_attack_tie(opts, [_Trace(200), _Trace(120), _Trace(0)]) == []
    # a KO on the menu → dominates, nothing to escalate
    assert pilot._close_attack_tie(opts, [_Trace(KO_SCORE + 2), _Trace(KO_SCORE), _Trace(0)]) == []
    # a single attack → no tie
    assert pilot._close_attack_tie([{"type": _ATTACK}, {"type": _PLAY}], [_Trace(200), _Trace(9)]) == []


@pytest.mark.req("REQ-ESCALATE-0002")
def test_escalation_defers_when_off_or_no_budget():
    """The escalation stands down (returns None) when the switch is off, when no search budget is
    set, or when the observation carries no search input — the tuned scoring owns the decision."""
    pilot = _shipped_pilot()
    obs = {"current": {"players": []}}                   # no search_begin_input
    board = object()
    # switch off (default) → None even with a budget
    pilot.search_budget = 50
    assert pilot._escalate(obs, {}, board, [], []) is None
    # switch on but no search input on obs → None
    pilot.escalation = True
    assert pilot._escalate(obs, {}, board, [], []) is None
    # switch on, has input, but budget 0 → None
    pilot.search_budget = 0
    assert pilot._escalate({"search_begin_input": {}}, {}, board, [], []) is None


@pytest.mark.req("REQ-ESCALATE-0003")
def test_escalation_off_by_default_on_the_shipped_pilot():
    """The shipped Pilot ships with escalation OFF and no search budget — a Tier-6 seam gates on its
    own ladder A/B before shipping (like the value model), so the default agent never pays the tree."""
    pilot = _shipped_pilot()
    assert pilot.escalation is False and pilot.search_budget == 0


# ── Density trigger (ADR-0043, deferred-refinement build): fire on opponent-choice TEXTURE ──────────

def _board(read_cards=None, gamma=0.0):
    """A minimal stand-in Board carrying only what the density signal reads (`read`, `posture_confidence`)."""
    read = SimpleNamespace(expected_cards=list(read_cards)) if read_cards is not None else None
    return SimpleNamespace(read=read, posture_confidence=gamma)


@pytest.mark.req("REQ-ESCALATE-0006")
def test_top_k_candidates_needs_an_attack_on_the_menu_and_stands_down_on_a_ko():
    """The density candidate set is the raw top-K options by tactical, gated to a combat-relevant board:
    an affordable attack must be ON THE MENU (not necessarily in the top-K) and no KO may be on the menu
    (a KO dominates — never escalate away from it). No positive-score filter — the two-ply commit gate,
    not a tactical sign, protects a weak line, so the raw top-K is simmed."""
    from common.strategy.context import _ATTACK, _PLAY, KO_SCORE
    pilot = _shipped_pilot()
    atk_dev = [{"type": _ATTACK}, {"type": _PLAY}, {"type": _PLAY}]
    # top-K by tactical with an attack on the menu → the three highest-scoring options
    assert set(pilot._top_k_candidates(atk_dev, [_Trace(120), _Trace(80), _Trace(40)])) == {0, 1, 2}
    # a 4th, lower option drops out of the top-3
    four = atk_dev + [{"type": _PLAY}]
    top = pilot._top_k_candidates(four, [_Trace(120), _Trace(80), _Trace(40), _Trace(10)])
    assert set(top) == {0, 1, 2} and 3 not in top
    # the attack need only be ON THE MENU, not in the top-K: a low-scored attack still arms the trigger
    low_atk = [{"type": _PLAY}, {"type": _PLAY}, {"type": _PLAY}, {"type": _ATTACK}]
    assert set(pilot._top_k_candidates(low_atk, [_Trace(120), _Trace(80), _Trace(40), _Trace(5)])) == {0, 1, 2}
    # no positive-score filter — a board where only the attack scores > 0 still sims the top-K
    assert set(pilot._top_k_candidates(atk_dev, [_Trace(50), _Trace(-10), _Trace(-20)])) == {0, 1, 2}
    # develops only (no attack anywhere) → not a combat decision → empty
    assert pilot._top_k_candidates([{"type": _PLAY}, {"type": _PLAY}], [_Trace(80), _Trace(40)]) == []
    # a KO on the menu dominates → empty
    assert pilot._top_k_candidates(atk_dev, [_Trace(KO_SCORE), _Trace(80), _Trace(40)]) == []
    # a single option → nothing to compare
    assert pilot._top_k_candidates([{"type": _ATTACK}], [_Trace(120)]) == []


@pytest.mark.req("REQ-ESCALATE-0007")
def test_opp_disruption_density_counts_revealed_full_and_predicted_discounted():
    """Density = Function Tags over the opponent's REVEALED cards at full weight (certain) + the Read's
    predicted cards at γ·inclusion_prob (the Brief-gated hidden-deck signal). A card with two disruption
    tags counts twice; γ=0 or absent Function Tags contribute nothing."""
    from common.cards import CardFunctions
    pilot = _shipped_pilot()
    pilot.functions = CardFunctions({100: ["gust"], 101: ["heal", "switch"], 200: ["bench_fill"]})
    obs = {"current": {"yourIndex": 0, "players": [
        {}, {"active": [{"id": 100}], "bench": [{"id": 200}], "discard": [{"id": 101}]}]}}
    # revealed: 1 (gust) + 0 (inert) + 2 (heal+switch) = 3.0
    assert pilot._opp_disruption_density(obs, _board()) == pytest.approx(3.0)
    # + predictions: γ0.8 · (0.5·1 for 100  +  0.25·2 for 101) = 0.4 + 0.4
    assert pilot._opp_disruption_density(
        obs, _board(read_cards=[(100, 0.5), (101, 0.25)], gamma=0.8)) == pytest.approx(3.8)
    # γ = 0 → an unconfident Read's predictions are ignored
    assert pilot._opp_disruption_density(
        obs, _board(read_cards=[(100, 0.5)], gamma=0.0)) == pytest.approx(3.0)
    # signal-blind (no Function Tags) → 0.0, so the trigger never fires
    pilot.functions = None
    assert pilot._opp_disruption_density(obs, _board(read_cards=[(100, 0.5)], gamma=0.8)) == 0.0


@pytest.mark.req("REQ-ESCALATE-0007")
def test_density_dominated_gates_on_the_threshold():
    from common.strategy.planner import _ESCALATE_DENSITY
    pilot = _shipped_pilot()
    pilot._opp_disruption_density = lambda obs, board: _ESCALATE_DENSITY          # exactly at the bar
    assert pilot._density_dominated({}, object()) is True
    pilot._opp_disruption_density = lambda obs, board: _ESCALATE_DENSITY - 0.01   # just below
    assert pilot._density_dominated({}, object()) is False


@pytest.mark.req("REQ-ESCALATE-0006")
def test_escalate_dispatches_to_density_only_on_a_dense_board():
    """With no close attack tie, escalation falls through to the density trigger — escalating the top-K
    when the board is disruption-dense, else deferring to the tuned scoring (never firing on plain boards)."""
    pilot = _shipped_pilot()
    pilot.escalation = True
    pilot.search_budget = 50
    obs = {"search_begin_input": {"deck": [1]}, "current": {"players": []}}
    pilot._close_attack_tie = lambda options, traces: []                  # no tie to break
    pilot._commit_escalation = lambda o, cands, traces, trigger: ("committed", trigger, tuple(cands))
    traces = [_Trace(1), _Trace(1)]
    # dense board → density path escalates the top-K
    pilot._density_dominated = lambda o, board: True
    pilot._top_k_candidates = lambda options, traces: [0, 1]
    assert pilot._escalate(obs, {}, object(), [{}, {}], traces) == (
        "committed", "opponent-disruption density", (0, 1))
    # plain board → defer (the tuned scoring owns it)
    pilot._density_dominated = lambda o, board: False
    assert pilot._escalate(obs, {}, object(), [{}, {}], traces) is None


@pytest.mark.req("REQ-ESCALATE-0009")
def test_commit_escalation_overrides_only_on_strict_improvement():
    """The shared commit gate (both triggers): sim each candidate two-ply, override the tuned pick ONLY
    when a different candidate STRICTLY beats the tuned pick's own two-ply value — else defer. Pinned
    deterministically with stubbed two-ply values (the live engine outcome is trajectory-dependent; the
    engine suite asserts the trigger FIRES, this asserts what it COMMITS)."""
    pilot = _shipped_pilot()
    pilot.search_budget = 100
    traces = [_Trace(100), _Trace(50), _Trace(10)]         # tuned top (highest tactical) = index 0
    # a non-tuned candidate STRICTLY wins the two-ply → override to it
    pilot._two_ply_value = lambda obs, step: {0: 5.0, 1: 9.0, 2: 3.0}[step[0]]
    line = pilot._commit_escalation({}, [0, 1, 2], traces, "opponent-disruption density")
    assert line is not None and line.next_step == [1] and line.goal == "escalation"
    assert "opponent-disruption density" in line.rationale
    # the tuned top is ALSO the two-ply best → escalation agrees → defer
    pilot._two_ply_value = lambda obs, step: {0: 9.0, 1: 5.0, 2: 3.0}[step[0]]
    assert pilot._commit_escalation({}, [0, 1, 2], traces, "close attack tie") is None
    # a mere TIE (best only equals the tuned pick's two-ply value) → not strict → defer
    pilot._two_ply_value = lambda obs, step: {0: 5.0, 1: 5.0, 2: 3.0}[step[0]]
    assert pilot._commit_escalation({}, [0, 1, 2], traces, "x") is None
    # fewer than two completed sims (engine slip / budget) → defer (the guaranteed fallback)
    pilot._two_ply_value = lambda obs, step: None
    assert pilot._commit_escalation({}, [0, 1, 2], traces, "x") is None
