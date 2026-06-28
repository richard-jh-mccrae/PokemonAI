# Agent Architecture — the Pilot

Deck-agnostic decision engine (`src/common/`). It turns each engine Observation
into a legal move the same way for every deck; a deck contributes only its `deck.csv` and a
declarative `strategy.py`. Optimised for **legibility** — every decision is explainable —
because in the Strategy Category the deliverable is the *reasoning*, not the ladder rank.

Glossary: [common/CONTEXT.md](../src/common/CONTEXT.md). Decisions:
[ADR-0012](adr/0012-optimize-for-strategy-category.md) (optimise for the Strategy Category),
[ADR-0008](adr/0008-pilot-is-a-layered-rules-pipeline.md) (this pipeline),
[ADR-0007](adr/0007-learning-is-one-offline-value-model.md) (the value-model seam),
[ADR-0009](adr/0009-training-methodology.md) (how it is tuned). Related runtime:
[General Strategy](general-strategy.md), [Scouting](scouting.md), [Function Tags](card-functions.md),
[Weights](weights.md), [Agent Checks](agent-checks.md).

## Thesis

The original contribution is not a single strong deck — it is a **general competence layer**
any thin deck-doctrine plugs into. Rules are the backbone (transparent, testable); learning
enters later at one seam ([ADR-0007](adr/0007-learning-is-one-offline-value-model.md)) without
becoming the backbone. A transparent rule agent whose every choice is justified beats a
stronger black box here, so we make the reasoning a first-class *output*
([ADR-0012](adr/0012-optimize-for-strategy-category.md)).

## The agent is a move-selector

The engine never asks "what do you do?" — it enumerates the legal options
(`obs.select.option`) and asks "which?". The Pilot returns indices into that list (count in
`[minCount, maxCount]`, unique, in range). Mulligan, setup, attach, evolve, attack, yes/no —
**every** decision is that one shape. The Pilot's job is to *score the options*.

## Pipeline: Sense → Plan → Score → Act

```
agent(obs) ─► Sense ───► Plan ────► Score ───────────────► Act ─► [option indices]
               │          │          │
   obs (+Read)─┘   SETUP / RACE /    per option:  Σ firing Hypothesis weights   (positional)
                   STABILIZE /                  + Tactical Evaluator             (combat)
                   CLOSE                         ─► take argmax, maxCount of them
```

- **Sense** — read the Observation (board, hand, my setup progress) and the Scout's **Read**.
- **Plan** — pick the current-turn mode from a *closed* set (`SETUP / RACE / STABILIZE /
  CLOSE`). Selection is shared logic parameterised by the Strategy: stay in `SETUP` until a
  win-condition **Line** is `ready` (payoff in play with enough energy), then `RACE`. So
  *"set up fast"* is an emergent consequence of a tunable readiness threshold, not bespoke
  code.
- **Score** — assign each option a number (below).
- **Act** — return the highest-scoring legal selection.

## The Strategy (per-deck doctrine)

A deck supplies `agents/<deck>/strategy.py`: pure data, no engine, no control flow.

```python
Strategy(
  name="mega_starmie",
  lines=[Line(path=[STARYU, MEGA_STARMIE_EX], payoff=MEGA_STARMIE_EX,
              role="win_condition", ready=Ready(energy=3))],   # CCC for Nebula Beam
  roles={CINDERACE: ["accel_source", "starter"], IGNITION_ENERGY: ["accel_source"], ...},
  params={"setup_energy_target": 3},                            # tunable scalars
  hypotheses=[Hypothesis(id="open-cinderace", rationale="...", when=<trigger>,
                         weight=40, status="assumed"), ...],
)
```

- **Function Tag vs Role.** A **Function Tag** is *universal and mechanical* — what a card
  does (`draw`, `search`, `energy_accel`, `heal`, …), probed offline and shipped as
  `card_functions.json` ([ADR-0006](adr/0006-function-tags-single-source-of-structural-facts.md),
  [Function Tags](card-functions.md)). A **Role** is the *per-deck* purpose the deck assigns
  to a card (`win_condition`, `accel_source`, `tutor`, …) — a sparse overlay drawn from a
  closed vocabulary, so roles stay comparable across decks.
- **Hypothesis.** A named, testable claim that biases scoring: a `rationale`, a trigger, a
  tunable `weight`, and a `status` (`assumed → testing → confirmed / refuted`). It is the
  unit the writeup is organised around.

Worked example: [agents/mega_starmie/strategy.py](../src/agents/mega_starmie/strategy.py).
This replaces the per-deck imperative style of
[demos/rules-based-lucario.py](../demos/rules-based-lucario.py) (hard-coded card ids + magic
numbers, no reuse or tunability).

## Scoring — hypotheses + the Tactical Evaluator

`Score(option) = Σ weight_h · fires_h(ctx)  +  tactical(option)`

- **Positional** judgement is the sum of firing Hypothesis weights. Because the score is
  *additive*, it is **linear in the weights** — which makes both tuning (a convex ranking
  fit, see [ADR-0009](adr/0009-training-methodology.md)) and explanation (read off which
  hypothesis moved the choice) easy.
