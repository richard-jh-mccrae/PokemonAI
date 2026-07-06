#import "preamble.typ": *

#heading(level: 1, numbering: none)[Final Examination]

#block(fill: accent.lighten(88%), stroke: 0.8pt + accent.lighten(25%), radius: 3pt, inset: 10pt)[
  #set text(size: 12pt)
  Twenty questions covering the whole book, deliberately *interleaved* — consecutive questions jump
  between topics, because real understanding means recognising which idea a problem needs without
  being told. Work them by hand; a calculator is fine. Aim for the *reasoning*, not just the number.
  Full worked solutions are in the next section. Suggested pass mark: 70%.
]

// local question renderer
#let eq(n, body) = block(above: 0.7em, below: 0.2em)[
  #grid(columns: (2.0em, 1fr), gutter: 0.4em,
    text(weight: "bold", fill: accent)[#n.], body)
]

#eq(1)[*(Scoring.)* Weights $bold(w) = (40, 10, -20)$; option X fires rules 1 and 3, option Y fires
rule 2, and $"tactical" = 0$ for both. Compute both scores and give the $argmax$.]

#eq(2)[*(Attribution.)* At a state, the correct option fires rules $\{2, 3\}$ and the chosen option
fires rules $\{1, 3\}$ (three rules total). Write the difference vector $bold(Delta)$, and state
whether this is a route-W (weight) or route-H (feature) fix, with the one-line reason.]

#eq(3)[*(Margin & repair.)* Continuing question 2, with weights $bold(w) = (20, 15, 30)$ and
$Delta"tactical" = 0$, compute the margin $m = sum_i w_i Delta_i$. Is the correction satisfied? Give
one single-weight change (weight, direction, smallest integer amount) that repairs it.]

#eq(4)[*(Loss.)* With hinge target $tau = 1$, compute the hinge loss for margins $m = 3$, $m = -2$,
and $m = 0.5$, and give the total.]

#eq(5)[*(Optimiser.)* Perform one structured-perceptron sweep on a single violated correction:
weight $w = 25$, seed $w^"seed" = 25$, $Delta = +1$, learning rate $eta = 1$, regularisation
$lambda = 0.2$. Give the updated weight.]

#eq(6)[*(Fixed point.)* A stubborn, always-violated correction pushes a weight by $+p$ each sweep
against the L2 pull-back. Using $w^* = w^"seed" + p \/ lambda$, find where a weight with seed $20$
settles under a push $p = 4$ and $lambda = 0.2$. What does raising $lambda$ do to that resting point?]

#eq(7)[*(Probability out.)* Compute the sigmoid $sigma(1) = 1 \/ (1 + e^(-1))$ using $e^(-1) approx
0.368$. In one sentence, what does the output represent in the value model?]

#eq(8)[*(Calibration.)* The value model predicts $p = 0.8$ for a state. Compute its log-loss if the
state was truly a *win* ($-ln 0.8$, use $ln 0.8 approx -0.223$) and if it was truly a *loss*
($-ln 0.2$, use $ln 0.2 approx -1.609$). Which error does log-loss punish harder, and why is that the
behaviour we want?]

#eq(9)[*(The floor.)* Explain why a model that always outputs $p = 0.5$ scores a log-loss of exactly
$ln 2 approx 0.693$ on every example, and what it means to score *below* $0.693$ on held-out data.]

#eq(10)[*(Counting.)* Compute $binom(7, 3)$ from the definition.]

#eq(11)[*(Deck odds.)* A card has $u = 1$ unseen copy; there are $K = 6$ hidden prize slots and
$d = 6$ hidden deck cards. Compute $H$ and $P("deck still holds the copy") = 1 - binom(K, u) \/
binom(H, u)$.]

#eq(12)[*(Expected value.)* A safe line is worth $90$. A gamble is worth $200$ with probability $0.3$
and $50$ with probability $0.7$. Compute the gamble's EV and state which line to take.]

#eq(13)[*(Minimax.)* You (MAX) choose L or R. After L the opponent (MIN) faces leaves $\{2, 8\}$;
after R they face $\{5, 4\}$. Give the value of each move, the root value, and your best move.]

#eq(14)[*(Search cost.)* With branching factor $b = 6$ and depth $d = 3$, how many leaves does the
game tree have? Why does this quantity make full-depth search impractical in general?]

#eq(15)[*(Expectimax.)* You (MAX) choose between a safe play worth $6$ and a coin play paying $12$ on
heads ($0.5$) and $0$ on tails. Compute the coin play's value and state your choice — then say what a
*risk-averse agent that is already winning* might do instead, and why.]

#eq(16)[*(Evaluation.)* An A/B test reports a $55%$ win rate over just $N = 100$ games. Estimate the
standard error $sqrt(hat(p)(1 - hat(p)) \/ N)$ and the approximate 95% half-width. Does this result
demonstrate a real improvement? Explain using where the interval sits.]

#eq(17)[*(Sample size.)* Confidence-interval width scales like $1 \/ sqrt(N)$. To shrink a half-width
from $4%$ to $1%$, by what factor must you increase the number of games?]

#eq(18)[*(Regularisation choice.)* You have 300 candidate rule-features and believe only about 20
matter, and you want the fit to *tell you which*. Which regulariser — L1 or L2 — do you choose, and
what property gives you the answer?]

#eq(19)[*(The blind spot.)* Explain, in terms of feature vectors, why *no* weight change can ever make
the agent rank two options differently when they fire exactly the same rules — and what you must do
instead.]

#eq(20)[*(Judgement.)* You are asked to build a decision agent for a new game. You have a slow
simulator, a few hundred hand-labelled example decisions, a CPU-only deployment target with no extra
libraries allowed, and a requirement that every decision be explainable to a judge. Name the family of
approach you would choose, cite three of the five "compass" questions that drive the choice, and name
one technique you would explicitly *avoid* and why.]
