# ADR-0009: Training methodology — three jobs, dense signals tune, the ladder gates

**Context.** [ADR-0007](0007-learning-is-one-offline-value-model.md) fixed *what* learning
enters (one offline value model); this fixes *how* the tunable surfaces are trained and how
match data is used. Ladder win/loss is the real signal but extremely low-bandwidth — one
noisy bit per ~40 decisions, one config per submission — so it cannot tune many rule
weights directly.

**Decision.** Split "training" into three jobs with three signals:

- **(A) Weight tuning** — the Strategy's Hypothesis weights + params. Score is *additive*
  (`Σ weight_h · fired_h + tactical + value`), hence linear in the weights, so tuning them
  to rank the correct option first is a convex **linear-ranking** fit (structured-perceptron
  / logistic rank): seconds on CPU, fully interpretable. Trained over dense **per-decision
  labels** from three stacking, ladder-gated sources:
  - *winner-imitation* — the winner's move in strong replays (silver; broad);
  - *peer blunder-correction* — human-marked blunders on any replay of **our** deck, ours or
    another team's (gold-ish, our judgement; broad; injects our expertise);
  - *own-Pilot blunder-correction* — human-marked blunders in our agent's own games (gold;
    targets our agent's real error surface; narrow).
- **(B) Value model** — trained separately by supervised replay-mining (`state → eventual
  win/loss`), per ADR-0007.
- **(C) Selection** — ladder A/B is the authoritative gate. It selects which whole config
  ships; it is never the per-weight optimizer.

**Data vs play.** Downloaded replays are the **data engine** (value model + imitation /
correction labels) — a replay is a frozen full-information *film*, ideal to mine. Self-play
is retained for the jobs a film can't do: **evaluation** (only live play scores a changed
policy), **on-policy coverage** (states the meta corpus is thin on), and **producing our
agent's own games** to mine for corrections.

**Rejected.** Ladder win/loss as the weight optimizer (too low-bandwidth). Off-policy
evaluation — scoring a changed policy by re-running downloaded matches (a film can't respond
once our agent deviates). RL / self-play as the primary trainer (ADR-0007).

**Consequences.** A **Correction** `(state, chosen, correct, attribution, rationale)` is the
curated unit of learning: it yields a ranking label and may create/edit a Hypothesis (its
reasoning becomes the Hypothesis `rationale`). One blunder-marking inspector serves both
self-play games and any replay featuring our deck. The default-vs-tuned weight diffs,
Hypothesis `status` transitions, and the correction log together are the documented
experiment trail the Strategy Category scores.
