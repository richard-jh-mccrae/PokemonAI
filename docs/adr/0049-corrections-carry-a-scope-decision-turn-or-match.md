# ADR-0049: A Correction carries a Scope — decision, turn, or match

**Status.** Accepted and BUILT — `scope` (`decision` | `turn` | `match`) ships through the whole blunder
path (`tools/train/blunder/correction.py`, `store.py`, `reviewed.py`, `report.py`); a legacy record with
no `scope` still loads as `decision`, and a scoped Correction never becomes a ranking constraint.

**Context.** [ADR-0015](0015-correction-schema.md) fixed a Correction to **one Decision**: `correct`
is a mandatory set of option indices at a single frame, and `(episode, seat, frame)` is its identity.
Real blunders are not all that shape. A turn can be lost by a *set* of individually defensible
Decisions played in the wrong order; a match can be lost to a wrong Game Plan that no single `select`
reveals. Those blunders currently have nowhere to go but a `sequencing_error` tag on one arbitrary
Decision — which is why that one category absorbs 58% of the log while six terms go unused. Worse,
the Tuner then feeds that tag to `fit_weights` as a ranking constraint, trying to fix a plan-layer
error by moving a Tier-0 weight — exactly the failure `docs/tuning/methodology.md` warns against.

Meanwhile the runtime grew the two layers those blunders belong to: the **Turn Planner**
(`plan_turn`, [ADR-0031](0031-turn-planner-is-goal-directed-engine-simulated-tier1-search.md) /
[ADR-0037](0037-lethal-solver-is-the-turn-planners-top-rung.md)) and the **Match Planner**
(`plan_match`, [ADR-0045](0045-match-scale-planning-is-a-closed-form-directive-game-plan.md)). The
correction log had no way to address either.

**Decision.** A Correction gains a **Scope** — `decision` (default) | `turn` | `match` — plus a
**Span** and an **Anchor** (`tools/train/CONTEXT.md`). It stays **one record type in one log**: the
scoped records share identity, provenance, `live_trace`, Category, CRITICAL and `posture_mismatch`
with the atomic ones, and a legacy line with no `scope` loads as `decision` unchanged.

- **Identity is the Scope's subject, not the frame.** `decision` → `(episode, seat, frame)`;
  `turn` → `(episode, seat, turn)`; `match` → `(episode, seat)`. The Anchor frame the human tagged
  from is kept as context. Reviewed-ledger keys follow: `<ep>-<frame>` | `<ep>-t<turn>s<seat>` |
  `<ep>-m<seat>`.
- **`correct` is optional off `decision` scope, and Anchor-only when given.** A multi-frame
  counterfactual line *cannot* be expressed as option indices: prescribing a different pick at the
  Anchor invalidates every later frame's `select.option`, which only exists because the original pick
  was made. So at most one prescription is sound — the **first divergent Decision** — and it indexes
  the Anchor. `match` scope forbids `correct` entirely; the intended line is `rationale` prose. This
  is ADR-0015's deferred Tier-2 boundary, restated as a schema invariant rather than a TODO.
- **A scoped Correction is never a ranking constraint.** `tuner/run.py` short-circuits `scope !=
  "decision"` before `ranking_constraint()` and routes it straight to the `open[]` worklist that
  `/blunder-buster` already drains. When an Anchor `correct` and `obs` exist, `featurize()` still runs
  — but only to record the fired-Hypothesis diff as `attribution` **information**. A sequencing error
  never moves a weight.
- **Embedded state is asymmetric, by what each layer can verify.** A `turn` Span embeds per-Decision
  `obs` + `live_trace` (no per-Decision `current`), so `retest_span` can re-drive the Turn Planner
  through `pilot.explain(obs_i)` and report the **first divergence** — everything past it is
  off-policy and reported as such. Its `verification_contract` is therefore `verifier`. A `match` Span
  embeds per-Turn headers (`chosen_label`s, `game_plan`) and no `obs`: nothing plans across turns
  (T5/T6 are inert-OFF), so a match Correction is doctrine and its contract is `seed-ladder`.
- **Category is orthogonal to Scope.** One closed vocabulary, unchanged. `slow_setup`,
  `overextension` and `prize_mismanagement` were always match-shaped terms being forced onto single
  Decisions; new terms are added by process, when a real blunder doesn't fit.

## Consequences

`retest`'s `fixed = all(c in chosen_after for c in correction.correct)` is vacuously `True` for an
empty `correct` — it must degrade to `None`. Both `target_layer` values a scoped blunder needs
(`planner-code` for `plan_turn`/`plan_match`) already exist in the Strategy Proposal contract, so
[ADR-0046](0046-strategy-authoring-splits-analysis-proposes-one-skill-applies.md) is untouched.
Routing stays `/blunder-buster`'s job: `scope` is a strong prior, not an auto-route — a Turn whose
`planned` is `null` throughout means the Planner never committed, and the gap is a general Hypothesis.

`ProposedHypothesis` becomes a mild misnomer (a turn record proposes planner code, not a Hypothesis).
Accepted: a second parallel array through `io.write_proposals`, `report_md.py`,
`reports/blunders.html` and the `/blunder-buster` completion gate costs more than the name does.

A turn Correction is ~50–60 KB against a decision Correction's ~17 KB. With replays discarded
([ADR-0002](0002-extracts-only-retention.md)) the embedded Span is the only surviving copy of the
turn, so the cost buys the record's entire re-measurability.
