"""The information-before-commitment boundary in `_finish_turn_last` — ADR-0095 decision 1, landed by
T2 (Issue #261 item 2f).

`_finish_turn_last` has always STATED the doctrine as its own purpose — *"take the most informative,
reversible actions first and the irreversible ones last"* — while `_tier()` ended on a bare
`return 0`, so every endorsed free `_PLAY` landed in one band and score decided inside it:

    Pokegear 3.0     free, INFORMATIVE   -> tier 0
    Crushing Hammer  free, COMMITTING    -> tier 0     <- same band; score decides

Tier 0 conflated *free* with *informative*. Its own docstring said *"Free, and reveals a better
target before you commit"* — a Hammer is free and reveals nothing.

Why this cannot be a score, and therefore cannot wait for the POC's differencing (ADR-0095
decision 3, `sound_rules.information-before-commitment`): digging first and digging second reach the
**same end state**, so no function of that state separates them. It is a structural ordering rule,
which is why it is on the whitelist rather than in an equation.

Two seams, deliberately:

  * the SEQUENCE on a real captured frame (REQ-INFOFIRST-0001) — the ADR's own falsifiable
    prediction, and the only place the claim meets a full menu;
  * the CLASSIFICATION at the tier function (REQ-INFOFIRST-0002…0004) — which is where the
    fail-direction ("untagged defaults to committing") is actually decidable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"

INFORMATIVE_TRAINERS = {"Buddy-Buddy Poffin", "Fighting Gong", "Mega Signal", "Poké Pad",
                        "Pokégear 3.0", "Ultra Ball", "Unfair Stamp"}
COMMITTING_TRAINERS = {"Air Balloon", "Crushing Hammer", "Gravity Mountain", "Hero’s Cape",
                       "Night Stretcher", "Premium Power Pro", "Risky Ruins", "Switch"}

POKEGEAR = 1122        # Pokegear 3.0 — Item, `dig` (card_functions.json)
HAMMER = 1120          # Crushing Hammer — Item, `energy_denial`; free and COMMITTING
IGNITION = 17          # Ignition Energy — the blind attach on f11's menu
STARYU = 1030          # a Basic Pokémon — the Bench-fill half of the classification
UNKNOWN_CARD = 9999999  # no CardStat, no Function Tags — the untagged fail-direction case


def _pilot(agent: str):
    from train.tune import _build_pilot          # `tools/` is on the path via tests/conftest.py
    p = _build_pilot(agent)[0]
    p._planning = False
    return p


@pytest.fixture(scope="module")
def f11():
    fx = json.loads((FIXTURES / "ms_information_before_commitment_f11.json")
                    .read_text(encoding="utf-8"))
    pilot = _pilot("mega_starmie")
    return fx, pilot, pilot.explain(fx["obs"])


@pytest.mark.req("REQ-INFOFIRST-0001")
def test_the_dig_is_taken_before_the_committing_item_on_the_anchor_frame(f11):
    """ADR-0095's falsifiable prediction, discharged. The ADR recorded this frame as a **standing
    disagreement** — the agent picked a Hammer where the human ruled Pokégear, and no gate flagged it
    because the baseline shared the wrong pick — and predicted the boundary would correct it.

    Asserted through the real `explain()` on the captured menu, because the claim is inherently about
    competing against the rest of a turn: on a hand-built two-option menu the Pilot has nothing else
    to do and the ordering is untested (the isolated-probe lesson)."""
    fx, _p, dec = f11
    assert list(dec.chosen) == list(fx["correct"]), (
        f"the informative dig must come off the menu first; correct={fx['correct']} "
        f"chosen={list(dec.chosen)}")


@pytest.mark.req("REQ-INFOFIRST-0001")
def test_the_hammer_is_still_endorsed_so_this_is_an_ORDERING_not_a_suppression(f11):
    """The boundary must not be a veto wearing a sequencer's clothes. The user's ruling ends *"Then,
    most likely, you'll also play Hammer and Ignition Energy in this same turn"* — all three plays are
    legal in one turn (`docs/rules.md` §3), and the engine re-presents the menu after each
    non-ending action, so the Hammer is DEFERRED rather than declined.

    If the Hammer's score had gone non-positive this test would fail, and the frame would have been
    "fixed" by suppressing a play the human explicitly endorses."""
    _fx, _p, dec = f11
    hammers = [o for o in dec.options if o.card_id == HAMMER]
    assert hammers, "the fixture must actually offer a Hammer, or it tests nothing"
    assert all(o.score > 0 for o in hammers), (
        f"the Hammer must stay ENDORSED — it is sequenced later, not declined; "
        f"got {[o.score for o in hammers]}")


@pytest.mark.req("REQ-INFOFIRST-0001")
def test_the_dig_wins_the_frame_DESPITE_scoring_below_the_options_it_precedes(f11):
    """The non-vacuity check, and the reason the boundary had to be a tier rather than a weight. The
    Pokégear is the LOWEST-scoring endorsed option on this menu: the Hammer out-scores it and the
    Ignition attach out-scores both. Ordering by score alone gives the human's ruling last."""
    _fx, _p, dec = f11
    gear = next(o for o in dec.options if o.card_id == POKEGEAR)
    hammer = next(o for o in dec.options if o.card_id == HAMMER)
    attach = max((o for o in dec.options if o.card_id == IGNITION), key=lambda o: o.score)
    assert gear.score < hammer.score < attach.score, (
        f"if the dig ever out-scored its rivals this test would pass without the boundary; "
        f"gear={gear.score} hammer={hammer.score} attach={attach.score}")


