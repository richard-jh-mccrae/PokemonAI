# Ply-1 exhaustive within-turn search — GRILL SPEC (to grill, not built)

**Status:** grill spec — seeds the session, no decisions locked. Graduates to an ADR (next free **0064**)
once grilled. Companion: [develop-rung-handoff.md](develop-rung-handoff.md) (the rung + leaf + lab),
[hypergeometric-fetch-closure.md](hypergeometric-fetch-closure.md) (the deferred draw-odds refinement).

## Thesis (established this session)
Replace the develop rung's **1-ply-then-greedy** approximation (`_develop_rollout_line` varies only the
FIRST action, then `_simulate_line` plays the rest greedily) with **exhaustive within-MY-turn search**: walk
every deterministic decision sequence, transposition-collapsed, chance-node-bounded, and score the leaf
states. It is the missing, cheapest, and **only fully-sound** rung of the stack (own legal moves — no
opponent model, no net).

## Why (the motivating measurement)
- Honest lab metric: the leaf picks the human's option as the **SOLE** top only **~5%** (2/37 lucario,
  14/267 full); the "65%" was ties (avg 3.7). The ceiling is **discrimination**, not accuracy.
- Those ties are largely an **artifact of the greedy continuation**: it commits ONE completion, collapsing
  many first-moves onto the same end-board (ep83661652: Gravity Mountain / Solrock / Riolu → identical board
  → 55/55/55). Exhaustive search compares each line by its BEST completion, so lines greedy homogenised
  separate out — no cross-turn depth required.

## THE CRUX — RESOLVED (probe run 2026-07-16, gate PASSED)
Question was: how many genuinely-DISTINCT end-of-turn states are reachable per turn under full search?
**Answer: they diverge, hard.** Full within-turn search reaches a **median 36 distinct end-boards** per
frame (mean 204, max 1227) where greedy's single completion collapsed them to 1 — the ties were a
**greedy-continuation artifact**, not real equivalences. Premise HOLDS: build it.
- **The twist (why this now pairs with a leaf grill):** those 36 boards collapse to only **~5 distinct
  LEAF values** (median; 3/37 fully blind). Search reaches the boards; the current leaf can't tell them
  apart. So ply-1 = exhaustive search **+** a finer leaf — complementary, not either/or. See
  [board-state-valuation-grill.md](board-state-valuation-grill.md), whose whole job is the 36→5 gap.
- **Gate 0 fixed the ORDER — LEAF FIRST.** An A/B of exhaustive-search + the CURRENT leaf vs the 1-ply
  rung on the honest SOLE-top is a **wash** (shared-top 67% vs 61%): deeper search over today's coarse
  leaf finds as many leaf-mistakes as it fixes. So build the **leaf** (board-state-valuation-grill, now a
  decided spec) FIRST; this search only starts paying once the leaf discriminates — its acceptance gate is
  "re-run Gate 0 and beat the 1-ply rung." `scratchpad/gate0_ab.py`.
- **Cost:** node counts median ~64, only 6/37 hit the 4000-node cap. The probe's minute-scale wall-times
  are its re-begin-per-node inefficiency, NOT the search — a proper *incremental* walk over a few thousand
  states is seconds. Tail turns (>4000 states) are where the speced budget-cap + fallback earn their keep.
- Probe lives at `scratchpad/transposition_probe.py` (reproduce; promote to a fixture if it recurs).

## Grill questions (the meat)
1. **Search structure.** State key for the transposition table (which fields define legality-equivalence:
   board + hand + deck-signature + energy-attached-this-turn + supporter-used + retreat-used + abilities-
   used?). Node/time budget + greedy fallback — what cap? Reuse the **lethal solver's** within-turn line
   enumeration (`_win_line` / `_family_win_candidates` already walk multi-step develop+attach+evolve+attack
   sequences) rather than a fresh walker?
2. **One search or a ladder?** Does exhaustive search *replace* the develop rung, or generalise the whole
   planner — win / KO / develop as ONE search with different leaf verdicts? Soundness boundary: the win
   rung (sound lethal) must still preempt; the leaf stays capped sub-prize (hard-rung invariant).
3. **Chance nodes = the search horizon.** Shuffle (Lillie's/Judge/Harlequin) and coins: STOP, don't expand
   past. For EXECUTION, commit up to the chance node, play it, observe, **re-walk** from the resolved state
   (replan at chance boundaries — bounds the tree for free).
4. **Valuing a chance node (so we can DECIDE to enter one).** Re-walk defers the *continuation*, not the
   *decision* — comparing "shuffle → ???" to a deterministic line needs an EV for the draw. **Reuse the
   hand-swing oracle** (ADR-0060, `strategy/refresh.py` `hand_swing` + the ADR-0024 keep-value / probable-
   miss guards) as the COARSE chance-node state-value — reframed from "score the action" to "EV of the
   post-shuffle position." The FINE version (P(draw the specific out), tutor-closure) is the deferred
   hypergeometric note. Grill: card-swing EV vs evaluate-at-node (board pre-draw) vs a hybrid.
5. **The leaf still values the leaves.** Full search yields MORE distinct boards → the leaf now ranks
   genuinely-different states → end-board features (Group 2) finally earn keep. Now-relevant enabler:
   **hand-visibility plumbing** (the sim's end-obs is opponent-perspective / hand-blind — read my hand from
   the search STATE). Note prize-race is rank-inert here (proven) — a general-eval term, not this.
6. **Gate + integration.** Always-on for develop turns, or a `_develop_should_fire`-style trigger? Cost on
   draw-engine turns (Lunatone draw-3 chains) — is the chance-node horizon + transposition + cap enough to
   keep it affordable (Kaggle ~10min/match; today's rung ~1s/game)?

## Scope
- **IN (ply-1):** exhaustive within-MY-turn search, transposition table, chance-node horizon + re-walk,
  coarse chance-node EV (reuse refresh oracle), leaf valuation of end-states, hand-visibility plumbing.
- **OUT (later):** 2-ply opponent lookahead (heuristic), the ML value net (ADR-0053), the fine
  hypergeometric fetch-closure, per-card situational valuation.

## Success measure
On the lab (honest **SOLE-top** + avg top-tie), exhaustive search beats the 1-ply rung — *and* the measured
transposition rate / per-turn timing confirms it's both discriminating and affordable. A/B via the leaf-lab
harness (extend `scratchpad/leaf_ab.py`'s ranker set with an exhaustive-search column).

## The stack this sits in
exhaustive within-turn search (SOUND, this spec) → a decent leaf → 2-ply opponent (heuristic) → value net.
Ply-1 is the missing bottom rung — cheapest and the only fully-sound one.
