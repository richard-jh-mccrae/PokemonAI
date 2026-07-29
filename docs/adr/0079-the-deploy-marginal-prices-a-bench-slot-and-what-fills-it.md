# ADR-0079 — The deploy marginal prices a bench slot and what fills it

**Status:** DRAFT — grilling in progress (`/grill-with-docs` on Issue #197, 2026-07-29). Decisions are
recorded here as they lock; nothing below is built. **Expect renumbering at merge** (#136 directive 8 —
0079 is claimed, not settled; ADR-0078 is itself claimed-not-merged on the Issue #199 line).

**Context issues:** Issue #197 (this grill — split out of the Issue #161 grill as the pregame-Bench
half), Issue #161 (`starter_priority`, the Active-slot sibling), Issue #136 (the Value System build
tracker), ADR-0069 (attach, Phase 1a — the axes-sum shape this follows), ADR-0070 (evolve, Phase 1b),
ADR-0073 (promote/retreat, Phase 1c — `PRIZE_DAMAGE_RATE`), ADR-0065 + ADR-0076 (the Needs assignment
this extends), ADR-0078 (the currency triangle), ADR-0034 (deck rules fold general when the vocabulary
is general), ADR-0072 (the gates a decider swap owes).

## Context

Issue #197 was opened as a narrow question — does the *pregame* bench placement (`_SETUP_BENCH`,
SelectContext 2) want a deck declaration the way the Active slot got one in Issue #161? The grill
widened it on the user's framing: **bench filling is not a setup event, it is a whole-game decision**,
and the interesting cases are mid-game.

Facts established at source before the first ruling (2026-07-29):

- **Meowth ex (1071)** — Basic, 170 HP, `{C}`, weakness `{F}`, retreat 1, **2 prizes**.
  *Last-Ditch Catch*: "**Once during your turn, when you play this Pokémon from your hand onto your
  Bench**, you may use this Ability. Search your deck for a **Supporter** card, reveal it, and put it
  into your hand. Then, shuffle your deck. **You can't use more than 1 Ability that has 'Last-Ditch'
  in its name each turn.**" *Tuck Tail* `●●●` 60 puts the body and all attached cards back into your
  hand — so a benched Meowth is **re-armable** for a later second fetch
  (`data/EN_Card_Data.csv`).
- **Set Up precedes the first turn** (`docs/rulebook.txt` L110–122), so "once during your turn" is
  structurally unsatisfiable at `_SETUP_BENCH`: pre-benching Meowth genuinely burns the Ability.
  The Bench holds **5** (L75, L122); benching Basics from hand is unlimited per turn and order-free
  (L120–122), so a bench drop is a **Commutative Set** member, not a Maneuver.
- **The bench slot is unpriced today.** Every bench rule gates on `c.board.my_bench < _BENCH_MAX`
  — a hard binary — and `Board.bench_full` is a boolean. The 5th slot costs exactly what the 1st
  costs: nothing.
- **Meowth's bench drop is mis-modelled as development.** `bench-the-supporter-tutor` (+25,
  `doctrine_fetch.py`) is gated on `not board.line_ready` (i.e. SETUP) **and**
  `board.no_supporter_in_hand` — so it cannot fire mid-game for a *specific* Supporter while any
  Supporter at all sits in hand. The value of the drop is a **fetch** value, not a development value.
- **The rule layer shows the diagnostic symptom of an unpriced resource:** three separate NEGATIVE
  rules exist only to veto deployments a slot price would have out-ranked on its own —
  `dont-pre-bench-the-supporter-tutor` (−15), `dont-pre-bench-a-redundant-utility` (−15),
  `dont-bench-multiprize` (−15) — alongside seven flat-weight rules in `baseline_bench.py`.
- **#197's "no motivating frame" premise is false.** `ml_dont_bench_redundant_solrock_f51` is a
  CRITICAL correction naming exactly the slot-scarcity defect: *"played a 2nd Solrock into the last
  bench slot … clogs the bench needed for the Makuhita→Hariyama line."* None of the three vetoes
  caught it, because the defect was the **cost of the last slot**, not the identity of the body.
  Supporting frames: `dp_dont_pre_bench_redundant_munkidori_f4`,
  `ml_dont_play_a_needless_pokemon_tutor_f114`, `ms_free_bench_evolve_f17`,
  `setup_bench_decline_f3` (the already-solved pregame Meowth case).
- **`supporter_tutor` is absent from `needs.SUPPLIES`**, so a bench-drop tutor has no slot kind to
  fill and no route into the Needs assignment.
- The Value System has per-seam equations for attach (1a), evolve (1b), promote/retreat (1c) and the
  opponent-target family (1e). **There is no deploy/bench phase.**

## Decisions