# ── the classification, at the tier seam ─────────────────────────────────────────────────────────

def _tiers(pilot, fx):
    """The tier the sequencer assigns each option, recovered from the order it returns."""
    obs = fx["obs"]
    select = obs["select"]
    options = select["option"]
    board = pilot._board(obs, select)
    traces = [pilot._option_trace(obs, select, board, o, i) for i, o in enumerate(options)]
    order = sorted(range(len(options)), key=lambda i: -traces[i].score)
    seq = pilot._finish_turn_last(obs, board, options, traces, order, select["maxCount"],
                                  select["context"])
    return seq, traces


@pytest.mark.req("REQ-INFOFIRST-0002")
def test_every_informative_play_precedes_every_committing_one(f11):
    """The band boundary itself, over the whole captured menu rather than one pair: no committing
    free PLAY may appear before an informative one. Stated as a partition so a future option kind
    landing in the wrong band fails here rather than only when it happens to out-score a dig."""
    fx, pilot, _dec = f11
    seq, traces = _tiers(pilot, fx)
    options = fx["obs"]["select"]["option"]
    tags = {POKEGEAR: "informative", HAMMER: "committing"}
    kinds = [tags.get(traces[i].card_id) for i in seq
             if options[i].get("type") == 7 and tags.get(traces[i].card_id)]
    assert "informative" in kinds and "committing" in kinds, (
        "this frame must offer BOTH bands, or the partition below is vacuous")
    assert kinds == sorted(kinds, key=lambda k: 0 if k == "informative" else 1), (
        f"informative plays must all precede committing ones; got {kinds}")


@pytest.mark.req("REQ-INFOFIRST-0003")
def test_the_four_classification_cases_including_the_untagged_fail_direction(f11):
    """`Pilot._informative_card`, the predicate the band splits on, over all four of its inputs.

    The last two are the ADR's stated fail direction: *"Untagged defaults to committing — the
    conservative direction, since a mis-tagged commitment sequencing early is the error that costs a
    card."* The asymmetry is real — a mis-classified commitment spends a card before the dig that
    would have re-aimed it, while a mis-classified dig only sequences one band late, and the engine
    re-presents the menu either way — so the DEFAULT is the part worth pinning."""
    _fx, pilot, _dec = f11
    assert pilot._informative_card(POKEGEAR) is True, "a `dig` Item ENLARGES the information set"
    assert pilot._informative_card(STARYU) is True, "a Bench fill is tier-0 free development"
    assert pilot._informative_card(HAMMER) is False, "a Hammer is free and reveals nothing"
    assert pilot._informative_card(UNKNOWN_CARD) is False, "an unknown card must read as COMMITTING"
    assert pilot._informative_card(None) is False, "and so must an option carrying no card at all"


