# Keep-value v2: needs-assignment — GRILLED 2026-07-19 (all six rounds ruled; build NOT started)

**Status:** SEEDED and GRILLED the same day, post the seam-D swap. All six rounds are now ruled
(three settled by evidence, three ruled by the user — see §Grill run). Per the shadow-equations
ruling the design is SETTLED → construction proceeds shadow-first; the live v1 equation (9/9 on
the discard corpus) keeps deciding meanwhile. Build order at the bottom. **WP-N1/N2 BUILT
2026-07-19; WP-N3 BUILT 2026-07-20; WP-N4 discard swap BUILT 2026-07-20** (see §Build order) — v2
now DECIDES the forced discard (`Pilot.needs_keep_value`, PROFILE armed ON), corpus-safe (12/12)
and the duplicate-pair naivety flipped without a new gate. The refresh-SHED shadow (WP-N4b) and the
gamble/refresh swaps remain staged; the gate stack stays live for those sites + as resolver inputs.

**Development window (user, 2026-07-19):** no new Kaggle submission for ~a week; the week's work is
hashing the keep_value equations out against the existing corrections corpus (the corpus is the
bench, not the ladder). Post-submission ladder performance carries NO penalty — iterate
aggressively; swap gates may be more forward-leaning than the usual armed-off discipline. The
Round-1 hedge is accordingly DISCRETIONARY (kept because it costs nothing and its firings are
missing-slot telemetry), not a safety requirement.

**Owner concern (user, 2026-07-19, verbatim substance):** the keep_value equation now carries "a
bunch of gates … in essence hypothesis/features/rungs tacked on the equation. That feels brittle …
not adequately accounting for the true value of the card in the particular board state, thus we need
a handicap. … who's to say that we don't in the future just need more and more and more gates that
begin to undermine each other?"

## The diagnosis (source-checked)

The grilled definition of worth is MARGINAL (spec Round 7): `worth(X | state) = best-plan(with) −
best-plan(without)`. The shipped equation approximates it as INTRINSIC worth (the tier table) ×
hand-written context patches (the gates). Every gate is a hand-compiled partial evaluation of
`best-plan(without X)`:

| gate / flag | the marginal it hand-compiles |
|---|---|
| deploy-now (closing) | without X the evolve-this-turn play vanishes — huge marginal |
| dup_hand / in_play | the other copy still runs the line — tiny marginal |
| need-met (tutor) | the wincon is in hand — the tutor's fetch adds nothing |
| spent_burst | the attack is funded; end of turn discards it anyway — ~0 |
| fuel (zone sign) | the discard pile is an INPUT (Aura Jab) — negative cost |
| pressure (successor/heal) | without it, no attacker/answer after the KO — spiked |
| quota ranks | the k-th copy's contribution is k−1 turns deferred — discounted |
| engine_supporter floor | ⚠️ the first PREFERENCE gate (not a rules constraint) — the smell |

**The brittleness is specific and real: gates do not compose by construction.** Each pair needed a
bespoke composition rule (closing ordered above re-access; the engine floor had to be a WORTH floor
or it broke the need-met gate; spent-burst checked before the floor). Interaction surface grows
~O(n²). One latent undermining case already exists: need-met zeroes a tutor whose fetch might be the
deploy-now ENABLER for a different need — pairwise gates cannot see it.

**The bounded-growth defense (and its limit):** gates so far map ~1:1 to the game's FINITE resource
systems (evolution timing, per-turn quotas, zone reachability, target existence, threat deadlines) —
a rulebook-closed set, so constraint-gates are bounded. The audit criterion going forward: a gate is
legitimate iff derivable from rules + representation. `engine_supporter` is the first preference
gate; a second one means this spec is overdue.

## The thesis to grill: reify NEEDS as data; compute the marginal by ASSIGNMENT

Round 8 §4 already contains the concept: `keep-cost(X) = role value × ΔP(CLASS NEED met by deadline
| keep vs shuffle)`. The gates hand-compile "which need, met how, by when." v2 makes needs DATA:

