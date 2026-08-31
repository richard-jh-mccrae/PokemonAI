# ADR-0194 — Corrections grade the exact one-ply Ledger boundary

Status: Accepted.

## Context

Deployment latency limits were truncating correction evidence. Compound actions also exposed
choices after the initiating action, so grading only the first menu confused initiation,
discard, fetch, and promotion errors. Continuing through another independent MAIN action would
instead price the rest of the turn and stop being one-ply evaluation.

## Decision

Corrections use an exhaustive compute profile with no inner wall-clock cutoff. Deployment keeps
its bounded profile. Search resolves required non-MAIN follow-up menus and stops at the first
return to MAIN. The resulting board is the compound action's successor; no later independent
MAIN action enters its value.

Hand value is the best feasible portfolio under shared turn resources, not the sum of mutually
exclusive options. Correction artifacts preserve the original committed choice separately from
the current choice and grade only complete pairwise values at the correction's exact locus.

The initial seed review raises hand-zone worth: retaining payment and discard material must
remain preferable to throwing it away when a search has no live target.

## Consequences

Ultra Ball may be corrected at play, discard, or fetch, with each locus receiving its own margin.
Incomplete candidates remain visible but cannot become training examples. Value audits expose
feature contribution differences, coverage gaps, break-even proposals, conflicts, and prior
preference violations. Weight adoption is rejected whenever an accepted preference regresses.

## Addendum 2026-08-28

Correction grading prices every candidate as expected successor value minus root value; the
Turn-End Counterfactual is only End's successor. Hand opportunity value is credited on use only
when that action realizes its selected Feasible Option Portfolio entry;
discarded payment receives no credit. Pokémon development uses shared-resource feasibility rather
than independent line sums. Corrections must obey the Anchor prompt's selection cardinality;
multi-MAIN sequences belong in turn-scope evidence.
