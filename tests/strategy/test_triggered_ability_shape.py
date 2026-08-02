"""**Issue #305** — a triggered Ability RIDES the option it was played by, measured not argued.

The apply-seam coverage census (`tools/apply_seam_coverage.py`, Issue #269) resolves 11 pool sites
on the assumption that an Ability reading *"When you play this Pokemon from your hand to evolve 1 of
your Pokemon / onto your Bench, you may…"* resolves **inside** the `_PLAY` / `_EVOLVE` option rather
than posing its own `_ABILITY` option on a later menu. The assumption is load-bearing: `_ABILITY` is
the sole kind `apply_option.ENGINE_ROUTE_KINDS` routes to the engine, so the other answer would move
all 11 sites onto the engine route and shrink Issue #299's scope.

**No corpus frame settles it** — every one of the 17 `_ABILITY` options in the 372-frame diagnostic
corpus is an *activated* Ability. So this file measures it against the live engine instead, driving
`meta_tracker.probe_triggered_ability.capture` — the same function that wrote the committed fixture
— and asserting the live shape still matches. A future engine build that moved the effect onto its
own option fails HERE, loudly, rather than silently invalidating the census.

The measured answer, both trigger kinds and both branches of the *"you may"* gate:

  EVOLVE / PLAY option  ->  YES_NO / ACTIVATE gate (contextCard = the card just played)
                        ->  the effect's OWN selects, inside the same option's resolution
                        ->  MAIN

and **no `OptionType.ABILITY` at any point** — not in the gate, not among the effect's selects, and
not on the MAIN menus of this turn or the next, in either branch. Declining is the stronger half:
an Ability the engine merely offered alongside the option would still be offered after its rider was
refused, and it is not.
"""
import json

import pytest

from conftest import FIXTURES, on_cgpy_twin

if on_cgpy_twin():                                    # the NATIVE engine is the authority here
    pytest.skip("triggered-Ability option shape: a native-engine measurement",
                allow_module_level=True)

from cg.api import OptionType, SelectContext, SelectType          # noqa: E402
from common.strategy.context import _ABILITY, _EVOLVE, _PLAY      # noqa: E402
from meta_tracker.cards import load_cards                         # noqa: E402
from meta_tracker.probe_triggered_ability import MODES, SCHEMA, capture  # noqa: E402
from seam_census_helpers import census_pool, load_census                 # noqa: E402

FIXTURE = FIXTURES / "triggered_ability_selects.json"

#: The 11 pool sites the answer moves (Issue #305's table), by trigger. **Iono's Bellibolt ex (269)
#: is deliberately absent** — the merged report said "12 sites" and listed it, but Electric Streamer
#: reads *"As often as you like during your turn"*, which is ACTIVATED. `test_the_erratum_...`
#: below pins that correction so the count cannot silently drift back to 12.
RIDER_SITES = {648: "on_evolve", 674: "on_evolve", 190: "on_evolve", 173: "on_evolve",
               742: "on_evolve", 743: "on_evolve", 310: "on_evolve",
               1071: "on_play", 75: "on_play", 135: "on_play", 209: "on_play"}
BELLIBOLT = 269


@pytest.fixture(scope="module")
def fixture_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def seam_census():
    return load_census()


@pytest.fixture(scope="module")
def live():
    """The measurement, re-driven against the live engine. A miss is a FAILURE, not a skip — the
    probe reached its option in 80/80 measured runs, so a None means the harness broke."""
    return capture(load_cards())


def test_live_engine_still_matches_the_committed_measurement(fixture_payload, live):
    """The rot guard. Everything `capture()` records is shuffle-invariant, so this compares equal
    every run — and stops comparing equal exactly when the engine's answer changes."""
    assert fixture_payload["schema"] == SCHEMA, "fixture predates the current record shape"
    assert live == fixture_payload


def test_the_answer_is_rider_not_its_own_ability_option(live):
    """AMBIGUOUS #3, ruled: the census's assumption (a) is the engine's behaviour."""
    assert live["answer"] == "rider"
    for subject in live["subjects"]:
        for mode in MODES:
            assert subject[mode]["ability_option_seen"] is False, (subject["name"], mode)


@pytest.mark.parametrize("mode", MODES)
def test_the_trigger_is_gated_by_an_ACTIVATE_yes_no_on_the_card_just_played(live, mode):
    """*"you may"* is posed as `SelectType.YES_NO` / `SelectContext.ACTIVATE`, and the select names
    the card it belongs to in `contextCard` — which is how a consumer knows whose trigger it is."""
    for subject in live["subjects"]:
        gate = subject[mode]["gate_select"]
        assert gate["type"] == int(SelectType.YES_NO), subject["name"]
        assert gate["context"] == int(SelectContext.ACTIVATE), subject["name"]
        assert gate["contextCard"]["id"] == subject["card_id"], subject["name"]
        assert [o["type"] for o in gate["option"]] == [int(OptionType.YES), int(OptionType.NO)]


