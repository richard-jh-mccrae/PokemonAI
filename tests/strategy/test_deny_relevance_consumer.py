"""Deny Relevance, the CONSUMER half — the three deny surfaces reading the read (ADR-0080, Issue #187).

Issue #199 shipped `common/deny_relevance.py` and `Pilot._relevance_terms` compute-only, behind
`deny_relevance`, with nothing consuming them. This file pins what Issue #187 wired up: the keep
price, the fire-now rung and the target pick all scoring off relevance instead of the ADR-0062 damage
magnitude.

`test_deny_relevance.py` pins the READ (REQ-DENYREL-0001…0018) at its own pure seam. Everything here
is asserted at the highest seam available instead — the score a real decision produces — because a
consumer test that reached into `_relevance_terms` would pass while the surfaces ignored it, which is
the exact failure mode this issue exists to fix (a correct read that nothing consumed).

Assertions are **rankings and signs**, never relevance floats: the doctrine is an ordering, and an
ordering survives a re-tune that a magnitude assertion would not.

The three user rulings of 2026-07-30 (ADR-0080 Amendment B) each get a test, since each overrides
something the ADR's own decision-3 table left terser than the shipped code:

  1. the keep price KEEPS its `/2**t` turns-to-ready grade      — REQ-DENYREL-0024
  2. the target pick DROPS `_DENIAL_BENCH` (pure argmax)        — REQ-DENYREL-0023
  3. `_DENIAL_UNFAVORED` is RE-EXPRESSED on relevance, not retired — asserted in
     `test_energy_denial_guards.py` on real captured frames, both instruments.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

RIOLU, MEGA_LUCARIO, SOLROCK = 677, 678, 676
MUNKIDORI, DRAGAPULT_EX, MEOWTH_EX = 112, 121, 1071
HAMMER = 1120                              # Crushing Hammer (energy_denial, coin 0.5)
FIRE, PSYCHIC, FIGHTING, DARKNESS = 2, 5, 6, 7

MAIN, DISCARD_ENERGY = 0, 30               # SelectContext
PLAY, ENERGY = 7, 6                        # OptionType
ACTIVE, BENCH = 4, 5                       # AreaType


def _pilot(deck="dragapult_ex", *, armed=True):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    p = _build_pilot(deck)[0]
    p._planning = False
    p.deny_relevance = armed
    return p


def _body(cid, energies=()):
    """An in-play body. ``energies`` are CARD IDS; `energyCards` carries the same cards, which is
    what a `DISCARD_ENERGY` option's `energyIndex` actually indexes (see `_option_energy_type`)."""
    return {"id": cid, "serial": 0, "energies": list(energies),
            "energyCards": [{"id": e} for e in energies],
            "tools": [], "preEvolution": [], "hp": 200, "maxHp": 200}


def _state(*, opp_active=None, opp_bench=(), hand=()):
    return {"turn": 4, "yourIndex": 0, "players": [
        {"active": [_body(999999)], "bench": [], "hand": [{"id": c} for c in hand],
         "handCount": len(hand), "discard": [], "prize": [None] * 3},
        {"active": [opp_active] if opp_active else [], "bench": list(opp_bench),
         "hand": None, "handCount": 0, "discard": [], "prize": [None] * 3},
    ]}


def _play_obs(**kw):
    """A MAIN menu whose only option PLAYS the Crushing Hammer — the fire-now surface."""
    return {"select": {"type": 0, "context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None,
                       "remainDamageCounter": 0, "remainEnergyCost": 0,
                       "contextCard": None, "effect": None},
            "logs": [], "current": _state(hand=(HAMMER,), **kw)}


def _strip_obs(targets, **kw):
    """A `DISCARD_ENERGY` select over ``targets`` — each ``(area, index, energyIndex)``."""
    opts = [{"type": ENERGY, "area": a, "index": i, "energyIndex": k} for a, i, k in targets]
    return {"select": {"type": 0, "context": DISCARD_ENERGY, "minCount": 1, "maxCount": 1,
                       "option": opts, "deck": None, "remainDamageCounter": 0,
                       "remainEnergyCost": 0, "contextCard": None, "effect": None},
            "logs": [], "current": _state(**kw)}


def _scores(pilot, obs):
    return [o.score for o in pilot.explain(obs).options]


# ── surface (b): fire now ────────────────────────────────────────────────────────────────────────

