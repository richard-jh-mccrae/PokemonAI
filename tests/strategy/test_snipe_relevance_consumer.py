"""Snipe Relevance at the CONSUMER seam — the Pilot plumbing (ADR-0085, Issue #188).

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
    """The kill-switch-OFF arm, forced EXPLICITLY.

    Until 2026-07-30 the shipped default was OFF, so these tests used `_shipped_pilot()` as the OFF
    arm and the two were the same pilot. Arming (ADR-0085 Amendment C) split them: the OFF path is
    still a live requirement — the switch has to keep working — but it is no longer the default, so
    it must be asked for by name rather than inherited.
    """
    p = _shipped_pilot(agent)
    p.snipe_relevance = False
    return p


# ───────────────────────────────────────────────────────── the switch's promises

@pytest.mark.req("REQ-SNIPECONS-0001")
def test_the_switch_ships_armed():
    """ADR-0085 decision 7 bar 5 staged OFF-first, then armed — this is the second stage.

    Arming was owed ADR-0072's two merit gates plus the paired-A/B Tripwire, and all three cleared
    on 2026-07-30 (ADR-0085 Amendment C): Decision Gate 0 unruled REGRESSION; Discrimination Gate
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
def test_off_is_documented_degraded_mode_not_a_rollback(fixture):
    """What the kill-switch means AFTER ADR-0085's deletion pass.

    This test previously asserted the opposite — that OFF left the six incumbent target rungs
    deciding, byte-identical. That was the correct contract for the staging commit, and it is now
    obsolete: the rungs are DELETED (Issue #136 standing directive 1, "rungs an equation replaces are
    DELETED, not suppressed"), so OFF no longer has an incumbent to fall back to. It scores every
    bench target 0 and the argmax degenerates to option index.

    That is the same contract `attach_value` (19 rungs deleted), `evolve_value` (4) and
    `promote_retreat_value` (11) already carry in PROFILE: the switch survives as an incident lever,
    and OFF is DOCUMENTED DEGRADED MODE, never a rollback. Asserted so the degradation is a stated
    property somebody has to look at, rather than a surprise found in a game.
    """
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
def test_the_counter_rungs_are_retained_and_the_target_rungs_are_gone():
    """ADR-0085 decision 5, after the deletion pass, asserted in BOTH directions.

    The six DAMAGE(15) target rungs are DELETED — not stood down, not shadowed. The three counter
    rungs are deliberately RETAINED: disjoint select contexts (13/14/16/40 vs 15) so they never
    co-fired with a target rung, already derived from knapsack reads, and zero corpus frames to
    bench a rewrite against.

    The earlier version of this test asserted every target rung carried a `snipe_relevance_armed`
    stand-down. That guard is itself deleted (the Context field with it), which is why the assertion
    is now about ABSENCE — a stand-down flag is what staging looks like, and staging is over.
    """
    from common.strategy.baseline.baseline_snipe import HYPOTHESES
    counter = {"place-counter-to-convert", "move-counters-off-the-damaged", "move-max-counters"}
    ids = {h.id for h in HYPOTHESES}
    assert counter <= ids, "the counter rungs must survive the fold"
    assert not (ids & _DELETED_TARGET_RUNGS), "the six target rungs must be gone, not suppressed"
    assert ids == counter, "the snipe cluster is now exactly the counter family"
    # ...and no surviving rung may still reference the retired stand-down flag.
    assert not any("snipe_relevance_armed" in (h.when.__code__.co_names or ()) for h in HYPOTHESES)



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
def test_the_brief_tiebreak_orders_an_all_zero_menu_but_never_manufactures_a_preference():
    """ADR-0085 Amendment H — the Brief Tiebreak's own contract, asserted directly.

    Four claims, each a way the tiebreak could go wrong:

    1. it FIRES on an all-zero tie (the E3 case a multiplier cannot express) and the strict-maximum
       priority wins — this is the deliberate divergence from `_deny_strip_tiebreak`, which guards
       `not rel -> 0.0`;
    2. it is SILENT when the tied candidates share a priority, so no preference is invented where the
       Brief expresses none — the property that keeps decision 7's `81905522-75` recorded miss
       missing, since its two options are the SAME card and so carry the SAME role;
    3. it is SILENT when nothing is tied — relevance already decided;
    4. the bonus CANNOT overtake a difference relevance itself settled, because it is half the finest
       gap the menu draws.
    """
    from common.snipe_relevance import K, brief_tiebreak as _tiebreak
    pilot = _armed()

    # 1. the all-zero menu: the briefed body wins, the avoided one gets nothing
    allzero = [(0.0, 90.0), (0.0, -90.0)]
    assert _tiebreak(allzero, 0.0, 90.0) > 0, "must fire at relevance 0 (the E3 case)"
    assert _tiebreak(allzero, 0.0, -90.0) == 0.0, "only the strict maximum is ordered"
    # ...including neutral-over-avoid, which a `best > 0` guard would have dropped
    assert _tiebreak([(0.0, 0.0), (0.0, -90.0)], 0.0, 0.0) > 0, "neutral outranks `avoid`"

    # 2. identical priorities (the two same-card Riolu on 81905522-75) -> no preference manufactured
    same = [(0.385714, 90.0), (0.385714, 90.0)]
    assert _tiebreak(same, 0.385714, 90.0) == 0.0, "tied on the Brief too — stay silent"

    # 3. nothing tied -> relevance already decided
    assert _tiebreak([(0.5, 90.0), (0.2, 0.0)], 0.5, 90.0) == 0.0

    # 4. the bonus is strictly smaller than the finest distinction relevance draws, so ordering a tie
    #    can never overtake a real difference. Gap here is 0.1; the bonus must stay under K x 0.1.
    menu = [(0.3, 0.0), (0.4, 90.0), (0.4, 0.0)]
    assert 0 < _tiebreak(menu, 0.4, 90.0) < K * 0.1

    # The consumer must DELEGATE to this function rather than carry a second copy of the arithmetic.
    # Asserted BEHAVIOURALLY: an earlier draft checked `"brief_tiebreak" in getsource(...)`, which the
    # method's own `def` line satisfies, so it passed unconditionally and could never have caught a
    # reimplementation.
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
    """The tiebreak is part of the Snipe Relevance instrument and rides its switch — ADR-0085
    Amendment H declines to mint a second kill-switch for it (Issue #136 directive 1). OFF it must not
    reach the score at all, or the deleted rungs' replacement would be half-live on the degraded
    path."""
    fx = _fx("planner_83661649_45.json")
    off = _off()
    obs, select = fx["obs"], fx["obs"]["select"]
    board = off._board(obs, select)
    for o in select["option"]:
        ctx = off._context(obs, select, board, o)
        assert off._snipe_brief_tiebreak(obs, select, board, o, ctx) == 0.0


