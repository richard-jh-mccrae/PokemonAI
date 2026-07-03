# ADR-0024: Shuffle-Refresh is the Fetch comparator's decision (A) only — a dead-hand fallback over keep-value, with a deferred stochastic pull-EV

**Status.** Accepted (grilled 2026-06-29); **Layer-A premise PARTLY REVERSED 2026-06-30** — the
`dig-before-commit` boundary guard is removed (see the Update note at the end of this Status block).
**Layer A core implemented 2026-06-29** test-first
(`tests/strategy/test_shuffle_refresh.py`, REQ-GEN-0042…0046). v1 scope = **Layer A** (the dead-hand fallback):
the `refresh-when-hand-is-dead` Hypothesis + the `Board.hand_is_dead` (full real-menu play-scan) and
`deck_holds_a_need` signals; the tag rename `discard_hand`→`shuffle_hand` + the `function_overrides.json`
durability fix; and the `dig-before-commit` boundary guard (a refresh no longer gets the early-dig
bonus). Layer B (stochastic pull-EV), the `hand_disruption` axis, and deck-overrides remain deferred
seams. Sibling to the **Fetch** doctrine ([ADR-0023](0023-fetch-is-a-shared-value-comparator.md))
and the **Gust** doctrine ([ADR-0022](0022-gust-is-closed-form-lethal-lookahead.md)); it **reuses**
the Fetch comparator rather than restating it.

**Update (2026-06-30) — the Layer-A "only when the hand is dead" premise is REFUTED.** The
`dig-before-commit` boundary guard (a `shuffle_hand` Supporter earns no early-dig bonus) made the
agent HOARD its draw Supporters: with no positive driver outside a literally-dead hand, a held
Lillie's / Harlequin scored ≤0, fell below the turn-ending attack in `_finish_turn_last`, and the
agent attacked instead of refilling — every turn it held one. Measured cost: the post-refactor build
won only **~24% of a 500-game mirror** vs the pre-refactor build #6 (`757b106`); restoring the
endorsement recovers it to **~51%** (together with the Buddy-Poffin bench-grab fix — see
[ADR-0023](0023-fetch-is-a-shared-value-comparator.md)). So `dig-before-commit` now DOES endorse a
Shuffle-Refresh as the hand-cycling draw it is. The premise was backwards for this deck: the dominant
misplay is *not refreshing*, not refreshing away a working hand. The two value-protection guards
(`attach-before-hand-shuffle`, `hold-wincon-dont-shuffle`) + the tier-3 sequencing (refresh after the
Energy attach, and the one-Supporter slot still prefers a tutor) keep the genuinely-bad shuffles out,
so the `hand_is_dead` machinery is now a redundant floor — a candidate for retirement (Layer-B work).

