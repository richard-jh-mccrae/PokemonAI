# ADR-0099 — A whitelist entry is TYPED, names its fact, and (if provisional) names what retires it

**Status:** Accepted (grilled 2026-08-01, `/grill-with-docs` on Issue #259, wave-1 packet item 5).
**Build = Issue #259 (POC-T0).**
**Amends [ADR-0092](0092-the-value-system-poc-builds-by-differencing-tracks-with-wave-rulings.md) §6**
(the sound-rule whitelist, ratified here in amended form) and **enforces its own T0 double-counting
rule** against the whitelist as well as against the term families. Does **not** supersede anything.

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

- `keep-a-bench` **deleted** (ADR-0096 d2 — it is the spare-body cliff, and guards nothing the
  filter does not already guarantee at MAIN).
- the **empty-Bench filter** re-typed `provisional`, with the retirement test stated
  (ADR-0096 d1).
- **Set-Up never-bench** split onto its own `structural` line with its own reason — weak dominance
  from three source-checked facts (`pilot.py:1750`) — rather than bundled with the in-game guard.
- **`_finish_turn_last`** narrowed from "the sequencing tiers" to the named
  *information-before-commitment* boundary (ADR-0095 d2); a line saying only "the tiers are
  sound" is unfalsifiable, and was in fact false in the free band.
- **`POC_WORTH_PRIZE_RATE`** typed `authored-scaffold` and bound (ADR-0097).
- **apply-seam coverage floors** added, typed `authored-scaffold` (ADR-0098 d3).

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

## Amendment A — a fourth type: `composed-into-the-leaf` (ruled 2026-08-01, Issue #263)

Ruled by the developer after this ADR was accepted and while PR #266 was in flight, on the authority
of the *"Contract impact of the Issue #263 ordering ruling"* comment on Issue #259. Recorded here
rather than as a sibling ADR for the same reason as [ADR-0098](0098-apply-seam-parity-detect-localize-contain.md)'s
Amendment A: this ADR is introduced by the same unmerged PR.

**What moved.** With the composer's ordering now uniform 1-ply differencing, the four per-seam
equations — `attach_value` ([ADR-0069](0069-the-attach-marginal-is-an-axes-sum-and-the-decider-may-say-no.md)),
`evolve_value` ([ADR-0070](0070-the-evolve-marginal-is-a-body-substituted-delta-in-damage.md)),
`promote_retreat_value` ([ADR-0100](0100-the-promote-retreat-equation-is-the-sub-lethal-residual-in-damage.md), Issue #141 — it was ADR-0073 until PR #267 resolved a five-day-latent number collision)
and `deploy_value` ([ADR-0086](0086-the-deploy-marginal-prices-a-bench-slot-and-what-fills-it.md)) —
**stop being DECIDERS** for any option the enumerator covers. Their *math* stays ratified; their
*role* changes.

That leaves them in a gap the three existing types cannot express. They are not deleted. They are not
whitelisted as rules that survive the purge. They survive as **`state_value` term-family internals**
(Issue #262 composes readiness and development out of them) and optionally as pruning
approximations. So the vocabulary gains a fourth type, `composed-into-the-leaf`, and the four
equations are listed under it.

**The mandatory field is the destination.** By symmetry with `provisional` (must carry a dated
retirement test) and `authored-scaffold` (must carry a reconciliation), a `composed-into-the-leaf`
entry **must name the `state_value` term family that absorbs it** — `attach_value` → readiness,
`evolve_value` → readiness, `promote_retreat_value` → survival, `deploy_value` → development. Without
a named destination, "survives as an internal" is indistinguishable from "kept out of sentiment", and
the next track deletes it. `validate()` rejects a composed entry with no destination, and rejects a
still-deciding entry that claims one — a `structural` rule naming a term family would be claiming to
be math it is not, and would thereby exempt itself from the one-guard-per-fact rule.

**The list now has two populations, and the double-guard detector runs over one of them.** A decider
*guards* a fact; a composed equation *prices* one. Folding both roles into a single coverage map
would report a rule and an equation as a double guard on the same fact, and a detector that cries
wolf is one nobody reads. `deciders()` and `composed()` partition the whitelist;
`undeclared_double_guarding()` reads the former.

**Why the exact string matters.** Issue #264's disposition table uses the same label, so
`composed-into-the-leaf` is asserted as a literal in the tests, not only through the constant. The
sharpest deletion hazard is `deploy_value`: ADR-0096 already deleted `keep-a-bench` off this list, so
a reader could reasonably conclude the whole Bench-pricing story was purged. It was not — the bench
slot priced as a scarce resource IS this equation, and it becomes development-family math.
