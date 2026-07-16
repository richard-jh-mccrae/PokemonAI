#import "preamble.typ": *

= The Tier Stack in Full: Every Layer, Its Math, and Its Switch

The earlier chapters taught the *ideas* — features, weights, loss, probability, search — one at a
time. This chapter assembles them into the actual machine and walks it top to bottom: every tier,
every sub-tier, the exact arithmetic each one runs, a worked Pokémon example, and the *kill-switch*
that turns it on or off. Think of it as the schematic that goes with the theory: when you finish, you
will be able to point at any decision the agent makes and name the layer that made it and the equation
it used.

== The stack, and the one rule that governs it

The agent is a stack of seven numbered #text(style: "italic")[tiers], T0 through T6. The numbering is
the runtime architecture — a tier is a layer that makes an *in-match decision*. Two structural facts
hold everywhere:

#keyidea[
  *Every tier degrades to the tier below it.* If a higher tier has nothing confident to say, control
  falls through to a lower one, and *T0 catches everything*. Nothing can crash or time out; the worst
  case is always "score it with the linear model and move on."
]

Most tiers can be switched off by a single boolean *kill-switch* (a flag in the deployment profile,
`src/common/runtime.py`). The switches let us ship a new layer *dark* and turn it on only once its
own A/B test clears. There is one machine-readable map of the whole stack — which switch governs
which tier — in `src/common/tiers.py`; it is the executable twin of this chapter, and a test pins
every switch to exactly one tier so the picture can never silently drift.

A reference is always written with both its number and its name, e.g. #text(weight: "bold")[T4.2 —
Opponent Model, Posture]. Sub-tiers use a dotted number (T1.1, T1.2, …). Let us walk them.

== T0 — Rules & Tuned Scoring #text(size: 11pt, fill: poke)[· always on (structural)]

This is the backbone from Chapters 2–6 and the universal fallback. Every option $o$ on the menu gets a
scalar score,

$ "Score"(o) = sum_i w_i dot "fired"_i (o) + "tactical"(o), $

and the agent plays $argmax_o "Score"(o)$. The left sum is the *learned* part: $"fired"_i (o)$ is $1$
when hand-authored rule $i$ applies to option $o$ and $0$ otherwise, and $w_i$ is that rule's weight,
fitted from human corrections (Chapters 4–6). The right term is fixed combat arithmetic. T0 has no
kill-switch because there is nothing to fall back *to* — it *is* the floor.

#example("T0 in one line")[
  Setup turn, two options. On (A) "attach to attach the win condition" ($w=25$) and "use energy
  acceleration" ($w=20$) fire; on (B) nothing fires. Neither deals damage, so $"tactical"=0$. Then
  $"Score"(A)=45 > "Score"(B)=0$ and the agent attaches. Retune the weights and the behaviour moves —
  the whole T0 learning problem in a sentence.
]

== T1 — Turn Planner #text(size: 11pt, fill: poke)[· on]

T0 scores options *one at a time*. T1 asks a bigger question: of all the *sequences* of plays I could
make this turn, which end-of-turn board is best? It does this with a #text(style: "italic")[Goal
Ladder] — a list of goals in strict priority order. It tries the top goal; if it can achieve it, it
commits; otherwise it drops to the next. Two ideas do the heavy lifting: the *sound win rung* (which
is provably correct, never a guess) and *sequence bands* (the order in which to take plays).

#defn("Sound vs. heuristic")[A *sound* result is one the engine can verify is true — "this exact line
of play wins this turn." A *heuristic* result is a ranked guess. T1's top rung is sound; everything
below it is a ranked guess that ultimately bottoms out in T0's score.]

=== T1.1 — Win Rung (the Lethal Solver) #text(size: 11pt, fill: poke)[· on]

The crown jewel. Before doing anything clever, ask: *can I just win this turn?* A knockout happens
when the damage I can deal to the opponent's Active this turn meets or exceeds its remaining hit
points. The Solver computes a #text(style: "italic")[minimum-bound] damage — the *worst-case* total,
taking the unluckiest coin flip on every coin-based attack — and declares a knockout only when even
that floor is enough:

