# ADR-TEMP-607: PUCT tree reuse is configurable

Accepted and implemented for Issue #607.

One boolean configuration switch will select fresh trees or verified tree reuse in the same PUCT engine.
Fresh mode starts a new tree after each actual decision. Reuse mode may retain a matching subtree only
when state, legal knowledge, behavior identity, horizon, and resource ownership prove compatibility;
otherwise it starts fresh and records why reuse was unavailable. No default mode was selected here.

Both modes are needed for inspection: fresh trees make each decision's search evidence self-contained,
while verified reuse preserves useful earlier effort at the cost of more complex evidence attribution
and lifecycle management. The switch changes reuse policy, not priors, evaluation, or admissibility.

Run records will identify the configured mode and actual reuse outcome. Inherited visits and newly
completed visits remain separate in diagnostics, and earlier computation is never reported as new work
or charged again as new elapsed time. Retained resources still occupy the configured capacity; reuse
cannot reset their accounting or retain handles after their owner is released. The accepted stop-at-cap
policy remains in force. Verification will cover both modes, compatibility rejection, accounting, and cleanup.

Verified inherited evidence may satisfy the inspection profile's simulation floor when it contains a
completed backup supporting a currently legal root action. Search still attempts further work within
its limits, but ordinary exhaustion before another simulation finishes may return a move from that
evidence. Diagnostics explicitly report zero new completed simulations in this case. The floor requires
valid search support, not repeated computation; the accepted cost is committing a move without further
analysis at its actual decision point.
