# ADR-TEMP-228 — A categorical instrument's ZERO must still pay the keep price: a whiff that TIES is not a hold

**Status:** Proposed (grilling 2026-07-31, `/grill-with-docs` on Issue #228). **Corrects
[ADR-0084](0084-denys-derived-clock-is-a-tiebreak-not-a-deadline-and-never-a-gate.md) Amendment B
point 3**, whose diagnosis of the blocking frame is measurably wrong. Build = Issue #228.

**Context issues:** Issue #228 (this grill — arm the deny instrument, Phase 1e's last item),
Issue #217 / ADR-0084 (the arming attempt that was blocked, and the Amendment this corrects),
Issue #187 / ADR-0080 (deny as a categorical relevance instrument), ADR-0062 (the incumbent denial
oracle the armed path replaces), ADR-0072 (the two mid-build merit gates), ADR-0091 / Issue #247
(the Option Equivalence oracle whose baseline re-capture invalidated every measurement in the issue
body), Issue #136 (the Value System tracker and its directive 1).

## Context

`deny_relevance` and `deny_strip_delta` ship **OFF**, in violation of tracker directive 1 (*"a
kill-switch may exist only as an emergency revert lever and ships ON"*). Issue #217 chartered the
arming; the Discrimination Gate blocked it; the pre-registered ship-dark fallback was taken and
arming was handed to Issue #228.

### Every measurement in Issue #228's body is stale

The issue records main at `f1c7c53` and the leaf baseline at `ac5b5b9`. Since then **ADR-0087**
(Issue #241, the Corpus Reader — corpus 332 → 372), **ADR-0089**/**ADR-0090** (Issue #250, the
Ruling Locator) and **ADR-0091** (Issue #247, Option Equivalence) all landed, and ADR-0091
re-captured **both** gate baselines at `a8da62d`. Re-measured on `375789d` against that baseline,
`python tools/train/leaf_lab.py diff --baseline data/leaf_lab/baseline.json`, 268 frames:

```
deny OFF     GATE: PASS   0 unruled, 0 ruled, 0 voided, held out 0
deny ARMED   GATE: FAIL   2 unruled
  REGRESSED 82225643|1|decision|11   OK -> MISS   rank 1 -> 3
  REGRESSED 83686860|1|decision|13   OK -> MISS   rank 1 -> 2
  IMPROVED  82224509|1|decision|67   MISS -> OK
```

Four of the issue's claims do not survive this. The OFF arm's held-out frame
(`86091435|0|decision|35`, owner Issue #165) is **absorbed by the re-capture** and no longer
reported. `83686860|1|decision|13` is **new** and appears in no prior measurement. The claim that
*"the delta between the two runs is exactly one frame"* is false — three gate verdicts move. And
there is an **IMPROVED** frame, which the issue records no possibility of.

### The three movements are ONE mechanism, and it is not the leaf

Every moved option moves by **exactly 50.0**. Reproduced offline on all three frames, wrapping
`Pilot._leaf_value` and `Pilot._predicted_loss` and dumping every kwarg in both flag states:
`prizes`, `readiness`, `value`, `line` and `_predicted_loss` are **bit-identical** OFF vs ARMED on
every moved option. Only `active_survives` flips, toggling `_PLANNER_SURVIVAL_W = 50.0`
(`src/common/strategy/planner.py:48`, applied at `:3148`).

The leaf reads nothing deny-related. The coupling is `_simulate_line`'s greedy in-turn continuation
— the same channel ADR-0072 finding 2 identified and ADR-0070 amendment H corroborated, now
confirmed a third time. The upstream term is `Pilot._denial_play_tactical`
(`src/common/pilot.py:5602`):

| frame | OFF — `opp_denial_best` | ARMED — `deny_relevance_best` |
|---|---|---|
| `83686860-13` | **−5.0** = 0.5 × 1.0 × **10.0** − 10 | **0.0** |
| `82225643-11` | **+22.5** = 0.5 × 1.0 × **65.0** − 10 | **0.0** |
| `82224509-67` | **+74.5** = 0.5 × 1.0 × **169.0** − 10 | **0.0** |

`board.deny_relevance_best` is 0.0 on all three boards, so the armed rung always takes its whiff
branch. The Hammer decision flips inside the rollout, one Energy moves on the opponent's board,
`_incoming_worst` crosses my Active's HP, and the survival term toggles.

**ADR-0084 Amendment B point 3 is therefore wrong.** It attributes this frame to the keep price
falling `5.0 -> 1.929` and concludes *"every deny component is individually correct."* The keep
price is a different surface (`needs.deny_slot`) and is not what moves the leaf; the mover is a rung
returning `0.0` where the incumbent returns a signed magnitude.

## Decision 1 — a blocking frame is DIAGNOSED before it is adjudicated

Issue #228's scope item 1 asked which of three rulings to apply to `82225643|1|decision|11`. **No
ruling is made on any of the three frames until the mechanism behind them is fixed and the gate
re-run.** Three frames moving by one constant, driven by one rung returning one wrong number, is a
defect signature, not three independent judgement calls.

This is ADR-0072 decision 5's own precedent applied a second time: the six inherited flips were put
in front of the user as individual rulings and turned out to be **one defect** (a bare-body evolve
priced at exactly 0.0, unreachable because `_finish_turn_last` only sequences options above zero).
Ruling them one at a time would have recorded six exceptions and fixed nothing. The shape here is
close enough to be uncomfortable — it is *again* a rung returning exactly 0.0 and *again*
`_finish_turn_last`'s zero boundary.

**The `IMPROVED` frame does not count as merit.** On `82224509|1|decision|67` the armed instrument
*declines* a 169-damage strip the incumbent takes; that demotes a rival option and the human's
`correct` wins by default. Counting it as upside would count a defect as a benefit.

## Decision 2 — the armed whiff must DECLINE strictly, not return 0.0

`_denial_play_tactical` (`src/common/pilot.py:5602-5606`) short-circuits before the keep price:

```python
value = (_DENY_RELEVANCE_K * board.deny_relevance_best if self.deny_relevance
         else board.opp_denial_best)
if not value:
    return 0.0                                  # nothing to deny — hold it (whiff)
...
return coin_odds(ctx.card_id) * weight * value - _DENIAL_ITEM_COST
```

The docstring states the contract: *"A whiff … prices at 0 and is held; `_finish_turn_last` tiers a
free Item ahead of everything, so declining one **REQUIRES a non-positive score**."* `0.0` is
non-positive and the contract still fails, because `_finish_turn_last` sequences early only on
`score > 0` (`pilot.py:1855`) — so a 0.0 Item lands in tier 4 **tied with End**, and stable score
order breaks the tie by option index. Measured directly on `83686860-13`, rollout steps 0–2
identical, step 3 divergent:

```
flags False   step3 chose [3] = End                       (Hammer scored -5.0)
flags True    step3 chose [0] = PLAY Crushing Hammer       (Hammer scored  0.0)
              step4 DISCARD_ENERGY -> opp Active energyIndex 0
```

**Ruled: the early return is deleted, so a whiff prices `−_DENIAL_ITEM_COST` and declines strictly.**
`0.5 × 1.0 × 0 − 10 = −10.0` is what the formula already says; the guard was suppressing its own
answer. A test pins whiff < End.

**Why this was invisible until arming.** The guard is on both paths, but reachable only when `value`
is exactly 0. The ADR-0062 magnitude is rarely exactly 0 while a Hammer is playable; a **categorical
[0,1] relevance scalar is 0 routinely and by design**. So the OFF path's decline was strict *by
accident of its arithmetic*, and the armed path inherited a contract its own value shape breaks.
That is the general lesson worth the ADR: **when a magnitude instrument is replaced by a categorical
one, every "is it zero" branch changes frequency class**, and any behaviour that rested on zero
being rare becomes a live defect.

Tracker build rule 11 — *"a compute-only layer is not a verified layer"* — is now **5-for-5**.
Issue #187's arming exposed three defects its pure tests could not reach, Issue #217's exposed a
fourth (the missing forward discount, ADR-0084 Amendment A), and this is the fifth.

## Open — not yet ruled

- **Is `deny_relevance_best == 0.0` correct on these boards?** The incumbent oracle reads 65.0 and
  169.0 of denial on two of them. Either relevance is correctly categorical-zero and the oracle is
  pricing something relevance deliberately ignores, or relevance is **blind**. ADR-0084 decision 8
  records the same shape on f21/f29 (`combat._promotion_open` shuts → `deny_relevance_best` 0 →
  whiff at 0.00) and ruled it *"same decision, different number"* — here it moves three frames.
  Under investigation; **decision 2 does not depend on the answer**.
- **Does arming also owe the DELETION of the OFF magnitude path?** Directive 1's *"Rungs an equation
  replaces are DELETED, not suppressed"* and the `snipe_relevance` precedent (ADR-0085 Amendment E)
  say yes; Issue #228's scope item 3 says the OFF path stays live. Held open, because on all three
  measured frames the OFF path is currently the **correct** one — deleting it now would delete the
  better behaviour.