$ "KO is guaranteed" quad <==> quad sum_(a in "my attacks this turn") "dmg"_min (a) >= "HP"_"remaining". $

Using the *minimum* (not the average) is the whole point: a sound win must hold under the worst luck,
so we never commit to a "win" that a bad flip erases. Each candidate line is then re-simulated through
the engine to confirm it is actually legal, and only a verified line locks.

#example("a guaranteed knockout")[
  Their Active has $110$ HP left. My attacker's cheapest attack deals a flat $120$ (no coin) once I
  attach one Energy, which I have in hand. $120 >= 110$, the attach is legal, the engine confirms the
  line — T1.1 locks the win and plays it. Note it fires *before* any "develop your board" instinct:
  there is nothing to develop *for* once the game is won.
]

#contrast("Why worst-case, not expected, damage here")[
  In Chapter 8 we happily used *expected* value to price a gamble. Here we deliberately use the
  *floor*. The difference is the question being asked. "Is this a sure win *this turn*?" must be
  answered conservatively — an average that says "probably lethal" is exactly the phantom-win that
  loses games. Expected value belongs one rung lower (T2), where we are *choosing among* risky lines,
  not *certifying* a win. Switches: `lethal_family`, `lethal_verify`, `lethal_veto` (all on).
]

=== T1.2 — KO the Key Threat #text(size: 11pt, fill: poke)[· on]

No guaranteed win? Then knock out the opponent's most dangerous body — the one whose attack most
threatens *me* next turn — preferring targets that also sit on my prize path (T3.1). Switch:
`planner_key_threat`.

=== T1.3 — KO for Prizes #text(size: 11pt, fill: poke)[· on]

No single key threat dominates? Take the knockout that banks the most *prize progress*, assembling the
cheapest line that gets there (tutor an Item → evolve → attach → attack). Switch:
`enabler_item_composer`.

=== T1.4 — Stabilize-then-KO #text(size: 11pt, fill: poke)[· on (structural)]

Behind on the board? Wall up / heal / deny first, *then* set up the knockout. This rung is structural
— part of the ladder's logic, with no separate switch.

=== T1.5 — Develop #text(size: 11pt, fill: poke)[· on]

Nothing urgent? Use the turn to build: draw, fill the bench, evolve, bank energy. A small within-turn
look-ahead ("rollout") checks that the developing line is affordable. Switch: `develop_rollout`.

#toolbox("Sequence bands: the order within a turn")[
  The engine re-offers the menu after each non-ending play, so *order matters*. T1 sorts the turn's
  plays into five #text(style: "italic")[sequence bands] — the most reversible, informative actions
  first, the irreversible ones last: band 0 free development, band 1 your one Supporter, band 2 the
  blind Energy attach, band 3 a hand-shuffle, band 4 the turn-ending attack. "Attack last" is just
  *sequence band 4 goes last*. (This is a *different* ladder from the tier stack — it orders plays
  *within* a turn, not layers of the agent.)
]

== T2 — Chance & EV (Gamble Lines) #text(size: 11pt, fill: poke)[· on]

When a line involves a coin flip, price it by *exact expected value* (Chapter 8), not vibes. If an
action has outcomes $k$ with probabilities $p_k$ and board-values $V_k$, its worth is

$ "EV" = sum_k p_k dot V_k, quad "with" sum_k p_k = 1. $

T2 sits as a candidate rung *below* the sound win rung (T1.1): a gamble may be the best *heuristic*
line, but it can never override a guaranteed win.

#example("is the coin worth it?")[
  A "flip a coin: heads, KO; tails, nothing" attack against a body worth $2$ prizes. Heads ($p=0.5$)
  is worth the two-prize KO; tails ($p=0.5$) is worth $0$. $"EV" = 0.5(2) + 0.5(0) = 1$ prize of
  value. If a *guaranteed* one-prize line is also available, its certain $1$ ties the gamble's *mean*
  — and because variance is bad when you are ahead, the deterministic line wins the ranking. Switch:
  `gamble_lines`.
]

