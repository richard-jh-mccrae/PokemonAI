#import "preamble.typ": *

= What We Built, and Why It Barely Looks Like "AI"

Before a single equation, we need a clear picture of the *machine*. This chapter gives you the map:
what the agent is, the one loop it runs forever, and — most importantly for your ML education — where
it sits on the spectrum between "a pile of hand-written rules" and "a giant learned black box." The
punchline is that it sits deliberately, and defensibly, near the hand-written end. Understanding *why*
is your first ML lesson.

== A game is a sequence of decisions under uncertainty

Strip away the Pokémon theme and the agent's world is simple. A native game engine runs the match. At
every choice point it hands the agent a *list of legal options* — play this card, attach this energy,
retreat, attack — and asks: which one? The agent answers, the engine advances the state, and the
question comes again, a few dozen times per game, until someone wins.

That is the entire job: a function from *state* to *chosen option*, called over and over. In the
literature this function is a #text(style: "italic")[policy]. In your world it is a *controller*: read
the sensors (the board state), pick an actuator command (the move), repeat. The Pokémon agent is a
controller for a turn-based system, and almost everything in this book is about how that controller
decides, and how it gets *better* at deciding.

#toolbox("The policy/controller equivalence")[
  A "policy" $pi("state") arrow.r "action"$ in machine learning is exactly a control law
  $u = k(x)$ in control theory. Reinforcement learning is, quite literally, adaptive optimal control
  rediscovered by a different community. If you are comfortable with a PID loop reading error and
  emitting a command, you already have the right mental model for an agent reading a board and
  emitting a move — the differences are the *state space* (huge, discrete) and how the law is *found*
  (from data, not pole-placement).
]

== The one loop the agent runs

Every decision is made the same way. The engine offers options $o_1, o_2, dots, o_n$. The agent
assigns each one a numeric #text(style: "italic")[score] and plays the highest — an $argmax$:

$ "chosen" = argmax_(o in "options") "Score"(o). $

The whole intellectual content of the agent is hidden inside that innocent word $"Score"$. Chapters 2
and 3 build it up properly; for now, know its shape. The score is a sum of two pieces:

$ "Score"(o) = underbrace(sum_i w_i dot "fired"_i (o), "positional — the rules") + underbrace("tactical"(o), "combat math"). $

The left piece adds up the *weights* $w_i$ of every hand-authored rule that "fires" on option $o$
(a rule that says, say, *prefer accelerating energy during setup*). The right piece is fixed combat
arithmetic (a knockout is worth a lot; three damage is worth a little). The left piece is the part we
*learn*. Hold that thought — it is the spine of Part II.

#example("one decision, scored")[
  It is your setup turn. Two options on the menu: (A) attach an Energy to your attacker, (B) retreat
  your attacker to the bench. Suppose two rules fire on (A) — "develop your win condition"
  ($w = 25$) and "use energy acceleration" ($w = 20$) — and none fire on (B). Neither move deals
  damage this turn, so $"tactical" = 0$ for both. Then $"Score"(A) = 45$, $"Score"(B) = 0$, and the
  agent attaches. Change the weights and you change the behaviour. *That is the entire learning
  problem in one sentence.*
]

== The spectrum: from hard-coded rules to a learned black box

Every decision-making system lives somewhere on a line:

#align(center, block(inset: 8pt)[
  #text(style: "italic")[hand-written rules] #h(0.6em) $arrow.l.r.long$ #h(0.6em)
  #text(weight: "bold", fill: accent)[our agent] #h(0.6em) $arrow.l.r.long$ #h(0.6em)
  #text(style: "italic")[end-to-end learned policy]
])

At the far left, a pure `if/else` expert system: totally legible, totally brittle, and incapable of
improving from experience — every new situation needs a human to add a branch. At the far right, a
deep network trained end-to-end (think of a chess or Go engine that learned entirely from self-play):
capable of superhuman play, but data-hungry, compute-hungry, and opaque — it cannot *tell you why* it
moved.

Our agent is a hybrid pinned much closer to the left. The backbone is hand-authored rules, but their
*weights are learned from data*, and a couple of thin, well-contained learned components refine
judgement at the edges. We get most of the legibility of the rule system and a real, measurable
learning loop, without paying the black box's costs. The rest of this book is essentially an
extended justification of that position — and a tour of the mathematics that makes each piece work.

