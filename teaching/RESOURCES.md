# Resources

High-trust external resources for the ML ideas in this system, plus the in-repo primary sources the
book is grounded in. Ordered roughly by accessibility for a strong engineer new to ML.

## Primary sources inside this repo (ground truth — read these first)
- `docs/tuning/methodology.md` — the linear model, corrections-as-ranking-labels, hinge loss, L2,
  the structured perceptron, the pocket, the adoption gate. The single best in-repo doc.
- `docs/architecture/tiers.md` + `tier-0..tier-6-*.md` — the whole decision stack.
- `docs/architecture/tier-5-value-model.md` + `docs/adr/0042-*.md` — the logistic value model.
- `docs/adr/0009-training-methodology.md`, `docs/adr/0007-*` — why one offline model, why not RL.
- `src/common/deck_odds.py` — the hypergeometric own-deck estimate (well-commented).
- `docs/adr/0039-*` (gamble lines / expectimax), `docs/adr/0043-*` (escalation search).

## Books (the canonical ladder)
- **An Introduction to Statistical Learning** (James, Witten, Hastie, Tibshirani) — *free PDF* at
  <https://www.statlearning.com>. The best first ML book for an engineer. Ch 2 (bias–variance),
  Ch 4 (logistic regression), Ch 6 (regularisation). START HERE.
- **The Elements of Statistical Learning** (Hastie, Tibshirani, Friedman) — free PDF at
  <https://hastie.su.domains/ElemStatLearn/>. The rigorous big sibling of ISL.
- **Reinforcement Learning: An Introduction**, 2nd ed. (Sutton & Barto) — free PDF at
  <http://incompleteideas.net/book/the-book-2nd.html>. For the "why not RL / AlphaZero" chapter.
- **Artificial Intelligence: A Modern Approach** (Russell & Norvig) — the classic for search,
  minimax, expectimax, game trees. Chapters 3, 5, 6.
- **Pattern Recognition and Machine Learning** (Bishop) — free PDF from Microsoft Research. Deeper
  probability/logistic/Bayesian treatment when he wants rigour.

## Courses / lectures
- **Andrew Ng, Machine Learning Specialization** (Coursera / DeepLearning.AI) — gentlest on-ramp to
  linear/logistic regression, cost functions, gradient descent. Matches Chapters 3–7 of this book.
- **David Silver, Reinforcement Learning course** (DeepMind/UCL, on YouTube) — for the search/RL arc.
- **3Blue1Brown, "Neural networks" + "Gradient descent" videos** (YouTube) — best visual intuition
  for gradient descent (our Chapter 6). Free.

## Papers worth reading once the basics land
- Silver et al., *Mastering the game of Go without human knowledge* (AlphaZero), Nature 2017 — the
  archetype of the search+network approach we deliberately did NOT take.
- Cortes & Vapnik, *Support-Vector Networks* (1995) — the origin of the hinge loss / margin (Ch 5).

## Communities (wisdom — test understanding on real people)
- **Kaggle forums / the competition discussion tab** — the most on-topic community; other competitors
  reason about the same simulator.
- **r/MachineLearning** and **r/learnmachinelearning** (Reddit) — beginner-friendly Q&A.
- **Cross Validated** (stats.stackexchange.com) — precise answers on loss functions, logistic
  regression, hypergeometric probability.
