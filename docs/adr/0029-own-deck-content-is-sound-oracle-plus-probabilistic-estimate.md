# ADR-0029: Own-deck content is a SOUND oracle PLUS a PROBABILISTIC estimate — two epistemics, never contradictory

**Status.** Accepted & **implemented** test-first 2026-06-30 (`tests/test_deck_odds.py`,
REQ-GEN-0053..0055). Adds `common/deck_odds.py` (the pure hypergeometric estimator), the
`Board.deck_contains_probability` signal, and one Fetch rung `dont-search-a-probable-whiff` (−25).
Complements — does **not** replace — the sound deck tracker
([ADR-0023](0023-fetch-is-a-shared-value-comparator.md)'s `OwnCardModel` /
`deck_definitely_empty_of`). Scope: **own** deck only; opponent-deck inference is separate and
unbuilt.

**Context.** Own-deck knowledge already has a **sound** half: `OwnCardModel`
([deck_tracker.py](../../src/common/deck_tracker.py)) resolves the 6-card prize split **exactly**
(only once a search reveals the whole deck) and otherwise reports stateless pigeonhole bounds;
`Board.deck_definitely_empty_of` / `deck_definitely_has` are **certain-or-silent** — a copy that
could sit in the hidden prizes leaves them silent. That is the correct epistemics for an availability
*gate*: the sound whiff guard `dont-search-an-empty-deck` (−60) stands a search down **only** on a
CERTAIN whiff, so a spare card is never burned on a guess.

