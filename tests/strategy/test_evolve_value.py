"""Evolve DECIDER on real frames (common/evolve_value.py) — ADR-0070, #140.

The equation's per-option TERM row, read off `OptionTrace.evolve_working` with the decider's
kill-switch forced ON. These assert it RANKS the corpus frames correctly — the design proof that
must hold before the `baseline_evolution` rungs are deleted. The algebra itself is pinned at the
pure-function seam (`test_evolve_decider.py`); this is the same claims through the real Pilot.

Card facts verified at source (data/EN_Card_Data.csv): Drakloak (120) HP 90, Dragon Headbutt {R}{P}
70, Recon Directive "top 2, put 1 in hand"; Dragapult ex (121) HP 320, Phantom Dive {R}{P} 200 —
the IDENTICAL cost that makes the doctrine derive.
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


def test_hold_the_income_off_unready_evolve_f35():
    """f35: Drakloak→Dragapult on {R}{D} — a wincon that CAN'T pay Phantom Dive {R}{P}, forfeiting the
    Recon stream. deploy is the UNREADY tier and the income loss nets it low — below the Recon ability
    (~+18), so once the equation drives the score the premature evolve is suppressed (hold)."""
    fx, d, evolve = _shadows("dragapult_ex", "dp_hold_evolve_until_typed_ready_f35")
    (only_evolve,) = evolve.values()
    assert only_evolve < 18, evolve            # below the Recon dig — will not be chosen
    assert only_evolve < 40                     # far below a READY-wincon deploy (the old flat +40 bug)


def test_which_body_prefers_the_energized_f82():
    """f82: two mid-line Dreepy→Drakloak evolves — the equation must prefer the ACTIVE body.

    PROMOTED from strict-xfail to PIN by ADR-0071 (#163). It was xfailed on the reading that the
    frame is a Turn-Planner maneuver and the standalone deploy `30.0 Active vs 37.5 benched` was
    CORRECT (ADR-0070 amendment C). **That 37.5 was the shared-budget inflation.** The bench held
    Dreepy 50, Dunsparce 50, Dreepy 50 against a 60 spread, so evolving one Dreepy out of range
    merely redirected the counters onto the other — it bought nothing. With the Harvest read at
    UNAVOIDABLE both bodies read `ko = 2`, so evolving buys exactly ZERO survival: the benched
    option falls to **25.0** against the Active's **30.0** (measured), and the equation reaches the
    human's answer on its own terms. The residual 25.0 is deploy value that is not the survival leg
    — the inflation removed is the 37.5 -> 25.0, not the whole score.

    The maneuver claim itself is untouched and still belongs to #165: the chain is a better play for
    a reason no single-action equation can see. What is discharged is the CROSS-LAYER REQUIREMENT
    this xfail carried — the pin no longer depends on a lethal tier reaching a counter-moving
    Ability, because it no longer depends on the inflated benched credit."""
    fx, d, evolve = _shadows("dragapult_ex", "dp_evolve_energized_line_body_first_f82")
    best = max(evolve, key=evolve.get)
    assert best == fx["correct"][0], evolve


def test_advance_the_line_beats_spreading_f29():
    """f29: advancing the started line (evolve Drakloak) out-values a spread attach onto a bare base."""
    fx, d, evolve = _shadows("dragapult_ex", "dp_charge_the_line_f29")
    assert evolve[fx["correct"][0]] > 0
    # The DECISION is the claim. Since the attach swap (#139, ADR-0069) an attach's score is a real
    # damage currency rather than a flat rung, so a build step can out-NUMBER an evolve rung — and it
    # no longer needs to lose on score to lose the turn: free development is tier 0 and the
    # irreversible attach is tier 2, so the evolve is taken first and the attach follows.
    assert d.chosen == fx["correct"], (
        f"the evolve lost the turn to a non-evolve option: chosen={d.chosen}, correct={fx['correct']}")


# ── the income half must actually COMPUTE (ADR-0070 amendment K, #167) ────────────────────────────

@pytest.mark.req("REQ-GEN-0091")
def test_the_dig_income_term_is_not_structurally_dead():
    """`_evolve_income_delta` was IDENTICALLY ZERO on every board — measured across the whole
    corpus, 49 priced evolve options on 31 frames returned a non-zero income term exactly 0 times.

    The cause: `mine.deck_energy_counts` holds `CountTriple`s, which deliberately refuse to be bare
    numbers (ADR-0068: "a consumer must NAME its epistemic"). The value went straight into
    `draw_hit_probability`, whose `int(copies)` raised TypeError into its own documented
    "bad input -> 0.0" guard — so §3's odds read, §7's split-horizon loss and amendment B's `typed=`
    fix all silently computed nothing.

    f35 is the case: the machinery correctly identifies that a **{P}** is the enabler the Drakloak's
    line lacks (Phantom Dive / Dragon Headbutt are both {R}{P} while it holds {R}{D}), with ~2.6
    expected copies left in a 39-card deck — and then threw that answer away. Recon Directive digs 2,
    so the hold has to be worth something."""
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
    """`_ability_on_menu` matched `option["cardId"]`, but an ABILITY option carries **area/index**
    and no `cardId` at all — so it returned False on every board ever. Two ADR-0070 inputs died with
    it: `body_ability_on_menu` (§7's "this turn's use is forfeit" half of the split-horizon loss) and
    `result_ability_now` (which un-halves an income gain that fires THIS turn).

    f35's menu carries `{'area': 4, 'index': 0, 'type': 10}` — the Active Drakloak's Recon Directive,
    demonstrably unused this turn. The docstring's intent ("the MENU is the fact") was right; the key
    was wrong."""
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
    """`_finish_turn_last`'s tier 0 already NAMES this: "free informative development — draw /
    search, fill the Bench, **evolve a benched Pokémon**". The `score <= 0 -> tier 4` gate starved
    it, because a same-line bench evolve nets to exactly 0.0 (the pre-evolution is pre-credited with
    the LINE's payoff by `_line_payoff_stat`, so the deploy delta cancels).

    Measured cost of that on 82229122|0|decision|17 (#167's sitting): the agent never evolves the
    Staryu, so its turn ends with three bare 70 HP Staryu instead of a 330 HP Mega Starmie ex."""
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
def test_an_evolve_that_MEASURABLY_weakens_the_board_stays_last():
    """The other half of the ruling: only a move that strengthens the board rides the exemption.
    f35's Drakloak -> Dragapult ex forfeits Recon Directive while the body still cannot pay Phantom
    Dive {R}{P} on {R}{D}, which the income half now prices at **-30.36**. Negative, so it stays a
    tier-4 option and the exemption must not rescue it."""
    fx, d, options, order = _sequence("dragapult_ex", "dp_hold_evolve_until_typed_ready_f35")
    ev = [i for i, o in enumerate(options) if o.get("type") == 9]
    assert ev and d.options[ev[0]].score < 0, "f35's evolve must be priced as a weakening"
    ender = [i for i, o in enumerate(options) if o.get("type") in (13, 14)]
    assert order.index(ev[0]) >= min(order.index(e) for e in ender), (
        "a board-weakening evolve must not ride the free-development exemption")


# ── tie-break: among EQUAL evolves, arm the payoff soonest (ADR-0070 amendment M, #167) ───────────

@pytest.mark.req("REQ-GEN-0094")
def test_equal_scored_evolves_order_by_the_results_arm_clock():
    """`evolve-the-energized-body-first` was RETIRED by the 1b swap on the premise that the equation
    subsumes it. It does not: `deploy = result - body` cancels PER SLOT, independently of how much
    Energy sits there, so an energised Staryu and a bare one both price at exactly 0.0 and the tie
    breaks by option INDEX.

    Measured on 81905522|0|decision|64 — the board is read correctly and freshly (after the attach,
    bench0's arm drops 3 -> 2 while bench1 stays 3); the delta simply erases it. So the ordering
    consults the one term that does NOT cancel: the RESULT's arm clock. Lower = arms sooner = put the
    evolution where the Energy already is."""
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
    """The real shape, and the one an adjacent-only implementation silently misses. On
    81905522|0|decision|64 the equal-score run is `[2, 0, 1, 6]` — a NON-evolve sits between the two
    evolves — so a "consecutive run" tie-break never forms a run and never fires, which is exactly
    how the first version of this passed its unit test while leaving the real frame broken.

    The evolves are permuted within the positions they already occupy; every non-evolve stays put."""
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
