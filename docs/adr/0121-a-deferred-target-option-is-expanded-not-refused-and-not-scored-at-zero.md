# ADR-0121: A Deferred-Target Option is EXPANDED — not refused, and never scored at zero

**Status.** Accepted (grilled 2026-08-04, `/grill-with-docs` on Issue #392 — six locked decisions,
two of them amendments to ADR-0100).

**Context issue.** Issue #392, filed from Issue #382's build (POC-T4/1). Blocks Issue #385 (T4/4, the
composer core). Spawned Issue #395 (the opponent role sheet).

## Context

Issue #263 § *The ordering heuristic* rules that the sequence composer prices **every** option the same
way: *"apply the single option through the seam, evaluate `state_value` on the result, rank by that
delta."* One scorer, 1 ply and n ply alike. The design rests on that being able to price every kind.

It cannot price a **retreat**, and the reason is a property of the engine rather than of the seam. A
`_RETREAT` option is the bare dict `{"type": 12}` — **5807 of 5807** offered options across the
committed parity corpus, **146 of 146** in the corrections corpus that both ADR-0072 gates replay
(`board_delta.py:565`, measured 2026-08-04). The engine spends `current.retreated` and poses the rest
as separate selects: `_DISCARD_ENERGY` (context 30) for the cost, then `_SWITCH` (context 3) for who
is promoted. So a retreat's 1-ply delta is **the allowance bit and nothing else** — a near-zero
against a leaf that scores the board, and Issue #263's own amendment says what a near-zero at ordering
time means: *"a 0 delta at ordering time means never explored, not undervalued."*

Under a plain top-k beam every retreat is therefore pruned before the follow-up select that carries
its value is ever reached — and Issue #263's own acceptance corpus is built on those lines (f32,
`dragapult_hammer_over_develop_f32.json`, whose rationale doc is
`docs/plans/turn-planner-retreat-to-item-lock-wall.md`; f35, `dp_hold_evolve_until_typed_ready_f35.json`,
which Issue #291's closeout rules *"the SAME class"*). The retired `retreat-to-wall-the-line` +30 rung
existed precisely because the flat-scored world could not otherwise reach them.

**Retreat is not alone, and the census is what turned a fix into an architecture.** `board_delta.py:604-616`
records **63** further `_PLAY` steps whose write's target *"is chosen at a follow-up select, so the
`_PLAY` option does not determine it — structurally the same case as `_RETREAT`"*: Boss's Orders ×30
(poses `_SWITCH` ctx 3), Crispin ×16 (`_TO_HAND` ctx 7), Wally's Compassion ×14 (ctx 17), Rosa's
Encouragement ×2 (ctx 22). The developer's framing at grill time generalised it past the census: *the
act of gusting away their Active matters as much as which benched body comes up; Crispin's two energy
types are outright good, but what makes them good is which body's energy needs they meet; healing is
great, but it depends on who needs it and by how much.* Cause and effect split across two engine
steps is a wide shape in this game, not four cards.

