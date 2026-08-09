"""The §3c completeness audit (`common/snapshot_coverage.py`, POC-T0 / Issue #259).

Walks the committed Effect Clause vocabulary (`card_effects.json`, ADR-0032) and asserts every
writable target has a snapshot home. An effect writing to state the snapshot cannot represent reads
as a 0 delta, and under the composer's 1-ply ordering (Issue #263) a 0 delta is not *undervalued* —
it is **never explored**: the option is pruned and nothing says why.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common import apply_option as ao
from common import snapshot_coverage as sc
from common import state_model as sm
# The ONE implementation of the owner-family prefix test; transcribing it here would be drift.
from common.scouting.card_text import name_in_family
# The engine's own OptionType numbers, taken from the DLL-free mirror `apply_option` reads them from.
from common.strategy.context import _EVOLVE as _EVOLVE_KIND
from common.strategy.context import _PLAY as _PLAY_KIND

_EFFECTS = Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json"


def _compendium() -> dict:
    return json.loads(_EFFECTS.read_text(encoding="utf-8"))


def _resolve(path: str) -> bool:
    """Resolved against the CLASSES, not an instance: building a real StateModel would need an
    engine observation, which this suite must not need."""
    roots = {"mine": sm.MySide, "theirs": sm.TheirSide}
    parts = path.split(".")
    if parts[0] in roots:
        cur, parts = roots[parts[0]], parts[1:]
    else:
        cur = sm.StateModel
    for p in parts:
        if not hasattr(cur, p):
            return False
        attr = getattr(cur, p)
        # A `lazy`/property descriptor has no return type to walk into, so the BodyView legs hop
        # through it explicitly — which is what lets a bench leg name its FIELD and be checked.
        cur = sm.BodyView if p in ("active", "bench") else attr
    return True


# ── the registry's own discipline ─────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-SNAPSHOT-0001")
def test_the_coverage_registry_is_valid():
    """An owed zone with no owner is a silence, not a schedule."""
    assert sc.validate() == []


@pytest.mark.req("REQ-SNAPSHOT-0001")
def test_an_owed_zone_without_an_owner_is_rejected():
    """Without the mandatory field, marking something owed would be a comment."""
    bad = sc.Zone("x", "d", sc.OWED)
    assert any("MUST name the track" in p for p in sc.validate([bad]))


@pytest.mark.req("REQ-SNAPSHOT-0001")
def test_a_hidden_zone_must_say_what_prices_it_instead():
    """Requiring the alternative pricing stops `hidden` becoming a place to file inconvenient zones,
    and records why a later reader must not 'fix' it by inventing a field."""
    bad = sc.Zone("x", "d", sc.HIDDEN)
    assert any("what prices them" in p for p in sc.validate([bad]))
    assert "no deal-seed" in sc.BY_ID["deck_order"].priced_by


# ── the audit itself ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_every_clause_kind_rider_and_effect_in_the_compendium_declares_what_it_writes():
    """The §3c audit test: an undeclared write-set prices its option at exactly 0 and prunes it."""
    vocab = sc.clause_vocabulary(_compendium())
    assert vocab, "read no clause vocabulary at all — the audit would pass vacuously"
    assert sc.undeclared_clauses(vocab) == [], (
        "clause kind(s)/rider(s)/effect(s) in card_effects.json with no entry in CLAUSE_WRITES. "
        "Declare what each one writes, in `snapshot_coverage.WRITABLE` vocabulary.")


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_audit_walks_all_four_vocabularies_including_effect_and_cost():
    """Asserted two ways per axis, because either alone would rot: the key list IS all four, and a
    value really in the compendium comes back out of the walk."""
    assert sc.VOCABULARY_KEYS == ("kind", "rider", "effect", "cost")
    vocab = sc.clause_vocabulary(_compendium())
    assert "discard_opp_energy" in vocab
    assert sc.CLAUSE_WRITES["discard_opp_energy"] == {"attached_energy", "their_discard_contents"}
    # `undeclared_clauses` looks the string up, never the key position it came from, which is why ONE
    # table serves all four axes — `gust` is a `kind` on one card and an `effect` on another.
    assert "discard_2" in vocab
    assert sc.CLAUSE_WRITES["discard_2"] == {"my_hand_ids", "my_discard_contents"}
    # The flip itself writes nothing — `coin` is an RNG READ.
    assert sc.CLAUSE_WRITES["coin"] == frozenset()
    assert "coin" in sc.NONDETERMINISTIC_CLAUSES


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_an_effect_value_nobody_declared_is_caught_by_the_walk():
    """It is not enough that `effect` is LISTED; the walk has to surface an undeclared value."""
    fabricated = {"1": [{"kind": "coin", "effect": "an_effect_that_does_not_exist"}]}
    assert sc.undeclared_clauses(sc.clause_vocabulary(fabricated)) == \
        ["an_effect_that_does_not_exist"]


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_every_cost_the_compendium_charges_declares_what_it_MOVES():
    """Cards taken out of play go to MY discard (`docs/rulebook.txt` L78), so no cost touches
    `their_discard_contents`. `bottom_2` is the one that discards NOTHING — its cards rejoin my deck."""
    discard_from_hand = {"my_hand_ids", "my_discard_contents"}
    for value in ("discard_1", "discard_2", "discard_3", "discard_hand"):
        assert sc.CLAUSE_WRITES[value] == discard_from_hand, value
        assert "their_discard_contents" not in sc.CLAUSE_WRITES[value], value
    assert sc.CLAUSE_WRITES["bottom_2"] == {"my_hand_ids", "my_deck_count", "deck_odds",
                                            "deck_order"}
    assert "my_discard_contents" not in sc.CLAUSE_WRITES["bottom_2"]
    assert "deck_order" in sc.CLAUSE_WRITES["bottom_2"], \
        "Kofu's cards go to a CHOSEN position in the deck — the zone no snapshot can hold"
    assert sc.BY_ID["deck_order"].status == sc.HIDDEN
    # Declared, and actually USED — a write-set for a cost no card charges would be untested prose.
    vocab = set(sc.clause_vocabulary(_compendium()))
    assert {"discard_1", "discard_2", "discard_3", "discard_hand", "bottom_2"} <= vocab
    # Deliberately NOT nondeterministic, unlike the neighbouring `other_to_bottom`: a cost names
    # cards out of a hand I can see and consults no RNG.
    assert not ({"discard_1", "discard_2", "discard_3", "discard_hand", "bottom_2"}
                & sc.NONDETERMINISTIC_CLAUSES)
    assert sc.clauses_writing_unhomed() == {}


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_a_cost_value_nobody_declared_is_caught_by_the_walk():
    """Asserted through the WALK, not the table: the table always bit on an undeclared cost — what
    never happened was `clause_vocabulary()` yielding the value to be looked up."""
    fabricated = {"1": [{"kind": "draw", "amount": 4, "cost": "a_cost_that_does_not_exist"}]}
    assert sc.undeclared_clauses(sc.clause_vocabulary(fabricated)) == \
        ["a_cost_that_does_not_exist"]
    # …and the same walk on the same fabricated card still finds the legitimate `kind`, so the single
    # result above is a measurement rather than a walk that reached nothing.
    assert "draw" in sc.clause_vocabulary(fabricated)


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_one_extractor_reads_a_clause_s_vocabulary_so_no_second_walk_can_drift():
    """`clause_values` is the single per-clause extractor both readers go through: every axis, in
    `VOCABULARY_KEYS` order, tolerating the list-valued rider a hand-rolled walk `TypeError`s on."""
    clause = {"kind": "coin", "effect": "gust", "amount": 2, "cost": "discard_2"}
    assert sc.clause_values(clause) == ["coin", "gust", "discard_2"]
    assert sc.clause_values({"kind": "draw", "rider": ["shuffle_own_hand_in", "other_to_bottom"]}) \
        == ["draw", "shuffle_own_hand_in", "other_to_bottom"]
    assert sc.clause_values({"amount": 3}) == []
    # The set walk is now this extractor, so the two can no longer disagree about the real artifact.
    from_extractor = {v for cls in sc.clause_lists(_compendium()).values()
                      for c in cls for v in sc.clause_values(c)}
    assert sorted(from_extractor) == sc.clause_vocabulary(_compendium())


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_gust_family_declares_the_pull_AND_what_leaving_the_active_spot_clears():
    """Leaving the Active Spot clears Special Conditions and attack effects (`docs/rulebook.txt`
    L143). `allowance_retreat_used` is deliberately ABSENT: an effect SWITCH is not a retreat."""
    vocab = sc.clause_vocabulary(_compendium())
    assert {"gust", "self_switch", "confuse_target"} <= set(vocab)
    both = {"bodies_in_play", "special_conditions", "transient_grants"}
    assert sc.CLAUSE_WRITES["gust"] == both
    assert sc.CLAUSE_WRITES["self_switch"] == both
    assert "allowance_retreat_used" not in sc.CLAUSE_WRITES["self_switch"]
    assert sc.CLAUSE_WRITES["confuse_target"] == {"special_conditions"}
    # Homed on BOTH sides: a gust clears the OPPONENT's Active's attack effects, and a my-side-only
    # home would declare a write the snapshot could not show.
    assert sc.homes()["transient_grants"] == ["mine.active.grant", "theirs.active.grant"]
    # The pull is deterministic — I choose the target off a public Bench. Only the COIN in front of
    # Pokemon Catcher's copy is not, and that is `coin`'s entry.
    assert "gust" not in sc.NONDETERMINISTIC_CLAUSES
    assert sc.clauses_writing_unhomed() == {}


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_stadium_kinds_delegate_their_write_to_the_effect_they_resolve_into():
    """Both kinds reading EMPTY is the ASSERTION, not an omission — what a Stadium writes is what its
    `effect` names, so the two kinds are empty AND every effect they resolve into is declared."""
    from common.strategy.context import _PLAY
    vocab = set(sc.clause_vocabulary(_compendium()))
    assert {"stadium_static", "stadium_trigger"} <= vocab
    assert {"hp_delta", "damage_reduction", "damage_boost", "prevent_damage",
            "damage_counters"} <= vocab
    assert sc.CLAUSE_WRITES["stadium_static"] == frozenset()
    assert sc.CLAUSE_WRITES["stadium_trigger"] == frozenset()
    assert sc.undeclared_clauses(sorted(vocab)) == []
    assert sc.CLAUSE_WRITES["hp_delta"] == {"damage_counters"}
    assert sc.CLAUSE_WRITES["damage_counters"] == {"damage_counters"}
    for read_only in ("damage_reduction", "damage_boost", "prevent_damage"):
        assert sc.CLAUSE_WRITES[read_only] == frozenset(), read_only   # read off the zone, not stored
    # A Stadium's board write — displacement and allowance — is STRUCTURAL, so it belongs to
    # `_PLAY`'s footprint and to no card's clauses. The two halves must not declare each other's job.
    assert {"stadium", "allowance_stadium_played"} <= ao.footprint(_PLAY).writes
    assert not any("stadium" in zs for zs in
                   (sc.CLAUSE_WRITES["stadium_static"], sc.CLAUSE_WRITES["stadium_trigger"]))
    assert sc.clauses_writing_unhomed() == {}


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_damage_counters_is_homed_on_BOTH_sides_and_on_the_bench():
    """A symmetric Stadium writes this zone on bodies that are neither mine nor Active, so a
    my-Active-only home would declare a write the snapshot cannot show."""
    assert sc.homes()["damage_counters"] == [
        "mine.active.hp_remaining", "mine.bench", "theirs.active.hp_remaining", "theirs.bench"]
    # The bench legs name the CONTAINER, as `bodies_in_play` does — each `BodyView` inside carries
    # the per-body reads, so "mine.bench" is not a scalar HP field.
    assert hasattr(sm.BodyView, "hp_remaining") and hasattr(sm.BodyView, "damage_counters")
    assert sc.homes()["bodies_in_play"] == ["mine.active", "mine.bench", "theirs.active",
                                            "theirs.bench"]


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_two_refresh_riders_declare_exactly_the_hands_they_move():
    """`shuffle_own_hand_in` is the ONE-SIDED refresh, so declaring the two opponent zones would
    claim a strip the card never performs. `both_hands_to_bottom` differs only in `deck_order`."""
    own, both = sc.CLAUSE_WRITES["shuffle_own_hand_in"], sc.CLAUSE_WRITES["both_hands_to_bottom"]
    assert own == {"my_hand_ids", "my_deck_count", "deck_odds", "deck_order"}
    assert not (own & {"their_hand_size", "their_deck_count"})
    assert both == sc.CLAUSE_WRITES["shuffle_both_hands"]
    assert both == own | {"their_hand_size", "their_deck_count"}
    assert {"shuffle_own_hand_in", "both_hands_to_bottom"} <= sc.NONDETERMINISTIC_CLAUSES
    # Declared, and actually USED — a write-set for a rider no card carries would be untested prose.
    assert {"shuffle_own_hand_in", "both_hands_to_bottom"} <= set(sc.clause_vocabulary(_compendium()))
    assert sc.clauses_writing_unhomed() == {}


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_every_clause_KEY_in_the_compendium_is_a_declared_parameter():
    """The KEY axis: a parameter no reader knows — a typo, or a shape authored ahead of its consumer
    — sits in the store and prices exactly 0. The walk descends into `amount_if`."""
    keys = sc.clause_keys(_compendium())
    assert sc.undeclared_clause_keys(keys) == [], (
        "clause keys with no CLAUSE_PARAMETERS entry: %s" % sc.undeclared_clause_keys(keys))
    assert {"to_hand_size", "amount_if", "cost_required", "condition"} <= set(keys)
    # Every VOCABULARY key is also a parameter key — one dict, two axes, not two vocabularies.
    assert set(sc.VOCABULARY_KEYS) <= set(sc.CLAUSE_PARAMETERS)
    # Every declared parameter says what it carries; an undescribed key is an undocumented one.
    assert [k for k, v in sc.CLAUSE_PARAMETERS.items() if not str(v).strip()] == []


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_clause_KEY_audit_actually_bites_including_inside_a_nested_block():
    """The positive control, including a typo NESTED inside `amount_if` — the case a shallow walk
    passes by not looking."""
    assert sc.undeclared_clause_keys(["a_parameter_nobody_declared"]) == \
        ["a_parameter_nobody_declared"]
    fabricated = {"999": [{"kind": "draw", "amount": 2,
                           "amount_if": {"condition": "x", "amonut": 4}}]}
    assert sc.undeclared_clause_keys(sc.clause_keys(fabricated)) == ["amonut"]
    # …and the same walk on the same fabricated card finds the legitimate nested key too, so the
    # single result above is a measurement rather than a walk that reached nothing.
    assert "condition" in sc.clause_keys(fabricated)


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_cost_vocabulary_declares_both_its_zones_and_its_count():
    """`CLAUSE_WRITES` names zones and deliberately not counts; `COST_CARDS` makes the count data.
    Graded BOTH ways: zones with no count cannot be charged, a count with no zones is undeclared."""
    assert sc.cost_card_problems(_compendium()) == [], sc.cost_card_problems(_compendium())
    assert sc.COST_CARDS["discard_1"] == 1        # 1233 Canari, "discard another card"
    assert sc.COST_CARDS["discard_2"] == 2        # 1121 Ultra Ball, "discard 2 other cards"
    assert sc.COST_CARDS["discard_3"] == 3        # 1092 Secret Box, "discard 3 other cards"
    # The two the seam REFUSES, for two different reasons — see COST_CARDS' own docstring.
    assert sc.COST_CARDS["discard_hand"] is None  # the count is the hand's size, not a constant
    assert sc.COST_CARDS["bottom_2"] is None      # returns cards to the DECK, so the pool moves
    # Read off the shipped store rather than restated, so a sixth cost value cannot be minted
    # without landing here.
    used = sc.cost_values(_compendium())
    assert used, "vacuity guard: no card carries a cost, so the assertion below compares nothing"
    assert used <= set(sc.COST_CARDS), sorted(used - set(sc.COST_CARDS))
    assert used <= set(sc.CLAUSE_WRITES), sorted(used - set(sc.CLAUSE_WRITES))


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_cost_vocabulary_audit_actually_bites():
    """Graded against the SHIPPED STORE, not a second list of the same keys — an audit comparing a
    table with a hand-copy of its own keys passes by agreeing with itself."""
    real = dict(sc.COST_CARDS)
    payload = _compendium()
    try:
        sc.COST_CARDS.pop("discard_2")                  # Ultra Ball really carries it
        assert any("discard_2" in p and "no count" in p for p in sc.cost_card_problems(payload))
        sc.COST_CARDS.update(real)
        sc.COST_CARDS["discard_2"] = 0
        assert any("discard_2" in p and "positive int" in p
                   for p in sc.cost_card_problems(payload))
    finally:
        sc.COST_CARDS.clear()
        sc.COST_CARDS.update(real)
    assert sc.cost_card_problems(payload) == []
    # The OTHER direction — a carried cost `CLAUSE_WRITES` never declared — is reachable only on a
    # synthetic, because no shipped card has one.
    fabricated = {"901": [{"kind": "fetch", "target": "pokemon", "zone": "deck",
                           "cost": "pitch_energy"}]}
    assert [p for p in sc.cost_card_problems(fabricated) if "pitch_energy" in p]


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_multi_leg_reveal_relation_is_coherently_declared():
    """`choice` is a PER-LEG flag, so it can be declared in shapes that mean nothing: on HALF a
    card's legs, or on a card with ONE leg. Differing `amount`s are a real either-or, not a defect."""
    assert sc.choice_relation_problems(_compendium()) == [], \
        sc.choice_relation_problems(_compendium())
    # The vacuity guard: the walk must actually reach multi-leg reveal cards.
    multi = [cid for cid, cs in sc.clause_lists(_compendium()).items()
             if len([c for c in cs if c.get("kind") in sc.REVEALING_CLAUSES]) > 1]
    assert len(multi) >= 10, f"the walk reached only {len(multi)} multi-leg reveal cards"
    # 1210 Brock's Scouting really does carry differing amounts on `choice` legs, and is clean.
    brock = [c for c in sc.clause_lists(_compendium())[1210] if c.get("kind") == "fetch"]
    assert {c.get("amount") for c in brock} == {1, 2} and all(c.get("choice") for c in brock)


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_reveal_relation_audit_actually_bites_on_both_incoherent_shapes():
    """The positive control for the audit above, one synthetic card per shape."""
    half = {"901": [{"kind": "fetch", "target": "pokemon", "zone": "deck", "choice": True},
                    {"kind": "fetch", "target": "energy", "zone": "deck"}]}
    assert [p for p in sc.choice_relation_problems(half) if "half-declared" in p]
    solitary = {"902": [{"kind": "fetch", "target": "pokemon", "zone": "deck", "choice": True}]}
    assert [p for p in sc.choice_relation_problems(solitary) if "ONE revealing clause" in p]
    # …and the coherent shapes stay silent, so the results above are a measurement rather than a
    # walk that complains about everything.
    union = {"903": [{"kind": "fetch", "target": "pokemon", "zone": "deck", "choice": True},
                     {"kind": "fetch", "target": "energy", "zone": "deck", "choice": True}]}
    conj = {"904": [{"kind": "fetch", "target": "pokemon", "zone": "deck"},
                    {"kind": "fetch", "target": "energy", "zone": "deck"}]}
    assert sc.choice_relation_problems(union) == []
    assert sc.choice_relation_problems(conj) == []


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_every_clause_SELECTOR_value_in_the_compendium_is_declared():
    """The SELECTOR axis (Issue #374): every consumer of these values fails CLOSED on a string it
    does not recognise, so a mistyped `target` funds nothing and reaches nothing — the §3c zero."""
    pairs = sc.clause_selectors(_compendium())
    assert sc.undeclared_selector_values(pairs) == [], (
        "selector values with no CLAUSE_SELECTORS entry: %s"
        % sc.undeclared_selector_values(pairs))
    # The walk actually reached the artifact, rather than passing by finding nothing.
    keys = {k for k, _ in pairs}
    assert (len(pairs), len(keys)) == (74, 17), (len(pairs), len(keys))
    # Every selector key is a declared PARAMETER and none is VOCABULARY: the discriminator is
    # *names a WRITE*, not *is a string*, and a selector narrows reach rather than writing.
    assert set(sc.CLAUSE_SELECTORS) <= set(sc.CLAUSE_PARAMETERS)
    assert not (set(sc.CLAUSE_SELECTORS) & set(sc.VOCABULARY_KEYS))


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_selector_value_audit_actually_bites_with_a_positive_control():
    """Bites BOTH ways: an undeclared VALUE on a known key, and a string-valued KEY the selector
    registry has never heard of even though `CLAUSE_PARAMETERS` may already declare it."""
    fabricated = {"999": [{"kind": "accel", "target": "a_target_nobody_declared"}]}
    assert sc.undeclared_selector_values(sc.clause_selectors(fabricated)) == \
        ["target=a_target_nobody_declared"]
    # A brand-new selector KEY bites too, or a key could arrive already exempt from its own audit.
    assert sc.undeclared_selector_values([("brandnewsel", "x")]) == ["brandnewsel=x"]
    # Nested, inside `amount_if`.
    nested = {"999": [{"kind": "draw", "amount_if": {"condition": "nope_typo", "amount": 2}}]}
    assert sc.undeclared_selector_values(sc.clause_selectors(nested)) == ["condition=nope_typo"]
    # …and every committed value still passes on that run, so the bites are discrimination rather
    # than a check that reddens on everything.
    assert sc.undeclared_selector_values(sc.clause_selectors(_compendium())) == []
    # A VOCABULARY value is `undeclared_clauses`' business, not this audit's — which is why `gust`
    # can be a `kind` and an `effect` without confusing either.
    assert sc.undeclared_selector_values(sc.clause_selectors(
        {"999": [{"kind": "a_kind_nobody_declared"}]})) == []


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_selector_values_are_keyed_PER_KEY_because_one_string_means_several_things():
    """`"basic"` is a `target`, an `applies_to` AND an `energy`, so a flat `value -> legal` set would
    have to accept `{"zone": "basic"}` — not a coarser audit but a WRONG one."""
    assert sc.undeclared_selector_values([("target", "basic")]) == []
    assert sc.undeclared_selector_values([("zone", "basic")]) == ["zone=basic"]
    assert sc.undeclared_selector_values([("zone", "deck"), ("source", "deck")]) == []
    # The collision is real in the committed store, not hypothetical.
    for key in ("target", "applies_to", "energy"):
        assert "basic" in sc.CLAUSE_SELECTORS[key], key


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_unconsumed_selector_ledger_is_declared_and_every_entry_is_reasoned():
    """Consumer-less values are declared LEGAL and LEDGERED; accepting them silently would make
    `CLAUSE_SELECTORS` a transcription of the store. The ledger may UNDER-report, never over."""
    declared = {f"{k}={v}" for k, vs in sc.CLAUSE_SELECTORS.items() for v in vs}
    assert set(sc.UNCONSUMED_SELECTORS) <= declared, (
        "ledgered values that are not declared selector values: %s"
        % sorted(set(sc.UNCONSUMED_SELECTORS) - declared))
    assert [k for k, v in sc.UNCONSUMED_SELECTORS.items() if not str(v).strip()] == []
    # The ledger is about the COMMITTED store, so every entry must still be carried by a real card.
    committed = {f"{k}={v}" for k, v in sc.clause_selectors(_compendium())}
    assert set(sc.UNCONSUMED_SELECTORS) <= committed, (
        "ledger entries no card carries any more: %s"
        % sorted(set(sc.UNCONSUMED_SELECTORS) - committed))


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_name_family_carries_TWO_tests_and_1134_is_not_a_typo():
    """TWO tests on one key: 1134 prints a quoted SUBSTRING over Supporter names, 1218/1220 an owner
    possessive `name_in_family` reads as a PREFIX. They coincide over this pool only by accident."""
    clauses = sc.clause_lists(_compendium())
    carriers = {cid: cl.get("name_family") for cid, cls in clauses.items() for cl in cls
                if cl.get("name_family")}
    assert carriers[1134] == "Team Rocket", "1134 keeps its PRINTED literal — it is not a typo"
    assert carriers[1218] == carriers[1220] == "Team Rocket's"
    # The prefix test really does separate them, so one key cannot serve both meanings.
    assert name_in_family("Team Rocket's Giovanni", "Team Rocket's") is True
    assert name_in_family("Team Rocket's Giovanni", "Team Rocket") is False
    # Positive control: the instrument is live, not answering False to everything.
    assert name_in_family("Hop's Bag", "Hop's") is True
    assert name_in_family("Amulet of Hope", "Hop's") is False
    for value in ("Team Rocket", "Team Rocket's", "Hop's", "Ethan's"):
        assert value in sc.CLAUSE_SELECTORS["name_family"], value
        assert f"name_family={value}" in sc.UNCONSUMED_SELECTORS, value


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_two_board_scaled_magnitudes_are_declared_and_stay_TWO_keys():
    """`amount_per` AGGREGATES (a string naming the counted set) and `each_of` DISTRIBUTES (a boolean
    over the clause's own `target`). Reading a distribution as a multiplier OVER-counts survival."""
    for key in ("amount_per", "each_of"):
        assert key in sc.CLAUSE_PARAMETERS, key
        assert sc.CLAUSE_PARAMETERS[key].strip(), key
        assert key not in sc.VOCABULARY_KEYS, (
            f"{key} names no write — it modifies a magnitude, and the write is still the kind's")
        assert key not in sc.CLAUSE_WRITES, key
    # Declared, and actually USED — a parameter no card carries would be untested prose.
    payload = _compendium()                                    # 1085/1187 aggregate; 1222 distributes
    clauses = {cid: cls for cid, cls in sc.clause_lists(payload).items()}
    carriers = {k: sorted(cid for cid, cls in clauses.items() if any(k in c for c in cls))
                for k in ("amount_per", "each_of")}
    assert carriers["amount_per"] == [1085, 1187], carriers["amount_per"]
    assert carriers["each_of"] == [1089, 1222, 1242], carriers["each_of"]
    # `amount_per` names its set; `each_of` defers to `target`.
    morty = next(c for c in clauses[1187] if "amount_per" in c)
    assert morty["kind"] == "draw" and morty["amount"] == 1
    assert morty["amount_per"] == "their_bench"
    fennel = next(c for c in clauses[1222] if "each_of" in c)
    assert fennel["kind"] == "heal" and fennel["amount"] == 40
    assert fennel["each_of"] is True and fennel["target"] == "any_pokemon", (
        "`each_of` is a boolean over the clause's OWN `target` — a second body-class namespace "
        "beside `target` is exactly the drift this key was shaped to avoid")
    for cid in carriers["each_of"]:
        assert all(c.get("target") for c in clauses[cid] if c.get("each_of")), (
            f"card {cid}: `each_of` with no `target` distributes over an unnamed set")
    # `CLAUSE_PARAMETERS` declares the two MUTUALLY EXCLUSIVE: a clause carrying both would claim its
    # magnitude is multiplied by one set AND distributed over another, which no card prints.
    both = [cid for cid, cls in clauses.items()
            if any("amount_per" in c and "each_of" in c for c in cls)]
    assert both == [], f"card(s) {both} carry BOTH board-scaled magnitudes"
    for key in ("amount_per", "each_of"):
        assert "utually exclusive" in sc.CLAUSE_PARAMETERS[key], (
            f"{key} stopped declaring the exclusion the assertion above enforces")
    # Both walk into the key audit off the real artifact, so a typo in either fails there.
    keys = set(sc.clause_keys(payload))
    assert {"amount_per", "each_of"} <= keys
    assert sc.undeclared_clause_keys(sorted(keys)) == []


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_a_board_scaled_magnitude_key_nobody_declared_is_caught_by_the_walk():
    """The near-miss that matters is a MISSPELLING of the two keys, since those are the strings an
    author will next type by hand."""
    fabricated = {"1": [{"kind": "draw", "amount": 1, "amount_pre": "their_bench"},
                        {"kind": "heal", "amount": 40, "target": "any_pokemon", "each_off": True}]}
    assert sc.undeclared_clause_keys(sc.clause_keys(fabricated)) == ["amount_pre", "each_off"]
    # …and the same walk finds the legitimate keys, so the result above is a measurement rather than
    # a walk that reached nothing.
    assert {"amount", "target", "kind"} <= set(sc.clause_keys(fabricated))
    # The correctly-spelled pair must come back CLEAN through the same call, or the assertion above
    # is green whether or not the two keys were ever declared.
    assert sc.undeclared_clause_keys(["amount_per", "each_of"]) == []


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_clause_map_names_no_zone_the_registry_has_never_heard_of():
    """A write-set naming an invented zone looks like coverage while corresponding to nothing."""
    assert sc.unknown_zones() == {}


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_no_clause_the_compendium_knows_writes_to_a_zone_with_no_home():
    """The strong invariant. The second assertion is a SUBSET, not an equality — a FIFTH axis is
    another test's business, but NARROWING the four would make this one's claim a lie."""
    assert sc.clauses_writing_unhomed() == {}
    assert {"kind", "rider", "effect", "cost"} <= set(sc.VOCABULARY_KEYS), (
        "the invariant above is only as complete as the axes CLAUSE_WRITES is keyed on — dropping "
        "one silently narrows what 'no clause the compendium knows' means")


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_homes_resolve_against_the_real_snapshot_classes():
    """What makes a claimed home TRUE rather than aspirational: a renamed attribute fails here."""
    broken = {zone: [p for p in paths if not _resolve(p)]
              for zone, paths in sc.homes().items()}
    broken = {z: p for z, p in broken.items() if p}
    assert broken == {}, f"registry claims snapshot reads that do not exist: {broken}"


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_audit_actually_bites():
    """The positive control for the green assertions above."""
    assert sc.undeclared_clauses(["a_clause_that_does_not_exist"]) == ["a_clause_that_does_not_exist"]


