# ADR index

The authoritative map of **number → file → status**. Generated 2026-07-14 during the audit-remediation
pass, which found 31 ADRs with no status line at all and 5 whose status was demonstrably false — a
status that lies is worse than none, and without this index auditing them meant reading 62 files.

## Numbering

Three numbers were used twice. Each collision was one **strategy** ADR and one **tooling** ADR, and the
bulk of inbound references meant the strategy one — so the tooling ADR moved and the strategy ADR kept
its number (2026-07-14):

| was | is now | doc |
|---|---|---|
| 0022 | **0057** | the self-play corpus (0022 stays the **Gust** doctrine) |
| 0033 | **0058** | the Arena (0033 stays the **transient-effect tracker**) |
| 0050 | **0059** | the cgpy engine twin (0050 stays **multi-step lethal verification**) |

`0050-glossary.md` is *not* an ADR — it is the companion vocabulary doc for ADR-0050 (lethal
verification), and its filename prefix is correct.

**Next free number: 0083.**

⚠️ The index below is **incomplete**: **0067** exists on disk but has never been given a row (it
landed on the #137 / 0a branch). 0069 and 0070 were backfilled 2026-07-26. Re-indexing 0067 is
unowned work — see #167's grill notes.

**0071 was claimed twice and resolved 2026-07-26.** #163's *bench survival is a shared-budget
Harvest* merged to `main` first and KEEPS 0071; #167's *mid-build swaps are gated by deterministic
instruments* renumbered to **0072** on rebase. Both are strategy ADRs, so the tooling-moves-first rule
above did not apply — first-merged kept the number.

**0074 was claimed three times and resolved 2026-07-27.** Three branches were open at once and each
authored an ADR numbered 0074. Resolved by the same first-merged-keeps-it rule: #175's *a probability
may weight a ranked value* merged first and KEEPS 0074; #177's *the KO oracle prices attachments as a
typed Budget* renumbered to **0075**; #186's *the opponent-target slot family splits by instrument
shape* renumbered to **0076** on rebase. All three are strategy ADRs, so the tooling-moves-first rule
did not apply to any of them. ⚠️ The lesson is now recurring (0071, then 0074 ×3): the number is
claimed at grill time but only settled at merge time, so a long-lived branch should expect to
renumber and should keep its ADR references greppable for exactly that reason.

**0076 was claimed twice and resolved 2026-07-29.** #186's *the opponent-target slot family*
(itself already renumbered 0074 → 0076 above) merged first and KEEPS 0076; Issue #172's *a ranked
count consumer reads `expected`* renumbered to **0077** on rebase. Same first-merged rule, and the
third instance of the recurring lesson in three days — the grill-time number is a claim, not a
reservation.

**0077 was claimed twice and resolved 2026-07-29.** Issue #172's *a ranked count consumer reads
`expected`* (itself already renumbered 0076 → 0077 above) merged first and KEEPS 0077; Issue #187's
*the value currencies are three scales bridged by derived rates* renumbered to **0078** on rebase.
Fourth collision in four days, and the second time a single ADR has been renumbered twice in its own
life. Treat the number as a rebase artifact rather than an identifier: **cite the issue alongside it**
("ADR-0078, Issue #187") so a rename can be applied to one branch's references without corrupting
another's.

**0079 was claimed twice and resolved 2026-07-29.** Issue #161's *the Set-Up Active pick is one deck
declaration* (itself already renumbered 0075→0077→0078→0079 across three rebases) merged first and
KEEPS 0079; Issue #199's *deny is a categorical relevance instrument* renumbered to **0080** on
rebase. **Fifth collision in four days**, and the second ADR in the series to be renumbered more than
once in its own life. The lesson is no longer "expect to renumber" but "the number is not the
identifier": cite the issue alongside it ("ADR-0080, Issue #199").

**0080 was claimed twice and resolved 2026-07-29.** Issue #199's *deny is a categorical relevance
instrument* (itself already renumbered 0079 → 0080 above) merged first and KEEPS 0080; Issue #203's
*the opener is hand-conditional* renumbered to **0081** on rebase. **Sixth collision in four days**,
and the third ADR in the series renumbered more than once in its own life. Issue #203's file carried
a grill-time warning that it expected to renumber, and it did — within the day. Both are strategy
ADRs, so the tooling-moves-first rule did not apply. At this point the collision is the norm rather
than the exception: **claim nothing, cite the issue, and renumber at rebase**.

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-data-source.md) | Source the deck Meta from Simulation-competition replays | accepted |
| [0002](0002-extracts-only-retention.md) | Extracts-only retention — discard raw replays | accepted |
| [0003](0003-scouting-knowledge-is-a-shipped-artifact.md) | Scouting knowledge is an offline-compiled, shipped artifact | Accepted and BUILT — `tools/build_scouting_artifact.py` compiles the committed |
| [0004](0004-shared-common-packaged-per-submission.md) | Shared `common/` + `cg/`, assembled into a self-contained submission at package time | Accepted and BUILT — the repo ships the `src/common/` + `src/cg/` + thin |
| [0005](0005-deck-stealer-source.md) | deck_stealer copies decks from a replay file, not the leaderboard or meta store | Accepted and BUILT — `tools/deck_stealer.py` is the shipped tool and sources decks from |
| [0006](0006-function-tags-single-source-of-structural-facts.md) | Function Tags are the single source of structural card facts; roles are tags-in-context | Accepted, then **partially reversed 2026-06-24** (the revision note below): Depth 1 (the |
| [0007](0007-learning-is-one-offline-value-model.md) | Learning enters as one offline, replay-trained general value model gated by the Read | Accepted — the one-learned-seam principle holds and the seam was built as |
| [0008](0008-pilot-is-a-layered-rules-pipeline.md) | The Pilot is a layered rules pipeline; decks plug in a declarative Strategy | Accepted and BUILT — `src/common/pilot.py` is the shipped Sense→Plan→Score→Act pipeline |
| [0009](0009-training-methodology.md) | Training methodology — three jobs, dense signals tune, the ladder gates | Accepted and BUILT — Job A (weight tuning from Corrections) ships as `tools/train/tune.py` |
| [0010](0010-local-agent-verification-on-cabt-env.md) | Local agent verification runs on the real cabt env (kaggle-environments), not the raw `cg` loop | Accepted and BUILT — `tools/sim/check_agent.py` verifies agents on the real `cabt` env, |
| [0011](0011-dataset-source.md) | Fetch from the daily top-episode dataset; drop the low band | accepted (supersedes the acquisition mechanism of ADR-0001; |
| [0012](0012-optimize-for-strategy-category.md) | Optimize for the Strategy Category — legible reasoning over leaderboard rank | Accepted — the standing goal of the whole repo. It is policy, not code: every later ADR is |
| [0013](0013-decklist-resolution-by-name.md) | Convert Limitless decklists by resolving card *names*, not (set, number) | Accepted and BUILT — `tools/deck_convert.py` is the shipped converter: name-keyed, |
| [0014](0014-blunder-inspector-viewer-engine.md) | Blunder inspector reuses the official cabt visualizer, embedded in a tagging shell | Accepted and BUILT — the vendored viewer + tagging shell ship in `tools/train/blunder/` |
| [0015](0015-correction-schema.md) | The Correction schema — atomic, two-axis, self-contained | Accepted and BUILT — the shipped Correction schema (`tools/train/blunder/correction.py`, |
| [0016](0016-energy-attachment-is-a-layered-procedure.md) | Energy attachment is a layered, override-able procedure | Accepted and BUILT — the universal energy reflexes live in |
| [0017](0017-corrections-compile-to-hypotheses.md) | Corrections compile to Hypotheses via the Tuner — attribution derived, Tier-0 now, fan-out | Accepted and BUILT — the Tuner (`tools/train/tuner/`) derives `attribution` by replaying |
| [0018](0018-applying-tuner-output.md) | Applying Tuner output — weights auto-load; Hypotheses are LLM-authored behind a Verifier | Accepted and BUILT — `tuned.json` auto-loads as the Pilot's `overrides` (now through |
| [0019](0019-submissions-are-traceable-and-tracked.md) | Submissions are traceable, self-describing, and tracked against performance | accepted |
| [0020](0020-forward-evolution-index-is-a-provider-primitive.md) | Forward-evolution knowledge is a provider primitive, distinct from the Read's EvoPath | accepted (2026-06-28) |
| [0021](0021-prefilter-balances-seats.md) | The self-play pre-filter balances seats; reproducibility is statistical, not seeded | Accepted and BUILT — `tools/sim/battle.py` seat-balances every run and appends a Battle |
| [0022](0022-gust-is-closed-form-lethal-lookahead.md) | Gust decisions are a closed-form lethal-lookahead over hypothetical defenders (board-only, Read-deferred) | Accepted (grilled 2026-06-29); **implemented 2026-06-29** — whether-to-play |
| [0023](0023-fetch-is-a-shared-value-comparator.md) | Fetch decisions are one shared closed-form value comparator (importance × gap × availability), board-only, Read-deferred | Accepted (grilled 2026-06-29); **core implemented 2026-06-29** test-first |
| [0024](0024-shuffle-refresh-is-fetch-decision-a-over-keep-value.md) | Shuffle-Refresh is the Fetch comparator's decision (A) only — a dead-hand fallback over keep-value, with a deferred stochastic pull-EV | Accepted (grilled 2026-06-29); **Layer-A premise PARTLY REVERSED 2026-06-30** — the |
| [0025](0025-baseline-rules-cluster-by-decision-context.md) | Baseline rules cluster by decision-context; `doctrine_` vs `baseline_` | Accepted and BUILT (behavior-neutral) — `common/strategy/baseline/baseline_*.py` holds the |
| [0026](0026-posture-generic-core-is-net-new-read-levers.md) | M2 Posture's generic core is the Read's net-new levers, not generic seek/avoid | Accepted and BUILT — `posture` is `PROFILE=True` (default ON): levers A (favorability) and |
| [0027](0027-matchup-brief-is-hand-authored-opponent-doctrine.md) | Per-archetype counterplay is a hand-authored Matchup Brief, distinct from the auto-Dossier | Accepted and BUILT — eight Briefs ship at `src/common/scouting/briefs/<slug>.json` with |
| [0028](0028-tool-deploy-is-survival-turns-board-math.md) | +HP Tool deploy is survival-turns board-math — proactive default, not hold-for-breakpoint | Accepted (grilled 2026-06-30, `/grill-with-docs`) and **BUILT** test-first (`/tdd`, |
| [0029](0029-own-deck-content-is-sound-oracle-plus-probabilistic-estimate.md) | Own-deck content is a SOUND oracle PLUS a PROBABILISTIC estimate — two epistemics, never contradictory | Accepted & **implemented** test-first 2026-06-30 (`tests/strategy/test_deck_odds.py`, |
| [0030](0030-winning-this-turn-is-an-eager-engine-verified-lethal-solver.md) | Winning this turn is an eager, engine-verified Lethal Solver (sound, shortest-line, execute-only) | Accepted (grilled 2026-07-01, `/grill-with-docs`). **Superseded in layout by |
| [0031](0031-turn-planner-is-goal-directed-engine-simulated-tier1-search.md) | The Turn Planner is a goal-directed, engine-simulated whole-turn optimizer (Tier-1 Search) | Accepted (grilled 2026-07-01, `/grill-with-docs`). **Extended by |
| [0032](0032-card-knowledge-is-an-engine-audited-effect-compendium.md) | Card knowledge is an engine-audited effect compendium (three tables + one damage oracle) | Accepted (grilled 2026-07-02, `/grill-with-docs`). **Built 2026-07-02** (TDD, all |
| [0033](0033-transient-attack-effects-are-a-log-inferred-match-scoped-tracker.md) | Transient attack effects are a log-inferred, match-scoped tracker | Accepted & built 2026-07-02 (TDD; the completion plan's P2 — |
| [0034](0034-deck-rules-fold-general-when-vocabulary-is-general.md) | Deck rules fold into the General Strategy when their vocabulary is general | Accepted and BUILT (2026-07-02) — the first fold round landed (mega_starmie ships |
| [0035](0035-weight-overrides-are-authored-seeds-under-learned-deltas.md) | Per-deck specialization of General-Strategy weights is a two-layer override — authored seeds under learned deltas | Accepted (grilled 2026-07-02, `/grill-with-docs`) and **BUILT** — `/deck-align` is shipped |
| [0036](0036-deck-strategies-realign-against-the-evolving-general-strategy.md) | Deck strategies are recurringly re-aligned against the evolving General Strategy — /deck-align, ledger-diffed and score_diff-gated | Accepted (grilled 2026-07-02, `/grill-with-docs`) and **BUILT** — `/deck-align` ships at |
| [0037](0037-lethal-solver-is-the-turn-planners-top-rung.md) | The Lethal Solver is the Turn Planner's sound top rung (one entry point, one generator family, verified locks replay) | Accepted (grilled 2026-07-03, `/grill-with-docs`). **Built 2026-07-03 (`/tdd`), all three |
| [0038](0038-brief-consumption-sharpens-the-owning-tactical-signal.md) | Brief consumption sharpens the owning Tactical signal (γ-scaled), not parallel Hypotheses | Accepted (2026-07-04) and built — then **SUPERSEDED by ADR-0051 (2026-07-12)**: the γ-gated Brief levers (`brief_preevo` / `brief_engine`) are **RE… |
| [0039](0039-gamble-lines-are-closed-form-expectimax-over-outcome-classes.md) | Gamble Lines are closed-form expectimax over Outcome Classes | Accepted (grilled 2026-07-05, `/grill-with-docs`). **Built 2026-07-05 (`/tdd`)**: the |
| [0040](0040-match-judgment-is-per-turn-closed-form-objectives.md) | Match-level judgment is per-turn closed-form objectives (Prize Path × KO Race → derived phases) | Accepted (grilled 2026-07-05, `/grill-with-docs`). **Built 2026-07-05 (`/tdd`)**: KO |
| [0041](0041-posture-is-observable-in-decision-telemetry.md) | Posture is observable in Decision Telemetry (matchup misplays route to a Brief, not a weight) | Accepted and BUILT (2026-07-05) — the Pilot stamps `_posture_record` on every Decision and |
| [0042](0042-base-value-model-is-a-dependency-free-logistic-over-objective-features.md) | The Automatic Value Model is a dependency-free logistic over the objective features | Accepted + **Built 2026-07-05** (`/tdd`, Tier 5). The single learned seam (ADR-0007), |
| [0043](0043-escalation-search-is-a-budgeted-depth-2-tree-on-a-close-attack-tie.md) | Escalation Search is a budgeted depth-2 tree on a close attack tie | **Deprecated & REMOVED (2026-07-17**, ADR-0064 Decision 6); corpus re-check clean; code + tests physically removed, `search_budget` kept inert |
| [0044](0044-opponent-choice-residue-is-narrow-closed-form-reads.md) | The deferred opponent-choice residue is narrow closed-form reads, not revived escalation search | Accepted (grilled 2026-07-06, `/grill-with-docs`) + **Built 2026-07-06** (`/tdd`) + |
| [0045](0045-match-scale-planning-is-a-closed-form-directive-game-plan.md) | Match-scale planning is a closed-form directive Game Plan atop the Turn Planner | Accepted (grilled 2026-07-06/07, `/grill-with-docs`) + **BUILT 2026-07-07 (`/tdd`, all four |
| [0046](0046-strategy-authoring-splits-analysis-proposes-one-skill-applies.md) | Strategy authoring splits — analysis skills propose, one skill applies | Accepted (2026-07-09). `update-strategy` built + proven; **all five producers trimmed to |
| [0047](0047-opponent-model-is-one-facade-over-knowledge-subsystems.md) | Opponent awareness is one facade over knowledge subsystems, not scattered fields | Accepted (grilled 2026-07-09, `/grill-with-docs`) + **Foundation built 2026-07-09**; the |
| [0048](0048-prize-economy-fetch-broadens-the-line-concept.md) | Prize-economy fetch broadens the Line concept behind a role-gated win-condition set | Accepted (grilled 2026-07-10) and BUILT — `prize_economy_fetch` is `PROFILE=True` (default |
| [0049](0049-corrections-carry-a-scope-decision-turn-or-match.md) | A Correction carries a Scope — decision, turn, or match | Accepted and BUILT — `scope` (`decision` | `turn` | `match`) ships through the whole blunder |
| [0050](0050-glossary.md) | Ubiquitous Language — Lethal verification & engine seeding (ADR-0050) | —  *(companion vocabulary doc for ADR-0050, not an ADR)* |
| [0050](0050-multi-step-lethal-verification-tool.md) | The Lethal Solver's engine verify seeds the EXACT deck; the multi-step verification tool is that seeding + a fixture backfill + a pytest helper | Accepted + **Phases 1, 2 AND 3 built** — Phase 3's follow-up hooks shipped 2026-07-13 and |
| [0051](0051-matchup-target-priority-spine.md) | ADR-0051 — Matchup Target Priority is one spine the targeting decisions read | Accepted (Phases 1–3b built 2026-07-12/13) |
| [0052](0052-combat-math-is-one-ko-oracle-module.md) | Combat math is one KO-oracle module with explicit dependencies | Accepted (2026-07-13) and **BUILT** — `CombatMath` ships as `src/common/strategy/combat.py` |
| [0053](0053-ml-training-pipeline-build-plan.md) | ML Training Pipeline — Build Plan | Accepted (2026-07-13); an accepted BUILD PLAN — no work package has started (the S1/WP0 row |
| [0054](0054-provider-splits-into-parsers-indexes-records.md) | The stat provider splits into parser battery, indexes, and records | Accepted (2026-07-13) and **BUILT** — `scouting/card_text.py` (parser battery) and |
| [0055](0055-one-agent-runtime-owns-the-deployment-profile.md) | One agent runtime owns the deployment profile | Accepted (2026-07-13) and **BUILT** — `src/common/runtime.py` is merged to main: `PROFILE` |
| [0056](0056-stat-provider-is-the-one-card-knowledge-seam.md) | The Stat Provider is the one card-knowledge seam; records answer single-card questions | Accepted (2026-07-13) and **BUILT** — merged to main: the Stat Provider is the one |
| [0057](0057-selfplay-corpus-uses-cabt-env-path.md) | The self-play corpus uses the cabt-env path (for Tuner-usable obs), not the A/B harness | Accepted and BUILT — `tools/sim/selfplay.py` generates the own-game corpus on the cabt-env |
| [0058](0058-arena-captures-pvc-on-cabt-env-path.md) | Arena captures PvC Matches on the cabt-env path (human bridged as an env agent) | Accepted and BUILT (2026-07-02) — `tools/arena/` hosts PvC Tables on the cabt env with the |
| [0059](0059-cgpy-is-a-trace-verified-python-twin-of-the-native-engine.md) | cgpy is a trace-verified pure-Python twin of the native engine | accepted (2026-07-10) |
| [0060](0060-hand-refresh-value-is-a-closed-form-card-swing.md) | Hand-refresh value is a closed-form card swing, not a hand-size threshold | Accepted (grilled 2026-07-14, `/grill-with-docs`) and **BUILT 2026-07-14 (`/tdd`)**, default |
| [0061](0061-a-locking-attacks-value-includes-its-forced-follow-up.md) | A locking attack's value includes its forced follow-up (Horizon-2) | Accepted (grilled 2026-07-14, `/grill-with-docs`) and **BUILT 2026-07-14 (`/tdd`)**, default |
| [0062](0062-energy-denial-is-what-the-strip-actually-takes-away.md) | Energy denial is what the strip actually takes away, not whether Energy is present | Accepted (grilled 2026-07-14, `/grill-with-docs`) and **BUILT 2026-07-14 (`/tdd`)**, default |
| [0063](0063-a-booster-scales-the-oracle-and-a-doomed-body-denies-nothing.md) | A booster scales the oracle; a doomed body denies nothing; banked Energy is worth what it will pay for | Accepted and **BUILT 2026-07-14 (`/tdd`)**, default ON — amends ADR-0062 |
| [0064](0064-incoming-counts-the-opponents-next-development-step-budgeted-by-the-read.md) | Incoming counts the opponent's next development step, budgeted by the Read | Accepted (grilled 2026-07-16) and **BUILT 2026-07-16/17** — all six decisions, suite-green; deprecates+removes ADR-0043, amends the `incoming-affordability` WON'T-FIX |
| [0065](0065-card-worth-is-one-marginal-oracle-with-a-closure-graph-backend.md) | Card worth is one marginal oracle with a closure-graph backend | Accepted (grilled 2026-07-17, Rounds 7–9) and **BUILT 2026-07-18** — the module seam (`fetch_closure.py` + `card_worth.py`); the four-shadow value convergence STAGED; amends ADR-0060 |
| [0065](0065-glossary.md) | Ubiquitous Language — Worth / Gates / Odds / Closure (ADR-0065) | —  *(companion vocabulary doc for ADR-0065, not an ADR)* |
| [0066](0066-the-gust-baseline-is-rider-aware-and-denial-is-marginal.md) | The gust baseline is rider-aware, and gust denial is marginal | Accepted and **BUILT 2026-07-19** — the gusting Round-0 build (3 targeted fixes: rider-aware baseline + threat-forfeit premium, marginal famine stall, loaded-equal-KO tie-break); amends ADR-0022 |
| [0068](0068-the-statemodel-is-a-lazy-pure-snapshot-shared-by-side.md) | The StateModel is a lazy, pure snapshot; reuse is by side, never by patch | Accepted (grilled 2026-07-24, `/grill-with-docs` on #138 — seven locked decisions); build = #138 (Phase 0b). `apply(action)` rejected; Carried State channel declared; Count Triple deck counts; Leaf Profile CI-pinned. *(0067 = the ADR-0067 epistemic split, authored on the #137/0a branch.)* |
| [0069](0069-the-attach-marginal-is-an-axes-sum-and-the-decider-may-say-no.md) | The attach marginal is an axes-sum, and the decider may say no | Accepted (grilled 2026-07-25, `/grill-with-docs` on #139 — thirteen locked decisions) and **BUILT** — Phase 1a, the FIRST no-shadow decider swap; its shape (fold → delete → retune → corpus re-rule → paired A/B) is the pattern 1b–1e follow *(index row backfilled 2026-07-26)* |
| [0070](0070-the-evolve-marginal-is-a-body-substituted-delta-in-damage.md) | The evolve marginal is a body-substituted delta, and its constants are odds | Accepted (grilled 2026-07-25, `/grill-with-docs` on #140) and **BUILT/MERGED 2026-07-26** — Phase 1b, the evolve decider ships ON; amendments A–I. §9's bench branch is corrected by ADR-0071, and amendment C's f82 planner-scope premise is retired by it *(index row backfilled 2026-07-26)* |
| [0071](0071-bench-survival-is-a-shared-budget-harvest-and-the-clock-accumulates.md) | Bench survival is a shared-budget Harvest, and the clock accumulates | Accepted (grilled 2026-07-26, `/grill-with-docs` on #163 — twelve locked decisions); build = #163, branching after #166 merges. Amends ADR-0070 §9 (amendment D) and the shipped `turns_to_ko_me`; corrects the CONTEXT.md Threat Clock promotion surcharge. *(0070 = the evolve marginal, authored on the #140/1b branch.)* |
| [0072](0072-mid-build-swaps-are-gated-by-deterministic-instruments.md) | A mid-build decider swap is gated by deterministic instruments; the paired A/B becomes a crash-and-catastrophe tripwire | Accepted (grilled 2026-07-26, `/grill-with-docs` on #167 — five locked decisions); build = #167. Amends #136 directive 6 and promotes ADR-0069 §8's sweep to a gate |
| [0073](0073-fetch-reach-and-fetch-deadness-are-opposite-readings-of-one-clause.md) | Fetch reach and fetch deadness are opposite readings of one clause | Accepted (grilled 2026-07-26, `/grill-with-docs` on #164); build = #164. Extends ADR-0065 / ADR-0032 / ADR-0029, companion to ADR-0068 |
| [0074](0074-a-probability-may-weight-a-ranked-value-never-gate-a-lock.md) | A probability may WEIGHT a ranked value, never GATE a lock | Accepted (grilled 2026-07-27, `/grill-with-docs` on #175) and **IMPLEMENTED 2026-07-27**. Extends ADR-0067, amends ADR-0031 decision 3; leaves ADR-0030/0037 untouched |
| [0075](0075-the-ko-oracle-prices-attachments-as-a-typed-budget.md) | The KO oracle prices attachments as a typed Budget, once, for every line | Accepted (grilled 2026-07-27, `/grill-with-docs` on #177 — five locked decisions); build = #177. Renumbered from 0074 on rebase (#175 merged first). Extends ADR-0067 and ADR-0074 into the five `_play_accel_extra` lines; gated by ADR-0072 |
| [0076](0076-the-opponent-target-slot-family-splits-by-instrument-shape.md) | The opponent-target slot family splits by instrument shape: held-card keep pricing extends the Needs assignment; target-ranking reads the marginal directly | Accepted (grilled 2026-07-27, `/grill-with-docs` on #186 — three locked decisions); build = #186, consumed by #187/#188/#189/#190. Renumbered from 0074 on rebase (#175 merged first, #177 took 0075). Extends ADR-0065's Needs/`keep_v2`; gated by ADR-0072. Amendments A–F |
| [0077](0077-a-ranked-count-consumer-reads-expected-not-the-probability-leg.md) | A ranked consumer asking HOW MANY reads `expected`, not the Probability Leg | Accepted (grilled 2026-07-28, `/grill-with-docs` on Issue #172 — four locked decisions); build = Issue #172. **Amends ADR-0074 decision 1** (the ranked branch splits by the question asked) and resolves its decision-6 untyped-union objection for `expected`; retires ADR-0061's hand-rolled `_deck_basic_energy_fuel` floor; gated by ADR-0072 |
| [0078](0078-the-value-currencies-are-three-scales-bridged-by-derived-rates.md) | The value currencies are three scales bridged by DERIVED rates, and building the bridge is a shared-layer prerequisite, not an instrument swap | Accepted (grilled 2026-07-28, `/grill-with-docs` on Issue #187 — six locked decisions); build = Issue #199 (S3c), consumed by Issue #187/#188/#189. Renumbered from 0077 on rebase (Issue #172 merged first). Hoists ADR-0073's `PRIZE_DAMAGE_RATE` to `common/currency.py` and names the still-underived Worth Damage Rate; supersedes ADR-0076 Amendment E's hand-off of the currency debt to Issue #189; overturns the WP-N8 play-side ruling. Amendments A–C record gate 1 failing, the user's instantaneous-deny ruling, and its passing |
| [0079](0079-the-setup-active-pick-is-one-deck-declaration.md) | The Set-Up Active pick is one deck declaration, not a pile of derived rungs | Accepted (grilled 2026-07-28, `/grill-with-docs` on #161 — nine locked decisions); build = #161. Completes ADR-0070 §4 and overturns the 2026-07-15 evolve grill's Ruling 5; applies ADR-0034 / ADR-0046. *(authored as 0075, renumbered 0075→0077→0078→0079 across three rebases — each of 0075/0076/0077/0078 merged first)*. Bench sibling split to #197 |
| [0080](0080-deny-is-a-categorical-relevance-instrument-not-a-magnitude-one.md) | Deny is a CATEGORICAL RELEVANCE instrument, not a magnitude one: the Worth Damage Rate is not needed, it is MOOT | Accepted (grilled 2026-07-29, `/grill-with-docs` on Issue #199 — five locked decisions); builds in Issue #187 (rechartered), Issue #199 closes as the shared layer reduced, Issue #188 unblocked, Issue #189 re-inherits the gust currency debt. Supersedes ADR-0078 decision 1 for deny and withdraws its one-backend claim for deny; answers gate 2 MOOT (the DISCARD sweep found the sole anchor degenerate — it prices 0.000 under both instruments, so the rate divides out) *(authored as 0079, renumbered 0079→0080 on rebase — Issue #161's Set-Up Active pick merged first)* |
| [0081](0081-the-opener-is-hand-conditional-via-a-turn-0-evolve-marginal.md) | The opener is hand-conditional: a turn-0 evolve marginal REORDERS the declaration, and pins hold their slots | Accepted (grilled 2026-07-29, `/grill-with-docs` on Issue #203 — five locked decisions plus Amendment A, which narrows decision 4 and defers decision 2); build = Issue #203. **Extends** ADR-0079 rather than overturning it (one rule, one boolean, `+40` all unchanged — the *resolution* of `top_starter_id` gains hand-awareness); collects the placement work ADR-0070 §4 parked. Applies ADR-0034 / ADR-0046 / ADR-0065 *(authored as 0080, renumbered 0080→0081 on rebase — Issue #199's deny instrument merged first)* |
| [0082](0082-the-gust-instrument-is-three-surfaces-and-only-one-crosses-a-scale-boundary.md) | Gust is a THREE-surface instrument, and only ONE of its surfaces crosses a scale boundary | Accepted (grilled 2026-07-29, `/grill-with-docs` on Issue #189 — six locked decisions); build = Issue #189, RECHARTERED from a one-surface behaviour-preserving repoint. **Answers** the currency debt ADR-0076 Amendment E raised and ADR-0080 decision 4 handed back — without the Worth Damage Rate, which is now MOOT for gust as well as deny (so moot everywhere it was owed). Narrows ADR-0080's "gust has no escape route" consequence; extends ADR-0073's lethal/sub-lethal seam; deletes `gust-for-the-loaded-equal-ko` per tracker directive #1. Corpus ownership ruled frame by frame: `85164131-22` → Issue #188, `86089120-14` already FIXED and unowned |
