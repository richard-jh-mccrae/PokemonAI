# ADR-0091 — Indistinguishable options are ONE decision, to the graders AND to the leaf

**Status:** Accepted (grilled 2026-07-31, `/grill-with-docs` on Issue #247 — nine locked decisions).
**Build = Issue #247.**
**Closes the deferral in [ADR-0088](0088-a-voided-ruling-leaves-the-agree-rate-and-the-gate.md)
decision 6** (which handled the `transposition` *instance* and named the *class* as this issue), and
**amends [ADR-0085](0085-snipe-is-a-categorical-relevance-instrument-and-the-fold-collapses-the-additive-stack.md)
Amendment J** (`satisfies_human`, until now the untouched predicate both `main` gates key on).
Extends **[ADR-0031](0031-the-turn-planner.md)**'s develop rollout with a soundness correction. Does
**not** supersede anything.

**Context issues:** Issue #247 (this grill), Issue #239 / ADR-0088 (the Voided Ruling and the
`transposition` disposition this retires the last entry of), Issue #241 / ADR-0087 (the Corpus
Reader, whose one-walk discipline the oracle is threaded through), Issue #178 (the reproducibility
heisenbug whose all-or-nothing rule decision 8 narrows), ADR-0072 (the two gates whose baselines this
re-captures).

## Context

`gates.satisfies_human` grades the agent by `correct ⊆ chosen` over **option indices**. It reads no
board. When a select menu offers two options that name genuinely interchangeable cards — two
identical undamaged Riolu on the bench, the same energy card to either of two identical basics — the
human's ruling names one index and the agent may pick the other. Same decision, graded as a
disagreement.

ADR-0088 handled the one known instance by inventing the `transposition` disposition, which **voids**
the frame out of the denominator: it stops grading in either direction. That ADR named the real fix
here and stated its precondition — *"it needs a sound 'these two options are indistinguishable'
oracle read off the frame's `obs` — a board-reading problem, not a corpus-record one."*

### Measured at the grill (2026-07-31, not recalled — 372 keyed Corrections)

```
frames carrying >=1 equivalence class:              101 / 372
Decision Gate verdicts that move:                     2
  81905522|0|decision|75  (ctx 15)  voided -> AGREE   the ADR-0088 instance
  86091728|0|decision|19  (ctx  0)  DISAGREE -> AGREE a SECOND instance, never ruled
Decision Gate agree rate:              248/346  ->  250/347
leaf frames carrying >=1 class:                      81 / 268 scorable
leaf CLASS ASYMMETRY (one class, several values):     5
```

### The oracle found a defect nobody was looking for

Scoring each class member through the leaf showed **five classes whose members score differently**.
On `81903490|0|decision|49` the bench holds three byte-identical Riolu (id 1030, 70/70, no energy, no
tools, equal `appearThisTurn`) and attaching the same energy card scores:

```
option 2 -> bench 0:  1167.0     end active = Mega Lucario ex (330hp), prizes 6->5, coins False
option 3 -> bench 1:    95.4     end active = Riolu (70hp),            prizes 6->6, coins True
option 4 -> bench 2:    95.4
```

Reproducible — same pilot twice, fresh pilot, identical. Not RNG, not state leakage, and **not a
positional rung**: `_engine_leaf_value`'s within-turn rollout is greedy and index-order dependent, so
it reaches a KO continuation from bench 0 and misses the isomorphic one from bench 1. Because the
bodies are interchangeable, **any line reachable after attaching to bench 0 is reachable after
attaching to bench 1** — the boards are isomorphic. The gap is search incompleteness presenting as a
value difference, and the Discrimination Gate is structurally blind to it: `correct_is_top` is
tie-lenient, so a frame where the leaf ranks one of two identical options 12× above the other still
reads `OK`.

## Decisions

**1. An option's identity is a FULL-OPTION fingerprint over every zone the snapshot reveals.**
`(type, seat, [(area, card-state-minus-serial) for each zone reference the option carries])`,
resolving ACTIVE(4)/BENCH(5) against `players[seat].active|bench`, HAND(2) against `.hand`,
DISCARD(3) against `.discard`, LOOKING(12) against `current.looking`. Any reference that fails to
resolve — DECK(1) is face-down, 262 options — makes the whole option unfingerprintable, so it joins
no class. **Blind ⇒ conservative, structurally**, rather than conservative by a hand-maintained list.

