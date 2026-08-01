"""**StateModel completeness, as a contract** (POC-T0 / Issue #259 §3c, ruled 2026-08-01).

> *"All fields should certainly be covered — we want to minimize this risk."*

The differencing system's worst failure mode is an effect that writes to state the snapshot cannot
represent. `state_value(after) − state_value(before)` then reads **0**, and under the composer's
1-ply ordering (Issue #263) 0 does not mean *undervalued* — it means **never explored**. The option
is silently pruned and nothing reports why. That is strictly worse than a crash, so completeness is
asserted rather than hoped for.

This module is the enumeration, as data:

* :data:`WRITABLE` — every zone or marker a card effect can write, each with its snapshot home, or
  an explicit reason it has none. Three statuses, and the third is the honest one:

  - ``homed``  — a public snapshot read represents it. The home is a dotted path, resolved against
    the real classes by `test_snapshot_coverage.py`, so a rename breaks the test rather than the
    contract.
  - ``owed``   — no home yet. **Must name the track that owes it.** T0 ships interfaces; T1
    (Issue #260) implements, so an owed entry is a work item, not an excuse.
  - ``hidden`` — deliberately unrepresented because it is *hidden information*. Deck ORDER is the
    case: no snapshot can hold it, and the odds machinery (`deck_odds`, `unseen_counts`) is what
    prices it. Recorded so a later reader does not "fix" it by inventing a field.

* :data:`CLAUSE_WRITES` — the Effect Clause vocabulary (`card_effects.json`, ADR-0032) mapped to the
  zones each clause writes. The audit test walks the committed compendium and fails on a clause kind
  or rider with **no declared write-set**, which is the "a new clause kind must fail rather than
  silently price 0" requirement made executable.

The strongest assertion this enables is :func:`clauses_writing_unhomed`: **no clause the compendium
knows may write to an `owed` zone.** It is empty today, and it is what keeps the owed list from
quietly becoming a live correctness hole rather than a scheduled one.

`apply_option`'s per-kind READ/WRITE footprints speak this same field vocabulary — one store, so a
footprint cannot name a zone the coverage registry has never heard of.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

#: A public snapshot read represents this zone.
HOMED = "homed"
#: No snapshot home yet; an owning track is named.
OWED = "owed"
#: Deliberately unrepresented — hidden information, priced by the odds machinery instead.
HIDDEN = "hidden"

STATUSES = frozenset({HOMED, OWED, HIDDEN})


@dataclass(frozen=True)
class Zone:
    """One writable zone or marker of game state."""

    #: Stable slug. `apply_option`'s footprints and the clause map both cite this.
    id: str
    #: What it is, in board terms.
    description: str
    #: One of :data:`STATUSES`.
    status: str
    #: ``homed`` ONLY: dotted path(s) from `StateModel`, comma-separated when more than one read
    #: composes the answer. Resolved against the real classes by the audit test.
    home: str = ""
    #: ``owed`` ONLY: the track/issue that owes the read. An owed zone with no owner is a silence.
    owner: str = ""
    #: ``hidden`` ONLY: why no field can represent it, and what prices it instead.
    priced_by: str = ""


#: §3c's enumeration. The "At minimum:" list from the issue body, plus the zones the Effect Clause
#: vocabulary actually writes.
WRITABLE: tuple[Zone, ...] = (
    Zone("my_discard_contents", "my discard pile, by card id — not only energy counts", HOMED,
         home="mine.discard_ids"),
    Zone("their_discard_contents", "their discard pile, by card id", HOMED,
         home="theirs.discard_ids"),
    Zone("my_hand_ids", "my hand, by card id", HOMED, home="mine.hand_ids"),
    Zone("their_hand_size", "their hand, by COUNT — the only honest read of a hidden zone", HOMED,
         home="theirs.hand_size"),
    Zone("my_deck_count", "cards left in my deck", HOMED, home="mine.deck_count"),
    Zone("their_deck_count", "cards left in their deck", HOMED, home="theirs.deck_count"),
    Zone("deck_odds", "the sound-emptiness and Deck-Content Odds reads over my deck (ADR-0029)",
         HOMED, home="mine.unseen_counts,mine.visible_counts,mine.prizes_hidden"),
    Zone("my_prizes", "my prizes remaining", HOMED, home="mine.prizes_remaining"),
    Zone("their_prizes", "their prizes remaining", HOMED, home="theirs.prizes_remaining"),
    Zone("stadium", "the Stadium in play", HOMED, home="stadium"),
    Zone("bodies_in_play", "who is Active and who is Benched, both sides", HOMED,
         home="mine.active,mine.bench,theirs.active,theirs.bench"),
    Zone("attached_energy", "Energy attached to a body", HOMED,
         home="mine.active.energy_count,mine.active.attached_types"),
    Zone("damage_counters", "damage on a body — heal writes it, attacks write it", HOMED,
         home="mine.active.hp_remaining"),
    Zone("allowance_energy_attached", "the one-Energy-per-turn allowance, spent or not", HOMED,
         home="energy_attached"),
    Zone("allowance_supporter_played", "the one-Supporter-per-turn allowance", HOMED,
         home="supporter_played"),

    # ── owed: enumerated by §3c, no public read yet. T0 ships interfaces; T1 implements. ──────────
    Zone("attached_tools", "Pokémon Tools attached to a body", OWED,
         owner="T1 / Issue #260 — the raws already carry a `tools` key (`_SideBase` body raws); "
               "what is missing is a typed BodyView read, so this is a promotion, not new plumbing"),
    Zone("special_conditions", "per-body Special Conditions (Asleep/Paralyzed/Burned/Poisoned/"
                               "Confused)", OWED,
         owner="T1 / Issue #260 — `MySide.attack_blocked` derives the two that block acting "
               "(rulebook L190/L206) but collapses them to one bool on the SIDE; the per-body "
               "condition set has no read"),
    Zone("allowance_retreat_used", "whether the one-Retreat-per-turn allowance is spent", OWED,
         owner="T1 / Issue #260 — the observation carries `current.retreated`; the snapshot does "
               "not surface it, so a retreat's own legality cannot be differenced"),
    Zone("transient_grants", "ADR-0033 transient grants and locks in force this turn", OWED,
         owner="T1 / Issue #260 — only `StateModel._transient_generation` exists, and it is a "
               "PRIVATE cache-invalidation counter, not a read of the grants themselves"),

    # ── hidden: no field can hold it. Recorded so nobody 'fixes' it. ──────────────────────────────
    Zone("deck_order", "the ORDER of cards in a deck — what a shuffle and a to-bottom rider change",
         HIDDEN,
         priced_by="Unknowable from an observation, and the reason the apply-seam refuses anything "
                   "riding a shuffle: the engine has no deal-seed, so a simulated shuffle is ONE "
                   "SAMPLE, not a distribution. Priced as a distribution by `deck_odds` "
                   "hypergeometrics instead (ADR-0029), which is `deck_odds` above."),
)

#: id -> Zone.
BY_ID = {z.id: z for z in WRITABLE}

#: The Effect Clause vocabulary (`card_effects.json`, ADR-0032) -> the zones each clause WRITES.
#: Keys are the committed `kind` and `rider` values. The audit test walks the compendium and fails on
#: any kind or rider absent here — that is the "a new clause kind fails rather than silently pricing
#: 0" requirement, executable.
CLAUSE_WRITES: dict[str, frozenset[str]] = {
    # kinds
    "accel": frozenset({"attached_energy", "my_discard_contents", "my_deck_count", "deck_odds"}),
    "coin": frozenset(),                     # writes nothing: it is an RNG READ. See COIN below.
    "draw": frozenset({"my_hand_ids", "my_deck_count", "deck_odds"}),
    "energy_provide": frozenset({"attached_energy", "allowance_energy_attached"}),
    "fetch": frozenset({"my_hand_ids", "bodies_in_play", "my_deck_count", "deck_odds"}),
    "heal": frozenset({"damage_counters"}),
    # riders
    "bounce_energy_to_hand": frozenset({"attached_energy", "my_hand_ids"}),
    "discard_basic_f_energy": frozenset({"my_hand_ids", "my_discard_contents"}),
    "discard_eot": frozenset({"attached_energy", "my_discard_contents"}),
    "discard_own_energy": frozenset({"attached_energy", "my_discard_contents"}),
    "other_to_bottom": frozenset({"my_deck_count", "deck_odds", "deck_order"}),
    "shuffle_both_hands": frozenset({"my_hand_ids", "their_hand_size", "my_deck_count",
                                     "their_deck_count", "deck_odds", "deck_order"}),
    "shuffle_self_in": frozenset({"bodies_in_play", "my_deck_count", "deck_odds", "deck_order"}),
}

#: Clauses that consult RNG. **Never eligible for the ENGINE-RESOLVED route** — the gate there is
#: *provably deterministic*, and the engine has no deal-seed, so simulating one of these returns a
#: single Monte-Carlo sample rather than a distribution (Issue #178's defect) AND breaks the
#: deterministic replay both gates depend on.
NONDETERMINISTIC_CLAUSES: frozenset[str] = frozenset({
    "coin", "other_to_bottom", "shuffle_both_hands", "shuffle_self_in",
})

#: Clauses that REVEAL information — they change the option set itself, not only the board. Issue
#: #263 must never fold one of these into a commutative block, whatever its read/write footprint
#: says: reordering around a reveal changes what the later choices are.
REVEALING_CLAUSES: frozenset[str] = frozenset({"draw", "fetch"})


def validate(zones: Sequence[Zone] = WRITABLE) -> list[str]:
    """Every way the registry fails its own discipline, as readable problems. Empty is the contract.

    A list rather than a raise, for the same reason `sound_rules.validate` is: an author fixing the
    registry wants every complaint at once."""
    problems: list[str] = []
    seen: set[str] = set()
    for z in zones:
        if z.id in seen:
            problems.append(f"{z.id}: duplicate id")
        seen.add(z.id)
        if z.status not in STATUSES:
            problems.append(f"{z.id}: status {z.status!r} is not one of {sorted(STATUSES)}")
        if not z.description.strip():
            problems.append(f"{z.id}: no description")
        if z.status == HOMED and not z.home.strip():
            problems.append(f"{z.id}: homed entries MUST name the snapshot read")
        if z.status == OWED and not z.owner.strip():
            problems.append(f"{z.id}: owed entries MUST name the track that owes them — an owed "
                            f"zone with no owner is a silence, not a schedule")
        if z.status == HIDDEN and not z.priced_by.strip():
            problems.append(f"{z.id}: hidden entries MUST say what prices them instead")
        if z.status != HOMED and z.home.strip():
            problems.append(f"{z.id}: only homed entries name a snapshot read")
    return problems


def homes() -> dict:
    """``{zone id: [dotted snapshot paths]}`` for every homed zone. The audit test resolves these
    against the real classes, so a renamed attribute fails there rather than rotting here."""
    return {z.id: [p.strip() for p in z.home.split(",") if p.strip()]
            for z in WRITABLE if z.status == HOMED}


def unhomed() -> dict:
    """``{zone id: owner}`` for every zone T1 still owes. The T1 checklist, generated rather than
    re-derived — and the set `clauses_writing_unhomed` is checked against."""
    return {z.id: z.owner for z in WRITABLE if z.status == OWED}


def undeclared_clauses(kinds: Sequence[str]) -> list[str]:
    """Clause kinds/riders with no declared write-set. **This is the §3c audit's teeth**: a new
    clause kind lands here rather than silently writing to nothing and pricing its option at 0."""
    return sorted(k for k in set(kinds) if k not in CLAUSE_WRITES)


def unknown_zones() -> dict:
    """``{clause: [zone ids]}`` naming a zone the registry has never heard of. Keeps `CLAUSE_WRITES`
    and :data:`WRITABLE` one vocabulary rather than two that drift."""
    return {clause: sorted(z for z in zs if z not in BY_ID)
            for clause, zs in CLAUSE_WRITES.items()
            if any(z not in BY_ID for z in zs)}


def clauses_writing_unhomed() -> dict:
    """``{clause: [owed zone ids]}`` — the strong one. Empty is the contract.

    A clause the compendium already knows, writing to a zone with no snapshot home, is a LIVE
    correctness hole: the seam would model that clause and the delta would silently omit part of
    what it did. Non-empty means the owed list has stopped being a schedule and started being a
    defect, and the zone must be homed before that clause is modelled."""
    owed = set(unhomed())
    return {clause: sorted(zs & owed) for clause, zs in CLAUSE_WRITES.items() if zs & owed}


__all__: Sequence[str] = (
    "HOMED", "OWED", "HIDDEN", "STATUSES", "Zone", "WRITABLE", "BY_ID", "CLAUSE_WRITES",
    "NONDETERMINISTIC_CLAUSES", "REVEALING_CLAUSES", "validate", "homes", "unhomed",
    "undeclared_clauses", "unknown_zones", "clauses_writing_unhomed",
)
