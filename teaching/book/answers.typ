#import "preamble.typ": *

#heading(level: 1, numbering: none)[Answer Key]

Worked solutions to the chapter problems and the final examination. Where a problem asks for judgement,
a model answer is given — yours may differ in wording and still be right. Numerical answers are rounded.

#let sech(s) = block(above: 1.0em, below: 0.3em, breakable: false)[
  #text(font: "New Computer Modern Sans", size: 13pt, fill: accent, weight: "bold")[#s]
]

#sech("Chapter 1 — The system at a glance")
#ans("1.1")[A *policy* is the whole function mapping a state to a chosen action; the *score function*
assigns a number to each individual option. The $argmax$ operates on the score function, ranging over
the options, and returns the highest-scoring one — the policy's output.]
#ans("1.2")[The 40 decisions *share* one bit, so each carries about $1\/40$ of a bit. A correction
targets *one* decision, so it is roughly $40 times$ denser per decision — and it also says *which* move
was wrong (credit assignment), which win/loss cannot. Hence corrections are the better signal for
tuning many rule weights.]
#ans("1.3")[$"Score"(A) = 30 + 15 + 5 + 0 = 50$; $"Score"(B) = 20 + 20 + 5 = 45$. $argmax = A$.]
#ans("1.4")[Model answers: *signal* ↔ sparse sensor data / little test coverage to learn from;
*legibility* ↔ certifiable, auditable code (e.g. DO-178C) where a black box is unacceptable;
*grader constraints* ↔ no FPU, fixed RAM, no dynamic allocation on the target MCU.]
#ans("1.5")[Better: an explicitly anticipated edge case, hand-coded, is handled exactly. Worse: an
*unanticipated* situation with no branch — it cannot weigh competing soft factors. Structural
capability ours has: it can *learn/generalise from data* (adjust weights); the pure `if/else` cannot
improve without a human editing code.]

#sech("Chapter 2 — Features")
#ans("2.1")[$bold(phi)(P) = (1, 1, 0)$; $bold(phi)(Q) = (0, 1, 1)$.]
#ans("2.2")[$bold(w) dot bold(phi)(P) = 1000 + 15 + 0 = 1015$; $bold(w) dot bold(phi)(Q) = 0 + 15 - 30
= -15$. $argmax = P$.]
#ans("2.3")[Control $= (0, 1, 0)$. The single number "archetype $= 1$" imposes a false *ordering and
magnitude* — it implies control lies between aggro and spread, and is "twice" aggro — but the
categories are unordered labels, so one-hot is required.]
#ans("2.4")[Mean $mu = (60 + 120 + 210 + 90)\/4 = 120$. Deviations $-60, 0, 90, -30$; squares
$3600, 0, 8100, 900$ sum $12600$; variance $12600\/4 = 3150$; $s = sqrt(3150) approx 56.12$.
Standardised $210$: $(210 - 120)\/56.12 approx +1.60$.]
#ans("2.5")[$2^12 = 4096$ possible vectors. Learning *one weight per feature* (12 numbers) needs data
on the order of the number of features; learning *a value per distinct situation* would need to observe
up to thousands of them. Features *generalise* across unseen combinations — the core reason to model
with features, not lookup.]

#sech("Chapter 3 — The linear model")
#ans("3.1")[$"Score"(A) = 25 + 10 + 0 = 35$; $"Score"(B) = 0 + 10 + 40 = 50$. $argmax = B$.]
#ans("3.2")[The shared $phi_2$ cancels. Need $w_1 + 10 > 50$, i.e. $w_1 > 40$; currently $25$, so raise
by more than $15$ — smallest integer $+16$ (to $41$, giving $51 > 50$).]
#ans("3.3")[Example: "attach Ignition to the attacker" vs "attach a Basic to the attacker" both fire
only `accel-into-main`, so both have the same $bold(phi)$. Any $bold(w)$ gives them the *same*
$bold(w) dot bold(phi)$, so the $argmax$ cannot separate them. You must *add a feature* (e.g. one that
fires on wasting a discard-energy) — route H.]
#ans("3.4")[New scores $112, 120, 107$ → $argmax$ is still the middle option (B). Unchanged: adding a
constant to every option leaves the $argmax$ invariant — only *differences* matter.]
#ans("3.5")[$"Score"(K) = 1000$, $"Score"(D) = 95$ → K is chosen. The combat term dwarfs the learned
positional weights, so it acts as a *hard override*: the learned layer only decides among options of
comparable tactical value.]
#ans("3.6")[Instruction: "keep your attacker Active during setup" is *strong doctrine* ($35$), and
"prefer a cheap retreat" is a *mild preference* ($12$). When both fire on opposite options,
hold-position ($35$) dominates, so the agent stays put.]