# ── the §3c minimum list, and what is still owed ──────────────────────────────────────────────────


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_the_issue_minimum_zone_list_is_all_enumerated():
    """Enumerated-and-owed is a fine answer; ABSENT is the silence the registry replaces."""
    for zone in ("my_discard_contents", "their_discard_contents", "my_hand_ids", "their_hand_size",
                 "my_deck_count", "their_deck_count", "deck_odds", "my_prizes", "their_prizes",
                 "stadium", "attached_tools", "damage_counters", "special_conditions",
                 "allowance_energy_attached", "allowance_supporter_played",
                 "allowance_retreat_used", "transient_grants"):
        assert zone in sc.BY_ID, zone


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_both_discards_carry_CONTENTS_not_only_energy_counts():
    """`discard_energy_counts` alone leaves a discard's actual cards invisible to every recursion
    and re-access read."""
    assert sc.BY_ID["my_discard_contents"].status == sc.HOMED
    assert sc.BY_ID["their_discard_contents"].status == sc.HOMED
    assert hasattr(sm.MySide, "discard_ids") and hasattr(sm.TheirSide, "discard_ids")


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_the_owed_list_is_empty_because_T1_carried_it():
    """Asserted EMPTY rather than deleted: the value is in the direction it fails, because a
    newly-owed zone appearing here is a real regression in coverage."""
    assert sc.unhomed() == {}
    for owner in sc.unhomed().values():          # vacuous today; the rule outlives the emptiness
        assert "Issue #" in owner


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_a_this_turn_damage_boost_is_ENUMERATED_and_homed_on_both_sides():
    """An `owed` zone is a scheduled gap with an owner; an UNENUMERATED one is invisible to every
    assertion here. A boost is open information, so `survival` needs THEIR side as `threat` needs mine."""
    zone = sc.BY_ID["this_turn_damage_boosts"]
    assert zone.status == sc.HOMED
    assert sorted(sc.homes()["this_turn_damage_boosts"]) == ["mine.damage_boosts",
                                                             "theirs.damage_boosts"]
    assert hasattr(sm.MySide, "damage_boosts") and hasattr(sm.TheirSide, "damage_boosts")


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_the_new_in_play_bit_is_ENUMERATED_homed_per_body_and_written_by_both_transitions():
    """All four legs name the FIELD, Bench included: a container leg resolves as long as the
    container exists and delegates the comparison to `apply_parity._project`, where a drop is SILENT."""
    zone = sc.BY_ID["new_in_play"]
    assert zone.status == sc.HOMED
    assert sc.homes()["new_in_play"] == [
        "mine.active.new_in_play", "mine.bench.new_in_play",
        "theirs.active.new_in_play", "theirs.bench.new_in_play"]
    assert hasattr(sm.BodyView, "new_in_play")
    # The registry's OTHER bench spelling: this deliberately goes RED on the migration ADR-0098
    # Amendment E leaves open, because the prose defending the difference would be stale that commit.
    assert "mine.bench" in sc.homes()["damage_counters"]

    # `_EVOLVE` READS the bit too: §4 is why `[play Basic, evolve it]` is illegal.
    play, evolve = ao.FOOTPRINTS[_PLAY_KIND], ao.FOOTPRINTS[_EVOLVE_KIND]
    assert "new_in_play" in play.writes and "new_in_play" not in play.reads
    assert "new_in_play" in evolve.writes and "new_in_play" in evolve.reads
    assert ao.footprints_writing_unhomed() == {}

    # Staying WHOLE-ZONE costs nothing today: `_PLAY` is incomplete so it commutes with nothing, and
    # two `_EVOLVE`s already collide on whole-zone `special_conditions`.
    assert "new_in_play" not in sc.ELEMENT_ZONES
    assert not play.complete
    assert "special_conditions" in evolve.writes and "special_conditions" not in sc.ELEMENT_ZONES
    assert not ao.commutes(_EVOLVE_KIND, _EVOLVE_KIND)


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_element_zones_are_real_zones_and_the_required_rejections_stay_whole_zone():
    """ADR-0098 Amendment D granted element-level granularity ON CONDITION these zones stay
    whole-zone, because each is what refuses a case the spec requires refused."""
    assert sc.ELEMENT_ZONES <= set(sc.BY_ID), sorted(sc.ELEMENT_ZONES - set(sc.BY_ID))
    must_stay_whole = {"bench_occupancy", "allowance_energy_attached", "allowance_supporter_played",
                       "allowance_stadium_played", "allowance_retreat_used", "special_conditions",
                       "stadium"}
    assert must_stay_whole <= set(sc.BY_ID)              # positive control: they are real zones
    assert sc.ELEMENT_ZONES & must_stay_whole == set()


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_the_unhomed_guard_distinguishes_declared_empty_writes_from_no_clauses():
    """A declared damage boost writes no snapshot zone; an actually clause-less card remains unseen."""
    compendium = _compendium()
    for cid in ("1141", "1211"):                     # Power Pro, Black Belt's Training
        assert compendium.get(cid) == [{"kind": "damage_boost"}], cid
    assert compendium.get("1175") is None, "Brave Bangle"
    assert compendium.get("1086"), "the positive control — this card DOES carry clauses"

    play = ao.FOOTPRINTS[_PLAY_KIND]
    assert not play.complete, "`_PLAY`'s footprint is structural only — the card's effect is not in it"
    homes = sc.homes()
    assert sorted(z for z in play.writes if not homes.get(z)) == [], \
        "every zone `_PLAY` declares is HOMED, so the footprint guard can never report a play"
    assert ao.footprints_writing_unhomed() == {}
    assert "no clauses unions to the empty set" in (ao.footprints_writing_unhomed.__doc__ or "")


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_no_transition_writes_to_a_zone_the_snapshot_cannot_represent():
    """Asserted EMPTY rather than deleted: the moment a new option kind or clause names a zone the
    snapshot cannot hold, this is where it surfaces."""
    assert ao.footprints_writing_unhomed() == {}
    assert sc.clauses_writing_unhomed() == {}