**1. Bench/deploy becomes the missing per-seam value equation — the Deploy Marginal — not a rule
repair and not a deck declaration.** *(User ruling, 2026-07-29.)*

One equation answers "what is putting THIS body into a bench slot worth, right now?", denominated in
the same damage currency as ADR-0069/0070/0073, and it DECIDES (no shadow staging — #136 directive 1).
It spans the whole game, not the pregame: the setup placement is simply the case with the longest
deadline and no Ability trigger. The flat rules it replaces are DELETED, not suppressed — the seven
`baseline_bench.py` Hypotheses plus `bench-the-supporter-tutor` /
`dont-pre-bench-the-supporter-tutor` / `dont-pre-bench-a-redundant-utility`.

Rejected alternatives:

- *A targeted rule-layer repair* (a bench-pressure signal + a sharpened `supporter_tutor` gate). Buys
  a fourth veto and leaves the currency problem: f51's defect is not expressible as a weight on a
  body, because it is a property of the SLOT.
- *A deck-declared `Strategy.bench_priority`* (Issue #161's sibling). Hardcodes per deck what is plainly
  general vocabulary — Roles, Function Tags, Needs slots, prize value — which ADR-0034 says folds
  general. It would also have to be re-declared for every future deck, and it cannot express
  "bench Meowth *this* turn because *this* Supporter is now needed."

Consequence for Issue #197's stated agenda: its item 3 ("the two-vocabulary cost" of a declaration for
the Active slot and derived rules for the Bench) is **superseded rather than answered** — the Bench
gets an equation, so the asymmetry with Issue #161's `starter_priority` becomes deliberate, and item 4's
shared-completeness-invariant question falls away with it.

Cost accepted with the ruling: this is a Value-System decider swap and owes the full ADR-0072
gauntlet (a `deploy_decider_sweep.py` Decision Gate with zero unruled REGRESSIONs, the Discrimination
Gate against `data/leaf_lab/baseline.json` run BEFORE the arming decision, and the mid-build
Tripwire A/B), its own glossary entries, and a sequencing decision against the in-flight
Issue #199 → Issue #187/#188/#189 chain.

**2. The slot cost is an EXACT ASSIGNMENT over deck-reachable suppliers — never a constant, never a
binary gate.** *(User ruling, 2026-07-29.)*

The Bench is five deadline-tagged slots in the `needs.py` slot family (ADR-0065's DP, as extended to a
second family by ADR-0076). The **supplier set** is the deployable bodies in hand **plus** the bodies
reachable from deck, read through `fetch_closure`'s **reach** direction (ADR-0073) and weighted by
Deck-Content Odds. The marginal is a difference of assignment values —

```
deploy_marginal(X) ⊃ − [ assignment_value(suppliers) − assignment_value(suppliers, X pinned) ]
```

— so the cost of the 5th slot is **emergent**: exactly the contribution of the supplier it displaces.
Zero on an empty Bench, steep on a full one with live candidates, and it needs no tuned constant. The
`my_bench < _BENCH_MAX` binary gate and `Board.bench_full` as a decision input both retire (the engine
still won't offer an illegal placement; that is the engine's job, not a weight's).

The deck leg is load-bearing rather than incidental. On the motivating frame the displaced body is
**Makuhita, in the deck** — reachable via the Ultra Ball in hand — and the human's recorded reason is
literally *"clogs the bench needed for the Makuhita→Hariyama line."* A hand-only supplier set prices
f51's last slot at ~0 and would leave the slot term untested by the only evidence there is for it.

Alternatives rejected, and why the frame does not settle it by itself: **f51 admits two independent
diagnoses.** The 2nd Solrock is also *redundant* (Solrock + Lunatone already in play; the readiness
leaf's `_READINESS_SATURATED` prices a duplicate utility body at 0.1×), so a body-side-only equation
(*option 3: no slot term*) and a hand-only assignment (*option 2*) BOTH land the right answer on that
board — for a reason the human did not give. That is the weight-coincidence pattern ADR-0069 catalogues
(the desperation attach that lived at `+15 − 12 = +3`). Only the displacement reading generalizes to
the case the user raised — filling every Bench slot with a *suboptimal combination* — because a bad
combination is one where every body looked fine individually and the SET was wrong, and only an
assignment sees sets.

Costs accepted with the ruling: the term reads a hidden zone, so it owes ADR-0077 **Leg Assignment**
discipline (this is a RANKED consumer, so a count question reads `expected` and a presence question
reads `p_any`; it may never read either as a gate); it adds a `fetch_closure` reach query to the
deploy path; and the supplier set needs an explicit cap, since the DP is `_MAX_KEEP_SLOTS`-bounded
at 16.

*(Further decisions appended as they lock.)*
