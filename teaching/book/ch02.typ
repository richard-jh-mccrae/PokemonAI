#import "preamble.typ": *

= From Board to Numbers: Features

A linear model cannot look at a Pokémon board. It can only add up numbers. So the first real task in
any machine-learning system is *representation*: how do we turn a rich, messy situation into a short
list of numbers that captures what matters? That list is called a #text(style: "italic")[feature
vector], and choosing it well is called #text(style: "italic")[feature engineering]. This chapter is
about that translation, because everything downstream — scoring, learning, probability — operates on
the numbers, never on the game.

== The representation problem

Consider the option "attach an Ignition Energy to my active Cinderace." To a human that carries a
world of meaning: what Cinderace does, whether it will attack this turn, that Ignition is discarded at
end of turn and is therefore precious. A linear model sees none of that. We must *hand it* the
relevant facts as numbers. Each fact we choose to expose is a #text(style: "italic")[feature]; the
vector of all of them for one option $o$ is written $bold(phi)(o)$ (the Greek letter "phi").

#defn("Feature vector")[$bold(phi)(o) = (phi_1(o), phi_2(o), dots, phi_d(o))$ is a length-$d$ list of
numbers describing option $o$. Each $phi_j$ is one measurement. In this agent most measurements are
*yes/no* facts, so most features are $0$ or $1$.]

== Binary features: the rules that "fire"

In our agent, a feature is a hand-authored rule with a trigger. The feature's value on option $o$ is
$1$ if the rule's trigger matches $o$, and $0$ otherwise — an #text(style: "italic")[indicator]. The
rule "prefer energy acceleration during setup" contributes a feature $phi_"accel"$ that equals $1$ on
any option that attaches accelerating energy during setup, and $0$ on everything else.

Because the values are $0$/$1$, the feature vector for an option is just a checklist of which rules
apply. This is a deliberate design choice: binary features are the easiest thing in the world to
reason about, to author, and — as we will see — to *learn weights for*.

#example("two options as vectors")[
  Take three rules in play: $phi_1 =$ "develop the win condition", $phi_2 =$ "use acceleration",
  $phi_3 =$ "keep position in setup". Two options:
  #block(inset: (left: 8pt), [
    #set text(size: 12pt)
    - Option A — *attach energy to the attacker*: develops ($1$), accelerates ($1$), not a
      position-hold ($0$). So $bold(phi)(A) = (1, 1, 0)$.
    - Option B — *retreat the attacker*: develops nothing ($0$), no acceleration ($0$), but it *does*
      break setup position ($0$ on the "keep position" rule, since retreating violates it).
      So $bold(phi)(B) = (0, 0, 0)$.
  ])
  Two options, two short lists of numbers. From here on the model only ever sees these lists.
]

== The dot product is the score

Now pair every feature with a #text(style: "italic")[weight] $w_j$ — a number saying how much that
fact should push a decision. Collect the weights into a vector $bold(w)$. The positional score is the
#text(style: "italic")[dot product] of weights and features:

$ "Score"_"pos"(o) = bold(w) dot bold(phi)(o) = sum_(j=1)^d w_j phi_j(o). $

Since the features are $0$/$1$, this sum just *adds up the weights of the rules that fired* — exactly
the phrasing from Chapter 1, now written as one clean operation. The dot product is the workhorse of
this entire book; nearly every model we meet is "compute a dot product, then do one more thing to it."

#toolbox("What a dot product means")[
  Geometrically, $bold(w) dot bold(phi) = norm(bold(w)) norm(bold(phi)) cos theta$, where $theta$ is
  the angle between the two vectors. It measures *alignment*: it is large and positive when
  $bold(phi)$ points the same way as $bold(w)$, zero when they are perpendicular, negative when they
  oppose. Reading the score as "how well does this option align with my learned preferences $bold(w)$?"
  is a picture that will serve you in every linear method — regression, logistic regression, SVMs, and
  the first layer of every neural network are all, at heart, a dot product.
]

== Features come in more than one flavour

Binary is the workhorse here, but you will meet three feature types everywhere in ML, and you should
know how to build each:

