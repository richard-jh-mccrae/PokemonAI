#import "preamble.typ": *

#show: book.with(title: "A Systems Engineer's Introduction to Machine Learning")

// ===========================================================================
//  FRONT MATTER  (roman numerals, unnumbered titles)
// ===========================================================================
#set page(numbering: "i")
#counter(page).update(1)

#let fmtitle(s) = block(above: 1.4em, below: 0.8em)[
  #text(font: "New Computer Modern Sans", size: 17pt, fill: accent, weight: "bold")[#s]
]

// ---- TITLE PAGE -----------------------------------------------------------
#v(3.5cm)
#align(center)[
  #text(font: "New Computer Modern Sans", size: 13pt, fill: accent, tracking: 2pt)[
    A SYSTEMS ENGINEER'S INTRODUCTION TO
  ]
  #v(0.4cm)
  #text(font: "New Computer Modern Sans", size: 40pt, fill: accent, weight: "bold")[
    Machine Learning
  ]
  #v(0.5cm)
  #text(size: 15pt, style: "italic", fill: probc)[
    taught through the machinery of a Pokémon TCG battle agent
  ]
  #v(2.2cm)
  #line(length: 45%, stroke: 0.8pt + accent)
  #v(0.6cm)
  #text(size: 12pt)[
    A ground-up course in the linear models, probability, and search \
    that actually run inside the *PokemonAI* Strategy agent — \
    with worked problems, a final examination, and answers in the back.
  ]
  #v(3.5cm)
  #text(size: 12pt, fill: black)[Written for an embedded software engineer meeting ML for the first time.]
  #v(0.2cm)
  #text(size: 12pt, fill: accent)[Edition 1 · Session 1 of an ongoing course]
]
#pagebreak()

// ---- PREFACE --------------------------------------------------------------
#fmtitle("To the reader")

You build embedded systems. You already think in state machines, lookup tables, control loops, and
fixed-point arithmetic; you already care about determinism, memory budgets, and what runs on the
target. This book claims that machine learning is *not* a foreign country to you — it is a set of
ideas that sit naturally next to the ones you already own. We are going to prove that claim by taking
apart a system you helped build: the decision engine of a Pokémon Trading Card Game agent.

Here is the pleasant surprise. That agent is *not* a deep neural network. It is a carefully chosen
stack of *classical* techniques — a linear scoring model, a learning-to-rank weight fitter, a small
logistic-regression "how am I doing" model, exact probability over the deck, and bounded look-ahead
search. Every one of them is something you can compute by hand on a napkin, and every one was chosen
*over* a flashier alternative for reasons an engineer will find familiar: the grader is offline,
CPU-only, and dependency-frozen; the behaviour must be legible; and the win/loss signal is far too
sparse to train a big model. Those constraints did not weaken the system. They shaped it — and
learning *why* each fork was taken teaches you more ML than any single algorithm would.

So this is a textbook about machine learning that happens to use Pokémon as its laboratory. We care
about the game only far enough to make an example concrete. What we are really doing is building your
intuition for *features, weights, loss functions, gradients, probability, expectation, and search* —
and, just as importantly, for the engineering judgement of *which tool fits which constraint*.

#fmtitle("How to use this book")

Read it in order; each chapter earns the next. Every chapter follows the same five-beat rhythm:
*what* the technique is, *the math* behind it, *why this one*, *what we rejected and why*, and *where
the idea transfers* beyond Pokémon. Three coloured margins recur throughout:

#example("green")[a concrete situation from the agent, to make an abstraction land.]
#contrast("amber")[a technique we could have used instead, and the reason we did not — this is where
half the learning lives.]
#toolbox("purple")[a related function or use-case from the wider world, so a tool you learn here pays
off in your next project.]

Every chapter ends with #text(weight: "bold")[Problems] — mostly mathematical, all doable by hand
with a calculator. #text(weight: "bold")[Do them.] Reading about a gradient builds a comforting
illusion of understanding; *computing* one builds the real thing. Full solutions are in the
#text(style: "italic")[Answer Key] at the back, and a #text(style: "italic")[Final Examination]
covering every chapter follows it, with its own worked solutions. There is a #text(style: "italic")[Glossary]
at the very end — when a term feels slippery, go look; that is what it is for.

This is Session 1 of a course, not a one-off. I am your teacher as well as the author: when a passage
is murky, *ask me*. The fastest way to learn is to argue with the explanation until it clicks.

#pagebreak()

// ---- NOTATION PRIMER ------------------------------------------------------
#fmtitle("Notation, and a short refresher")

You need surprisingly little mathematics to follow this book. Here is essentially all of it, in one
place, so nothing later trips you up. If it is familiar, skim it; if not, this half-page is enough.

#defn("Vectors")[A vector is just an ordered list of numbers, written in bold: $bold(w) = (w_1, w_2,
w_3)$. We use them to hold either the *weights* of our model or the *features* of a situation. To a C
programmer a vector is a `float[]`; every operation below is a short `for` loop.]

#defn("Summation")[$sum_(i=1)^n a_i$ means $a_1 + a_2 + dots.c + a_n$ — "add these up". It is a
`for` loop that accumulates. If the range is obvious we write just $sum_i a_i$.]

#defn("Dot product")[The single most important operation in the book. For two vectors of the same
length, $bold(w) dot bold(phi) = sum_i w_i phi_i = w_1 phi_1 + w_2 phi_2 + dots.c$. It multiplies
the lists element-by-element and sums the result — one number out.]

#defn($argmax$)[$argmax_o f(o)$ is "the option $o$ that makes $f(o)$ largest". Not the largest value
— the *thing* achieving it. Picking the best-scoring move is an $argmax$.]

#defn("The exponential and the logarithm")[$e approx 2.718$; $e^x$ (also written $exp(x)$) grows
fast and is always positive. Its inverse is the natural log $ln(x)$: $ln(e^x) = x$. Two facts we
reuse: $e^0 = 1$, and $ln(1) = 0$. Handy value: $ln(2) approx 0.693$.]

We introduce every other symbol ($sigma$, $lambda$, $eta$, $tau$, $gamma$, $Delta$) at the moment it
is needed, and collect them all in the Glossary. That is the whole toolkit. Turn the page.

// ---- CONTENTS -------------------------------------------------------------
#pagebreak()
#fmtitle("Contents")
#outline(title: none, depth: 1, indent: 1.2em)

// ===========================================================================
//  BODY  (arabic numerals, numbered chapters)
// ===========================================================================
#set page(numbering: "1")
#counter(page).update(1)

#include "ch01.typ"
#include "ch02.typ"
#include "ch03.typ"
#include "ch04.typ"
#include "ch05.typ"
#include "ch06.typ"
#include "ch07.typ"
#include "ch08.typ"
#include "ch09.typ"
#include "ch10.typ"
#include "ch11.typ"
#include "ch12.typ"
#include "exam.typ"
#include "answers.typ"
#include "glossary.typ"
