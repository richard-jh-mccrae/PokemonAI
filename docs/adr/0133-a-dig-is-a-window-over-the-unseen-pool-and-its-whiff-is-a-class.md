# ADR-0133: A dig is a WINDOW over the unseen pool, and its whiff is a class

**Status.** Accepted (Issue #440, 2026-08-08). BUILT. Extends ADR-0130 (the reveal node this fills in)
and ADR-0073 (the two readings of a fetch clause, which this makes three). Depends on Issue #454's
CHOSEN/DEALT split — without it this change would have been silently worse than the refusal it
replaces. Scope narrowed by the owner to the `dig` cards of `mega_starmie` and `hydrapple`.

## Context

`board_expectation` refused every `dig` clause through `fetch_closure.fetch_is_unconditional`, which
rejects `trigger` / `dig` / `condition` / `name_family` as one. Measured over the committed corpus
(375 correction rows, **279 at `CONTEXT_MAIN`**), that cost **30 Pokégear 3.0 options across 27
frames** — options the composer records as a gap and does not rank at all.

A dig is not a wider whole-deck search. Every enumeration ADR-0130 built answers *"is the target
still in my deck?"*; a dig asks *"is it in the top N?"*, and a copy at position N+1 is a **miss**. So
a dig has a real whiff class that a whole-deck search does not, and nothing in `src/common` computed
a top-N window probability. (The `dig` hits elsewhere are the `card_functions.json` Ability TAG —
`functions.dig_depth` feeding the scalar `draw_hit_probability` — a different question on a different
key. Positive control: that same instrument finds `draw_hit_probability` consumed in eight modules.)

**Three facts made the obvious change the wrong one.**

1. **`Expectation.best()` is a MAX.** Before Issue #454 it was the only aggregator, on the stated
   grounds that *"both producers emit CHOICE nodes."* A whiff is DEALT. Adding the class without the
   resolution split would have priced Pokégear at *"I always find my best Supporter"* — the agent
   gambles, nothing raises, no test fails.
2. **Un-gating `dig` alone models the card as a CERTAIN whiff.** `supporter` is in
   `FETCH_DEADNESS_ONLY_TARGETS`, so `fetch_target_matches` returns `False` for every card and
   Pokégear's pool comes back **empty** — verified against the whole `mega_starmie` decklist
   (`matches == []`, `matches(deadness=True) == [1182, 1189, 1223, 1225, 1227, 1229]`). Issue #394's
   decline read this as *"widening the dig gate retires 0 of its steps"*; after Issue #456 added the
   1.0-probability `_whiff()` path it became worse than that — all 30 options priced as a card spent
   for nothing.
3. **The predicate drops a printed restriction on a Pokémon target.** Bug Catching Set is *"{G}
   Pokémon and Basic {G} Energy"* and carries `energy_type: 1` on both legs; `fetch_target_matches`
   binds `energy_type` to Energy targets only. Over `hydrapple` its Pokémon leg reaches **12 ids
   where 10 are legal**, wrongly admitting 140 Fezandipiti ex ({D}) and 1071 Meowth ex ({C}).
   ADR-0073 §3 recorded this as an accepted caveat *"unresolvable from `CardStat`"*. **That premise
   is stale**: `CardStat.energyType` is populated for Pokémon through the shipped `_build_cache`
   (Applin 1, Teal Mask Ogerpon ex 1, Meowth ex 0, Fezandipiti ex 7).

## Decision

**1. The enumerator stops asking the endorser's question. `fetch_is_unconditional` is not split.**

Issue #440's body framed this as splitting a four-reader predicate without widening what those
readers endorse. There is a cleaner answer: this node has no business asking. `_check_clause` gates
on `trigger` / `condition` / `name_family` individually and admits `dig`, because the window is
**priced** rather than assumed away. `fetch_is_unconditional` is untouched and its four endorser
readers — `fetch_target_matches`'s own reach gate, the Attach Budget's deck-fetch unit
(`combat_math/energy.py`), and `planning/gamble.py`'s slot / Supporter-energy-tutor /
Supporter-evolution-tutor legs — keep byte-identical behaviour.

`dig` joins `_HANDLED_FETCH_KEYS`; **`dig_from` deliberately does not**. The bottom-N is the same
distribution by exchangeability, but nothing in scope needs it and an unhandled key is the
fail-closed answer.

**2. A third READING, not a widened reach one.**

ADR-0073 established one predicate with two readings and stated why they cannot merge: which
direction of over-inclusion is safe depends on the consumer's quantifier. This node is a third
quantifier — it neither endorses (`any(reachable)`) nor vetoes (`all(gone)`), it **enumerates and
weights**. So `fetch_target_matches(clause, stat, *, reading=REACH)` over `REACH | DEADNESS |
WINDOW`, keeping the keyword shape ADR-0073 chose so a caller that forgets still gets the safe
answer. The old `deadness: bool` is migrated, not aliased: two spellings of one reading is the defect
ADR-0073 is about. `WINDOW` differs from `REACH` in exactly three places:

- it does not apply the `fetch_is_unconditional` gate;
- it resolves `supporter`. ADR-0073 blocked that class from reach because a dig-7 Pokégear would
  claim it *fills* a Supporter need. An enumerator claims nothing — it reports P(hit) and P(whiff) —
  and ADR-0073's own consequences anticipated this as *"a deliberate, measured change rather than a
  silent consequence of a new card row."* `any` stays DEADNESS-only under every reading: it names no
  class, and nothing in scope needs one;
- it applies `energy_type` to Pokémon targets. A **narrowing**, which is why it is safe here and
  unsafe for DEADNESS (narrowing an `all(gone)` conjunction FABRICATES a whiff claim). REACH's own
  un-widening moves three cards in other decks and owes its own score-diff; it is filed separately
  and deliberately not folded in.

**3. The prize split disappears into the pool. `deck_count + prizes_hidden`, not `deck_count`.**

The deck is a uniformly random `D`-subset of the `D + H` unseen cards and the window is a uniformly
random `W`-subset of the deck, so the window is a uniformly random `W`-subset of the `D + H` unseen
cards. Ranging the hypergeometric over the full unseen pool therefore handles the prize split
**exactly**, with no mixture. Checked against the explicit mixture — the shape
`gamble._prize_split_hit` spells out — at eight real corpus shapes: agreement to ≤ 1.1e-16. The
window itself is still `min(dig, deck_count)`: you look at the top of the DECK, and late it holds
fewer than seven cards.

`p_contains_at_least`'s availability weight is **not** reused on this route. Different question.

**4. The classes are one exact closed form, and the whiff is its `M = ∅` member.**

Rank the matching ids by `score(model after taking that id)` descending, at ADR-0128's noise floor
with a card-id tie-break. With group *g* holding `c_g` unseen copies, `N_k` the cumulative count and
a delivery cap of one:

```
P(take group i) = miss(N_{i-1}, P, W) − miss(N_i, P, W)        P(whiff) = miss(N_n, P, W)
```

telescoping to exactly 1.0. `deck_odds._none_of` already **was** that bracket —
`draw_hit_with_engines` builds its two-window term from it — so it is promoted to the public
`window_miss_probability` rather than copied. For `m > 1` the same construction generalises: groups
above the cutoff contribute exactly what the window held, the cutoff group contributes `b ≥ a_k`, and
everything ranked below is free because it was never reached.

**The policy is part of the model.** The probabilities are exact *under* take-the-best-scoring-match,
so the ranking is not a display order and two processes reading one board must reach the same one.

**5. `resolution = DEALT`, and the whiff is PINNED past the branching cap.**

The window deals; the pick inside it is chosen; the greedy policy is already baked into the
probabilities, so `.ordering()` must take `expected()`. And because a greedy ranking makes the
classes `BRANCH_CAP` drops the *worst* ones, truncation on a DEALT node biases the value **upward** —
so the whiff keeps a slot regardless of its rank. It never takes the *only* slot: at a cap of one,
pricing a live dig as a certain whiff is a worse lie than dropping the class, so it is dropped and
counted in `truncated` rather than silently gone.

**6. `expectation()` takes `score=` and REFUSES without it** — `_cost_indices`' `shed` discipline one
seam over: *with no oracle it refuses rather than inventing a second one.* `composer._one_ply` and
`tools/train/expectation_census.py` pass `state_value`. ADR-0128's floor moves to
`apply_option.SCORE_PLACES` so the composer's ordering and this one cannot be given different floors.

**Rejected: splitting `fetch_is_unconditional` into per-field predicates.** Issue #440's own
framing, and it puts the change in the shared predicate where four endorsers read it. Decision 1
reaches the same place by removing a question rather than adding an answer.

**Rejected: widening `REACH` to resolve `supporter`.** It would make a plain Supporter search a
closure edge and move the out-count, which is a measured change to five endorsing call sites and not
this issue's.

**Rejected: a two-class hit/whiff Expectation.** Cheaper, and it throws away *which* card the window
handed over — the thing the composer differences on. The per-group form costs one model build per
candidate and is exact.

## Consequences

- **All 30 Pokégear 3.0 options enumerate**, at 5–7 classes each (25 of them 7), zero truncated, mass
  1.0 on every one. Whiff probability min **0.0074**, median **0.0535**, max **0.1150** — so the card
  hits ~95% of the time in this deck, and the change is not "5% better pricing" but "30 options enter
  the ranking at all."
- **The expectation census over all 377 traces, before and after, accounts for every step.** Enumerated
  by a reveal node **368 → 394 of 663** (55.5% → 59.4%), all of it `board_expectation` (249 → 275);
  refusals **295 → 269**. The old `not the unconditional` bucket held **61** steps and is gone: 22
  Pokégear 3.0 and 4 Bug Catching Set now ENUMERATE (**+26**, exactly the delta), and the other 35
  moved to a bucket naming their own field — Roto-Stick 14 to `amount`, Meowth ex 12 and Hop's Bag 2
  to *"which this seam cannot decide"*, Explorer's Guidance 4 and Dusk Ball 3 to `clause key(s)`.
  Nothing else moved, and `truncated at BRANCH_CAP` went 15 → 14.
- **One card outside the named scope changed, and it is a correctness fix: 1142 Fighting Gong in
  `mega_lucario`.** It already enumerated, and its Pokémon leg carries `energy_type: 6`, so the
  narrowing applies. Printed text, read at source: *"Search your deck for a Basic {F} Energy card **or
  a Basic {F} Pokémon**"* — and 1071 Meowth ex is **{C}**. The old reading let Gong enumerate a class
  that delivers a body the card cannot take. Measured over the 27 Gong steps in the trace corpus: no
  class delivers Meowth ex any more, and the census's class-count distribution moves three steps DOWN
  (11: 3→1, 12: 15→14) for exactly that reason. Kept rather than special-cased: `outcome_pool` reads
  ONE reading, and making it depend on whether an unrelated field is present would put the seam's
  policy at its call site. Distinct from the REACH follow-up below, which is the same defect at a
  different reading with different consumers.
- **Bug Catching Set is dark where it counts, and not entirely dark.** `hydrapple` has no
  corrections — that store is `mega_starmie` 251, `mega_lucario` 70, `dragapult_ex` 54 — so its 11
  groups at `m = 2` (up to 78 classes, truncating hard) get no *decision* measurement, which is the
  owner's explicit call to validate on the ladder. It is exercised 4 times in the parity trace corpus,
  so the multi-card path is not unrun; recorded precisely so a later reader neither mistakes unit
  coverage for measurement nor reads "dark" as "never executed".
- **ADR-0131's anchor frame changed, and its ruling did not.** On
  `ms_information_before_commitment_f11` the ruled Pokégear 3.0 moves from an unpriced sentinel to
  **−0.0093**: a 1-for-1 Item→Supporter swap barely moves the end board, less the whiff. That is
  ADR-0095 speaking — *a composer is a function of the end state, so it cannot see information
  value* — not a defect. The six-way tie at 0.0 still holds, `_composer_line` still abstains, and the
  structural sequencer still plays the ruled dig. The test that asserted the option stays *unpriced*
  is re-ruled to assert it prices **below** the tie, which pins both halves.
- **The closed form is pinned against brute force**, not against a second formula: seven
  parametrised shapes enumerate every `W`-subset of the pool, greedy-pick in rank order and tally —
  covering `m = 1`, same-group pairs, a `take` above what the window can hold, and the empty pool.
- **The rest of the family still refuses, each naming its own field** — Roto-Stick (`amount: "all"`),
  Dusk Ball (`dig_from`), Explorer's Guidance (`rider`), Hassel (`condition`), Hop's Bag
  (`name_family`), Meowth ex (`trigger`), Drakloak (`other_to_bottom`, the RNG gate being the more
  specific one). Admitting `dig` admitted nothing else, and that is a test rather than a claim.
- **Issue #469 can reuse this.** 120 Drakloak's `{"kind": "draw", "amount": 1, "window": 2}` is the
  same window math on the other clause kind, which is why `window_classes` takes an order, a pool and
  a window rather than a fetch clause.
- **Follow-up, not folded in:** the `energy_type`-on-a-Pokémon-target narrowing for REACH (1142
  Fighting Gong, 1233 Canari, 1238 Tarragon — none in scope), and `gamble._prize_split_hit`'s O(u)
  mixture loop, which Decision 3's identity collapses to a single call.