#sech("Chapter 4 — Learning to rank")
#ans("4.1")[$bold(Delta) = (0, -1, +1, 0)$ (rule 1 fires on both → 0; rule 2 only on chosen → $-1$;
rule 3 only on correct → $+1$; rule 4 on neither → 0).]
#ans("4.2")[$m = 10(0) + 40(-1) + 15(+1) + 5(0) = -25$. Violated ($m <= 0$).]
#ans("4.3")[Raise $w_3$ by at least $26$ (to $41$): $m = -40 + 41 = +1 > 0$. Or lower $w_2$ by at least
$26$ (to $14$): $m = -14 + 15 = +1 > 0$.]
#ans("4.4")[$(0, -1, +1, 0)$ is not all-zero → *route W*. If both fire $\{1, 2\}$ then
$bold(Delta) = (0, 0, 0, 0)$ and the positional margin is $0$ → *route H*: the options are identical
to every rule, so no weight change can separate them; a new feature is required.]
#ans("4.5")[$k = C$ (first the human chose that the agent did not); $c = B$ (first the agent chose that
the human did not). Diffing $A$ vs $A$ gives an empty difference — a vacuous "$0 > 0$" constraint that
teaches nothing and can never be satisfied.]
#ans("4.6")[Each correction carries roughly $40 times$ the information per decision and *localises the blame*
to a specific move; 500 win/loss bits are sparse and cannot say *which* of 25 weights is wrong. So the
40 corrections are far more useful for tuning 25 weights.]

#sech("Chapter 5 — Loss functions")
#ans("5.1")[$m = 5 → 0$; $m = 1 → 0$; $m = 0 → 1$; $m = -4 → 5$. The $m = 5$ case contributes $0$ — it
is satisfied beyond the margin $tau$, so training ignores it.]
#ans("5.2")[Losses $0, 0.75, 2, 4$; total $6.75$. The $m = -3$ correction contributes most ($4$),
a fraction $4\/6.75 approx 0.59$ (59%).]
#ans("5.3")[Zero–one counts $2$ violated ($m = -1, -3$). The $m = 0.25$ case: zero–one calls it
satisfied, hinge charges $0.75$ (it is inside the margin). Hinge's treatment is more useful — it still
nudges the barely-satisfied case off the knife-edge toward robustness.]
#ans("5.4")[Hinge$(50) = max(0, 1 - 50) = 0$ — it leaves the already-correct ordering alone. Squared
loss to a target of $1$ would report $(50-1)^2 = 2401$ and wastefully try to *shrink* the margin.
Hinge's flat region is exactly the right behaviour for a ranking task.]
#ans("5.5")[Non-zero hinge iff $m < 1$: the margins $0.9$ (loss $0.1$), $-0.5$ (loss $1.5$), and $-2$
(loss $3$). These three are the support vectors. A non-support correction is satisfied with room and
could be deleted without changing the fit.]
#ans("5.6")[Log-loss (cross-entropy): you need a *calibrated probability* to threshold at $0.5$, and
the hinge loss produces only a ranking score, not a probability.]

#sech("Chapter 6 — Fitting the weights")
#ans("6.1")[Step 1: $20 + 1(+1) = 21$. Step 2: $21 - 1 dot 0.2 (21 - 20) = 21 - 0.2 = 20.8$.]
#ans("6.2")[At equilibrium the net change is zero: $p - lambda(w^* - w^"seed") = 0$ (with $eta = 1$),
so $w^* = w^"seed" + p\/lambda$.]
#ans("6.3")[$w^* = 30 + 5\/0.1 = 80$; with $lambda = 0.5$, $w^* = 30 + 5\/0.5 = 40$. Larger $lambda$
holds the weight nearer its seed — $lambda$ is the conservatism/shrinkage knob.]
#ans("6.4")[Hinge: $m_1 = 2 → 0$, $m_2 = -1 → max(0, 1-(-1)) = 2$. Regulariser:
$(0.5\/2)[(32-30)^2 + (18-20)^2] = 0.25(4 + 4) = 2$. $J = 0 + 2 + 2 = 4$.]
#ans("6.5")[The $+1$ and $-1$ pushes cancel each sweep, so $w$ stays at $10$ forever. The two
corrections are *contradictory* — no single weight makes both margins positive — so $J > 0$ always.
The pocket returns the best-$J$ iterate seen (here $w = 10$ throughout).]
#ans("6.6")[Choose *L1* (lasso): it drives the roughly 185 useless weights *exactly to zero*, so the
surviving non-zero weights *are* the roughly 15 that matter. L2 would only shrink all 185 toward zero without
zeroing them, so it would not select.]
#ans("6.7")[Update $w arrow.l w(1 - 2eta)$. $eta = 0.1$: $w = 0.8$ (converges toward 0). $eta = 1.0$:
$1 → -1 → +1$ (bounces between $plus.minus 1$). $eta = 1.5$: $1 → -2$ ($|{-2}| > 1$, diverges).
Lesson: too small is slow, moderate converges, too large oscillates or blows up — there is a stability
ceiling on $eta$.]

