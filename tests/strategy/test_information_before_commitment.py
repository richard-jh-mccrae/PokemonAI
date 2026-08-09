"""The information-before-commitment boundary in `_finish_turn_last` — ADR-0095 decision 1.

Digging first and digging second reach the same end state, so no function of that state separates
them: this is a structural ordering rule, not a score.
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

POKEGEAR = 1122        # `dig`
HAMMER = 1120          # `energy_denial`
IGNITION = 17
STARYU = 1030          # a Basic Pokémon
UNKNOWN_CARD = 9999999  # no CardStat, no Function Tags


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
    fx, _p, dec = f11
    assert list(dec.chosen) == list(fx["correct"]), (
        f"the informative dig must come off the menu first; correct={fx['correct']} "
        f"chosen={list(dec.chosen)}")


@pytest.mark.req("REQ-INFOFIRST-0001")
def test_composer_keeps_pokegear_ahead_of_a_higher_scoring_retreat():
    """Composer must retain the structural information tier when scores disagree."""
    fx = json.loads((FIXTURES / "ms_t3holdout_82227388_0_decision_50.json")
                    .read_text(encoding="utf-8"))
    decision = _pilot("mega_starmie").explain(fx["obs"])
    assert list(decision.chosen) == list(fx["correct"])
    assert decision.planned and decision.planned.goal == "compose"


@pytest.mark.req("REQ-INFOFIRST-0001")
def test_the_hammer_is_still_endorsed_so_this_is_an_ORDERING_not_a_suppression(f11):
    _fx, _p, dec = f11
    hammers = [o for o in dec.options if o.card_id == HAMMER]
    assert hammers, "the fixture must actually offer a Hammer, or it tests nothing"
    assert all(o.score > 0 for o in hammers), (
        f"the Hammer must stay ENDORSED — it is sequenced later, not declined; "
        f"got {[o.score for o in hammers]}")


@pytest.mark.req("REQ-INFOFIRST-0001")
def test_the_dig_wins_the_frame_DESPITE_scoring_below_the_options_it_precedes(f11):
    _fx, _p, dec = f11
    gear = next(o for o in dec.options if o.card_id == POKEGEAR)
    hammer = next(o for o in dec.options if o.card_id == HAMMER)
    attach = max((o for o in dec.options if o.card_id == IGNITION), key=lambda o: o.score)
    assert gear.score < hammer.score < attach.score, (
        f"if the dig ever out-scored its rivals this test would pass without the boundary; "
        f"gear={gear.score} hammer={hammer.score} attach={attach.score}")


# ── the classification, at the tier seam ─────────────────────────────────────────────────────────

def _tiers(pilot, fx):
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
    _fx, pilot, _dec = f11
    assert pilot._informative_card(POKEGEAR) is True, "a `dig` Item ENLARGES the information set"
    assert pilot._informative_card(STARYU) is True, "a Bench fill is tier-0 free development"
    assert pilot._informative_card(HAMMER) is False, "a Hammer is free and reveals nothing"
    assert pilot._informative_card(UNKNOWN_CARD) is False, "an unknown card must read as COMMITTING"
    assert pilot._informative_card(None) is False, "and so must an option carrying no card at all"


def _pool_trainers():
    """Every card across the shipped decks that can reach the free `_PLAY` band the boundary splits;
    Supporters have their own tier, and Pokémon/Energy are classified structurally, not by tag."""
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
    """A Tool is played as an `_ATTACH`, and Ultra Ball hits the `cost_discard` branch first, so
    neither reaches the free-band boundary despite being classified by it."""
    pool = _pool_trainers()
    assert pool["Ultra Ball"][1] is True and "cost_discard" in pool["Ultra Ball"][2]
    assert all("tool" in pool[n][2] for n in ("Air Balloon", "Hero’s Cape"))
    assert all(pool[n][1] is False for n in ("Air Balloon", "Hero’s Cape"))


@pytest.mark.req("REQ-INFOFIRST-0004")
def test_the_boundary_does_not_touch_the_bands_above_or_below_it():
    from common import pilot as P
    assert (P._TIER_INFORMATIVE < P._TIER_COMMIT_FREE < P._TIER_SUPPORTER
            < P._TIER_COMMITMENT < P._TIER_SHUFFLE < P._TIER_ENDER), (
        "development -> free commitment -> Supporter -> attach -> hand-shuffle -> attack is the "
        "shipped sequence; ADR-0095 put the new boundary INSIDE the free band, not around it")
