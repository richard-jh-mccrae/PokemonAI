# ML Training System — Deep Research Report (2026-07-11)

**Question:** how does this system evolve from ~95% hand-authored weighted features (tuned by
manual blunder corrections) into an ML training pipeline that is decision-by-decision context
aware, can split features for novel board states and matchups, recognizes "played perfectly but
lost", and stays competitive across deck/meta/rotation shifts with minimal manual work?

**Method:** deep-research workflow — 5 search angles, 21 primary sources fetched, 103 claims
extracted, top 25 adversarially verified (3 independent refutation votes each): 24 confirmed,
1 refuted. Findings below marked **[VERIFIED]** (survived the 3-vote gate) or **[EXTRACTED]**
(fetched with verbatim quotes from the primary source, not adversarially verified — the verify
budget covered only the top-25 claims).

---

## TL;DR — the recommended shape

The literature converges on one keystone artifact and four loops around it:

1. **Train a win-probability value network from self-play logs** (small — poker's Modicum used a
   2×64-node net on a 4-core CPU). Every other capability derives from it.
2. **Automated blunder labeling via value deltas** (Suphx's global-reward-predictor recipe, chess
   annotator style): flag decisions where P(win|action taken) drops vs the best alternative.
   Replaces manual blunder-correction rounds. "Played perfectly but lost" = a lost match with no
   negative deltas — detected automatically.
3. **Weight training via expert iteration**: planner + value net = the expert; the interpretable
   linear Hypothesis layer = the apprentice, trained against the expert's per-decision targets.
   No manual labels; the rule layer remains the runtime policy. Feature *splitting* becomes
   mechanical: matchup-conditioned weight tables, and automatic compound-feature construction
   from co-active feature pairs that correlate with apprentice-vs-expert error.
4. **League self-play with exploiter probes**, not vanilla self-play — headline winrates hide
   exploitability (ByteRL was beaten 90% by a cheap best-responder despite beating a top-10
   human), and naive single-agent self-play provably fails to converge in imperfect-info games.
5. **Evaluation = duplicate deals + matchup/position balancing + value-net variance correction
   (AIVAT) + deal stratification.** Raw gauntlet winrates are independently confirmed to
   mispredict real strength — our local lesson generalizes.

