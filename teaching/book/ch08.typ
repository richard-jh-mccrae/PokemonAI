#import "preamble.typ": *

= Counting the Deck: Probability and Expected Value

The agent plays under uncertainty: cards are hidden in the deck and under the prizes, and coins are
flipped. A weaker agent papers over this with vibes — "probably safe," "usually works." Ours computes
the odds *exactly*, because for a deck of known composition the mathematics is elementary and there is
no excuse for guessing. This chapter builds that machinery from counting up to *expected value*, the
principle that lets the agent price a risky play against a safe one on a single common scale. None of
it needs calculus — just careful counting.

== Counting: combinations

Almost every deck question reduces to "in how many ways can I choose $k$ things from $n$, when order
does not matter?" That count is the #text(style: "italic")[binomial coefficient]:

$ binom(n, k) = (n!) / (k! (n - k)!), quad "read" quad n "choose" k. $

Here $n! = n times (n-1) times dots.c times 1$. For example $binom(5, 2) = 5! \/ (2! dot 3!) = 120
\/ (2 dot 6) = 10$: there are ten ways to pick two cards from five. This one function is the atom of
everything below. (In the code it is `math.comb` — one standard-library call, no dependencies.)

== Drawing without replacement: the hypergeometric distribution

When you draw cards from a deck, you do *not* put them back — each draw changes what remains. That is
sampling #text(style: "italic")[without replacement], and the distribution governing "how many of the
thing I want turn up" is the #text(style: "italic")[hypergeometric]. The agent's central deck question
has this exact shape:

#block(inset: (left: 6pt), text(style: "italic")[Some copies of a card I need are unseen — hidden
either in my deck or under my face-down prizes. What is the probability at least one is still in my
deck (rather than all being stranded under the prizes)?])

Set up the count. Let $u$ be the number of unseen copies, $K$ the number of hidden prize slots, and
$d$ the number of hidden deck cards, so there are $H = d + K$ hidden positions in total, of which the
$K$ prize slots are a random subset. The card is *absent* from the deck only if *all* $u$ copies
landed in the $K$ prize slots. The number of ways to place all $u$ copies among the prize slots is
$binom(K, u)$, out of $binom(H, u)$ ways to place them among all hidden positions, so:

$ P("all" u "copies prized") = binom(K, u) / binom(H, u), quad quad
P("deck still holds" >= 1) = 1 - binom(K, u) / binom(H, u). $

This is the formula in `deck_odds.py`, and it is *exact* — no sampling, no approximation. Notice how
it behaves at the edges, which is how you sanity-check any probability formula: if $u = 0$ (every copy
already seen elsewhere) it gives $0$; if $u > K$ (more copies than prize slots, so by pigeonhole one
*must* be in the deck) it gives $1$; if $K = 0$ (no hidden prizes) it gives $1$. A good formula agrees
with common sense at the extremes and fills in the uncertain middle with real numbers.

#example("should I play a second search card?")[
  You want to draw your last Staryu; it might be prized. Say $u = 2$ copies are unseen, $K = 6$ prize
  slots are hidden, and $d = 12$ deck cards remain, so $H = 18$. Then $P("both prized") = binom(6, 2)
  \/ binom(18, 2) = 15 \/ 153 approx 0.098$, so $P("still in deck") approx 0.902$. Now the agent
  knows: a search that hunts Staryu will hit about $90%$ of the time — worth playing. Contrast the
  vibes-based agent, which either wastes the search on a near-certain whiff or skips a $90%$ play out
  of vague caution. Exact odds turn a judgement call into arithmetic.
]

A close cousin answers "if I draw $n$ cards from a pool of $p$ containing $c$ copies of what I want,
what is the probability I hit at least one?" — same logic, $1 - binom(p - c, n) \/ binom(p, n)$. This
is the engine behind pricing a "draw six cards and hope" play.

#toolbox("With replacement vs without: binomial vs hypergeometric")[
  If you *did* replace each card before the next draw, the count of hits would follow the
  #text(style: "italic")[binomial] distribution, and $P(>= 1 "hit"" in " n "draws") = 1 - (1 - c\/p)^n$
  — simpler, because the per-draw odds never change. The hypergeometric is its without-replacement
  sibling. When the pool $p$ is *large* relative to the draws, removing a few cards barely changes the
  odds and the two nearly agree — which is why pollsters (sampling millions without replacement)
  happily use binomial-style formulas. In a 60-card deck the difference is real, so we use the exact
  hypergeometric. Related counting puzzles you now have the tools for: the birthday problem, lottery
  odds, and the "how likely is my opening hand to brick" calculation every deck-builder wants.
]

