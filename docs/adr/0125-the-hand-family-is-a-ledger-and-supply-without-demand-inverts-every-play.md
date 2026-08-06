# ADR-0125: The `hand` family is a LEDGER — supply without demand inverts every card play

**Status.** Accepted (Issue #400 Phase 2, measured and built 2026-08-06). BUILT.

**Context issue.** Issue #400 (POC-T4), which blocks Issue #386 (T4/5, the arming swap). Found while
drilling why a reveal-terminated sequence never wins; briefly split out as Issue #431 and folded back
so the two halves ship in one PR.

## Context

`state_value`'s `hand` family prices what my hand COVERS: `assignment_coverage` (the slots held cards
can fill) + `re_access` (what the deck re-supplies) + `hand_worth` (the latent remainder), crossed
once at `POC_WORTH_PRIZE_RATE`. Nothing priced the position's DEMAND.

That is a half-ledger, and under differencing a half-ledger inverts every card play: spending a card
moves supply down and demand not at all, so the play reads as a loss.

**It was invisible for a second reason, and the two had to be found in that order.**
`planner._leaf_state_model` built the model with `needs=lambda: self._leaf_needs_resolution(end, ...)`
— a closure over the ROOT observation — and `StateModel.rebuilt` forwards `_origin`'s kwargs
verbatim. So every hypothetical board the composer synthesized read the **root** board's Needs
resolution, `_hand_legs` returned the same three numbers for every candidate in a whole
`composer.compose` call, and the family contributed exactly 0 to every delta. A fetch — whose entire
effect is on the hand — differenced to **exactly 0.0** on all 12 corpus frames where the human ruled
one, with `Expectation.best()` equal to `expected()` across five different fetched cards.
`rebuilt`'s docstring promises *"Fresh, never patched … staleness is impossible by construction"*:
true of the `state_value` memo, false of this kwarg.

Re-binding alone was measured **first**, and it is what exposed the ledger: agreement **82 → 64** of
270 MAIN ruled frames, with the breaks concentrated on one kind — `_ATTACH` 31, `_EVOLVE` 9 — and
`_ATTACH` picks collapsing 130 → 26 while `_ATTACK` exploded 65 → 143. The hold price switched on
and nothing paid it back.

**The mechanism, read off the Needs slots rather than reasoned about.** On `85045840|0|decision|10`
the ruled Energy attach moves the resolution from

```
6 slots  ... fund_attack active:unit0 (8.0), fund_attack active:unit1 (8.0)   coverage 58.128
```

to

```
4 slots  ... BOTH fund_attack slots gone                                       coverage 50.128
```

One Energy retires **two** slots — 16 Worth of demand — at a cost of 8 Worth of supply. The leaf
charged the 8 and credited nothing, scoring the attach at **−0.0667 prizes**. Across the 31 frames
where the human ruled an attach, the ruled play priced **negative on 31 of 31**, median −0.06442, and
`readiness` — the family that ought to carry the arrival — moved a median **+0.00056**, because it is
deliberately banded at `_READINESS_W` (*"readiness prices POTENTIAL, and the prize for actually
swinging belongs to `attack_ev`"*). The two families were pricing the same fact ~100× apart.

The module's own scaffold note already ruled the ordering this violated: *"a card in hand is worth
less than the attached unit it might become."*

## Decision

**1. `hand` gains a fourth leg, `slot_demand`, and becomes a signed ledger.**

```
hand = (assignment_coverage + re_access + hand_worth − slot_demand) × POC_WORTH_PRIZE_RATE
```

`slot_demand = Σ slot.value` over the same `needs.Resolution` the other three legs read. **No new
constant, no new currency, no new source of truth** — the demand was always in the Resolution and was
simply never read. It is a LEG rather than a seventh family on purpose: four readings of ONE supplier
belong behind one `does_not_read` contract, and splitting them would put one Resolution behind two.

The signed total means *"the latent Worth I hold, minus the need my hand and deck cannot meet"*, so a
position whose needs outrun its hand scores negative. The old `max(0.0, worth)` floor is DELETED —
it predates the demand leg and would flatten every unmet-need board onto one number, which is
`development`'s cliff exactly: a cost clipped at zero makes the need free again.

**2. Fuel slots are excluded from the demand half, because the supply half excludes them.**
`needs._keep_slot_dp` assigns over `supplied_by_pitch is False` slots only, so a fuel slot never
contributes to coverage; counting it as demand would credit its retirement against a supply that
never credited holding the fuel. One rule, both sides. Measured, the two spellings pick **identically
on all 270** MAIN ruled frames — so this is a coherence choice, not a scored one, and it is recorded
as such rather than presented as evidence.

**3. The `needs` supplier becomes BOARD-BOUND: `(obs, my_index) -> Resolution`.** `StateModel.build`
binds it to the observation it is building and `_origin` keeps the UNBOUND supplier, so `rebuilt`
re-binds against its own board automatically. The re-binding is a property of the type rather than of
every caller remembering — which is the whole reason the closure form failed. A resolved `Resolution`
passed directly is still taken verbatim and never called, so fixtures and any caller already holding
one are untouched.

**4. The 6 residual negatives are RECORDED, not tuned away.** After the fix the ruled attach reads
median **+0.01181** and stays negative on **6 of 31** — every one a PARTIAL funding, where the attach
does not retire the slot because a `needs` slot is present-or-absent and never fractional. That
residual belongs to `_resolve_needs`' slot granularity, one seam over, and is named here rather than
absorbed by a constant.

## Consequences

**Measured over the 270 MAIN single-pick corpus frames carrying a ruling, four arms paired per frame:**

| arm | agreement | `_ATTACH` picks | `_ATTACK` picks | `_PLAY` picks |
|---|---|---|---|---|
| human ruling | — | 81 | 45 | 94 |
| baseline | 82 | 130 | 65 | 10 |
| re-bind only (decision 3) | **64** | 26 | 143 | 16 |
| re-bind + ledger (**shipped**) | **86** | 97 | 98 | 9 |

```
re-bind only     vs base:  FIXED 25  BROKE 43  net -18   (BROKE: _ATTACH 31, _EVOLVE 9, _RETREAT 2, _PLAY 1)
re-bind + ledger vs base:  FIXED 13  BROKE  9  net  +4   (BROKE: _ATTACH 7, _EVOLVE 1, _PLAY 1)
ruled `_ATTACH` 1-ply delta:  negative on 31/31 (median -0.06442)  ->  negative on 6/31 (median +0.01181)
```

The 7 surviving `_ATTACH` breaks are the 6 partial fundings of decision 4 plus one; they are owed a
wave-3 ruling, not a constant.

**Both ADR-0072 gates are BYTE-IDENTICAL, verified by an asserted revert rather than assumed.** The
Discrimination Gate reads 70 REGRESSED / 12 IMPROVED / gated 197 / held out 67 / voided 3 / PASS with
the change and *character-for-character the same* without it; the Decision Gate reads
`agree 251/340 -> 255/343 (1 picks moved, 2 rulings moved, 31 voided)` / gated 0 / PASS on both sides.
The revert was asserted with `git diff HEAD --stat` before each control run, because a stash stack is
shared across worktrees and a "reverted" measurement can silently run its own diff.

**The reason the live agent does not move is already on the record** and is the third `blind_to` entry
of the `hand` family: on the develop rollout's simulated end board *my hand is hidden* (the engine's
end observation is opponent-perspective), so `_leaf_needs_resolution` returns None, the whole family
prices a real zero, and the new leg prices zero with it. The fix fires exactly where a REAL board is
scored — which is every call Issue #263's 1-ply ordering makes, and the composer is still DARK. That
is a fact to re-check the moment the composer is armed, not a permanent property.

