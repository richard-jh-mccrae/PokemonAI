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
     `test_energy_denial_guards.py` on real captured frames.

Issue #228 then armed the flag and DELETED the ADR-0062 magnitude oracle it replaced
(`Board.opp_denial_best`, `Pilot._opp_denial_best`, `Pilot._denial_at`, `_DENIAL_BENCH`) under the
tracker's directive that *"rungs an equation replaces are DELETED, not suppressed"*. Several tests
here used to draw their contrast by scoring the same board on both instruments; those now state the
claim against the armed read alone, and each says so in its own docstring. OFF is **documented
DEGRADED MODE, never a rollback** — every deny surface stands down, which is what
`test_off_is_documented_DEGRADED_MODE_and_emits_ABSENT_not_a_measured_zero` pins.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

RIOLU, MEGA_LUCARIO, SOLROCK = 677, 678, 676
MUNKIDORI, DRAGAPULT_EX, MEOWTH_EX = 112, 121, 1071
TERAPAGOS_EX = 176                         # Basic, retreat 2 — ms f21/f29's Active (EN_Card_Data.csv)
HAMMER = 1120                              # Crushing Hammer (energy_denial, coin 0.5)
FIRE, PSYCHIC, FIGHTING, DARKNESS = 2, 5, 6, 7

MAIN, DISCARD_ENERGY = 0, 30               # SelectContext
PLAY, ENERGY, END = 7, 6, 14               # OptionType
ACTIVE, BENCH = 4, 5                       # AreaType


