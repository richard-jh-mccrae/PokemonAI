# PokémonAI: Search, Policy, and Value Learning
## Implementation Handoff

**Design target:** scalable, high-strength play across many decks under strict runtime budgets.

---

## 1. Executive Summary

The current agent uses the Ledger for live decisions. Bellman is quarantined as an offline teacher;
its former production latency measurements are historical, not a description of the deployed agent.

The target architecture **keeps sequence search**.

The goal is not to replace planning with one-step greedy decisions. Instead:

1. Expensive search becomes an **offline teacher**.
2. Search results train a learned policy `P(a|s)`.
3. Search results and game outcomes train a learned value `V(s)`.
4. The learned policy reduces wasted search width.
5. The learned value reduces required search depth.
6. Search budgets are progressively tightened while preserving playing strength.

Manual features and strategies are bootstrap tools only. They should not remain the permanent source of deck-specific strategic intelligence.

The long-term objective is:

> **Compress expensive search into learned intuition without eliminating planning.**

---

## 2. Core Architecture

```text
TRAINING

manual hints + learned P
          |
          v
   deep / medium search
       /           \
      v             v
 policy target    value target
       \           /
        \         /
         train P,V
            ^
            |
       match outcome


DEPLOYMENT

ObservationState
      |
      v
 learned P(a|s)
      |
      v
 selective search
      |
      +----> learned V(s) at leaves
      |
      v
 best sequence / plan
```

The mature system should still search.

It should **not** reduce to:

```text
choose action = argmax V(s+1)
```

That would recreate the weakness of the original linear-combination agent: evaluating individual moves without adequately reasoning about multi-action sequences.

---

## 3. Keep P, Q, and V Separate

Do not collapse these into one generic score.

| Quantity | Meaning | Purpose |
|---|---|---|
| `P(a|s)` | Policy prior | Where should search look first / spend budget? |
| `Q(s,a)` | Search value | What has the current search discovered about this action? |
| `V(s)` | State value | If search stops here, how good is this state long-term? |

### `P(a|s)`

Answers:

> Which actions or branches deserve search attention?

Initially, this may come from manual features.

Later, it should be learned from deep-search results.

### `Q(s,a)`

Answers:

> After actually searching this action, how good does it appear?

This is search-derived information.

### `V(s)`

Answers:

> If search stops here, what is the best estimate of long-term winning prospects?

Eventually:

```text
V(s) ~= P(win | current observation, strong future play)
```

Ledger features can bootstrap `P`.

A Search Algorithm computes or updates `Q`.

`V` approximates what much deeper search and eventual outcomes would reveal.

---

## 4. Search Requirements

### 4.1 Preserve sequence planning

The mature agent must still discover multi-action lines such as:

```text
Ultra Ball
  -> choose discards
  -> search attacker
  -> bench attacker
  -> attach energy
  -> retreat
  -> attack
```

A learned value model should make such planning cheaper, not remove it.

### 4.2 Replan at information boundaries

The existing idea of stopping or replanning when meaningful new information appears is useful.

Examples:

- draw cards
- shuffle and redraw
- reveal information
- random outcome
- opponent turn
- opponent action
- prize information
- search/reveal effects

Use receding-horizon planning:

```text
observe
  -> plan sequence
  -> execute valid prefix
  -> new information appears
  -> observe
  -> replan
```

### 4.3 Make search anytime

Search should always have a valid best-known answer.

Conceptually:

```text
50 ms   -> reasonable answer
500 ms  -> better answer
2 s     -> better answer
5 s     -> better answer
20 s    -> better answer
```

Avoid designs where the search is only useful after completing a predetermined traversal.

### 4.4 Generalize the search interface

Do not bind the project to the quarantined Bellman traversal.

Use interfaces such as:

```text
SearchAlgorithm
SearchPolicy
ValueEvaluator
BudgetController
BeliefModel
TranspositionTable
```

This allows benchmarking:

- quarantined Bellman teacher traversal
- MCTS
- PUCT
- dynamic lookahead
- sparse sampling
- two-step lookahead
- other selective search methods

All should be able to use the same simulator, observation representation, policy model, value model, replay data, and benchmark positions.

---

## 5. Search Priors

Manual features should not prescribe an entire path.

They should provide local hints such as:

```text
At state S:

Ultra Ball    prior .42
Attach        prior .27
Supporter     prior .18
Retreat       prior .08
Other         prior .05
```

The search algorithm then decides what to do with that information.

For example:

```text
features say A looks promising
        |
        v
search expands A
        |
        v
search discovers A is mediocre
        |
        v
Q(A) falls
        |
        v
budget shifts toward B/C
```

The prior should guide, not control.

---

## 6. Progressive Widening

When a state has many legal actions, do not necessarily expose all children immediately.

Example:

```text
initially:

S
├── A
├── B
└── C
```

