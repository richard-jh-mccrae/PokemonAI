# Board-state valuation (the leaf) — GRILL SPEC / HANDOFF (to grill, not built)

**Status:** grill spec — the board-value function (the "leaf") is the **co-bottleneck** the ply-1
transposition probe exposed. Not built; grill later. Companion to
[ply1-turn-search-grill-spec.md](ply1-turn-search-grill-spec.md) (which GENERATES the boards this grades)
and [develop-rung-handoff.md](develop-rung-handoff.md). Graduates to an ADR when grilled.

## Why this exists (the measured problem)
The ply-1 probe: full within-turn search reaches a **median 36 distinct end-boards** per turn, but the
current leaf grades them into only **~5 distinct values** (3/37 frames fully blind). Search *reaches* the
boards; the leaf can't *tell them apart*. And the honest lab metric — the leaf picks the human's option as
the **SOLE** top only **~5%** (2/37 lucario). **Closing the 36→5 granularity gap is this doc's whole job.**

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

**Why it collapses 36→5:** on a develop turn (no prize/win) the grade reduces to
`(0 or 50, survival) + min(100, development)`. Survival is **binary**; development is a **sum of small
integers** (10/15/20/23/30 per body) — an integer lattice. Dozens of different boards land on the same
total. That coarseness IS the bottleneck.

## What the grade does NOT see (the enrichment surface)
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
  (distinct-boards vs distinct-values) — reproduce under `scratchpad/`.

## Related
[[value-model-needs-nonmirror-gauntlet]] · [[ml-build-plan-adr-0053]] · [[leaf-lab-develop-rung]] ·
[[turn-planner-develop-rung]]. ADRs: 0031 (Turn Planner), 0042 (value model, parked), 0053 (ML value net).
