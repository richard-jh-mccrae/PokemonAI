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

== Planning the whole match, without searching the opponent

The turn planner of §9.1 is a *within-turn* optimiser: it looks at the moves available *now* and finds
the best way to end *this* turn. But real strategy spans the whole *match* — "force them to spend all six
prizes chipping through my walls while I build the finisher," "do not knock out that weak blocker yet, it
is shielding me from the monster waiting behind it." That is planning at a larger scale, and the obvious
way to do it — *search the opponent's future choices* — is exactly what we just watched *lose* (§9.4):
the depth-2 escalation's crude model of the opponent's reply was worse than no search at all.

So the agent plans the match a different way. It *computes*; it does not *search*. The key realisation is
that the most useful match-scale questions do not require branching on what the opponent *chooses* — they
require *arithmetic* on what the cards *can do*. "How many of my turns to take six prizes?" and "how many
of their turns until they can knock out my attacker?" are *counting* problems, not search problems — as
long as you make one honest simplification: hold the opponent *static* (reckon on their current board and
its natural development, not their cleverest reply). That assumption is a lie, but a *bounded, safe* lie,
and it turns an intractable tree into a handful of divisions.

The layer that does this is the *Match Planner*. Once per turn, before the turn planner runs, it computes
a #text(style: "italic")[Game Plan]: a *route* (which specific enemy Pokémon I will knock out to bank my
six prizes), a *mode* (am I racing, stalling, stabilising, sacrificing?), a *confidence* (how feasible is
this plan, as a number), and a *directed goal* it hands down to the turn planner ("this turn, develop";
"this turn, knock out on the route"). It never locks: it is recomputed from scratch every turn, so when
the opponent does something surprising, the numbers simply move and the plan follows — no special "they
countered me" detector required.

=== The Threat Clock: a number, computed

The heart of it is one primitive, and it is pure arithmetic of the kind you already trust. The
#text(style: "italic")[Threat Clock] answers, for one of my Pokémon: *in how many of the opponent's turns
could they first knock it out?* Everything it needs is a card fact. An attacker needs a certain amount of
Energy for its knockout attack; Energy arrives at about one per turn; evolving to a bigger form costs a
turn per step; a benched attacker needs a turn to be promoted to the front. Add those up to find when the
first hit lands,

$ "first hit" = max(1, "evolutions needed", "energy needed" - "energy now") + "promotion", $

and if one hit does not knock out, keep hitting — $ceil("HP" \/ "damage")$ hits, one per turn — so the
knockout lands on turn $"first hit" + "hits" - 1$. Take the smallest such number over every attacker they
have, or could evolve into. *That* is the Threat Clock.

#example("reading the clock")[
  My 330-HP attacker is Active. The opponent's dangerous form sits on their bench (so no evolution needed,
  but a promotion does), needs 3 Energy for an attack that hits me for 200, and currently holds 1 Energy.
  Energy at one per turn: it needs $3 - 1 = 2$ more turns to afford the attack. Its first hit therefore
  lands in $max(1, 0, 2) + 1 = 3$ turns. Two hits of 200 knock out 330 ($ceil(330\/200) = 2$), so the
  knockout falls on turn $3 + 2 - 1 = 4$. *Four turns of breathing room* — enough to heal, or to knock out
  its enabler first. No search, no simulation: four divisions and a maximum.
]

The Match Planner's *confidence* is built the same honest way — a plain weighted sum, not a learned model:

$ c = 0.5 + 0.12 times ("race margin") + 0.05 times ("survival window" - 1), $

clamped to $[0, 1]$. Start at a coin-flip; add for every turn I am ahead in the prize race; add for every
turn of Threat-Clock breathing room. Above a threshold (here $0.55$) the Game Plan *directs* the turn
planner; below it, the plan stays quiet and the turn planner falls back to its own goals and the tuned
weights of Part II. It is a *feasibility* number, deliberately legible: you can read straight off it *why*
the agent is confident.

#contrast("Why not search the opponent, or learn the confidence?")[
  Two tempting upgrades, both rejected on purpose. #text(weight: "bold")[Search the opponent's replies.]
  That is precisely the depth-2 escalation of §9.4 — built, measured, and *beaten* by the tuned scorer;
  branching on opponent choice through a crude reply model is worse than the honest static arithmetic.
  #text(weight: "bold")[Make confidence a learned win-probability.] We *have* such a model — the value
  model of Chapter 7 — but it estimates "am I winning *overall*," not "is *this specific route* feasible,"
  and it was parked for adding no signal over the closed form. A legible weighted sum you can audit beat
  both. This is the thesis of the whole book compressed into one design choice: when the exact computation
  is cheap and honest, prefer it to both search and learning.
]

