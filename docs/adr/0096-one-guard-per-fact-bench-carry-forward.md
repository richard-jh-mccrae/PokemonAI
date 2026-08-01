# ADR-0096 — One guard per fact: the Bench doctrine carries forward as term-family entries

**Status:** Accepted (grilled 2026-08-01, `/grill-with-docs` on Issue #259, wave-1 packet item 3).
**Build = Issue #259 (POC-T0 registry), with retirement owned by T1 and deletions by T2.**
**Rules on [Issue #231](https://github.com/richard-jh-mccrae/PokemonAI/issues/231)** (closed by this
ADR) and carries forward Issues #232, #237, #254 into the POC's term families.
**Narrows [ADR-0086](0086-the-deploy-marginal-prices-a-bench-slot-and-what-fills-it.md) decision 7**
(which made the empty-Bench guard an unconditional sound filter — this makes that unconditionality
*provisional and dated* rather than permanent) and **preserves its decision 9 unchanged**.
**Applies [ADR-0064](0064-the-predicted-loss-rung.md)'s `_predicted_loss` as the single surviving
guard.** Does **not** supersede anything.

⚠️ **Temp-named, not numbered.** Real number assigned at `/open-pr` rebase time. Cite the issue.

**Context issues:** Issue #259 (this grill), Issue #231 (ruled and closed here), Issues #232 / #237 /
#254 (carried forward, not re-grilled), Issue #197 (the deploy-decider swap that raised all four).

## Context

The user's account of why the POC exists, in their own words:

> "This topic was grilled on at length and produced the issues 231, 232, 237, and 254. I was starting
> to implement them when I learned that the State Model and CombatMath layers were not providing the
> level of information that I assumed. This is what sparked this entire reconsideration of our
> system. However, the notes from the benching pokemon still stand."

The doctrine, as stated: never bench during Set Up (hard no — there is no cost or risk to waiting);
an open Bench slot carries a **slot price that escalates as slots deplete**, so the last slot is not
spent on a non-critical support body that a second wincon should have; special bodies (Meowth ex) are
benched **solely to fire an Ability**, so the Ability's value is weighed against the slot price; and
the loss-prevention fill **must consult CombatMath** for whether the Active is KO-able next turn.

### Measured 2026-08-01, not recalled

The doom-gated guard the doctrine asks for **already exists**. `_predicted_loss`
(`src/common/strategy/planner.py:3154`, ADR-0064 decision 3):

```
bench empty  AND  combat.reachable_incoming(active, opp_bodies,
                      charged=_incoming_budget, evo_min_energy=1) >= my_hp
      ->  -KO_SCORE        else 0
```

That is the CombatMath read, already wired, with bounded pessimism (`evo_min_energy=1` — a bare
0-Energy pre-evo is not a credible next-turn game-ender) and the charged budget.

It is **not** the `_their_turns_to_ko` read Issue #231 argued was too sparse to gate on (`None` on
189 non-Set-Up frames). Wave-1 packet item 3 concedes the point — "the sparse-signal premise in the
issue text pointed at the wrong oracle anyway" — and then keeps the unconditional filter regardless.
With the sparse-signal objection void, the only surviving objection is the bounded/unbounded
asymmetry, and `-KO_SCORE` already sits **outside** `_LINE_CAP`'s 590 positional band, so it is
un-outbiddable by construction. The asymmetry argument does not reach `_predicted_loss`.

**One board fact, three mechanisms, all three on the §6 whitelist:**

| # | mechanism | shape | gated on the doom read? |
|---|---|---|---|
| 1 | `_predicted_loss` | `-KO_SCORE` terminal rung | **yes — CombatMath** |
| 2 | `Pilot._empty_bench_forced` | order filter (`pilot.py:1787`) | no |
| 3 | `keep-a-bench` | +60 weight, unscoped `when()` (`baseline_bench.py:26`) | no |

T0's headline rule is "every board fact enters through exactly ONE term family." The draft whitelist
breaks it three ways on this one fact.

Set Up is a genuinely different rule and is **already correct**: `pilot.py:1750` proves deferring
weakly dominant from three source-checked facts — the placement is optional (`rulebook.txt` L97), no
attack reaches me first in either seat (`docs/rules.md` §2), and of the 21 damage-counter Abilities
in `data/EN_Card_Data.csv` **zero** sit on a Basic, so no Ability damage reaches me either.

## Decision

**1. One guard per fact; the filter is PROVISIONAL, with a dated retirement test.**
`_empty_bench_forced` is whitelisted **tagged provisional** — a substrate-gap workaround, not a
permanent structural rule. The registry states its retirement test now, so it cannot quietly become
permanent: after T1 threads TheirSide, measure `reachable_incoming`'s answer rate over every
post-setup empty-Bench corpus frame; **retire the filter iff** the read answers on all of them AND
both gates stay green with it removed. `_predicted_loss` is then the sole guard and enters
`state_value`'s `survival` family as a terminal term.

**2. `keep-a-bench` (+60) is deleted.** It guards nothing the filter does not already guarantee at
MAIN (the filter runs *after* `_finish_turn_last`, `pilot.py:1605` vs `1601`, so it wins outright),
and per Issue #231's own numbers it is the *entire* gap between a spare body pricing 1.96 and 61.96
— i.e. it **is** the spare-body cliff. Deletion is measured, not blind: both gates run with the rung
removed, and its unscoped `when()` is probed in the `_SETUP_BENCH` context that decision 9 excludes
the filter from.

**3. Set Up stays a hard no, on its own whitelist line.** ADR-0086 decision 9 is unchanged and is
ratified separately from the in-game guard, with its stated reason (weak dominance, three
source-checked facts) — not bundled with it.

**4. The four issues carry forward as term-family entries, not as re-grills.**

| source | finding | lands as |
|---|---|---|
| Issue #231 | conditional guard? | `survival` — one guard, `_predicted_loss`, CombatMath-gated |
| Issue #232 | spare body 1.96 vs 61.96 | `development` — an escalating slot price; the cliff is the +60 |
| Issue #237 | `_TO_BENCH` + `bench_harvest` | one deploy marginal owns every entry point |
| Issue #254 | rollout slot ordering | Option-Equivalence: open slots are indistinguishable = ONE class |
| doctrine | never bench at Set Up | whitelisted as-is, own line |
| doctrine | Meowth ex = Ability only | `ability_marginal` leg weighed against the slot price |

**5. The slot price escalates.** `development` prices an open Bench slot as a *scarce resource whose
marginal cost rises as slots deplete*, so the last slot is not spent on a non-critical body. This
replaces the current cliff, in which the whole signal was a flat +60 that fired only at zero bench.
Issue #231 is closed as **ruled-keep-provisional** on this ADR.

## Consequences

- The POC ships with a known-redundant guard for at least one track. That is deliberate and
  **visible**: a dated obligation on the registry beats an invisible permanent exception.
- Someone must actually run the retirement test after T1. If it is not run, the filter stays — which
  is the safe direction, but the registry entry is what makes the omission legible.
- Deleting `keep-a-bench` will move frames in both gates; each becomes a wave item.
- The escalating slot price is new work in T3's `development` family, not a port of an existing term.
  The convexity shape (how steeply the price rises) is authored for the POC and queued for the
  post-POC learning phases, like every other authored constant inside a firing equation.
- Issues #232 / #237 / #254 are **not** re-grilled. Their content is carried by the table above; the
  owning tracks implement against it.
