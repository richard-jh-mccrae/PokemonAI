# ADR-0064: Incoming counts the opponent's next development step, budgeted by the Read

**Status.** Accepted (grilled 2026-07-16, session grill on
[`docs/plans/2ply-opponent-survival-grill-spec.md`](../plans/2ply-opponent-survival-grill-spec.md) —
six locked decisions). **BUILT 2026-07-16/17** — the threat read, the refactor, the loss rung,
grant-awareness AND the charged matched-Read relaxation landed and suite-green; only the promote
stand-down (Decision 4 consumer) remains (see §Build status). Deprecates ADR-0043; amends the
`incoming-affordability.md` WON'T-FIX.

## Build status

**Landed and suite-green (Decisions 1 both directions, 2, 3, 5):**
- `CombatMath.reachable_incoming` (`src/common/strategy/combat.py`) — the one reachability primitive:
  current form + one forward evolution hop, BOTH energy policies (ceiling worst-case / charged
  per-attack typed affordability with the colourless-burst split), transient-grant-aware on the
  current form. Unit-tested end-to-end incl. the typed/colourless split (`tests/strategy/test_reachable_incoming.py`).
- `_incoming_worst` (`planner.py`) refactored to a thin adapter over it — all five call sites flip
  together; pool-forward existence gate; default **ceiling / worst-case** energy policy (the
  `_incoming_budget` stash is `None` in v1 ⇒ every survival read is unconditionally worst-case, the
  bounded-pessimism default). Fixes the named bug (a benched evolving threat is now seen). No fixture
  re-baseline was needed — added pessimism flipped no asserted decision.
- The `-KO_SCORE` predicted-loss rung (`_predicted_loss`, wired into `_engine_leaf_value`) — gated on
  the visible bench-empty fact + budgeted Incoming ≥ HP. Unit-tested (`tests/strategy/test_predicted_loss_rung.py`).
- Grant-awareness (Decision 5) comes for free through the primitive: self-lock/same-lock/self-bonus
  honoured on a body's live-Active form, so the two engine-leaf call sites now read a locked opponent
  Active correctly; benched bodies carry no grant.
