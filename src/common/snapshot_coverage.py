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
  zones each clause writes. The audit test walks the committed compendium and fails on a clause
  ``kind``, ``rider``, ``effect`` **or** ``cost`` with **no declared write-set**, which is the "a new
  clause kind must fail rather than silently price 0" requirement made executable.

  ``effect`` was the third of those and it was unaudited until Issue #300: :func:`clause_vocabulary`
  walked kinds and riders only, so Crushing Hammer's
  ``{"kind": "coin", "effect": "discard_opp_energy"}`` passed the audit green while the write it
  actually performs — the opponent's attached Energy, and their discard — had no declared home at
  all. The walk lives in THIS module rather than in the test for exactly that reason: a vocabulary
  the audit forgets to visit is an audit that passes by not looking.

  ``cost`` was the FOURTH and went the same way (Issue #350). Ultra Ball's ``"cost": "discard_2"``
  moves two real cards from my hand to my discard and Kofu's ``"bottom_2"`` puts two on the bottom
  of my deck; neither value could fail the audit however undeclared it was, because the walk did not
  visit the key. **The ruling is that `cost` JOINS `VOCABULARY_KEYS` rather than taking a registry
  of its own**, on three grounds, none of them "it is smaller":

  - It matches :data:`VOCABULARY_KEYS`' own printed definition — *a value drawn from a closed set
    that must have a declared write-set* — exactly as `kind` / `rider` / `effect` do.
  - **Union, not nesting**, and that was already ruled elsewhere rather than decided here:
    `apply_option.FOOTPRINTS` records that T4 supplies a played card's per-OPTION footprint *"by
    unioning `snapshot_coverage.CLAUSE_WRITES` over the card's clauses"*. A flat `value → zones`
    table unions by construction, so a cost's zones join its clause's with no new machinery. The
    `gust` entry is the standing precedent that position does not matter: one key serves it as a
    `kind` (Boss's Orders) and as an `effect` (Pokemon Catcher), because
    :func:`undeclared_clauses` looks the string up, never where it came from.
  - A second registry would need its own :func:`undeclared_clauses`, :func:`unknown_zones` and
    :func:`clauses_writing_unhomed` — four functions duplicated to hold five entries whose values
    are zone ids from the same :data:`BY_ID` namespace. That is the "two vocabularies that drift"
    :func:`unknown_zones` exists to prevent, and the drift that let `effect` go unaudited from the
    day it was authored.

* :data:`CLAUSE_PARAMETERS` — the same discipline on the OTHER axis of the same dict (Issue #302).
  `CLAUSE_WRITES` audits clause VALUES; nothing audited the clause KEYS, so a parameter no reader
  knows — a typo, or a shape authored ahead of the consumer that was meant to read it — sat in the
  store and priced exactly 0. :func:`undeclared_clause_keys` is its teeth.

  **The board-scaled magnitudes are TWO keys, not one** (Issue #349), and the issue left that open —
  *"two keys or one, argued either way, but the argument is written down"*. A clause could say how
  many (`amount`) and how many UNTIL (`to_hand_size`); it could not say how many PER, and two printed
  shapes are neither:

  - ``amount_per`` **AGGREGATES**. 1187 Morty's Conviction — *"Draw a card for each of your
    opponent's Benched Pokémon"* — is one `amount` times a count of bodies that are NOT the clause's
    targets, landing in ONE destination. Nothing else on the clause names that set, so the key does:
    a string.
  - ``each_of`` **DISTRIBUTES**. 1222 Fennel — *"Heal 40 damage from each of your Pokémon"* — is the
    full `amount` to EVERY body `target` already names. A boolean, because re-naming the set here
    would open a second body-class namespace beside `target` and `applies_to`, which is the drift
    :func:`unknown_zones` exists to prevent one axis over.

  They cannot share a key. The magnitudes differ by a factor of N and the collapse fails in the
  OVER-counting direction: read as a multiplier, Fennel credits my Active 200 on a full board instead
  of 40, which is a KO_SCORE-class phantom survival in `planner._heal_candidate`. Nor can `kind`
  decide it — the same board set is counted aggregately by one card and distributed over by another
  (62 Koraidon's *"30 damage for each of your Ancient Pokémon in play"* against 1085 Awakening Drum's
  draw over that identical set), so aggregate-vs-distribute is ORTHOGONAL to both `kind` and the set.

  Both are PARAMETERS rather than :data:`VOCABULARY_KEYS`, and ``applies_to`` is the standing
  precedent rather than a call made here: it too is a string-valued body-class selector from a closed
  set and it too lives in this registry, because the discriminator is *names a WRITE*, not *is a
  string*. A magnitude modifier writes nothing — the write is still the clause `kind`'s.

  **The consequence is a known gap and it is recorded rather than left silent:** ``amount_per``'s
  VALUES are unaudited. :func:`undeclared_clauses` walks only :data:`VOCABULARY_KEYS`, so a typo —
  ``"their_bnech"`` — passes both audits and prices exactly 0, which is this module's own stated
  failure mode one level down from the axis it just widened. That is not new and not specific to this
  key: ``target``, ``applies_to``, ``restriction``, ``source`` and ``name_family`` are all
  string-valued selectors in the same position — thirteen keys carrying 54 distinct values, none of
  them audited — so a per-key registry for this one alone would be both new machinery and
  inconsistent with twelve neighbours. Closing it properly means deciding whether ONE selector-value
  registry serves all thirteen, which is its own ruling and is filed as **Issue #374**. That issue
  also carries the live instance this gap has already produced: 1134 Team Rocket's Transceiver's
  ``name_family`` is spelled ``"Team Rocket"`` where 1218 and 1220 spell it ``"Team Rocket's"``, and
  `card_text.name_in_family`'s prefix test matches 0 of 6 Team Rocket's cards on the first spelling
  and 6 of 6 on the second. Until it lands the guard here is narrow and real:
  `test_snapshot_coverage.py` asserts each carrier's exact value off the committed artifact, so a
  typo in 1085 or 1187 fails there.

* :data:`COVERS_FULL` / :data:`COVERS_PARTIAL` — whether a card's clause SET covers its whole printed
  effect. A **partial** set is worse than none: §3b has no PARTIAL fate, so the seam models what the
  clauses say and the omitted leg differences to exactly 0 — the silent-zero failure this module
  exists to prevent, arriving through the compendium instead of through the snapshot. The verdict is
  authored per card (`tools/meta_tracker/effect_overrides.json` → `card_effects.json`, both under
  :data:`COVERS_KEY`) and :func:`clauses_cover` turns it into the tri-state `apply_option.fate`
  consumes, so a partial set REFUSES rather than pricing three quarters of a card.

The strongest assertion this enables is :func:`clauses_writing_unhomed`: **no clause the compendium
knows may write to an `owed` zone.** It is empty today, and it is what keeps the owed list from
quietly becoming a live correctness hole rather than a scheduled one.

`apply_option`'s per-kind READ/WRITE footprints speak this same field vocabulary — one store, so a
footprint cannot name a zone the coverage registry has never heard of.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Sequence

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
    # BOTH sides. Energy denial (`discard_opp_energy`) writes the OPPONENT's attachments, so a
    # my-side-only home would declare a write the snapshot could not actually show — the same silent
    # zero one level down. `TheirSide` shares `_SideBase.active`, so the read genuinely exists.
    Zone("attached_energy", "Energy attached to a body, either side", HOMED,
         home="mine.active.energy_count,mine.active.attached_types,"
              "theirs.active.energy_count,theirs.active.attached_types"),
    # BOTH sides, and the BENCH as well as the Active — the same argument `attached_energy` and
    # `transient_grants` already carry. A SYMMETRIC Stadium writes this zone on bodies that are
    # neither mine nor Active (Issue #304): Gravity Mountain's `hp_delta` is *"Each Stage 2 Pokémon
    # in play (both yours and your opponent's)"*, and Risky Ruins places its 2 counters on whichever
    # player just BENCHED a Basic. A my-Active-only home would declare a write the snapshot cannot
    # show — the silent zero one level down.
    #
    # The home was already too narrow before those clauses landed: `heal` writes here too and 1096
    # Poke Vital A heals *"1 of your Pokémon"*, benched or not. The bench legs name the CONTAINER,
    # exactly as `bodies_in_play` already does — every `BodyView` in it carries `hp_remaining` and
    # `damage_counters`.
    Zone("damage_counters", "damage on a body — heal writes it, attacks write it, and a symmetric "
                            "Stadium writes it on either side's Bench", HOMED,
         home="mine.active.hp_remaining,mine.bench,theirs.active.hp_remaining,theirs.bench"),
    Zone("allowance_energy_attached", "the one-Energy-per-turn allowance, spent or not", HOMED,
         home="energy_attached"),
    Zone("allowance_supporter_played", "the one-Supporter-per-turn allowance", HOMED,
         home="supporter_played"),

    # ── homed by T1 (Issue #260). Each was `owed` at T0 with this track named as its owner. ───────
    Zone("attached_tools", "Pokémon Tools attached to a body", HOMED,
         home="mine.active.tool_ids"),
    Zone("special_conditions", "Special Conditions on the Active (only the Active can carry one — "
                               "`docs/rules.md` §8, which is why the engine puts the five flags on "
                               "PlayerState rather than on the body)", HOMED,
         home="mine.conditions,theirs.conditions"),
    Zone("allowance_retreat_used", "whether the one-Retreat-per-turn allowance is spent", HOMED,
         home="retreated"),
    # BOTH sides, for the same reason `attached_energy` is. A `gust` (Issue #303) pulls the
    # OPPONENT's Active to their Bench, and `docs/rulebook.txt` L143 says what that does to it:
    # *"When your Active Pokémon goes to your Bench (whether it retreated or got there some other
    # way), some things do go away—Special Conditions and any effects from attacks."* A my-side-only
    # home would declare a write the snapshot could not show — the silent zero one level down.
    Zone("transient_grants", "ADR-0033 transient grants and locks in force this turn, either side",
         HOMED, home="mine.active.grant,theirs.active.grant"),
    Zone("bench_occupancy", "how many bodies each Bench holds, and whether it is full — the loss "
                            "condition's own state (`docs/rules.md` §7 case 2)", HOMED,
         home="mine.bench_count,theirs.bench_count"),
    Zone("allowance_stadium_played", "the one-Stadium-per-turn allowance", HOMED,
         home="stadium_played"),

    # ── enumerated by POC-T3.5 (Issue #282). It was ABSENT, not owed — the worse status. ──────────
    #
    # A zone marked `owed` is a scheduled gap with an owner; a zone nobody enumerated is one nobody
    # decided about, and no assertion in this module can be about it. That is how a whole class of
    # card slipped past the §3c audit: Premium Power Pro (1141), Black Belt's Training (1211) and
    # Brave Bangle (1175) have NO Effect Clauses at all — `card_effects.json` returns nothing for any
    # of them — so `clauses_writing_unhomed()` walks past them by construction, and every per-card
    # write-set is a union over clauses that unions to the empty set. Their effect lives entirely in
    # the parsed `CardStat.damageBoost` / `damageBoostType` / `damageBoostVsEx` triple.
    #
    # The READ existed before this entry did (`_SideBase.damage_boosts`, Issue #279) — this is an
    # enumeration catching up with a shipped home, not a new capability. Which is exactly why it was
    # easy to miss: the code was right and the contract could not say so.
    Zone("this_turn_damage_boosts",
         "the flat damage boosts live for a side's attacks this turn — a played Premium Power "
         "Pro / Black Belt's Training, and a boost Tool attached to that side's Active. "
         "((amount, attackerEnergyType|None, vsExOnly), ...), the shape `strategy/damage.py` "
         "consumes off the Damage Formula context's `atk_boosts` key", HOMED,
         home="mine.damage_boosts,theirs.damage_boosts"),

    # ── hidden: no field can hold it. Recorded so nobody 'fixes' it. ──────────────────────────────
    Zone("deck_order", "the ORDER of cards in a deck — what a shuffle and a to-bottom rider change",
         HIDDEN,
         priced_by="Unknowable from an observation FOR A SHUFFLE, and the reason the apply-seam "
                   "refuses anything riding one: the engine has no deal-seed, so a simulated shuffle "
                   "is ONE SAMPLE, not a distribution. Priced as a distribution by `deck_odds` "
                   "hypergeometrics instead (ADR-0029), which is `deck_odds` above. **A to-top "
                   "effect is a different case, recorded so it is not conflated with the shuffle "
                   "one** — Ciphermaniac's Codebreaking (1188) and Academy at Night (1248) both put "
                   "a KNOWN card on top, so the next draw is knowable, not hidden information at "
                   "all. This zone stays HIDDEN here too, today, because nothing tracks it — a "
                   "dedicated `known_top` zone (an ordered tuple, invalidated on any shuffle) was "
                   "sketched but is an open build-or-decline decision (Issue #289), not yet ruled. "
                   "Until it lands, `deck_odds` prices a to-top card exactly as an unseen one, which "
                   "is a KNOWN gap rather than the honest silence it is for an actual shuffle."),
)

#: id -> Zone.
BY_ID = {z.id: z for z in WRITABLE}

#: The Effect Clause vocabulary (`card_effects.json`, ADR-0032) -> the zones each clause WRITES.
#: Keys are the committed `kind`, `rider`, `effect` **and** `cost` values — all four, because all
#: four are vocabulary a card can be written in. The audit test walks the compendium
#: (:func:`clause_vocabulary`) and fails on any of them absent here: that is the "a new clause kind
#: fails rather than silently pricing 0" requirement, executable.
CLAUSE_WRITES: dict[str, frozenset[str]] = {
    # kinds
    "accel": frozenset({"attached_energy", "my_discard_contents", "my_deck_count", "deck_odds"}),
    # The FLIP writes nothing — it is an RNG READ, which is why `coin` is in NONDETERMINISTIC_CLAUSES
    # rather than carrying zones. What the flip GATES is a separate vocabulary: the clause's `effect`
    # value, declared below. Reading this entry as "a coin clause writes nothing" is the Issue #300
    # defect — Crushing Hammer's whole point is the write its `effect` names.
    "coin": frozenset(),
    "draw": frozenset({"my_hand_ids", "my_deck_count", "deck_odds"}),
    "energy_provide": frozenset({"attached_energy", "allowance_energy_attached"}),
    # Issue #204: a `discard_energy_recur` line reloading Basic Energy from its OWN discard pile
    # onto a body in play. No deck zone — unlike `accel`, the source is the visible discard, which
    # is why the clock may read it soundly rather than through the odds machinery.
    "energy_recur": frozenset({"attached_energy", "my_discard_contents"}),
    "fetch": frozenset({"my_hand_ids", "bodies_in_play", "my_deck_count", "deck_odds"}),
    # Issue #303: *"Switch in 1 of your opponent's Benched Pokemon to the Active Spot."* — Boss's
    # Orders and six siblings, the highest-exposure family the POC-A2 census refused. Three writes,
    # not one: the pull rewrites who is Active on THEIR side (`bodies_in_play`), and moving a body
    # out of the Active Spot ENDS what it was carrying — `docs/rulebook.txt` L143, *"whether it
    # retreated or got there some other way … Special Conditions and any effects from attacks"* go
    # away. Declaring only the move would price the condition/grant clear at exactly 0, which is the
    # silent zero this module exists to prevent.
    #
    # `gust` is also the `effect` value of Pokemon Catcher's coin clause (1124), and one key serves
    # both: :func:`undeclared_clauses` looks the string up, not the position it came from.
    "gust": frozenset({"bodies_in_play", "special_conditions", "transient_grants"}),
    "heal": frozenset({"damage_counters"}),
    # Issue #304: the Stadium vocabulary. TWO kinds rather than one, because Groups A–E of that
    # issue's census are five unrelated effect shapes wearing the same card type — a single
    # `stadium` kind would be either a union of everything or a lie.
    #
    # **Both are declared EMPTY, and reading that as "a Stadium writes nothing" is the Issue #300
    # defect again.** What a Stadium writes is what its `effect` names (below), exactly as Crushing
    # Hammer's write is what its `coin`'s `effect` names. What is common to every Stadium — the one
    # in play is DISPLACED and the once-per-turn allowance is spent — is STRUCTURAL, so it belongs
    # to `apply_option`'s `_PLAY` footprint and not to any card's clauses.
    "stadium_static": frozenset(),
    "stadium_trigger": frozenset(),
    # riders
    "bounce_energy_to_hand": frozenset({"attached_energy", "my_hand_ids"}),
    # Issue #303, Lisia's Appeal: *"If you do, the new Active Pokemon is now Confused."* The
    # condition lands on the body the gust just pulled — the OPPONENT's new Active — and
    # `special_conditions` is homed on both sides (`mine.conditions,theirs.conditions`) for exactly
    # that. Only the Active can carry one (`docs/rules.md` §8), which is why the rider is meaningful
    # solely on a clause that just made a body Active.
    "confuse_target": frozenset({"special_conditions"}),
    "discard_basic_f_energy": frozenset({"my_hand_ids", "my_discard_contents"}),
    "discard_eot": frozenset({"attached_energy", "my_discard_contents"}),
    "discard_own_energy": frozenset({"attached_energy", "my_discard_contents"}),
    # Issue #301: the dug cards a `dig` fetch does NOT take go to the DISCARD rather than being
    # shuffled back (Explorer's Guidance). It is the one dig rider that moves cards between two
    # zones instead of merely re-ordering the deck, which is why it needs a write-set of its own and
    # `deck_order` is NOT among them — nothing is shuffled, the remainder simply leaves the deck.
    "discard_remainder": frozenset({"my_discard_contents", "my_deck_count", "deck_odds"}),
    "other_to_bottom": frozenset({"my_deck_count", "deck_odds", "deck_order"}),
    # Issue #303: the gust rider that also moves MY OWN Active — Prime Catcher's *"If you do, switch
    # your Active Pokemon with 1 of your Benched Pokemon"* and Team Rocket's Giovanni's opening leg.
    # Same three writes as `gust`, on my side of the board instead of theirs.
    #
    # **`allowance_retreat_used` is deliberately ABSENT, checked at source before this was written.**
    # An effect-driven switch is NOT a retreat: `docs/rules.md` §3 prints the manual limit as *"1
    # (pay the Retreat cost in Energy; **card effects can switch for free**)"*, and
    # `docs/rulebook.txt` L618 defines retreating as discarding Energy equal to the printed Retreat
    # Cost, once per turn (L142 the same). Both cards say *"switch"*, never *"retreat"*, so neither
    # pays the cost nor spends the once-per-turn allowance — and declaring the allowance would make
    # every effect-switch read as having burned the turn's retreat, blocking a real one that is still
    # available. L143 is the same sentence read the other way: a body reaching the Bench *"some other
    # way"* still drops its Special Conditions, which is why those two zones ARE here.
    "self_switch": frozenset({"bodies_in_play", "special_conditions", "transient_grants"}),
    "shuffle_both_hands": frozenset({"my_hand_ids", "their_hand_size", "my_deck_count",
                                     "their_deck_count", "deck_odds", "deck_order"}),
    # Issue #302: the ONE-SIDED refresh. *"Shuffle your hand into your deck"* — Lillie's
    # Determination (24 copies, our highest-exposure partial) and Lacey. `shuffle_both_hands` minus
    # the two opponent legs, and a separate key rather than a reuse because the difference IS the
    # card: `refresh.py`'s ADR-0060 oracle splits exactly on it (`opp_shuffles`), and a one-sided
    # refresh that declared `their_hand_size` would claim a strip the card never performs.
    "shuffle_own_hand_in": frozenset({"my_hand_ids", "my_deck_count", "deck_odds", "deck_order"}),
    # Issue #302, Lucian: *"Each player shuffles their hand and puts it on the bottom of their
    # deck."* The same six zones as `shuffle_both_hands` — a hand leaving for the deck is the same
    # set of writes wherever in the deck it lands — but a distinct key, because to-BOTTOM and
    # shuffled-IN are different facts about `deck_order` and `other_to_bottom` already keeps that
    # distinction for the dig riders.
    "both_hands_to_bottom": frozenset({"my_hand_ids", "their_hand_size", "my_deck_count",
                                       "their_deck_count", "deck_odds", "deck_order"}),
    "shuffle_self_in": frozenset({"bodies_in_play", "my_deck_count", "deck_odds", "deck_order"}),
    # effects — the leg a `coin` (or a `stadium_static` / `stadium_trigger`) RESOLVES INTO.
    "discard_opp_energy": frozenset({"attached_energy", "their_discard_contents"}),
    # ── Issue #304, the `stadium_static` effects ──────────────────────────────────────────────────
    # `applies_to` names the body the modifier is ABOUT, and WHICH body that is, is fixed by the
    # effect rather than by a separate field: the modified body for `hp_delta`, the DEFENDER for
    # `damage_reduction` / `prevent_damage`, the ATTACKER for `damage_boost`.
    #
    # **Only the HP delta writes the snapshot at all.** Lively Stadium's +30 and Gravity Mountain's
    # −30 move a body's max HP, and `damage_counters` is the zone homed on the HP read
    # (`…active.hp_remaining`), so an HP floor change IS a damage-model write — which is also why it
    # was the widening that zone's home needed. The three damage modifiers are READ by `CombatMath`
    # off the `stadium` zone when it prices an attack and store nothing, so declaring a write for
    # them would claim a snapshot change that never happens — the mirror-image error, and just as
    # able to make a delta lie.
    "hp_delta": frozenset({"damage_counters"}),
    "damage_reduction": frozenset(),
    "damage_boost": frozenset(),
    "prevent_damage": frozenset(),
    # The one `stadium_trigger` effect: Risky Ruins' tax on bench development — *"Whenever any
    # player puts a Basic non-{D} Pokémon onto their Bench during their turn, place 2 damage
    # counters on that Pokémon"* — which fires on exactly the option the Deploy Marginal (ADR-0086)
    # prices, on BOTH sides.
    #
    # This key is an `effect` VALUE that happens to be spelled like the ZONE it writes. The two
    # namespaces are separate and stay separate mechanically (`undeclared_clauses` looks keys up
    # here; `unknown_zones` looks values up in `BY_ID`), but a reader meeting
    # `"damage_counters": {"damage_counters"}` cold deserves to be told which is which.
    "damage_counters": frozenset({"damage_counters"}),
    # ── costs — the FOURTH axis (Issue #350) ──────────────────────────────────────────────────────
    # What playing the card costs, paid out of my own resources. A `cost` is not a flavour note:
    # every value here moves real cards out of my hand, and at T4 an undeclared one prices at exactly
    # 0 — Ultra Ball's two discarded cards would look free.
    #
    # Four identical entries rather than one, because the write-set is about ZONES and
    # `undeclared_clauses` looks up the exact string: folding them would leave three of the four
    # undeclared. The COUNT lives in the value's name today, a compendium shape this issue does not
    # change.
    #
    # Printed text quoted from `tools/meta_tracker/cards.json` (engine `all_card_data()`), never
    # recalled. Which discard they land in is `docs/rulebook.txt` L78: *"Each player has their own
    # discard pile. Cards taken out of play go to the discard pile"* — mine, so no cost writes
    # `their_discard_contents`.
    #
    #   discard_1     1233 Canari, 1187 Morty's Conviction, 1208 Iris's Fighting Spirit
    #                 *"You can use this card only if you discard another card from your hand."*
    #   discard_2     1121 Ultra Ball — *"…if you discard 2 other cards from your hand."*
    #   discard_3     1092 Secret Box (×4 legs) — *"…if you discard 3 other cards from your hand."*
    #   discard_hand  1192 Carmine, 1206 Larry's Skill (×3 legs) — *"Discard your hand…"*
    "discard_1": frozenset({"my_hand_ids", "my_discard_contents"}),
    "discard_2": frozenset({"my_hand_ids", "my_discard_contents"}),
    "discard_3": frozenset({"my_hand_ids", "my_discard_contents"}),
    "discard_hand": frozenset({"my_hand_ids", "my_discard_contents"}),
    # **The sharp one, and the reason a reader must not generalise from the four above.** 1200 Kofu:
    # *"Put 2 cards from your hand on the bottom of your deck in any order."* Nothing is discarded at
    # all. Two cards leave my hand and JOIN my deck, so `my_deck_count` goes UP rather than down,
    # two known cards become unseen (`deck_odds`), and where they land is `deck_order` — the
    # registry's ONE `hidden` zone. `other_to_bottom` already declares the same three for the dig
    # riders; this adds `my_hand_ids` because the material comes from the hand, not the deck. It is
    # the value Issue #302 added LAST, so "a cost discards from hand" was exactly the wrong
    # generalisation to reach for — the whole argument for declaring costs at all.
    #
    # **Deliberately NOT in `NONDETERMINISTIC_CLAUSES`**, and checked rather than inherited from its
    # neighbour: `other_to_bottom` IS nondeterministic because it re-buries cards a `dig` pulled out
    # of an unknown deck, so simulating it is one Monte-Carlo sample. Kofu charges cards I can see
    # and lets me choose their order, so no RNG is consulted and the determinism proof survives. The
    # `draw 4` it gates is NOT a separate clause — Kofu's whole entry is the single clause
    # `{"kind": "draw", "amount": 4, "cost": "bottom_2", "cost_required": true}`, so the draw is this
    # same clause's own `kind`, and `draw` carries the determinism story for that half.
    "bottom_2": frozenset({"my_hand_ids", "my_deck_count", "deck_odds", "deck_order"}),
}

#: Clauses that consult RNG. **Never eligible for the ENGINE-RESOLVED route** — the gate there is
#: *provably deterministic*, and the engine has no deal-seed, so simulating one of these returns a
#: single Monte-Carlo sample rather than a distribution (Issue #178's defect) AND breaks the
#: deterministic replay both gates depend on.
NONDETERMINISTIC_CLAUSES: frozenset[str] = frozenset({
    "coin", "other_to_bottom", "shuffle_both_hands", "shuffle_self_in",
    # Issue #302's two refresh riders. Both shuffle, so both defeat the determinism proof for the
    # same reason `shuffle_both_hands` does — and both are the RIDER on a `draw`, which is already
    # a `REVEALING_CLAUSES` member, so the two lists agree about these cards from either direction.
    "shuffle_own_hand_in", "both_hands_to_bottom",
})

#: Clauses that REVEAL information — they change the option set itself, not only the board. Issue
#: #263 must never fold one of these into a commutative block, whatever its read/write footprint
#: says: reordering around a reveal changes what the later choices are.
REVEALING_CLAUSES: frozenset[str] = frozenset({"draw", "fetch"})

#: The clause keys that are VOCABULARY — a value drawn from a closed set that must have a declared
#: write-set — as opposed to a parameter (`amount`, `dig`, `hp_max`) or a gate (`restriction`,
#: `condition`). :func:`clause_vocabulary` walks exactly these, and `CLAUSE_WRITES` keys exactly
#: these. One list, so "which keys does the audit walk?" has a single answer rather than one per
#: reader — the drift that let `effect` go unaudited from the day it was authored, and `cost` after
#: it. `cost` joined as the fourth at Issue #350; the module docstring carries that ruling.
VOCABULARY_KEYS: tuple[str, ...] = ("kind", "rider", "effect", "cost")

#: Every clause KEY the compendium is allowed to use, each with what it carries. The other half of
#: the §3c audit, and the half that did not exist until Issue #302.
#:
#: :data:`CLAUSE_WRITES` audits the VALUES of :data:`VOCABULARY_KEYS`; nothing audited the keys, so a
#: parameter nobody reads — a typo (``to_hand_sizes``), or a shape authored for a consumer that was
#: never built — rode in the store silently and priced exactly 0. That is the same silent zero this
#: module exists to prevent, arriving through the other axis of the same dict.
#:
#: Issue #302's acceptance asked for its three new shapes to be *"declared in `CLAUSE_WRITES` and
#: pass `undeclared_clauses()`"*. They cannot be, and the reason is the distinction this module
#: already draws two paragraphs up: `to_hand_size` / `amount_if` / `cost_required` are PARAMETERS —
#: their values are ints, dicts and booleans, not strings drawn from a closed set — so
#: `clause_vocabulary` never yields them and `undeclared_clauses` could never see them. Putting a KEY
#: name into a table of VALUE names would also collide the two namespaces `CLAUSE_WRITES`'s own
#: `damage_counters` comment warns about. This registry is that acceptance criterion in the form the
#: registry can actually hold: the keys are declared, and :func:`undeclared_clause_keys` is the audit
#: that bites when a new one is not.
#:
#: Nested keys count: `amount_if` carries a `condition` plus whichever magnitude it replaces, and
#: :func:`clause_keys` walks into it, so a typo inside the block fails exactly as one outside it.
CLAUSE_PARAMETERS: dict[str, str] = {
    # ── identity ──────────────────────────────────────────────────────────────────────────────────
    "kind": "the clause's family — a VOCABULARY key, write-set in CLAUSE_WRITES",
    "rider": "a secondary effect riding the clause — a VOCABULARY key",
    "effect": "the leg a `coin` / `stadium_*` clause resolves into — a VOCABULARY key",
    # ── magnitude ─────────────────────────────────────────────────────────────────────────────────
    "amount": "how many / how much, an int or \"all\"",
    "amount_on_evolution": "`energy_provide`'s second magnitude, on the evolution branch",
    "amount_if": "{condition, amount|to_hand_size} — the magnitude that REPLACES the base one when "
                 "the board predicate holds (Issue #302; `amount_on_evolution`'s shape, generalised "
                 "to a named predicate rather than one hard-coded branch)",
    "to_hand_size": "draw UNTIL the hand holds N — a refill, not a draw-N (Issue #302). Mutually "
                    "exclusive with `amount`: the count depends on the hand at resolution",
    # ── the board-scaled magnitudes (Issue #349) ──────────────────────────────────────────────────
    # `amount` says how many and `to_hand_size` says how many UNTIL; neither says how many PER. Two
    # printed shapes are neither, and they are TWO keys rather than one because a consumer that read
    # either as the other would be wrong by `amount x (N-1)` in the OVER-counting direction — on a
    # heal, exactly the phantom survival the planner refuses to manufacture.
    #
    # The two differ in where the magnitude LANDS, and that is why one names a set and one does not.
    "amount_per": "AGGREGATE: `amount` multiplied ONCE PER body in the named board set, landing in "
                  "the clause's single destination (Issue #349). A STRING, because the counted set "
                  "is not the clause's target and nothing else on the clause names it — 1187 "
                  "Morty's Conviction draws one card per OPPONENT benched body into MY hand. "
                  "Mutually exclusive with `each_of`",
    "each_of": "DISTRIBUTE: the FULL `amount` to EVERY body the clause's `target` names, not to one "
               "of them (Issue #349) — 1222 Fennel's *heal 40 from each of your Pokemon*. A "
               "BOOLEAN, deliberately: `target` already carries the set, and a second body-class "
               "namespace beside `target` and `applies_to` is the drift `unknown_zones` prevents "
               "one axis over. Requires a `target`; mutually exclusive with `amount_per`",
    "window": "how many cards an ability's draw sees, when that differs from what it takes",
    "dig": "how deep a search looks",
    "hp_max": "an HP ceiling on what the clause may target",
    # ── target and source ─────────────────────────────────────────────────────────────────────────
    "target": "the card class or body the clause acts on",
    "target_type": "an energy-type narrowing of `target`",
    "applies_to": "the body class a Stadium modifier is ABOUT",
    "zone": "where a fetch looks (deck / discard)",
    "dest": "where a fetch puts what it finds",
    "source": "the zone a clause draws its material from",
    "source_class": "the card class the modifier's SOURCE must belong to",
    "energy": "the Energy class an accel attaches (basic / special)",
    "energy_type": "an EnergyType lock on the Energy a clause moves",
    "dig_from": "which end of the deck a dig reads",
    "to_hand": "how many of an accel's units go to HAND instead of being attached",
    # ── gates ─────────────────────────────────────────────────────────────────────────────────────
    "condition": "a DYNAMIC board-state gate — the clause whiffs unless it holds",
    "restriction": "a STATIC target-class gate — which cards are eligible at all",
    "trigger": "which OPTION the clause rides (on_evolve / on_bench_play / on_attach / on_attack)",
    "on": "a Stadium trigger's EVENT — deliberately not `trigger`, which routes to a site",
    "timing": "where in the damage pipeline a modifier applies",
    "name_family": "an owner name family gating the clause",
    "no_rule_box": "the target must have no Rule Box",
    "no_ability": "the target must have no Ability",
    "cost": "what playing the card costs, paid from my own resources — a VOCABULARY key since "
            "Issue #350, write-set in CLAUSE_WRITES. Listed beside its gate rather than up with "
            "the other three because `cost` and `cost_required` are one fact in two halves",
    "cost_required": "TRUE when failing to pay `cost` makes the card UNPLAYABLE, which is a "
                     "different fact from the cost merely being expensive (Issue #302). A "
                     "PARAMETER, not vocabulary: its value is a boolean, so it names no write",
    # ── shape ─────────────────────────────────────────────────────────────────────────────────────
    "type": "the card type a clause names, where `target` would be ambiguous",
    "choice": "the clause is one alternative of a choose-one card",
    "distinct_types": "the fetched cards must differ in Energy type",
    "symmetric": "the effect applies to BOTH players, not only the one who played it",
}

# ── the compendium's audited shape ────────────────────────────────────────────────────────────────
# `card_effects.json` is `{cardId: [clauses]}` plus ONE reserved non-numeric key, mirroring the
# `_note` convention `effect_overrides.json` already uses. The parse lives here rather than in each
# reader so a reader cannot quietly disagree about what the file contains.

#: The reserved key carrying the per-card clause-set completeness verdicts.
COVERS_KEY = "_covers"

#: The clause set covers the card's WHOLE printed effect.
COVERS_FULL = "full"
#: The clause set covers only PART of it. The rest differences to 0 — which under 1-ply ordering
#: reads as *never explore this*, not as *undervalued*.
COVERS_PARTIAL = "partial"

COVERS_VERDICTS = frozenset({COVERS_FULL, COVERS_PARTIAL})

#: Card ids whose clause set was PARTIAL when the verdicts were first authored (Issue #300, ported
#: from the Issue #269 census's hand-ruled table). **The audit asserts this set only ever SHRINKS**,
#: for the same reason `footprints_writing_unhomed()` is asserted empty: an owed list that can grow
#: silently is not a schedule. A card leaving it is clause work landing; a card ARRIVING in it is
#: either new exposure that owes a ruling, or a verdict quietly downgraded — both want a human.
#:
#: Entries stay after their card is fixed: this is the record of what was owed when the baseline was
#: ruled, not a live list. 1086 / 1100 / 1110 / 1118 all promoted to `full` at Issue #301 (the
#: missing-`amount` fixes) and are kept here for exactly that reason — `partial_clause_cards()` is
#: where the live answer lives.
#:
#: **Issue #301's five additions are NEW EXPOSURE, ruled, not a downgrade.** Each is a card that had
#: NO clauses at all — so no verdict — and now has an authored set that is honestly incomplete:
#:
#: * 1115 Hop's Bag, 1134 Team Rocket's Transceiver, 1215 Ethan's Adventure, 1220 Team Rocket's
#:   Proton — each restricted to a card-NAME family the closure records but cannot DECIDE (no
#:   build-time family index over the pool). The clause carries the restriction and
#:   `fetch_closure` refuses it for reach, which is the fail-CLOSED direction; ignoring the field to
#:   claim `full` would read Hop's Bag as fetching any Basic. Ruled at Issue #301, cross-posted from
#:   Issue #306.
#: * 1206 Larry's Skill — all three search legs authored; *"Discard your hand"* is the card's whole
#:   cost and no clause field carries it (the same ruling 1192 already carries).
#:
#: None of the five is in a shipped deck; their combined meta weight is ~0.4 copies.
#:
#: **Issue #303's two additions are NEW EXPOSURE, ruled, not a downgrade** — same shape as Issue
#: #301's five: both cards had NO clauses and therefore no verdict, and both now carry an authored
#: `gust` set that is honestly incomplete.
#:
#: * 1124 Pokemon Catcher — a COIN-gated gust. The flip is carried and its `effect` names the gust,
#:   but the clause set states the 50/50 as a certainty, which needs an `Expectation` rather than a
#:   scalar transition. That is 1120 Crushing Hammer's ruling verbatim, and the two must agree: they
#:   are the same `{"kind": "coin", "effect": …}` shape, so ruling this one `full` would put two
#:   opposite verdicts on one shape in the same store.
#: * 1218 Team Rocket's Giovanni — both legs authored (the self-switch, then the pull it gates), but
#:   the *Team Rocket's* NAME family on the self-switch is recorded and UNDECIDED, exactly as it is
#:   for 1115 / 1134 / 1215 / 1220: no build-time family index over the pool exists, so the clause
#:   deliberately decides nothing rather than reading as an unrestricted switch.
#:
#: Neither is in a shipped deck; their combined meta weight is ~0.03 copies.
#:
#: **Issue #349's two additions are NEW EXPOSURE, ruled, not a downgrade** — the same shape as Issue
#: #301's five and Issue #303's two: both cards had NO clauses and therefore no verdict, and both now
#: carry an authored set that is honestly incomplete. Both scale over a printed body TRAIT — *Ancient*
#: and *Future* — and that trait has **no structural field at all** in the engine's own
#: `all_card_data()` dump (`tools/meta_tracker/cards.json` carries `stage` / `ex` / `megaEx` / `tera`
#: / `aceSpec` and nothing else of that family; the words occur only inside printed TEXT). So the
#: magnitude's SHAPE is now carried and the SET it ranges over is recorded and undecided, which is the
#: `name_family` ruling verbatim.
#:
#: * 1085 Awakening Drum — *"Draw a card for each of your Ancient Pokémon in play."* `amount_per:
#:   "my_ancient"`. Not in the census pool at all.
#: * 1089 Reboot Pod — *"Attach a Basic Energy card from your discard pile to each of your Future
#:   Pokémon."* `each_of` over `target: "future"`, which `combat._accel_target_ok` fails CLOSED on as
#:   an unmodelled target class — so the clause funds no body rather than funding every one.
#:
#: Neither is in a shipped deck; their combined meta weight is ~0.001 copies.
PARTIAL_CLAUSE_BASELINE: frozenset[int] = frozenset({
    1080, 1085, 1086, 1089, 1100, 1110, 1115, 1118, 1120, 1124, 1134, 1153, 1181, 1187, 1192, 1199,
    1200, 1203, 1206, 1207, 1208, 1213, 1214, 1215, 1216, 1218, 1220, 1222, 1223, 1227, 1237, 1239,
    1242,
})


def is_card_key(key) -> bool:
    """Is this JSON key a card id rather than one of the file's reserved keys?

    The one predicate, because every store in this family (`card_effects.json`,
    `effect_overrides.json`, `observed_restrictions.json`) mixes numeric card entries with `_note`
    prose and, since Issue #300, :data:`COVERS_KEY`. A reader that rolls its own `int(k)` walk is the
    one that trips on the next reserved key somebody adds."""
    return str(key).lstrip("-").isdigit()


def clause_lists(payload: Mapping) -> dict[int, list[dict]]:
    """``{card id: [clauses]}`` from a raw compendium payload — the card entries only.

    Reserved keys are skipped rather than `int()`-ed, which is what a hand-rolled
    ``{int(k): v for k, v in raw.items()}`` in each reader would do to them."""
    return {int(k): list(v) for k, v in (payload or {}).items() if is_card_key(k)}


def covers_table(payload: Mapping) -> dict[int, dict]:
    """``{card id: {"covers": ..., "reason": ...}}`` from a raw compendium payload.

    Empty when the payload carries no verdicts at all — a compendium built before Issue #300 degrades
    to "unknown everywhere", which :func:`clauses_cover` maps to `None` and the seam fails closed on,
    rather than to a fabricated "full"."""
    block = (payload or {}).get(COVERS_KEY) or {}
    return {int(k): dict(v) for k, v in block.items()
            if is_card_key(k) and isinstance(v, Mapping)}


def clause_values(clause: Mapping) -> list[str]:
    """Every vocabulary value in ONE clause, in :data:`VOCABULARY_KEYS` order. Duplicates kept.

    **The single per-clause extractor**, so no reader keeps its own idea of which keys are vocabulary
    or how a list-valued rider is read. That drift is not hypothetical twice over: it is what let
    ``effect`` go unaudited from the day it was authored (Issue #300) and ``cost`` after it (Issue
    #350), and `tools/apply_seam_coverage.py`'s *Clause write-set health* table kept a hand-rolled
    ``kind``-plus-``rider`` walk that reported on two axes while the audit walked three.

    A list is accepted as well as a string because a `rider` may be either, and a hand-rolled
    ``used[clause["rider"]] += 1`` raises `TypeError` on the list form rather than reading it."""
    out: list[str] = []
    for key in VOCABULARY_KEYS:
        value: Any = clause.get(key)
        if isinstance(value, str) and value:
            out.append(value)
        elif isinstance(value, (list, tuple)):
            out.extend(v for v in value if isinstance(v, str) and v)
    return out


def clause_vocabulary(payload: Mapping) -> list[str]:
    """Every vocabulary value the committed compendium actually uses, sorted.

    :func:`clause_values` over every clause — ``kind``, ``rider``, ``effect`` and ``cost``. Read off
    the artifact rather than from a hand-kept list, because a hand-kept list is precisely what a new
    clause value would not be added to.

    **The values are one flat namespace, deliberately.** A string means the same write wherever it
    appears, which is why `gust` needs one entry for a `kind` and an `effect` alike, and why a cost's
    zones simply union into its clause's."""
    return sorted({v for clauses in clause_lists(payload).values()
                   for clause in clauses for v in clause_values(clause)})


def clause_keys(payload: Mapping) -> list[str]:
    """Every clause KEY the committed compendium actually uses, sorted — nested blocks included.

    The key-side twin of :func:`clause_vocabulary`, and read off the artifact for the same reason: a
    hand-kept list is precisely what a new key would not be added to. It descends into a nested
    mapping (`amount_if`) so a typo one level down is as visible as one at the top."""
    keys: set[str] = set()

    def walk(block: Mapping) -> None:
        for key, value in block.items():
            keys.add(str(key))
            if isinstance(value, Mapping):
                walk(value)

    for clauses in clause_lists(payload).values():
        for clause in clauses:
            walk(clause)
    return sorted(keys)


def undeclared_clause_keys(keys: Sequence[str]) -> list[str]:
    """Clause keys with no entry in :data:`CLAUSE_PARAMETERS`. Empty is the contract.

    The teeth on the key axis, exactly as :func:`undeclared_clauses` is on the value axis: a
    parameter nobody declared is a parameter nobody reads, and it prices its option at 0 as surely as
    an undeclared clause kind does. Takes the keys rather than the compendium so it can be bitten by
    a fabricated one; pair it with :func:`clause_keys` to walk the real artifact."""
    return sorted(k for k in set(keys) if k not in CLAUSE_PARAMETERS)


def clauses_cover(covers: str | None) -> bool | None:
    """A `covers` verdict as the tri-state `apply_option.fate`'s ``clauses_cover`` argument takes:
    ``"full"`` → `True`, ``"partial"`` → `False`, anything else (absent, unknown) → `None`.

    Tri-state rather than boolean, and `None` rather than `False`, for the reason ``deterministic``
    is: *not yet ruled* and *ruled incomplete* are different facts, and the seam is entitled to
    report them differently even though both fail closed."""
    if covers == COVERS_FULL:
        return True
    if covers == COVERS_PARTIAL:
        return False
    return None


def partial_clause_cards(payload: Mapping) -> dict[int, str]:
    """``{card id: reason}`` for every card whose clause set is declared PARTIAL. The owed list.

    The reason is the authored one — the leg the clauses miss, quoted card by card — so this doubles
    as the work item rather than pointing at one."""
    return {cid: str(entry.get("reason", "")).strip()
            for cid, entry in sorted(covers_table(payload).items())
            if entry.get("covers") == COVERS_PARTIAL}


def covers_problems(payload: Mapping) -> list[str]:
    """Every way the `covers` block fails its own discipline. Empty is the contract.

    A list rather than a raise, like :func:`validate`: an author fixing the compendium wants every
    complaint at once. The first check is the one that matters — a clause-bearing card with NO
    verdict is exactly the silent "assume it is complete" this field replaces."""
    problems: list[str] = []
    clauses, covers = clause_lists(payload), covers_table(payload)
    for cid in sorted(clauses):
        if cid not in covers:
            problems.append(f"card {cid}: has Effect Clauses but no {COVERS_KEY} verdict — absent "
                            f"reads as UNKNOWN, and an unknown clause set cannot be told from a "
                            f"complete one")
    for cid, entry in sorted(covers.items()):
        verdict = entry.get("covers")
        if verdict not in COVERS_VERDICTS:
            problems.append(f"card {cid}: covers {verdict!r} is not one of {sorted(COVERS_VERDICTS)}")
        if not str(entry.get("reason", "")).strip():
            problems.append(f"card {cid}: every verdict MUST quote what the clauses do (or do not) "
                            f"carry — an unreasoned verdict cannot be re-checked against the card")
        if cid not in clauses:
            problems.append(f"card {cid}: has a {COVERS_KEY} verdict but no Effect Clauses — there "
                            f"is no clause set for it to be a verdict about")
    return problems


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
    """Clause vocabulary with no declared write-set. **This is the §3c audit's teeth**: a new clause
    value lands here rather than silently writing to nothing and pricing its option at 0.

    Takes the values, not the compendium, so it can be bitten by a fabricated one; pair it with
    :func:`clause_vocabulary` to walk the real artifact. **The pairing is the point**: this function
    would already have bitten `discard_2` before Issue #350, because the table simply lacked the key
    — what was missing was the WALK arriving, since `cost` was not in :data:`VOCABULARY_KEYS`. That
    walk now covers all four — until Issue #300 it covered two and `effect` was the third; `cost` was
    the fourth."""
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
    "NONDETERMINISTIC_CLAUSES", "REVEALING_CLAUSES", "VOCABULARY_KEYS", "CLAUSE_PARAMETERS",
    "COVERS_KEY", "COVERS_FULL", "COVERS_PARTIAL", "COVERS_VERDICTS", "PARTIAL_CLAUSE_BASELINE",
    "is_card_key", "clause_lists", "covers_table", "clause_values", "clause_vocabulary",
    "clause_keys",
    "clauses_cover", "partial_clause_cards",
    "covers_problems", "validate", "homes", "unhomed",
    "undeclared_clauses", "undeclared_clause_keys", "unknown_zones", "clauses_writing_unhomed",
)
