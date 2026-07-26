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
