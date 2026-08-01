# ADR-0098 — The apply-seam is guarded by detect → localize → classify → CONTAIN

**Status:** Accepted (grilled 2026-08-01, `/grill-with-docs` on Issue #259, wave-1 packet item 6 —
the escape-hatch doctrine fork, plus the user's remedy requirement).
**Build = Issue #259 (POC-T0 contract + registry), lanes and gate owned by T4.**
**Extends [ADR-0059](0059-cgpy-is-a-trace-verified-python-twin-of-the-native-engine.md)** (the parity-trace
format, the replayer, the differ and the DLL-free CI gate — this adds a third lane to rails that
already exist) and **ratifies ADR-0092 §4-T0/§4-T4's** "engine-sim as parity fixture, never a
runtime path" **with the guard that makes it survivable**. Does **not** supersede anything.

**Context issues:** Issue #259 (this grill), Issue #165 / POC-T4 (the planner that consumes the
seam), ADR-0050 (`_exact_own_zones`, the anchored-seed machinery weighed in the rejected option).

## Context

### Four objects, routinely conflated — named once, here

| # | object | what it is |
|---|---|---|
| 1 | **native engine** | `cg/cg.dll` / `cg/libcg.so` via `src/cg/api.py`. The competition simulator. THE authority. Never modified. |
| 2 | **cgpy** | `src/cgpy/` (ADR-0059). A pure-Python **reimplementation** of #1. A real engine — setup machine, turn loop, damage, effect-DSL. **Not complete:** per `src/cgpy/CONTEXT.md` status 2026-07-11, **123/414** kaggle episodes fully green; 1074/1556 attacks and 856/1267 cards live, rest deferred. |
| 3 | **Engine Search / engine-sim rollout** | Not an engine. The *use* of an engine's fork API (`search_begin`/`search_step`) to play hypotheticals forward. Runs on either backend — native in production, cgpy injected offline via the `_search_api` seam. |
| 4 | **`apply_option`** | Not an engine. The closed-form ONE-STEP transition T0 specifies: StateModel + option → StateModel', stepping nothing. |

ADR-0092's "the engine-sim survives only as a T4 parity fixture, never a runtime path" retires **3**
from decision time and puts **4** in its place. cgpy is neither retired nor built by that sentence.

### The fork, and why it was declined

The escape-hatch question asked whether **3** should remain a runtime route under narrow
preconditions — ADR-0050's `_exact_own_zones` already seeds the exact deck/prize split when the
tracker has anchored, so for deterministic, shuffle-free transitions on anchored state the engine is
exact where `apply_option` is a hand-written model of it. Two objections survived (a commonly-cited
third — "the engine cannot fork cheaply" — is simply false; it forks an independent position and the
Pilot already uses it live for the Lethal Solver):

1. **Single-sample, not expectation.** Any line drawing past a shuffle returns one Monte-Carlo draw
   from the sim's own RNG. Measured, ml f24 2026-07-27 (`_simulate_line` docstring): the same first
   step scored 7000 / 162 / 129 / 122 / 89 / 57.5 across processes.
2. **Offline invisibility — decisive.** `search_begin` requires `search_begin_input`, present only
   on a live agent observation: **0 of 372 gate frames** carry it; only 5 seeded fixtures do
   (`src/common/runtime.py:108`). A decision taken through an engine route is invisible to the
   Discrimination Gate, the Decision Gate, the leaf lab and the correction corpus.

For a build whose whole verification story is gates plus batched wave rulings, a second route no
instrument can see would put the very families the POC exists to price beyond the reach of
everything that rules them.

### The exposure that remains, and the user's requirement

Declining the fork leaves one stated cost: *if the parity fixture is thin on some option kind we
will not find out in production.* The user's requirement on accepting: **"needs to be an automated
process of failure identification and rectification."**

Automated *repair* of a hand-written model is not achievable — nothing infers the correct
closed-form transition from a diff. Automated **detect → localize → classify → contain** is, and
containment is the half that protects production.

## Decision

**1. `apply_option` is the SOLE runtime transition for the POC.** The engine-sim is a test fixture.
The anchored-and-shuffle-free engine route is recorded as a named **post-POC amendment candidate**
with its reopening trigger: material divergence, in the parity lane below, on deterministic
transitions (evolve, attach, retreat/promote, deploy).

