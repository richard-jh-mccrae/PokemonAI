# ADR-0012: Optimize for the Strategy Category — legible reasoning over leaderboard rank

**Status.** Accepted — the standing goal of the whole repo. It is policy, not code: every later ADR is
written under it (rules backbone, per-decision rationale, one gated learned seam).

**Context.** Two sibling competitions share one ladder: the **Simulation Category**
scores raw win rate; the **Strategy Category** scores the *documented reasoning* behind
the agent — why a strategy was chosen, which hypotheses were tested, demonstrated
understanding of mechanics, strength across matchups, originality, and structured
reporting. The rubric states explicitly that mid- or lower-tier ladder entries can win
the Strategy Category on analysis/originality/structure, and that a high leaderboard slot
does **not** guarantee a Strategy result.

**Decision.** We target the **Strategy Category** and optimize for **legibility**, not
ladder rank. Concretely: a rules-backbone agent (the **Pilot**) that emits a per-decision
rationale, and a per-deck doctrine (**Strategy**) expressed as a registry of named,
testable hypotheses — so the competition writeup is *generated from* the instrumented
agent rather than written about a black box.

**Consequences.**
- A stronger but opaque agent is *worse* for our goal than a slightly weaker, fully
  explainable one. Every layer must be able to say *why* it chose what it chose.
- Chasing the Simulation leaderboard (e.g. heavy RL) is rejected as the wrong axis — and
  the one ladder dataset we have showed RL/MCTS losing to a tuned rule agent anyway (see
  [ADR-0007](0007-learning-is-one-offline-value-model.md)).
