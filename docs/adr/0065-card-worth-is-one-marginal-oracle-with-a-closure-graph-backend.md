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
- **WP-N5b — the readiness-leaf fold is BLOCKED on hand-visibility plumbing (2026-07-20).** Round 5's
  actual "readiness consumes the needs module" fold — the leaf's own deferred v2 "actionable-resource
  term" (`board-state-valuation-grill.md` §v1→v2: "credit only held cards with a LIVE use") IS the
  needs assignment — cannot be built yet: the sim end-obs HIDES my hand (`_readiness` reads
  active/bench only; grill §"What the grade does NOT see"), so the leaf has no hand to value. The
  fold needs the hand-visibility plumbing FIRST (the grill names it the v2 enabler). Staged; the
  general-worth slots (WP-N5) already moved the shared vocabulary onto the leaf's terms, so the fold
  is a wiring + bench-gated swap once the hand is plumbed, not a re-derivation.

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
