# Seam handoff: tutor-chain grab value (a tutor is worth what it reaches)

**Parallel-session slot C.**
**Corpus acceptance target:** `85059103-9` (mega_lucario), xfail-strict — at a TO_HAND grab the agent
takes Judge (+10, `grab-a-draw-supporter-in-setup`) over Team Rocket's Petrel (0). The human
(CRITICAL): "I would have fetched a Petrel, which can be used to fetch a Fighting Gong, which can be
used to fetch a Solrock…" — the chain opener out-values a third draw Supporter. Note the duplicate
Lillie's is ALREADY correctly avoided (`dont-grab-a-card-already-in-hand` fires); redundancy is not
the gap — chain value is.

## Grill status: ◐ principle grilled (spec Round 9 §3) — mechanism OPEN

Round 9 §3: **"a tutor's held value = the closure-reachable value, recursively free."** That is the
whole design sentence; the mechanism was never grilled. The graph legs exist:
`fetch_closure.fetch_target_matches` / the clause tier know what Petrel reaches (`target: trainer`,
zone deck), and the Petrel 2-hop is already implemented for the GAMBLE side
(`planner._supporter_energy_tutor_reaches`, `_supporter_evolution_tutor_reaches`) — the grab side
never reads it.

**Open questions to settle (grill first):**
1. RECURSION SHAPE: `chain_value(tutor) = max over reachable targets of grab_value(target)`, one hop
   at a time with the existing 2-hop cap (spec-verified legal in one turn)? A discount per hop
   (certainty decays: the hop costs a play and reveals nothing until resolved)? Never a SUM — a
   tutor fetches one thing.
2. DOUBLE-COUNT: `_grab_value_of` already sums positive TO_HAND rungs for the TARGET; a chain term
   for the TUTOR must not stack with `play-a-tutor-for-the-unfound-wincon` (+25) or
   `grab-a-draw-supporter-in-setup` (+10) — one currency zone. Likely shape: a new grab rung
   (`grab-the-chain-opener`?) whose value derives from the chain, REPLACING the flat tutor-grab
   band for cards with a `trainer`/`energy` fetch clause.
3. OPPORTUNITY COST: Petrel spends the one-per-turn Supporter slot; a chain through two Supporters
   is NOT free in one turn. The `supporter_played` / post-Item gating from the gamble's Supporter
   branch is the precedent — reuse its logic, don't re-derive.
4. Memoisation: `_search_deck_set` is memoised per card; a recursive chain value must be memoised
   with the same deck-fixed discipline (and stay cycle-safe: Petrel reaches Petrel).

## Build plan

1. RED: the corpus xfail + a unit test on `85059103-9`'s board (Petrel outranks Judge at the grab).
2. Implement the settled chain term in `doctrine_fetch`'s grab side, reading `fetch_closure` (never
   a text parse; clauses only). Fail direction: endorser (unknown chain → 0, never inflates).
3. Re-audit: `test_fetch_doctrine.py` grab tests, the greedy multi-pick (`_greedy_grab` re-scoring
   must see the chain value decay once the chain's END target is acquired), fetch-target corpus PINS
   (`84890060-26`, `84071010-53`, `83686860-33`, `85058051-13`, `81903490-8`), broad sweep.
4. Promote the target; update the findings doc.

## Conflicts with other seams

Touches `doctrine_fetch.py`'s **grab** section — seam B (held-card-risk) edits the same file's
whether-to-play section; coordinate merge order (textual only). Reads `fetch_closure.py` (no edits
expected — if the chain needs a new graph helper, add it there, it's the shared home). Not alongside
the discard convergence (seam D). Corpus-file edit on promotion.
