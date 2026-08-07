# ADR-0064: Incoming counts the opponent's next development step, budgeted by the Read

**Status.** Accepted (grilled 2026-07-16, six locked decisions). **BUILT 2026-07-16/17** — the threat read, the refactor, the loss rung,
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

- **Escalation removal (Decision 6) — DONE (2026-07-17).** The corpus re-check was clean (no correction
  fixture depends on an escalation pick; every agent runs `search_budget: 0`), so the whole Tier-6
  cluster was physically removed: `_escalate`/`_commit_escalation`/`_two_ply_value`/`_close_attack_tie`/
  `_top_k_candidates`/`_opp_disruption_density`/`_disrupt_weight`, the `_ESCALATE_*`/`_DISRUPT_TAGS`
  constants, the `escalation` ctor param + runtime PROFILE key, and both dedicated test files.
  `search_budget` is kept (now inert) so the submission manifest stays Tier-0 (test-pinned). ADR-0043
  header + the ledger row updated to "Deprecated & Removed".

**All six ADR-0064 decisions are now built and suite-green.**

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
([ADR-0065](0065-card-worth-is-one-marginal-oracle-with-a-closure-graph-backend.md)).

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
  the T0 planner disposition (since deleted); `interpose`/
  `dont-promote-into-their-prize-reach`'s existing passing cases (reviewed correction corpus + the
  tuner's score-diff gate); the escalation corpus re-check before its removal task lands.
- Retest through the real `decide()`, never an isolated probe; `tune.py` clobbers `tuned.json`;
  `src/cg/` is off-limits.

## Deferred

- **`active_doomed` unification** onto the budget model — behind its own fixture re-baseline
  (Decision 2). **DONE 2026-07-23** (the doom-shadow grill,
  the doom-shadow grill handoff (since deleted) RULED appendix): a
  RELAX-ONLY matched-Read gate (`Pilot.doom_matched_relax`, PROFILE ON) — behind a γ-matched Brief
  with no discard-recur fuel, a worst-case doom cry stands only if the charged curve confirms it
  under `Pilot._DOOM_CHARGED` (`base_attach: 2` — the doom consumer budgets the manual attach PLUS
  one generic supporter-accel, Crispin/Waitress being pool-generic; the grill found
  `_incoming_budget`'s `base_attach: 1` would have relaxed genuinely-doomed frames — a ×2-weak
  Riolu vs a Munkidori whose discard visibly held a Crispin). The conjunction direction matters:
  the charged read's own extra reach can credit forward forms the worst-case forward gate does not
  (a 1-Energy Makuhita → Wild Press 210), so it may only CLEAR doom, never add it (the 82525101-14
  Ultra-Ball-discard pin). Pinned by `tests/strategy/test_doom_matched_relax.py`.
- **Escalation code removal** — behind the corpus re-check (Decision 6).
- **Hypergeometric draw-odds** for the availability gate — its own note
  ([ADR-0065](0065-card-worth-is-one-marginal-oracle-with-a-closure-graph-backend.md)).
- **Loss-rung v2:** a bench of guaranteed-dead bodies (all KO-able next turn) as a doom equivalent of
  bench-empty — v1 gates on the literal visible fact only.

## Amendment A — the hand-size divergence is RETRACTED, not implemented (2026-07-30, Issue #213)

Decision 2 kept `active_doomed` unconditionally worst-case and named the follow-up. When that
follow-up was shadowed (S1b, `doomed_incoming` + `Pilot._threat_shadow`), the shadow's
documentation recorded **two** divergences between the worst-case incumbent and the Threat-Clock
curve:

1. the curve gates the current form on affordability (`can_pay_cheapest` under one attach), and
2. the curve omits the `hand_size_attacker` forward counter.

**(2) was never true on a production path.** Alakazam's Powerful Hand carries the Damage Formula's
`atk_hand` scaler on its `AttackStat` like any other scaling attack, and all six Incoming call
sites thread the per-decision damage context, so the curve prices it — in fact slightly HIGHER than
the hand-rolled branch did, because the generic term reads the full hand where the branch spent the
card used to evolve. Measured against the real provider at a 7-card hand, both reads return 140 for
an Alakazam Active *and* for a Kadabra one evolution away, and both call it doomed.

So the claim is **retracted rather than implemented**. `forward_incoming_damage`'s hand-size branch
is deleted (dead on every production path), the card-level case moves into the single shared
`CombatMath.card_level_damage` fallback that both fallback paths now reach, and the equivalence is
pinned by `REQ-DOOMSHADOW-0004`.

