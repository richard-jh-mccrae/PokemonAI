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
  Scoped in [`docs/plans/gate-library-scope.md`](../plans/gate-library-scope.md). The
  searcher/recycler leg landed 2026-07-19 (the fetcher gate — see the reconciliation bullet above);
  later stages (quota / pressure gates; the discard-side `86091435-68` which needs a principled
  discard convergence first, NOT a flat rung) extend the same `deploy_odds` seam.
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
