# The Value System POC — six-track parallel build plan (2026-08-01)

**Provenance:** user grill session 2026-07-31/08-01 (four rulings, below), preceded by a five-sweep
source audit of the entire value stack (StateModel, CombatMath, value modules, pilot wiring +
PROFILE, planner/doctrines). Supersedes the one-issue-at-a-time cadence of Issue #136's phase list
for everything up to and including the Turn Planner. Issue #136 remains the master tracker; this
doc is the build doctrine its POC section points at. ADR: ADR-0092 (settled — merged uncollided in
PR #258).

**The goal, in the user's words:** a proof-of-concept that is "complete enough to show the promise
of a State Model with full use of value equations and no piles of rules or hypothesis." Not
perfect. Built fast, in parallel, with the user steering by exception (wave rulings), not by
participation (per-issue grills).

---

## 1. Locked doctrine (user rulings, 2026-07-31/08-01)

1. **Scope cut:** build through the Turn Planner AND `state_value` (old Issues #165 + #145,
   merged into tracks T3/T4). The learning phases (Issues #146–#148) and depth-2 search
   (Issue #150) are OUT. Slowking onboarding (Issue #149) OUT. Decline-a-prize (Issue #190)
   deferred post-POC.
2. **Trainer architecture — hybrid differencing:** already-built bespoke equations stay as-is
   (attach, evolve, promote/retreat, deploy, snipe relevance, deny relevance, gust-target,
   refresh-swing, keep-value). Every UNBUILT family (fetch/search, draw economy, tools, stadium,
   heal, gust whether-to-play) is priced by the Turn Planner as an end-state difference:
   `value(play) = state_value(after) − state_value(before)`, stochastic outcomes as closed-form
   hypergeometric expectation, never engine-shuffle rides. One mechanism replaces ~60 rungs.
3. **Verification — gates + batched waves, no A/Bs:** the test suite and both deterministic gates
   (Discrimination, Decision) run per track. Per-swap A/B gauntlets are DROPPED for this build
   (POC bar). Corpus flips accumulate per integration wave; the user rules them in ~3 batched
   sessions ("wave ruling packets"). Flips are never auto-conformed; the gates are never vacuous.
   This amends tracker directive 6 for the POC tracks only (recorded in ADR-0092).
4. **Tracker restructure:** the plan is filed as six track issues (POC-T0…T5), each a
   self-contained spec authored by Claude to post-grill depth. Absorbed issues are closed with
   supersession comments. No per-issue grilling exists anywhere in the flow.

**Standing rulings carried in from the same conversation:**

- The StateModel is the SOLE data supplier, both sides — "every ounce of observable data as it is
  at decision time," including the opponent's hand count and discard contents.
- Shadows and v1/hypothesis fallbacks are DELETED, not kept as backups or double-checkers.
- No new hypothesis rungs. Sound structural rules survive only on the ratified whitelist (§6).
- POC quality bar: correctness of shape over polish; "it will not be perfect, and that's OK."

**Defaults set by Claude and announced (objections land in wave 1):**

- Multi-turn stays closed-form clocks only. The planner's horizon is this turn's end state; the
  *terms* of `state_value` look forward (clocks, readiness odds) — no reply-tree machinery.
- Deletion is as-you-go per track, never a deferred final sweep (T5 only mops up cross-track
  leftovers).
- The Worth↔prize exchange rate stays underived. Hand quality enters `state_value` through its
  consequences (readiness, survival, re-access), plus one explicitly AUTHORED POC scaffold
  constant (`POC_WORTH_PRIZE_RATE`, §4-T3) — ratified in wave 1, module-local to `state_value`,
  never added to `common/currency.py`, retired by the post-POC learning phases.

---

## 2. Built-vs-remaining inventory (source-verified 2026-07-31)

**FIRING (equation-owned, rungs deleted):** attach (ADR-0069) · evolve (ADR-0070) ·
promote/retreat (ADR-0100) · deploy (ADR-0086) · snipe relevance (ADR-0085) · forced-discard
needs-assignment (ADR-0065) · refresh-swing v1 SHED (ADR-0060) · energy-deny magnitude
(ADR-0062) · gamble (ADR-0039) · lethal solver (ADR-0030/0037) · race/path/threat-clock
(ADR-0040/0045/0064/0071) · Tier-4 Read (ADR-0026/0047/0051).

**DARK (built, OFF):** `deny_relevance` + `deny_strip_delta` (Issue #228 debt, two flips
recorded) · `leaf_hand_value` · `value_model` (parked; post-POC Issue #147 replaces it).

**SHADOW (computes, decides nothing — all die in this build):**
~~`_discard_shadow`~~ ~~`_refresh_shed_shadow`~~ ~~`_threat_shadow`~~ ~~`_recur_shadow`~~
~~`_opponent_target_shadow`~~ ~~`hand_size_relief`~~ — **ALL DEAD.** `_refresh_shed_shadow`
2026-08-01 (ADR-0101, item 2b promoted its subject); `hand_size_relief` 2026-08-02 (item 2c promoted
its subject into `score`, so the field and its `hs_relief` telemetry key went with the flats they
reported past); the other four 2026-08-02 (item 2h).

**UNCONSUMED (dead surface):** StateModel TheirSide clock family (every live consumer bypasses
to CombatMath with `charged`/`forward_ids`/harvest kwargs `build()` never receives) · sharing
machinery (`opponent_fingerprint`, `shares_opponent_with`, `probe`) · assorted DOA members ·
`combat.rider_recoil` · pilot `_forward_incoming_damage` wrapper.

**WEIGHT-DRIVEN (hypothesis families to be dissolved by T4):** fetch/search grab ladder
(~45 rungs, `doctrine_fetch.py`) · gust whether-to-play (5 rungs) · heal timing (2 rungs) ·
tool equip band (5 rungs) · hand-disruption (3 rungs) · supporter/draw economy · stadium ·
counter-place arming constants. (Opening/mulligan rungs are declaration-backed and stay,
whitelisted.)

**Known equation gaps absorbed into tracks:** Issue #225 (4 unpriced damage scalers), Issue #257
(opponent deck-search Energy accel invisible to the Threat Clock), Issue #204 (recur fuel not on
`turns_to_afford`), Issue #217 (deny deadline expressed three non-derived ways), Issue #237
(Deploy Marginal `_TO_BENCH` entry + harvest sharpening), Issue #232 (spare-body cliff),
Issue #254 (develop-rollout index-order dependence), Issue #212 (free-Item hold price),
Issues #220/#221/#222 (refresh v2 / relief promote / STRIP-GIFT grading).

---

## 3. Track map and dependency graph

```
T0 Spine (serial, ~1 session)
 ├──> T1 Substrate completion   (parallel lane A)
 ├──> T2 Phase-1 finish line    (parallel lane B, items independently parallel)
 └──> T3 state_value            (critical path)
        └──> T3.5 A1 remediation (critical path — INSERTED 2026-08-01)
               └──> T4 Turn Planner    (critical path)
                      └──> T5 Purge + integration (joins all lanes)

A1 Term sufficiency audit      (parallel AUDIT lane; blocks nothing, read-only)
A2 Apply-seam coverage report  (parallel AUDIT lane; blocks nothing, read-only)
```

**A1 — term sufficiency audit** (Issue #268, report: `term-sufficiency-audit.md`). Walks the four
DECKS rather than the corpus, because the corpus records what the OLD rung-driven agent looked at,
so a term the new architecture needs and the old agent never exercised leaves no trace in either
gate. Feeds T3's registry (its `blind_to` lists) and T4's blind-spot checklist. Read-only — it
produces findings, not code, and the disposition of each finding is decided after it lands.

**A2 — apply-seam coverage report** (Issue #269, report: `apply-seam-coverage.md`, census:
`tools/apply_seam_coverage.py`). The complement to A1: A1 asks whether `state_value`'s TERMS cover
what wins games, A2 asks whether the apply-seam can even produce the state those terms would score.
Resolves every effect site in the real card pool — our five decks plus the scouting artifact's 122
archetype builds — to one of §3b's three fates, weighted by copy count and by meta prior. Headline:
**69.4 % of effect-bearing sites REFUSE**, the dominant cause is clause-vocabulary breadth rather
than the shuffle or opponent choice, and the ENGINE-RESOLVED bridge resolves **zero** of the live
Ability options in the 372-frame corpus. Feeds T4's planning; findings become issues after it lands.

**T3.5 — A1 remediation** (Issue #278, 13 subtasks). A1's findings, implemented. Inserted into the
critical path by developer ruling 2026-08-01: **finish T3 → land T3.5 → start T4.** It is on the
critical path rather than beside it because T4's ordering heuristic evaluates `state_value` on every
candidate, so a term that mis-prices combat mis-orders every candidate that touches it — and under
1-ply differencing a mis-priced option is not merely undervalued, it is never explored. Four of the
findings are blockers, three of them one structural error seen from three sides (`state_value` reads
damage as a printed number rather than as the damage model's answer). Does NOT re-open ruled
omissions: those stay with T1 / T2 / T4 and are tabulated in the issue.

Critical path: **T0 → T3 → T3.5 → T4 → T5**. T1 and T2 fill parallel worktree lanes and must land
before T5 begins. Each track is one issue, one branch, one PR (multi-session inside a track is
fine; worktrees isolate lanes). Contract-freeze discipline: after T0 merges, its three contracts
change only by a wave-packet ruling — never silently by a downstream track.

**Wave ruling packets (the user's entire steering surface):**

- **Wave 1 (immediately after T0 files):** deny's two recorded flips (`84071010|0|decision|15`,
  `82225643|1|decision|11`) · the sound-rule whitelist (§6) · Issue #231 recommendation (keep the
  empty-Bench filter unconditional) · `POC_WORTH_PRIZE_RATE` authored-scaffold approval.
- **Wave 2 (T1+T2 landed):** their gate flips, batched.
- **Wave 3 (T4 landed):** the big batch — the planner takes over the trainer families; every flip
  the gates catch is presented frame → old vs new → recommendation.

Packet format: one issue comment per wave on the relevant track issue, one line per flip:
`frame_key | old decision | new decision | Claude rec + one-line why`. The user replies with
per-line verdicts; baselines are re-captured only after those verdicts (a baseline is a ruling
record — never auto-recaptured).

---

## 4. The tracks

### T0 — Spine: freeze the three contracts (serial; blocks everything)

1. **`state_value` term registry + currency rules.** `state_value(model) → float`,
   prize-denominated. Term families (each a pure function of the StateModel, each emitting a
   `working` dict): `prize_race` (lead + proximity), `survival` (my bodies:
   Σ prize_at_risk × halve(turns_to_ko_me − 1), both areas, harvest-aware),
   `threat` (their exposure to me: per-body `opponent_target_value` over my reachable KOs),
   `readiness` (per-body payoff × readiness odds × role relevance, off the existing
   needs/marginal machinery), `hand` (assignment coverage of live slots + re-access;
   Worth-denominated part crosses on `POC_WORTH_PRIZE_RATE` — authored, module-local,
   wave-1-ratified, retired post-POC), `development` (bench/line topology the deploy/evolve
   marginals already price). Double-counting rule: a fact enters through exactly ONE term family
   (registry documents which; the audit's coverage map is the checklist).
2. **StateModel completion API.** `build()` gains `read=`, `charged=`, `forward_ids=`, and
   TheirSide gains full public discard contents (`theirs.discard_ids`), hand count, and the
   threaded clock kwargs so model-routed calls are no longer strictly-worse than the bypasses.
   Signature + semantics frozen here; migration executed in T1.
3. **The apply-seam.** `apply_option(model, option) → model'` — closed-form hypothetical
   transitions for the option kinds the planner sequences (trainer play, attach, evolve, bench,
   retreat/promote; attack/end are terminal). Stochastic effects (draw N, search-reveal) return an
   EXPECTATION node: outcome classes enumerated by Option-Equivalence identity, weighted by the
   existing hypergeometrics (`deck_odds`), branching capped. The engine-sim *rollout* survives only
   as a T4 parity **test fixture**, never a runtime path — but the `_search_api` **seam** it rides
   is preserved, because §3b's ENGINE-RESOLVED fate needs it.

   **§3b — three fates, ruled 2026-08-01.** The per-kind table resolves every option to exactly one
   of: **MODELLED** (closed-form from Effect Clauses; always preferred) · **ENGINE-RESOLVED** (the
   clause vocabulary has a gap, but the effect is *provably deterministic*, the board is REAL and
   the call is 1-ply — simulate through `_search_api`, read the board back into a StateModel,
   difference normally, **emit telemetry**) · **REFUSED** (everything else). A silent no-op is never
   a fate: it prices the option at 0 delta, and at ordering time 0 means *never explored*.
   The gate is **"provably deterministic", not "unmodelled"** — an unmodelled effect that MIGHT
   touch RNG is REFUSED, fail-closed (ADR-0067). Refused outright: opponent-choice effects (no
   opponent model — an accepted POC gap), anything riding the shuffle (the engine has **no
   deal-seed**, so a sim is ONE SAMPLE not a distribution — Issue #178's defect — and nondeterminism
   breaks the deterministic replay both gates depend on), and anything at **depth ≥ 2** (the board
   is then a synthesized StateModel, which cannot be handed back to the native engine).

   **§3b — per-kind READ/WRITE footprints.** The table exposes, per option kind, the snapshot fields
   the transition WRITES and the fields it READS. Issue #263 consumes both to prove commutativity
   (two options commute iff neither reads what the other writes and they do not both write the same
   field) and collapse orderings into one canonical candidate per subset. **Fail closed:** an
   unknown or partial footprint commutes with NOTHING. A kind that REVEALS information (draw /
   search / reveal) can never join a commutative block whatever its footprint says — it changes the
   option set itself.

4. **§3c — StateModel completeness is a CONTRACT** (`src/common/snapshot_coverage.py`, ruled
   2026-08-01). The differencing system's worst failure mode is an effect writing to state the
   snapshot cannot represent: the delta reads 0, and 0 means *never explored*. So every zone or
   marker a card effect can write is enumerated with its snapshot home, or an explicit status —
   `owed` (**must name the owning track**) or `hidden` (deck ORDER, priced by `deck_odds` instead).
   An **audit test** walks the committed Effect Clause vocabulary and fails on a clause kind or
   rider with no declared write-set, and on any clause writing to a zone with no home.
4. **Sound-rule whitelist** drafted for wave-1 ratification (§6).

Deliverables: `src/common/state_value.py` skeleton (registry + signatures + working shape),
StateModel API stubs with frozen docstrings, `apply_option` interface module, whitelist section
in this doc, ADR-0092. Acceptance: contracts reviewed in wave 1; suite green (stubs inert).

### T1 — Substrate completion (parallel lane A; absorbs Issues #223, #204, #257, #225)

- Thread TheirSide: implement the T0 API; migrate the bypass census (snipe/deny/opponent-target
  rows, `_opp_cannot_punish_wincon`, planner survival reads, `_opp_turns_to_ready`, recur reads)
  onto model routes carrying `charged`/`forward_ids`; migrate Board raw-read stragglers
  (opp hand count, stadium, payable).
- Fold the legacy doom pair: add the `uncharged` policy to `combat.incoming`;
  `incoming_active_damage`/`forward_incoming_damage` become delegates (byte-identical fold —
  the 94.5%-agreement divergence stays a *policy*, not a second code path); delete the dead
  pilot wrapper.
- Oracle gaps: Issue #225's four scaler families priced in the Damage Formula; Issue #257's
  opponent deck-search accel entering the charged budget; Issue #204's `discard_recur_fuel` on
  `turns_to_afford`.
- Dead-surface purge: `rider_recoil`, DOA StateModel members, stored-unread fields (keep the
  sharing machinery — pre-built for post-POC Issue #150; document as such).

Acceptance: zero direct CombatMath calls on model-covered questions outside the documented
deliberate list; gates green; flips → wave 2.

### T2 — Phase-1 finish line (parallel lane B; items independently parallel; absorbs Issues
#228, #189, #217, #220, #221, #222, #237, #232, #254, #212)

- **Arm deny:** flip `deny_relevance` + `deny_strip_delta` ON after wave-1 rules the two recorded
  flips; DELETE the ADR-0062 magnitude-oracle OFF path and the flag fallbacks; resolve
  Issue #217's deadline question inside the armed instrument (derived clock or ruled-keep, its
  two pre-registered gates decide).
- **Gust repoint (old Issue #189):** gust whether-to-play leaves the 5-rung band — the play is
  priced by the T4 differencing once available; T2 does the *target/keep* side cleanup on the
  shared marginal and stages the rung deletion behind T4's landing (single-commit swap, no
  shadow).
- **Refresh v2 swap (old Issues #220/#222): DONE 2026-08-01 (ADR-0101).** `set_keep_v2` SHED
  replaces v1 Σ keep-cost as the decider; `_refresh_shed_shadow` DELETED (with its telemetry key,
  `needs_sweep`'s refresh half, and the newly-dead `_refresh_cycle_adaptive`). STRIP/GIFT grading
  **resolved as PARKED on measurement** — 59.4% of an opponent's rep prices `role_value` 0, so
  design A would bias the GIFT leg in ADR-0060's CRITICAL direction; the flats stay typed under
  `firing-equation-constants` and the prerequisite (`gusting-keepcost-design.md` §2's shared role
  sheet) is named. Gates: Discrimination PASS/0 moved, Decision 2 FIX + 3 REGRESSION → wave 2.
- **Relief promote (old Issue #221): DONE 2026-08-02 (ADR-0102).** `hand_size_relief` enters score
  as the SURVIVAL a refresh buys — two `turns_to_ko_me` reads across one counterfactual on the
  Damage Formula's own `atk_hand` / `def_hand` keys, in the shared sub-prize survival currency. It
  prices **both** hands, because the set scales off both: Alakazam's Powerful Hand (20/card, theirs)
  and Mega Froslass ex's Resentful Refrain (50/card, MINE), the latter moved by every refresh
  including a self-only Lillie's. `play-harlequin-vs-hand-size` (+25), `disrupt-when-unfavored`
  (+18), `strip-the-stacked-engine-hand` (+22), the reporting-only field/telemetry and the two Board
  signals left unconsumed are all deleted. Lever A returns as `phase_scale`, not a second
  `_DENIAL_UNFAVORED` (ADR-0078 decision 6). Gates: Decision PASS / 0 unruled; Discrimination 2
  `OK → MISS` **held out onto Issue #262** — both caused by the +25's deletion alone, neither a decision
  move (the agent still plays the human's option on both).
- **Deploy finish (old Issues #237/#232): DONE 2026-08-02 (ADR-0086 amendment G, ADR-0096 build
  note).** `_TO_BENCH` is priced — the supplier split is by CERTAINTY, not zone, so a revealed fetch
  candidate joins the hand on the ready side and leaves the deck counts. `bench_harvest` enters as a
  SECOND ROUTE to a benched body (riders reach it without a promotion, out of one shared budget), on
  one derivation shared with the live path so the delta's two sides cannot drift. The spare-body
  cliff is resolved by DELETING `keep-a-bench` (+60) — the whole gap — with `baseline_bench.py`;
  the *escalating* slot price stays T3's `development` work per ADR-0096's own Consequences.
  `bench-fill-a-basic` (+12) deleted with the wiring; the bench take-fewer bar moves to `< 0`.
  Gates: Discrimination PASS, 1 IMPROVED (`86090164|1|turn|6`); Decision PASS, 250/346
  unchanged. The
  motivating frame `86091728-43` does NOT flip and the reason is recorded: its ruling needs the
  deck-tracker's prize inference and an `item_lock` worth entry, neither a deploy-seam gap.
- **Rollout order fix (old Issue #254): DONE 2026-08-02 (ADR-0103).** The order-dependence was not
  the search's but the POLICY's — the develop rollout re-runs `_evaluate` on each intermediate
  SearchState, whose `(score, needy_line_attach)` sort fell through to the ENGINE MENU INDEX. The
  third key is now the ADR-0091 fingerprint, index demoted below it; `_greedy_grab` takes the same
  key (composed with item 2d's context-dependent take-fewer bar, which landed on the same loop).
  Unconditional and LIVE (a sim-only tie-break would simulate a different agent).
  **Leaf Lab CLASS ASYMMETRY 5 classes → 0**, Discrimination Gate PASS / 0 moved, leaf SOLE-top
  38→39. One Decision-Gate REGRESSION went to wave 2 and was **ruled there**
  (`86089120|0|decision|14`): the user ruled the two tied attaches genuinely equal in value on a bare
  Dreepy, so the correction's `correct` names one of an indistinguishable-by-value pair — recorded as
  a **`transposition`** (ADR-0088), the first since ADR-0091 retired the last one. Both gates PASS.
- **Free-Item hold (old Issue #212): DONE 2026-08-02 (ADR-TEMP-261, item 2f).** `_DENIAL_ITEM_COST`
  is DELETED and generalized into the keep machinery as
  `max(needs.keep_v2(card), hold_value.ITEM_HOLD_FLOOR) × currency.ITEM_HOLD_WORTH_RATE` —
  `Pilot._item_hold_price` off the same `_resolve_needs` the refresh SHED and the discard decider
  already decide on. **The floor is load-bearing and was measured before it was written:** on all four
  committed deny anchors a role-less Hammer's `keep_v2` reads `0.00 / 4.82 / 3.57 / 0.00`, because its
  only slot is the very `deny` slot the fire rung is pricing — so a pure keep reading collapses to 0
  on exactly the boards where the strip whiffs and re-opens ADR-0093 decision 4's defect. The floor
  binds on all four anchors, so the swap is arithmetically identical for deny on every ruled frame —
  Issue #212's *"must not perturb the deny 5/5"* met by MEASUREMENT (not by construction: a Hammer
  covering a second live `deny` slot would price above the floor, which is the equation working) —
  and that is what keeps the build's gate movement attributable to the sequencer half. The ~1.0 worth↔damage rate the constant silently implied is now explicit and
  seam-scoped beside `DEPLOY_BAND`, with the same reconciliation debt against `poc-worth-prize-rate`.
  **This item also lands ADR-0095 decision 1**, the sequencer change that ADR assigns to T2 and no
  other item owns: `_finish_turn_last`'s free band splits on INFORMATION
  (`0 informative · 1 committing · 2 Supporter · 3 attach · 4 shuffle · 5 ender`), keyed off a
  Function Tag with untagged defaulting to committing. **ADR-0095's falsifiable prediction held** —
  `82225643|1|decision|11` now takes the human's Pokégear while the Hammer stays ENDORSED (an ordering,
  not a suppression, exactly as the ruling asks). Gates: Discrimination PASS (0 unruled, held-outs
  unchanged); Decision surfaced **1 REGRESSION** — `82225643|1|decision|12`, the next frame of the
  same turn, and the same frame the Discrimination Gate reports `MISS → OK`, so the valuation agrees
  with its ruling and only the SEQUENCER re-orders. Not self-ruled: put to the user with its
  evidence and **USER-RULED ACCEPT 2026-08-02** (`fixed`, non-voiding — the boundary orders the dig
  ahead of the Hammer across two actions of one turn, which is what the adjacent f11 ruling asks for,
  and f12's own `correct` was adjudicating Hammer-vs-ATTACK). Baseline re-captured at the ruling
  commit; **both gates PASS**, agree 251/345, suite 4504. The leaf baseline is deliberately not
  re-captured (it passes), and what the Decision re-capture absorbed beyond its own ruling is named
  in `docs/ci.md`'s provenance table.
- **Shadow deletion: DONE 2026-08-02 (item 2h), except the `_DISCARD` ladder.** All four shadows,
  their `Decision` fields and telemetry keys, the v1 discard fallback (`discard_keep_value` flag +
  `_discard_equation_pick`) and `_discard_equation_rows`' now-unread v1 ranking are deleted, along
  with the three probes whose entire contract was reading them (`threat_sweep`, `needs_sweep`,
  `doom_audit` — ADR-0089: a RULING's script dies with its answer) and the blunder shell's
  discard-shadow dropdown. Gates green, suite green, zero decision movement.
  **The tuned `_DISCARD` ladder is deleted too** (12 rungs, by name in the PR body), but only after
  its SECOND consumer was re-pointed: it was also the scoring basis of the fetch doctrine's shed
  predictor, so deleting it blind would have silenced three live cost-netting rungs
  (`costly-fetch-sheds-junk`, `dont-shed-a-live-card`, `dont-shed-a-key-card`) — the Issue #238
  shape. User-ruled 2026-08-02: re-point the predictor onto the equation that DECIDES the discard.
  `_shed_signals` now prices the two cards the v2 assignment would actually shed
  (`needs.removal_score`, extracted so the predictor and `cheapest_removal` share one objective),
  and the deadness/re-access derivations are shared by both row builders rather than spelled twice.
  Every ladder case pinned as a corpus ruling is reproduced by v2 unchanged. Decision Gate PASS and
  the agree rate RISES (249/345 → 251/345). Discrimination Gate is RED on two frames
  (`85045840|0|decision|10`, `|12`) → wave 2: the shipped decision on both is unchanged and already
  matches the human, but the re-pointed bands decline the Ultra Ball inside the sim's continuation,
  so the human's line develops less on the simmed end board. Not self-ruled and not tuned around —
  **user-ruled ACCEPT 2026-08-02**, both frames recorded `fixed` (non-voiding) and the leaf baseline
  re-captured against the ruling. Both gates PASS.
  Two findings the sweep surfaced rather than caused, both pre-existing on `main` at `ce28431`:
  **Issue #294** — `cheapest_removal` is blind to the `pitch` term, so two RULED ladder-win cases
  shed the wrong card in shipped play (kept as strict-xfail TARGETs so the deletion of the shadow
  that showed it does not bury it); and the leaf-profile test was crediting the deny slot for
  `_recur_shadow`'s model reads, so `DENY_SLOT_PROFILE` turns out to be unexercised by that file's
  corpus.

Acceptance: PROFILE has zero OFF value flags (except `value_model`, deleted-or-inert pending
post-POC Issue #147); zero shadow emitters; gates green; flips → wave 2.

⚠️ **The OFF-flag clause is not met and no item in this track owns it.** After item 2h,
`PROFILE` carries TWO `False` value flags: the named exception `value_model`, and
**`leaf_hand_value`** (ADR-0065 WP-N5b — the develop-rung leaf's actionable-resource term, armed-off
2026-07-20 pending its leaf-lab bench). Items 2a–2h between them touch nothing that arms or retires
it. Flagged here rather than quietly satisfied by counting only the flags a track happened to reach:
T5's PROFILE collapse is the natural owner, and it needs either the bench result or a deletion.

### T3 — `state_value` (critical path; old Issue #145 merged)

Implement the T0 registry: compose the FIRING equations into the one scalar; per-term `working`
emission (the post-POC correction rounds need it; it costs little now); incremental eval via the
StateModel's existing lazy memo (the ADR-0068 amendment-A requirement); replace the develop
rollout's `_engine_leaf_value` composition (readiness-leaf constants absorbed where redundant,
whitelisted where load-bearing); `_predicted_loss` and the KO band survive as terminal terms.
Unit basis: prizes; damage crosses on `PRIZE_DAMAGE_RATE`; Worth crosses only on the wave-1
scaffold. Acceptance: `state_value` scores every corpus frame without error; leaf-lab
discrimination on the develop corpus does not regress unruled; flips → wave 3.

### T4 — Turn Planner (critical path; old Issue #165 merged)

The sequence composer: enumerate candidate within-turn sequences over Option-Equivalence classes
(beam with per-class top-k by local marginal; attack/end terminal; budget-aware for the 2-vCPU
grader), evaluate `state_value(end)` through the apply-seam, commit the argmax sequence's first
action. The preemptive sound ladder stays ABOVE it (lethal solver, forced lines — whitelisted).
This is where the unbuilt trainer families get priced: fetch/search (expectation over reveal
classes), draw supporters, tools, stadium, heal, gust whether-to-play, and the Issue #165
maneuver frames (f32/f35 retreat-to-wall item-lock, f82 Adrena-Brain). Their rung piles are
DELETED in the same PR (directive: the swap is the deletion; `retreat-to-wall-the-line` +30 and
the fetch ladder die here). Engine-sim parity fixture proves the apply-seam on the old develop
corpus, then the runtime engine rollout retires. Acceptance: every previously-weight-driven
family decides through the planner; gates green; flips → wave 3.

### T5 — Purge + integration (joins all lanes)

Cross-track leftovers: any rung not deleted by its owning track and not whitelisted; PROFILE
collapse of retired flags; the wave-3 ruling session; hierarchy doc regenerated from source; a
smoke gauntlet (a few hundred games, crash-free = pass — explicitly NOT a win-rate gate);
Issue #136 checked off through the POC line. Acceptance = §7.

---

## 5. Steering model (what the user does)

Three touches, nothing else: (1) wave ruling packets — per-frame verdicts, minutes each;
(2) PR review per track, as deep as desired (gates enforce nothing-unruled regardless);
(3) the escape hatch — a track that hits a genuine doctrine fork files ONE question into the
next wave packet; it never opens a grill. Budgeted escape-hatch count: ≤2 across the build
(build-rule 11 says arming exposes defects; expect them in T2/T4).

## 6. Sound-rule whitelist (RATIFIED wave 1, 2026-08-01 — amended by the Issue #259 grill)

Rules that SURVIVE the purge because they encode game structure or fail-direction policy, not
strategy hypotheses. **Every entry is TYPED and names the board fact it guards** (ADR-0099):
`structural` = permanent; `provisional` = a substrate-gap workaround, which MUST carry a dated
retirement test; `authored-scaffold` = a constant, which MUST carry a reconciliation note and a
post-POC fitting queue entry; `composed-into-the-leaf` = a per-seam equation that stops DECIDING
when the composer lands but survives as `state_value` term-family math, which MUST name the term
family that absorbs it. **An untyped entry is rejected by the T0 registry** — the flat draft
list put ONE board fact (an empty Bench under a knock-outable Active) on §6 three times in three
shapes, violating T0's own double-counting rule, and nothing about writing it prompted the catch.

The list has **two populations**. The first three types still decide something at runtime, and the
one-guard-per-fact rule is about them. `composed-into-the-leaf` is math, not a guard: those four
entries are here so that "no longer a decider" is not read as "delete it". Issue #264's disposition
table uses this same label.

**`src/common/sound_rules.py` is the machine-checkable authority**; this table is its rendering, and
`tests/strategy/test_sound_rules.py` cross-checks the two by `id` so they cannot drift.

| id | entry | type | fact guarded / reason | retires when |
|---|---|---|---|---|
| `ko-score-band` | `KO_SCORE` band + `_LINE_CAP` invariant | `structural` | a prize is never outbid by a positional term | — |
| `setup-never-bench` | Set-Up never-bench (ADR-0086 d9, `pilot.py:1750`) | `structural` | deferring is weakly dominant — optional placement (rulebook L97), no attack reaches me first either seat, zero damage-counter Abilities on a Basic | — |
| `empty-bench-filter` | empty-Bench forced deploy filter | **`provisional`** | loss condition, `docs/rules.md` §7 case 2 | after T1: `reachable_incoming` answers on every post-setup empty-Bench corpus frame AND both gates green without it → `_predicted_loss` becomes the sole guard |
| `predicted-loss` | `_predicted_loss` (−KO_SCORE bench-empty doom) | `structural` | same fact, CombatMath-gated — the ONE surviving guard on retirement | — |
| `information-before-commitment` | `_finish_turn_last` — the **information-before-commitment** boundary | `structural` | an informative reversible play weakly dominates a commitment; the engine re-presents the menu | — *(BUILT 2026-08-02 by item 2f, ADR-0095 d1: until then the free band was ONE tier and the entry described an intent, not a boundary)* |
| `doom-ceiling-fail-direction` | worst-case doom ceiling as survival fail-direction | `structural` | fail-direction policy (a *policy parameter* after T1's fold) | — |
| `declaration-rungs` | opening/mulligan declaration rungs | `structural` | deck-declared, not tuned | — |
| `lethal-solver-preemption` | Lethal-Solver preemption above the planner | `structural` | sound win detection outranks every heuristic | — |
| `firing-equation-constants` | authored constants inside firing equations (ROLE_TIER/TAG_TIER, readiness-leaf values, planner sub-prize constants, confidence seeds, the refresh swing's STRIP/GIFT/FRESH, the free-Item hold floor `hold_value.ITEM_HOLD_FLOOR` + its seam rate `currency.ITEM_HOLD_WORTH_RATE`) | `authored-scaffold` | tolerated for POC | post-POC learning phases — plus one named prerequisite: STRIP/GIFT retire on `gusting-keepcost-design.md` §2's shared opponent role sheet (ADR-0101). The hold floor/rate joined 2026-08-02 as a net REDUCTION (item 2f: the deleted `_DENIAL_ITEM_COST` was the same number hard-gated to one card class) and carry `DEPLOY_BAND`'s reconciliation debt against `poc-worth-prize-rate` |
| `poc-worth-prize-rate` | `POC_WORTH_PRIZE_RATE` (T3-local) | `authored-scaffold` | reconciled against trainer ≈1.0 / energy ≈6.7 / deploy ≈0.83 (ADR-0097) | post-POC fit against ruled spend-vs-hold frames converges |
| `apply-seam-coverage-floors` | apply-seam per-option-kind coverage floors | `authored-scaffold` | ADR-0098 d3 | post-POC review as the seam table grows |
| `attach-value-composed` | `attach_value` (ADR-0069) | `composed-into-the-leaf` | the marginal value of attaching an Energy → composes into **readiness** | — (role change, not retirement) |
| `evolve-value-composed` | `evolve_value` (ADR-0070) | `composed-into-the-leaf` | the marginal value of evolving a body → composes into **readiness** | — |
| `promote-retreat-value-composed` | `promote_retreat_value` (Issue #141; ADR-0100, was ADR-0073 before PR #267) | `composed-into-the-leaf` | the marginal value of changing who is Active → composes into **survival** | — |
| `deploy-value-composed` | `deploy_value` (ADR-0086) | `composed-into-the-leaf` | the marginal value of putting a body into play → composes into **development** | — |

**Role change, not deletion (added 2026-08-01, Issue #263 ordering ruling):** the composer's beam
ordering became **uniform 1-ply differencing** — apply each candidate through the apply-seam, score
`state_value` on the result, rank by the delta. Under the old phrasing the per-seam equations
provided the local ordering, which left heal / fetch / tool / stadium / draw with no local price and
therefore pruned at zero before the leaf saw them. So the four equations stop being deciders for any
option the enumerator covers; their math is ratified and stays, as leaf internals and optionally as
pruning approximations.

**Deleted by this ratification:** `keep-a-bench` (+60) — it guards nothing the filter does not
already guarantee at MAIN (the filter runs *after* `_finish_turn_last`), and per Issue #231's own
numbers it IS the spare-body cliff (1.96 → 61.96). Deletion is measured, not blind. **Carried out
2026-08-02 by T2 item 2d**, together with `baseline_bench.py` (the rung was the module's only
remaining member): both gates PASS with it removed — Decision 250/346 unchanged, Discrimination
182 → 183/248.

Everything else with a tuned weight is deleted by its owning track.

## 7. POC acceptance (the definition of done)

1. Zero hypothesis weights consulted on any `decide()` path outside the ratified whitelist.
2. Zero shadow emitters; zero v1/fallback decider paths; zero dark value flags (sole exception:
   the parked `value_model` seam, owned post-POC by Issue #147).
3. The StateModel is the sole supplier: no undocumented CombatMath bypasses on model-covered
   questions; TheirSide fully threaded.
4. Suite + both gates green with every flip ruled (waves 1–3 complete; baselines re-captured
   only on rulings).
5. Smoke gauntlet completes crash-free.
6. `state_value` + Turn Planner decide every previously-weight-driven family; the fetch ladder,
   heal/tool/stadium/hand-disruption/gust-whether rungs no longer exist in the tree.

## 8. Disposition of prior issues

Closed as superseded (content folded into the named track): #144→T2 · #145→T3 · #165→T4 ·
#189→T2 · #204→T1 · #212→T2 · #217→T2 · #220→T2 · #221→T2 · #222→T2 · #223→T1 · #225→T1 ·
#228→T2 · #232→T2 · #237→T2 · #254→T2 · #257→T1. Ruled-then-closed in wave 1: #231. Untouched
(post-POC or out of scope): #146–#151, #190, and the corrections/gate-machinery family
(#224, #229, #230, #238, #251, #256).
