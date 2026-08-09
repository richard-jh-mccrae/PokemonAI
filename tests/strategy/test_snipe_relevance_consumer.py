"""Snipe Relevance at the CONSUMER seam — the Pilot plumbing (ADR-0085, Issue #188).

`test_snipe_relevance.py` covers the pure scorer's legs; this covers the switch, the per-decision
caches, the structural dominators that live OUTSIDE the scalar, and end-to-end picks when ARMED.

⚠️ The four `ms_snipe_*` fixtures are the HELD-OUT set: they live in `tests/fixtures/corrections/`
rather than `data/corrections/`, so the sweep the scorer's shape was selected against never saw them.
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


#: The six DAMAGE(15) target rungs ADR-0085 deleted — named once so both directions can assert it.
_DELETED_TARGET_RUNGS = frozenset({
    "snipe-for-the-ko", "snipe-the-top-threat", "snipe-the-threat", "snipe-on-the-path",
    "snipe-the-forced-promotion", "snipe-the-evolving-threat"})


def _fx(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / name).read_text(encoding="utf-8"))


def _armed(agent="mega_starmie"):
    p = _shipped_pilot(agent)
    p.snipe_relevance = True
    return p


def _off(agent="mega_starmie"):
    """The OFF arm, forced EXPLICITLY — the shipped default is ARMED, so OFF cannot be inherited."""
    p = _shipped_pilot(agent)
    p.snipe_relevance = False
    return p


# ───────────────────────────────────────────────────────── the switch's promises

@pytest.mark.req("REQ-SNIPECONS-0001")
def test_the_switch_ships_armed():
    """ADR-0085 decision 7 bar 5 staged OFF-first, then armed (Amendment C) — this is stage two."""
    from common.runtime import PROFILE
    assert PROFILE["snipe_relevance"] is True
    assert _shipped_pilot().snipe_relevance is True


@pytest.mark.req("REQ-SNIPECONS-0001")
@pytest.mark.parametrize("fixture", [
    "planner_83667237_107.json", "planner_83661649_45.json",
    "ms_snipe_evolving_wincon_preevo_f75.json", "ms_snipe_riolu_over_lunatone_f47.json",
    "ms_snipe_energized_bench_f39.json", "ms_snipe_attacker_line_over_support_f85.json",
])
def test_off_is_documented_degraded_mode_not_a_rollback(fixture):
    """The rungs are DELETED, so OFF has no incumbent to fall back to: it scores every bench target 0
    and the argmax degenerates to option index. An incident lever, never a rollback."""
    fx = _fx(fixture)
    off = _off()
    obs, select = fx["obs"], fx["obs"]["select"]
    board = off._board(obs, select)
    for o in select["option"]:
        ctx = off._context(obs, select, board, o)
        assert off._snipe_relevance_terms(obs, select, board, o, ctx) is None
        assert off._snipe_relevance_tactical(obs, select, board, o, ctx) == 0.0
        assert off._snipe_ko_dominator(ctx) == 0.0
    fired = set()
    for opt in off.explain(obs).options:
        fired |= {h.id for h, _w in opt.fired}
    assert not (fired & _DELETED_TARGET_RUNGS), "the deleted rungs must not come back"


@pytest.mark.req("REQ-SNIPECONS-0002")
def test_the_incumbent_rungs_stand_down_as_a_body_when_armed():
    """The marginal REPLACES its rungs, never stacks with them — one surviving rung means the
    additive stack lives on underneath the scalar."""
    fx = _fx("planner_83667237_107.json")
    armed = _armed()
    d = armed.explain(fx["obs"])
    target_rungs = {"snipe-for-the-ko", "snipe-the-top-threat", "snipe-the-threat",
                    "snipe-on-the-path", "snipe-the-forced-promotion", "snipe-the-evolving-threat"}
    for opt in d.options:
        assert not ({h.id for h, _w in opt.fired} & target_rungs)





@pytest.mark.req("REQ-SNIPECONS-0003")
def test_the_per_body_read_resolves_once_per_decision_and_is_cached():
    """A DAMAGE select offers the same bodies repeatedly and `_context` runs per OPTION, so an
    uncached read re-runs the per-body curve simulation once per option (ADR-0076 Amdt C)."""
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
    """A KO_SCORE-class Tactical dominator, not a tunable weight: `K x relevance` is bounded by
    MAX_ATTACK_DAMAGE, so no sum of positional claims can reach the KO band."""
    from common.snipe_relevance import K
    from common.strategy.context import KO_SCORE
    assert K < KO_SCORE, "no relevance score may ever reach the KO band"


@pytest.mark.req("REQ-SNIPECONS-0005")
def test_the_brief_tiebreak_orders_an_all_zero_menu_but_never_manufactures_a_preference():
    """ADR-0085 Amendment H. Firing on an all-zero tie is the deliberate divergence from
    `_deny_strip_tiebreak`, which guards `not rel -> 0.0`."""
    from common.snipe_relevance import K, brief_tiebreak as _tiebreak
    pilot = _armed()

    # 1. the all-zero menu: the briefed body wins, the avoided one gets nothing
    allzero = [(0.0, 90.0), (0.0, -90.0)]
    assert _tiebreak(allzero, 0.0, 90.0) > 0, "must fire at relevance 0 (the E3 case)"
    assert _tiebreak(allzero, 0.0, -90.0) == 0.0, "only the strict maximum is ordered"
    # ...including neutral-over-avoid, which a `best > 0` guard would have dropped
    assert _tiebreak([(0.0, 0.0), (0.0, -90.0)], 0.0, 0.0) > 0, "neutral outranks `avoid`"

    # 2. identical priorities -> no preference manufactured where the Brief expresses none
    same = [(0.385714, 90.0), (0.385714, 90.0)]
    assert _tiebreak(same, 0.385714, 90.0) == 0.0, "tied on the Brief too — stay silent"

    # 3. nothing tied -> relevance already decided
    assert _tiebreak([(0.5, 90.0), (0.2, 0.0)], 0.5, 90.0) == 0.0

    # 4. the bonus is strictly smaller than the finest distinction relevance draws, so ordering a tie
    #    can never overtake a real difference. Gap here is 0.1; the bonus must stay under K x 0.1.
    menu = [(0.3, 0.0), (0.4, 90.0), (0.4, 0.0)]
    assert 0 < _tiebreak(menu, 0.4, 90.0) < K * 0.1

    # Delegation asserted BEHAVIOURALLY: a `"brief_tiebreak" in getsource(...)` check is satisfied by
    # the method's own `def` line, so it passes unconditionally and never catches a reimplementation.
    import common.snipe_relevance as srel
    fx = _fx("planner_83661649_45.json")
    obs, select = fx["obs"], fx["obs"]["select"]
    board = pilot._board(obs, select)
    calls = []
    real = srel.brief_tiebreak
    srel.brief_tiebreak = lambda *a, **k: (calls.append(a) or real(*a, **k))
    try:
        for o in select["option"]:
            pilot._snipe_brief_tiebreak(obs, select, board, o,
                                        pilot._context(obs, select, board, o))
    finally:
        srel.brief_tiebreak = real
    assert calls, "the Pilot must route through `snipe_relevance.brief_tiebreak`, not reimplement it"


@pytest.mark.req("REQ-SNIPECONS-0006")
def test_the_brief_tiebreak_is_silent_when_the_instrument_is_off():
    """The tiebreak rides the instrument's switch; ADR-0085 Amendment H mints no second one."""
    fx = _fx("planner_83661649_45.json")
    off = _off()
    obs, select = fx["obs"], fx["obs"]["select"]
    board = off._board(obs, select)
    for o in select["option"]:
        ctx = off._context(obs, select, board, o)
        assert off._snipe_brief_tiebreak(obs, select, board, o, ctx) == 0.0


