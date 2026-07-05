#import "preamble.typ": *

= Looking Ahead: Search, Minimax, and Expectimax

Everything so far judged a *single* move by scoring it. But good play often needs to look *ahead*:
"if I attach here, then next turn I can knock out, unless they retreat, in which case…" Reasoning about
sequences of moves — yours, chance's, and the opponent's — is #text(style: "italic")[search], the
other great pillar of game AI alongside learning. This chapter builds the classical search ideas the
agent uses to plan a turn and to know when it has a guaranteed win, and then draws the sharp line
between our *bounded, exact* search and the *deep, learned* search of an AlphaZero — and why, here,
bounded wins.

== Planning a turn as search

Within a single turn the agent may take several actions before ending it. The *turn planner* treats
this as a search over the *reachable end-of-turn boards*: enumerate sensible action sequences, evaluate
the board each one leads to (using the scoring and EV machinery of the previous chapters as the
*leaf evaluation*), and keep the best. Its most important rung is the #text(style: "italic")[lethal
solver]: a *sound* check for "can I guarantee a win this turn?" If a forced knockout sequence exists,
search finds it and takes it — no probability, no learning, just a proof. When you *can* compute the
right answer exactly, you should; learning is for when you cannot.

== Adversarial search: the game tree and minimax

Looking past your own turn means modelling the opponent, and the opponent is not on your side. The
classical framework is the #text(style: "italic")[game tree]: nodes are states, edges are moves,
levels alternate between *your* turn and *theirs*. You pick moves to *maximise* an evaluation; a
rational opponent picks moves to *minimise* it. Propagating values up this tree is #text(style:
"italic")[minimax]: at a leaf, evaluate the board; at a MAX node, take the largest child value; at a
MIN node, take the smallest.

#example("a two-ply minimax")[
  It is your move (MAX). You have two plays, L and R. After L, the opponent (MIN) chooses between
  boards worth $3$ and $5$ to you; being adversarial, they pick $3$. After R, they choose between $2$
  and $9$; they pick $2$. So L is *worth* $3$ and R is worth $2$ — the value each play has *after* the
  opponent's best reply. You (MAX) take $max(3, 2) = 3$: play L. Note the trap this avoids — R
  contains the tempting $9$, but a competent opponent never lets you have it. Minimax is the
  mathematics of "assume they play well."
]

The cost of search is its curse. If there are $b$ legal moves at each step (the #text(style:
"italic")[branching factor]) and you look $d$ steps ahead (the #text(style: "italic")[depth]), the
tree has about $b^d$ leaves. This grows explosively: at $b = 10$, looking $5$ moves ahead is
$10^5 = 100{,}000$ boards; $10$ moves ahead is ten *billion*. Exponential growth is why you cannot
simply "search to the end" of a non-trivial game, and it is the single fact that shapes every
practical search algorithm.

#toolbox("Alpha–beta pruning, and the search family")[
  You rarely search the whole tree. #text(weight: "bold")[Alpha–beta pruning] is the classic
  speed-up: while exploring, if you have already found a reply so good for the opponent that it makes
  the current branch worse than one you have banked, you can *stop* exploring that branch — its exact
  value cannot change your decision. In the best case this roughly *square-roots* the number of leaves
  you must examine, letting a chess engine search twice as deep for the same work. Cousins of this
  idea power much of classical AI: #text(weight: "bold")[A\*] for shortest paths, #text(weight:
  "bold")[iterative deepening] for anytime search, and #text(weight: "bold")[transposition tables]
  (a cache — very much an engineer's move) to avoid re-evaluating states reached by different move
  orders.
]

== Chance in the tree: expectimax

Card games have *randomness* — a coin flip, a shuffle-and-draw. The tree then contains a third kind of
node, a #text(style: "italic")[chance node], whose value is not a max or a min but an *expectation*
(Chapter 8): the probability-weighted average of its children. Minimax plus chance nodes is
#text(style: "italic")[expectimax]. This is exactly the gamble-line evaluation of Chapter 8, now seen
as one level of a search tree: a decision node choosing the best line, where a line may pass through a
chance node priced by EV.

#example("one chance node")[
  You (MAX) choose between a *safe* play worth $5$, and a *coin* play that wins big on heads: heads
  ($0.5$) leads to a board worth $10$, tails ($0.5$) to a board worth $2$. The coin play is a chance
  node worth $0.5 times 10 + 0.5 times 2 = 6$. You compare $max(5, 6) = 6$ and take the coin — its
  *expected* value beats the safe line, even though its worst case ($2$) is worse than the safe $5$.
  Expectimax is how you fold "on average" reasoning into look-ahead.
]

