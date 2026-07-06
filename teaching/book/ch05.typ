#import "preamble.typ": *

= Loss Functions: Measuring Wrongness

We have corrections, each demanding a positive margin $m > 0$. With many corrections and many weights,
some demands will conflict, and no single choice of weights satisfies all of them. So we cannot ask
for perfection; we must ask for the *least bad* weights. To do that we need a single number that says
how wrong a given weight vector is — a #text(style: "italic")[loss function]. Minimising it is what
"training" *means*. This chapter builds the loss our system uses, the *hinge loss*, and shows why it
beats the obvious alternatives.

== The idea of a loss

#defn("Loss function")[A loss $L$ takes a training example and the model's current parameters and
returns a non-negative number: $0$ when the model handles the example perfectly, larger the worse it
does. The #text(style: "italic")[empirical risk] is the total (or average) loss over all examples,
$J(bold(w)) = sum_"examples" L$. Training = choose $bold(w)$ to make $J$ small.]

This is the same move you make when tuning any system: define an error metric, then minimise it. The
entire art is *choosing a loss whose minimum is the behaviour you actually want, and whose shape a
minimiser can navigate.* Those two demands — right minimum, navigable shape — are in tension, and the
hinge loss is a beautiful compromise between them.

== The loss we *wish* we could use, and why we can't

What we truly care about is the *count of violated corrections*. That is the #text(style:
"italic")[zero–one loss]: $L_"0/1" = 1$ if $m <= 0$ (violated), else $0$. Its minimum is exactly
right — fewest mistakes. But its *shape* is useless for optimisation: it is flat everywhere except a
cliff at $m = 0$. "Flat" means that for almost any small change to a weight, the count does not move at
all, so it gives no hint about *which way* to nudge. In the language of Chapter 6, its gradient is zero
almost everywhere. Minimising the zero–one loss directly is, in general, computationally intractable.

The standard resolution across all of machine learning is to replace the un-navigable true loss with a
#text(style: "italic")[surrogate]: a loss with the same spirit but a smooth, sloped shape that a
minimiser can descend. The hinge loss is the surrogate of choice for margins.

== The hinge loss

The hinge loss charges a penalty whenever the margin falls short of a small positive target $tau$, and
charges nothing once the margin comfortably clears it:

$ L_"hinge"(m) = max(0, tau - m). $

Read it piecewise. If $m >= tau$, then $tau - m <= 0$ and the loss is $0$ — the correction is not just
satisfied but satisfied with room to spare. If $m < tau$, the loss is $tau - m$, growing linearly as
the margin gets worse (and it keeps growing into negative margins, so a badly-violated correction
hurts more than a barely-violated one). The graph is a straight ramp that "hinges" flat at $m = tau$
— hence the name.

Two design points. We use $tau = 1$ rather than $tau = 0$ so that a satisfied correction is pushed a
little *past* the boundary, not left balanced on the knife-edge where a tiny weight wobble would flip
it — a margin buys robustness. And because the loss is exactly $0$ for comfortably-satisfied
corrections, *they stop contributing*: training focuses all its attention on the corrections near or
past the boundary. Those boundary-defining examples have a name.

#toolbox("Support vectors, and the SVM")[
  The hinge loss is the defining loss of the #text(style: "italic")[Support Vector Machine] (SVM),
  one of the most important pre-deep-learning classifiers. The examples with non-zero hinge loss —
  the ones sitting on or inside the margin — are the #text(style: "italic")[support vectors]; they
  alone determine the solution, and the rest could be deleted without changing it. This "only the hard
  cases matter" property is why SVMs generalise well from few examples, and it is exactly why our
  tuner spends its effort on the corrections that are actually in dispute. Our method — pairwise hinge
  loss with the regularisation of Chapter 6 — is precisely a *RankSVM*.
]

#example("hinge loss on the Ignition corrections")[
  Suppose after a round of tuning, three corrections have margins $m_1 = 3$, $m_2 = 0.5$, $m_3 = -2$,
  with $tau = 1$. Their hinge losses are $max(0, 1 - 3) = 0$ (satisfied, no penalty), $max(0, 1 -
  0.5) = 0.5$ (satisfied but inside the margin — still nudged), and $max(0, 1 - (-2)) = 3$ (badly
  violated — the loudest complaint). The total loss is $0 + 0.5 + 3 = 3.5$, and correction 3
  dominates it. A minimiser will therefore work hardest on correction 3 — which is what you want.
]

