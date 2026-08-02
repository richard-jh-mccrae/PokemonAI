# ADR-0102 — An exact tie breaks on class identity, not on menu position

**Status:** Accepted; BUILT 2026-08-02 (Issue #261 POC-T2 item 2e, old Issue #254).
**Reverses the rejection recorded in
[ADR-0091](0091-indistinguishable-options-are-one-decision.md) decision 5** (*"make the rollout
order-invariant … open-ended … Filed as Issue #254"*) — not by taking the option that ADR rejected,
but by finding a cheaper one it had not considered. Extends ADR-0091's fingerprint to a fourth
consumer. Does not supersede anything.

**Context issues:** Issue #254 (the filed root cause), Issue #247 / ADR-0091 (the oracle and the
symptom fix this completes), Issue #178 (the reproducibility rule the develop rung's authority rests
on), Issue #261 (POC-T2, the track this item belongs to).

## Context

ADR-0091 measured the leaf pricing **one decision two ways**: on `81903490|0|decision|49` three
byte-identical Riolu scored `1167.0 / 95.4 / 95.4`, reproducibly, across fresh Pilots. It fixed the
*reading* — `fan_out` gives every class member the class maximum, sound by isomorphism — and named
the cause it was not fixing:

> `_engine_leaf_value`'s within-turn rollout is greedy and index-order dependent, so it reaches a KO
> continuation from bench 0 and misses the isomorphic one from bench 1.

It rejected fixing that cause as open-ended, reading it as a **search** problem: *"invariance means
exhausting the branch or canonicalising states inside the search — `transposition_probe.py`'s
territory, and that probe exists precisely because nobody has established the search can afford it."*