Rejected — **key on the target slot (`option_slot`)**: an option can name TWO cards at once (a `type
8` attach carries `area/index` = the hand card AND `inPlayArea/inPlayIndex` = the recipient body), and
a body-only fingerprint produced **6 false equivalences** — different energies onto one body reading
as one decision. Measured, not argued. `option_slot` also stays untouched for its own sake: it is
*"which one identity does this option target"*, load-bearing for three sweeps and every committed
Axis Claim, and re-pointing it would silently re-base all of them (`gates.py:138`).

Rejected — **board bodies only**: cannot resolve an attach at all, so it fixes the ctx-15 instance and
misses the ctx-0 one. That is the instance, not the class.

**2. The equivalence is a property of the CORPUS, read once and threaded — never of a capture.**
`satisfies_human(chosen, correct, *, equiv=None)`; `equiv` defaults to `None` and reproduces today's
behaviour byte-for-byte, so the three decider sweeps and all eleven existing tests need no edit.
`decider_lab.py` builds the map from the walk it already does and threads it into `build_report`,
`decider_lab_diff` and `agree_delta` beside the existing `voided=`. Both sides of a diff are restated
against **today's** map — the identical argument `agree_delta` already makes for `voided`
(`gates.py:600`). Rows also record `"equiv"` so the artifact says WHICH options were equivalent, on
the precedent of the per-row `voided` marker.

Rejected — **read `equiv` off each capture's rows**: a baseline captured before this build has none,
so the two sides of one diff would grade under two different oracles.

Rejected — **canonicalise indices at capture and leave `satisfies_human` alone**: `ruling_moves`
compares `correct` across captures to detect a human re-ruling, and canonicalising would make a
genuine ledger edit `[3] -> [1]` invisible. The artifact would also stop recording what the human
actually wrote.

**3. The `transposition` LEDGER ENTRY is deleted; the WORD survives.**
`81905522-75` leaves `data/corrections/reviewed.json` and re-enters the graded population, where it
now reads AGREE. `DISPOSITIONS` and `VOIDING_DISPOSITIONS` keep `transposition` as the human escape
hatch for indistinguishability the snapshot cannot express — face-down DECK options can never be
grouped, and an equivalence turning on information outside `obs` would otherwise have no way to be
recorded at all. `test_the_transposition_frame_ADR_0085_relies_on_is_recorded_and_voided` is rewritten
to assert the stronger property (the frame is gradeable AND satisfied), turning a test that pinned the
workaround into one that pins the fix.

Rejected — **retire the word with the entry**: forecloses the off-board case and costs an ADR to
reinstate.

Rejected — **ship the oracle and leave the frame voided**: keeps excusing a frame the gate can now
adjudicate, which is verbatim the complaint in this issue's title.

**4. The Leaf Lab gets the same oracle, and a CLASS ASYMMETRY report.**
`correct_is_unique_top` becomes *unique up to indistinguishability*; `top_tie` counts **classes**, not
raw options. A tie between options that are the same decision is correct behaviour, and scoring it as
a discrimination failure aims leaf-enrichment work at a phantom. New per-row `class_asymmetry`
(indices + spread) is printed by both the lab readout and `print_gate_report`, **reported and never
gating** — the doctrine `gates.py:24` already applies to the tie metrics, and for the same reason: a
metric nobody has ruled on must not start failing `main`.