Later:

```text
S
├── A
├── B
├── C
├── D
└── E
```

The search algorithm controls **when** to widen.

The prior helps determine **which unseen action** to add next.

This separates selection from expansion.

---

## 7. Bootstrap Phase

The bootstrap phase uses existing knowledge to generate useful training data quickly.

Recommended sequence:

1. Reuse or create a modest set of general features/strategies that rank plausible branches.
2. Provide a crude initial leaf evaluator only where bounded search requires one.
3. Keep leaf evaluation separate from search-order features.
4. Run feature-steered searches at multiple time or node budgets.
5. Record observations, actions, search results, best sequences, convergence behavior, and final outcomes.
6. Train `P(a|s)` from action/line preferences discovered by stronger search.
7. Train `V(s)` from deeper-search estimates plus actual win/loss outcomes.
8. Evaluate each candidate generation against frozen prior agents before promotion.

Manual feature work is therefore a **launch vehicle**, not the permanent architecture.

---

## 8. Tiered Teacher Search

For selected states, evaluate the same position at multiple search budgets.

```text
Stable:

0.1 s -> A, V=.64
1 s   -> A, V=.68
5 s   -> A, V=.69
15 s  -> A, V=.69
```

Compare:

```text
Unstable:

0.1 s -> A, V=.61
1 s   -> C, V=.43
5 s   -> B, V=.72
15 s  -> B, V=.55
```

Use convergence as training metadata.

Stable targets can receive higher weight. Unstable states can be re-searched, down-weighted, or queued as difficult states.

---

## 9. Policy Learning

Initially:

```text
manual features
      |
      v
search ordering
      |
      v
deep offline teacher search
```

If the manual prior ranks one action highest but deep search consistently discovers another action or line is better, that disagreement becomes an automatic policy correction.

Train:

```text
P_theta(a|s)
```

toward the stronger-search preference.

Deep search therefore becomes the automated replacement for manual blunder labeling.

---

## 10. Value Learning

### 10.1 Terminal values

Terminal values are exact, for example:

```text
win  = +1
loss = -1
```

or:

```text
win  = 1
loss = 0
```

### 10.2 Non-terminal values

The long-term goal is:

```text
V(s) ~= probability of eventual win
       under strong future play
```

A useful training loss may combine:

```text
value_loss =
    alpha * error(V_model, V_deep_search)
  + beta  * error(V_model, final_game_result)
```

Do not train `V` only from Bellman outputs. Complete-match outcomes are the external reality check.

### 10.3 TD / n-step learning

Temporal-difference or n-step targets can later improve sample efficiency. Add them after search distillation, outcome-based value learning, and calibration are working.

---

## 11. Generation-Based Training Loop

```text
Generation N
    |
    v
generate self-play / cross-play matches
    |
    v
cheap / medium search for most decisions
    |
    v
save observations and search traces
    |
    v
select informative states
    |
    v
deep teacher re-search
    |
    v
add policy/value/outcome targets
to replay buffer
    |
    v
train candidate P,V
    |
    v
evaluate against frozen opponent pool
    |
    v
promote only if acceptance criteria pass
    |
    v
Generation N+1
```

Use batches and frozen generations. Do not mutate the live agent after every game.

---

## 12. Mature Training Loop

Once bootstrapped, the architecture remains similar.

The major change is progressively tighter search budgets.

```text
learned P
    |
    v
budget allocation
    |
    v
selective Search Algorithm
    |
    v
learned V at leaves
    |
    v
better P and V
    |
    v
repeat
```

The mature system still searches. It simply searches less broadly, less deeply, and more selectively.

---

## 13. Adaptive Search Budget

Eventually implement or learn:

```text
B(s)
```

where `B(s)` estimates how much computation a position deserves.

Possible behavior:

```text
obvious decision       -> milliseconds
normal decision        -> short search
uncertain decision     -> medium search
critical complex turn  -> deeper search
```

The optimization target is:

```text
maximize playing strength
subject to total match-time constraint
```

---

## 14. Compute Plan for a 10-Core CPU Machine

A practical arrangement:

```text
CPU 1-8  -> match generation
CPU 9-10 -> deep teacher re-search
```

Later:

```text
GPU -> batched P/V inference + training
CPU -> simulator + tree management
```

Do not deep-search every state. Spend teacher compute where it is likely to change the model.

---

## 15. Prioritized Re-search / Active Learning

Deep-search states preferentially when:

- shallow and deep search disagree
- `P(a|s)` strongly prefers an action deeper search rejects
- `V(s)` strongly disagrees with deeper search
- top candidate lines are close
- the state contains unfamiliar mechanics
- the position is structurally unusual
- final result is surprising relative to predicted `V`
- search remains unstable as budget increases

Spend expensive compute where it has the highest information value.

---

## 16. Transpositions and Canonicalization