**What NOT to do (evidence-backed):** end-to-end neural policy self-play (industrial compute:
24 V100s + 5,856 CPU cores × 23 days for master-level Hearthstone; a desktop PPO pipeline
plateaued ~50–59%); hand-authored dense per-move reward shaping (statistically significantly
*worse* than sparse win/loss in a CCG); full Student-of-Games-style subgame resolving (infostate
enumeration per public state is combinatorially huge for a TCG — though "categorically unusable"
was REFUTED; sampled-belief variants remain the planner's long-term upgrade path).

---

## Verified findings

### 1. Deep Monte-Carlo self-play is the proven desktop-budget path **[VERIFIED 3-0, 3-0, 2-1]**

DouZero mastered DouDizhu — large, stochastic, imperfect-information, massive turn-varying
action space — from scratch on a single server with 4 consumer GPUs in days of training,
ranking #1 of 344 agents on the external Botzone leaderboard. Two design lessons transfer:

- **Sampled-return value estimation** (plain Monte-Carlo + deep nets + parallel actors) beat
  fancier methods. Standard policy-gradient/DQN failed on this game *specifically because of the
  turn-varying action space*.
- **Legal actions are encoded as network INPUTS, not fixed output heads.** The successor
  PerfectDou (PPO, NeurIPS 2022) kept this. Directly applicable: our engine's select options are
  already structured objects — score each (state, action) pair, don't enumerate an action head.

Sources: [DouZero, ICML 2021](https://arxiv.org/abs/2106.06135) ·
[PMLR PDF](https://proceedings.mlr.press/v139/zha21a/zha21a.pdf) ·
[PerfectDou](https://arxiv.org/abs/2203.16406)

### 2. Value-function deltas solve per-decision credit under luck **[VERIFIED 3-0, 3-0]**

Suphx (rated above 99.99% of ranked human Mahjong players on Tenhou) trains a **global reward
predictor Φ** and assigns each round the delta **Φ(x^k) − Φ(x^{k−1})** as its RL reward, instead
of raw round score or terminal result. The paper's own motivation: "a negative round score may
not necessarily mean a poor policy." This is the template for replacing manual blunder labels
with automatic value-delta annotations — both directions ("good play, bad outcome" and "bad
play, good outcome") are handled.

Caveat: Suphx's predictor trained on top-human logs; our analog is self-play logs (no human
corpus exists for this card pool).

Source: [Suphx, MSR 2020](https://arxiv.org/abs/2003.13590)

### 3. Variance is THE bottleneck; the fix is learned baselines **[VERIFIED 3-0 ×6]**

The CFR lineage's core lesson for per-decision learning in stochastic games:

- MCCFR converges slowly *because of* high variance in sampled value estimates.
- **VR-MCCFR** adds state-action baselines (policy-gradient style), stays unbiased: ~10×
  convergence speedup, ~1000× empirical variance cut. With a perfect baseline, variance is
  provably zero.
- **DREAM** scales this to neural nets with a learned history baseline, but keeps an extremely
  high-variance importance-sampling term.
- **ESCHER** removes importance sampling entirely via a learned history value function; unbiased,
  converges to approximate Nash w.h.p., regret-estimate variance 8–9 orders of magnitude below
  DREAM on benchmark games; beats DREAM/NFSP >90% head-to-head in dark chess.

Read across: *any* per-decision learning signal we build must be baseline-corrected by a learned
value function — which is the same artifact as the blunder labeler.

Sources: [VR-MCCFR, AAAI 2019](https://arxiv.org/abs/1809.03057) ·
[DREAM, 2020](https://arxiv.org/abs/2006.10410) ·
[ESCHER, ICLR 2023](https://arxiv.org/abs/2206.04122)

### 4. Winrates hide exploitability — probe with best responders **[VERIFIED 3-0 ×4]**

ByteDance's search-free self-play system beat a top-10-ranked (China) Hearthstone player in all
four Bo5 tournaments. The same lineage's ByteRL won the LOCM 2022 competition at 84.41%. Yet a
cheap targeted pipeline — behavior cloning on ~125k ByteRL self-play matches (~3.5M state-action
pairs, reaching 42.4%), then PPO fine-tuning — beat it **90.4%** on 32-deck pools (54.2% on
1024-deck pools). Implication: keep a standing **exploiter probe** in evaluation; ladder winrate
alone certifies nothing about robustness. (Kaggle ladder replays of top opponents are exactly the
corpus a behavior-cloned exploiter/opponent model needs — the ByteRL exploit did it with 125k
matches.)

Sources: [Hearthstone system, IEEE CoG 2023](https://arxiv.org/pdf/2303.05197) ·
[ByteRL exploitability, 2024](https://arxiv.org/abs/2404.16689) ·
[LOCM ByteRL](https://arxiv.org/abs/2303.04096)

### 5. Compute reality check **[VERIFIED 3-0 ×4]**

- ByteRL's best non-cheat Hearthstone model: **24 V100 GPUs + 5,856 CPU cores × 23 days**,
  3.2e8 samples per learning period. LOCM champion: 24 GPUs × 72h, billions of episodes.
  Student of Games: AlphaZero-scale TPU fleets.
- A single-desktop PPO self-play pipeline (100k episodes, GTX 1050 Ti) **plateaued ~50% avg /
  59.2% best** vs a mid-level one-step-lookahead baseline.
- Counterweight: DouZero reached SOTA on 4 consumer GPUs in days, and the desktop-PPO authors
  attribute part of their gap to budget-forced choices (1-layer MLPs, no permutation-invariant
  encoding). The desktop ceiling is **method-dependent, not absolute**.

For us (~1000 games/min simulator ≈ 1.4M games/day, CPU-only inference): spend compute on value
learning + credit assignment *over the existing interpretable layer*, not end-to-end policy
self-play.

Sources: [2303.05197](https://arxiv.org/pdf/2303.05197) ·
[desktop PPO LOCM, Entertainment Computing 2023](https://ronaldo.games/assets/pdf/entcom-2023.pdf) ·
[Student of Games](https://arxiv.org/abs/2112.03178)

### 6. Gauntlet winrates mispredict real strength — independently confirmed **[VERIFIED 3-0 ×2]**

In the Hearthstone work, cheat-model c5 beat non-cheat b4 head-to-head (55%) in the internal
table, yet its checkpoint played *worse* against the human — including an obvious blunder
(Antique Healbot at full health). PyTAG independently reports agent-vs-agent winrates give
little insight into real strength. The same team's serious protocol: **45,000 matches per model
pairing, balanced over hero matchup (3×3) and first/second position (2×)**. Our "gauntlet
invalid" lesson is real, but the fix is protocol design, not abandoning offline measurement.

Sources: [2303.05197](https://arxiv.org/pdf/2303.05197) · [PyTAG](https://arxiv.org/abs/2405.18123)

### 7. Student of Games: the sound search shape, and its TCG bottleneck **[VERIFIED 3-0 ×3]**

SoG (growing-tree CFR: public-state search tree, regret updates alternating with expansion,
leaves backed by a learned counterfactual value-and-policy net) is provably sound for 2p0s and
beat Slumbot (poker) and PimBot (Scotland Yard). Its stated limit: it **enumerates all
information states within each public state** — combinatorially huge for a TCG (~10^7–10^8
candidate opponent hand/deck states vs poker's 1,326 hands). The stronger claim that
subgame-resolving is therefore *categorically unusable* for CCGs was **REFUTED 0-3** — the
authors themselves propose generative sampling of world states as the workaround. Practical
read: full GT-CFR is out of budget, but its shape — decision-time search over a *sampled* belief
subset, backed by a learned value net — is the principled upgrade path for our Turn Planner +
lethal solver.

Sources: [SoG, Science Advances 2023](https://www.science.org/doi/10.1126/sciadv.adg3256) ·
[arXiv](https://arxiv.org/abs/2112.03178) · [history filtering](https://arxiv.org/abs/2311.14651)

### 8. Naive dense reward shaping actively hurts **[VERIFIED 3-0, downgraded medium]**

In LOCM, potential-based shaping with opponent-health loss or a competition-winning heuristic
score failed to beat sparse terminal win/loss — the health-based variant was statistically
significantly WORSE (p<0.05) during training stretches; unshaped won (59.2% vs 55.2%/56.8%).
Single study, deterministic simplified CCG, tiny nets — directional only. Combined with
findings 2–3, the design rule: **dense credit comes from learned value functions/baselines,
never hand-picked heuristic potentials.**

Source: [Entertainment Computing 2023](https://ronaldo.games/assets/pdf/entcom-2023.pdf)

---

## Extracted findings (not adversarially verified)

These claims were fetched with verbatim quotes from primary sources but fell outside the top-25
verification budget. Treat as strong leads, verify before load-bearing use.

### Hybrid: keep the hand-authored layer, learn on top

- **Residual Policy Learning** (Silver/Allen/Tenenbaum/Kaelbling 2018): model-free RL learns a
  *corrective residual* on top of a nondifferentiable hand-designed controller — no gradients
  through the base needed; solves long-horizon sparse-reward tasks pure RL fails; composes with
  planner/MPC-style bases (i.e. with our Turn Planner). The canonical "keep the Pilot, learn the
  correction" recipe. [arXiv 1812.06298](https://arxiv.org/abs/1812.06298)
- **Expert iteration for LINEAR feature policies** (Soemers/Piette/Browne 2019, "Biasing MCTS
  with Features for General Games"): train a linear feature-weight policy with **zero manual
  labels** — MCTS visit-count distributions are the per-move target, cross-entropy SGD updates
  the weights. And **the feature set grows automatically**: new compound features are added by
  combining co-active feature pairs whose activation best correlates with apprentice-vs-expert
  error (redundancy-penalized). This is a principled mechanization of "split a feature when
  context demands it". Warning from the same paper: per-node feature-evaluation cost can negate
  search gains (8× MCTS iteration loss in one game); prune to top-|weight| features.
  [arXiv 1903.08942](https://arxiv.org/abs/1903.08942)
- **Linear beats fancier under limited compute** (LOCM evolution study): an evolved linear
  weight vector over ~20 hand-crafted features beat two genetic-programming tree representations
  (54.8% vs 45.6/45.7%); self-play "progressive fitness" beat evolving against a fixed opponent
  (54.8% vs 42.9%). Recommended curriculum: evolve linear first, then losslessly convert to
  trees and continue. [arXiv 2105.01115](https://arxiv.org/abs/2105.01115)
- **Distillation direction** (if we ever train a neural policy): VIPER distills a DNN into a
  decision tree, weighting samples by the oracle's Q-loss so capacity concentrates on *critical
  states* — trees an order of magnitude smaller at equal strength; trees verify formally in
  seconds vs minutes-to-timeout for DNNs. INTERPRETER renders distilled trees as **editable
  Python programs**: one hand-added rule fixed a misbehavior (diver-saving 18.6%→98.5%), a
  one-feature edit bought robustness to a distribution shift, and inference is ~79 µs/decision
  on CPU. When one tree can't fit a task, the fix was **two expert trees + a context-dispatching
  meta-policy** — mixture-of-experts as the scaling path.
  [VIPER, NeurIPS 2018](https://people.csail.mit.edu/asolar/papers/BastaniPS18.pdf) ·
  [INTERPRETER 2024](https://arxiv.org/pdf/2405.14956)
- **Context splitting works at scale too**: the Hearthstone system split one shared policy into
  per-hero models for +6.5% winrate; other measured single-change deltas: γ=1.0 for terminal
  win/loss (+7%), keeping off-policy staleness near on-policy (+10%), V-Trace clipping + PPO
  surrogate (+15.1%). [arXiv 2303.05197](https://arxiv.org/pdf/2303.05197)
- **Concept bottlenecks** (SCoBots): interpretable relational-concept layers matched deep-RL
  performance and *surfaced a previously unknown reward-hacking defect* in Pong — transparency
  as a defect-detection mechanism, not just a writeup nicety.
  [arXiv 2401.05821](https://arxiv.org/abs/2401.05821)

### Metagame adaptation

- **AlphaStar league** (Nature 2019): imitation from human replays + a league of main agents,
  past checkpoints, and dedicated **exploiter agents** whose job is finding main-agent
  weaknesses; main agents become transitively stronger. The full league payoff matrix contained
  ~3,000,000 rock-paper-scissors cycles — non-transitivity at that scale is *why* pairwise
  gauntlet winrates mislead. Final skill was measured on the live human ladder, not internally.
  [Nature s41586-019-1724-z](https://www.nature.com/articles/s41586-019-1724-z)
- **Offline RL from replays works in a Pokemon domain** (Metamon, RLC 2025 — Pokemon Showdown
  video-game battling, not TCG): reconstructed 475k+ human battles from spectator logs into
  first-person trajectories with **no manual labeling**; imitation → offline RL → self-play
  fine-tuning reached top-10% of active ladder humans with *no search at inference*; performance
  scaled with data (3M trajectories). Evaluation used GXE (Glicko expected winrate vs random
  opponent) with ≥400 battles per eval. Precedent for harvesting Kaggle ladder replays.
  [arXiv 2504.04395](https://arxiv.org/pdf/2504.04395)
- **Naive self-play doesn't converge** in imperfect-info games (fails even on rock-paper-
  scissors, yields highly exploitable policies) — use fictitious-play/CFR/PSRO-flavored
  population schemes. Also: abstraction-based precomputed policies are "mostly obsolete" vs
  decision-time search (local best response exploited the best abstraction agents by huge
  margins, couldn't exploit DeepStack).
  [Schmid thesis, arXiv 2111.05884](https://arxiv.org/pdf/2111.05884)

### CPU-budget inference

- **Modicum** (depth-limited solving, NeurIPS 2018): master-level HUNL poker **in real time on a
  4-core CPU + 16 GB RAM** (~20 s/hand), strategy computed in 700 core-hours (vs ~2M core-hours
  for predecessors). Key idea: at the depth limit, let the opponent choose among <10 continuation
  strategies (multi-valued leaves) — single-value leaves provably fail. A **2-hidden-layer,
  64-node value net** was fast enough on CPU. [arXiv 1805.08195](https://arxiv.org/pdf/1805.08195)
- **ISMCTS** (Cowling/Powley/Whitehouse 2012): determinization has two systematic pathologies
  (strategy fusion, non-locality) plus budget-splitting; ISMCTS searches one tree of information
  sets and goes deeper per CPU-second. BUT in Dou Di Zhu (closest to a shuffled-deck TCG) it was
  only on par with determinized UCT — the union of legal actions across an infoset inflated
  branching ~10×. Depth-per-determinization is the binding resource: 1 determinization × 10,000
  iterations beat 40 × 250 by 22.9%.
  [IEEE TCIAIG 2012](https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf)
- **Suphx runtime adaptation**: determinize hidden state, roll out, apply *test-time gradient
  fine-tuning* to the policy mid-match — exists, but carries nontrivial inference cost.

### Evaluation methodology

- **AIVAT** (Burch et al.): provably unbiased variance reduction needing only a rough heuristic
  state-value estimate + the known strategy of one side; corrects variance from BOTH chance
  (shuffles/draws) and known-strategy randomization. Poker: >10× fewer hands for significance;
  on DeepStack's human match it cut the 95% CI from ±220 to ±40 mbb/g (~85% std-dev reduction).
  Key synergy: **counterfactual values already computed by decision-time search serve as AIVAT's
  value estimates for free** — an agent that computes per-decision values gets low-variance
  evaluation as a byproduct. Raw winrate is so noisy that multi-day man-machine poker matches
  failed to reach significance despite substantial margins.
  [arXiv 1612.06915](https://arxiv.org/abs/1612.06915) · [thesis 2111.05884](https://arxiv.org/pdf/2111.05884)
- **Deal stratification** (ISMCTS paper): fix a pool of deals, replay each many times (5000
  deals × 75 plays), and **stratify by skill-sensitivity** — pre-classify deals by whether a
  cheating perfect-info player significantly beats the baseline (i.e. deals where hidden info
  matters). On the sensitive stratum, real algorithm differences appeared that aggregate
  winrates completely masked. This is likely *the* fix for our gauntlet-signal failure.
- Suphx needed 5000+ Tenhou expert-room games plus bootstrap resampling for a stable rating;
  the ByteRL study used 5 seeds × 95% CIs per configuration; Metamon used ≥400 battles/eval.
  High-N with balancing is table stakes.

### Data-efficiency levers (for whenever a neural component trains)

- Permutation-equivariant set encoders (Deep Sets / Set Transformers) flagged as the key untried
  lever for card games — flat per-slot encodings force relearning each card concept per slot.
- Invalid-action masking is critical; **argmax (not softmax) action selection** is standard in
  CCGs because a single suboptimal move can swing a game.
- **Oracle guiding** (Suphx): train initially with hidden info visible, anneal it away — a
  sample-efficiency trick our simulator supports trivially (we control both sides in self-play).
- γ = 1.0 for terminal win/loss reward (+7% in Hearthstone work) — no discounting inside a match.

---

## Recommended architecture for this repo

Mapped onto what exists today (Pilot's linear Hypothesis scoring, Turn Planner, lethal solver,
the Read/Briefs, corrections pipeline, `tools/battle.py` ≈ 1000 games/min, the T5 value model
currently gated OFF):

**Stage 1 — the value net (keystone).**
Train P(win | state) on self-play logs across all deck pairs (not just mirrors — supersedes the
T5 mirror-corpus design). Input = engine state + existing Hypothesis signals as features + the
Read's archetype (matchup conditioning). Start Modicum-small (2×64). γ=1.0, terminal win/loss
target, then TD bootstrapping. ~1.4M games/day of fresh data is available locally; CPU inference
cost is microseconds.

**Stage 2 — the automated blunder labeler.**
Chess-annotator loop over self-play and ladder replays: at each decision, ΔP(win) between action
taken and best alternative (value net, plus planner rollout where cheap). |Δ| above threshold →
auto-Correction into the existing corrections pipeline; humans review only flagged anomalies,
never raw replays. Lost-match-with-no-negative-deltas = "played well, lost" — logged, not
punished. This *is* Suphx's delta-reward + VIPER's critical-state weighting applied to our
pipeline.

**Stage 3 — expert-iteration weight tuning.**
Expert = Turn Planner + value net (shallow search / one-step lookahead). Apprentice = the linear
Hypothesis layer (stays the runtime policy — interpretability preserved, and the linear-beats-
trees-under-limited-compute result says we lose little). Weights train against per-decision
expert targets; `tune.py`'s perceptron becomes the SGD loop. Feature splitting becomes
mechanical: (a) matchup-conditioned weight overrides learned, not authored (the
`Strategy.weight_overrides` + Brief machinery already exists as the runtime carrier); (b)
Soemers-style compound-feature construction from co-active pairs correlating with
apprentice-vs-expert error; (c) per-archetype expert split when one table can't fit (+6.5%
precedent).

**Stage 4 — league, not vanilla self-play.**
Population = all deck agents + past checkpoints + a standing exploiter (behavior-clone the
current main from its own logs, PPO-fine-tune, exactly the ByteRL exploit recipe). Exploiter
winrate spiking = the robustness alarm no gauntlet gives. Harvest Kaggle ladder replays of top
opponents (ADR-0019 data access) for opponent models and imitation seeds (Metamon precedent).

**Stage 5 — evaluation protocol (replaces "gauntlet is dead" with "gauntlet done right").**
Duplicate deals (same shuffle seeds, both sides), balanced matchup × first/second, deal pool
stratified by skill-sensitivity (cheating-agent-vs-baseline gap), AIVAT-style correction using
the value net's per-decision values. Expect ~10× sample-efficiency on significance; ladder stays
the final arbiter.

**Rotation/meta shift loop:** new deck/set → deck-genie authors doctrine (seed weights = priors)
→ self-play regenerates corpus → value net fine-tunes → expert iteration retunes weights →
blunder labeler surfaces residual gaps. Manual work shrinks to doctrine authoring + reviewing
flagged anomalies.

**Explicit non-goals:** end-to-end neural policy (compute-infeasible, loses the writeup story);
hand-crafted dense reward shaping; full infostate-enumerating subgame resolving. Long-term
planner upgrade: sampled-belief decision-time search backed by the value net (SoG shape,
generative-sampling variant).

---

## Open questions

1. **Sample sizes for our effect sizes**: how many duplicate-dealt games to detect a 2–3%
   winrate delta with the stratified + AIVAT-corrected protocol? (Hearthstone bar: 45k/pairing
   raw; AIVAT suggests ~10× less.)
2. **Does ESCHER-scale regret learning fit a desktop** for a TCG-sized game, or is Deep
   Monte-Carlo the only proven desktop path? (ESCHER's variance wins were measured on small
   benchmarks with oracle value functions.)
3. **Interpretability-preserving loop is unvalidated end-to-end**: no verified claim covered
   rule distillation, concept bottlenecks, or MoE gating as a *complete* training loop — the
   pieces exist (RPL, expert iteration, VIPER/INTERPRETER), the composition is ours to prove.
4. **Risk-sensitivity**: "when to take risks" mostly falls out of maximizing P(win) instead of
   expected material (a value net encodes it), but no strong direct literature survived on
   explicit risk modulation mid-match. Suphx's test-time adaptation is the nearest mechanism.
5. **Minimal league size** for our deck pool — AlphaStar's league is industrial; what's the
   3-agents-and-an-exploiter version worth?

## Refuted during verification

- "CCG hidden-information spaces make poker-style search/subgame-resolving methods *unusable*,
  forcing model-free policy methods" — **refuted 0-3**. Expensive in enumeration form, yes;
  unusable, no (generative belief sampling is the stated workaround).

## Source list

21 primary sources fetched; all claims above link inline. Recency caveat: DouZero (2021) and
Suphx (2020) have been surpassed on their leaderboards (PerfectDou/AlphaDou; Tencent LuckyJ) —
the method lessons hold, the rankings don't. The Hearthstone human eval is n=1 player on a
restricted 2015 card pool; the reward-shaping negative result is one study on a deterministic
simplified CCG.
