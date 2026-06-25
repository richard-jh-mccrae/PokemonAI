# ADR-0017: Corrections compile to Hypotheses via the Tuner — attribution derived, Tier-0 now, fan-out

**Context.** The blunder inspector emits **Corrections** ([ADR-0015](0015-correction-schema.md));
[ADR-0009](0009-training-methodology.md) fixed *that* they tune Hypothesis weights (Job A) and
*may* author a Hypothesis, but not *how*. Marking blunders is **manual and expensive**, so each
Correction must yield the maximum reusable signal.

**Decision.**

- **`attribution` is derived, never hand-written.** The **Tuner** replays the Pilot on the
  Decision and diffs which Hypotheses fire for `correct` vs `chosen`: they **differ** →
  `hypothesis:<id>` (a weight fix, route **W**); **identical** → `missing_hypothesis` (a new rule,
  route **H** — *principled*: no weight can reorder identical feature sets); the gap is **combat**
  → `tactical`.
- **The Correction embeds the agent `obs`** (int-enum, hidden-info — the Pilot's exact input)
  alongside the full-info film `current` (human display). The Pilot can't read the film's
  string-enum form, so featurization needs `obs`. Embedding makes the Correction self-contained
  (tunes even after the replay is discarded) at **identical accuracy** to re-deriving from the
  replay.
- **Fan-out — one Correction, many signals.** A Tier-0 **ranking label** (fit `tuned.json` weights
  by convex linear-ranking, ADR-0009); a proposed **Hypothesis** when `missing_hypothesis` (it
  generalizes the *whole class* — the highest-leverage output); and a Hypothesis **status**
  transition (`assumed→confirmed/refuted` — the writeup trail). *A weight tweak fixes a point; a
  new Hypothesis fixes a class.*
- **v1 scope:** Tier-0 weight labels + **assisted** Hypothesis authoring (the Tuner proposes
  id/rationale/seed and a trigger sketch; a human commits the executable `when()`) + status
  transitions. All no-engine.
- **The ladder A/B (Job C) is the only ship gate;** the Tuner never self-validates.

**Considered / rejected.** Re-deriving `obs` from the replay each run (no accuracy gain, and
replay-dependent — against ADR-0002's "survives deletion"). Auto-writing executable `when()`
unreviewed (correctness/safety). Counterfactual rollout on a film (ADR-0009: a film can't respond
once we deviate).

**Deferred** (see [docs/blunder-tuner.md](../blunder-tuner.md)). Tier-1 **value-model preference**
labels `V(after-correct) > V(after-chosen)` — the value model doesn't exist yet (Job B), and
`after-correct` needs a one-step engine apply (clean mid-turn, murky for turn-enders); the
Correction is designed Tier-1-ready so no data is lost. Whole-game regression; auto-propagation to
similar decisions (precision risk).

**Consequences.** The Correction schema gains an `obs` field ([ADR-0015](0015-correction-schema.md)
amended; backfill existing records from the retained replays). The highest-leverage output is a
generalizing Hypothesis, not a weight nudge. Each blunder does double duty: an agent fix **and**
documented experiment evidence the Strategy Category scores.
