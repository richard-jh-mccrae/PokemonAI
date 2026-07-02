# ADR-0032: Card knowledge is an engine-audited effect compendium (three tables + one damage oracle)

**Status.** Accepted (grilled 2026-07-02, `/grill-with-docs`). **Built 2026-07-02** (TDD, all
slices + F/G tiers): AttackStat + the `predicted_damage` oracle routed through every Tier-0 damage
site; audit harness + differential diff + override generator — **96.6% of 9.5k engine measurements
predicted exactly, over-prediction zero**; Effect Clauses (incl. condition gates) feed the Planner's
stabilize; defender-side fields engine-verified (the untagged-Sylveon gap, Nebula-pierces-Drednaw).
Spec: [docs/attack-effects.md](../attack-effects.md). Terms in
[src/common/CONTEXT.md](../../src/common/CONTEXT.md): *Attack Effect*, *Damage Formula*, *Effect
Clause*.

**Context.** The agent's closed-form (Tier-0) layers blunder wherever a card's mechanics exceed the
current representation. The motivating case: vs Crustle (`prevent_ex_damage`), Mega Starmie ex must
never Jetting Blow (0 to the Active — though its 50 bench-snipe still lands) and always Nebula Beam
(it *ignores Abilities*, so 210 lands). Today `_ability_prevents_damage` is **attack-independent** —
it zeroes *every* attack, including the one that ignores the Ability, and
[pilot.py](../../src/common/pilot.py) `_tactical` returns 0 before crediting the still-landing
bench-snipe rider. There is no attack-level "ignores Abilities/Weakness/Resistance" anywhere in the
model. Meanwhile the existing card knowledge is scattered across mechanisms grown one blunder at a
time: four parallel `{attackId: value}` dicts threaded as separate `Pilot.__init__` args (damage,
cost, recoil, bench-snipe), regex text-parsers in [provider.py](../../src/common/scouting/provider.py)
that deliberately under-credit conditional phrasings, boolean Function Tags (ADR-0006), and `CardStat`
card facts. Damage math is re-derived at ~8 call sites (pilot, lethal, planner, gust/tool doctrines).
The Engine Search (Tier-1) already resolves all of this correctly — but only closed-form reasoning
prunes and chooses *before* the sim budget is paid, so gaps there are real blunders. Verified scale:
1556 attacks / 1267 cards; 381 attacks print damage 0 while some (Alakazam's Powerful Hand) deal
scaling damage the printed number hides.

**Decision.**

1. **Consumer-bounded encoding, all-cards review (not an exhaustive effect database).** Every card is
   reviewed by pipeline; a mechanic is *encoded* when a Tier-0 consumer would blunder without it.
   Mechanics only the engine ever resolves go on a known-deferred ledger, not into unread models.
2. **Two-tier representation.** Attack-keyed **`AttackStat`** (`{attackId: AttackStat}`, mirroring
   `CardStat`, one provider build site, one constructor arg — the four flat dicts fold in
   incrementally) carries per-attack facts: damage, cost, ignore-flags (Ability / Weakness /
   Resistance), riders (recoil, bench-snipe), and the damage shape below. Card-keyed facts stay on
   `CardStat`, extended with **fitted defensive fields** (e.g. `damage_reduction`,
   `prevents_damage_from: none|ex|all`); Function Tags remain boolean *routing triggers* (ADR-0006
   untouched) while the parametric fields carry the math.
3. **Damage is a formula, not a number.** Four verified classes: **(A) visible-state scalers**
   (Alakazam hand-size, Kyogre discard-count, Psychic's opponent-energy) → closed-form
   `base + per_unit × count(var)` over a closed variable enum, exact at decision time; **(B) true
   RNG** (coins) → measured `min`/`max` bounds — my Lethal reads the floor (sound; CONTEXT.md
   *Lethal* already demands worst-case coins), Incoming reads the ceiling; **(C) hidden-state
   scalers** (Mega Abomasnow ex's Hammer-lanche deck-discard) → sound pigeonhole floor from the exact
   deck tracker (ADR-0029's sound half) + hypergeometric EV from Deck-Content Odds for heuristic
   ranking; **(D) persistent modifiers** (Frost Barrier's next-turn −30) → a defender-side fact;
   *runtime visibility of the transient state is a noted deferral*. Expected value was rejected
   outright: it breaks soundness in both directions (phantom coin-lethals; understated threat).
4. **One damage oracle.** A single `predicted_damage(attacker, attack_id, defender, board, bound)`
   consults AttackStat modifiers + Weakness/Resistance + defender Ability/reduction fields,
   **per-target** (an Ability that zeroes Active damage does not zero a bench rider — fixing the
   latent Jetting-Blow-vs-Crustle snipe blindness). All ~8 damage call sites route through it. A new
   mechanic lands in exactly one place, and the audit diffs exactly one function.
5. **The differential engine audit is generator, verifier, and gate.** Generalizing
   [probe_resistance.py](../../tools/sim/probe_resistance.py): drive the native engine, diff actual
   dealt HP against the oracle's prediction — **every mismatch is a discovered gap**. A fixed ~5-body
   defender panel (vanilla / Weak / Resistant / ex-damage-preventer for ex attackers / +HP-tool body)
   exercises every modifier class; sweep-probing varies one state variable and regresses dealt damage
   to fit Class-A formulas; `search_begin(manual_coin=True)` forks both coin outcomes to measure B's
   exact bounds. Measurements **directly populate** the shipped table (as probes populate
   `card_functions.json`); `attack_overrides.json` is the hand-authored tail for what no panel
   reaches, triaged by meta usage but targeting 100%. Text is never the source — it is the *cue*
   (flagging effect-words that produced no modifier) and the *diagnosis* after a diff fires.
6. **Trainers/Abilities get parametric Effect Clauses, engine-measured.** The probe classifier
   already reads magnitudes (`HP_CHANGE.value`) and throws them away; it now keeps them —
   `card_effects.json`: `cardId → [{kind, amount, target_restriction, rider}]` (Wally's Compassion =
   `heal(all, Mega-only)` + `bounce_energy(→hand)`). Restrictions are *observed* from which targets
   the select actually offers (seed the board with a damaged Mega and non-Mega); untriggerable
   clauses go to overrides via the text-cue queue.
7. **All cards, offline, shipped.** Everything is precompiled in `tools/` (the probe/audit build),
   shipped as static JSON beside `card_functions.json` (ADR-0003/0004), loaded once at match start —
   O(1) per decision, zero grader probing. All-cards breadth makes meta shifts a non-event: a niche
   deck that surfaces next week is already in the table.

**Build order (I1, tracer-bullet).** (1) AttackStat + oracle + consumer routing + goldens
(Nebula-vs-Crustle = 210; Jetting Blow vs Crustle = 0 Active + 50 bench), hand-seeded overrides
first; (2) the audit-generator replaces hand seeds with engine-derived tables over all 1556 attacks;
(3) defender-side audit → CardStat fields; (4) Effect Clauses + first consumer (heal amounts into the
Planner's stabilize math). Parallelizable as three tracks (spine serial in `src/common`; audit
harness and clause classifier in `tools/` worktrees) with a serial union-verify join.

**Considered options.** *Exhaustive structured effect DB regardless of consumers* — rejected: unread
models rot unverified. *Text-parse as primary source* — rejected: lossy and forbidden
([CLAUDE.md](../../CLAUDE.md): the simulator is the authority; the probe pipeline exists because
text parsing was already rejected for tags). *Keep adding flat per-mechanic dicts* — rejected:
constructor explosion, no single verifiable unit. *Parametric Function Tags* — rejected:
stringly-typed math in a `list[str]`. *Expected-value damage* — rejected: unsound both directions.
*Meta-ranked breadth (audit only played cards)* — rejected by the owner: the compendium must cover
all cards so meta shifts and niche techs are pre-covered; meta rank triages only the hand-override
queue.

**Consequences.** The oracle becomes the single seam where card mechanics meet decisions — mixins
stop re-deriving damage. The audit doubles as a CI regression gate (prediction == engine on the
panel; golden interactions locked). The regex parsers survive as offline-safe fallback when the
engine isn't loaded, cross-checked by the audit instead of trusted blind. Known deferrals: transient
effect state at runtime (Frost Barrier's active −30), meta-defender diffing beyond the fixed panel
(add only if a gap escapes), non-damage clause tails via overrides.
