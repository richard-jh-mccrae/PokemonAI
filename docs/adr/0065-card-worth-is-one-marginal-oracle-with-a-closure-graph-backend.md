# ADR-0065: Card worth is one marginal oracle with a closure-graph backend

**Vocabulary.** See [`0065-glossary.md`](0065-glossary.md) for the agreed terms: **Worth**
(`card_worth.py`), **Gates** (`gate_library.py`), **Odds** (`deck_odds.py`), **Closure**
(`fetch_closure.py`). Every equation below is `value = Worth × Odds`.

**Status.** Accepted (grilled 2026-07-17 across Rounds 7–9 of
[`docs/plans/hypergeometric-fetch-closure.md`](../plans/hypergeometric-fetch-closure.md)) and
**BUILT 2026-07-18 — the module seam + two consumers converged, suite-green.** The gamble keep-floor
(WP6) and the **refresh SHED** consume the oracle; the **fetch grab/pitch** shadow was investigated
and found ALREADY subsumed (its tuned discard ladder prices roles + redundancy; its residual gaps are
the gate library's, not keep_cost's — see §Build status). Only the plan-tier credit remains STAGED. Amends ADR-0060 (its flat SHED + the
`hold-wincon` / `hold-line-piece` / `hold-wincon-with-base` / `hold-irreplaceable-tool` guard
jurisdiction is now folded into the graded `Σ keep_cost`); builds on ADR-0023 (the shared fetch
comparator) and ADR-0032 (Effect-Clause tier).

## Build status

**Landed and suite-green (the "one module home" — Round 10 §2):**
- **`src/common/fetch_closure.py`** — the tutor / recycle / search GRAPH and its clause predicates,
  lifted out of the Pilot into pure, Pilot-independent functions over the card REPRESENTATION only
  (`card_effects.json` FETCH clauses + `CardStat`, never a text parse — the Round-11 ruling):
  `fetch_target_matches(clause, stat)`, `reaccess_outs(cid, counts, stat_of, clauses_of)`,
  `fetch_reaches_pokemon(target, cid, counts, stat_of, clauses_of)`. The Pilot's
  `_fetch_target_matches` (was on `FetchMixin`), `_card_reaccess_outs` / `_fetch_reaches_pokemon`
  (on `PlannerMixin`) now DELEGATE — one implementation, read by the fetch doctrine, the gamble
  gain side, and the keep-cost by construction. Behaviour-preserving; pinned by
  `tests/strategy/test_fetch_closure.py` (parity against the ground-truth Pilot methods over the
  real decks).
- **`src/common/card_worth.py`** — the WORTH backend: the ONE tuned currency (`ROLE_TIER` /
  `ENERGY_TIER` / `ACE_SPEC_TIER`), the `role_value(roles, is_ace_spec, is_typed_basic_energy)`
  primitive (the Pilot's `_role_value` delegates; later extended with `tags=` — the TAG_TIER bullet
  below), and the `keep_cost(role_value, reaccess_odds)` primitive (later extended with the
  `deadline_odds` gate factor — the gate-library bullet below). The Pilot supplies card facts; the
  module owns the numbers.
- **The gamble keep-floor consumes it (WP6):** `planner._keep_cost = role_value × (1 − re-access
  odds)`, the closure pointed backwards, replacing the binary protected-hand veto.
