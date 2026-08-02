# ADR-TEMP-261 — A free Item's HOLD price is the keep machinery, FLOORED; and the free band splits on information

**Status:** Accepted; **BUILT** 2026-08-02. Build = **Issue #261 (POC-T2) item 2f**, discharging old
Issue #212.

**Amends [ADR-0062](0062-energy-denial-is-what-the-strip-actually-takes-away.md)** (whose
`_DENIAL_ITEM_COST` is deleted, its value re-homed and its implied rate named) and
**[ADR-0078](0078-the-value-currencies-are-three-scales-bridged-by-derived-rates.md)** (whose
worth↔damage catalogue gains its first row as a real constant instead of a ratio between two that
never met in an expression). **Discharges [ADR-0095](0095-information-precedes-commitment.md)
decision 1**, whose sequencer change that ADR assigned to T2 and which no other T2 item owned; its
falsifiable prediction held. Does **not** supersede anything.

**Context issues:** Issue #261 (POC-T2, item 2f), Issue #212 (the structural half of the free-Item
hold, closed as superseded and restated by Issue #261), Issue #228 / ADR-0093 (which made a whiffing
free Item decline, and is the half Issue #261 says is *already discharged*), Issue #259 / ADR-0095
(the information boundary), Issue #259 / ADR-0097 (the Worth→prize scaffold this reconciles against),
Issue #262 (POC-T3, where the hold stops being a seam and becomes the `hand` term's difference).

## Context

Issue #261 item 2f re-scopes old Issue #212: *"ADR-0093 already made a whiffing free Item pay
`−_DENIAL_ITEM_COST` and DECLINE. What remains is the **generalization**: one hold price consumed by
every free-Item decider, not the deny-scoped constant. Re-scope, don't rebuild."* The POC plan says
how: *"generalize `_DENIAL_ITEM_COST` into the keep machinery."*

Two things were owed here, and Issue #212's own grill agenda put them in one question — *"Is the
right answer a price, or a sequencer change? Rule which layer owns the fix before pricing anything."*
ADR-0095 answered it: **both, and they are different layers.** The price is this ADR's decisions 1–3;
the sequencer is decision 4, which ADR-0095 already ruled and left to T2 to land.

### What the constant actually was

```python
_DENIAL_ITEM_COST = 10     # the value of KEEPING the Hammer. An Item is finite, and a free Item is
                           # tiered ahead of everything by `_finish_turn_last` — so a purely positive
                           # term could never decline one: any score above zero gets it played.
```

Every clause of that rationale is general and none of it is about Hammers. But its only consumer,
`_denial_play_tactical`, is gated shut for everything else (`if ctx.option_type != _PLAY or
"energy_denial" not in ctx.tags`), so *"an Item is finite"* was priced for Crushing / Enhanced Hammer
and for no other card in the pool. Every other free Item is declined, where it is declined at all, by
a hand-authored negative rung aimed at one card class — and the failure is silent, because the
sequencer's default for an unnoticed free Item is *play it*.

### Measured 2026-08-02, at source, not recalled

The obvious build — *"the hold price IS `needs.keep_v2`"* — was measured before it was written, on
the four committed deny anchors. `keep_v2` for the Crushing Hammer being played:

| frame | Hammer `keep_v2` | incumbent `_DENIAL_ITEM_COST` |
|---|---|---|
| `82225643-11` | **0.00** | 10 |
| `82224509-67` | 4.82 | 10 |
| `82749168-29` | 3.57 | 10 |
| `83968638-17` | **0.00** | 10 |

