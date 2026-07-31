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

`board.deny_relevance_best` reads 0.0 **mid-sim** on all three boards, so the armed rung takes its
whiff branch there. The Hammer decision flips inside the rollout, one Energy moves on the opponent's
board, `_incoming_worst` crosses my Active's HP, and the survival term toggles.

**At the ROOT board the armed read is correct and agrees with the incumbent to the cent** —
`_DENY_RELEVANCE_K × deny_relevance_best == opp_denial_best`, the identity
`K = _DENY_RELEVANCE_NORM = MAX_ATTACK_DAMAGE` exists to guarantee (`pilot.py:160-180`):

| frame | `opp_denial_best` | armed `deny_relevance_best` | `K ×` | fire rung, BOTH arms |
|---|---|---|---|---|
| `83686860-13` | 10.0 | 0.0285714 | **10.0** | −5.00 (hold) |
| `82225643-11` | 65.0 | 0.1857143 | **65.0** | +22.50 (play) |
| `82224509-67` | 130.0 | 0.3714286 | **130.0** | +74.50 (play) |

So the instrument is not wrong. The **169.0** first attributed to the oracle on `82224509-67` is
Lever A's unfavored weight, `_DENIAL_PLAY_W × (1.0 + _DENIAL_UNFAVORED) × 130.0 = 1.3 × 130.0`
(`pilot.py:5606`; measured `favorability=0.2733`, `matchup_coverage=1.0`). Card facts verified in
`data/EN_Card_Data.csv`, including the single-hop **Riolu (677) → Mega Lucario ex (678)** line
(Aura Jab `{F}` 130 / Mega Brave `{F}{F}` 270). On `82224509-67` the human ruled the Hammer play
**correct** — *"opponents active is their main attacker with an energy on it, thats a huge threat.
use crushing hammer."* Armed, mid-sim, the agent declines it.

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

## Decision 2 — an ABSENT armed read must never be readable as a MEASURED ZERO