- **The refresh SHED consumes it (2026-07-18):** `pilot._refresh_swing_tactical`'s flat
  `_REFRESH_SHED × cards-lost` term is now `pilot._refresh_shed_keepcost = Σ keep_cost` over the
  actual hand — a wincon/engine is expensive to shuffle, a dead hand nearly free, the closure
  supplying the redundancy discount. The four hand-QUALITY guards (`hold-wincon` / `hold-line-piece`
  / `hold-wincon-with-base` / `hold-irreplaceable-tool`) that propped up the flat term RETIRE into it
  (the currency-zone rule). All six ADR-0060 corrections (ml f111, ms f60/f94/f45/f100/f64) hold
  under the graded term; the corpus KEEP pins hold; one corpus TARGET (`85164605-64`) flipped to a
  pin (the costly-hand Lillie's drops below tier-0, freeing a lethal). `hold-successor-when-doomed`
  survives — its `active_doomed` premise is a DEADLINE the fixed re-access window doesn't yet model
  (the gate library, still staged), not a pure keep-value the closure prices.
- **The coverage lint (Round 9 §5):** `tests/strategy/test_role_coverage.py` — no card silently
  priced at zero from a typo (every declared role is known vocabulary; every ROLES key is a real
  deck card; every worth-roled card prices positive).
- **The TAG_TIER worth coverage (2026-07-19, the combat-tempo investigation — its plan doc is
  retired, see git history):** `role_value` = the MAX
  claim across roles, behavioural tags (`TAG_TIER`: `discard_eot` 30 / `clutch_heal` 20 / `gust` 10
  / `recycle` 10 — the discard ladder's keep bands mirrored into the one currency), and the
  ACE-SPEC / energy fallbacks. Closes the gap where the DISCARD ladder priced Ignition / Wally's
  but the worth oracle saw 0, so the graded refresh shed shuffled them away for free. Two corpus
  targets flipped and promoted (`82749168-65`, `83969481-55`); ADR-0060's parked "hand QUALITY"
  seam, now concretely covered for the tagged classes.
- **The duplicate-copy reconciliation + the fetcher gate (2026-07-19).** The two keep-value
  consumers priced duplicate held copies differently by container accident: the gamble summed per
  copy at +1 out each; the refresh SHED iterated the deduped `Board.hand_ids` frozenset — one
  charge per distinct card, duplicates free, and EVERY copy of the played refresh excluded. Both
  now read ONE summation, `planner._hand_keep`: duplicates price MARGINALLY (each of the k held
  copies charges with all k shuffled siblings as outs — the first sets-not-sums step, spec
  §Round 7), the played refresh is excluded once, and duplicate-free hands price identically by
  construction. The reconciliation exposed a latent mispricing the dedup accident had masked
  (pin `83457493-31`: two dead Poffins + a dead Night Stretcher held at worth ~10 each — the second
  Poffin rode free), fixed the honest way: the **fetcher gate**, the gate library's
  searcher/recycler leg (`gate_library.fetch_deploy_odds` via `planner._deploy_odds`), collapses a
  fetch TRAINER whose every target is provably dead — the SAME sound predicates the play-side
  rungs trust (`dont-search-an-empty-deck`'s deck whiff-set ⊆ `deck_empty_ids`;
  `dont-recycle-the-dead`'s `recycle_dead_only`), Trainer-only so a recycle-tagged BODY (Kyogre)
  stays priced. The pin's margin went −2.7 (broken) / ≈+2 (the lucky accident) → **+19.1**
  (honest: three dead cards shed free). Suite + corpus green (3092).
- **The pre-anchor cost-side prize split (2026-07-19, behavioural-review Finding 2).** Pre-anchor,
  keep-cost re-access counted possibly-prized unseen outs at full strength against a prize-free
  pool, while the gamble's GAIN side was exactly prize-weighted — re-access overestimated, keep
  under-charged, a pre-anchor pro-gamble bias from both directions at once. `_prize_split_hit`
  gains a ``certain`` term (the shuffled hand copies, never prize-assignable, join every branch's
  window draw) and `_keep_cost` / `_hand_keep` route the re-access through it when
  ``prizes_hidden > 0`` — the ONE split primitive now prices both sides; the anchored path is
  byte-identical, the gain side (``certain=0``) unchanged. Alongside (review Finding 3):
  `fetch_closure.reaccess_outs`'s blanket "errs by under-counting" claim softened to name its three
  accepted over-counting channels (type-locked Pokémon fetch fail-open, uncharged tutor costs,
  slot-less Supporter tutors). Suite + corpus green (3094).
- **The refresh-chain stage + the first-reveal ruling (2026-07-19, the spec-checklist grill).** The
  spec's two unbuilt checklist items were grilled at source. (a) **Hand-expansion chains — BUILT**,
  narrowed to the measured live residue: a drawn Unfair Stamp (gated on the new
  `Board.my_pokemon_koed_last_turn`, the opponent-turn-start prize mirror in
  `opponent_resources`) or a drawn Supporter refresh (post-Item only) re-opens a full window at the
  same outs — `planner._gamble_chain_refreshes` + a disjoint additive branch, anchored-only,
  `chain_refresh` on the trace; Pokégear-class chains are provably slot-dead and the opponent side
  stays ADR-0064's. (b) **First-reveal information credit — CLOSED refuted-for-now** (every shipped
  fetch anchors; fetch-early is correction-refuted `85163634-17`; sequencing owned by
  `dig-before-commit`), revival gate recorded on the spec checklist. Suite + corpus green (3096).
- **The pressure + quota gates — the gate library COMPLETE (2026-07-19, TDD).** Stage 3, the
  **pressure gate** (`gate_library.closing_gate_reaccess` via `planner._gate_closing`): under a
  doomed Active, the held cards that ANSWER the doom — the successor wincon with its Line
  pre-evolution in play, and the `clutch_heal` / `switch` tags — charge FULL role worth (the
  Round-8 §3 closing-edge spike: a probabilistic redraw is not bankable against the doom deadline).
  This retired **`hold-successor-when-doomed` (−35), the LAST flat refresh guard**: at its anchor
  (ep83037962 f49) Harlequin prices **−12.0 through the graded equation alone** (was −23.9 with
  the rung; +11.1 with neither), the substance pin and the synthetic pair re-audited green. Stage
  4, the **quota gate** (`gate_library.quota_window` in `_hand_keep`): the k-th held copy of a
  once-per-turn card (Energy attach / Supporter slot, rules.md §3) has deadline k−1 turns (+1 on a
  spent quota — `energy_attached` / `supporter_played` / the played refresh being a Supporter), so
  each rank's re-access window widens by its turns of natural draws — "the 3rd hand Energy is
  near-free" is now derived. The ADR-0060 keep pins and the TAG_TIER pins hold under both. Suite +
  corpus green (3100).
- **The discard SHADOW emitter (2026-07-19)** — the fourth shadow's evidence bridge, the first
  equation shipped under the shadow-equations ruling: `pilot._discard_shadow` computes the oracle's
  v1 keep-cost (Worth × Gates × deterministic pitch re-access, `fuel` zone sign) at every real
  discard pick and emits the full working + the agreement bit beside the ladder's decision —
  `Decision.discard_shadow` → the `@T` key → the blunder-shell dropdown — deciding NOTHING. First
  corpus sweep: 3 agree / 9 disagree over the recorded discard decisions; the rows localise the
  migration's prerequisites (line-MEMBER worth derivation; set semantics; a worth-0 tie-break).
  The swap stays gated per the ruling (seam D). Suite + corpus green (3104).
- **Seam-D grill RULED + steps 1-2 built (2026-07-19).** Ruling (with the user): *gates real,
  equation shadow, swap gated-last* — a GATE is a Worth factor (built real, fires live at the
  gamble/refresh sites, corpus-gated), while the discard DECISION SITE rides as a shadow until its
  agreement earns the swap. Built: the **pitch-preference term** (`_discard_shadow` gained a
  deadness/zone `pitch` count — dead-opener/redundant-tutor/stranded/fodder/fuel/spent-burst —
  ranking the zero-keep ties keep-cost can't), the **need-met gate** (`gate_library.need_met_odds`:
  a wincon-tutor whose wincon is in hand collapses to 0, live at gamble/refresh), and the shadow's
  **worth tie-break** (lower-worth duplicate sheds first — sets-not-sums). Measured vs the HUMAN
  corpus, the equation went **8/12 → 11/12, now BEATING the tuned ladder's 9/12**; the only miss is
  `86091435-68` (the deploy-now spike). The swap (`keep_cost_gated` decides) is the next gated
  decision. Suite + corpus green (3110).
- **The last miss re-reviewed — the equation's pick ruled CORRECT (2026-07-19).** On the shadow's
  working the user re-reviewed `86091435-68` and refuted the recorded label's 2nd slot (the
  Crushing Hammer should be KEPT for the opponent's Active) — the equation's pick endorsed over the
  human label. Corpus: the strict target → refuted/excluded (reviewed.json), its surviving
  substance relaxed into `test_deploy_now_drakloak_is_not_pitched` (strict-xfail: the sole
  evolve-the-Active Drakloak must never be pitched). Scoreboard: the equation matches the human
  **11/11** on surviving labels vs the ladder's **9/11**, and is user-endorsed on the refuted 12th
  — it now strictly dominates the ladder on every recorded discard decision. The swap awaits the
  user's go.
- **Seam-D CONVERGED — the deploy-now spike + the LIVE SWAP (2026-07-19).** The fourth valuation
  shadow is now the DECIDER. (a) **Deploy-now spike:** `Board.deploy_now_ids` (a hand evolution with
  an eligible in-play base this turn) wired as a `_gate_closing` closing edge — keep spikes to full
  worth, flipping `86091435-68` while `83686860-18` still pitches correctly (the covered-vs-open pair).
  (b) **Engine-supporter gate** (Finding 2's 5th premise) closed as a discard-context worth floor.
  (c) **The swap:** `Pilot.discard_keep_value` (PROFILE armed ON, `develop_rollout` precedent) — the
  equation's ranking (`_discard_equation_rows`, shared with the shadow) decides the forced discard in
  place of the `_DISCARD` ladder; OFF is byte-identical. Acceptance: **9/9 live discard corpus** (the
  ladder 9/11); the relaxed deploy-now target promoted to a pin; all discard pins green; full suite
  3114. The four-shadow disagreement (Round 7) is now fully retired — grab/pitch, refresh swing,
  gamble keep-floor, AND discard all read the one currency. Open: the duplicate-pair set semantics,
  and folding the shadowed `_DISCARD` rungs once the in-ladder A/B clears.
- **Line-member worth derivation (2026-07-19, the shadow's first prerequisite closed).** The shadow
  sweep found an undeclared middle Line stage (the f68 Drakloak on Dreepy→Drakloak→Dragapult ex)
  pricing **0** — `_role_value` saw only the declared base. `planner._role_value` now derives
  `win_condition_base` worth for every `_line_preevo_set` member (Round 9 'derive first'), so the
  Drakloak prices 20. WORTH-ONLY: the Line-membership fact enters the value currency (keep-cost
  sites + the shadow) but NOT `_roles_of` / `c.roles` — injecting it there would flip the discard
  ladder's `_BASE_ROLES` exemptions and REGRESS the covered-Drakloak pin `83686860-18`, so that
  discrimination stays the gated seam-D migration. The gamble keep-floor / refresh SHED re-audit is
  a no-op (no pin moved). Suite + corpus green (3105).
- **Keep-value v2 (Needs) WP-N1–N3 built (2026-07-19/20; `keep-value-needs-assignment-grill-spec.md`).**
  The successor to the gate stack the user flagged as brittle ("more and more gates that begin to
  undermine each other"): needs reified as deadline-tagged SLOTS (`common/needs.py`, the fifth
  glossary term), a card's keep-value its MARGINAL slot coverage under EXACT bitmask-DP assignment —
  so multi-copies, energy-attached, doom, quotas, fuel and deploy-now are slot PROPERTIES resolved
  GLOBALLY in one assignment, not pairwise-composed gates. WP-N1 the module + the two soundness nets
  (the COVERAGE LINT: every worth source names ≥1 slot; the DISSOLUTION LEDGER: every v1 gate names
  its re-deriving slot); WP-N2 the assignment engine (`assignment_value` / `keep_v2` / `set_keep_v2`
  / `cheapest_removal`); WP-N3 the Pilot resolver (`pilot._needs_v2`: the live board → slots /
  eligibility / resupply) + `keep_v2` / `eq2_pick` / `agree_v2` columns on `discard_shadow`,
  shadow-only. The sweep's four disagreements each adjudicated to a resolver gap (the half-tier
  SUCCESSION slot for a wincon line — "copy 2's marginal = its next-best slot"; line slots
  Pokémon/ACE-SPEC only; the draw-engine band off the eligible suppliers; a residual-worth
  tiebreak), never the design; post-adjudication **agree_v2 12/12** with the live v1 decider.
- **WP-N4 — the discard decider swap (2026-07-20, dev-window ruling).** The per-family swap for the
  cleared discard family: `Pilot.needs_keep_value` (PROFILE armed ON, the `develop_rollout`/seam-D
  precedent) makes the v2 needs-assignment (`_needs_v2` → `eq2_pick`, `needs.cheapest_removal` over
  the resolved slots) the forced-discard DECIDER, superseding v1's per-card gate composition;
  precedence `needs_keep_value` > `discard_keep_value` > the ladder, each a kill-switch, OFF falls
  through. Corpus-safe BY CONSTRUCTION (agree_v2 12/12 → every human `correct` v1 satisfied, v2
  satisfies), and the **duplicate-wincon pair flips WITHOUT a new gate** — the naivety v1 could not
  fix (both copies read keep-0) is structurally gone: each copy's solo marginal is the succession
  slot, the pair's set marginal is full+half. **Gate dissolution, precisely:** the discard DECISION
  no longer runs v1's brittle pairwise gate composition — it flows through the global assignment.
  The gate code is NOT deleted: `_deploy_odds` (evolution + fetcher + need-met), the fuel/burst
  flags and the quota window are CONSUMED by the resolver (a dead evolution's line slot is valued
  ×0 — the ledger's "dead evolution = no line slot," derived not asserted) AND still price the
  gamble keep-floor + refresh SHED, which have not swapped. **The hedge is RETAINED** (v2 never
  prices below v1's post-gate keep): the resolver is still v0-scope — resupply 0.0 (errs toward
  keep) and opponent DENY slots deferred — so trusting v2 raw is premature; the hedge retires with
  the resolver's completion. Staged next (WP-N4b): the refresh-SHED shadow join (a MAGNITUDE shadow,
  distinct from the discard's pick-agreement — the discard corpus is this week's bench per the
  user). Suite + corpus green (3055); the corpus discard pins hold under v2 as the live decider.
- **WP-N4b — the refresh-SHED MAGNITUDE shadow, and its verdict: the refresh family is NOT cleared
  (2026-07-20).** The refresh SHED is a scalar (`_refresh_shed_keepcost` = Σ keep_cost), not a pick,
  so its shadow is a MAGNITUDE comparison, not the discard's pick-agreement: `pilot._refresh_shed_shadow`
  emits v1's Σ keep_cost beside v2's whole-hand assignment marginal (`needs.set_keep_v2` over the
  held hand, resolved through the shared `_resolve_needs` core factored out of `_needs_v2`), and —
  since the shed is the ONLY term that changes — the two refresh SWINGS
  (`swing_v2 = swing_v1 + (v1_shed − v2_shed)`) and the decision-relevant SIGN-agreement bit (would
  swapping the shed flip play/don't-play?). Rides `Decision.refresh_shadow` → the `@T` key, deciding
  NOTHING. **The sweep's verdict (83 refresh decisions): 18 sign-flips, and v2 UNDER-prices the shed
  in 46 (vs over-prices in 35), the UNSAFE direction — it would shuffle away hands v1 correctly
  keeps.** The cause is diagnostic, not a bug: v2's v0 resolver is DISCARD-bench-scoped — its slots
  price a card's LINE / fund-attack / answer-doom / fuel NEED, but not a card kept for GENERAL worth
  (a spare engine/attacker/backup body with no open line slot, an energy on a powered Active). The
  discard family cleared 12/12 because the discard corpus lived within that scope; the refresh's
  whole-hand valuation exposes the gap. So the refresh site does NOT swap — the shadow did its job,
  and its telemetry stages the prerequisite: general-worth slot coverage, which is the readiness
  leaf's board-value terms (`board-state-valuation-grill.md`) — i.e. WP-N5's fold, not a bolt-on
  gate. v1 stays the refresh/gamble keep-value spine meanwhile. Suite + corpus green (3055).
- **WP-N5 — the general-worth slot: the resolver enrichment WP-N4b demanded (2026-07-20).** The
  refresh sweep proved the v0 resolver blind to a card's LATENT worth (a spare engine/attacker with
  no open need slot priced ~0). The fix is the readiness leaf's own vocabulary applied to the HAND:
  a `general` slot kind (`needs.general_worth_slot`) — a held card's role tier × `_GENERAL_WORTH_W`
  (0.45, the leaf's `_READINESS_BENCH_DISCOUNT`: a hand card is ~one deploy away, like a benched
  body), emitted ONE per distinct card (so spare COPIES price marginally — sets-not-sums, the
  assignment de-duplicates) and BELOW every specific need (a need-filler assigns to its need first).
  PITCH-GATED: a row the pitch term flags dead-weight (spent_burst / fuel / dead_opener / stranded /
  redundant_tutor / fodder) has no latent worth — context-correct, since refresh rows carry no pitch
  flag so a SHUFFLED burst keeps its future-attach worth (the gate caught c4f5, where an ungated
  general slot RESURRECTED the spent Ignition v1 correctly zeroed — the 83454549-36 trap again).
  **Measured: refresh under-pricing (the UNSAFE direction — shuffling away a kept hand) more than
  HALVED, 46 → 19 of 83; sign-flips 18 → 13; the residual flipped to over-pricing (35 → 62, the SAFE
  direction), cleanly isolating the one remaining gap as the missing resupply/re-access discount.**
  The discard corpus held **12/12** under v2 as the live decider; the **leaf-lab bench is UNCHANGED
  (39/267 SOLE-top, 71% shared, avg-tie 3.0)** — the enrichment touched only the keep-value resolver,
  not the leaf, so no accidental coupling (the discipline check, run `tools/train/leaf_lab.py`). Suite
  green (3057).
- **WP-N5b — the readiness-leaf fold: BUILT behind a flag, MEASURED, verdict MIXED → armed OFF
  (2026-07-20).** Round 5's "readiness consumes the needs module" fold — the leaf's own deferred v2
  "actionable-resource term" (`board-state-valuation-grill.md` §v1→v2) IS the needs assignment. Two
  pieces built behind `Pilot.leaf_hand_value` (PROFILE armed OFF — flag-off is byte-identical, suite
  3057): (a) the HAND-VISIBILITY PLUMBING the grill named the v2 enabler — the sim end-obs is
  OPPONENT-perspective so my hand is hidden (verified empirically: `handCount` present, no `hand`
  key; `SearchState` exposes only the perspective-filtered `observation`, no full-state accessor),
  so `_simulate_line` now CAPTURES my hand from the last my-perspective step and INJECTS it into the
  end obs; (b) `pilot._hand_readiness` — the leaf's resource term = the held hand's slot coverage
  (`needs.set_keep_v2` via `_resolve_needs`, the SAME valuation the keep-value sites use — one
  vocabulary, not a rival), capped, added to `_readiness` in `_engine_leaf_value`. **Bench verdict
  (the discipline gate, `leaf_lab.py` + `gate0_ab.py`): MIXED, does not clear.** Full leaf-lab (267):
  SOLE-top 39→50–54 (15%→20%, the honest headline UP) and avg top-tie 3.0→2.2 (the 36→5 granularity
  gap TIGHTER) — but "correct at top at all" 190→148 (the term breaks ties ~15 toward correct, ~42
  AGAINST — real ranking errors), and the drop is NOT W-sensitive (0.2→0.5 all ~53–55% shared), so
  it is intrinsic, not miscalibration. Gate-0 (lucario ctx-0 subset, CAP 2500): SOLE-top flat, 1-ply
  at-top 75%→50%. The grill's "a big new positive term VOIDS every guard" warning, materialized: a
  raw hand-value term rewards HOARDING over deploying — the opposite of the develop rung's job. Kept
  armed OFF; the plumbing + the bench methodology stay as the enabler.
- **WP-N5c — the hand term narrowed to "live use" (specific needs only); STILL armed OFF, ceiling
  diagnosed (2026-07-20).** Dissecting the 51 regressed frames (`ep83661652`: every option reaches
  the SAME board 93, so the hand term is the only discriminator, and it hands the lines holding two
  extra cards 676/677 **+23** vs the correct line that PLAYED them **+2** — pure hoarding, driven by
  the GENERAL-worth slots). Fix: `_resolve_needs(..., include_general=False)` for the leaf only —
  keep-value keeps latent worth (deciding what to shed prices a spare), but the leaf's term is the
  grill's "held cards with a LIVE use" = the SPECIFIC needs, not latent worth. **Measured: recovered
  ~⅓ of the lost shared-top (leaf-lab 141→153 of 267) while keeping the SOLE-top gain (50→48, still
  18% vs 15% baseline).** But shared-top stays below baseline (153 vs 190): the specific-need slots
  THEMSELVES still credit fumbles — a `deploy_now` evolution HELD at end-of-turn is a card I didn't
  evolve. **The ceiling, now precise:** keep-value credits "held cards with a use," but the LEAF
  wants the COMPLEMENT — resources I COULDN'T deploy this turn (future value), not ones I chose not
  to. At a static end-of-turn board those are indistinguishable without a per-card "was this
  deployable" counterfactual. So the needs valuation (built for keep decisions) does not cleanly map
  to the leaf's end-of-turn board value; the fold is PARKED armed-OFF pending either that complement
  term or a pure small tie-breaker (break the 36→5 exact-value ties without overturning real gaps).
  N5c is committed as the better term (halves the regression, matches the grill's spec); the arming
  bar (SOLE-top AND shared-top both up, like the v1 leaf) is not met.
- **WP-N5d + the ε tie-breaker — the hand fold's CEILING reached; CLOSED as measured-and-parked
  (2026-07-20).** Both staged shapes built and measured. (a) **N5d, the deployability
  counterfactual** (`_held_undeployable` + the `heldCtx` sim snapshot — attach/Supporter quotas,
  bodies with fresh `appearThisTurn`, bench fullness, captured at the last my-perspective step):
  the leaf credits ONLY held cards that COULD NOT have been deployed this turn (an Energy past the
  attach quota, a Supporter past the slot, an evolution with no eligible base, a Basic on a full
  bench; Items always deployable → never credited); deployable held cards still participate in the
  assignment (covering slots, shrinking undeployable siblings' marginals) but earn nothing. On the
  diagnostic frame the hoarding reward collapsed +23 → +3. (b) **The ε tie-break sizing**
  (`_HAND_TIEBREAK_W/_CAP`: term < the ~0.025 smallest genuine leaf gap, so it can ONLY split
  exact-value ties). **Measured (leaf-lab 267): N5d-full 45/163/2.51, N5d-ε 46/165/2.50 — ε ≈ full,
  CONFIRMING N5b's W-insensitivity: tie-splits are the entire mechanism, magnitude irrelevant. The
  decisive metric — E[correct picks] = Σ 1/tie-size over at-top frames (what the argmax rung with
  order-broken ties actually delivers): baseline 83.5/267 vs N5d-ε 84.5/267 — a WASH** (+7 SOLE-top
  exactly offset by mis-split ties). Root cause, now fully explained: the residual tied boards
  differ by the leaf's OTHER named blindnesses (who's-Active, tools — the grill's own collision
  dissection); when the true discriminator is positional, ANY hand-based tie-split is noise. **A
  hand term structurally cannot clear the bar — the next SOLE-top gains belong to who's-Active and
  tool terms in the leaf itself (leaf-native work, not the needs fold).** N5d+ε committed as the
  best-behaved shape; `leaf_hand_value` stays armed OFF; the fold re-opens only after those
  blindnesses are read. Suite green (3057).

- **WP-N6 — the refresh slot-RESUPPLY discount (2026-07-20): built + measured; refresh swap still
  NOT cleared.** The WP-N5 residual (v2 over-pricing the refresh SHED because uncovered/covered
  slots never saw the closure's re-access odds) fixed at its site: `pilot._refresh_slot_resupply`
  fills the assignment's resupply vector for the REFRESH window — per slot, P(re-supply within the
  refresh's own draw window), outs = the slot's supplier classes pointed backwards via the NEW
  `fetch_closure.class_reaccess_outs` (the SET walk: own copies of every member class + each
  reaching tutor counted ONCE; `reaccess_outs` now delegates to it), held eligible copies as
  certain outs over the shuffle-grown pool, prize-split-weighted pre-anchor — v1's `_keep_cost`
  model per SLOT instead of per copy. Closing-edge kinds (`deploy_now`/`answer_doom`) and
  pitch-side fuel stay 0.0; `fund_attack` windows widen by the quota deadline (`quota_window`
  re-derived). **In-build adjudication: `general` slots stay 0.0** — `_GENERAL_WORTH_W` (0.45) was
  measured at resupply 0.0 and empirically already carries the site's re-access discount; stacking
  ×(1−r) flipped the sweep unsafe (under-pricing 19→62). **Measured (83 frames): sign-flips 13→8
  (every large baseline over-pricing flip fixed, worst −46; 3 new tips all |swing_v2| ≤ 2),
  mean |v2−v1| 9.7→6.7, bias +5.8→−2.2 (centered); discard 12/12 held (that site keeps resupply
  0.0 — no redraw window).** The swap bar (flips ≈ 0) is NOT met and the residuals are v2 SCOPE
  gaps shared with the discard decider — the flat `answer_doom` TAG-tier value (over-prices a
  worth-0 switch at 20, under-prices the doomed successor vs v1's full-worth closing spike) and
  the saturating engine band vs v1's per-supporter sum — so re-pricing them is its own
  adjudicated piece. The hedge (v2 floors at v1's post-gate keep) stays.

- **WP-N7 — opponent DENY slots (2026-07-20, thread 2): built + measured; the hedge stays.** The
  Round-3 ruled opponent read wired into `_resolve_needs` (unflagged, the WP-N5 enrichment
  precedent): one deny slot per opponent in-play body a strip bites, valued by the SHIPPED
  ADR-0062 denial oracle (consumed intact — Active ×1.0 with the `active_can_ko` drop, bench
  ×0.25) and graded by `needs.deny_slot` over the visible turns-to-ready
  (`pilot._opp_turns_to_ready` — energy deficit at the 1-attach quota vs forward hops, max of
  legs, fail-closed on unknowns). `needs.SUPPLIES` gained `"energy_denial"` (the Hammers);
  eligibility derives from SUPPLIES itself so vocabulary and routing cannot drift. A deadline-0
  deny takes resupply 0.0 (the closing edge, applied in `_refresh_slot_resupply`). **Measured:
  discard 12/12 byte-identical (the live decider unmoved); the Hammer/gust classes get their
  first v2 pricing but the hedge-floor firing count is UNCHANGED (13/68 rows) — deny retires
  zero firings, so the hedge stays.** With WP-N6 integrated the refresh shadow reads flips=13 /
  under=38 / over=40: the oracle's DAMAGE-denominated values (~140) sit above the worth tiers
  (~8–30), which folds the deny scale into the same open CURRENCY adjudication as the flat
  `answer_doom` tier and the engine band — the named prerequisite for the refresh swap and
  hedge retirement.

- **Leaf-native who's-Active + tool terms (2026-07-20, thread 3 — the board-state grill's build,
  logged there in full):** the promotion-ease bench-position lift shipped in the readiness leaf
  (`planner._bench_position_w` / `_promotion_ease`; retreat-tools route to position, HP-tools
  already reach survival via engine `hpBonus`), a zero-regression Pareto step — leaf-lab SOLE-top
  39→40/267, E[correct picks] 83.8→84.7, shared-top flat 190, Gate-0 subset up. The who's-Active
  mobility micro-credit is HAND-ARMED (rides `leaf_hand_value`, still OFF). **The N5d hand-fold
  re-measure with the new terms: 52 SOLE / 164 shared — still does NOT clear (shared-top down);
  the fold stays parked.** The step-1 dissection capped the ceiling: 77/151 residual leaf ties
  are pure transpositions no board term can split.

- **WP-N8 — the slot-CURRENCY adjudication (2026-07-20): grilled with the user, built, all inside
  the assignment.** Three seams where a slot value spoke the wrong unit, ruled frame-by-frame and
  folded into the value derivations (no new gates/rungs/flags; discard held 12/12 byte-identical,
  leaf-lab unmoved 40/190, refresh sign-flips 13→11):
  * **Answer-doom is a plan, not a flat tier.** The switch/heal answer slot is valued at the doomed
    body's OWN preserved worth (`_role_value(active)`), and the successor rides a new URGENT
    succession slot (`needs.line_slots(succession_urgent=…)` — full tier, deadline 0 when the Active
    is doomed with its base in play; the old flat-20 successor spike re-derived as the line's own
    worth). The closing edge in `_refresh_slot_resupply` generalized to any `line`/`deny` slot at
    deadline ≤ 0.
  * **A duplicate saturating-need Supporter is worth 0** (a deletion): a cid eligible for the
    draw-engine need gets no general-worth slot, so the spare copy prices 0 (the WP-N5 ~9 latent
    credit for a spare, refuted).
  * **The deny slot is the disruption card-tier** (`TAG_TIER["gust"]` ≈ 10, graded by
    turns-to-ready), not the ADR-0062 damage swing (~140) — the oracle becomes a GATE only; the
    damage magnitude stays on the play-side gust rungs. Scoped to the deny slot (a role-less Hammer
    keeps global worth 0), so the leaf is untouched.
  Two items the grill surfaced belong to the TURN/MATCH PLANNER, not keep-value, and are recorded
  unbuilt: threshold-race snipe targeting and gust-line tempo evaluation.

- **WP-N9 — the refresh SHED SWAPS, and WP-N4b's verdict is discharged (2026-08-01, ADR-0101,
  Issue #261 item 2b).** `_refresh_shed_keepcost` IS `needs.set_keep_v2` over the whole shuffled hand;
  the `Σ keep_cost` path at that site is deleted and `_refresh_shed_shadow` / `Decision.refresh_shadow`
  / the `refresh_shadow` telemetry key / `needs_sweep.py`'s REFRESH half go with it. **The arming bar
  WP-N4b set itself — sign-flips ≈ 0 — was never met** (18 → 13 → 11 → **16** at the swap, over a
  corpus grown 83 → 96 refresh decisions): ADR-0092 retired that bar, not the measurement. A POC track
  swaps and routes every moved frame to a wave ruling against a recorded baseline. Measured at the
  swap: Discrimination Gate PASS / 0 moved, Decision Gate 2 FIX + 3 REGRESSION (all five
  shadow-predicted sign-flips), `discard agree_v2` 12/12 UNMOVED — the shared resolver did not drift.
  The three regressions are one mechanism, named rather than tuned: a swing inside ±3 of zero being
  read as play/don't-play by `_finish_turn_last`'s `score > 0` promotion, which T4's differencing
  replaces. `_hand_keep` stays as the gamble keep-floor's own summation — this ADR's "one summation for
  both sites" claim is retired, deliberately: the two sites ask different questions (one card's floor
  vs the hand's joint price) and shared an answer.

- **WP-N10 — the pitch term reaches the assignment that decides (2026-08-02, ADR-0106,
  Issue #294).** WP-N3's own build note above says the residual-worth tiebreak makes *"the
  deploy-dead Cinderace shed before a live spare"*; it never did. `deploy` sees dead evolutions,
  dead fetchers and need-met tutors, and none of the five expired-role facts `_apply_pitch_terms`
  derives — so the dead-opener case fell to the menu index and the spent burst (`83454549-36`) was
  KEPT, because residual worth reads the catalog tier a corpse still carries (Ignition 30 vs a live
  spare's 0). `needs.cheapest_removal`'s key is now
  `(removal_score, −Σ deadness, Σ residual_worth, indices)`. Deadness RANKS, it does not PRICE: for
  a dead card `P(met | keep) == P(met | pitch) == 0`, and this ADR's own `keep_cost = Worth × Odds ×
  Gates` is a product of clamped non-negative factors — so the "a dead card's keep is negative"
  reading would have to invent its magnitude, which is the rung-fitting ADR-0092 deletes. The row now
  carries `deadness` (a categorical bit over the five expired-role facts, which RANKS) beside the
  unchanged `pitch` COUNT (`+ fuel`, which gates latent worth and the junk band); ranking on `pitch`
  double-prices fuel and shed an attack's only funder on `83966336|0|decision|27`. Both legs are
  spelled once, in `Pilot._removal_ranking_legs`, because the discard decider and the fetch
  doctrine's shed predictor must rank identically. Both gates byte-identical to the pre-change tree;
  zero corpus frames moved.

**Investigated and found already-subsumed — the fetch grab/pitch shadow (2026-07-18).** Unlike the
gamble's binary veto and the refresh's flat SHED, the discard/pitch valuation is a mature,
correction-tuned 12-rung ladder (`doctrine_fetch.py` `_DISCARD` rungs) that ALREADY prices roles
(`keep-key −30` wincon/ACE-SPEC/burst, `keep-line-base −15`, `keep-engine −8`, …) AND redundancy
(`card_is_hand_duplicate` / `card_is_redundant`; the grab side's `dont-grab-a-card-already-in-hand`).
Measuring the seven corpus targets against the shipped agent: **five were malformed fixtures** (a
single-index `correct` for a `minCount=2` forced discard) that the ladder ALREADY satisfies
(`correct ⊆ chosen` — the flagged card is discarded); they are reclassified as subset PINS. The two
genuine residual gaps — `86091435-68` (don't pitch a Drakloak that can *evolve the active this turn*)
and `85059103-9` (prefer the Petrel tutor-chain over a redundant draw Supporter; the duplicate is
already avoided) — are **DEADLINE / fetch-priority** nuances, NOT keep-value: a flat `keep_cost` floor
on Drakloak would regress `83686860-18` (where pitching a Drakloak IS correct, a benched copy exists)
to fix `86091435-68`. That distinction is the gate library's jurisdiction (below), not the oracle's.
Converging the ladder onto `keep_cost` would re-baseline ~8 tuned pins for zero measured corpus
benefit — the anti-speculation / currency-zone discipline says don't. The shadow is effectively
already converged; its residue rides with the gate library.

**Staged (designed here, NOT built — each a corpus-gated behavioural flip):**
- **The gate library — Stage 1 BUILT 2026-07-18 (evolution gate).** `keep_cost` gains its deadline
  factor: `keep_cost = role_value × deploy_odds × (1 − reaccess)` — the `[P(met | keep) − P(met |
  shuffle)]` form with `deploy_odds` = P(the card's role is realisable by its deadline).
  `common/gate_library.py` owns the odds; `planner._deploy_odds` resolves base presence (the evolution
  gate: a bare base by `evolvesFrom` name in play / hand / the deck counts). An undeployable evolution
  (base gone from every zone) collapses to `deploy_odds = 0` → shed freely; everything else stays 1.0.
  **Amended 2026-08-02 by [ADR-0104](0104-a-hand-card-that-can-never-be-played-covers-no-slot.md)
  (Issue #288):** the parenthesis above is no longer how the evolution gate resolves. That one-hop
  comparison is superseded by `common.playability`'s backward CHAIN walk with the Rare Candy escape,
  and `gate_library.deploy_odds` now takes the resolved `playable` boolean rather than three zone
  booleans. The equation, the factor's meaning and its fail-open direction are unchanged — only where
  the answer comes from, and it moved because `pilot._resolve_needs`' new eligibility gate asks the
  same question and two answers would have disagreed about the same card.
  Wired on the two converged keep-value sites (gamble keep-floor, refresh SHED). This restores the
  retired `hold-wincon-dont-shuffle` `wincon_in_hand_undeployable` stand-down, gradedly, in the one
  equation — **as a PARAMETER, not a new rung** (the discipline the whole ADR protects). It is a
  correctness/robustness change: LATENT on the current corpus + pins (pre-anchor the base sits in the
  unseen deck, so nothing is discounted — it bites only a genuinely dead card), unit- and
  synthetic-integration-tested (`test_gate_library.py`, `test_undeployable_wincon_is_cheap_to_shuffle_
  but_a_deployable_one_is_not`), zero regressions.
  The scope/staging plan doc is retired — every stage it scoped is now BUILT: the fetcher gate
  (2026-07-19, the reconciliation bullet above), the **pressure gate** and the **quota gate**
  (2026-07-19, the bullet below). The one remaining gate-adjacent piece — the discard-side
  deploy-now spike (`86091435-68`), which needs a principled discard convergence first, NOT a flat
  rung — is owned by `docs/plans/seam-discard-convergence.md`.
- ~~The held-card-risk tier-2 seam (Round 8 §5)~~ **BUILT 2026-07-19**
  (`dont-fetch-before-the-deadline` + `dont-shuffle-away-the-deferred-fetch`,
  `tests/strategy/test_held_card_risk.py`;
  corpus target `85163634-17` promoted to a pin) — and **the skill loop** (deck-genie Role Sheet /
  deck-align fold — Round 9 §4), still staged. The oracle is the backend; the skill loop is how
  decks feed it.

## Context

Round 7 (user grill, source-checked): "what a card is worth" is ONE marginal quantity, and the repo
carried FOUR disjoint shadows of it that disagreed by construction — the fetch grab/pitch comparator,
the refresh card-swing (ADR-0060), the gamble keep-floor, and the develop-leaf plan credit. Each had
its own private valuation; a Mega Lucario ex was worth one thing to the fetch doctrine and another to
the refresh scorer. The codebase already proved the one-oracle pattern locally (ADR-0023's shared
fetch comparator, ADR-0052's KO oracle); worth had simply never been consolidated.

Rounds 8–9 produced the closed form. Two results made it BUILDABLE without a taste model:

1. **Keep-cost is the closure pointed backwards.** The cost of shuffling a card away is
   `role value × (1 − P(re-access it by its deadline))` — the SAME window-hypergeometric-over-closure
   primitive the gamble uses for its GAIN side, run in reverse. Redundancy and proximity both live
   inside the one closure query; proximity is the deadline PARAMETER of the re-access probability, not
   a multiplier (the live-now ×1.0 / next-turn ×0.7 table was refuted before it was built).
2. **The horizon discipline guard.** The oracle prices ONLY the positional band. Match-deciding cards
   are the hard rungs' jurisdiction (lethal solver / loss rung / win rung at KO_SCORE scale, which
   outrank leaf math by construction); worth-to-the-match enters through role TIER alone — bounded,
   already encoded. No match-importance multiplier, no blanket γ. This is the structural guard
   against a +76-class runaway (ADR-0060's first cut) recurring in the new currency: enumerate the
   computable risks (stripped, gate-closes), never a fudge factor.

## Decision

**One module cluster is the value BACKEND; the doctrines stay the DECIDERS.** `fetch_closure.py` owns
the graph, `card_worth.py` owns the currency + primitives, `deck_odds.py` keeps the window/prize-split
math. `doctrine_fetch` / `doctrine_shuffle_refresh` / the gamble rung keep owning WHEN-to-decide
(rungs, gates, telemetry) and become CONSUMERS of the shared backend. The four-shadow disagreement
dies by construction — not because a doctrine was deprecated, but because they all read the same
`role_value` and the same closure.

**Base value = one general tier table × mostly-derived roles** (Round 9). Roles derive first
(`_roles_of`: accel_source from the attack representation; the deck confirms/overrides), deck-genie
declares only the sparse identity residue — never invents numbers. The energy / ACE-SPEC fallbacks
cover the un-Roled mid cards. The currency-zone rule (ADR-0060's +76 lesson) governs every future
convergence: a graded term REPLACES its guard family and re-audits it, never bolts on beside it.

### Consequences

- The extraction is behaviour-preserving: the gamble, fetch, and blunder suites are unchanged
  (1160 + 27 pinned green). The seam is the deliverable; the flips are the follow-on work.
- Every future value consumer has ONE place to call and ONE currency to argue about under the
  score-diff gate — the four private valuations can no longer drift apart.
- The `no_rule_box` / `energy_type` / `evolvesFrom` parametric facts stay in `card_effects.json`
  clauses read by `fetch_target_matches`; the closure is a representation query, never a text parse.

## Alternatives rejected

- **Converge all four shadows at once.** Big-bang re-baselines every calibrated consumer in one
  step; the round-11 gotcha ("accurate data flips calibrated consumers") and ADR-0060's +76 incident
  both argue for staging each flip under its correction family + the score-diff gate.
- **A proximity multiplier / match-importance γ.** Refuted in Round 8: the same card at the same
  proximity has opposite costs depending on the closure, and a blanket γ is exactly the +76 runaway
  shape. Deadlines and the role tier carry it instead.
- **Keep the closure on the Pilot mixin.** It already unified `_fetch_target_matches` cross-mixin,
  but left the graph un-testable in isolation and un-callable by a non-Pilot consumer (the worth
  backend). A pure module is the ADR-0052 one-oracle shape.
