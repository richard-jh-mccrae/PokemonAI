#import "preamble.typ": *

= Fitting the Weights: Gradient Descent, the Perceptron, and the Pocket

We now have a loss to minimise. This chapter is the engine room: *how* the weights actually move. We
add one more term to the objective — a #text(style: "italic")[regulariser] that keeps the fit honest —
then descend the whole thing with an update so simple it is a few lines of arithmetic: the *structured
perceptron*. Along the way you will meet gradient descent (the workhorse of nearly all modern ML), the
*pocket* trick for messy data, and an *adoption gate* that decides whether the fit was even worth
shipping. This is the most mechanical chapter, so do its problems by hand; that is where it sticks.

== The full objective

Fitting corrections is only half of what we want. The other half is *not to over-react*: our weights
began as carefully authored expert seeds, and we would like to move them only as much as the data
truly demands. So the objective has two terms:

$ J(bold(w)) = underbrace(sum_"corrections" max(0, tau - m), "fit the corrections (hinge)") +
underbrace(lambda/2 sum_i (w_i - w_i^"seed")^2, "stay near the expert seeds (L2)"). $

The first term is Chapter 5's hinge loss, summed over corrections. The second is the #text(style:
"italic")[L2 regulariser]: it charges a *quadratic* penalty for every unit a weight strays from its
seed $w_i^"seed"$. The knob $lambda$ (Greek "lambda," called `reg` in the code) sets how conservative
we are: large $lambda$ trusts the seeds and barely moves; small $lambda$ trusts the data and moves
freely.

== Why regularise, and why *quadratic*

#text(style: "italic")[Overfitting] is the disease regularisation prevents. With enough freedom, a
model will contort itself to nail every training example — including their noise — and then generalise
terribly to new situations. In our setting the pathology is concrete: a raw fit on a handful of narrow
corrections will happily gut a broad, valuable doctrine weight to satisfy a couple of special cases.
Regularisation is the counter-pressure that says "movement must be *earned*."

The quadratic shape is the crucial detail. Because the penalty grows with the *square* of the
displacement, moving one weight far is very expensive ($10^2 = 100$) while nudging ten weights a
little is cheap ($10 times 1^2 = 10$) — for the *same* total displacement. So L2 *prefers small,
spread-out adjustments over one dramatic lurch*, which is exactly the temperament you want when
refining an expert prior. (Statistically, this term is a *Gaussian prior* on the weights centred at
the seeds — you are doing Bayesian estimation whether you call it that or not.)

#toolbox("L2 vs L1: ridge and lasso")[
  Two regularisers dominate practice. #text(weight: "bold")[L2] (our choice; also called *ridge*
  regression) penalises $sum w_i^2$ and *shrinks* weights smoothly toward the centre without ever
  quite zeroing them. #text(weight: "bold")[L1] (*lasso*) penalises $sum abs(w_i)$ and tends to drive
  weak weights *exactly to zero*, performing automatic feature selection. Rule of thumb: reach for L1
  when you suspect most features are useless and you want a *sparse* model; reach for L2 when you
  believe most features matter a little and you want *stability*. We want stability around a hand-
  authored prior, so L2 is right. Using both at once is the *elastic net*.
]

== Gradient descent in one paragraph

To minimise $J$ we roll downhill. The #text(style: "italic")[gradient] $nabla J$ is the vector of
partial derivatives $partial J \/ partial w_i$; it points in the direction of *steepest increase* of
$J$. So to *decrease* $J$ we step in the *opposite* direction, scaled by a #text(style:
"italic")[learning rate] $eta$ (Greek "eta"):

$ bold(w) arrow.l bold(w) - eta nabla J(bold(w)), quad "repeat until settled." $

That single line is the beating heart of almost all machine learning, from linear regression to
billion-parameter networks. Everything specific to a model is just *what $nabla J$ works out to be*.
Because our $J$ is *convex* — a single bowl with no false bottoms, thanks to the linear score and the
convex hinge and quadratic terms — gradient descent is guaranteed to find the true minimum. That
guarantee is a luxury deep networks do not have, and a direct dividend of staying linear.

== The gradient works out to the perceptron update

Take the two terms in turn. For a *violated* correction (margin $m < tau$), the hinge piece is
$tau - m = tau - sum_i w_i Delta_i - Delta"tactical"$, whose derivative with respect to $w_i$ is
$-Delta_i$. Descending (stepping against the gradient) therefore *adds* $eta Delta_i$ to each weight.
For the L2 term, the derivative with respect to $w_i$ is $lambda(w_i - w_i^"seed")$, so descending
*subtracts* $eta lambda (w_i - w_i^"seed")$. Put together, one sweep of the optimiser is:

#block(inset: (left: 8pt), [
  #set text(size: 12pt)
  #enum(
    [for every correction still violated, and every rule $i$: $quad w_i arrow.l w_i + eta Delta_i$
      #h(1em) _(push toward satisfying it)_],
    [for every weight: $quad w_i arrow.l w_i - eta lambda (w_i - w_i^"seed")$ #h(1em) _(pull back
      toward the seed)_],
    [clamp every weight into the legible band $[-100, 100]$.],
  )
])

This is the #text(style: "italic")[structured perceptron] — the 1950s perceptron update, generalised
to structured choices and fitted with a regulariser. No external library, no matrix solver: a couple
of loops over small integers. For a system that must run inside a frozen, CPU-only grader, "the
optimiser is ten lines of arithmetic" is not a compromise; it is a feature.

