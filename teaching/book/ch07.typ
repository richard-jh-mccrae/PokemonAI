#import "preamble.typ": *

= From Scores to Probabilities: The Value Model

So far our scores have been *ordinal*: bigger means "prefer," and nothing more. The number $50$ did
not mean "50% likely to win" — it meant only "beats $45$." That is all a ranking system needs. But
sometimes we need a genuine, trustworthy *number*: given this board, what is the probability we go on
to win? That question demands #text(style: "italic")[calibrated probability], and the tool for it is
#text(style: "italic")[logistic regression] — the same linear machine as before, with one function
bolted on the end and a different loss. This is the one genuinely *learned-from-outcomes* component in
the whole agent, and its story ends with an honest anticlimax that is itself a lesson.

== Why we want a probability at all

Two jobs need a real probability, not a rank. First, *pricing risk*: to decide whether a gamble is
worth it (Chapter 8) you compute an expected value, and expectation needs probabilities as weights —
"prefer" will not multiply. Second, *judging a position*: it is useful for the planner to blend in a
soft estimate of "how am I doing here?" as a tie-breaker between otherwise-close plans. Both require a
function that reads a board and returns a number in $[0, 1]$ that behaves like a probability. That is
exactly what the *value model* provides: a map $"state" arrow.r P("win")$.

== The sigmoid: turning a score into a probability

Our linear score $z = bold(w) dot bold(phi)$ can be any real number, from $-oo$ to $+oo$. A
probability must live in $(0, 1)$. We need a squashing function that maps the whole real line into
that interval, smoothly and monotonically. The standard choice is the #text(style:
"italic")[logistic sigmoid]:

$ sigma(z) = 1 / (1 + e^(-z)). $

Check its behaviour at three points and you understand it completely. At $z = 0$: $sigma(0) = 1 \/ (1
+ 1) = 0.5$ — a zero score means "coin flip." As $z arrow.r +oo$: $e^(-z) arrow.r 0$, so $sigma
arrow.r 1$ — a large positive score means "almost certainly win." As $z arrow.r -oo$: $e^(-z) arrow.r
oo$, so $sigma arrow.r 0$. It is a smooth S-curve, steepest at the middle and flattening at the ends,
which matches intuition: near a 50/50 board, a small edge swings the odds a lot; from an already-won
board, more advantage barely moves the near-certain probability.

#text(style: "italic")[Logistic regression] is precisely this: compute a linear score $z = bold(w)
dot bold(phi) + b$ (the $b$ is a _bias_, or intercept — one more learned number), then return $sigma(z)$.
It is a linear model wearing a probability hat.

#toolbox("The logit: reading the weights as odds")[
  Invert the sigmoid and you get $z = ln(p \/ (1 - p))$ — the score *is* the log-odds (the "logit")
  of winning. That gives each weight a crisp meaning: increasing a feature by one unit adds its weight
  to the log-odds, i.e. *multiplies the odds* of winning by $e^(w)$. This is why logistic regression
  is the workhorse of medicine and credit scoring: a doctor can read "this risk factor multiplies the
  odds of the disease by $1.4$" straight off a fitted weight. Legibility again — the same reason we
  favour it over a black box.
]

== The right loss for probabilities: log-loss

We cannot train this with the hinge loss — hinge cares about ranking, not about the *value* of the
probability. For calibrated probabilities the correct loss is #text(style: "italic")[log-loss] (also
called *cross-entropy* or *negative log-likelihood*). For one example with true outcome $y in \{0,
1\}$ and predicted win-probability $p$:

$ L_"log" = - [ y ln p + (1 - y) ln(1 - p) ]. $

Read it in two cases. If the state truly led to a win ($y = 1$), the loss is $-ln p$: near $0$ when
you confidently and correctly said $p approx 1$, but exploding toward $+oo$ if you confidently said
$p approx 0$ and were wrong. If it led to a loss ($y = 0$), the loss is $-ln(1 - p)$, symmetric. The
crucial property is the *savage punishment of confident wrong answers*: predicting $0.99$ on a state
you then lose costs you $-ln(0.01) approx 4.6$, while an honest $0.5$ costs only $-ln(0.5) approx
0.69$. Log-loss does not merely want you to be right; it wants you to be *correctly unsure*. That is
what "calibrated" means, and it is why this loss, not squared error, is standard for probabilities.

#example("what the model learns, and the coin-flip floor")[
  We train by *state-level supervision*: mine finished games, and label every board along the way with
  who *eventually* won. One match is one noisy win/loss bit — but it yields *thousands* of labelled
  states, and the noise averages out into a smooth probability. The fitted weights stay readable: the
  top ones are `prize_diff` $+0.44$ (being ahead on prizes strongly predicts winning),
  `line_ready` $+0.31$, `active_doomed` $-0.27$ (your attacker about to be knocked out predicts
  losing). To judge the model we compare its *holdout log-loss* against a baseline that always guesses
  $0.5$: that baseline scores $-ln(0.5) = ln 2 approx 0.693$ per state — the *coin-flip floor*. Our
  model scored $approx 0.555$. Beating $0.693$ is the proof it learned real signal, not noise.
]

