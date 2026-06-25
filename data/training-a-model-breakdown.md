# Training a Model for Your Agent — Beginner Breakdown

A start-to-finish guide for using replay data to improve your agent's decisions, written for someone new to ML. Context: Pokémon TCG AI Battle Challenge — CPU-only runtime, 10-minute match bank, no guaranteed GPU, no internet in the sandbox.

---

## The trap to avoid first

If you have replay data and you're picturing "training a model" as **reinforcement learning** (PPO, self-play), **stop.** RL is the hardest, most expensive, most failure-prone path — and the one real ladder dataset we have showed RL/MCTS losing to a tuned rule-based agent.

With replays already in hand, the right tool is **supervised / imitation learning** — dramatically simpler, cheaper, and far more likely to work. This whole guide assumes that.

---

## Step 1 — Pick the right *kind* of model

Three options, in increasing difficulty:

1. **Value function (START HERE).**
   - Input: a game state. Output: one number — your probability of winning from here.
   - Labels are **free**: every state in a replay is labeled by whether that player *eventually won* (1) or *lost* (0).
   - Plain supervised learning — the easiest thing in ML.
   - Plugs directly into the engine's search API as your **leaf evaluation** in `search_begin`, replacing the hand-built target-value formula.
   - **This is your highest-leverage first model.**

2. **Policy (behavioral cloning) — second.**
   - Input: a state. Output: which action a good player took (predict the move).
   - Supervised, but trickier: the output is a choice over a variable-length legal-option list.
   - Useful as **move-ordering** for the search.

3. **Reinforcement learning — last, maybe never.**
   - Learn from scratch by playing and getting rewarded for wins.
   - Needs self-play infra, a Gym wrapper around cabt, large compute, careful tuning — and may still lose to the value function.
   - Skip until everything else is exhausted.

**Beginner with data → build the value function.**

---

## Step 2 — The data pipeline (this is ~80% of the real work)

Training the model is the easy 20%. Turning replays into a dataset is the job.

Produce a table where **each row is one decision point**:

- **Features (X):** the game state as a numeric vector —
  - your prizes, energy counts, hand size
  - board Pokémon encoded via `CardData` fields: HP, ex/megaEx, type, attacks
  - opponent's visible board and **discard pile**, turn number, etc.
  - This *feature engineering* is where domain knowledge pays off. Start simple (a few dozen numbers), expand later.
- **Label (y):** for the value model — did this player win the game? (1/0). One 20-turn game → ~20+ labeled states.

**Two critical filters:**
- **Only learn from good players.** Train on winners / high-Elo games, not random bots, or you clone mediocrity.
- **Dedupe** so one dominant deck (e.g., the current Lucario majority) doesn't drown the signal.

Output: a big CSV/parquet of `(state_vector, won?)`. Many replays → hundreds of thousands to millions of rows. Plenty.

---

## Step 3 — Framework and model: start boring

For a tabular feature vector predicting a number, the best beginner choice is **NOT a neural net**. Use **gradient-boosted trees**:

- **LightGBM** (or XGBoost). `pip install lightgbm`.
- Trains in **minutes on a laptop CPU**, no GPU, almost no tuning.
- Handles messy tabular features gracefully; very hard to mess up.
- Strong baseline immediately.

Move to a small neural net (an **MLP in PyTorch**) only if you outgrow trees — e.g., feeding raw board structure instead of hand-engineered features. PyTorch is the standard, but it's a step up in complexity you don't need yet.

---

## Step 4 — Do you need to rent a cloud GPU? No.

For the value-function approach, **you do not need to rent anything.**

- **LightGBM on your laptop CPU** trains this in minutes to an hour.
- A small PyTorch MLP trains fine on CPU or a free GPU.

Free options, right where your data lives:
- **Kaggle Notebooks** — free GPU/TPU quota, competition data already attached. The obvious place to train.
- **Google Colab** — free-tier GPU for PyTorch experiments.

You'd only reach for **paid cloud GPUs** for large-scale deep RL / self-play — the expensive path to avoid, and which the competition's **"Reasonableness Standard"** caps anyway (excessive paid training spend can disqualify you).

### The constraint that actually matters: inference, not training
Whatever you train must run on **CPU, inside the 10-minute match bank**, in a sandbox with **no internet and no GPU**.
- LightGBM model or small MLP → runs in microseconds on CPU. ✅
- Giant transformer → does not fit. ❌

"Small model trained on free compute" isn't a compromise here — it's required by the runtime.

---

## Step 5 — How the model ships into your agent

1. **Serialize** the trained model: LightGBM native format, a PyTorch `state_dict`, or export to **ONNX** for portable CPU inference.
2. **Bundle** it inside `submission.tar.gz`.
3. In `main.py`, **load it once at module import** (the pregame processing window), cache it in a global.
4. During decisions, feed the current state's feature vector in → get a win-probability out → use it as the **leaf evaluation** when you step the search, or as a **tiebreaker** in the rule agent.

The model is **a file you load**, not a service you call.

---

## The beginner roadmap, in order

1. Write the **replay parser** → produce the `(state_features, won?)` dataset. *Most of your time goes here.*
2. Train a **LightGBM value model**. Confirm it beats a coin-flip on held-out games.
3. Wire it in as **leaf eval / tiebreaker**. **A/B test on the real ladder** — not on a local metric (local measures mislead in this competition).
4. If it helps, optionally add a **behavioral-cloning policy** for move ordering.
5. Only then, and only if motivated, explore **RL** — expecting it may not beat steps 2–4.

---

## Honest reality checks

- **Imitation caps at what you imitate.** A value model from average games predicts average outcomes — filter hard for strong players.
- **Distribution shift.** Your model trains on others' game states, but your agent steers into new states it never saw, where predictions get shaky. Value functions tolerate this better than behavioral cloning — another reason to start with the value model.
- **This may not beat your tuned heuristic.** Ladder evidence says learned approaches have lost to clean rule agents here. Treat the model as a measured experiment **layered on top of a working heuristic baseline**, validate every version on the actual ladder, and keep the simple agent as your fallback. The model earns its place only if the ladder says so.

---

## Next step

The single thing that most determines success is the **state-feature encoding** — how you turn a game state into the numeric vector `X`. Build it from the `CardData` and observation fields already mapped (prizes, energy, board, discard, ex/megaEx flags, types, attack costs/damage). That's where a beginner either wins or wastes weeks.
