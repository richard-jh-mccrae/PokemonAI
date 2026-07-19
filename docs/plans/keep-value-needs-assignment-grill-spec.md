# Keep-value v2: needs-assignment — GRILL SPEC (seeded, NOT grilled)

**Status:** SEEDED 2026-07-19 from a user concern, immediately post the seam-D swap. Design NOT
settled — grill before code (the shadow-equations ruling repeals construction-waits only for settled
designs). The live equation (9/9 on the discard corpus) keeps deciding meanwhile.

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

## Open grill questions (the rounds this spec needs)

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

## Acceptance (pre-committed)

- Every retired gate's anchor case re-derives: `86091435-68`/`83686860-18` (deploy-now pair),
  `83037962-49` (successor), `83457493-31` (dead fetchers), `82753102-16` (need-met),
  `83454549-36` (spent burst), `84071010-45` (fuel), `83967840-54` (worth tie), quota/ADR-0060 pins.
- The duplicate-pair set case (forced discard-2 of two wincons) — the one the current equation still
  gets wrong — flips WITHOUT a new gate.
- The live 9/9 discard corpus holds; the full suite + the six ADR-0060 pins hold; the readiness
  leaf-lab metrics do not regress if the seam is shared.
