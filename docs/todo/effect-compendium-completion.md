# Effect-Compendium Completion Plan (ADR-0032 follow-through)

The compendium core is shipped (96.6% engine-verified, over-prediction 0). This is the attack
plan for what remains — each phase is one working session, independently mergeable, TDD.

## P1 — Discard-visibility scalers + the Incoming context hole  ✅ DONE 2026-07-02

**Fact base:** `PlayerState.discard` is a full visible `Card` array for BOTH players; Riptide-class
"for each … Energy in your discard" is attacker-relative → for the opponent's Kyogre, "your" = THEIR
discard, which we see. Family: attacks 15, 446, 1042 (+ any the sweep re-confirms).

1. `AttackStat` scaler filter: `scaleVar="atk_discard_energy"` + a `scaleEnergyType` field
   (Riptide {W}=3); parser family for "for each (Basic) {X} Energy card in your discard pile".
2. **Close the Incoming context hole (the real fix):** `_predicted_max_damage` currently passes NO
   context — an opponent scaler reads 0 threat. Build the attacker-relative context inside it
   (opp hand count, opp bench, opp Active energies, opp discard typed-counts) from the state the
   Board already carries; my-attack context gains my typed discard counts.
3. Verify: unit goldens (opp Kyogre with 5 {W} in discard → Incoming 100) + an attrition-pass
   audit measurement for 1042 if cheap.
4. Rider note: Riptide shuffles the counted Energy back — damage math unaffected; the
   discard-count *drops* after their attack (tracker-free, re-read each turn — self-correcting).

## P2 — Transient-effect tracker (the Frost Barrier family)  ✅ DONE 2026-07-02 (ADR-0033; engine-verified Reflect −40)

**Fact base:** 138 attacks carry "during your (opponent's) next turn" effects; the obs exposes NO
per-Pokémon effect state → must be TRACKED from logs (deck-tracker precedent, `OwnCardModel`).
ADR-worthy: a new match-scoped model + expiry semantics. Suggest `/grill-with-docs` → ADR-0034+.

1. **Exhaustive sweep** of all 1556 attack texts → classify every next-turn clause:
   takes-less (17), prevent-all (6), defender-can't-retreat (29), self-can't-attack (2),
   next-turn damage bonus, immunity variants, attack-locks ("can't use that attack"), the rest →
   a closed field vocabulary on `AttackStat` (`grantsNextTurnReduction`, `…PreventAll`,
   `locksDefenderRetreat`, …) + a ledger for one-offs.
2. **`TransientTracker`** (`common/`): consumes each obs's `logs`; an `ATTACK` log + the attack's
   transient fields → `{side, serial, effect, expiry}`. Expiry rules to pin down in the grill:
   turn boundary, leaving the Active, evolving, KO (verify vs rules.md / probe the engine).
3. Consumers: oracle (a live reduction/prevent on the defender joins `compute_active_damage` —
   pierced by `ignoresEffects`, matching the Drednaw finding); Incoming (my body's live protection
   shrinks the estimate → doom/heal/tool math); Board signals for the locks (a retreat-locked
   opponent, a can't-attack turn = free develop).
4. Engine-verify: probe an attacker using Frost Barrier, measure next-turn dealt = base − 30;
   goldens for prevent-all and a lock.

## P3 — Deviations + small closures  ✅ DONE 2026-07-02 (CI gate wired; riders single-sourced; condition gates evaluated; hidden pigeonhole/EV; counter/prize scalers; restriction-observation boards via agent)

- **CI audit gate:** bounded audit in CI (the 26 flag attacks + Crustle/Drednaw panels, ~1 min) +
  `diff_attack_audit` step failing on any NEW over-prediction. Full-pool run stays manual.
- **Restriction-observation boards** (the grilled H3 mechanism): probe boards seeded with a damaged
  Mega AND non-Mega → derive clause `restriction` from which targets the select OFFERS; replace the
  hand-authored restriction overrides where measured.
- **Fold the legacy dicts:** route `bench_snipe`/`recoil` reads through `_attack_stat`; drop the 4
  parallel dicts from `Pilot.__init__` (+ `tune.py`, fixture). Mechanical, suite-gated.
- **`hidden_units` wiring:** pigeonhole floor via the exact deck tracker + EV via `deck_odds` for
  the 3 deck-discard attacks; feeds the existing `context["hidden_units"]` seam.
- **Planner condition gates:** evaluate the board-checkable clause `condition`s
  (Bianca `remaining_hp_30_or_less`, Jumbo `energy_3_plus`) instead of fail-closed skipping.
- **Residual ledger:** fit the remaining visible-state families (per-2-cards, "for each damage
  counter on …"), re-generate overrides, re-diff — target < 50 unique unmodeled attacks.

## P4 — Strength validation & ship  ◐ mirror-smoke DONE (6/6 clean, full wiring); TRUE A/B pending: needs the main checkout's Build Ledger — `python tools/sim/battle.py <old-build-id> mega_starmie -n 40`

- Self-play A/B: new build vs pre-compendium build (mirror + vs the #6 reference deck), enough
  games for a signal; `check_agent` Playability/Deployability gates; then merge PR + submit.

**Ordering:** P1 → P2 → P3 → P4. P2 is the only one needing a design session first; P1/P3 are
direct TDD. All phases append to the audit's verification story for the Strategy writeup.
