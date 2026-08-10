# ADR-TEMP-507 — Every action is benefit minus opportunity cost

Status: Accepted and built for Issue #507.

## Context

The value system already had the right spine but not a total card-cost contract. ADR-0065 supplied
deck-role Worth; ADR-0127 made the hand a demand ledger; Item denial had a dedicated hold price; and
Composer differenced modeled boards. Gaps between those seams still let an unclaimed card disappear
for zero, let a reveal boundary carry an unchanged continuation as speculative benefit, and let
pre-attack board value survive after the defender was Knocked Out.

The governing equation is:

```
net(action) = realised benefit(action) - opportunity cost(consumed cards and allowances)
```

End Turn consumes nothing and is exactly zero. Every other known action consumes something finite.
If it realizes no benefit, its net value is strictly negative and End Turn wins.

Card actions pay through held-card Worth. `common.action_cost` closes the remaining non-card gap:
Attack and activated Ability spend an ordinal residual one decimal order above the shared score-noise
floor because no specialised magnitude owns their turn/allowance. It is deliberately too small to
overturn a measured benefit; it only makes a no-benefit action strictly worse than End. Manual Retreat
does not use that generic residual because its synthesized post-board, Energy resource premium, and a
strict cost for consuming the once-per-turn retreat allowance live in the promote/retreat equation.

## Decision

### Portable card Worth

`common.card_worth` owns shared function defaults. The same card therefore begins with the same
Worth in every deck:

| function | Worth |
|---|---:|
| Energy acceleration | 12 |
| search, tutor, dig, Bench fill, Item lock | 10 |
| draw or hand refresh | 8 |
| Energy denial | 6 |
| switch or stall | 5 |

Every known card also has a 5-Worth finiteness floor. Resolution is `max(shared function, declared
deck role, ACE/Energy fact, known-card floor, deck override)`. A deck override may raise this result,
never lower it. Unknown facts may still resolve to zero; that is refusal to claim value, not a free
action.

### One demand ledger, not manufactured demand

The ADR-0127 Needs ledger remains authoritative. Function tags do not create matching board demand:
that prototype inverted attach and strategy choices. Instead, each held row receives only the
residual needed to preserve its option floor:

```
latent residual = max(0, card floor - assignment marginal)
```

A live need therefore pays the card once through assignment coverage. A redundant or currently
unneeded card retains future option value. Spending either loses value; no-live-demand is no longer
equivalent to worthless.

The live Pilot and every Composer leaf use the same role/function resolver. ADR-0095's structural
information-before-commitment boundary remains: a conditional reveal's local trace may be zero because
Composer owns both its expected benefit and consumed-card cost, while the sequencer owns the contingent
ordering Composer cannot represent. That zero is a local no-claim, not the action's net value; only End
Turn has a deliberate terminal value of zero. The informative-zero fallback is limited to quota-free,
non-Supporter plays with no fired value rule or discard cost. An unmodelled Supporter cannot borrow that
fallback because it also consumes the once-per-turn Supporter allowance.

### The seven corpus mechanisms

1. **Setup before a terminal Knock Out.** The ordinary KO relief replaces future exposure to the
   defender with exposure after its worst honest promoter. A negative ordinary result is preserved
   unchanged: it exactly cancels survival value already banked by manipulating the Active that this
   attack removes. Only when ordinary relief is nonnegative may immediate posture relief from removing
   the current-form Active threat raise it: `ordinary if ordinary < 0 else max(ordinary, posture)`.
   The readings are never summed, and `attack_ev` weights the selected result by KO probability once.
   This preserves f59's wasted-Hammer cancellation; disruption against a survivor or promoter remains.
2. **Fetch targets and fetch plays.** TO_HAND choices read their hypothetical marginal from the same
   Needs resolution. A condition-locked target has zero realized fetch benefit this turn even though
   the card can retain future held Worth. Deterministic fetch PLAYs subtract the tutor and discard
   costs from delivered target value; conditional reveals leave their complete stochastic net to
   Composer. A positive fetch Supporter may replace End, or another Supporter only when its net benefit
   exceeds Composer's chosen first-step margin over the best *different-first-step* alternative;
   same-first-step continuations are not an opportunity cost.