== Expected value: pricing uncertainty on one scale

Knowing the odds is half the job; the other half is *deciding*. The tool is #text(style:
"italic")[expected value] (EV): the probability-weighted average of the outcomes' values.

$ "EV" = sum_"outcomes" P("outcome") times "value"("outcome"). $

EV is the "fair price" of a gamble — the average payoff if you could run it many times. Its magic is
#text(style: "italic")[linearity]: the EV of a whole turn is the sum of the EVs of its parts, so you
can build up the value of a complicated line piece by piece. The agent uses EV to compare a *gamble
line* (a play with one chance node — a shuffle-and-redraw, a coin attack) against a *deterministic
line* (a guaranteed outcome) on a single common scale.

#example("to gamble or to bank?")[
  A safe line guarantees a board worth $100$. A risky line either hits (probability $0.6$) for a board
  worth $200$, or misses (probability $0.4$) for $0$. Which is better? Compute the gamble's EV:
  $0.6 times 200 + 0.4 times 0 = 120$. Since $120 > 100$, the gamble is worth it *on average* — take
  it. Crucially, the decision rule is *EV comparison*, not "is success more likely than not?" Here
  success is $60%$; but even at a lower hit rate the gamble could win on EV if the payoff were bigger.
  The break-even hit rate is where $200 p = 100$, i.e. $p = 0.5$: above it, gamble; below it, bank.
  This is why the agent prices gambles by EV and never by a fixed "$P > 50%$" threshold — the payoff
  sizes matter as much as the odds.
]

Putting the two halves together: the agent computes the *exact* hit probability with the
hypergeometric formula, multiplies by the *value* of each resulting board (from its combat math), sums
to an EV, and compares against the safe line. This is a one-level #text(style: "italic")[expectimax] —
a decision node choosing the max over lines, each line possibly containing a chance node evaluated by
expectation. Chapter 9 generalises this to looking several moves ahead.

#contrast("Why exact odds instead of Monte Carlo simulation?")[
  A popular alternative is #text(weight: "bold")[Monte Carlo]: don't derive the probability — *simulate*
  the draw thousands of times and count how often you hit. It is general (it works when the maths is
  too hard to do by hand) and it is how big game engines like AlphaGo estimate positions. We don't
  need it here: our deck composition is known exactly, so the hypergeometric gives the *true*
  probability in one cheap `comb` call, with *zero sampling noise* and no time budget spent rolling
  dice. Monte Carlo would give a noisy estimate of a number we can get exactly — strictly worse.
  Reach for simulation when the state space is too tangled for a closed form (Chapter 9's deep trees);
  reach for the exact formula whenever, as here, you can actually write it down.
]

#problems("8", (
  [Compute the combinations $binom(6, 2)$, $binom(10, 3)$, and $binom(18, 2)$ from the definition
   $binom(n,k) = n! \/ (k!(n-k)!)$.],
  [Own-deck odds. A card has $u = 2$ unseen copies; there are $K = 4$ hidden prize slots and $d = 8$
   hidden deck cards. Compute $H$, then $P("deck still holds" >= 1) = 1 - binom(K, u) \/ binom(H, u)$.],
  [Sanity-check the formula at the edges. Without heavy computation, state the value of
   $P("deck holds" >= 1)$ when (a) $u = 0$; (b) $u = 5$ while $K = 3$; (c) $K = 0$. Give the one-line
   reason for each.],
  [Draw-and-hope. Your deck-pool has $p = 20$ cards including $c = 3$ copies of the card you need. You
   will draw $n = 6$. Compute $P(>= 1 "hit") = 1 - binom(p - c, n) \/ binom(p, n)$, given
   $binom(17, 6) = 12376$ and $binom(20, 6) = 38760$.],
  [With vs without replacement. For the same $p = 20$, $c = 3$, $n = 6$, compute the *binomial*
   (with-replacement) estimate $1 - (1 - c\/p)^n = 1 - 0.85^6$ (use $0.85^6 approx 0.377$). Compare it
   to your exact answer from problem 4 and explain, in one sentence, the direction of the difference.],
  [Expected value. A safe line is worth $80$. A gamble is worth $150$ with probability $0.5$ and $20$
   with probability $0.5$. Compute the gamble's EV and state which line the agent takes.],
  [Break-even. A gamble pays $180$ on success and $0$ on failure; the safe line is worth $90$. Below
   what success probability $p$ should the agent *decline* the gamble? Show the equation you solved,
   and explain why this is the right rule even when $p < 0.5$ can still favour gambling for a
   different payoff.],
))
