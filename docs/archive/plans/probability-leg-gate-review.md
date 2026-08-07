# #175 — the Probability Leg: the merge gates

Merge evidence for **#175** (ADR-0074), owed by ADR-0072 decision 2: every mid-build swap owes both
deterministic gates, per-frame, with every flip ruled by the user before merge. Companion to
`attach-decider-swap-review.md` / `evolve-decider-swap-review.md`.

**Verdict: both gates PASS.** The Decision Gate is byte-identical to baseline (the change moves zero
decider frames). The Discrimination Gate passes with one improvement, one user-ruled held-out
regression, and a neutral-to-positive aggregate.

Baseline `003b1b7` (the last commit before the first #175 feature commit) against `aefc1c7`.

## Decision Gate — PASS ×3, identical to baseline

Each sweep was run at BOTH revisions, because a sweep grades the decider against the legacy scoring
on a fixed comparison — its flip count is standing state, not this branch's doing, and only a
baseline run can tell the two apart.

| sweep | frames | flips | FIX | REGRESSION | verdict | vs baseline |
|---|---|---|---|---|---|---|
| attach | 133 | 29 | 22 | **0** | PASS | identical |
| evolve | 4 | 4 | 4 | **0** | PASS | identical |
| promote/retreat | 16 | 16 | — | 0 gated (1 held out, `owner=#165`) | PASS | identical |

Every tally matches byte-for-byte across the two revisions. **#175 moved zero decider frames.**

## Discrimination Gate — PASS

`tools/train/leaf_lab.py capture` / `diff`, all 267 scorable frames.

```
improvements (MISS -> OK):  83966336|0|decision|27
regressions  (OK -> MISS):  85164605|1|decision|41   [held out, owner=#145]
added 0 · removed 0
gated on 266 frame(s), held out 1
GATE: PASS
```

| metric | baseline | HEAD |
|---|---|---|
| leaf_correct (lenient) | 190 | 190 |
| leaf_correct_strict | 34 | **35** |
| avg_top_tie | 3.112 | **3.086** |

Strict correctness up one, average tie size down — the change discriminates very slightly better
across the corpus, which is the direction a term that adds information should move.

**The baseline had to be re-captured mid-review**, after `83966336-27` was re-ruled (below): the
first capture measured a different question, and diffing against it would have compared two
different ground truths.

## Flip 1 — `83966336|0|decision|27`: the ground truth was wrong

Originally `REGRESSED`; after re-ruling, an **improvement**.

The record said `correct=[1]` Lillie's Determination, rationale *"You used Petrel to grab a supporter
that we already have in hand. waste"*. **User ruling 2026-07-27: Petrel is the right first action —
what was wrong is WHAT it fetched.** The line is Petrel → fetch **Air Balloon** → attach to the
Active Riolu → retreat → promote Solrock, holding Lillie's for next turn (still exactly 6 prizes, so
it still draws 8).

Verified at source for that board:

- Petrel searches any **Trainer**; Pokémon Tools are Trainers, so Air Balloon is a legal target.
- Air Balloon reads −{C}{C} retreat; Riolu's printed retreat is 2 with **zero** Energy attached, so
  the retreat is otherwise unpayable — the Balloon is what makes it free.
- Their bench is three Solrocks with **no Lunatone**, so Cosmic Beam *"does nothing"*. Their only
  live line is Riolu → Mega Lucario ex + 1{F}, Aura Jab 130.
- Aura Jab 130 KOs Riolu (80) **and** Solrock (110) — the retreat does not dodge a KO, it chooses
  which card eats it. Solrock costs 1 prize and zero attached Energy and we hold a second; Riolu is
  the Mega Lucario ex base.

Measured on that board: leaving Riolu Active exposes it on **63.9%** of their next turns; after the
retreat, **~18.6%** (they need the KO *and* a Boss's Orders to gust it back). The Lillie's-now gamble
the old ruling implied is **48.0%** to reach any same-turn KO — worse than a certainty that costs
nothing.

Re-ruled in `data/corrections/mega_lucario_20260705_484d957/corrections.jsonl` (`aefc1c7`):
`correct=[0]`, category `slow_setup`, with a `turn_plan`. The identity key was deliberately left at
`decision|27` — `scope`/`subject` are the ADR-0049 identity, so turn-scoping would mint a new key
(invalidating the pinned baseline) and require a `span` every other turn-scoped record carries. The
turn-planner attribution (**#165**) lives in the rationale.

**Honest caveat, recorded because it matters:** HEAD ranks Petrel top for the *wrong reason* — a
27.7% Ultra Ball line the sim happened to find, not the Air Balloon plan. Right option, wrong
argument. Nothing in code computes the ruled reasoning; that is #165's gap, and the `turn_plan`
captures the intent so it is not lost.

## Flip 2 — `85164605|1|decision|41`: near-indifferent, residual owned by #145

Held out, `owner=#145`, ruled 2026-07-27. Fixture:
`tests/fixtures/corrections/ms_item_over_supporter_indifferent_f41.json`.

The correction (`correct=[3]` Mega Signal over Salvatore — Item before Supporter) **is valid**, and
the user confirmed it. It is also immaterial on this board: *"since we will not play a supporter this
turn otherwise, it doesn't really matter."*

The leaf agreed and always did — **nine of eleven options tie at exactly 2207.50** pre-change
(`correct_is_unique_top: false`), because the turn converges on the same 2-prize double-KO regardless
of first action: evolve a Staryu → Mega Starmie ex, free-retreat Cinderace (retreat 0) into the
3-{W} body, Jetting Blow 120 KOs Kadabra (80 HP) and its 50 bench rider *exactly* KOs an Abra (50 HP).

Why the flip is a metric artifact rather than a behaviour regression:

- **The correct option's value is identical before and after** (2207.50). What moved is a sibling.
- Ties break by option order, so the leaf's real pick was index 0 — Salvatore, the tagged blunder —
  **both before and after**. The committed action is wrong identically either way; `OK` at baseline
  came only from leaf-lab's lenient shared-max rule.
- leaf-lab scores the develop-rung leaf, but this frame's live decision came from the *planner*
  (`"planned": {"step":[0], "goal":"ko_for_prizes"}`), so the row diagnoses a rung that did not
  make this call.

**What #175 actually changed here**, traced at `e1fbb8d` vs `aefc1c7`: inside the Lillie's branch the
sim stopped paying Ultra Ball's cost with two {W} Energy and instead discarded a Pokégear, attaching
the saved Energy to the benched Staryu — strictly better play, readiness 157.5 → 172.08, same 2
prizes, same survival.

That surfaced the real residual, which is **#145's**: `_readiness` ranks a benched Staryu carrying
1{W} (172.08) **above** a benched second Mega Starmie ex with none (157.5). That is the leaf's own
currency calibration; #145 owns `_readiness` (`planner.py:3119`) and the currency audit. Deleting the
`owner` returns the frame to gating (ADR-0072 decision 4).

## Reproducing

```
python tools/train/probes/attach_decider_sweep.py
python tools/train/probes/evolve_decider_sweep.py
python tools/train/probes/promote_retreat_decider_sweep.py
python tools/train/leaf_lab.py capture --out <baseline>.json      # at 003b1b7
python tools/train/leaf_lab.py diff --baseline <baseline>.json
```

Supporting probes written for this review: `tools/train/probes/anchor_rate.py` (how often the deck
tracker is un-anchored — the residual #175 can act on at all) and
`tools/train/probes/rung_scale.py` (the ADR-0074 decision-5 commensurability measurement).
