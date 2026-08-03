# ADR-0049: A Correction carries a Scope — decision, turn, or match

**Status.** Accepted and BUILT — `scope` (`decision` | `turn` | `match`) ships through the whole blunder
path (`tools/train/blunder/correction.py`, `store.py`, `reviewed.py`, `report.py`); a legacy record with
no `scope` still loads as `decision`, and a scoped Correction never becomes a ranking constraint.
**`match` retired entirely 2026-08-03 (Issue #353) — see Amendment A below; going forward `scope` is
`decision` | `turn` only.**

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

## Amendment A (2026-08-03) — `match` scope is retired entirely (Issue #353)

**BUILT** — merged to `main` via PR #360 (commits `38763327` "Retire match correction scope for
Issue #353" and `1734cead`), same day as this ruling. This amendment records the decision and its
reasoning; the shipped diff is the authority on exact line-level detail.

**Closes [ADR-0113](0113-the-store-is-an-archive-so-the-writers-rules-are-re-applied-as-a-report.md)
decisions 1 and 3** (both *"ruled, NOT EXECUTED"* for a hypothetical future `match`-scope record)
**and the wave-3 packet's R1 note** (Issue #256, *"now zero-instance, still open"*) — all three become
moot rather than needing execution, because the scope value they are about no longer exists to
instantiate.

**Context.** Issue #353 opened on a narrower question: should a `match`-scope Correction ever grade at
its Anchor, given ADR-0113 decision 1 already ruled no but left it unexecuted — only one record was
ever affected, and it has since been re-scoped away (ADR-0113 Amendment A). Reviewing that history
directly, the developer went further: the corpus has held **zero** `match`-scope records since that
re-scope; the **one** record that ever carried the scope turned out, on the same close reading that
produced ADR-0113 Amendment A, to be a note about a single Main select — not a whole game; and nothing
else in this training history has ever needed the category. Zero real instances, in either direction,
across the scope's entire lifetime — stronger than "rare and currently unrepresented," and evidence the
category was never load-bearing.

**Decision.** `match` is removed from `SCOPES`. A Correction may only be `decision` or `turn` scope,
going forward.

- **Write path.** `SCOPES = ("decision", "turn")`. The match-forbids-`correct` branch in
  `build_correction` and the match arm in `subject_of` (`tools/train/blunder/correction.py`) become
  unreachable the moment `scope not in SCOPES` raises first, and are deleted rather than left as dead
  code. The human-tagging UI's "whole match" option (`tools/train/blunder/shell.py`) is removed, not
  merely left to error on submit. The branches that mirror it for reporting/proposing —
  `service.build_span` + `_match_span`, `reviewed.review_key`, `tuner/propose.py`'s `_where` and label
  builder, `tune.py`'s `_scope_tag`, `tuner/report_md.py`'s `_where` — are deleted as a set; each was
  written parallel to a `turn` branch specifically to serve `match`, and none has a reason to exist
  once the scope does not. **`gates.py`'s own writer-mirroring audit loses its match rule too** —
  `REFUSED_SHAPE_RULES` drops `match_names_a_correct` and `shape_the_constructor_would_refuse` drops
  the branch that raised it — folding cleanly into ADR-0113 decision 4's existing "an unrecognised
  `scope` returns alone" behavior rather than needing a new case.
- **Read path.** `decider_lab.py`'s `_records` `keep` predicate and `leaf_lab.py`'s `is_leaf_frame`
  both gain an explicit `scope != "match"` guard, above `is_leaf_frame`'s disjunction (per the wave-3
  packet's own sketch for this). This is deliberately redundant with the write-path removal:
  [ADR-0113](0113-the-store-is-an-archive-so-the-writers-rules-are-re-applied-as-a-report.md) decision
  4 already committed this codebase to `Correction.from_dict` performing **no validation**, precisely
  so the store can archive anything ever committed — which means a `scope: "match"` record could still
  reach the corpus by a route the writer never controlled (a hand-edit, a merge from a branch cut
  before this amendment, a restored git history). The one record this repo has ever hand-patched
  (`ee3191f7c3d6`, patched 2026-07-29, discovered by ADR-0113) is itself proof this channel is not
  hypothetical. Removing the writer's ability to create the shape is necessary but not sufficient; the
  gates guard is what makes the retirement hold even against the corpus's own archive philosophy.

**Measured consequence: zero.** The corpus holds 354 `decision` / 18 `turn` / 0 `match` records today.
Both new guards are no-ops on every committed row — no frame changes gate membership, no baseline
moves, and neither [ADR-0088](0088-a-voided-ruling-leaves-the-agree-rate-and-the-gate.md)'s
void-and-re-capture protocol nor a re-capture of `data/decider_lab/baseline.json` /
`data/leaf_lab/baseline.json` is owed. This is why the timing is right: the guard costs nothing to add
today and would cost a full re-capture (plus a live regression risk) if added only after some future
record actually used the scope.

**What this leaves stale in the ADR text above, deliberately not rewritten (this repo does not edit
ADR history):** the Decision section's *"Scope — decision (default) | turn | match"*, the `match`
clause under *"`correct` is optional off `decision` scope, and Anchor-only when given,"* and the Span
asymmetry paragraph's `match`-Span sentence. All describe a vocabulary this Amendment retires; this
Amendment, not that text, is authoritative on Scope's live vocabulary from 2026-08-03 forward.

**Not touched.** Category (orthogonal to Scope, per the original decision, unchanged). `turn` scope's
entire contract — subject-keying, optional Anchor-indexed `correct`, Span shape, `retest_span`'s
re-drive. `decision` scope, ADR-0111, ADR-0113 decisions 2 and 4 — all unaffected.
