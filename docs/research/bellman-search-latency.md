# Bellman search latency: competition write-up notes

Status: implemented and measured, 2026-08-12.

## Write-up summary

The agent plans a complete legal turn with a Bellman recurrence over native-engine successor states.
Its first production implementation bounded each root branch independently but searched almost every
ordering of the available actions. A representative slow decision took 21.5 seconds, visited roughly
3,600 states, and executed about 70 million Python calls. Only 1.4 seconds was spent in the native
engine transition call; most time was spent rebuilding equivalent states, recomputing their utility,
and revisiting permutations of commutative actions.

The fix has five deck-neutral parts:

1. **Pre-expansion partial-order reduction.** Each deterministic action declares the abstract state
   resources it reads and writes. Independent actions receive one stable canonical order through a
   sleep set, so `A → B` is searched and the equivalent `B → A` permutation is not. Unknown and
   stochastic effects are barriers; chance and reveal outcomes reset the sleep set.
2. **Exact transpositions.** A determinized hidden world is identified by the actual ordered contents
   of both decks, both prize zones, and the opponent hand—not by the path of actions used to reach
   it. Equivalent public states reached through different action orders can now share exact Bellman
   results, while different hidden worlds remain distinct.
3. **Successive-halving allocation.** Every legal root action receives the same 96-node probe. The
   two highest-valued incomplete Bellman continuations receive deeper refinement. Deterministic,
   chance, and reveal-choice roots have explicit capacity bounds reflecting their branching shape.
   Final choice still compares Bellman values; allocation never reads card identity or card name.
4. **Cheaper native conversion.** Native dataclasses are converted without `dataclasses.asdict`'s
   recursive deep-copy overhead.
5. **Immutable fact caches.** Card stats, attack facts, resource jobs, and prize-route capacities are
   cached inside the board-potential evaluator. This changes evaluation cost, not evaluation value.

Search depth is not capped. A line may continue until the engine ends the turn, an attack resolves,
a game result occurs, a semantic cycle is found, or the explicit node budget is consumed.

## Why this is a value-guided beam

The old `beam_width` was mostly an action-count gate: below the threshold it searched exhaustively;
above it the solver could fall back to End. The implemented root beam instead forms itself from
measured continuation values:

```text
equal probe for every legal root
              ↓
Bellman benefit − cost + continuation value
              ↓
refine the best two incomplete roots
              ↓
commit only the highest backed-up root value
```

This is an adaptive computation budget, not a second play policy. The same value families used for
the final decision also determine which incomplete calculations deserve more work. Forced effect
choices remain legal Bellman choices and turn depth remains unlimited.

## Alternatives tested

- **One-step beam ranking:** rejected. It was fast but pruned enabling moves whose value appeared
  only after a later action, regressing correction fixtures.
- **Principal-variation-only search:** rejected. A single greedily guided path reordered established
  heal/setup lines.
- **Caching incomplete transposition values:** rejected. Incomplete values depend on the remaining
  budget and changed correction choices.
- **MCTS/PUCT:** deferred. These methods become attractive with a trained, calibrated policy/value
  model and many cheap rollouts. The present system has an exact native transition model and authored
  state-value equations, so deterministic transpositions plus adaptive exact search are simpler and
  less noisy.
- **Beam-stack search:** a plausible future extension if the competition requires anytime recovery
  toward a proof of optimality. It adds systematic backtracking to ordinary beam search.

## Measured result

| Measurement | Before | Final |
|---|---:|---:|
| Exact packaged native mirror | exceeded 600 s | 143.5 s |
| Mirror completion | timeout | both seats `DONE` |
| Final mirror decisions | incomplete match | 90 |
| Rationale-led hard correction gates | — | 25/25 pass |
| Runnable Bellman suite | — | 96/96 pass |

Mirror duration varies with shuffled games, so these are measured runs rather than a deterministic
speedup ratio. The material result is that the same 600-second submission gate changed from a timeout
to a complete clean-room native-engine match.

## Validation cleanup

The obsolete 259-record adjudication test was retired: its frozen source artifacts were deliberately
removed and the live correction store has since grown beyond it. Current rationale-led correction
gates remain the gameplay regression contract. The checker also restricts Kaggle Environment's eager
registration to CABT, so unrelated OpenSpiel native code is no longer loaded during Pokémon checks.

## Primary references

- Li, Jamieson, DeSalvo, Rostamizadeh, and Talwalkar, **“Hyperband: A Novel Bandit-Based Approach to
  Hyperparameter Optimization,”** JMLR 18, 2018. Successive halving/adaptive resource allocation:
  https://www.jmlr.org/papers/v18/16-558.html
- Zhou and Hansen, **“Beam-Stack Search: Integrating Backtracking with Beam Search,”** ICAPS 2005.
  Anytime beam search with systematic recovery and eventual optimality:
  https://m.aaai.org/Papers/ICAPS/2005/ICAPS05-010.pdf
- Orseau, Lelis, Lattimore, and Weber, **“Single-Agent Policy Tree Search With Guarantees,”**
  NeurIPS 2018. Best-first allocation guided by a policy:
  https://papers.nips.cc/paper/7582-single-agent-policy-tree-search-with-guarantees
- Guez et al., **“Learning to Search with MCTSnets,”** ICML 2018. Learned expansion, evaluation,
  and backup as the longer-term alternative once a trained search policy exists:
  https://proceedings.mlr.press/v80/guez18a.html

## Implementation trail

- `src/common/commutativity.py`: conservative action read/write footprints and independence proof.
- `src/common/solver.py`: sleep-set partial-order reduction, equal probes, refinement, diagnostics.
- `src/common/native_engine.py`: hidden-world identity, exact transpositions, cheaper conversion.
- `src/common/potential.py`: immutable evaluator caches and repeated-fact elimination.
- `docs/adr/0139-mega-starmie-uses-one-bellman-style-full-turn-planner.md`: architecture amendment.
- `tests/bellman/test_m3_solver.py`: allocation contract.
- `tests/bellman/test_native_engine.py`: hidden-world identity contract.
