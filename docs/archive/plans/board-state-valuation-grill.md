# Board-state valuation (the leaf) — GRILL SPEC / HANDOFF (v1 BUILT 2026-07-16)

**Status:** **v1 BUILT + measured 2026-07-16** (`_readiness` + the line account in
`src/common/strategy/planner.py`, wired into `_engine_leaf_value`; tests
`tests/strategy/test_readiness_leaf.py`). Leaf-lab movement on the 267-frame corpus: **SOLE-top 5% → 12%**
(14 → 33/267), **shared-top 60% → 72%** (160 → 193/267), **avg top-tie 3.7 → 3.1**. Named scenarios: **#4
hold-the-evolve = SOLE-top**; **#1 discard-to-draw = shared-top rank-1 with the attach blunder deprecated**
(the tied lines are equivalent non-blunders that also fire Lunar Cycle). **Gate 0 PASSES**: on the honest
SOLE-top, exhaustive-search + this leaf **BEATS the 1-ply rung — 27% vs 18%** (9 vs 6 of 33 lucario frames)
with tighter ties (2.24 vs 2.64), where the pre-readiness `_board_development` leaf was a wash. (Gate 0
run with `gate0_ab.py` at a bounded `CAP=2500` so all frames complete in-session; both columns grade the
full `turn_value = readiness + Σ ability-fire − Σ spend`, only the SEARCH differs.) The board-value function (the
"leaf") is the **co-bottleneck** the ply-1 probe exposed, and Gate 0 confirmed it's the BINDING one
(exhaustive search + the CURRENT leaf was a wash vs the 1-ply rung → fix the leaf FIRST). Companion to
[ply1-turn-search-grill-spec.md](ply1-turn-search-grill-spec.md) (which GENERATES the boards this grades)
and [develop-rung-handoff.md](develop-rung-handoff.md). Graduates to an ADR once search v1 lands on it.

**What v1 built (deltas from the spec below):** the design landed as specced with three measurement-forced
refinements. (1) **The ability value is a LINE credit, not only a board term.** The greedy continuation
CONVERGES end-boards (all lines fire the draw ability eventually; the drawn cards play into the same board,
hand → 0), so ability_readiness on the static end board can't separate "fire it FIRST" from "fire it later /
never". The `max(attack, ability)` board term stays (engine-online asset + saturation), but the decisive
"fire it = value" signal is a **line account**: `turn_value = readiness(end) + Σ ability-fire credits −
Σ spend costs`, both reused from the live tuned weights (`OptionTrace.fired`) along the simmed line
(`_ABILITY_FIRE_IDS` / `_CLASS_B_SPEND_IDS`). This is what flips scenarios 1 & 4. (2) **"Reachable
evolution" = DEPLOYABLE this turn (hand+play), not the whole decklist.** The sim's end-obs hides deck
CONTENTS (only `deckCount`), so the "anywhere in deck+hand" v1 proxy would use `self.deck` — which ALWAYS
contains the payoff, making the gate vacuous (every Riolu reads as Mega-Lucario-ready). Hand+play is the
sound this-turn-reachable set; deck-odds is v2. (3) **A weak win-condition pre-evo credits ONLY its
reachable payoff's attack**, not its own throwaway chip — so with the payoff undeployable an energized
Riolu reads ~0 ("the attach's ~0 readiness gain", scenario 1).

## Why this exists (the measured problem)
The ply-1 probe: full within-turn search reaches a **median 36 distinct end-boards** per turn, but the
current leaf grades them into only **~5 distinct values** (3/37 frames fully blind). Search *reaches* the
boards; the leaf can't *tell them apart*. And the honest lab metric — the leaf picks the human's option as
the **SOLE** top only **~5%** (2/37 lucario). **Closing the 36→5 granularity gap is this doc's whole job.**

## How we got here — the method (competition-writeup record)

This spec was not designed top-down; it was **forced, step by step, by measurements on our own logged
games**. The sequence, one day (2026-07-16), each step gating the next:

1. **A symptom, then a bench.** The armed-ON develop rung played setup turns "drunk". Rather than patch
   rules, we built a measurement bench first: the **leaf lab** (`tools/train/leaf_lab.py`) re-scores every
   human-tagged correction board offline (cgpy engine twin — no Kaggle round-trip) and asks one question:
   *does the leaf rank the human's pick on top?* First finding: the lab could only score 2 frames, because
   it gated on a rare payload. Broadening it to every MAIN-select correction (`is_leaf_frame`) took the
   bench from **2 → 267 scorable frames** — the entire correction corpus became the leaf's test set.
