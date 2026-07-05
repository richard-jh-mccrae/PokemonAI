# 0001 — Mission set; ground-up textbook is the first artifact

**Date:** 2026-07-05
**Status:** active

## What happened
Richard invoked `/teach` asking for a ~50-page textbook that teaches the ML/decision system we built,
using Pokémon as the running example (not teaching the game). He is an embedded engineer, new to ML,
and wants theory **and** hand-workable math practice, compare/contrast with the roads not taken,
transferable "toolbox" tidbits, improvement recommendations, further reading, and a final test.

## Key insight driving the curriculum
This system is **not** a deep-learning system, and that is the pedagogical gift. It is a tour of
**classical ML + decision theory** that a systems engineer can fully reason about:
1. Feature engineering + a **linear scoring model** (argmax over `w·φ + tactical`).
2. **Learning to rank** — corrections are pairwise labels; the "W route".
3. **Hinge loss**, margins (the SVM connection).
4. **L2-regularised structured perceptron** + the **pocket algorithm** + an adoption gate.
5. **Logistic regression** value model — sigmoid, log-loss, calibration, state-level supervision.
6. **Hypergeometric probability** + **expected value / expectimax** (gamble lines).
7. **Search** — game trees, minimax, expectimax, bounded escalation; the RL/AlphaZero contrast.
8. **Evaluation** — A/B ladder, confidence intervals, parked-OFF honesty, Goodhart.

The "why classical, not deep" answers (offline/CPU/dependency-frozen grader, legibility gate,
low-bandwidth W/L signal, data-hunger, self-inflicted-loss risk) are themselves first-class lessons.

## Zone of proximal development
Start at true zero-ML (vectors, dot products, what a "feature" is) and climb to logistic regression,
expectimax, and the RL contrast. Anchor every abstraction in embedded-engineer intuition
(lookup tables, state machines, control loops, fixed-point/determinism).

## Decisions
- Deliverable format: **Typst → PDF** (self-contained via pip; no system LaTeX needed).
- Book lives in `teaching/book/`; scaffolding (MISSION/NOTES/RESOURCES) in `teaching/`.
- Next likely step after he reads it: convert chapters into interactive retrieval-practice HTML
  lessons, and/or a hands-on lab running the real tuner and watching weights move.