**Cost: none measured.** Per-decision wall-clock over the same corpus, median 25.4 ms / max 1.38 s
against a baseline median 26.8 ms / max 2.03 s — inside run-to-run noise on a non-idle box, and the
Needs DP is lazy, so a candidate whose leaf never reaches the hand term still pays nothing.

**One shipped test changed its assertion, and the change is the point.**
`test_holding_a_useful_card_is_worth_something_but_less_than_playing_it_is` asserted the LEVEL
(`working["hand"] > 0.0`). Under a ledger a hand that exactly covers the position's only need nets to
zero deficit, so the level reads 0 while the sentence the test defends — the ADR-0097 sanity that
holding a useful card beats not holding it — is a claim about the MARGINAL, and it still holds at
+0.25 prizes. The test now takes that difference against an explicit counterfactual resolution. The
counterweight ADR-0097 exists for is intact and separately tested: a card that covers nothing and
retires nothing is still charged its latent Worth to play.

## What this does NOT do

- **It does not touch `POC_WORTH_PRIZE_RATE` or `_READINESS_W`.** The ~100× band gap between the two
  families remains, and the ledger makes it not matter for the attach case because supply and demand
  now cancel inside ONE family at ONE rate. Whether the two bands should be reconciled is a separate
  question and is not settled here.
- **It does not fix Issue #400 Phase 1** (a reveal-truncated sequence carrying `EV(terminal) = 0`).
  Measured on top of this, Phase 1 adds a further +1 agreement (86 → 87) and moves `_PLAY` 9 → 15.
- **It does not close the `_PLAY` gap.** 76 of the 92 frames where the composer misses a ruled
  `_PLAY` are seam REFUSALS, which no valuation ruling reaches; they are routed in Issue #400's body.

## Prior art

`state_value.hand`'s own docstring predicted the mechanism — *"under differencing the card leaves
`hand` and arrives in `readiness`/`development`, so the hold is the Worth this term loses"* — and the
scaffold note predicted the ordering it broke — *"a card in hand is worth less than the attached unit
it might become."* Neither was wired to a demand half, and nothing measured the consequence until the
composer differenced on real boards. ADR-0121 is the shape precedent: a mechanism whose structural
zero the beam then ranks on, dissolved rather than admitted. ADR-0119 is the precedent for a change
justified by what it MEASURED rather than by what it shipped.

*Positive control on the diagnosis, because it is what caught two blind probes.* Two corpus scans
reported `_hand_legs` unchanged on 125 reveal outcome classes and on 14 modelled non-revealing
`_PLAY`s — a silence indistinguishable from a broken instrument. A synthetic control (empty my hand
entirely, rebuild through the sanctioned seam) ALSO moved nothing, which is what proved the term was
not insensitive but disconnected, and pointed at the closure.
