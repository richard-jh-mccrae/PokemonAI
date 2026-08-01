# ADR-0098 — The apply-seam is guarded by detect → localize → classify → CONTAIN

**Status:** Accepted (grilled 2026-08-01, `/grill-with-docs` on Issue #259, wave-1 packet item 6 —
the escape-hatch doctrine fork, plus the user's remedy requirement).
**Build = Issue #259 (POC-T0 contract + registry), lanes and gate owned by T4.**
**Extends [ADR-0059](0059-cgpy-is-a-pure-python-twin-of-the-native-engine.md)** (the parity-trace
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