But prizes are **hidden almost all game**, so the sound oracle is silent on the *most common*
own-deck question: *"should I keep hunting card C?"* — e.g. play a **second** Buddy-Buddy Poffin that
*might* whiff because the last Staryu *might* be prized. A correction was **refuted** on exactly this
(reviewed.json `82524455-f6`: *"only 1 of 3 Staryu visible; the other 2 could sit in the 6 hidden
prizes, so 'a 2nd Buddy-Buddy whiffs' is a probabilistic read, not a fact"*). The refutation is
correct **for the sound oracle** — and it names precisely the missing tool: a *probabilistic* read.
Flagged as a deferred dependency during the 2026-06-30 recipient-first work
(`turbo-flare-recipient-first`; that fix itself needed **no** deck deduction).

**Decision.**

1. **Two epistemics, kept physically separate — and they never contradict.** The SOUND oracle stays in
   `deck_tracker.py`, certain-or-silent, unchanged (its module invariant is preserved). The new
   PROBABILISTIC estimate lives in its **own** module `common/deck_odds.py`, so a reader never
   confuses "provably empty" with "probably empty." The estimate is built to **agree with the sound
   oracle at every extreme** (below), so the two signals can only ever *refine* each other, never
   disagree.

2. **The model is a hypergeometric split of a card's UNSEEN copies over the hidden prize slots.** For a
   card with `u = decklist − visible` unseen copies, `K = prizes_hidden` face-down prize slots and
   `H = deck_count + K` total unseen positions, treating the prizes as a uniformly random `K`-subset of
   the unseen positions gives `P(deck still holds ≥1 copy) = 1 − C(K,u)/C(H,u)`. Closed-form, off the
   known decklist + the always-visible zones + `deckCount` + the prize count — **no Search, no learned
   model** (consistent with the Tier-0 closed-form contract and the card2vec rejection).

3. **Sound at the extremes — the agreement contract.** `u == 0` → **0.0** (every copy seen ⇒
   sound-EMPTY); `u > K` → **1.0** (more unseen copies than prize slots ⇒ pigeonhole-present, where the
   *stateless* sound oracle stays silent on presence); `K == 0` → **1.0** (no hidden prizes ⇒ every
   unseen copy is in the deck); `deck_count == 0` → **0.0** (an empty deck holds nothing). And when the
   tracker has **resolved** the prizes, there is no randomness left, so the estimate **collapses to
   exact certainty by reusing the SAME sound counts** (`deck_known_counts`: 1.0 in-deck / 0.0
   otherwise) — the two signals are then identical by construction.

4. **Exposed as one Board signal, consumed as a SOFT suppressor — never a forcer, never a replacement.**
   `Board.deck_contains_probability(cid)` reads the precomputed `deck_contains_odds` dict. The Fetch
   doctrine's new `dont-search-a-probable-whiff` (−25) fires off `Context.search_targets_unlikely` —
   the best still-**reachable** target's probability is below `_WHIFF_PROB_THRESHOLD` (0.20). It is
   **mutually exclusive** with the sound `search_targets_exhausted` (which requires the reachable set
   *empty*), so the two never double-count: the sound guard owns the CERTAIN whiff, this tips a LIKELY
   one. Weighted **well above** the sound guard (−25 vs −60): a guess only cancels a lone free-dig
   `dig-before-commit` (+20) endorsement — it does **not** override a real lacking-need grab (you still
   dig hard for an unfound win-condition, whose `fetch-when-it-fills-a-need` endorsement survives).

5. **Conservative threshold honours the refutation.** At 0.20 a search is stood down only when its best
   target is ≥4× more likely prized than in-deck. The refuted `82524455-f6` shape (2 of 3 Staryu
   hideable in 6 prizes) scores **≈ 0.98** — far above the bar, so it is **not** suppressed: the
   probabilistic read says "probably still there," exactly matching the refutation.

6. **Grader-safe and behaviour-neutral by default.** `deck_odds` is pure, lib-free (`math.comb`) and
   **never raises** — any bad input collapses to **1.0** ("assume present"), the conservative direction
   that never suppresses on garbage. The Board signal is **None** (silent → probability 1.0) whenever it
   is uncomputable (no decklist / no `deckCount`); since no prior test populates `deckCount`, every
   existing decision is unchanged (690 tests green).

**Considered options.**

- **Fold the estimate into `deck_tracker.py`** — rejected: that module's invariant is *certain-or-silent*
  ("never probabilistic"); a guessing function there would muddy the one place whose whole value is
  soundness. A sibling module makes the split physical and legible.
- **Make the probabilistic signal a HARD veto (replace or outrank the sound guard)** — rejected: it would
  burn a spare card on a guess, the exact failure the sound oracle exists to avoid. A guess gets a soft
  weight that only tips a marginal search.
- **A positive "the deck probably has it, so go fetch it" endorsement** — rejected for v1, mirroring
  ADR-0023's deck-knowledge stance (availability gates, never forces; gap drives). The over-play risk
  (digging because you *can*, not because you *lack*) needs the value layer; the probabilistic oracle
  stays a suppressor. `deck_contains_probability` is exposed for a future positive reader, staged like
  `deck_definitely_has`.
- **A full joint-probability "P(the search finds *anything*)" over the whole fetch set** — rejected as
  over-engineered: the targets are correlated (one hidden pool) and the closed-form joint is fiddly. The
  best-single-target heuristic is conservative (it suppresses *less* than the true joint would), simple,
  and matches the "is even my best shot probably gone?" intuition.
- **Tie the threshold to the Plan / Read** — deferred behind the same seam as ADR-0023's Plan-scaled bar
  and Read-conditioned fetching; v1 is a single tuned constant.

**Consequences.** The build adds `common/deck_odds.py` (`p_contains` + `contains_odds`), the
`Board.deck_contains_odds` field + `deck_contains_probability` method, the `Pilot._deck_contains_prob`
wiring (resolved → certainty via `deck_known_counts`, else hypergeometric), the
`Context.search_targets_unlikely` signal + `FetchMixin._search_probable_whiff`, and the
`dont-search-a-probable-whiff` rung. The deferred `turbo-flare-recipient-first` dependency is **closed**.
The sound oracle and the `dont-search-an-empty-deck` guard are untouched. Glossary term **Deck-Content
Odds** in [src/common/CONTEXT.md](../../src/common/CONTEXT.md); rung documented in
[general-strategy.md](../general-strategy.md#fetch-search-doctrine--designed-adr-0023). **Deferred
seams:** a positive fetch endorsement off the odds; a Plan/Read-scaled threshold; opponent-deck
inference (separate ADR when built).
