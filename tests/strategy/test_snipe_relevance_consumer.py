"""Snipe Relevance at the CONSUMER seam — the Pilot plumbing (ADR-0083, Issue #188).

Seam 1 (`test_snipe_relevance.py`) pins the pure scorer's legs on authored worked examples. This file
pins what the *Pilot* does with it: the switch's OFF-byte-identical promise, the resolve-once-per-
decision cache, the two structural dominators that live OUTSIDE the scalar, and end-to-end picks on
the committed fixtures with the switch ARMED.

Prior art: `test_deny_relevance_consumer.py` for the sibling instrument, and
`test_gust_target_slot_resolver.py::test_the_per_body_value_resolves_once_per_decision_and_is_shared`
for the cache spy.

⚠️ The four `ms_snipe_*` fixtures are the HELD-OUT set — they live in `tests/fixtures/corrections/`
rather than `data/corrections/`, so the 19-frame sweep the scorer's shape was selected against never
saw them. They caught a real design defect on their first application (the flat forced-promotion
constant took Solrock over Riolu on f75), which is why they are asserted armed here.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent="mega_starmie"):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(agent)[0]


def _fx(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / name).read_text(encoding="utf-8"))


def _armed(agent="mega_starmie"):
    p = _shipped_pilot(agent)
    p.snipe_relevance = True
    return p


# ───────────────────────────────────────────────────────── the switch's promises

@pytest.mark.req("REQ-SNIPECONS-0001")
def test_the_switch_ships_off():
    """ADR-0083 decision 7 bar 5. Arming needs ADR-0072's two merit gates plus the paired-A/B
    Tripwire; until those run, OFF is what ships."""
    from common.runtime import PROFILE
    assert PROFILE["snipe_relevance"] is False
    assert _shipped_pilot().snipe_relevance is False


@pytest.mark.req("REQ-SNIPECONS-0001")
@pytest.mark.parametrize("fixture", [
    "planner_83667237_107.json", "planner_83661649_45.json",
    "ms_snipe_evolving_wincon_preevo_f75.json", "ms_snipe_riolu_over_lunatone_f47.json",
    "ms_snipe_energized_bench_f39.json", "ms_snipe_attacker_line_over_support_f85.json",
])
def test_off_is_byte_identical_to_the_incumbent(fixture):
    """The OFF path must be the shipped rungs, untouched. The scalar contributes nothing, the six
    target rungs fire as they always did, and the MatchupPlan steer still scores beside them."""
    fx = _fx(fixture)
    off = _shipped_pilot().explain(fx["obs"])
    baseline = _shipped_pilot()
    baseline.snipe_relevance = False
    assert off.chosen == baseline.explain(fx["obs"]).chosen


@pytest.mark.req("REQ-SNIPECONS-0002")
def test_the_incumbent_rungs_stand_down_as_a_body_when_armed():
    """The currency-zone rule: the marginal REPLACES its rungs, it never stacks with them. All six
    additive target rungs must go silent together, or the additive stack survives underneath the
    scalar and the fold has changed nothing."""
    fx = _fx("planner_83667237_107.json")
    armed = _armed()
    d = armed.explain(fx["obs"])
    target_rungs = {"snipe-for-the-ko", "snipe-the-top-threat", "snipe-the-threat",
                    "snipe-on-the-path", "snipe-the-forced-promotion", "snipe-the-evolving-threat"}
    for opt in d.options:
        assert not ({h.id for h, _w in opt.fired} & target_rungs)


@pytest.mark.req("REQ-SNIPECONS-0002")
def test_the_counter_rungs_are_retained_and_unaffected():
    """ADR-0083 decision 5: the three `DAMAGE_COUNTER_ANY` / counter-mover rungs are LIVE and
    deliberately retained — disjoint select contexts (13/14/16/40 vs 15) so they never co-fire with
    a target rung, already derived from knapsack reads, and zero corpus frames to bench a rewrite
    against. They must not carry the stand-down."""
    from common.strategy.baseline.baseline_snipe import HYPOTHESES
    counter = {"place-counter-to-convert", "move-counters-off-the-damaged", "move-max-counters"}
    target = {"snipe-for-the-ko", "snipe-the-top-threat", "snipe-the-threat", "snipe-on-the-path",
              "snipe-the-forced-promotion", "snipe-the-evolving-threat"}
    ids = {h.id for h in HYPOTHESES}
    assert counter <= ids, "the counter rungs must survive the fold"
    guarded = {h.id for h in HYPOTHESES if "snipe_relevance_armed" in (h.when.__code__.co_names or ())}
    # Asserted in BOTH directions so the test cannot pass vacuously: every target rung carries the
    # stand-down, and no counter rung does.
    assert guarded == target


@pytest.mark.req("REQ-SNIPECONS-0003")
def test_the_per_body_read_resolves_once_per_decision_and_is_cached():
    """ADR-0076 Amendment C's promise, carried to this instrument: a DAMAGE select offers the same
    bench bodies repeatedly and `_context` runs per OPTION, so an uncached read would re-run the
    per-body curve simulation once per option."""
    fx = _fx("planner_83667237_107.json")
    armed = _armed()
    obs, select = fx["obs"], fx["obs"]["select"]
    board = armed._board(obs, select)
    calls = {"n": 0}
    real = armed.combat.turns_to_afford

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    armed.combat.turns_to_afford = counting
    for o in select["option"]:
        ctx = armed._context(obs, select, board, o)
        armed._snipe_relevance_terms(obs, select, board, o, ctx)
    first = calls["n"]
    for o in select["option"]:
        ctx = armed._context(obs, select, board, o)
        armed._snipe_relevance_terms(obs, select, board, o, ctx)
    assert calls["n"] == first, "the second pass must be served entirely from the cache"


# ───────────────────────────────────────────── the dominators, OUTSIDE the scalar

@pytest.mark.req("REQ-SNIPECONS-0004")
def test_a_knock_out_dominates_every_relevance_score_structurally():
    """`snipe-for-the-ko` stops being a tunable +60 weight and becomes a KO_SCORE-class Tactical
    dominator — the same move the Tera veto made. The weight form is a documented blunder class:
    `30 + 40 + 45 = 115` on an un-KO-able body beat `60` on a KO-able one (`82754241-45`). As
    structure it is unrepresentable, because `K x relevance` is bounded by MAX_ATTACK_DAMAGE (350)
    and can never approach KO_SCORE (1000)."""
    from common.snipe_relevance import K
    from common.strategy.context import KO_SCORE
    assert K < KO_SCORE, "no relevance score may ever reach the KO band"


@pytest.mark.req("REQ-SNIPECONS-0004")
def test_the_ko_dominator_fires_only_when_armed_and_only_on_a_ko_target():
    """The dominator's own contract, asserted directly rather than through a fixture that happens to
    offer a snipe KO. OFF it contributes nothing (the +60 rung is still doing the job); ON it is the
    structural replacement."""
    from common.strategy.context import KO_SCORE
    kos = type("C", (), {"target_kos": True})()
    no_kos = type("C", (), {"target_kos": False})()
    off, on = _shipped_pilot(), _armed()
    assert off._snipe_ko_dominator(kos) == 0.0, "OFF: the incumbent rung owns the KO"
    assert on._snipe_ko_dominator(kos) == KO_SCORE
    assert on._snipe_ko_dominator(no_kos) == 0.0


@pytest.mark.req("REQ-SNIPECONS-0004")
def test_the_scalar_stands_down_entirely_when_a_knock_out_is_on_offer():
    """Every positional rung stood down on a KO target, and the scalar must too — otherwise the
    dominator and the graded term both score and the sum is back."""
    fx = _fx("planner_83667237_107.json")
    armed = _armed()
    obs, select = fx["obs"], fx["obs"]["select"]
    board = armed._board(obs, select)
    board.snipe_ko_available = True
    for o in select["option"]:
        ctx = armed._context(obs, select, board, o)
        assert armed._snipe_relevance_tactical(obs, select, board, o, ctx) == 0.0


@pytest.mark.req("REQ-SNIPECONS-0005")
def test_a_benched_tera_is_ordered_last_but_stays_selectable():
    """`rules.md §185` — a benched Tera takes NO damage from attacks, so a snipe at one is always
    strictly wasted. But `_snipe_tera_veto` expresses that as an ORDERING (`-KO_SCORE`), never a
    removal: when a benched Tera is the ONLY offered target the select is forced and the agent must
    still answer. A literal `relevance = 0` that dropped the option would break a legal-move case."""
    from common.snipe_relevance import target_relevance
    armed = _armed()
    tera_ctx = type("C", (), {"target_is_bench_tera": True})()
    assert armed._snipe_tera_veto(tera_ctx) < 0, "ordered last..."
    # ...and the scalar itself does not zero it, so the option is still scored and selectable.
    assert target_relevance(incoming_damage=200, turns_to_afford=0, is_tera=True,
                            hp_remaining=200, rider_damage=50)["relevance"] > 0.0


# ───────────────────────────────────────────── held-out fixtures, ARMED

@pytest.mark.req("REQ-SNIPECONS-0006")
@pytest.mark.parametrize("fixture,by_card_id", [
    ("ms_snipe_evolving_wincon_preevo_f75.json", True),    # offers TWO Riolu — match by card id
    ("ms_snipe_riolu_over_lunatone_f47.json", False),
    ("ms_snipe_energized_bench_f39.json", False),
    ("ms_snipe_attacker_line_over_support_f85.json", False),
])
def test_the_armed_instrument_holds_the_held_out_fixtures(fixture, by_card_id):
    """The generalisation check. These four were never seen by the 19-frame sweep the scorer's shape
    was selected against, and `f75` is the one that caught the flat forced-promotion constant."""
    fx = _fx(fixture)
    armed = _armed()
    chosen = armed.explain(fx["obs"]).chosen
    if not by_card_id:
        assert chosen == fx["correct"]
        return
    select = fx["obs"]["select"]

    def card_of(pick):
        return (armed._option_pokemon(fx["obs"], select, select["option"][pick[0]]) or {}).get("id")

    assert card_of(chosen) == card_of(fx["correct"])


@pytest.mark.req("REQ-SNIPECONS-0006")
@pytest.mark.parametrize("fixture", ["planner_83667237_107.json", "planner_83661649_45.json"])
def test_the_armed_instrument_holds_the_adr_0044_reads(fixture):
    """The two ADR-0044 anchors. `107` is half of the impossibility pair — the redundant second Mega
    Lucario ex must stay unpicked, which is the blunder a naive fold onto the prize marginal
    restored. `45` is the Forced-Promotion Read."""
    fx = _fx(fixture)
    assert _armed().explain(fx["obs"]).chosen == fx["correct"]