⚠️ **This decision replaces an earlier, wrong Decision 2** (*"the armed whiff must decline
strictly"*), committed at `f0124de` before the root cause was found. That repair — early-return
deleted so a whiff prices `−_DENIAL_ITEM_COST` — would have made the armed rollout **always hold**
the Hammer, where the incumbent correctly plays it at +22.50 and +74.50. It is the opposite error,
and it would have looked like a fix because the three gate frames would have moved. Recorded rather
than silently overwritten, because a plausible repair that moves the gate the right way for the
wrong reason is the exact failure this ADR's Decision 1 exists to prevent.

**The root defect.** `_opponent_target_rows` returns `None` mid-sim, by design and by docstring
(`src/common/pilot.py:8093-8095`):

```
None when sparse: mid-sim (`self._planning`), no live my Active, or no opponent in-play bodies.
```
```python
if getattr(self, "_planning", False):
    return None
```

`_planning` is the never-nest-a-search reentrancy guard (`planner.py:473`), set for every rollout
step and by `leaf_lab.board_leaf_values`. So mid-sim the cache is `None`, `pilot.py:6816`'s
`and self._opponent_target_cache is not None` fails, and `board.deny_relevance_best` keeps its
dataclass default — `deny_relevance_best: float = 0.0` (`pilot.py:508`). The fire rung reads that
default as a measured zero and whiffs.

**The OFF path has no equivalent hole:** `opp_denial_best` is computed unconditionally at
`pilot.py:6753`, with no `_planning` guard. So arming does not replace one value with another
mid-sim — it replaces a value with *nothing*, and nothing is spelt `0.0`.

**Ruled: absence is typed as absence.** `deny_relevance_best` becomes `float | None`, and every
consumer distinguishes "measured zero" from "not measured". This is ADR-0084 decision 4's own rule —
*"a value of `None` means **absent, not zero**"*, already quoted in `_deny_strip_shift_map` — applied
to the one field that could not express it.

**The codebase already defends this failure mode on the sibling surfaces.** `_deny_rows`, verbatim:

> *"Falls back to a fresh compute for a hand-built `board` that never went through `_board()`;
> without it an armed hand-built board would emit NO deny slots and **read as a whiff, which is a
> silent behaviour change rather than a fail-closed one**."*

Three deny surfaces. The two target-pick maps carry that cache-or-compute ladder. The fire rung does
not, and it is the one that moved three gate frames. Note the ladder alone would **not** fix this:
its fallback calls `_opponent_target_rows`, which returns `None` mid-sim for the same reason — it
rescues hand-built test boards, not rollouts.

## Decision 3 — the armed read goes LIVE mid-sim, with a pre-registered cost fallback

The agent must not evaluate a policy differently inside its own rollout than outside it. That split
is the third confirmed source of continuation collateral in this repo (ADR-0072 finding 2, ADR-0070
amendment H, and now this), and failing closed to the incumbent would make it permanent and
load-bearing.

**Ruled: drop the `_planning` early return for the deny read.** `_opponent_target_rows` calls only
`combat.turns_to_ko_me` (the closed-form S1 curve) and `combat.prize_value` — it starts no nested
engine search — so the guard is a **cost** decision (`pilot.py:8001`: *"no shadow work in
rollouts"*), not a correctness one.

**The cost is UNMEASURED and the fallback is pre-registered, not discovered.** N+1
`turns_to_ko_me` per board per sim step, on the hottest path in the codebase; memoising on board
identity is the first lever. **If a Discrimination Gate arm exceeds ~2× its current ~20 minutes,
Decision 3 falls back to fail-closed-to-the-incumbent** (`None` → `opp_denial_best`), and the split
policy is accepted with that cost recorded. Pre-registering the fallback follows ADR-0084's own
ship-dark idiom: the escape is chosen before the number is known, so it cannot be chosen *because*
of the number.

**Falsifiable prediction.** With the absence fixed, the armed fire rung returns −5.00 / +22.50 /
+74.50 mid-sim — identical to the incumbent — so all three frames stop moving and the
Discrimination Gate passes armed. If it does not, Decision 2's diagnosis is incomplete and the
adjudication reopens.

## Decision 4 — a genuine whiff still ties End, and that is a SEPARATE defect

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

**Ruled: the early return is deleted, so a genuine whiff prices `−_DENIAL_ITEM_COST` and declines
strictly.** `0.5 × 1.0 × 0 − 10 = −10.0` is what the formula already says; the guard was suppressing
its own answer. A test pins whiff < End.

⚠️ **This fix must land only alongside Decisions 2 and 3, never instead of them.** Applied on its
own it makes the armed rollout hold the Hammer on every board where the read is merely *absent* —
including the two where the human ruled the play correct — and it would move all three gate frames
while doing so. A repair that greens the gate by suppressing a value it never measured is worse than
the defect: the gate would then certify the split policy rather than catch it. Decision 4 is
correct only once absence and measurement are distinguishable, which is Decision 2's job.

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

## Settled by measurement — relevance is NOT blind

The open question in this ADR's first draft — *"is relevance correctly zero, or blind?"* — is
answered **neither**. Armed, the read is 0.0286 / 0.1857 / 0.3714 and `K ×` it reproduces the
incumbent exactly (table above). The 0.0 was the **unarmed** reading all along.

`combat._promotion_open` is **not** what shuts, either. It is consulted only for bench rows
(`pilot.py:6849-6850` weights `area == "active"` at 1.0 unconditionally) and the argmax row is the
opponent's **Active** on all three frames. ADR-0084 decision 8's f21/f29 note describes a board
whose only energized body is *benched*; that shape does not occur here.

Ground truth, verified at source, agrees with the armed read on every frame: `83686860-13` strips
Snover's only `{W}` (retreat 3, CSV line 1255) and delays the Abomasnow line exactly one attach-turn
— honestly small at 10.0; `82225643-11` is ADR-0062's own `_DENIAL_FORWARD` anchor; `82224509-67`
buys exactly one turn against a lethal Mega Brave 270 into our 200 remaining HP.

## Open — not yet ruled

- **Does arming also owe the DELETION of the OFF magnitude path?** Directive 1's *"Rungs an equation
  replaces are DELETED, not suppressed"* and the `snipe_relevance` precedent (ADR-0085 Amendment E)
  say yes; Issue #228's scope item 3 says the OFF path stays live. Held open pending Decision 3's
  cost measurement: if the pre-registered fallback is taken, `opp_denial_best` becomes the armed
  path's own mid-sim value and **cannot** be deleted, so the two questions are coupled.