@pytest.mark.req("REQ-DENYREL-0019")
def test_the_hammer_fires_on_a_live_threat_and_is_held_against_a_bare_board():
    """The fire-now rung, both directions, through the option score.

    A Dragapult ex holding the `{R}` its Phantom Dive (`{R}{P}` 200) needs is a real strip, so the
    Hammer must price positive. The same board with no Energy attached anywhere is the ADR-0062
    whiff — relevance 0, and `_finish_turn_last` tiers a free Item ahead of everything, so declining
    one REQUIRES a non-positive score rather than merely a small one."""
    p = _pilot()
    live = _scores(p, _play_obs(opp_active=_body(DRAGAPULT_EX, [FIRE])))[0]
    bare = _scores(p, _play_obs(opp_active=_body(DRAGAPULT_EX)))[0]
    assert live > 0, f"a live typed strip must price positive (got {live})"
    assert bare <= 0, f"a bare board is a whiff and must be HELD (got {bare})"


@pytest.mark.req("REQ-DENYREL-0020")
def test_the_fire_factor_is_the_normalizer_so_it_prices_in_damage_units():
    """`_DENY_RELEVANCE_K` is DERIVED, not chosen: it must be exactly the normalizer relevance was
    divided by, so that `K x relevance` is the setback DAMAGE and the armed fire rung prices in the
    same units the ADR-0062 magnitude rung did.

    That identity is the whole reason the two instruments agree. Pinned as an identity rather than a
    value so a future set re-deriving `MAX_ATTACK_DAMAGE` from the CSV carries K with it — a copied
    literal would silently desynchronise the fire rung from the read.

    The measured consequence, and the reason this matters: on f21/f29's benched Dragapult ex the
    armed rung prices **exactly -1.25**, the same figure ADR-0062 derived `_DENIAL_BENCH` from and
    ADR-0082 Amendment A re-verified. Any other K breaks that agreement (at 140 the same board prices
    -6.50, still a hold but no longer the incumbent's own number)."""
    from common.deny_relevance import MAX_ATTACK_DAMAGE
    from common.pilot import _DENIAL_BENCH, _DENIAL_ITEM_COST, _DENIAL_PLAY_W, _DENY_RELEVANCE_K
    assert _DENY_RELEVANCE_K == MAX_ATTACK_DAMAGE, (
        "K must BE the normalizer, not a copy of its current value")
    # The f21/f29 board, priced by hand from the documented arithmetic: a benched body whose only
    # affordable setback is 70 damage (Jet Headbutt), discounted for the bench.
    by_hand = 0.5 * _DENIAL_PLAY_W * _DENY_RELEVANCE_K * (70 / MAX_ATTACK_DAMAGE) * _DENIAL_BENCH \
        - _DENIAL_ITEM_COST
    assert by_hand == pytest.approx(-1.25), (
        f"the identity must reproduce ADR-0062's own -1.25 on this board (got {by_hand})")


# ── surface (c): which Energy ────────────────────────────────────────────────────────────────────

@pytest.mark.req("REQ-DENYREL-0021")
def test_the_within_body_ruling_is_expressible_at_all_only_because_the_lookup_is_typed():
    """The user's Munkidori ruling, end to end — *"hammer against the darkness to mute the ability."*

    Both options point at the SAME body, so nothing about the body separates them: only the Energy's
    own type does. That is why the consumer keys its lookup on the option's Provider-resolved type
    rather than on `relevance_energy`, whose index counts PROVIDED UNITS and so cannot be matched
    against an option's `energyIndex` at all.

    OFF, both options score identically and the argmax falls through to index 0 — the historical
    "stripped whatever landed first" defect, which lands on the right answer here only by luck. Armed,
    the `{D}` wins strictly, which is the difference between being right and being lucky."""
    p = _pilot()
    obs = _strip_obs([(BENCH, 0, 0), (BENCH, 0, 1)],                 # the {D}, then the {P}
                     opp_active=_body(DRAGAPULT_EX, [FIRE]),
                     opp_bench=[_body(MUNKIDORI, [DARKNESS, PSYCHIC])])
    armed = _scores(p, obs)
    assert armed[0] > armed[1], (
        f"must strip the {{D}} to mute Adrena-Brain, not the {{P}} off Mind Bend's cost ({armed})")
    off = _scores(_pilot(armed=False), obs)
    assert off[0] == off[1] > 0, (
        f"the magnitude instrument cannot see a within-body difference, so this documents WHY the "
        f"typed lookup was needed ({off}) — and > 0, or the tie would be a vacuous both-zero one")


