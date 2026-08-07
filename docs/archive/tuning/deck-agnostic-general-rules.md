# Deep dive: why "98 % general" carried Mega Starmie but not Mega Lucario

**Round:** 2026-07-05 · **Trigger:** *"Mega Starmie plays great (98 % general rules), Mega Lucario
makes very basic blunders. Shuffle / fetch should already be covered — deep-dive how general
strategies can be made more deck-agnostic."*

This is the write-up of that dive. Two findings: one **measurement** bug in how `/blunder-buster`
decides what is "open", and one **doctrine** gap in a general rule that looked deck-agnostic but
wasn't. The doctrine gap is fixed this round; the measurement finding is a standing lesson.

---

## TL;DR

- The user's instinct was right on both halves. **Shuffle and fetch *are* covered** — the retest
  confirms Lucario no longer shuffles Riolu away (`hold-line-piece-dont-shuffle`) or refetches a
  discarded base. The residual "very basic blunder" was a *third* thing: **which Basic to develop.**
- The general rule `develop-a-basic-in-setup` develops *a* Basic but is **indifferent to which one**.
  On a deck whose Basics are mostly the wincon line (Starmie: Staryu is the line) that indifference is
  invisible. On a **support-heavy** deck (Lucario: Riolu is the wincon base, but Solrock / Lunatone /
  Makuhita are all competing Basics) the pick fell to an **option-index tiebreak** — Riolu never got
  benched because it sat lower in the menu. That is the deck-agnostic lesson: **general
  develop/fetch/discard rules that quantify over "any card of kind X" must be made *line-aware*.**
- Separately: the pipeline said the open set was **empty** while the agent was still blundering. That
  is a real blind spot in the **W-route "satisfied"** measure — it compares two tagged options by raw
  linear score and never runs the real `decide()`. Nine corrections were "W-route satisfied"; a
  real-Pilot re-measure showed **two CRITICAL ones were not actually fixed.**

---

## Finding 1 — the measurement blind spot (why "0 open" was wrong)

`/blunder-buster`'s open set is `open[]` (missing-hypothesis proposals) + `UNSATISFIED` lines, both
computed by the **W-route featurizer** (`tools/train/tuner/featurize.py`). For each correction it:

1. runs `pilot.explain(obs)`, reads the **fired-Hypothesis set** and **raw score** for the tagged
   `chosen` and `correct` options only;
2. if the fired sets differ → a **ranking constraint** `score(correct) > score(chosen)` fed to the
   weight fit; "satisfied" iff current weights already rank it that way.

The blind spot: **"W-route satisfied" only means the two tagged options rank correctly in a pairwise
raw-score comparison. It never asks what `decide()` actually returns.** `decide()` (`pilot.py
_evaluate`) does three things the W-route ignores:

- **Lethal Solver / Turn Planner short-circuits** — a locked line returns before scoring (already
  handled: `live_trace.lethal` / `planned`).
- **`_finish_turn_last` tier re-sort** — options are re-ordered into tiers (tier-0 develop … tier-4
  attack) *after* scoring; the pick is the top of the **lowest non-empty tier**, not the top raw
  score. The code comment says it outright: *"decide()-only ordering nicety, W-route-invisible, never
  enters the weight fit."*
- **multi-pick / select-nothing resolution** — greedy grab, optional-pick take-fewer.

So a correction can be "W-route satisfied" yet `decide()` still plays the blunder — or, conversely,
`decide()` can already play the fix while the W-route calls it UNSATISFIED (a develop that scores
*below* the attack it out-tiers). **Both directions happened this round.**

### The re-measure (the fix for the blind spot: always retest through the real Pilot)

Re-running `retest(correction, real_pilot)` — which calls the full `explain()`/`decide()` — over all
9 "W-route satisfied" Lucario corrections:

| result | corrections |
|---|---|
| genuinely fixed by `decide()` | f29; 83966336 f9/f14/f27/f44; 83967841 f14/f17 (7) |
| **still blundering (both CRITICAL)** | **83661652 f30, f40** (2) |