== T3 — Match Objectives #text(size: 11pt, fill: poke)[· on]

T1 optimises *this turn*; T3 supplies *match-scale intent*, recomputed every turn by pure arithmetic —
no search. Three sub-tiers, all feeding T1's targets and T0's weights.

=== T3.1 — Prize Path (and Denial) #text(size: 11pt, fill: poke)[· on]

You win by taking $6$ prizes; different knockouts are worth different prizes (a regular Pokémon $=1$,
an *ex* $=2$, a *Mega-ex* $=3$). The Prize Path is the *cheapest set of knockouts that sums to your
remaining prizes*. Formally, over the opponent's knock-out-able bodies $B$, find the subset
$S subset.eq B$ that reaches your remaining count at least cost:

$ min_(S subset.eq B) sum_(b in S) "turns"(b) quad "subject to" quad sum_(b in S) "prize"(b) >= "prizes"_"remaining", quad "prize"(b) in {1,2,3}. $

With at most six bodies a side this is a tiny subset-sum — solved exactly, every turn. The *Denial*
half runs the same math for the *opponent* and refuses to gift them a body that completes *their*
cheapest route (the "make them take 7, not 6" brake). Switches: `objectives_path`,
`prize_economy_fetch`, `snipe_prize_redundant`.

=== T3.2 — KO Race #text(size: 11pt, fill: poke)[· on]

Who wins the damage race? Turns-to-knock-out, both directions, is a ceiling division:

$ "turns to KO" = ceil("HP" / "damage per turn"). $

Compare my turns-to-KO of their wall against their turns-to-KO of my body; the smaller number is
ahead. Crucially, chip damage from *bench snipes* is credited when it lands on a race target.

#example("the 100-damage chip that wins the race — case a21472")[
  Two of my attacks over three turns total $450$ damage against a $440$-HP line — $450 >= 440$, so I
  race them out in three turns *in any order*. A separate $100$ bench-snipe onto a fragile pre-evo
  (a Riolu) lands in those *same* three turns and breaks what looked like a tie. The agent had been
  blind to this until KO-Race credited the rider; now it takes the snipe. This is why match-scale
  arithmetic, not just single-turn scoring, matters. Switch: `objectives_race`.
]

=== T3.3 — Derived Phases #text(size: 11pt, fill: poke)[· on]

From the race and path signals, label the turn: #text(style:"italic")[stabilize] when behind and
their KO is imminent, #text(style:"italic")[close] when I am $<= 2$ prizes from winning, else
setup/race. To stop the label flickering turn to turn, it uses *hysteresis* — a Schmitt trigger, from
your embedded world: enter STABILIZE only when the race deficit crosses $-1$, exit only when it climbs
back to $+1$. The label nudges weight bands; it never hard-gates a move. Switch: `objectives_phases`.

== T4 — Opponent Model #text(size: 11pt, fill: poke)[· on]

Everything above can see the board. T4 reasons about what the opponent *has not shown yet* — using a
confidence-gated belief so that a wrong guess costs almost nothing.

=== T4.1 — The Read #text(size: 11pt, fill: poke)[· on]

From revealed cards, the Scout maintains a posterior belief over which archetype the opponent is
playing, and a single confidence scalar $gamma in [0,1]$. Every prediction it makes is *scaled by
$gamma$*, so an unknown opponent ($gamma -> 0$) changes nothing — the agent plays exactly as if it had
no read at all. Concretely, a predicted (not-yet-benched) attacker is only treated as "about to
arrive" with a deploy lead of

$ "turns until it can attack" = ceil(2 / gamma), $

which is a short lead when we are confident ($gamma$ near $1$) and an unreachable one when we are not.
This is *fail-open* by construction. Switch: `posture`.