@pytest.mark.req("REQ-SNIPECONS-0006")
def test_the_tiebreak_does_raise_a_zero_score_and_that_is_safe_only_on_a_forced_select():
    """ADR-0072's Endorsement Claim asks `score > 0`, so raising a zero is safe only because `DAMAGE`
    is a FORCED select — a RULES fact a future context reusing this term would NOT inherit."""
    from common.strategy.context import _DAMAGE
    from common.snipe_relevance import brief_tiebreak

    allzero = [(0.0, 90.0), (0.0, 0.0)]
    assert brief_tiebreak(allzero, 0.0, 90.0) > 0.0, "the E3 fix necessarily makes a 0 score positive"
    assert brief_tiebreak(allzero, 0.0, 0.0) == 0.0, "and only for the strict maximum"

    # The safety condition: every select this term reaches is the forced DAMAGE pick.
    for name in ("planner_83661649_45.json", "planner_83667237_107.json",
                 "ms_snipe_energized_bench_f39.json"):
        assert _fx(name)["obs"]["select"].get("context") == _DAMAGE, (
            "the tiebreak's Endorsement-Claim safety argument holds only on a FORCED select")


@pytest.mark.req("REQ-SNIPECONS-0006")
def test_the_peer_list_resolves_once_per_decision():
    """The tiebreak is peer-relative, so a naive implementation is O(n^2) `_context` per decision."""
    fx = _fx("planner_83661649_45.json")
    armed = _armed()
    obs, select = fx["obs"], fx["obs"]["select"]
    board = armed._board(obs, select)
    assert armed._snipe_peer_cache is None, "_board() must reset the per-decision cache"
    first = armed._snipe_brief_peers(obs, select, board)
    assert armed._snipe_peer_cache is first
    assert armed._snipe_brief_peers(obs, select, board) is first, "resolved once, then shared"


