"""**StateModel completeness, as a contract** (POC-T0 / Issue #259 §3c).

The worst failure mode is an effect writing to state the snapshot cannot represent: the delta reads
0, and under 1-ply ordering 0 means *never explored*, not *undervalued*. So completeness is asserted
across four registries — :data:`WRITABLE` (zones), :data:`CLAUSE_WRITES` (the vocabulary of `kind` /
`rider` / `effect` / `cost`), :data:`CLAUSE_PARAMETERS` and :data:`CLAUSE_SELECTORS` (clause keys and
selector values), plus the per-card `covers` verdict, whose PARTIAL refuses rather than pricing
three quarters of a card.

Every walk lives HERE, not in the test: a vocabulary the audit forgets to visit passes by not
looking. :func:`clauses_writing_unhomed` is the strongest — no known clause may write an `owed` zone.
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
    description: str
    status: str
    #: ``homed`` ONLY: dotted path(s) from `StateModel`, comma-separated. Resolved by the audit test.
    home: str = ""
    #: ``owed`` ONLY: the track/issue that owes the read. An owed zone with no owner is a silence.
    owner: str = ""
    #: ``hidden`` ONLY: why no field can represent it, and what prices it instead.
    priced_by: str = ""


#: §3c's enumeration, plus the zones the Effect Clause vocabulary actually writes.
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
    # BOTH sides: energy denial writes the OPPONENT's attachments.
    Zone("attached_energy", "Energy attached to a body, either side", HOMED,
         home="mine.active.energy_count,mine.active.attached_types,"
              "theirs.active.energy_count,theirs.active.attached_types"),
    # BOTH sides and the BENCH: a symmetric Stadium and a `heal` both reach a body that is neither.
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
    # BOTH sides: a body reaching the Bench ANY way drops these (`docs/rulebook.txt` L143).
    Zone("transient_grants", "ADR-0033 transient grants and locks in force this turn, either side",
         HOMED, home="mine.active.grant,theirs.active.grant"),
    Zone("bench_occupancy", "how many bodies each Bench holds, and whether it is full — the loss "
                            "condition's own state (`docs/rules.md` §7 case 2)", HOMED,
         home="mine.bench_count,theirs.bench_count"),
    Zone("allowance_stadium_played", "the one-Stadium-per-turn allowance", HOMED,
         home="stadium_played"),

    # ── ABSENT rather than owed (Issue #282) — no assertion can be about an unenumerated zone.
    Zone("this_turn_damage_boosts",
         "the flat damage boosts live for a side's attacks this turn — a played Premium Power "
         "Pro / Black Belt's Training, and a boost Tool attached to that side's Active. "
         "((amount, attackerEnergyType|None, vsExOnly), ...), the shape `strategy/damage.py` "
         "consumes off the Damage Formula context's `atk_boosts` key", HOMED,
         home="mine.damage_boosts,theirs.damage_boosts"),

    # ── Issue #391. All four legs name the FIELD, not a CONTAINER: a container leg resolves however
    # little the parity lane actually compares, which is the vacuity this module exists to prevent.
    Zone("new_in_play",
         "whether a body ENTERED PLAY this turn, per body — the engine's own `appearThisTurn`. "
         "`docs/rules.md` §4: *\"Cannot evolve a Pokémon the turn it was played/put into play\"*, "
         "which is what makes the 2-ply sequence [play Basic, evolve it] ILLEGAL rather than merely "
         "bad. BOTH SIDES, and the reason is a READ one rather than the WRITE one its neighbours "
         "carry: nothing writes the opponent's half (only my own _PLAY and _EVOLVE set the bit, on "
         "my own bodies), but the engine carries it on their bodies too — measured across the "
         "committed parity corpus — and §4 gates their evolutions on it exactly as it gates mine, "
         "so *what can they field next turn* is the same read as *what can I*", HOMED,
         home="mine.active.new_in_play,mine.bench.new_in_play,"
              "theirs.active.new_in_play,theirs.bench.new_in_play"),

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

BY_ID = {z.id: z for z in WRITABLE}

#: Element zones keyed by the serial of the CARD the option names in hand. Instance-level is a
#: LICENCE (ADR-0098 Amendment D): a footprint naming no instance is UNRESOLVED and conflicts.
CARD_KEYED_ZONES: frozenset[str] = frozenset({"my_hand_ids"})

#: Element zones keyed by the serial of the BODY the option targets. What a turn or a player owns
#: WHOLE stays out: the allowances, bench_occupancy, special_conditions, stadium, transient_grants.
BODY_KEYED_ZONES: frozenset[str] = frozenset({
    "bodies_in_play", "attached_energy", "attached_tools", "damage_counters"})

#: DERIVED: a zone listed twice could be added to one set, forgotten in the other, and silently
#: stop being separable.
ELEMENT_ZONES: frozenset[str] = CARD_KEYED_ZONES | BODY_KEYED_ZONES

#: ⚠️ Both discard zones are deliberately OUT: the seam cannot resolve WHICH card arrives there (a
#: `cost` clause discards at a follow-up select), and keying a zone wrongly would licence a reorder.

#: The Effect Clause vocabulary (`card_effects.json`, ADR-0032) -> the zones each clause WRITES. All
#: four vocabulary keys, so a new clause value FAILS rather than silently pricing its option at 0.
CLAUSE_WRITES: dict[str, frozenset[str]] = {
    # kinds
    "accel": frozenset({"attached_energy", "my_discard_contents", "my_deck_count", "deck_odds"}),
    # The FLIP writes nothing; what it GATES is the clause's `effect` value, declared below.
    "coin": frozenset(),
    "draw": frozenset({"my_hand_ids", "my_deck_count", "deck_odds"}),
    "energy_provide": frozenset({"attached_energy", "allowance_energy_attached"}),
    # No deck zone: unlike `accel` the source is the VISIBLE discard, so the clock reads it soundly.
    "energy_recur": frozenset({"attached_energy", "my_discard_contents"}),
    "fetch": frozenset({"my_hand_ids", "bodies_in_play", "my_deck_count", "deck_odds"}),
    # THREE writes: leaving the Active Spot ENDS conditions and attack effects (rulebook.txt L143).
    "gust": frozenset({"bodies_in_play", "special_conditions", "transient_grants"}),
    "heal": frozenset({"damage_counters"}),
    # Both EMPTY: what a Stadium writes is what its `effect` names, and what EVERY Stadium does —
    # displace the one in play, spend the allowance — is `apply_option`'s `_PLAY` footprint.
    "stadium_static": frozenset(),
    "stadium_trigger": frozenset(),
    # riders
    "bounce_energy_to_hand": frozenset({"attached_energy", "my_hand_ids"}),
    # Lands on the body the gust just pulled — their new Active, the only body that can carry one.
    "confuse_target": frozenset({"special_conditions"}),
    "discard_basic_f_energy": frozenset({"my_hand_ids", "my_discard_contents"}),
    "discard_eot": frozenset({"attached_energy", "my_discard_contents"}),
    "discard_own_energy": frozenset({"attached_energy", "my_discard_contents"}),
    # No `deck_order`: nothing is shuffled, the untaken remainder simply leaves the deck.
    "discard_remainder": frozenset({"my_discard_contents", "my_deck_count", "deck_odds"}),
    "other_to_bottom": frozenset({"my_deck_count", "deck_odds", "deck_order"}),
    # The gust rider that moves MY OWN Active. `allowance_retreat_used` is deliberately ABSENT: an
    # effect SWITCH is not a retreat (`docs/rules.md` §3, `docs/rulebook.txt` L618), so it spends none.
    "self_switch": frozenset({"bodies_in_play", "special_conditions", "transient_grants"}),
    "shuffle_both_hands": frozenset({"my_hand_ids", "their_hand_size", "my_deck_count",
                                     "their_deck_count", "deck_odds", "deck_order"}),
    # The ONE-SIDED refresh; a separate key because `refresh.py`'s oracle splits on it.
    "shuffle_own_hand_in": frozenset({"my_hand_ids", "my_deck_count", "deck_odds", "deck_order"}),
    # A distinct key: to-BOTTOM and shuffled-IN are different facts about `deck_order`.
    "both_hands_to_bottom": frozenset({"my_hand_ids", "their_hand_size", "my_deck_count",
                                       "their_deck_count", "deck_odds", "deck_order"}),
    "shuffle_self_in": frozenset({"bodies_in_play", "my_deck_count", "deck_odds", "deck_order"}),
    # effects — the leg a `coin` (or a `stadium_static` / `stadium_trigger`) RESOLVES INTO.
    "discard_opp_energy": frozenset({"attached_energy", "their_discard_contents"}),
    # Only the HP delta writes anything: the three damage modifiers are READ off the `stadium` zone.
    "hp_delta": frozenset({"damage_counters"}),
    "damage_reduction": frozenset(),
    "damage_boost": frozenset(),
    "prevent_damage": frozenset(),
    # An `effect` VALUE that happens to be spelled like the ZONE it writes — two namespaces, kept
    # separate mechanically: `undeclared_clauses` looks keys up here, `unknown_zones` values in BY_ID.
    "damage_counters": frozenset({"damage_counters"}),
    # ── costs. Four identical entries because `undeclared_clauses` looks up the exact string.
    "discard_1": frozenset({"my_hand_ids", "my_discard_contents"}),
    "discard_2": frozenset({"my_hand_ids", "my_discard_contents"}),
    "discard_3": frozenset({"my_hand_ids", "my_discard_contents"}),
    "discard_hand": frozenset({"my_hand_ids", "my_discard_contents"}),
    # Kofu discards NOTHING: two cards JOIN my deck, so `my_deck_count` goes UP. Deliberately NOT
    # nondeterministic — I see the cards and choose their order, so no RNG is consulted.
    "bottom_2": frozenset({"my_hand_ids", "my_deck_count", "deck_odds", "deck_order"}),
}

#: **How many cards each cost takes.** ``None`` means the seam REFUSES: `discard_hand`'s count is the
#: hand's size (a flagged decline, no shipped carrier) and `bottom_2` moves deck zones a discard doesn't.
COST_CARDS: dict[str, int | None] = {
    "discard_1": 1,
    "discard_2": 2,
    "discard_3": 3,
    "discard_hand": None,
    "bottom_2": None,
}

#: DERIVED from the compendium, not listed: an earlier draft graded a table against its own keys.
def cost_values(payload: Mapping) -> frozenset[str]:
    """Every `cost` value the shipped compendium actually uses."""
    return frozenset(c["cost"] for cs in clause_lists(payload).values() for c in cs
                     if c.get("cost") is not None)

#: Clauses that consult RNG. **Never eligible for the ENGINE-RESOLVED route**: the engine has no
#: deal-seed, so simulating one returns a single sample and breaks the gates' deterministic replay.
NONDETERMINISTIC_CLAUSES: frozenset[str] = frozenset({
    "coin", "other_to_bottom", "shuffle_both_hands", "shuffle_self_in",
    # Both shuffle, so both defeat the determinism proof; both also ride a `draw`.
    "shuffle_own_hand_in", "both_hands_to_bottom",
})

#: Clauses that REVEAL information — they change the option set itself, not only the board. Issue
#: Issue #263 must never fold one into a commutative block: reordering changes what the later choices are.
REVEALING_CLAUSES: frozenset[str] = frozenset({"draw", "fetch"})

#: The clause keys whose VALUES must have a declared write-set. ONE list, so "which keys does the
#: audit walk?" has a single answer.
VOCABULARY_KEYS: tuple[str, ...] = ("kind", "rider", "effect", "cost")

#: Every clause KEY the compendium may use, with what it carries — nested blocks included.
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
    # ── board-scaled magnitudes: TWO keys, not one — reading either as the other is wrong by
    # `amount x (N-1)`, the OVER-counting direction (Issue #349).
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
                     "PARAMETER, not vocabulary: its value is a boolean, so it names no write. "
                     "Authored IF AND ONLY IF the card prints a restriction on PAYING THAT COST — "
                     "*\"You can use this card only if you discard/put…\"*, or Kofu's parenthetical "
                     "inverse naming the same payment — and NOT for the wider \"prints a "
                     "playability restriction\", which ten board-condition cards would satisfy "
                     "(1101 Call Bell's *\"only if you go second\"* takes a `condition`). A "
                     "biconditional Issue #372 ruled and `tests/cards/test_card_effects.py` grades "
                     "against the engine's own card text in both directions",
    # ── shape ─────────────────────────────────────────────────────────────────────────────────────
    "type": "the card type a clause names, where `target` would be ambiguous",
    "choice": "the clause is one alternative of a choose-one card",
    "distinct_types": "the fetched cards must differ in Energy type",
    "symmetric": "the effect applies to BOTH players, not only the one who played it",
}

#: Every SELECTOR value the compendium may use, keyed by the clause key that carries it (Issue
#: Issue #374). Keyed, because a FLAT namespace would be wrong: `"basic"` means three things across keys.
CLAUSE_SELECTORS: dict[str, frozenset[str]] = {
    # `_accel_target_ok` fails CLOSED, so a mistyped `target` means the accel funds NO body at all.
    "target": frozenset({
        "any", "any_pokemon", "basic", "basic_energy", "basic_pokemon", "bench_only", "benched",
        "energy", "evolution", "future", "item", "mega", "opponent_active", "own_line", "own_type",
        "pokemon", "pokemon_ex", "stadium", "stage1", "stage2", "supporter", "tera", "tool",
        "trainer",
    }),
    # `target_type` is deliberately ABSENT: its values are ints, so the walk never yields it, and an
    # empty entry would be inert — an unknown KEY already bites.
    "applies_to": frozenset({"basic", "basic_non_dark", "metal", "name_family", "no_rule_box",
                             "stage2"}),
    "source_class": frozenset({"ex_or_v"}),
    "type": frozenset({"colorless", "psychic"}),
    # ── zones ─────────────────────────────────────────────────────────────────────────────────────
    "zone": frozenset({"deck", "discard"}),
    "dest": frozenset({"bench", "in_play"}),
    "source": frozenset({"deck", "discard", "opponent_attack"}),
    "dig_from": frozenset({"bottom"}),
    "energy": frozenset({"basic"}),
    # ── gates. Every consumer fails CLOSED, so the nine unread values are ledgered below.
    "condition": frozenset({
        "all_own_pokemon_team_rocket", "coin_tails", "energy_3_plus", "exactly_6_prizes_remaining",
        "going_second_first_turn", "hand_size_10_plus_after_draw", "more_prizes_remaining_than_opp",
        "once_per_turn_ability", "opp_3_or_fewer_prizes", "played_supporter_this_turn",
        "pokemon_ko_last_turn", "remaining_hp_30_or_less", "solrock_in_play",
    }),
    "restriction": frozenset({"active_dragon_only", "active_only", "arvens_pokemon", "mega_only",
                              "psychic_only"}),
    "trigger": frozenset({"on_attach", "on_attack", "on_bench_play", "on_evolve"}),
    "on": frozenset({"bench_play"}),
    "timing": frozenset({"after_weakness_resistance", "before_weakness_resistance"}),
    # `"Team Rocket"` is NOT a misspelling of `"Team Rocket's"`: 1134 prints a SUBSTRING test over
    # Supporter NAMES where the other four print an owner PREFIX. Both kept exactly as printed.
    "name_family": frozenset({"Ethan's", "Hop's", "Team Rocket", "Team Rocket's"}),
    # Declaring the one sentinel is what lets a mistyped `"al"` bite instead of reading as 0.
    "amount": frozenset({"all"}),
    "amount_per": frozenset({"my_ancient", "their_bench"}),
}

#: ``"key=value" -> why nothing reads it yet``. Declared LEGAL and LEDGERED rather than failed or
#: waved through; NOT asserted exhaustive — measured by sweeping CODE string literals only.
UNCONSUMED_SELECTORS: dict[str, str] = {
    # Both heal readers decline `amount_per` by name, in the under-counting direction.
    "amount_per=my_ancient": "1085 Awakening Drum. Issue #349 ruled the ANCIENT trait unmodellable — "
                             "the dump carries stage/ex/megaEx/tera/aceSpec and nothing of that "
                             "family — so the shape is carried and the set stays undecided",
    "amount_per=their_bench": "1187 Morty's Conviction. The set IS decidable (theirs.bench is homed) "
                              "but no consumer multiplies by it yet; both heal readers decline it in "
                              "the under-counting direction",
    # ⚠️ `applies_to=basic_non_dark` / `stage2` / `basic` LEFT this ledger (Issues #410, Issue #433):
    # `board_delta._APPLIES_TO` resolves all three. `metal` stays — its write-set is EMPTY.
    "applies_to=metal": "1244 Full Metal Lab. A {M}-body scope on a damage modifier read off the "
                        "stadium zone, which branches on the effect rather than this narrowing",
    # Each of these nine already reaches "the clause whiffs" — the safe direction.
    "condition=all_own_pokemon_team_rocket": "1216 Team Rocket's Ariana. Board-wide family "
                                             "membership; the `team_rocket` Function Tag is the "
                                             "index that would answer it",
    "condition=coin_tails": "1223 Harlequin, 1237 Lucian. An RNG branch, so a scalar transition "
                            "cannot state it — the `coin` Expectation ruling, one key over",
    "condition=exactly_6_prizes_remaining": "1227 Lillie's Determination. Prize state is homed; no "
                                            "reader gates a clause on it yet",
    "condition=going_second_first_turn": "1101 Call Bell. Turn-parity state the Board carries but no "
                                         "clause reader consults",
    "condition=hand_size_10_plus_after_draw": "1181 Billy & O'Nare. Post-resolution hand size — a "
                                              "predicate about the clause's own outcome, not the "
                                              "board before it",
    "condition=opp_3_or_fewer_prizes": "1199 Lacey, 1214 Emcee's Hype. Prize state is homed; no "
                                       "clause reader gates on it yet",
    "condition=played_supporter_this_turn": "1242 Community Center. The allowance IS homed "
                                            "(`supporter_played`); the alternating per-player "
                                            "availability is what stays unmodelled",
    "condition=solrock_in_play": "675 Lunatone. A named-partner board check; "
                                 "`parse_attack_bench_requirement` answers the attack-side twin, not "
                                 "this clause gate",
    "dig_from=bottom": "1102 Dusk Ball. Which END of the deck a dig reads — `deck_order` is the "
                       "registry's one HIDDEN zone, so the distinction has nowhere to land",
    # `fetch_closure` refuses for reach, reading the key's PRESENCE and never the value.
    "name_family=Ethan's": "1215 Ethan's Adventure. Recorded and undecided (Issue #301); "
                           "`fetch_closure` refuses on the key's presence",
    "name_family=Hop's": "1115 Hop's Bag, 1255 Postwick. Same ruling. `name_in_family` implements "
                         "the string test but is wired only to the TOOL-side holderNameFamily",
    "name_family=Team Rocket": "1134 Team Rocket's Transceiver, and the ONE substring-over-Supporter"
                               "-names test in the store — not a misspelling of the possessive. "
                               "Kept as printed; see CLAUSE_SELECTORS",
    "name_family=Team Rocket's": "1218 Giovanni, 1220 Proton. The Pokemon-membership half is now the "
                                 "`team_rocket` Function Tag, so the string value stays recorded and "
                                 "unread",
    "on=bench_play": "1260 Risky Ruins. The one `stadium_trigger` EVENT; the trigger fires on the "
                     "option `apply_option` already prices, so nothing dispatches on the string",
    "restriction=active_dragon_only": "1105 Dragon Elixir. `_heal_restriction_targets` (and its "
                                      "Active-spot wrapper `_heal_restriction_ok`) fails closed on "
                                      "it, so the heal never counts toward survival and never ranks "
                                      "a HEAL target — under-count, at both consumers",
    "restriction=arvens_pokemon": "1130 Arven's Sandwich. An owner family wearing the `restriction` "
                                  "key rather than `name_family`; same Issue #301 refusal. The card "
                                  "carries a SECOND heal clause gated only on `active_only`, so the "
                                  "refusal costs its 30 branch nothing",
    "source=opponent_attack": "1244 Full Metal Lab, 1247 Neutralization Zone. Names the OPPONENT's "
                              "attack as the material a modifier acts on; the damage readers branch "
                              "on the effect instead",
    "source_class=ex_or_v": "1247 Neutralization Zone. The modifier's source must be an ex/V body — "
                            "a second class namespace beside `target`, authored with the clause",
    "target=future": "1089 Reboot Pod. Issue #349 ruled the FUTURE trait unmodellable for the same "
                     "reason as ANCIENT; `_accel_target_ok` fails CLOSED, so the clause funds no "
                     "body rather than funding every one",
    "target=opponent_active": "1255 Postwick. The body a Stadium's damage modifier is aimed at, read "
                              "off the stadium zone by effect rather than by this value",
    "target=own_type": "190 Archaludon ex. A same-type-as-holder narrowing; no consumer resolves a "
                       "relative body class yet",
    "timing=after_weakness_resistance": "1244 Full Metal Lab. WHERE in the damage pipeline a modifier "
                                        "lands. `CombatMath` hard-codes its pipeline order, so the "
                                        "declared timing is not what sequences it",
    "timing=before_weakness_resistance": "1255 Postwick. Same — the pipeline position is structural "
                                         "in `damage.py`, not dispatched off this string",
    "trigger=on_attach": "19 Telepath Psychic Energy. Which OPTION the clause rides; the routing is "
                         "by clause `kind` at the site, so the declared trigger is not consulted",
    "trigger=on_attack": "678 Mega Lucario ex. Same routing story",
    "trigger=on_bench_play": "1071 Meowth ex. Same routing story",
    "type=colorless": "17 Ignition Energy. The card type a clause names where `target` would be "
                      "ambiguous; the energy readers use `energy_type` instead",
    "type=psychic": "19 Telepath Psychic Energy. Same",
}

# ── the compendium's audited shape: `card_effects.json` is `{cardId: [clauses]}` plus reserved
# non-numeric keys. The parse lives here so no reader can disagree about what the file contains.

#: The reserved key carrying the per-card clause-set completeness verdicts.
COVERS_KEY = "_covers"

#: The clause set covers the card's WHOLE printed effect.
COVERS_FULL = "full"
#: The clause set covers only PART of it. The rest differences to 0 — which under 1-ply ordering
#: reads as *never explore this*, not as *undervalued*.
COVERS_PARTIAL = "partial"

COVERS_VERDICTS = frozenset({COVERS_FULL, COVERS_PARTIAL})

#: Card ids whose clause set was PARTIAL when the verdicts were first authored. **The audit asserts
#: this set only ever SHRINKS**; entries stay after a fix — `partial_clause_cards()` is the live answer.
PARTIAL_CLAUSE_BASELINE: frozenset[int] = frozenset({
    1080, 1085, 1086, 1089, 1100, 1110, 1115, 1118, 1120, 1124, 1134, 1153, 1181, 1187, 1192, 1199,
    1200, 1203, 1206, 1207, 1208, 1213, 1214, 1215, 1216, 1218, 1220, 1222, 1223, 1227, 1237, 1239,
    1242,
})


def is_card_key(key) -> bool:
    """The ONE predicate: every store in this family mixes numeric card entries with reserved keys."""
    return str(key).lstrip("-").isdigit()


def clause_lists(payload: Mapping) -> dict[int, list[dict]]:
    """Reserved keys are SKIPPED rather than `int()`-ed, unlike a hand-rolled comprehension."""
    return {int(k): list(v) for k, v in (payload or {}).items() if is_card_key(k)}


def covers_table(payload: Mapping) -> dict[int, dict]:
    """Empty when the payload carries no verdicts, which :func:`clauses_cover` maps to `None` —
    never to a fabricated "full"."""
    block = (payload or {}).get(COVERS_KEY) or {}
    return {int(k): dict(v) for k, v in block.items()
            if is_card_key(k) and isinstance(v, Mapping)}


def clause_values(clause: Mapping) -> list[str]:
    """The single per-clause extractor; a list-valued `rider` is accepted as well as a string."""
    out: list[str] = []
    for key in VOCABULARY_KEYS:
        value: Any = clause.get(key)
        if isinstance(value, str) and value:
            out.append(value)
        elif isinstance(value, (list, tuple)):
            out.extend(v for v in value if isinstance(v, str) and v)
    return out


def clause_vocabulary(payload: Mapping) -> list[str]:
    """ONE flat namespace, deliberately: a string means the same write wherever it appears, so
    `gust` needs a single entry for both the `kind` and the `effect` position."""
    return sorted({v for clauses in clause_lists(payload).values()
                   for clause in clauses for v in clause_values(clause)})


def clause_keys(payload: Mapping) -> list[str]:
    """Descends into a nested mapping, so a typo one level down is as visible as one at the top."""
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


def clause_selectors(payload: Mapping) -> list[tuple[str, str]]:
    """A PAIR, because selector values share no namespace; :data:`VOCABULARY_KEYS` are skipped."""
    out: set[tuple[str, str]] = set()

    def walk(block: Mapping) -> None:
        for key, value in block.items():
            if isinstance(value, Mapping):
                walk(value)
                continue
            if key in VOCABULARY_KEYS:
                continue
            if isinstance(value, str) and value:
                out.add((str(key), value))
            elif isinstance(value, (list, tuple)):
                out.update((str(key), v) for v in value if isinstance(v, str) and v)

    for clauses in clause_lists(payload).values():
        for clause in clauses:
            walk(clause)
    return sorted(out)


def undeclared_selector_values(pairs: Sequence[tuple[str, str]]) -> list[str]:
    """Selector pairs with no :data:`CLAUSE_SELECTORS` entry, as ``"key=value"``. Empty is the
    contract. Bites BOTH an undeclared value and a string-valued key the registry never heard of."""
    return sorted(f"{k}={v}" for k, v in set(pairs)
                  if k not in CLAUSE_SELECTORS or v not in CLAUSE_SELECTORS[k])


def undeclared_clause_keys(keys: Sequence[str]) -> list[str]:
    """Empty is the contract. Takes the keys, not the compendium, so a fabricated one can bite it."""
    return sorted(k for k in set(keys) if k not in CLAUSE_PARAMETERS)


def clauses_cover(covers: str | None) -> bool | None:
    """``"full"`` → True, ``"partial"`` → False, anything else → None. Tri-state because *not yet
    ruled* and *ruled incomplete* are different facts, even though both fail closed."""
    if covers == COVERS_FULL:
        return True
    if covers == COVERS_PARTIAL:
        return False
    return None


def partial_clause_cards(payload: Mapping) -> dict[int, str]:
    """The owed list. The reason is the authored one, so this IS the work item."""
    return {cid: str(entry.get("reason", "")).strip()
            for cid, entry in sorted(covers_table(payload).items())
            if entry.get("covers") == COVERS_PARTIAL}


def covers_problems(payload: Mapping) -> list[str]:
    """Empty is the contract. A list rather than a raise: an author wants every complaint at once."""
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


def cost_card_problems(payload: Mapping) -> list[str]:
    """Every way the compendium, :data:`COST_CARDS` and :data:`CLAUSE_WRITES` disagree about the cost
    vocabulary. A stale `COST_CARDS` entry for a value no card carries is a declared refusal, not a bug."""
    problems: list[str] = []
    used = cost_values(payload)
    for value in sorted(used - set(COST_CARDS)):
        problems.append(f"cost {value!r}: carried by a shipped card but absent from COST_CARDS — "
                        f"the apply seam has no count to charge for it")
    for value in sorted(used - set(CLAUSE_WRITES)):
        problems.append(f"cost {value!r}: carried by a shipped card but has no CLAUSE_WRITES entry "
                        f"— a cost whose ZONES are undeclared prices at exactly 0")
    for value, count in sorted(COST_CARDS.items()):
        if count is not None and (not isinstance(count, int) or count < 1):
            problems.append(f"cost {value!r}: count {count!r} is neither None nor a positive int")
    return problems


def choice_relation_problems(payload: Mapping) -> list[str]:
    """Every way a card's multi-leg REVEAL relation is declared incoherently — ``choice`` on only
    SOME revealing legs (neither reading available), or on a card with only one. Empty is the contract."""
    problems: list[str] = []
    for cid, clauses in sorted(clause_lists(payload).items()):
        reveal = [c for c in clauses if c.get("kind") in REVEALING_CLAUSES]
        if not reveal:
            continue
        flagged = [bool(c.get("choice")) for c in reveal]
        if len(reveal) == 1:
            if flagged[0]:
                problems.append(f"card {cid}: `choice` on a card with ONE revealing clause — an "
                                f"alternative to nothing; every search already lets the player pick")
            continue
        if any(flagged) and not all(flagged):
            problems.append(f"card {cid}: `choice` is declared on {sum(flagged)} of {len(reveal)} "
                            f"revealing legs — neither a union nor a conjunction can be read from a "
                            f"half-declared relation")
    return problems


def validate(zones: Sequence[Zone] = WRITABLE) -> list[str]:
    """Empty is the contract; a list rather than a raise, so an author gets every complaint at once."""
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
    """The audit test resolves these against the real classes, so a rename fails there, not here."""
    return {z.id: [p.strip() for p in z.home.split(",") if p.strip()]
            for z in WRITABLE if z.status == HOMED}


def unhomed() -> dict:
    """``{zone id: owner}``, generated rather than re-derived — the set `clauses_writing_unhomed`
    is checked against."""
    return {z.id: z.owner for z in WRITABLE if z.status == OWED}


def undeclared_clauses(kinds: Sequence[str]) -> list[str]:
    """Clause vocabulary with no declared write-set — **the §3c audit's teeth**. Takes the values,
    not the compendium, so a fabricated one can bite; pair it with :func:`clause_vocabulary`."""
    return sorted(k for k in set(kinds) if k not in CLAUSE_WRITES)


def unknown_zones() -> dict:
    """Keeps `CLAUSE_WRITES` and :data:`WRITABLE` one vocabulary rather than two that drift."""
    return {clause: sorted(z for z in zs if z not in BY_ID)
            for clause, zs in CLAUSE_WRITES.items()
            if any(z not in BY_ID for z in zs)}


def clauses_writing_unhomed() -> dict:
    """``{clause: [owed zone ids]}`` — the strong one. Empty is the contract: a known clause writing
    to an unhomed zone is a LIVE correctness hole, and the zone must be homed before it is modelled."""
    owed = set(unhomed())
    return {clause: sorted(zs & owed) for clause, zs in CLAUSE_WRITES.items() if zs & owed}


__all__: Sequence[str] = (
    "HOMED", "OWED", "HIDDEN", "STATUSES", "Zone", "WRITABLE", "BY_ID", "CLAUSE_WRITES",
    "COST_CARDS", "cost_values",
    "NONDETERMINISTIC_CLAUSES", "REVEALING_CLAUSES", "VOCABULARY_KEYS", "CLAUSE_PARAMETERS",
    "CLAUSE_SELECTORS", "UNCONSUMED_SELECTORS",
    "COVERS_KEY", "COVERS_FULL", "COVERS_PARTIAL", "COVERS_VERDICTS", "PARTIAL_CLAUSE_BASELINE",
    "is_card_key", "clause_lists", "covers_table", "clause_values", "clause_vocabulary",
    "clause_keys", "clause_selectors",
    "clauses_cover", "partial_clause_cards",
    "cost_card_problems", "choice_relation_problems",
    "covers_problems", "validate", "homes", "unhomed",
    "undeclared_clauses", "undeclared_clause_keys", "undeclared_selector_values", "unknown_zones",
    "clauses_writing_unhomed",
)
