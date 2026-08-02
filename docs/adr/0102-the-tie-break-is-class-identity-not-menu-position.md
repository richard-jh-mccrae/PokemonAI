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
to the pre-Issue-#247 **rung**"*, and widening a leaf-named flag to govern the live policy's ordering would
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
permutation-invariant and agrees with menu position, so any fix to Issue #254 moves live ties; the
choice is only whether it moves them somewhere principled.

**5. `_greedy_grab` takes the same key, and the key is a FUNCTION.**
The multi-pick path had the identical defect (`max(..., key=(score, -j))`) and is reached by the same
re-run policy inside the rollout. It cannot consume `_score_order`'s list — it re-scores between picks
on a virtual board — so it takes the key, computed once from the original menu the loop never
permutes. Fixing only `_score_order` would have left the invariance true of single-picks and false of
grabs, which is the half-application `_option_equivalence`'s own docstring exists to prevent.

The ordering itself therefore lives in `Pilot._order_key`, not in a lambda at each site. The first
draft of this change wrote it twice and the two spellings had already diverged — the needy-Line leg
was in the sort and silently absent from the grab. Two spellings of one ordering is exactly how a key
added to one site fails to reach the other, which is the same drift argument decision 7 of ADR-0091
makes about the oracle itself.

**6. `class_asymmetry` gains a `1e-9` tolerance.**
See the measurement above. The bar sits eleven orders above the observed float noise and six below
the `0.001` the leaf's own values are rounded to, so nothing the leaf can express is swallowed. The
instrument that measures Issue #254 has to be able to say the word "zero".

## Amendment A — the shed predictor follows the decider (2026-08-02, Issue #261 item 2h)

Item 2h deletes the tuned `_DISCARD` ladder. As the discard DECIDER's fallback it was already dead —
`needs_keep_value` has decided that select since 2026-07-20 — but it was also the scoring basis of
the fetch doctrine's shed predictor (`_pitch_value_of` / `_shed_signals`), and through it of three
LIVE cost-netting rungs. Deleting it blind would have left every pitch score `0.0`, all three signals
permanently False, and the rungs reading them silent forever: Issue #238's shape, where 13 Corrections
were closed as `covered` by rungs a deletion pass had already removed.

**Ruled by the user, 2026-08-02: re-point the predictor onto the equation that decides.** The
predictor's own docstring had always stated the contract — *"scoring with the SAME rungs the real
discard select uses keeps prediction and pick agreeing"* — and that sentence had been false since the
day v2 shipped ON. So `_shed_signals` now prices the two cards the v2 assignment would actually shed,
and the sentence is true again.

Three seams were extracted rather than duplicated, each because two callers needed the same answer:

* **`needs.removal_score`** — the objective `cheapest_removal` minimises, named and made public. The
  decider picks the set that minimises it; the predictor asks what that set costs. Predicting with a
  different formula than the one that decides is the drift `_discard_equation_rows` was narrowed to
  prevent in the same commit.
* **`Pilot._apply_pitch_terms`** — the deadness derivation (`dead_opener`, `redundant_tutor`,
  `stranded`, `fodder`, `spent_burst`, `fuel`), now shared by both row builders. A card is dead
  weight or it is not.
* **`Pilot._as_discard_rows`** — the whole-hand rows re-read in DISCARD context. This one is a
  correction to a first attempt that wrote the pitch terms in `_needs_hand_rows` itself, which is
  wrong and measurably so: `_resolve_needs` withholds a card's general slot when its pitch term flags
  it dead, and its own comment already said why refresh rows must not carry one — *"a SHUFFLED burst
  IS a future attach, so they keep their general worth."* Enriching the builder made every refresh
  SHED read its hand as a discard, and the Lillie's big-hand pins plus two hyperclosure corpus frames
  caught it. A `cost_discard` fetch really does discard, so it asks for discard semantics explicitly.

The three bands are now one number — what the shed costs — with `ACE_SPEC_TIER` as the key bar, the
lowest tier the retired `keep-key-cards-at-discard` (−30) protected, reused rather than re-invented so
no new constant enters the fit. The junk band additionally requires each shed card to be dead or
REPLACEABLE, because v2 prices a redundant spare and a role-less singleton identically at keep 0 while
only the first is a card we still effectively have.

**Measured cost, and the one thing it did move.** Suite green (4419). Decision Gate **PASS**, and the
agree rate goes UP — `249/345 -> 251/345`, four FIX and one NEUTRAL — so the ladder was costing
agreement, not buying it. Discrimination Gate **RED on two frames**, `85045840|0|decision|10` and
`|12`, both `OK -> MISS`, rank 1 -> 2. Dissected rather than ruled here:

* The **shipped decision is unchanged on both** and already matches the human — measured on the
  pre-change tree as well, so this is not a fix and must not be reported as one. What moved is the
  leaf's RANKING of the human's option.