**2. A third lane on ADR-0059's rails — detect + localize.** At each recorded native trace frame,
push the recorded choice through `apply_option` and diff the resulting StateModel against the
StateModel built from the **next** frame's recorded observation, localized by
`cgpy/verify/differ.first_divergence` (JSON path, no normalization).

Two properties this inherits and one it does not:
- The reference is the **recorded native trace**, never cgpy. Checking a hand-written model against
  a 123/414-green reimplementation would be checking a model against a model.
- The god frames supply hidden state, and the trace supplies the native side — so the lane is
  **DLL-free**, exactly as ADR-0059's gate is, and the `search_begin_input` blocker does not apply.
- Unlike cgpy's lane it is **not** a whole-game forward replay reproducing a full observation. It is
  one step, compared over StateModel fields.

**3. A per-option-kind COVERAGE gate.** CI asserts a minimum exercised-transition count for every
option kind the T0 seam table declares, and **fails on any kind below floor**. This attacks fixture
thinness directly rather than trusting the corpus to be representative. Silent under-coverage is the
named exposure; a gate is the only thing that converts it into a build failure.

**4. QUARANTINE — the containment half.** A divergence class marks its option kind `unverified` in a
registry; T4's planner refuses to enumerate sequences through an unverified kind and defers to the
whitelisted sound ladder. A parity failure therefore **degrades** the agent instead of silently
mis-playing it. Mandatory companion: telemetry naming which kinds are quarantined and why — without
it a degraded agent is indistinguishable from a bad one.

**5. A FUZZ lane.** Generate legal boards, push each option kind through `apply_option`, diff against
the same reference. Self-expanding coverage the 372-frame corpus cannot provide; it is what finds
the thin kinds before a graded match does.

## Consequences

- The quarantine registry is a real runtime coupling between a test artifact and planner behaviour.
  It must never become a silent kill-switch — decision 4's telemetry is not optional.
- The fuzz lane needs a legal-board generator that does not exist yet. That is new T4 work.
- Coverage floors are authored numbers and will need revising as the seam table grows; they are
  whitelisted authored constants like any other, and queued for post-POC review.
- If the parity lane shows divergence concentrated on deterministic transitions, that is precisely
  the evidence that reopens decision 1's post-POC candidate — the fork is declined on current
  evidence, not on principle.

## Amendment A — the seam is on the HOT path at 1 ply (ruled 2026-08-01, Issue #263)

Ruled by the developer **after this ADR was accepted and while PR #266 was in flight**, on the
authority of the *"Contract impact of the Issue #263 ordering ruling"* comment on Issue #259.
Recorded here rather than as a sibling ADR because this ADR is introduced by the same unmerged PR —
minting a new number to amend a same-PR sibling would record a history that never existed.

**What moved.** Issue #263's composer was amended: its beam ordering heuristic is now **uniform
1-ply differencing** — apply each candidate option through this seam, score `state_value` on the
result, rank by the delta. It replaces *"the firing per-seam equations provide the local ordering."*
The reason is a coverage hole in the old phrasing, not a preference: **heal, fetch, tool, stadium and
draw have no per-seam equation at all**, so under equation-provided ordering they would have sorted
at zero and been pruned before the leaf ever saw them.

**Four contract consequences**, all inside this track's scope:

**A1. The option-kind table is TOTAL.** Ordering visits every option on a live select menu, not only
the kinds that appear mid-sequence, so `KIND_COVERAGE` classifies every `OptionType` member as
`modelled` / `terminal` / `refused`. `TRANSITION_KINDS`, `TERMINAL_KINDS` and `REFUSED_KINDS` are
DERIVED from that one table — a hand-kept second copy is the drift ADR-0087 charges for one store
over, and here it would let the planner believe a kind is modelled while the seam refuses it.

Measured over the 372 corpus frames both gates read (`data/corrections/*/corrections.jsonl`,
2026-08-01):

| where | kinds seen |
|---|---|
| MAIN menu | PLAY 699 · ATTACH 796 · EVOLVE 49 · **ABILITY 17** · RETREAT 146 · ATTACK 231 · END 279 |
| elsewhere | CARD 507 · SKILL 2 |
| never seen | DISCARD(11), and every YesNo / Count / Energy / attached-card kind |

**ABILITY is what makes this concrete**: 17 live MAIN-menu options that the pre-amendment table did
not declare at all, so ordering would have *raised* on them. `DISCARD(11)` is declared `refused`
rather than `modelled` for the opposite reason — zero observations is no evidence to model against,
and declaring it modelled would owe T4 an implementation nothing can check.

