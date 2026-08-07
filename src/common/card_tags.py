"""**The Function Tag vocabulary, as a contract** (Issue #395 D6).

`card_functions.json` is a committed artifact: it is built offline against the native engine over
several stochastic games per card, then shipped. That makes it exactly the kind of store the effects
layer already learned to guard — and until this module it had none of that guarding. Two holes, both
measured rather than argued:

* **Nothing declared the vocabulary.** `function_audit._CUES` is a 17-tag whitelist that *exempts*
  what it has never heard of — the exact inversion of `snapshot_coverage.undeclared_clauses`, which
  *rejects* it. 25 of the 42 shipped tags were audited by nothing at all, so a typo'd tag was a tag
  that shipped, read by no consumer and reported by no test.
* **Nothing checked that a shipped tag could be REBUILT.** Eleven tag instances lived in the shipped
  table and in neither the prober's derived set nor `function_overrides.json`, so
  ``python tools/build_card_functions.py --fresh`` deleted all eleven silently: `--fresh` sets
  ``prior = {}`` and the monotonic accumulate union was the only thing preserving them. One of the
  eleven was `prevent_ex_damage` on 345 Crustle — the input to the damage oracle's ex-immunity read,
  `_body_threat_rank`'s `+500` and snipe relevance's `prevents_my_ex` leg, all three lost in one
  documented command with nothing red. `test_card_functions_oracle.py` could not see it: it asserts
  **overrides ⊆ table** and only that direction.

So this module is the enumeration, as data, in the shape `snapshot_coverage` already proved out:
**declare** a closed registry → **walk the shipped store, never a hand-kept list** → expose the
teeth as a function → assert it in pytest with a vacuity guard and a positive control on the same
run.

* :data:`TAG_REGISTRY` — every legal tag with its :data:`SOURCES` origin, a prose reason, and the
  modules that consume it. A tag whose ``consumers`` is empty is declared inert **on purpose** and
  says why — the honest half, mirroring `snapshot_coverage.UNCONSUMED_SELECTORS`. Both failure
  shapes are then visible: a tag nothing reads, and (via :func:`undeclared_tags`) a tag nothing
  declared.
* :data:`PARAMETRIC_PREFIXES` — the ``name:N`` families (`dig:2`, `provides:1`, `provides_evo:3`),
  which are one vocabulary entry each rather than one per observed N.
* :func:`tag_vocabulary` / :func:`undeclared_tags` — the walk and its teeth.
* :func:`unsourced_tag_instances` — the rebuild-reachability check, i.e. *is `--fresh` lossless?*

**Lib-free and dependency-free on purpose**, like `matchup_plan` and `briefs`: `tools/` imports it to
lint the store it builds, and `src/common/` imports it at runtime. It does NOT import the classifier,
and the classifier's :data:`~meta_tracker.card_functions.DERIVED_TAGS` is **passed in** rather than
re-transcribed here (:func:`unsourced_tag_instances` takes it as an argument) — a second
transcription of that set is precisely the drift this module exists to stop, and the direction of the
dependency is what keeps `src/` free of `tools/`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

#: A tag's origin — *which store can produce it*, which is the same question as *what happens to it
#: on a `--fresh` rebuild*.
DERIVED = "derived"        # `classify_functions` can emit it from a probe record. A curated override
                           # may ALSO supply it for a card the probe cannot reach (Enhanced Hammer's
                           # `energy_denial`); that is a reach patch, not a second vocabulary.
CURATED = "curated"        # ONLY `function_overrides.json` produces it. No probe shape yields it.
PARAMETRIC = "parametric"  # a `name:N` family — see :data:`PARAMETRIC_PREFIXES`. Curated in practice
                           # (the probe emits the plain `dig`, never a depth).
SOURCES = (DERIVED, CURATED, PARAMETRIC)


@dataclass(frozen=True)
class Tag:
    """One legal Function Tag.

    ``consumers`` are dotted MODULE paths, resolved and checked by
    `tests/cards/test_card_functions_oracle.py` against the real tree — so the claim breaks when a
    reader moves, rather than quietly becoming aspirational. An empty tuple is a positive statement
    (*nothing reads this yet, and here is why*), not an omission, and the same test asserts nothing
    reads it — which is the direction that catches an "inert" label going stale."""

    source: str
    reason: str
    consumers: tuple[str, ...] = ()


#: ``prefix -> what the N means``. A parametric tag is ``f"{prefix}{N}"`` with an integer N; the
#: registry declares the FAMILY, so a new depth needs no vocabulary change. `cards.CardFunctions`
#: reads them through `_parametric_tag`, which is why the prefix (colon included) is the unit here.
PARAMETRIC_PREFIXES: dict[str, str] = {
    "dig:": "how many cards this card's draw/dig Ability puts within REACH in one use — "
            "`CardFunctions.dig_depth`, read by the evolve decider's readiness odds and by "
            "`draw_hit_probability`. Per-card DATA that ages with the pool, not a constant.",
    "provides:": "how many Energy UNITS this card provides once attached — `CardFunctions."
                 "energy_provision`. The colour is NOT here: `CardStat.energyType` carries it.",
    "provides_evo:": "the same provision for a card whose units change on an Evolution Pokémon "
                     "(Issue #142) — the `evolution=True` leg of `energy_provision`.",
}


#: The closed vocabulary. Prose is sourced from `docs/card-functions.md`'s tag reference where it has
#: a row, and from the consumer itself where it does not — ten of these tags were undocumented there,
#: which is its own small piece of the same hole.
TAG_REGISTRY: dict[str, Tag] = {
    # --- resource ---------------------------------------------------------------------------
    "draw": Tag(DERIVED,
                "Draws cards into hand — raw card advantage / engine fuel. A `DRAW` log by the "
                "actor, or a look-at-top-then-take (`LOOKING→HAND`).",
                ("common.deciders.context_build", "common.deciders.hand", "common.deciders.order", "common.strategy.context",
                 "common.strategy.doctrines.doctrine_fetch")),
    "search": Tag(DERIVED,
                  "Tutors a SPECIFIC card straight out of the deck (`DECK→HAND`/`BENCH`/`ACTIVE`) — "
                  "consistency. A top-N look is `dig`+`draw`, not this.",
                  ("common.deciders.hand", "common.deciders.order", "common.strategy.context",
                   "common.strategy.doctrines.doctrine_fetch")),
    "dig": Tag(DERIVED,
               "Looks at / reorders the top or bottom of the deck — selection and information. A "
               "`MOVE_CARD` touching the `LOOKING` area.",
               # `baseline_sequencing` was deleted by POC-T4/5 (Issue #386) along with the whole
               # SEQUENCING cluster. The tag did not lose its consumer with it: `pilot`'s
               # `_finish_turn_last` is what reads `dig` now, through `_informative_card`, and that
               # is the ADR-0095 boundary rather than a rung. Named as `common.pilot`, already
               # listed first.
               ("common.deciders.hand", "common.deciders.order", "common.strategy.context")),
    "energy_accel": Tag(DERIVED,
                        "Attaches Energy beyond the manual once-per-turn drop — ramp / tempo. An "
                        "`ATTACH` log by the actor from a non-Tool card.",
                        ("common.strategy.combat", "common.strategy.context",
                         "common.strategy.baseline.baseline_energy")),
    "recycle": Tag(DERIVED,
                   "Returns cards from the discard pile to hand/deck/play — resource recursion.",
                   ("common.card_worth", "common.needs",
                    "common.strategy.doctrines.doctrine_fetch")),
    "tutor_energy": Tag(CURATED,
                        "A deck-search specifically for an ENERGY card into hand — the attachable "
                        "fuel the Turn Planner's Supporter-enabled KO line needs (ADR-0031). "
                        "Refines the probe's plain `search`, which sees only the generic "
                        "`DECK→HAND` move. Discard-pile retrieval stays `recycle`, a top-N look "
                        "stays `dig`.",
                        ("common.strategy.planner", "common.strategy.combat")),
    "tutor_pokemon": Tag(CURATED,
                         "A fetch whose reachable class is Pokémon — the Planner's fetch-class read "
                         "and the fetch doctrine's cost/benefit split on an Ultra Ball-shaped play. "
                         "NOT read by `fetch_closure`, whose ADR-0032 clause predicate REPLACED the "
                         "tag-keyed `_FETCH_FILTERS` (it names the tag only in prose).",
                         ("common.deciders.deploy", "common.strategy.planner",
                          "common.strategy.doctrines.doctrine_fetch")),
    "tutor_mega": Tag(CURATED,
                      "A fetch restricted to a Rule-Box Mega ex — the fact the generic "
                      "`tutor_pokemon` cannot carry, so a wincon-in-hand read would over-claim. "
                      "Same non-consumer note as `tutor_pokemon`: `fetch_closure` mentions it, and "
                      "reads the clause instead.",
                      ("common.deciders.deploy", "common.deciders.hand", "common.deciders.needs", "common.strategy.planner")),
    "tutor_trainer": Tag(CURATED,
                         "A Supporter that searches ANY Trainer card out of the deck (Team "
                         "Rocket's Petrel class) — the Planner's route to a wincon-line Trainer.",
                         ("common.strategy.planner",)),
    "supporter_tutor": Tag(CURATED,
                           "A body whose ON-PLAY Ability fetches a SUPPORTER (Meowth ex's "
                           "Last-Ditch Catch) — a bench-drop that buys a Supporter, which is a "
                           "utility body rather than a wall. Replaced `stall` on 1071 in 2026-07.",
                           ("common.deciders.attach", "common.deciders.deploy", "common.needs", "common.strategy.context")),
    "bench_fill": Tag(CURATED,
                      "Fetches Basics straight onto the Bench (Buddy-Buddy Poffin) — bench "
                      "development and deck-thinning in one play; sequenced ahead of hand-refill "
                      "tutors in a thin deck.",
                      ("common.deciders.deploy", "common.strategy.doctrines.doctrine_fetch")),
    "cost_discard": Tag(CURATED,
                        "A fetch that COSTS a discard from hand (Ultra Ball class) — a blind, "
                        "costly commitment the sequencer defers behind free development, and whose "
                        "shed side `doctrine_fetch` prices.",
                        # Same deletion as `dig` above: the deferral is `_finish_turn_last`'s
                        # `_TIER_COMMITMENT`, in `common.pilot`.
                        ("common.deciders.order", "common.strategy.doctrines.doctrine_fetch")),
    "rare_candy": Tag(CURATED,
                      "Puts a Stage 2 from hand straight onto its root Basic, SKIPPING the Stage 1 "
                      "— so a missing Stage 1 does not prove a Stage 2 dead. Distinct from "
                      "`rush_evolve`: this fetches nothing. The literal has ONE home, "
                      "`playability.RARE_CANDY_TAG`; the Pilot's Rare Candy KO line reads it "
                      "through that constant rather than restating it.",
                      ("common.playability",)),
    "rush_evolve": Tag(CURATED,
                       "Evolves a Pokémon ahead of the normal schedule — even the turn its "
                       "pre-evolution was played. Brings the win condition online a turn early.",
                       ("common.deciders.deploy", "common.deciders.hand", "common.deciders.needs", "common.strategy.planner",
                        "common.strategy.baseline.baseline_evolution")),
    # --- disruption -------------------------------------------------------------------------
    "gust": Tag(DERIVED,
                "Drags the opponent's Active out to pull a target up (Boss's Orders) — a `SWITCH` "
                "log on the OPPONENT's side.",
                ("common.deciders.board_build", "common.deciders.needs", "common.deciders.order", "common.strategy.planner",
                 "common.strategy.doctrines.doctrine_gust")),
    "hand_disruption": Tag(DERIVED,
                           "Shuffles or discards the opponent's hand — resource denial. Their "
                           "cards move `HAND→DECK`/`DISCARD` during this card's resolution.",
                           # `baseline_disruption` was deleted by POC-T4/5 (Issue #386). The tag
                           # keeps its live consumer: `pilot` reads it at the shuffle-refresh
                           # tier and through the Opponent Model.
                           ("common.deciders.board_build", "common.deciders.deploy", "common.deciders.hand", "common.deciders.needs",)),
    "energy_denial": Tag(DERIVED,
                         "Removes the opponent's ATTACHED Energy — tempo denial (their "
                         "`ENERGY→DISCARD`).",
                         ("common.deciders.deny", "common.needs")),
    "shuffle_hand": Tag(CURATED,
                        "A refresh that shuffles BOTH hands away and redraws (Iono, Unfair Stamp) "
                        "— a Gamble Line: it can refill a small opponent hand, so ADR-0060 forbids "
                        "reading it as a strip.",
                        # minus `baseline_disruption`, deleted by POC-T4/5 (Issue #386); the
                        # shuffle DOCTRINE is where the Gamble-Line reading actually lives.
                        ("common.deciders.context_build", "common.deciders.order", "common.strategy.planner",
                         "common.strategy.doctrines.doctrine_shuffle_refresh")),
    "item_lock": Tag(CURATED,
                     "A body whose Ability locks Item play (the benched-disruptor maneuver) — read "
                     "on BOTH sides: it gates our own Item lines and prices their disruptor.",
                     ("common.deciders.board_build", "common.deciders.promote", "common.strategy.doctrines.doctrine_fetch")),
    # --- board ------------------------------------------------------------------------------
    "switch": Tag(DERIVED,
                  "Moves my OWN Active out — reposition / escape. Also read on THEIR side, where a "
                  "switch card anywhere waives the Threat-Clock bench-promotion surcharge.",
                  ("common.deciders.evolve", "common.deciders.needs", "common.deciders.promote", "common.strategy.objectives", "common.strategy.planner")),
    "heal": Tag(DERIVED,
                "Removes damage from my Pokémon — longevity. An `HP_CHANGE` (value > 0, not a "
                "damage counter) on my side.",
                ("common.strategy.planner", "common.strategy.baseline.baseline_phases")),
    "clutch_heal": Tag(CURATED,
                       "A heal that also BOUNCES the healed Pokémon's Energy to hand (Wally's "
                       "Compassion) — a defensive save, not a value heal: held until the Active is "
                       "doomed, then played and re-powered the same turn.",
                       # minus `baseline_heal`, deleted by POC-T4/5 (Issue #386): a clutch heal is
                       # now priced by the survival delta it buys, which `needs` and the planner
                       # already read.
                       ("common.deciders.heal", "common.deciders.needs", "common.card_worth", "common.needs",
                        "common.strategy.planner")),
    "spread": Tag(DERIVED,
                  "Places damage counters across the opponent's board 'in any way' (a "
                  "`DAMAGE_COUNTER_ANY` select context) — snipe / multi-KO setup. **Inert as a "
                  "TAG**: the spread that decides anything is priced off the ATTACK "
                  "(`AttackStat.benchSpread` → `combat.rider_spread`), which is per-attack rather "
                  "than per-card, so no consumer asks the card-level question."),
    "prevent_ex_damage": Tag(CURATED,
                             "This body takes NO damage from attacks by the opponent's Pokémon ex "
                             "(Crustle's Mysterious Rock Inn) — the card fact that makes it their "
                             "main attacker in an ex-dominated format. Read three ways: the damage "
                             "oracle zeroes my ex's damage into it, `_body_threat_rank` boosts a "
                             "line carrying it, and snipe relevance's `prevents_my_ex` leg.",
                             ("common.deciders.snipe", "common.strategy.damage")),
    "bench_guard": Tag(CURATED,
                       "Protects benched Pokémon from the EFFECTS of attacks/Abilities (Battle "
                       "Cage). **Inert**: passive and text-derivable, authored ahead of the "
                       "anti-spread consumer that would read it."),
    "discard_energy_recur": Tag(CURATED,
                                "A line that reloads Basic Energy from a DISCARD pile — the "
                                "attrition read that stops a spent board being priced as spent.",
                                ("common.deciders.doom", "common.strategy.combat")),
    "discard_eot": Tag(CURATED,
                       "An Energy DISCARDED at end of turn (Ignition Energy) — worth attaching "
                       "only if the holder attacks that same turn.",
                       ("common.deciders.attach", "common.deciders.board_build", "common.deciders.hand", "common.deciders.lethal", "common.deciders.needs", "common.card_worth", "common.needs",
                        "common.strategy.combat", "common.strategy.planner")),
    "tool": Tag(CURATED,
                "A Pokémon Tool — an attachment whose static modifiers ride the holder. What "
                "reads it is the ATTACH transition: `board_delta` routes a Tool attach on "
                "`stat.is_tool` and lands the holder's flat HP grant on the same step.",
                # `doctrine_tool` was deleted by POC-T4/5 (Issue #386) with its MAIN-phase
                # rungs, and `common.pilot` stopped naming the tag with it. The tag outlived
                # the doctrine because three seams still ask "is this a Tool?" as a
                # STRUCTURAL question rather than a positional one — which is why it is not
                # INERT. (`board_delta` asks the same question through `CardStat.is_tool`,
                # a cardType test, so it is not a reader OF THIS TAG and is not listed.)
                ("common.board_choice", "common.fetch_closure",
                 "common.snapshot_coverage")),
    # --- special conditions -------------------------------------------------------------------
    # All five are probe-derived and all five are INERT as card-level tags, for one shared reason:
    # a condition decides a turn through the ATTACK that inflicts it (`AttackStat`, the Damage
    # Formula and the engine's own condition state), never through "this card can, someday, poison".
    # Declared rather than deleted because the probe emits them on every build — an undeclared tag
    # the builder produces would turn `undeclared_tags` red on the next rebuild.
    "poison": Tag(DERIVED, "Inflicts Poisoned — passive chip damage each turn. **Inert as a tag** "
                           "(the attack, not the card, is what the turn reads)."),
    "burn": Tag(DERIVED, "Inflicts Burned — chip damage plus a recovery flip. **Inert as a tag.**"),
    "sleep": Tag(DERIVED, "Inflicts Asleep — cannot attack or retreat until a wake flip. **Inert "
                          "as a tag.**"),
    "paralyze": Tag(DERIVED, "Inflicts Paralyzed — cannot attack or retreat for one turn. **Inert "
                             "as a tag.**"),
    "confuse": Tag(DERIVED, "Inflicts Confused — attacking risks self-damage on a flip. **Inert as "
                            "a tag.**"),
    # --- setup / play-role / membership --------------------------------------------------------
    "opener": Tag(CURATED,
                  "A NON-Basic that may take the Active Spot from hand during setup "
                  "(Explosiveness — Cinderace), so a hand with no Basic is still keepable.",
                  ("common.deciders.hand", "common.strategy.context")),
    "stall": Tag(CURATED,
                 "A PLAY-ROLE, not a card function: a big-HP wall piloted NOT to attack, buying "
                 "tempo to set up. A curated seed of the obvious meta walls — real coverage needs "
                 "replay-usage data the pipeline does not capture. **Not** a "
                 "'does not attack much' catch-all: 1071 Meowth ex was re-modeled OFF it "
                 "(`_note_1071_stall_retired`).",
                 ("common.deciders.context_build", "common.strategy.context", "common.strategy.planner")),
    "team_rocket": Tag(CURATED,
                       "The one owner-NAME-family tag and the one ruled exception to REQ-FUNC-0001 "
                       "(Issue #374): the 52 Pokémon whose PRINTED NAME carries the \"Team "
                       "Rocket's\" prefix. In-play membership is free off `CardStat.name`; what "
                       "needs an index over the POOL is the hidden-DECK half. **Inert**, ledgered "
                       "as authored ahead of its consumer."),
}


def is_parametric(tag: str) -> str | None:
    """The :data:`PARAMETRIC_PREFIXES` family ``tag`` belongs to, or ``None``.

    The N must be a non-negative integer: ``dig:2`` is a depth, ``dig:many`` is a typo, and a family
    that accepted any suffix would exempt the whole family from :func:`undeclared_tags` — the
    "arrives already exempt from the audit meant to cover it" failure `undeclared_selector_values`
    guards against one store over."""
    for prefix in PARAMETRIC_PREFIXES:
        if tag.startswith(prefix) and tag[len(prefix):].isdigit():
            return prefix
    return None


def tag_vocabulary(table: Mapping) -> list[str]:
    """Every distinct tag string in a shipped ``{cardId: [tags]}`` table, sorted.

    **The walk, and it walks the ARTIFACT rather than a hand-kept list** — the effects layer's
    rationale applies here unchanged: *a hand-kept list is precisely what a new tag value would not
    be added to*. Reserved keys (`_note`, and any metadata block a later reader adds) are skipped
    rather than `int()`-ed, so this survives the store gaining one."""
    out: set[str] = set()
    for key, tags in (table or {}).items():
        if not is_card_key(key):
            continue
        out.update(t for t in (tags or ()) if isinstance(t, str) and t)
    return sorted(out)


def undeclared_tags(tags: Sequence[str]) -> list[str]:
    """Tags with no :data:`TAG_REGISTRY` entry and no parametric family. Empty is the contract.

    **The teeth.** A tag nothing declared is a tag nothing reads — it ships, it is audited by
    `function_audit._CUES` only if that 17-tag whitelist happens to name it, and it decides exactly
    nothing. Takes the values rather than the table so it can be bitten by a fabricated one; pair it
    with :func:`tag_vocabulary` to walk the real store. That pairing is the whole lesson of Issue
    #350 restated on this store: a table that would have bitten is worth nothing until the WALK
    arrives."""
    return sorted(t for t in set(tags)
                  if t not in TAG_REGISTRY and is_parametric(t) is None)


def unsourced_tag_instances(table: Mapping, overrides: Mapping,
                            derived: frozenset | set | Sequence[str]) -> dict[int, list[str]]:
    """``{cardId: [tags no rebuild could re-derive]}`` — empty iff ``--fresh`` is LOSSLESS.

    **The strong one, and it was RED when it was written** (eleven instances, Issue #395 Fact 3). A
    shipped tag is reachable by a rebuild in exactly two ways: `classify_functions` emits it from a
    probe record (``derived``), or `function_overrides.json` names it for that card — the union
    ``tags |= set(overrides or [])`` sits UPSTREAM of the accumulate step, so it survives ``--fresh``
    and the accumulate union does not. Anything else in the table got there by hand, and the next
    documented rebuild deletes it with nothing red.

    ``derived`` is a PARAMETER, taken from `meta_tracker.card_functions.DERIVED_TAGS`, because a
    second transcription of the classifier's own output is the drift this module exists to stop —
    and because taking it as an argument is what lets `src/common/` hold this check without importing
    `tools/`."""
    derived = set(derived)
    ov = {int(k): set(v or ()) for k, v in (overrides or {}).items() if is_card_key(k)}
    out: dict[int, list[str]] = {}
    for key, tags in (table or {}).items():
        if not is_card_key(key):
            continue
        cid = int(key)
        gap = sorted(t for t in (tags or ()) if t not in derived and t not in ov.get(cid, ()))
        if gap:
            out[cid] = gap
    return out


def is_card_key(key) -> bool:
    """Is this JSON key a card id rather than one of the store's reserved keys?

    The one predicate for this family, and deliberately the same rule as
    `snapshot_coverage.is_card_key` states for the effects family: every store here mixes numeric
    card entries with `_note` prose, and *a reader that rolls its own `int(k)` walk is the one that
    trips on the next reserved key somebody adds*. It is not IMPORTED from there because that module
    is the effects layer's contract and this one must stay importable from `tools/` with no
    dependency on it; the shared rule is one line and its home is stated in both places."""
    return str(key).lstrip("-").isdigit()


__all__: Sequence[str] = (
    "DERIVED", "CURATED", "PARAMETRIC", "SOURCES", "Tag", "TAG_REGISTRY", "PARAMETRIC_PREFIXES",
    "is_parametric", "is_card_key", "tag_vocabulary", "undeclared_tags", "unsourced_tag_instances",
)
