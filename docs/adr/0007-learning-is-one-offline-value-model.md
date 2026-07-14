# ADR-0007: Learning enters as one offline, replay-trained general value model gated by the Read

**Status.** Accepted — the one-learned-seam principle holds and the seam was built as
[ADR-0042](0042-base-value-model-is-a-dependency-free-logistic-over-objective-features.md), but it
ships **armed-off** (`value_model` is `PROFILE=False` in `src/common/runtime.py`). The LightGBM model
class named here was superseded by a dependency-free logistic; a v2 is planned in ADR-0053.

**Context.** We want "intelligence through training" to *reinforce* a rules backbone
without becoming the backbone. The runtime is CPU-only, no GPU, no internet, ~10-minute
match bank, and grader processes don't persist state across matches — so all learning
must happen **offline** (mine replays → retrain → resubmit), and inference must be cheap.

**Decision.** All learned intelligence enters through **one seam**: a single
**deck-agnostic value model** — `state → P(win)`, trained supervised on mined replays
(label = eventual winner), shipped as a file, loaded once at import, and consumed as the
**leaf evaluation** in the Search API and/or a **tiebreaker** in the rules Score layer.
Opponent-specificity comes not from a separate model but from the **Read** conditioning
the search inputs (the predicted opponent deck fed into `search_begin`); the Read's
`confidence` / `unknown_mass` gates how far we specialize off the general base (an unseen
deck falls back to general). Build order: general → matchup-conditioned → per-deck
fine-tune (3 → 2 → 1).

**Considered options.**
- **RL / self-play from scratch** — rejected: hardest and most expensive path, needs a
  Gym wrapper + large compute the runtime forbids, and ladder evidence shows it losing to
  tuned rules.
- **Three separately-trained models (my-deck / per-archetype / general) blended** —
  rejected *for now*: per-deck and per-archetype data barely exists yet, two of the three
  duplicate Scouting ([ADR-0003](0003-scouting-knowledge-is-a-shipped-artifact.md)), and
  an opaque ensemble fights the legibility goal
  ([ADR-0012](0012-optimize-for-strategy-category.md)). Genuine per-deck / per-archetype
  models are deferred **behind the same value-model interface** until data justifies them.
- **Neural policy / learned card embeddings** — rejected: no torch at runtime, and the
  full card table is available at inference so there's nothing to generalize over. The
  value model is gradient-boosted trees (LightGBM) over engineered features.

**Consequences.** The value model is a *measured experiment layered on a working
heuristic baseline*, validated by ladder A/B, with the heuristic kept as fallback — it
earns its place only if the ladder says so. The state-feature encoding is the
highest-leverage design surface.
