#import "preamble.typ": *

= Judging a Change: Evaluation and Honesty

We have built a machine that scores moves, learns weights, estimates probabilities, and searches. One
question remains, and it is the most important one: *did any of it actually help?* Every change we make
— a new rule, a re-tuned weight, a value model switched on — is a *hypothesis*, and a hypothesis must
be *tested* against reality, not against our own hopes. This chapter is about evaluation: how we know a
change is real, why a promising number can be a lie, and why "we built it and turned it off" is
sometimes the most honest sentence in the whole project. This is the scientific method wearing a lab
coat over the machine-learning, and it is what separates engineering from wishful thinking.

== The ground truth is winning games

Notice the layering. The loss functions of Chapters 5–7 are *proxies*: we minimise hinge loss or
log-loss because they are tractable and correlated with good play, but nobody awards prizes for low
hinge loss. The only thing that actually matters is *winning games on the ladder*. So the final judge
of any change is an #text(style: "italic")[A/B test]: play many games with the change on (A) versus off
(B) and compare win rates. The loss is what we *train* on; the win rate is what we *evaluate* on. Never
confuse the two — a model can drive its training loss to zero and still lose more games, and if it
does, the games win the argument.

== Noise, and the confidence interval

Win rates are *noisy*: flip a fair coin 100 times and you will rarely get exactly 50 heads. So if
version A wins 52% of 400 games, is it truly better, or did it get lucky? The tool that answers this is
the #text(style: "italic")[confidence interval] (CI): a range that, loosely, "we are 95% sure contains
the true win rate." For a win rate $hat(p)$ over $N$ games, the standard error is

$ "SE" = sqrt((hat(p)(1 - hat(p))) / N), quad "and the 95% CI is roughly" quad hat(p) plus.minus 1.96 times "SE". $

The single most important habit this gives you: *look at whether the interval crosses the break-even
line.* A result of "51%, 95% CI $[48%, 54%]$" is *not* evidence of improvement — the interval includes
50%, so the data cannot distinguish the change from doing nothing. Only when the whole interval sits
above 50% have you shown a real gain. Reporting a bare "51%!" without its interval is the most common
way honest-looking numbers mislead.

#example("safe, but not an improvement")[
  When the value model of Chapter 7 was first A/B-tested it scored *50%, CI $[48%, 53%]$* over 2000
  games. Read that correctly: the interval straddles 50%, so this is *not* a win — it is a
  demonstration that the change is *safe* (it did not make things worse, and it did not crash). "Safe
  but not yet better" is a real, reportable result, and it is different from both "better" and
  "worse." Conflating "not shown to help" with "shown not to help" is a classic error; the CI keeps
  the two distinct.
]

The width of the CI shrinks like $1 \/ sqrt(N)$: to *halve* your uncertainty you must play *four
times* as many games. This is why serious A/B tests need thousands of games, and why you cannot settle
a 1%-size effect with a few dozen matches — the noise is larger than the signal you are hunting.

== The gate, not the optimiser

There is a discipline in *how* the win-rate signal is used. It is far too low-bandwidth to tune
individual weights (Chapter 1: one bit per roughly 40 decisions), so it is *never* the per-weight optimiser.
Instead it is the *gate*: it decides whether a whole finished configuration ships. Corrections and
their dense per-decision labels do the fine-grained teaching (Chapters 4–6); the ladder does the
final, coarse, authoritative yes/no. Using each signal only for the job its bandwidth suits is a piece
of engineering judgement worth carrying everywhere.

#contrast("Judging a change by its training score — the cardinal sin")[
  The tempting shortcut is to evaluate a change by the very number you optimised — "the new weights
  satisfy more corrections, ship them!" This is measuring the change against its own homework. The
  danger is #text(weight: "bold")[overfitting to the corpus]: weights contorted to nail your specific
  training corrections may play *worse* in general, and the correction count will happily rise while
  the win rate falls. This is #text(weight: "bold")[Goodhart's Law] — *"when a measure becomes a
  target, it ceases to be a good measure."* The defences are exactly those a scientist uses: a
  *held-out* set the model never trained on (Chapter 7's holdout log-loss), and an *independent* metric
  on fresh data (the ladder win rate). The tuner is forbidden from self-certifying for precisely this
  reason; the games it never saw get the final word.
]

== Isolating the effect: paired comparison

One subtlety makes or breaks a game-AI A/B test. If deck D beats deck O 55% of the time *regardless* of
your change, then measuring "D-with-change versus O" and seeing 55% proves nothing — you are seeing the
deck matchup, not your change. The fix is a #text(style: "italic")[paired comparison]: measure the
*difference* between change-on and change-off *against the same fixed opponent*, so the raw matchup
cancels and only your change's effect survives. The value model's honest verdict — an aggregate
*$-0.55%$, CI $[-1.27%, +0.16%]$* across six matchups — came from exactly this paired design. A naïve
single-battle "51%" would have been meaningless; the paired delta is what let us conclude, truthfully,
"this does not help."

== Parking as a first-class result

Which brings us to the theme of the whole book's ending. Two of the most sophisticated components —
the learned value model and the depth-2 escalation search — were built completely, validated
carefully, and then *switched off*, because their honest A/B tests showed no gain (the value model
$-0.55%$; the escalation search a clear regression to 44%). In a culture that rewards shipping, this is
countercultural and correct. A change that does not beat the baseline should not ship, no matter how
clever it is or how much work it took — and saying so plainly, with the numbers, is the mark of a
mature system. *Parked, with evidence* is not failure; it is the evaluation loop doing its job. The
sunk cost of building something is never a reason to inflict it on the win rate.

#problems("10", (
  [Read the interval. Three A/B results: (a) 53%, CI $[50.5%, 55.5%]$; (b) 51%, CI $[48%, 54%]$;
   (c) 47%, CI $[45%, 49%]$. For each, state whether it shows an improvement, no distinguishable
   effect, or a regression — and justify by where the interval sits relative to 50%.],
  [Compute a CI. A change wins $hat(p) = 0.52$ over $N = 2500$ games. Compute the standard error
   $sqrt(hat(p)(1 - hat(p)) \/ N)$ and the approximate 95% half-width $1.96 times "SE"$. Does the
   resulting interval clear 50%?],
  [Sample size. Using $"SE" prop 1 \/ sqrt(N)$, by what factor must you increase the number of games
   to *halve* the width of a confidence interval? If 2500 games gave a half-width near $2%$, roughly
   how many games would you need for a half-width near $0.5%$?],
  [Paired design. Deck D beats opponent O about 60% of the time no matter what. You want to know
   whether a new rule helps D. Explain why a single battle "D-with-rule vs O = 61%" is nearly
   worthless, and what quantity the *paired* A/B measures instead.],
  [Goodhart in the wild. A teammate tunes weights until the agent satisfies 100% of the 40
   corrections, and proposes shipping on that basis. State the risk in one sentence, name the law it
   illustrates, and give the two checks you would demand before shipping.],
  [The honest verdict. The value model's paired A/B was $-0.55%$ with CI $[-1.27%, +0.16%]$. Argue,
   in three sentences, why "park it, switched off" is the correct decision here — addressing both the
   sign of the point estimate and the fact that the interval's upper end is (barely) positive.],
))