1. **Derive need-slots from board state** (never authored — Round 9): `evolve-Active (deadline this
   turn)` · `fund-attack(body) = cost − attached` · `attach(turn t, t+1, …)` (the quota, as slots) ·
   `answer-incoming-KO (deadline from the threat read, value from the prize swing)` · `complete
   line-2` · `draw-engine (recurring)` · `supply-wincon (the tutor's slot)` · `discard-fuel
   (supplied BY pitching — the zone sign as a slot)`. Nearly all resolve from EXISTING Board
   signals (attack costs vs attached, `deploy_now_ids`, `active_doomed`/incoming, quotas,
   `deck_empty_ids`, the closure).
2. **Assign** the held multiset + closure re-supply (at its odds) to slots — greedy with re-score
   after each commitment (the `_greedy_grab` precedent; ~6 cards × ~a dozen slots, closed-form).
3. **keep(X) = coverage lost when X leaves, after re-assignment.** Marginal BY CONSTRUCTION; slot
   values stay in the ONE currency (the tier points move from cards to the slots their roles fill).

**What falls out instead of being gated** (each = an acceptance test): multi-copies (copy 2's
marginal = its next-best slot — sets-not-sums dies as a naivety, incl. the open forced-discard-2
duplicate-wincon case); energy-attached (fund-attack slots shrink as energy lands; surplus prices
low; spent_burst = "slot already met"); doom (a deadline-valued answer slot, graded not boolean);
deploy-now / quotas / fuel / need-met / covered copies (slot properties); the tutor-vs-deploy-now
interaction (resolved globally by the assignment, impossible pairwise).

**Relationship to the readiness leaf (board-state-valuation-grill.md) — do NOT build a rival:** the
needs-assignment is the closed-form LINEARIZATION of the readiness board-value: slots ≈ readiness
terms (attack/ability readiness, saturation, preconditions, the line account); keep(X) ≈ ∂readiness/
∂X over reachable boards. Two hand-crafted approximations of the same V must share ONE vocabulary
seam — grill where it lives (`common/`?) and which side owns which term.

**What stays as-is:** the one tuned currency (slot values under the correction corpus — deck-genie
still never invents numbers); the Closure as re-supply odds; the horizon discipline (positional band
only; hard rungs own the match); the fail directions.

**Rejected without grilling:** a learned V as the spine (ADR-0007/0042 park it; 12 discard
corrections train nothing; the handCount-overfit precedent) — ML stays the residue owner. Also
rejected: "just soften the booleans" (graded gates fix cliffs, not composition — same architecture).

## GRILL RUN 2026-07-19 — three rounds settled by evidence, three rulings pending

**Round 1 (slot soundness) — RULED (user, 2026-07-19): lint + transitional hedge.** The needs
vocabulary already exists in the codebase IN TRIPLICATE — the gamble's five Outcome Classes
(needs-as-GAINS: energy / evolution / pump / gust / survival), the gate library + ladder premises
(needs-as-KEEPS), and the readiness leaf's terms (needs-as-BOARD: cost-progress, ability,
saturation, preconditions) — so enumeration is unification, not invention. Because a MISSED slot
sheds a good card (the wrong fail direction — every gate erred toward keep), v2 ships BOTH: the
coverage lint (every ROLE_TIER/TAG_TIER key → ≥1 slot class it supplies; every retired gate/rung →
its deriving slot — the dissolution ledger, CI-gated) AND the transitional hedge
`keep = max(marginal, intrinsic tier)`, retiring per-family as shadow evidence clears each.

**Round 2 (assignment algorithm) — SETTLED: greedy REFUTED, exact bitmask DP.** Counterexample: A
supplies S1(20)+S2(15), B supplies S1 only — greedy prices marginal(B)=0, optimal 15 (two hand
Drakloaks vs {evolve-Active-now, line-2}). Exact assignment is lib-free trivial at this size
(~12 slots × ≤8 cards ≈ 33k ops/solve; all marginals ≈ 300k ops/decision; memoized by
hand-fingerprint for the mid-sim SHED). Bonus: a forced discard-2 asks for the PAIR minimizing
`V(H) − V(H − pair)` — exact SET semantics natively; the duplicate-wincon naivety dies here.

