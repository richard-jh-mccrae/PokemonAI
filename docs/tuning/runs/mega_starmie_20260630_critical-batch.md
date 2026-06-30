# /blunder-buster round — mega_starmie critical batch (build 6fd8a19), 2026-06-30

Corrections: `data/corrections/mega_starmie_20260630_6fd8a19/corrections.jsonl` (7; 3 machine-CRITICAL).
Built in worktree `blunder-critical` off `fa9baf5` (clean HEAD, no Tool-doctrine WIP) because the live
tree was being edited (ADR-0028 build). C4/C5/C6/C7 are orthogonal to that WIP — verified identical
featurization with/without it. Suite: **656 passed, 9 skipped**.

## Authored this round (4 fixes)

### C4 — `discard-the-hand-duplicate` (CRITICAL)  [ep82867148 f48, wasted_resource→discard]
Blunder: a forced discard-2 pitched **Boss's Orders + Harlequin** (singleton disruptors score 0 → lose
the index tie-break) while holding 2× Lillie's + 3× Mega Starmie ex. Fix: a new keep-value floor — a
card held **2+ in hand** (fungible Energy excluded) is the lowest-keep pitch, so a singleton disruptor
is never shed over a duplicate. New infra: `Board.hand_duplicate_ids` + `Context.card_is_hand_duplicate`
+ `_hand_duplicate_ids` (excludes `CardType.BASIC_ENERGY/SPECIAL_ENERGY`), `context._BASIC_ENERGY/_SPECIAL_ENERGY`.
Seed **+12** (band: > the −8 engine-keep so a duplicate Lillie's nets +4; < 30 so a duplicate Mega stays −18, protected).
- Verifier: **passed** (cluster satisfied, **0 regressions** across the corpus). Retest **[0,3]→[1,2] fixed=True** — pitches the 2 duplicate Lillie's, keeps both disruptors + all wincons + both energies.
- Tests: `test_discard_the_hand_duplicate_pitches_a_duplicate_effect_card_over_a_singleton`, `…_excludes_fungible_energy`.

### C5 — `hold-wincon-with-base-dont-shuffle` (CRITICAL)  [ep82867148 f52, sequencing]
Blunder: played Lillie's (shuffling 3 Mega Starmie ex into the deck) while a **benched Staryu base** was
ready to evolve them. `hold-wincon-dont-shuffle` (−25) was overpowered by `dig-before-commit` (+20) +
`refresh-when-hand-is-dead` (+8) → Lillie's +3 → tier-3, sequenced before the attack. Fix: a stronger
hold when the held wincon has a **base in play** (`line_preevo_in_play`) — deploy-soon, so don't bury it.
Seed **−15** (stacks on −25 → nets the shuffle below 0 vs +28). No new infra (existing signals).
- Verifier: **passed** (0 regressions). Retest **[0]→[2] fixed=True** — Lillie's −12 → tier-4; the Turbo Flare attack is taken, the held Mega is kept to evolve next turn.
- Tests: `test_hold_wincon_with_base_dont_shuffle_fires_when_a_base_is_benched`, `…_silent_when_no_base_is_in_play`.

### C6 — `_retreat_to_lethal_tactical` stand-down (CRITICAL, tactical core)  [ep82867148 f62, bad_retreat]
Blunder: retreated Cinderace into an energised Staryu even though **Cinderace already KOs** the 20-HP
opponent — the retreat-to-lethal lookahead credited the Staryu's equal KO at 1000.901 (the position
epsilon tipped it past the attack's 1000.9), making retreat tier-0. Fix: the lookahead now stands down
whenever the **current Active already takes this KO (or a better one)** — `best ≤ my_active_ko` → 0 — so
it fires ONLY for a strictly-better bench KO (e.g. a snipe rider). Replaces the narrow `active_is_wincon
and _can_ko` guard. W-route-invisible (tactical), so it never surfaced as UNSATISFIED.
- Retest: retreat tactical **1000.901→0** (score −25); the agent no longer retreats — it develops (Buddy-Poffin, tier-0) then KOs with Cinderace, leaving the energised Staryu benched to evolve. **[9]→[7]**, first-dev-differs (the KO is still taken, attack-last). All 3 existing `_retreat_to_lethal` tests preserved (test #1 still retreats — its bench KO is strictly better via snipe).
- Test: `test_retreat_lethal_stands_down_when_the_active_already_takes_an_equal_ko`.

### C7 — attach-target tie-break (`attach_to_needy_line`)  [ep82867148 f87, soft]
Blunder: attached the spare Water to a benched **Cinderace** (off-line opener) over a **Staryu** (the
wincon line base) — both needy bench bodies tie at +10, index tie-break picked Cinderace. The human's
literal label (Ignition→Staryu) is **refuted** (dominated: `dont-waste-discard-energy` soundly prefers
the reusable Water over wasting the one-shot Ignition on a non-attacking bench body). Intent fix: a
**decide()-only ordering tie-break** (W-route-invisible, like attack-last) prefers an attach to a needy
Line body among EQUAL-score attaches. A fitted weight was rejected — collinear with `power-up-attacker`,
it destabilised the W-route fit (regressed the covered ep82228017 f4 in fitted-weight space at every
weight ≥1, though f4's real decide() is unchanged). New infra: `Context.attach_target_is_line_member`,
`OptionTrace.attach_to_needy_line`, secondary sort key in `_evaluate`.
- Retest **[7]→[8]** — Water→Staryu (line base), not Cinderace. f4 stays correct (no regression — confirmed real decide()).
- Test: `test_attach_tiebreak_prefers_the_line_base_over_an_off_line_body`.

## Covered (by the live ADR-0028 WIP — verified via real `decide()` on the live tree, 2026-06-30)
- **C1** ep82866415 f43 — `deploy-hp-tool` (+40) attaches the Cape (tier-2) + `hold-irreplaceable-tool-dont-shuffle` (−30) suppresses Lillie's; the agent digs then deploys the Cape — no longer shuffles the ACE SPEC away (first-dev-differs).
- **C2** ep82866415 f48 — `deploy-hp-tool` deploys the Cape on the Active win-condition (ADR-0028 wincon-default; the bench-Staryu snipe target is the deferred §5c refinement, and the ADR rejected that reasoning for this frame).
- **C3** ep82867148 f34 — degenerate (chosen==correct==Attack); the play-Ultra-Ball-to-develop-a-recipient intent is carried by `develop-turbo-flare-recipient` + `fetch-base-before-stranded-payoff`.

## Completion ledger
| Corr | Episode/frame | CRIT | Outcome | Evidence |
|---|---|---|---|---|
| C4 | 82867148-48 | ✓ | **fixed** | discard-the-hand-duplicate; Verifier passed +0 reg; retest [0,3]→[1,2] |
| C5 | 82867148-52 | ✓ | **fixed** | hold-wincon-with-base-dont-shuffle; Verifier passed +0 reg; retest [0]→[2] |
| C6 | 82867148-62 | ✓ | **fixed** | _retreat_to_lethal stand-down; retreat tac 1000.9→0; retest [9]→[7] develop-then-KO |
| C7 | 82867148-87 | – | **fixed (intent) / refuted (literal)** | attach tie-break, retest [7]→[8]=Water→Staryu; Ignition label dominated |
| C1 | 82866415-43 | – | **covered** | deploy-hp-tool + hold-irreplaceable-tool-dont-shuffle (live WIP) |
| C2 | 82866415-48 | – | **covered** | deploy-hp-tool (live WIP) |
| C3 | 82867148-34 | – | **covered** | degenerate; develop-turbo-flare-recipient + fetch-base-before-stranded-payoff |
