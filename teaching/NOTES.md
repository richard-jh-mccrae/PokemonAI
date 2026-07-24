# Teaching notes & preferences

## About the learner
- Embedded SW engineer. Comfortable with: C/C++, bit-level thinking, state machines, control loops,
  lookup tables, determinism, real-time constraints. **Use these as analogies** — they land.
- New to ML vocabulary. Introduce every term; never assume "gradient", "regularisation", "logistic"
  are known. Define on first use, keep a glossary.
- Wants **math he can do by hand**, with answers to check against. Keep numbers small and clean.

## Style that works
- Textbook voice in the deliverable (full clear prose). Chat replies stay caveman-lite per global prefs.
- Every technique: (1) what, (2) the math, (3) why *this* one, (4) what we rejected, (5) where it
  transfers. This 5-beat pattern is the spine of every chapter.
- Colour-coded callouts in the book: green = Pokémon example, amber = road-not-taken, purple = toolbox.

## Toolchain (durable — reuse next session)
- **Typst** is installed via `pip install typst` (self-contained compiler, no system LaTeX).
  Compile: `python -c "import typst; typst.compile('main.typ', output='out.pdf')"` from `teaching/book/`.
- **PyMuPDF** (`pip install pymupdf`) renders pages to PNG for visual QA (no poppler on this box).
- Math gotcha: multi-letter words in Typst math must be quoted — `$"Score"$`, `$w_"seed"$`.

## Lessons shipped
- **0001 — The Fail-Direction Rule** (Session 2, grounded in issue #137). Teaches the one durable
  idea behind the `reachable_attach` oracle: round an uncertain value feature toward the affordable
  error, away from the catastrophic one — `reachable_attach` fail-CLOSED (under-count my budget) vs
  `reachable_incoming` fail-OPEN (over-count their threat), same "pessimistic about my own safety"
  principle, opposite arithmetic. Worked f70 problem (Crispin → {R}{P} → Phantom Dive) done by hand;
  4-question graded quiz; transfers to admissible A* heuristics / sound static analysis / fail-safe
  embedded defaults. NOT yet a learning record — wait until he demonstrates recall (do the quiz cold).

## Reusable components (assets/) — reuse, don't re-inline
- `assets/lesson.css` — shared stylesheet; palette + type match the cheat-sheet + book. Callout
  classes `.poke/.amber/.tool`, energy tokens `.e-R/.e-P/.e-C`, worked-example `pre.work`, quiz styles.
- `assets/quiz.js` — retrieval-practice widget. Markup contract documented in the file header.
  First pick locks the question (genuine recall); immediate colour + prose feedback; running tally;
  `.reveal` show/hide for spaced items. **Spread the correct option across positions** (a keen
  learner will notice if the answer is always first) — lesson 0001 uses positions 2,3,1,4.

## Open threads for future sessions
- Next lesson teed up: **typed greedy matching** — how `_typed_can_pay` proves `{R}{P}` is coverable
  and why greedy suffices (the #137 build shape, step 2). Then `readiness_p` = hypergeometric EV
  (interleaves back to book Ch 6 — good spacing).
- Retro-fit the *book chapters* into interactive HTML lessons using the new assets (the original
  open thread) — now unblocked by lesson.css + quiz.js.
- He may want to actually *run* the tuner / value-model trainer and watch weights move — a hands-on lab.
