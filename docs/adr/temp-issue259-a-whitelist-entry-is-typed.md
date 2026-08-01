# ADR-TEMP-259f — A whitelist entry is TYPED, names its fact, and (if provisional) names what retires it

**Status:** Accepted (grilled 2026-08-01, `/grill-with-docs` on Issue #259, wave-1 packet item 5).
**Build = Issue #259 (POC-T0).**
**Amends [ADR-0092](0092-the-value-system-poc-builds-by-differencing-tracks-with-wave-rulings.md) §6**
(the sound-rule whitelist, ratified here in amended form) and **enforces its own T0 double-counting
rule** against the whitelist as well as against the term families. Does **not** supersede anything.

⚠️ **Temp-named, not numbered.** Real number assigned at `/open-pr` rebase time. Cite the issue.

**Context issues:** Issue #259 (this grill), Issue #231 (whose entry this grill split and re-typed).

## Context

ADR-0092 §6 drafted the whitelist as a flat prose list: "rules that SURVIVE the purge because they
encode game structure or fail-direction policy, not strategy hypotheses."

The flat shape failed on its first real test, in this grill. One board fact — **an empty Bench under
a knock-outable Active** — appeared on the list **three times, in three different shapes**:

```
_predicted_loss           -KO_SCORE terminal rung, CombatMath-gated   (planner.py:3154)
_empty_bench_forced       order filter, unconditional                 (pilot.py:1787)
keep-a-bench              +60 tuned weight, unscoped when()           (baseline_bench.py:26)
```

T0's headline rule is "every board fact enters through exactly ONE term family." The whitelist broke
it three ways, on the first fact anyone looked at, and the draft line
(`the empty-Bench forced deploy filter + keep-a-bench`) bundled a structural filter with a tuned
`assumed` hypothesis as if they were one object. Nothing about writing that line prompted the
question that would have caught it.

A whitelist whose entries carry no type cannot adjudicate the next overlap either, and this build
will produce more: six parallel tracks, each deleting rungs against a shared list.

## Decision

**1. Every entry is TYPED. Untyped entries are rejected by the registry.**

| tag | meaning | mandatory field |
|---|---|---|
| `structural` | permanent — encodes a game rule or a fail-direction policy | the rule or policy it encodes |
| `provisional` | a substrate-gap workaround, not a permanent truth | **a dated retirement test** |
| `authored-scaffold` | a constant, not a rule | **a reconciliation note + a post-POC fitting queue entry** |

**2. Every entry names the board fact it guards.** This makes T0's double-counting rule checkable
*against the whitelist itself*, not only against the `state_value` term families — which is where
the failure above actually lived.

**3. §6 is ratified as amended by this grill**, not as drafted. Four lines changed:

- `keep-a-bench` **deleted** (ADR-TEMP-259c d2 — it is the spare-body cliff, and guards nothing the
  filter does not already guarantee at MAIN).
- the **empty-Bench filter** re-typed `provisional`, with the retirement test stated
  (ADR-TEMP-259c d1).
- **Set-Up never-bench** split onto its own `structural` line with its own reason — weak dominance
  from three source-checked facts (`pilot.py:1750`) — rather than bundled with the in-game guard.
- **`_finish_turn_last`** narrowed from "the sequencing tiers" to the named
  *information-before-commitment* boundary (ADR-TEMP-259b d2); a line saying only "the tiers are
  sound" is unfalsifiable, and was in fact false in the free band.
- **`POC_WORTH_PRIZE_RATE`** typed `authored-scaffold` and bound (ADR-TEMP-259d).
- **apply-seam coverage floors** added, typed `authored-scaffold` (ADR-TEMP-259e d3).

## Consequences

- The two dated obligations this grill created — the filter's retirement test and the rate's fitting
  — are now structurally visible on the registry rather than buried in ADR prose nobody re-reads.
  That is the point of the `provisional` tag existing at all.
- Expect the first typing pass to expose at least one further entry that cannot answer "which fact
  do you guard, and what retires you?" That is a finding, not a delay.
- Typing costs authoring effort per entry, at the one moment it is cheap.
- The alternative considered and rejected — deferring ratification to wave 2, after T1 measures the
  substrate — would block four parallel lanes on a measurement that has not started, because every
  track grades its flips against this list. T0 is the serial track precisely so this does not happen.