@pytest.mark.req("REQ-DENYREL-0022")
def test_the_forward_line_outranks_the_dead_end_across_bodies():
    """*"KO their Lucario; bench has Riolu + Solrock, each one Energy → hammer the Riolu."*

    Riolu's `{F}` is banked toward Mega Lucario ex (a SINGLE hop in this set — Mega Brave `{F}{F}`
    270); Solrock's Cosmic Beam does nothing without a Lunatone benched, and Solrock has no
    descendants at all. Raw current-form damage orders these two backwards, which is why the read
    scans the whole line."""
    p = _pilot("mega_lucario")
    obs = _strip_obs([(BENCH, 0, 0), (BENCH, 1, 0)],                 # Riolu's {F}, Solrock's {F}
                     opp_active=_body(MEOWTH_EX),
                     opp_bench=[_body(RIOLU, [FIGHTING]), _body(SOLROCK, [FIGHTING])])
    riolu, solrock = _scores(p, obs)
    assert riolu > solrock, f"the banked Riolu outranks the dead-end Solrock ({riolu} vs {solrock})"


@pytest.mark.req("REQ-DENYREL-0023")
def test_the_target_pick_applies_no_area_weight(  # ruling 2, 2026-07-30
):
    """**User ruling 2026-07-30 (ADR-0080 Amendment B): the armed target pick is a PURE
    `argmax relevance` — no `_DENIAL_BENCH`.**

    Two copies of the same body holding the same Energy, one Active and one benched, therefore score
    EQUAL armed: relevance already prices a benched body's slower clock through its own line scan, so
    discounting it again double-counts. OFF the bench option is discounted by `_DENIAL_BENCH` (0.25),
    and that constant stays live on the OFF path — it is unread while armed, not deleted, so
    ADR-0062's derivation survives for whoever retires the magnitude path.

    Guarded on `active_can_ko` being False, or the redundancy gate would zero the Active instead."""
    p = _pilot()
    obs = _strip_obs([(ACTIVE, 0, 0), (BENCH, 0, 0)],
                     opp_active=_body(DRAGAPULT_EX, [FIRE]),
                     opp_bench=[_body(DRAGAPULT_EX, [FIRE])])
    assert not p._board(obs, obs["select"]).active_can_ko, "fixture must not have us KO-ing the Active"
    active, bench = _scores(p, obs)
    assert active == bench > 0, (
        f"armed must apply no area weight ({active} vs {bench}) — and both > 0, or an equality that "
        f"held only because relevance was 0 everywhere would pass while proving nothing")
    off_active, off_bench = _scores(_pilot(armed=False), obs)
    assert off_bench < off_active, (
        f"the OFF path must still discount the bench by _DENIAL_BENCH ({off_bench} vs {off_active})")


# ── surface (a): the keep price ──────────────────────────────────────────────────────────────────

def _deny_slots(pilot, obs):
    """The emitted `deny` Slots — seam 2, read directly rather than through a DP assignment that
    could mask a regression. Mirrors `test_needs_deny_resolver._deny_slots`."""
    board = pilot._board(obs, obs["select"])
    rows, _ = pilot._discard_equation_rows(obs, obs["select"], board, obs["select"]["option"])
    slots, _elig = pilot._resolve_needs(obs, board, rows)
    return [s for s in slots if s.kind == "deny"]


def _discard_obs(**kw):
    """A forced DISCARD over a hand holding the Hammer — the shape the keep price is resolved in."""
    return {"select": {"type": 0, "context": 8, "minCount": 1, "maxCount": 1,
                       "option": [{"type": 3, "area": 2, "index": 0}], "deck": None,
                       "remainDamageCounter": 0, "remainEnergyCost": 0,
                       "contextCard": None, "effect": None},
            "logs": [], "current": _state(hand=(HAMMER,), **kw)}


