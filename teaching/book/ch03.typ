#import "preamble.typ": *

= The Linear Model and the Decision Rule

We now have features $bold(phi)(o)$ and weights $bold(w)$, and a score that is their dot product.
Put a name to it: this is a #text(style: "italic")[linear model], the most important and most
underrated tool in machine learning. This chapter pins down exactly what "linear" buys us, how the
$argmax$ turns a score into a decision, and — because half of learning is knowing a tool's limits —
what a linear model structurally *cannot* do. That limitation is not a flaw to apologise for; it is
the hinge on which Chapters 4 and 11 turn.

== What "linear" means

A model is *linear in its weights* if the score is a weighted sum of features with no weight
multiplying another weight, and no weight buried inside a nonlinear function:

$ "Score"_"pos"(o) = w_1 phi_1(o) + w_2 phi_2(o) + dots.c + w_d phi_d(o) = bold(w) dot bold(phi)(o). $

Two consequences follow immediately, and both matter enormously. First, each weight acts
*independently and additively*: raising $w_3$ lifts the score of every option on which rule 3 fires,
by the same amount, regardless of the other features. Second — and this is the deep one — the score
is a *straight-line* function of the weights, which (Chapter 6) makes fitting them a well-behaved,
bowl-shaped optimisation with no false summits to get stuck on. Linearity is what makes the learning
tractable. We pay for it in expressive power, and we will count the cost honestly in §3.5.

The agent's full score adds the fixed combat term from Chapter 1, $"Score"(o) = bold(w) dot bold(phi)
(o) + "tactical"(o)$. You can think of $"tactical"$ as one more feature whose weight is pinned by the
rules of the game rather than learned — a knockout simply *is* worth about $1000$, and no amount of
data should talk us out of taking a free one.

== The decision rule: argmax

Scoring is not deciding. The decision is the $argmax$: compute every option's score and play the
largest.

$ "chosen" = argmax_(o in "options") "Score"(o). $

Three practical notes. #text(weight: "bold")[Ties] are broken by a fixed order so behaviour is
deterministic — an embedded engineer's instinct, and the right one for reproducibility.
#text(weight: "bold")[Only differences matter:] adding the same constant to every option's score
changes no decision, because $argmax$ is blind to overall level. This is why we will spend Chapter 4
looking at *score differences between two options*, never at absolute scores.
#text(weight: "bold")[A knockout is never sacrificed:] because $"tactical"$ dwarfs the positional
weights, an available knockout wins the $argmax$ regardless of the rules — the combat term acts as a
hard override sitting on top of the soft, learned preferences.

#example("reading the weights as doctrine")[
  The weights live on a legible scale that a human authored and can audit: roughly, $10$–$20$ is "a
  mild preference," $30$–$50$ is "strong doctrine," and the combat term operates in the thousands.
  So when you read $w_"accel-into-main" = 30$, you are reading a *sentence of strategy*: "rushing
  energy onto the main line is strong doctrine." This is the legibility we refused to trade away in
  Chapter 1 — every weight is an opinion you can point at, argue with, and correct. A neural network's
  millions of weights say nothing you can read.
]

== The geometry: weights point, the boundary is flat

Picture the weight vector $bold(w)$ as an arrow in feature space. The score of an option is how far
that option's feature vector reaches *along* $bold(w)$ (the dot-product-as-alignment picture from
Chapter 2). Now ask: for two options A and B, where is the agent *indifferent*? Exactly where their
scores are equal, $bold(w) dot bold(phi)(A) = bold(w) dot bold(phi)(B)$, i.e. $bold(w) dot
(bold(phi)(A) - bold(phi)(B)) = 0$. That equation defines a flat surface — a line in 2-D, a plane in
3-D, a #text(style: "italic")[hyperplane] in general. On one side A wins; on the other, B. This flat
decision boundary is the signature of every linear model, and its flatness is precisely the
limitation of §3.5.

== One family, three jobs

The same linear machine does three different jobs depending on what you attach to the score. It is
worth knowing all three, because you will choose between them in future projects:

#block(inset: (left: 6pt))[
  #set text(size: 10pt)
  - #text(weight: "bold")[Regression] — use the score *as* the prediction of a real number.
    "Predicted damage $= bold(w) dot bold(phi)$." (Ordinary linear regression.)
  - #text(weight: "bold")[Classification] — threshold or squash the score into a class. "If
    $bold(w) dot bold(phi) > 0$, predict *win*." (The perceptron; logistic regression — Chapter 7.)
  - #text(weight: "bold")[Ranking] — use the score only to *order* options and pick the top.
    This is what our agent does. We never need the score to be calibrated or true — only to put the
    right option on top.
]

Recognising that the agent does *ranking*, not regression or classification, is what makes Chapter 4
click: we do not need to know an option's "true value," only that the right option outscores the
wrong one.

== Why linear — and the price we pay

Linear models are, in a sense, the fixed-point arithmetic of ML: not the fanciest tool, but small,
fast, predictable, and correct far more often than newcomers expect. Four reasons we chose one:

#block(inset: (left: 6pt))[
  #set text(size: 10pt)
  - #text(weight: "bold")[Legible.] Every weight is a readable stance (the example above).
  - #text(weight: "bold")[Cheap to run.] One dot product per option — trivially inside the grader's
    budget, no dependencies.
  - #text(weight: "bold")[Cheap to learn.] Few parameters means it learns from little data, and the
    fit is convex (Chapter 6): no local optima, no random restarts, seconds on a CPU.
  - #text(weight: "bold")[Robust.] With few knobs it is hard to overfit, and easy to regularise when
    you do (Chapter 6).
]

The price is real and worth stating plainly. A linear model *cannot represent an interaction between
features unless you hand it that interaction as a new feature.* If "attach Ignition energy" is fine on
your attacker but wasteful on your bench, no single weight on a generic "attach energy" feature can
say both — the model is *blind* to the distinction until someone engineers a more specific feature
that separates the two cases. That blindness has a precise fingerprint: two options with *identical
feature vectors* always get *identical scores*, so no reweighting can ever tell them apart. Hold on to
that sentence. In Chapter 4 it becomes the razor that decides whether a mistake needs a new *weight*
or a new *feature*.

#contrast("When you would leave linear behind")[
  Decision trees and neural networks are *nonlinear*: they can carve feature space into curved,
  interacting regions and represent "Ignition is good here but bad there" with no hand-built feature.
  That power is exactly what you want when interactions are pervasive and unknown, and when you have
  the data and compute to fit thousands or millions of parameters safely. The judgement call is the
  whole game: nonlinear models buy expressiveness and *spend* data, compute, and legibility. In this
  project we are data-poor and legibility-bound, so we stay linear and pay the modest price of
  engineering our own interaction features. In a data-rich vision or language problem, the balance
  flips and you should flip with it. Chapter 11 lays the alternatives out side by side.
]

#problems("3", (
  [Options A and B have feature vectors $bold(phi)(A) = (1, 1, 0)$ and $bold(phi)(B) = (0, 1, 1)$
   with weights $bold(w) = (25, 10, 40)$ and $"tactical" = 0$ for both. Compute both scores and give
   the $argmax$.],
  [Using the same A and B, you want A to win. The shared feature $phi_2$ cancels. By how much would
   you need to *raise* $w_1$ (leaving $w_3$ fixed) to make $"Score"(A) > "Score"(B)$? Show the
   inequality you solved.],
  [Prove the "identical features" claim with numbers: construct two options with the *same* feature
   vector but which you (as a human) know should be ranked differently. Explain in one sentence why
   *no* choice of $bold(w)$ can separate them, and what you would have to change instead.],
  [Show that $argmax$ ignores overall level: options A, B, C score $12, 20, 7$. Add $100$ to all
   three. Does the chosen option change? State the general principle in one sentence.],
  [A knockout sets $"tactical" = 1000$. Option K makes a knockout but fires *no* positional rules;
   option D fires positional rules summing to $95$ but makes no knockout. Which is chosen, and what
   does this tell you about the relationship between the learned layer and the combat layer?],
  [Interpretation: an auditor reads $w_"hold-position-in-setup" = 35$ and $w_"prefer-cheap-retreat" =
   12$. In plain English, what strategic instruction has the agent been given about retreating during
   setup, and which preference dominates when both fire on opposite options?],
))