That reading is wrong, and the measurement is what shows it. The rollout does not search: it steps
one greedy line, re-running the Pilot's own policy on each intermediate SearchState
(`_simulate_line`'s `dec = self._evaluate(odict)`). So its order-dependence is not the search's — it
is **the policy's**, one line of it:

```python
by_score = sorted(range(len(options)),
                  key=lambda i: (traces[i].score, traces[i].attach_to_needy_line), reverse=True)
```

A stable sort with no third key falls through to the menu index, and the menu index is the one thing
about an option that is **not a board fact**. Two isomorphic boards present menus that are
permutations of each other, so the same exact tie resolves toward a different body on each — and from
there the two lines diverge for good. Nothing has to be exhausted to fix that; the tie has to stop
being positional.

### Measured at the build (2026-08-02, on the committed corpus — not recalled)

```
Leaf Lab CLASS ASYMMETRY      5 classes  ->  0        (worst spread 2097.25 -> none)
  81903490|0|decision|49  [8, 9, 10]   spread 1144.50   gone
  81903490|0|decision|49  [2, 3, 4]    spread 1071.60   gone
  82749168|1|decision|29  [4,5,12,13]  spread 2097.25   gone
  81906755|1|decision|93  [3, 4]       spread    9.72   gone
  86090164|1|turn|6       [18, 22]     spread    3.42   gone
Discrimination Gate           PASS, 0 frames moved
leaf SOLE-top                 38/248 -> 39/248     shared-top  182/248 -> 183/248
Decision Gate                 1 REGRESSION, 1 NEUTRAL, 2 FIX (the 2 FIX pre-date this item)
suite                         4440 green
```

The one class that still appears in the raw values is `82749168|1|decision|29` at
`124.83000000000001 / 124.82999999999998` — a spread of `2.8e-14`, which is float non-associativity
in a sum whose terms arrive in a different order per option, not the leaf pricing one decision two
ways. `class_asymmetry` gained a `1e-9` tolerance so the instrument can report **clean**; a finding
that can never go away is one readers learn to skip.

## Decisions

**1. The third sort key is the option's Option-Equivalence fingerprint (ADR-0091), and the index is
demoted below it.**
`(-score, not needy_line_attach, fingerprint, index)`. The fingerprint is a pure function of the
board, so permuting the menu permutes the keys with it and invents no new ones. The index still
decides — but only between options that key **equal**, which means either the same decision (ADR-0091
says picking one is picking the other) or unfingerprintable (below).

**2. An unfingerprintable option keys `""` and keeps its menu position.**
Blind ⇒ conservative, structurally — the same rule `option_fingerprint` already keeps for a face-down
DECK reference. A stable sort preserves menu order among equal keys, and the *relative* order of
those options is itself permutation-invariant: nothing about which bench slot holds what reorders the
deck. Rejected — **synthesising a key from the option's index or type**: that is a canonical identity
asserted from ignorance, which is the design ADR-0091 rejected at the oracle and would be no better
here.

**3. Unconditional — no kill-switch, and `leaf_option_equivalence` keeps its own narrower contract.**
Three reasons, in order. It **deletes an inconsistency** rather than adding a value term, which is the
same ground ADR-0091 decision 9 shipped its own flag ON rather than armed-off. `_prefer_soonest_arming_evolve`
is the exact precedent one layer up — an index-tie fix in this very sort, shipped unflagged. And
ADR-0092's POC doctrine has no room for an OFF branch that nothing verifies. Reusing
`leaf_option_equivalence` was considered and rejected: its stated contract is *"OFF = byte-identical
to the pre-#247 **rung**"*, and widening a leaf-named flag to govern the live policy's ordering would
make the name a lie and the rollback a different, larger thing than it says.

**4. The canonical key applies to the LIVE policy, not only inside the sim.**
Gating it on `self._planning` would have moved zero corpus frames, and that is precisely the argument
against it: the develop rung's whole authority to OVERRIDE the tuned scoring is that its end-board is
what *this agent* would actually reach. A policy that breaks ties one way live and another way in its
own simulation is simulating a different agent — the rung/instrument drift that rotted the decider
sweeps (`decider_lab.py`'s module docstring), re-created inside one Pilot. It would also load a second
meaning onto `_planning`, whose one fact is *"never nest a search"* (ADR-0096, one guard per fact).

**Consequence, accepted and stated rather than hidden:** which of several EXACTLY tied options gets
picked changes in live play too. It has to. There is no total order over options that is both
permutation-invariant and agrees with menu position, so any fix to #254 moves live ties; the choice
is only whether it moves them somewhere principled.

**5. `_greedy_grab` takes the same key.**
The multi-pick path had the identical defect (`max(..., key=(score, -j))`) and is reached by the same
re-run policy inside the rollout. It cannot consume `_score_order`'s list — it re-scores between picks
on a virtual board — so it takes the key, computed once from the original menu the loop never
permutes. Fixing only `_score_order` would have left the invariance true of single-picks and false of
grabs, which is the half-application `_option_equivalence`'s own docstring exists to prevent.

**6. `class_asymmetry` gains a `1e-9` tolerance.**
See the measurement above. The bar sits eleven orders above the observed float noise and six below
the `0.001` the leaf's own values are rounded to, so nothing the leaf can express is swallowed. The
instrument that measures #254 has to be able to say the word "zero".

## Consequences

* The develop rollout explores isomorphic lines identically. `fan_out` stays — it is still the right
  reading, and it now has nothing to correct on the measured corpus, which is the outcome that proves
  the cause was located rather than papered over.
* One Decision-Gate REGRESSION, wave-2 material: `86089120|0|decision|14`, `[1] -> [3]`, human `[1]`.
  Both are *Attach a Basic Energy onto Dreepy* — `{P}` (option 1) versus `{R}` (option 3) — scoring
  **exactly** 16.5, so the pick was riding on menu position and happened to land on the human's card.
  The attach decider's own working shows it sees the difference and then discards it:
  `this_turn` is `10.0` for `{P}` (it arms Dreepy's `{P}`-cost *Petty Grudge* NOW) and `0.0` for
  `{R}`, but `attack_axis` takes `max(this_turn, build)` and `build` is `12.5` for both, so both
  marginals come out `15.5`. That is a located gap in a shipped FIRING equation (ADR-0069), not in
  this ordering, and repairing it here would mean re-composing an attach axis that prices every attach
  frame. Filed and held out onto its own owner.
* Cost: two call sites re-keyed, one helper added to `option_equivalence`, one instrument tolerance,
  and two committed tests that were pinning the old positional tie-break rewritten onto what they were
  actually about (`test_pilot.py`'s off-Damage-select baseline, `test_tuner_retest.py`'s
  state-exactness guard).
* Not addressed, by design: `planner.py`'s line-shaped `_commit_best` candidates, which ADR-0091
  decision 6 also left alone and for the same reason — an equivalence over multi-step *lines* is a
  strictly larger claim with no corpus evidence behind it. T4's enumerator inherits the fingerprint
  ordering; that is where the larger claim gets its evidence.