@pytest.mark.req("REQ-DENYREL-0024")
def test_the_keep_price_scales_with_relevance_and_keeps_its_readiness_grade(  # ruling 1, 2026-07-30
):
    """The keep price stops being the FLAT disruption tier and becomes `tier x relevance`, and
    **User ruling 2026-07-30: it KEEPS the `/2**t` turns-to-ready grade.**

    Relevance is deliberately not imminence-gated — it scans forward forms precisely so a Riolu's
    banked `{F}` scores at all — so without the grade a four-turns-out threat would keep-price like a
    ready one. Asserted structurally rather than on a number: the emitted value must be strictly
    below `tier x relevance` whenever the body is not ready yet (deadline > 0), which is exactly what
    the halving does, and must equal it at deadline 0.

    A bare board emits NO deny slot at all: relevance 0 subsumes the ADR-0062 bite gate."""
    from common.card_worth import TAG_TIER
    p = _pilot("mega_lucario")

    ready = _deny_slots(p, _discard_obs(opp_active=_body(MEGA_LUCARIO, [FIGHTING, FIGHTING])))
    assert ready, "a powered Mega Lucario ex must open a deny slot"
    assert ready[0].deadline == 0 and 0 < ready[0].value <= TAG_TIER["gust"], (
        f"a ready body's slot is tier x relevance, ungraded ({ready[0]})")

    banked = _deny_slots(p, _discard_obs(opp_bench=[_body(RIOLU, [FIGHTING])]))
    assert banked, "a Riolu banking toward Mega Lucario ex must open a deny slot"
    assert banked[0].deadline > 0, "a Riolu one hop out is not ready yet"
    assert banked[0].value < TAG_TIER["gust"], (
        f"the /2**t grade must still discount a body that is not ready ({banked[0]})")

    assert not _deny_slots(p, _discard_obs(opp_active=_body(MEGA_LUCARIO))), \
        "a bare board denies nothing — relevance 0 emits no slot, no separate bite gate needed"


@pytest.mark.req("REQ-DENYREL-0025")
def test_a_body_we_knock_out_this_turn_opens_no_keep_slot():
    """The redundancy gate reaching the keep price: a Hammer is not worth keeping for Energy on a
    corpse. ADR-0080 step 2, and the ADR-0063 `active_can_ko` drop arriving structurally rather than
    as the surface-level guard it used to be."""
    p = _pilot("mega_lucario")
    obs = _discard_obs(opp_active=_body(MEGA_LUCARIO, [FIGHTING, FIGHTING]))
    board = p._board(obs, obs["select"])
    rows, _ = p._discard_equation_rows(obs, obs["select"], board, obs["select"]["option"])
    board.active_can_ko = True
    board.deny_relevance_rows = ()                      # force the re-resolve to see the new flag
    p._opponent_target_cache = None
    slots, _elig = p._resolve_needs(obs, board, rows)
    assert not [s for s in slots if s.kind == "deny"], \
        "the Active dies this turn — its Energy is not worth a Hammer"


# ── the OFF path ─────────────────────────────────────────────────────────────────────────────────

# ── the three findings the corpus measurement exposed (ADR-0080 Amendment B) ─────────────────────

@pytest.mark.req("REQ-DENYREL-0027")
def test_the_fire_rung_prices_only_what_they_can_afford_right_now():
    """**Finding A.** The keep price and the target pick credit BANKED potential — that is the
    doctrine, and it is why a Riolu's `{F}` is worth taking before Mega Lucario ex exists. The FIRE
    rung must not: crediting an attack they cannot yet make spends a finite Item on a threat that has
    not arrived.

    ms f21/f29's board is the anchor (they are the SAME board, ruled `[7]` and `[10]` — both AGAINST
    the Hammer). A benched Dragapult ex holds one `{R}`; Phantom Dive `{R}{P}` needs two, so it is
    unaffordable, while Jet Headbutt `●` 70 is affordable. Pricing the full read fires at +2.50 and
    reproduces the original *"wasted crushing hammer"* blunder; pricing the affordable setback gives
    -1.25 — ADR-0062's own figure, to the cent.

    Asserted as the two readings DIVERGING on one board, which is the property, rather than as the
    two numbers."""
    p = _pilot()
    obs = _play_obs(opp_bench=[_body(DRAGAPULT_EX, [FIRE])])
    board = p._board(obs, obs["select"])
    row = next(r for r in p._opponent_target_cache[1] if r["area"] == "bench")
    assert row["relevance"] > row["relevance_fire"] > 0, (
        f"the banked reading must exceed the affordable one on this board ({row['relevance']} vs "
        f"{row['relevance_fire']}) — if they were equal the gate would be untested")
    assert _scores(p, obs)[0] <= 0, "an unaffordable threat must not be worth SPENDING a Hammer on"


