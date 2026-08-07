# T0 → Turn-Planner disposition — every hypothesis, every correction class, accounted for

**Status:** grilled 2026-07-16. The audit the planner build is validated against: ALL 164 T0 hypotheses
(145 general+doctrine, 16 mega_lucario, 3 dragapult_ex, + per-deck tuned/override weights) and all 362
logged corrections (14 categories), dispositioned against the turn-planner design
([board-state-valuation-grill.md](../archive/plans/board-state-valuation-grill.md) +
[ply1-turn-search-grill-spec.md](../archive/plans/ply1-turn-search-grill-spec.md)). Nothing is dropped: every rule keeps a
named owner; retirement only ever happens per-rule on lab proof (decision below).

## The five classes (decided)

| class | size | owner | mechanism |
|---|---|---|---|
| **A. State-valuation** | ~45 hyps; misattachment(41)+slow_setup(27) corrections | **readiness leaf** | emergent state value: attack/ability-readiness, gates, saturation |
| **B. Spend-costs** | ~40 hyps; wasted_resource(100) — biggest class | **spend account** (new) | `turn_value = leaf(end) − Σ spend_costs(line)` — see below |
| **C. Sequencing crutches** | ~15 hyps; sequencing_error(111) — #1 class | **the search** | ordering emergent from walking all orderings; Phase-3 retire targets |
| **D. Opponent-facing** | ~35 hyps; bad_target(26)+prize-math | **survival term / T3 / 2-ply** + T0 sub-selects | deliberately OUT of the readiness leaf |
| **E. Sub-select scoring** | ~50 hyps (doctrine_fetch family, discards, mulligan) | **T0 stays, inside rollouts** | `_simulate_line` re-runs `decide()` = T0 prices every sub-select within a planned line |

**The architecture sentence:** the planner PROPOSES lines, T0 DISPOSES sub-picks inside them, the leaf +
spend account JUDGE the results, the win rung preempts everything, and non-MAIN contexts stay T0 forever.

## Decision 1 — the two-account turn value (adopted)

```
turn_value(line) = readiness_leaf(end board)            ← class A: state, evaluated ONCE at the end
                 − Σ spend_costs(actions along line)    ← class B: path, legitimately additive
```
Rationale: class-B rules price the CONSUMPTION of a scarce resource (Ultra Ball, `discard_eot` Energy, the
one-per-turn Supporter slot, a held gust/heal) — invisible on the end board (spent cards don't show; hand
hidden), and NOT state (so summing them double-counts nothing — the flaw that killed raw Σ-scores does not
apply to pure spends). This closes the measured conservation residue AND Gate 0's "search amplifies leaf
errors" break mode (wasteful lines now carry their cost). **Spend weights are REUSED from the live T0
weight set** (general + deck overrides + tuned.json) — already corrections-tuned; do not re-derive.
Classification criterion (guard against drift back to state-summing): a spend cost is a negative weight
whose referent is the SPEND itself, conditioned on context — never a score of the resulting board.
Scope: applies to sub-prize line ranking; the sound win rung preempts as always (a win pays any cost).

## Decision 2 — prove-then-retire, per rule (adopted)

Every class-A/C rule keeps firing until the lab proves the planner reproduces it: per-hypothesis, run the
correction corpus with the rule OFF + planner ON → retire only on no-regression (the Phase-3 pipeline +
reviewed ledger, now with a real bench). T0 remains the universal fallback for non-MAIN contexts
permanently. The 362-correction corpus is the standing acceptance suite.

## Per-hypothesis disposition

Class tags: **A** leaf-subsumable · **B** spend account · **C** search-subsumable · **D** opponent layer ·
**E** T0-keep (sub-select / non-MAIN). Dual tags where a rule spans (primary first). "keep" = never a
retire candidate.

### bench (7)
| hypothesis | class | note |
|---|---|---|
| keep-a-bench (60) | A | = the leaf's `floor` term (binary bench-exists) |
| pre-position-attacker (25) | A | next-attacker readiness on the bench |
| develop-a-basic-in-setup (12) | A | body base credit |
| develop-the-wincon-base-first (6) | A | plan-tier / look-through readiness |
| dont-bench-multiprize (−15) | D | prize liability — survival/prize-economy layer |
| dont-bench-onto-their-path (−10) | D | T3 path denial |
| develop-the-accel-recipient (20) | A | precondition gate (accel needs a recipient) |