@pytest.mark.req("REQ-SNIPECONS-0006")
def test_the_tiebreak_does_raise_a_zero_score_and_that_is_safe_only_on_a_forced_select():
    """ADR-0072's Endorsement Claim asks *is this slot taken at all*, against `score > 0`.

    An earlier draft of this test asserted the tiebreak *cannot* flip such a claim, on a corpus
    fixture — and it was VACUOUS twice over: that board draws no relevance tie (peers price
    `[0.0, 0.375]`), so every bonus was 0.0 and the assertion passed with the feature deleted; and it
    never computed a score or evaluated a claim at all. The honest statement is the opposite of what
    it claimed, so it is asserted here in that direction instead.

    The tiebreak **does** turn a flat `0.0` into a small positive on the winning option — that is
    precisely its job on the all-zero menu Amendment E3 describes. What makes it safe is a RULES fact,
    not a code fact: `DAMAGE` (SelectContext 15) is a **forced** select. The engine is asking which
    target, not whether to snipe, so every option is already being taken and no `score > 0` threshold
    decides participation. Asserted rather than assumed, because the safety rests entirely on the
    select's kind — a future context reusing this term would not inherit it.
    """
    from common.strategy.context import _DAMAGE
    from common.snipe_relevance import brief_tiebreak

    # It raises a zero. Stated plainly, because the guarantee is about WHERE it may do so.
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
    """The tiebreak is peer-relative, so a naive implementation rebuilds every rival's Context on
    every option — O(n^2) `_context` per decision. The peer list is cached per decision beside
    `_snipe_relevance_cache`, and `_board()` resets it."""
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
    """ADR-0085 decision 7 **bar 4's fourth authored fixture**, finally satisfiable.

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
        "bench-count scaler prices at its printed base (Issue #213 / ADR-0085 bar 4)")
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
    """ADR-0085 Amendment A2, the question the ADR explicitly owed a test rather than an assumption.

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
