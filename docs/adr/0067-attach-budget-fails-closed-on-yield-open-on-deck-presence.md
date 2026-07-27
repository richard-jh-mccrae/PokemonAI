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

   Where a card's own text leaves a yield genuinely ambiguous, the ambiguity is resolved the same
   way. Crispin over a deck down to ONE not-provably-empty colour finds a single Energy, and "put
   1 of them into your hand. Attach the other" does not say which half that lone card is. **Ruled:
   it is the HAND half** — so it still needs the turn's manual attach and is worth nothing once
   that is spent. The braver reading (the card attaches itself with the manual attach already
   gone) would be a claim no source settles, made in the direction this ADR forbids guessing in.
   The engine could be probed to settle it; until then the code states the assumption rather than
   implying the model has no choice to make.
   The two Energy zones are therefore read at different precisions: the **discard is public**, so
   a discard-sourced yield is capped at the supply really sitting there and the whole turn's
   discard-drawing effects are capped JOINTLY (two Wondrous Patches over one {P} is one attach;
   Rosa's "up to 2" over a lone Basic Energy is one) — a type palette alone would silently
   over-count. That cap is carried as a **capacity group** into the affordability matcher rather
   than trimmed off the unit list beforehand, because the constraint is per-COLOUR, not merely a
   count: two units off a `{R:1, P:1}` pile genuinely reach `{R}{P}` but must not reach `{P}{P}`,
   and a count-only cap calls the second payable. Colourless slots are charged against the same
   capacity — an Energy spent paying a colourless slot still leaves the pile. The hidden deck is
   ruled the opposite way:
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

## Amendment (2026-07-27, grilled — issue #142, Phase 1d): the leg is chosen by WHICH CONSUMER ASKS

The original decision splits the epistemic by **what** is uncertain (yield vs deck presence). Phase
1d's consumer sweep found that insufficient: the same deck-presence uncertainty has *opposite* safe
directions depending on the question being asked, so the leg must also be chosen by **who is
asking**.

**The Provable Budget.** A second reading of the same Budget, one argument apart: the deck-fetch leg
counts a type only where `CountTriple.floor >= 1` (the pigeonhole surplus — more unseen copies than
hidden prize slots, so they cannot all be prized) instead of `ceiling > 0`. Same oracle, same clause
interpreter, same caps; everything already certain is in BOTH legs — an Energy in hand, an Item accel
(Items all play, no quota to lose), a discard-sourced attach over the public pile. Both legs collapse
once a deck-revealing search anchors the prizes.

**The assignment rule.** A consumer takes the fail-OPEN leg when a false *famine* is the costly error
— it is about to STAND DOWN, and the original +105 blunder is what standing down wrongly costs. It
takes the Provable leg when a false *live-ness* is the costly error — it is about to SPEND something
that expires unused if the reach never materialises (`dont-play-damage-boost-when-cant-attack`: an
Item, discarded having buffed nothing, ep83966336 f14).

**Known limitation, stated rather than implied.** The instrument is imperfect for the case that
motivated it. The residual risk behind a spend decision is largely the **one-Supporter-per-turn slot**
— the Budget enumerates each Supporter as an alternative play-set and asserts only that *a* play-set
exists, never which one the turn spends — and no leg models that. The Provable leg addresses it
obliquely, by zeroing the deck leg (`floor = 0` whenever `unseen <= 6`, i.e. every realistic Energy
suite pre-anchor). Accepted for a −12 nudge; explicitly NOT extended to the composed-line KO claim,
which keeps the fail-open leg at parity with its predecessor. The honest instrument for the tail —
whose error runs ≈0.06% at 3 unseen copies but ≈13% at 1 — is `readiness_p`, tracked as **#175**.

## Amendment (2026-07-27, grilled — issue #142): famine scans ALL attacks, and carries a rule-level leg

Two corrections to this ADR's Consequences section, both found by building against it.

1. **The famine premise is `not reachable_attach(active, None)`, not `…, "cheapest"`.** Once costs
   are typed, "the cheapest attack is unpayable ⇒ cannot attack" is unsound — a cheap `{F}{F}` can be
   unpayable while a dearer all-colourless cost is payable. `attack_id=None` scans every attack. (The
   shipped 0a code is already correct; the prose was not.)
2. **Famine is not purely an affordability question.** A body that cannot legally attack is a famine
   however much Energy it holds: Asleep or Paralyzed ("it cannot attack or retreat",
   `docs/rulebook.txt` L190 / L206), or the first player on turn 1 (`turn <= 1`; rulebook L152). These
   are SIDE-level facts — the condition flags ride on the player dict, not the body — so they live as
   `MySide.attack_blocked` on the StateModel, and `CombatMath.reachable_attach` stays body-scoped
   (typed cost plus ADR-0033 locks). The engine-menu conjunct is NOT the mechanism: it remains on the
   attached-plus-manual signal, where its own guard is corrected from "is there an Energy card in
   hand" to "is the Budget non-empty" — the same under-read as the retired `+1`, one conjunct away.

**Composition with doom.** `active_doomed` over-claims their threat (worst-case, relax-only); the
corrected famine is optimistic about my own reach on the deck leg. Under `active_doomed and
active_famine` the two therefore pull opposite ways rather than compounding, and the conjunction is
tighter than either leg. The one path that could still manufacture a false famine — an accel card
with no Effect-Clause row — is audited and CI-gated by `tests/strategy/test_attach_budget_coverage.py`.

## Amendment (2026-07-27, grilled — issue #142): hand SPECIAL Energy is a Function Tag, not a branch

A third way the Budget went silently blind, found while swapping the consumers — and live on a
shipped deck, so it belongs beside the fail-closed rulings above rather than in a follow-up.

The Budget's hand leg counted `is_typed_basic_energy`, so a **Special** Energy contributed nothing.
Ignition Energy "provides {C} Energy… If this card is attached to an Evolution Pokémon, it provides
{C}{C}{C} Energy instead" (card text, `data/EN_Card_Data.csv` id 17) — one attach arms a Mega
Starmie ex from ZERO. mega_starmie runs it; slowking runs Boomerang (9) and Telepath Psychic (19).
Unmodelled, that board reads as a famine while the hand holds the card that arms it: the same class
as the retired `+1`, one zone over.

**Ruled: the provision is a `provides:N` / `provides_evo:N` PARAMETRIC Function Tag** — the same
shape and the same reason as `dig:N`, per-card DATA that ages with the card pool through the
card-functions pipeline rather than a constant in the affordability code. Curated in
`tools/meta_tracker/function_overrides.json` against the card text (unioned at build, never
clobbered by regeneration). The COLOUR is deliberately NOT tagged — `CardStat.energyType` already
carries it, so the tag adds only what the stats cannot say. The manual attach consequently plays one
source GROUP rather than one unit: a Basic is one, a Special is however many it prints, coloured
exactly as `_attached_units` colours the same card once attached.

Untagged still contributes ZERO (the yield ruling above, unchanged), and
`test_attach_budget_coverage.py` now audits Special Energy in shipped decks exactly as it audits
accel cards — verified non-vacuous by dropping the tag and watching the gate fail.