**Round 3 (opponent-facing slots) — RULED (user, 2026-07-19): VISIBLE state + basic lookahead of
their IN-PLAY Pokémon.** Opponent-side needs derive from what we can SEE — their board (bodies,
attached energy, forward evolution from the representation), their DISCARD contents, their hand
COUNT (never hidden contents) — plus a basic forward projection of their in-play bodies: the derived
**turns-to-ready** per body — turns until their wincon and backup Pokémon are fully energized
(energy deficit at the attach quota, accel-aware via the Read) and evolved (forward-index hops,
one per turn). Richer than the seeded existing-oracles-only recommendation, and it is what gives
opponent-facing slots their DEADLINES: a denial/disruption/answer card's slot value is graded by how
close their threat is to online (a Hammer is worth more the closer their attacker is to ready —
the user's own 86091435-68 Hammer ruling, now derivable with timing). Discipline preserved:
visible facts + representation-derived projection only — no hidden-hand guessing; ADR-0064's
pessimism still owns the threat CEILING (safety direction untouched). Existing oracles are consumed
for slot VALUES where they already price them (ADR-0062 `_opp_denial_best`/`denial_value`,
`_gust_best_ko_prizes`, the threat read, `CombatMath.turns_to_ko`, opponent Resources); the
lookahead supplies the deadline structure. Kinship noted for one-vocabulary discipline: the gusting
design's `their_keep_cost` (Worth across the table) gets this read as its natural backend.

**Round 4 (recurring-needs horizon) — SETTLED.** Deadlines, not decay (Round 8 §3 stands). Slots
materialize only where a signal resolves them: deadline-0 and deadline-1 concretely; quota rank k>2
keeps the shipped window treatment; Σ slot values capped < KO_SCORE (the readiness invariant — the
horizon discipline preserved).

**Round 5 (vocabulary + the readiness seam) — RULED (user, 2026-07-19): RATIFIED as proposed.**
**Needs** is the fifth Ubiquitous Language term (Worth · Odds · Gates · Closure · Needs); one pure
needs module; keep_value consumes it first; the readiness leaf folds in LATER and only under its
267-frame leaf-lab bench; the gate library becomes a derived view (a gate = a slot with a deadline)
and retires as each gate re-derives. The 0065 glossary carries the ratified row (module pending).

**Round 6 (migration) — SETTLED: the proven seam-D pattern.** v2 emits inside the existing
`discard_shadow` (per-row `keep_v2` + a v1-vs-v2 agreement bit) and beside the refresh SHED;
per-family swap under the corpus gates; the acceptance list below is the contract.

## Open grill questions (the original rounds, kept for the record)

1. **Slot enumeration soundness** — what guarantees a need isn't missed (the coverage-lint pattern:
   every ladder rung / retired gate maps to a slot class)? What is the fail direction of an
   UN-modeled need (errs toward keep?)?
2. **Assignment algorithm** — greedy-with-re-score vs optimal matching; does greedy's order-dependence
   ever flip a corpus case? (The Hungarian algorithm at n≈12 is trivial if needed.)
3. **Opponent-side slots** — does `answer-incoming` stay the only opponent-facing slot (ADR-0064
   pessimism owns the rest), or do gust/denial targets become slots too (the gusting design's
   `their_keep_cost` is Worth-across-the-table — same vocabulary?)?