**What is unchanged.** Decision 2 stands: `active_doomed` remains unconditionally worst-case.
`REQ-DOOMSHADOW-0002`, which pins the **affordability** divergence, is untouched — its fixture
carries no hand-size attacker and its premise was never in question. Divergence (1) is now the only
one, and it remains the shadow's whole reason to exist.

**Evidence.** `threat_sweep.py --doom` after the change: **304/319 agree, 15 disagreements, all
one-directional (incumbent-doomed-only)**. The same 15 the pre-change sweep reported on a corpus
that has since grown from 274 frames to 319 — the retirement moved the doom agreement by exactly
nothing, which is what "this divergence was never real" predicts.

## Amendment B — the loss rung is the TERMINAL-LOSS family, not the bench-empty rung (2026-08-02, Issue #283)

Decision 3 named its trigger *"my bench empty + budgeted Incoming ≥ my Active's HP"* and called the
result a predicted **game loss**. The second half of that name was always the general claim; the
first half was one instance of it. `docs/rules.md` §7 lists three win conditions, and Decision 3
guarded only **case 2** (*no Pokémon in play to replace a KO'd Active*). **Case 1** — *you win when
you take your last prize card* — is reachable by the same next-turn Knock Out the same clock already
budgets, and nothing priced it.

### The gap, and why it is this term's

*"They are at 3 prizes and my Active is a 3-prize Mega"* is a **loss**. *"They are at 6 prizes and my
Active is a 3-prize Mega"* is an **exposure**. The value stack scored them identically, because the
fact is the PRODUCT of a body's prize yield and their remaining count and `state_value`'s
double-counting rule splits those across two families that may not combine: `survival` prices
`prize_at_risk × halve(turns_to_ko_me − 1)` and names `my_prizes_remaining` in its `does_not_read`;
`prize_race` prices the counts and names `prize_at_risk` in its. `registry_gaps()` reported nothing —
the fact was *claimed*, just by families structurally unable to form it. This is the double-counting
rule producing a blind spot rather than preventing double-counting, and the remedy is not to relax
the rule: it is to put the fact where a game-ending fact already belongs. `_predicted_loss` is the
one term licensed to price outside the positional band, charging `LOSS_PRIZES`, which POC-T3 DERIVED
to exceed the largest sum every other family can express.

**This is not a disjointness breach, and the distinction is load-bearing.** Case 1 consults their
prize count as a **win-condition TEST**, never as race value. What `does_not_read` protects is the
RACE — lead and proximity — and `prize_race` keeps sole ownership of it. Both families say so in
their `composition`, and `prize_race`'s points back so the reader arriving from that side lands on
the argument too.

**The registry fact stays `predicted_loss`, already in `survival.reads`.** What enters the scalar is
the terminal verdict; their count is an input to that verdict the way `turns_to_ko_me`'s own inputs
are, and no family declares those either. Adding a second fact string for the count so the read
would show up in the tuples was considered and rejected: `sound_rules.SCHEDULED_PAIRS` records the
same temptation and the same answer — *"distinguishing them by tacking '(the CombatMath-gated
reading)' onto one would make the coverage map read as two separate facts, and the double-guard
detector would pass VACUOUSLY"*. So `double_counted()` and `registry_gaps()` stay empty on their
merits and the read is documented in prose, which is the only place a nuance the vocabulary cannot
express can honestly live. **It is deliberately NOT in `blind_to`** — that field's contract is
dimensions owned by NOBODY, `blind_spots()` feeds it to Issue #263's composer as the
uncovered-dimension checklist, and putting a covered fact there would corrupt a machine-read list to
make a documentation point. Only the MARGIN below the test goes there, because that genuinely is a
zero nobody prices.

### What changed

- `state_value._predicted_loss` returns True on **either** case, sharing one clock read and this
  ADR's `evo_min_energy=1` bounded-pessimism guard **verbatim**. Dropping the guard for the new case
  would fire the term on boards the incumbent leaves alone — a behaviour change disguised as a port.
