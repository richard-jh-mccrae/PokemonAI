# ADR-0138: Exact frontier identity precedes continuation-aware admission

Status: Accepted for production activation by developer request (Issue #496, 2026-08-10).

## Context

Composer applied a per-parent top-k cutoff and then a second depth-wide cutoff. Distinct action
orders could execute to the same modeled future while still occupying separate frontier slots, and
an enabling action was ranked only by its immediate leaf even when one additional modeled action
made its value visible. The existing subset lattice removes only permutations inside one open,
footprint-proven commutative block; it deliberately cannot merge conflicting orders before both
transitions execute.

## Decision

`state_model.semantic_state_key` is the one versioned exact modeled-state identity. It canonicalizes
the complete source `current` tree without dropping unknown keys, alpha-renames engine serials by
visible location while preserving identity relationships, and includes carried state, known prize
fidelity, both turn-boost streams, transient generation, and `state_value.registry_identity()`.
Unresolved identity and non-finite state fail closed. `snapshot_coverage.WRITABLE` has an explicit
mapping gate, so a new zone cannot silently miss the key.

`composer.frontier_key` adds the remaining legal serial-free semantic option classes, remaining
depth, and decision-boundary context. Hidden or unresolved option identity makes that node
unmergeable. Equality is the full canonical tuple; hashes are indexing only.

Each depth now has one continuable-frontier pipeline: generate every legal transition, emit existing
terminal/reveal/refusal candidates, exact-deduplicate continuable children, compute an admission
estimate on the unique children, and apply one global top-k-plus-epsilon cutoff. Conflicting orders
both execute before their equal results may merge. Differing open-block histories merge with the
block reset, conservatively restoring a continuation superset. Every semantic and raw origin remains
in deterministic provenance; the representative is the smallest semantic path.

The admission estimate is the better of stopping and exactly one additional action through the
same `_rank`/`_one_ply` transition machinery. CHOSEN uses its existing maximum, DEALT its existing
expectation, reveal its ADR-0129 continuation, and refusal contributes nothing optimistic. The
estimate changes frontier admission only, never `Candidate.score` or final selection. Ranked
transitions cache by the exact frontier context and are reused when the retained child expands.

`compose_reference` runs the same transition and Candidate core without beam/epsilon or continuation
admission, under explicit depth, transition, unique-node, and optional wall caps. Any cap, refusal,
or coverage gap reports `UNKNOWN`; deterministic tests omit the wall cap.

## Consequences

### Required negative gate result

The policy is implemented behind `compose(..., exact_dedup=True,
continuation_admission=...)`, and both switches now default on. The committed 383-frame corpus replay
of dedup-only `4/4/0.005` composed 286 frames with ruled agreement `90/277`, while P50/P95/max were
`0.328/4.559/59.867 s`. P95 exceeds both the committed `0.40–0.43 s` ceiling and the grader's `3 s`
per-decision floor. The run generated 3,431 deferred-target instances and 3,601 expectation nodes;
this is a real depth-wide generation cost, not an error or a reason to raise the ceiling.

On a completed bounded reference for real frame `83686860|1|decision|29`, continuation changed one
admission but did not change the selected `[4, 0]` plan or reduce first-action miss/regret. The
dedup-only row also changed that frame's ruled agreement from one to zero. Thus neither the
continuation-benefit gate nor the no-regression/runtime default gate passed. The defaults are
nevertheless enabled by explicit developer direction; the runtime evidence remains recorded here
for follow-up tuning.

The PR #502 Mega probe confirms the semantic rule that duplicate Wally copies are interchangeable:
current-path alpha normalization collapses the six depth-two continuable nodes to three exact
frontier states. The earlier 6→4 observation distinguished duplicate Wally engine identities and is
therefore not a valid acceptance target under the serial-independent identity contract. No
card/frame exception or raw-serial discriminator is used.

OEC, `Footprint`/`footprints_commute`, the subset lattice, expectation parent-slot accounting,
ADR-0128 score flooring, ADR-0129 reveal EV, ADR-0131 tie defer, refusal semantics, and terminal
dominance remain authoritative. `transposition_probe._bodykey` remains offline and lossy and is not
imported by runtime. Combat profiles and NeedGraph remain value consumers, never state-key material.

Diagnostics advance once and distinguish immediate rank from admission rank/score, report
generated/unique/merged/unmergeable counts and block resets per depth, retain all origins, and expose
the exact key schemas and value-registry identity. Composer Lab owns the baseline, dedup-only,
continuation, budget, epsilon, reference, and predeclared SHA-256 holdout matrix.

No card, deck, frame, mechanic-value, or sequence exception is introduced. PR #490's Wally/bounce
and hand-refresh bypasses remain unmerged; independently owned information ordering, lethal, literal,
and sound mechanic rules remain live.