== The loss zoo: choosing the right shape

Different jobs want different losses. Knowing the menu lets you pick correctly in your next project:

#block(inset: (left: 4pt))[
  #set text(size: 12pt)
  #table(
    columns: (auto, 1fr, 1fr),
    stroke: 0.5pt + black,
    inset: 5pt,
    align: (left, left, left),
    table.header(
      text(weight: "bold")[Loss], text(weight: "bold")[Formula (per example)], text(weight: "bold")[Use it when]
    ),
    [Zero–one], [$1$ if wrong, else $0$], [You want the true error count — but it is intractable to optimise directly.],
    [Hinge (SVM)], [$max(0, tau - m)$], [Ranking / classification with a *margin*; you want robustness and sparse support. *(Us.)*],
    [Squared (MSE)], [$(y - hat(y))^2$], [Regression — predicting a real number; penalises big errors hard.],
    [Absolute (MAE)], [$abs(y - hat(y))$], [Regression robust to outliers (penalty grows only linearly).],
    [Log / cross-entropy], [$-ln p_"true"$], [You want *calibrated probabilities* out — the value model, Chapter 7.],
  )
]

Notice the wrong-tool failure modes. Squared loss on a *ranking* problem punishes a correction that is
correct *by a huge margin* (it drives $hat(y)$ toward an arbitrary target even when the ordering is
already right) — wasted effort, and it can even *un-fix* other corrections to chase a number nobody
asked for. The hinge loss, by going flat once satisfied, never does this. Conversely, hinge gives you
no probability — if you need to *price a gamble* you need the log loss and the machinery of Chapter 7.
Match the loss to the question.

#contrast("Why not just optimise the thing we care about?")[
  It is tempting to say "we care about the violated-correction count, so optimise *that*." We just
  saw why we cannot: the zero–one loss is flat with a cliff, so a gradient-based minimiser is blind on
  it, and exact minimisation is NP-hard in general. The hinge loss is a *convex surrogate* — it upper-
  bounds the zero–one loss (so driving hinge down drives the true error down too) while being smooth
  enough to descend. This "optimise a tractable surrogate that bounds the intractable truth" pattern
  is one of the most transferable ideas in the field: you will meet it again as cross-entropy standing
  in for accuracy, and as a relaxation standing in for a hard combinatorial objective.
]

#problems("5", (
  [With $tau = 1$, compute the hinge loss $max(0, tau - m)$ for each margin: $m = 5$, $m = 1$, $m =
   0$, $m = -4$. Which contributes nothing to training, and why?],
  [A dataset of four corrections has margins $\{2, 0.25, -1, -3\}$ (still $tau = 1$). Compute the
   total hinge loss $J = sum_i max(0, 1 - m_i)$. Which single correction contributes the most, and
   what fraction of the total is it?],
  [Contrast with the zero–one loss. For the same four margins $\{2, 0.25, -1, -3\}$, how many
   corrections does the *zero–one* loss count as violated (using the $m <= 0$ rule)? Explain why the
   correction with margin $0.25$ is treated differently by the two losses, and which treatment is more
   useful for guiding the *next* weight update.],
  [Squared loss goes wrong on ranking. Suppose the correct behaviour is simply "$k$ outranks $c$," and
   one weight setting already gives margin $m = 50$ (hugely correct). A squared loss aimed at a target
   margin of $1$ would report error $(50 - 1)^2 = 2401$ and try to *shrink* the margin. What does the
   hinge loss report for $m = 50$, and why is that the behaviour you want here?],
  [Identify the support vectors. Six corrections have margins $\{4, 1.0, 0.9, -0.5, 3, -2\}$, $tau =
   1$. Which of them have non-zero hinge loss (i.e. are "support vectors" driving the fit)? What is
   the practical meaning of a correction that is *not* a support vector?],
  [Design judgement. You are building a spam filter and you want it to output "probability this email
   is spam," which you will threshold at 0.5. Which loss from the zoo do you reach for, and why *not*
   the hinge loss? (Two sentences.)],
))
