# ADR-0200: PUCT uses separate operation limits

Accepted and implemented for Issue #607.

One PUCT decision will share separate limits for transitions, chance realizations, and evaluator calls,
including prior preparation and work performed by every worker. Retained states and outstanding tasks
will have separate caps; hard deadlines will contain variable operation, preparation, and transport costs.
Play, analysis, and evaluation will supply these limits through declared profiles of the same PUCT engine.

Separate limits make each work ceiling directly verifiable without maintaining exchange rates between
unlike operations. A weighted allowance would permit more flexible allocation, but its conversion weights
would become another behavior requiring measurement and versioning. The accepted cost is additional
counters, configuration, and explicit reservation accounting across preparation and worker stages.

When the selected traversal requires an operation whose allowance is exhausted, the decision stops new
traversal and returns its best-known action from completed valid backups after handling outstanding work
within the deadline. This is ordinary budget completion, distinct from initialization degradation or a
runtime failure. The design does not redirect traversal toward cheaper paths solely to spend remaining
allowances: doing so would introduce a resource-dependent allocation policy into the root visit counts.
Unused allowances are an accepted cost of keeping that selection behavior explicit and verifiable.

Reaching the retained-state cap also stops new search work and returns the best action supported by
completed simulations after settling outstanding work within the deadline. Capacity is reserved before
creating states; owned states are released when their search lifecycle ends. The initialization evidence
floor still applies. This makes memory exhaustion an explicit, ordinary search stop rather than silently
changing exploration through eviction and reconstruction. The accepted cost is leaving other allowances
unused; generous inspection limits can later be adjusted from measured state use and stopping reasons.

The initial inspection profile requires one valid leaf evaluation and completed simulation backup before
committing a move. If the budget expires before that evidence exists, initialization is degraded and the
review run stops with an explicit diagnostic. A prior-only move would obscure whether the reviewed choice
was produced by PUCT. Once that minimum is met, ordinary budget exhaustion may return the best searched
action and the match continues; neither exhaustive turn coverage nor equal root coverage is required.
With [verified tree reuse](0204-puct-tree-reuse-is-configurable.md), inherited completed backups
supporting a currently legal root action may meet this floor even when no new simulation finishes.

An actual decision with exactly one legal action before admissibility filtering may execute immediately,
without meeting the simulation floor. Record it as a forced move with zero new simulations. There is no
choice to improve at that point; avoiding redundant search is worth giving up additional preparation for
the following decision. Effect-resolution menus with multiple legal actions still require search, and
forced transitions inside a simulated path still consume the shared budget.

Initial manual inspection will use generous finite limits, informed by decision timings, with memory and
runtime containment. One completed simulation is a minimum evidence floor, not a quality certificate.
This acceptance applies to the initial inspection profile; zero-simulation behavior in other profiles is
not decided here. The review-run integration remains owned by Issue #659.

Hard engine, evaluator, search, or worker failures stop an inspection match, even when earlier completed
evidence exists. Preserve the decision input, seed, configuration, valid partial statistics, and typed
error for reproduction; cancel and clean up outstanding work. Continuing through a recovery move would
change the trajectory under review, so an unfinished match is the accepted cost of making failures
actionable. Ordinary budget completion and the approved typed uniform-prior fallback still permit play
to continue. The search result exposes the failure; Issue #659 consumes it to stop the review run.

In Ledger-prior mode, guidance will be requested at the root and every newly expanded branching decision
through the existing Policy Model contract, using reusable candidate evidence where available. Root-only guidance
would leave deeper sequencing choices without the Ledger's policy hints. Guidance throughout the turn
is preferred for manual quality inspection despite the additional preparation cost, which remains charged
to the shared decision limits. Non-comparable candidate evidence uses the typed whole-roster uniform
fallback established by [ADR-0199](0199-policy-models-consume-priced-candidate-evidence.md).

Prior preparation will have per-node and cumulative decision allowances inside the shared operation limits.
Exhausting a preparation allowance ends that optional preparation and uses the typed uniform fallback when
the roster lacks comparable evidence; exhausting an overall operation limit still stops search. Initial
inspection gives preparation and search generous finite caps with headroom, rather than tuning tight limits
before representative matches and decision timings exist.

Initial offline inspection compares uniform-prior and Ledger-prior PUCT with the same frozen Ledger leaf
evaluator. The priority is completing matches with faithful decision evidence for manual review and later
improvement. Recorded inputs, seeds, effective configurations, prior source/fallback, completed work, and
stopping reasons must make these runs interpretable and reproducible.

Decision timing will distinguish prior preparation from search work and show total elapsed decision time
with initialization, worker/transport, and reporting overhead accounted for. Prior preparation includes
candidate pricing and normalization wherever they occur in the tree, not just root initialization.
Concurrent stage/worker totals must be labeled separately from elapsed time so overlapping work is not
presented as an additive wall-time breakdown. Cached work is attributed when performed, not charged again
when reused. These records support later tuning without mistaking missing or duplicated cost for progress.

Concurrent reservations and interrupted work follow the accepted
[coordinated stage design](0203-puct-coordinates-reproducible-batches.md).
The numerical limits used in the discussion were illustrative, not accepted defaults. Initial numerical
tuning remains subject to representative measurements under the accepted generous inspection policy.
