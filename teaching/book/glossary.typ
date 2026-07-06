#import "preamble.typ": *

#heading(level: 1, numbering: none)[Glossary]

A compact reference for the vocabulary introduced in this book. Where a term has a plain-language name
and a formal name, both are given.

#let g(term, body) = block(above: 0.55em, below: 0.55em)[
  #text(weight: "bold", fill: accent)[#term] #h(0.3em) #body
]

#g("Adoption gate")[The acceptance rule that ships tuned weights only if they satisfy *strictly more*
corrections than the expert seeds; otherwise nothing ships. A validation criterion that guards against
motion mistaken for progress. (Ch 6, 10)]
#g("A/B test")[Comparing two versions by running both and measuring an outcome — here, win rate on the
ladder. The authoritative *evaluation*. (Ch 10)]
#g("Argmax")[The *argument* that maximises a function: $argmax_o f(o)$ is the option $o$ giving the
largest $f$. The decision rule. (Ch 1, 3)]
#g("Bias–variance trade-off")[Total error decomposes into *bias* (rigidity of a simple model) plus
*variance* (sensitivity of a complex model to data) plus irreducible noise. Little data favours low
variance (simple models). (Ch 11)]
#g("Calibration")[A probability is calibrated if, among states it calls $p$, a fraction $p$ actually
occur. Log-loss training encourages it. (Ch 7, 12)]
#g("Confidence interval (CI)")[A range that plausibly contains the true value (e.g. a win rate). Its
width shrinks like $1\/sqrt(N)$. If it straddles the break-even line, the effect is not demonstrated.
(Ch 10)]
#g("Correction")[A labelled comparison "at this state, option $k$ should outrank $c$." Our unit of
supervised training data; formally a *pairwise ranking label*. (Ch 4)]
#g("Cross-entropy / log-loss")[The loss $-[y ln p + (1-y) ln(1-p)]$ for probabilistic predictions;
punishes confident-wrong answers severely. (Ch 7)]
#g("Dot product")[$bold(w) dot bold(phi) = sum_i w_i phi_i$ — element-wise multiply and sum. Measures
alignment; the core of every linear model. (Ch 2)]
#g("Expected value (EV)")[The probability-weighted average of outcomes, $sum P dot "value"$. The fair
price of a gamble; the basis of *expectimax*. (Ch 8, 9)]
#g("Expectimax")[Minimax extended with *chance nodes* valued by expectation. Folds randomness into
look-ahead search. (Ch 9)]
#g("Feature ($bold(phi)$)")[A number measuring one fact about an option; here usually a binary
indicator (a rule that fires, $1$, or not, $0$). The vector $bold(phi)$ is the model's whole view of an
option. (Ch 2)]
#g("Feature engineering")[Hand-designing the features. The *route-H* fix — inventing a new distinction
the model was blind to. (Ch 2, 4)]
#g("Gradient descent")[Minimising a function by repeatedly stepping opposite its gradient, scaled by
the learning rate $eta$. The workhorse optimiser. (Ch 6)]
#g("Hinge loss")[$max(0, tau - m)$ — the SVM/ranking loss; zero once the margin clears $tau$, linear
below. A convex surrogate for the intractable zero–one loss. (Ch 5)]
#g("Hyperplane")[The flat decision boundary of a linear model, where two options score equally. (Ch 3)]
#g("Hypergeometric")[The distribution for drawing *without replacement*; gives exact deck-content
odds, $1 - binom(K,u)\/binom(H,u)$. Contrast the *binomial* (with replacement). (Ch 8)]
#g("Hypothesis")[Our name for a weighted if-then rule; formally a binary *feature* with a learned
*weight*. (Ch 1–4)]
#g("Learning to rank")[Learning to *order* items rather than predict a number (regression) or class
(classification). We use the *pairwise* form. (Ch 3, 4)]
#g("Linear model")[A score that is a weighted sum of features, $bold(w) dot bold(phi)$ — additive,
legible, convex to fit, cheap to run. (Ch 3)]
#g("Logistic regression")[A linear score passed through the sigmoid to yield a probability; trained
with log-loss. The value model. (Ch 7)]
#g("Margin ($m$)")[The score gap $sum_i w_i Delta_i + Delta"tactical"$ for a correction; positive means
satisfied. Also, the buffer a model keeps past the boundary for robustness. (Ch 4, 5)]
#g("Minimax")[Propagating values up a game tree: MAX takes the largest child, MIN the smallest —
"assume the opponent plays well." (Ch 9)]
#g("Monte Carlo")[Estimating a quantity by random sampling. Used when no closed form exists; needless
where one does (our deck odds). (Ch 8, 9)]
#g("One-hot encoding")[Representing a $k$-valued category as $k$ binary features, exactly one hot.
Avoids imposing a false ordering. (Ch 2)]
#g("Overfitting")[Fitting the training data's noise so that new data is handled poorly. Countered by
*regularisation* and honest *evaluation*. (Ch 6, 10)]
#g("Pocket algorithm")[On contradictory (non-separable) data the perceptron oscillates; the pocket
keeps and returns the best-scoring weights it ever saw. (Ch 6)]
#g("Policy")[A function from state to action — the agent's decision law. Equivalent to a controller
$u = k(x)$. (Ch 1)]
#g("Regularisation (L2 / L1)")[A penalty that keeps weights small or near a prior. *L2* (ridge) shrinks
smoothly toward the seed (a Gaussian prior); *L1* (lasso) zeroes weak weights (sparsity). Knob:
$lambda$. (Ch 6)]
#g("Sigmoid ($sigma$)")[$sigma(z) = 1\/(1 + e^(-z))$ — squashes any real number into $(0,1)$;
$sigma(0) = 0.5$. Turns a score into a probability. (Ch 7)]
#g("Standardisation")[Rescaling a feature to mean $0$, spread $1$: $(phi - mu)\/s$. Stops large-scale
features from dominating. (Ch 2, 7)]
#g("Structured perceptron")[The regularised sub-gradient update that fits our weights: nudge toward
violated corrections, pull back toward seeds, clamp. (Ch 6)]
#g("Support vector")[A training example on or inside the margin (non-zero hinge loss); these alone
determine the fit. (Ch 5)]
#g("Tactical term")[The fixed, rule-of-the-game combat value (a knockout $approx 1000$). A hard
override on top of the learned positional score. (Ch 1, 3)]

