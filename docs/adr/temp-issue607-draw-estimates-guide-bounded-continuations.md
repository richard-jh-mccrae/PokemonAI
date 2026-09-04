# ADR-TEMP-607: Draw estimates guide bounded continuations

Accepted and implemented for Issue #607.

PUCT may continue beyond a simulated shuffle-draw within the same decision budget. Existing bounded
whole-hand Ledger valuation supplies draw-action prior evidence; selected sampled successors receive
Ledger evaluation and may subsequently be expanded by PUCT. No sampled hand receives a separate full
search budget, and completing every sampled continuation is not a prerequisite for returning an action.

Always stopping simulated search at a draw was considered because it bounds continuation cost more
aggressively. It would leave the recognition of every post-draw opportunity to the Ledger's static
assessment. Bounded continuation search preserves the opportunity to investigate those sequences at
the accepted cost of additional, explicitly limited computation and retained state.

Each sampled draw node will use a configurable bounded set of reproducible sample slots. Slots are
selected uniformly from the configured set and resolved only when first requested; repeated selections
may deepen the same continuation. Coalescing equivalent successors preserves slot multiplicity and
leaves unresolved slots selectable. The existing chance identity machinery supplies reproducibility.

This favors depth after drawing over generating a fresh hand on every visit, without requiring a large
upfront batch. A finite set can miss important outcomes, so inspection must support comparisons across
sample counts and seeds. No numerical sample count has been selected. All resolution, evaluation, and
continuation work remains subject to the shared decision limits and bounded state ownership.

The native adapter keeps each sampled shuffle branch inside one bounded worker and routes its later actions
back to that owner. The coordinator receives only legal observations, stable identities, and accounting
evidence; opaque native handles never cross a process boundary. Reproducible sample keys choose bounded
hidden-zone orderings before the native engine performs the shuffle, and repeated requests use the retained
sample result. The offline adapter resumes the same class of bounded sampled successor through its forkable
engine. Both therefore search reachable post-draw actions within the shared decision limits.

Prior evidence alone creates no completed PUCT visits or backed-up returns. Inspection distinguishes
configured sample slots, resolved slots, distinct successor states, and repeat search visits. Repeated
visits do not constitute additional draw samples; observed return variation is not automatically a
calibrated confidence interval. These evidence distinctions follow the accepted accuracy requirement.
State retention follows the accepted [stop-at-cap policy](temp-issue607-puct-operation-limits.md).
Parallel work follows the accepted
[coordinated batch design](temp-issue607-puct-coordinates-reproducible-batches.md).
