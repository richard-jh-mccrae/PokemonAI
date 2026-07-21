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
| **Opponent read — their DISCARD** | ❌ not read at all | — | Feeds both the snipe fuel-gauge rule and threat reads. |
| **Attack / lethal / KO race** | ✅ covered (separate arc) | combat/objectives/lethal verification | Out of this review's scope; noted for completeness. |

## Uncovered-but-buildable, ranked by payoff

1. **The energy-attach equation** — one-currency oracle for the attach. Biggest correction mass
   (41 + shares of 111 sequencing / 27 slow-setup), design seeded
   (`attach-valuation-grill-spec.md`), machinery (worth/odds/gates/needs) all built. Run the grill,
   build in shadow, swap per the seam-D pattern.
2. **Opponent-discard reading** — a small pure signal ("their discard holds N energy of type T /
   these trainers") consumed by threat ranks and the snipe gauge. Prerequisite for 3.
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
