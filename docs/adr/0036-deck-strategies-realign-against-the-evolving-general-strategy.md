# ADR-0036: Deck strategies are recurringly re-aligned against the evolving General Strategy — /deck-align, ledger-diffed and score_diff-gated

**Status.** Accepted (grilled 2026-07-02, `/grill-with-docs`) and **BUILT** — `/deck-align` ships at
`.claude/skills/deck-align/`. *(Status corrected 2026-07-14: it still read "skill build pending".)* Builds on
[ADR-0034](0034-deck-rules-fold-general-when-vocabulary-is-general.md) (the fold policy + the
`score_diff` gate — both shipped) and
[ADR-0035](0035-weight-overrides-are-authored-seeds-under-learned-deltas.md).

**Context.** ADR-0034 fixed the *policy* (universal-vocabulary rules live general; declarations are
the deck's opt-in) and executed one fold round by hand — but nothing owns the **recurrence**. The
General Strategy keeps growing (baseline clusters, doctrines, the Lethal Solver / Turn Planner /
effect compendium); `/blunder-buster` keeps authoring rules (some deck-placed by ADR-0018, each "a
standing folding candidate"); new `Context`/`Board` vocabulary, Function Tags, params and opt-in
surfaces keep appearing after a deck was authored. Each deck slowly drifts: foldable rules linger,
newer general rules/systems silently cover deck rules, declarations miss new surfaces
(`my_archetype`, `preferred_start`, `fetch_priority`, Brief coverage), STRATEGY.md dispositions and
`tuned.json` keys go stale. deck-genie authors once; the upkeep step had no owner.

**Decision.**

1. **A new maintenance skill, `/deck-align <deck>`** — deck-genie's upkeep counterpart, reusing
   deck-genie's `references/` (disposition vocabulary, authoring rules, gates) so the two cannot
   drift. Bare `/deck-align` prints a staleness report across agents (a deck with no real
   `strategy.py` is deck-genie's job first). Three axes per pass:
   - **Folds** — the recurring application of ADR-0034: deck rules whose vocabulary has proven (or
     become) general fold into the matching cluster/doctrine; deck rules now covered by a
     newer general rule *or subsumed by a system* (Planner / Lethal / doctrine Mixin / sequencing)
     retire with a migration NOTE naming the successor. Weight-differing folds use
     `weight_overrides` (ADR-0035). Coverage is proven on the deck's recorded decision surface
     (`score_diff`), never by prose similarity; partial coverage is not a fold — it is keep, split,
     or generalize-the-trigger (a broadened trigger must be provably vacuous on the origin deck's
     pool, per ADR-0034). Each fold/generalization is presented **per-item for sign-off**
     (candidate, generalized trigger sketch, affected decks, gate preview) before execution.
   - **Vocabulary + wiring modernization** — triggers rewritten onto vocabulary that postdates the
     deck (new `Context`/`Board` fields, Function Tags; gated in `score_diff` **choice** mode);
     new opt-in surfaces wired (params, `fetch_priority`, Brief coverage, Role vocabulary).
   - **Docs + hygiene** — STRATEGY.md disposition table refreshed to current rule names/homes;
     stale `tuned.json` keys purged; stale migration NOTEs pruned; the strategy.py fold table kept
     current; `weight_overrides` entries whose underlying general value has drifted since
     authoring flagged for re-justification (they shadow pooled learning once the ADR-0035
     general-tuned layer exists).
2. **Ledger-diffed, not full-audit.** A per-agent `aligned.json` sidecar records the `src/common`
   commit (+ date + pass summary) last aligned against; a pass reviews the `git diff` of
   `src/common` + `card_functions.json` + `docs/general-strategy.md` since that commit. `--full`
   forces complete re-reconciliation; a deck with no ledger gets a full first pass. Local
   provenance only — the Bundle whitelist (`package.py`) never ships it.
3. **Gated, in order:** suite-green + `score_diff` (**always**: `scores` mode for folds — the
   ADR-0034 score-equality bar; `choice` mode for vocabulary fixes; capture taken before the pass
   touches anything) + `check_agent` Playability (**always**) + self-play A/B mirrors (**only when
   the pass intends behavior change** — weight shifts, wiring that activates new rules). A change
   to shared general rules runs `score_diff` for **every** agent with a corpus; A/B for the origin
   deck plus any agent whose diff shows real decision changes (role-keyed rules stay silent for
   decks without the Role, bounding the blast radius). The human commits every diff (ADR-0017).
4. **Ownership unchanged:** `/deck-align` never hand-writes learned weights — its authored deltas
   live in `weight_overrides` (ADR-0035); learned deltas orphaned by a retired id are dropped and
   the tuner re-learns from Corrections against the new rule set.

**Considered options.**

- **Enhance deck-genie instead** — rejected: authoring (research-heavy, card-by-card grill, from
  scratch) and upkeep (diff-driven, no research, sweepable) have different triggers and shapes;
  shared `references/` prevent drift without merging the skills.
- **Full audit every run** — rejected: O(deck rules × general rules) re-confirmation of unchanged
  facts; the ledger makes frequent cheap passes the norm.
- **Never retire — let equivalent rules co-fire additively** (weights stack by design, ADR-0008) —
  rejected: duplicated doctrine drifts, double-counts one reason, and buries the legibility the
  Hypothesis registry exists for.
- **Propose-only folds** (durable queue, ADR-0018-style) — rejected: per-item sign-off + the gates
  already provide the review; a queue adds ceremony and a second session nobody schedules.

**Consequences.** `aligned.json` joins the agent-dir sidecars. STRATEGY.md dispositions become
maintained artifacts rather than authoring-time snapshots. Run cadence is manual — after any
session that lands new general rules/systems (blunder-buster rounds, doctrine ADRs), the ledger
diff keeps casual runs cheap. Glossary (Alignment Pass, Alignment Ledger, Fold, Score-Diff Gate,
Disposition) in [src/common/CONTEXT.md](../../src/common/CONTEXT.md).
