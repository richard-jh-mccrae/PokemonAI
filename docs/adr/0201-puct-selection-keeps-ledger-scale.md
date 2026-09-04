# ADR-0201: PUCT selection keeps the Ledger scale

Accepted and implemented for Issue #607.

Initial PUCT selection will use raw Ledger Q values and a configured exploration coefficient, c_puct,
in compatible units. Backup and reporting retain the frozen Ledger Value Scale. The coefficient remains
fixed within a configuration and is recorded with each run; changing it creates a distinct configuration.
Uniform-prior and Ledger-prior comparisons hold this selection configuration constant.

Running normalization by discovered extrema was considered because it can accommodate different score
ranges. It would also change the exploration balance as new extrema appear, adding another moving part
to the initial quality investigation. Fixed units keep that balance directly inspectable at the accepted
cost of calibrating exploration strength against the Ledger's score range. No numerical coefficient has
been selected; normalization can be evaluated later as an explicitly different experiment.

An unvisited action uses the current node's Ledger value as a selection-only starting reference. Its
recorded visit count remains zero and Q remains absent until a completed valid backup supplies evidence;
the reference introduces no synthetic visits or accumulated return. This keeps prior-guided allocation
active without an obligatory first visit to every admissible action at each branching node. Some actions
may remain unvisited under finite limits, and inspection output must preserve that distinction.