**Below the incumbent on every anchor, and exactly 0 on two.** The reason is structural, not a corpus
accident: a Crushing Hammer carries no `ROLE_TIER` and no `TAG_TIER` entry, so its ONLY slot is the
`deny` slot — `card_worth` says so in as many words (*"A role-less Hammer still prices its global
worth 0; only its live-strip DENY slot earns the band"*). That is the very slot the fire rung is
already pricing. So:

* on `83968638-17` the opponent has nothing worth stripping, the deny slot is worth ~nothing, and the
  assignment says keeping the Hammer is worth nothing — **on exactly the board where the strip
  whiffs**. A pure keep-machinery price would return 0, the rung would score `odds × w × 0 − 0` =
  **0.0**, and ADR-0093 decision 4's defect walks straight back in: `_finish_turn_last` promotes on
  `score > 0`, so a 0.0 free Item lands in the last tier TIED with End and stable score order plays
  it by option index;
* on `82225643-11` the strip does *not* whiff — but the hand holds **two** Hammers against one deny
  slot, so each solo-prices 0 (sets-not-sums, and correct as an assignment). The copy being spent
  looks free precisely when the hand is richest in it.

## Decision 1 — the hold price is the keep machinery FLOORED, and the floor is load-bearing

```
hold(card) = max( needs.keep_v2(card, over the whole hand), ITEM_HOLD_FLOOR ) × ITEM_HOLD_WORTH_RATE
```

Two facts, and the measurement above is why both are needed.

**The assignment leg** is the card's exact counterfactual marginal against the board's resolved
NEEDS — the same `_needs_hand_rows` → `_resolve_needs` → `needs.keep_v2` path the refresh SHED
(ADR-0101) and the discard decider (ADR-0065 WP-N4) already decide on. One keep question, one answer;
a second opinion about what a held card is worth is the drift ADR-0103 amendment A had to unwind on
the shed predictor.

**The floor** is the finiteness the assignment cannot see. A card spent is a card gone whatever the
assignment covers, and that is the half of ADR-0062's sentence — *"an Item is finite"* — that no
counterfactual over board needs can express.

**`max`, not `+`.** The floor is a LOWER BOUND on the card's worth, not a surcharge on top of it, so
a card whose live need already exceeds it is not charged twice. This is the ADR-0063 discipline
pointed at a cost, and it is the same shape `needs.keep_v2` already uses for its own `intrinsic`
hedge — a second hedge of that kind, not a new arithmetic.

**Consequence, stated precisely rather than over-claimed.** The swap is arithmetically identical for
deny **wherever the floor binds**, and the floor binds on every committed deny anchor — measured,
four of four, and every deny fixture in the suite prices the same before and after. It is *not*
identical **by construction**: `keep_v2` above the floor is reachable in principle (a Hammer covering
a second live `deny` slot), and if a board reaches it the Hammer costs more to spend than the
incumbent charged — which is the equation working rather than drifting, and is the whole point of
generalising. So Issue #212's scope note is met by MEASUREMENT over the ruled frames, not by
arithmetic identity. The corollary is what matters here: **no gate movement in this build is
attributable to the price**, which is what makes decision 4's movement attributable to decision 4.

## Decision 2 — the value is RE-HOMED, deliberately not re-derived

`ITEM_HOLD_FLOOR = 10.0` is `_DENIAL_ITEM_COST`'s number, in `common/hold_value.py`, whitelisted
under `sound_rules.firing-equation-constants` as the authored constant it is.

Issue #212 put re-deriving it explicitly out of scope (*"It is derived and its derivation is
re-confirmed as of ADR-0062 Amendment A"*), and keeping it is what makes the generalisation
behaviour-preserving where the corpus has already ruled. It is also exactly
`card_worth.TAG_TIER["gust"]` — the disruption-Trainer band — which is not noted as a coincidence but
as the reason decision 3's rate is 1.0.

**This is a net REDUCTION in authored scaffold, not an addition.** One constant hard-gated to one card
class becomes one floor under a board-derived equation that every free-Item decider can consume.

## Decision 3 — the implied worth↔damage rate is NAMED, seam-scoped, beside `DEPLOY_BAND`

`currency.py` catalogues three de-facto worth↔damage rates that disagree by ~6.7×, and its first row
read:

```
trainer   TAG_TIER["gust"] 10.0  vs  _DENIAL_ITEM_COST 10        ~1.0
```

That row described a ratio between two constants **that never met in an expression** — which is
precisely why nothing stopped it drifting. Deleting the constant forces the crossing into the open,
and the honest thing to do with it is name it: `currency.ITEM_HOLD_WORTH_RATE = 1.0` with
`item_hold_to_damage()`, on exactly the terms ADR-0086 amendment C set for the deploy band —
*"stated plainly rather than buried: it IS a worth↔damage rate, scoped to one seam"* — including its
reconciliation debt against a future general rate. `test_currency.py`'s worth-leg guard now reads the
shipped rate instead of a ratio, which is strictly stronger: the number it guards is the number the
agent multiplies by.

**Rejected: `state_value.POC_WORTH_PRIZE_RATE`.** It is the right long-run home — ADR-0097 is explicit
that under differencing *"the Worth does not cancel, on every play that spends a card"*, which is this
exact quantity — but it is `None`, T3 owns authoring it (Issue #262), and T2 cannot honestly price a
hold against a number that does not exist. Naming a seam-scoped rate now is what gives T3's authoring
note a concrete incumbent to reconcile against, which ADR-0097 decision 1 requires of it anyway.

**Rejected: adding the rate to `currency.py` as a fourth catalogue row without the floor.** The floor
is a policy about spending cards, not an exchange rate, and `currency.py`'s contract is conversions.
Hence the split: the equation and its authored floor live in `common/hold_value.py` (the
`deploy_value.py` pattern — pure, lib-free, the Pilot resolves the board facts), the crossing lives
where every crossing lives.

## Decision 4 — the free band splits on INFORMATION, not on cost (ADR-0095 decision 1, landed)

`_finish_turn_last` has always stated the doctrine as its own purpose — *"take the most informative,
reversible actions first and the irreversible ones last"* — while `_tier()` ended on a bare
`return 0`, so **every endorsed free `_PLAY` landed in one band** and score decided inside it:

```
Pokegear 3.0     free, INFORMATIVE   -> tier 0
Crushing Hammer  free, COMMITTING    -> tier 0     <- same band; score decides
```

Tier 0's own docstring says *"Free, and reveals a better target before you commit"*. A Hammer is free
and reveals nothing. The band now splits, and every later band shifts by one:

```
0 informative free · 1 committing free · 2 Supporter · 3 attach/cost_discard · 4 shuffle · 5 ender
```

**Why this item owns it.** ADR-0095's header assigns the sequencer change to T2; no item in Issue
#261's list names it; item 2f is T2's only free-Item item; and Issue #212's grill agenda item 1 asked
this exact question. Building the price and leaving the ordering would have left the ADR's obligation
homeless and its named prediction unmeasured.

**Why it cannot wait for T4.** Playing Pokégear before the Hammer versus after reaches the **same end
state**, so a planner that ranks a fixed sequence by `state_value(end)` is blind to it by
construction (ADR-0095 decision 3). It is on the whitelist as `information-before-commitment`,
`structural`, and this build is what makes that entry true rather than aspirational — the entry's own
note records that the old, broader line *"was in fact FALSE in the free band."*

**Classification, and its fail direction.** `Pilot._informative_card` keys off card FACTS, never
names: a `draw` / `search` / `dig` Function Tag, or the card being a Pokémon (a Bench fill, which
tier 0 has always listed). **Untagged defaults to COMMITTING**, per the ADR, and the asymmetry is
real — a mis-classified commitment sequencing early spends a card before the dig that would have
re-aimed it, while a mis-classified dig sequencing one band late costs nothing but ordering, because
the engine re-presents the menu either way.

**Scoped to `_PLAY`**, which is where ADR-0095 diagnosed the defect (*"every endorsed free `_PLAY`
lands in tier 0"*) and where its witness pair lives. An Evolve or an Ability spends no card at a
target; re-banding those is measurement this ADR did not do.

**ADR-0095's falsifiable prediction HELD.** `82225643|1|decision|11` — the standing disagreement the
ADR recorded as *"the falsifiable prediction this ADR leaves behind"* — now picks the human's `[0]`
(Pokégear) where it picked a Hammer, and it does so while the Hammer stays ENDORSED at +22.50. That
matters: the ruling ends *"Then, most likely, you'll also play Hammer and Ignition Energy in this
same turn"*, so a fix that suppressed the Hammer would have matched the pick and contradicted the
ruling. The dig is also the LOWEST-scoring endorsed option on that menu (Pokégear 20.0 < Hammer 22.50
< Ignition attach 51.4), which is why no weight could have expressed it.

## Measured at the build (2026-08-02, against the committed baselines)

Baselines first, on the unmodified tree, so every number below is a delta and not a reading:

```
BEFORE   Decision Gate        PASS   0 unruled, 2 held out (#262, #272), 1 voided
                              agree 249/345 -> 251/345
         Discrimination Gate  PASS   0 unruled, 2 held out (#262 x2), 0 voided

AFTER    Decision Gate        FAIL   1 unruled REGRESSION, 2 held out, 1 voided
                              agree 249/345 -> 251/345   (11 picks moved)
                              FIX (5): 82225643|1|decision|11 [3] -> [0]  (human [0])   <- ADR-0095's prediction
                                       + the four the baseline already fixed
         Discrimination Gate  PASS   0 unruled, the SAME 2 held out (#262 x2), 0 voided
                              agree 180/247 -> 179/247   (3 picks moved)
                              IMPROVED 82225643|1|decision|12  MISS -> OK
```

`_DENIAL_ITEM_COST`'s deletion moves **nothing**: every deny fixture in the suite prices identically,
by decision 1's construction. All movement is decision 4's, which is exactly the attribution
decision 1's floor was chosen to preserve.

### The one unruled REGRESSION goes to WAVE 2, un-self-ruled

```
REGRESSED 82225643|1|decision|12   [1] -> [0]   (human [1])
```

It is the **next frame of the same turn** as the prediction that held, and the two rulings interact:

* **f11** (`correct [0]`, Play Pokégear): *"This goes into the box of 'Collect information before
  committing'. Do PokeGear first. Then, most likely, you'll also play Hammer and Ignition Energy in
  this same turn."*
* **f12** (`correct [1]`, Play Crushing Hammer): *"Rioulu would not have died from this attack, and
  next turn he might evolve to opponents main attacker, mega lucario, thus playing the crushing
  hammers could have reduced its threat through energy removal."*

f12's live `chosen` was `[6]` — the **attack**. So the f12 ruling is adjudicating *Hammer vs attack*,
not *Hammer vs dig*; the agent now plays the Pokégear `[0]` still on that menu (the real episode
attached Ignition on f11, so both digs survive into f12), which is what f11's ruling asks for, and
the Hammer remains endorsed at +22.50 to be played later in the same turn.

**The two gates disagree about this frame, and the disagreement is legible rather than confusing.**
The Discrimination Gate reports it **IMPROVED, `MISS -> OK`**: the human's `correct` — the Hammer —
is now the TOP-ranked option by leaf value, where before it was not. So the valuation agrees with the
f12 ruling, and it is the SEQUENCER that takes the dig first, which is precisely what a tier is for
(it overrides score by construction; a boundary expressible as a score would not have needed one).

**That reading is NOT applied.** It is the user's to make, and self-ruling a frame whose two adjacent
rulings appear to adjudicate different comparisons is exactly the move ADR-0072 decision 5 and
ADR-0092's wave process exist to prevent. Recorded here with its evidence; the gate stays RED until
it is ruled.

## Consequences

- Every free-Item decider now has one hold price to subtract, and it is board-derived. Today
  `_denial_play_tactical` is its only equation-shaped consumer — gust's whether-to-play is still the
  five-rung band item 2g stages behind T4, and a Supporter's cost is its one-per-turn slot rather
  than the card. The seam is what lets 2g/T4 consume the same answer instead of minting a second.
- The `dont-*` rungs that hand-decline specific free Items (`dont-search-an-empty-deck`,
  `dont-tutor-the-held-wincon`, and the rest) are NOT retired here. Issue #212's agenda asked whether
  they could fold into a general price; they cannot fold into a FLOOR, because each encodes a
  card-class fact the assignment does not model (a search over an empty deck is dead in a way no keep
  marginal sees). They fold into T4's differencing or not at all, and that is stated rather than left
  as an implied follow-up.
- One more `authored-scaffold` name on the whitelist and one fewer magic number in `pilot.py`.
- Other frames will move in both gates as this boundary meets the rest of the corpus. Each is a wave
  item, exactly as ADR-0095 said.