@pytest.mark.parametrize("mode", MODES)
def test_no_ABILITY_option_is_ever_posed_for_a_triggered_ability(live, mode):
    """The crux. Not in the gate, not among the effect's own selects, and not on the MAIN menus of
    this turn or the next — including after the rider was DECLINED, which is the branch a separately
    posed Ability would survive."""
    for subject in live["subjects"]:
        rec = subject[mode]
        assert int(OptionType.ABILITY) not in [o["type"] for o in rec["gate_select"]["option"]]
        for sel in rec["effect_selects"]:
            assert int(OptionType.ABILITY) not in sel["option_types"], subject["name"]
        assert rec["main_menus_sampled"] == 2, subject["name"]
        assert rec["main_menus_with_ability_option"] == 0, subject["name"]


def test_accepting_resolves_the_effect_inside_the_same_option(live):
    """The other half of the question: the engine goes straight to the effect's own selects as part
    of resolving the play/evolve, and only then returns to MAIN.

    Punk Up searches the deck and attaches (`ATTACH_TO` then `ATTACH_FROM`); Last-Ditch Catch
    fetches a Supporter to hand (`TO_HAND`). Declining skips straight back to MAIN."""
    by_id = {s["card_id"]: s for s in live["subjects"]}
    assert [e["context"] for e in by_id[648]["accept"]["effect_selects"]] == \
        [int(SelectContext.ATTACH_TO), int(SelectContext.ATTACH_FROM)]
    assert [e["context"] for e in by_id[1071]["accept"]["effect_selects"]] == \
        [int(SelectContext.TO_HAND)]
    for subject in live["subjects"]:
        assert subject["accept"]["returned_to_main"], subject["name"]
        assert subject["decline"]["effect_selects"] == [], subject["name"]
        assert subject["decline"]["returned_to_main"], subject["name"]


def test_the_option_taken_is_the_one_the_census_credits(live):
    """A Stage 1/2 rider is reached by EVOLVE and a Basic's by PLAY — the two option kinds the
    census files these sites under."""
    for subject in live["subjects"]:
        want = "EVOLVE" if subject["trigger"] == "on_evolve" else "PLAY"
        for mode in MODES:
            assert subject[mode]["option_taken"] == want, (subject["name"], mode)


def test_the_census_routes_every_rider_site_to_the_measured_option(seam_census):
    """The measurement's consequence, asserted on the census itself: each of Issue #305's 11 sites
    carries its effect on the `_EVOLVE` / `_PLAY` site the engine actually poses it on, and none of
    them mints a separate `_ABILITY` site. If a later ruling flips this routing, the report's
    AMBIGUOUS #3 answer needs re-reading."""
    mod, cards, effects, _covers = seam_census
    for card_id, trigger in RIDER_SITES.items():
        card = cards[card_id]
        sites, _aside = mod.sites_for(card_id, card, effects.get(card_id, []))
        want = _EVOLVE if trigger == "on_evolve" else _PLAY
        carriers = [s for s in sites if s.kind == want and s.has_effect]
        assert len(carriers) == 1, f"{card.get('name')}: expected one {want} site carrying the rider"
        assert not [s for s in sites if s.kind == _ABILITY], \
            f"{card.get('name')}: a triggered Ability must not mint an `_ABILITY` site"


def test_the_erratum_the_pool_carries_exactly_eleven_rider_sites(seam_census):
    """The count, DERIVED from the pool rather than retyped from the issue. The merged report said
    *"12 sites"* and listed Iono's Bellibolt ex; Electric Streamer reads *"As often as you like
    during your turn, you may attach…"*, which is ACTIVATED, so it poses its own `_ABILITY` option
    and was never one of these. Walking the pool answers 11, and this fails if a deck or the
    scouting artifact ever adds a twelfth — which is a real event worth a ruling, not a silent one.
    """
    mod, cards, _effects, _covers = seam_census
    derived = {cid: mode
               for cid in census_pool(mod)
               if (cards.get(cid) or {}).get("category") == "pokemon"
               for mode in [mod._ability_mode(a.get("text") or "")
                            for a in (cards[cid].get("abilities") or [])]
               if mode in ("on_play", "on_evolve")}
    assert derived == RIDER_SITES
    assert len(derived) == 11


def test_the_erratum_bellibolt_is_activated_not_a_rider(seam_census):
    """The other half of the erratum, named rather than left implicit in a set difference."""
    mod, cards, _effects, _covers = seam_census
    texts = [a.get("text") or "" for a in (cards[BELLIBOLT].get("abilities") or [])]
    assert texts, "Iono's Bellibolt ex carries no Ability text — card source changed?"
    assert [mod._ability_mode(t) for t in texts] == ["activated"]
    assert BELLIBOLT not in RIDER_SITES