4. **Where recurring needs end** — draw-per-turn, attach-per-turn are unbounded streams; the horizon
   cap that keeps Σ slot values < KO_SCORE (the readiness leaf's invariant).
5. **The seam with readiness** — one needs model consumed by both the leaf (board value) and
   keep_value (card marginal), or two views over shared vocabulary?
6. **Migration** — shadow-first beside the live equation (emit both, agreement bit — the proven
   seam-D pattern); each retired gate's corpus case is the acceptance test ("the gate library
   dissolves into the needs model"); per-family swap under the corpus + score-diff gates.

## BUILD ORDER (post-grill; shadow-first per the standing ruling — each WP suite-green, staged)

1. **WP-N1 — the needs module** (`common/needs.py`, the fifth glossary seam): pure slot derivation.
   My-side slots (fund-attack per body = cost − attached; evolve/deploy slots off `deploy_now_ids` +
   the forward index; attach/supporter quota slots; line completion; draw-engine; discard-fuel) and
   the RULED opponent-side read (visible zones + turns-to-ready per their in-play body). Slot values
   in the ONE currency (tier points move to the slots roles fill; oracle-priced values consumed,
   never re-derived). The coverage lint + dissolution ledger land WITH the module.
2. **WP-N2 — exact assignment + marginals** (Round 2) — **BUILT 2026-07-19.** `needs.assignment_value`
   (V = Σ uncovered·resupply + exact best coverage of v·(1−resupply), lib-free bitmask DP, ≤16
   slots), `keep_v2` (counterfactual marginal with re-assignment, hedged at `intrinsic`),
   `set_keep_v2` (joint multi-pick marginal — the duplicate-wincon naivety structurally impossible),
   `pitch_gain` (fuel slots ride the pitch side), and `cheapest_removal` (the discard objective:
   `max(set marginal, max member hedge) − Σ pitch gains`; hedge floors by MAX not SUM, preserving
   sets-not-sums). The Round-2 counterexample, the resupply-derived re-access discount, and the
   deploy-now full-loss spike are the pinned proofs (`test_needs.py`). Memoization by
   hand-fingerprint arrives with the WP-N3 resolver (the stateful side).
3. **WP-N3 — the resolver + shadow columns** (Round 6) — **BUILT 2026-07-20.** `pilot._needs_v2`
   (the Pilot-side resolver: line / deploy-now / fund-attack / draw-engine / supply-wincon /
   answer-doom / fuel slots from the live board, v1's deploy gates consumed per the ledger;
   resupply 0.0 — errs toward keep — and opponent DENY slots deferred to WP-N4) + `keep_v2` per
   shadow row and `eq2_pick` / `agree_v2` on the record, deciding nothing.
   **Build-time hedge refinement (2026-07-19):**
   the Round-1 hedge floor is **v1's KEEP value (post-gates), not the raw intrinsic tier** — a
   raw-tier floor would re-price the spent burst at 30 / the redundant tutor at 10, undoing the
   gate knowledge v1 encodes; "v2 never prices below the shipped decider" preserves it, and floor
   firings still telemeter missing slots. The refresh-SHED shadow site is DEFERRED to WP-N4 (the
   discard corpus is this week's bench; the refresh families join when their sites swap).
   **Build-time derivations (2026-07-20, from the first sweep's 4 disagreements — each adjudicated
   to a v2 resolver gap, none to the design):**
   * the **SUCCESSION slot** (`needs.line_slots`): a wincon-class line opens a second half-tier
     slot — "copy 2's marginal = its next-best slot" made concrete; a spare wincon insures the
     line against attrition, never free. The duplicate-pair headline case now picks the true
     spares (`test_v2_prices_duplicate_wincons_as_a_set_not_a_sum`).
   * **line slots are Pokémon/ACE-SPEC only**: an Energy with a line-class derived role (Ignition
     as `accel_source`) must not reopen a line slot — it resurrected the spent burst that
     fund-attack absence had just re-derived (83454549-36).
   * the **draw-engine band** reads off the eligible suppliers: engine-ROLE tier for a body need,
     v1's tuned engine-supporter band (8) when only supporters can fill it (83686860-11 — a
     12-point Lillie's out-priced the fund Energies the human keeps).
   * `needs.cheapest_removal` gained a **residual-worth tiebreak** (worth × deploy): among
     equal-marginal removals the lower residual worth sheds first — v1's worth tie-break
     re-derived (83967840-54), and the deploy-dead Cinderace sheds before a live spare.
   Post-adjudication sweep: **agree_v2 12/12** against the live decider over every replayable
   discard correction — every human `correct` the decider satisfies, v2 satisfies. Suite green
   (3133); needs + shadow suites 27.
4. **WP-N4 — per-family swaps + gate dissolution** — **DISCARD SWAP BUILT 2026-07-20.** The discard
   family cleared (agree_v2 12/12 + the duplicate-pair flip), so its site swapped:
   `Pilot.needs_keep_value` (PROFILE armed ON, kill-switch) makes `_needs_v2`'s `eq2_pick` the
   forced-discard DECIDER — precedence `needs_keep_value` > `discard_keep_value` (v1) > the ladder.
   Corpus-safe by construction; the duplicate-wincon pair v1 pitched now survives the DECISION
   (`test_v2_decides_the_discard_under_the_kill_switch`). **Gate dissolution, precisely:** the
   discard DECISION stops running v1's pairwise gate composition and flows through the global
   assignment; the gate code is NOT deleted — `_deploy_odds` / the fuel·burst flags / the quota
   window are CONSUMED by the resolver (a dead evolution's line slot valued ×0 — the ledger derived)
   AND still price the gamble keep-floor + refresh SHED, which have not swapped. **The hedge is
   RETAINED**, not retired: the resolver is still v0-scope (resupply 0.0; opponent DENY slots
   deferred), so "v2 never prices below the shipped decider" stays until the resolver completes.
   **WP-N4b BUILT 2026-07-20 — the refresh-SHED MAGNITUDE shadow, verdict: refresh NOT cleared.**
   `pilot._refresh_shed_shadow` emits v1's Σ keep_cost beside v2's whole-hand assignment marginal
   (`needs.set_keep_v2` over the held hand, via the shared `_resolve_needs` core), the two refresh
   swings (`swing_v2 = swing_v1 + (v1_shed − v2_shed)` — the shed is the only term that moves) and
   the SIGN-agreement bit — the magnitude analog of the discard's pick-agreement, deciding nothing.
   **Sweep (83 refresh decisions): 18 sign-flips, v2 UNDER-prices the shed in 46 / over-prices 35 —
   the unsafe direction (it would shuffle away hands v1 keeps).** Diagnostic, not a bug: v2's v0
   resolver is DISCARD-bench-scoped — it prices a card's line/fund/doom/fuel NEED, not its GENERAL
   worth (a spare engine/attacker/backup with no open slot; an energy on a powered Active). So the
   refresh site does NOT swap; the shadow's telemetry stages the prerequisite below.
5. **WP-N5 — general-worth slots + the readiness fold** (Round 5's condition; now also the WP-N4b
   prerequisite): the resolver gains the GENERAL-worth slots the refresh sweep proved missing — a
   card's board value where it isn't a specific line/fund/doom/fuel need — which are exactly the
   readiness leaf's board-value terms (`board-state-valuation-grill.md`), so readiness consumes the
   needs module ONLY under the 267-frame leaf-lab bench (no regression on SOLE-top / distinct-values
   / Gate 0). The refresh/gamble swaps follow once their shadows clear under the enriched resolver.

## Acceptance (pre-committed)

- Every retired gate's anchor case re-derives: `86091435-68`/`83686860-18` (deploy-now pair),
  `83037962-49` (successor), `83457493-31` (dead fetchers), `82753102-16` (need-met),
  `83454549-36` (spent burst), `84071010-45` (fuel), `83967840-54` (worth tie), quota/ADR-0060 pins.
- The duplicate-pair set case (forced discard-2 of two wincons) — the one the current equation still
  gets wrong — flips WITHOUT a new gate.
- The live 9/9 discard corpus holds; the full suite + the six ADR-0060 pins hold; the readiness
  leaf-lab metrics do not regress if the seam is shared.
