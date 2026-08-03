"""**The §3c completeness audit** (`common/snapshot_coverage.py`, POC-T0 / Issue #259, ruled
2026-08-01).

> *"All fields should certainly be covered — we want to minimize this risk."*

The differencing system's worst failure mode is an effect that writes to state the snapshot cannot
represent. The delta then reads **0**, and under the composer's 1-ply ordering (Issue #263) a 0 delta
does not mean *undervalued* — it means **never explored**. The option is pruned and nothing says why.

So this is the audit the issue asks for: it walks the committed Effect Clause vocabulary
(`card_effects.json`, ADR-0032) and asserts every writable target has a snapshot home. A new clause
kind with no home **fails here** rather than silently pricing 0.

Two tests are the load-bearing ones:

* `test_no_clause_the_compendium_knows_writes_to_a_zone_with_no_home` — the strong invariant. Owed
  zones are a schedule; a clause writing to one makes them a live defect.
* `test_the_homes_resolve_against_the_real_snapshot_classes` — the registry claims dotted paths;
  this is what makes those claims true rather than aspirational, so a rename breaks the test.

Prior art for the style: `test_sound_rules.py` (data in the module, cross-check in the test) and
`tests/test_adr_index.py` (a structural invariant asserted straight off the artifact).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common import apply_option as ao
from common import snapshot_coverage as sc
from common import state_model as sm
# The engine's own `OptionType.PLAY`, taken from the DLL-free mirror `apply_option` itself reads it
# from — a second transcription of the number here is the drift ADR-0087 charges for one store over.
from common.strategy.context import _PLAY as _PLAY_KIND

_EFFECTS = Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json"


def _compendium() -> dict:
    return json.loads(_EFFECTS.read_text(encoding="utf-8"))


def _resolve(path: str) -> bool:
    """Does the dotted path name a real attribute, walking from `StateModel`?

    Resolved against the CLASSES, not an instance — `_Lazily` descriptors live on the class and
    building a real StateModel would need an engine observation, which this suite must not need."""
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
        # A `lazy`/property descriptor has no return type to walk into; the BodyView legs
        # (`mine.active.energy_count`) hop through it explicitly.
        cur = sm.BodyView if p in ("active",) else attr
    return True


# ── the registry's own discipline ─────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-SNAPSHOT-0001")
def test_the_coverage_registry_is_valid():
    """Every homed zone names its read, every owed zone names the track that owes it, every hidden
    zone says what prices it instead. An owed zone with no owner is a silence, not a schedule."""
    assert sc.validate() == []


@pytest.mark.req("REQ-SNAPSHOT-0001")
def test_an_owed_zone_without_an_owner_is_rejected():
    """The failure the `owed` status exists to prevent: a gap that nobody is carrying. Without the
    mandatory field, marking something owed would be a comment."""
    bad = sc.Zone("x", "d", sc.OWED)
    assert any("MUST name the track" in p for p in sc.validate([bad]))


@pytest.mark.req("REQ-SNAPSHOT-0001")
def test_a_hidden_zone_must_say_what_prices_it_instead():
    """`hidden` is the honest status, not the convenient one — deck ORDER genuinely cannot be
    represented. Requiring the alternative pricing stops it becoming a place to file inconvenient
    zones, and records why a later reader must not 'fix' it by inventing a field."""
    bad = sc.Zone("x", "d", sc.HIDDEN)
    assert any("what prices them" in p for p in sc.validate([bad]))
    assert "no deal-seed" in sc.BY_ID["deck_order"].priced_by


# ── the audit itself ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_every_clause_kind_rider_and_effect_in_the_compendium_declares_what_it_writes():
    """**The §3c audit test.** A new clause value with no declared write-set lands here rather than
    silently writing to nothing — which, under differencing, prices its option at exactly 0 and
    prunes it forever."""
    vocab = sc.clause_vocabulary(_compendium())
    assert vocab, "read no clause vocabulary at all — the audit would pass vacuously"
    assert sc.undeclared_clauses(vocab) == [], (
        "clause kind(s)/rider(s)/effect(s) in card_effects.json with no entry in CLAUSE_WRITES. "
        "Declare what each one writes, in `snapshot_coverage.WRITABLE` vocabulary.")


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_audit_walks_all_four_vocabularies_including_effect_and_cost():
    """**The Issue #300 hole, as a test — and Issue #350's, which was the same hole one axis over.**

    The walk used to cover `kind` and `rider` only, so Crushing Hammer's
    `{"kind": "coin", "effect": "discard_opp_energy"}` passed green while the write it performs —
    the opponent's Energy, and their discard — had no declared home at all. `cost` was the fourth
    such axis and went the same way: it is a closed set of strings that MOVES CARDS BETWEEN ZONES,
    and no value of it could fail the audit however undeclared it was.

    Asserted two ways per axis, because either alone would rot: that the key list IS all four, and
    that a value actually in the compendium comes back out of the walk. A walk that names an axis
    but never meets one of its values would be an audit passing by absence."""
    assert sc.VOCABULARY_KEYS == ("kind", "rider", "effect", "cost")
    vocab = sc.clause_vocabulary(_compendium())
    assert "discard_opp_energy" in vocab
    assert sc.CLAUSE_WRITES["discard_opp_energy"] == {"attached_energy", "their_discard_contents"}
    # The fourth axis, reached by the same walk: `undeclared_clauses` looks the string up, never the
    # key position it came from, which is why one table serves all four (the `gust` precedent — one
    # entry for a value that is a `kind` on Boss's Orders and an `effect` on Pokemon Catcher).
    assert "discard_2" in vocab
    assert sc.CLAUSE_WRITES["discard_2"] == {"my_hand_ids", "my_discard_contents"}
    # And the flip itself still writes nothing — `coin` is an RNG READ, which is the half of that
    # comment that was always true.
    assert sc.CLAUSE_WRITES["coin"] == frozenset()
    assert "coin" in sc.NONDETERMINISTIC_CLAUSES


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_an_effect_value_nobody_declared_is_caught_by_the_walk():
    """The bite for the third vocabulary specifically: it is not enough that `effect` is *listed*, the
    walk has to surface an undeclared one."""
    fabricated = {"1": [{"kind": "coin", "effect": "an_effect_that_does_not_exist"}]}
    assert sc.undeclared_clauses(sc.clause_vocabulary(fabricated)) == \
        ["an_effect_that_does_not_exist"]


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_every_cost_the_compendium_charges_declares_what_it_MOVES():
    """**Issue #350's write-sets.** A `cost` is not a flavour note — every committed value moves real
    cards out of my hand, and until this landed none of them said where the cards went.

    Card text quoted from the engine dump `tools/meta_tracker/cards.json` (`all_card_data()`), never
    recalled; which discard they land in is `docs/rulebook.txt` L78, *"Each player has their own
    discard pile. Cards taken out of play go to the discard pile"* — MY discard, so a cost never
    touches `their_discard_contents`.

    * 1092 Secret Box    — *"discard 3 other cards from your hand"*  → `discard_3`
    * 1121 Ultra Ball    — *"discard 2 other cards from your hand"*  → `discard_2`
    * 1233 Canari / 1187 Morty's Conviction / 1208 Iris's Fighting Spirit
                         — *"discard another card from your hand"*   → `discard_1`
    * 1192 Carmine / 1206 Larry's Skill — *"Discard your hand…"*     → `discard_hand`
    * 1200 Kofu — *"Put 2 cards from your hand on the bottom of your deck in any order."* →
      `bottom_2`, **the one whose write-set differs**: nothing is discarded at all. Two cards leave
      my hand and JOIN my deck, so the count goes UP, two known cards become unseen (`deck_odds`),
      and where they land is `deck_order` — the registry's one `hidden` zone. A reader who assumed
      "a cost discards from hand" would be wrong about exactly the value that was added last
      (Issue #302), which is why it is asserted separately rather than folded into the four."""
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
    # **Deliberately NOT nondeterministic**, checked at source rather than inherited from the
    # neighbouring `other_to_bottom` (which IS). Kofu names the cards and their order out of a hand
    # I can see; `other_to_bottom` re-buries cards a `dig` pulled from an unknown deck, so simulating
    # it is one sample. A cost consults no RNG, so none of the five defeats the determinism proof.
    assert not ({"discard_1", "discard_2", "discard_3", "discard_hand", "bottom_2"}
                & sc.NONDETERMINISTIC_CLAUSES)
    assert sc.clauses_writing_unhomed() == {}


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_a_cost_value_nobody_declared_is_caught_by_the_walk():
    """**The positive control for the fourth axis**, and the one this issue turns on: before it
    landed, `undeclared_clauses(["discard_2"])` already returned `["discard_2"]` — the table would
    have bitten. What never happened was the WALK arriving, because `cost` was not in
    `VOCABULARY_KEYS`, so `clause_vocabulary()` never yielded the value to be looked up.

    So the bite is asserted through the walk, on a fabricated cost, on the same run as the green
    assertion over the real compendium above — a red that only the table can produce would prove
    nothing about whether the audit reaches `cost` at all."""
    fabricated = {"1": [{"kind": "draw", "amount": 4, "cost": "a_cost_that_does_not_exist"}]}
    assert sc.undeclared_clauses(sc.clause_vocabulary(fabricated)) == \
        ["a_cost_that_does_not_exist"]
    # …and the same walk on the same fabricated card still finds the legitimate `kind`, so the single
    # result above is a measurement rather than a walk that reached nothing.
    assert "draw" in sc.clause_vocabulary(fabricated)


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_one_extractor_reads_a_clause_s_vocabulary_so_no_second_walk_can_drift():
    """**Why `cost` was reachable to miss twice.** `VOCABULARY_KEYS` exists so *"which keys does the
    audit walk?"* has ONE answer, but the census's write-set-health table
    (`tools/apply_seam_coverage.py`) kept its own hand-rolled `kind`-plus-`rider` walk — so the
    report titled *Clause write-set health* has been silently reporting on two axes since Issue #300
    minted the third, and would have missed the fourth for the same reason.

    :func:`snapshot_coverage.clause_values` is the single per-clause extractor both readers now go
    through. Asserted here in the direction that matters: it yields every axis, in `VOCABULARY_KEYS`
    order, and tolerates the list-valued rider `clause_vocabulary` always accepted — the shape a
    hand-rolled `used[c["rider"]] += 1` would have raised `TypeError` on."""
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
    """**Issue #303's write-set, and the rules check it rests on.**

    A gust is three writes, not one. The pull rewrites who is Active (`bodies_in_play`), and
    `docs/rulebook.txt` L143 says what moving a body out of the Active Spot does to it: *"When your
    Active Pokémon goes to your Bench (whether it retreated or got there some other way), some
    things do go away—Special Conditions and any effects from attacks."* Declaring only the move
    would price the clear at exactly 0, which is the silent zero this module exists to prevent.

    **`allowance_retreat_used` is deliberately absent**, and that is the question the issue owed at
    source: `docs/rules.md` §3 prints the manual limit as *"1 (pay the Retreat cost in Energy; card
    effects can switch for free)"*, and `docs/rulebook.txt` L618 defines retreating as discarding
    Energy equal to the printed Retreat Cost, once per turn. Prime Catcher and Team Rocket's
    Giovanni both say *switch*, never *retreat* — so an effect switch neither pays the cost nor
    spends the allowance, and declaring it would make every gust look like it burned the turn's
    retreat."""
    vocab = sc.clause_vocabulary(_compendium())
    assert {"gust", "self_switch", "confuse_target"} <= set(vocab)
    both = {"bodies_in_play", "special_conditions", "transient_grants"}
    assert sc.CLAUSE_WRITES["gust"] == both
    assert sc.CLAUSE_WRITES["self_switch"] == both
    assert "allowance_retreat_used" not in sc.CLAUSE_WRITES["self_switch"]
    assert sc.CLAUSE_WRITES["confuse_target"] == {"special_conditions"}
    # `transient_grants` is homed on BOTH sides for the same reason `attached_energy` is: a gust
    # clears the OPPONENT's Active's attack effects, and a my-side-only home would declare a write
    # the snapshot could not show.
    assert sc.homes()["transient_grants"] == ["mine.active.grant", "theirs.active.grant"]
    # The pull itself is deterministic — I choose the target off a public Bench. Only the COIN in
    # front of Pokemon Catcher's copy is not, and that is `coin`'s entry, not this one.
    assert "gust" not in sc.NONDETERMINISTIC_CLAUSES
    assert sc.clauses_writing_unhomed() == {}


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_stadium_kinds_delegate_their_write_to_the_effect_they_resolve_into():
    """**Issue #304's write-sets.** A Stadium is not one mechanic — the 22 in the pool are five
    unrelated effect shapes wearing one card type — so it gets two kinds, and neither carries a
    write-set of its own. What each one writes is what its `effect` names, which is 1120 Crushing
    Hammer's `coin` shape and the reason the Issue #300 walk covers `effect` at all.

    **Both kinds reading EMPTY is the assertion, not an omission**, and the case is pinned two ways
    so the reading cannot rot: the kinds are empty, AND every `effect` value they resolve into is
    declared. Reading `stadium_static == frozenset()` as *"a Stadium writes nothing"* is exactly the
    defect Crushing Hammer taught.

    Only `hp_delta` writes the snapshot. Lively Stadium's +30 and Gravity Mountain's −30 move a
    body's max HP, and `damage_counters` is the zone homed on the HP read. The three damage
    modifiers are read by `CombatMath` off the `stadium` zone when it prices an attack and store
    nothing, so declaring a write for them would claim a change that never happens."""
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
        assert sc.CLAUSE_WRITES[read_only] == frozenset(), read_only
    # A Stadium's board write — the displacement and the allowance — is STRUCTURAL, so it is
    # `apply_option`'s `_PLAY` footprint's and not any card's clauses'. Asserted here so the two
    # halves of one mechanic cannot drift into each declaring the other's job.
    assert {"stadium", "allowance_stadium_played"} <= ao.footprint(_PLAY).writes
    assert not any("stadium" in zs for zs in
                   (sc.CLAUSE_WRITES["stadium_static"], sc.CLAUSE_WRITES["stadium_trigger"]))
    assert sc.clauses_writing_unhomed() == {}


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_damage_counters_is_homed_on_BOTH_sides_and_on_the_bench():
    """A symmetric Stadium writes this zone on bodies that are neither mine nor Active (Issue #304):
    Gravity Mountain is *"Each Stage 2 Pokémon in play (both yours and your opponent's)"*, and Risky
    Ruins places 2 counters on whichever player just benched a Basic. A my-Active-only home would
    declare a write the snapshot cannot show — the same argument that already homes `attached_energy`
    and (Issue #303) `transient_grants` on both sides.

    The home was too narrow before those clauses landed, which is why this is a fix and not merely an
    accommodation: `heal` writes here too and 1096 Poke Vital A heals *"1 of your Pokémon"*, benched
    or not."""
    assert sc.homes()["damage_counters"] == [
        "mine.active.hp_remaining", "mine.bench", "theirs.active.hp_remaining", "theirs.bench"]
    # The bench legs name the CONTAINER, exactly as `bodies_in_play` does; each `BodyView` inside it
    # carries the per-body reads. Asserted so "mine.bench" cannot be read as a scalar HP field.
    assert hasattr(sm.BodyView, "hp_remaining") and hasattr(sm.BodyView, "damage_counters")
    assert sc.homes()["bodies_in_play"] == ["mine.active", "mine.bench", "theirs.active",
                                            "theirs.bench"]


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_two_refresh_riders_declare_exactly_the_hands_they_move():
    """**Issue #302's write-sets.** Two new riders, and the reason each is its own key rather than a
    reuse of `shuffle_both_hands` is the same both times: the difference between them IS the card.

    `shuffle_own_hand_in` is the ONE-SIDED refresh — Lillie's Determination (24 copies, our largest
    partial exposure) and Lacey shuffle only MY hand away. It is `shuffle_both_hands` minus
    `their_hand_size` and `their_deck_count`, and declaring those two would claim a strip the card
    never performs. `common/strategy/refresh.py`'s ADR-0060 oracle already splits on exactly this
    (`opponent_shuffles`), so the compendium agreeing with it is one fact stated once.

    `both_hands_to_bottom` writes the SAME six zones as `shuffle_both_hands` — a hand leaving for the
    deck is the same set of writes wherever in the deck it lands — and is still a distinct key,
    because to-BOTTOM and shuffled-IN are different facts about `deck_order`, a distinction
    `other_to_bottom` already keeps for the dig riders.

    Both are NONDETERMINISTIC: both shuffle, so both defeat the determinism proof the engine route
    needs, exactly as `shuffle_both_hands` does."""
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
    """**Issue #302's other axis.** `CLAUSE_WRITES` audits the VALUES of `kind` / `rider` / `effect`;
    until now nothing audited the KEYS, so a parameter no reader knows — a typo, or a shape authored
    ahead of the consumer meant to read it — sat in the store and priced exactly 0. That is the same
    silent zero the module exists to prevent, arriving through the other axis of the same dict.

    The walk descends into `amount_if`, so a typo one level down is as visible as one at the top."""
    keys = sc.clause_keys(_compendium())
    assert sc.undeclared_clause_keys(keys) == [], (
        "clause keys with no CLAUSE_PARAMETERS entry: %s" % sc.undeclared_clause_keys(keys))
    # The three shapes Issue #302 minted, and the nested block they live beside.
    assert {"to_hand_size", "amount_if", "cost_required", "condition"} <= set(keys)
    # Every VOCABULARY key is also a parameter key — one dict, two axes, not two vocabularies.
    assert set(sc.VOCABULARY_KEYS) <= set(sc.CLAUSE_PARAMETERS)
    # Every declared parameter says what it carries; an undescribed key is an undocumented one.
    assert [k for k, v in sc.CLAUSE_PARAMETERS.items() if not str(v).strip()] == []


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_clause_KEY_audit_actually_bites_including_inside_a_nested_block():
    """The positive control for the walk above. A green key audit means nothing unless the check can
    go red, and it must go red for a typo NESTED inside `amount_if` as well as for a top-level one —
    the nested case is the one a shallow walk would pass by not looking."""
    assert sc.undeclared_clause_keys(["a_parameter_nobody_declared"]) == \
        ["a_parameter_nobody_declared"]
    fabricated = {"999": [{"kind": "draw", "amount": 2,
                           "amount_if": {"condition": "x", "amonut": 4}}]}
    assert sc.undeclared_clause_keys(sc.clause_keys(fabricated)) == ["amonut"]
    # …and the same walk on the same fabricated card finds the legitimate nested key too, so the
    # single result above is a measurement rather than a walk that reached nothing.
    assert "condition" in sc.clause_keys(fabricated)


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_two_board_scaled_magnitudes_are_declared_and_stay_TWO_keys():
    """**Issue #349.** A clause could say *how many* (`amount`) and *how many until* (`to_hand_size`),
    but not *how many PER*. Two printed shapes were neither, and the issue left it open whether they
    are one key or two — *"argued either way, but the argument is written down"*. They are two, and
    this is the argument made executable.

    Card text quoted from the engine dump `tools/meta_tracker/cards.json` (`all_card_data()`), never
    recalled:

    * `amount_per` — **AGGREGATE**. 1187 Morty's Conviction: *"Draw a card for each of your
      opponent's Benched Pokémon."* One `amount`, multiplied by a count of bodies that are NOT the
      clause's targets, landing in ONE destination (my hand). The counted set is not derivable from
      anything else on the clause, so the key names it: a string.
    * `each_of` — **DISTRIBUTE**. 1222 Fennel: *"Heal 40 damage from each of your Pokémon."* The FULL
      `amount` to EVERY body the clause already targets. The set is `target`, which the clause
      carries, so re-naming it here would be a second body-class namespace beside `target` and
      `applies_to` — the drift `unknown_zones` exists to prevent, one axis over. A boolean.

    **They cannot share a key, and the failure is not symmetric.** A consumer that read Fennel's
    distribution as a multiplier would credit my Active `40 × 5 = 200` on a full board instead of 40
    — an OVER-count on a survival read, which is the KO_SCORE-class phantom this codebase refuses.
    Nothing on the clause could recover which was meant: `kind` does not decide it either, because
    the same board set is counted aggregately by one card and distributed over by another (62
    Koraidon: *"This attack does 30 damage for each of your Ancient Pokémon in play"* against 1085
    Awakening Drum's draw over that identical set). Aggregate-vs-distribute is ORTHOGONAL to both
    `kind` and the body set, so it needs its own key rather than a rule for inferring it.

    **Both are PARAMETERS, not `VOCABULARY_KEYS`**, and `applies_to` is the standing precedent rather
    than a judgement made here: it too is a string-valued body-class selector drawn from a closed set
    and it too lives in `CLAUSE_PARAMETERS`, because the discriminator is *names a WRITE*, not *is a
    string*. Neither of these writes anything — the write is still the clause `kind`'s."""
    for key in ("amount_per", "each_of"):
        assert key in sc.CLAUSE_PARAMETERS, key
        assert sc.CLAUSE_PARAMETERS[key].strip(), key
        assert key not in sc.VOCABULARY_KEYS, (
            f"{key} names no write — it modifies a magnitude, and the write is still the kind's")
        assert key not in sc.CLAUSE_WRITES, key
    # Declared, and actually USED — a parameter no card carries would be untested prose.
    payload = _compendium()
    clauses = {cid: cls for cid, cls in sc.clause_lists(payload).items()}
    carriers = {k: sorted(cid for cid, cls in clauses.items() if any(k in c for c in cls))
                for k in ("amount_per", "each_of")}
    assert carriers["amount_per"] == [1085, 1187], carriers["amount_per"]
    assert carriers["each_of"] == [1089, 1222, 1242], carriers["each_of"]
    # The shapes, off the artifact. `amount_per` names its set; `each_of` defers to `target`.
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
    # `CLAUSE_PARAMETERS` declares the two MUTUALLY EXCLUSIVE. A declared invariant nothing checks is
    # the toothless kind, and this one is cheap: a clause carrying both would be claiming its
    # magnitude is simultaneously multiplied by one set and distributed over another, which is not a
    # shape any card prints. (`to_hand_size` / `amount` carry the same declared exclusion, asserted
    # in `tests/cards/test_card_effects.py` — this is that discipline on the new pair.)
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
    """The positive control for the pair above. Green on the real compendium proves nothing unless the
    same walk goes red on a near-miss — and the near-miss that matters is a plausible MISSPELLING of
    the two keys this issue mints, since those are the strings an author will next type by hand."""
    fabricated = {"1": [{"kind": "draw", "amount": 1, "amount_pre": "their_bench"},
                        {"kind": "heal", "amount": 40, "target": "any_pokemon", "each_off": True}]}
    assert sc.undeclared_clause_keys(sc.clause_keys(fabricated)) == ["amount_pre", "each_off"]
    # …and the same walk on the same payload finds the legitimate keys, so the result above is a
    # measurement rather than a walk that reached nothing.
    assert {"amount", "target", "kind"} <= set(sc.clause_keys(fabricated))
    # The correctly-spelled pair must come back CLEAN through the same call — without this the
    # assertion above is green whether or not the two keys were ever declared, which is the shape of
    # control that proves nothing.
    assert sc.undeclared_clause_keys(["amount_per", "each_of"]) == []


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_clause_map_names_no_zone_the_registry_has_never_heard_of():
    """One vocabulary, not two. A write-set naming an invented zone would look like coverage while
    corresponding to nothing the snapshot was ever checked for."""
    assert sc.unknown_zones() == {}


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_no_clause_the_compendium_knows_writes_to_a_zone_with_no_home():
    """**The strong invariant.** Owed zones are a schedule; a clause that already writes to one makes
    them a defect — the seam would model that clause and the delta would silently omit part of what
    it did. Non-empty here means the zone must be homed BEFORE that clause is modelled.

    **It reads as a complete statement about what the compendium writes, so it must be told which
    axes it is complete OVER** (Issue #350). It walks `CLAUSE_WRITES`, whose keys are the values of
    all four :data:`snapshot_coverage.VOCABULARY_KEYS` — `kind`, `rider`, `effect` and, since this
    issue, `cost`. Until Issue #300 it was three and `effect` was silently outside it; until Issue
    #350 it was three-plus-`cost`-missing and Ultra Ball's two discarded cards were outside it. The
    second assertion is what keeps the sentence honest, and it is a SUBSET rather than the equality
    `test_the_audit_walks_all_four_vocabularies_including_effect_and_cost` owns: a FIFTH axis is that
    test's business and must not redden this one too, but NARROWING the list back would make this
    docstring a lie, and that is what fails here."""
    assert sc.clauses_writing_unhomed() == {}
    assert {"kind", "rider", "effect", "cost"} <= set(sc.VOCABULARY_KEYS), (
        "the invariant above is only as complete as the axes CLAUSE_WRITES is keyed on — dropping "
        "one silently narrows what 'no clause the compendium knows' means")


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_homes_resolve_against_the_real_snapshot_classes():
    """What makes a claimed home true rather than aspirational. Resolved against the classes so a
    renamed or deleted attribute fails here — the registry is only worth having if it tracks the
    code it describes."""
    broken = {zone: [p for p in paths if not _resolve(p)]
              for zone, paths in sc.homes().items()}
    broken = {z: p for z, p in broken.items() if p}
    assert broken == {}, f"registry claims snapshot reads that do not exist: {broken}"


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_the_audit_actually_bites():
    """A green audit means nothing unless the check can go red. Exercised on a fabricated clause, so
    the four green assertions above are evidence rather than an empty walk."""
    assert sc.undeclared_clauses(["a_clause_that_does_not_exist"]) == ["a_clause_that_does_not_exist"]


# ── the §3c minimum list, and what is still owed ──────────────────────────────────────────────────


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_the_issue_minimum_zone_list_is_all_enumerated():
    """§3c names a minimum set outright. Enumerated-and-owed is a fine answer; ABSENT is not — an
    unenumerated zone is one nobody has decided about, which is the silence the registry replaces."""
    for zone in ("my_discard_contents", "their_discard_contents", "my_hand_ids", "their_hand_size",
                 "my_deck_count", "their_deck_count", "deck_odds", "my_prizes", "their_prizes",
                 "stadium", "attached_tools", "damage_counters", "special_conditions",
                 "allowance_energy_attached", "allowance_supporter_played",
                 "allowance_retreat_used", "transient_grants"):
        assert zone in sc.BY_ID, zone


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_both_discards_carry_CONTENTS_not_only_energy_counts():
    """§3c calls this out by name — *"both discards including contents (not only energy counts)"* —
    because the pre-existing snapshot had `discard_energy_counts` and nothing else, so a discard's
    actual cards were invisible to every recursion and re-access read."""
    assert sc.BY_ID["my_discard_contents"].status == sc.HOMED
    assert sc.BY_ID["their_discard_contents"].status == sc.HOMED
    assert hasattr(sm.MySide, "discard_ids") and hasattr(sm.TheirSide, "discard_ids")


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_the_owed_list_is_empty_because_T1_carried_it():
    """**T0 shipped four owed zones with T1 named as their owner; T1 (Issue #260) homed all four.**
    The list is pinned EMPTY rather than deleted, because the assertion's value is in the direction
    it fails: a newly-owed zone appearing here is a real regression in coverage, and an `owed` entry
    that arrives without a named owner is the silence the registry exists to replace."""
    assert sc.unhomed() == {}
    for owner in sc.unhomed().values():          # vacuous today; the rule outlives the emptiness
        assert "Issue #" in owner


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_a_this_turn_damage_boost_is_ENUMERATED_and_homed_on_both_sides():
    """The zone Issue #282 added, and the reason absence is worse than `owed`.

    A this-turn flat damage boost IS state a card effect writes — Premium Power Pro's *"During this
    turn, attacks used by your {F} Pokémon do 30 more damage"* — and the registry did not name it at
    all. Nothing here could then be about it: an `owed` zone is a scheduled gap with an owner, while
    an unenumerated one is invisible to every assertion in this module.

    It is homed on BOTH sides deliberately. A boost is open information in either direction (the play
    is in the log both players see, an attached boost Tool is on the board), so `survival` reading
    THEIR boosted attack needs `theirs.damage_boosts` exactly as `threat` needs mine — and a
    my-side-only home would declare a write the snapshot could only half show, which is the same
    silent zero one level down that `attached_energy` already carries a two-sided home for."""
    zone = sc.BY_ID["this_turn_damage_boosts"]
    assert zone.status == sc.HOMED
    assert sorted(sc.homes()["this_turn_damage_boosts"]) == ["mine.damage_boosts",
                                                             "theirs.damage_boosts"]
    assert hasattr(sm.MySide, "damage_boosts") and hasattr(sm.TheirSide, "damage_boosts")


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_the_unhomed_guard_cannot_see_a_card_with_no_clauses_at_all():
    """**The limitation Issue #282 asks to be recorded, as a test rather than only a docstring.**

    Both `unhomed` guards work off DECLARED write-sets: `clauses_writing_unhomed()` walks the
    compendium, and `footprints_writing_unhomed()` walks the per-KIND footprints. A card with NO
    clauses unions to the empty set, so neither guard can ever report it, however much state it
    writes. The three boost cards are exactly that shape, which is asserted here against the
    committed compendium so the claim cannot rot into an anecdote.

    The control is the second assertion: the same lookup DOES return clauses for a card that has
    them, so an empty answer above is evidence about those cards rather than about a broken read.

    **Restated 2026-08-03, when Issue #298's batch gave `_PLAY` a footprint.** This test previously
    asserted `_PLAY` was ABSENT from :data:`apply_option.FOOTPRINTS` — that was the mechanism, not
    the finding, and asserting the mechanism made the test fail on a change that did not touch the
    limitation at all. `_PLAY` now carries a footprint of the STRUCTURAL zones every play moves (the
    card leaves hand, a Stadium swaps, an allowance is spent, a Basic reaches the Bench), and every
    one of them is HOMED. It is `complete=False` precisely because the card's own EFFECT is still
    not covered — that comes from its clauses, to be unioned at T4. So the guard still reports
    nothing for a clause-less card, and the limitation Issue #282 asked to be recorded is untouched.
    The assertions below now pin THAT, which is the thing that must not silently change."""
    compendium = _compendium()
    for cid in ("1141", "1211", "1175"):             # Power Pro, Black Belt's Training, Brave Bangle
        assert compendium.get(cid) is None, cid
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
    """The strong claim §3c was written for, now actually true.

    At T0 this was the opposite assertion: EVOLVE cleared Special Conditions and RETREAT spent the
    retreat allowance, both zones with no snapshot home, so part of what those transitions did was
    invisible — and an under-reported delta is a PRUNED option, not a mispriced one (ADR-0092 §3c).
    T1 homed `special_conditions` (`_SideBase.conditions`) and `allowance_retreat_used`
    (`StateModel.retreated`), so the apply-seam's whole write-set is now representable.

    Kept as an equality against the empty dict rather than deleted: the moment a new option kind or
    a new clause names a zone the snapshot cannot hold, this is where it surfaces."""
    assert ao.footprints_writing_unhomed() == {}
    assert sc.clauses_writing_unhomed() == {}


# ── clause-set completeness: a PARTIAL set must not price as a complete one (Issue #300) ───────────


@pytest.mark.req("REQ-SNAPSHOT-0004")
def test_every_clause_bearing_card_declares_whether_its_clause_set_is_COMPLETE():
    """**The teeth for the compendium half.** A card with clauses and no verdict reads as *unknown*,
    and an unknown clause set is indistinguishable from a complete one at the seam — which is exactly
    the "model three quarters of the card and price the rest at 0" failure §3c forbids one level up.

    `covers_problems` also refuses an unreasoned verdict: the reason quotes the leg the clauses carry
    or miss, and without it the ruling cannot be re-checked against the printed card."""
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
    """The owed list, generated off the artifact rather than re-derived.

    *Surfer* used to be the worked example here — `draw 1` on a card that SWITCHES the Active first —
    and Issue #302 closed it (the switch is now the `self_switch` rider), which is what a shrinking
    owed list is supposed to look like. The example moved to *Judge*, whose leg cannot be closed the
    same way: the card is SYMMETRIC, and pricing the opponent's shuffled-away hand needs a
    `state_value` term the POC does not have, so it is a declared unknown rather than unfinished
    work."""
    partial = sc.partial_clause_cards(_compendium())
    assert partial, "no card is declared partial — the audit would be reporting on nothing"
    assert 1213 in partial and "symmetric" in partial[1213].lower()
    assert all(reason.strip() for reason in partial.values())
    # Declared partial ⇒ actually clause-bearing. A verdict about an absent clause set is a comment.
    clauses = sc.clause_lists(_compendium())
    assert all(cid in clauses for cid in partial)


@pytest.mark.req("REQ-SNAPSHOT-0004")
def test_the_partial_list_only_ever_SHRINKS():
    """Same shape and same reason as `footprints_writing_unhomed()` being asserted empty: an owed list
    that can grow silently is not a schedule. A card LEAVING the baseline is clause work landing — no
    failure. A card ARRIVING is either new exposure that owes a ruling or a verdict quietly
    downgraded, and both want a human before they land."""
    grown = set(sc.partial_clause_cards(_compendium())) - sc.PARTIAL_CLAUSE_BASELINE
    assert grown == set(), (
        f"card(s) {sorted(grown)} became PARTIAL after the baseline was ruled. Either close the "
        f"clause gap, or rule the addition and extend `PARTIAL_CLAUSE_BASELINE` deliberately.")


@pytest.mark.req("REQ-SNAPSHOT-0004")
def test_a_partial_verdict_fails_CLOSED_and_stays_distinguishable_from_an_unruled_one():
    """The seam-facing half: the tri-state `apply_option.fate` takes for ``clauses_cover``.

    `False` and `None` both refuse, and they are still different facts — *ruled incomplete* is a
    measured gap with an owner, *unruled* is a card nobody has looked at. Collapsing them would make
    the owed list unreadable, which is the same reason `deterministic` is tri-state."""
    assert sc.clauses_cover(sc.COVERS_FULL) is True
    assert sc.clauses_cover(sc.COVERS_PARTIAL) is False
    assert sc.clauses_cover(None) is None
    assert sc.clauses_cover("anything else") is None


@pytest.mark.req("REQ-SNAPSHOT-0004")
def test_the_reserved_covers_key_is_never_read_as_a_clause_list():
    """`card_effects.json` is `{cardId: [clauses]}` plus one reserved key. Every reader goes through
    the shared parse for exactly this reason — a hand-rolled `int(k)` walk would either crash on it or
    quietly treat the verdict block as a 59th card's clauses."""
    payload = _compendium()
    assert sc.COVERS_KEY in payload
    assert sc.COVERS_KEY not in {str(cid) for cid in sc.clause_lists(payload)}
    assert set(sc.clause_lists(payload)) == set(sc.covers_table(payload)), (
        "the clause lists and the verdicts must cover exactly the same cards")
    # The verdict block carries its own authored `_note` into the SHIPPED artifact — a compendium
    # that carries a vocabulary but not the sentence explaining where it is edited sends its next
    # reader to the wrong file. It is reserved, so no card walk may pick it up.
    assert "_note" in payload[sc.COVERS_KEY] and "effect_overrides.json" in \
        payload[sc.COVERS_KEY]["_note"]
    assert not sc.is_card_key("_note") and not sc.is_card_key(sc.COVERS_KEY)
