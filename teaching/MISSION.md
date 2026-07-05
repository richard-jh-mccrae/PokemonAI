# Mission

**Who:** Richard — a professional **embedded software engineer**. Strong on C/C++, systems, and
determinism. **New to machine learning**; this Pokémon TCG competition is his first real ML system.

**What he wants:** To walk away from the competition with a *keen, durable, first-principles
understanding* of the decision/learning system we built together — not just what each function does,
but **why that function and not another**, and how to carry the ideas to other problems.

**Why it matters:** He wants "understanding and awareness over time" — storage strength, not a
one-off skim. ML is a skill gap he intends to close for good, using a system he already has intuition
about (this codebase) as the anchor.

**The concrete deliverable requested (Session 1):** A **textbook** (PDF), reads like a real textbook,
**≤ 50 pages**, built from the ground up. Requirements he stated:

- Well-organised chapters that build up.
- **Worked problems (mathematical), answers in the back.** Don't just describe the functions — make
  him *practice* them and understand *why* we use them.
- Compare/contrast: the routes we took vs the parallel techniques we didn't, and why.
- "Toolbox" tidbits on related functions/use-cases so learnings transfer beyond this project.
- The book uses **Pokémon as the running example**, but teaches the *system/ML*, not the game.
- Ends with **system-improvement recommendations** + **follow-up reading**.
- **A final test** covering all topics.

**Grounding constraint (from the project):** Teach the ML that is *actually in the codebase* —
verified against `docs/` and `src/`, never recalled from generic ML memory. The system is
deliberately classical (a legible linear model + learning-to-rank + a small logistic value model +
closed-form probability + bounded search), and the *reasons* for that (offline, CPU-only,
dependency-frozen grader; legibility; low-bandwidth W/L signal) are themselves core lessons.

**Delivered Session 1:** `teaching/book/PokemonAI-ML-Textbook.pdf` — 12 chapters + final exam +
answer key + glossary. This file grounds all future lessons.
