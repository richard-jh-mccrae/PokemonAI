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

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"

POKEGEAR = 1122        # Pokegear 3.0 — Item, `dig` (card_functions.json)
HAMMER = 1120          # Crushing Hammer — Item, `energy_denial`; free and COMMITTING
IGNITION = 17          # Ignition Energy — the blind attach on f11's menu
STARYU = 1030          # a Basic Pokémon — the Bench-fill half of the classification
UNKNOWN_CARD = 9999999  # no CardStat, no Function Tags — the untagged fail-direction case


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = mod._build_pilot(agent)[0]
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
        f"if the dig ever out-scored its rivals this pin would pass without the boundary; "
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