# ── clause-set completeness: a PARTIAL set must not price as a complete one (Issue #300) ───────────


@pytest.mark.req("REQ-SNAPSHOT-0004")
def test_every_clause_bearing_card_declares_whether_its_clause_set_is_COMPLETE():
    """An unknown clause set is indistinguishable from a COMPLETE one at the seam. An unreasoned
    verdict is refused too: without the quoted leg the ruling cannot be re-checked against the card."""
    assert sc.covers_problems(_compendium()) == []


@pytest.mark.req("REQ-SNAPSHOT-0004")
def test_the_completeness_audit_bites():
    """Green means nothing unless it can go red — one fabricated payload per way to be wrong."""
    assert any(f"no {sc.COVERS_KEY} verdict" in p
               for p in sc.covers_problems({"1": [{"kind": "draw", "amount": 1}]}))
    unreasoned = {"1": [{"kind": "draw"}], sc.COVERS_KEY: {"1": {"covers": "full"}}}
    assert any("MUST quote" in p for p in sc.covers_problems(unreasoned))
    bogus = {"1": [{"kind": "draw"}], sc.COVERS_KEY: {"1": {"covers": "mostly", "reason": "x"}}}
    assert any("is not one of" in p for p in sc.covers_problems(bogus))
    orphan = {sc.COVERS_KEY: {"1": {"covers": "full", "reason": "x"}}}
    assert any("no Effect Clauses" in p for p in sc.covers_problems(orphan))


