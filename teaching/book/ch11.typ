#import "preamble.typ": *

= The Road Not Taken: A Field Guide to the ML You Didn't Use

Throughout this book, every chapter closed by naming a fancier technique and explaining why we passed
on it. That was not modesty — it was the curriculum. The most valuable thing a working ML engineer
owns is not a favourite algorithm but a *map*: a sense of what each tool is for, and the judgement to
match tool to problem. This chapter gathers all those forks into one field guide, so the next time you
face a decision problem — at work, in another competition, on a robot — you have a checklist instead of
a reflex. First the map, then the compass that reads it.

== The map: techniques we considered and set aside

#block(inset: 0pt, [
  #set text(size: 9pt)
  #table(
    columns: (auto, 1fr, 1fr),
    stroke: 0.4pt + gray,
    inset: 5pt,
    align: (left + top, left + top, left + top),
    table.header(
      text(weight: "bold")[Technique],
      text(weight: "bold")[What it is],
      text(weight: "bold")[Why not here / when to reach for it],
    ),
    [Deep neural network (end-to-end)],
    [Many layers of learned nonlinear features; maps raw input to output, learning its own representation.],
    [*Not here:* data-hungry, opaque, heavy runtime. *Reach for it* with abundant data and unknown features — vision, audio, language.],

    [Reinforcement learning (Q-learning, policy gradient)],
    [Learn a policy/value from the reward of your own actions, by trial and error over many episodes.],
    [*Not here:* win/loss reward is one noisy bit per roughly 40 moves — too sparse to train much. *Reach for it* with a cheap simulator and dense-enough reward (robotics, control, games with fast self-play).],

    [AlphaZero (MCTS + value/policy net + self-play)],
    [Deep tree search guided by a network trained on millions of self-play games.],
    [*Not here:* needs vast compute/data, perfect information, tolerance for opacity. *Reach for it* for perfect-information games with a fast simulator and a big compute budget.],

    [Gradient-boosted trees (XGBoost, LightGBM)],
    [An ensemble of small decision trees; the go-to for tabular prediction, captures interactions automatically.],
    [*Not here as runtime:* needs a library the frozen grader may lack; small ceiling over a linear model once features are already nonlinear. *Reach for it* for tabular prediction when you can ship the dependency.],

    [Learned embeddings (card2vec)],
    [Represent each entity as a learned vector so "similar" items sit nearby, à la word2vec.],
    [*Not here:* data-hungry, and we already know exact card facts. *Reach for it* when entities have no usable hand-features and you have lots of co-occurrence data.],

    [$k$-nearest-neighbours],
    [Predict by looking up the most similar past cases; no training, all work at query time.],
    [*Not here:* needs a stored corpus and a good distance metric; slow at scale. *Reach for it* as a strong, simple baseline when you have clean, low-dimensional data.],

    [Bayesian methods / probabilistic models],
    [Maintain full probability distributions over unknowns; update beliefs with evidence via Bayes' rule.],
    [*Partly here* (our hypergeometric deck odds are exact Bayesian reasoning). *Reach for the heavy machinery* when you must quantify uncertainty and can encode a prior.],

    [Monte Carlo simulation],
    [Estimate a quantity by random sampling instead of deriving it.],
    [*Not here:* our odds have an exact closed form (hypergeometric), so sampling would only add noise. *Reach for it* when the maths is intractable — deep trees, tangled distributions.],
  )
])

== The compass: five questions that pick the tool

The table's "why not here" column is really the same five questions asked over and over. Internalise
these and you can reason about a new problem the way a senior practitioner does — not "what is the
best model?" but "what do my *constraints* permit and *require*?"

#block(inset: (left: 6pt))[
  #set text(size: 10pt)
  + #text(weight: "bold")[How much data do I have?] Millions of labelled examples unlock deep models;
    a trickle demands hand-features and simple models with strong priors. *(We had a trickle.)*
  + #text(weight: "bold")[What is my compute and runtime budget?] A frozen, CPU-only, ten-minute
    grader forbids heavy inference and non-stdlib dependencies. *(Ours did.)*
  + #text(weight: "bold")[How dense is my feedback signal?] Dense per-decision labels can tune many
    parameters; one sparse bit per episode can only *gate*. *(Corrections dense; win/loss sparse.)*
  + #text(weight: "bold")[Must the system be legible?] If a human has to read, audit, or defend the
    decisions, favour models whose parameters mean something. *(A Strategy competition demanded it.)*
  + #text(weight: "bold")[Do I already know the structure?] When you have an exact model of part of
    the problem (prize counting, deck odds), *encode* it — do not make a network rediscover it.
    *(We knew the rules exactly.)*
]

Run this book's system through the five and its whole shape falls out: little data, tight runtime,
mixed signal density, legibility required, known structure ⟹ a legible linear model, tuned by dense
corrections, gated by sparse win/loss, with exact probability where the structure is known and only a
*thin, optional* learned seam on top. Not a compromise forced by ignorance of deep learning — a design
*derived* from constraints. That derivation is the skill. The algorithms are just its vocabulary.

#toolbox("The bias–variance trade-off, in one breath")[
  Behind "simple model for little data" sits the field's central trade-off. A *simple* model (few
  parameters, like ours) has high *bias* — it may be too rigid to capture the truth — but low
  *variance* — it barely changes when the data wobbles. A *complex* model (a deep net) has low bias but
  high variance — it can fit anything, including the noise, and swings wildly with small data changes.
  *Total error = bias + variance + irreducible noise.* With little data, variance dominates, so the
  simple model usually wins; with lots of data, you can afford complexity to cut bias. Regularisation
  (Chapter 6) is the dial between them. This one idea explains more model-selection decisions than any
  other — keep it in your pocket.
]

#problems("11", (
  [Match the tool. For each problem, name a technique from the map that fits, and justify with one or
   two of the five compass questions: (a) classify 10 million product photos into 5000 categories;
   (b) predict loan default from 30 tabular financial features, with a full data-science stack
   available and a need to explain each decision to a regulator; (c) control a simulated robot arm
   where you can run millions of fast practice episodes; (d) estimate, exactly, the chance your next
   two draws include a specific card from a known deck.],
  [Apply the five questions. You must build an on-device classifier for a microcontroller with 32 KB
   of RAM, no floating-point unit, and 500 hand-labelled examples. Walk through the five compass
   questions and recommend an approach. Which questions dominate, and which techniques are ruled out?],
  [Bias–variance. You fit a model and find it scores well on the training corrections but poorly on
   held-out games. Is this a high-bias or high-variance symptom? Name two remedies, and say which
   direction each moves you along the trade-off.],
  [Argue the counterfactual. Suppose the grader suddenly allowed any library, gave you a GPU, and
   handed you 50 million labelled game states. Which two design decisions in this book would you
   revisit, and what would you consider switching to? Which decision would you *keep* regardless, and
   why?],
  [Know the structure. Give one example, from any domain you know, where a quantity people usually
   *estimate with data* actually has an *exact closed form* worth using instead — and state the cost
   of using the data-hungry method when the exact one exists.],
))
