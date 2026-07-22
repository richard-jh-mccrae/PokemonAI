# Evolve valuation — grill-session seed: one equation for the Evolve decision

**Status (2026-07-15).** SEED for a grill session — NOT designed, NOT built. The counterpart to
`attach-valuation-grill-spec.md`; item #4 of `valuation-systems-coverage-review.md` ("Generalize
evolution-timing"). The doc names the frame verbatim — the evolve decision is **"Needs-vocabulary
shaped"** — and the Needs substrate already carries every term (see §"Machinery"). This grill decides
HOW an evolve's marginal need-coverage combines; the build extends `needs.py`, it does not add rungs.

Precipitating correction: a first pass shipped three brittle rungs (`evolve-to-turn-on-the-draw-engine`,
`dont-open-the-fragile-line-base` gated on `card_id == DREEPY`, `dont-grab-the-unpayable-fetcher`) and
was REVERTED (2026-07-15) — the exact per-case brittleness the value systems exist to retire. This spec
is the right-shaped replacement. (The fetch case is NOT here: an unpayable fetcher is a GATE — the
`fetch_deploy_odds` sibling — built directly, no grill.)

## Why this is a convergence

Evolving is priced today by a **pile of rungs** in `baseline_evolution.py` (`evolve-into-wincon` +40,
`advance-the-evolution-line` +15, `evolve-the-energized-body-first` +5,
`advance-the-energized-line-body-first` +5, `prefer-rush-evolve-tutor` +30,
`dont-rush-evolve-without-target` −60) PLUS deck text (`dragapult_ex` `hold-evolution-until-attacker-ready`
−46). Every one is a shadow or premise-gate of a single quantity — the marginal change in board
need-coverage the evolve produces — and the deck rung is exactly the ADR-0034 fold candidate item #4
wants gone. Correction mass: the 0715 dragapult evolving cohort (86090164, 86091435, 86091728) plus the
covered anchors (f82 body-first, f31 promote-preserve, f29 charge-the-line).

## The hypothesis (one sentence)

An evolve's value is the **marginal change in board need-coverage it produces**, priced in the one
currency — the income it turns ON or OFF, the readiness/line it advances, minus the coverage it
destroys and the exposure it takes on:

```
evolve_value(body B → result R) =
    Δcover(draw_engine)      = cover(R's ability) − cover(B's ability)   ← draw_engine_slot delta (income)
  + Δcover(line / deploy)    = R advances the wincon line / is deploy-now ← line_slots + deploy_now_slot
  + Δcover(fund_attack)      = R can pay a VALUED attack it couldn't      ← typed-readiness, gated by turns_to_ready
  − exposure_cost(R in slot) = R's fragility × threat in the slot it occupies (Active vs Bench)
```