#pagebreak()

#let sech(s) = block(above: 0.4em, below: 0.5em)[
  #text(font: sansfont, size: 12pt, fill: accent, weight: "bold")[#s]]
#sech("Symbols")

#block(inset: 0pt, [
  #set text(size: 12pt)
  #table(
    columns: (auto, 1fr),
    stroke: 0.5pt + black, inset: 5pt, align: (left, left),
    table.header(text(weight: "bold")[Symbol], text(weight: "bold")[Meaning]),
    [$bold(w)$], [the weight vector — the learned parameters of the model],
    [$bold(phi)(o)$], [the feature vector of option $o$],
    [$bold(w) dot bold(phi)$], [the dot product / positional score],
    [$"Score"(o)$], [$bold(w) dot bold(phi)(o) + "tactical"(o)$, the full score],
    [$Delta_i$], [feature difference $"fired"_i(k) - "fired"_i(c) in \{-1,0,+1\}$ for a correction],
    [$m$], [the margin of a correction, $sum_i w_i Delta_i + Delta"tactical"$],
    [$tau$], [the hinge-loss margin target (we use $tau = 1$)],
    [$lambda$], [the L2 regularisation strength (the conservatism knob; code: `reg`)],
    [$eta$], [the learning rate (step size) in gradient descent],
    [$J(bold(w))$], [the training objective (total loss) being minimised],
    [$sigma(z)$], [the logistic sigmoid $1\/(1 + e^(-z))$],
    [$p$], [a probability — of winning, or of a draw hitting],
    [$binom(n,k)$], [$n$ choose $k$, the number of ways to pick $k$ of $n$],
    [$b, d$], [search branching factor and depth; tree size $approx b^d$],
    [$gamma$], [the Read's confidence gate on opponent-model signals (mentioned in passing)],
    [$argmax$], [the option achieving the maximum score — the decision],
  )
])

#v(1em)
#align(center)[#text(style: "italic", fill: accent)[— End of book. Questions to your teacher are always
in order. —]]
