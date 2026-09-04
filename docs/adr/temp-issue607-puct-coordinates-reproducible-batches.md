# ADR-TEMP-607: PUCT coordinates reproducible batches

Accepted and implemented for Issue #607.

One coordinator will own PUCT statistics and decision-wide budgets, select numbered batches of search
work, and apply completed valid backups in a deterministic order. One bounded worker facility executes
the work. Batch size is an explicit configuration value independent of worker count; workers provide
parallelism without multiplying the decision's allowance or owning independent full root searches.

Batching permits parallel continuation work beyond the preparation available inside a single sequential
simulation. The accepted cost is delayed feedback: completed evaluations cannot revise earlier choices
within that batch. Batch size therefore belongs to behavior identity and experimental comparisons.
Batch size one supplies the serial reference; larger batches are separately configured experiments.

While selecting a batch, the coordinator will track pending visits separately and include them in
exploration counts without changing the branch's value estimate. Completed N/W/Q change only through
valid backups; settling or cancelling work releases its pending counts exactly once. This accounts for
effort already assigned without introducing a temporary value penalty requiring calibration in Ledger
units. A strongly valued branch may still receive multiple tasks within one batch, an accepted cost of
preserving the distinction between scheduling effort and observed outcomes.

The same configured structural experiment must reproduce across worker counts through logical task,
sample, and reduction identities. Deadline-limited runs may complete different work and must say so.

The coordinator will reserve shared operation and capacity allowances before admitting each bounded work
stage, in fixed logical task order. Workers return stage results before receiving further grants.
Stage admission and reduction must be independent of worker completion order; workers cannot spend beyond
their grants or obtain a fresh decision budget. This keeps enforcement and structural replay verifiable
at the accepted cost of additional communication and waiting, both included in overhead accounting.

Interrupted batches retain complete, valid simulation results accepted before the decision closes,
reduced in logical task order. Unfinished simulations contribute no visits or values; late results cannot
change a closed decision. These consequences follow the accepted anytime and evidence requirements.
Hard failures preserve valid partial evidence for diagnostics and stop inspection as already agreed.

Native shuffle continuations add worker affinity to this facility. An affinity binds later work for one
sampled engine branch to the worker that owns its opaque handle. Fixed logical dispatch order still governs
admission and reduction; affinity may leave another worker idle rather than transfer ownership. The
coordinator tracks retained native states per affinity and reports their decision-wide total and peak.
Worker teardown releases the current total before final evidence is built; the peak remains recorded.

Reservations and performed work remain distinguishable. Release only allowances proved unused; completed
or attempted work remains accounted for even when it produces no backup. Cancellation releases pending
visit counts and closes owned work without fabricating completion. These accounting invariants prevent
interrupted or parallel work from silently exceeding the decision's limits.