"When to evolve (now vs later)" is not a gate — it is this value vs the alternative of KEEPING B's
coverage and evolving later: a `deploy_now` slot is deadline-0 and un-bankable (full marginal), but if
evolving DESTROYS a live `draw_engine` (Drakloak's Recon), the deploy must out-value the income stream
it ends. That comparison IS `hold-evolution-until-attacker-ready`, derived not asserted.

The existing rungs as shadows: `evolve-into-wincon`/`advance-the-evolution-line` = the line/deploy Δ;
`evolve-the-energized-body-first`/`advance-the-energized-line-body-first` = the fund_attack Δ maximised
on the body that already carries energy (which-body); `prefer-rush-evolve-tutor` = a deploy_now
enabler; `hold-evolution` = the income-vs-deploy temporal comparison; `dont-rush-evolve-without-target`
= deploy_now slot ABSENT (no target) ⇒ 0.

## Machinery that already exists (verify at source, reuse — don't rebuild)

- **`needs.py` slots** — `deploy_now_slot(key, value)` (an eligible evolution THIS turn, deadline 0);
  `draw_engine_slot(engines_online, value)` (the recurring draw need, SATURATING — the marginal engine
  halves; this is the income term for BOTH turning one on and losing one); `line_slots(key, value,
  succession, primary_met, succession_urgent)` (assembly + succession); `fund_attack_slots(body_key,
  cost_remaining, quota_spent)` (per missing Energy unit, with deadline); `answer_doom_slot(value,
  deadline)` (the doomed-body preserve).
- **`turns_to_ready(energy_deficit, evolve_hops, attaches_per_turn)`** — the exact "energy clock": MAX
  of attach-turns and evolve-hops (parallel, not summed). The now-vs-later timing.
- **Typed readiness** — `AttackStat.energyTypes` (Phantom Dive = `(Fire, Psychic)`, enum matches obs
  `energies`) → a colour-aware "can R pay a valued attack" test. Verified 2026-07-15: the raw
  `evolve_body_energy` COUNT is colour-blind ({R}{D} = 2 but 1 toward {R}{P}); the equation must use
  the typed affordability, not the count.
- **`card_worth`** (ROLE/TAG tiers) for the ability's worth and the result's worth.
- **`_resolve_needs`** (pilot) — the assignment engine the evolve delta plugs into.

## Round 0 — the measurement pass (DO THIS FIRST)

Replay the evolving cohort through the real `explain()` (FRESH pilot per replay), join `reviewed.json`.
Classify each: already-passing (the covered anchors — f82, f31, f29 — are regression pins) /
income-on (②, 86090164 f40: Dunsparce→Dudunsparce) / income-off-hold (①, 86091435 f35:
Drakloak→Dragapult on wrong colours) / exposure-opener (f2, 86091728 f2: open Munkidori over Dreepy) /
which-body (f82) / refuted (86091728 f12 — first-turn evolve illegal, rules.md L97). Build the corpus
family (pins + xfail) in the hyperclosure-corpus style. Only the legs the survivors flag get converged.

## The grill agenda

1. **The income Δ — persistent vs one-shot.** `draw_engine_slot` saturates (marginal engine halves).
   Drakloak's Recon is a PERSISTENT stream (evolving forfeits EVERY future dig); Dudunsparce's Run Away
   Draw is a ONE-SHOT that recycles itself. Same slot, different horizon — does the persistent stream
   price as a sum-over-turns (a large hold pressure) while the burst prices as a single deadline-0
   deploy? Settle the horizon term.
2. **The typed-readiness gate.** `fund_attack` coverage from an evolve counts only if R can pay a
   VALUED attack — via `AttackStat.energyTypes`, not the energy count (f35 anchor). `turns_to_ready`
   sets the deadline: a body still k typed-Energy short has the readiness slot k turns out, so evolving
   into it buys no THIS-turn readiness.
3. **When to evolve = deploy_now vs kept income.** The now-vs-later argmax: `deploy_now_slot`
   (deadline 0, un-bankable, full marginal) vs the `draw_engine` coverage the evolve destroys. ①'s
   "delay until strictly necessary" must fall out — evolve fires only when the deploy Δ (readiness/line)
   exceeds the income stream ended. Grill that the shipped `hold-evolution` fixtures survive the fold.
4. **The doom carve-out — the affordability question (the ① blocker).** `hold-evolution`'s carve-out
   "evolve now if `active_doomed`" inherits the DELIBERATELY affordability-blind doom oracle
   (`docs/todo/incoming-affordability.md`, ADR-0064): at f35 it fires on an Archaludon holding 1 of 3
   Metal that cannot reach lethal for turns, wrongly securing a body against a non-threat. Does the
   evolve equation get an affordability-aware `turns_to_ready`-of-THEIR-attack read (the same lookahead
   already computed for `deny_slot`), scoped to this carve-out — or does it inherit the global punt?
   This is the gate that kept ① from landing; settle it here.
5. **Exposure / the opener (f2).** A body's value AS the Active = its Active-slot coverage, NOT its
   latent bench worth. Dreepy (fragile, 2 hops from any attacker, no ability) covers ≈ 0 as Active — a
   `general_worth`/line body whose value is future and bench-bound; Munkidori covers more (attacks, has
   Adrena-Brain). The comparison is exposure × fragility, deck-agnostic. CRITICAL counterexample it must
   respect: a **1-hop aggressive base that itself attacks SHOULD open** (mega_lucario opens Riolu, ml
   f1) — so the term is hops-to-payoff × can't-attack-now × slot-threat, never a card-id.
6. **Which-body (f82).** Two equal evolves, one on an energized body → the fund_attack Δ is larger on
   the body already carrying Energy (its readiness slot is nearer deadline). The +5 tie-breaks fold into
   this marginal.
7. **Fold list.** Which of the 6 baseline rungs + the deck `hold-evolution` fold into the oracle; which
   SURVIVE as structure (`dont-rush-evolve-without-target` = slot absence; the deploy-now spike is
   already a slot). The dragapult deck rung folds per ADR-0034 (/deck-align).
8. **Where it lands.** A signed evolve tactical (the ADR-0062 shape) shadow-emitted first (the
   shadow-equations ruling — build in shadow, swap staged), calibrated at the old rung currency.

## Hazards (don't re-buy)

- **The card-id reflex** — f2's reverted rung was `card_id == DREEPY`. The opener term MUST derive from
  line-shape (hops-to-payoff, can't-attack-now), or it re-breaks mega_lucario's open-Riolu.
- **The doom affordability punt** — §4 is a global-doctrine seam (`incoming-affordability.md`); do not
  silently adopt affordability everywhere. Scope any affordability read to the evolve carve-out and say so.
- **The saturation double-count** — `draw_engine_slot` already halves the marginal engine; the income Δ
  must READ that slot's resolver, not re-derive a second engine value (the ② rung's +15 was a naked
  re-derivation).
- **Regression pins** — the covered anchors (f82, f31 promote-preserve-wincon, f29 charge-the-line) and
  the whole `test_baseline_clusters.py` evolution set must survive the fold.

## Sibling grills

- **Attach** (`attach-valuation-grill-spec.md`) — shares the readiness machinery and the currency; the
  fund_attack slot is common to both. Ideally coordinated.
- **Promote/retreat** (`promote-retreat-grill-spec.md`) — the retreat-happy finding (f52/f67, "don't
  retreat a KO-capable Active") belongs there, not here.
- **The unpayable-fetcher GATE** (f47) — built directly as a `fetch_deploy_odds` sibling (can't pay ⇒
  0.0 deploy odds), zeroing the false `grab-the-chain-opener` credit at source. No grill.

## Build shape (per the shadow-equations ruling)

**Phase 1 — the shadow oracle** (after the grill settles the design; no swap gate): compute the evolve
Δ-coverage at the real decision point, emit per-option in the trace (inner terms — income Δ, typed
readiness, line Δ, exposure — plus the output and the AGREEMENT bit vs the rungs' pick). **Phase 2 —
staged swaps**: Round-0 corpus family + shadow-telemetry disagreements rank the fold order (failing legs
first, agreeing anchors last); each swap under corpus + score-diff + the currency-zone rule. Deck-rung
fold via /deck-align. Earns its ADR at the first swap.