#sech("Chapter 7 — The value model")
#ans("7.1")[$sigma(0) = 0.5$; $sigma(2) = 1\/(1 + 0.1353) approx 0.881$; $sigma(-2) = 1\/(1 + 7.389)
approx 0.119$. And $sigma(-2) = 1 - sigma(2)$ because $sigma(-z) = 1 - sigma(z)$ — the S-curve is
symmetric about $(0, 0.5)$.]
#ans("7.2")[$z = 0.44(1.5) + (-0.27)(1.0) = 0.66 - 0.27 = 0.39$; $sigma(0.39) = 1\/(1 + 0.677) approx
0.596$.]
#ans("7.3")[$-ln(0.596) approx 0.517$; the careless $p = 0.05$ gives $-ln(0.05) approx 2.996$ — about
$5.8 times$ the penalty. Confident-and-wrong is punished far harder than honest uncertainty.]
#ans("7.4")[If $y = 1$: $-ln 0.5 = 0.693$; if $y = 0$: $-ln(1 - 0.5) = 0.693$ — always $0.693$.
Beating $0.693$ on held-out data means the model's confident-correct calls outweigh its
confident-wrong ones — genuine predictive signal beyond guessing.]
#ans("7.5")[Model A: $-ln(1 - 0.5) = 0.693$; Model B: $-ln(1 - 0.9) = -ln 0.1 = 2.303$. B is punished
much more. Log-loss is instilling *calibration* — do not be confidently wrong.]
#ans("7.6")[A larger opponent bench *lowers* our predicted win-probability (negative weight). Per
standardised unit it multiplies the *odds* of winning by $e^(-0.47) approx 0.625$ — about a 37.5% cut.]
#ans("7.7")[About $2000 times 40 = 80{,}000$ labelled rows. One row per match gives only 2000 noisy
bits; the state-level view yields 80k labelled states, so averaging over them turns the noisy
per-match bit into a smooth, calibrated per-state probability.]

#sech("Chapter 8 — Probability & expected value")
#ans("8.1")[$binom(6,2) = 15$; $binom(10,3) = 120$; $binom(18,2) = 153$.]
#ans("8.2")[$H = 8 + 4 = 12$; $binom(4,2)\/binom(12,2) = 6\/66 approx 0.091$; so
$P approx 1 - 0.091 = 0.909$.]
#ans("8.3")[(a) $u = 0 → 0$ (every copy already seen elsewhere). (b) $u = 5 > K = 3 → 1$ (pigeonhole:
five copies cannot all fit in three prize slots). (c) $K = 0 → 1$ (no hidden prizes, so every unseen
copy is in the deck).]
#ans("8.4")[$1 - 12376\/38760 = 1 - 0.319 approx 0.681$.]
#ans("8.5")[Binomial: $1 - 0.85^6 = 1 - 0.377 = 0.623$. The exact hypergeometric ($0.681$) is
*higher*: without replacement, each non-target drawn enriches the remaining pool with targets, raising
the hit chance.]
#ans("8.6")[EV $= 0.5(150) + 0.5(20) = 85 > 80$ → take the gamble.]
#ans("8.7")[Decline when $180p < 90$, i.e. $p < 0.5$ (break-even $180p = 90 ⟹ p = 0.5$). It is the
right rule because it compares *payoff $times$ probability* to the safe value; with a larger payoff the
break-even $p$ drops below $0.5$ (e.g. a $300$ payoff breaks even at $p = 0.3$), so the decision turns
on EV, not on a fixed 50% threshold.]