* Cause, located: the re-pointed bands now price the Ultra Ball's forced discard at `4.5` — it would
  shed the held Boss's Orders — so `dont-shed-a-live-card` fires and the greedy continuation inside
  the sim DECLINES the fetch. The human's line therefore develops less on the simmed end board
  (12.5 -> 0.0) while the Ultra-Ball-first line is unaffected (10.025), because `_engine_leaf_value`
  forces its first step and cannot decline anything.
* The decline is consonant with the human's own rationale on that very frame — *"save boss's orders
  for a time when it is actually valuable."*
* The candidate fix, had the ruling gone the other way, was named and deliberately NOT applied: the
  `live` band is mapped to `cost > 0`, where v1's was *"a keep FLOOR fires"* — a card the doctrine
  actively protects, not any card with any worth. That is a category difference in the translation,
  but every replacement bar is a number, and picking one against two frames is the rung-fitting
  ADR-0092 exists to delete. It went to the wave-2 packet instead of into the commit.

**RULED: ACCEPT (user, 2026-08-02)** — *"the decline agrees with that frame's own rationale."* Both
frames carry a non-voiding `fixed` ruling in `data/corrections/reviewed.json` (the correction STANDS
and keeps gating; what was accepted is the leaf ranking), and `data/leaf_lab/baseline.json` is
re-captured against it at `f47a3ef` through `guarded_capture` — which would have refused the write
had either frame been unruled (ADR-0094). Both gates PASS.

**What the deletion proved.** Every `_DISCARD` ladder case committed as a corpus ruling —
`test_discard_selection.py`'s four, `test_fetch_doctrine.py`'s three, and the burst-Energy blunder pin
— is reproduced by the keep-value equation with the ladder gone. Those tests now grade the DECISION
rather than the rung name, which is what the blunders were about, and the ladder is shown redundant
rather than assumed so. One fixture had to be corrected, not the code: the key-band test benched no
base for its Mega, so v2 correctly read that wincon as STRANDED — unplayable this game, therefore not
a key card — a distinction the flat −30 rung could not make.

## Consequences

* The develop rollout explores isomorphic lines identically. `fan_out` stays — it is still the right
  reading, and it now has nothing to correct on the measured corpus, which is the outcome that proves
  the cause was located rather than papered over.
* One Decision-Gate REGRESSION, taken to the wave-2 packet and **ruled there**:
  `86089120|0|decision|14`, `[1] -> [3]`, human `[1]`. Both are *Attach a Basic Energy onto Dreepy* —
  `{P}` (option 1) versus `{R}` (option 3) — scoring **exactly** 16.5, so the pick was riding on menu
  position and happened to land on the human's card. It was filed as a located gap in the attach
  decider (`attack_axis = max(this_turn, build)` collapsing the `this_turn` 10.0 that `{P}`'s
  `{P}`-cost *Petty Grudge* earns), and the **user ruled that reading wrong**: *"attaching either F or
  P energy to Dreepy should be equal value when it has no energy"* — the Dragapult line needs both
  (`{R}{P}` Phantom Dive), the Active is bare, and Petty Grudge's 10 on turn 2 is not what either
  attach is for. So the equation's tie is CORRECT and the correction's `correct=[1]` names one of an
  indistinguishable-by-value pair.

  Recorded as a **`transposition`** (ADR-0088 decision 6) in `data/corrections/reviewed.json`: the
  ruling STANDS on its own rationale — *"Gusting up their main attacker only helps them"*, i.e. attach
  rather than play Boss's Orders — but no agent can be scored on picking between the two attaches.
  Both gates PASS with it voided. Note it is NOT an Option-Equivalence class (ADR-0091 fingerprints
  differ — distinct card ids), so `satisfies_human` cannot absorb it and the disposition is the only
  mechanism that fits; this is the first `transposition` entry since ADR-0091 retired the last one.
  Issue #292, which carried the rejected reading, is closed `not_planned` with the ruling on it.
* **Runtime cost, measured** (2026-08-02, 300 corpus frames / 2193 options / mean 7.3 per frame):
  fingerprinting costs **0.031 ms per decision**, ~3% of the ~0.95 ms whole-Board build
  `test_leaf_profile.py` uses as its reference. It runs on every live decision AND every rollout
  step, unflagged, so the number is recorded rather than assumed — the same "measure before
  asserting" correction `decider-gate-main.yml` had to make about its own runtime objection.
* Cost: two call sites re-keyed, one helper added to `option_equivalence`, one instrument tolerance,
  and two committed tests that were pinning the old positional tie-break rewritten onto what they were
  actually about (`test_pilot.py`'s off-Damage-select baseline, `test_tuner_retest.py`'s
  state-exactness guard).
* Not addressed, by design: `planner.py`'s line-shaped `_commit_best` candidates, which ADR-0091
  decision 6 also left alone and for the same reason — an equivalence over multi-step *lines* is a
  strictly larger claim with no corpus evidence behind it. T4's enumerator inherits the fingerprint
  ordering; that is where the larger claim gets its evidence.
