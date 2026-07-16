# 2-ply opponent survival / return-KO reachability — GRILLED, decisions locked

**Status:** grilled 2026-07-16 — all six grill questions resolved into the six **Locked Decisions**
below; **graduated to [ADR-0064](../adr/0064-incoming-counts-the-opponents-next-development-step-budgeted-by-the-read.md)**
(this doc remains the build plan). Companion to
[board-state-valuation-grill.md](board-state-valuation-grill.md) (the leaf — my-side readiness; this doc
is its deliberately-excluded opponent-facing counterpart), [ply1-turn-search-grill-spec.md](ply1-turn-search-grill-spec.md)
(the sound within-turn search; this layer is heuristic, sits above it), and
[t0-planner-disposition.md](t0-planner-disposition.md) (class D — opponent-facing — is this doc's scope).
[hypergeometric-fetch-closure.md](hypergeometric-fetch-closure.md) is the deferred probability refinement
this layer will eventually want. Despite the historical title, this layer is best understood as a
**hidden-development Incoming**, not a search — see §Relationship to ADR-0043.

## Thesis

Two of the leaf's `readiness` design is deliberately silent on the opponent's board — that's this layer's
job (`board-state-valuation-grill.md` §Target: "the opponent is NOT modelled here — the survival term + the
later 2-ply own that"). This spec is that survival layer: **how much development can the opponent's
board reach by their next turn, and does it kill me or let them punish a greedy promote/hold** — a bounded,
heuristic, one-development-step lookahead (promote + evolve + attach + attack), NOT a search tree.

## THE VERIFIED GAP — a precise, code-cited starting point

`Pilot._incoming_worst` (`src/common/strategy/planner.py:2056-2075`) is the closed-form "Incoming" the
survival term (`_PLANNER_SURVIVAL_W = 50.0`, flat) and `_survives_after_ko` already use. Read closely:

```python
for p in opp_bodies:
    pstat = self.stats.get(p.get("id"))          # <-- looks up the body AS IT CURRENTLY IS
    energy = len(p.get("energies") or []) + 1     # allows ONE attach next turn
    if pstat.can_pay_cheapest(energy):
        worst = max(worst, int(self._predicted_max_damage(pstat, {"id": my_id})))
```

It allows **one Energy attach**, but **never an evolution**. A benched Riolu is scored as Riolu's own
(trivial) attack — never as "could evolve to Mega Lucario ex and swing for real damage."

Two further defects the grill surfaced in the same loop:

- **Cheapest-gated max:** once a body affords its *cheapest* attack it is credited its *biggest*
  (`predicted_max_damage` explicitly documents "does NOT filter by the opponent's Energy
  affordability"). A naive evolution extension therefore credits a 1-Energy Mega Lucario ex with
  Mega Brave 270 — it cannot produce the spec's own variant-2 arithmetic. Per-attack affordability
  (Locked Decision 1) is required, not optional.
- **The WON'T-FIX collision:** `docs/todo/incoming-affordability.md` records that a blind
  affordability cap on the survival read was **built and reverted (2026-07-07)** — on the real
  CRITICAL states `planner_6858`/`planner_0cbc` a Mega Starmie mirror at 1 Energy held a hidden
  **Ignition Energy** ({C}{C}{C} burst) and fired Nebula Beam (●●●) next turn; the capped read said
  "not doomed" and re-opened the blunder. Locked Decision 1 **amends** that WON'T-FIX (Read-budgeted
  affordability, worst-case fallback) rather than contradicting it; the ADR must say so explicitly,
  and the two CRITICAL states are the regression gate.

## The worked example — VERIFIED numbers (never recalled; read from `pilot._attack_stat` / `EN_Card_Data.csv`)

Board: my Active is a Mega Starmie at **270 HP remaining** (330 max, {L}-weak — no W/R wrinkle vs
Fighting), 1 energy, empty bench, hand = Lillie's Determination + Wally's Compassion, no energy attached
yet this turn. Opponent's Active = Riolu; their bench has one more Riolu with 1 Energy. I can KO their
Active Riolu this turn.

**Verified card facts** (`data/EN_Card_Data.csv`, `pilot._attack_stat` via the live provider):
- `Riolu` (id 677) → `Mega Lucario ex` (id 678, HP 340) — **single hop**, confirmed both in
  `docs/rulebook.txt` Appendix 1 and `docs/rules.md` §4: *"`Riolu` → `Mega Lucario ex` is a single hop."*
- **Aura Jab** (attack id 982): damage **130**, cost **{F}** (1). Its effect attaches up to 3 Basic {F}
  Energy from the discard **to the Bench** — accel, but bench-directed (see Locked Decision 1's
  attack-accel exclusion).
- **Mega Brave** (attack id 983): damage **270**, cost **{F}{F}** (2 typed Fighting),
  `nextTurnSameAttackLock=True` (can't reuse next turn — the card fact behind the ep85058574 correction;
  it also matters symmetrically for this layer's own next-ply reasoning).
- `docs/rules.md` §4 (`[RULE: rulebook L335]`): evolving into a Mega ex **does NOT end the turn** — this
  is what makes the opponent's worst-case turn (promote → evolve → attach → attack) legal in ONE turn.
  §4 also: a body cannot evolve the turn it was *put into play* — but every body on their bench during
  my turn was benched on/before their previous turn, so all their current bench bodies are evolvable on
  their next turn (promotion is not "coming into play"); and evolving **clears attack effects**, so a
  forward form legitimately escapes its pre-evolution's transient lock.

**The two variants:**
- Bench Riolu has **1 energy**: opponent's worst case = promote it, evolve to Mega Lucario ex (legal,
  doesn't cost the turn), attach the 2nd energy (affords Mega Brave, {F}{F}), attack for **270** —
  EXACTLY KOs my 270-HP Mega Starmie. Correct answer: play **Wally's Compassion** (defensive).
  Unconditional — the threat direction needs no Read match.
- Bench Riolu has **0 energy**: after one attach they have 1 energy — affords only **Aura Jab
  (130 < 270)**, no KO. Correct answer: play **Lillie's Determination** (greedy is fine).
  **Conditional on a matched Lucario Read** (Locked Decision 1): the greedy read charges Mega Brave's
  typed {F}{F} cost against attached+1 only because the matched rep list shows no trainer/ability/
  special-energy accel that could burst it. Unmatched Read → worst-case budget → the agent correctly
  refuses to be greedy. The acceptance test MUST set up the brief match (γ over threshold).

`_incoming_worst` as written returns **Riolu's own attack (30)** in both variants (never reaching Mega
Brave), so `_survives_after_ko` reports "survives" in variant 1 too — the false negative is exact and
reproducible.

## The prize-math promote scenarios — MOSTLY ALREADY BUILT

The other two scenarios (opp at 2–3 prizes, my Mega Lucario ex KO'd, promote Hariyama not the
3-prize Mega Lucario / promote Mega Lucario when the opponent can't punish) map onto **existing, shipped
hypotheses** — `src/common/strategy/baseline/baseline_promote.py`:

- `interpose-the-cheap-attacker-to-preserve-the-wincon` (+50): promote a cheap body over the wincon when
  `opp_prizes_remaining >= 2` and `bench_wincon_prize_value > card_prize_value` — **exactly** "opp at 2-3
  prizes, don't feed them the 3-prize Mega Lucario."
- `dont-promote-into-their-prize-reach` (−20): softens promoting the wincon further when
  `card_prize_value >= opp_prizes_remaining >= 2`.

**The gap is scenario 3 — the flip when the opponent CAN'T punish.** `interpose` fires on exactly THREE
drivers (weakness trade / an accel_source powering an underpowered finisher / a shown gust) — none is
"the opponent's board literally cannot afford to KO my wincon next turn." This layer supplies that as a
**stand-down condition** (not a fourth positive driver): when the safety-direction read (Locked
Decisions 1+4 — matched Read required) says their best reachable next-turn attack cannot threaten the
wincon, `interpose` (all three drivers) and `dont-promote-into-their-prize-reach` both stand down, and
`promote-the-ready-wincon` (+40) wins. One primitive, two consumers — the leaf's survival/loss reads and
the promote family's stand-down.

## LOCKED DECISIONS (grill session 2026-07-16)

### 1. The reachability primitive: per-attack, typed-cost affordability under a Read-supplied energy budget

Consolidate on **`_threat_forms`** (`src/common/strategy/objectives.py:280`, ADR-0045) — the one existing
read with per-body × per-form × per-attack granularity (current form + one forward hop via
`forward_card_ids`, promotion-surcharge-aware) — extended with a **ceiling/charged policy switch**,
rather than forking a fifth Incoming variant out of `_incoming_worst`. `_incoming_worst` becomes a
consumer of the shared primitive.

Affordability is charged **per attack, per cost shape**:
- **Typed slots** ({F}{F} etc.) can only be paid by attached typed energy + typed accel. Ignition
  Energy provides **{C}{C}{C}** (verified: id 17, self-discards) — it can pay Nebula Beam's ●●● in one
  attach but can NEVER pay Mega Brave's {F}{F}. Colorless burst does not threaten typed costs.
- **Energy budget** = attached + 1 attach + a **colorless-burst allowance derived from the matched
  Read's representative decklist** (special energy providing >1 unit; `energy_accel`-tagged trainers/
  abilities — derived by scan, calibrated tier, NOT a hand-asserted brief boolean).
- **Attack-based accel is excluded from the one-step budget**: one attack per turn means Aura-Jab-class
  accel can never fuel its own attacker in the same turn, and its past uses are already visible in
  `attached`. Provably exact within this layer's horizon, not an approximation.
- **Unmatched or low-γ Read → worst-case budget** (affordability uncharged). Fail-scared, never
  fail-brave. Consequence accepted: early game we play cautious until the Read matches; a
  matched-but-wrong Read (rogue list with unseen typed accel) loses a game and is the blunder-buster
  pipeline's problem, never a magic-number fudge.

This **amends the WON'T-FIX** in `docs/todo/incoming-affordability.md`: the survival read stops being
unconditionally worst-case and becomes charged-with-archetype-budget, defaulting to worst-case. Under
the new model the planner_6858 mirror still reads doomed (Starmie archetype runs Ignition; Nebula Beam
is colorless-costed → burstable), so the original blunder stays fixed — re-verify on the real states.

### 2. Scope: a REFACTOR of `_incoming_worst` onto the shared primitive — not an in-place edit

`_incoming_worst` is not patched where it stands: it becomes a **thin adapter over the consolidated
reachability primitive** (Decision 1's `_threat_forms`-based read), so the Incoming family gets ONE
home instead of a fifth dialect. All **five** call sites flip together through that adapter, keeping
their signatures (`planner.py:1391, 1575` snipe-survival picks; `2054` `_survives_after_ko` and its
seven callers; `2117, 2424` engine leaves) — they share one function asking one question, and a partial
flip would create two survival dialects in one file. `active_doomed` (`combat.py`) is **separate
machinery** and stays worst-case in v1; unifying it onto the budget model is a named follow-up behind
its own fixture re-baseline (it carries the 19-test blast radius that got the last attempt reverted
mid-session).

### 3. Predicted loss is a rung, not a weight

When — and only when — both gates hold on a candidate line's end board:
1. **my bench is empty** (visible fact, zero prediction error), and
2. **budgeted incoming ≥ my Active's HP** (Locked Decision 1's read),

the line's leaf value gets **`-KO_SCORE` added** (equivalently: returned as a floor) — mirroring the
existing `_two_ply_value` precedent (`planner.py:2418`, "the reply WON for them"). Everything else in
`_leaf_value` stays untouched: `_PLANNER_SURVIVAL_W` stays **50** and keeps pricing the ordinary,
recoverable lose-a-body case. Properties the ADR should state:
- **Composes with prizes:** 1 prize taken (+1000) into bench-empty doom (−1000) nets ≈ 0 and loses to
  any safe positional line — correct; and a line that *wins outright* still dominates (the win rung
  returns `KO_SCORE × (prizes+1)` before leaf math — Q5's never-override-a-sound-rung holds).
- **No paralysis:** uniform doom across all candidates cancels in the ranking; the rung only moves
  picks where lines differ in exposure — e.g. it rewards benching a Basic turn 1 (the anti-donk play).
- **No scale change:** no existing constant is touched, so no ADR-0060-style threshold re-audit of the
  old scale is needed — only the new code path.

### 4. Availability gate: existence for threat, matched Read for safety

The original "is it anywhere in their deck+hand" is **uncomputable** — their deck and hand are hidden
zones; the leaf's my-side evo-gate is a false mirror (my deck+hand are visible to me, theirs never are).
Replaced by a two-tier gate, asymmetric by direction (same principle as Decision 1: over-counting their
reach costs a −20 nudge; under-counting it feeds them the 3-prize wincon):
- **Threat direction (survival/loss-rung):** existence only — the pool-level `_ForwardIndex` says
  something evolves from the body. A benched Riolu *is* the evidence they run the Mega; Decision 1's
  budget arithmetic bounds the pessimism, no further gate.
- **Safety direction (interpose/dont-promote stand-down):** requires the **matched Read** — the rep
  list contains the evolution, minus visibly-exhausted copies (KO'd/discarded/prized;
  `copies_left_odds` where cheap). No match → no stand-down; never promote the wincon on a guess.
- Hypergeometric draw-odds stay deferred ([hypergeometric-fetch-closure.md](hypergeometric-fetch-closure.md)).

### 5. Transient-lock awareness is narrower than drafted

Benched bodies **cannot carry a live grant** — `TransientTracker` grants bind to the attacker's serial,
and a body that leaves the Active presents a new serial — so `_survives_after_ko` (bench-only, post-KO)
needs no lock read, and `incoming_active_damage` (`combat.py:279`) already honors grants for their
Active (self-lock → 0, same-attack lock excluded, self-bonus added). The residue: route the two
engine-leaf call sites that include their Active (`planner.py:2117, 2424`) through the grant-aware
read. Evolution clears attack effects (`rules.md` §4), so a forward form escapes its pre-evolution's
lock — the serial mechanism gives this for free. Symmetrically, our own Mega-Brave-class lockout is
already priced by the follow-up cost model (`pilot.py:2312`, ADR-0061).

### 6. The ADR-0043 two-ply escalation is DEPRECATED — this layer supersedes its survival role

Ruled: an opponent-reply search is neither feasible nor necessary — we can never assume what they hold
or what they do with it; we see their board, hand size, prizes and discard, and deduce a best guess
(Decisions 1 + 4). The escalation's reply sim is **structurally blind to hidden-hand development** (it
can only make the opponent play visible cards — it can never play the Mega Lucario ex we cannot see),
which is exactly the threat class that decides these boards. Evidence it is already dead weight:
- It requires BOTH the `escalation` kill-switch (default `False`, `pilot.py:1019`) AND
  `search_budget > 0` — and **every shipped agent pins `search_budget: 0`** (mega_starmie,
  mega_lucario, dragapult_ex; escalation is `search_budget`'s ONLY functional consumer, per
  ADR-0043's own 2026-07-14 note).
- Prior regression on record: `planner.py:270` — "the regressed escalation was the two-ply OPPONENT
  tree."
- Raising `search_budget` silently re-labels telemetry AND the submission manifest as Tier-1
  (test-pinned, `tests/submit/test_submit_brief.py`), changing the competition writeup's narrative.

**Action:** ADR-0043 is marked **Deprecated** in the ledger and file header (done this session).
Physical removal of `_escalate` / `_commit_escalation` / `_two_ply_value` / `_close_attack_tie` /
`_density_trigger` / `_top_k_candidates` / the `escalation` switch is a follow-up build task of
ADR-0064, gated on one corpus re-check: no reviewed correction case depends on an escalation pick
(the tuner's score-diff gate). Decision 3's `-KO_SCORE` precedent is conceptual and survives the
removal — the loss rung lives in the `_leaf_value` pathway, not in `_two_ply_value`.

This layer itself never simulates opponent moves, never resolves coins, and never overrides a sound
win/KO rung; it only adjusts sub-prize survival scoring, the loss rung, and promote-family stand-downs.

## Scope

- **IN:** the reachability primitive per Locked Decision 1 (one evolve hop + one attach + derived burst
  allowance, ceiling/charged policy switch on `_threat_forms`); the `_incoming_worst` refactor onto it
  (Decision 2 — thin adapter, five call sites); the loss rung (Decision 3); the interpose/dont-promote
  stand-down (Decision 4 safety gate); the grant-aware routing residue (Decision 5); the ADR-0043
  deprecation marking (Decision 6 — done this session; code removal is the build follow-up).
- **OUT:** any opponent search/tree (Decision 6 deprecates the last one); `active_doomed` unification
  (named follow-up, own re-baseline); fine hypergeometric draw-odds (deferred, its own note); per-card
  situational opponent modeling; learned opponent models.

## Success measure

- **Variant 1** (bench Riolu 1 energy → defend): must rank correctly, **unconditionally**.
- **Variant 2** (bench Riolu 0 energy → greedy): must rank correctly **under a matched Lucario Read**
  (the fixture must establish the brief match, γ over threshold); with no match the agent correctly
  stays defensive — that is the specified behavior, not a failure.
- **Regression gates:** `test_critical_0cbc_*` / `test_critical_6858_*` re-verified on their REAL
  states (the WON'T-FIX amendment's safety gate — the Starmie mirror must still read doomed); the
  class-D correction set in `t0-planner-disposition.md` (bad_target 26, prize-math, `ignored_threat`,
  `missed_disruption` — e.g. ep84889539); no regression on `interpose`/
  `dont-promote-into-their-prize-reach`'s existing passing cases (reviewed correction corpus + the
  tuner's score-diff gate).
- **Escalation deprecation check:** before the removal build-task lands, confirm no reviewed
  correction case depends on an escalation pick (they cannot today — every shipped agent runs
  `search_budget: 0` — but the corpus re-check makes it evidence, not inference).
- **Budget for the blast radius:** the five call sites flip together; expect synthetic-fixture flips
  and re-baseline them deliberately — give fixture opponents the energy/evolution they are meant to
  threaten with (the recipe from `incoming-affordability.md`'s definition-of-done), or assert the new,
  more-accurate read where that is the correct outcome. The last, smaller Incoming change broke 19
  tests; plan for it, don't discover it.
- Cost: one reachability pass per opponent body per candidate line, bounded by bench size (≤5) × forms
  × attacks — cheap; confirm against the Kaggle ~10min/match budget once wired (measure-first, no hard
  caps yet).

## Where things live

- **The gap:** `_incoming_worst`, `_survives_after_ko` — `src/common/strategy/planner.py:2048-2075`;
  all five call sites: `planner.py:1391, 1575, 2054, 2117, 2424`. Leaf survival term: `_leaf_value`,
  `_PLANNER_SURVIVAL_W` — `planner.py:2033-2046`.
- **The primitive to build on:** `_threat_forms` / `_threat_clock` — `src/common/strategy/objectives.py:263-318`
  (ADR-0045); the loss-rung precedent: `_two_ply_value` — `planner.py:2402-2426` (ADR-0043,
  deprecated per Decision 6 — the precedent is conceptual and survives the code's removal).
- **Existing evolution-aware / grant-aware reads:** `forward_incoming_damage`, `incoming_active_damage`,
  `active_doomed` — `src/common/strategy/combat.py:273-330`; `_ForwardIndex` —
  `src/common/scouting/forward_index.py` (ADR-0020).
- **The promote family:** `src/common/strategy/baseline/baseline_promote.py` — `interpose-the-cheap-
  attacker-to-preserve-the-wincon`, `dont-promote-into-their-prize-reach`, `promote-the-ready-wincon`.
- **Card/attack facts:** `pilot._attack_stat(attack_id)` (`src/common/pilot.py`), `CardStat`/
  `data/EN_Card_Data.csv` — **verify at source**, per `CLAUDE.md`, never recall (this doc's own numbers
  were pulled this way — the pattern to repeat when building).
- **Rules:** `docs/rules.md` §4 (evolution timing, the Mega-ex turn-not-ending delta, effects cleared on
  evolve) — the authority for whether the opponent's worst-case line is even legal.
- **Lockout state:** `TransientTracker` — `src/common/transients.py` (ADR-0033).
- **The Read / budget derivation:** `src/common/scouting/` (Scout/Read/EvoPath, briefs), the
  `board.opponent` facade — `src/common/opponent_model.py` (ADR-0047), `src/common/opponent_resources.py`
  (`copies_left_odds`, `hand_size_delta`); rep-list scan sources: brief artifact +
  `src/common/card_functions.json` (`energy_accel`) + `EN_Card_Data.csv` (special energy units).
- **The amended WON'T-FIX:** `docs/todo/incoming-affordability.md` — the ADR must record the amendment.
- **Deferred sharpening:** [hypergeometric-fetch-closure.md](hypergeometric-fetch-closure.md).

## Builder gotchas (carried forward — a remote/fresh session needs these without local memory)

- **This layer is HEURISTIC, not sound** — unlike the win rung and unlike ply-1's search. It must never
  preempt a sound win/KO; it only refines sub-prize survival/promote scoring plus the gated loss rung
  (which composes below the win rung by construction — Decision 3).
- **Bounded pessimism, not blind pessimism** — the bound is now PRINCIPLED: typed-cost arithmetic +
  the derived burst allowance (Decision 1), worst-case only when the Read is unmatched. Never a
  magic-number fudge in either direction.
- **The loss rung is deliberately NOT a scale change** — `_PLANNER_SURVIVAL_W` stays 50; do not "tune"
  the rung's magnitude, it is `-KO_SCORE` by definition (one prize of caution for a predicted loss).
- **Verify every card/rule fact at the point of use** — this doc's numbers (Mega Brave 270/{F}{F}/
  lockout, Ignition {C}{C}{C}, the single-hop evolution, the turn-not-ending delta, effects-cleared-on-
  evolve) were pulled from `pilot._attack_stat` / `EN_Card_Data.csv` / `docs/rules.md` this session; a
  builder must re-verify for whatever card/matchup a real correction names.
- **`tune.py` clobbers `tuned.json`**; **`src/cg/` is off-limits**; retest through the real `decide()`,
  never an isolated hand-built probe (manufactures phantom misplays by omitting realistic options).

## Related

[[posture-target-selection-gap]] · [[snipe-threat-two-signals]] · [[promote-after-ko-priority]] ·
[[opponent-model-facade-adr-0047]] · [[prize-economy-fetch-grilled]] · [[readiness-leaf-spend-account]].
ADRs: 0020 (Forward Evolution Index), 0031 (Turn Planner), 0033 (TransientTracker), 0040 (Match
Objectives / Path Denial), 0043 (Escalation two-ply — DEPRECATED by Decision 6), 0044 (opponent-choice
snipe reads), 0045 (Threat Clock), 0047 (Opponent Model facade), 0061 (lock follow-up cost).
