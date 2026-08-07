"""Deny Relevance, the CONSUMER half — the three deny surfaces reading the read (ADR-0080, Issue #187).

The three deny surfaces — the keep price, the fire-now rung and the target pick — all score off
relevance instead of the ADR-0062 damage magnitude, which Issue #228 armed and DELETED.

`test_deny_relevance.py` pins the READ at its own pure seam; everything here is asserted at the
highest seam available (the score a real decision produces), because a consumer test that reached
into `_relevance_terms` would pass while the surfaces ignored it — the failure this file exists for.

Assertions are RANKINGS and SIGNS, never relevance floats. OFF is documented DEGRADED MODE, never a
rollback: every deny surface stands down.
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
    # Set EXPLICITLY rather than inherited from PROFILE, so these tests keep meaning the same thing
    # whichever way the shipped flag goes. Guarding the shipped value is `test_runtime`'s job.
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
    """`_finish_turn_last` tiers a free Item ahead of everything, so DECLINING one requires a
    non-positive score rather than merely a small one."""
    p = _pilot()
    live = _scores(p, _play_obs(opp_active=_body(DRAGAPULT_EX, [FIRE])))[0]
    bare = _scores(p, _play_obs(opp_active=_body(DRAGAPULT_EX)))[0]
    assert live > 0, f"a live typed strip must price positive (got {live})"
    assert bare <= 0, f"a bare board is a whiff and must be HELD (got {bare})"


@pytest.mark.req("REQ-DENYREL-0020")
def test_the_fire_factor_is_the_normalizer_so_it_prices_in_damage_units():
    """`_DENY_RELEVANCE_K` must BE the normalizer relevance was divided by, so `K x relevance` is the
    setback DAMAGE — a copied literal would silently desynchronise the fire rung from the read."""
    from common.deny_relevance import MAX_ATTACK_DAMAGE
    from common.hold_value import ITEM_HOLD_FLOOR
    from common.pilot import _DENIAL_PLAY_W, _DENY_RELEVANCE_K
    from common.strategy.denial import coin_odds

    class _Ctx:
        option_type, tags, card_id = PLAY, ["energy_denial"], HAMMER

    assert _DENY_RELEVANCE_K == MAX_ATTACK_DAMAGE, (
        "K must BE the normalizer, not a copy of its current value")
    MEGA_BRAVE = 270                               # Mega Lucario ex, {F}{F} — the attack denied
    by_hand = coin_odds(HAMMER) * _DENIAL_PLAY_W * _DENY_RELEVANCE_K \
        * (MEGA_BRAVE / MAX_ATTACK_DAMAGE) - ITEM_HOLD_FLOOR
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
    """Both options name the SAME body, so only the Energy's type separates them — which is why the
    consumer keys on the option's Provider-resolved type, not on `relevance_energy`'s unit index."""
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
    """Riolu's `{F}` is banked toward Mega Lucario ex while Solrock has no descendants at all. Raw
    current-form damage orders these two BACKWARDS, which is why the read scans the whole line."""
    p = _pilot("mega_lucario")
    obs = _strip_obs([(BENCH, 0, 0), (BENCH, 1, 0)],                 # Riolu's {F}, Solrock's {F}
                     opp_active=_body(MEOWTH_EX),
                     opp_bench=[_body(RIOLU, [FIGHTING]), _body(SOLROCK, [FIGHTING])])
    riolu, solrock = _scores(p, obs)
    assert riolu > solrock, f"the banked Riolu outranks the dead-end Solrock ({riolu} vs {solrock})"


@pytest.mark.req("REQ-DENYREL-0023")
def test_the_target_pick_applies_no_area_weight(  # ruling 2, 2026-07-30
):
    """ADR-0080 Amendment B: a PURE `argmax relevance`, because relevance already prices a benched
    body's slower clock. The CLOCK is off here, or its tiebreak would look like an area weight."""
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
    """The emitted `deny` Slots, read directly rather than through a DP assignment that could mask a
    regression."""
    board = pilot._board(obs, obs["select"])
    rows = pilot._discard_equation_rows(obs, obs["select"], board, obs["select"]["option"])
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
    """`tier x relevance`, but it KEEPS the `/2**t` grade: relevance is not imminence-gated, so
    without it a four-turns-out threat keep-prices like a ready one (ADR-0080 Amendment B)."""
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
    """ADR-0080 step 2 at the keep price: a Hammer is not worth keeping for Energy on a corpse."""
    p = _pilot("mega_lucario")
    obs = _discard_obs(opp_active=_body(MEGA_LUCARIO, [FIGHTING, FIGHTING]))
    board = p._board(obs, obs["select"])
    rows = p._discard_equation_rows(obs, obs["select"], board, obs["select"]["option"])
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
    """The keep price and the target pick credit BANKED potential; the FIRE rung must not, or it
    spends a finite Item on a threat that has not arrived. Two boards: promotion gate OPEN, then SHUT."""
    from common.hold_value import ITEM_HOLD_FLOOR
    from common.pilot import _DENIAL_PLAY_W, _DENY_RELEVANCE_K
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
    assert _scores(p, obs)[0] == pytest.approx(priced * row["relevance_fire"] - ITEM_HOLD_FLOOR), (
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
    """The binding-count clause fires when the body is EXACTLY paying the cost, which is what
    separates the two colourless cases the doctrine rules opposite ways. Both halves asserted."""
    from common import deny_relevance as dr
    from common.pilot import _DENIAL_FORWARD
    # Both attacks are the body's OWN, so the forward discount cannot reach them — passed as the
    # production constant so this stays a colourless-cost test, never a discount test.
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
    """A Brief multiplies the derived RANK; applied to the fire reading it becomes an override, since
    that reading is compared against the hold price (ADR-0063: a booster scales, never overrides)."""
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

    from common.hold_value import ITEM_HOLD_FLOOR
    from common.pilot import _BRIEF_THREAT_BOOST, _DENIAL_PLAY_W, _DENY_RELEVANCE_K
    from common.strategy.denial import coin_odds

    assert board.deny_relevance_best > 0, (
        "this board must leave the promotion gate OPEN, or a zeroed reading would make the assertion "
        "below pass even if the Brief did reach the fire leg")
    assert _BRIEF_THREAT_BOOST > 1.0, "the sharpener must actually be a boost, or nothing is at risk"
    p._unfavored = lambda _b: False
    raw = (coin_odds(HAMMER) * _DENIAL_PLAY_W * _DENY_RELEVANCE_K * row["relevance_fire"]
           - ITEM_HOLD_FLOOR)
    assert _scores(p, obs)[0] == pytest.approx(raw), (
        f"the fire rung must price the RAW affordable reading even though this body is Brief-named — "
        f"a {_BRIEF_THREAT_BOOST}x boost here would show up as a different number, and lifting a hold "
        f"above the item cost is an override, not a boost")


@pytest.mark.req("REQ-DENYREL-0026")
def test_off_is_documented_DEGRADED_MODE_and_emits_ABSENT_not_a_measured_zero():
    """OFF is DEGRADED MODE: all three deny surfaces stand down and the Board emits `None`, not 0.0.
    `None` is ABSENT where `0.0` claims *"measured, and it is nothing"* (ADR-0093 decision 2)."""
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
    assert board.deny_relevance_rows is None, (
        "and the ROWS carry the same distinction one level up — `None` is not measured, `()` would "
        "be measured and empty. Both fields say ABSENT, which is the whole point of this test")
    assert _deny_slots(p, _discard_obs(opp_active=_body(MEGA_LUCARIO, [FIGHTING, FIGHTING]))) == [], (
        "and the keep price stands down with it — OFF emits no deny slot at all")


# ── Issue #217 / ADR-0084: the derived clock is a TIEBREAK, not a deadline, and never a gate ──────
# On REAL boards: one engineered to produce a chosen `strip_shift` is one nobody has checked exists.

FIXTURES = REPO / "tests" / "fixtures" / "corrections"

# Real boards carrying a CROSS-BODY relevance tie whose clock deltas DIFFER.
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
    """ADR-0084 decision 2. Untied, the pick falls through to the engine's option order — ADR-0062's
    *"stripped whatever Energy happened to land first"*, arriving one surface later."""
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
    """ADR-0084 decisions 2 and 3: `strip_shift` is ONE reading per body, so the tiebreak must
    express no preference between two types on it rather than manufacture one."""
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
    """ADR-0084 Amendment A: `_DENIAL_FORWARD` was never applied to relevance's forward leg, so the
    armed read priced a forward threat at DOUBLE. BOTH readings are pinned — the discount bites on each."""
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
    """ADR-0084 decision 7, asserted NEGATIVELY so that reviving the rejected `strip_shift > 0` gate
    breaks something: muting an ABILITY is real denial that delays no damage, so the clock reads 0."""
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

    # ...and UNCHANGED, not merely present: compared against the same armed pilot with the Δ off, so
    # the only difference is the reading the dropped bite gate would have consumed.
    q = _pilot("mega_lucario")
    q.deny_strip_delta = False
    without = _deny_slots(q, obs)
    assert [(x.key, x.value, x.deadline) for x in with_clock] ==            [(x.key, x.value, x.deadline) for x in without], (
        f"the keep price must be byte-identical with and without the strip Δ — it is decision 1's "
        f"surface and decision 7 removed its only proposed consumer; got {with_clock} vs {without}")


@pytest.mark.req("REQ-DENYREL-0034")
def test_a_held_hammer_scores_at_or_below_zero_whichever_branch_it_takes():
    """ADR-0093 decision 4: a shut gate must still PAY the hold price, because `0.0` does not decline
    — `_finish_turn_last` promotes on `score > 0`, so a 0.0 Hammer ties End and wins on option index."""
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
        from common.hold_value import ITEM_HOLD_FLOOR
        # The floor binds here: a role-less Hammer's only Needs slot is the `deny` slot the shut gate
        # just zeroed, so without the floor the whiff prices 0.0 again (ADR-0093 decision 4).
        assert all(ex.options[i].score == pytest.approx(-ITEM_HOLD_FLOOR) for i in hammer), (
            f"{fixture}: a shut gate must take the whiff branch and still PAY THE HOLD PRICE — this "
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
    """ADR-0084 decision 2's subordination half: the tiebreak is LEXICOGRAPHIC. Over EVERY pair, not
    one hand-picked one — an off-by-one in the bound surfaces as a clock bonus that overtakes."""
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


# ── the read must SURVIVE the rollout (ADR-0093, Issue #228) ─────────────────────────────────

def _play_or_end_obs(**kw):
    """The fire-now menu with End beside it — `_finish_turn_last` tiers the two together when the
    Hammer is unendorsed, so this is the only board on which "held" is falsifiable."""
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
    """`_opponent_target_rows` returns None mid-sim, so the cache is empty and the fire rung read the
    default as a MEASURED zero. An IDENTITY, not a literal: the defect IS a disagreement (ADR-0093)."""
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
    """`_finish_turn_last` sequences early only on `score > 0`, so a 0.0 free Item lands in the LAST
    tier tied with End and stable score order plays it by option index. A tie is not a hold."""
    p = _pilot()
    p._planning = planning
    hammer, end = _scores(p, _play_or_end_obs(opp_active=_body(DRAGAPULT_EX)))
    assert hammer < end, (
        f"a whiffing Hammer scored {hammer} against End at {end} — a tie is not a hold, and the "
        f"lower option index plays it")