- **Combat** judgement is the **Tactical Evaluator**: it ranks attack options by
  engine-computed outcomes (KO / bench-snipe / prize math), never authored damage numbers.
  Hypotheses *bias* it; they do not replace it.
- **Metareasoning / the Search budget.** Tier-0 is closed-form (printed damage × weakness vs
  HP) and covers most decisions, including all of mega_starmie's attacks. Tier-1 escalates to
  the engine's Search API only when it changes the decision (effectful attacks, lethal
  confirmation, close-line lookahead) and the per-move budget allows. `search_budget=0` ships
  by default — no lookahead until live timing justifies it. The grader gives **2 vCPUs and
  ≈10 min/match** ([Agent Checks](agent-checks.md) → Grader resources), so any lookahead is
  bounded by wall-clock on 2 cores, **not** by memory — RAM is ample at 12.2 GiB. The Pilot
  **never crashes or times out**: a bad hypothesis or malformed observation degrades to a legal
  fallback.

## Posture — the Read changes play *(designed; wiring pending)*

[Scouting](scouting.md) already produces the **Read** (recognised opponent Archetype +
confidence, threats, targets). **Posture** consumes it through the seams above, all
**confidence-gated** (unknown opponent → Posture ≈ off; recognised → ramps up):

1. a deck-agnostic generic core in the Pilot — seek `targets`, avoid `threats`, calibrate
   aggression to favourability (strength across matchups, free for every deck);
2. deck-specific Read-conditioned Hypotheses;
3. feeding the Read's predicted opponent deck into `search_begin` (Tier-1).

## Training — three jobs ([ADR-0009](adr/0009-training-methodology.md))

| Job | Tunes | Signal | Method |
|---|---|---|---|
| A · Weights | Hypothesis weights + params | dense per-decision labels | linear ranking |
| B · Value model | the Tier-1 leaf-eval | replay states → win/loss | supervised (LightGBM) |
| C · Selection | which config ships | ladder win-rate | A/B gate |

Labels for (A) stack from three ladder-gated sources: *winner-imitation*, *peer
blunder-correction* (mark a blunder on any replay of our deck), and *own-Pilot
blunder-correction* (the gold, targeted signal). A **Correction** is
`(state, chosen, correct, attribution, rationale)`: it yields a ranking label and may create
or edit a Hypothesis. **Downloaded replays are the data engine; self-play is the evaluator,
on-policy filler, and source of our own games to correct** — a replay is a frozen film you
mine, not an opponent you can box against.

## Legibility — the writeup writes itself

Every decision can emit a one-line rationale (card → tag/role → Hypothesis → Plan). The
default-vs-tuned weight diffs, the Hypothesis `status` transitions, and the Correction log are
the documented experiment trail the Strategy Category scores. This document is the spine; the
instrumentation fills it in. What the final writeup must contain — Kaggle's
[Winning Model Documentation Guidelines](writeup-guidelines.md) mapped to each of these
artifacts — is the [Strategy Writeup guidelines](writeup-guidelines.md).

## Layout

```
src/
  common/
    pilot.py    Sense→Plan→Score→Act, choose_plan, Tactical Evaluator
    strategy.py Plan/Ready/Line/Hypothesis/Strategy + closed Plan & Role vocab
    cards.py    CardFunctions (Function Tag loader)
    scouting/   Scout / Read
    value/      Base Value Model loader            [planned]
  agents/<deck>/  main.py · deck.csv · strategy.py · tuned.json (machine overrides)
tools/
  meta_tracker/  replays → meta + scouting artifact + card_functions
  sim/           Agent Checks (Playability / Deployability on the real cabt env)
  train/         replay parser · blunder inspector · weight-tuner · value trainer   [planned]
  selfplay/      self-play harness (evaluator + on-policy + correction source)       [planned]
```

## Build · run · test

- **Tests** (fast, lib-free): `python -m pytest tests/ -q`. Pilot behaviours are
  `REQ-PILOT-####`; tests build observation dicts by hand (`tests/pilot_helpers.py`) and never
  load the native engine.
- **Verify on the real engine**: `python tools/sim/check_agent.py mega_starmie` — **Playability**
  (a full self-match, no crash/timeout/illegal) and **Deployability** (the packaged Bundle),
  on the pinned cabt env ([Agent Checks](agent-checks.md)).
- **Package**: `python tools/package_agent.py mega_starmie` assembles the submission Bundle.

## Status

- **Built** (TDD): the pipeline runs end-to-end and always returns a legal selection;
  `choose_plan` (SETUP→RACE); additive Hypothesis scoring over the deck Strategy **merged with the
  deck-agnostic [General Strategy](general-strategy.md)** (override-by-id, `0` disables); the
  **decision trace** (`Pilot.explain` → which Hypotheses fired, for the writeup); `Context` carries
  the engine `CardStat`; the Tier-0 Tactical Evaluator applies **Weakness ×2** (Active only);
  `CardFunctions`; mega_starmie wired end-to-end.
- **Designed, not yet wired**: Posture (the Read → play); the richer Tactical Evaluator
  (Jetting-Blow bench-snipe / wall-disruption); the [General Strategy](general-strategy.md) roadmap
  (board-state rules); the `tools/train` + `tools/selfplay` loop and the Base Value Model. These
  are the next slices.
