# Board-state valuation (the leaf) — GRILL SPEC / HANDOFF (to grill, not built)

**Status:** **GRILLED — design decided 2026-07-16 (build spec below); not yet built.** The board-value
function (the "leaf") is the **co-bottleneck** the ply-1 probe exposed, and Gate 0 confirmed it's the
BINDING one (exhaustive search + the CURRENT leaf is a wash vs the 1-ply rung → fix the leaf FIRST).
Companion to [ply1-turn-search-grill-spec.md](ply1-turn-search-grill-spec.md) (which GENERATES the boards
this grades) and [develop-rung-handoff.md](develop-rung-handoff.md). Graduates to an ADR at build.

## Why this exists (the measured problem)
The ply-1 probe: full within-turn search reaches a **median 36 distinct end-boards** per turn, but the
current leaf grades them into only **~5 distinct values** (3/37 frames fully blind). Search *reaches* the
boards; the leaf can't *tell them apart*. And the honest lab metric — the leaf picks the human's option as
the **SOLE** top only **~5%** (2/37 lucario). **Closing the 36→5 granularity gap is this doc's whole job.**

## GRILLED DESIGN — the readiness leaf (decided 2026-07-16)
**Target = my-side readiness** — a P(win) proxy over MY position: how close I am to executing my win. The
opponent is NOT modelled here (the survival term + the later 2-ply own that). **Structure = gated-additive**,
every term capped so the sum stays **< one prize** (the hard-rung invariant is preserved).

```
readiness =  Σ_bodies attack_readiness(b)     ← the core, most of the weight
           + engine      (a draw/accel body that can FIRE its ability this turn — small flat)
           + floor       (a bench exists — small BINARY safety: a KO doesn't lose the game)
           [+ resource]  (v2, deferred — see below)
           , all capped; Σ_max < KO_SCORE.

attack_readiness(b) = position_w(b) × progress(b) × value(best_reachable_attack(b))
   best_reachable_attack = b's own attack OR the attack of a REACHABLE evolution
        · gated on the evolution being available (v1: coarse "is it anywhere in deck+hand";
          v2: deck-odds — see hypergeometric-fetch-closure.md)
        · discounted per evolution hop still owed
   progress = min(energy, cost) / cost  ∈ [0,1]      (energy carries through evolution — verify rules.md)
   value    = the attack's damage / KO-threat         (CombatMath / AttackStat)
   position_w:  Active = 1.0
                Bench  = base_discount lifted toward 1.0 by PROMOTION-EASE
                         (active's retreat cost − free-retreat tools on the active − a switch in hand);
                         degrades to the flat base_discount when hand info is absent
   = 0 if b has no reachable attack                    (the GATE — this is what kills "energy anywhere")
```
**Tools are not a term** — each routes to what it touches: retreat-tools (Air Balloon) → `position_w`;
damage-tools → `value`; HP-tools (Hero's Cape) → the **survival** term (separate).

**Boundary (deliberately OUT of readiness):** the exposed/doomed-Active defensive risk = the survival term;
the opponent's board / prize race / threat = survival + the 2-ply; per-card situational value = the net.

**v1 → v2 split:**
- **v1 (build now):** `attack_readiness + engine + floor`; evo-availability = coarse "anywhere in
  deck+hand"; `position_w` bench = the flat base_discount (the mobility lift needs the hand).
- **v2 (after hand-visibility plumbing):** the mobility lift (switch-in-hand), the gated actionable-resource
  term (credit ONLY held cards with a LIVE use — an evolution for a base in play, a tutor with a target,
  energy when there's an attacker to feed; NEVER raw handCount — measured overfit), and the deck-odds
  evo-availability sharpening.

**Calibration / soundness:** a small weight set → hand-tune on the lab. Split the sub-prize budget so
`attack_readiness` dominates and `engine`/`floor` are minor nudges; verify `Σ_max < KO_SCORE` so no
positional board can outrank a real prize. Measure every change on **SOLE-top + the probe's
distinct-values / distinct-boards ratio**. **Acceptance gate = re-run Gate 0**: the leaf is "good enough"
when exhaustive search + this leaf BEATS the 1-ply rung (today that A/B is a wash — the leaf is why).

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
  (distinct-boards vs distinct-values) — reproduce under `scratchpad/`.

## Related
[[value-model-needs-nonmirror-gauntlet]] · [[ml-build-plan-adr-0053]] · [[leaf-lab-develop-rung]] ·
[[turn-planner-develop-rung]]. ADRs: 0031 (Turn Planner), 0042 (value model, parked), 0053 (ML value net).