== Standardise first

Recall from Chapter 2 that when features have wildly different scales, the big ones dominate the dot
product for no good reason, and gradient descent zig-zags. So before fitting, each feature is
*standardised*: subtract its mean, divide by its standard deviation, so every feature has mean $0$ and
spread $1$. Then it is the same machinery as Chapter 6 — gradient descent on the (convex) log-loss
with an L2 regulariser — producing a small vector of weights shipped as a plain JSON file the grader
evaluates with one dot product and one sigmoid. No libraries, pure arithmetic.

== Why logistic, and not something stronger

The obvious objection: logistic regression is *linear*; surely a gradient-boosted tree ensemble or a
neural net would predict win-probability better? We said no, for reasons that should now feel familiar.

#contrast("GBDTs and neural nets for the value model")[
  A #text(weight: "bold")[gradient-boosted decision tree] (LightGBM, XGBoost) is often the best
  off-the-shelf predictor on tabular data, and a #text(weight: "bold")[neural net] can model any
  interaction at all. We rejected both *for this seam*, on three grounds. #text(weight: "bold")[Runtime:]
  the grader is dependency-frozen — a tree ensemble or net needs a library that may not be present, so
  *inference* must be pure standard-library, which a logistic model satisfies trivially.
  #text(weight: "bold")[Small ceiling:] our features are already the *nonlinear* prize-race
  primitives computed by other tiers, so most of the interaction a tree would discover is *already
  baked into the inputs* — the extra accuracy a GBDT could add over a linear model is small.
  #text(weight: "bold")[Legibility:] narratable weights beat an opaque forest in a competition that
  grades explanation. (If the linear model ever plateaus, the escape hatch is a GBDT *trainer* that
  exports a pure-Python forest — keeping the runtime dependency-free. Match the tool to the
  constraint, as ever.)
]

== The honest ending

Here is the anticlimax, and it is the most professionally important paragraph in this chapter. After
building the value model correctly — fixing a training bug, retraining on 92,000 states, confirming it
beat the coin-flip floor — we ran the real test: does turning it on win *more games*? The answer was
*no*: it changed the win rate by $-0.55%$ (essentially zero, slightly negative), so it was
#text(style: "italic")[parked — built, validated, and left switched off]. Why? Because its features
were largely *redundant* with the closed-form position judgement the other tiers already compute; over
redundant inputs a general model adds a little miscalibration, not new signal. This is not a failure
of the method — it is the method working. A learned component must *earn* its place against a strong
baseline, and when it cannot, the honest and correct move is to shelve it (keeping it ready for the
day it has non-redundant features to learn from). A senior practitioner ships the *null result* with
the same rigour as a win. We meet the machinery that renders this verdict — the A/B test — in
Chapter 10.

#problems("7", (
  [Compute the sigmoid $sigma(z) = 1 \/ (1 + e^(-z))$ for $z = 0$, $z = 2$, and $z = -2$. (Use
   $e^2 approx 7.389$.) Verify $sigma(-2) = 1 - sigma(2)$ and explain why that symmetry holds.],
  [A value model has weights $bold(w) = (0.44, -0.27)$ on standardised features
   `prize_diff` and `active_doomed`, and bias $b = 0$. For a board with standardised features
   $bold(phi) = (1.5, 1.0)$, compute the score $z = bold(w) dot bold(phi) + b$ and the win-probability
   $sigma(z)$. (Use $e^(-0.39) approx 0.677$.)],
  [Log-loss of confidence. The state above was actually *won* ($y = 1$). Compute the log-loss
   $-ln p$. Now suppose a careless model had predicted $p = 0.05$ on this winning state — compute its
   log-loss. By what factor is the careless model punished more?],
  [The coin-flip floor. Show that a model which always outputs $p = 0.5$ has log-loss exactly $ln 2
   approx 0.693$ on *every* example, win or lose. Why does beating $0.693$ on held-out data
   demonstrate the model learned something real?],
  [Calibration intuition. Two models each predict on a state that is truly a loss ($y = 0$). Model A
   says $p = 0.5$; model B says $p = 0.9$. Compute each one's log-loss $-ln(1 - p)$. Which is
   punished more, and what habit is log-loss training instilling by doing so?],
  [Read a weight. In the fitted model `opp_bench` has weight $-0.47$. Using the log-odds
   interpretation, does a larger opponent bench raise or lower our predicted win-probability, and by
   what *multiplicative* factor on the odds per standardised unit? (Use $e^(-0.47) approx 0.625$.)],
  [Why state-level supervision. One match ends in a single win/loss bit but passes through roughly 40 board
   states. If you mine 2,000 matches, roughly how many labelled *(state, outcome)* training rows do
   you get? Contrast this with using one row per match, and explain why the state-level view "turns
   one noisy bit into calibrated probability."],
))