=== Sensors and actuators: how a new layer earns its place

Here is the most important *engineering* idea in this chapter, and you already own it. Return to Chapter 1:
the agent is a *controller* — read the sensors, command the actuators. That distinction is not only a
metaphor for the agent as a whole; it is a discipline *inside* it. A component that merely *computes a
number* is a #text(style: "italic")[sensor]. A component that *changes the move* is an
#text(style: "italic")[actuator]. The two are built — and switched on — *separately*.

The Threat Clock is a *sensor*. On its own it changes *nothing*: it reads the board and produces "4
turns." A number cannot alter a decision until something *reads it into the score*. Those readers — the
goal the Match Planner hands the turn planner, and the gate that decides whether to *decline* an available
knockout — are the *actuators*. When the Match Planner was first built, the sensor came first and was wired
to *nothing but telemetry*: it computed the entire Game Plan, printed it for inspection, and provably moved
not one decision (the full test suite stayed byte-for-byte identical). Only *afterwards* were the actuators
added, each behind its own on/off switch.

#keyidea[
  Separate *sensing* from *acting*. A primitive that computes a value (a #text(weight: "bold")[sensor]) can
  be added and verified while it changes *no behaviour at all* — you check its output is sane in isolation.
  Only then do you wire an #text(weight: "bold")[actuator] that reads it into a decision, behind a switch
  you can flip off. Build the thermometer before the thermostat: install both at once and, when the room
  runs cold, you cannot tell whether the thermometer is *misreading* or the thermostat is *mis-reacting*.
]

Why go to the trouble? *Attribution.* Add a new sensor and a new actuator in one change, watch the win rate
drop, and you have two suspects and no way to separate them. Add the sensor alone, confirm the agent still
plays *identically*, and you have proven the sensor is behaviour-neutral; any later change in play must come
from the actuator you then wired — which is itself behind a switch, so you can A/B it (Chapter 10) against
its own "off." This is exactly how a careful engineer brings a new sensor into a running control loop: log
it read-only first, confirm it reads true, *then* close the loop on it. The agent's entire tier stack was
built this way — every planned or learned layer wired behaviour-neutral, verified, and only then allowed to
touch an actuator, one switch at a time. It is why "which change moved the win rate?" always has an answer.

#toolbox("Instrument first, actuate later")[
  This is a standard, hard-won pattern far beyond ML. Ship a new metric to a dashboard *before* you let it
  page anyone. Run a new fraud model in #text(weight: "bold")[shadow mode] — scoring live traffic,
  blocking nothing — until its numbers are trusted, then let it decline a transaction. Put every
  behavioural change behind a #text(weight: "bold")[feature flag] so it can be dark-launched and reverted
  in one line. In control terms: validate the observer before you close the loop. The Threat Clock spent
  its first life in shadow mode, and the switches on its actuators are feature flags. "Compute-only" is not
  a limitation — it is the safe first half of every honest deployment.
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
  [The Threat Clock. My Active has 300 HP. The opponent's only threat is a benched attacker (already its
   final form) that needs 4 Energy for an attack dealing 160 damage and currently holds 2 Energy; Energy
   arrives at one per turn. (a) In how many turns can it first attack? (b) How many hits knock out my
   300 HP? (c) On which of the opponent's turns does the knockout land? (d) Is this a *search* or a
   *computation*, and which single assumption makes it so cheap?],
  [Sensors and actuators. Classify each as a *sensor* (computes a value, changes no move) or an
   *actuator* (changes the move): (a) the Threat Clock producing "4 turns"; (b) the gate that declines a
   knockout because it would "wake the giant"; (c) a component that writes the Game Plan to a telemetry
   log. Then, in one sentence, explain why building the sensor first — wired to nothing but telemetry —
   lets you *attribute* a later change in win rate to a specific cause.],
  [Confidence. The Match Planner scores a plan's feasibility as $c = 0.5 + 0.12 m + 0.05(s - 1)$, clamped
   to $[0, 1]$, where $m$ is the race margin (turns ahead) and $s$ the survival window (Threat-Clock
   turns); it directs the turn planner only when $c >= 0.55$. Compute $c$ and state "directs" or "stays
   quiet" for (a) $m = 1, s = 4$ and (b) $m = -1, s = 1$. (c) In one sentence, why is a legible weighted
   sum preferred here over the learned value model of Chapter 7?],
))
