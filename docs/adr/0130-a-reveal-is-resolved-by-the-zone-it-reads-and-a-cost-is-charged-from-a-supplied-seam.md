# ADR-0130 - A reveal is resolved by the ZONE it reads, and a cost is charged from a seam the caller supplies

**Status:** Accepted (Issue #394, 2026-08-06); BUILT. Widens `common/board_expectation.py` (Issue
#383) and `common/board_choice.py` (Issue #392, ADR-0121) rather than rebuilding either. Coverage of
the apply seam's refused `_PLAY` steps goes **81 → 244 of 663 (12.2% → 36.8%)**, re-measured at every
commit and never projected. Consumes ADR-0029's prize split (generalised) and ADR-0032's compendium;
does **not** amend ADR-0091's fingerprint or ADR-0103's tie-break. Everything here is inert at
runtime except one refactor, so `score_diff` and both ADR-0072 gates are NULL CONTROLS and are
reported as such.

## Context

The composer (`common/composer.py`, dark) ranks a turn by 1-ply differencing:
`delta = state_value(after) − state_value(before)`. A card whose board it cannot synthesize is
`REFUSED`, and `composer.selection_key`'s first leg is `bool(candidate.coverage_gap)` — so a refused
option sorts behind **every** scored one regardless of merit. Issue #400 measures the cost: of 92
missed human-ruled `_PLAY` frames, **76 are seam refusals**.

`board_expectation` enumerated 81 of 663 refused steps. The rest sat in ten buckets, and this issue
is what four of them turned out to be.

## Decision 1 — a reveal belongs to the node that owns its ZONE, and `fetch` is in neither vocabulary

The largest single finding, and it is a **routing** defect rather than a missing capability.

`board_expectation` refuses a discard search in terms that name its own remedy:

> *"a `discard`-zone search carries NO chance — that zone is visible — so it is a pure CHOICE node,
> not an expectation"*

That module shipped at Issue #392. Its registry had no `fetch` entry, so **46 corpus steps** sat in a
bucket whose own sentence said where they belonged — including Night Stretcher, 8 copies across 4 of
the 5 shipped decks.

The split is by zone, not by clause kind:

| | zone | what is uncertain | node |
|---|---|---|---|
| deck search | hidden | *is the target even in there?* | `board_expectation` — a distribution from `deck_odds` |
| discard search | face-up | *nothing* — only which card I take | `board_choice` — a pure choice |

So `fetch` is deliberately **not** added to `CHOICE_CLAUSES`: the clause kind is identical on both
sides and only the zone tells them apart, so folding the kind in would claim both. `choice_key` asks
the zone question first and returns a new `FETCH_DISCARD` key; a deck fetch still falls through to
the existing *"no clause with a deferred target"* refusal. `CHOICE_KEYS` is the closure over all
three families, in one store rather than recomputed per reader.

**A discard class carries no `deck_odds` call at all.** The zone is face-up, so every class is
available with certainty and the probability is the choice node's uniform placeholder. That is the
whole reason this is a second node rather than a flag on the first.

**The census was under-reporting by construction** and is corrected here: it only ever asked the
chance node, so every visible-zone search was invisible to the instrument measuring coverage. It now
asks both and reports the split.

## Decision 2 — the multi-leg RELATION is already in the data, and two cards had it backwards

`_sole_clause` refused any card with more than one revealing clause and *guessed* the relation in its
own refusal — *"printed as a CONJUNCTION … nothing in the clause vocabulary distinguishes AND from
OR"*. Both halves are false.

`CLAUSE_PARAMETERS["choice"]` declares *"the clause is one alternative of a choose-one card"*, and
the discriminator is that flag plus `amount`:

```
every leg `choice` + amounts EQUAL   -> UNION, shared cap (absent => 1)
every leg `choice` + amounts DIFFER  -> EXCLUSIVE either-or -> refuse
no leg `choice`    + >= 2 legs       -> CONJUNCTION, one card per leg
some legs `choice`, some not         -> half-declared       -> refuse
```

Cross-checked card-for-card against the engine, which draws the same three distinctions with three
structurally different ops — one op over a union filter (`anyOf`, `pokemonOrBasicEnergy`);
`xDeckToHandBuckets` / `xDeckTakeSequenceAndShuffle`; `xDeckToHandEitherOr`. The mapping is 1:1 over
all 15 multi-leg cards, and **two disagreed**:

* **1097 Night Stretcher** — *"Put a Pokémon **or** a Basic Energy card…"*
* **1142 Fighting Gong** — *"…a Basic {F} Energy card **or** a Basic {F} Pokémon"*

Both are unions taking ONE card; both were declared as conjunctions, i.e. as delivering two. Between
them they carried **69 of the 98** steps that bucket held. Fixed at the authoring source
(`effect_overrides.json`) and re-stamped; behaviourally inert, because `choice` had exactly one
reader and that reader was unreachable.

**The relation reader lives in `fetch_closure`, read by BOTH nodes.** Two nodes facing the same
question with two spellings is how they come to disagree about the same card (ADR-0087).

**The audit that would have caught this did not exist**, and now does: a cross-STORE test asserting
each multi-leg card's declared relation against its engine chain op, with the no-override skips
enumerated by name. Every audit that read only the compendium agreed with itself.

## Decision 3 — an empty leg SKIPS; a reach-gated leg REFUSES; and the asymmetry is the rule

Three different things a leg can fail at, and they are not interchangeable:

* **empty on this board** — the engine skips it (`chain_overrides.json`'s provenance for 1231 Dawn:
  *"empty buckets skip with a tac bump"*). Load-bearing rather than theoretical: Dawn's leg product
  is 0 on **all 8** of its corpus steps because two of its three legs are empty on every one.
  Refusing there would refuse a card the engine resolves happily.
* **reach-gated on every board** (`supporter` / `any` — deadness-only classes) — a **card** fact, not
  a board one. Enumerating Secret Box's other three legs would model three quarters of a card while
  reporting completeness.
* **reach-gated, but the card has only ONE leg** — **not refused here.** With one leg there is no
  other leg to skip, so no partial answer can be manufactured; the card simply reaches nothing, and
  the empty-pool refusal says so precisely.

The third clause was found by measurement, not design. A first draft refused any reach-gated leg and
moved eight real cards — Pokégear 3.0, Meowth ex, Roto-Stick, Miracle Headset — off refusal reasons
that correctly describe them onto one that does not.

## Decision 4 — the cost's discard set is PASSED IN, never computed at the seam

`board_expectation` refused on the presence of a `cost` — 69 steps, 65 of them Ultra Ball, which
sits in all five shipped decks. WHICH cards are paid is a live decision `needs.cheapest_removal`
already makes at the real select. What was missing was a way to ask it from here, and measurement
says there is none:

* `cheapest_removal` is a pure function over sequences — not the blocker;
* its inputs are. `Pilot._resolve_needs` reads 16 distinct `self.X` including `self.strategy`,
  `self.deck` and five memo caches, and Roles are DECLARED, so a `StateModel` structurally cannot
  supply them;
* `StateModel.build` has two call sites in `src/`. Production passes **no** `needs=`; the planner
  passes the LEAF resolution, which is `include_general=False`, carries no pitch terms, and is pinned
  to the ROOT observation (Issue #400 Phase 2);
* `composer.py` has **no `Pilot` reachable anywhere** — its one code import is `strategy.context`, a
  pure constants module.

So `shed` becomes the fourth caller-supplied seam on `compose()`, threaded exactly like `search_api`
/ `deterministic` / `clauses_cover`, and the caller that holds a Pilot passes
`Pilot.cost_shed_indices`.

**Rejected:** pricing the cost UNPAID (over-values every Ultra Ball by the two cards it does not
charge for); reading `model.mine.needs` (wrong resolution, wrong observation); recomputing at the
seam (a second board→slots derivation beside the Pilot's, which is what `MySide.needs` exists to
prevent). Also rejected, with evidence: reaching for `keep_v2`, which ADR-0122 measured **worse** and
reverted.

**The cost is applied BEFORE the search** — the engine's own order (`play: [costHandTrash,
effectDeckToHandAndShuffle]`). Observable rather than cosmetic: charging after would let a delivered
card be discarded to pay for the search that delivered it.

**An unpayable cost refuses as an ILLEGAL play, not a free one.** The engine's gate is `handOthers`.
Pricing it as merely cheap puts an unreal option on the menu with a positive delta, which is worse
than the silent zero the seam exists to prevent.

**The count is DATA.** `snapshot_coverage.COST_CARDS` replaces a hardcoded `2` that was right for
Ultra Ball and silently wrong for Secret Box (3) and Canari (1). Two values are `None` — the seam
refuses — for two different reasons that must not be generalised from one another: `discard_hand`'s
count is the hand's size and not a constant (a SCOPE decision — its carriers are in no shipped deck);
`bottom_2` returns cards to the **DECK**, which moves `unseen_counts` and would invalidate the very
pool being enumerated (a correctness one).

## Decision 5 — a multi-card delivery is a MULTISET, and it needs a closed form `deck_odds` lacked

A pool is `{card id: copies}`, so taking two copies of one card is a legal, distinct outcome.
Measured: 1205 Cyrano's pool is a **single distinct card id on all four** of its corpus steps —
exactly where a subset enumerator returns one class and is wrong about what a three-card search
delivers.

That needs *P(≥ k copies still in deck)*, which `p_contains` (≥1 only) cannot answer.
`deck_odds.p_contains_at_least` is the hypergeometric CDF over the same prize split, and its summand
is not new algebra — it is the per-split PMF `planner._prize_split_hit` already builds, summed rather
than folded through a draw window. **`p_contains` DELEGATES at k=1**; two closed forms for one model
is how they drift, and the identity is asserted over the whole small grid.

Deliveries are of exactly `min(m, available)`, never fewer, and that is a ruling: *"up to 3"* permits
taking two, but for a free search into HAND taking fewer is dominated. Deliberately **not**
generalised to a Bench delivery, where each arrival hands over Prize-Path exposure and taking fewer
CAN be right — one more reason that destination stays Issue #410's.

The synthesized serial gains an ordinal (`-(card_id * 100 + ordinal)`): `-card_id` alone collides the
moment one class delivers two copies of a card.

## Decision 6 — the gate ORDER is part of the answer, because a backlog row nobody can act on lies

Three declines, each landing on a gate that describes it:

* **RNG (85 steps)** — permanent; the engine has no deal-seed.
* **`dig` (61 steps)** — a genuinely different probability model, *P(target in the top N)* rather
  than *P(target still in deck)*. Deferred with a named follow-up rather than buried; Pokégear 3.0 is
  live in a shipped deck, so this is real work.
* **a reveal declared on a BODY (11 steps)** — Lunatone's and Fezandipiti ex's clauses are
  **Abilities**, and an Ability does not fire because the body was PLAYED. Modelling a reveal there
  would be flatly **WRONG**, not under-scoped. Only an `on_bench_play` trigger rides the `_PLAY`.

The clause gates now run **before** the card-type floor. Measured landing: **11** at the new ability
gate, **12** (Meowth ex) at the reach predicate, **0** at the floor — that bucket is gone. The floor's
sentence is about where the SOURCE card lands, which is a fact about the play rather than about the
reveal; it survives as a structural backstop and catches nothing real.

## What this does NOT do

* **No rung, no Hypothesis, no weight, no tuned constant.** This supplies boards to difference.
  The one ordering input added (`board_choice`'s discard rank, `MySide.role_worth`) is
  **ordering-only** — it enters no score, adds to no delta, and decides only which classes survive
  `BRANCH_CAP`; a test asserts every surviving class keeps the same uniform probability.
* **No engine shuffle**; `NONDETERMINISTIC_CLAUSES` still refuses.
* **Does not arm anything.** `board_expectation`, `board_choice`, `apply_option` and `composer` are
  all dark. `runtime.PROFILE["deferred_target_expansion"]` is unchanged.
* **Does not build the Bench delivery** (58 `dest` steps) — Issue #410 owns it, and
  `multiset_classes` is what unblocks its R8/R9.

## Consequences

**Coverage, re-measured per commit** (`python tools/train/expectation_census.py`):

| after | enumerated / 663 | |
|---|---:|---|
| baseline | 81 (12.2%) | |
| D2/D3 relation | 126 (19.0%) | +45 — Fighting Gong 27, Hilda 10, Dawn 8 |
| D5 multiset | 130 (19.6%) | +4 — Cyrano |
| D1 discard node | 176 (26.5%) | +46 — Night Stretcher 42, Max Rod 2, Energy Retrieval 2 |
| D4 cost seam | **244 (36.8%)** | +68 — Ultra Ball 64, Canari 4 |

**`BRANCH_CAP` now BINDS** — classes reach 12 and **one** corpus step truncates, where the header
previously recorded zero. That is the no-silent-caps contract working, not a regression: truncation
is visible in `Expectation.truncated` **and** in `total_probability` falling short by the dropped
mass. Recorded because the previous header asserted the cap never binds, and that is no longer true.

**Against the population that actually matters**, stated so the corpus-step table is not read as an
agreement forecast: of Issue #400's 76 seam refusals on human-ruled `_PLAY` frames, this retires
**13** — Hilda 6, Night Stretcher 4, Ultra Ball 3. Poffin's 8 are the Bench half; 30 are RNG; 12 were
gust/heal/accel; Salvatore's 5 are `dest: in_play`; Pokégear's 8 are the `dig` decline.

### `composer_lab`, before and after — measured against the rebased base, and a wave-packet ruling

`python tools/train/composer_lab.py`, this branch against `origin/main` @ `8196e75d` (the base this
issue actually merges onto — `main` gained Issue #400 Phase 1, ADR-0129, between this issue's build
and its rebase, which is why the comparison below supersedes an earlier, staler one taken against
`643c4155`):

| | main | this | |
|---|---:|---:|---|
| frames with a coverage gap | 255 | **241** | −14 |
| expectation nodes | 758 | **1107** | +349 |
| composer == chosen | 58 | **60** | +2 |
| **composer == ruled** | **92 / 270** | **88 / 270** | **−4** |
| truncated by the branch cap | 4 | 4 | 0 |

**Agreement moves, and it moves down.** Phase 1 gives a reveal line a real terminal EV to compete on
— the summand this ADR's earlier draft named as missing — and once it exists, the extra coverage
this issue supplies lets a reveal line **win** decisions it used to lose by construction
(`coverage_gap` sorting it last, whatever its score). Reported as measured rather than smoothed into
the flat result an earlier draft of this ADR recorded against the pre-Phase-1 base.

**Per ADR-0092: a flip off a human ruling is never auto-conformed. Every one of the 9 was taken to
the developer, individually, before this issue shipped.** The raw −4 undersells what the ruling
found — the mechanical `composer == ruled` string match cannot distinguish "wrong" from "a
DIFFERENT correct answer than the one recorded," and four of the nine turned out to be the latter:

| frame | ruled pick | composer's new pick | ruling |
|---|---|---|---|
| `82228640-7` | Attach Energy → Staryu | Play Ultra Ball | **composer wrong** — Ultra Ball is saved to find Mega Starmie ex, already in hand; discarding Hilda for it forfeits an energy AND a Pokémon for a coin-flip Pokémon alone |
| `82752045-18` | Attack with Turbo Flare | Play Hilda | **composer wrong** — "playing Hilda here did not help us at all" |
| `83967841-17` | End turn | Play Ultra Ball | **composer wrong** — still setting up, nothing needs evolving; save Ultra Ball for next turn |
| `85163634-17` | Attack with Turbo Flare | Play Ultra Ball | **composer wrong** — fetching a turn early risks a Judge/Harlequin disruption for no gain; no cost to waiting |
| `82756021-101` | Attack with Jetting Blow | Play Hilda | **architectural, out of scope** — the ruled line is a lethal read (*"just attack for the win"*); a 1-ply composer with no threat-planner access cannot see it, this issue or any other reveal-vocabulary issue included |
| `82228640-48` | Attach Energy → Mega Starmie ex | Play Hilda | **NOT wrong** — the final Staryu copy is prized, so Hilda's value shifts to the energy fetch plus deck-thin for next turn; both lines are fine |
| `82228640-53` | Attach Energy → Mega Starmie ex | Play Hilda | **NOT wrong** — no other Supporter that turn, so Hilda is "just" deck-thinning; a weak premise, but not a wrong one |
| `82748422-26` | Attach Energy → Mega Starmie ex | Play Hilda | **NOT wrong** — fetching energy here is fine |
| `85058574-88` | Attack with Aura Jab | Play Ultra Ball | **NOT wrong** — discard an Energy + Solrock, fetch Mega Lucario ex is a good move |

**4 genuine misses, 1 out-of-scope architectural gap, 4 that were never really regressions** — the
binary metric just has no way to record "also correct." None of the 4 genuine misses trace to a
defect in THIS issue's code: each is the composer's 1-ply valuation making a call this issue's
widening merely gave it the OPPORTUNITY to make, on a question (multi-turn resource timing, whether
a fetch helps *this* board) that Issue #386/#387's ranking work owns, not this one's coverage work.
Recorded as an owed ruling rather than silently absorbed — the four are real, named, and left for the
ranking issues to close, exactly as ADR-0122 is precedent for taking a measured miss seriously rather
than waving it into a footnote.

**Evidence, and what could not be evidence.** Every module touched except one is dark, so
`score_diff` and both ADR-0072 gates are NULL CONTROLS here and are reported as such rather than
quietly satisfied (PR #411's lesson). What did bite: the apply-seam parity lane (1361 tests green),
the census re-run at every step, the composer_lab wave-packet ruling above, and — for the single live
commit, the `_shed_signals` refactor — `score_diff` **0 divergent over 375 frames**, a MEANINGFUL
null because its only mover (`cost_discard` is carried by exactly one card, Ultra Ball) is present in
all five shipped decks.

**Three fixture defects surfaced, each caught by an existing guard rather than by the author**, and
they are recorded because each is the same failure mode: `pilot_helpers.fetch_effects` never mirrored
`cost_discard`, so every fixture's Ultra Ball was free while the real card is not; `test_gamble`
pinned the pre-correction Fighting Gong clause as a whole dict; and two new `CardStat` rows were
written from memory (Lunatone hp 90, Meowth ex hp 200) and rejected against the CSV by
`test_cardstat_fixture_facts.py` (110/{F} and 170/{C}).

**Spawned:** the `dig` family (61 steps) and Issue #410's now-unblocked Bench half.

**Repaired in passing, and flagged rather than folded in silently:** `tools/train/expectation_census.py`
had not run since PR #407 renamed `apply_parity._load`/`_chosen_option` — the instrument this issue's
acceptance depends on was broken on `main`, and it also lacked the `sys.path` bootstrap every sibling
CLI has, so its own documented command could never work. `board_choice.target_space` carried a latent
`NameError` on its empty-space refusal (`key` unbound). `docs/plans/apply-seam-coverage.md` was stale
since PR #436 deleted a deck.