#keyidea[
  $gamma$-gating is the single most important safety idea in T4: multiply every speculative claim by
  your confidence, and a low-confidence model degrades *gracefully* to "do nothing" instead of acting
  on a bad guess. It is the probabilistic version of an embedded watchdog defaulting to a safe state.
]

=== T4.2 — Posture #text(size: 11pt, fill: poke)[· on]

Two levers derived from the Read: *favorability* (press when ahead, disrupt when behind) and
*accurate development* (respect a predicted evolving threat). Shares the `posture` switch with T4.1.

=== T4.3 — Matchup Briefs #text(size: 11pt, fill: poke)[· on]

Hand-authored counterplay per known archetype (target priorities against *this* deck), routed in when
the Read recognises the opponent. Switch: `matchup_targeting`.

=== T4.4 — Learned Matchup Weights #text(size: 11pt, fill: contrastc)[· grilled, unbuilt]

The *machine-learned* counterpart of the hand-authored Briefs, and the one runtime layer that the ML
training pipeline (next section, and the companion volume) will *add*. Instead of authoring per-matchup
target priorities by hand, learn a table of weight adjustments $delta_A [h]$ per archetype $A$ and
rule $h$, applied only when the Read is confident:

$ "effective"(h) = "base"(h) + gamma dot delta_(A^star)[h], $

where $A^star$ is the Read's top archetype. The $gamma$ factor makes it fail-open exactly like T4.1.
Design is locked; it flips on at the training pipeline's Adoption Gate. No runtime switch yet.

== T5 — Automatic Value Model #text(size: 11pt, fill: contrastc)[· built, gated off]

This is Chapter 7 made concrete: a small logistic-regression model that reads a board and returns one
number, the probability I go on to win. With standardised features $bold(z)$, weights $bold(w)$, bias
$b$, and the logistic squashing function $sigma$,

$ P("win" | "board") = sigma(bold(w) dot bold(z) + b), quad sigma(x) = 1/(1 + e^(-x)). $

T1's planner uses it to *judge leaves*: instead of scoring an end-of-turn board with the closed-form
approximation alone, add a small term proportional to how much the model likes it, $W dot (P - 0.5)$,
capped below one prize so it *refines* the ranking without ever overturning sound combat math. It
currently ships *dark* (switch `value_model` off): its first version was redundant with the
closed-form leaf, and the rebuilt version flips on only at the Adoption Gate. It is the keystone the
whole training pipeline is built to produce.

== T6 — Escalation Search #text(size: 11pt, fill: contrastc)[· built, gated off]

The closed-form tiers (T0–T3) are blind to the opponent's *reply*: two attacks can price identically
this turn yet leave very different boards after the opponent's best answer.

=== T6.1 — Two-ply search #text(size: 11pt, fill: contrastc)[· gated off]

When the top two attack options are within a small margin $epsilon$ of each other in tactical score —
a genuine tie the closed form cannot separate — spend a *bounded* look-ahead: simulate my move, then
the opponent's best reply (Chapter 9's minimax), and value the resulting board. Score a move by its
worst-case reply,

$ "value"(o) = min_("opponent replies" r) V("board after " o " then " r), $

and prefer the option whose *answered* board is best. A hard budget (`search_budget`) caps the work.
It ships off: its two-ply proxy for the opponent lost to the tuned scorer in testing, so it waits for
a better reply model. Switches: `escalation` and `search_budget > 0` (both off).

=== T6.2 — Sampled-Belief Search #text(size: 11pt, fill: contrastc)[· unbuilt (research)]

The principled upgrade path: a decision-time search that samples the opponent's hidden cards from the
T4 belief and backs the tree up with the T5 value model (the "Student of Games" shape). Not built —
a research direction, recorded so the map is complete.

== The whole stack on one page