Treat this as a core requirement.

Many action orders lead to the same effective state:

```text
attach -> bench -> tool
bench  -> attach -> tool
tool   -> bench  -> attach
```

If the resulting state is identical and no meaningful information event occurred:

```text
all paths -> same canonical hash/node
```

Ordering remains significant around draws, reveals, deck searches, random outcomes, shuffles, and other information-changing events.

---

## 17. Hidden Information

### 17.1 Strict observation boundary

Maintain two state concepts:

```text
GameState:
  complete simulator truth

ObservationState:
  exactly what the acting player
  is legally allowed to know
```

`P` and `V` consume only `ObservationState`.

This should be enforced with tests.

### 17.2 Belief model

Where useful, represent hidden information probabilistically rather than as one `UNKNOWN` value.

Search can sample hidden worlds consistent with the observation.

### 17.3 Chance outcomes

Use exact probability calculations where cheap, such as hypergeometric draw probabilities.

Use Monte Carlo or sparse sampling when the outcome space becomes large.

Optimize expected downstream value, not merely the probability of hitting one desired card.

### 17.4 Determinization warning

Avoid strategy fusion.

The search must not choose different current actions based on hidden facts the real player cannot know.

Current actions must be chosen at the information-set or observation level.

---

## 18. Multi-Turn Planning

Two layers should coexist.

### 18.1 Implicit long-horizon planning

`V(s)` is trained from complete games and can learn long-term consequences without explicitly searching every future turn each time.

### 18.2 Explicit selective multi-turn search

When useful:

```text
our plan
  -> opponent strong/plausible response
    -> our continuation
      -> V(s)
```

Do not naïvely expand full turns for both players everywhere.

---

## 19. Opponent Modeling

Do not assume one opponent response.

Search multiple strong or plausible replies.

The same side-to-move policy/value model can be used to model strong opponent play.

---

## 20. Cross-Deck Generalization

Mirror matches are useful for bootstrap but insufficient long-term.

Train across many deck pairings and hold out some decks for generalization tests.

The objective is one general `P,V` system conditioned on state and deck/card context, not one permanently separate brain per deck.

---

## 21. Agent Population / League Training

Ten training agents do not need ten independent answer systems.

Prefer multiple checkpoints of the same general architecture:

```text
shared model architecture
       |
       +-- frozen Gen 12
       +-- frozen Gen 18
       +-- frozen Gen 24
       +-- current Gen 29
       +-- specialist checkpoint
```

Workers can generate games from different checkpoint and deck combinations.

All useful experience feeds the shared learner.

---

## 22. Card and State Representation

Do not rely only on card IDs.

Use identity embeddings plus structured mechanics.

Possible inputs include:

- HP
- type
- stage
- retreat cost
- attack energy requirements
- attack damage
- attack conditions/effects
- abilities
- once-per-turn constraints
- draw/search/shuffle/reveal effects
- energy acceleration/movement
- gust/switch/status effects
- evolution dependencies
- prize value
- special rules

Where feasible, create a normalized machine-readable representation of card effects.

New mechanics should require simulator implementation, not manual strategic-value assignment.

---

## 23. Replay Data Schema

Suggested fields:

| Field | Purpose |
|---|---|
| `observation_state` | Legal player-visible model input |
| `side_to_move` | Perspective for P/V |
| `legal_actions` | Candidate action set |
| `manual_prior` | Bootstrap feature/strategy ordering |
| `policy_prediction` | P before search |
| `value_prediction` | V before search |
| `search_budget` | Time/nodes allowed |
| `search_stats` | Visits, Q, convergence, transpositions |
| `best_sequence` | Best line found |
| `teacher_policy_target` | Target from stronger search |
| `teacher_value_target` | Deep-search state estimate |
| `final_result` | Win/loss ground truth |
| `deck_id` | Player deck context |
| `opponent_deck_id` | Matchup context |
| `model_version` | Reproducibility |
| `search_version` | Reproducibility |

---

## 24. Evaluation Metrics

Track:

- win rate against frozen checkpoints
- win rate against a fixed benchmark suite
- win rate by deck and matchup
- held-out deck performance
- wall-clock decision time
- full-match wall time
- nodes expanded per decision
- policy agreement with deep teacher
- value calibration
- shallow-vs-deep search agreement
- blunder rate on regression positions
- search stability as budget increases

Useful metric:

```text
Delta V =
    V_deep_search
  - V_deployment_search
```

The gap should shrink over generations.

---

## 25. Preserve the Deep Teacher

Do not delete the expensive search after deployment becomes fast.

Use it offline for:

- difficult states
- regressions
- new decks
- new cards
- new mechanics
- search disagreements
- policy disagreements
- value disagreements

A 60–90 second search can be unacceptable online but valuable as offline supervision.

---

## 26. Recommended Build Order