#sech("Chapter 9 — Search")
#ans("9.1")[Value of L $= min(6, 1) = 1$; value of R $= min(4, 3) = 3$; root $= max(1, 3) = 3$; best
move R.]
#ans("9.2")[$b^d = 8^4 = 4096$ leaves; general formula $b^d$. It grows *exponentially*, so even modest
$b$ and $d$ exceed any time/compute budget — you cannot search to the end.]
#ans("9.3")[Coin EV $= 0.5(16) + 0.5(0) = 8 > 7$ → take the coin. Indifferent when $16p = 7$, i.e.
$p = 7\/16 approx 0.4375$.]
#ans("9.4")[Higher EV is right when the bet can be *repeated* or variance is tolerable. But when
*ahead late*, a loss is catastrophic and an extra win is unnecessary, so a risk-averse agent takes the
safe $7$. EV alone ignores *variance* and *stakes* — it is not the sole decision rule.]
#ans("9.5")[A *missed* win merely means you keep playing — bounded cost. A *falsely claimed* win makes
you commit to a line that does not actually win, and you may lose. Soundness is a worst-case guarantee:
under-claiming is safe, over-claiming (an optimistic evaluation) can be fatal.]
#ans("9.6")[(a) *search* — exact, provable, per-decision. (b) *learning* — a fast learned/heuristic
evaluation of a fuzzy board. (c) *neither* — an exact closed-form (hypergeometric) computation.]

#sech("Chapter 10 — Evaluation")
#ans("10.1")[(a) Interval entirely above 50% → improvement. (b) Interval straddles 50% → no
distinguishable effect. (c) Interval entirely below 50% → regression.]
#ans("10.2")[$"SE" = sqrt(0.52 dot 0.48 \/ 2500) = sqrt(0.0000998) approx 0.0100$; half-width
$1.96 times 0.0100 approx 0.0196 approx 2.0%$. Interval $approx [50.0%, 54.0%]$ — it *just* clears 50%.]
#ans("10.3")[Since $"width" prop 1\/sqrt(N)$, halving width needs $4times$ the games; $2% → 0.5%$ is a
$4times$ shrink, hence $16times$ the games — about $2500 times 16 = 40{,}000$.]
#ans("10.4")[A single "$61%$" mixes the fixed 60% deck matchup with your change, so it cannot isolate
the change from noise. The *paired* A/B measures $"winrate"("on") - "winrate"("off")$ against the same
opponent, cancelling the matchup and leaving only the change's effect.]
#ans("10.5")[Risk: overfitting to the 40 corrections, which may worsen general play while the count
rises — *Goodhart's Law*. Demand: a *held-out* set the model never trained on, and an *independent*
ladder A/B on fresh games.]
#ans("10.6")[The point estimate is negative ($-0.55%$), so the best guess is that it hurts slightly;
the interval sits almost entirely below 0 (upper end only $+0.16%$), so there is no credible gain; and
since the layer is capped and degrade-safe, parking it costs nothing. A change must *beat* the baseline
to ship — this one does not — so parking-with-evidence is correct.]

#sech("Chapter 11 — Road not taken")
#ans("11.1")[(a) Deep neural network — abundant data, features unknown (pixels). (b) Gradient-boosted
trees — tabular, dependency available, and legible-enough with feature importances for the regulator.
(c) Reinforcement learning — cheap fast simulator, dense-enough reward from many episodes. (d) Exact
hypergeometric computation — the structure is known, so no learning is needed.]
#ans("11.2")[Dominant questions: *data* (only 500 examples) and *runtime* (32 KB, no FPU). These rule
out deep nets and anything needing floating-point-heavy inference or a big model. Recommend a small,
integer-friendly linear/logistic model or a tiny decision tree with hand-features — legible and cheap.]
#ans("11.3")[High *variance* (fits the training corrections, fails to generalise). Remedies: stronger
regularisation (moves toward higher bias / lower variance), and more/broader training data (lowers
variance without adding bias). Simplifying the model also reduces variance.]
#ans("11.4")[Model answer: revisit (i) the linear value model — a GBDT or neural net now becomes
viable and could raise the ceiling; (ii) the hand-features — a learned encoder could replace some.
*Keep* the exact hypergeometric deck odds regardless: an exact closed form is never worth replacing
with a data-hungry approximation. Legibility may still constrain the choice.]
#ans("11.5")[Model answer: e.g. lottery/poker odds, queueing delays (Little's law), or error-bar
propagation — all have exact closed forms. Using Monte Carlo instead spends compute to obtain a *noisy
estimate* of a number you could have computed *exactly*.]

