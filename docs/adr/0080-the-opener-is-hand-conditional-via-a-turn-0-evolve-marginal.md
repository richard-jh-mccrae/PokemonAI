# ADR-0080 — The opener is hand-conditional: a turn-0 evolve marginal REORDERS the declaration, and pins hold their slots

**Status:** Accepted (grilled 2026-07-29, `/grill-with-docs` on Issue #203 — five locked decisions).
Build: Issue #203. **Extends ADR-0079** (the Set-Up Active pick is one deck declaration) rather than
overturning it: the declaration stays, `open-the-declared-starter` stays at `+40`, and the seam keeps
exactly one rule and one boolean. What changes is that the declaration's *effective order* is
resolved against the opening hand before the boolean is read. Collects the placement work
**ADR-0070 §4** parked as *"a placement follow-up"*. Applies **ADR-0034** (ids live in the
declaration, never in a trigger), **ADR-0046** (analysis proposes, one skill applies) and
**ADR-0065** (no fudge constants).

**Context issues:** Issue #203 (this grill / build), Issue #161 / ADR-0079 (the declaration this
extends), Issue #197 (the pregame **Bench** sibling — disjoint select context, still not merged).

⚠️ **Number claimed at grill time.** `docs/adr/README.md` records the recurring lesson (0071 once,
0074 three ways, 0076 twice, 0079 three times): the number settles at *merge* time, not grill time.
Keep references greppable and expect to renumber.

## Context

ADR-0079 replaced five `_SETUP_ACTIVE` rungs with one rule over one deck declaration
(`Strategy.starter_priority` → `open-the-declared-starter`). That shipped and is correct as far as it
goes. This ADR is about what a flat ranking **cannot express**: the right opener frequently depends
on *what else is in hand*, not on which bodies are on offer.

**The defect, reproduced live on the shipped `mega_lucario` Pilot (2026-07-29):**

```
case1  hand=[{F}En, Solrock, Riolu, MegaLucEx]   top_starter_id=Solrock  chosen=Solrock   ❌
case2  hand=[{F}En, Solrock, Riolu, Makuhita]    top_starter_id=Solrock  chosen=Solrock   ✅
```

Nothing about the *bodies* differs between the two frames — only the hand does. Yet both open
Solrock, whose Cosmic Beam `{F}` 70 *"does nothing"* without a benched Lunatone, while Riolu is one
hop and one `{F}` from Aura Jab **130**. Case 1 is a true **inversion**, not a tie-break, so
"declaration + equation **tie-breaks**" is too weak a design — the equation must be able to
**reorder**.

Five findings from this grill reshaped the issue as filed. All were verified at source, and three
changed the answer space.

**1. The issue's second discriminator does not discriminate.** Issue #203 states case 1 flips on
*"is the payoff in hand"* **and** *"is Solrock live at all"*. Neither hand contains Lunatone, so
Solrock is equally dead — and equally able to fetch one later — in **both** frames. The *only*
separator between case 1 and case 2 is **Mega Lucario ex being in hand**. This halves the equation's
required inputs and is why the shipped `Strategy.partners`
(`{SOLROCK: [LUNATONE], LUNATONE: [SOLROCK]}`, read by `Pilot._partner_absent` for the attach
oracle) — which looked like the obvious existing vocabulary for case 1 — turns out not to be
load-bearing here.

**2. The hand read the issue asks for already exists.** Issue #203's question 3 asks whether the
equation needs *"a hand-contents read the Set-Up Active seam does not have today"*. Measured: it does
not. `board.hand_ids` is **fully populated at the pregame seam**, including the non-startable payoff
card (`MegaLucEx`, 678, appears in the trace above), and `board.hand_basic_energy` reports the `{F}`.
No new `Board` field, no new plumbing.

**3. Case 3's premise holds, but as a DECK fact, not a card fact.** Cinderace (666) is a **Stage 2,
`evolvesFrom` Raboot**, retreat 0 (engine `CardData`). `src/agents/mega_starmie/deck.csv` runs 4×
Cinderace and **zero Raboot, zero Scorbunny** — so setup genuinely is its only route into play *in
this deck*, and a deck running the line would have another. Issue #203's proposed *"card-fact
predicate"* is therefore insufficient on its own: the predicate must read the **decklist**.
`Pilot.deck` (`pilot.py:1136`) holds all 60 ids, and matching on the `evolvesFrom` **name** correctly
handles reprints (Raboot exists as both 152 and 665).

