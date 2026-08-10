# ADR-0137: Combat realization aligns each attack and Energy owner

Status: Accepted; built for Issue #495 (2026-08-10).

## Context

Readiness selected one attack's payoff and a line-wide clock selected another attack's cost.
Attach, retreat, evolution, acceleration, and Needs each repeated part of the same build question.
Issue #493 measured contradictory marginals; ADR-0136 supplied the canonical value/status contract.

## Decision

`CombatMath` alone resolves cost slots, Energy provision, typed matching, restaging, expiration, and
one named attack's clock. `MySide.forward_forms` alone enumerates reachable successor topology.

`common.state_value.combat_build_profile` evaluates every attack on the current and reachable forms.
Persistent standing is the maximum of `payoff * (matched / required)^2 * halve(hops)`. Zero-cost
attacks are complete. `combat_realization` keeps each attack's payoff, condition, cost, build, and
clock together and takes `max(build, legal-now, typed-future)`, then the maximum across attacks.
The readiness family applies its existing role relevance and body/board caps afterward.

Held Energy is not attached build. `NeedGraph` owns it as one weighted next-attach slot per in-play
body. Every exact Energy card has its own edge value from `readiness_supply_delta`; the existing
one-card/one-slot assignment remains authoritative. Effect-authored acceleration uses exhaustive
small-N allocation because convex progress makes greedy routing unsound.

Attach and retreat are damage-currency adapters over the shared build profile. Evolution, promote,
dig closure, acceleration, deploy unlock, and recipient capacity consume the same profile or
marginal. Terminal `attack_ev`, transition semantics, search policy, and all existing value rates,
weights, caps, and family order remain unchanged.

## Consequences

New understood cards inherit value from provider mechanics without deck/card policy. UNKNOWN cost,
provision, restaging, or reachable candidates stays scalar-zero-compatible and appears in profile,
readiness, and hand diagnostics. Contract schemas advance to state-value `/2`, coverage schema 4,
and Composer sensitivity `/3`.

## Corpus ruling and validation

Issue #495 accepts movement only when the shared profile produces the separating value; no card,
frame, Active-slot, search-width, or search-depth exception is added. The base/current lab comparison
at `516e82d1` therefore rules these decision movements as one domain class: the selected option owns
the stronger exact attack envelope after typed provision, per-attack cost, reachable form, and
now/future legality are kept together.

* MAIN: `82225643|1|decision|11`, `82229122|0|decision|45`,
  `82523811|1|decision|59`, `82523811|1|decision|95`,
  `82525741|0|decision|77`, `82866415|0|decision|48`,
  `83968638|1|decision|17`, `84071010|0|decision|15`,
  `84890060|1|decision|11`, `85045840|0|decision|6`,
  `85059103|0|decision|84`, `85785606|0|decision|19`, and
  `86090676|1|decision|39`.
* Target selection: `83116081|0|decision|21` uses the exact per-body attach marginal;
  `83686860|1|decision|11` uses the exact evolved-body realization.

Each changed seam has a direct corpus assertion with its mechanic stated beside the expected option.
The discrimination lab improves `79/247` to `83/247`: five old misses become correct and two become
misses. `81903490|0|decision|27` is a leaf-only miss while the shipped decider becomes correct, so it
is not a selected-action regression. `86089617|1|decision|4` remains reported under its existing
Issue #332 holdout; its future leg correctly excludes Energy that cannot survive to that turn.
Authoritative lab baselines remain untouched.

The deterministic sensitivity sweep has 17/17 controls, including the Mega Starmie Wally/attach
order proof and identity-independent equivalent-Energy proof. Strategy, train, parity, coverage,
schema, and generated-report gates are the executable acceptance record. Parallel corpus-lab wall
time is unchanged within measurement noise (base 146.7 s; Issue #495 148.4 s).