- Case 1 spans **both my areas**, because §7 case 1 is about a BODY and not about the Active Spot: a
  chipped multi-prize body on the Bench under a live snipe rider ends the game just as finally. The
  area is declared to the clock (`my_benched=`), which confines a benched body's reachability to the
  snipe/spread riders and honours Tera bench-immunity (`docs/rules.md` §11) instead of crediting
  printed damage that cannot land there.

  **The cost of that reach, measured and stated rather than left to be found.** Case 2 is gated on a
  VISIBLE fact (my Bench is empty) before it consults the clock; case 1's gate is a prize comparison,
  so on a board where their count is low it consults the clock for every body I own. Under the
  ceiling energy policy — ADR-0064's own `doom-ceiling-fail-direction`, whitelisted STRUCTURAL — an
  attack is credited once it is payable under `attached + 1`, so an opponent Active carrying **no
  Energy at all** can still stamp a chipped multi-prize benched body as lethal. That is the same
  pessimism the incumbent already applies to the Active, applied to one more body; it is not a new
  fail direction, but it is a WIDER one, and if a wave ruling ever finds it firing on boards a human
  would play through, this paragraph is where to start rather than the case-1 test.
- The count comes from `model.prize_race.opp_prizes_remaining`, so an ABSENT `prize` zone reads 0
  and 0 is falsy — the fail direction, not an accident. A hand-built board that carries no zone
  makes no claim, and a board on which they have already taken their last prize has no next turn to
  predict. No new accessor: the model already owns the read.
- A second whitelist entry, `prize-lethality` (`common/sound_rules.py`, rendered in
  `docs/plans/value-system-poc-plan.md` §6). A DIFFERENT board fact guarded by the same term, so it
  is its own typed row rather than a reworded one, and `undeclared_double_guarding()` stays empty
  because no other DECIDER guards it.

### The magnitude is BINARY (ruled, Issue #283)

A body whose loss hands them 2 of the 3 prizes they need is worse than the flat exposure `survival`
prices, but it is **not** a loss. A graded form is sharper and riskier; the honest POC answer is the
test that matches the win condition, and the graded form is recorded as a post-POC question — in
`survival`'s `blind_to`, so Issue #263's composer sees the margin as a named zero rather than an
accidental one. The term's `bool` return makes the ruling structural rather than conventional, and
`REQ-LOSSRUNG-0001` carries a test on the 2-against-3 case so a later graded form is a deliberate
change rather than a drift.

### Prior art, recorded rather than re-derived

`promote_retreat_value.PromoteBody.fatal()` (ADR-0100 §7a) already prices this fact at the
**promote/retreat** site — `KO_SCORE if prizes >= opp_prizes_remaining >= 2`, gated on a clock of 1,
standing down on a Knock-Out trade. That is `mega_lucario`'s CRITICAL prize-trade doctrine already
covered where the body PICK is made. This amendment closes the other half: the **board scalar**,
which scores every candidate end board and which had no reading of the fact at all. The whitelist
keeps them apart by role — `promote-retreat-value-composed` is typed `composed-into-the-leaf` (math,
not a guard), so `facts_guarded()` does not pair them.

**The `>= 2` floor does NOT transfer, and the divergence is deliberate.** `fatal()` fires only when
`prizes >= opp_prizes_remaining >= 2`; case 1 here has no floor. The floor is right there and wrong
here because the two sites rank different things. `fatal()` ranks **sibling bodies** at one promote
decision: at 1 prize remaining every body of mine is fatal, so the term is constant across the
candidates and orders nothing — carrying it would add a `KO_SCORE` magnitude that changes no pick.
`state_value` ranks **candidate boards**: at 1 prize remaining a board that leaves my Active doomed
charges `LOSS_PRIZES` and one that does not (I healed above the Incoming, retreated, or Knocked out
their only attacker) charges nothing, so the term discriminates exactly where it matters most.
Suppressing it at 1 would blind the scalar on the last turn of the game. This is Decision 3's own
*"no paralysis"* property — *"uniform doom across candidates cancels in the ranking; the rung only
moves picks where lines differ in exposure"* — read one level up: uniform across BODIES is not
uniform across BOARDS.

### Where this landed, and where it did not

`PlannerMixin._predicted_loss` (`strategy/planner.py`) is the INCUMBENT rung and is **untouched**.
POC-T3 (Issue #262) replaced `_engine_leaf_value`'s hand-composed leaf with `state_value`, which
left that method with no production caller; `_engine_leaf_value`'s own docstring names it in the
list T4 (Issue #263) deletes with the rollout. Extending a method nothing calls would have priced
this fact nowhere and added a second spelling for T4 to reconcile. Issue #283's body predates T3's
merge and reads as though the two were one function — they were, until 2026-08-02.

### Deferred, unchanged

**Loss-rung v2** (a Bench of guaranteed-dead bodies as a doom equivalent of bench-empty) is still
open: this amendment adds a second CASE, not a second reading of case 2's bench fact.