@pytest.mark.req("REQ-SNAPSHOT-0004")
def test_the_partial_clause_cards_are_real_and_carry_the_leg_they_miss():
    """The owed list is generated from the artifact; every listed verdict names its missing leg."""
    partial = sc.partial_clause_cards(_compendium())
    assert partial, "no card is declared partial — the audit would be reporting on nothing"
    assert len(partial) == 14
    assert 1237 in partial and "coin" in partial[1237].lower()
    assert all(reason.strip() for reason in partial.values())
    # Declared partial ⇒ actually clause-bearing. A verdict about an absent clause set is a comment.
    clauses = sc.clause_lists(_compendium())
    assert all(cid in clauses for cid in partial)


@pytest.mark.req("REQ-SNAPSHOT-0004")
def test_the_partial_list_only_ever_SHRINKS():
    """An owed list that can grow silently is not a schedule. LEAVING is clause work landing;
    ARRIVING is new exposure or a quietly downgraded verdict, and both want a human first."""
    grown = set(sc.partial_clause_cards(_compendium())) - sc.PARTIAL_CLAUSE_BASELINE
    assert grown == set(), (
        f"card(s) {sorted(grown)} became PARTIAL after the baseline was ruled. Either close the "
        f"clause gap, or rule the addition and extend `PARTIAL_CLAUSE_BASELINE` deliberately.")