**Context.** A **Hand Refresh** supporter throws your whole hand away to draw a fresh one; almost
every deck runs one, and the dominant misplay is refreshing away a *working* hand. This set's cards —
**Lillie's Determination** (1227), **Judge** (1213), **Harlequin** (1223), **Lacey** (1199) — all
**shuffle the hand into the deck** then draw (the **Shuffle-Refresh** sub-kind; verified at source,
`data/EN_Card_Data.csv`). That is *not* a discard: the cards rejoin the deck and the pull pool —
distinct from a **Discard-Refresh** (hand → discard: Larry's Skill, Amarys — out of scope) and from
`recycle` (discard → hand: Night Stretcher — the opposite direction). The glossary (**Hand Refresh /
Shuffle-Refresh / Discard-Refresh**) is in [src/common/CONTEXT.md](../../src/common/CONTEXT.md). There
is **no "Professor's Research"** in this set.

The carrier tag is `discard_hand` — a **misnomer** (the motion is hand→deck, a shuffle) and a
**provenance bug**: it is neither probe-derived (`tools/meta_tracker/card_functions.py` emits
`hand_disruption` only for the *opponent's* forced hand→deck, `draw` for our own) nor in
`tools/meta_tracker/function_overrides.json`, so it survives in `card_functions.json` only as a
hand-edit a rebuild would silently clobber — yet `attach-before-hand-shuffle` /
`hold-wincon-dont-shuffle` already depend on it. Existing partial infra: those two negative guards,
plus `dig-before-commit` (which wrongly endorsed a refresh as a "dig").

**The reframe that drives this ADR.** A **fetch** presents a *choose-from-deck select* — the Fetch
doctrine is three decisions (A whether-to-play, B what-to-grab, C what-to-discard) over one
`fetch_value`. A **Shuffle-Refresh presents no select at all**: the shuffle (whole hand) and the draw
(N cards) are automatic. The Pilot's only choice is the MAIN-menu "play it?" — **decision (A) only** —
and the gain is **stochastic** (N random cards), not a chosen best card. So most of the Fetch
machinery (B greedy-grab, C discard-inversion) does not apply, and the one thing a refresh needs that
a fetch never did — a *probability* over the draw — is genuinely new.

**Decision.**

1. **Model as Fetch decision (A) only.** A Shuffle-Refresh is a single whether-to-play question. No
   grab-target, no discard-target. Expressed as additive, status-tracked Hypotheses in the
   [ADR-0008](0008-pilot-is-a-layered-rules-pipeline.md) idiom — **no monolithic `refresh_value`
   function** (the same "the scored sum *is* the value" choice as ADR-0023).
2. **Reuse the Fetch comparator, do not restate it.** The *cost* side (the hand we'd shuffle away) is
   valued by the **Fetch keep-value** (`fetch_value` read as "want it in hand"); the *gain-exists*
   side (does the deck still hold a card I lack) reuses the **need model**
   (`_fetch_fills_a_need` / `_grab_value_of`); the Supporter-slot economy and the Plan-scaled bar are
   the same as Fetch (A); deck-knowledge stays an **availability gate, never a forcer**. This buys the
   invariant **"never shuffle away a hand you'd fetch back"** for free — the mirror of Fetch's "never
   pitch what you'd fetch back."
3. **"Dead hand" = a full scan, not a keep-value floor.** `Board.hand_is_dead` is true iff **no
   non-refresh card in hand yields any positive-scoring play this turn** (each hand card virtually
   scored through the real hypothesis + closed-form tactical pipeline, reusing the
   `_fetch_fills_a_need` virtual-scoring pattern), **and** the deck still holds something I lack
   (`Board.deck_holds_a_need`). Keep-value ≈ 0 alone is *insufficient* — it is blind to a playable
   tutor, a gust-for-KO, a clutch heal — and would refresh those away. The full scan **is** pillar
   "use key cards first" proven structurally: every useful card outscores the refresh, so the refresh
   is reached only when nothing else is worth doing. Compute is trivial (≤ ~10 hand cards).
4. **v1 = Layer A.** One positive Hypothesis **`refresh-when-hand-is-dead`** (`when = shuffle_hand and
   board.hand_is_dead and board.deck_holds_a_need`), seed weight small-positive (~+8: beats `End`≈0,
   loses to any real play; ladder-tunes per [ADR-0009](0009-training-methodology.md)). Board-only,
   fires from turn 1, all Plans (it never preempts an attack — the scan is hand-only, attacks stay
   tier-2 turn-enders in `_finish_turn_last`, so a dead-hand + lethal refreshes *then* KOs the same
   turn).
5. **Keep the two existing guards as explicit keep-value floors.** `hold-wincon-dont-shuffle` (−25)
   still earns its place for the *wincon-in-hand-but-not-playable-this-turn* case (keep-worthy, yet
   yields no positive play, so the scan alone would call the hand dead). `attach-before-hand-shuffle`
   (−60) stays as the held-energy floor + sequencing. The full scan subsumes the *common* cases; these
   floor the narrow ones — exactly as ADR-0023 kept `keep-key-cards-at-discard` beside the comparator.
6. **Deferred seams (designed-in, not built).** **(Layer B) stochastic pull-EV** — the user's
   "what can I expect to pull": a hypergeometric over the deck-tracker's exact `deck_known_counts`
   ([sound-deck-emptiness oracle] / `OwnCardModel`), live only *post-anchor* (after a search reveals
   the deck), refining the binary "deck holds a need" into "P(the N-card draw fills it)" and unlocking
   the conditional 8-card windows (Lillie's at exactly 6 prizes, Lacey at opp ≤ 3 prizes). Must account
   for the shuffle **growing** the deck by the returned hand (the pull pool includes the dead cards you
   just put back) — the subtlety a fetch never has. **`hand_disruption` offensive axis** — Judge /
   Harlequin force the *opponent* to refresh too; a positive term scaling with the opponent's hand size
   (board-only, observable) for when wrecking a hoarded hand outweighs the symmetric refresh.
   **Deck-override** — mostly the existing `_weight` by-id override (a deck that should refresh more /
   never / for a combo just tunes the weight); no new seam needed for v1.
7. **Tag rename + provenance fix (implementation step).** Rename `discard_hand` → `shuffle_hand`
   across `card_functions.json` + the Hypotheses + docs, **and add it to `function_overrides.json`**
   (cards 1213/1223/1227/1199) so a rebuild can no longer clobber it.
8. **Boundary with the Fetch session (landed).** The only overlap with the parallel `dig-before-commit`
   redesign is that the +20 early-dig bonus must not reach a refresh. Resolved with a minimal additive
   guard (`"shuffle_hand" not in c.tags`, mirroring the existing `cost_discard` exclusion); the Fetch
   session keeps/subsumes it rather than re-litigating.

**Considered options.**

- **Unify Shuffle- and Discard-Refresh under one doctrine** — rejected: recoverability and the pull
  pool differ (a shuffle returns the hand to the deck — the Layer-B math and the "what you lose"
  calculus change; a discard does not). Scope to Shuffle-Refresh; Discard-Refresh is a noted sibling.
- **A standalone hand-quality heuristic** (don't reuse the Fetch keep-value) — rejected: duplicates the
  value logic and risks a "shuffle away what you'd have fetched back" inconsistency between two
  value functions. Reusing the comparator gives the invariant for free.
- **Model as decision (A/B/C) like Fetch** — rejected: a Shuffle-Refresh presents no select, so B and C
  are vacuous. Only (A) exists.
- **"Dead hand = keep-value ≈ 0" binary** — rejected: blind to a playable tutor / gust-for-KO / clutch
  heal (all keep-value 0), which it would refresh away. The full play-scan fixes this.
- **A narrow curated dead-hand predicate scan** (develop / attach / fetch-fills-need / keep-worthy) —
  rejected: still misses situational live cards; the full "no positive play this turn" scan needs no
  curated list and is accurate by construction.
- **Lead with the stochastic pull-EV (Layer B) as the primary driver** — deferred, not v1: it is
  structurally unavailable before the tracker anchors, and worthless while the agent is still
  refreshing live hands. Foundation (Layer A) first, math second — the ADR-0023 staging.
- **An offset Hypothesis cancelling `dig-before-commit`'s +20 on `shuffle_hand`** — rejected: brittle
  coupling to a weight the Fetch session is actively changing. The additive exclusion guard is robust.

## Amendment (2026-07-03, grilled): Layer B = deck-side suppressors only; the dead-hand machinery retires

The 2026-06-30 refutation changed Layer B's gap: the misplay is no longer "silent on a mediocre
hand" (the flat `dig-before-commit` +20 endorses every refresh) — it is that the +20 is
**deck-blind**. And the hand side needs nothing new: `_finish_turn_last` tier-3 means the refresh
executes only after every endorsed play, so the hand at shuffle time is already the residual dregs;
the curated holds floor the keep-worthy-but-unplayable cards. Decisions:

- **Retire `refresh-when-hand-is-dead` (+8) and the `Board.hand_is_dead` full-menu scan** (the
  Update note's retirement candidate, confirmed): on a dead hand the refresh already wins via +20
  with nothing else endorsed — the rung adds compute and test surface, no behavior.
  `deck_holds_a_need` survives, repurposed as the sound veto's substrate. REQ-GEN-0042…0046 tests
  rewritten at build.
- **Two deck-side suppressors, mirroring the search whiff family** (discrete rungs — the Item-2
  idiom decision, ADR-0023 amendment, applies here too):
  - `dont-refresh-for-nothing` **−40**, sound-or-silent: `deck_holds_a_need` False = every needed
    card provably gone (valid pre-anchor). Deliberately weaker than the search's −60: a refresh can
    carry non-pull value — the disruption endorsements (`play-harlequin-vs-hand-size` +25,
    `disrupt-when-unfavored` +18) survive the veto and a Judge/Harlequin still plays *as
    disruption*; a plain Lacey/Lillie's dies (+20−40).
  - `dont-refresh-into-a-probable-miss` **−25**, POST-ANCHOR only (`deck_known_counts`):
    hypergeometric P(≥1 needed card among the N drawn) < **0.20** (`_WHIFF_PROB_THRESHOLD`,
    consistent with the sibling). The pool is the shuffle-grown deck **D′ = deck + returned hand −
    the played card** (returned dregs dilute; K unchanged — a held card is by definition not
    lacking). Mutually exclusive with the sound rung by construction (requires K > 0).
- **Draw-count N is an id-keyed fact table** (verified at `data/EN_Card_Data.csv` 2026-07-03), the
  conditional windows folded into N — no boost rung: Lillie's Determination (1227) 6, **8 at own
  prizes exactly 6**; Lacey (1199) 4, **8 at opp prizes ≤ 3**; Judge (1213) 4; Harlequin (1223)
  exact over the coin branches (3/5).
- **Scoped OUT, recorded:** any hand-level value scalar (the 83116081-17 / 83117367-34 Lillie's-vs-
  Harlequin pair stays a Base-Value-Model call, ADR-0007); the `hand_disruption` offensive axis
  and the board-conditioned side of the symmetric-refill cost (opponent hand-size scaling) — its
  *favorability-conditioned* half shipped as `dont-gift-a-refresh-when-favored` (ADR-0026
  amendment, same day); pre-anchor probabilistic EV (an E[K]-of-an-expectation blurs ADR-0029's separation for a
  rung that would ~never fire on a rich deck). The ADR-0028 anti-shuffle Tool floor is untouched
  (attached cards are not in hand).
- **Evidence gate:** full-corpus retest + arena A/B (overlay zeroing the two rungs); TDD, REQ-GEN
  numbers continuing after the Item-2 build's allocations.

**A/B verdict (2026-07-03, built same day) — the sound veto REGRESSED and was DELETED.** 1000-game
mirror legs: both rungs ON 43% (CI 40–46); `dont-refresh-for-nothing` alone 47% (44–50);
`dont-refresh-into-a-probable-miss` alone 50% (47–53). Root cause: the veto reused the Fetch NEED
model, but grab-rung needs (gap-gated, satisfy-count 1) under-count refresh VALUE for a deck whose
engine is the refresh itself — mid-game with the wincon deployed and not energy-starved, every deck
card scores 0 grab-value while refreshing for more Energy/attackers is still right. **Revision
shipped:** `dont-refresh-for-nothing`, `deck_holds_a_need` and its `_has_shuffle_refresh` gate are
deleted; `dont-refresh-into-a-probable-miss` (post-anchor, −25) owns the whole deck side, its **K = 0
case** (P = 0) covering the provably-spent deck — which is a post-anchor situation in practice (this
deck anchors early through its search density). Re-A/B of the revision: 48% (45–51), neutral →
default ON. The retirement and everything else in this amendment stands.

**Consequences.** The two existing guards become explicit keep-value floors *beside* the reused
comparator (a future reader who sees them scattered should read this ADR + ADR-0023 for the shape).
The build adds two `Board` signals (`hand_is_dead` via a hand-card play-scan reusing the
`_fetch_fills_a_need` virtual-scoring pattern; `deck_holds_a_need`) and one Hypothesis
(`refresh-when-hand-is-dead`); the tag rename + `function_overrides.json` durability fix; and tests
`tests/strategy/test_shuffle_refresh.py` (REQ-GEN-0042…), test-first per the global testing standard.
Layer B (stochastic pull-EV), the `hand_disruption` offensive axis, and deck-overrides arrive on the
designed-in seams without reshaping the comparator. Documented in
[general-strategy.md](../general-strategy.md#shuffle-refresh-doctrine--designed-adr-0024); glossary in
[src/common/CONTEXT.md](../../src/common/CONTEXT.md). v1 plays board-only; the Read/Posture is not
wired (matching ADR-0022/0023).
