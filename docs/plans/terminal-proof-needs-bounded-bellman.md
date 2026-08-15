# Terminal-proof, Needs-bounded Bellman decision record

Status: accepted.

## Decision

Normal-turn planning uses this precedence:

```text
guaranteed same-turn Terminal Proof
-> recipient-specific Needs and exact Odds
-> admissible branch pruning
-> bounded Bellman search
```

Pregame declarations and mandatory engine selections remain outside that pipeline.

## Why Terminal Proof remains separate

Winning is the terminal objective, not one Need among several. A heuristic Need can rank promising
preparations, but it cannot safely trade a guaranteed win for development value. Terminal Proof
therefore runs first and owns any verified same-turn win. It shares the authoritative transition
algebra with Bellman; it does not restore the deleted Goal Ladder, tactical scores, or a second rules
model.

The proof obligation is universal over uncertainty: every positive-probability chance outcome and
every opponent choice must still win. Our choices are existential. Unknown or analytically sampled
hidden information cannot prove a win. Proof locks are semantic, turn-scoped, and invalidated by any
state, menu, seat, profile, or proof-identity mismatch.

This preserves the useful contract of the former lethal solver while removing its duplicated combat
and card-rule machinery. It also covers recovery-first wins that the former MAIN-only generator could
not own.

## Why Needs changes bounded decisions

A Need names one recipient, one capability, and one slot. This prevents a tutor, Energy, evolution,
or heal from gaining value for an unrelated body. Mutually exclusive attacks remain alternative
plans; their value is never combined in actual utility. A fetch with no reachable target has no
current Need coverage.

Needs and exact access Odds schedule useful branches first. They do not enter Bellman utility. Their
second role is to supply an optimistic remaining-opportunity ceiling:

\[
Q_U(s,a)=\Delta V(s,a)+U(s')+\sum \text{remaining achievable Needs}
\]

An executable continuation supplies the lower bound. The search may delete a branch when:

\[
Q_U(s,a)\le \max_b Q_L(s,b)
\]

Equality is safe only when the optimistic decision-count and canonical tie-break also cannot beat the
incumbent. Unknown facts yield an infinite upper bound. A node or width cap cannot invent a zero lower
bound; only a resolved legal continuation may become an incumbent.

## Proof obligations

- A reported Terminal Proof reaches the native win result in the current turn under every represented
  uncertainty.
- Every prune preserves the complete Bellman optimum and records its executable incumbent and
  optimistic bound.
- Need assignment never reuses one resource, recipient, typed slot, fetched target, or mutually
  exclusive attack plan.
- Runtime telemetry distinguishes proof creation, replay, invalidation, abstention, bound pruning, and
  unknown evidence without feeding those diagnostics back into policy.
- The correction corpus, native artifact, package, and mirror latency gates remain release blockers.

The implementation and executable inventory live in `src/common` and `tests/bellman`; this record owns
only the ordering, safety argument, and proof obligations.