**4. A general readiness/tempo equation BREAKS case 2.** Solrock's Cosmic Beam does nothing
partnerless, so a 2-turn reachable-damage read scores Solrock **0** against Riolu's Accelerating Stab
**30** — flipping case 2 to Riolu, which the user ruled wrong. Rescuing it needs an override
threshold somewhere between 30 and 130: a taste constant with a derivation-shaped explanation, i.e.
the `_PRIZE_UNIT = 12` failure mode ADR-0065 forbids and ADR-0078 re-records.

**5. Two live decks are hazarded by an unguarded marginal.**

| deck | line | marginal if payoff in hand | hazard |
|---|---|---|---|
| `mega_starmie` | Staryu 20 → **Mega Starmie ex 120/210** | up to **+190** | flips Cinderace → Staryu and **permanently forfeits all 4 Cinderace** |
| `dragapult_ex` | Dreepy 10/40 → **Drakloak 70** → Dragapult ex 70/200 | **+30…+60** | promotes Dreepy above Munkidori / Dunsparce / Fezandipiti ex |
| `dragapult_ex` | Dunsparce 20 → **Dudunsparce 90** | **+70** | promotes Dunsparce above Munkidori |

The dragapult rows overturn an **explicit user ruling** recorded in ADR-0079 Amendment B — Dreepy
ranks 5th, *below* a 2-prize Fezandipiti ex, because *"an Active Dreepy is a misplaced Line base…
the Line base is wanted on the BENCH."* So pins are needed for **demotions**, not only for rank-1
intent, and the derived predicate of decision 1 does **not** catch these.

Other facts verified at source and load-bearing below: `docs/rules.md:96-97` — *"Cannot evolve a
Pokémon the turn it was played/put into play"* and *"Cannot evolve on either player's very first
turn"*, so an opened Riolu's Mega lands turn 2 at the earliest; `Strategy.starter_priority` has **no
serialization surface** (Python `strategy.py` files and tests only — no manifest, no JSON); the
Hypothesis layer scores strictly boolean (`score = sum(w for _h, w in fired) + tactical`), so there
is no multiplier surface.

## Decision

**1. Rank 1 IS overridable. Un-overridability is a PIN, and pins are DERIVED first, DECLARED as the
override.** The equation may reorder anything not pinned, rank 1 included — option "the equation only
reorders ranks 2..N" is refuted by the motivating frame, since Solrock **is** rank 1 in
`mega_lucario/strategy.py:378` and case 1 requires overriding it.

The derived pin is a new Pilot predicate, `_route_only_at_setup(cid)`: the card `_opens_from_hand`
(the `opener` Function Tag) **∧** `stats[cid].evolvesFrom` is truthy **∧** no card in `self.deck`
carries that `evolvesFrom` **name**. That is "this body's only route into play is the setup pick",
and it pins Cinderace with **no author input** while staying correct across deck edits — add Raboot
to the deck and the pin lifts by itself.

Derivation-first with declaration as the confirm/override is this repo's established pattern, cited
in ADR-0079 Amendment F for `_derived_accel_body_ids`. A purely-declared pin was rejected because it
hands the author a judgement the engine can compute and **drifts** — a stale pin survives the deck
edit that invalidates it.

**2. The declared pin is a MARKABLE ENTRY IN THE ONE LIST, not a second field.**
`starter_priority=[Pin(BUDEW), MUNKIDORI, DUNSPARCE, …]`, where `Pin` is a frozen dataclass exported
from `common.strategy.strategy` and the field types as `list[int | Pin]`. One normaliser
(`_rank_id(entry)`) that every reader goes through.

A separate `starter_pinned: frozenset[int]` was rejected **by name**: ADR-0079's Alternatives-rejected
section already lists *"the list supplying only order — **two declarations that must agree per
card**"*, and its decision 4 retired the `starter` Role on the reasoning that *"two vocabularies for
one concept … desynchronises at the first edit."* A pinned id absent from `starter_priority` would be
a silent no-op — precisely that failure. Deriving the pin from the `item_lock` Tag instead was also
rejected: it rebuys, one ADR later, the `open-the-item-lock-starter` proxy that ADR-0079 decision 2
deleted, and it over-fires on a deck that wants its item-lock body benched.

Cheap because `starter_priority` has no serialization surface (Context). The one hazard is that a
missed call site fails **open** — an unwrapped `Pin` compares unequal to a bare id and the body
silently stops being top-starter — so the normaliser gets its own test.

