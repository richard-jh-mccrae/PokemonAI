# Fetch-Closure & Card-Worth — Build Handoff (2026-07-17)

Self-contained pickup doc for building the fetch-chain-closure / card-worth system. **Read first:**
[hypergeometric-fetch-closure.md](hypergeometric-fetch-closure.md) — the 14-round grill record; it
is the SPEC (every ruling source-verified, every number's provenance stated). This doc is the BUILD
ORDER. Writeup-facing summary: [tier-2-chance-ev.md](../architecture/tier-2-chance-ev.md) §"Fetch-chain
closure & card worth".

## TL;DR

The gamble/fetch/shuffle economics undercount reality: outs are the tutor+recycle+draw-engine
CLOSURE, not literal cards, and the cost of a shuffle is graded re-access, not a binary veto. The
14-round grill produced a complete Tier-0 closed-form spec — one primitive (window hypergeometric ×
prize split over closure entry points, deterministic interior hops) pricing both the GAIN side
(gamble outs) and the COST side (keep-value). **Already built and suite-green (2940 passed):** the
three-deck tag audit (7 fixes + 2 consumer recalibrations) and full gamble observability
(trace → `@T` telemetry → blunder-shell dropdown). Everything else is designed, not built.

## Ground rules (repo invariants — violating these is how builds die here)

- **Verify at source, never memory** (CLAUDE.md): card facts from `data/EN_Card_Data.csv` /
  `CardStat`; rules from `docs/rules.md` → `docs/rulebook.txt`; tags from
  `src/common/card_functions.json`. The set differs from mainline TCG.
- **Currency zone:** a graded term REPLACES its guard family and re-audits it, never bolts on
  beside it (ADR-0060's +76 incident; round 11 lived it twice — see Gotchas).
- **Tags stay boolean, additive, via `tools/meta_tracker/function_overrides.json`** (probe rebuilds
  never clobber overrides). Parametric predicates go in `card_effects.json` (ADR-0032). Attack-based
  accel is NEVER card-tagged (the ADR-0064 burst-budget scan reads `energy_accel` tags).
- **Fail directions:** an endorser under-counts (bad input → 0.0); a suppressor assumes-present
  (bad input → 1.0). Never raise (grader safety).
- **Mid-sim guard:** never write traces/state under `self._planning` (engine re-runs the policy).
- **Test through the real `decide()`/`explain()`**, never isolated probes. `tune.py` clobbers
  `tuned.json`. `src/cg/` is off-limits. Cross-platform (pathlib, `encoding="utf-8"`).
- Suite: `python -m pytest tests/ -q` — expect ~2940 passed; `tests/meta_tracker/test_dashboard.py`
  + `test_pipeline.py` fail without `plotly` (env gap, pre-existing).

## Status

| Piece | State |
|---|---|
| 14-round grilled spec | **DONE** — `hypergeometric-fetch-closure.md` |
| Tag-completeness audit (3 decks, 50 cards) | **BUILT** — 7 additive fixes (140/305/674/675 + tutor_pokemon on 1142/1152/1225), 2 consumer recalibrations, suite-green |
| Gamble observability | **BUILT** — `_gamble_trace` → `Decision.gamble` → sparse `@T` `gamble` key → shell `<details>` dropdown; pinned in `test_gamble.py` |
| Correction-seeded test corpus | **BUILT** — `tests/strategy/test_hyperclosure_corpus.py`: 27 PINS (incl. the 2 TAG_TIER worth flips) + 4 SUBSTANCE PINS + 4 xfail-strict TARGETS; fresh pilot per replay; diagnoses in `combat-tempo-cluster-findings.md` |
| WP1 Stage-1 closure outs | **BUILT** — `_gamble_ko_classes` outs = literal ∪ tutor/recycle closure; post-Item Supporter supplement (5-tuple) |
| WP3 draw-engine + accel clauses | **BUILT** — `card_effects.json` draw/accel clauses; AttackStat `recover*` tier (Turbo Flare deck-source) |
| WP4 Stage-2 draw engines | **BUILT** — `draw_hit_with_engines` two-window closed form (exact at depth 1) |
| WP5 Outcome classes | **BUILT** — evolution-KO / gust / pump / survival / bench-fill; each void-if-in-hand + det + legality |
| WP6 Keep-value replaceability floor | **BUILT** — `common/card_worth.py` tier table; graded `_keep_cost` REPLACES the 3 binary gamble stand-downs; suite-green (2975) |
| WP7 oracle module + skill loop | **CORE BUILT** — `common/fetch_closure.py` (graph) + `common/card_worth.py` (worth backend); ADR-0065; role-coverage lint. Two consumers converged (gamble keep-floor WP6; **refresh SHED** 2026-07-18 — flat `_REFRESH_SHED` + 4 `hold-*` guards → `Σ keep_cost`). Fetch grab/pitch + plan-tier credit + gate library + skill loop STAGED |

## Work packages (priority order; each lands separately, suite-green, trace-extended)

**WP1 — Stage-1 closure outs in `_gamble_ko_classes`** (planner.py:~1590). Add to each class's outs:
Item-class deck tutors whose predicate matches the missing slot (Energy Search 1119 any-Basic,
Fighting Gong 1142 {F}-only + its Basic-{F}-Pokémon branch, Energy Search Pro 1100) AND ≥1 matching
target remains in deck; recycle Items whose target sits in the visible discard (Energy Retrieval
1118, Night Stretcher 1097). Supporter tutors count ONLY when the refresh was an Item (Unfair Stamp
1080 — 4/5 refreshes are Supporters, the slot is spent). Predicates from WP3's clauses (interim:
a small in-module table verified against card text — NOT bare tags; Gong's tag can't see the
{F}-lock). Extend the trace's `sought` with closure outs. Errs by under-counting only. Gate: unit
tests + the corpus family "fetch-target valuation".

**WP2 — Pre-anchor gambles** (spec §design point 4). Replace `_best_gamble_line`'s
`stand_down("pre-anchor…")` with the prize-split-weighted window sum: unseen copies u of a class
split over deck+prizes (ADR-0029 `p_contains` weights), P = Σ_j w_j × window(j), ≤5 `comb` terms.
Rewrite REQ-GAMBLE-0003 (pre-anchor now PRICES instead of standing down; feature-off stand-down
stays). Tutor-out validity goes probabilistic (void only when every target is provably prized).

**WP3 — The clause tier** (`src/common/card_effects.json`, ADR-0032 shape). Add the spec §Round-11
backlog: fetch/tutor predicates (1086 ≤70-HP Basics ×2 → BENCH; 1097/1110/1118 recycle; 1121
cost-discard-2; 1122 top-7-take-supporter; 1142 {F}-locked; 1145 mega; 1152 no-Rule-Box; 1189
no-Ability evolution; 1198 2-diff-Basics-1-attached; 1219 any-Trainer; 1225 evolution + ANY energy
incl. Special; 1071 Supporter on-bench-play), draw engines (66 draw-3-self-shuffle; 120
top-2-take-1; 140/675 conditional; 1080 5/2 post-KO), accel (666/678 via-attack; 1240
discard→Stage-2 prize-behind), 1120 coin, 17 Ignition {C}{C}{C}-on-Evolution. Migrate
`doctrine_fetch._FETCH_FILTERS` to consume clauses (it's the fifth private-valuation shadow; note
`tutor_energy` has NO filter today — the whiff guard can't check energy tutors). WP1's interim
table folds in here.

**WP4 — Stage-2 draw engines.** The two-window closed form (spec §Stage 2): P = P₁ + [P(miss) −
P(miss ∧ no usable engine)] × P₂ over the thinned pool. Depth = board-supported engine capacity
(eligible pre-evo/engine pairings + bench space; rules.md §4 evolution timing), NOT a constant —
measured: depth 1 ≈ +4.5pp, depth 2 ≈ +0.6pp and only legal with 2 eligible pre-evos. Window-2
outs = the full Stage-1 union (engine→tutor→energy is the common chain). Recon = top-2-take-1
greedy (out > engine > other); Run Away Draw returns itself+attached (known-composition pool shift).
On-board engines with unused abilities: unconditional windows, sequenced BEFORE the refresh.

**WP5 — Outcome classes (the enabler taxonomy, spec §Rounds 5/12).** Order: **evolution-KO first**
(highest value; `_gamble_ko_classes` prices only the current Active's attacks today — planner.py
feeds it `board.my_active_id`'s stat; evolving keeps Energy, a Mega ex does NOT end the turn),
then gust (Boss's 1182 enables the benched-target KO), damage pump (`CardStat.damageBoost` +
`damageBoostType`/`damageBoostVsEx` — verified parsed, provider.py:97-100), survival
(switch/heal vs the ADR-0064 predicted-loss shape), bench-fill anti-donk (Poffin's BENCH
destination). Generalize the shortfall gate: `shortfall ≤ 1 + reachable accel attaches` (Crispin /
`energy_accel` edges), derived per slot type. Each class: void-if-in-hand + det baseline +
legality gate. Every class extends the `gamble` trace.

**WP6 — Keep-value: the replaceability floor + graded swing** (spec §Rounds 6-8). **BUILT** (the
gamble protected-hand jurisdiction; refresh-swing SHED re-audit deferred to WP7's oracle fold).
`common/card_worth.py` owns the ONE tuned currency (`ROLE_TIER`/`ENERGY_TIER`/`ACE_SPEC_TIER` +
`keep_cost`); the Pilot derives re-access odds from the closure (`_card_reaccess_outs` = the fetch
graph pointed backwards) and prices `_keep_cost = role_value × (1 − reaccess_odds)` per held card.
`_best_gamble_line` REPLACES the three binary protected-hand stand-downs (`wincon_in_hand`,
`line_preevo_in_hand`, `irreplaceable_tool_in_hand`) with a graded `hand_keep` term folded into the
det baseline (`ev > det + hand_keep`; `best` scores `ev − hand_keep`; the eval row carries a `keep`
field). A KO gamble now fires while holding a *re-accessible* wincon/pre-evo and stands down only
when the held plan piece is genuinely closure-unreachable — the replaceability floor, graded, zero
new constants. Pinned in `test_card_worth.py` (3) + `test_gamble.py`
(`test_wp6_ko_gamble_fires_despite_a_held_line_preevo_via_graded_keep_cost`); full-family re-audit
of strategy/blunder/agents = no flips. Original design: Keep-cost(X) =
role value × ΔP(class need met by X's DEADLINE | keep vs shuffle) — the closure pointed backwards;
deadlines from the gate library (evolution eligibility, quota k-1, closing edges from
`reachable_incoming`); sets not sums (discard PAIRS valued jointly — `_shed_signals`' independent
top-2 is the naive form); zone/deck-signed (Kyogre-class discard-fuel). ⚠️ This REPLACES the
ADR-0060 flat prices and the binary hold-* guards' jurisdiction — full family re-audit against the
six ADR-0060 corrections + the corpus, per the currency-zone rule. Unblocks the development gamble
(third family — the empty-bench Turbo-Flare→Staryu case, spec §Round 13) and the mid-value classes.

**WP7 — The card-worth oracle module + skill loop** (spec §Rounds 7-9). **CORE BUILT 2026-07-18**
(the "one module home" — Round 10 §2; behaviour-preserving, suite-green). `common/fetch_closure.py`
now owns the tutor/recycle/search GRAPH as pure Pilot-independent functions (`fetch_target_matches`,
`reaccess_outs`, `fetch_reaches_pokemon`); the Pilot's `_fetch_target_matches` (was on FetchMixin),
`_card_reaccess_outs` / `_fetch_reaches_pokemon` (PlannerMixin) DELEGATE — the fetch doctrine, the
gamble gain side, and the keep-cost read ONE implementation. `common/card_worth.py` owns the WORTH
currency + primitives (`role_value` added; `_role_value` delegates). ADR-0065 earned. Role-coverage
lint (`tests/strategy/test_role_coverage.py`) pins the Round-9 §5 guard (soundly checkable subset).
STAGED (each a corpus-gated flip, per "staged like the ADR-0064 five-call-site refactor"): the refresh
SHED convergence (ADR-0060's flat −8 + `hold-*` guards → `Σ keep_cost`, re-baselines the six
corrections), the fetch grab/pitch convergence, the gate library + deadlines (no consumer yet — Round
8 §6 anti-speculation), the held-card-risk tier-2 seam, and the skill loop. Original design:
`common/fetch_closure.py`
(typed graph + clause predicates) + `common/card_worth.py` (role tier table — ONE tuned currency —
gate library, deadlines, keep-cost), extending `deck_odds.py`. Doctrines stay the deciders and
become consumers (grab/pitch, refresh swing, gamble floors, plan-tier credit — the four shadows
converge). Earns its OWN ADR at this point. deck-genie gains the Role-Sheet output contract
(declare identity: Lines/roles/sparse SYNERGIES — the Meowth-ex lesson: a wrong declared role is
worse than none); deck-align re-audits the three agents and FOLDS deck rules the oracle now derives
(ADR-0034). CI coverage lint: every `deck.csv` card resolves to a role.

**Cross-cutting — the correction-seeded test corpus** (spec §Round 10, with correction ids per
family). **BUILT 2026-07-18** — `tests/strategy/test_hyperclosure_corpus.py`: the 35 vetted
shuffle/fetch/discard corrections replayed through the real `explain()`. Two roles (the TDD ratchet):
**19 PINS** the shipped agent already ranks correctly (plain assertions — the regression net that
makes each staged convergence flip provable) and **16 TARGETS** the convergence must FIX
(`xfail(strict=True)` — green while unfixed, a red XPASS the moment a flip lands = "promote to pin").
`reviewed.json` joined first — the 6 refuted/covered ids + 1 no-agent record are provably excluded
(`test_excluded_ids_are_provably_out`). Families: discard-pair valuation, fetch-target valuation,
hold-the-fetch, shuffle timing/keep-value, discard-as-resource. This is the acceptance suite the
refresh-SHED and grab/pitch convergences land against.

## Gotchas (paid for this session — don't re-buy)

- **Accurate data flips calibrated consumers.** The round-11 tag fixes broke 3 pinned tests: a test
  had pinned "Lunatone untagged" as ground truth; `dig-before-commit` +20 endorsed BENCHING a
  draw-tagged body (fixed: stands down on Pokémon plays — benching a later-drawing body is not a
  dig; Meowth ex belongs to `bench-the-supporter-tutor`); `fetch-the-support` +15 stacked with a
  deck engine rung above the +35 famine Energy (fixed: famine stand-down per its own charter).
  Expect the same class of flips in WP1/WP5/WP6 — re-baseline deliberately, per the corrections.
- **The gamble trace is part of every WP's definition of done** — closure outs land in `sought`,
  new classes land in `classes`, new stand-downs get named reasons. `test_gamble.py` pins the
  shapes; the shell dropdown renders whatever the record carries.
- **plan_turn caches by fingerprint** — `_gamble_trace` is cleared per fingerprint, persists across
  same-turn decisions (intended). The replay-locked path never carries it.
- **_gamble_ko_classes returns 5-tuples** `(copies, value, label, sought, (sup_copies, sup_ids))`
  since 2026-07-18 (4-tuples round 14 → the 5th slot is the post-Item-refresh Supporter supplement,
  applied per refresh option in the pricing loop; the trace carries it as `post_item_*`).
- **Synthetic fixtures and the famine gate:** a `state()` board with no Active energy IS the famine
  — power the Active in fixtures that aren't about famine (test_fetch_doctrine.py precedent), and
  don't make the support-in-play card the Active (self-defeating gap-gate).
- **Illustrative numbers in the spec** (65%, +4.5pp, +76…) are labeled with their scenarios — recompute
  for tests, don't assert the doc's numbers.
- **Windows + Linux both first-class** — the suite runs on both in CI.

## Where things live

- **Spec:** `docs/plans/hypergeometric-fetch-closure.md` (rounds 1-14, checklist, anchors table).
- **Gamble rung:** `src/common/strategy/planner.py` — `_best_gamble_line` (+ trace), `_gamble_ko_classes`
  (4-tuples), `_gamble_det_baseline`, `_gamble_burst_copies`; `plan_turn` clears the trace.
- **Odds:** `src/common/deck_odds.py` (`draw_hit_probability`, `p_contains`); tracker
  `src/common/deck_tracker.py`; opponent side `src/common/opponent_resources.py` (NOT in scope —
  ADR-0064 owns it with pessimism; user ruling: not worth it yet).
- **Telemetry:** `src/common/telemetry.py` (sparse `gamble` key); `src/common/pilot.py`
  (`Decision.gamble`); shell dropdown `tools/train/blunder/shell.py` (`show()`).
- **Tags:** `src/common/card_functions.json` + `tools/meta_tracker/function_overrides.json`
  (curated entry point) + `tools/build_card_functions.py` (probe pipeline). Clauses:
  `src/common/card_effects.json`. Fetch filters: `doctrine_fetch._FETCH_FILTERS` (fold in WP3).
- **Corrections:** `data/corrections/*/corrections.jsonl` + `reviewed.json`; tagging shell
  `python -m tools.train.blunder …`; classification `/blunder-buster`.
- **Tests:** `tests/strategy/test_gamble.py` (REQ-GAMBLE-0001..5 + trace), `test_fetch_doctrine.py`,
  `test_blunder_20260705.py` / `20260709_energy_color.py` / `20260703_develop_wincon_base.py`
  (the recalibration pins).

## Related ADRs / memory

ADR-0029 (deck-content odds — the seed), ADR-0039 (gamble lines), ADR-0023/0024 (fetch comparator /
shuffle-refresh), ADR-0060 (refresh card-swing — WP6 re-audits it), ADR-0064 (opponent side stays
pessimistic; accel-tag scan integrity), ADR-0032 (effect compendium — WP3's home), ADR-0006 (tags
boolean-only), ADR-0034/0036/0046 (fold / re-align / proposal pipeline), ADR-0052 (one-oracle
pattern — WP7's shape), ADR-0007/0042/0053 (the parked value model — owns the synergy residue ONLY).