def _pilot(deck="dragapult_ex", *, armed=True):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    p = _build_pilot(deck)[0]
    p._planning = False
    p.deny_relevance = armed
    # Set EXPLICITLY rather than inherited from PROFILE: these tests state their own preconditions,
    # so they keep meaning the same thing whichever way the shipped flag goes. Guarding the shipped
    # value is `test_runtime`'s job (`PROFILE == EXPECTED_SHIPPED`), not this file's.
    p.deny_strip_delta = armed
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

    That identity is the whole reason the instrument could REPLACE the magnitude rung rather than
    re-scale it. Pinned as an identity rather than a value so a future set re-deriving
    `MAX_ATTACK_DAMAGE` from the CSV carries K with it — a copied literal would silently
    desynchronise the fire rung from the read.

    **The witness moved twice (ADR-0084 decision 5, then Issue #228).** This used to price f21/f29's
    benched Dragapult ex by hand at **-1.25**, the figure ADR-0062 derived `_DENIAL_BENCH` from. That
    arithmetic went through the bench discount, which decision 5 retired from this rung in favour of
    ADR-0071's promotion gate and Issue #228 then deleted outright — so there is no `_DENIAL_BENCH`
    to multiply by any more, and on that board the gate SHUTS and the rung reads 0.00 (asserted in
    `test_a_held_hammer_scores_at_or_below_zero_whichever_branch_it_takes`).

    So the identity is pinned on a board that exercises it: their Active is a Mega Lucario ex sitting
    on exactly the `{F}{F}` Mega Brave (270) needs, so the strip puts that nuke out of reach and the
    rung must pay `coin x W x 270 - keep price` = 125.00. `K x relevance` reproduces 270 only if K IS
    the normalizer — at any other value the by-hand figure and the rung part company, which is
    exactly what this test is for. Card facts verified at data/EN_Card_Data.csv (MEG 77)."""
    from common.deny_relevance import MAX_ATTACK_DAMAGE
    from common.pilot import _DENIAL_ITEM_COST, _DENIAL_PLAY_W, _DENY_RELEVANCE_K
    from common.strategy.denial import coin_odds

    class _Ctx:
        option_type, tags, card_id = PLAY, ["energy_denial"], HAMMER

    assert _DENY_RELEVANCE_K == MAX_ATTACK_DAMAGE, (
        "K must BE the normalizer, not a copy of its current value")
    MEGA_BRAVE = 270                               # Mega Lucario ex, {F}{F} — the attack denied
    by_hand = coin_odds(HAMMER) * _DENIAL_PLAY_W * _DENY_RELEVANCE_K \
        * (MEGA_BRAVE / MAX_ATTACK_DAMAGE) - _DENIAL_ITEM_COST
    assert by_hand == pytest.approx(125.0), (
        f"the documented arithmetic must price this board at +125.00 (got {by_hand})")

    p = _pilot("mega_lucario")
    obs = _play_obs(opp_active=_body(MEGA_LUCARIO, [FIGHTING, FIGHTING]))
    board = p._board(obs, obs["select"])
    p._unfavored = lambda _b: False                # Lever A has its own test; isolate the identity
    assert p._denial_play_tactical(obs, board, _Ctx()) == pytest.approx(by_hand), (
        "the fire rung must price in damage units — `K x relevance` IS the setback damage, so the "
        "rung and the hand-computed formula cannot differ unless K stopped being the normalizer")


# ── surface (c): which Energy ────────────────────────────────────────────────────────────────────

@pytest.mark.req("REQ-DENYREL-0021")
def test_the_within_body_ruling_is_expressible_at_all_only_because_the_lookup_is_typed():
    """The user's Munkidori ruling, end to end — *"hammer against the darkness to mute the ability."*

    Both options point at the SAME body, so nothing about the body separates them: only the Energy's
    own type does. That is why the consumer keys its lookup on the option's Provider-resolved type
    rather than on `relevance_energy`, whose index counts PROVIDED UNITS and so cannot be matched
    against an option's `energyIndex` at all.

    The historical "stripped whatever landed first" defect landed on the right answer here only by
    luck: any BODY-keyed reading — which is all the retired ADR-0062 magnitude oracle ever had —
    scores these two options identically, because they name the same body. Armed, the `{D}` wins
    strictly, which is the difference between being right and being lucky.

    **The reference moved (Issue #228).** That contrast used to be drawn by scoring the same menu on
    the OFF path and asserting the tie; the magnitude oracle is deleted, so it is drawn instead from
    the read's own shape — the two options resolve to ONE row, and the whole discrimination lives
    inside that row's `relevance_by_type`. Nothing else on the row could have separated them."""
    p = _pilot()
    obs = _strip_obs([(BENCH, 0, 0), (BENCH, 0, 1)],                 # the {D}, then the {P}
                     opp_active=_body(DRAGAPULT_EX, [FIRE]),
                     opp_bench=[_body(MUNKIDORI, [DARKNESS, PSYCHIC])])
    board = p._board(obs, obs["select"])
    armed = _scores(p, obs)
    assert armed[0] > armed[1], (
        f"must strip the {{D}} to mute Adrena-Brain, not the {{P}} off Mind Bend's cost ({armed})")

    keys = {_key_of(o) for o in obs["select"]["option"]}
    assert keys == {("bench", 0)}, (
        f"the ruling is only a WITHIN-body one if both options name the same body; got {keys}")
    by_type = p._deny_relevance_map(obs, board)[("bench", 0)]
    assert by_type[DARKNESS] > by_type[PSYCHIC] > 0, (
        f"the separation must live in the TYPED map — a body-keyed reading has one number for this "
        f"row and could not express the ruling at all ({by_type})")


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
    discounting it again double-counts.

    **The contrast lost its other half (Issue #228).** This used to also score the menu OFF and assert
    the bench option came back discounted by `_DENIAL_BENCH` (0.25). That constant and the path that
    read it are deleted under tracker directive 1, so the incumbent behaviour is now recorded here in
    prose and asserted only where it still runs: `_deny_best_of`'s promotion GATE, which carries
    `_DENIAL_BENCH`'s actual QUESTION ("can that benched body reach the Active position at all") on
    the fire rung, and is asserted by
    `test_energy_denial_pilot.py::test_the_hammer_fires_on_a_loaded_BENCH_behind_a_bare_active` and
    `test_a_held_hammer_scores_at_or_below_zero_whichever_branch_it_takes`.

    Guarded on `active_can_ko` being False, or the redundancy gate would zero the Active instead.

    **The CLOCK is switched off here (ADR-0084).** On this board the two bodies differ ONLY by area,
    so the clock's tiebreak (`strip_shift` 6 on the Active, 0 on the bench) is indistinguishable from
    an area weight and would mask the very thing this test isolates. Turning it off is not a dodge —
    it is the absence-versus-zero distinction the tiebreak is built on, and the clock's own behaviour
    is asserted separately in `test_the_clock_breaks_a_cross_body_relevance_tie`."""
    p = _pilot()
    p.deny_strip_delta = False
    obs = _strip_obs([(ACTIVE, 0, 0), (BENCH, 0, 0)],
                     opp_active=_body(DRAGAPULT_EX, [FIRE]),
                     opp_bench=[_body(DRAGAPULT_EX, [FIRE])])
    assert not p._board(obs, obs["select"]).active_can_ko, "fixture must not have us KO-ing the Active"
    active, bench = _scores(p, obs)
    assert active == bench > 0, (
        f"armed must apply no area weight ({active} vs {bench}) — and both > 0, or an equality that "
        f"held only because relevance was 0 everywhere would pass while proving nothing")


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
    two numbers.

    **Restructured for ADR-0084 decision 5, and it now tests two boards rather than one.** The old
    fixture omitted the opponent's Active entirely — which its own claim to be f21/f29's board
    contradicted, and which stopped being harmless once the bench weight became the promotion gate:
    with no Active, `_promotion_open` takes its documented free-promotion leg (a body absent from the
    list was Knocked Out, and its replacement comes off the Bench for free), so the gate opens and the
    bench counts fully. Asserting `score <= 0` on the real anchor board would then be VACUOUS about
    affordability, because a shut gate zeroes the reading whatever its affordability. So:

      * **gate OPEN** (no Active) tests finding A itself, by arithmetic — the rung must price the
        AFFORDABLE reading, and the banked one would score strictly higher on the same board;
      * **gate SHUT** (the real anchor's **Terapagos ex** Active — Basic, retreat cost **2**, verified
        in `EN_Card_Data.csv` — holding no Energy, so it cannot retreat) tests the corpus ruling: the
        Hammer is HELD."""
    from common.pilot import _DENIAL_ITEM_COST, _DENIAL_PLAY_W, _DENY_RELEVANCE_K
    from common.strategy.denial import coin_odds

    # ── gate OPEN: the fire rung reads AFFORDABLE, not banked (finding A, by arithmetic) ──
    p = _pilot()
    obs = _play_obs(opp_bench=[_body(DRAGAPULT_EX, [FIRE])])
    p._board(obs, obs["select"])
    row = next(r for r in p._opponent_target_cache[1] if r["area"] == "bench")
    assert row["relevance"] > row["relevance_fire"] > 0, (
        f"the banked reading must exceed the affordable one on this board ({row['relevance']} vs "
        f"{row['relevance_fire']}) — if they were equal the gate would be untested")
    p._unfavored = lambda _b: False
    priced = coin_odds(HAMMER) * _DENIAL_PLAY_W * _DENY_RELEVANCE_K
    assert _scores(p, obs)[0] == pytest.approx(priced * row["relevance_fire"] - _DENIAL_ITEM_COST), (
        "the fire rung must price the AFFORDABLE reading")
    assert priced * row["relevance"] > priced * row["relevance_fire"], (
        "and the banked reading would have priced strictly higher — that gap IS finding A")

    # ── gate SHUT: the real anchor's board, where the corpus ruled HOLD ──
    q = _pilot()
    anchor = _play_obs(opp_active=_body(TERAPAGOS_EX), opp_bench=[_body(DRAGAPULT_EX, [FIRE])])
    board = q._board(anchor, anchor["select"])
    assert board.deny_relevance_best == 0.0, (
        "Terapagos ex holds no Energy against retreat cost 2 and no switch survives the read, so the "
        "promotion gate must SHUT and the benched threat must carry no weight at all")
    assert _scores(q, anchor)[0] <= 0, "an unaffordable threat must not be worth SPENDING a Hammer on"


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
    from common.pilot import _DENIAL_FORWARD
    # Both attacks are the body's OWN (`is_forward=False`), so the ADR-0084 Amendment A forward
    # discount cannot reach them — passed as the production constant rather than a literal so this
    # stays a colourless-cost test and never silently becomes a discount test.
    WATER, COLOURLESS_3 = 3, [(210, {}, 3, False)]        # Nebula Beam ●●● 210
    exactly = dr.strip_relevance(energy_type=WATER, type_count=3, line_attacks=COLOURLESS_3,
                                 total_attached=3, attached_counts={WATER: 3},
                                 forward_discount=_DENIAL_FORWARD)
    assert exactly["affordable_setback"] == 210 and exactly["relevance"] > 0, \
        "3 attached against a ●●● cost: the strip breaks the attack"
    short = dr.strip_relevance(energy_type=WATER, type_count=1, line_attacks=COLOURLESS_3,
                               total_attached=1, attached_counts={WATER: 1},
                               forward_discount=_DENIAL_FORWARD)
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
    override it* — so the sharpener is scoped to the rank and the keep price only.

    **Re-anchored for ADR-0084 decisions 5 and 8.** This used to assert the absolute figure `-1.25`,
    which the promotion gate retires: that number was `70 x 0.25` against `_DENIAL_BENCH`, and the
    gate is boolean. Re-asserting the new absolute would assert arithmetic rather than the claim, and on
    a gate-SHUT board the assertion would be vacuous (relevance zeroes out, so a Brief could reach the
    fire leg unpunished and the test would still pass). So the claim is asserted COMPARATIVELY instead —
    the fire rung's score must equal the arithmetic computed from the RAW affordable reading. Any boost
    reaching that rung would change the number, so this is airtight without depending on the retired
    constant — and it stays non-vacuous because this board leaves the promotion gate OPEN.

    (A cross-deck control was tried first and rejected: `dragapult_ex`'s own matched Brief also names
    Dragapult ex — it is the mirror — so it is not an unbriefed control at all.)"""
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

    from common.pilot import _BRIEF_THREAT_BOOST, _DENIAL_ITEM_COST, _DENIAL_PLAY_W, _DENY_RELEVANCE_K
    from common.strategy.denial import coin_odds

    assert board.deny_relevance_best > 0, (
        "this board must leave the promotion gate OPEN, or a zeroed reading would make the assertion "
        "below pass even if the Brief did reach the fire leg")
    assert _BRIEF_THREAT_BOOST > 1.0, "the sharpener must actually be a boost, or nothing is at risk"
    p._unfavored = lambda _b: False
    raw = (coin_odds(HAMMER) * _DENIAL_PLAY_W * _DENY_RELEVANCE_K * row["relevance_fire"]
           - _DENIAL_ITEM_COST)
    assert _scores(p, obs)[0] == pytest.approx(raw), (
        f"the fire rung must price the RAW affordable reading even though this body is Brief-named — "
        f"a {_BRIEF_THREAT_BOOST}x boost here would show up as a different number, and lifting a hold "
        f"above the item cost is an override, not a boost")


@pytest.mark.req("REQ-DENYREL-0026")
def test_off_is_documented_DEGRADED_MODE_and_emits_ABSENT_not_a_measured_zero():
    """The kill-switch's OFF half.

    ⚠️ **RE-SUBJECTED (Issue #228). Read this before assuming coverage was lost.** This test used to
    be `test_off_reproduces_the_documented_incumbent_arithmetic_exactly`: it recomputed
    `coin x W x (unfavored?) x opp_denial_best - item cost` by hand and asserted the OFF branch of
    `_denial_play_tactical` matched, so that "byte-identical to the incumbent" was a claim a future
    edit could falsify. **That subject no longer exists** — tracker directive 1 ("rungs an equation
    replaces are DELETED, not suppressed") removed `Board.opp_denial_best`, `Pilot._opp_denial_best`
    and `Pilot._denial_at`, and with them the arithmetic there was to reproduce. The lost coverage is
    named plainly rather than quietly re-scoped: **nothing now pins the ADR-0062 magnitude formula,
    because nothing computes it.**

    What OFF means now is the `snipe_relevance` precedent: **documented DEGRADED MODE, never a
    rollback.** All three deny surfaces stand down — the fire rung returns exactly 0.0 (before the
    keep price, so a held Hammer is not even charged for being held), the target pick returns 0.0,
    and no deny slot is emitted. That contract is what this test pins, together with the
    absence-versus-zero distinction it already carried:

    RE-RULED (Issue #228, ADR-TEMP-228 decision 2). The Board assertion below once read `== 0.0` —
    the dataclass default, back when the field could not express absence. OFF emits no relevance at
    all, and `None` says exactly that where `0.0` said "measured, and it is nothing". The distinction
    is the defect: mid-sim the ARMED read was equally absent, and the fire rung whiffed on strips
    worth +22.50 and +74.50 because it could not tell the two apart."""
    from common.strategy.denial import coin_odds

    class _Ctx:
        option_type, tags, card_id = PLAY, ["energy_denial"], HAMMER

    p = _pilot("mega_lucario", armed=False)
    obs = _play_obs(opp_active=_body(MEGA_LUCARIO, [FIGHTING, FIGHTING]))
    board = p._board(obs, obs["select"])
    p._unfavored = lambda _b: False
    assert coin_odds(HAMMER) > 0, "the fixture's card must be a real coin-flip denier"
    assert p._denial_play_tactical(obs, board, _Ctx()) == 0.0, (
        "OFF is DEGRADED MODE: the fire rung stands down at exactly 0.0, ahead of the keep price — "
        "a board this loaded (Mega Brave's own {F}{F}) prices +125.00 armed")
    assert board.deny_relevance_best is None, "OFF must emit no relevance at all — ABSENT, not zero"
    assert board.deny_relevance_rows == ()
    assert _deny_slots(p, _discard_obs(opp_active=_body(MEGA_LUCARIO, [FIGHTING, FIGHTING]))) == [], (
        "and the keep price stands down with it — OFF emits no deny slot at all")


# ── Issue #217 / ADR-0084: the derived clock is a TIEBREAK, not a deadline, and never a gate ──────
#
# All of these are asserted on REAL captured boards, because the clock (`strip_shift`) is a
# `turns_to_ko_me` simulation and a hand-built board engineered to produce a chosen shift is a board
# nobody has checked can exist (the isolated-probe lesson, plus ADR-0062's corollary: when an oracle
# refuses a test board, check the BOARD before the assertion).
#
# The SELECT is synthesised over those real boards, because no captured fixture carries a
# `DISCARD_ENERGY` menu — the engine only poses one mid-resolution, after a Hammer's coin comes up
# heads. That is NOT the isolated-probe trap: the option set is fully enumerable (every Energy on
# their board, per `_denial_target_tactical`'s own contract) and `_strip_over_board` enumerates all
# of it, so no option the engine would have offered is missing.

FIXTURES = REPO / "tests" / "fixtures" / "corrections"

#: Real boards carrying a CROSS-BODY relevance tie whose clock deltas DIFFER — verified 2026-07-30.
#: dp f82: active0 `{FIRE: 0.571}` delta 8 vs bench1 `{PSYCHIC: 0.571}` delta 0.
#: ms f94: active0 `{FIGHTING: 0.964}` delta 1 vs bench1 `{FIGHTING: 0.964}` delta 0.
_TIE_ACTS = [("dp_evolve_energized_line_body_first_f82.json", "dragapult_ex"),
             ("ms_dont_lillies_away_the_bigger_hand_f94.json", "mega_starmie")]


def _fixture_obs(name):
    import json
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["obs"]


def _strip_over_board(obs):
    """A `DISCARD_ENERGY` select over EVERY Energy on the opponent's board — the menu the engine
    actually poses, synthesised over a real captured board."""
    state = obs["current"]
    players, yi = state["players"], state.get("yourIndex", 0)
    opp = players[1 - yi]
    opts = []
    for area, bodies in ((ACTIVE, opp.get("active") or []), (BENCH, opp.get("bench") or [])):
        for bi, body in enumerate([b for b in bodies if b]):
            for k in range(len(body.get("energies") or [])):
                opts.append({"type": ENERGY, "area": area, "index": bi, "energyIndex": k})
    assert opts, "fixture board carries no strippable Energy — wrong board for this test"
    return dict(obs, select={"type": 0, "context": DISCARD_ENERGY, "minCount": 1, "maxCount": 1,
                             "option": opts, "deck": None, "remainDamageCounter": 0,
                             "remainEnergyCost": 0, "contextCard": None, "effect": None})


def _rows_by_key(pilot):
    """`{(area, bi): row}` off the per-decision opponent-target cache — relevance and clock."""
    cache = pilot._opponent_target_cache
    assert cache, "an armed board must resolve opponent-target rows"
    return {(r["area"], r["bi"]): r for r in cache[1]}


def _key_of(option):
    return ("active" if option["area"] == ACTIVE else "bench", option["index"])


@pytest.mark.req("REQ-DENYREL-0030")
@pytest.mark.parametrize("fixture,deck", _TIE_ACTS)
def test_the_clock_breaks_a_cross_body_relevance_tie(fixture, deck):
    """**ADR-0084 decision 2.** Two candidates tied on relevance EXACTLY, on different bodies, whose
    strips buy different amounts of survival: the one that actually buys turns must win.

    Today that tie resolves by whatever order the engine listed its options — the precise defect
    ADR-0062 named for the scoring case (*"the argmax fell through to index 0 and we stripped
    whatever Energy happened to land first"*), arriving one surface later."""
    p = _pilot(deck)
    obs = _strip_over_board(_fixture_obs(fixture))
    p._board(obs, obs["select"])                       # populates the per-decision cache
    rows = _rows_by_key(p)

    best = {}                                          # (area, bi) -> best score over its Energies
    for opt, sc in zip(obs["select"]["option"], _scores(p, obs)):
        k = _key_of(opt)
        best[k] = max(sc, best.get(k, float("-inf")))

    rel = {k: max((r.get("relevance_by_type") or {}).values(), default=0.0) for k, r in rows.items()}
    top = max(rel.values())
    tied = [k for k, v in rel.items() if v == pytest.approx(top)]
    assert len(tied) >= 2, f"fixture must present a tie at the top relevance; got {rel}"
    shifts = {k: rows[k].get("strip_shift") for k in tied}
    assert len(set(shifts.values())) > 1, (
        f"fixture must present DIFFERING clock deltas among the tied pair; got {shifts}")

    winner = max(tied, key=lambda k: shifts[k])
    for k in tied:
        if k != winner:
            assert best[winner] > best[k], (
                f"the clock must break the tie: {winner} buys {shifts[winner]} turns and scores "
                f"{best[winner]}, {k} buys {shifts[k]} and scores {best[k]} — equal scores mean the "
                f"pick still falls through to engine option order")


@pytest.mark.req("REQ-DENYREL-0031")
def test_the_clock_is_silent_on_a_within_body_tie():
    """**ADR-0084 decisions 2 and 3.** Two Energy TYPES on the SAME body, tied on relevance: the
    clock cannot discriminate them — `strip_shift` is one reading per body, and the measured negative
    result is that WHICH Energy you remove never changes it (109 bodies, 0 cases). So the tiebreak
    must express no preference rather than manufacture one.

    ml f121: the Active holds `{PSYCHIC: 0.714, FIRE: 0.714}`, both at clock delta 3."""
    p = _pilot("mega_lucario")
    obs = _strip_over_board(_fixture_obs("ml_aurajab_dont_load_the_engine_f121.json"))
    p._board(obs, obs["select"])
    by_type = _rows_by_key(p)[("active", 0)].get("relevance_by_type") or {}
    tied_types = [t for t, v in by_type.items() if v == pytest.approx(max(by_type.values()))]
    assert len(tied_types) >= 2, f"fixture must tie two types on one body; got {by_type}"

    on_active = [sc for opt, sc in zip(obs["select"]["option"], _scores(p, obs))
                 if _key_of(opt) == ("active", 0)]
    top = max(on_active)
    assert sum(1 for sc in on_active if sc == pytest.approx(top)) >= 2, (
        f"two equally-relevant Energies on ONE body must score equal — the clock reads the same for "
        f"both, so a preference here would be manufactured; got {on_active}")


@pytest.mark.req("REQ-DENYREL-0035")
def test_the_armed_read_discounts_a_forward_form_by_exactly_DENIAL_FORWARD():
    """**ADR-0084 Amendment A — the defect Issue #217's investigation found in Issue #187's build.**

    ADR-0080 decision 2 makes `_DENIAL_FORWARD` *"central"* to relevance's forward-potential leg and
    *"promoted rather than deleted"*. It was never applied there: the only consumer was `_denial_at`,
    on the OFF path. So the ARMED instrument credited a forward form at full damage and priced a
    forward threat at DOUBLE the incumbent — a real shipped defect, live for a week.

    ms 82225643 f11 is the witness the user ruled on (2026-07-30, *"rationale is correct"*): turn 2, a
    Basic Riolu holding one `{F}`, and Mega Lucario ex's Aura Jab (`{F}` 130) credited in full fired a
    Hammer over the Pokégear 3.0 dig the corpus rules correct. Their hand holds no Mega Lucario ex, so
    that attack cannot happen this turn or next.

    **The reference moved (Issue #228), the claim did not.** This used to assert the two instruments
    AGREEING on this board — armed's affordable reading against `Board.opp_denial_best` — so that a
    re-derived `_DENIAL_FORWARD` carried both sides with it. The OFF instrument is deleted, so the
    discount is now pinned DIRECTLY: the armed forward-leg readings must equal the discounted value
    computed from `_DENIAL_FORWARD` and the card facts. Same guarantee against the same defect (an
    undiscounted read prices exactly double each figure below); it simply no longer borrows a second
    instrument to say so, and a re-derived `_DENIAL_FORWARD` still carries the assertion with it
    because the constant is read, not spelled.

    Both readings are pinned, because the discount has to bite on both and they differ:

      * **fire** (`affordable_relevance`) — restricted to attacks the body could pay for as it
        stands, which off one `{F}` is Aura Jab (`{F}` 130) and not Mega Brave (`{F}{F}` 270). This
        is the reading the fire rung consumes, and the one the old cross-check compared.
      * **banked** (`relevance` / `relevance_setback`) — the whole line including what they cannot
        afford yet, so Mega Brave 270. It deliberately EXCEEDS the affordable reading; comparing it
        against the OFF number was this test's own first mistake (it read 135 vs 65 and looked like
        a bug when both were correct).

    Card facts verified at data/EN_Card_Data.csv (MEG 76/77): Riolu is the SOLE pre-evolution of Mega
    Lucario ex, a single hop, Aura Jab {F} 130 and Mega Brave {F}{F} 270."""
    from common.deny_relevance import MAX_ATTACK_DAMAGE
    from common.pilot import _DENIAL_FORWARD

    AURA_JAB, MEGA_BRAVE = 130, 270

    obs = _fixture_obs("ms_hammer_forward_form_riolu_f12.json")
    armed = _pilot("mega_starmie")
    armed._board(obs, obs.get("select"))
    row = max(_rows_by_key(armed).values(), key=lambda r: r.get("relevance") or 0.0)
    assert row.get("relevance_forward") == MEGA_BRAVE, (
        f"this fixture only tests the discount if the top row's relevance comes off the FORWARD form "
        f"at its RAW value ({row.get('relevance_forward')} vs Mega Brave's {MEGA_BRAVE})")

    armed_fire = (row.get("relevance_fire") or 0.0) * MAX_ATTACK_DAMAGE
    assert armed_fire == pytest.approx(_DENIAL_FORWARD * AURA_JAB), (
        f"the fire reading must credit Aura Jab at the mandated discount, not in full "
        f"({armed_fire} vs {_DENIAL_FORWARD * AURA_JAB}; undiscounted it prices {AURA_JAB}, double)")
    assert row.get("relevance_setback") == pytest.approx(_DENIAL_FORWARD * MEGA_BRAVE), (
        f"and the banked reading must credit Mega Brave at the SAME discount "
        f"({row.get('relevance_setback')} vs {_DENIAL_FORWARD * MEGA_BRAVE})")
    assert (row.get("relevance") or 0.0) > (row.get("relevance_fire") or 0.0), (
        "the BANKED reading must still exceed the affordable one — the discount scales the forward "
        "credit, it does not delete the banked doctrine (ADR-0063: a discount, never a deletion)")


@pytest.mark.req("REQ-DENYREL-0033")
def test_the_clock_never_gates_the_keep_price_even_when_it_reads_zero():
    """**ADR-0084 decision 7, the reversal — asserted NEGATIVELY.** A `strip_shift > 0` gate on the
    keep price was recommended, ACCEPTED, and then reversed on measurement: it would have suppressed
    128 of 218 relevance-positive corpus rows, because the clock measures *"does this strip delay MY
    defeat by a whole turn or more"* rather than *"does this strip do anything"*.

    Munkidori is the cleanest witness of the blindness. Its `{D}` fuels Adrena-Brain — an ABILITY — so
    stripping it is real denial that changes no damage clock at all, and the clock reads 0. The keep
    price must still open a slot on it. This test exists so that reviving the gate breaks something."""
    p = _pilot("mega_lucario")
    obs = _discard_obs(opp_bench=[_body(MUNKIDORI, [DARKNESS])])
    board = p._board(obs, obs["select"])
    rows = {(r["area"], r["bi"]): r for r in p._opponent_target_cache[1]}
    row = rows[("bench", 0)]

    assert row.get("relevance_ability_leg", 0.0) > 0, (
        "the fixture only tests the blindness if relevance comes from the ABILITY leg")
    assert not row.get("strip_shift"), (
        f"and only if the clock reads nothing on it; got {row.get('strip_shift')} — muting an Ability "
        f"delays no damage, so a KO clock cannot see this denial at all")
    with_clock = _deny_slots(p, obs)
    assert with_clock, (
        "the keep price must STILL open a deny slot on a body the strip Δ cannot see — a delta may "
        "order a tie, never gate one (ADR-0084 decision 7)")

    # ...and UNCHANGED, not merely present: the strip Δ must not touch this surface at all. Compared
    # against the same armed pilot with the Δ switched off, so the only difference is the reading the
    # dropped bite gate would have consumed.
    q = _pilot("mega_lucario")
    q.deny_strip_delta = False
    without = _deny_slots(q, obs)
    assert [(x.key, x.value, x.deadline) for x in with_clock] ==            [(x.key, x.value, x.deadline) for x in without], (
        f"the keep price must be byte-identical with and without the strip Δ — it is decision 1's "
        f"surface and decision 7 removed its only proposed consumer; got {with_clock} vs {without}")


@pytest.mark.req("REQ-DENYREL-0034")
def test_a_held_hammer_scores_at_or_below_zero_whichever_branch_it_takes():
    """**ADR-0084 decision 8's build requirement.** Retiring `_DENIAL_BENCH` from the fire rung routes
    a shut-gate board down the rung's WHIFF branch (`if not value: return 0.0`) instead of through the
    arithmetic, so a hold that used to price `-1.25` now prices `0.00`.

    Both are holds, but only if nothing downstream distinguishes a zero from a small negative — the
    governing rule is that the tier requires `score <= 0`, which `0.0` satisfies. Asserted rather than
    assumed, because a free Item is tiered ahead of everything by `_finish_turn_last` and a `> 0`
    comparison anywhere would play the Hammer the corpus ruled against.

    (The asymmetry itself — that a bad strip prices 0 where ADR-0062's reasoning implies it should
    price negative — was knowingly left open and handed forward by ADR-0084 decision 8. **Issue #228
    CLOSED it** (ADR-TEMP-228 decision 4): the whiff short-circuit is gone, so a shut gate now prices
    `odds x weight x 0 - _DENIAL_ITEM_COST` = **-10.0**. It had to close, because `0.0` did not
    actually decline — `_finish_turn_last` promotes on `score > 0`, so the Hammer landed in the last
    tier TIED with End and stable score order played it by option index.)

    **Asserted on the REAL f21/f29 fixtures, with their full captured menus.** A first attempt used a
    hand-built menu and was worthless twice over: `explain().chosen` is a LIST, so `chosen != 0` was
    vacuously true, and with only one or two synthesised options the Pilot has nothing better to do and
    plays the Hammer anyway. The claim is inherently about competing against the rest of a real turn,
    so only a real menu can carry it — the isolated-probe lesson exactly."""
    for fixture, want in (("ms_doom_relax_bare_terapagos_f21.json", [7]),
                          ("ms_doom_relax_bare_terapagos_f29.json", [10])):
        p = _pilot("mega_starmie")
        obs = _fixture_obs(fixture)
        select = obs["select"]
        board = p._board(obs, select)
        assert board.deny_relevance_best == 0.0, (
            f"{fixture}: their Terapagos ex holds 0 Energy against retreat cost 2, so the promotion "
            f"gate must SHUT and the benched threat must carry no weight")

        ex = p.explain(obs)
        hammer = [i for i, o in enumerate(select["option"])
                  if p._option_card_id(obs, select, o) == HAMMER]
        assert hammer, f"{fixture} must actually offer a Hammer, or it tests nothing"
        from common.pilot import _DENIAL_ITEM_COST
        assert all(ex.options[i].score == pytest.approx(-_DENIAL_ITEM_COST) for i in hammer), (
            f"{fixture}: a shut gate must take the whiff branch and still PAY THE KEEP PRICE — this "
            f"fixes WHICH branch, so the assertion below is known to be testing the zero-relevance "
            f"case; got {[ex.options[i].score for i in hammer]}")
        assert not set(ex.chosen) & set(hammer), (
            f"{fixture}: a whiffing Hammer must NOT be chosen — a free Item is tiered ahead of "
            f"everything by `_finish_turn_last`, and at the old 0.0 it TIED End and won on option "
            f"index. chosen={ex.chosen}")
        assert list(ex.chosen) == want, (
            f"{fixture}: and the decision must still match the corpus ruling {want}; got {ex.chosen}")


@pytest.mark.req("REQ-DENYREL-0032")
@pytest.mark.parametrize("fixture,deck", _TIE_ACTS)
def test_the_clock_never_reorders_what_relevance_already_separates(fixture, deck):
    """**ADR-0084 decision 2, the subordination half.** The tiebreak is LEXICOGRAPHIC: wherever two
    candidates differ on relevance, relevance decides, whatever the clock says.

    Asserted as an invariant over every pair rather than on one hand-picked pair, because the bound
    is derived from the observed relevance gap and an off-by-one in that derivation surfaces as
    exactly this — a clock bonus large enough to overtake a real difference."""
    p = _pilot(deck)
    obs = _strip_over_board(_fixture_obs(fixture))
    p._board(obs, obs["select"])
    rows = _rows_by_key(p)

    scored = []
    for opt, sc in zip(obs["select"]["option"], _scores(p, obs)):
        k = _key_of(opt)
        etype = p._option_energy_type(rows[k].get("body"), opt)
        scored.append(((rows[k].get("relevance_by_type") or {}).get(etype, 0.0), sc, k, etype))

    assert any(a[0] > b[0] and a[0] != pytest.approx(b[0]) for a in scored for b in scored), (
        f"the sweep below is vacuous unless the fixture actually presents two candidates that "
        f"DIFFER on relevance; got {sorted({round(r, 4) for r, *_ in scored})}")
    for rel_a, sc_a, key_a, t_a in scored:
        for rel_b, sc_b, key_b, t_b in scored:
            if rel_a > rel_b and rel_a != pytest.approx(rel_b):
                assert sc_a > sc_b, (
                    f"relevance {rel_a} at {key_a}/{t_a} scored {sc_a}, but LOWER relevance {rel_b} "
                    f"at {key_b}/{t_b} scored {sc_b} — the clock must never overtake a relevance "
                    f"difference, only break an exact tie")


# ── the read must SURVIVE the rollout (ADR-TEMP-228, Issue #228) ─────────────────────────────────

def _play_or_end_obs(**kw):
    """The fire-now menu with End beside it — the two options `_finish_turn_last` tiers together
    when the Hammer is unendorsed, and therefore the only board on which "held" is falsifiable."""
    obs = _play_obs(**kw)
    obs["select"]["option"] = [{"type": PLAY, "index": 0}, {"type": END}]
    return obs


@pytest.mark.req("REQ-DENYREL-0036")
@pytest.mark.parametrize("board,label", [
    (lambda: _play_obs(opp_active=_body(DRAGAPULT_EX, [FIRE])), "a live typed strip"),
    (lambda: _play_obs(opp_active=_body(DRAGAPULT_EX)), "a bare board (a real whiff)"),
    (lambda: _play_obs(opp_active=_body(MEGA_LUCARIO, [FIGHTING])), "the forward-line anchor"),
])
def test_the_armed_fire_rung_prices_the_same_MID_SIM_as_it_does_at_the_root(board, label):
    """**The defect Issue #228 was blocked by.** `_opponent_target_rows` returns None mid-sim, so
    the per-decision cache is empty, `Board.deny_relevance_best` keeps its default, and the fire rung
    read that default as a MEASURED zero — a whiff. The incumbent had no such hole because
    `opp_denial_best` was computed unconditionally (it is since deleted, Issue #228, so the armed
    ladder is the only thing standing between this defect and the shipped agent).

    Measured consequence: on three corpus frames the armed rung returned 0.00 mid-sim where the
    incumbent returned -5.00 / +22.50 / +74.50, flipping the Hammer decision inside the rollout,
    moving one Energy on the opponent's board, and toggling `_PLANNER_SURVIVAL_W` (50.0) in the leaf.
    That is what the Discrimination Gate saw as `82225643|1|decision|11`,
    `83686860|1|decision|13` and `82224509|1|decision|67`.

    Asserted as an IDENTITY between the two readings rather than against a literal, because the
    defect is a disagreement — any pinned number would also have to be re-derived on every re-tune,
    while "the agent scores this the same inside its own rollout as outside it" is invariant."""
    p = _pilot()
    obs = board()
    p._planning = False
    root = _scores(p, obs)[0]
    p._planning = True
    mid = _scores(p, obs)[0]
    assert mid == pytest.approx(root), (
        f"{label}: the fire rung scored {mid} mid-sim but {root} at the root — the agent is "
        f"simulating a policy it does not play")


@pytest.mark.req("REQ-DENYREL-0037")
@pytest.mark.parametrize("planning", [False, True])
def test_a_real_whiff_scores_STRICTLY_below_End_so_that_held_means_held(planning):
    """`_denial_play_tactical`'s docstring promised *"a whiff prices at 0 and is held … declining one
    REQUIRES a non-positive score."* It did not hold. `_finish_turn_last` sequences early only on
    `score > 0`, so a 0.0 free Item lands in the LAST tier **tied with End**, and stable score order
    breaks that tie by option index — the Hammer sits first, so the whiff was PLAYED.

    The retired OFF path escaped this by arithmetic accident: its magnitude was rarely exactly 0
    while the card was playable, so `odds x weight x value - keep price` came out strictly negative.
    A categorical [0,1] relevance scalar is 0 routinely and by design, which is what made a latent
    contract violation a live defect at arming time (`src/common/CONTEXT.md`, ABSENT is not ZERO).

    Run under both `_planning` states: mid-sim is where it actually bit."""
    p = _pilot()
    p._planning = planning
    hammer, end = _scores(p, _play_or_end_obs(opp_active=_body(DRAGAPULT_EX)))
    assert hammer < end, (
        f"a whiffing Hammer scored {hammer} against End at {end} — a tie is not a hold, and the "
        f"lower option index plays it")
