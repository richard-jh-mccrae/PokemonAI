# TODO — the two parked learned/search tiers (T5 value model · T6 escalation)

**Status:** open (2026-07-07), split out of the tier-vs-planner review. After the ADR-0045 S3/S4 flip
([match-planner](../adr/0045-match-scale-planning-is-a-closed-form-directive-game-plan.md)), **T5
(`value_model`) and T6 (`escalation`) are the ONLY two decision seams still DEFAULT OFF** — every other tier
ships default-ON and refines on the ladder. This file pins their fate: **keep both, defer both, gate the flip
on the Kaggle LADDER — not on a better gauntlet.**

Decision docs: [Tier 5](../architecture/tier-5-value-model.md) /
[ADR-0042](../adr/0042-base-value-model-is-a-dependency-free-logistic-over-objective-features.md);
[Tier 6](../architecture/tier-6-escalation-search.md) /
[ADR-0043](../adr/0043-escalation-search-is-a-budgeted-depth-2-tree-on-a-close-attack-tie.md).

## Decision: keep both, don't refactor away

Both are **dead-weight-free when OFF** — `_value_term` short-circuits before featurizing
(`if not value_model.present: return 0.0`), `_escalate` returns at its first guard (`if not escalation:
return None`) — degrade-safe, capped sub-prize, and **never override a sound rung**. Carrying cost ≈ zero.
They are the **only homes for two irreducible gaps no closed-form layer — the Match Planner included — can
ever represent**:

- **T5** — learned **leaf-judgment calibration** the closed-form leaf lacks.
- **T6** — **opponent-CHOICE** reply reasoning (boards where the outcome depends on *which* of several
  replies the opponent picks; the closed-form tiers collapse the opponent to a static/worst-case projection).

Deleting either throws away working wiring (the leaf seam `_value_term` is already wired; `_escalate` is the
Turn Planner's last rung) + the retrained favorability-live artifact, to re-author it later. The Match Planner
**deepens** both — richer, more cohesive T3/T4 primitives are exactly the feature set a conditioned T5 learns
over and the leaf T6's tree evaluates. They are a stack, not competitors.

## The park asymmetry — same "agent-v-agent" label, different instruments

| | park instrument | result | valid? |
|---|---|---|---|
| **T6** | mega_starmie **MIRROR** A/B, 1000 games | ON **44 %**, CI 41-47 (entirely sub-50) | **YES** — a same-strong-deck mirror is immune to the weak-opponent saturation that voids the gauntlet; only one seat runs escalation ⇒ clean isolation. A real self-inflicted regression. |
| **T5** | cross-deck **gauntlet** (SM/ML/DP paired-delta), 48k games | delta **−0.55 %**, CI **[−1.27, +0.16]** (crosses 0) | **NO** for gain — exactly the 3 decks ADR-0045 calls "too weak to discriminate"; the number proves nothing. |

**Premise correction:** only **T6** was validly refuted. **T5 was never validly measured for gain** — its OFF
disposition stands only on (1) the mirror **safety** A/B (50 %, no regression), (2) the **redundancy**
argument (a *general* logistic over features the closed-form leaf already scores can't add signal), and
(3) conservative-default-for-an-optional-seam. See the Tier-5 doc's *Rationale correction (2026-07-07)*.

## The unlocks + flip conditions

### T5 — matchup-conditioned value model (do first; higher value)

The **general** model is a dead end *by construction* (redundancy). The real signal is **conditioning on the
Read's believed archetype** — the one thing a general model over redundant inputs cannot add.

- **Build:** a `--conditioned` split (ADR-0007 general → conditioned → per-deck) on the kept
  `src/common/value/value_model.json` base (favorability-live, holdout logloss 0.555). The leaf seam
  (`_value_term` → `_leaf_value`, `_PLANNER_VALUE_W`, capped sub-prize) is **already wired** — no plumbing.
- **Validate on the LADDER**, not the gauntlet (the gauntlet cannot measure this gain).
- **Flip condition:** the conditioned model shows gain via **manual Kaggle-ladder corrections + user
  feedback** (the ship-and-refine gate, ADR-0044/0045), with the mirror safety A/B still ~50 % + 0 crashes as
  the floor. Kill-switch `value_model` stays the one-line revert.

### T6 — real opponent-reply model (lower priority)

T6's park is **valid**, so **do not re-test** — the fix is the Gap items, not trigger breadth:

- **Build:** a **real opponent-deck reply model** (via the T4 overlay) to replace the our-policy proxy that
  "systematically loses to the tuned scorer"; then wire the **T5 leaf** as the two-ply leaf.
- **Cheap salvage to try first:** a **commit-margin gate** (commit only on strict improvement beyond a margin,
  not any ε) + a **higher density threshold** — before investing in a reply model.
- **Flip condition:** with a real reply model, the **mega_starmie mirror A/B climbs above ~50 % + margin**
  (a mirror is the *valid* instrument here) and 0 crashes. Kill-switches `escalation` + `search_budget>0`.

## Definition of done (this todo)

Each tier flips DEFAULT ON in the three agents' `main.py` **only** when its flip condition above is met, or is
explicitly re-affirmed parked with the ladder evidence recorded in its architecture doc. **Neither is gated on
"a better gauntlet"** — a better gauntlet fixes neither the redundancy (structural) nor the measurement (only
the ladder measures gain); it would only give T6's future reply model a stronger sparring partner. Update the
tier-5 / tier-6 docs + ADR-0042 / ADR-0043 status blocks + the `tier-planner-t5-t6-fate` memory when either
lands.

> ⚠️ **Verify every card/attack/rule fact at source before acting** (per `CLAUDE.md`): Pokémon **TCG**
> Scarlet & Violet with competition-simulator deltas — read `docs/rules.md` / `docs/rulebook.txt` /
> `data/EN_Card_Data.csv` / the engine, never memory.
