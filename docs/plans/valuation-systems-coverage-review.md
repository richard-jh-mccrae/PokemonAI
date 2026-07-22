# Valuation systems — coverage review & ranked next work (handoff, 2026-07-20)

A plain-language map of the Worth / Odds / Gates (+ Needs assignment) systems: which decision
variants they cover today, how well, and what is uncovered but buildable. Written at the end of the
keep-value-v2 session line (WP-N1 → N8); every claim below was verified against the code/benches on
2026-07-20. Companion handoffs: `keep-value-v2-session-handoff.md` (the build ledger + open
threads) and `turn-planner-snipe-and-gust-scenarios.md` (the two planner scenarios, corpus-scoped).

## The systems in one breath each

- **Worth** (`src/common/card_worth.py`) — every card priced in ONE points currency by its JOB
  (role/tag tiers: wincon 30, energy 8, engine band 8–20, ACE SPEC 25). No gut-feel numbers.
- **Odds** (`src/common/deck_odds.py`) — pure probability: draw-window hypergeometrics, the
  prize-split estimate, engine-assisted reach. Opinion-free.
- **Gates** (`src/common/gate_library.py`) — reality checks that zero a price: dead evolution,
  exhausted fetcher, need-already-met, this-turn deadlines (closing edges), once-per-turn quotas.
- **Closure** (`src/common/fetch_closure.py`) — the search graph: which tutors reach which cards,
  so redundancy discounts are derived, never asserted.
- **Needs** (`src/common/needs.py` + `pilot._resolve_needs`) — the assignment engine: list what
  the BOARD needs (slots), match held cards to needs exactly, a card's value = its marginal need
  coverage × (1 − the odds the deck refills that need anyway).

## Coverage by decision variant

