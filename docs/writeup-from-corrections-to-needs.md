# From Hand Corrections to a General Theory of Card Value

**Competition-writeup source material** (feeds [writeup-guidelines](writeup-guidelines.md) §A4
Features and §A6 Interesting Findings). This documents one working arc — the keep-value line,
reviewed and rebuilt 2026-07-19/20, merged as PR #121 — because it is the clearest single example
of the project's method: *human corrections are the teacher, hand-built features are the
curriculum, and the destination is a general mechanism that derives what the features asserted.*
Full chronological detail: [ADR-0065 §Build status](adr/0065-card-worth-is-one-marginal-oracle-with-a-closure-graph-backend.md)
and [the grill spec](plans/keep-value-needs-assignment-grill-spec.md).

---

## The story, plainly

Our agent learns from being corrected. When it makes a move a human would never make — throwing
away the card its whole game plan depends on, shuffling back a hand full of live pieces — we
record the moment, mark what the right move was, and that correction becomes part of the agent's
curriculum. Over months this produced a real skill: dozens of small, named rules, each one born
from a specific recorded mistake. "Never discard the burst Energy — unless the attack it funds is
already paid for." "A tutor is worthless once the card it fetches is in your hand." "A spare copy
is cheap to lose — unless it's the copy you can *evolve this very turn*."

Each rule was true. But look at their shape: every one is an **exception to an exception**. The
owner named the problem before any measurement did:

> "a bunch of gates … in essence hypothesis/features/rungs tacked on the equation. That feels
> brittle … who's to say that we don't in the future just need more and more and more gates that
> begin to undermine each other?"

That intuition was correct, and the fix was not another rule. It was a reframe. Instead of asking
*"what is this card worth, minus a patch, plus a patch?"*, the agent now asks the question a human
actually asks: **"what does my situation need, and which cards fill those needs?"** Like packing a
suitcase — you don't rate each item in isolation; you ask what's still uncovered. Two identical
rain jackets? Each one *alone* looks redundant, but you'd never toss both. The old rule pile made
exactly that mistake with our two copies of the deck's star Pokémon; the new mechanism *cannot*
make it, because it prices the pair as a pair.

The corrections didn't become obsolete. They became the **exam**. The new mechanism had to
reproduce every recorded human answer before it was allowed to decide anything — and where it
disagreed, each disagreement was studied until it either exposed a flaw in the mechanism (fixed by
derivation, never by patch) or, in one memorable case, a flaw in the recorded answer itself: shown
the equation's full working, the human re-reviewed their own correction and ruled the *agent's*
pick correct.

---

## The technical arc, in five stages

### Stage 0 — corrections compile to features

The base architecture ([ADR-0017](adr/0017-corrections-compile-to-hypotheses.md)): every recorded
correction becomes a weighted Hypothesis (a rule with a `when=` condition and a tuned score), fit
offline against the correction corpus. The discard decision alone accumulated a 12-rung tuned
ladder (`keep-key-cards −30`, `keep-line-base −15`, `discard-the-dead-opener`, …). This works —
and it is where the "features" of a classical ML writeup live in a rules agent: each rung is a
hand-engineered feature with a learned weight.

### Stage 1 — features consolidate into an equation (v1)

The card-worth oracle ([ADR-0065](adr/0065-card-worth-is-one-marginal-oracle-with-a-closure-graph-backend.md))
replaced per-rule scores with one equation in one currency:

```
keep_cost(X) = Worth(X) × Gates(X) × (1 − re-access Odds over the Closure)
```

Worth = a tuned role/tag tier table; Odds = hypergeometric deck math; Closure = the tutor/search
graph; **Gates = the deadline factors**, and here is the key observation: *every gate was a
hand-compiled special case of the same underlying quantity*. The grilled definition of worth is
marginal — `worth(X | state) = best-plan(with X) − best-plan(without X)` — and each
correction-born gate is a human pre-computing that marginal for one situation:

| gate (born from a correction) | the marginal it hand-compiles |
|---|---|
| deploy-now spike (`86091435-68`) | without X, the evolve-this-turn play vanishes — huge |
| dup-in-hand / in-play | another copy runs the line — tiny |
| need-met (`82753102-16`) | the tutor's target is already in hand — zero |
| spent burst (`83454549-36`) | the attack is funded; the card self-discards anyway — ~zero |
| fuel / zone sign (`84071010-45`) | the discard pile is an *input* — negative cost |
| pressure gate (`83037962-49`) | without it, no answer after the KO — spiked |
| quota ranks | the k-th copy's use is k−1 turns deferred — discounted |

The brittleness is structural, not aesthetic: **gates do not compose by construction.** Each pair
needed a bespoke ordering rule (the closing edge had to beat re-access; the engine floor had to be
a *worth* floor or it broke the need-met gate). Interaction surface grows ~O(n²) with each new
correction-born gate.

### Stage 2 — the reframe: needs as data, value as assignment (v2)

Instead of hand-compiling the marginal per case, compute it. Reify what the position requires as
**slots** — deadline-tagged needs derived from board state, never authored: *fund this attack*
(one slot per missing Energy, deadlines from the once-per-turn attach quota), *finish this
evolution line* (plus a half-tier succession slot: the plan must survive attrition), *answer the
incoming KO*, *keep a draw engine online* (saturating), *fetch the win condition* (absent once
it's in hand), *fuel the discard-cost attack* (a slot filled **by pitching**). Then:

```
V(hand)   = max assignment of held cards to slots   (exact bitmask DP, ≤16 slots — no greedy;
                                                     a counterexample refuted greedy in the grill)
keep(X)   = V(hand) − V(hand − X)                   (the counterfactual marginal, re-assignment included)
keep(set) = V(hand) − V(hand − set)                 (exact set semantics — sets, not sums)
discard   = argmin over pick-sets of
            max(keep(set), max member hedge) − Σ pitch gains,  ties → lower residual worth
```

Every gate becomes a *property of the slot structure* instead of a multiplier: need-met is slot
**absence**; the spent burst is fund-slot absence; duplicates price marginally because a sibling
covers the slot; the deploy-now spike is a deadline-0 slot no re-access can refill; fuel rides the
pitch side of the objective. Interactions that were impossible pairwise (a tutor whose fetch is
the deploy-now enabler for a *different* need) resolve globally in one assignment.

### Stage 3 — retiring features without losing their knowledge

Two soundness nets, both CI-enforced, make the migration safe:

- **The coverage lint**: every worth source (every role, every tag) must name ≥1 slot kind it can
  supply — because a *missed* need sheds a good card, the wrong failure direction.
- **The dissolution ledger**: every v1 gate must name the slot that re-derives it. Retiring a gate
  without its deriving slot is a red test. No correction's knowledge can silently evaporate.

And a transitional **hedge**: v2 never prices a card below v1's shipped answer until the resolver
is complete — a firing hedge is telemetry for a missing slot, not a silent regression.

### Stage 4 — evidence-gated migration (the discipline is the method)

Nothing swapped on argument. Every step ran **shadow-first**: the new equation computed at every
real decision and *emitted beside* the shipped decision, deciding nothing, until the corpus
cleared it.

- **Discard — cleared and shipped.** First sweep: 8/12 agreement with the human corpus. All four
  disagreements adjudicated to resolver gaps and fixed *by derivation*: the succession slot
  ("copy 2's marginal is its next-best slot"), line slots restricted to bodies (an Energy's
  derived role must not resurrect a spent burst), the draw-engine value band read off its
  suppliers, a residual-worth tiebreak. Result: **12/12**, the duplicate-pair blunder structurally
  impossible, swapped live behind a kill-switch.
- **Refresh — measured, not cleared, so not shipped.** The whole-hand shadow revealed v2
  under-priced hands in the *unsafe* direction (46 of 83 frames). One derived enrichment (a held
  card's latent worth, discounted by the readiness leaf's own deploy factor) halved it (→19) and
  flipped the residue to the safe side. The site stays on v1 until the remaining piece (the
  re-supply discount) lands. The shadow's job was to say "not yet" — it did.
- **The board-value fold — measured to a wash, parked with a proof.** Three iterations of feeding
  held-hand value into the game-planner's board scorer were benchmarked on 267 replayed frames.
  Final metric — *expected correct picks under order-broken ties* — moved 83.5 → 84.5: a wash. The
  dissection proved *why*: the remaining errors are governed by board facts the scorer cannot yet
  see (who is Active, attached Tools), which no hand term can read. Built, measured, switched off,
  and documented — the negative result is as load-bearing as the positive ones.

### Stage 5 — the epilogue the CI wrote

The merged PR's only CI failure was a heisenbug worth its own finding: the engine's simulator
auto-resolves coin flips from unseeded global RNG, and on one recorded frame a candidate line
simmed to an ordinary board on one RNG stream and a **phantom outright win** on another (162 vs
7000, same line). The fix generalizes the session's principle one more time: *an unsound value
may never preempt a sound one*. A simmed win that consumed coin flips is no longer a win claim,
and the rollout rung ranks only reproducible (coin-free) end boards. Two regression tests pin it.

---

## Why this is the submission's story

- **It reinterprets "feature engineering" honestly for a rules agent** (§A4): our features are
  correction-born rules; our "importance analysis" is the dissolution ledger — a table of which
  feature each general mechanism absorbed, with the anchor correction each one came from.
- **It answers "what set you apart"** (§A6): not that the agent has no hand-built knowledge, but
  that hand-built knowledge is treated as *scaffolding with an exit plan* — compiled from
  corrections, consolidated into an equation, then derived away by a general mechanism that must
  beat the corpus before it may decide, with every retirement provable.
- **Every number is reproducible offline**: `tools/train/probes/needs_sweep.py` (the 12/12 and the
  refresh split), `tools/train/leaf_lab.py` (the 267-frame board-value bench), the corpus suite
  (`tests/strategy/test_hyperclosure_corpus.py`). No ladder round-trip needed.

  > **Corpus Provenance** (ADR-0089 decision 2). `needs_sweep.py` read the corpus through a raw
  > JSONL walk that was short **40** records (ADR-0087, Issue #241), so "reproducible" was not quite
  > true — the sweep saw 332 frames of a 372-frame corpus. It now routes through
  > `gates.keyed_corrections`, and both readings are re-derived and stamped rather than inherited:
  >
  > * **`discard agree_v2` — the acceptance number — HOLDS: 12/12**, measured at `4be1db3`, full
  >   corpus. This is the one that gates a claim, and the widening does not move it.
  > * **The refresh split is a DIAGNOSTIC, and its population grew with the corpus**: 83 refresh
  >   decisions before, **96** now (measured at `4be1db3`) — sign-flips 16, v2 under-prices 51,
  >   v2 over-prices 41. ADR-0065's figures (83 frames; sign-flips 13→11 across its amendments) are
  >   historical readings *of their own corpus* and stay as recorded; they are not restated here.
  >
  > This is precisely why a corpus-wide ruling carries its commit and frame count. An unstamped "the
  > numbers reproduce" would have quietly meant a different set of numbers.
- **The teacher stayed in the loop both directions**: corrections trained the features; the
  equation's emitted working, in one case (`86091435-68`), out-argued the correction itself and
  the human amended the label. That closed loop — legible reasoning a human can audit and be
  persuaded by — is the Strategy category's thesis in one anecdote.

## Artifact index

| artifact | role |
|---|---|
| `src/common/needs.py` | the slot vocabulary, exact assignment, soundness nets |
| `src/common/pilot.py` (`_resolve_needs`, `_needs_v2`, shadows) | the board→slots resolver + emitters |
| `src/common/{card_worth,deck_odds,gate_library,fetch_closure}.py` | the v1 oracle (Worth · Odds · Gates · Closure) |
| `docs/adr/0065-glossary.md` | the five-term ubiquitous language |
| `docs/plans/keep-value-needs-assignment-grill-spec.md` | the grill, rulings, WP build log with all measurements |
| `docs/plans/keep-value-v2-session-handoff.md` | live state + open threads for the next session |
| `tests/strategy/test_needs.py`, `test_discard_shadow.py` | the mechanism's pinned proofs |
| `tools/train/probes/needs_sweep.py` | reproduces the acceptance numbers |
