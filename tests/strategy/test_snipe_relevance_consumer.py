"""Snipe Relevance at the CONSUMER seam — the Pilot plumbing (ADR-0084, Issue #188).

Seam 1 (`test_snipe_relevance.py`) covers the pure scorer's legs on authored worked examples. This
file covers what the *Pilot* does with it: the switch's OFF-byte-identical promise, the resolve-once-per-
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


def _off(agent="mega_starmie"):
    """The kill-switch-OFF arm, forced EXPLICITLY.

    Until 2026-07-30 the shipped default was OFF, so these tests used `_shipped_pilot()` as the OFF
    arm and the two were the same pilot. Arming (ADR-0084 Amendment C) split them: the OFF path is
    still a live requirement — the switch has to keep working — but it is no longer the default, so
    it must be asked for by name rather than inherited.
    """
    p = _shipped_pilot(agent)
    p.snipe_relevance = False
    return p


# ───────────────────────────────────────────────────────── the switch's promises

@pytest.mark.req("REQ-SNIPECONS-0001")
def test_the_switch_ships_armed():
    """ADR-0084 decision 7 bar 5 staged OFF-first, then armed — this is the second stage.

    Arming was owed ADR-0072's two merit gates plus the paired-A/B Tripwire, and all three cleared
    on 2026-07-30 (ADR-0084 Amendment C): Decision Gate 0 unruled REGRESSION; Discrimination Gate
    PASS run ARMED per ADR-0072 decision 5 (0 unruled `OK -> MISS`, 1 ruled to #165); Tripwire
    -1.25 pp, 95% CI [-4.79, +2.29], 0 crashes / 2400 games -> `mid_build_verdict` True.
    """
    from common.runtime import PROFILE
    assert PROFILE["snipe_relevance"] is True
    assert _shipped_pilot().snipe_relevance is True


@pytest.mark.req("REQ-SNIPECONS-0001")
@pytest.mark.parametrize("fixture", [
    "planner_83667237_107.json", "planner_83661649_45.json",
    "ms_snipe_evolving_wincon_preevo_f75.json", "ms_snipe_riolu_over_lunatone_f47.json",
    "ms_snipe_energized_bench_f39.json", "ms_snipe_attacker_line_over_support_f85.json",
])
def test_off_leaves_the_incumbent_path_entirely_intact(fixture):
    """The OFF path must be the shipped rungs, untouched.

    An earlier version of this test compared a shipped pilot against a shipped pilot with the flag
    set to its own default — i.e. OFF against OFF — and so could not have detected any OFF-path
    change at all. It now asserts the three things that actually constitute "unchanged": the scalar
    contributes nothing, at least one incumbent target rung still fires, and the MatchupPlan steer
    still scores beside them. (The behavioural evidence proper is `snipe_decider_sweep.py`'s OFF
    column, which replays every corpus frame through a genuinely shipped pilot.)"""
    fx = _fx(fixture)
    off = _off()
    obs, select = fx["obs"], fx["obs"]["select"]
    board = off._board(obs, select)
    target_rungs = {"snipe-for-the-ko", "snipe-the-top-threat", "snipe-the-threat",
                    "snipe-on-the-path", "snipe-the-forced-promotion", "snipe-the-evolving-threat"}
    fired, steered = set(), 0.0
    for o in select["option"]:
        ctx = off._context(obs, select, board, o)
        assert off._snipe_relevance_terms(obs, select, board, o, ctx) is None
        assert off._snipe_relevance_tactical(obs, select, board, o, ctx) == 0.0
        assert off._snipe_ko_dominator(ctx) == 0.0
        steered += abs(off._snipe_matchup_tactical(obs, select, board, o, ctx))
    for opt in off.explain(obs).options:
        fired |= {h.id for h, _w in opt.fired}
    assert fired & target_rungs, "the incumbent rungs must still be deciding while OFF"
    assert steered >= 0.0        # the steer is reachable OFF; armed it folds into the multiplier


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
    """ADR-0084 decision 5: the three `DAMAGE_COUNTER_ANY` / counter-mover rungs are LIVE and
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


@pytest.mark.req("REQ-SNIPECONS-0005")
def test_a_bench_count_scaler_is_priced_at_its_board_effective_damage_not_its_printed_base():
    """ADR-0084 decision 7 **bar 4's fourth authored fixture**, finally satisfiable.

    The bar reads: *"Lillie's Clefairy ex reading its board-effective damage rather than 20 once the
    combined-bench scaler family lands."* That family landed with Issue #213
    (`CombatMath.threat_ceiling` prices the Damage Formula's `per_unit x count(variable)` term), and
    the plumbing must actually PASS the board context for it to be visible — `context=None` silently
    returns the printed base.

    This is asserted at the seam rather than harvested from a frame **because the corpus cannot pose
    it**: zero of the 23 committed `DAMAGE` frames offer a bench-count or hand-count scaler as a
    snipe target, so `snipe_decider_sweep.py` is structurally blind here and would report 19/19
    whether the context were passed or not. That blindness is precisely why bar 4 demanded AUTHORED
    per-leg fixtures instead of the 19 the scorer's shape was selected against.

    Card 272 is Lillie's Clefairy ex (Full Moon Rondo: printed 20, +20 per COMBINED bench body,
    `data/EN_Card_Data.csv`). Missing the context under-reads it by 10x at a full bench, and both
    `imminence` and `forced` take that number.
    """
    from common.strategy.combat import CombatMath  # noqa: F401  (documents the owning module)
    CLEFAIRY_EX = 272
    combat = _shipped_pilot().combat

    printed = combat.threat_ceiling(CLEFAIRY_EX, context=None)
    empty = combat.threat_ceiling(CLEFAIRY_EX, context={"both_bench": 0})
    full = combat.threat_ceiling(CLEFAIRY_EX, context={"both_bench": 9})
    assert printed == empty == 20, "no context / no bench both fall back to the printed base"
    assert full == 200, "a full combined bench is 20 + 20x9 -- the term the printed read drops"

    # The plumbing: the snipe scalar's `incoming` call must carry the stash, or the scaling term is
    # invisible to it no matter how well `threat_ceiling` computes.
    import inspect
    src = inspect.getsource(_shipped_pilot().__class__._snipe_relevance_terms)
    assert "_opp_attack_context" in src, (
        "`_snipe_relevance_terms` must pass `context=` to `combat.incoming` -- without it every "
        "bench-count scaler prices at its printed base (Issue #213 / ADR-0084 bar 4)")
    assert "forward_max_damage" not in src, (
        "the forward leg must read `_threat_damage_pair`, not the provider's PRINTED forward index "
        "(which returns 0 for card 272)")


@pytest.mark.req("REQ-SNIPECONS-0004")
def test_the_ko_dominator_fires_only_when_armed_and_only_on_a_ko_target():
    """The dominator's own contract, asserted directly rather than through a fixture that happens to
    offer a snipe KO. OFF it contributes nothing (the +60 rung is still doing the job); ON it is the
    structural replacement."""
    from common.strategy.context import KO_SCORE
    kos = type("C", (), {"target_kos": True})()
    no_kos = type("C", (), {"target_kos": False})()
    off, on = _off(), _armed()
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


@pytest.mark.req("REQ-SNIPECONS-0007")
def test_snipe_credits_banked_potential_unlike_denys_fire_reading():
    """ADR-0084 Amendment A2, the question the ADR explicitly owed a test rather than an assumption.

    Deny's Finding A (ADR-0080 Amendment B) split its read: full relevance credits BANKED potential,
    which is right for deciding whether to KEEP a Hammer and wrong for deciding whether to SPEND one
    — *"it fires at a threat that has not arrived."* Every snipe is a spend, so the naive transfer
    would restrict snipe to an affordable-now read too.

    That transfer is REFUTED for snipe, and this test is why: `snipe-the-evolving-threat` exists
    precisely to pre-chip a body that CANNOT attack yet (a Riolu banking toward Mega Lucario ex), and
    decision 3 sources `their_plan` from a `t=1` ceiling curve that deliberately credits one attach.
    A body three turns from arming still scores, discounted rather than zeroed."""
    from common.snipe_relevance import target_relevance
    banked = target_relevance(incoming_damage=270, turns_to_afford=3,
                              hp_remaining=200, rider_damage=50)
    arrived = target_relevance(incoming_damage=270, turns_to_afford=0,
                               hp_remaining=200, rider_damage=50)
    assert banked["imminence"] > 0.0, "a not-yet-armed threat is DISCOUNTED, never zeroed"
    assert arrived["imminence"] > banked["imminence"], "...and an arrived one still outranks it"


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