### Phase A — Search infrastructure

1. Map the quarantined teacher and the live Ledger contracts it must not cross.
2. Identify state mutation, action generation, search ordering, leaf evaluation, and information boundaries.
3. Refactor behind `SearchAlgorithm`, `SearchPolicy`, and `ValueEvaluator`.
4. Preserve current playing behavior.

### Phase B — Information correctness

5. Add canonical `ObservationState`.
6. Keep full `GameState` private to simulator internals.
7. Add anti-information-leak tests.

### Phase C — Search efficiency

8. Add canonical state hashing.
9. Add transposition tables.
10. Identify strategically equivalent action permutations.
11. Add configurable time/node budgets.
12. Make search anytime.

### Phase D — Training telemetry

13. Emit detailed per-search records.
14. Add tiered-search support.
15. Record convergence.
16. Record policy/value predictions.
17. Build deterministic benchmark-state replay.

### Phase E — First learned value

18. Build replay buffer.
19. Train first `V(s)` from deep-search targets plus final outcomes.
20. Measure value calibration.
21. Compare search with and without learned V.

### Phase F — First learned policy

22. Train `P(a|s)` from deep-search action preferences.
23. Blend manual prior and learned P.
24. Reduce manual-prior weight as learned P proves stronger.

### Phase G — Generational training

25. Add batch self-play / cross-play.
26. Freeze generations.
27. Evaluate candidate vs old checkpoints.
28. Promote only if metrics pass.

### Phase H — Active learning

29. Add prioritized difficult-state queue.
30. Deep-search disagreement states.
31. Retrain from high-information samples.

### Phase I — Cross-deck scale

32. Add multi-deck curriculum.
33. Add opponent league.
34. Add held-out deck benchmarks.

### Phase J — Search alternatives

35. Benchmark the quarantined teacher, MCTS, PUCT, sparse sampling, and dynamic lookahead through the same P/V interfaces.

### Phase K — Budget learning

36. Add state-dependent search-budget control.
37. Optimize playing strength under whole-match time limits.

### Phase L — Performance

38. Optimize multiprocessing.
39. Add batched inference.
40. Add GPU training/inference when hardware becomes available.

---

## 27. Key Experiments

| Experiment | Question |
|---|---|
| Features vs learned P | At equal search budget, when does learned P beat manual ordering? |
| No V vs learned V | How much search depth can V eliminate at equal strength? |
| Search-budget sweep | Strength at 50 ms, 0.5 s, 2 s, 5 s, 15 s? |
| Bellman vs MCTS/PUCT | Which uses the same P/V most efficiently? |
| Transpositions on/off | How much branching is removed? |
| Random vs prioritized re-search | Which improves more per CPU-hour? |
| Mirror-only vs cross-deck | Does cross-deck training improve transfer? |
| Card ID vs structured representation | Which generalizes better to new cards? |
| Static vs adaptive budget | Can dynamic budget improve strength under the same match clock? |
| Manual prior ablation | When can handcrafted hints be removed entirely? |

---

## 28. Acceptance Criteria for a Mature Agent

A mature agent should:

- still plan meaningful multi-action sequences
- meet ladder match-time limits with margin
- spend little search on obvious positions
- spend more search on difficult positions
- approach deep-teacher strength with much smaller runtime
- maintain calibrated `V(s)`
- perform strongly across multiple deck types
- generalize usefully to held-out decks
- adapt to new cards with minimal manual strategy work
- avoid hidden-information leakage
- retain old capabilities while learning new decks
- use deep offline search as a teacher rather than a deployment requirement

---

## 29. Non-Goals / Warnings

Do **not**:

- replace search with greedy `max V(s+1)` as the default
- treat manual feature scores as win probabilities
- require exhaustive full-tree traversal in production
- deep-search every training state
- train only mirror matches
- let P/V consume hidden simulator truth
- assume the quarantined Bellman traversal must become the final Search Algorithm
- judge improvement only against the immediately previous generation
- create one permanently independent model per deck unless measurements show a real need

---

## 30. Final Architectural View

```text
                         ObservationState
                              |
                  +-----------+-----------+
                  |                       |
                  v                       v
             Policy P(a|s)            Value V(s)
                  |                       ^
                  v                       |
          candidate/search order          |
                  |                       |
                  +---- selective search--+
                         /    |    \
                      chance hidden opponent
                      model   info  response
                         \    |    /
                          best sequence
                               |
                            execute
                               |
                       new information
                               |
                             replan
```

Offline:

```text
deep teacher search
        +
complete-match outcomes
        |
        v
train P and V
        |
        v
reduce required search
        |
        v
repeat
```

> **The objective is not to eliminate search. It is to progressively compress expensive search into learned policy and value models so that increasingly selective search approaches the playing strength of the expensive teacher under a strict runtime budget.**
