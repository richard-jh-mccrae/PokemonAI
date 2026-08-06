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
fails on a kind, rider or `effect` with no declared write-set — the requirement that a new clause
fail rather than silently price 0. (`effect` joined that walk in Issue #300; before it, the walk
covered kinds and riders only, so Crushing Hammer's `{"kind": "coin", "effect":
"discard_opp_energy"}` passed green while the write it performs had no declared home. The walk now
lives in `snapshot_coverage.clause_vocabulary()` rather than in the test, because a walker on the
checking side is one nobody updates when the schema grows.) The same issue added the per-card
`_covers` verdict: a clause set that covers only PART of its printed card is declared as such, and
`snapshot_coverage.clauses_cover()` turns that into the fail-closed tri-state `fate()` refuses on,
so a partial set cannot price as a complete one. The strong invariant is `clauses_writing_unhomed()`: **no clause the
compendium already knows may write to an owed zone**, which is what keeps the owed list a schedule
rather than a live correctness hole. It is empty.

`footprints_writing_unhomed()` is **not** empty, and that is a finding rather than a defect in the
registry: `_EVOLVE` clears Special Conditions (`docs/rules.md` §4) and so does `_RETREAT`, since they
are cleared "when it leaves the Active Spot OR evolves" (§8) — both rulebook-sourced, and the second
easy to miss because the rules text leads with the evolve half. `special_conditions` has no home, so
part of what those two transitions do is currently invisible to a delta. Surfaced as a generated T1
work list, with a test asserting the set can only shrink.

## Amendment C — the fate is PER-OPTION, not per-kind (ruled 2026-08-02, Issue #299)

Amendment B added the ENGINE-RESOLVED fate and put `_ABILITY` alone behind it. POC-A2's census
(`docs/plans/apply-seam-coverage.md`, Issue #269) then measured what that cost, and the answer was
the largest single lever in the whole report.

### C1. What the measurement said

- `ENGINE_ROUTE_KINDS` was `{_ABILITY}`, and **every** live `_ABILITY` option in the 372-frame corpus
  (17 of them) is Drakloak's Recon Directive or Lunatone's Lunar Cycle — deck-reading draw engines,
  fail-closed REFUSED. The bridge resolved **zero** live options. That is not a corpus artefact:
  Issue #305 measured that a *triggered* Ability never poses an `_ABILITY` option at all, so widening
  the corpus could not have found one.
- **46 refused sites** on MODELLED kinds (`_PLAY` / `_ATTACH` / `_EVOLVE`) carried no RNG,
  hidden-zone or opponent-choice marker — precisely the shape B1 calls ENGINE-RESOLVED, refused only
  because of the kind they sat on.
- Four cards (Drakloak, Lunatone, Dudunsparce, Fezandipiti ex) carried Effect Clauses covering their
  **whole** Ability and were unreachable: `fate` returned MODELLED only for a MODELLED kind, so they
  routed to the engine and the engine refused them for nondeterminism.

### C2. The ruling

**The kind table stops being the gate.** It answers *"is there a uniform board transition for this
KIND?"*; the fate answers *"can we resolve THIS option's card effect?"* Those are different
questions, and `refuse(..., scope=OPTION_SCOPE)` already modelled the difference — it just had
nowhere to send the option. Now it does:

    TERMINAL                                  -> not a fate; `is_terminal` first, `apply_option` raises
    UNDECLARED                                -> REFUSED (the vocabulary moved underneath us)
    clauses_cover is True                     -> MODELLED, whatever the kind says
    kind MODELLED and clauses_cover not False -> MODELLED (the structural path, unchanged)
    depth 0 + deterministic + search_api      -> ENGINE-RESOLVED, for ANY declared non-terminal kind
    otherwise                                 -> REFUSED, at the engine precondition it missed

**Decision 1 is not reopened.** It declined the engine as the *runtime pricing mechanism* on two
measured objections, and both remain excluded by construction exactly as B1 argued: *provably
deterministic* answers single-sample-past-a-shuffle, and 1-ply-on-a-real-board answers offline
invisibility. Widening WHICH kinds may cross that bridge changes neither premise — the preconditions
are properties of the call, never of the kind, which is why gating on the kind was the error.

**`KIND_COVERAGE` is unchanged.** No kind was promoted or demoted: the composer's pruning depends on
the table and B1 forbids demoting one without a ruling. `ENGINE_ROUTE_KINDS` survives as
documentation of which kinds have no closed-form answer to fall back to, re-documented at its
definition and beside `__all__` rather than silently repurposed. `KIND_SCOPE` is likewise kept and
declared no-longer-emitted: once the table stopped deciding fates, "this kind has no uniform
transition" stopped being why an option refuses.

### C3. `clauses_cover`, and why its two falsey answers differ

Issue #300 shipped the per-card `_covers` verdict and `snapshot_coverage.clauses_cover()`; this
amendment wires it into `fate`. `True` wins outright — a complete clause set is closed-form,
deterministic in distribution, and what the compendium exists to provide, so it is strictly better
evidence than a kind-level default. `False` (a `partial` verdict) REFUSES a kind the table calls
MODELLED, which is the entire reason the verdict was declared: before this, a partial set priced as a
complete one and the uncovered leg differenced to a silent 0.

`None` does **not** refuse, and that asymmetry is deliberate. `None` is *absence of a compendium
entry*, which covers both "an effect nothing models" **and** "no printed effect for a clause to
cover" — a vanilla Basic's deploy, a Basic Energy attach, a Tool attach, which are most of the pool
and are structurally MODELLED. Refusing on `None` would refuse the structural transitions the seam
exists to provide. Separating the two is the **caller's** obligation, since only the caller holds the
card's effect text; `tools/apply_seam_coverage.py:clauses_cover` is the worked example and the census
is the first consumer.

### C4. Consequences

- **Telemetry:** `EngineResolved.clause_gap` must now name the CARD, not only the kind. With the
  route `_ABILITY`-only the kind was nearly an identifier; open to every declared kind, a backlog
  line reading *"kind 7"* covers 699 corpus `_PLAY` options. Extended in the existing field, not
  beside it — the backlog groups by that one string.
- **Measured movement** in the census: ENGINE-RESOLVED 10 -> 57 sites (8 -> 40 copies across our
  decks, 0.2 -> 9.8 meta-weighted); MODELLED 312 -> 295 sites, because the 21 MODELLED-PARTIAL sites
  left it; REFUSED 92 -> 62. The report's "deterministic-shaped" refusal row is now **0**, and its
  emptiness is a live check on the routing rather than a backlog.
- **The census now CALLS `fate`** instead of mirroring its cascade by hand, supplying the two
  judgements it is entitled to make. One store for the resolution order, so the report cannot claim
  a fate the seam would not return.
- **Nothing at runtime moved.** No production caller invokes `apply_option` yet (T4 / Issue #263
  writes them), so both gates were expected to be — and were — unaffected.

## Amendment D — footprint granularity is ELEMENT-level (ruled 2026-08-04, Issue #263 / Issue #383)

**This is a contract-freeze ruling line**, in the form ADR-0092's freeze discipline requires: the
footprint contract Amendment B froze at POC-T0 is EXTENDED here, and it lands only because the
developer ruled it on the record. Requested by the Issue #383 build session on
[Issue #263](https://github.com/richard-jh-mccrae/PokemonAI/issues/263#issuecomment-5180494615)
**before any code was written**, with a stated fail-closed fallback; **GRANTED 2026-08-04** (option
1 of two). Recorded here rather than in `data/leaf_lab/wave3-rulings.md` because that file is the
gate-flip record — frame → verdict — and this ruling moves no frame: it changes what the contract
means, which is what an ADR amendment is for.

### D1. What was wrong

Amendment B's rule — *"two options commute iff neither reads what the other writes and they do not
both write the same field"* — is sound and **licensed nothing**. Measured over every pair in
`KIND_COVERAGE`, including self-pairs: **zero commuting pairs**. *Positive control:* `commutes` does
return True for two hand-built complete disjoint footprints, so the zero was the table's answer and
not a broken function.

That made Issue #263 § *Commutative-block collapse*'s own worked example — *"an Energy, an evolution
and a Tool in any of 3! orders reaches ONE board, so it is ONE candidate"* — **unprovable by the very
test that section mandates**. A Tool arrives as `OptionType.ATTACH` exactly like an Energy, so the
triple is two `_ATTACH`s and one `_EVOLVE`, and at whole-zone granularity every pair collides on
`my_hand_ids`, two of them on `bodies_in_play`, and the two `_ATTACH`s on
`allowance_energy_attached`. The section's justification — that reorderings crowd genuinely different
lines out of a beam of width *k*, a **search-quality** property rather than a speed one — was
therefore unbought.

### D2. The ruling

**Where a write is an element-level removal or addition over distinct instances, two such writes to
DISTINCT instances commute.** The instance key is the engine's own `serial`.

`snapshot_coverage.ELEMENT_ZONES` is the registry — **five** zones, DERIVED from the two halves that
say which serial keys them (`CARD_KEYED_ZONES`, `BODY_KEYED_ZONES`) so the membership is never listed
twice: `my_hand_ids` by the played card's serial, and `bodies_in_play` / `attached_energy` /
`attached_tools` / `damage_counters` by the target body's.

**The grant as delivered said "discard arrivals by `serial`", and that leg is NOT implemented — a
deliberate narrowing in the fail-closed direction.** The seam cannot resolve the key:
`their_discard_contents` receives a card that is never from my hand, and `my_discard_contents` is
right only for *"the Trainer I played lands in my discard"* — wrong for every `cost` clause
(`discard_1` … `discard_hand`) and for `discard_own_energy`, where WHICH card is discarded is chosen
at a follow-up select. Declaring a zone element-level while keying it wrongly is unsound in the one
direction this registry exists to prevent, so both discards stay whole-zone until an option shape
carries the arriving card's identity. It costs nothing today: no two `_PLAY`s can commute anyway,
because `_PLAY` writes whole-zone `bench_occupancy`.

**Everything else stays whole-zone, and that exclusion is a condition of the grant, not a leftover.**
Each excluded zone is what refuses a case the spec requires refused:

| zone | what it refuses | source |
|---|---|---|
| `bench_occupancy` | two Basics contending for the last Bench slot — the orders reach *different* boards | Issue #263 § *Commutative-block collapse*, named as a required rejection |
| `allowance_energy_attached` | a second Energy attach — only one of the two is a legal play at all | `docs/rules.md` §3, *"Attach Energy from hand \| **1** (manual attachment; card effects can add more)"* |
| `allowance_supporter_played` / `allowance_stadium_played` / `allowance_retreat_used` | the same, per turn | `docs/rules.md` §3, *"Play a Supporter \| **1**"* etc. |
| `special_conditions` | any pair touching them — conditions live on the Active alone and the engine holds the five flags on `PlayerState`, so there is no per-body instance to key on | `docs/rules.md` §8 |
| `stadium` | any pair — one shared slot for the whole board | `docs/rulebook.txt` L135-137 |

**`serial` is the same field ADR-0091's Option Equivalence deliberately IGNORES**, and the two are
not in conflict. The fingerprint drops it because two indistinguishable bodies are ONE decision;
commutativity keeps it because two writes to indistinguishable bodies are still TWO writes. Same
field, opposite questions — stated here so a later reader does not "fix" one to match the other.

### D3. Fail-closed, unchanged and unweakened

The refinement widens what can be **proved** disjoint; it widens nothing that is **assumed** disjoint.

- An unknown or partial footprint still commutes with NOTHING.
- A revealing play still joins no block, whatever its footprint says.
- A clause-less `_PLAY` is still UNKNOWN, never an empty write-set — and `clauses_cover=True` cannot
  complete an empty clause list, since that would be coverage asserted over the compendium's silence.
- **Unresolved beats precise:** a footprint naming an element zone *without* naming an instance is an
  UNKNOWN there and collides with every other write to it, however precisely the other side named
  itself. This is what keeps a targetless `_RETREAT` (all 5807 offered occurrences in the parity
  corpus are the bare `{"type": 12}`) and a whole-hand shuffle correctly non-commutative.

### D4. Consequences

- **`Footprint` gains `read_elements` / `write_elements`** (`{(zone, serial)}`), additive — `reads`
  and `writes` keep their meaning, so no existing entry changes.
- **`KIND_COVERAGE`'s table is untouched and `commutes()` still licenses ZERO pairs.** An element is
  an instance and a KIND has no instance, so a per-kind footprint resolves nothing and fails closed.
  The refinement lives entirely in `option_footprint`, which is where instances exist.
- **`option_footprint` narrows a KIND's structural floor to the SUB-CASE the option takes**
  (`_structural_drop`), because a kind footprint is the UNION of sub-cases that never co-occur and
  a table cannot tell them apart while an option can. Two places it is load-bearing, both discovered
  by mutating `ELEMENT_ZONES` and watching a rejection test stay green:
  - `_ATTACH` — the Tool leg writes `attached_tools` (+`damage_counters`), the Energy leg writes
    `attached_energy` + `allowance_energy_attached`; `board_delta._attach` already branches on
    `CardStat.cardType`. **Without the split an Energy and a Tool collide on the allowance and the
    worked triple cannot commute even under this ruling.**
  - `_PLAY` — a Basic deploy writes exactly `{my_hand_ids, bodies_in_play, bench_occupancy}`
    (`board_delta._play`'s own returned set). While the floor also declared `stadium`, both discards
    and two allowances, two Basic deploys collided on five zones neither of them writes, so the
    last-Bench-slot rejection **this ruling names** was never the thing doing the rejecting. A
    Trainer's `_PLAY` is NOT narrowed — `board_delta._play` refuses it, so there is no measured
    write-set to narrow to, and the full floor stands.
  The narrowing applies to the FLOOR only; the clause union goes on top of the result, or a
  Supporter's `gust` would have its `bodies_in_play` write stripped off by a sub-case that knows
  nothing about it.
- **A Basic deploy's `bodies_in_play` element is the HAND CARD's serial** — `board_delta._play`
  builds the benched body as `{"id": card_id, "serial": card.get("serial"), …}`. Resolved only for a
  Basic Pokémon: a Trainer that moves a body moves someone ELSE's (a `gust` writes the opponent's
  Active), so keying that by my hand card would be false precision.
- **`option_serials` honours the option's `playerIndex`** (private `_option_serials` until POC-T4/4,
  Issue #385, which made it public so the composer could re-resolve a block member by instance rather
  than write a second walk beside it). An option naming the opponent's board
  resolves to no element rather than to my own body at that index — a serial from the wrong side is
  false precision, the one direction that can license a bad reorder. Unreachable today, guarded
  anyway.
- **A narrowness worth recording rather than discovering:** two `_EVOLVE`s on distinct bodies still
  do NOT commute, because `_EVOLVE` writes whole-zone `special_conditions`. That is correct under
  this ruling as written (§8 gives no per-body instance to key on) but it was not anticipated in the
  request's conflict table, and it means evolution pairs stay at full width.
- **A requirement this puts on the composer (Issue #385), accepted by the developer with the grant:**
  element-level commutativity is a claim about the resulting **board**, never about option
  **encodings**. An option names its card by hand *index*, and removing hand card 0 shifts card 3 to
  index 2 — so the composer must re-resolve each block member against the board it is actually
  applied to, or canonicalise the block by `serial`. Replaying a saved option dict in a different
  order is wrong even when the two plays provably commute.
- **Nothing at runtime moved.** No production caller invokes `apply_option`, so both ADR-0072 gates
  were expected to be — and were — byte-identical.

## Amendment E — the new-in-play bit gets a zone, a read, and two footprint declarations (built 2026-08-04, Issue #391)

Not a ruling — no contract meaning changes and nothing was granted. It is recorded here because it
**edits facts Amendments B and D state outright**, and an ADR that quietly rots is worse than one
that corrects itself: B3's registry gains a zone, and D4's *"a Basic deploy writes exactly
`{my_hand_ids, bodies_in_play, bench_occupancy}`"* is now a set of four.

### E1. What was wrong

`appearThisTurn` — *"this body entered play this turn"* — was in **no** `snapshot_coverage` zone. So
it had no `StateModel` home, `state_value` could not read it, and no instrument built on the registry
could compare it. It is the bit `docs/rules.md` §4 turns into a rule: *"Cannot evolve a Pokémon the
turn it was played/put into play"*, which is what makes the 2-ply sequence `[play Basic, evolve it]`
**illegal** rather than merely bad — precisely the kind of sequence Issue #263's composer enumerates.

It surfaced through Amendment B's own discipline. Issue #382's parity lane injected four deliberate
defects to prove it could see them; three went red and the fourth — a `_PLAY` deploy that forgets the
bit — went **green**, because the lane compares the HOMED zones of `snapshot_coverage` and no zone
named it. `board_delta._play` and `_evolve` both wrote the bit correctly the whole time. Nothing in
the tree could hold them to it.

This is the status Issue #282 named **ABSENT, not owed — the worse status**, with one difference that
is the reason it took an issue rather than a line in Issue #382's diff: `this_turn_damage_boosts`
already HAD a shipped `_SideBase` read, so enumerating it was documentation catching up with code.
Here there was no read at all — **12 sites across 5 modules** consult the bit off a RAW body dict and
none off a snapshot — so the fix included **building** `BodyView.new_in_play`.

⚠️ **That number is 12, and Issue #391's body says 33.** The issue counted grep LINES; this counts
`.get("appearThisTurn")` in parsed CODE, which is the distinction `snapshot_coverage`'s
`UNCONSUMED_SELECTORS` was re-measured for one axis over — *"a grep for each value over `src/`
counted a string quoted in a COMMENT or a DOCSTRING as reached"*. At the merge-base: 34 matching
lines, of which **12 reads** (`pilot` ×4, `planner` ×4, `doctrine_fetch`, `frame_view`, cgpy's
`search` ×2), **4 dict-literal writes** (two of them `board_delta`'s own), and 18 lines of prose.
*Positive control on the instrument:* the same walk finds 15 `.get("maxHp")` reads. **The issue's
CONCLUSION survives** — none of the 12 is a snapshot read and `BodyView` had no such field — so this
corrects the evidence, not the decision. Two smaller claims in the same section do not survive and
are recorded so nobody re-derives from them: *"`grep -rn "appear" src/common/snapshot_coverage.py`
returns nothing"* is false (line 979 carries the word *"appears"* in prose), and *"`sc.BY_ID` has 24
entries"* was 23 before this change.

### E2. What changed

- **`snapshot_coverage.WRITABLE` gains `new_in_play`**, HOMED, on both sides.
- **The both-sides home rests on a READ argument, not the write one its neighbours use.**
  `attached_energy` / `damage_counters` / `transient_grants` are two-sided because *an effect writes
  the opponent's half*; nothing writes theirs here — only my own `_PLAY` and `_EVOLVE` set the bit, on
  my own bodies. It is homed on both anyway because the FACT is symmetric and fully visible (measured
  on the committed parity corpus: the engine carries `appearThisTurn` on the opponent's bodies and it
  clears across the turn boundary exactly as mine does) and because the RULE is symmetric — §4 gates
  their evolutions on it exactly as it gates mine.
- **All four legs name the FIELD, Bench included** (`mine.bench.new_in_play`), which is a departure
  from `damage_counters`' container spelling and the departure is the point. A leg naming a field is
  resolved against the real class by `test_snapshot_coverage.py`; a leg naming a container resolves
  as long as the container exists and delegates what is actually compared to `apply_parity._project`,
  where dropping a field is **silent**. `damage_counters` keeps the older spelling: migrating it
  changes what the lane compares and belongs to whoever measures it.
- **`_EVOLVE`'s footprint gains the zone on BOTH sides of the arrow.** It WRITES it (the evolved body
  arrives new in play — measured, `alakazam_9000` f127) and it READS it (§4 is the kind's legality
  input). Declaring the read is what lets `footprints_commute` refuse `[play Basic, evolve it]` for
  the reason the rule gives rather than incidentally via `my_hand_ids`.
- **`_PLAY`'s structural floor gains it as a WRITE**, and so does `_structural_drop`'s Basic-deploy
  sub-case — which is the D4 sentence this amendment corrects. A play's own legality does not depend
  on the bit, so there is no read.
- **`apply_parity`'s DECLARED BLIND SPOTS list loses its first entry**, and
  `test_the_diff_BITES_when_a_transition_is_wrong` grows the sibling
  `test_a_deploy_that_forgets_the_NEW_IN_PLAY_bit_now_bites`. Two tests rather than one union: this
  one proves the lane sees an ALLOWANCE, that one proves it sees a per-BODY bit on the Bench.

### E3. It stays WHOLE-ZONE, and that is a declined widening

`new_in_play` would QUALIFY for `ELEMENT_ZONES` under Amendment D's own criterion — the bit lives on
one body and each transition sets exactly one. It is **out** anyway: joining is a licence, D names its
membership as *"five zones"* and its exclusions as *a condition of the grant*, and a licence is the
developer's to give.

**It costs nothing today, measured rather than assumed.** `_PLAY` is `complete=False`, so it commutes
with nothing at all; two `_EVOLVE`s already collide on whole-zone `special_conditions` (D4's own
recorded narrowness). No `commutes()` or `footprints_commute()` answer in the tree differs either
way, and `test_the_new_in_play_bit_is_ENUMERATED_homed_per_body_and_written_by_both_transitions`
asserts that rather than claiming it. What element-keying would buy is a FUTURE distinction —
`[play Basic A, evolve body B]` provably commuting while `[play Basic A, evolve A]`, the sequence §4
forbids, still conflicts, since `board_delta._play` gives the deployed body the hand card's own
`serial`. Whole-zone refuses both, which is the sound direction.

### E4. Consequences

- **The full 377-trace parity sweep stays clean with the zone compared**, which is the claim that
  matters: the seam was already right about the bit and now the lane can say so.
- **`sc.unhomed()` and `footprints_writing_unhomed()` are still `{}`** — the zone arrived HOMED, which
  `test_the_owed_list_is_empty_because_T1_carried_it` requires.
- **The audit harness can now check a per-body read on the BENCH at all.** `test_snapshot_coverage`'s
  `_resolve` hops `bench` as well as `active`; until this it could only verify a per-body field on the
  Active, which is why bench legs were spelled as containers in the first place.
- **Nothing at runtime moved.** No production caller invokes `apply_option`, and no consumer reads the
  new field yet — Issue #385's composer is the first.
