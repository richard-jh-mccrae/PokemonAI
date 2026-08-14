# Family-ranked Bellman search implementation specification

Status: attachment vertical slice implemented 2026-08-14; ordering, widening, and adaptive clock
remain shadow-disabled after the newest correction corpus blocked activation.

## Objective

Keep successor-state Bellman value as the sole decision value while using mature local equations to
decide which sibling choices receive search work first. A clear local winner is searched first; close
competitors widen promptly; no learned or authored score permanently deletes a legal line.

The first production slice covers attachment families, fair search waves, deterministic plan reuse,
adaptive planning epochs, complete parameter reporting, and training-ready telemetry. Later families
reuse the same contracts.

## Authority and non-goals

- `BoardPotential` and `ValueOracle` remain the only strategic utility owners.
- A Family Score schedules search only. It is never added to Bellman value.
- `ProductionSolver` owns wave admission, equal work, refinement, and deadline behavior.
- `BellmanRuntime` owns match-scoped Plan Suffix validation and reuse.
- `Strategy` supplies deck-authored profile adjustments, not executable deck policy.
- The legacy `common.deciders` mixin graph and sequence overrides do not return.
- The future coefficient learner's objective, algorithm, and training cadence are deliberately deferred.

This changes ADR-0139's equal-probe allocation rule without changing its one-Bellman-policy rule. The
implementation must record that architectural amendment when it ships.

## Pilot Profile

Create one typed `PilotProfile` as the canonical registry for every behavior-changing Pilot parameter.
Each parameter belongs to exactly one group:

- value equations;
- family ranking and tie margins;
- search waves and node allocation;
- planning clock;
- belief and hidden-information sampling;
- deterministic plan reuse;
- scouting and matchup posture;
- diagnostics and telemetry.

Every definition carries a stable field name, default, bounds, units, learnability, and owning group.
Equations consume typed fields. They may not contain fallback literals or private adjustable constants.
Rules facts and hard safety bounds remain code-owned, read-only values and appear separately in reports.

Resolve each adjustable parameter as:

```text
global learned value
+ deck-specific learned adjustment
+ authored deck adjustment
= effective value, clamped to its declared bounds
```

Until learning exists, the global learned layer is the authored global default and learned adjustments
are zero. A future strategy-profile version may scope deck learning; exact deck-list equality must not
discard useful deck knowledge after a small list edit. This versioning mechanism is deferred.

Unknown, duplicate, out-of-bounds, or missing required parameters fail packaging and runtime startup.
The submitted profile is immutable for a match. Online learning is prohibited.

## Starting equation values

