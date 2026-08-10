"""The Function Tag vocabulary, as a closed contract over `card_functions.json` (Issue #395 D6).

**Lib-free and dependency-free on purpose**: `tools/` imports it to lint the store it builds and
`src/common/` imports it at runtime, so it must not import the classifier — hence
`meta_tracker.card_functions.DERIVED_TAGS` is PASSED IN to :func:`unsourced_tag_instances`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

#: A tag's origin — which store can produce it, i.e. what survives a `--fresh` rebuild.
DERIVED = "derived"        # `classify_functions` can emit it from a probe record (an override may
                           # ALSO supply it for a card the probe cannot reach — a reach patch).
CURATED = "curated"        # ONLY `function_overrides.json` produces it. No probe shape yields it.
PARAMETRIC = "parametric"  # a `name:N` family; curated in practice (the probe emits plain `dig`).
SOURCES = (DERIVED, CURATED, PARAMETRIC)


@dataclass(frozen=True)
class Tag:
    """``consumers`` are dotted MODULE paths, resolved against the real tree by
    `tests/cards/test_card_functions_oracle.py`; an empty tuple asserts nothing reads the tag."""

    source: str
    reason: str
    consumers: tuple[str, ...] = ()


#: ``prefix -> what the N means``. The registry declares the FAMILY, so a new depth needs no
#: vocabulary change. The prefix includes the colon — `cards._parametric_tag`'s unit.
PARAMETRIC_PREFIXES: dict[str, str] = {
    "dig:": "how many cards this card's draw/dig Ability puts within REACH in one use — "
            "`CardFunctions.dig_depth`, read by the evolve decider's readiness odds and by "
            "`draw_hit_probability`. Per-card DATA that ages with the pool, not a constant.",
    "provides:": "how many Energy UNITS this card provides once attached — `CardFunctions."
                 "energy_provision`. The colour is NOT here: `CardStat.energyType` carries it.",
    "provides_evo:": "the same provision for a card whose units change on an Evolution Pokémon "
                     "(Issue #142) — the `evolution=True` leg of `energy_provision`.",
}


#: The closed vocabulary. Prose is sourced from `docs/card-functions.md` where it has a row.
TAG_REGISTRY: dict[str, Tag] = {
    "draw": Tag(DERIVED,
                "Draws cards into hand — raw card advantage / engine fuel. A `DRAW` log by the "
                "actor, or a look-at-top-then-take (`LOOKING→HAND`).",
                ("common.deciders.context_build", "common.deciders.hand", "common.deciders.order", "common.strategy.context")),
    "search": Tag(DERIVED,
                  "Tutors a SPECIFIC card straight out of the deck (`DECK→HAND`/`BENCH`/`ACTIVE`) — "
                  "consistency. A top-N look is `dig`+`draw`, not this.",
                  ("common.deciders.hand", "common.deciders.order", "common.strategy.context")),
    "dig": Tag(DERIVED,
               "Looks at / reorders the top or bottom of the deck — selection and information. A "
               "`MOVE_CARD` touching the `LOOKING` area.",
               ("common.deciders.hand", "common.deciders.order", "common.strategy.context")),
    "energy_accel": Tag(DERIVED,
                        "Attaches Energy beyond the manual once-per-turn drop — ramp / tempo. An "
                        "`ATTACH` log by the actor from a non-Tool card.",
                        ("common.strategy.combat_math.energy", "common.strategy.context")),
    "recycle": Tag(DERIVED,
                   "Returns cards from the discard pile to hand/deck/play — resource recursion.",
                   ("common.card_worth", "common.needs")),
    "tutor_energy": Tag(CURATED,
                        "A deck-search specifically for an ENERGY card into hand — the attachable "
                        "fuel the Turn Planner's Supporter-enabled KO line needs (ADR-0031). "
                        "Refines the probe's plain `search`, which sees only the generic "
                        "`DECK→HAND` move. Discard-pile retrieval stays `recycle`, a top-N look "
                        "stays `dig`.",
                        ("common.strategy.planning.gamble", "common.strategy.planning.readiness", "common.strategy.combat_math.energy")),
    "tutor_pokemon": Tag(CURATED,
                         "A fetch whose reachable class is Pokémon — the Planner's fetch-class read "
                         "and the planner's cost/benefit split on an Ultra Ball-shaped play. "
                         "NOT read by `fetch_closure`, whose ADR-0032 clause predicate REPLACED the "
                         "tag-keyed `_FETCH_FILTERS` (it names the tag only in prose).",
                         ("common.deciders.deploy", "common.strategy.planning.gamble", "common.strategy.planning.ko_classes", "common.strategy.planning.readiness")),
    "tutor_mega": Tag(CURATED,
                      "A fetch restricted to a Rule-Box Mega ex — the fact the generic "
                      "`tutor_pokemon` cannot carry, so a wincon-in-hand read would over-claim. "
                      "Same non-consumer note as `tutor_pokemon`: `fetch_closure` mentions it, and "
                      "reads the clause instead.",
                      ("common.deciders.deploy", "common.deciders.hand", "common.deciders.needs", "common.strategy.planning.gamble", "common.strategy.planning.ko_classes", "common.strategy.planning.readiness")),
    "tutor_trainer": Tag(CURATED,
                         "A Supporter that searches ANY Trainer card out of the deck (Team "
                         "Rocket's Petrel class) — the Planner's route to a wincon-line Trainer.",
                         ("common.strategy.planning.wins",)),
    "supporter_tutor": Tag(CURATED,
                           "A body whose ON-PLAY Ability fetches a SUPPORTER (Meowth ex's "
                           "Last-Ditch Catch) — a bench-drop that buys a Supporter, which is a "
                           "utility body rather than a wall. Replaced `stall` on 1071 in 2026-07.",
                           ("common.deciders.attach", "common.deciders.deploy", "common.needs", "common.strategy.context")),
    "bench_fill": Tag(CURATED,
                      "Fetches Basics straight onto the Bench (Buddy-Buddy Poffin) — bench "
                      "development and deck-thinning in one play.",
                      ("common.deciders.deploy",)),
    "cost_discard": Tag(CURATED,
                        "A fetch that COSTS a discard from hand (Ultra Ball class) — a blind, "
                        "costly commitment the sequencer defers behind free development, and whose "
                        "shed side `doctrine_fetch` prices.",
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
                       ("common.deciders.deploy", "common.deciders.hand", "common.deciders.needs", "common.strategy.planning.gamble")),
    "gust": Tag(DERIVED,
                "Drags the opponent's Active out to pull a target up (Boss's Orders) — a `SWITCH` "
                "log on the OPPONENT's side.",
                ("common.deciders.board_build", "common.deciders.needs", "common.deciders.order", "common.strategy.planning.gamble", "common.strategy.planning.ko_classes", "common.strategy.planning.wins",
                 "common.strategy.doctrines.doctrine_gust")),
    "hand_disruption": Tag(DERIVED,
                           "Shuffles or discards the opponent's hand — resource denial. Their "
                           "cards move `HAND→DECK`/`DISCARD` during this card's resolution.",
                           ("common.deciders.board_build", "common.deciders.deploy", "common.deciders.hand", "common.deciders.needs",)),
    "energy_denial": Tag(DERIVED,
                         "Removes the opponent's ATTACHED Energy — tempo denial (their "
                         "`ENERGY→DISCARD`).",
                         ("common.deciders.deny", "common.needs")),
    "shuffle_hand": Tag(CURATED,
                        "A refresh that shuffles BOTH hands away and redraws (Iono, Unfair Stamp) "
                        "— a Gamble Line: it can refill a small opponent hand, so ADR-0060 forbids "
                        "reading it as a strip.",
                        ("common.deciders.context_build", "common.deciders.order", "common.strategy.planning.gamble",
                         "common.strategy.doctrines.doctrine_shuffle_refresh")),
    "item_lock": Tag(CURATED,
                     "A body whose Ability locks Item play (the benched-disruptor maneuver) — read "
                     "on BOTH sides: it gates our own Item lines and prices their disruptor.",
                     ("common.deciders.board_build", "common.deciders.promote")),
    "switch": Tag(DERIVED,
                  "Moves my OWN Active out — reposition / escape. Also read on THEIR side, where a "
                  "switch card anywhere waives the Threat-Clock bench-promotion surcharge.",
                  ("common.deciders.evolve", "common.deciders.needs", "common.deciders.promote", "common.strategy.objectives", "common.strategy.planning.leaf")),
    "heal": Tag(DERIVED,
                "Removes damage from my Pokémon — longevity. An `HP_CHANGE` (value > 0, not a "
                "damage counter) on my side.",
                ("common.strategy.planning.ko_classes", "common.strategy.planning.ladder")),
    "clutch_heal": Tag(CURATED,
                       "A heal that also BOUNCES the healed Pokémon's Energy to hand (Wally's "
                       "Compassion) — a defensive save, not a value heal: held until the Active is "
                       "doomed, then played and re-powered the same turn.",
                       ("common.deciders.heal", "common.deciders.needs", "common.card_worth", "common.needs",
                        "common.strategy.planning.ladder", "common.strategy.planning.leaf")),
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
                                ("common.deciders.doom", "common.strategy.combat_math.energy")),
    "discard_eot": Tag(CURATED,
                       "An Energy DISCARDED at end of turn (Ignition Energy) — worth attaching "
                       "only if the holder attacks that same turn.",
                       ("common.deciders.attach", "common.deciders.board_build", "common.deciders.hand", "common.deciders.lethal", "common.card_worth", "common.needs",
                        "common.strategy.combat_math.energy", "common.strategy.planning.gamble", "common.strategy.planning.ladder", "common.strategy.planning.wins")),
    "tool": Tag(CURATED,
                "A Pokémon Tool — an attachment whose static modifiers ride the holder. What "
                "reads it is the ATTACH transition: `board_delta` routes a Tool attach on "
                "`stat.is_tool` and lands the holder's flat HP grant on the same step.",
                # `board_delta` asks the same question through `CardStat.is_tool` (a cardType test),
                # so it is not a reader OF THIS TAG and is deliberately not listed.
                ("common.board_choice", "common.fetch_closure",
                 "common.snapshot_coverage")),
    # --- special conditions: all five INERT (a condition decides a turn through the ATTACK that
    # inflicts it), declared anyway because the probe emits them and an undeclared tag goes red.
    "poison": Tag(DERIVED, "Inflicts Poisoned — passive chip damage each turn. **Inert as a tag** "
                           "(the attack, not the card, is what the turn reads)."),
    "burn": Tag(DERIVED, "Inflicts Burned — chip damage plus a recovery flip. **Inert as a tag.**"),
    "sleep": Tag(DERIVED, "Inflicts Asleep — cannot attack or retreat until a wake flip. **Inert "
                          "as a tag.**"),
    "paralyze": Tag(DERIVED, "Inflicts Paralyzed — cannot attack or retreat for one turn. **Inert "
                             "as a tag.**"),
    "confuse": Tag(DERIVED, "Inflicts Confused — attacking risks self-damage on a flip. **Inert as "
                            "a tag.**"),
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
                 ("common.deciders.context_build", "common.strategy.context", "common.strategy.planning.readiness")),
    "team_rocket": Tag(CURATED,
                       "The one owner-NAME-family tag and the one ruled exception to REQ-FUNC-0001 "
                       "(Issue #374): the 52 Pokémon whose PRINTED NAME carries the \"Team "
                       "Rocket's\" prefix. In-play membership is free off `CardStat.name`; what "
                       "needs an index over the POOL is the hidden-DECK half. **Inert**, ledgered "
                       "as authored ahead of its consumer."),
}


def is_parametric(tag: str) -> str | None:
    """The N must be a non-negative integer — a family that accepted any suffix would exempt the
    whole family from :func:`undeclared_tags`."""
    for prefix in PARAMETRIC_PREFIXES:
        if tag.startswith(prefix) and tag[len(prefix):].isdigit():
            return prefix
    return None


def tag_vocabulary(table: Mapping) -> list[str]:
    """Every distinct tag string in a shipped ``{cardId: [tags]}`` table, sorted. Walks the ARTIFACT,
    never a hand-kept list — that list is exactly what a new tag value would not be added to."""
    out: set[str] = set()
    for key, tags in (table or {}).items():
        if not is_card_key(key):
            continue
        out.update(t for t in (tags or ()) if isinstance(t, str) and t)
    return sorted(out)


def undeclared_tags(tags: Sequence[str]) -> list[str]:
    """Tags with no :data:`TAG_REGISTRY` entry and no parametric family. Empty is the contract; takes
    VALUES rather than the table so a fabricated one can bite it. Pair with :func:`tag_vocabulary`."""
    return sorted(t for t in set(tags)
                  if t not in TAG_REGISTRY and is_parametric(t) is None)


def unsourced_tag_instances(table: Mapping, overrides: Mapping,
                            derived: frozenset | set | Sequence[str]) -> dict[int, list[str]]:
    """``{cardId: [tags no rebuild could re-derive]}`` — empty iff ``--fresh`` is LOSSLESS. ``derived``
    is a PARAMETER (`meta_tracker.card_functions.DERIVED_TAGS`) so `src/` need not import `tools/`."""
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
    """Is this JSON key a card id rather than a reserved key like `_note`? Deliberately the same rule
    as `snapshot_coverage.is_card_key`, restated rather than imported to keep this module leaf-free."""
    return str(key).lstrip("-").isdigit()


__all__: Sequence[str] = (
    "DERIVED", "CURATED", "PARAMETRIC", "SOURCES", "Tag", "TAG_REGISTRY", "PARAMETRIC_PREFIXES",
    "is_parametric", "is_card_key", "tag_vocabulary", "undeclared_tags", "unsourced_tag_instances",
)