- **The charged matched-Read relaxation (Decision 1 safety direction, variant 2).** `_incoming_budget`
  is populated in `_board` behind a γ-matched Brief: `{"base_attach": 1, "burst_on_evo": 2}`, else
  `None` (worst-case ceiling for an unrecognized opponent — never relax on a guess). The
  colourless-burst-allowance derivation dilemma **dissolved**: since a colourless burst can only ever
  make a *colourless-costed* attack more reachable (the pessimism-safe direction — it can never fund a
  typed {F}{F}), a flat matched-archetype `burst_on_evo=2` keeps a burst nuke (Nebula ●●●) doomed
  (so the `planner_6858` mirror stays lethal, re-verified green) while the typed/colourless split
  sharpens genuine typed-cost reach (variant 2's "greedy is fine"). No fragile per-special-energy unit
  accounting needed. Ignition's `{C}{C}{C}` lands only on an Evolution, so the burst is evolution-gated
  in the primitive (verified against the card text).

**The phantom-threat guard (surfaced by the build, `evo_min_energy`).** The loss rung + worst-case
ceiling first produced a **turn-2 `-KO_SCORE` catastrophe**: a lone Cinderace faced an opponent's
0-Energy benched Staryu, and the ceiling credited that Staryu evolving to Mega Starmie ex and Jetting
Blowing for 240 (×2 Water weakness) — the exact "assume-they-have-everything → play scared" phantom the
grill's builder-gotcha warned of. Fix: the catastrophe rung earns a stricter evidence bar than the ±50
survival nudge — its reachability read credits an evolution hop only off a pre-evo that ALREADY carries
Energy (`evo_min_energy=1`; a bare 0-Energy pre-evo needs the evolution in hand plus a from-scratch
attach and is not a credible next-turn game-ender). This distinguishes variant 1 (Riolu WITH 1 Energy →
loss rung fires → defend) from the phantom (0-Energy Staryu → no catastrophe). Pinned by
`test_reachable_incoming.py::test_evo_min_energy_*` and `test_predicted_loss_rung.py::…phantom`.

- **The promote stand-down (Decision 4 consumer).** `Board.opp_cannot_punish_wincon` runs the charged
  safety read against my best benched win-condition; when the opponent's board cannot KO it next turn,
  `interpose-the-cheap-attacker-to-preserve-the-wincon` and `dont-promote-into-their-prize-reach` both
  stand down so `promote-the-ready-wincon` (+40) wins (scenario 3). The build surfaced the soundness
  line: the veto fires **only behind a matched Read** (`_incoming_budget` populated) — unmatched → fail
  CLOSED (keep interpose; a placeholder/unmodelled opponent must never expose a 3-prize wincon on a
  can't-model read, the "under-counting feeds them the wincon" direction). Pool-forward existence +
  `evo_min_energy=0` keep it pessimistic even when matched. Pinned by
  `test_promote_preserve_wincon.py::test_standdown_veto_is_matched_read_only`; the existing interpose
  cases still fire (unmatched in-test → veto off).

**Remaining:**
- Escalation code removal (Decision 6) — already gated on a corpus re-check; ADR-0043 marked Deprecated.
  All six decisions are otherwise built and suite-green.

## Context

`Pilot._incoming_worst` (`src/common/strategy/planner.py:2056-2075`) — the closed-form **Incoming**
behind the leaf's survival term (`_PLANNER_SURVIVAL_W = 50.0`) and `_survives_after_ko` — allows the
opponent one Energy attach and **never an evolution**. A benched Riolu is priced as Riolu's own attack
(Accelerating Stab, 30), never as "promote → evolve to Mega Lucario ex → attach → Mega Brave 270" —
a line that is legal in ONE opponent turn because evolving into a Mega ex does not end the turn
(`docs/rules.md` §4, `[RULE: rulebook L335]`). The false negative is exact and reproducible: my
270-HP-remaining Mega Starmie ex reads "survives" against a 1-Energy benched Riolu that kills it.

Three constraints shaped the fix:

1. **Cheapest-gated max.** `predicted_max_damage` deliberately does not filter attacks by
   affordability ("counts each body's biggest attack once it can afford its cheapest"), so a naive
   evolution extension credits a 1-Energy Mega Lucario ex with Mega Brave 270 — collapsing both
   directions into "always doomed" and playing scared everywhere.
2. **The WON'T-FIX.** `docs/todo/incoming-affordability.md` records that a blind affordability cap on
   the survival read was built and **reverted (2026-07-07)**: on the real CRITICAL states
   `planner_6858`/`planner_0cbc`, a Mega Starmie mirror at 1 Energy held a hidden **Ignition Energy**
   and fired Nebula Beam next turn — the capped read said "not doomed" and re-opened the blunder.
3. **The machinery mostly exists.** `_threat_forms` (`objectives.py:280`, ADR-0045) already yields
   `(cost, damage, energy, evo_hops, promo)` per opponent body × form × attack, one forward hop via
   the `_ForwardIndex` (ADR-0020), promotion-surcharge-aware, per-attack affordability-exact;
   `incoming_active_damage` (`combat.py:279`) already honors TransientTracker grants. The gap was
   never "build a reachability primitive" — it was that `_incoming_worst` is the one Incoming read
   that never learned what `_threat_forms` knows.

## Decision

### 1. One reachability primitive: per-attack, typed-cost-shape affordability under a Read-supplied energy budget

Consolidate on `_threat_forms` with a **ceiling/charged policy switch**; `_incoming_worst` becomes a
thin adapter over it (one Incoming home, not a fifth dialect). Affordability is charged per attack,
**per cost shape** — the sharpening that dissolves the WON'T-FIX dilemma:

- **Typed slots can only be paid by typed energy.** Ignition Energy (id 17) provides **{C}{C}{C}**
  (self-discards): it pays Nebula Beam's `●●●` in one attach — the planner_6858 burn — but can
  **never** pay Mega Brave's `{F}{F}`. Colorless burst does not threaten typed costs; the arithmetic
  knows the difference, so no deck-level "assume the worst" is needed.
- **Energy budget** = attached + 1 attach + a **colorless-burst allowance derived from the matched
  Read's representative decklist** (special energy providing >1 unit, `energy_accel`-tagged
  trainers/abilities — derived by scan, calibrated tier, never a hand-asserted brief boolean).
- **Attack-based accel is excluded from the one-step budget** — provably, not approximately: one
  attack per turn means Aura-Jab-class accel can never fuel its own attacker the turn it attacks, and
  its past uses are already visible in `attached`.
- **Unmatched or low-γ Read → worst-case budget** (affordability uncharged). Fail-scared, never
  fail-brave. Accepted consequences: early game plays cautious until the Read matches; a
  matched-but-wrong Read (a rogue list with unseen typed accel) loses a game and is the
  blunder-buster pipeline's problem — never a magic-number fudge.

This **amends the WON'T-FIX**: the survival read stops being unconditionally worst-case and becomes
charged-with-archetype-budget, defaulting to worst-case. Under the new model the planner_6858 mirror
still reads doomed (Starmie's Read carries Ignition; Nebula Beam is colorless-costed → burstable), so
the original blunder stays fixed — re-verified on the real states as the safety gate.

The worked pair (verified card facts, `EN_Card_Data.csv` / `pilot._attack_stat`):

| opponent bench Riolu | their best reachable next turn | vs my 270 HP | correct play | condition |
|---|---|---|---|---|
| 1 Energy | promote → evolve → attach 2nd {F} → Mega Brave **270** | exact KO | defend (Wally's) | unconditional |
| 0 Energy | promote → evolve → attach 1st {F} → Aura Jab **130** | survives | greedy (Lillie's) | **matched Lucario Read only** — no trainer/ability/special-energy accel in the rep list reaches {F}{F} |

### 2. Scope: refactor all five `_incoming_worst` call sites together; `active_doomed` is a named follow-up

The five call sites (`planner.py:1391, 1575` snipe-survival; `2054` `_survives_after_ko` + its seven
callers; `2117, 2424` engine leaves) flip together through the adapter — one function, one question; a
partial flip is two survival dialects in one file. `active_doomed` (`combat.py`) is separate machinery
and **stays worst-case**: unifying it is a follow-up behind its own fixture re-baseline (it carries
the 19-test blast radius that got the last affordability attempt reverted mid-session).

### 3. Predicted loss is a rung, not a weight

When — and only when — a candidate line's end board has (a) **my bench empty** (visible fact, zero
prediction error) and (b) **budgeted incoming ≥ my Active's HP** (Decision 1's read), the line's leaf
value gets **`-KO_SCORE`** added (equivalently: returned as a floor) — the `_two_ply_value:2418`
precedent ("the reply WON for them"), which is conceptual and survives that code's removal
(Decision 6). Nothing else changes: `_PLANNER_SURVIVAL_W` stays **50** and keeps pricing the
ordinary, recoverable lose-a-body case. Properties:

- **Composes with prizes:** 1 prize taken (+1000) into bench-empty doom (−1000) nets ≈ 0 and loses to
  any safe positional line; a line that wins outright still dominates (the win rung returns
  `KO_SCORE × (prizes+1)` before leaf math) — the hard-rung invariant holds untouched.
- **No paralysis:** uniform doom across candidates cancels in the ranking; the rung only moves picks
  where lines differ in exposure — e.g. it rewards benching a Basic turn 1 (the anti-donk play).
- **No scale change:** no existing constant moves, so no ADR-0060-style re-audit of the old scale —
  only the new code path. The rung's magnitude is `-KO_SCORE` *by definition* (one prize of caution
  for a predicted loss); it is not a tuning knob.

### 4. Availability gate: existence for threat, matched Read for safety

The drafted "is the evolution anywhere in their deck+hand" is **uncomputable** — hidden zones; the
leaf's my-side evo-gate is a false mirror (my deck+hand are visible to me, theirs never are).
Replaced, asymmetric by direction because the failure costs are asymmetric (over-counting their reach
costs a −20 nudge; under-counting it feeds them the 3-prize wincon):

- **Threat direction** (survival / loss rung): existence only — the pool-level `_ForwardIndex` says
  something evolves from the body. A benched Riolu *is* the evidence they run the Mega; Decision 1's
  budget bounds the pessimism.
- **Safety direction** (the promote stand-down): requires the **matched Read** — rep list contains
  the evolution, minus visibly-exhausted copies (KO'd/discarded/prized; `copies_left_odds` where
  cheap). No match → no stand-down; never promote the wincon on a guess.

Consumers: the reachability read vs the wincon's HP becomes the **stand-down condition** on
`interpose-the-cheap-attacker-to-preserve-the-wincon` (all three drivers) and
`dont-promote-into-their-prize-reach`, letting `promote-the-ready-wincon` (+40) win when the
opponent's board literally cannot punish it. Hypergeometric draw-odds stay deferred
([hypergeometric-fetch-closure.md](../plans/hypergeometric-fetch-closure.md)).

### 5. Transient locks: narrower than drafted

Benched bodies cannot carry a live grant (serial-binding — a body that leaves the Active presents a
new serial), so `_survives_after_ko` needs no lock read, and `incoming_active_damage` already honors
grants for their Active. Residue: route the two engine-leaf call sites that include their Active
(`planner.py:2117, 2424`) through the grant-aware read. Evolution clears attack effects (`rules.md`
§4), so a forward form escapes its pre-evolution's lock — the serial mechanism gives this for free.

### 6. The ADR-0043 two-ply escalation is DEPRECATED

Ruled: an opponent-reply search is neither feasible nor necessary — we never assume their hand; we
deduce reach from visible zones (board, hand size, prizes, discard) plus the Read. The escalation's
reply sim is structurally blind to hidden-hand development (it can only make the opponent play
visible cards — never the Mega Lucario ex we cannot see), which is the threat class that decides
these boards. It was already dead in production: `escalation` defaults `False`, escalation is
`search_budget`'s only functional consumer, and **every shipped agent pins `search_budget: 0`**;
`planner.py:270` records the prior two-ply-opponent-tree regression. ADR-0043 is marked Deprecated
(ledger + file header); physical removal of `_escalate`/`_commit_escalation`/`_two_ply_value`/
`_close_attack_tie`/`_density_trigger`/`_top_k_candidates` and the switch is a follow-up build task,
gated on a corpus re-check that no reviewed correction depends on an escalation pick.

This layer itself never simulates opponent moves, never resolves coins, and never overrides a sound
win/KO rung — it only adjusts sub-prize survival scoring, the loss rung, and promote stand-downs.

## Consequences

- **`docs/todo/incoming-affordability.md` is amended** (pointer added): the survival read becomes
  charged-with-archetype-budget with a worst-case fallback; `active_doomed` itself stays worst-case
  until its own follow-up. `test_critical_0cbc_*` / `test_critical_6858_*` re-verified on their REAL
  states are the amendment's safety gate.
- **Blast radius is budgeted, not discovered:** expect synthetic-fixture flips across the five call
  sites; re-baseline deliberately — give fixture opponents the energy/evolution they are meant to
  threaten with (the WON'T-FIX note's own definition-of-done recipe), or assert the new,
  more-accurate read where that is the correct outcome. The last, smaller Incoming change broke 19
  tests.
- **Variant 2's acceptance test is conditional by design:** the fixture must establish the matched
  Lucario Read (γ over threshold); with no match the agent correctly stays defensive — specified
  behavior, not a failure. Variant 1 is unconditional.
- **No-regression gates:** the class-D correction set in
  [`t0-planner-disposition.md`](../plans/t0-planner-disposition.md); `interpose`/
  `dont-promote-into-their-prize-reach`'s existing passing cases (reviewed correction corpus + the
  tuner's score-diff gate); the escalation corpus re-check before its removal task lands.
- Retest through the real `decide()`, never an isolated probe; `tune.py` clobbers `tuned.json`;
  `src/cg/` is off-limits.

## Deferred

- **`active_doomed` unification** onto the budget model — behind its own fixture re-baseline
  (Decision 2).
- **Escalation code removal** — behind the corpus re-check (Decision 6).
- **Hypergeometric draw-odds** for the availability gate — its own note
  ([hypergeometric-fetch-closure.md](../plans/hypergeometric-fetch-closure.md)).
- **Loss-rung v2:** a bench of guaranteed-dead bodies (all KO-able next turn) as a doom equivalent of
  bench-empty — v1 gates on the literal visible fact only.
