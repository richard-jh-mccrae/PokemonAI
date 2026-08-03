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
def test_the_audit_walks_all_three_vocabularies_including_effect():
    """**The Issue #300 hole, as a test.** The walk used to cover `kind` and `rider` only, so
    Crushing Hammer's `{"kind": "coin", "effect": "discard_opp_energy"}` passed green while the write
    it performs — the opponent's Energy, and their discard — had no declared home at all.

    Asserted two ways, because either alone would rot: that the key list IS all three, and that the
    value actually in the compendium comes back out of the walk. A walk that names `effect` but never
    meets one would be an audit passing by absence."""
    assert sc.VOCABULARY_KEYS == ("kind", "rider", "effect")
    assert "discard_opp_energy" in sc.clause_vocabulary(_compendium())
    assert sc.CLAUSE_WRITES["discard_opp_energy"] == {"attached_energy", "their_discard_contents"}
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
def test_the_clause_map_names_no_zone_the_registry_has_never_heard_of():
    """One vocabulary, not two. A write-set naming an invented zone would look like coverage while
    corresponding to nothing the snapshot was ever checked for."""
    assert sc.unknown_zones() == {}


@pytest.mark.req("REQ-SNAPSHOT-0002")
def test_no_clause_the_compendium_knows_writes_to_a_zone_with_no_home():
    """**The strong invariant.** Owed zones are a schedule; a clause that already writes to one makes
    them a defect — the seam would model that clause and the delta would silently omit part of what
    it did. Non-empty here means the zone must be homed BEFORE that clause is modelled."""
    assert sc.clauses_writing_unhomed() == {}


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
    """The owed list, generated off the artifact rather than re-derived. *Surfer* is the worked
    example the census led with: it carries `draw 1`, and the printed card SWITCHES the Active first
    — the reason it is played at all."""
    partial = sc.partial_clause_cards(_compendium())
    assert partial, "no card is declared partial — the audit would be reporting on nothing"
    assert 1203 in partial and "switch" in partial[1203].lower()
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