3. **Hand refresh.** A non-positive refresh cannot precede an already available positive attack or
   End merely because its reveal continuation speculates about an unknown hand. Positive refreshes
   remain eligible.
4. **Clutch healing and Retreat.** The planner may compare heal → cheapest legal typed attach → Knock
   Out as one line, charging the heal, Energy, and attack efficiency and testing survival against the
   honest promoter. A manual Retreat separately pays its synthesized post-board loss, any Energy
   resource premium, and its once-per-turn allowance; a positive retreat may still win when it is the
   only route to a decisive attack. If a later reveal follows a root Retreat, Composer keeps the
   realized retreat leaf/cost but assigns that reveal no synthesized replacement-Active terminal EV:
   the promote/retreat equation and its decisive-attack guard already own that off-menu continuation.
5. **One-shot Energy.** `discard_eot` Energy may fund a legal current-turn attack or retreat, but it
   cannot bank standing retreat potential or spend the same transient supply on both axes.
6. **Concentrated Energy and a reachable pivot.** Readiness carries only the incremental payoff from a
   usable cheaper attack toward a stronger attack. Duplicate attackers saturate after the strongest
   copy, preventing simultaneous credit for mutually exclusive future attacks. A benched attach earns
   same-turn attack value only when a doomed Active has a legal Retreat on the root menu, and only for
   damage added over that body and the best other pivot; an already-lethal pivot earns zero attach
   benefit. This corrects the historical Mega Lucario f24 line by attaching to the benched attacker
   that can be promoted for the Knock Out. A positive persistent setup attach may likewise realize the
   expiring manual-attach allowance before a non-winning turn ender.
7. **Gust targeting.** Boss and other deferred targets use one shared evaluator for their complete
   reachable-turn value, preserving the immediate leaf and reachable continuation/terminal value as
   separate summands. Main-menu expansion, Candidate construction, and follow-up replanning consume
   that same result, so no layer ranks on the immediate per-body marginal alone or adds a continuation
   twice. One sound dominance gate closes f109: if the root already offers a deterministic one-prize
   Active Knock Out and the gust line's terminal EV does not exceed the best root attack terminal EV,
   the gust cannot bank transient target-swap leaf relief. The gate leaves f30's loaded-threat gust and
   f119's higher-payoff gust-and-spread line intact. It does not suppress real setup before that KO:
   on f109, Hilda adds a realized +0.2625 leaf and preserves Nebula's terminal EV, so live play chooses
   Hilda `[2]`; the old attack-only `[5]` index is stale, while Boss remains excluded.

## Consequences

All 21 Issue #507 Mega Starmie correction frames now replay correctly, including the cross-deck
terminal-KO controls. Tests pin shared cross-deck Worth, upward-only overrides, redundant-card option
cost, ordinal Attack/Ability and Retreat-allowance costs, positive and negative fetch/refresh
boundaries, condition-locked fetch targets, Supporter opportunity comparison, KO survival-relief
branching and f59's exact Hammer cancellation, clutch-heal lines, transient-Energy accounting,
concentrated/pivot attachment (including f24), and
deferred-target continuation without duplicate summands, replacement-Active terminal synthesis, or
f109's transient gust relief. The valid f109 Hilda setup and the f30/f119 gust lines remain positive
controls.

## Validation

The frozen validation artifacts were read, never captured or restamped.

- **Pilot target replay:** 21/21 targets pass.
- **Decision Gate:** 29 unruled, 20 held out, and 3 voided. The unruled count is unchanged from the
  pre-#507 gate, while 23 ruled corrections now report FIX.
- **Leaf diagnostic:** the stale corpus reports a 61/51/8 split after a +10/-7 frame shift, with 17
  improvements.

The nine target `OK -> MISS` leaf flips are expected because Leaf Lab grades the first step while
#507 assigns value to the complete line. They cover fetch, attach, refresh, heal sequencing, and
deferred-target continuations. Every negative first step among them has an asserted positive
continuation; no pure-cost action outranks End Turn's exact zero. Neither Decision Gate nor Leaf Lab's
baseline was changed.

This ADR amends historical descriptions of role-less Hammer, Budew, or informative Items as globally
worth zero. Those descriptions remain evidence of the former behavior, not current policy. It does
not replace structural legality, per-turn quotas, target equivalence, the Needs demand graph, or the
Composer's refusal rules.