**4a. (Build time) The Leaf Lab reads its sim TWICE: RAW for the finding, CANONICAL for the verdict.**
Found by a test, not by inspection. Canonicalising before computing `class_asymmetry` makes the
finding empty **by construction** — an instrument that can only ever report "nothing", which is
verbatim the vacuous-gate failure `decider_lab_diff`'s docstring exists about. Grading the raw values
instead measures something the agent does not do, since the rung fans the class maximum out before it
ranks, and rung/instrument drift is how the sweeps rotted. Both jobs are real, so both readings are
kept: the recorded `values` column stays RAW (it is the asymmetry's evidence), and every verdict —
`correct_is_top`, `correct_rank`, `top_tie` — is computed on the canonicalised copy.

**5. The leaf ASYMMETRY is fixed by canonicalising to the class MAXIMUM.**
The rung groups its candidates, sims ONE representative per class (**the lowest option index** —
deterministic, so a ranking is reproducible across processes, which `#178` made non-negotiable), and
assigns that value to every member. Sound by the isomorphism argument: the best continuation
available from one member is available from all, so raising the others is correcting an omission, not
optimism. It is also a **performance win** — a 3-member class costs one rollout instead of three.

Rejected — **make the rollout order-invariant** (the true root cause): open-ended. The rollout is
greedy under a budget, so invariance means exhausting the branch or canonicalising states inside the
search — `transposition_probe.py`'s territory, and that probe exists precisely because nobody has
established the search can afford it. **Filed as Issue #254**, with the five frames and the
measurement.

Rejected — **canonicalise to the class minimum**: discards a KO line the sim proved reachable.
Conservative in the wrong direction; the maximum is the *provably attainable* value.

**6. The seam is `_develop_rollout_line` + the Leaf Lab, sharing ONE helper.**
Both rank one-per-menu-entry (`[i]`), which is the shape the oracle was measured on, and they read the
same helper so the rung and the instrument that grades it cannot drift — the drift that rotted the
sweeps (`decider_lab.py:9`). `planner.py:1496` is untouched (single candidate, nothing to compare).
`planner.py:474` is untouched because `cand.next_step` is a multi-step **line**, not an option index;
an equivalence over lines is a strictly larger claim with no corpus evidence behind it. That site
keeps whatever order-sensitivity it has, unmeasured — stated rather than papered over.

**7. The oracle lives in SHIPPED code; `gates.py` imports it.**
One pure, dependency-free module (no `cg.api` import, so `gates.py` can read it without mapping the
native library and stays unit-testable with no engine). Two implementations of "these options are the
same" would drift, and the drift would be invisible because the agent and its grader would each be
self-consistent.

**8. The representative's stream bit governs its whole class.**
`_develop_rollout_line`'s all-or-nothing defer (`if stream: return None`) is unchanged in **rule** and
narrowed in **population** — the ranking is then composed entirely of values the rung actually
consulted, each reproducible, which is what the rule asserts. It also removes an order-dependent
defer that is live today: a class currently gives up the whole turn when one isomorphic sibling
happens to roll a coin its twin did not, and which sibling rolls is exactly the cross-process variance
`#178` documents (the same first step simmed 7000 / 162 / 129 / 89 / 57.5). Consequence, accepted:
**the rung defers less often than today.**

Rejected — **sim every member anyway, defer if any rode the stream**: forfeits the performance saving
and keeps the defer hostage to a continuation the build has decided not to believe in.

Rejected — **rank the non-stream members only**: contradicts `_develop_rollout_line`'s own docstring
— *"a subset ranking is not a ranking... Rank everything or rank nothing"* — written after f24 showed
that excluding stream-riders systematically leaves the do-nothing options standing.

**9. `leaf_option_equivalence` ships ON.**
Every Pilot ctor flag must appear in `PROFILE` (`runtime.py:26`, pinned both ways by
`tests/agents/test_runtime.py`), so the flag is mandatory; only its value was open. ON, because this
is not a speculative new term needing ladder evidence — it deletes an inconsistency, and the corrected
value is one the simulator itself demonstrated reachable. Follows the `develop_rollout: True`
precedent. The evidence gate is ADR-0072's two instruments plus the human flip review this build owes
before either baseline is re-captured.

Rejected — **armed-OFF pending a ladder A/B**: the `leaf_hand_value` precedent is for a *new positive
leaf term*, the class of change that silently voids guards calibrated against the old one. This is the
opposite shape. Shipping dark would also leave the new asymmetry report firing forever on a defect the
code could already have fixed.

## Measured AT THE BUILD (2026-07-31, both gates run against the committed baselines)

```
Decision Gate:        PASS   0 picks moved   agree 248/346 -> 250/347   voided 25 -> 24
Discrimination Gate:  PASS   0 OK->MISS, 0 MISS->OK      agree 183/249 (unchanged)
  leaf SOLE-top (strict):            35/249  ->  40/249   (ties now counted over CLASSES)
  CLASS ASYMMETRY:            4 frames / 5 classes, worst spread 2097.25
```

Both gate predictions from the grill held exactly. Five frames moved into the strict rate because a
tie *within* one class stopped being scored as a discrimination failure — the phantom decision 4
describes, now measured rather than argued.

### ⚠️ Neither gate can exercise the develop rung — found at the build, not assumed

**Zero of the 372 committed Corrections carry `search_begin_input`.** `_develop_rollout_line` fires
only on a reseedable board, so the Decision Gate replays every frame with the rung inert: its `PASS`
and its `0 picks moved` are **not evidence about decisions 5, 6 or 8.** The Leaf Lab reaches the leaf
only because it injects a placeholder token, and it calls `_engine_leaf_value` per option directly
rather than through the rung — so it does not exercise the rung either.

That is not a defect introduced here; it is the shape of the corpus. But it means the rung's
canonicalisation, its representative choice and its narrowed stream defer rest entirely on **unit
coverage** (`tests/strategy/test_develop_rollout_rung.py`, seven cases: one sim per class, class
maximum fanned out, a distinguishable twin still ranked separately, kill-switch OFF byte-identical,
a stream-riding representative still deferring, a stream-riding non-representative no longer
deferring, and the committed pick being the class's lowest index). Stated plainly because a green
gate that never ran the code reads as evidence otherwise — the exact misreading ADR-0085 Amendment I
was written about.

## Found by the two-axis review, after the build

**A real defect, shipped and caught: one pick satisfied TWO ruled cards in one class.**
`satisfies_human`'s first implementation asked only *"does some member of this card's class appear in
the pick?"* — so a ruling of `[1, 3]` over two indistinguishable options was satisfied by `[1]` alone.
Verified live before the fix: `satisfies_human([1], [1,3], equiv=…)` returned `True`. That contradicts
the decision's own stated rule (*a class widens WHICH option satisfies a ruled card; it never excuses
a missing one*) and the spec's user story 44. **Zero of the 372 committed frames hit it**, so it was
latent rather than a live mis-grade — which is exactly why it needed a test rather than a corpus
assertion. Now COUNTING, not membership: classes partition the menu (an option has one fingerprint,
so it sits in exactly one class), which makes per-class counting an *exact* bipartite matching rather
than an approximation.

**A coverage hole:** `decider_lab_diff`'s `equiv` threading had no test — the very path that decides
whether `main` goes red. Three added, including the one that reproduces the defect first
(`REGRESSION` without the map, `NEUTRAL` with it) and one pinning that both sides of a diff are
restated against a single map.

**Duplication the module's own docstring forbids:** the "classes of a map" walk existed three times
and "the class of an index" three times, each spelt slightly differently. Both are now single
functions in `common.option_equivalence` (`classes`, `class_of`) that every caller reads — a second
definition of *"these are one decision"* drifts silently, because each copy stays internally
consistent. `fan_out` also became list-in/list-out, deleting a `{i: v for i, v ...}` adapter that both
call sites were writing.

**Deviation from the spec, accepted deliberately:** decision 4 said the asymmetry finding is rendered
"in the lab readout **and in the shared gate report block**". It is rendered only in the lab readout.
`print_gate_report` is shared by BOTH gates, and the Decision Gate has no leaf values and so can never
populate the field — adding it there would be a parameter one of two callers can only ever pass empty,
which is Speculative Generality in the one printer whose whole purpose is that the two gates cannot
drift in shape. The effect the decision wanted is met: `_print_report` runs on the `diff` path, so CI
prints the finding on every push.

## Consequences

* An indistinguishable-options ruling can be **satisfied on purpose** — the title of Issue #247.
* The leaf stops valuing one decision at 1167.0 and 95.4 depending on bench slot, and recovers a KO
  line the greedy rollout was missing for two of three identical bodies.
* Shipped play moves twice over — leaf values, and a rung that defers less often. Both land in one
  Decision Gate flip review.
* **Both** baselines are re-captured, each as its own commit with its delta stated, and **only after
  the flips are ruled with the human** — `CLAUDE.md`'s never-auto-recapture rule is about the gate
  blessing itself, and ADR-0088 set the precedent for the sanctioned path.
* Cost: an oracle lifted into shipped code, a new `PROFILE` flag, two ruling-record commits, and the
  leaf strict-rate becoming non-comparable to its old self.
* Not addressed, by design: the greedy rollout's order-dependence itself (**Issue #254**),
  `planner.py:474`'s line-shaped candidates, and Issue #229's DECLINE-writer question.