**A2. Refusal is a RESULT, not a no-op and not an exception.** `apply_option` returns one of three
shapes: a `StateModel`, an `Expectation`, or a **`Refusal`**. A silent no-op prices the option at
exactly 0.0 delta, and at ordering time 0.0 does not read as *undervalued* — it reads as *never
explore this*, and the gap never surfaces as anything but an agent that mysteriously ignores
Pokégear. A `Refusal` is visible to the composer, which answers it by **always-expanding**;
`must_expand()` is where that policy lives so no caller re-derives it from an `isinstance` check.

Four refusal scopes, because the composer treats them identically but the coverage gate and the
telemetry line must not: `kind` (declared unmodellable), `option` (kind modelled, this card's effect
is not — *"the card leaves my hand"* is structural for every `_PLAY`, but a Trainer's effect is
per-card), `undeclared` (the enum grew — `src/cg/api.py` says outright that members are appended
during the competition), `quarantine` (decision 4's parity divergence, now routed through this same
path so quarantine and the table give ONE answer).

Consequently `transition_kind()` **no longer raises**. It did, when the seam was asked about four
kinds mid-sequence; on the 1-ply hot path a raise is a forfeited grader match over an option we
merely could not price. `UnsupportedTransition` survives with one honest job: `require_model()`,
which the parity lane calls because a step *it* cannot model is a coverage gap that must fail the
run, not a branch to expand.

**A3. Transitions are LAZY.** Once per candidate per decision rules out an eager deep copy per
branch on 2 vCPUs. Transitions materialise only what the caller reads, riding the lazy pure snapshot
of [ADR-0068](0068-the-statemodel-is-a-lazy-pure-snapshot-shared-by-side.md). T0 cannot test this —
nothing is implemented — so it is asserted as stated contract, which is what stops T4 discovering
the requirement late.

**A4. `Expectation` is ORDERABLE at 1 ply, not merely expandable.** A draw Supporter must be rankable
against a Tool attach on the same scale *before* anything decides to expand it. `Expectation.expected(score)`
is that number, **renormalised over the enumerated mass** — the expectation conditional on branches
that survived the cap. Letting truncated mass contribute 0 would bias precisely against the widest
enumerations, and the widest enumerations are the draw and search effects this amendment exists to
stop pruning. `total_probability` still exposes the gap, so a caller that wants to discount an
incomplete enumeration can; it is not this method's job to do it silently. Zero enumerated mass
raises rather than returning 0.0 — an un-enumerated effect must not read as a worthless one.

**What did NOT move:** the `state_value` term registry and the StateModel completion API. Decisions
1–5 above stand unchanged; this amendment widens the contract's surface, it does not revisit the
declined engine route.

## Amendment B — three fates, footprints, and a completeness contract (ruled 2026-08-01, Issue #259 §3b/§3c)

Ruled by the developer into the Issue #259 **body** (sections 3b and 3c, both new) while PR #266 was
in flight, with an "AMENDMENT CHECKLIST" comment as the delta list. Recorded here for the same reason
as Amendment A: this ADR is introduced by the same unmerged PR, so a sibling number would record a
history that never existed.

### B1. Three fates — and the engine route comes BACK, narrowly

Amendment A left two outcomes (modelled or refused). §3b adds a third between them:

| fate | when | returns |
|---|---|---|
| **MODELLED** | closed-form from Effect Clauses. Always preferred. | a `StateModel` / `Expectation` |
| **ENGINE-RESOLVED** | clause-vocabulary gap, **but** provably deterministic **and** real board **and** 1-ply | an `EngineResolved` wrapper |
| **REFUSED** | everything else | a `Refusal` (always-expand) |

This does **not** reopen decision 1. That decision declined an engine route *as the runtime pricing
mechanism*, on two objections: single-sample-past-a-shuffle, and offline invisibility. The narrow
fate here is immune to both by construction — *provably deterministic* excludes anything past a
shuffle, and 1-ply-on-a-real-board means the frame is a live observation, which is the only kind that
carries `search_begin_input` at all. It is a bridge for a **vocabulary** gap, not a substitute for
the closed-form model.

**The gate wording is load-bearing: "provably deterministic", NOT "unmodelled".** So `deterministic`
is **tri-state** and its unproven default (`None`) refuses — ADR-0067's yield convention, fail
closed. Two independent fatal reasons, both worth restating because either alone settles it:

