# ADR-0080 — The opener is hand-conditional: a turn-0 evolve marginal REORDERS the declaration, and pins hold their slots

**Status:** Accepted (grilled 2026-07-29, `/grill-with-docs` on Issue #203 — five locked decisions,
plus **Amendment A** from the same session, which narrows decision 4 and defers decision 2 — read it
before building; it changes what two decisions deliver).
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
the Line base is wanted on the BENCH."*

> **Superseded by Amendment A.** This finding originally concluded that pins are needed for
> **demotions** and that `dragapult_ex` must ship `Pin(DREEPY)` / `Pin(DUNSPARCE)`. Amendment A
> silences all three rows *structurally* instead — none of Drakloak, Dudunsparce or Hariyama is a
> declared `Line` payoff — so no demotion pin is needed anywhere in the repo today. The finding is
> kept because it is what *diagnosed* the mis-specification, and because it is the frame that would
> revive decision 2 if a deck ever wants a promotion the Line clause forbids.

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

**2. The declared pin is a MARKABLE ENTRY IN THE ONE LIST, not a second field. ⚠️ DEFERRED — not
built; see Amendment A.** Amendment A's Line-payoff clause leaves this form with **zero consumers**,
so it ships as a decided *shape* awaiting a frame (ADR-0079 decision 3's discipline), not as code.
The reasoning below is what to build **if** a frame ever needs it.
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
ONLY when the offered body's evolution payoff is in hand AND that payoff is the deck's declared
WIN CONDITION.** For an offered body `b`, if some `e` in `board.hand_ids` has
`stats[e].evolvesFrom == stats[b].name` **and** `e == line.payoff` for some `line` in
`Strategy.lines`, the marginal is `maxDamage(e) − maxDamage(b)`, in damage. Otherwise **0**.

The Line-payoff clause is **Amendment A** and is load-bearing, not a refinement: without it the
equation fires on 5 promotable bodies across the three authored decks and only 1 firing is wanted.

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

Under Amendment A this silence is *measured*, not asserted: across `mega_lucario`, `dragapult_ex` and
`mega_starmie` the equation changes **exactly one decision** — case 1 — and `dragapult_ex` is
untouched entirely.

> **The gate is the declared Line PAYOFF, never the win-condition ROLE set — and the two must not be
> collapsed** (build, 2026-07-29). The runtime already has `_wincon_set`, whose first clause is
> identical to the payoff set this decision needs, so reusing it looks like ordinary deduplication.
> It is not. `_wincon_set` additionally unions in every card carrying a `win_condition` /
> `primary_attacker` **Role**, and a Role is a label on a card that says nothing about whether that
> card ends a declared evolution path. Reading it here would let a role-tagged body on **no** Line act
> as an opener payoff, widening the gate past what this decision specifies.
>
> The hazard is live, not theoretical. mega_lucario's Hariyama (210 damage) is excluded twice over —
> its Line role is `secondary_attacker` *and* its card Role is `["secondary_attacker", "gust"]`.
> Promote that Role to `primary_attacker` in a future `/deck-align` pass — an entirely reasonable
> doctrine edit — and the `_wincon_set` reading silently re-admits Hariyama, resurrecting the
> Makuhita-over-Solrock defect from a change that looks unrelated to openers.
>
> **The two sets coincide for all three authored decks today**, so the divergence is latent: swapping
> them changes no shipped behaviour and reddens no test that existed before this note. That is
> precisely why it is recorded *here* and guarded by a dedicated test
> (`test_a_ROLE_tagged_body_that_is_no_line_payoff_does_not_promote_its_base`) rather than left in a
> docstring on `_wincon_payoff_ids` — a docstring dies with the function a reviewer proposes deleting,
> and prose asks a maintainer to be careful where a test makes carelessness fail. Mutation-checked:
> widening the gate to `_wincon_set` reddens that test and no other.

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

## Amendment A — the payoff must be the declared LINE payoff; decision 2 loses its consumers (2026-07-29, same grill)

Decision 4 as first locked claimed to be *"silent by default"*. **Enumerating every promotable body in
the repo falsifies that claim**, and the check should have been run before locking:

| deck | base | in-hand payoff | a declared `Line` payoff? | wanted? |
|---|---|---|---|---|
| `mega_lucario` | Riolu | Mega Lucario ex | ✅ `Line(payoff=MEGA_LUCARIO_EX)` | ✅ **the fix** |
| `mega_lucario` | Makuhita | Hariyama (210) | ✗ no Line | ✗ |
| `dragapult_ex` | Dreepy | **Drakloak** | ✗ the Line's payoff is Dragapult **ex** | ✗ ruled against |
| `dragapult_ex` | Dunsparce | Dudunsparce | ✗ no Line — the *draw engine* | ✗ |
| `mega_starmie` | Staryu | Mega Starmie ex | ✅ `Line(payoff=MEGA_STARMIE_EX)` | ~ harmless |

**1 of 5 firings is wanted.** The design was noisy by default, and decision 2's pins were being used
to suppress the noise one card at a time — which is **re-buying the guard pile ADR-0079 decision 2
deleted**. That deletion rested on *"a guard that second-guesses a complete, deliberate ranking is …
an override of deck intent"* — sound while the ranking is **static**, which is exactly the property
this ADR removes. `dragapult_ex`'s Dunsparce row is the deleted `dont-open-with-the-engine` (−12)
arriving back verbatim: `STRATEGY.md:128` says *"bench Dunsparce … → evolve → Run Away Draw"*.

**The fix is at the specification, not per instance:** the in-hand payoff must be the `payoff` of a
declared `Line` — the deck's stated win condition. Existing vocabulary (all four agents declare
`lines`), so no new declaration.

