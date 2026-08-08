<!-- Strategy Proposal — SPLIT OUT of spend-boss-orders-on-the-ko-not-setup during the /update-strategy
grill (2026-07-09). The clean KO-sequencing half (f79/f81: a KO-enabling gust rides tier 0) was applied;
these two are distinct mechanisms. Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md -->

## gust-for-the-stall-stands-down-in-valueless-setup
- id: gust-for-the-stall-standdown-in-setup
- source: blunder-buster
- target_layer: general-hypothesis
- for: general
- candidate_signal: `gust-for-the-stall` (+10, doctrine_gust) fires on `active_doomed and gust_best_ko_prizes==0 and stall_target_exists`, and as a Supporter it tiers to 1 in `_finish_turn_last` — AHEAD of a develop attach (tier 2). Needs a "the stall buys no real value / a develop is the better use in setup" gate, WITHOUT demoting the famine hard-stall `stall-gust-over-dev-when-starved` (+95, gated `not active_attack_payable`) which must still beat develop.
- verification_contract: verifier
- provenance: correction 85046350:f10 | fixture tests/fixtures/corrections/dragapult_gust_wasted_in_setup_f10.json | split from `spend-boss-orders-on-the-ko-not-setup` (data/strategy/proposals/blunder-20260709-dragapult_ex.md, applied 2026-07-09)
- status: applied

**Spec (authoring spec — thin fodder):**
f10, early setup: the agent plays **Boss's Orders** (`gust-for-the-stall` +10) to drag a Snover Active for
a marginal stall, over **attaching {P} to the Dreepy** (develop, +10). Both score +10, but Boss's is a
Supporter (tier 1) and the attach is tier 2, so the gust wins the sequence — the human wants to **develop
and save the premium Boss's Orders**. The stall-gust is a stated LAST resort ("only wins the slot when
nothing else helps") but the tier-1 Supporter placement makes even a +10 stall beat a develop.

**Why it's split (the hazard):** a blanket "stall-gust loses to develop" would ALSO demote the famine
hard-stall `stall-gust-over-dev-when-starved` (+95), which DELIBERATELY beats develop when I can't pay any
attack (ep83457493 f20). Both fire on the SAME Boss's PLAY option (they stack), so the fix must distinguish
the generic +10 setup stall (yield to develop) from the +95 famine stall (beat develop) — by score band, by
a `not line_ready`-and-develop-available gate on `gust-for-the-stall` only, or by tiering a non-KO gust as a
commitment (tier ≥2) while the famine rung re-lifts it. **Gate:** f10 flips [1]→[2] (attach); no regression
on the famine stall (ep83457493 f20) or the mega_starmie gust ledger.

**update-strategy verdict (2026-07-10): APPLIED — reframed to "don't gust a HARMLESS Active away."** The
grill's sharper insight: gusting the benched Snover up would send opp's Kyogre (0 Energy → harmless:
Riptide needs discarded {W}, Swirling Waves unpayable) to the Bench to reposition/power up — the gust
ACCELERATES them. So `gust-for-the-stall` (+10) is gated on `opp_active_can_damage_us` (doctrine_gust.py):
only stall when the opp's CURRENT Active can actually hurt us; keep a harmless Active pinned and develop.
Scoped to the +10 mild stall ONLY — the +95 famine `stall-gust-over-dev-when-starved` is NOT gated (its
canonical case ep83457493 f20 is a harmless-NOW but forward-lethal Riolu — exactly when famine-stall MUST
fire; gating it breaks that test). The synthetic `DOOM_ACTIVE`/`KADA` stubs were completed with `attacks`
(they ARE threats — stub fix, not a gate weakening). VERIFIED: f10 flips [1]→[2] attach; test_gust.py
31/31 + full suite green; pinned by test_blunder_20260710_split_fixes.py::test_f10_...

---

## poffin-whiff-guard-covers-exhausted-bench-fill
- id: poffin-whiff-guard-bench-fill
- source: blunder-buster
- target_layer: general-hypothesis
- for: general
- candidate_signal: extend the whiff guard (`dont-search-an-empty-deck` / `search_targets_exhausted`, doctrine_fetch) to a Buddy-Buddy Poffin BENCH-FILL fetch when no fetchable ≤70-HP Basic remains in the deck (the sound deck oracle / `deck_tracker`), so `prefer-bench-fill-first` (+15) stands down on a fetch that can place nothing.
- verification_contract: verifier
- provenance: correction 85046350:f79 (CRITICAL — the gust half is applied; this is the co-fix) | fixture tests/fixtures/corrections/dragapult_poffin_whiff_take_gust_ko_f79.json | split from `spend-boss-orders-on-the-ko-not-setup`
- status: applied

**Spec (authoring spec — thin fodder):**
At f79 the agent's Buddy-Buddy Poffin **whiffs** — the deck holds no fetchable ≤70-HP Basic to bench, so
the bench-fill places nothing (the human saves it as Ultra Ball fodder). The applied KO-sequencing fix
already flips f79 to the gust-KO (Boss's tier 0 beats the tier-0 Poffin), so this is **no longer needed for
the fixture** — but the underlying bug (a bench-fill fetch that can place nothing still scores
`prefer-bench-fill-first` +15) is real and general. **Author:** gate `prefer-bench-fill-first` (and the
bench-fill grab valuation) on the sound deck oracle — stand down when Poffin's fetch set (≤70-HP Basics) is
provably exhausted, mirroring `dont-search-an-empty-deck`. **Gate:** on a synthetic exhausted-bench-fill
state, `prefer-bench-fill-first` does not fire; inert while a fetchable Basic remains; no regression on the
Buddy-Poffin bench-fill tests.

**update-strategy verdict (2026-07-10): APPLIED — root-cause FILTER fix (chosen over gating the rung).**
The bug lived in `_FETCH_FILTERS["bench_fill"]` (doctrine_fetch.py): it read "any Basic", but Buddy-Buddy
Poffin only fetches Basics with **70 HP or less** — so the whiff oracle couldn't see the exhaustion.
Tightened to `0 < st.hp <= 70` (Poffin is the ONLY `bench_fill`-tagged card — verified in
card_functions.json — so it's safe). Now the SOUND guard `dont-search-an-empty-deck` (-60) fires on a
provably-exhausted Poffin; no separate `prefer-bench-fill-first` gate is needed (the -60 dominates the
+15). VERIFIED: at f79 the whiffing Poffin nets **-25** (dig +20 + bench-fill +15 - 60) and the Boss's
gust-KO (+50) stays the pick; full suite green; pinned by test_blunder_20260710_split_fixes.py::test_f79_...