1. The engine has **no deal-seed**, so a shuffle-riding sim returns ONE SAMPLE rather than a
   distribution. That is Issue #178's defect, and the same measurement decision 1 rests on.
2. Nondeterminism breaks the **deterministic replay both gates depend on**. A frame whose decision
   turns on a coin flip cannot be ruled, so it cannot be graded, so the gate protecting it is
   vacuous — the failure mode this whole ADR series exists to prevent.

Refused outright, therefore: opponent-choice effects (an accepted POC gap — there is no opponent
model), anything riding the shuffle, and **anything at depth ≥ 2**. Depth is not a policy dial: past
the first ply the preceding steps were closed-form applies, so the board is a *synthesized*
StateModel and there is nothing to hand the native engine. Each precondition refuses under **its own
scope** (`depth` / `nondeterminism` / `no-engine`) because they are three different pieces of work.

**`_search_api` is preserved on purpose.** Issue #263 retires it as a runtime *rollout*; the *seam*
survives as exactly this fallback. Do not design as if it disappears — a natural misreading of "the
rollout is retired", and the reason the issue says so explicitly.

**Telemetry is structural, not conventional.** The route returns an `EngineResolved` wrapper rather
than a bare model, so a caller cannot use the answer without seeing that the engine produced it. §3b
calls this route *"a bridge that makes the vocabulary gap visible for later modelling, never a
resting place"*, and a convention every caller could forget would not deliver that.

### B2. Per-kind READ/WRITE footprints

The table exposes, per kind, the snapshot fields the transition WRITES and the fields it READS.
Issue #263 consumes both to prove **commutativity** — two options commute iff neither reads what the
other writes and they do not both write the same field — and collapse orderings into one canonical
candidate per subset.

**Fail closed:** an unknown or partial footprint commutes with NOTHING. An under-reporting footprint
is worse than none, because it licenses a reorder that changes the board and lets the composer
collapse two genuinely different lines into one candidate. Only `_ATTACH`, `_EVOLVE` and `_RETREAT`
carry complete footprints (their write-sets follow from the rulebook, not from card text); `_PLAY`
deliberately does not, because a Trainer play writes whatever its Effect Clauses write and that is
per-card.

Separately, a kind that **reveals information** can never join a commutative block whatever its
footprint says: a reveal changes the OPTION SET, not only the board, so reordering around it changes
what the later choices are.

### B3. StateModel completeness is a contract (§3c)

> *"All fields should certainly be covered — we want to minimize this risk."*

The differencing system's worst failure mode is an effect writing to state the snapshot cannot
represent: the delta reads **0**, and under 1-ply ordering 0 means *never explored*, not
*undervalued*. `src/common/snapshot_coverage.py` is therefore the enumeration, as data — every
writable zone with its snapshot home, or one of two explicit statuses:

- **`owed`** — no home yet, and it **must name the owning track**. An owed zone with no owner is a
  silence, not a schedule. Four today, all T1 / Issue #260: `attached_tools` (the raws carry a
  `tools` key; the typed read is missing), `special_conditions` (`attack_blocked` derives the two
  that block acting but collapses them to one bool on the SIDE), `allowance_retreat_used` (the
  observation has `current.retreated`; the snapshot does not surface it), `transient_grants` (only a
  private generation *counter* exists, not a read of the grants).
- **`hidden`** — deliberately unrepresentable. Deck **order** is the case, and it must say what
  prices it instead (`deck_odds` hypergeometrics). Recorded so nobody "fixes" it by inventing a
  field, and it is the same fact that makes shuffle-riding effects REFUSED above.

The **audit test** walks the committed Effect Clause vocabulary (`card_effects.json`, ADR-0032) and
fails on a kind or rider with no declared write-set — the requirement that a new clause fail rather
than silently price 0. The strong invariant is `clauses_writing_unhomed()`: **no clause the
compendium already knows may write to an owed zone**, which is what keeps the owed list a schedule
rather than a live correctness hole. It is empty.

`footprints_writing_unhomed()` is **not** empty, and that is a finding rather than a defect in the
registry: `_EVOLVE` clears Special Conditions (`docs/rules.md` §4) and so does `_RETREAT`, since they
are cleared "when it leaves the Active Spot OR evolves" (§8) — both rulebook-sourced, and the second
easy to miss because the rules text leads with the evolve half. `special_conditions` has no home, so
part of what those two transitions do is currently invisible to a delta. Surfaced as a generated T1
work list, with a test asserting the set can only shrink.
