# Teaching workspace — ML through the PokemonAI agent

An ongoing, multi-session course teaching Richard (embedded engineer, new to ML) the machine-learning
and decision-theory ideas that actually run inside this repo's Strategy agent.

## The deliverable
- **`book/PokemonAI-ML-Textbook.pdf`** — a ~72-page ground-up textbook: 13 chapters (Ch. 13 is
  the complete tier-stack reference — every tier/sub-tier, its math, and its kill-switch), worked
  problems, a final exam, full answer key, and a glossary. Read this first.
- **`reference/formula-cheatsheet.html`** — a printable one-page formula reference (open in a
  browser; print to A4/Letter).

## Rebuilding the PDF
The book is written in **Typst** (self-contained, installed via `pip install typst` — no system
LaTeX). From `teaching/book/`:
```
python -c "import typst; typst.compile('main.typ', output='PokemonAI-ML-Textbook.pdf')"
```
`main.typ` is the spine; it `#include`s `preamble.typ` (styling) + `ch01..ch12`, `exam`, `answers`,
`glossary`. To preview a page as an image (no poppler on this box, use PyMuPDF):
```
python -c "import fitz; fitz.open('PokemonAI-ML-Textbook.pdf')[0].get_pixmap(dpi=100).save('p0.png')"
```

## Course state
- `MISSION.md` — why we're learning this and what the deliverable must contain.
- `NOTES.md` — teaching preferences + toolchain gotchas.
- `RESOURCES.md` — high-trust books/courses/communities (ISL first).
- `learning-records/` — what's been established; drives the next session.

## Likely next sessions
1. Turn chapters into **interactive HTML lessons** with retrieval-practice quizzes (spacing +
   interleaving) once he's read the book.
2. A **hands-on lab**: run the real tuner on a batch of corrections and watch the weights move;
   implement logistic regression + the hypergeometric calculator from scratch.