== Why bounded and exact, not deep and learned

Here we arrive at the crossroads with the most famous systems in game AI. Engines like AlphaZero play
superhuman chess and Go by combining a *deep* search — #text(style: "italic")[Monte Carlo Tree Search]
(MCTS), which samples thousands of lines deep into the tree — with a *neural network* that evaluates
leaves and suggests moves, all trained by millions of *self-play* games. It is the crowning
achievement of the search-plus-learning marriage. We use a small, sharp fraction of it and deliberately
skip the rest.

#contrast("AlphaZero-style MCTS + a value network — why not here")[
  Four reasons, each a now-familiar constraint. #text(weight: "bold")[Compute & time:] MCTS spends its
  strength on *thousands* of simulations per move; our grader allows about ten minutes for an entire
  match on a CPU. #text(weight: "bold")[Data:] the leaf-evaluating network is trained on *millions* of
  self-play games — we have a trickle. #text(weight: "bold")[Hidden information:] chess and Go are
  *perfect-information*; our opponent's hand and deck order are hidden, so a naïve tree would branch on
  information we do not have (this is why the agent models the opponent only through a light, γ-gated
  *Read*, not a full search of their choices). #text(weight: "bold")[Legibility:] a searched line that
  a human can read and check beats an opaque rollout in a Strategy competition. So we take search's
  *sound* core — the exact lethal solver, the one-level expectimax for gambles, a *bounded, depth-2*
  escalation for the hardest ties — and lean on the tuned linear model for everything else. Tellingly,
  even that depth-2 escalation, when measured, *lost* to the simpler tuned scorer and was switched off:
  more search is not automatically better search. Its two-ply model of the opponent's reply was too
  crude to trust, and a crude look-ahead is worse than a good heuristic.
]

#toolbox("Search vs learning, and the reinforcement-learning bridge")[
  Search and learning are the two ways to get good decisions, and they trade off. *Search* spends
  compute *at decision time* to reason about consequences; *learning* spends compute *ahead of time*
  to compile experience into a fast policy or evaluation. #text(weight: "bold")[Reinforcement
  learning] (RL) is the framework that unifies them: an agent learns a policy or value function from
  the *reward* of its own actions, and AlphaZero is RL with search inside the loop. We reject RL as our
  *primary* trainer for the reason from Chapter 1 — the win/loss reward is one noisy bit per roughly 40
  decisions, far too sparse to train much — but the vocabulary (policy, value, reward, exploration
  versus exploitation) is worth owning; it is the lingua franca of sequential decision-making, and the
  *multi-armed bandit* — the minimal RL problem of balancing trying new options against exploiting the
  best known one — underlies everything from A/B testing (next chapter) to ad placement.
]

#problems("9", (
  [Minimax. You (MAX) choose L or R. After L the opponent (MIN) faces leaves $\{6, 1\}$; after R they
   face leaves $\{4, 3\}$. Give the value of L, the value of R, the root value, and your best move.],
  [Tree growth. A position has branching factor $b = 8$. How many leaves are there at depth $d = 4$?
   Write the general formula, and explain in one sentence why "just search to the end of the game" is
   infeasible for large $b$ and $d$.],
  [Expectimax. You (MAX) choose between a safe play worth $7$ and a coin play: heads ($p = 0.5$) leads
   to $16$, tails to $0$. Compute the coin play's expected value and state which play you take. Then
   find the heads-probability $p$ at which you would be *indifferent* between the two.],
  [Worst case vs expected. In problem 3, the coin play's *worst* outcome is $0$, worse than the safe
   $7$. Give one reason an agent might still prefer the higher-EV coin play, and one situation (think
   about being *ahead* late in a match) where it should prefer the safe play despite lower EV. What
   does this tell you about EV as the *sole* decision rule?],
  [Soundness. The lethal solver only claims a win when it can *prove* a forced knockout sequence
   exists. Why is it acceptable for it to sometimes *miss* a win it cannot prove, but *never*
   acceptable for it to *claim* a win that is not forced? Relate your answer to the difference between
   an optimistic and a sound (worst-case) evaluation.],
  [Match the method. For each, say whether *search at decision time* or *learning ahead of time* is
   the better fit, and why (one line each): (a) "is there a guaranteed knockout this turn?"; (b) "how
   good is this messy midgame board, roughly?"; (c) "what is the exact probability my next draw hits?"],
))
