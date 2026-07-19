# Seam handoff: tutor-chain grab value (a tutor is worth what it reaches)

**Parallel-session slot C. STATUS: BUILT 2026-07-19** — `grab-the-chain-opener` (+15) shipped in
`doctrine_fetch.py` (grab side), backed by `FetchMixin._chain_grab_value` / `_chain_fetch_targets`
and `fetch_closure.fetch_target_matches`' new `trainer` branch; `Context.card_chain_value` wired in
`pilot._context`. Acceptance target `85059103-9` XPASSed and is PROMOTED to a corpus pin; unit
suite `tests/strategy/test_tutor_chain_grab.py` (REQ-GEN-0077); full sweep green (3048 passed,
3 xfailed = the other seams' targets). Findings doc §D updated.
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

**Open questions — SETTLED (grill closed 2026-07-19; the shipped mechanism):**
1. RECURSION SHAPE: `chain_value(tutor) = δ × max over reachable targets t of
   max(grab_value(t), chain_value(t) if t is an ITEM)`, with δ = 0.75 **per hop**
   (`_CHAIN_HOP_DISCOUNT`) and the existing 2-hop cap (`_CHAIN_MAX_HOPS = 2` — the gamble's
   spec-verified one-turn Petrel → Item → target chain). MAX, never a sum (a tutor fetches ONE
   card). δ < 1 buys the **monotone-decay invariant**: at the same select a direct target strictly
   outranks a tutor that merely reaches it, and each extra hop decays further (a hop costs a play
   and reveals nothing until resolved). Reachable = the tutor's clause-derived deck target set,
   minus `deck_empty_ids` (whiff-sound) minus non-Energy cards already in hand (the value must be
   value you LACK — the chain-side mirror of `dont-grab-a-card-already-in-hand`). End-target value
   is `_grab_value_of` — the ADR-0023 shared oracle — so every need stand-down is inherited and the
   chain decays automatically as needs are met (incl. `_greedy_grab`'s virtual board: Solrock
   acquired → `fetch-the-missing-engine-half` stands down → the chain through it dies).
2. DOUBLE-COUNT: one currency zone by three devices. (a) The new rung (`grab-the-chain-opener`) is
   TO_HAND CARD-side only, so it can never co-fire with the PLAY-side
   `play-a-tutor-for-the-unfound-wincon` (+25) / `dig-before-commit` — a different decision. (b)
   `_grab_value_of`'s reduced Context leaves `card_chain_value` at its 0.0 default, so the chain
   rung never fires INSIDE the oracle — no self-recursion, and a tutor valued as an END target
   stays flat. (c) The gate excludes a draw-tagged Supporter — a card rides the draw band OR the
   chain band, never both. The rung IS the (previously missing) flat tutor-grab band: a **static,
   tunable +15** (weights are the ADR-0008 tuner currency; dynamic magnitudes live only in the
   Tier-0 combat tactical channel), fired only when the exactly-computed chain value clears
   `_CHAIN_OPENER_FLOOR = 10` — the flat draw-Supporter band it competes with (this also kills
   noise chains: δ² × the +3 color tie-break ≈ 1.7, silent). +15 sits above draw (+10), below every
   real direct need (+18/+20/+22/+30/+35), and `dont-grab-a-card-already-in-hand` (−12) still nets
   a held tutor below a fresh Judge.
3. OPPORTUNITY COST: a Supporter tutor with `board.supporter_played` prices chain 0 (fail-closed;
   `card_unplayable_this_turn` −12 additionally demotes it). The chain never descends THROUGH a
   Supporter — Item-only intermediates, the gamble's `ist.is_item` post-Item gating reused verbatim
   (`_supporter_energy_tutor_reaches` precedent): a two-Supporter chain is not free in one turn.
4. MEMOISATION & CYCLES: the GRAPH leg (tutor → full-scope deck target ids, `trainer`/`energy`/
   Pokémon clauses via `fetch_closure.fetch_target_matches`) is deck-fixed and memoised per card id
   (`_chain_target_cache`, the `_search_deck_set` discipline). The VALUE loop is board-dependent —
   computed per Context build with a per-call memo of `_grab_value_of` results. Cycle-safe three
   ways: a path-local `seen` set (Petrel's trainer clause reaches Petrel — cut), Item-only descent
   (cuts Supporter self-loops structurally), and the 2-hop cap.

Known, documented optimism: an intermediate Item's own cost (Ultra Ball's discard-2) is not priced
inside the chain — mitigated by MAX (a free Fighting Gong dominates whenever both reach the same
target), the static +15 cap, and the floor. `fetch_closure.fetch_target_matches` gains the
`trainer` target branch (the one shared predicate; also fixes `reaccess_outs`' under-count — Petrel
genuinely re-accesses a shuffled-back Trainer).

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
