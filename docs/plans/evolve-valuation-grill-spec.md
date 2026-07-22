# Evolve valuation — grill-session seed: one equation for the Evolve decision

**Status (2026-07-15).** DESIGN SETTLED (grill 2026-07-15, §"Settled design" below) — NOT yet built.
The counterpart to `attach-valuation-grill-spec.md`; item #4 of `valuation-systems-coverage-review.md`
("Generalize evolution-timing"). The doc names the frame verbatim — the evolve decision is
**"Needs-vocabulary shaped"** — and the Needs substrate already carries every term (see §"Machinery").
The grill decided HOW an evolve's marginal need-coverage combines; the build extends `needs.py`, it does
not add rungs. Next action: Round 0 measurement, then the Phase-1 shadow oracle.

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

## Round 0 — the measurement pass (DONE 2026-07-15)

Measured through the real `explain()` (FRESH pilot per replay); corpus family committed at
`tests/strategy/test_evolve_valuation_corpus.py` (pins + `xfail(strict)` targets, hyperclosure style).
Baseline:

| correction | leg | result |
|---|---|---|
| f82 85785609-82 | which-body | **PIN** (pass) |
| f31 85046350-31 | promote-preserve-the-line | **PIN** (pass) |
| 83686860-29 | line-progress (advance over spread) | **PIN** (pass) |
| f85 | concentrate on the started line | **PIN** (pass) |
| 86090164-40 | income-ON (one-shot burst) | **TARGET** (xfail) |
| 86091435-35 | income-OFF hold + typed + scoped doom | **TARGET** (xfail) |
| 86091728-2 | exposure / opener (line-shape) | **TARGET** (xfail) |
| 86091728-12 | first-turn evolve illegal (rules.md L97) | refuted (excluded) |

4 pins, 3 targets — the equation's job is the 3 targets without regressing the 4 pins. Each target's
`xfail(strict)` flips to a hard failure (XPASS) the moment the equation lands, forcing the mark's removal.

## Settled design (grill rulings, 2026-07-15)

1. **Income Δ — horizon (RULED).** `Δcover(draw_engine) = cover(R's ability) − cover(B's ability)`; the
   SIGN gives pull (turn-on) vs hold (turn-off). Magnitude splits on the RECYCLE card-fact:
   - **ONE-SHOT** (self-shuffle — Run Away Draw "shuffle this Pokémon into your deck") → a single
     **deadline-0** draw event ≈ `draw_engine_slot` value; a deploy-now burst (pull). ② needs no more.
   - **PERSISTENT** (body stays — Recon, once/turn) → a **stream** =
     `draw_engine_value × turns_to_ready(R's payoff attack, TYPED)`. The hold pressure that collapses to
     0 exactly when the body is typed-ready. ① is DERIVED, and colour-safe (uses the typed deficit).
2. **Typed readiness (RULED).** `fund_attack` coverage from an evolve counts only via
   `AttackStat.energyTypes` (colour-aware), never the energy count; deadline = `turns_to_ready(typed_
   deficit, evolve_hops)`. A body that can't pay the payoff colours buys 0 this-turn readiness (f35's
   {R}{D} reads 1-short of {R}{P}).
3. **When to evolve — derived (RULED).** now-vs-later = `deploy_now_slot` (deadline-0, un-bankable) vs
   the persistent income stream ended. Evolve iff deploy Δ (readiness + line) ≥ the stream.
   `hold-evolution` is DELETED, not asserted.
4. **Doom carve-out — scoped affordability (RULED, user 2026-07-15).** The "evolve now if
   `active_doomed`" carve-out gets a **SCOPED opponent-`turns_to_ready` read** — reusing the `deny_slot`
   lookahead (their visible Energy deficit + forward hops) — so it fires only when the opponent can
   ACTUALLY reach the KO. Scoped to THIS carve-out; the global affordability-blind doom oracle
   (`docs/todo/incoming-affordability.md`, ADR-0064) is UNTOUCHED. This lands ① (f35: Archaludon on 1 of
   3 Metal ⇒ not doomed-for-evolve ⇒ hold and keep digging Recon).
5. **Exposure / opener (RULED).** `exposure_cost(R) = R's fragility × threat-in-its-slot`; the opener
   term derives from LINE-SHAPE — `hops_to_payoff × can't-attack-now × slot-threat` — **never a
   card-id**. Dreepy (2 hops, no attack) ≈ 0 Active-coverage; **Riolu (1 hop, attacks) still opens**
   (mega_lucario constraint preserved).
6. **Which-body (RULED, folded).** The energized body's readiness slot is nearer its deadline ⇒ larger
   `fund_attack` Δ. The two `+5` tie-breaks disappear into item 2.
7. **Fold list (RULED).** FOLD into the oracle: `evolve-into-wincon`, `advance-the-evolution-line`, both
   `energized-body-first`, and the deck `hold-evolution` (via /deck-align, ADR-0034). SURVIVE as
   structure: `dont-rush-evolve-without-target` (= deploy-now slot ABSENT), `prefer-rush-evolve-tutor`
   (= a deploy-now ENABLER, a PLAY option type, not an evolve).
8. **Landing (RULED).** A signed `_evolve_value_tactical` (ADR-0062 shape), **shadow-emitted first**
   (shadow-equations ruling), calibrated at the old rung currency; staged swaps ranked by the Round-0
   corpus + shadow disagreements. Earns its ADR at the first swap.

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

**Phase 1 — the shadow oracle: DONE (2026-07-15, commit 9d0b958).** `common/evolve_value.py` computes
the full equation (deploy readiness-conditioned + income_gain − income_loss + scoped-doom); the Pilot
reads the board into `EvolveInputs` and emits `OptionTrace.evolve_shadow`. Proven to rank all four
evolve corpus cases correctly in shadow (f40 +12, f35 +3 held below Recon, f82 energized 32 > bare 27,
f29 32 > spread); suite green.

**Phase 2 — the swap: ATTEMPTED, then REVERTED to shadow (2026-07-15) — two calibration gaps found.**
Wiring `evolve_shadow` into `score` and deleting the rungs flipped f40 to pass (XPASS, as designed) but
surfaced two regressions the shadow ranking did not — the "seed at old currency, full-family re-audit"
hazard, made concrete:
  1. **The exposure term is load-bearing, not optional.** dragapult f32: evolving the threatened Active
     Dreepy→Drakloak scores 32 (deploy 15 + energized 5 + income 12) and beats the correct
     `retreat-to-wall-the-line` (30). Without the exposure penalty (evolving a fragile Active under a
     real threat, wall alternative present) the income term over-values the evolve. Build the exposure
     term BEFORE the swap.
  2. **Mega-family deploy under-calibrates vs the old rung STACK.** mega_starmie 82525741-78: an unready
     Mega Starmie evolve scores 10 (UNREADY tier) but must beat a competing attach (45) / Pokégear (20)
     the old `evolve-into-wincon +40` stack cleared. The `_DEPLOY_WINCON_*` band needs re-auditing
     against the full mega/lucario evolve corpus (not just the dragapult targets), with the discriminator
     staying `income_loss` (megas have none → evolve; dragapult's Recon → hold), NOT the flat tier.

Next: build the exposure term + re-audit the deploy band against the mega/lucario evolve corpus (extend
the Round-0 corpus family with those cases), re-prove in shadow, then re-attempt the swap under corpus +
score-diff + the currency-zone rule. Deck-rung fold (`hold-evolution`) via /deck-align. Earns its ADR at
the first successful swap.