#block(inset: (left: 2pt))[
  #set text(size: 11pt)
  #table(
    columns: (auto, 1fr, auto),
    inset: 5pt, align: (left, left, left), stroke: 0.4pt + accent.lighten(40%),
    table.header([*Tier · sub-tier*], [*The one-line math*], [*Switch · default*]),
    [T0 Rules & Tuned Scoring], [$argmax_o [sum_i w_i "fired"_i + "tactical"]$], [— · on],
    [T1.1 Win Rung (Lethal)], [$sum "dmg"_min >= "HP"$ (sound)], [`lethal_family` · on],
    [T1.2 KO Key Threat], [KO the most-threatening body], [`planner_key_threat` · on],
    [T1.3 KO for Prizes], [cheapest line to max prize gain], [`enabler_item_composer` · on],
    [T1.4 Stabilize-then-KO], [wall/heal, then set up], [structural · on],
    [T1.5 Develop], [affordable within-turn build], [`develop_rollout` · on],
    [T2 Chance & EV], [$"EV" = sum_k p_k V_k$], [`gamble_lines` · on],
    [T3.1 Prize Path], [min-cost subset-sum to prizes], [`objectives_path` · on],
    [T3.2 KO Race], [$ceil("HP" / "dmg")$, both sides], [`objectives_race` · on],
    [T3.3 Derived Phases], [Schmitt trigger on race delta], [`objectives_phases` · on],
    [T4.1 Read], [$gamma$-scaled posterior; lead $ceil(2 / gamma)$], [`posture` · on],
    [T4.2 Posture], [favorability + accurate-dev], [`posture` · on],
    [T4.3 Matchup Briefs], [authored per-archetype targets], [`matchup_targeting` · on],
    [T4.4 Learned Matchup Weights], [$"base" + gamma dot delta_(A^star)[h]$], [— · grilled, unbuilt],
    [T5 Value Model], [$sigma(bold(w) dot bold(z) + b)$], [`value_model` · gated off],
    [T6.1 Two-ply search], [$min_r V("after " o", " r)$], [`escalation` · off],
    [T6.2 Sampled-Belief Search], [sample belief + value net], [— · unbuilt],
  )
]

Everything above the value model is arithmetic you can do by hand; the two gated tiers are where
*learning* re-enters, and where the companion training volume picks up.

#problems("13", (
  [State the fallback rule of the tier stack in one sentence, and explain why T0 is the only tier with
   no kill-switch.],
  [T1.1 declares a knockout only when $sum "dmg"_min >= "HP"_"remaining"$. Their Active has $130$ HP.
   Attack X deals a flat $80$; attack Y is "flip a coin: heads $100$, tails $0$." Can the agent
   *guarantee* a knockout using X then Y this turn? Show the min-bound sum and justify the yes/no.],
  [A gamble attack is "heads: KO a $2$-prize *ex*; tails: nothing," a fair coin. Compute its EV in
   prizes. A guaranteed line takes a $1$-prize KO. Which does T2 prefer when you are *ahead*, and
   why does variance tip the decision?],
  [Opponent has, knock-out-able: a Mega-ex ($3$ prizes, $2$ turns to KO), an ex ($2$, $1$ turn), and a
   basic ($1$, $1$ turn). You need $3$ prizes. List every subset that reaches $3$ prizes and its total
   turns; give the Prize Path (the $argmin$).],
  [The Read's confidence is $gamma = 0.5$. Using deploy lead $ceil(2 / gamma)$, how many turns until a
   predicted attacker is treated as able to attack? Recompute for $gamma = 0.25$ and for
   $gamma -> 0$. In one sentence, why does this make a wrong read nearly free?],
  [T5 outputs $P("win") = sigma(bold(w) dot bold(z) + b)$. If $bold(w) dot bold(z) + b = 0$, what is
   $P$? If it $= +2$? (Use $sigma(2) approx 0.88$.) The planner adds $W(P - 0.5)$ to a leaf with
   $W = 80$: what does a $P = 0.88$ board contribute, and why is the term centred at $0.5$?],
))
