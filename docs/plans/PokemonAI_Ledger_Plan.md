# The Ledger: 1-ply Worth-Differencing Decider

**Status:** SUPERSEDED by Issue #582's canonical Feature Catalog and linear activation model.
This file preserves the original build plan; its weight-vector and per-Brief override claims are
historical, not live architecture. Steps 1–7 shipped as ADR-0145 (the Ledger + runtime swap) and
ADR-0146 (the preview seam). Step 8, the manual training rounds, is UNDERWAY: the grading
harness was made honest first (ADR-0147 — own-prize anchor, retired rulings), scouting now
originally priced the opponent's side with per-Brief overrides (retired by Issue #582), and the §7 nudge loop was
rebuilt as `tools/train/ledger_tune.py` (per-nudge zero-regression gate, reports under
`docs/tuning/runs/`).

**Role:** Phase 1 — the Ledger replaces Bellman as the sole live decider: a single-decision
(1-ply) lookahead that prices every option by the board-value change it causes and takes the
best one. Trained manually against the corrections corpus until the generality dashboard
satisfies the owner. Phase 2 — the same evaluator migrates into search as the branch-ordering
policy prior, per `PokemonAI_Search_Policy_Value_Handoff.md`. The Ledger is the same evaluator
that eventually serves multi-decision / multi-turn evaluation; it is deliberately ONE system,
not a bundle of bespoke per-aspect value functions.

---

## 1. The evaluator: worth moving between zones

One equation. Board value = Σ over every visible card: `worth(card, context) ×
position_multiplier(zone, usability)` + the prize race, with the opponent's side counted by the
same equation and negated.

- **Zones (own side):** in play and powered > in play bare > in hand > in deck > discarded.
  Attached energy and tools score through the body they sit on.
- **Usability-dependent multipliers, not flat:** an energy attached to a body whose attacks and
  retreat cannot consume it contributes 0 benefit. The position multiplier asks the card store
  (attack costs, retreat cost, ability fuel) whether the attachment is consumable.
- **Historical design:** card worth came from the ADR-0143 card store through a general weight
  vector plus per-deck overrides. Issue #582 replaced this with the canonical Feature Catalog,
  full Valuation Configuration, and own-deck sparse coefficient deltas.
- **Demand-aware, combination-aware hand worth.** A card in hand is priced against what the
  board is missing, not what the card supplies in the abstract (the ADR-0127 lesson). Pairs
  matter: Rare Candy with its evolution in the same hand outprices either alone. This
  nonlinearity is what makes sampled-hand evaluation (§3) meaningful.
- **Opponent side:** same equation, negated. Unseen opponent hand cards carry a flat expected
  worth (hand size is visible); scouting may sharpen this later.
- **Currency:** prizes, so numbers stay comparable with Bellman's.
- The old seventeen-family value stack (`value.py`, `potential.py`, `demand.py`) is NOT
  imported. It is the checklist of what the one equation must account for: prize race, damage
  progress, readiness, hand access/demand, opponent hand, energy position, development, bench
  scarcity, prize liability, special conditions.

### Only ending the turn is worth zero

End-turn is the zero baseline. Every other action = benefit − the full worth of what it
consumes. Consequences the equation must produce:

- Attaching a dark energy to a body that can't use it: benefit 0 − energy worth → negative →
  refused.
- Damage counters are a priced resource: counters placed on a body already at ≤0 effective HP
  destroy nothing → 0 benefit − the spend → negative → refused.
- Ultra Ball with nothing needed from the deck: fetch benefit below the two discards + the
  card itself → negative → waits.
- Benching: a bench slot is a scarce good with option value, and a benched body is prize
  liability. The fifth redundant basic prices at or below zero; the basic that grows into the
  win condition prices high.

---

## 2. Transitions: engine applies, BoardState digests

For each option on the menu, the pure-Python engine copy plays it (the same `TransitionProvider`
seam the solver uses) and prints the resulting board. `BoardState.advance(printout)` (ADR-0144)
digests it. The Ledger is BoardState's first production consumer. (Changed-piece re-pricing is
DEFERRED: v1 re-evaluates the whole board — measured 30–80 ms per decision, the cache is not
yet needed; `BoardState.changed` is the seam when it is.)