**3. The equation reads the HAND ONLY.** Inputs are `board.hand_ids`, `board.hand_basic_energy` and
card facts. No `deck_contains_odds`, no `deck_definitely_empty_of`. Fully deterministic.

The reason is that **at turn 0 the deck carries no frame-specific information.** Nothing has been
drawn, discarded or revealed. So the sound oracle is near-vacuously false at this seam (it can only
answer "yes" once cards are known-gone, and at setup essentially none are), while the probabilistic
one is a *near-constant per deck* — a hypergeometric over a fixed 60-card list. Anything it would say
is a property of the decklist, which the author already knows and has already encoded in the
ranking's order; letting the equation re-derive it slightly wrongly is strictly worse. It would also
brush ADR-0074 (*"a probability may weight a ranked value, never gate a lock"*), and a pin is a lock.

This yields the division of labour the design rests on: **the declaration owns what the deck
contains; the equation owns what this hand contains.** The equation reads exactly the information the
declaration structurally cannot know, and nothing else.

**4. The currency is DAMAGE, and the equation is ADR-0070's evolve marginal read at turn 0. It fires
ONLY when the offered body's evolution payoff is in hand.** For an offered body `b`, if some `e` in
`board.hand_ids` has `stats[e].evolvesFrom == stats[b].name`, the marginal is
`maxDamage(e) − maxDamage(b)`, in damage. Otherwise **0**.

| frame | hand | Riolu | Solrock | equation |
|---|---|---|---|---|
| case 1 | Solrock, Riolu, **Mega Luc ex**, `{F}` | Aura Jab 130 − Stab 30 = **+100** | 0 | **fires → Riolu** ✅ |
| case 2 | Solrock, Riolu, Makuhita, `{F}` | no Mega in hand → **0** | 0 | **silent → Solrock** ✅ |

The decisive property is that the equation is **silent by default**. It has no opinion on which body
is "better" — it detects only a *stranded payoff in hand*, which is the one thing a ranking authored
before the hand is dealt cannot carry. Cases 2, 3, 4 and 6 therefore keep the shipped answer **by
construction rather than by tuning**, which is what removes the need for the threshold constant
Context finding 4 shows a general tempo equation would require.

It reconciles with ADR-0069/0070 **by identity rather than by conversion**: it *is* the evolve
marginal, in damage, evaluated at turn 0 instead of on the `_EVOLVE` path — the work ADR-0070 §4
parked. Prize-equivalents (`PRIZE_DAMAGE_RATE`) buy nothing at a seam where no KO is in reach;
card-worth points are unavailable outright, since ADR-0078 decision 2 records that the **Worth Damage
Rate does not exist** and its gate 2 remains unanchored as of that ADR's Amendment C.

**Issue #203's question 5 dissolves rather than needing a ruling.** Frame **6b** (Dreepy +
Fezandipiti ex, no accel) holds no evolution payoff, so the equation is silent, the declaration
stands, and the answer is Fez ex — the shipped behaviour. The frame is undecided only for designs
that read it; this one does not.

**5. The override is STRUCTURAL — the equation reorders the declaration BEFORE `top_starter_id`
resolves. Pinned entries hold their declared slot; unpinned entries are re-sorted among the remaining
slots by (marginal desc, declared rank asc).** `Pilot._top_starter_id` gains the reorder and then
does its existing `next(cid for cid in order if cid in present)`. `open-the-declared-starter` is
untouched at `+40`.

So **ADR-0079 decision 5 survives intact**: one rule, one boolean, a forced single pick
(`minCount`/`maxCount` 1) whose argmax reads only the winner. The equation changes what the
declaration *says*, not what anything *scores*.

Additive scoring — an `_opener_tactical` term in the `tactical` sum — was rejected as **unsound, not
merely inelegant**: `open-the-declared-starter`'s weight is **learned**. ADR-0079's own Consequences
record `tuned.json` carrying `"open-the-accelerator": 45.0`, and this rule inherits that lane, so a
tuner that learns 150 silently disarms the override with nothing failing. Correctness that depends on
a learned scalar staying small is not correctness. It is also the cross-currency comparison Issue
#203 warns about — a damage magnitude racing a doctrine weight band, i.e. the `+40 > +35` accident
ADR-0079 deleted, rebuilt. A second Hypothesis (`open-the-unlocked-payoff` at a higher seed) avoids
the currency mixing but is two rules at one seam ordered by two independently-tuned *learnable*
numbers — the same pile, and the same fragility.