The two survivors were exactly what the user was watching. **Lesson: the W-route is a fast router,
not a resolution oracle. Every correction — especially the "satisfied" ones — must be confirmed
through the real `decide()` before it is called resolved.** The 20260705 sibling round already learned
half of this (its test docstring notes two fixes "depend on a `_finish_turn_last` sequencing
THRESHOLD, not a ranking margin, so they gate [as replay tests] rather than via the weight fit"); this
round generalises it.

---

## Finding 2 — the doctrine gap (a general rule that wasn't deck-agnostic)

`develop-a-basic-in-setup` (`baseline/baseline_bench.py`, +12) fires on **every** startable Basic in
setup. On the ep83661652 turn-5 board (Active Lunatone, bench just Meowth ex, hand holding Riolu +
Solrock/Makuhita/Lunatone) all the Basics tie at **12**:

```
[1] Play Solrock   score 12   develop-a-basic-in-setup:12
[2] Play Riolu     score 12   develop-a-basic-in-setup:12      <- the wincon base
[3] Attack …       score 30   (tactical)
```

`decide()` out-tiers the attack (develop is tier-0, attack tier-4 — good), but among the **tied**
develops it keeps score order and takes the **lowest option index**. Riolu's menu position, not its
role, decided it — so the wincon base never hit the bench. Three CRITICAL corrections
(f33 / f40 / f44) are all this one bug.

### The fix — make the develop rule line-aware

The signal already existed: `Context.card_is_line_preevo` = "this card is a non-payoff member of a
declared Strategy `Line`" (`pilot._line_preevo_set()`). It is exactly the wincon base and nothing
else — `{Riolu}` for Lucario, `{Staryu}` for Starmie, `{Dreepy}` for Dragapult. Crucially it is
**False for off-line Basics** (Solrock, Lunatone) *and* for a **secondary** evolution base that is not
a declared Line (Makuhita → Hariyama is not in `strategy.lines`, so Makuhita is False too).

```python
Hypothesis(
    id="develop-the-wincon-base-first",
    when=lambda c: not c.board.line_ready and c.option_type == _PLAY
    and c.card_is_line_preevo and c.board.my_bench < _BENCH_MAX and "opener" not in c.tags,
    weight=6, status="assumed")
```

A **faint tiebreaker** (band 0–5, "all else equal, lean this way"): Riolu now scores 18 vs the other
Basics' 12, so it leads the develop tiebreak, while still sitting below a real attack (the tier system,
not the weight, keeps develop-before-attack). **No-op** for a deck whose only setup Basic already is
the Line base (Starmie). Retest: f33/f40/f44 → Play Riolu, all fixed; Verifier `regressed=[]`.

---

## The generalisable lesson

The deck-agnostic-ness of a general rule is not "does it avoid hard-coded card ids" — Lucario's rules
already did. It is **"does it quantify at the right granularity."** `develop-a-basic-in-setup`
quantifies over *Basics*; the decision it governs needs *line role*. The fix wasn't a new signal or a
deck override — it was refining the general rule to read a **role/line signal that already existed.**

A checklist for auditing a general rule against a new deck (what to look for in `/deck-align` and the
next `/blunder-buster`):

1. **Does the rule pick among a SET (which Basic / which card to fetch / which to discard), or a
   single yes-no?** Set-pickers are where indifference hides. A yes-no rule (`keep-a-bench`) can't
   mis-rank; a set-picker (`develop-a-basic`, `fetch-*`, `keep-*-at-discard`) needs a **priority key**
   or it falls to option index.
2. **Is the priority key a role/line signal, not a card kind?** Prefer `card_is_line_preevo`,
   `card_is_wincon`, `roles`, `top_fetch_priority_id` over "is a Pokémon" / "is an Energy".
3. **On a support-heavy deck, do off-line Basics/Trainers out-compete the wincon pieces on this
   rule?** Starmie hides this (its Basics *are* the line); Lucario/Dragapult expose it (many Basics,
   one line).
4. **Does the decision run through `_finish_turn_last`, the Lethal Solver, or the Planner?** If so the
   W-route can't measure the fix — gate it with a **real-`decide()` replay test**, not the weight fit.

The fetch side already internalised (1)–(2): `fetch-the-engine-first`, `prefer-wincon-line-piece`,
`fetch-energy-when-starved` are all priority-keyed. The **develop** and **discard** sides were the
laggards; the develop side is closed this round. (Discard is currently sound for Lucario —
`keep-line-base-at-discard` protects the wincon base — but is a candidate for the same
priority-key audit on the next support-heavy deck.)

---

## Provenance

- Rule: `src/common/strategy/baseline/baseline_bench.py` → `develop-the-wincon-base-first`.
  **Both are gone.** The rung was deleted by ADR-0086 (its job is the Deploy Marginal's
  assignment relevance), and the module itself by Issue #261 item 2d once `keep-a-bench` —
  its last member — went with ADR-0096 decision 2. This round's finding stands as the record
  of why a flat develop rung could not rank the wincon base; the fix now lives in the
  equation.
- Gate: `tests/strategy/test_blunder_20260703_develop_wincon_base.py` (3 replay fixtures + negative).
- Run report: `docs/tuning/runs/mega_lucario_20260705-130130.md`.
- Ledger: `data/corrections/reviewed.json` (f30/f33/f44 covered/rule-fixed, real-Pilot confirmed).
- Method: `docs/tuning/methodology.md` (W-route vs H attribution; the retest closes the loop).