Use commit
[`b4ddaf6`](https://github.com/richard-jh-mccrae/PokemonAI/tree/b4ddaf602f5110b5bb1349f7b1a7e9e09302eead/src/common)
as the starting source for mature bespoke equation behavior.

Classify every old constant before porting it:

- strategic magnitude becomes a named tunable coefficient;
- tie or admission threshold becomes a named tunable search parameter;
- card or rules fact remains untunable;
- mathematical cap or safety bound remains code-owned;
- sequence override is rejected.

The starting profile must preserve the old equation inequalities and ranking fixtures before learning or
deck adjustment changes them.

## Action Family contract

At each state controlled by our actor, assign every legal action to exactly one Action Family. Initial
families include attachment, evolution, deployment, promote/retreat, healing, denial, snipe, discard,
fetch, and attack. An action with no ranker forms an unclassified singleton and enters the first wave.

A family ranker is pure. It receives the current immutable state, legal sibling actions, current facts,
and resolved Pilot Profile. It returns, per candidate:

- canonical action identity;
- raw named features;
- coefficient contributions;
- Family Score;
- scored or abstained status;
- gap from the family leader;
- admission wave and explanation.

Family Scores compare candidates only inside one family. A scorer missing required facts must abstain.
An abstained candidate remains in the first wave, and no scored candidate may cause it to be deferred.

Rankers rerun at every hypothetical decision state. They therefore may prefer Water Energy before Wally
and Ignition Energy after Wally without becoming a global sequence policy.

## Attachment family

Port the pure feature math from the old attachment equation. Preserve its axes:

```text
attack axis = max(immediate attack, persistent build, acceleration route)
attachment score = attack axis
                 + retreat equity
                 + ability fuel
                 - evaporation loss
                 - renewable-resource tie cost
```

Typed Energy provision, survival, role eligibility, spent utility, overkill, ability fuel, and end-turn
discard are card/rules-derived features or gates. Their strategic magnitudes live in the Pilot Profile.
Hand and resource opportunity costs already owned by Bellman value must not be added to Bellman again.

Do not port `_attach_sequence_override`. The ranker answers only "which attachment first?" Bellman still
answers "attachment, Wally, retreat, attack, or something else?"

## Structural pruning

Permanent pruning is a separate layer from family ranking. It accepts only explicit proofs:

- identical semantic successor state;
- legal choices already established as equivalent;
- established commutativity;
- mathematical dominance independent of any adjustable coefficient.

Every prune records its proof type and retained representative. A large Family Score gap is never proof.
If proof construction fails, retain the candidate.

## Search waves

Production search proceeds in completed rounds:

1. Apply Structural Prunes.
2. Build Action Families and score them cheaply.
3. Admit each family leader, every singleton, and every abstained candidate.
4. Give the admitted wave equal shallow work.
5. Admit near-tied runners-up in tunable, deterministic batches.
6. Give each newly admitted batch equal shallow work.
7. Deepen the strongest Bellman results only after required shallow waves complete.
8. Admit distant candidates when uncertainty and remaining budget justify it.

Exact-equivalent successors collapse before near-tie batching. No arbitrary fixed "top two" limit may
discard a larger genuine tie set. Family tie margins, batch sizes, shallow work, uncertainty admission,
and refinement work are named Search Profile parameters.

If a deadline interrupts a round, that partial round cannot determine the action. Return the incumbent
from the last completed fair round. The cheap all-family evaluation is round zero, so an incumbent always
exists. Prefer node/work quotas for reproducibility; wall time remains the emergency ceiling.

## Plan Suffix

The solver returns the chosen first action plus the deterministic principal continuation up to the next
Information Boundary. Each suffix step stores:

- expected semantic state key;
- expected legal-menu digest;
- canonical next action identity;
- Pilot Profile hash;
- turn and acting seat.

On the next callback, `BellmanRuntime` rebuilds the observed state. If every guard matches and the action
remains legal, execute the cached action without planning. Any mismatch discards the suffix and starts a
fresh Planning Epoch.

Draws, reveals, coin outcomes, opponent control, turn end, changed hidden-information knowledge, or
profile changes are Information Boundaries. Deterministic effect-selection callbacks are not boundaries
when their predicted state and legal menu match exactly. A suffix never survives into the opponent's turn.

## Planning clock

A fresh Planning Epoch receives a tunable wall-clock allowance derived from `remainingOverageTime`.
The initial Clock Profile is a piecewise-linear curve with named, tunable anchors:

```text
600 seconds remaining -> 30-second epoch
200 seconds remaining -> 15-second epoch
140 seconds remaining -> 10-second epoch
near exhaustion       ->  2-second emergency epoch
```

Interpolate between anchors. A validated Plan Suffix receives no search allowance. A new callback alone
does not create a fresh epoch; an Information Boundary or validation failure does. The external callback
watchdog remains a read-only safety bound, not a strategic parameter.

## Failure behavior

- Invalid profile: fail build or startup.
- State-specific scoring gap: abstain and search broadly.
- Unexpected scorer exception: record the fault and disable that family for the match.
- Structural-proof failure: retain the candidate.
- Plan Suffix mismatch: discard it and replan.
- Deadline: return the last completed-round incumbent.

No optimization failure may delegate to legacy policy or crash an otherwise legal match decision.

## Submission manifest and brief

The submission manifest contains the complete immutable Pilot Profile and its hash. `brief.html` renders
collapsible sections matching the profile groups. Each adjustable parameter shows:

- stable name and owning family;
- global value;
- deck-learned adjustment;
- authored deck adjustment;
- final effective value;
- bounds, units, and snapshot provenance.

Highlight non-global values and summarize how many parameters the deck customizes. Include read-only
safety bounds in their own section. Extend `brief.csv` with typed parameter rows so automation sees the
same data as the HTML. The manifest is the source; both renderers are projections.

## Telemetry contract

Decision telemetry records family candidates, raw features, weighted contributions, score gaps, tie
margins, admission waves, abstentions, final Bellman values, Structural Prunes, completed rounds, Plan
Suffix hits, and invalidation reasons.

The full profile appears once in the submission manifest. Per-decision telemetry carries its profile hash,
not a repeated coefficient table. These records preserve future training inputs without choosing a future
learning objective.

## Implementation sequence

### 1. Profiles and reporting

- Add typed profile schema, resolution, validation, hashing, and grouped metadata.
- Add deck-authored adjustments to `Strategy` without reusing its untyped `params` map.
- Extend submission manifest, HTML, and CSV projections.
- Move current adjustable solver/planner constants into the registry without changing behavior.

### 2. Family substrate

- Add pure family classification, score, abstention, and diagnostic records.
- Add the separate Structural Prune proof interface.
- Run rankers in shadow while preserving current search allocation.

### 3. Attachment port

- Port attachment feature math from `b4ddaf6` into the pure family interface.
- Convert strategic literals into typed profile fields.
- Port old band and corpus cases as ranking fixtures; exclude old sequence overrides.

### 4. Fair waves

- Replace equal probing of every root action with family leaders, abstentions, and singleton coverage.
- Add near-tie batches, completed-round publication, and Bellman-only refinement.
- Apply the same mechanism at every own-actor hypothetical state.

### 5. Deterministic continuation

- Expose the deterministic principal continuation from the solver.
- Validate and execute Plan Suffix steps in the match-scoped runtime.
- Replan only at Information Boundaries or validation failures.

### 6. Adaptive clock and telemetry

- Replace the fixed planning ceiling with the Clock Profile curve.
- Emit complete family, wave, profile-hash, and suffix telemetry.
- Ensure malformed or oversized telemetry cannot corrupt collection.

### 7. Family rollout

After the attachment slice passes, port evolve, promote/retreat, deploy, denial, snipe, healing,
discard/fetch, and attack equations one family at a time. Each family advances through shadow, ordering,
and widening gates during development; stages need not be separate releases.

## Test and CI requirements

Add executable contracts for:

- profile layering, bounds, hash stability, schema completeness, and unknown-key rejection;
- absence of adjustable literals outside the registered profile;
- manifest/HTML/CSV equality and collapsible grouped rendering;
- exclusive family membership, singleton coverage, and abstention safety;
- Family Score never entering a Bellman ledger or final value;
- Structural Prunes requiring a coefficient-independent proof;
- fair shallow waves, near-tie batching, and last-completed-round deadline behavior;
- attachment rankings and old inequality fixtures;
- root Water preference and post-Wally Ignition/Water near-tie handling for episode 92717347 frame 83;
- exact Plan Suffix validation and every Information Boundary invalidation;
- Clock Profile anchors, interpolation, emergency behavior, and callback watchdog separation;
- scorer fault isolation and broad-search fallback;
- telemetry schema, profile joining, and collection of large records;
- exact native bundle packaging with no legacy decider or policy fallback.

CI runs focused unit tests, the complete Bellman/submission suite, the Mega Starmie correction corpus,
recent replay latency comparison, and the exact native five-match mirror gate.

## Activation gates

The attachment slice may widen production search only when all conditions hold:

- no regression on accepted correction rulings;
- episode 92717347 frame 83 still chooses Wally;
- its root attachment family searches Water first;
- after Wally, Ignition is searched first and near-tied Water is admitted next;
- deterministic suffix callbacks validate and execute without replanning;
- fresh epochs respect the resolved clock curve;
- cached continuation callbacks are effectively immediate;
- recent Mega Starmie replays show measurable branch and latency reduction;
- telemetry remains complete and well-formed;
- native packaging and mirror gates pass.

Correctness blocks activation regardless of speed.

## Deferred decisions

- Learning objective and optimizer.
- Training cadence beyond offline immutable snapshots.
- Strategy-profile versioning for deck-learned adjustments.
- Automatic promotion thresholds shared by every future family.
- Porting families beyond attachment before the vertical slice is accepted.