- "All card mechanics covered" comes from the engine: anything it can execute, the Ledger can
  price. No hand-written transition prediction (the old composer's stub graveyard).
- Pricing an option resolves its forced follow-up prompts inside the preview: Ultra Ball's
  discard choice and fetch choice are chosen greedily by the same Ledger, expected value at
  random points. The preview's sub-choices are advisory — when the real prompt arrives, the
  Ledger re-decides on the real board.

---

## 3. Chance model: sampled hands, exact probabilities

Per `PokemonAI_Supporter_Decision_Handoff.md`: never decide a shuffle/draw Supporter from
P(draw card X). Compare expected value of the resulting states against not playing it.

- Small outcome spaces enumerate exactly (a coin flip is a 50/50 branch — Harlequin's two
  legs are both evaluated, including the opponent's mirror draw on each leg).
- Large outcome spaces (a 6-card hand off a shuffled deck) are sampled: draw whole hands,
  evaluate each resulting state with the Ledger, average weighted by probability.
- Hypergeometric closed forms (the ADR-0029 machinery's concept) feed the chance model —
  outcome weights, at-least-one checks — but never decide the action directly.
- **Sampling is seeded from the state key**: replaying a correction frame yields the same
  answer every time. The sample budget is bounded for the match clock.
- Phase 1: each sampled hand is read by the Ledger's static evaluation. The chance machinery
  is a seam: phase 2 swaps the static read for a short search continuation without touching
  the probability model — the handoff doc's bootstrap→mature path.

---

## 4. Turn policy: spend the turn, then end best

Split every menu: turn-continuing actions vs turn-enders (attack, pass). While any
turn-continuing action has a positive swing after honest costs, take the best one. Only when
nothing is worth doing, compare the turn-enders and take the best. The Ledger re-decides after
every action, so ordering quirks resolve themselves (playable cards get played before a
shuffle-hand Supporter because dumping them first raises its swing). Accepted bootstrap
myopia: it never holds a positive-swing play back for a future turn.

---

## 5. Coverage policy: decide anyway, log the gap

An unknown card gets the standing floor worth; an unmodelled random outcome gets a neutral
default. The decision still happens. Every such event writes a coverage note tagged with the
exact card and mechanism, counted per decision actually affected (never per mention — the
census lesson). The notes are the gap-closing worklist.

---

## 6. Runtime placement: Ledger live, Bellman quarantined

- The Ledger becomes the one live decide() path for all deck agents.
- Bellman is quarantined under `deprecated/` as an offline teacher only. Future sequence search
  belongs to the generic Search Algorithm.
- **Rename first, own commit:** Bellman's `algebra.Ledger` class becomes `BellmanLedger` so the
  new system owns the name. Mechanical sweep across the kept code and tests.
- No mid-match fallback to Bellman — mixed-brain training data was explicitly rejected.
- Archived Bellman tests are historical evidence, not a current validation suite.

---

## 7. Training: corrections corpus through a new harness

- Replay the existing correction frames (all three decks with corrections: mega_starmie,
  mega_lucario, dragapult_ex) through the Ledger. Every
  disagreement with a human ruling was a training signal: adjust general coefficients first; reach
  for a deck tweak only when a deck genuinely dissents from the general rule.
- **The harness surfaces the ruling's rationale** beside every disagreement: frame, the
  Ledger's pick with its price breakdown, the ruled play, the rationale text. The rationale is
  context — some old rulings may deserve a second look rather than a weight nudge.
- New blunders from watched games are filed as new correction frames, as today.
- Tuning method: the documented nudge / keep-best-so-far / adoption-gate methodology,
  re-pointed at the Ledger's canonical valuation configuration.
- Watched-game batches start with dragapult ex; replay grading covers all decks from day one.

### Done bar (ends phase 1)

The generality dashboard, then the owner's call:

1. Agreement rate with human rulings per deck — the general configuration alone must clear the bar
   on every deck; deck tweaks only polish the remainder.
2. Zero regressions: frames it already gets right stay right.
3. A watched batch of full games per deck with no new must-fix blunder filings.

---

## 8. Build order

Each step lands with its tests; docs and CI adjustments ride the step that makes them true.

1. **Rename** `algebra.Ledger` → `BellmanLedger` (own commit, mechanical, suite stays green).
2. **Evaluator core** — `src/common/ledger/`: worth × position over BoardState, symmetric
   sides, demand/combination-aware hand terms, cost charging. Unit tests per §1 consequence
   (the dark-energy refusal, the dead-counter refusal, the Ultra Ball wait, bench scarcity).
3. **Preview seam** — engine applies an option, BoardState digests, changed-piece re-pricing;
   forced-chain resolution. Tests against pinned engine frames.
4. **Chance model** — exact branches, seeded hand sampling, hypergeometric weights, bounded
   budget. Tests: determinism under replay, Harlequin two-leg EV, Lillie's hand-swap EV.
5. **Decider loop** — spend-the-turn rule, gap logging. Full-game smoke via cgpy.
6. **Runtime swap** — decide() routes to the Ledger; Bellman unplugged; pinned-choice gates
   re-pointed or quarantined case by case. ADR covering the Ledger, the swap, and the rename.
7. **Replay harness + dashboard** — corrections corpus replay, rationale-surfacing triage
   view, per-deck agreement numbers, regression tracking, coverage-note worklist.
8. **Training rounds** — manual, per §7, until the done bar.

---

## 9. Non-goals (phase 1)

- No learned models; weights are hand-trained.
- No multi-action beam or sequence search (that is phase 2, where this evaluator becomes the
  prior and the leaf read inside search).
- No revival of old composer code — its dependency stack is deleted; its lessons live in §1/§4/§5.
- No import of the old value families — checklist only.
- No ladder-strength claims: the scoreboard is generality on the corrections corpus, not win
  rate.
