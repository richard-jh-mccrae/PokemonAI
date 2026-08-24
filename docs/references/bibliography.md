# Design Provenance — Bibliography & Evidence Ledger

**Purpose.** The competition writeup must explain *how we came to each design choice and why* —
with the prior art and its measured success. This document is that ledger: every load-bearing
choice in the Value System (tracker issue #136), the precedent it rests on, the measured result
that justified it, and the source. Compiled from the 2026-07-23 deep-research pass over 2020–2026
primary sources and the earlier research ledger attached to Issue #136.

**Verification honesty (state this in the writeup too).** Sources marked **[P]** were fetched and
read at the primary location (author-maintained repos/docs). Sources marked **[S]** were verified
through corroborated search extracts of the primary URL because the research sandbox's egress
policy blocked direct fetches of most paper hosts (arxiv.org, OpenReview, PMLR, etc.); exact
figures from [S] sources are directionally reliable but were not re-read from the PDF. Internal
results marked **[I]** are our own measured experiments in this repository.

---

## 1. The fundamental bet: interpretable evaluation + search, not end-to-end RL

**Choice:** hand-crafted, machine-tuned value terms over a shared state model, with shallow sound
search — instead of an end-to-end neural policy.

- **Legends of Code and Magic / Strategy Card Game AI Competition** (Kowalski & Miernik,
  competition summary, arXiv 2305.11814) — search + hand-crafted/tuned end-turn evaluation won
  every edition until the final one; the eventual neural champion required industrial compute.
  https://arxiv.org/pdf/2305.11814 [S]; competition repo
  https://github.com/acatai/Strategy-Card-Game-AI-Competition [P]
- **ByteRL** (ByteDance; LoCM 2022 double champion, arXiv 2303.04096) — the end-to-end champion —
  was later shown **"easily exploitable"**: a behavior-cloned + RL-fine-tuned adversary beat it
  90.4% on 32-deck pools (*Learning to Beat ByteRL*, arXiv 2404.16689). https://arxiv.org/abs/2404.16689 [S]
- **ygo-agent** (Yu-Gi-Oh, open source) — reference end-to-end model trained on **100M+ games,
  32×RTX-4090 × 5 days**; README still lists "zero-shot generalization of new cards" as future
  work. https://github.com/sbl1996/ygo-agent [P]
- **Compute reality** (prior report): master-level end-to-end Hearthstone took 24 V100s + 5,856
  CPU cores × 23 days (arXiv 2303.05197); a single-desktop PPO pipeline plateaued ~50–59%
  (Entertainment Computing 2023). [S]
- **Our constraint:** Kaggle grader = 2 vCPUs, ~10 min/match, pure-Python-stdlib runtime
  (`tools/sim/CONTEXT.md`). [I]

## 2. Throughput-preserving evaluation: immutable observations and additive features

**Choice:** ObservationState is the immutable legal-view boundary; the Ledger evaluates one Feature
Catalog through additive marginal valuation (ADR-0154–ADR-0156). Future search consumes that seam.

- **Stockfish NNUE** (merged Aug 2020) — merge-time gain **+92.77 ±2.1 Elo** (60k games); the
  architecture wins through an incrementally-updated first-layer accumulator, extreme shallowness
  ("most of the knowledge is stored in the first layer"), and the doc's warning that "more
  sophisticated feature sets... usually cannot combat the hit on performance."
  https://github.com/official-stockfish/nnue-pytorch/blob/master/docs/nnue.md [P];
  launch post https://github.com/official-stockfish/stockfish-web/blob/master/content/blog/2020/introducing-nnue-evaluation.md [P]
- **Classical-eval removal** (Stockfish 16, 2023) — the handcrafted eval was deleted only after a
  smaller second net was measured "worth more elo" — replacement by measurement, not fashion; the
  same discipline as our corpus-gated decider swaps.
  https://github.com/official-stockfish/Stockfish/discussions/4678 [P]

## 3. Phase/regime-bucketed weights over one shared term basis

**Choice:** ONE always-computed term basis; weight sets bucketed by cheap discriminators
(prizes-remaining; race-vs-interaction regime), per-deck weights learned — never per-deck code forks.

- **Stockfish layer stacks** — 8 output weight sets selected by `(piece_count − 1) / 4`, chosen
  because piece count is "cheap to compute, fairly well-behaved during the game." Prizes-remaining
  is our piece count. (Same NNUE doc as §2.) [P]
- **Texel tuning** (Østensen 2014; standard below top engines) — hand-crafted terms with
  logistic-regression-learned weights, **phase-interpolated between two weight sets over one
  shared basis** (`E = p·xW_mid + (1−p)·xW_end`) — the direct ancestor of our terms+calibrator.
  https://github.com/maksimKorzh/wukongJS/blob/main/docs/TEXEL'S_TUNING.MD [P]
- **GNU Backgammon** — the canonical race-to-N engine: a trivially cheap position classifier
  dispatches to class-conditional evaluators (`CLASS_RACE` / `CLASS_CRASHED` / `CLASS_CONTACT`,
  separate nets and feature sets), with exact databases taking unconditional precedence.
  Source: `eval.h`/`eval.c` in the official mirror https://github.com/mormegil-cz/gnubg [P]
- **Metamon** (UT Austin, RLC 2025; Pokémon Showdown) — measured the generalist/specialist
  tradeoff: the broad 142M model beats specialists **across** formats but *loses in-domain to the
  Gen1 specialist* that hit #1 on the human ladder → shared representation + per-deck
  specialization beats either extreme; initialize specialists from the generalist.
  https://github.com/UT-Austin-RPL/metamon [P]; paper arXiv 2504.04395 [S]

## 4. Sound solvers above estimation

**Choice:** the engine-verified, min-bound, coin-safe lethal solver outranks all value estimation;
worst-case logic is reserved for the lethal boundary, not used as the global criterion.

- **GNU Backgammon** — exact bearoff/hypergammon databases take unconditional precedence over the
  nets (§3 source). [P]
- **Knowledge-based paranoia search in Skat** (Edelkamp, arXiv 2104.05423) — worst-case search is
  deployed for endgame **safety plays only**; good play means playing to *likely* distributions —
  global paranoia measurably over-pessimizes. https://arxiv.org/pdf/2104.05423 [S]

## 5. The P(win) model: tabular learner + calibration + auxiliary targets

**Choice:** logistic-linear calibrator first (weights feed term-level blunder diagnosis), promote
to depth-limited GBDT only on measured interaction miscalibration; isotonic calibration; 3-way
W/D/L output; prize-differential auxiliary target; labels blended beyond pure terminal outcome.

- **Grinsztajn, Oyallon & Varoquaux** (NeurIPS 2022 D&B) — tuned tree ensembles beat MLPs/
  ResNets/FT-Transformers on medium tabular data; GBDTs robust to uninformative features (our
  always-computed terms include dead-in-context ones).
  https://github.com/LeoGrin/tabular-benchmark [P]; paper arXiv 2207.08815 [S]
- **McElfresh et al.** (NeurIPS 2023 D&B) — across 19 algorithms × 176 datasets, GBDT-vs-NN
  usually matters less than light GBDT tuning. https://github.com/naszilla/tabzilla [P];
  paper arXiv 2305.02997 [S]
- **Niculescu-Mizil & Caruana** (ICML 2005) — boosted models are systematically miscalibrated;
  **isotonic regression ≥ Platt once the calibration set exceeds ~1,000 points** (ours will by
  orders of magnitude). https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf [S]
- **KataGo** (Wu, arXiv 1902.10565) — auxiliary ownership/score targets and horizon-blended value
  labels are a major share of a ~9.1× self-play efficiency product; our analog: a prize-differential
  auxiliary target + optional label blending.
  https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md [P]
- **Leela Chess Zero** — WDL head (+~20 Elo) and moves-left auxiliary head; a WDLP head study
  reports +33 Elo (ICGA/ACG 2021). Directly relevant: this simulator's delta rules a simultaneous
  win a DRAW, so a 3-way W/D/L output is correct here.
  https://lczero.org/blog/2023/07/the-lc0-v0.30.0-wdl-rescale/contempt-implementation/ [S]

## 6. Belief-sampled depth-2 with an opponent reply portfolio (Phase 6, issue #150)

**Choice:** K≈16–24 posterior-stratified hidden-zone samples; at each world the opponent picks the
best of a small **portfolio of reply policies**; calibrated P(win) leaf immediately after the
reply; mean aggregation with a single lethal-boundary safety veto. Gated on the value model.

- **Depth-limited solving / Modicum** (Brown & Sandholm, NeurIPS 2018, arXiv 1805.08195) — a
  single fixed opponent continuation policy at the depth limit is a *formally characterized
  failure mode* (the RPS+ construction: search becomes indifferent among strategies including
  maximally exploitable ones); a small portfolio of continuation strategies fixes it. Modicum:
  master-level HUNL **in real time on a 4-core CPU**, strategy computed in ~700 core-hours.
  https://arxiv.org/pdf/1805.08195 [S]
- **Matrix-valued states** (Milec, Kovařík & Lisý, AAMAS 2025, arXiv 2501.10464) — extends the
  portfolio result; >2× utility vs opponents who err beyond the depth limit.
  https://arxiv.org/pdf/2501.10464 [S]
- **Our own negative result** — the parked Tier-6 depth-2 (single determinization +
  self-policy-reply + weak heuristic leaf) regressed ~12 points in a 1,000-game mirror A/B
  (ADR-0043/0064; the `tier-6-escalation-search.md` design note was removed with the tier) — the exact pathological
  configuration the literature names. The design sequence (evaluation first, search after) follows
  from this measurement. [I]
- **Determinization counts** (Powley/Whitehouse/Cowling, Dou Di Zhu, AISB/CIG 2011) — playing
  strength rises rapidly up to ~20 determinizations, then plateaus; GIB fixed 50.
  http://orangehelicopter.com/academic/papers/aisb11.pdf [S];
  GIB: https://www.ijcai.org/Proceedings/99-1/Papers/084.pdf [S]
- **Archetype-conditioned sampling** (Dockhorn et al., Hearthstone, IPMU 2018) — opponent-model
  hand prediction "allows reducing the number of necessary simulations without loss of quality."
  https://adockhorn.github.io/files/papers/2018__IPMU__Predicting_Opponent_Moves_for_Improving_Hearthstone_AI.pdf [S]
- **EPIMC / postponed reasoning** (Arjonilla et al., ALA 2024, arXiv 2408.02380) — cutting to a
  value estimate before hidden information is exploited deep in the tree reduces strategy-fusion
  damage (Dark Chess: 80/65/45% win at postponement depths 3/2/1) — supports evaluating the
  calibrated leaf right after the reply. https://www.lamsade.dauphine.fr/~cazenave/papers/ALA2024_paper_32.pdf [S]
- **ISMCTS** (Cowling, Powley & Whitehouse, IEEE TCIAIG 2012) — the classic pathologies
  (strategy fusion, non-locality) and the depth-per-determinization tradeoff.
  https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf [S]

## 7. The human-feedback loop (correction rounds + machine labeler, issues #146/#147)

**Choice:** pairwise chosen-vs-correct corrections (ranking constraints); review queue ranked by
committee disagreement; machine labels in BOTH directions (blunder flags AND confident
"agent-was-right" constraints) gated by an audited precision threshold; human-first fitting with
dynamic noise filtering of machine constraints.

- **PEBBLE** (Lee, Smith & Abbeel, ICML 2021, arXiv 2106.05091) — pairwise preferences with
  relabeling reach ground-truth-reward performance with hundreds-to-~1,400 queries. [S]
- **SURF** (ICLR 2022, arXiv 2203.10050) — confidence-gated pseudo-labeling multiplies human
  labels ~6× (400 queries matching what PEBBLE needed ~2,500 for) — the model for extending our
  auto-labeler beyond blunders to confident agreements. [S]
- **B-Pref** (NeurIPS 2021 D&B, arXiv 2111.03026) — ensemble-disagreement/uncertainty query
  selection beats uniform; coverage/diversity selection does not — the basis for the
  disagreement-ranked review queue. https://github.com/rll-research/BPref [P for repo] [S for numbers]
- **RIME** (ICML 2024 Spotlight, arXiv 2402.17257) — feedback-efficient learners are the MOST
  fragile to label noise; baselines collapse at 20–30% preference error — exactly a
  0.80-precision auto-labeler's regime; loss-based dynamic filtering + warm-starting on trusted
  labels restores robustness. Basis for human-first fit ordering + machine-constraint filtering. [S]
- **ThriftyDAgger** (CoRL 2021, arXiv 2109.08273) — novelty+risk-gated querying under a fixed
  human budget (+58%/80% in their domains) — budget-aware querying precedent. [S]
- **XIL / explanation feedback** (CAIPI, AIES 2019; Schramowski et al. 2020; arXiv 2306.16431) —
  supports the *direction* of term-level correction but has no quantified game evidence; our
  term-decomposition review loop is ahead of the literature here, stated as such. [S]

## 8. Self-play, evaluation methodology, and the league question

**Choice:** paired matchup×seat-balanced A/B as the standard gate for every decider swap; a
control variate on paired residuals (calibrated early-turn P(win)) instead of full AIVAT;
frozen-checkpoint opponent pool now, league/exploiter deferred.

- **AIVAT** (Burch et al., AAAI 2018) — 85% standard-deviation reduction (≈44× sample savings)
  in poker evaluation; the ceiling our control-variate approach approximates. [S]
- **Paired-seed theory** (arXiv 2512.24145, 2025) + **TAG framework practice** (arXiv 2503.02686)
  — seed pairing provably reduces variance under positive seed-outcome correlation. NOTE: literal
  duplicate deals are **engine-blocked here** (no deal seed; forks reshuffle hidden zones —
  `src/cgpy/CONTEXT.md` [I]); we keep the paired estimator + control variate, which is
  most of the benefit. [S]
- **AlphaStar league** (DeepMind, Nature 2019) — leagues fix exploitability/forgetting rather than
  raw Elo; **Minimax Exploiter** (Ubisoft, AAMAS 2024) shows exploiter value at modest scale but
  not in card games — no published evidence a 3–5-member league beats a checkpoint pool at our
  scale → league deferred, checkpoints kept. [S]
- **Suphx** (MSR 2020, arXiv 2003.13590) — value-delta credit assignment under luck (the
  global-reward-predictor Φ-delta recipe) — the template for the automatic blunder labeler.
  See also the research ledger attached to Issue #136. [S]
- **Our own instruments** — the merged eval harness (PR #112: ~9k games detects a 3% win-delta;
  duplicate-position auxiliary mode) and blunder labeler (PR #115) with measured internal A/Bs
  (e.g., doom-relax: 4,800-game gauntlet, verdict ON). [I]

## 9. Card representation and new-set adaptation (post-competition goal)

**Choice:** fail-CLOSED per-card effect models for play-time value (nothing in the literature
demonstrates zero-shot *gameplay* strength on unseen cards); text-embedding **tag bootstrapping**
to turn new-set onboarding into review-and-correct.

- **Bertram et al.** (IEEE CoG 2024, arXiv 2407.05879, MTG drafting) — text+feature card
  embeddings predict ~43–55% of expert picks on *completely unseen* cards — useful for proposing
  annotations, insufficient for play. [S]
- **UrzaGPT** (2025, arXiv 2508.08382) — GPT-4o drafts 43% zero-shot; a LoRA-tuned small LLM
  66.2% — same conclusion. [S]
- **Cardsformer** (ECAI 2023) — grounds Hearthstone card text in a learned transition model;
  claims strength "even with untrained cards in the deck" (no public numbers in repo — flagged).
  https://github.com/WannianXia/Cardsformer [P for repo]
- **ygo-agent** (§1) — LLM text-embeddings of card effects, yet zero-shot new-card play remains
  open — the strongest evidence that fail-closed explicit modeling is currently correct. [P]

## 10. Negative results that shaped the design (cite these — they are the "why")

- **Tier-6 depth-2 regression** (−12 pts, 1,000-game A/B) → evaluation-first sequencing; reply
  portfolios; belief sampling. [I]
- **ByteRL exploitability** (90.4% loss to a targeted adversary) → diverse-pool evaluation of
  learned weights, exploiter probes on the roadmap. [S]
- **Zero-score index-tie CRITICAL bugs** (ADR-0062; mega_starmie ep82867148 f48/f87; mega_lucario
  ep83661652 f33/f40/f44) → the deterministic tie-break policy and the continuous scalar. [I]
- **Dense hand-crafted reward shaping worse than sparse win/loss** (LOCM, Entertainment
  Computing 2023) → learned value deltas, never
  heuristic potentials, for credit assignment. [S]
- **Naive self-play non-convergence in imperfect-info games** (Schmid thesis, arXiv 2111.05884;
  see prior report) → checkpoint pools, eventual league. [S]

---

*Related internal records: `docs/adr/`, the Value System tracker (Issue #136), and its phase issues
(#137–#150), each carrying the per-phase evidence.*

## 11. Offline teacher and future Search Algorithm allocation

**Historical choice:** the quarantined Bellman teacher used exact hidden-world transpositions, equal
root probes, and ranked successive halving. The live Ledger does not run this traversal.

- **Hyperband / successive halving** (Li et al., JMLR 2018) — primary precedent for allocating a
  small equal budget broadly, then concentrating computation on promising incomplete candidates.
  https://www.jmlr.org/papers/v18/16-558.html [P]
- **Beam-stack search** (Zhou & Hansen, ICAPS 2005) — primary anytime/complete beam-search
  alternative; retained as the future recovery design rather than added to the live latency fix.
  https://m.aaai.org/Papers/ICAPS/2005/ICAPS05-010.pdf [P]
- **Single-Agent Policy Tree Search With Guarantees** (Orseau et al., NeurIPS 2018) — primary
  best-first policy-guided allocation result. https://papers.nips.cc/paper/7582-single-agent-policy-tree-search-with-guarantees [P]
- **MCTSnets** (Guez et al., ICML 2018) — learns where, what, and how to search; deferred until this
  agent owns a calibrated learned policy/value model. https://proceedings.mlr.press/v80/guez18a.html [P]

## 12. Analytic shuffle-refresh decisions

**Choice:** integrate hidden redraw identities out as exact hypergeometric need-coverage classes.
Do not construct a hypothetical hand or search actions using cards that have not actually been
drawn. Current planning language lives in `docs/plans/PokemonAI_Supporter_Decision_Handoff.md`.

- **Multivariate hypergeometric distribution** — sampling identities without replacement; supplies
  the exact probability mass over semantic need-coverage classes. [S]
- **Receding-horizon replanning** — commit only the refresh action, observe the real redraw, then
  solve again from the new observation. The analytic pre-commit equation estimates the gamble; it
  never becomes an executable post-draw policy. [S]