### energy (22)
| hypothesis | class | note |
|---|---|---|
| power-up-attacker (15/tuned 18) | A | progress×value core |
| concentrate-energy-on-wincon (25/16–23) | A | progress toward BIGGEST attack |
| build-active-wincon (20/24.7) | A | same, active position weight |
| dont-fund-the-non-attacking-body (−12) | A | THE gate (no reachable attack/ability ⇒ 0) |
| dont-power-the-draw-engine (−18) | A | gate + ability-vs-attack value |
| dont-waste-off-type-energy (−12) | A | progress counts only PAYABLE energy (type-aware) |
| prefer-active-attach-in-setup (8/11) | A | position weight |
| attach-energy-last (−5/−2) | C | ordering crutch — search emergent |
| advance-the-accel-pieces (30/33) | A | ability-readiness (accel fireable) |
| use-acceleration (25/27) | A | ability-readiness |
| spread-attach-to-the-needy (15) | E | ATTACH_FROM sub-select |
| concentrate-accel-on-one-line-body (20) | E | ATTACH_FROM sub-select |
| dont-feed-the-doomed (−30/−24..−27) | D | doomed read — survival term |
| arm-the-doomed-active (20) | D | survival + this-turn attack value |
| feed-the-line-for-disruptor-lock (20) | A/C | maneuver = search finds it; lock value = ability-readiness |
| dont-waste-discard-energy (−60) | B | THE canonical spend cost |
| conserve-discard-energy-prefer-basic (−40) | B | spend cost (fungible alternative exists) |
| conserve-burst-when-no-ko (−30) | B | spend cost conditioned on no-payoff |
| dont-attach-discard-energy-turn1 (−60) | B | spend cost (rules.md first-turn) |
| dont-overbuild-the-doomed-wincon (−45/−42) | D | doomed read — survival |
| prefer-reusable-over-burst (−12) | B | spend preference |
| feed-the-firing-accelerator (35) | A | ability-readiness precondition |

### evolution (6)
| hypothesis | class | note |
|---|---|---|
| evolve-into-wincon (40) | A | payoff readiness jump |
| advance-the-evolution-line (15/18) | A | look-through hop discount |
| evolve-the-energized-body-first (5) | A | energy carries through — progress preserved |
| advance-the-energized-line-body-first (5) | A | same |
| prefer-rush-evolve-tutor (30) | E/B | sub-select value + Supporter-slot economics |
| dont-rush-evolve-without-target (−60) | A/B | precondition gate + spend veto |

### opening (6) — all E (pregame contexts; planner never runs there)
keep-a-startable-hand(−40) · honor-preferred-start(−30) · open-the-accelerator(40) ·
open-the-item-lock-starter(35) · dont-open-multiprize-active(−15) · dont-open-with-the-engine(−12).
Position/role logic mirrors the leaf's position_w — keep aligned, never retire.