#block(inset: (left: 6pt))[
  #set text(size: 12pt)
  - #text(weight: "bold")[Indicator (binary):] a yes/no fact, $0$ or $1$. "A knockout is available."
  - #text(weight: "bold")[Numeric (continuous):] a count or magnitude. "Prizes remaining $= 3$",
    "damage $= 210$". Our combat term and the value model's inputs use these.
  - #text(weight: "bold")[Categorical:] a choice among $k$ unrelated labels — say the opponent's
    archetype $in$ {aggro, control, spread}. You cannot feed "archetype $= 2$" to a linear model,
    because that falsely implies control is "twice" aggro. Instead you #text(style: "italic")[one-hot
    encode] it into $k$ binary features, exactly one of which is $1$.
]

Numeric features bring a subtlety we will need in Chapter 7: if one feature ranges over $[0, 1]$ and
another over $[0, 210]$, the big one dominates the dot product for no good reason. The fix is
#text(style: "italic")[standardisation] — rescale each feature to have mean $0$ and spread $1$ by
subtracting its average $mu$ and dividing by its standard deviation $s$: $phi' = (phi - mu) \/ s$.
Binary features mostly dodge this issue, which is one more reason the agent leans on them.

== Why hand-designed features, and not learned ones?

Here is a genuine fork in the road, and the reason this chapter matters. Modern deep learning is
famous for *not* doing feature engineering: you feed a network the raw board and it *learns* its own
internal features. So why did we, by hand, decide which facts matter?

#contrast("Learned features: embeddings and raw-board encoders")[
  We seriously considered — and rejected — two learned-representation ideas. #text(weight: "bold")[Card
  embeddings ("card2vec"):] learn a vector for each card so that similar cards sit near each other, the
  way word-embeddings do for language. #text(weight: "bold")[A raw-board neural encoder:] feed the
  whole state to a network and let it invent features. Both are elegant, and both were the wrong tool
  *here*: they are data-hungry (we have a trickle of games, not millions), they demand a heavier
  runtime than the frozen, CPU-only grader allows, and they are opaque in a competition that grades
  *explainability*. Worst of all, a raw encoder would spend its scarce data *re-learning things we
  already know exactly* — like how prizes are counted. When you possess a precise model of your
  domain, encoding it as features by hand is not old-fashioned; it is *cheaper, smaller, and clearer*
  than making a network rediscover it. Deep learning earns its keep when the features are genuinely
  unknown (pixels, audio, language). Ours are not.
]

The trade is explicit. Hand features cost human insight up front and can miss patterns we did not
think to encode. Learned features cost data and compute and clarity. Given *our* constraints, the
hand trade wins — and, crucially, we can always add a feature the moment a mistake reveals we are
missing one. That "add a feature to fix a blind spot" move is the subject of Chapter 4.

#problems("2", (
  [Build the feature vectors. Rules in play: $phi_1 =$ "makes a knockout", $phi_2 =$ "develops the
   bench", $phi_3 =$ "wastes a discard-energy". Option P *knocks out and develops the bench*; option
   Q *wastes a discard-energy and develops the bench*. Write $bold(phi)(P)$ and $bold(phi)(Q)$.],
  [With weights $bold(w) = (1000, 15, -30)$ for the three rules above, compute $bold(w) dot
   bold(phi)(P)$ and $bold(w) dot bold(phi)(Q)$, and say which option wins the $argmax$.],
  [One-hot encode a categorical feature "opponent archetype" with the three possible values
   {aggro, control, spread}. Write the three-component vector for an opponent that is *control*.
   Why is the single-number encoding "archetype $= 1$" a mistake for a linear model?],
  [Standardise the numeric feature "damage." Over recent options the damage values were
   $\{60, 120, 210, 90\}$. Compute the mean $mu$. (You may use the population standard deviation
   $s = sqrt(1/n sum (x_i - mu)^2)$; compute it, then give the standardised value of the
   $210$-damage option, $(210 - mu)\/s$.)],
  [A feature vector has $d = 12$ binary features. How many *distinct* feature vectors are possible in
   principle? If in practice only 30 of those combinations ever occur in real games, what does that
   tell you about how much data you need to learn a weight per feature, versus learning a value per
   distinct situation?],
))
