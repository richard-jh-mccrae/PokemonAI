# ADR-0084 — Deny's derived clock is a **tiebreak**, not a deadline, and never a **gate**

**Status:** Accepted (grilled 2026-07-30, `/grill-with-docs` on Issue #217 — eight locked decisions,
one of them a mid-grill **reversal of a decision already accepted**). **Build = Issue #217.**
Retires `_DENIAL_BENCH` from the armed fire rung in favour of
[ADR-0071](0071-bench-survival-is-a-shared-budget-harvest-and-the-clock-accumulates.md) decision 6's promotion gate.
**Does NOT supersede [ADR-0062](0062-energy-denial-is-what-the-strip-actually-takes-away.md)** — its
`/2**t` grade and its `_DENIAL_BENCH` derivation both survive, the latter on the OFF path only.
Does not reopen [ADR-0080](0080-deny-is-a-categorical-relevance-instrument-not-a-magnitude-one.md)
decision 1.

⚠️ **Number claimed 2026-07-30 while `docs/adr/README.md` read "Next free number: 0083."** That
pointer is **stale**: Issue #188's ADR already claims 0083 after renumbering off 0082 (tracker
Issue #136 records it as the sixth collision in five days). This ADR deliberately skips to **0084**
to avoid a seventh, and the README's pointer is corrected in the same change. Cite the issue
alongside the number.

**Context issues:** Issue #217 (this grill), Issue #187 (S4-deny, whose build surfaced this and whose
ruling 2 is refined here), Issue #199 (S3c, which shipped `deny_strip_delta` and Deny Relevance
compute-only), Issue #136 (the Value System tracker, whose build rules 1 and 11 decide the arming),
Issue #188 / Issue #189 (snipe and gust — verified out of scope), ADR-0062 (the denial oracle),
ADR-0071 (the promotion gate), ADR-0072 (the Discrimination Gate), ADR-0078 (the withdrawn currency
plan, whose Amendment B rules the Δ instantaneous), ADR-0080 (deny as a relevance instrument).

## Context

Issue #187 left deny expressing **timing** three different ways across its three surfaces, none of
them derived:

| surface | timing term | provenance |
|---|---|---|
| (a) keep price | `/2**t` halving, `t = turns_to_afford` | ADR-0062 / `needs.deny_slot` |
| (b) fire rung | `_DENIAL_BENCH = 0.25` flat area weight | ADR-0062, from the f29 bound `< 30/70` |
| (c) target pick | none | ruled out 2026-07-30 (Issue #187 ruling 2) |

The charter proposed collapsing all three into one derived clock, on the reading that
`combat._promotion_open` (ADR-0071 decision 6) already refutes `_DENIAL_BENCH`'s stated premise —
retreat-then-attack is legal in ONE turn (`docs/rules.md` §2 puts retreat in the any-order action
phase, §3 makes attack the separate turn-ending step, both `[ENGINE-LEGAL]`), so *a benched attacker
owes Energy, never tempo*.

**The proposal is answered NO.** The clock is sound for exactly one narrow job. Getting there took
two go/no-go gates and four further measurements, three of which returned negatives.

## The gates (probe: `tools/train/probes/deny_gate217.py`, commit `809c6d5`)

Both run armed (`deny_relevance` + `deny_strip_delta` forced ON), live `_opp_switch_enabler()`,
21 Hammer-ruled corpus frames.

**Gate 1 — does the boolean promotion gate reproduce f21/f29? PASS.** Zero sign changes; boolean and
incumbent miss the same 6 rulings.

| frame | ruled | promotion gate | incumbent (`0.25`) | boolean |
|---|---|---|---|---|
| f21 | HOLD | **shut** | −1.25 HOLD | **0.00 HOLD** |
| f29 | HOLD | **shut** | −1.25 HOLD | **0.00 HOLD** |
| f15 | PLAY | open | +55.00 PLAY | +55.00 PLAY |

**The charter predicted this would FAIL on a board fact that is false.** It reasoned that an Active
able to pay its retreat cost makes the benched Dragapult ex count fully. On f21/f29 their Active is
card **176 holding 0 Energy against a printed retreat cost of 2**, and `_opp_switch_enabler()` reads
**False** live. Both legs shut, so bench weight is **0.0** — stricter than 0.25, not looser.

This does not contradict `pilot.py:6155`'s comment (*"measured: ms f21 flips to playing the Hammer"*).
That records dropping the discount, i.e. weight → 1.0, which reproduces as **+25.00 PLAY**. The gate
is 0.0 **or** 1.0 and resolves to 0.0 here. Both readings are now measured and they agree.

**Gate 2 — does the clock separate the imminence pair on imminence alone? PASS on the anchors.**
`min(clock | PLAY) = 0.267 > max(clock | HOLD) = 0.150`.

| frame | raw denial | ruled | `strip_shift` |
|---|---|---|---|
| f15 | 30 | PLAY | **8** |
| f21 / f29 | 70 | HOLD | **0** (every body) |

That is precisely the inversion ADR-0062 recorded as impossible for magnitude — *"no monotone pricing
of magnitude alone can separate them"* — produced with no constant. **Recorded honestly:** across the
whole ruled corpus the clock is NOT separable (`0.000` vs `0.900`), driven entirely by six frames the
incumbent misses identically (`82748422-26`, `83053965-28`, `83455356-11`, `83664340-24`,
`85046350-32`, `86091435-68`), already ruled onto other layers by `deny_gate1.py`.

**Charter correction.** Gate 2's text names **f12** but cites f15's numbers. f12 is ADR-0062's
`_DENIAL_FORWARD` lower bound (`> 0.154`), not an imminence anchor. The pair is **f29 vs f15**.

## Decisions

### 1. `/2**t` SURVIVES. A clock DELTA may never be substituted for a clock READING.

A reading is a *when* (`turns_to_afford = 1` → armed next turn) and is what `/2**t` discounts. A delta
is a *how much* (`strip_shift = after − base` → this strip buys N turns) — a **payoff** on the turn
scale, not a date. Measured, they disagree in both directions:

| frame | body | `t_afford` → `/2**t` | `strip_shift` |
|---|---|---|---|
| f21/f29 | bench0 | 1 → **0.5** | **0** |
| f15 | active0 | 1 → **0.5** | **8** |
| f26 | active0 | 0 → **1.0** | **0** |

Substituting the payoff for the deadline would import deny's VALUE into the keep price — the scale
crossing ADR-0080 decision 1 found underivable, and explicitly out of Issue #217's scope. Recorded in
`src/common/CONTEXT.md` under **The Two Clocks**.

### 2. The target pick gains a LEXICOGRAPHIC strip-Δ tiebreak. Issue #187 ruling 2 is REFINED, not confirmed.

Relevance stays the sole ranker; `strip_shift` orders only options already **exactly** tied. Measured
over 319 frames carrying opponent-target rows:

- **47** frames offer ≥2 nonzero-relevance options — a real choice exists
- **28 of 47 (60%)** have a **tied** argmax, today resolved by engine option order
- **22** of those tie ACROSS bodies (the tiebreak can act; **11** have differing `strip_shift`, gaps to `[0, 8]`)
- **6** tie WITHIN one body, where `strip_shift` is identical by construction — correctly inert (see decision 3)

A tie resolved by engine ordering is the exact defect ADR-0062 named for the scoring case: *"the argmax
fell through to index 0 and we stripped whatever Energy happened to land first."* At target-pick time
the card is already spent, so the cost is sunk and maximising **payoff** is the right objective — which
is why `strip_shift` is legitimate here for the same reason it is illegitimate on the keep price. A
lexicographic key leaves the value scale untouched, so ADR-0080 decision 1 stays closed.

Ruling 2 is **refined**: it correctly dropped `_DENIAL_BENCH`'s *area weight* from this surface, and
that stands. Its broader "no timing at all" reading does not.

### 3. NEGATIVE RESULT — the Δ policy stays `energies[:-1]`. Which Energy you remove never matters.

Across **109 corpus bodies holding ≥2 Energies**, which Energy is removed changes `turns_to_ko_me` in
**0 cases**, with **0** false negatives for the shipped policy. So a per-removed-Energy-TYPE
generalisation — which `_DENY_CHARGED`'s typed framing implies, and which decision 2's per-option
tiebreak would appear to want — is **measurably inert** while raising cost from 2 to `1 + Ntypes`
`turns_to_ko_me` simulations per body per decision. `_strip_delta_terms` is unchanged: one Energy, the
last-attached, both legs under `_DENY_CHARGED`, instantaneous per ADR-0078 Amendment B.

This also settles decision 2's 6 within-body ties: they are unbreakable by strip Δ not through a policy
shortcut but because the clock genuinely does not discriminate there.

The policy is **empirically** rather than **provably** safe, and this ADR is the record of that
distinction: if a board ever appears where a body holds one critical and one surplus Energy and sets
the clock, re-run this measurement rather than re-deriving the question cold.

### 4. WITHDRAWN — the bite gate's fail direction.

Accepted mid-grill (fail-OPEN on absence, fail-CLOSED on a measured zero, distinguishing *"we know it
does nothing"* from *"we don't know"*), then made moot by decision 7. Recorded because the reasoning
survives for any future gate on this seam, and because the emitter's *"Fail-closed everywhere"* claim
at `pilot.py:3785` was found to predate a gate whose input can be absent as distinct from zero.

### 5. `_DENIAL_BENCH` retires from the ARMED fire rung, in favour of `combat._promotion_open`.

`pilot.py:6163`'s `(1.0 if r["area"] == "active" else _DENIAL_BENCH)` becomes area-active **or**
promotion-open → `1.0`, else `0.0`. The constant survives at its two OFF-path sites (`pilot.py:4976`,
`pilot.py:5083`) per tracker build rule 11, so ADR-0062's derivation is not deleted and the
OFF-vs-ARMED diff stays available.

**The reason is architectural, not numerical.** The codebase currently holds **two contradictory
models of promotion**: `combat._promotion_open` says benching costs Energy and not tempo, derived from
`docs/rules.md`; `_DENIAL_BENCH` says it costs a 4× tempo discount, derived from two frames. Every
future deny change would have to pick one. Retiring the constant leaves one model, already consumed by
`incoming`, already tested.

**Gate 1 proved SIGN, not RANK — and that gap is a build requirement, not a footnote.** Where the gate
is open and a bench body is relevant, the rung's magnitude inflates hard: f79 `55.00 → 95.00`, f26
`16.25 → 95.00`, f24 `17.50 → 100.00`. No sign flipped, but that rung competes in tiering against every
other option. So this retirement is gated on a full `decide()` retest of the 12 Hammer-bearing frames
plus `leaf_lab diff` against `data/leaf_lab/baseline.json` with zero unruled `OK → MISS` flips, run
**before** the arming decision (ADR-0072 decision 5). If the retest finds a reordering, the honest
outcome is that `_DENIAL_BENCH` was load-bearing for rank though gate 1 cleared it for sign, and the
retirement does not ship.

### 6. Issue #217 ARMS `deny_relevance` and `deny_strip_delta`.

Both ship OFF (`runtime.py:169`, `:178`), and every decision here lives inside the
`if self.deny_relevance:` branch — so shipping them dark would change nothing. Tracker build rule 1 is
explicit that a kill-switch *ships ON*; rule 11 records that Issue #199 shipped this very read
compute-only with 18 green tests and no consumer, and *"wiring it in Issue #187 immediately exposed three
defects the pure tests could not reach."* Adding five more unexercised decisions to that path defers
the discovery of their defects to whoever arms the switch, with a larger blast radius.

Battery, in order — corpus `decide()` retest → Discrimination Gate → `gauntlet_ab.py --overlay` at
n=200/arm/directed, requiring `crashes == 0` and `ci_lo >= −5 pp`. The flag-overlay instrument is
correct rather than `gauntlet_swap_ab.py`, because rule 11 keeps the OFF path live, making the arming
purely additive.

**This converts Issue #217 from the risk-free simplification its charter advertises into a live
behaviour change.** The pre-registered fallback, if any gate fails, is to ship the decisions behind the
OFF switch and hand arming forward — taken as a retreat, not as a plan.

### 7. REVERSAL — the keep-price bite gate is DROPPED. A delta may never gate.

Decision 1 originally carried a second half: gate the keep price on `strip_shift > 0`, recommended and
**accepted** as a narrow fix that would *"stop pricing strips that do nothing."* The measurement then
refuted it:

```
rows with relevance > 0: 218
  of those, strip_shift <= 0 -> BITE GATE WOULD SUPPRESS: 128   (59%)
  of those suppressed, relevance is ABILITY-leg only:        5
```

**The recommendation was made on a claim of narrowness that had not been measured, and it was wrong by
a factor of the majority of the corpus.** Recorded as a reversal rather than rewritten, because a
measurement overturning an already-accepted decision mid-grill is the load-bearing part of the record.

`strip_shift > 0` reads as *"the strip does something"* but only measures *"the strip delays MY death
by a whole turn or more"* — strictly narrower, in three named ways:

1. **Ability mutes** — the charter's own case, confirmed: 5 suppressed rows, all card **112**,
   relevance entirely from the ability leg (`abil 0.171`, `atk 0.0`). An Ability mute is not damage.
2. **Integer coarseness** — `turns_to_ko_me` is a whole-turn worst-case count; a real sub-turn setback
   reads exactly 0.
3. **Self-referential framing** — it asks whether *my* death is delayed, and is blind to a strip that
   wrecks their plan without touching their clock against me.

Decision 4's fail-open rule does not rescue this: all 128 are **measured** zeros, so fail-closed
applies to every one by design. Nor could the gate be validated — ADR-0080 records the corpus holds
exactly **one** keep-side anchor, pricing 0 under both instruments, so no evidence exists that could
confirm or refute a 59% keep-side re-pricing.

`_strip_delta_terms` is therefore **revived with exactly one consumer** — decision 2's tiebreak — which
satisfies Issue #217's acceptance criterion (*"revived with a consumer, or retired"*). Relevance remains
the sole keep-side gate, exactly as shipped. This is item 5 of the charter's agenda answered: the clock
cannot see what relevance sees, which is why **relevance must stay the value read**.

### 8. `_DENY_RELEVANCE_K`'s identity is PRESERVED; its evidence is re-anchored.

`K = _DENY_RELEVANCE_NORM = MAX_ATTACK_DAMAGE = 350.0` (`deny_relevance.py:101`), derived as the largest
attack damage in the set. Decision 5 changes an **area weight**, which multiplies outside the
normalizer, so K is untouched by construction and there is no free parameter to re-derive.

What decision 5 does break is the **witness**. `pilot.py:148` anchors the identity on *"f21/f29's
benched Dragapult ex prices −1.25 on both."* Under the boolean gate the bench weight is 0, so
`value == 0` and the rung takes its whiff branch (`if not value: return 0.0`) — **0.00, not −1.25**.
Same decision, different number, stale proof. The comment is rewritten to cite f12 (`+55.0` vs
`+22.50`) and f26 (`+16.25` vs `+1.25`), recording f21/f29 as routed to the whiff branch under the gate,
still HOLD.

Build requirement: **assert that no tier or comparator distinguishes `0.00` from a small negative.** The
governing rule is that tier 4 needs `score <= 0`, which `0.0` satisfies — but it must be asserted, not
assumed.

**Knowingly left open.** The whiff branch returns `0.0` where ADR-0062's own reasoning implies a bad
strip should price negative (`_DENIAL_ITEM_COST` exists precisely so *"the strip must beat the hold"*).
Fixing that changes every zero-value frame, predates this issue, and is handed forward. If the
`0.00`-vs-`−1.25` assertion finds any tier that does distinguish them, that fix becomes forced.

## Consequences

- **The charter's central proposal is refuted.** `/2**t` and `_DENIAL_BENCH` are NOT collapsed into one
  derived term. Issue #217's title is wrong and its "not blocking anything / correct as shipped"
  framing is superseded by decision 6.
- **Net simplification is real but smaller than chartered:** one constant retired from the live path,
  one hand-set timing term kept on a type argument, one tiebreak added, three negative results recorded.
- **Three measurements are now on the record as reusable negatives** — the 109-body Δ-policy
  equivalence, the 128/218 bite-gate suppression, and gate 2's whole-corpus non-separation. Each names
  the probe and the sample size so the next grill re-runs rather than re-derives.
- **`tools/train/probes/deny_gate217.py` was the harness** for all of it, alongside `deny_gate1.py`.
  Both were **deleted by Issue #243 / ADR-0089 (2026-07-31)**: their questions are answered and
  recorded here and in ADR-0080, they were short 40 corpus records apiece, `deny_gate217` selected
  six hardcoded `(episode, frame)` literals, and both force flags that still ship OFF — so what they
  measured was not the shipped agent. The measurements above keep their standing; re-derive from
  this ADR's description rather than editing a stale harness.
- **Issue #188 / Issue #189 unaffected.** Verified deny-scoped: `gust_target_slot` carries no timing
  grade of its own because its two-term marginal already embeds timing through `turns_to_ko_me`, so
  ADR-0076 decision 3 does not route this away from a deny issue. `discard_recur_fuel` on
  `turns_to_afford` (Issue #204) is untouched — decision 1 keeps `turns_to_afford` on deny's path, so
  nothing is silently absorbed.
- **A process finding worth keeping:** the grill accepted a decision, then measured it, then reversed
  it. Both the acceptance and the reversal are recorded. The general lesson is narrower than "measure
  first" — it is that **a gate's input must be checked against the predicate it stands in for, not
  merely against the frames the gate was invented to fix.**

## Amendment A (2026-07-30) — the armed read never applied ADR-0080's mandated forward discount

**Found while building decision 6, by investigating the one Discrimination Gate flip this work caused.
A defect in Issue #187's build, not in this one.**

[ADR-0080](0080-deny-is-a-categorical-relevance-instrument-not-a-magnitude-one.md) decision 2 is
explicit about the forward-potential leg: *"Riolu carries Mega Lucario ex; Solrock carries nothing.
This makes `_DENIAL_FORWARD = 0.5` **central**, reversing ADR-0078's re-audit which had it slated for
deletion"*, and in its consequences, *"`_DENIAL_FORWARD` is **promoted rather than deleted**."*

**It was never applied to the relevance read.** Its only consumer was `_denial_at` — the **OFF** path.
`strip_relevance`'s affordability gate was a pure energy-COUNT test (`total_attached >= total_cost`)
with no `is_forward` branch, so a forward form's attack entered the reading at full damage. The armed
instrument therefore priced a forward threat at **double** the incumbent for the life of Issue #187's
build.

**The witness, ruled by the user 2026-07-30 (*"82225643-11 rationale is correct"*).** ms 82225643 f11
is turn 2. The target is a Basic Riolu holding one `{F}`; Mega Lucario ex's Aura Jab (`{F}`, 130) was
credited in full, firing a Hammer at `55.0` over the Pokégear 3.0 dig the corpus rules correct — and
their hand holds no Mega Lucario ex, so that attack cannot land this turn or next.

| reading | before | after | OFF reference |
|---|---|---|---|
| f12 affordable (`relevance_fire`) | 130 | **65** | **65** — parity to the cent |
| f11 fire-rung score | `+55.0` | **`+22.5`** | `+22.5` |
| f12 banked (`relevance`) | 270 | 135 | — (deliberately higher) |

**Fix.** `strip_relevance` splits its setback by source and combines them as
`max(own, forward_discount x forward)` — byte-for-byte the shape `_denial_at` uses — for both the
banked and the affordable readings. `forward_setback` stays RAW for diagnosis. `forward_discount` is
**keyword-only with NO default**: a permissive default is exactly how this went wrong, so omitting it
now fails loudly at the call instead of silently crediting in full.

A **discount, never a deletion** — ADR-0063 derived the bound from two frames and its lower leg is ms
82225643 f12, which must still PLAY the Hammer off a banked `{F}`. Excluding forward attacks from the
affordable reading outright was considered and rejected for exactly that reason.

Pinned by `REQ-DENYREL-0035`, which asserts the two instruments AGREEING on one board rather than
either number, so a re-derived `_DENIAL_FORWARD` carries both sides with it. It also asserts the banked
reading still exceeds the affordable one — the discount scales the forward credit without deleting the
banked doctrine. (A first draft of that test compared BANKED against OFF, read 135 vs 65, and looked
like a bug when both numbers were correct; the parity claim belongs on the affordable reading, which is
the one the fire rung consumes and the one `_denial_at` is the counterpart of.)

## Amendment B (2026-07-30) — decision 6 is NOT taken: the pre-registered ship-dark fallback was used

**Decision 6 chartered arming `deny_relevance` and `deny_strip_delta`. The Discrimination Gate blocked
it, so the fallback decision 6 pre-registered — *"ship the decisions behind the OFF switch and hand
arming forward"* — was taken. Arming is owed by Issue #228, Phase 1e's last item.**

This is recorded as a decision NOT taken rather than quietly dropped, because the reasoning for arming
(tracker directive 1: a kill-switch *ships ON*) is unchanged and still owed.

**What the gate reports, attributed across four configurations.** Every Issue #217 change was stashed
and re-run to isolate ownership:

| config | flips |
|---|---|
| clean tree, zero changes of mine | `84071010\|0\|decision\|15` |
| code changes only, flags OFF (**as shipped**) | `84071010\|0\|decision\|15` — *identical* |
| flags ON, incumbent `_DENIAL_BENCH` | `84071010`, `82225643\|1\|decision\|11` |
| flags ON, all changes | `84071010`, `82225643` — *identical to the row above* |

Three consequences follow, and only one of them is this issue's problem:

1. **`84071010|0|decision|15` is PRE-EXISTING and unrelated to deny.** It regresses on a clean tree.
   The baseline was captured at `e4c46ca` and main has since landed Issue #213's `scaled_threat_rank`
   (`fac85e2`). The baseline is a **ruling record** (`CLAUDE.md`: auto-recapture *"would make the gate
   vacuous"*), so this cannot be self-served — it needs a ruling and a re-capture by that change's
   owner. **As shipped, this work adds ZERO gate regressions.**
2. **Decisions 2 and 5 are gate-NEUTRAL.** Rows 3 and 4 are identical, so neither the tiebreak nor
   `_DENIAL_BENCH`'s retirement moves a single leaf frame. Decision 5's own precondition — the
   `decide()` retest — passed independently: **0 decision flips over 331 corpus frames**.
3. **`82225643|1|decision|11` survives the Amendment A fix**, and is a **LEAF** interaction in which
   every deny component is individually correct. Armed, the Hammer's keep price legitimately falls
   `5.0 -> 1.929` (`TAG_TIER["gust"] 10 x banked 0.386 / 2^1`) — exactly what ADR-0080 designed. A
   Hammer that is cheaper to HOLD makes PLAYING one cost less worth, so Hammer-play boards outrank the
   Pokégear dig in the leaf (`correct=63.0` vs `top=113.0`, rank 1 -> 3).

**Point 3 is why this issue stopped rather than pressing on.** The user ruled the corpus rationale
correct on that frame, so the outcome is wrong — but no deny component is wrong, which makes it a leaf
card-worth weighting question. Decision 1 leaves the keep price deliberately unchanged, and the leaf is
a different subsystem; "fixing" a correct component to move a leaf rank would be the wrong repair.

**Consequence for the shipped state.** Decisions 2, 5, 7 and 8 and Amendment A are all merged and
**inert** — every one lives inside `if self.deny_relevance:`. The nine tests covering them set the
flags explicitly, so they exercise the armed path without depending on the shipped value. Rule 11's
warning is now 4-for-4: Issue #187's arming exposed three defects its pure tests could not reach, and
Issue #217's exposed a fourth. Issue #228 should budget for a fifth.