#contrast("Why not train one big network end-to-end?")[
  It is the obvious modern move, and we rejected it on purpose. Three reasons, each of which will
  recur: #text(weight: "bold")[(1) Signal.] The only ground-truth reward is win/loss — *one noisy
  bit per roughly forty decisions.* That is far too little information to train millions of
  parameters; the network would spend enormous data just to discover things we can write down for
  free. #text(weight: "bold")[(2) Legibility.] This is a *Strategy* competition: the deliverable is
  an explainable decision-making approach. A black box that cannot justify a move fails the brief
  even if it wins. #text(weight: "bold")[(3) The grader.] It runs offline, CPU-only, with a frozen
  set of libraries and about ten minutes per match. A heavyweight learned runtime is simply not
  admissible. We will meet each of these constraints again as *design forces*, not footnotes.
]

== The constraints are the curriculum

Notice that none of those three reasons is "deep learning is bad." Deep learning is spectacular when
its preconditions hold: oceans of data, cheap compute, and a tolerance for opacity. Here *none* of
them holds, so the engineering answer changes. This is the single most valuable habit this book can
give you: *match the method to the constraints.* A senior ML engineer is not someone who reaches for
the biggest model — it is someone who can look at data volume, compute budget, latency, and
explainability requirements and say "logistic regression is correct here" with the same confidence
you would say "a lookup table is correct here."

Those constraints — offline, CPU-only, dependency-frozen, ten-minute budget, must-be-legible — will
feel like home. They are embedded constraints wearing an ML costume: no heap to spare, no floating
network, deterministic enough to certify, small enough to fit. Every chapter that follows was shaped
by them.

== The road ahead

The agent is organised as a stack of *tiers*, each falling back to the one below it if it has nothing
to say. You do not need the details yet, but the shape previews the book:

#block(inset: (left: 6pt))[
  #set text(size: 12pt)
  - #text(weight: "bold")[Tier 0 — Rules & tuned scoring.] The linear model of §1.2 and its learned
    weights. *Chapters 2–6.*
  - #text(weight: "bold")[Tiers 1–2 — Planning & chance.] Looking ahead a turn, and pricing risky
    moves by exact expected value. *Chapters 8–9.*
  - #text(weight: "bold")[Tiers 3–4 — Objectives & the opponent.] Turning "who is winning the prize
    race" into arithmetic. *Touched in Chapters 8–10.*
  - #text(weight: "bold")[Tier 5 — The value model.] One small logistic-regression "am I winning?"
    estimator. *Chapter 7.*
  - #text(weight: "bold")[Tier 6 — Escalation search.] A narrow, bounded look-ahead for the hardest
    ties. *Chapter 9.*
  - #text(weight: "bold")[The Match Planner.] The newest layer, sitting *on top*: it turns the Tier-3
    objectives into a turn-by-turn *game plan* for the whole match — by pure arithmetic, not search.
    *Chapter 9.*
]

Everything rests on Tier 0, and Tier 0 rests on a single idea — turning a messy game state into a
list of numbers a linear model can score. That is Chapter 2.

#problems("1", (
  [In your own words (two sentences), state the difference between a *policy* and the *score
   function* it uses. Which one does the $argmax$ operate on?],
  [An average match lasts about 40 decisions and ends in a single win or loss. Treating that
   win/loss as one *bit* of feedback, how many decisions share the credit or blame for that one bit?
   Contrast this with a hand-marked "correction" that labels *one specific decision* as wrong: how
   many decisions' worth of feedback does the correction carry? What does this ratio suggest about
   which signal is better for tuning many rule weights?],
  [Using the scoring shape $"Score"(o) = sum_i w_i "fired"_i (o) + "tactical"(o)$, compute the scores
   for options (A) and (B), and give the $argmax$: on (A) the rules with weights $\{30, 15, 5\}$ fire
   and $"tactical" = 0$; on (B) the rules with weights $\{20, 20\}$ fire and $"tactical" = 5$.],
  [The chapter lists three reasons we did not train one end-to-end network: *signal*, *legibility*,
   *grader constraints*. For each, name one *embedded-systems* project constraint that is analogous
   (for instance, "no floating-point unit on the MCU"). One sentence each.],
  [Suppose a competitor's agent is a pure `if/else` expert system with no weights. Give one situation
   it will handle *better* than our weighted agent, and one it will handle *worse*. What single
   capability does ours have that theirs structurally cannot?],
))