Effect: Dreepy, Dunsparce and Makuhita go silent **structurally**. Staryu still fires but is
harmless — Cinderace's *derived* pin holds slot 0 when present, and when absent Staryu is the only
other body in the deck. Net across all three authored decks: **exactly one behaviour change,
`mega_lucario` case 1** — the one measured defect in Issue #203.

**Consequences of the amendment:**

- **`dragapult_ex` needs no pins and sees no behaviour change.** The build-blocking dependency
  recorded before this amendment is **withdrawn**.
- With Dreepy and Dunsparce silent, nothing can out-promote Budew, so **Budew needs no pin either**.
  Decision 2's declared-`Pin` form therefore has **zero consumers** and is deferred rather than built
  — ADR-0079 decision 3's *"the refinement awaits a frame"* discipline, applied to this ADR's own
  vocabulary.
- Decision 1's **derived** pin (`_route_only_at_setup`, Cinderace) is unaffected and remains
  essential; only its declared-override half loses its consumer.
- **Accepted limit:** a deck whose correct opener flip involves a non-win-condition body is now
  unreachable, and needs a fresh grill rather than a tweak. The only in-repo candidates are a draw
  engine the doctrine says to bench and a stepping stone already ruled against, so the limit is
  currently free.

Recorded at length because the sequencing is the lesson, and it is the same one ADR-0078 Amendment C
records: the design was locked on an *asserted* property ("silent by default") that a five-row
enumeration falsified in minutes. The decklists were available the whole time.

## Consequences

- The Set-Up Active seam keeps **one rule and one boolean**; what gains hand-awareness is the
  *resolution* of `board.top_starter_id`, not the scoring. ADR-0079 decisions 1, 2, 5 and 6 are
  unchanged.
- `Pilot._top_starter_id` stops being a five-line "first present" scan and becomes a ranking function
  needing `stats` and the hand. It earns its own unit tests, and **`board.top_starter_id` becomes
  hand-dependent** — existing fixtures that assume it resolves to Solrock need hand-aware rebuilds.
- ~~**`dragapult_ex` requires `Pin(DREEPY)` and `Pin(DUNSPARCE)`.**~~ **Withdrawn by Amendment A** —
  both rows are silenced structurally by the Line-payoff clause, and `dragapult_ex` sees no
  behaviour change at all.
- `Strategy.starter_priority` keeps its `list[int]` type for now: decision 2's `Pin` form is
  **deferred**, so no call site changes and `test_budew_sacrificial_starter.py:56` stands as written.
  If a frame ever revives it, the field types as `list[int | Pin]` and the affected sites are
  `Pilot._top_starter_id`, the ADR-0079 decision 5 completeness invariant (which must normalise
  through `_rank_id`, else a wrapped id reads as unranked), that Budew assertion, and `/deck-align`'s
  drift finding — with a missed site failing **open**.
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
- ~~`/deck-genie` and `/deck-align`'s opener banks gain a *"which ranks are pins"* question.~~
  **Superseded by Amendment A** — with the declared `Pin` deferred there is nothing to ask. What the
  banks (ADR-0079 decision 10) *do* now owe is a **`Line` payoff check**, because the Opener Marginal
  reads `Strategy.lines[].payoff`: a deck that declares no Line, or names the wrong payoff, silently
  gets no equation at all.
- **New dependency, and it is unguarded.** ADR-0079 decision 5 gives `starter_priority` a CI
  completeness invariant; `Strategy.lines` has **no equivalent** (no `tests/strategy/` test asserts a
  deck declares one). The marginal fails **closed** when it is missing, so this is a silent-no-op
  risk rather than a wrong-answer risk — but it means the opener fix can be disabled by an unrelated
  edit to `lines` with nothing failing. Worth an invariant when this builds.

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
- **An unrestricted payoff, with demotion pins suppressing the hazards** (decision 4 as first
  locked). 1 wanted firing in 5, and the suppression is ADR-0079's deleted guard pile rebuilt by
  hand, per card, per deck — with every future deck needing an author to spot the hazard unaided.
  Superseded by Amendment A.
- **Restricting to a TERMINAL hop** (nothing in the deck evolves from the payoff) instead of the Line
  payoff. Kills Dreepy — Drakloak is not terminal, and per `docs/rules.md` §4's *"new in play"*
  clause it cannot evolve again the same turn anyway — but Dudunsparce and Hariyama **are** terminal,
  so two hazards survive. Strictly dominated by Amendment A's clause.