Slot-holding is also what gives `Pin` the semantics Context finding 5 demands: it expresses a
**demotion** pin (`Pin(DREEPY)` at rank 5 = *"Dreepy stays fifth, do not promote it"*), which a
"pinned wins if present" semantics cannot express at all.

## Consequences

- The Set-Up Active seam keeps **one rule and one boolean**; what gains hand-awareness is the
  *resolution* of `board.top_starter_id`, not the scoring. ADR-0079 decisions 1, 2, 5 and 6 are
  unchanged.
- `Pilot._top_starter_id` stops being a five-line "first present" scan and becomes a ranking function
  needing `stats` and the hand. It earns its own unit tests, and **`board.top_starter_id` becomes
  hand-dependent** — existing fixtures that assume it resolves to Solrock need hand-aware rebuilds.
- **`dragapult_ex` requires `Pin(DREEPY)` and `Pin(DUNSPARCE)` as part of this change.** Per Context
  finding 5 these are not optional polish: shipping decision 4 without them actively regresses the
  deck against the ADR-0079 Amendment B user ruling. Being doctrine, they go through the ADR-0046
  proposal pipeline with a `score_diff` gate, not a hand edit.
- `Strategy.starter_priority` types as `list[int | Pin]`. Known call sites: `Pilot._top_starter_id`,
  `tests/strategy/test_setup_active_placement.py` (the completeness invariant),
  `tests/strategy/test_budew_sacrificial_starter.py:56` (asserts `starter_priority[:1] == [_BUDEW]`,
  becomes `[Pin(BUDEW)]`), and `/deck-align`'s drift finding. A missed site fails **open**.
- The completeness invariant of ADR-0079 decision 5 must normalise through `_rank_id` — otherwise a
  `Pin`-wrapped id reads as unranked and the invariant fails for a spurious reason.
- `Strategy.partners` gains no consumer here. Context finding 1 establishes it does not discriminate
  case 1, so the temptation to wire it at this seam is recorded as **declined**, with the reason.
- **Accepted limit:** the equation is deliberately narrow and prices no tempo/readiness family. The
  accelerator question (frames 6 / 6b) and the opportunity-cost question (frame 5, Meowth ex's
  bench-only Last-Ditch Catch) get no equation — only the declaration. A future frame showing one of
  those genuinely inverting a ranking reopens this, and should reopen it as a grill rather than as a
  threshold.
- **Accepted risk:** the derived pin reads `self.deck`, so an agent constructed with an empty or
  wrong decklist silently loses its Cinderace-class pins. `_route_only_at_setup` should fail
  **closed** (pin when unknown), the opposite of `_is_startable_body`'s fail-open, because the cost
  of a missing pin is a permanently forfeited card and the cost of a spurious one is a suboptimal
  open.
- `/deck-genie` and `/deck-align`'s opener banks (ADR-0079 decision 10) gain a question they do not
  ask today: *which of your ranks are pins, and which are demotion pins?* Without it the hazard in
  Context finding 5 recurs for every newly-authored deck.

## Alternatives rejected

- **The equation only tie-breaks; the declaration always wins.** Refuted by case 1, which is an
  inversion between identical bodies — a tie-break cannot reach it. This is the design Issue #203 was
  filed to move past.
- **The equation only reorders ranks 2..N; rank 1 is sacred.** Refuted by the motivating frame:
  Solrock *is* rank 1, and case 1 requires overriding it.
- **Everything overridable; the declaration is a pure prior.** Forfeits all 4 Cinderace in
  `mega_starmie` (Context finding 5) — an irreversible loss traded for a marginal turn-1 gain.
- **Pins declared only, no derivation.** Author burden for a computable fact, plus stale-pin drift
  across deck edits.
- **Pins derived only, no declaration.** Cannot express Budew's intent or dragapult's demotion pins,
  neither of which is derivable.
- **A general 2-turn readiness/tempo equation** (`build_standing` / `turns_to_ready` re-read at turn
  0), the shape Issue #203's family (A) sketched. Breaks case 2 (Context finding 4) and needs an
  underivable threshold to rescue it.
- **Denominating in prize-equivalents or card-worth points.** The former converts for no benefit at a
  seam with no KO in reach; the latter is unavailable — ADR-0078's Worth Damage Rate has no anchor.
- **Reading deck reachability (odds or the sound oracle).** Carries no frame-specific information at
  turn 0 (decision 3).
- **Additive `_opener_tactical`, or a second higher-weighted Hypothesis.** Both make the override's
  correctness depend on **learned** weights, and both re-introduce the cross-rule ordering ADR-0079
  decision 2 deleted (decision 5).