@pytest.mark.req("REQ-SNIPECONS-0005")
def test_a_bench_count_scaler_is_priced_at_its_board_effective_damage_not_its_printed_base():
    """`threat_ceiling(context=None)` silently returns the PRINTED base, so the plumbing must pass
    the board context. Asserted at the seam because no committed `DAMAGE` frame poses a scaler."""
    from common.strategy.combat import CombatMath  # noqa: F401  (documents the owning module)
    CLEFAIRY_EX = 272
    combat = _shipped_pilot().combat

    printed = combat.threat_ceiling(CLEFAIRY_EX, context=None)
    empty = combat.threat_ceiling(CLEFAIRY_EX, context={"both_bench": 0})
    full = combat.threat_ceiling(CLEFAIRY_EX, context={"both_bench": 9})
    assert printed == empty == 20, "no context / no bench both fall back to the printed base"
    assert full == 200, "a full combined bench is 20 + 20x9 -- the term the printed read drops"

    # The scalar's `incoming` call must carry the stash, or the scaling term is invisible to it no
    # matter how well `threat_ceiling` computes.
    import inspect
    src = inspect.getsource(_shipped_pilot().__class__._snipe_relevance_terms)
    assert "_opp_attack_context" in src, (
        "`_snipe_relevance_terms` must pass `context=` to `combat.incoming` -- without it every "
        "bench-count scaler prices at its printed base (Issue #213 / ADR-0085 bar 4)")
    assert "forward_max_damage" not in src, (
        "the forward leg must read `_threat_damage_pair`, not the provider's PRINTED forward index "
        "(which returns 0 for card 272)")


@pytest.mark.req("REQ-SNIPECONS-0004")
def test_the_ko_dominator_fires_only_when_armed_and_only_on_a_ko_target():
    from common.strategy.context import KO_SCORE
    kos = type("C", (), {"target_kos": True})()
    no_kos = type("C", (), {"target_kos": False})()
    off, on = _off(), _armed()
    assert off._snipe_ko_dominator(kos) == 0.0, "OFF: the incumbent rung owns the KO"
    assert on._snipe_ko_dominator(kos) == KO_SCORE
    assert on._snipe_ko_dominator(no_kos) == 0.0


@pytest.mark.req("REQ-SNIPECONS-0004")
def test_the_scalar_stands_down_entirely_when_a_knock_out_is_on_offer():
    """Otherwise the dominator and the graded term both score, and the sum is back."""
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
    """`rules.md §185`. `_snipe_tera_veto` is an ORDERING (`-KO_SCORE`), never a removal: a lone
    benched Tera is a FORCED select and the agent must still answer."""
    from common.snipe_relevance import MyRouteInputs, TheirPlanInputs, target_relevance
    armed = _armed()
    tera_ctx = type("C", (), {"target_is_bench_tera": True})()
    assert armed._snipe_tera_veto(tera_ctx) < 0, "ordered last..."
    # ...and the scalar itself does not zero it, so the option is still scored and selectable.
    scored = target_relevance(
        plan=TheirPlanInputs(incoming_damage=200, turns_to_afford=0, is_tera=True),
        route=MyRouteInputs(hp_remaining=200, rider_damage=50))
    assert scored["relevance"] > 0.0


@pytest.mark.req("REQ-SNIPECONS-0007")
def test_snipe_credits_banked_potential_unlike_denys_fire_reading():
    """ADR-0085 Amendment A2 REFUTES the transfer of deny's affordable-now read: pre-chipping a body
    that cannot attack yet is the whole point, so `their_plan` reads a `t=1` ceiling curve."""
    from common.snipe_relevance import MyRouteInputs, TheirPlanInputs, target_relevance
    route = MyRouteInputs(hp_remaining=200, rider_damage=50)
    banked = target_relevance(plan=TheirPlanInputs(incoming_damage=270, turns_to_afford=3),
                              route=route)
    arrived = target_relevance(plan=TheirPlanInputs(incoming_damage=270, turns_to_afford=0),
                               route=route)
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
    """The two ADR-0044 anchors: half of the impossibility pair, and the Forced-Promotion Read."""
    fx = _fx(fixture)
    assert _armed().explain(fx["obs"]).chosen == fx["correct"]