**The decisive fact is that this is NOT a coverage gap.** All four cards are `covers: "full"`
(Issue #300's Clause-Set Completeness), and `CLAUSE_SELECTORS["target"]`
(`snapshot_coverage.py:668`) already records the target **class** — `any`, `any_pokemon`, `benched`,
`stage2`, and so on. What is absent is the target **instance**, which only the board can supply. The
class had two incoherent fates for one shape: a `_PLAY` REFUSED *loudly* (Issue #263 line 50 — *"a
one-action terminal candidate flagged as a coverage gap … never silently dropped"*), while a
`_RETREAT` priced ~0.0 and was pruned *silently*. That asymmetry, not the retreat, is the defect.

## Decision

**1. Deferred-Target Expansion, in a new composer-local module — not a beam whitelist, and not a
seam change.** For an option whose engine resolution defers its target, the composer resolves the
target class against the board and emits one candidate per legal instance, each a fully synthesized
`Delta` scored by `state_value`. Issue #392 offered a structural beam-admission whitelist as the
cheaper route; it was rejected because it buys *presence* without buying *comparability* — the
retreat's 1-ply score stays a lie and the composer ranks on it, which breaks Issue #263's *"the SAME
scorer runs at 1 ply and n ply"* for one kind. Expansion dissolves the bug instead: there is no
~0-scored retreat left to admit.

`board_delta._retreat` does **not** change. It stays allowance-only and parity-honest, because
modelling a swap the engine did not perform diverges from the recorded native trace on the very next
frame and the trace is the reference (`apply_option.py`'s header, ADR-0098). The expander is a
**planning** model living beside the seam, never a claim about how the engine steps. The seam's
MAIN-menu gate (`board_delta.transition` refuses `context != CONTEXT_MAIN`, measured at 14 580 of
14 581 modelled steps) is what makes this a separate module rather than a widening.

**2. Expansion is data-driven off the compendium's target vocabulary, never per-card.** The class
resolver reads `CLAUSE_SELECTORS["target"]` and its neighbours (`restriction`, `zone`, `source`); a
hand-written expander per card hardcodes what is already data.

**3. A cheap Target Ranker prefilters; the leaf decides.** Target spaces are products, not lists —
Crispin is (which type to hand × which type to attach × which of ~6 recipients), ~36 candidates for
one card, ≈230 ms at the corpus P95 6.4 ms per `state_value` call against a ~79 ms per-decision lower
bound. So a `TARGET_RANKERS` registry keyed by clause kind orders the class with closed-form math and
the composer expands only the top-*m* through `state_value`. This is exactly the role Issue #263
§ *Consequence* sanctions for the retiring deciders — *"optionally as pruning approximations"*, never
an independent source of truth. A kind with no registered ranker falls back to expand-all under a
declared cap. `m` and the cap are sized from § *Beam-quality package* item 3's margin telemetry, not
guessed.

Two rankers, because the sides are not symmetric. **Our-side** targets (promotion, heal, `accel`
recipient) rank on `card_worth.role_value` + `needs.turns_to_ready` — role-keyed and general, so
ADR-0034's fold policy is satisfied and no deck name reaches `src/common/`. **Their-side** targets
(gust) cannot use `role_value` at all: `planner._role_value` sources roles from our own deck, and
ADR-0101 measured that **59.4%** of the opponent's representative build therefore prices 0 — *"exactly
their attackers and wincons."* They rank on `pilot._opponent_target_rows`' `value`
(`needs.opponent_target_value(prize_advance=, survival_shift=, phase=)`), which is prize + KO-clock
math with no role notion in it. **That shortfall is recorded, not accepted silently: Issue #395.**

**4. Parent-slot beam accounting — an expanded family holds ONE beam slot, taken by its best child.**
Expansion is an evaluation-time fan-out, not a candidate-generation fan-out. The composer scores every
instance, takes `argmax`, and emits one candidate carrying `(parent_option, chosen_target, score)`.
Beam width `k` keeps its pre-expansion meaning, so § *Beam-quality package*'s epsilon band and margin
telemetry keep meaning what Issue #263 says they mean and `k` needs no re-derivation. Flat competition
was rejected for silently redefining `k` (a Crispin would need `k` ≥ 40 before an unrelated play
survives); a per-family quota `q` was rejected for introducing a second width parameter that the
required telemetry has no notion of. The accepted loss — the *second*-best target is unreachable at
this node — is bounded by decision 6's replan rather than silent.

**5. The Energy-discard leg is EXPANDED; ADR-0100's `build_after` is demoted from answer to ranker.**
*(Amends ADR-0100.)* `docs/rulebook.txt` L142 — *"you must discard 1 Energy from your Active Pokémon
for each [symbol] listed in its Retreat Cost"* — imposes no type restriction, and L143 keeps the
retreating body's remaining attachments as it hits the Bench. So a retreat has a **second** deferred
dimension, and `RetreatSide.build_after` already resolves it by *"the greedy cheapest-to-lose typed
choice"*. That criterion asks which Energy hurts **A's own** line payoff attack least — chosen when
A's future was not being searched, and blind to which type another line is starving for or what A
must pay when it returns. The greedy set becomes the *ranker* for that dimension, so expansion still
leads with it and simply does not stop there. The leg collapses to one candidate whenever attached ==
cost or the Retreat Cost is 0, so the multiplication is conditional. **A corpus-ruled decision is
being demoted on a design argument, which is how rulings die quietly — this is recorded as an ADR-0100
amendment deliberately, not left implicit.**

**6. One evaluator at both sites: the follow-up select REPLANS through the same expansion basis.**
*(Amends ADR-0100.)* When the engine actually poses the `_SWITCH` / `_TO_HAND`, the composer
re-decides using the identical Target Ranker + `state_value` machinery that chose the play, over the
real board. This satisfies Issue #263 § *Every fresh decision point is a composer decision* literally
while preserving ADR-0100 §9's invariant — *"that the two sites run the same evaluator is what makes
the old divergence — retreat BECAUSE Cinderace is worth promoting, then promote Budew — structurally
impossible."* ADR-0100's three call sites collapse to one evaluator at a different layer than that ADR
describes.

**The honest reason, because the obvious one is false.** The developer asked directly what could
possibly change between choosing to retreat and being asked whom to promote. For a retreat: **nothing**.
The `_DISCARD_ENERGY` touches only A, and every term of `promote_value(B)` reads B — the same fact
ADR-0100 §9 states from the other side (*"CONSTANT across destinations"*); nothing is revealed by
discarding one's own attached Energy; the opponent cannot act during our turn. A commitment would
provably agree. The argument for replanning is **not** that the board moves — it is that **Crispin
already breaks the commitment today**: *"Search your deck for up to 2 Basic Energy cards of different
types, **reveal them**"* is an information-revealing play, which § *Commutative-block collapse* names
a block boundary, and the recipient was chosen before the search resolved. Census: retreat, Boss's
Orders, Wally's Compassion and Rosa's Encouragement reveal nothing (Rosa's attaches from the public
discard); Crispin reveals. Commitment makes coherence a **standing per-member proof obligation** over
a data-driven vocabulary that will grow, and its failure mode is a legal, plausible, wrong pick with
no error anywhere. Replanning makes coherence **structural**, and for the four silent members it is
provably a no-op costing one evaluation.

**7. A resolution-parity lane verifies the synthesis.** The expander predicts a board the engine
reaches only after two or three further selects — outside the existing parity lane's reach, and an
unverified synthesis feeding `state_value` is exactly what Issue #382's lane exists to prevent. A
sibling of `tools/train/apply_parity.py` walks each Deferred-Target Option forward past its follow-up
selects to the first settled frame, reads the target the trace records as **taken**, and asserts the
expander's `Delta` for that instance equals the recorded observation on the zones it writes.
Population: the **2254** retreat steps Issue #382's lane already exercises, plus the census's **63**
`_PLAY` steps. Only the taken branch is verifiable — the counterfactuals are unobserved by
construction — but a systematic enumeration or arithmetic error cannot survive 2254 taken branches.
It gates in CI beside the existing lane. The expander is additionally *composed from* the seam's
already-parity-verified copy-on-write primitives, so the arithmetic inherits that guarantee and the
lane is left to check the composition, which is where the risk actually is. Synthetic-fixture testing
alone was rejected: a hand-built expectation encodes the author's model of the engine, which is the
same model the expander encodes.

**This decision is what makes decision 6 checkable rather than merely asserted.** Coherence between
the MAIN-site synthesized board and the select-site real board is *implied* by the lane — one
evaluator over two boards the lane proves equal cannot disagree unless the lane is red. Divergence
becomes a CI condition instead of a runtime surprise.

## Consequences

- Issue #385's composer core is written against expansion, parent-slot accounting and a replanning
  follow-up. Its spec must carry decisions 1, 4 and 6 verbatim.
- ADR-0100 gains two amendments (decisions 5 and 6). Neither is a bug fix; both demote parts of a
  corpus-ruled equation to new roles, and both must be recorded on that ADR when the build lands.
- `promote_retreat_value.promote_value(B)` gets a principled home — the our-side promotion ranker —
  instead of being orphaned when the composer retires its decider role. `preservation(A)` and
  `retreat_cost(A)` retire as deciders outright: under parent-slot accounting the leaf already reads
  the discarded Energy and A's new bench position, so adding them would double-pay.
- The gust ranker ships structurally blind to 59.4% of the opponent's build. Named, measured and
  owned by Issue #395; it is a stated ceiling, not an oversight.
- A second CI lane and its trace-walking logic are new surface. The trace-walk — finding each
  maneuver's settled frame — is the part with no prior art and is where the bugs will be.
- `_RETREAT` stops being special. It becomes the first member of a named class, and the next card the
  compendium learns with a deferred target is priced without new code.
- **Citation correction.** Issue #392 and Issue #263 both cite `promote_retreat_value` as *ADR-0073*.
  ADR-0073 is `fetch-reach-and-fetch-deadness-are-opposite-readings-of-one-clause`. The correct
  reference throughout is **ADR-0100**.

## Build record (2026-08-05) — what the implementation measured, and what it changed about the ruling

The seven decisions above shipped as written. Five things the grill could not know were measured
during the build, and each is recorded here because each is a fact about the decision rather than a
detail of the code.

### 1. The near-zero is EXACTLY zero

Decision 1 rests on a retreat's 1-ply delta being *"a near-zero against a leaf that scores the
board"*. Measured through built, engine-backed Pilots on Issue #263's own two acceptance frames
(`tools/train/probes/choice_beam.py`), it is **exactly 0.0** on both — `board_delta._retreat` writes
`allowance_retreat_used` alone, and no `state_value` family reads the retreat allowance. Expanded, the
same option scores the max over its classes: **f32 +0.00075 prizes over 2 classes**, **f35 +0.00186
over 4**. The defect is therefore sharper than stated, not softer.

### 2. The class identity needs TWO collapses, because `option_fingerprint` provably cannot do one

Decision 1 said the classes are collapsed by ADR-0091's fingerprint on the post-choice observation.
That is right for the promotion dimension and **impossible for the Energy-discard one**:
`option_fingerprint` compares a body's card lists by value *including their order*, so discarding
entries 0 and 1 versus 0 and 6 of eight attached Energy leaves the same multiset in a different order
and fingerprints differently. Measured at `boomer_9001` f39 (Mega Zygarde ex, eight Energy, Retreat
Cost 2). No canonical removal repairs it either — the engine's own pick among identical cards is
arbitrary and lands in that same order, so a canonicalised synthesis would disagree with the recorded
board.

So the two collapses coexist and answer different questions: the space collapses **identical Energy
CARD ids** (*is this the same CHOICE?*, in the option's coordinates) and the fingerprint collapses
**identical post-choice boards** (*is this the same BOARD?*, ADR-0091's declared identity, which is
what makes two indistinguishable benched Riolu one class). Neither subsumes the other.

### 3. The probability denominator is the FULL enumeration

Decision 1's phrasing (*"every `OutcomeClass.probability` is `1/len(classes)`"*) is ambiguous between
the kept classes and the enumerated ones, and only one reading satisfies the stated purpose. It is the
**full** enumeration: normalising over the survivors would make `total_probability` read 1.0 while
classes were being dropped, which is the "no silent caps" failure the same sentence forbids.

### 4. Decision 7's lane is green, and its two refusal families are INHERITED

**377 traces / 37 983 frames / 2254 choice steps: 2200 verified, 0 diverged, 0 unenumerated**, 14
refused, 40 unsettled (no same-orientation MAIN frame follows — 17 traces end mid-resolution, 23 pass
the turn there). The 14 refusals are 12 untagged Special Energy (`board_delta.units_for_cards` cannot
derive their provision — the shared primitive's own fail-closed refusal) and 2 Ethan's Magcargo, whose
*"If this Pokémon has no Energy attached, it has no Retreat Cost"* is a **fourth free-retreat grant
shape nothing parses** (recorded as an ADR-0100 amendment note; `Pilot._effective_retreat_cost` has the
same gap and over-charges the pivot).

One comparison is relaxed and counted: `my_discard_contents` as a multiset. The engine appends
simultaneously-discarded Energy in the order the ctx-30 selects were **answered**, which is a property
of the policy that recorded the trace rather than of the rules — `docs/rulebook.txt` L142 assigns
none, and every committed trace is our own self-play, so inferring it would be fitting to ourselves.
Measured: **10 of 2254**, all in that zone, all identical multisets, every one a transposed pair.

### 5. The f32/f35 margin telemetry: f35 discharges it, f32 cannot, and `k` is not derived

The criterion asks for rank at 1-ply ordering relative to `k` **and** score margin to the k-th
candidate. The rank half is **1 on both frames, in both modes**, so the line survives any `k >= 1`.

The margin half needed a correction the first pass got wrong. `k` is not derived anywhere — neither
Issue #263 nor this issue fixes a beam width — so quoting one figure at an undefended `k` reports the
caller's choice as a property of the frame. `tools/train/probes/choice_beam.py` therefore reports the
margin as a **curve over every width the menu supports**, and the two frames then split:

* **f35 DISCHARGES the criterion.** Two scored candidates, so `k=2` is real: margin to the 2nd
  candidate **0.001125 unexpanded → 0.002985 expanded**, a **2.65x** widening of the line's lead over
  its rival. That is exactly the item-3 demonstration asked for.
* **f32 cannot, and the reason is COVERAGE not ordering.** Its menu scores one candidate (3 refused,
  1 terminal), so no `k >= 2` margin exists at any width. A refusal is not a pruned option —
  `must_expand` makes it the always-expand path — so this is a fact about how much of a Trainer-heavy
  menu the apply seam can price at this commit, and it becomes computable when that coverage grows
  rather than when Issue #385's composer lands.

**The first pass asserted the margin was undefined on BOTH frames, at a hardcoded `k=3`.** That was a
narrowing dressed as a finding: `/code-review`'s Spec axis recomputed it at `k=2` with this build's
own tool and found f35's margin perfectly well defined. Recorded here because the failure mode is the
one a self-filed spec is most prone to — the implementer choosing the parameter that makes their own
criterion unmeasurable.

### Groundwork this build incurred, flagged rather than hidden

* **`common.retreat_cost` (new)** — ADR-0100 §8's grant-aware cost extracted from `Pilot`, because the
  size of a retreat's Energy-discard space *is* that number and a choice node computing it for itself
  would be a second reader of a fact ADR-0070 already drew the *"one function owns the fact"* lesson
  for. The Pilot's three methods are one-line delegations; the arithmetic is unchanged. It does **not**
  discharge the `_can_retreat` / `planner` divergence Issue #149 owns.
* **`board_delta.clear_conditions` / `units_for_cards` promoted to public** — the same POC-T4/2 move
  that made `fork` / `fork_player` / `take_from_hand` / `card_clauses` public, for the same reason.
* **`role_span()` derives from `matchup_plan.ROLE_REGISTRY`** — so decision 3's span is read off the
  sheet rather than transcribed. **The rebase proved the point**: Issue #395 merged to `main` mid-build
  and did exactly what a transcribed constant could not survive — moved the table from a private
  `_ROLE_PRIORITY` to a public closed registry, added `attacker` 50 and `enabler` 40, gated `avoid` on
  prize value. The derivation absorbed it with no edit to the arithmetic and no change to the D7
  guarantee, which is stated over `max(abs(·))` rather than over any row. (This build had added its own
  `role_registry()` accessor for the private table; Issue #395's public `ROLE_REGISTRY` supersedes it,
  and it was dropped at the rebase rather than kept as a second name for one thing.)
* **`.github/filters.yml`** — the apply-seam sources now trigger `tests/parity`. This closed a real
  gap rather than widening the filter: neither seam-parity lane was reachable from a source change on
  a PR, so `board_delta.py` could be rewritten without replaying a trace.
* **`apply_parity.load` / `chosen_option` promoted to public** — the same second-consumer rule, applied
  in `tools/` where the first pass had applied it only in `src/`.

### Corrections the review forced, recorded because they are the self-filed spec's own failure modes

* **Decision 2 was not implemented on the first pass.** It rules the class resolver *"data-driven off
  the compendium's target vocabulary, never per-card"*, and `_gust_space` hardcoded
  ``if target != "any": refuse`` — the per-card branch D2 forbids, dressed as fail-closed. It now
  reads `CLAUSE_SELECTORS["target"]` and partitions all **24** declared values into 14 board
  predicates, 10 category errors (a card class is not a body in play) and 0 scoped gaps, with
  vocabulary drift refusing separately in both the value and the key dimension. The three are three
  different sentences because they are three different pieces of work.
* **The margin criterion was narrowed rather than measured** — see section 5.

Both were caught by `/code-review`'s Spec axis, briefed that this spec was self-filed and told to
grade the spec as well as the diff. Neither would have been caught by a scope-coverage reading: the
first looked implemented, and the second looked like an honest negative result.

### What Issue #395's merge changed about this ADR, recorded at the rebase

`role_priority` was a **forward dependency** for the whole of decision 3's their-side combination when
this was built: `pilot._opponent_target_rows` did not carry the field, and `gust_rank_key` read it with
a `0.0` default so the key could be written and graded before it existed. **Issue #395 D7 merged to
`main` on 2026-08-05, mid-build.** The field is now live and this issue is its first composer consumer,
as its own § *Prior art* predicted.

The default is KEPT rather than removed, and that is a ruling rather than an oversight: `0.0` is
exactly what an unroled body contributes on a live row, so ONE key orders a menu whose rows carry the
field and a menu whose rows predate it, identically. `tests/strategy/test_deferred_target_rank.py` now
also checks the field NAME against the shipped producer, which is the half that could not be asserted
before the merge — every other test in that file builds its own rows, and a key reading
`row["priority"]` would have passed all of them while ordering nothing on a live menu.

### The composer-beam half of the f32/f35 criterion has an owner

PR #399 (Issues #385/#386, open at this writing) builds `composer.Frame.margin_for(index)` and cites
this issue's criterion verbatim as its reason — *"a claim about the option the HUMAN ruled, which is
the one a beam would prune. Measuring the composer's own pick instead would answer a different
question and would pass by construction whenever the composer picked at all."* That is the right home
for the margin at a REAL beam, and it is not this issue's to build: no beam exists here.

`tools/train/probes/choice_beam.py` therefore measures the half that does exist — the margin in the
**1-ply ordering** — and reports it as a curve over every width the menu supports rather than at one
undefended `k`. On that instrument f35 discharges the criterion (margin to the 2nd candidate
**0.001125 → 0.002985**, a 2.65x widening) and f32 cannot, because its menu scores a single candidate
at any width. The two instruments answer different questions and neither substitutes for the other.

### What Issue #394's merge changed about this ADR, recorded at the second rebase

Issue #394's branch carried **Issue #408**, which wrote `CardStat.stage` — a field that had been
declared and never populated. That falsified a claim this build had measured and written down:

> *"the shipped provider fills `evolvesFrom`, `stage2`, `ex`, `megaEx` and `tera`, and leaves `stage`
> **None**, so a predicate keyed on `stage` would silently match nothing."*

True when written, false on the rebased base. Two consequences, both acted on rather than noted:

1. **Decision 2's stage predicates now read the canonical field.** `provider.stage_from_card` is
   *"the ONE derivation (Issue #408)"* and rules out precisely what this build had done: *"Not derived
   from `evolvesFrom`: that is exact on today's pool but it is a second READING — inferring a printed
   stage from an evolution name — where the booleans are the engine's answer."* Switched on a
   measurement rather than on the quote: the two readings agreed on **every** Pokémon in the shipped
   pool, so it is a provenance fix and not a behaviour change. The predicates fail CLOSED on a missing
   `stage`, which narrows a target space rather than widening it.
2. **The grant this issue extracted was woken by the same commit.** `common.retreat_cost`'s `"basic"`
   predicate — moved out of `Pilot._retreat_free_granted` by this build — compared against `None` for
   every card until Issue #408. Verified through the extracted module on the rebased base: a Basic at
   printed Retreat Cost 2 reads **0** with Latias ex in play and **2** without, so the woken predicate
   survives the move intact. That method's docstring note about the double-deadness travelled with the
   code rather than being deleted alongside it.

Neither changed the resolution-parity lane: **2254 steps, 2200 verified, 0 diverged, 0 unenumerated**,
identical to the pre-rebase run.
