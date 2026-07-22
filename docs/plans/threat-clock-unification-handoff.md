# Unify threat/doom + board-clock into one Threat Clock (handoff, 2026-07-22)

**For a session picking up the opponent-read value equations.** Today the opponent's threat is read
by **two subsystems** that are really two projections of the *same* opponent-attacker model onto
different axes, with deliberately **opposite conservatism**. This handoff argues they can — and should
— be one **Threat Clock** (ADR-0045 names it), records why they're split, and gives the concrete,
partly-built combine path. Companions: `snipe-system-handoff.md`, `turn-planner-snipe-and-gust-scenarios.md`.

## The two subsystems today

| | **Threat / doom** (`combat.py`) | **Board-clock** (`pilot._opp_turns_to_ready`) |
|---|---|---|
| Question | "Does their attack **kill** my Active next turn?" | "How many **turns** until their line is **armed**?" |
| Output | **damage** vs my HP → boolean `active_doomed` | **turns** (a count) → the deny-slot deadline |
| Horizon | 1 step (current form + one evo hop), ADR-0064 | N steps: `energy_deficit / 1-attach-per-turn + evolve_hops` |
| Entry points | `active_doomed` / `incoming_active_damage` / `forward_incoming_damage` / `reachable_incoming` | `_opp_turns_to_ready` → `needs.turns_to_ready` |
| Consumers | heal, retreat, tool-deploy, posture, leaf survival (**18 call sites**) | the deny slot (Hammer valuation) in `_resolve_needs` |
| ADR | 0052 / 0064 | 0064 (deny), 0062 (oracle) |

## Why they're split — the load-bearing tension

**Opposite fail-closed directions on the SAME fact (the opponent's reachable accel):**

- **Doom is PESSIMISTIC.** `reachable_incoming(charged=None)` = the **ceiling**: *"affordability
  deliberately NOT charged — a hidden Ignition-class burst reaches a costly nuke in one turn."* It
  **assumes** they accelerate, so survival never under-prepares. Fail-closed toward *"assume I'm in
  danger."*
- **Board-clock is OPTIMISTIC.** `_opp_turns_to_ready`: *"card-effect accel is NOT modelled: that can
  only OVER-state t and UNDER-price the deny slot — the fail-closed direction."* It **assumes** they
  can't accelerate, so a speculative deny is never over-valued. Fail-closed toward *"assume they're
  slow."*

Merge them naïvely and one consumer gets the wrong conservatism (survival under-prepares, or every
deny looks urgent and wastes Hammers). **This is the whole reason they're two subsystems, not one.**

## The unification — one Threat Clock, policy as a parameter

Both are slices of a single function:

```
incoming(t, accel_policy) = worst W/R-adjusted damage the opponent's board deals my Active
                            at future turn t, under an assumed accel/evolve model over t turns
```

Everything derives from the curve:
- `active_doomed`   = `incoming(1, ceiling) >= my_hp`
- `turns_to_ready`  = `min{ t : incoming(t, policy) >= line's biggest-attack damage }`
- `turns_to_ko_me`  = `min{ t : incoming(t, policy) >= my_hp }`
- `deny_value`      = how far a strip shifts the curve **right** (Δt on `turns_to_ready`)

**The opposite-conservatism problem is already solved in the seed:** `reachable_incoming` takes the
accel policy as a **parameter** (`charged=None` = ceiling; `charged={base_attach, burst_on_evo}` =
budgeted). Survival passes the ceiling; deny passes the fail-closed-slow policy. Same curve, different
argument — the conservatism stays selectable instead of hard-coded per subsystem.

## Why now / the built bridge

- **`reachable_incoming` is already `incoming(t=1, policy)`** — ADR-0064's "Incoming that counts one
  development step." The combine is: **generalize `t=1` → `t=N`** (walk the accel/evolve model forward
  N turns) and make `_opp_turns_to_ready` a **query that inverts the curve** (first t crossing the
  armed threshold) instead of a separate energy-deficit calc.
- **ADR-0045 already names the "Threat Clock"** as the multi-turn model — today a *complement*, not a
  *replacement*. This handoff proposes promoting it to the replacement.
- **`discard_energy_recur` (built 2026-07-22) is a shared input to the accel policy** — a
  discard-refueler (Mega Lucario ex, Archaludon ex) is *both* more dangerous (higher `incoming`) *and*
  faster (lower `turns_to_ready`). With two subsystems you wire it twice; with one clock, once. This is
  itself an argument for merging, and it's the pending consumer of that tag.

## Blockers (why it's a project, not a refactor)

1. **Cost** — a full curve is costlier than a one-step worst-case; consumers that only want the boolean
   still pay for the curve. Memoize per decision (like `_opp_attack_context` is stashed once/turn).
2. **The two conservatisms must stay selectable** — the policy parameter is load-bearing, not cosmetic;
   don't collapse it.
3. **Time-vs-damage inversion** — `turns_to_ready` answers a *time* question by inverting the *damage*
   curve; get the armed-threshold definition right (biggest-attack cost payable, not lethality).
4. **Suite bars** — 18 doom call sites + the deny slot ride this; shadow-first, hold the discard corpus
   12/12 and the full suite, fresh Pilot per replay (standing cautions).

## Recommended first step

Extract `incoming(t, policy)` as a pure function generalizing `reachable_incoming` (t as a param,
memoized), re-express `active_doomed` and `_opp_turns_to_ready` as two queries against it **behind a
shadow** (emit both old + new, assert byte-identical on the corpus), then swap per the seam-D pattern.
Thread `discard_energy_recur` into the accel policy as the first net-new behavior once the shadow is
clean.
