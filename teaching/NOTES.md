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

## Open threads for future sessions
- Turn each chapter into an interactive HTML *lesson* with retrieval-practice quizzes (spacing +
  interleaving) once he's read the book.
- He may want to actually *run* the tuner / value-model trainer and watch weights move — a hands-on lab.