### heal / disruption / posture / phases (11)
| hypothesis | class | note |
|---|---|---|
| hold-clutch-heal (60) | B/D | spend-hold + doomed read (Wally's timing) |
| dont-waste-clutch-heal (−40) | B | spend veto |
| play-harlequin-vs-hand-size (25) | D | ADR-0060 swing oracle — keep |
| disrupt-when-unfavored (18/17) | D | posture lever — keep |
| dont-gift-a-refresh-when-favored (−15) | D | keep |
| strip-the-stacked-engine-hand (22) | D | keep |
| disrupt-the-tailored-hand (0) / unfair-stamp-comeback-posture (0) | D | inert forward contracts — keep |
| phase-stabilize-prefer-heal (8) / phase-close-stop-developing (−6) | D | T3 phase bands |
| play-safe-when-ahead-on-prizes (0) | D | posture |

### promote / retreat (12)
| hypothesis | class | note |
|---|---|---|
| promote-the-ko-attacker (45) / promote-the-accelerator-for-the-ko (50) | D/E | TO_ACTIVE sub-select + KO math |
| interpose-the-cheap-attacker (50) / dont-promote-into-their-prize-reach (−20) | D | **prize math — the user's Hariyama-vs-Lucario case**; needs the 2-ply return-KO read for the energy-conditional flip |
| promote-the-ready-wincon (40) / promote-the-staller (20) / dont-promote-onto-their-path (−8) | D/E | promote family |
| hold-position-in-setup (−25) | A/C | position value + ordering |
| retreat-to-ready-attacker (60) / retreat-to-wall-the-line (30) / swap-out-the-locked-attacker (35) | A/C | readiness position_w + cooldown state; search finds the maneuver |
| dont-play-switch-for-no-gain (−8) | B | spend veto |

### sequencing (4)
use-the-draw-engine-ability (18) → **A** (ability-readiness co-equal — fire it = value) ·
dig-before-commit (20/18–23) → **C** · dont-play-damage-boost-when-cant-attack (−12) → **B** (spend
veto conditioned on no-attack; the ep86089617 case) · dont-spend-unneeded-supporter (0) → **B**.

### snipe (9) — all D/E (damage-target sub-selects; T0 keeps them; 2-ply sharpens threat reads later)
snipe-for-the-ko(60) · snipe-the-top-threat(30/27) · snipe-the-threat(20/17) · snipe-on-the-path(12) ·
snipe-the-forced-promotion(40/37) · snipe-the-evolving-threat(45/48) · place-counter-to-convert(30) ·
move-counters-off-the-damaged(30) · move-max-counters(30).

### doctrine_fetch (52) — all E (search/discard sub-selects), with B dual-tags on the spend-shaped ones
Notable: dont-search-an-empty-deck(−60)/dont-search-a-probable-whiff(−25)/search-the-confirmed-hit(15) —
E/B, the deck-odds family ([hypergeometric-fetch-closure.md](../archive/plans/hypergeometric-fetch-closure.md) sharpens);
dont-tutor-the-held-wincon(−45)/dont-grab-a-card-already-in-hand(−12)/dont-fetch-the-redundant-piece —
E + the leaf's SATURATION mirrors on-board redundancy; keep-floors at discard (keep-key-cards −30 etc.) —
E/B; grab-what-i-can-play-this-turn(−12) — E/C (search sees playability); the rest E.

### doctrine_gust (4)
gust-for-the-ko (50/51) → **B/D** (hold = spend; KO payoff = win/KO rungs) · gust-for-the-stall (10/7),
stall-gust-over-dev-when-starved (95/92), gust-to-strand-the-key-attacker (20) → **D** (doomed/stall
reads — survival layer; keep).

### doctrine_shuffle_refresh (6) — all B/E
attach-before-hand-shuffle (−60) → **C** (pure ordering — search emergent) · hold-wincon-dont-shuffle
(−25) / hold-line-piece (−25/−24) / hold-wincon-with-base (−15) / hold-successor-when-doomed (−35) →
**B** (keep-value spend costs) · dont-refresh-into-a-probable-miss (−25) → **B** (deck-odds).

### doctrine_tool (6)
deploy-hp-tool (40) → **D** (survival) · equip-the-retreat-tool-on-the-active (8) → **A** (mobility
position_w) · hold-the-retreat-tool-with-no-retreat (−12) / save-tool-for-the-attacker (−15) /
hold-irreplaceable-tool (−30) / protect-ace-spec-tool (−10) → **B** (spend/hold costs).

### mega_lucario deck layer (16)
start-solrock-over-lunatone (12) → E (opening) · attach-solrock-over-line-base (3) → A ·
aurajab-skip-partnerless-solrock (−20) / aurajab-load-the-wincon-line (10) → E (ATTACH_FROM) + A
precondition · fetch-the-missing-engine-half (22) / dont-fetch-the-redundant-piece (−22) /
dont-fetch-the-inert-engine-piece (−20) → E + leaf saturation/precondition mirrors ·
dont-bench-a-redundant-engine-piece (−25) → A (saturation) · spring-heave-ho-when-it-pays (25) /
heave-ho-decline-without-payoff (−40) / heave-ho-gust-when-it-pays (15) → D (gust payoff) ·
fire-lunar-cycle (15) → **A (ability-readiness co-equal — the discard-energy-to-draw-3 case)** ·
grab-lunar-cycle-fuel (8) → E · dont-lunar-cycle-away-the-last-attachable-f (−30/−24) → **B (the
ability's own spend cost — fuel vs attach conflict)** · lunar-cycle-the-weak-preevo-last-f (30) → A/B ·
gravity-mountain-vs-stage2 (15) → D (symmetric-stadium read).

### dragapult_ex deck layer (3)
bench-the-comeback-drawer (18) → A (ability-readiness, phase-gated) ·
**hold-evolution-until-attacker-ready (−46) → A — THE ability-vs-evolve case (user example 4); the leaf's
max(attack, ability) + progress must reproduce this or the design fails** ·
play-risky-ruins-when-net-positive (15) → D (symmetric-stadium net read).

## Correction-category → owner (the 362)
sequencing_error(111)→C/search · wasted_resource(100)→B/spend · misattachment(41)→A/leaf ·
slow_setup(27)→A/leaf · bad_target(26)→D · wrong_supporter(14)→B+D · bad_retreat(14)→A/C+D ·
other(12)→mixed · missed_win(11)→win rung (built) · wrong_attack(5)→D+cooldown state ·
missed_disruption(5)→D · missed_ko(3)→KO rung (built) · ignored_threat(2)→D · overextension(1)→D.

## Acceptance
1. Leaf v1 ships → run the lab per class-A hypothesis family (SOLE-top + no-regression on the 362 corpus).
2. Spend account ships → the 100 wasted_resource corrections are the bench; re-run Gate 0 (exhaustive
   search must now BEAT 1-ply, not wash).
3. Search ships → sequencing_error(111) is the bench; Phase-3 retirement begins, per-rule, prove-then-retire.
4. D stays measured by the existing tuner/posture benches; E by the existing correction-score gate.
