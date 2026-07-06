#import "preamble.typ": *

= Mistakes as Data: Learning to Rank

We have a linear model whose behaviour is entirely determined by its weights. Now we make it
*learn* — that is, we let data choose the weights. This chapter is about where that data comes from
and what shape it takes. The answer is elegant and specific to a ranking system: our training
examples are *corrections*, and each one is a single statement of the form "at this state, that move
should have outranked this one." Turning such statements into weights is a classic ML problem called
#text(style: "italic")[learning to rank], and this chapter sets it up. Chapters 5 and 6 solve it.

== A correction is one labelled comparison

When we review a replay and spot a blunder, we record a #text(style: "italic")[correction]: at some
game state, the agent *chose* option $c$, but the *correct* option was $k$. That is the entire label.
It does not say how good $k$ is, or assign either move a number. It says only: $k$ should have beaten
$c$. In the language of Chapter 3, the agent does *ranking*, so the natural training signal is a
*pairwise ranking constraint*:

$ "Score"(k) > "Score"(c) quad quad ("correct should outrank chosen"). $

This is a form of #text(style: "italic")[supervised learning]: we have input–label pairs, where the
input is a pair of options at a state and the label is "left one wins." What makes it *ranking* rather
than *regression* is that the label is an *ordering*, not a target value.

#toolbox("Three ways to learn a ranking")[
  Ranking problems — search results, recommendation feeds, our move selection — come in three
  training flavours. #text(weight: "bold")[Pointwise]: predict an absolute score for each item
  (reduces to regression), then sort. #text(weight: "bold")[Pairwise]: learn from "item A should
  outrank item B" comparisons — this is us. #text(weight: "bold")[Listwise]: optimise the quality of
  the whole ordering at once. We use pairwise because it matches our data *exactly*: a human marking a
  blunder produces "$k$ beats $c$," never an absolute "this move is worth 0.72." The famous algorithms
  here — RankSVM (pairwise + hinge loss, essentially our method) and RankNet (pairwise + a neural net)
  — are the same idea at different scales.
]

== The margin: what "$k$ beats $c$" becomes

Because the score is *linear*, the requirement $"Score"(k) > "Score"(c)$ simplifies beautifully.
Subtract the two scores; every rule that fires on *both* options cancels, because it contributes the
same weight to each. Define the *feature difference* for each rule $i$:

$ Delta_i = "fired"_i (k) - "fired"_i (c) in \{ -1, 0, +1 \}. $

$Delta_i = +1$ means rule $i$ fired only on the *correct* option (so raising its weight helps the
correction); $Delta_i = -1$ means it fired only on the *chosen* option (so *lowering* it helps);
$Delta_i = 0$ means it fired on both or neither and is irrelevant to this comparison. The condition
$"Score"(k) > "Score"(c)$ becomes a single linear inequality in the weights:

$ underbrace(sum_i w_i Delta_i + Delta"tactical", "the margin" #h(0.2em) m) > 0. $

We call the left-hand side the #text(style: "italic")[margin] $m$. A correction is #text(style:
"italic")[satisfied] when $m > 0$ — the agent, with its current weights, already ranks $k$ above $c$
— and #text(style: "italic")[violated] when $m <= 0$. The margin is the single number every later
chapter pushes on: Chapter 5 measures how far it falls short, Chapter 6 nudges weights to lift it.

#example("the Ignition-energy correction as a difference vector")[
  A real cluster of corrections: the agent attached a precious *Ignition Energy* to its attacker when
  it should have attached a plain *Basic Energy* (Ignition is discarded at end of turn and is better
  saved for a different line). Two rules matter. $phi_"accel"$ = "rush energy onto the main line"
  fires on *both* attach options — so $Delta_"accel" = 0$, it cancels. $phi_"waste"$ = "this wastes a
  discard-energy" fires only on the *chosen* (Ignition) option — so if we had that rule,
  $Delta_"waste" = +1$ on the correct option's side... but note: at the time of the blunder that rule
  *did not exist*. Every rule that existed fired identically on both options, so every $Delta_i = 0$
  and the margin was stuck at $Delta"tactical" = 0$. Read the next section to see why that exact fact
  — *all deltas zero* — is a diagnosis, not a dead end.
]

== The fork in the road: reweight, or add a feature?

Before we touch a single weight, the margin tells us *what kind of fix a correction needs*. Look at
the $Delta_i$ values:

#block(inset: (left: 6pt))[
  #set text(size: 12pt)
  - #text(weight: "bold")[Some $Delta_i eq.not 0$ — route W ("weight").] The two options already
    *look different* to the existing rules. They are distinguished; we merely have the relative
    weights wrong. A change to $bold(w)$ *can* re-order them. This is a #text(style: "italic")[linear
    learning-to-rank] problem, and it is automatic and safe (Chapters 5–6).
  - #text(weight: "bold")[Every $Delta_i = 0$ — route H ("hypothesis").] The two options are
    *identical* to every rule the agent has. This is exactly the blindness of Chapter 3: identical
    features force identical positional scores, so *no reweighting can ever separate them.* The agent
    needs a brand-new feature that fires on one option and not the other. This is #text(style:
    "italic")[feature engineering], and it needs a human to invent the distinction.
]

This diagnosis is the practical payoff of everything in Chapters 2–3. A weight problem and a
missing-feature problem look identical on the surface — "the agent made a bad move" — but they have
completely different fixes, and the margin's $Delta$ vector tells them apart mechanically. Confusing
the two is the most common way to waste effort in a system like this: you can tune weights forever and
never fix a route-H blunder, because the model is *blind*, not *miscalibrated*.

#contrast("Two other signals we could learn from — and why corrections are the gold")[
  Corrections are not the only possible training data. #text(weight: "bold")[Winner-imitation]: mine
  strong replays and label the *winner's* move as "correct." Cheap and plentiful, but *silver* — the
  winner made bad moves too, and won anyway; the signal is noisy. #text(weight: "bold")[Raw win/loss]:
  let the final result train the weights directly. This is the reinforcement-learning instinct, and we
  reject it as a *weight optimiser* for the reason in Chapter 1 — one noisy bit per roughly 40 decisions is
  far too little to tune many weights, and it cannot tell you *which* of those 40 moves was the bad
  one. A hand-marked correction is *gold*: it pins the blame on one specific decision and states the
  better move, carrying vastly more information per example. We *use* all three (imitation for broad
  coverage, corrections for precision), but corrections are what make the agent sharp. Win/loss is
  kept for what it alone can do — being the final *judge* (Chapter 10), never the optimiser.
]

== Multi-pick corrections (a wrinkle worth seeing)

Some choices ask for a *set* — "discard two cards," "grab two Pokémon." A correction then compares two
*sets*, and diffing them naively can produce a phantom: if the human picked $\{0, 2\}$ and the agent
picked $\{0, 1\}$, blindly comparing position-by-position makes the shared "0" cancel into an
*empty* difference — a constraint no weight could ever satisfy, because it says nothing. The fix is to
diff on the #text(style: "italic")[set difference]: $k$ is the first item the human chose that the
agent did not (here, card 2), and $c$ is the first the agent chose that the human did not (card 1).
This keeps every correction a *meaningful* inequality. The lesson generalises: when you turn
human judgements into training labels, watch for labels that are vacuously true — they teach nothing
and quietly corrupt your sense of what is "already satisfied."

#problems("4", (
  [At a state, on the *correct* option $k$ the rules with indices $\{1, 3\}$ fire; on the *chosen*
   option $c$ the rules with indices $\{1, 2\}$ fire. Rules are numbered 1–4. Write the difference
   vector $bold(Delta) = (Delta_1, Delta_2, Delta_3, Delta_4)$.],
  [Using that $bold(Delta)$ and current weights $bold(w) = (10, 40, 15, 5)$ with $Delta"tactical" =
   0$, compute the margin $m = sum_i w_i Delta_i$. Is the correction satisfied or violated?],
  [The correction in problem 2 is violated. Name *two different* single-weight changes that would each
   satisfy it (state the weight, the direction, and the smallest integer change that makes $m > 0$).],
  [Attribution. In problem 1 the deltas were $(0, -1, +1, 0)$ — not all zero. Is this a route-W or a
   route-H fix? Now suppose instead that on both $k$ and $c$ the firing rule sets are *identical*,
   $\{1, 2\}$ on each. Compute $bold(Delta)$, the positional part of the margin, and state which route
   applies and *why no weight change can help.*],
  [A multi-pick discard: the human discarded cards $\{A, C\}$; the agent discarded $\{A, B\}$. Give
   the single $k$ and $c$ the set-difference rule extracts. Explain in one sentence what goes wrong if
   you instead diff "first pick vs first pick" ($A$ vs $A$).],
  [Conceptual. You have 500 win/loss results and 40 hand-marked corrections. You want to tune 25 rule
   weights. Argue in three sentences why the 40 corrections are the more useful training set for that
   job, referring to information-per-example and credit assignment.],
))
