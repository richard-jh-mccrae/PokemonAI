# ADR-0008: The Pilot is a layered rules pipeline; decks plug in a declarative Strategy

**Context.** Per [ADR-0012](0012-optimize-for-strategy-category.md) we optimize for
legibility, and per [ADR-0007](0007-learning-is-one-offline-value-model.md) learning is one
deferred value-model seam — so the agent's backbone is rules. We want one decision
architecture every deck-agent reuses, where a new deck contributes as little code as
possible and everything it does contribute is explainable.

**Decision.** Every agent runs one shared **Pilot** pipeline (`common/`):
`Sense → Plan → Score → Act` on each `agent(obs)` call (the engine enumerates legal
options; the Pilot returns indices).
- **Sense** — summarise the Observation into features, including the Scout's **Read**.
- **Plan** — pick the current-turn mode from a closed set (`SETUP / RACE / STABILIZE /
  CLOSE`) via shared logic parameterised by the Strategy's win-condition-readiness predicate.
- **Score** — score each legal option two ways: declarative **Hypotheses**
  (positional/strategic boosts) and a shared, Search-backed **Tactical Evaluator** for
  combat (enumerate attacker × attack × target; outcomes computed by the engine, not
  hand-coded). Hypotheses *bias* the evaluator.
- **Act** — return the top-`maxCount` options.

The deck supplies only a declarative **Strategy** (`agents/<deck>/strategy.py`): structured
sections — `lines` (win-condition paths + readiness), `roles` (a closed per-deck **Role**
overlay on the universal **Function Tags**), `params` (tunables), and `hypotheses` (named,
weighted, status-tracked, rationale-carrying). No imperative control flow unless forced —
code hooks are a last resort.

Cross-cutting:
- **Posture** — how the Read changes play: a deck-agnostic generic core in the Pilot
  (seek targets, avoid threats, calibrate aggression to favourability) + deck-specific
  Read-conditioned Hypotheses, all **confidence-gated** by the Read.
- **Search budget** — a tunable (`search_budget`, default `0` = no lookahead): Tier-0
  closed-form by default, Tier-1 Search on escalation, under a hard per-move budget with a
  legal fallback (never crash/time out).
- **Tunables** — data only (Strategy `params` + Hypothesis weights); shared Pilot defaults
  overridable per-deck; a separate machine-written overrides file merged at load.
- **Legibility** — every decision emits a one-line rationale (card → tag/role → Hypothesis
  → Plan); the writeup is generated from this, not written about a black box.

**Considered options.** A learned-policy backbone (rejected — see ADR-0007: runtime +
legibility). Per-deck imperative agents like `demos/rules-based-lucario.py` (rejected:
magic numbers, hard-coded card IDs, no reuse / tunability / legibility across a growing
roster of agents).

**Consequences.** A new deck is mostly *data* (a Strategy), not code. The shared pipeline
is the reusable asset and the writeup's backbone. Combat correctness comes from the engine;
positional judgement from Hypotheses now and the Base Value Model later — both behind the
Score interface.