| Variant | Status | Where | Notes |
|---|---|---|---|
| **Forced discard** | ✅ LIVE, new engine decides | `needs_keep_value` ON; `_needs_v2` | 12/12 vs the correction corpus; duplicates/fuel/successor all priced. The most mature site. |
| **Shuffle-refresh** (Judge/Harlequin/Lillie's) | ✅ covered, OLD brain decides | `_refresh_swing_tactical` (v1); v2 shadow | v2 sign-disagrees on 11/83 after the WP-N8 rulings. The swap is unblocked but not benched-clear (bar: flips ≈ 0). |
| **Gusting — which target** | ✅ covered | `doctrine_gust._gust_target_tactical` | KO-gated, prize + sunk-energy + snipe-synergy ranked; ADR-0066 ruled ceiling. |
| **Gusting — whether (tempo trade)** | ⚠️ partial | same | "CAN'T-KO → don't gust" is gated (f31). The can-KO-but-bad-trade case (their full-health attacker promotes back) has NO corpus anchor — see the planner-scenarios handoff §B. |
| **Energy attachment** | ❌ NOT one-currency — the flagship gap | ~22 rules in `baseline_energy.py` + deck rules | 41 `misattachment` corrections (largest pile). Grill seed EXISTS: `attach-valuation-grill-spec.md`. The Game-B instinct ("attach to the Staryu — race the successor's energy clock") is exactly its P-term. |
| **Evolving — evolve now** | ✅ covered | deploy-now spike, dead-evolution gate, rush_evolve | Closing edge: an evolve-now can't be banked. |
| **Evolving — DELAY (ability income)** | ✅ covered BY HAND, per-deck | `dragapult_ex/strategy.py` `hold-evolution-until-attacker-ready` | Delays Drakloak→Dragapult until the body carries 2 energy for Phantom Dive, keeping Recon Directive digging meanwhile. The GENERAL systems have no concept "evolving destroys the pre-evo's ability" — generalization candidate below. |
| **Snipe targeting** | ⚠️ 16/19, three known misses | `baseline_snipe.py` + `_target_*` signals | The 3 misses are 3 DIFFERENT gaps (discard-fuel gauge, already-evolved printed damage, a pure tie) knotted into shared machinery — grill before building (planner-scenarios handoff §A). Threshold-race targeting not modeled. |
| **Retreat / switch / who's Active** | ✅ covered | promote/retreat baselines; leaf promotion-ease lift (2026-07-20); answer-doom keep pricing | A Switch under doom now prices at what saving the Active preserves (WP-N8 R1). |
| **Healing** | ✅ covered | clutch_heal tags, answer-doom slot, don't-waste rules | |
| **Bench / deploy / fetch** | ✅ covered | Poffin/ball composers, bench baselines, fetch closure | |
| **Discard-as-resource (MY fuel)** | ✅ covered | fuel slots (pitch side), Aura-Jab class detection | Pitching a matching energy is progress, not loss. |
| **Opponent read — their board clock** | ✅ covered (new) | WP-N7 deny slots, `_opp_turns_to_ready`, posture Briefs | Assume-the-accel pessimism is doctrine (ADR-0064). |
| **Opponent read — their DISCARD (damage-scaling)** | ✅ covered | `card_text.parse_attack_scaling` `atk_discard_energy` → `_damage_context(attacker_is_me=False)` → combat KO oracle | A Riptide-class scaler (Kyogre: 20× Basic `{W}` in *their* discard) is priced EXACTLY into `active_doomed`/`incoming_active_damage` — the discard is open info in both directions. Deck-discard scalers (Abomasnow Hammer-lanche) handled via `hiddenPerUnit`. Corrected 2026-07-22 (was mislabelled "not read at all"). |
| **Opponent read — their DISCARD (as a resource)** | ❌ not read | — | The unread half: discard as a RECOVERY/recursion pool — energy/Pokémon they can re-attach or fetch back (Mega Lucario ex reloads `{F}` from discard; Night Stretcher/Super Rod recursion), and line-liveness (can they re-power/re-evolve a KO'd threat). Feeds threat-persistence + gust/deny valuations. Generalize via a `card_functions` tag for attacks/abilities that use their own discard. |
| **Attack / lethal / KO race** | ✅ covered (separate arc) | combat/objectives/lethal verification | Out of this review's scope; noted for completeness. |

## Uncovered-but-buildable, ranked by payoff

1. **The energy-attach equation** — one-currency oracle for the attach. Biggest correction mass
   (41 + shares of 111 sequencing / 27 slow-setup), design seeded
   (`attach-valuation-grill-spec.md`), machinery (worth/odds/gates/needs) all built. Run the grill,
   build in shadow, swap per the seam-D pattern.
2. **Opponent-discard reading (resource half only)** — the damage-scaling half is DONE (Riptide-class,
   see the coverage table). What remains: read the discard as a RECOVERY pool — an always-on pure signal
   ("their discard holds N energy of type T / these recoverable Pokémon"), generalized by a `card_functions`
   tag for attacks/abilities that use their own discard (Mega Lucario ex `{F}` reload, Slowpoke/Night
   Stretcher recursion), feeding threat-persistence + gust/deny valuations. NOTE the snipe "fuel-gauge"
   motivation is retired: its one corpus anchor (83667237-107) was ruled 2026-07-22 to be a THRESHOLD-RACE
   frame, not a discard read (see the snipe/gust scenarios handoff). Read-always per user (free info).
3. **The snipe-targeting grill** — the 3 corpus failures + the threshold-race rule, ruled
   frame-by-frame, then a `snipe_sweep` bench (23 DAMAGE frames; hold 16, fix the ruled). Do NOT
   blind-build: root causes are in shared threat-rank + prize-guard machinery
   (planner-scenarios handoff §A).
4. **Generalize evolution-timing** — derive "delay the evolve" from ability income vs attack
   readiness vs the energy clock, so the Dragapult hand rule becomes a fold candidate instead of
   deck text. Needs-vocabulary shaped (the draw-engine need Drakloak fills TODAY vs the attacker
   need Dragapult fills LATER).
5. **The gust tempo trade** — waits on a corpus anchor exercising can-KO-but-bad-trade; flag for
   capture during play (planner-scenarios handoff §B).
6. **Internal follow-ups** (unblocked by WP-N8, each needs its own bench): the refresh-SHED swap
   (bar: sign-flips ≈ 0, at 11/83) and hedge retirement (bar: a sweep showing v2 never prices below
   the shipped decider with the floor off). Plus the two LIVE-ladder-gated items: the `_DISCARD`
   rung fold and ladder evidence for the armed flags (post dev-window).

## Standing cautions (repeat offenders)

- Every build above must hold the discard corpus 12/12 and the full suite; shadow-first for
  anything touching a live decider; fresh Pilot per replay; verify card facts at source.
- Adding a big positive term silently voids guards calibrated against the old scale.
- Blind pokes at shared machinery (threat rank, prize guards) risk the frames that already pass —
  grill first, bench always.

## Opponent-read grill findings (2026-07-22) — logged, not yet built

Session grilling the two opponent-read rows. Rulings + findings, in order surfaced:

- **`82749168-38` refuted (user ruled: pilot right).** The labelled snipe is onto a **benched**
  Dragapult ex — Tera prevents all attack damage while benched (rulebook App.6), so the 50 rider
  does 0; `dont-snipe-a-benched-tera` already ranks it below the real Hoothoot snipe. Drop it from
  the "3 snipe misses" → snipe is **16/18**, two real gaps (discard-fuel *retired* below + the pure
  Riolu transposition, unfixable).
- **`83667237-107` is a THRESHOLD-RACE frame, not discard-fuel (user ruled).** Makuhita is the pick
  because it's the only benched body a 2-turn Jetting Blow snipe (50+50 ≥ 80 HP) can KO before the
  finisher lands (+ prize-cap avoids the 2nd Mega + the chip banks for a later gust-KO). The
  discard `{F}` is a **risk** to the plan (they can evolve Makuhita out of range), not the motive.
  ⇒ the snipe **discard-fuel gauge has no corpus anchor** — retired; threshold-race (#3) is the real
  driver. Live retest: pilot takes an on-path 110-body (+12), Makuhita scores 0 (`reviewed.json`
  "fixed" is stale — ADR-0044 only killed the 2nd-Mega pick).
- **Discard damage-scaling is already read** (Kyogre Riptide class) — coverage row above corrected.
  Built `discard_energy_recur` tag (Mega Lucario ex 678, Archaludon ex 190; `recycle` reused for
  Slowpoke 162) as inert vocabulary; the `_opp_turns_to_ready` wiring is the pending #2 proposal.
- **Kyogre/Mega Abomasnow ex recycling deck — two logged findings:**
  - **(a) Denial is futile vs a recycler.** Riptide shuffles its scored `{W}` back into the deck and
    Hammer-lanche re-mills it — the `{W}` pool is renewable, so Crushing-Hammer-class energy denial
    on them is near-worthless. Doctrine for the `kyogre_mega_abomasnow_ex` Brief; a candidate consumer
    of the `recycle`/`discard_energy_recur` vocabulary. The live *discard* read is NOT fooled by the
    recycle — reading the live pile each turn tracks the pulse correctly.
  - **(b) Opponent Hammer-lanche is under-read.** It is a HIDDEN deck-density scaler (`100×` Basic
    `{W}` off the top 6 of *their* deck); `_damage_context` estimates deck density only for
    `attacker_is_me`, so the opponent's ~350-avg nuke prices at its flat base (~0) in the doom oracle.
    Their density is hidden → only a matchup-Brief prior (`opp_deck_basic_water_density` ≈ 0.58) can
    price it soundly. Brief-scoped, not a general read.
- **`dp_stall_gust_false_famine_accel_f70` — the SELF-side of assume-the-accel (user ruled: 100% our
  choice).** Active Dragapult ex 0e, hand holds Crispin (`tutor_energy`). The equation fires a
  famine stall-gust (+105) reading "0e → can't attack". FALSE: Crispin attaches one Basic Energy by
  its effect AND hands a second of a different type, which the unused manual attach then plays —
  Dragapult ex reaches `{R}{P}` THIS turn = **Phantom Dive 200 + 6 counters** (verified: all three
  hand cards are Supporters, so Boss's-stall vs Crispin-attack is mutually exclusive — the stall
  forgoes the 200). Fix at value altitude, NOT a stall-gust gate: a **self reachable-attach
  affordability oracle** symmetric to ADR-0064 `reachable_incoming` — budget this turn's attaches =
  `manual_attach (if unused)` + the attach effects of `tutor_energy`/`energy_accel` cards in hand,
  and model the FULL budget (reaches the 2-cost `{R}{P}`, not just the cheapest `●`). Famine = the
  cheapest attack unpayable even with that budget. Dissolves the stall-gust premise for every
  consumer (stall-gust, posture, doom) with no new rung/gate.
- **Gust-target/whether cluster — OWNED BY ANOTHER SESSION (gust-value equation in progress).**
  User confirmed the anchor `86089120-14` (turn-2 setup gust worth **0**: no KO, nothing stranded,
  develop instead) and it gives Scenario B the corpus ground the planner handoff said it lacked
  (siblings: `85785067-41` gust the support ex to delay; `85163079-30` gust a KO-able wincon;
  `85164131-22` an answerable body is worth 0 to touch). The unified read — gust value =
  `KO_prizes + tempo_denied(role, turns_out_of_position) - return_threat` - is being built in a
  separate session; do NOT author it here. Logged for cross-reference only.
