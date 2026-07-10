<!-- Strategy Proposal — SPLIT OUT of line-readiness-signals-model-the-multi-stage-line during the
/update-strategy grill (2026-07-09). The distance fix (applied) stops f14's CRITICAL strand but lands
on a redundant 2nd Dreepy, not Budew; making Budew specifically win is a distinct develop-preference
finding, captured here. Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md -->

## fetch-fresh-disruptor-over-redundant-in-play-base
- id: fetch-fresh-disruptor-over-redundant-in-play-base
- source: blunder-buster
- target_layer: general-hypothesis
- for: general
- candidate_signal: `card_is_line_preevo` + a NEW "a copy of this base is already in play" signal (`card_base_copy_in_play` — Board/Context, from visible zones); the `item_lock` tag (fresh disruptor edge) and/or a multiprize-ex penalty at `_TO_HAND` on a thin bench. Reconciles the two line-piece boosts that over-fire on a REDUNDANT base: `fetch-base-before-stranded-payoff` (+20, doctrine_fetch.py) and `prefer-wincon-line-piece` (+18).
- verification_contract: verifier
- provenance: correction 85045840:f14 (CRITICAL) | fixture tests/fixtures/corrections/dragapult_fetch_stranded_payoff_f14.json | split from `line-readiness-signals-model-the-multi-stage-line` (data/strategy/proposals/blunder-20260709-dragapult_ex.md, applied 2026-07-09) | [[wroute-satisfied-not-fixed]]
- status: open

**Spec (authoring spec — thin fodder):**
f14 (CRITICAL), turn 2: Active a lone **Dreepy (0e)**, bench EMPTY, its immediate pre-evo **Drakloak in
the DISCARD**. At an Ultra Ball grab the agent took the two-hop **Dragapult ex** (strands). The applied
distance fix (`wincon_base_deployable` → require the IMMEDIATE pre-evo) already **stops the strand**
(Dragapult ex no longer grabbed — pinned by
`test_blunder_20260709_line_readiness.py::test_f14_strand_is_stopped...`). But the human's `correct` is
**Budew** (develop the empty bench with a live **item-lock** disruptor), and the distance fix alone lands
on a **redundant 2nd Dreepy**, not Budew. The scoring, post-distance-fix (verified this session):

| grab | rungs | score |
|------|-------|-------|
| **2nd Dreepy** | prefer-wincon-line-piece +18, fetch-base-before-stranded +20 (now fires), fetch-a-starter +12 | **+50** |
| Meowth ex | fetch-a-starter +12 | +12 |
| **Budew** (`correct`) | fetch-a-starter +12 | +12 |

Two things are needed for Budew to WIN, and neither is the distance fix:
1. **Stand down the two line-piece boosts on a REDUNDANT base.** `fetch-base-before-stranded-payoff`
   (+20) and `prefer-wincon-line-piece` (+18) are meant to secure *a* base to unblock the line — but a
   copy of this base is **already in play** (the Active Dreepy), so a 2nd adds no line progression (the
   real blocker is the discarded Drakloak). Gate both to **not** `card_base_copy_in_play` → the 2nd
   Dreepy drops to fetch-a-starter +12.
2. **Break the resulting +12 tie toward the fresh disruptor.** At +12 the redundant Dreepy, Meowth ex,
   and Budew tie, and option-index picks **Meowth ex** (a 2-prize ex, opt 0) — still not Budew (opt 1).
   Add a small edge for a fresh `item_lock`/disruptor Basic at a thin-bench `_TO_HAND` grab (and/or a
   mild penalty for tutoring a multiprize **ex** to hand in setup) so Budew wins.

**Why it wins:** "when your bench is empty, develop a FRESH body (a free disruptor) — don't tutor a
second copy of a base you already have, and don't bank a 2-prize ex to hand" is general develop
discipline; silent for decks whose grabs aren't redundant bases. **Verify:** decide() on
`dragapult_fetch_stranded_payoff_f14.json` flips to `correct=[1]` Budew; inert on single-hop decks and on
non-redundant grabs (Score-Diff / suite-green). Card facts (Budew `item_lock`, Meowth ex 2-prize) are
engine ground truth — verify at source before shipping.
