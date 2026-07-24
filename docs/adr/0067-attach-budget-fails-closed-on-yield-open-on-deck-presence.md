# ADR-0067: The Attach Budget fails closed on yield, open on deck presence

**Status.** Accepted (grilled 2026-07-24, issue #137 — Phase 0a of the Value System build,
tracker #136). Companion to ADR-0064 (`reachable_incoming`, the opponent-side twin) and
ADR-0032 (the Effect-Clause compendium the Budget reads).

## Context

The self-side **Attach Budget** / **Reachable Attach** oracle (`CombatMath.attach_budget` /
`reachable_attach`, see the `src/common/CONTEXT.md` glossary) answers "which attack can MY body
pay THIS turn, given everything I can attach this turn." Its famine reading gates LIVE deciders
(the stall-gust family, posture/doom), so its fail direction is load-bearing — and the two
failure modes pull opposite ways:

- **Over-counting the budget** (a false "can attack") silently turns off a famine stall or
  mis-prices doom.
- **Under-counting it** (a false famine) is the motivating blunder itself:
  `dp_stall_gust_false_famine_accel_f70` fired a +105 stall reading "0 Energy → can't attack"
  while Crispin in hand reached `{R}{P}` Phantom Dive that very turn.

A single fail direction cannot serve both. The tension concentrates in the deck-fetch leg:
Crispin's yield needs "that Energy type still in my deck," and with a 3×{R}/3×{P}/2×{D} energy
suite, *provable* presence (anchored deck-tracker counts, else the pigeonhole floor over 6
hidden prize slots) is unattainable before the first deck search anchors the prizes — a strict
soundness gate would zero Crispin's budget for the whole pre-anchor phase and re-fire the exact
false famine the oracle exists to kill.

## Decision

The epistemic is split by **what** is uncertain, not applied uniformly:

1. **Yield fails CLOSED.** A card contributes to the Budget only what its Effect-Clause row
   (`card_effects.json`, ADR-0032) provably models: an absent/unmodelled clause is ZERO, quotas
   are enforced structurally (one Supporter per turn; hand-yield cards compete for the single
   manual attach), Crispin's two units require two distinct Basic-Energy types, and a
   coverage-gate test makes the zero *audited* — every `tutor_energy`/`energy_accel`-tagged card
   in any agent's deck must carry a clause row or sit on an explicit known-unmodelled list.
   The two Energy zones are therefore read at different precisions: the **discard is public**, so
   a discard-sourced yield is capped at the supply really sitting there and the whole turn's
   discard-drawing effects are capped JOINTLY (two Wondrous Patches over one {P} is one attach;
   Rosa's "up to 2" over a lone Basic Energy is one) — a type palette alone would silently
   over-count. The hidden deck is ruled the opposite way:
2. **Deck presence fails OPEN (not-provably-empty), typed.** A typed deck-fetch counts unless
   the deck is PROVABLY empty of that Energy type (`basic_energy_types_in_deck()`, the typed
   per-id extension of the sound emptiness oracle) — the same epistemic the live
   `basic_energy_in_deck` gate already uses, now per-type. The residual over-count (every copy
   of the needed type prized, ≈0.1% for a 3-copy suite) is accepted.
3. **The honest probability lives in `readiness_p`.** The EV variant prices the uncertain
   middle hypergeometrically (`deck_contains_probability`: prize-resolved / pigeonhole extremes
   → 1.0, provably-empty → 0.0). Consumers that can act on a probability read it there; the
   boolean never smuggles one.

**Rejected:** uniform strict provability (anchored-exact else pigeonhole) on the deck-fetch leg.
It buys soundness against a ~0.1% prized-copy corner at the cost of reinstating the motivating
+105 false-famine blunder across every pre-anchor frame of a thin-energy deck.

## Consequences

- Consumers inherit the split blindly: the famine premise swaps to
  `not reachable_attach(active, "cheapest")` with NO new rung or gate, and 1c re-points
  `_promote_fetch_p` at `readiness_p` for its probabilistic middle.
- A future truly-sound consumer (one that cannot tolerate the prized-copy corner) must NOT
  reuse the boolean — it needs the anchored/pigeonhole tier explicitly.
- The clause interpreter is the extension point: new accel cards are new DATA rows
  (clauses/conditions), never new branches in the budget code.
- **Crispin's hand half rides its ACCEL clause (`to_hand: 1`), not a new `fetch` clause** — found
  at build time. A `fetch` row would have been read by the live gamble energy-closure
  (`planner._fetch_reaches_slot`), which `effect_overrides.json` deliberately excludes Crispin
  from ("a Supporter is slot-dead after a Supporter refresh"), so the obvious encoding would have
  silently changed a shipped consumer in a phase whose contract is *no consumer behavior change*.
  The rider keeps the Budget's view complete while every existing clause consumer sees exactly
  what it saw before. New vocabulary this adds to the compendium: `to_hand`, `distinct_types`,
  `target_type` (a recipient's required EnergyType), and `energy_type` on an accel clause.
