"""Evolve DECIDER on real frames (common/evolve_value.py) — ADR-0070, Issue #140.

The equation's per-option TERM row off `OptionTrace.evolve_working`, kill-switch forced ON: does it
RANK the corpus frames? The algebra itself is pinned at the pure-function seam,
`test_evolve_decider.py`.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _shadows(agent, fixture):
    """(fixture, decision, {option index -> the evolve decider's total}) with the switch forced ON."""
    fx = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
    pilot = _pilot(agent)
    pilot.evolve_value = True                    # price the frames even while PROFILE ships it OFF
    d = pilot.explain(fx["obs"])
    opts = fx["obs"]["select"]["option"]
    evolve = {i: (d.options[i].evolve_working or {}).get("tactical", 0.0)
              for i, o in enumerate(opts) if o.get("type") == 9}
    return fx, d, evolve


def test_income_on_evolve_is_endorsed_f40():
    """f40: Dunsparce→Dudunsparce turns a draw engine ON (one-shot) with no line/deploy — a positive
    income Δ, so the evolve is endorsed (>0) and will sequence ahead of the non-lethal KO."""
    fx, d, evolve = _shadows("dragapult_ex", "dp_evolve_the_draw_engine_f40")
    assert evolve[fx["correct"][0]] > 0, evolve


def test_multiattack_evolve_keeps_the_cheap_realizable_attack_f35():
    """Phantom Dive is mismatched, but the form's cheaper 70-damage attack remains realizable."""
    fx, d, evolve = _shadows("dragapult_ex", "dp_hold_evolve_until_typed_ready_f35")
    (only_evolve,) = evolve.values()
    assert 0 < only_evolve < 40


def test_which_body_prefers_the_energized_f82():
    """f82: two mid-line Dreepy→Drakloak evolves; the equation must prefer the ACTIVE body. Evolving
    one bench Dreepy out of a spread's range only redirects the counters, so it buys no survival."""
    fx, d, evolve = _shadows("dragapult_ex", "dp_evolve_energized_line_body_first_f82")
    best = max(evolve, key=evolve.get)
    assert best == fx["correct"][0], evolve


def test_advance_the_line_beats_spreading_f29():
    """f29: advancing the started line (evolve Drakloak) out-values a spread attach onto a bare base."""
    fx, d, evolve = _shadows("dragapult_ex", "dp_charge_the_line_f29")
    assert evolve[fx["correct"][0]] > 0
    # An attach may out-SCORE an evolve without winning the turn: free development is tier 0 and the
    # irreversible attach is tier 2, so the evolve is taken first and the attach follows.
    assert d.chosen == fx["correct"], (
        f"the evolve lost the turn to a non-evolve option: chosen={d.chosen}, correct={fx['correct']}")


# ── the income half must actually COMPUTE (ADR-0070 amendment K, #167) ────────────────────────────

@pytest.mark.req("REQ-GEN-0091")
def test_the_dig_income_term_is_not_structurally_dead():
    """`deck_energy_counts` holds `CountTriple`s, which refuse to be bare numbers (ADR-0068), so
    `draw_hit_probability`'s `int(copies)` raised into its bad-input guard and the income half died."""
    fx = json.loads((FIXTURES / "dp_hold_evolve_until_typed_ready_f35.json").read_text(encoding="utf-8"))
    pilot = _pilot("dragapult_ex")
    pilot.evolve_value = True
    pilot.explain(fx["obs"])                       # populate the StateModel
    me = fx["obs"]["current"]["players"][0]
    drakloak = next(x for x in (me.get("active") or []) if x)

    income = pilot._evolve_income_delta(drakloak, 120, is_active=True)
    assert 0.0 < income <= 1.0, (
        f"the Recon Directive dig is priced at {income} — the income half is dead")


@pytest.mark.req("REQ-GEN-0092")
def test_an_ability_still_on_the_menu_is_detected_by_its_SLOT_not_a_cardId():
    """An ABILITY option carries **area/index** and no `cardId` at all, so matching on `cardId`
    returns False on every board (killing `body_ability_on_menu` and `result_ability_now`)."""
    fx = json.loads((FIXTURES / "dp_hold_evolve_until_typed_ready_f35.json").read_text(encoding="utf-8"))
    pilot = _pilot("dragapult_ex")
    assert pilot._ability_on_menu(fx["obs"], 120) is True     # Drakloak, at area 4 / index 0
    assert pilot._ability_on_menu(fx["obs"], 121) is False    # Dragapult ex is in HAND, not in play


# ── free development: a benched evolve at 0 is tier-0, not tier-4 (ADR-0070 amendment L, #167) ────

def _sequence(agent, fixture):
    """The real `_finish_turn_last` order for a fixture's MAIN menu."""
    fx = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
    pilot = _pilot(agent)
    pilot.evolve_value = True
    d = pilot.explain(fx["obs"])
    select = fx["obs"]["select"]
    options = select["option"]
    board = pilot._board(fx["obs"], select)
    by_score = sorted(range(len(options)), key=lambda i: -d.options[i].score)
    order = pilot._finish_turn_last(fx["obs"], board, options, d.options, by_score, 1,
                                    select.get("context"))
    return fx, d, options, order


@pytest.mark.req("REQ-GEN-0093")
def test_a_benched_evolve_priced_at_zero_is_free_development_not_a_turn_ender():
    """A same-line bench evolve nets exactly 0.0 (`_line_payoff_stat` pre-credits the pre-evolution
    with the LINE's payoff, so the deploy delta cancels), which a `score <= 0 -> tier 4` gate starves."""
    fx, d, options, order = _sequence("mega_starmie", "ms_free_bench_evolve_f17")
    ev = [i for i, o in enumerate(options)
          if o.get("type") == 9 and o.get("inPlayArea") != 4]
    ender = [i for i, o in enumerate(options) if o.get("type") in (13, 14)]
    assert ev, "fixture carries no benched evolve"
    assert all(d.options[i].score == 0.0 for i in ev), "fixture is meant to pin the ZERO case"
    for i in ev:
        assert order.index(i) < min(order.index(e) for e in ender), (
            f"benched evolve {i} sequenced at/after the turn-ender — it is free development")


@pytest.mark.req("REQ-GEN-0093")
def test_an_evolve_with_positive_shared_realization_stays_in_development_order():
    """The cheap attack makes f35 positive even though its expensive typed attack is mismatched."""
    fx, d, options, order = _sequence("dragapult_ex", "dp_hold_evolve_until_typed_ready_f35")
    ev = [i for i, o in enumerate(options) if o.get("type") == 9]
    assert ev and d.options[ev[0]].score > 0
    ender = [i for i, o in enumerate(options) if o.get("type") in (13, 14)]
    assert order.index(ev[0]) < min(order.index(e) for e in ender)


# ── tie-break: among EQUAL evolves, arm the payoff soonest (ADR-0070 amendment M, #167) ───────────

@pytest.mark.req("REQ-GEN-0094")
def test_equal_scored_evolves_order_by_the_results_arm_clock():
    """`deploy = result - body` cancels PER SLOT, so an energised and a bare body both price 0.0.
    The tie consults the one term that does NOT cancel: the RESULT's arm clock, lower = sooner."""
    from types import SimpleNamespace
    opts = [{"type": 9, "inPlayArea": 5, "inPlayIndex": 0},      # energised body
            {"type": 9, "inPlayArea": 5, "inPlayIndex": 1},      # bare body
            {"type": 14}]                                         # END
    def tr(score, arm):
        return SimpleNamespace(score=score,
                               evolve_working=None if arm is None else {"result": {"arm": arm}})
    pilot = _pilot("mega_starmie")

    # bare body sits FIRST by index; the tie-break must pull the sooner-arming one ahead
    traces = [tr(0.0, 3), tr(0.0, 2), tr(0.0, None)]
    assert pilot._prefer_soonest_arming_evolve([0, 1, 2], opts, traces)[:2] == [1, 0]

    # already in arm order -> unchanged (stable)
    traces = [tr(0.0, 2), tr(0.0, 3), tr(0.0, None)]
    assert pilot._prefer_soonest_arming_evolve([0, 1, 2], opts, traces)[:2] == [0, 1]

    # DIFFERENT scores are never reordered — the tie-break only breaks EXACT ties
    traces = [tr(5.0, 3), tr(0.0, 2), tr(0.0, None)]
    assert pilot._prefer_soonest_arming_evolve([0, 1, 2], opts, traces) == [0, 1, 2]

    # a non-evolve tied with an evolve is untouched: an evolve can never be promoted past it
    opts2 = [{"type": 7, "index": 0}, {"type": 9, "inPlayArea": 5, "inPlayIndex": 1}]
    traces2 = [tr(0.0, None), tr(0.0, 2)]
    assert pilot._prefer_soonest_arming_evolve([0, 1], opts2, traces2) == [0, 1]


@pytest.mark.req("REQ-GEN-0094")
def test_the_tied_evolves_need_not_be_ADJACENT_in_the_score_order():
    """A NON-evolve can sit between two tied evolves, so a consecutive-run tie-break never fires.
    The evolves are permuted within the positions they already occupy; non-evolves stay put."""
    from types import SimpleNamespace
    opts = [{"type": 9, "inPlayArea": 5, "inPlayIndex": 1},      # 0: bare body,      arm 3
            {"type": 7, "index": 0},                              # 1: a non-evolve
            {"type": 9, "inPlayArea": 5, "inPlayIndex": 0},      # 2: energised body, arm 2
            {"type": 14}]                                         # 3: END, lower score
    def tr(score, arm):
        return SimpleNamespace(score=score,
                               evolve_working=None if arm is None else {"result": {"arm": arm}})
    traces = [tr(0.0, 3), tr(0.0, None), tr(0.0, 2), tr(-5.0, None)]
    pilot = _pilot("mega_starmie")
    # in: evolve(arm3) @pos0, non-evolve @pos1, evolve(arm2) @pos2
    # out: the two evolves swap; the non-evolve does NOT move off position 1
    assert pilot._prefer_soonest_arming_evolve([0, 1, 2, 3], opts, traces) == [2, 1, 0, 3]