def _pool_trainers():
    """Every non-Pokémon, non-Energy, non-Supporter card across the three shipped decks — i.e. every
    card that can reach the free `_PLAY` band the boundary splits. Supporters have their own tier and
    are never in that band; Pokémon and Energy are classified structurally, not by tag."""
    out = {}
    for deck in ("mega_starmie", "mega_lucario", "dragapult_ex"):
        p = _pilot(deck)
        for cid in sorted(set(p.deck)):
            st = p.stats.get(cid)
            if st is None or getattr(st, "is_pokemon", False) or getattr(st, "is_energy", False):
                continue
            if getattr(st, "is_supporter", False):
                continue
            out[getattr(st, "name", str(cid))] = (cid, p._informative_card(cid),
                                                  set(p.functions.tags(cid) or ()))
    return out


@pytest.mark.req("REQ-INFOFIRST-0005")
def test_every_trainer_in_the_pool_classifies_and_the_informative_ones_are_exactly_the_tagged_ones():
    """**The Function Tag audit ADR-0095 says is owed** — *"every Item must classify as informative or
    committing. Untagged defaults to committing."* Run over the whole shipped pool rather than the
    handful a fixture happens to hold, because the failure this guards is a card nobody looked at.

    Two claims. The first is a property and cannot rot: informative is EXACTLY the tag-carrying set,
    so no second classification route can quietly appear for a Trainer. The second pins the committing
    side BY NAME, and it is deliberately the brittle half — a new Trainer entering the pool untagged
    lands there silently and correctly (that is the fail direction), and this is the one place that
    makes it show up in a diff so a human classifies it once."""
    pool = _pool_trainers()
    assert pool, "the audit must actually see the pool, or it asserts nothing"
    from common.pilot import _INFORMATIVE_TAGS
    for name, (cid, informative, tags) in pool.items():
        assert informative == bool(_INFORMATIVE_TAGS & tags), (
            f"{name} ({cid}) classifies {informative} on tags {sorted(tags)} — informative must be "
            f"exactly the tag-carrying set for a Trainer")
    informative = {n for n, (_c, i, _t) in pool.items() if i}
    committing = {n for n, (_c, i, _t) in pool.items() if not i}
    assert informative == INFORMATIVE_TRAINERS, f"informative set moved: {informative}"
    assert committing == COMMITTING_TRAINERS, (
        f"committing set moved: {committing}. A NEW Trainer here has defaulted to committing, which "
        f"is the safe direction but is a classification nobody has made yet — read its card text and "
        f"either add the tag or add it to this list.")


@pytest.mark.req("REQ-INFOFIRST-0005")
def test_the_two_committing_classes_that_never_reach_the_new_branch_anyway():
    """Non-vacuity for the audit above, and the correction of an example that was wrong in this
    file's first draft: a **Tool** (Air Balloon, Hero's Cape) is played as an `_ATTACH`, not a
    `_PLAY`, so it takes the blind-commitment tier and never meets the free-band boundary; **Ultra
    Ball** is informative by tag but is `cost_discard`, and that branch is checked FIRST, so it takes
    the costly-commitment tier too.

    Both are still classified — the audit covers them — but their tier comes from elsewhere, and
    saying so here stops the next reader inferring a tier from a classification."""
    pool = _pool_trainers()
    assert pool["Ultra Ball"][1] is True and "cost_discard" in pool["Ultra Ball"][2]
    assert all("tool" in pool[n][2] for n in ("Air Balloon", "Hero’s Cape"))
    assert all(pool[n][1] is False for n in ("Air Balloon", "Hero’s Cape"))


@pytest.mark.req("REQ-INFOFIRST-0004")
def test_the_boundary_does_not_touch_the_bands_above_or_below_it():
    """Scope, pinned. The tier constants are the sequencer's whole contract with the rest of the
    Pilot, and the boundary shifted every band after the free one by exactly one. Asserted as the
    ORDER of the named constants rather than their values, so a future insertion has to state its
    intent here instead of silently renumbering."""
    from common import pilot as P
    assert (P._TIER_INFORMATIVE < P._TIER_COMMIT_FREE < P._TIER_SUPPORTER
            < P._TIER_COMMITMENT < P._TIER_SHUFFLE < P._TIER_ENDER), (
        "development -> free commitment -> Supporter -> attach -> hand-shuffle -> attack is the "
        "shipped sequence; ADR-0095 put the new boundary INSIDE the free band, not around it")
