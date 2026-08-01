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


def _clause_vocabulary() -> set[str]:
    """Every `kind` and `rider` value in the committed compendium. Read from the artifact, not from a
    hand-kept list — a hand-kept list is exactly what a new clause would not be added to."""
    vocab: set[str] = set()
    for clauses in json.loads(_EFFECTS.read_text(encoding="utf-8")).values():
        for c in clauses:
            if c.get("kind"):
                vocab.add(c["kind"])
            rider = c.get("rider")
            if isinstance(rider, str):
                vocab.add(rider)
            elif isinstance(rider, (list, tuple)):
                vocab.update(r for r in rider if isinstance(r, str))
    return vocab


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
def test_every_clause_kind_and_rider_in_the_compendium_declares_what_it_writes():
    """**The §3c audit test.** A new clause kind with no declared write-set lands here rather than
    silently writing to nothing — which, under differencing, prices its option at exactly 0 and
    prunes it forever."""
    vocab = _clause_vocabulary()
    assert vocab, "read no clause vocabulary at all — the audit would pass vacuously"
    assert sc.undeclared_clauses(sorted(vocab)) == [], (
        "clause kind(s)/rider(s) in card_effects.json with no entry in CLAUSE_WRITES. Declare what "
        "each one writes, in `snapshot_coverage.WRITABLE` vocabulary.")


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
def test_the_owed_list_is_exactly_what_T1_is_carrying():
    """Pinned so the set can only SHRINK without a deliberate edit. A newly-owed zone appearing here
    is a real regression in coverage and should be seen as one, not absorbed."""
    assert set(sc.unhomed()) == {
        "attached_tools", "special_conditions", "allowance_retreat_used", "transient_grants"}
    for owner in sc.unhomed().values():
        assert "Issue #260" in owner


@pytest.mark.req("REQ-SNAPSHOT-0003")
def test_the_kinds_whose_transition_touches_an_unhomed_zone_are_named():
    """Not empty, and that is the point. Evolving CLEARS Special Conditions (`docs/rules.md` §4) and
    so does leaving the Active Spot (§8) — both rulebook-sourced — while `special_conditions` has no
    snapshot home, and retreat also touches the unhomed retreat allowance.

    That is §3c's failure mode in the concrete: part of what those transitions do is invisible, so
    the delta under-reports and an under-reported delta is a pruned option. Named here so T1 has a
    generated work list instead of a paragraph, and so the set cannot grow unnoticed."""
    from common.strategy.context import _EVOLVE, _RETREAT
    touching = ao.footprints_writing_unhomed()
    assert set(touching) == {_EVOLVE, _RETREAT}
    assert touching[_EVOLVE] == ["special_conditions"]
    assert touching[_RETREAT] == ["allowance_retreat_used", "special_conditions"]