#sech("Chapter 12 — Improving the system")
#ans("12.1")[Model answer: *more and better corrections.* In a data-poor regime each correction is a
dense, credit-assigned training label (Chapter 4), so better labels beat fancier models — the highest
leverage per unit effort.]
#ans("12.2")[The general model's features were *redundant* with the closed-form leaf, so it added no
new signal. Conditioning on the matchup gives it *novel* signal — "this board favours us *against that
deck*" — which the closed-form judgement does not already encode.]
#ans("12.3")[Model answer: (1) *bin* states by predicted probability (e.g. all predictions near 0.7);
(2) within each bin compute the *actual* win fraction; (3) plot predicted (x) vs actual (y). A
well-calibrated model lies on the diagonal $y = x$ — of the states it called 70%, about 70% were won.]
#ans("12.4")[Open — a good plan names a concrete build, the chapter idea it exercises, and an
*automatic feedback loop* (e.g. "compare my hypergeometric output to a 10,000-trial simulation and
assert they agree to within sampling error").]

#pagebreak()
#sech("Final Examination — solutions")
#ans("E1")[$"Score"(X) = 40 + (-20) = 20$; $"Score"(Y) = 10$. $argmax = X$.]
#ans("E2")[$bold(Delta) = (-1, +1, 0)$ (rule 1 only on chosen; rule 2 only on correct; rule 3 on both).
Not all zero → *route W*.]
#ans("E3")[$m = 20(-1) + 15(+1) + 30(0) = -5$; violated. Fix: raise $w_2$ by at least $6$ (to $21$):
$m = -20 + 21 = +1$. (Equivalently lower $w_1$ by at least $6$.)]
#ans("E4")[Hinge: $m = 3 → 0$; $m = -2 → 3$; $m = 0.5 → 0.5$; total $3.5$.]
#ans("E5")[$25 + 1 = 26$, then $26 - 0.2(26 - 25) = 25.8$.]
#ans("E6")[$w^* = 20 + 4\/0.2 = 40$. Raising $lambda$ moves the resting point *back toward the seed*
($20$) — the pull-back is stronger.]
#ans("E7")[$sigma(1) = 1\/(1 + 0.368) approx 0.731$. It is the model's estimated *probability of
winning* from that state.]
#ans("E8")[Win: $-ln 0.8 approx 0.223$. Loss: $-ln 0.2 approx 1.609$. The confident-but-wrong case
(loss) is punished roughly $7 times$ harder — this drives *calibration*, discouraging overconfidence.]
#ans("E9")[Whatever the outcome, the model contributes $-ln 0.5 = 0.693$, so its average is exactly
$0.693$. Scoring *below* $0.693$ on held-out data proves the model carries real predictive signal.]
#ans("E10")[$binom(7,3) = 7! \/ (3! dot 4!) = 5040\/(6 dot 24) = 35$.]
#ans("E11")[$H = 6 + 6 = 12$; $binom(6,1)\/binom(12,1) = 6\/12 = 0.5$; $P = 1 - 0.5 = 0.5$.]
#ans("E12")[EV $= 0.3(200) + 0.7(50) = 60 + 35 = 95 > 90$ → take the gamble.]
#ans("E13")[L $= min(2, 8) = 2$; R $= min(5, 4) = 4$; root $= max(2, 4) = 4$; best move R.]
#ans("E14")[$6^3 = 216$ leaves. The count is $b^d$ — *exponential* in depth — so full-depth search
quickly exceeds any budget.]
#ans("E15")[Coin $= 0.5(12) + 0.5(0) = 6$, equal to the safe $6$ — indifferent on EV. A risk-averse
agent that is already winning takes the *safe* $6$, because the coin's downside ($0$) risks a loss it
does not need to take (variance matters near the finish).]
#ans("E16")[$"SE" = sqrt(0.55 dot 0.45\/100) = sqrt(0.002475) approx 0.0498$; half-width
$1.96 times 0.0498 approx 9.8%$. Interval $approx [45%, 65%]$ straddles 50%, so *no* — with only 100
games the noise swamps the effect; not a demonstrated improvement.]
#ans("E17")[Width $prop 1\/sqrt(N)$, so a $4times$ width reduction needs $4^2 = 16 times$ the games.]
#ans("E18")[*L1* (lasso): it drives the roughly 280 useless weights *exactly to zero*, so the surviving
non-zero weights identify the roughly 20 that matter.]
#ans("E19")[Identical firing sets mean identical feature vectors $bold(phi)$, so $bold(w) dot bold(phi)$
is identical for *every* $bold(w)$ — the two options always tie in the positional score, and $argmax$
cannot separate them. You must engineer a *new feature* that fires on one option but not the other
(route H).]
#ans("E20")[A *legible rules/linear model* tuned by the few hand-labels, with exact computation where
structure is known. Compass drivers: little *data*, CPU-only/no-library *runtime*, and required
*legibility* (also: known *structure*). Avoid an *end-to-end deep net or RL policy* — data-hungry,
opaque, and starved by the sparse reward.]
