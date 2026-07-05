#import "preamble.typ": *

= Improving the System, and Where to Read Next

You now understand the machine end to end: features and a linear score, corrections and a ranking fit,
a hinge loss minimised by a regularised perceptron, a logistic value model, exact deck probability and
expected value, bounded search, and the evaluation discipline that judges it all. This closing chapter
does two things. First, it points at where the system could genuinely get *better* — grounded in the
project's own open threads, not hand-waving — so you can see the frontier from where you stand. Second,
it hands you the ladder of resources to keep climbing after this book. The goal was never to finish
learning; it was to start on solid ground.

== Concrete improvements, and the ideas they teach

Each of these is a real, documented opportunity in the system. Notice that every one is also a *lesson*
— a place where a technique from this book would earn its keep.

#block(inset: (left: 6pt))[
  #set text(size: 10pt)
  + #text(weight: "bold")[A matchup-conditioned value model.] The general value model was parked
    because its features were redundant with the closed-form judgement (Chapter 7). The unlock is to
    make it *conditional on the matchup* — separate weights, or a matchup feature, so it can learn
    "this board favours *us against that deck*," which the closed-form leaf does *not* already encode.
    *Lesson: a learned layer earns its place only where it adds non-redundant signal — so aim it there.*
  + #text(weight: "bold")[A gradient-boosted trainer that exports a pure-Python forest.] If the linear
    value model ever plateaus, the escape hatch (Chapter 7's *toolbox*) is to *train* a GBDT offline
    and *export* it as plain-Python `if`-thresholds — capturing tree-style interactions while keeping
    the runtime dependency-free. *Lesson: separate the training environment from the inference
    environment; they have different constraints.*
  + #text(weight: "bold")[A real opponent-reply model for escalation search.] The depth-2 search was
    parked because its two-ply model of the opponent was too crude (Chapter 9). A better opponent
    model — even a light learned policy predicting their likely reply — plus a *commit-margin gate*
    (only trust the search when it wins by a clear margin) could revive it. *Lesson: a search is only
    as good as its leaf evaluation and its opponent model; improve those before searching deeper.*
  + #text(weight: "bold")[More and better corrections.] The single highest-leverage, lowest-tech
    improvement: every hand-marked blunder is a dense training label (Chapter 4). More corrections,
    and richer *features* to express the ones that are route-H, sharpen the agent directly.
    *Lesson: in a data-poor regime, better labels beat fancier models almost every time.*
  + #text(weight: "bold")[Calibration monitoring.] The value model already emits its `win_prob` on
    telemetry. Plotting predicted-vs-actual win rates (a *reliability diagram*) would show whether it
    is *calibrated* — a standard, revealing diagnostic. *Lesson: measure the probability quality, not
    just the win rate.*
]

== A learner's path: turn reading into skill

Reading builds *fluency* — the comfortable sense that you follow the argument. Only *doing* builds
*storage strength* — the durable ability to reproduce and apply it. So the best next step is to make
the abstract concrete with your own hands. A suggested progression, each a weekend-sized project:

#block(inset: (left: 6pt))[
  #set text(size: 10pt)
  + Implement logistic regression from scratch in C or Python — sigmoid, log-loss, gradient descent —
    and watch it separate two clouds of points. You will *feel* Chapters 6–7.
  + Code the structured-perceptron weight update from Chapter 6 and run it on a handful of invented
    corrections; watch the pocket save you on contradictory data.
  + Write the hypergeometric deck calculator from Chapter 8 and check it against a brute-force
    simulation — proving to yourself that the closed form and the Monte Carlo agree.
  + Build a tiny minimax/expectimax solver for tic-tac-toe or a toy card game (Chapter 9).
  + Run the project's own tuner on a batch of corrections and read the before/after weight diffs — the
    theory of this book, executing on the real system.
]

== Further reading, ranked for an engineer

These are the high-trust resources behind this book, ordered as a climbing route. (Full links live in
the workspace's `RESOURCES.md`.)

#block(inset: (left: 6pt))[
  #set text(size: 9.8pt)
  - #text(weight: "bold")[Start here — _An Introduction to Statistical Learning_] (James, Witten,
    Hastie, Tibshirani; free PDF). The best first ML book for a numerate engineer. Chapters on the
    bias–variance trade-off, logistic regression, and regularisation map directly onto Chapters 3–7
    here.
  - #text(weight: "bold")[Visual intuition — 3Blue1Brown] "Gradient descent" and "Neural networks"
    videos (YouTube, free). The clearest picture of Chapter 6 you will find.
  - #text(weight: "bold")[Gentle course — Andrew Ng's _Machine Learning Specialization_] (Coursera).
    Linear/logistic regression, cost functions, gradient descent, hands-on. Matches Chapters 3–7.
  - #text(weight: "bold")[Search & games — Russell & Norvig, _AI: A Modern Approach_.] The classic for
    minimax, alpha–beta, and expectimax (Chapter 9).
  - #text(weight: "bold")[Reinforcement learning — Sutton & Barto,] _Reinforcement Learning: An
    Introduction_ (2nd ed., free PDF). For the RL/AlphaZero road not taken; the vocabulary of
    sequential decision-making.
  - #text(weight: "bold")[Rigour later — Hastie et al., _Elements of Statistical Learning_] and Bishop,
    _Pattern Recognition and Machine Learning_ (both free PDFs). When you want the mathematics in full.
]

#toolbox("Where to test your understanding on real people")[
  Wisdom comes from friction with practitioners, not just books. Good rooms to argue in: the
  #text(weight: "bold")[Kaggle competition forums] (the most on-topic — other competitors reasoning
  about the same simulator); #text(weight: "bold")[Cross Validated] (stats.stackexchange.com) for
  precise questions on loss functions, logistic regression, and probability; and
  #text(weight: "bold")[r/learnmachinelearning] for beginner-friendly discussion. Post a claim from
  this book and see if it survives contact. It usually will — and where it does not, you will have
  learned the most.
]

== A closing word

The system in this book is deliberately modest, and that is its lesson. It does not use the most
powerful techniques available; it uses the *right* ones for its constraints, and it tests every one of
them honestly against the only judge that matters. That temperament — reach for the simplest thing that
could work, understand *why* it works, and let evidence, not enthusiasm, decide what ships — is worth
far more than any single algorithm. You came to this competition to learn machine learning. What you
have actually been learning is *engineering judgement applied to learning systems*. Carry it forward.
Then take the exam.

#problems("12", (
  [Pick the highest-leverage improvement from the list for a *data-poor* project, and defend the
   choice in two sentences using an idea from Chapter 4.],
  [The matchup-conditioned value model is expected to help where the general one did not. Explain
   *why*, in terms of feature *redundancy* versus *novelty* (Chapter 7).],
  [Design a reliability check. You have 5,000 states where the value model predicted a win-probability
   and you know the eventual outcome. Describe, in three steps, how you would *plot* whether the model
   is calibrated, and what a well-calibrated result would look like.],
  [Choose your first hands-on project from the learner's path and write a one-paragraph plan: what you
   will build, which chapter's idea it exercises, and how you will know it works (your feedback loop).],
))