2. **First fix from the bench, not from intuition.** Dissecting misses showed the wincon-development
   credit was keyed on the payoff — **which is never in play during setup**, so the credit was inert
   exactly when the rung fires. The plan-tier fix (payoff > line-piece > off-plan) came straight from
   correction ep86090147 ("fetch a pokemon for our bench first") and flipped it MISS→OK; corpus 155→160/267.
3. **An honest metric reframed the problem.** "Ranks correct on top" was 65% — but mostly **ties** (avg
   3.7-way). The strict number (correct is the SOLE top — what the argmax rung actually picks) was **~5%**.
   The leaf's failure is *indiscrimination*, not inaccuracy.
4. **Two probes killed the obvious next steps before we built them.** The **transposition probe**: full
   within-turn search reaches ~36 genuinely distinct end-boards (the ties were an artifact of greedy
   continuation) — but the leaf collapses them to ~5 values, and the collision dissection named the exact
   blindnesses (who's-Active, hand, tools). **Gate 0**: exhaustive search over the *current* leaf is a
   wash vs the 1-ply rung (67% vs 61%) — deeper search just amplifies leaf error. Conclusion, fixed by
   measurement: **leaf first, then search.** (Two seductive alternatives — Σ-of-greedy-scores as turn
   value, raw hand-count credit — were also A/B'd on the bench and **rejected on evidence**: 41% vs 65%,
   and a regression of the flagship frame, respectively.)
5. **The corrections + hypotheses ARE the spec.** To make the planner "account for all T0 work", we read
   **every logged correction (362)** and **every T0 hypothesis (164, with tuned weights)** and dispositioned
   each into five classes with a named owner ([t0-planner-disposition.md](../../plans/t0-planner-disposition.md)):
   state-valuation → this leaf; spend-costs → the new spend account; sequencing crutches → the search;
   opponent-facing → survival/2-ply; sub-selects → T0 stays, inside rollouts. The design terms below are
   in near 1:1 correspondence with that corpus: the gate ("never attach a useless energy ever" ×8),
   ability co-equality ("discard energy, draw 3" / "always use Drakloak's ability before evolving"),
   preconditions ("Solrock is worthless without a Lunatone — write that down"), saturation ("we only ever
   need one Solrock and one Lunatone"), the spend account (100 wasted_resource corrections: "save the
   Ultra Ball", "wasted Crushing Hammer"), and the two-account line value — the human's own Σ-points
   instinct, restricted to the half that is mathematically sound (pure spends are additive; state scores
   double-count). The tuned rule weights are **reused** as the spend costs, so years of correction-tuning
   carry over instead of being re-derived.
6. **Acceptance is pre-committed.** Four named human scenarios (below), the 362-correction corpus as a
   regression suite, the SOLE-top + distinct-values metrics, and a re-run of Gate 0 (search must *beat*
   the 1-ply rung once this leaf lands). Rules retire only per-rule, on proof (planner-ON/rule-OFF,
   no corpus regression).

The through-line for the writeup: **human corrections are the teacher, hypotheses are the accumulated
curriculum, and every architectural decision was gated by an offline measurement on that corpus** —
the same corpus the tuned rule layer was trained on now specifies, tests, and (eventually, per-rule,
on proof) retires into the turn planner.

## GRILLED DESIGN — the readiness leaf (decided 2026-07-16)
**Target = my-side readiness** — a P(win) proxy over MY position: how close I am to executing my win. The
opponent is NOT modelled here (the survival term + the later 2-ply own that). **Structure = gated-additive**,
every term capped so the sum stays **< one prize** (the hard-rung invariant is preserved).

```
readiness =  Σ_bodies contribution_readiness(b)   ← the core, most of the weight
           + floor       (a bench exists — small BINARY safety: a KO doesn't lose the game)
           [+ resource]  (v2, deferred — see below)
           , all capped; Σ_max < KO_SCORE.

contribution_readiness(b) = max( attack_readiness(b), ability_readiness(b) )   ← CO-EQUAL (edge-case
   round 2026-07-16: these decks are ABILITY-centric in setup — Lunatone draw-3, Drakloak Recon —
   so abilities are a first-class contribution, not an "engine" footnote), × saturation(b)

attack_readiness(b) = position_w(b) × progress(b) × value(best_reachable_attack(b))
   best_reachable_attack = b's own attack OR the attack of a REACHABLE evolution
        · gated on the evolution being available (v1: coarse "is it anywhere in deck+hand";
          v2: deck-odds — see hypergeometric-fetch-closure.md)
        · discounted per evolution hop still owed
        · an attack LOCKED OUT next turn (Mega-Brave-class transient, ADR-0033) counts 0 for next-turn
          readiness — read the cooldown state, not just energy
   progress = min(energy, cost) / cost  ∈ [0,1]      (energy carries through evolution — verify rules.md;
                                                      only PAYABLE energy counts — type-aware, so
                                                      off-type energy earns nothing)
   value    = the attack's damage / KO-threat         (CombatMath / AttackStat)
   position_w:  Active = 1.0
                Bench  = base_discount lifted toward 1.0 by PROMOTION-EASE
                         (active's retreat cost − free-retreat tools on the active − a switch in hand);
                         degrades to the flat base_discount when hand info is absent
   = 0 if b has no reachable attack                    (the GATE — this is what kills "energy anywhere")

ability_readiness(b) = value(best FIREABLE ability: draw/accel/setup)
   · PRECONDITION-gated: partner in play (Lunatone needs Solrock — "write that down"), cost payable
     (Lunar Cycle needs a discardable {F} in hand), not already spent this turn
   · position: NO bench discount (abilities fire from the bench — Solrock-active/Lunatone-benched is
     the IDEAL board) unless the ability text is active-only (read per card)
   = 0 if nothing fireable

saturation(b): a body filling a UTILITY/ENGINE role already filled by another in-play body contributes
   ~0 (a 2nd Lunatone is fodder — "we only ever need one Solrock and one Lunatone"); ATTACKERS still
   accumulate (a 2nd attacker advances the prize race). Role-keyed, never a global body-count penalty.
```

**Line value (the planner's ranking scalar — decided with the T0 disposition,
[t0-planner-disposition.md](../../plans/t0-planner-disposition.md)):**
```
turn_value(line) = readiness(end board) − Σ spend_costs(actions along the line)
```
Spend costs = the class-B T0 rules (wasted Ultra Ball / `discard_eot` / Supporter slot / held gust-heal
etc.), REUSED from the live tuned weight set, summed along the path. Pure spends are additive (no state
double-count — the flaw that killed raw Σ-scores does not apply). The sound win rung preempts as always.
**Tools are not a term** — each routes to what it touches: retreat-tools (Air Balloon) → `position_w`;
damage-tools → `value`; HP-tools (Hero's Cape) → the **survival** term (separate).

**Boundary (deliberately OUT of readiness):** the exposed/doomed-Active defensive risk = the survival term;
the opponent's board / prize race / threat = survival + the 2-ply; per-card situational value = the net.

**v1 → v2 split:**
- **v1 (build now):** `contribution_readiness (attack ∥ ability, precondition-gated, saturated) + floor`
  + the spend account; evo-availability = coarse "anywhere in deck+hand"; `position_w` bench = the flat
  base_discount (the mobility lift needs the hand). Ability preconditions/costs read from Function Tags +
  card data — verify at source, never recall.
- **v2 (after hand-visibility plumbing):** the mobility lift (switch-in-hand), the gated actionable-resource
  term (credit ONLY held cards with a LIVE use — an evolution for a base in play, a tutor with a target,
  energy when there's an attacker to feed; NEVER raw handCount — measured overfit), and the deck-odds
  evo-availability sharpening.

**Calibration / soundness:** a small weight set → hand-tune on the lab. Split the sub-prize budget so
`attack_readiness` dominates and `engine`/`floor` are minor nudges; verify `Σ_max < KO_SCORE` so no
positional board can outrank a real prize. Measure every change on **SOLE-top + the probe's
distinct-values / distinct-boards ratio**. **Acceptance gate = re-run Gate 0**: the leaf is "good enough"
when exhaustive search + this leaf BEATS the 1-ply rung (today that A/B is a wash — the leaf is why).

**Builder gotchas (from project memory — restated here so a fresh/remote session has them):**
- **A big new positive term silently VOIDS every guard calibrated against the old one** (ADR-0060 lesson).
  `readiness` replaces `_board_development`'s scale — re-check EVERY consumer/threshold sized against the
  old dev values (`_PLANNER_DEV_CAP`, the develop-rung gate constants, any tuned weight that assumed the
  old magnitude) before trusting old behaviour.
- **A flat positive score can never DECLINE a free play** — the tiering plays any option scoring > 0. The
  spend account must make a wasteful spend NET negative on the line value, not merely less positive.
- **Isolated hand-built probes manufacture phantom misplays** — measure on real fixtures / the full menu
  (the lab + the committed probes), never a synthetic decide() board with options omitted.
- **"W-route satisfied" ≠ fixed; always retest through the real `decide()`** — a leaf/gate change is
  invisible to the weight fit; the lab and `tools/train/retest_one.py` are the honest checks
  (`train.tuner.retest.retest()` returns a dict — `r["fixed"]`).
- **`tune.py` clobbers `tuned.json`** — keep it out of build commits. **`src/cg/` is off-limits.**
- **cgpy is parity-limited (~298/434)**: trust the RANKING it produces, never the absolute value.

**Named acceptance scenarios (user, 2026-07-16 — each must rank correctly, or the design fails):**
1. **Discard-to-draw:** Solrock+Lunatone+Riolu in play, 0 energy on board, 1 energy in hand, no Mega
   Lucario. Correct: attach to NO ONE — discard the energy to Lunar Cycle (draw 3).
   `ability_readiness(Lunatone)` + the attach's ~0 readiness gain must beat any attach. (leaf)
2. **Prize-math promote:** opp at 2–3 prizes, my Mega Lucario KO'd; promote Hariyama (1-prize sacrifice,
   210 swing) over the 3-prize Mega Lucario. (opponent layer — interpose family + 2-ply; OUT of the leaf)
3. **Same, opp can't punish** (their attacker at 1 energy): promote Mega Lucario instead — the flip needs
   the 2-ply return-KO read. (opponent layer)
4. **Hold-the-evolve:** benched Drakloak, 1 energy, Dragapult in hand — do NOT evolve until 2 energy;
   Drakloak's Recon Directive outvalues a premature Dragapult. `max(attack, ability)` + progress must
   reproduce the tuned −46 (`hold-evolution-until-attacker-ready`). (leaf)

*(The "Grill questions" section below is the pre-grill record; the decisions above supersede it.)*

## How boards are graded TODAY (the baseline to beat)
One function: `_engine_leaf_value` → `_leaf_value` (`src/common/strategy/planner.py`). A weighted sum,
prizes dominant, every positional term capped **below one prize** (KO_SCORE = 1000 — the hard-rung invariant):
```
grade =  KO_SCORE · prizes_taken_this_turn                 # 1000 each — dominant
       + (50 if my active survives the worst Incoming else 0)
       + min(100, 1.0 · development)                       # _board_development, capped
       + min(100, 0.1 · threat_removed)                    # 0 on a develop turn
       + 80 · (P(win) − 0.5)                               # value model — parked/OFF → 0 today
       ; a line that WINS short-circuits to KO_SCORE·(prizes+1).
```
`development = _board_development(me)` sums over my bodies (active+bench), tiered by game-plan role
(the plan-tier shipped this arc): `10 + 5·energy` base, `+10 + 5·energy` if the **payoff** (`_wincon_set`),
`+5 + 3·energy` if a **plan piece** (`_development_plan_set`), `+0` off-plan (an opener like Meowth ex).

**Why it collapses 36→5 — VERIFIED (not a counting bug; the leaf is blind to first-order facts).**
On a develop turn (no prize/win) the grade reduces to `(0 or 50, survival) + min(100, development)`, and
walking one frame's full tree dissects the collapse (ep83661652):
```
36 distinct full boards      (bodies + tools + prize + handCount)
 → 18 board POSITIONS          the leaf ignores HAND SIZE               (36→18)
 →  7 dev-input signatures      (tier, energy) per body only            (18→7)
 →  6 distinct grades           integer sums that coincide              (7→6)
```
The 12 boards that all grade **56** lay it bare — same three bodies, but:
```
hand=2  Lunatone[E2](plan)+Air Balloon | Meowth ex[E0](off) | Riolu[E0](plan)
hand=2  Meowth ex[E0]                   | Lunatone[E2]+Air Balloon | Riolu[E0]
hand=3  Lunatone[E2]+Air Balloon        | Meowth ex[E0]           | Riolu[E0]
```
`_board_development` sums active+bench, ignores tools, ignores the hand, and treats plan-pieces as
fungible — so a board with **Lunatone[E2]+Air Balloon ACTIVE** grades identically to one with a bare
Meowth ex active. Three first-order blindnesses fall out, each sound to fix:
1. **Who's Active** — active+bench are summed; the leaf can't tell a loaded attacker up front from a
   liability that's about to be KO'd.
2. **Hand size** — the entire 36→18 step; cards retained are invisible.
3. **Tools** — Air Balloon (free retreat) contributes nothing.
(+ plan-piece fungibility and integer-sum collisions finish 18→6.) That coarseness IS the bottleneck —
and this is the concrete tie the leaf grill must break.

## What the grade does NOT see (the enrichment surface)
- **Who's Active** — active+bench are summed into one `development` total (verified above): a loaded
  attacker in the active spot scores the same as it would benched, and a fragile active liability isn't
  penalised. First-order and unread.
- **Value model OFF** (ADR-0042 parked) → the one learned term is 0. No P(win) input today.
- **Survival is shallow + binary** — `_incoming_worst` counts only the opponent's attacks from bodies
  *already in play* (+1 attach); it does NOT model them evolving a benched pre-evo into a threat
  (Riolu→Mega Lucario ex), and it's 0/50, not a magnitude (bench-empty active-KO = game LOSS, not −50).
- **Hand unread** — `development` is bodies+energy only; nothing for cards retained / held tutors with
  live targets (and the simmed end-obs HIDES my hand — the opponent-perspective plumbing gap).
- **Opponent board barely read** — only via survival's Incoming. No prize-race, no reading THEIR setup.
- **Prize-race standing** is rank-inert *here* (proven) — a general-eval term, not `_board_development`.

## Grill questions (the meat)
1. **Shape of the valuator.** Richer closed-form leaf vs the learned **value net** (ADR-0053) vs a **hybrid**
   (closed-form base + learned residual)? The probe says the ceiling is *granularity* — which shape widens
   36→5 fastest, and which stays sound/legible?
2. **Soundness envelope.** The capped-sub-prize invariant must hold (positional never outranks a real
   prize). Current positional headroom ≈ 290 of 1000. Every new term must fit under KO_SCORE; how is the
   budget split as terms are added?
3. **Finer development.** Candidate discriminators to widen 36→5, each judged sound + non-redundant:
   evolution-readiness / primed bodies, energy that can *actually* pay an attack (vs stranded), bench
   composition, HP / damage state, tool deployment, board-wide threat/tempo.
4. **Survival as magnitude, not a bit.** Replace 0/50 with graded survival (turns-to-live; loss-avoidance
   ≈ KO_SCORE when the bench is empty; evolve-into-threat Incoming). Shared face with the 2-ply survival
   upgrade — decide what lives in the leaf vs the lookahead.
5. **Hand-aware terms** (needs the hand-visibility plumbing first). Held-resource value (tutors with live
   targets), energy-in-hand vs the 1-attach limit. AVOID the raw-`handCount` overfit (it regressed the
   flagship Poké Pad frame — measured).
6. **Value BOTH boards.** The user's full-state vision: my threat vs theirs, prize race, their development,
   opp hand size / discard / archetype (the Read). What's sound and cheap here vs what's the net's job.
7. **Calibration / measurement.** Bench = the lab (honest **SOLE-top** + avg top-tie) and the probe's
   **distinct-leaf-values / distinct-boards** ratio. Targets: raise distinct-leaf-values toward
   distinct-boards, and move SOLE-top off 5% — without inverting a sound prize/win.

## Scope
- **IN:** the board-state value function — features, shape (closed-form / net / hybrid), soundness envelope,
  calibration. The hand-visibility plumbing (its enabler).
- **OUT:** the search that GENERATES the boards (ply-1 spec), the 2-ply opponent lookahead (except where it
  feeds the survival term), the fine hypergeometric draw-odds (its own note), per-card situational value
  (combinatorial — the net's job, deferred).

## The stack this sits in
exhaustive within-turn search (generates boards) → **THIS: grade the boards (leaf)** → 2-ply opponent
(heuristic) → value net. This is the *valuation* layer; the probe proved it's the partner bottleneck to the
search, not a substitute for it.

## Where things live
- Grading: `_engine_leaf_value`, `_leaf_value`, `_board_development`, `_development_plan_set` + the
  `_PLANNER_*` constants — `src/common/strategy/planner.py`.
- Learned-term seam: `_value_term`, `_PLANNER_VALUE_W`, `value_model` (ADR-0042, parked).
- Survival: `_incoming_worst`, `_survives_after_ko` — `planner.py`.
- Measurement: `tools/train/leaf_lab.py` (honest SOLE-top / distinct-value); the transposition probe
  (distinct-boards vs distinct-values) — `tools/train/probes/transposition_probe.py`; per-frame leaf
  dumps `tools/train/probes/leaf_diag.py`; the Gate-0 A/B `tools/train/probes/gate0_ab.py`.

## Build log — who's-Active + tool terms (2026-07-20, thread 3 of the keep-value-v2 line)

**Step-1 dissection (the measured ceiling; N5d diagnosis CONFIRMED).** Per-option end-board
signatures over the 267 scorable leaf-lab frames: 39 sole-top / 151 at-top-tied / 77 miss. Of the
151 tied groups, **77 are pure transpositions** (every tied rival board byte-identical — no board
term can ever split them; the hard cap on leaf enrichment), 50 differ on who's-Active, 5 on tool
deployment. Perfect-split ceiling for active+tool terms: +37.9 E[correct].

**Shipped (unconditional): the PROMOTION-EASE lift** — `_bench_position_w` lifts the 0.45 bench
weight toward `_READINESS_PROMO_MAX` (0.5) via `_promotion_ease` (free effective retreat = printed
cost − attached `retreatReduction` tools — the retreat-tool → position routing; or a `switch`-tag
card in the VISIBLE hand at 0.9; a merely PAYABLE retreat is NOT ease — paying discards the Energy,
rulebook L142, and crediting it regressed ep86091435), applied to the SINGLE best benched attacker
(one retreat/turn). Measured frontier: ceiling 1.0 / per-body lifts let "hide the attacker behind a
free-retreat wall" boards beat the human's attacker-in-front lines (37/184); 0.5 single-best is the
zero-regression point. **Bench: SOLE-top 39→40/267, E[correct] 83.8→84.7, avg-tie 3.02→2.99,
shared-top flat 190; Gate-0 (lucario ctx-0, CAP=2500) 1-ply SOLE 8→9, exhaustive 9→10, no
regression; suite green.** HP-tools need no term (engine bakes `hpBonus` into body hp → survival
already reads Hero's Cape); damage-tools skipped as bench-inert (Brave Bangle's conditional parses
to 0; no shipped deck runs a parseable damage tool).

**HAND-ARMED (rides `leaf_hand_value`, still OFF): the who's-Active mobility micro-credit**
(`_READINESS_MOBILITY_W` × `_active_quality` — a mobile Active or an energized declared-line
pre-evo with a REACHABLE payoff). Hand-blind it nets SOLE +4 but trades shared-top frames whose
labels pivot on hidden-hand context (held Lunar-Cycle fuel, the Mega-in-hand attach) — so it arms
with the hand plumbing, correctly scenario-1-gated.

**The N5d hand-fold re-measure with the new terms: 52 SOLE / 164 shared / 2.40 tie / 88.0 E —
still NOT cleared (shared-top down); `leaf_hand_value` stays parked.** The verdict against the
letter of the bar (SOLE AND shared both up): NOT CLEARED — shipped anyway as a strictly-≥ Pareto
step (zero regressed frames, four metrics up, shared flat); the residual shared-top movement lives
in hand-context frames the transposition finding caps.

## Related
[[value-model-needs-nonmirror-gauntlet]] · [[ml-build-plan-adr-0053]] · [[leaf-lab-develop-rung]] ·
[[turn-planner-develop-rung]]. ADRs: 0031 (Turn Planner), 0042 (value model, parked), 0053 (ML value net).