#example("one update by hand")[
  Take the Ignition cluster with one discriminating rule, $Delta = +1$ on
  the correct option, current weight $w = 30$, seed $w^"seed" = 30$, $eta = 1$, $lambda = 0.1$. The
  correction is violated, so step 1 gives $w arrow.l 30 + 1 dot (+1) = 31$. Step 2 pulls back:
  $w arrow.l 31 - 1 dot 0.1 dot (31 - 30) = 31 - 0.1 = 30.9$. One sweep moved the weight from $30$ to
  $30.9$. If the correction stays violated sweep after sweep, where does $w$ come to rest? Set the two
  moves equal and opposite — that is the next section's problem, and its answer is the single most
  useful formula in this chapter.
]

== Contradiction, oscillation, and the pocket

Real correction sets are #text(style: "italic")[non-separable]: they contradict each other, so *no*
weight vector satisfies all of them, and the perceptron never fully settles — it *oscillates* around
the boundary, and the *last* weights it happens to produce can be worse than ones it passed through
earlier. The remedy is the #text(style: "italic")[pocket algorithm]: as you iterate, keep a copy of
the best-scoring weights seen so far (lowest $J$), and *return that pocketed copy*, not the final one.
Simple, and essential — without it, satisfiable corrections were being silently reported as
impossible.

The regulariser also tames a second failure. On a *perpetually* violated correction, a raw perceptron
would push a weight to absurd values (we once watched one climb to $156$). With the L2 pull-back, a
constant push of size $p$ settles at a *bounded* fixed point: the weight comes to rest where the push
and the pull-back cancel, at roughly $w^"seed" + p \/ lambda$. Small $lambda$ ⟹ the weight can travel
far; large $lambda$ ⟹ it stays near the seed. This is the mathematics of "how much should one stubborn
correction be allowed to move a weight," and you will derive it yourself in the problems.

== The adoption gate: ship only what earns it

Even a bounded, pocketed fit can be a bad idea. So there is a final, blunt check: the tuned weights
are shipped *only if they satisfy strictly more corrections than the expert seeds already did.*
Otherwise the move bought nothing (or merely traded one satisfied correction for another), and we keep
the seeds. A consequence worth internalising: an *empty* result — "no weight change ships" — is a
perfectly honest, common outcome. It means *this batch of mistakes is not a weight problem at all; it
needs new features* (route H, Chapter 4). The gate is what stops the optimiser from lying to us with
motion that looks like progress.

#contrast("Why not Adam, momentum, or a fancy optimiser?")[
  Modern deep learning leans on elaborate optimisers — momentum, RMSProp, Adam — because their loss
  surfaces are *non-convex*: riddled with ravines, saddle points, and local minima that plain gradient
  descent stalls in. Those tools are heavier machinery for a harder landscape. Our landscape is a
  single convex bowl with a dozen weights, so plain (sub)gradient descent finds the global optimum in
  a handful of cheap iterations; Adam would be a cannon aimed at a nail, and it would drag in
  dependencies the grader forbids. The lesson is the recurring one: the optimiser should match the
  *shape of the problem*. Convex-and-small earns the simplest tool in the drawer.
]

#problems("6", (
  [Do one full perceptron sweep. A single discriminating rule has weight $w = 20$, seed $w^"seed" =
   20$; the correction is violated with $Delta = +1$; $eta = 1$, $lambda = 0.2$. Apply step 1 then
   step 2 and give the new weight.],
  [Derive the fixed point. A correction stays violated forever, applying a constant push of $+p$ to a
   weight each sweep, against the L2 pull-back $-eta lambda (w - w^"seed")$ (with $eta = 1$). Setting
   the net change to zero at equilibrium, solve for the resting weight $w^*$ in terms of $w^"seed"$,
   $p$, and $lambda$.],
  [Use your formula. With $w^"seed" = 30$, a push $p = 5$, and $lambda = 0.1$, what weight does the
   stubborn correction drive to? Now raise $lambda$ to $0.5$ — what is the new resting weight? State
   in one sentence what $lambda$ controls.],
  [Compute the regularised objective. Weights $bold(w) = (32, 18)$, seeds $bold(w)^"seed" = (30, 20)$,
   $lambda = 0.5$; and two corrections with margins $m_1 = 2$, $m_2 = -1$ under $tau = 1$. Compute
   $J = sum max(0, 1 - m_i) + (lambda\/2) sum (w_i - w_i^"seed")^2$.],
  [Show the oscillation intuition. Two corrections demand *opposite* moves on the same weight: one has
   $Delta = +1$, the other $Delta = -1$, and both are always violated. Ignoring regularisation, trace
   the weight over three sweeps starting from $w = 10$, $eta = 1$, applying *both* pushes each sweep.
   What happens, and what does the pocket algorithm return?],
  [L1 vs L2 choice. You fit a model with 200 candidate features and strongly suspect only about 15 truly
   matter; you want the model to *tell you which*. Which regulariser do you choose and what property
   of it gives you the answer? What would L2 do differently to the 185 useless features?],
  [Learning-rate intuition (no Pokémon needed). Minimising $f(w) = w^2$ by gradient descent, the
   update is $w arrow.l w - eta dot 2 w$. Starting at $w = 1$, compute $w$ after one step for $eta =
   0.1$ and for $eta = 1.5$; for $eta = 1.0$ take *two* steps. Which $eta$ converges toward the
   minimum, which *bounces* between two values forever, and which *diverges*? What does this teach
   about choosing $eta$?],
))