@pytest.mark.req("REQ-DENYREL-0028")
def test_a_body_exactly_paying_a_colourless_cost_is_relevant_but_one_short_is_not():
    """**Finding B.** ADR-0080's read skipped pure-colourless costs outright, so the binding-count
    clause was unreachable for them and every `●●●` nuke read as a whiff — re-introducing the exact
    defect ADR-0062 was written to fix (*"a benched Mega Starmie ex sitting on 3 Energy unmolested"*,
    ms f26).

    The clause now fires when the body is EXACTLY paying the cost, which is what separates the two
    colourless cases the doctrine rules opposite ways. Both halves asserted, because a test its own
    bug would pass is not a test:
      * exactly on the cost -> relevant (a strip drops it under);
      * one short -> irrelevant (it could not attack before the strip either — the Meowth ex ruling,
        which REQ-DENYREL-0009 pins independently at the read's own seam).
    """
    from common import deny_relevance as dr
    WATER, COLOURLESS_3 = 3, [(210, {}, 3, False)]        # Nebula Beam ●●● 210
    exactly = dr.strip_relevance(energy_type=WATER, type_count=3, line_attacks=COLOURLESS_3,
                                 total_attached=3, attached_counts={WATER: 3})
    assert exactly["affordable_setback"] == 210 and exactly["relevance"] > 0, \
        "3 attached against a ●●● cost: the strip breaks the attack"
    short = dr.strip_relevance(energy_type=WATER, type_count=1, line_attacks=COLOURLESS_3,
                               total_attached=1, attached_counts={WATER: 1})
    assert short["relevance"] == 0.0, \
        "1 attached against a ●●● cost denies nothing — it could not attack either way"


@pytest.mark.req("REQ-DENYREL-0029")
def test_a_brief_sharpens_the_rank_but_never_the_decision_to_spend_the_card():
    """**Finding C.** ADR-0080 decision 2 makes a matched Brief a multiplier on the derived *rank*.
    Applied to the FIRE reading as well it becomes an override, because that reading is compared
    against `_DENIAL_ITEM_COST`: measured, the 1.25x boost turns f21's -1.25 into +0.94 and plays the
    Hammer the human ruled against, on a board where the only thing that changed is that the body
    happens to be Brief-named.

    That is the f17 discipline restated for a new booster — *a booster must scale the oracle, never
    override it* — so the sharpener is scoped to the rank and the keep price only."""
    p = _pilot("mega_starmie")
    obs = _play_obs(opp_bench=[_body(DRAGAPULT_EX, [FIRE])])
    board = p._board(obs, obs["select"])
    row = next(r for r in p._opponent_target_cache[1] if r["area"] == "bench")
    assert DRAGAPULT_EX in (board.brief_threat_ids or ()), (
        "this frame only tests anything if the body IS Brief-named — mega_starmie's matched Brief "
        "lists Dragapult ex, which is why the boost was reaching the fire leg in the first place")
    # The ranked reading carries the boost; the fire reading is the raw affordable relevance.
    assert row["relevance_fire"] == pytest.approx(70 / 350.0), (
        "the fire reading must be the unboosted affordable setback (Jet Headbutt 70 / 350)")
    assert _scores(p, obs)[0] == pytest.approx(-1.25), (
        "a Brief-named body must not lift this hold above zero — that is an override, not a boost")


@pytest.mark.req("REQ-DENYREL-0026")
def test_off_reproduces_the_documented_incumbent_arithmetic_exactly():
    """The kill-switch's OFF half, pinned against the formula rather than against itself.

    `_denial_play_tactical` OFF must equal `coin x W x (unfavored?) x opp_denial_best - item cost`
    recomputed independently here. Asserting OFF == OFF would be vacuous; recomputing the documented
    arithmetic is what makes "byte-identical" a claim a future edit can falsify."""
    from common.pilot import _DENIAL_ITEM_COST, _DENIAL_PLAY_W
    from common.strategy.denial import coin_odds

    class _Ctx:
        option_type, tags, card_id = PLAY, ["energy_denial"], HAMMER

    p = _pilot("mega_lucario", armed=False)
    obs = _play_obs(opp_active=_body(MEGA_LUCARIO, [FIGHTING, FIGHTING]))
    board = p._board(obs, obs["select"])
    p._unfavored = lambda _b: False
    expected = coin_odds(HAMMER) * _DENIAL_PLAY_W * board.opp_denial_best - _DENIAL_ITEM_COST
    assert p._denial_play_tactical(board, _Ctx()) == expected
    assert board.deny_relevance_best == 0.0, "OFF must emit no relevance at all"
    assert board.deny_relevance_rows == ()