@pytest.mark.req("REQ-SNAPSHOT-0004")
def test_a_partial_verdict_fails_CLOSED_and_stays_distinguishable_from_an_unruled_one():
    """`False` and `None` both refuse but stay different facts: *ruled incomplete* is a measured gap
    with an owner, *unruled* is a card nobody has looked at."""
    assert sc.clauses_cover(sc.COVERS_FULL) is True
    assert sc.clauses_cover(sc.COVERS_PARTIAL) is False
    assert sc.clauses_cover(None) is None
    assert sc.clauses_cover("anything else") is None


@pytest.mark.req("REQ-SNAPSHOT-0004")
def test_the_reserved_covers_key_is_never_read_as_a_clause_list():
    """`card_effects.json` is `{cardId: [clauses]}` PLUS one reserved key, so a hand-rolled `int(k)`
    walk either crashes on it or treats the verdict block as another card's clauses."""
    payload = _compendium()
    assert sc.COVERS_KEY in payload
    assert sc.COVERS_KEY not in {str(cid) for cid in sc.clause_lists(payload)}
    assert set(sc.clause_lists(payload)) == set(sc.covers_table(payload)), (
        "the clause lists and the verdicts must cover exactly the same cards")
    # The verdict block's `_note` ships in the artifact so its next reader is not sent to the wrong
    # file. It is reserved, so no card walk may pick it up.
    assert "_note" in payload[sc.COVERS_KEY] and "effect_overrides.json" in \
        payload[sc.COVERS_KEY]["_note"]
    assert not sc.is_card_key("_note") and not sc.is_card_key(sc.COVERS_KEY)
