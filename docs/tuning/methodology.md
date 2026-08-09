# How the agent learns from its mistakes — the tuning methodology

This document explains, from first principles, how a flagged mistake in a game becomes a concrete
change to the agent. It is written to be readable without machine-learning background, and to name
the formal techniques used so the process can be defended to a professional data scientist. Each
`/blunder-buster` run also writes a short, plain-language report under
[`docs/tuning/runs/`](runs) — this page is the "how it works" those reports link to.

See also: [blunder-tuner.md](../blunder-tuner.md) (the implementation), [weights.md](../weights.md)
(the weight scale), and [ADR-0009](../adr/0009-training-methodology.md) / [ADR-0017](../adr/0017-corrections-compile-to-hypotheses.md)
(the design decisions).

> **Current correction policy (supersedes the legacy W/H authoring text below).** Corrections no longer
> create or tune decision rungs, Hypotheses, or `when()` rules. The replay's Composer telemetry is the
> diagnostic substrate: first repair transition coverage and end-state differencing; then repair
> within-turn sequence enumeration and commit ordering. A `state_value` equation may change only when
> the trace proves both competing transitions were modelled and identifies the specific value family
> responsible for the wrong ordering. This keeps correction work focused on the differencer and turn
> sequencer rather than compensating for a missing sequence with another local rule.

---

## 1. The loop in one picture

```
play a game ─▶ download replay ─▶ flag a Decision as a blunder + write the better move (a "Correction")
     ▲                                                   │
     │                                                   ▼
 ladder A/B  ◀── ship a new build ◀── tune: turn Corrections into ── weight changes (automatic)
 (the judge)                                            └────────── new rules   (human-authored)
```

The deliverable of the *Strategy* competition is the agent's **decision-making approach**, so the
whole point of this loop is to make that approach better in a way we can explain and trace.

---

## 2. How the agent makes one decision

At every choice point the engine hands the agent a list of legal **options** (play a card, attach an
energy, retreat, attack, …). The agent gives each option a **score** and picks the highest
(`argmax`). The score is a simple sum:

$$\text{Score}(o) \;=\; \underbrace{\sum_{i} w_i \cdot \text{fired}_i(o)}_{\text{positional: the rules}} \;+\; \underbrace{\text{tactical}(o)}_{\text{combat math}}$$

- A **Hypothesis** is a hand-written rule with a trigger and a weight, e.g. *"during setup, prefer
  playing energy-acceleration"* (`use-acceleration`, weight `+25`). $\text{fired}_i(o)$ is `1` if
  rule $i$'s trigger matches option $o$, else `0`. So the left term just **adds up the weights of
  the rules that fire** on that option.
- $\text{tactical}(o)$ is the combat value (damage, a knockout = `1000`, …) computed by the engine.
  It is fixed, not learned.

This is a **linear model**: the score is a weighted sum of binary features. That single fact is what
makes the learning below tractable — everything reduces to choosing the weights $w_i$.

> **One non-additive exception — tiered turn sequencing (`_finish_turn_last`).** The engine
> re-presents the open turn menu after each non-ending action, so the whole turn still happens — and
> the Pilot's final step **reorders** the argmax to take the most informative, reversible actions
> first and the irreversible ones last, at a single-pick MAIN menu: **tier 0** free informative
> development (draw/search, fill the Bench, evolve a benched Pokémon, play a Pokémon, an attach/gust
> that unlocks a KO — any option a rule scored `> 0`) → **tier 1** the one-per-turn **Supporter**
> (after the free Item digs, which may upgrade which Supporter you commit) → **tier 2** the blind/costly
> commitments (the Energy attach, a `cost_discard` search) → **tier 3** a `shuffle_hand` Supporter (it
> nukes the hand, so attach first) → **tier 4** the turn-ending attack (plus Retreat / End /
> non-beneficial). A knockout is never forfeited (an Evolve-of-the-Active drops to the last tier when a
> KO is on the menu; the KO outscores everything there). This is a selection layer **the weight fit does not model**: it reasons about the additive
> score above, so it will flag a sequencing-fixed (or tie-resolved) Correction as `UNSATISFIED` /
> propose a rule for it even though the real `decide()` already chooses correctly. (It also made the
> old `build-before-attack` / `dont-chip` chip-penalty weights obsolete — they were removed.) **The
> authoritative measure of whether a Correction is fixed is the real Pilot `decide()` / the Verifier —
> not the W-route count.** When in doubt, replay the agent, don't read the additive margin.

The weights live on a documented, legible scale ([weights.md](../weights.md)): `10–20` = a normal
preference, `30–50` = strong doctrine, and so on. They start as **authored seeds** (an expert prior)
and are refined by the process below.

---

## 3. A Correction is one labelled comparison

When we review a replay and flag a blunder, we record a **Correction**: at this exact game state the
agent **chose** option `c`, but the **correct** option was `k`. In learning terms this is a single
**pairwise ranking label**:

$$\text{Score}(k) \;>\; \text{Score}(c) \qquad\text{("correct should outrank chosen")}$$

Each Correction also stores the rationale (why) and a self-contained snapshot of the state, so it
remains usable long after the replay is gone (see [ADR-0015](../adr/0015-correction-schema.md)).

### 3.1 …but only when its **Scope** is one Decision

A Correction carries a **Scope** ([ADR-0049](../adr/0049-corrections-carry-a-scope-decision-turn-or-match.md)):
`decision` (the default, and everything below in §4–§6), `turn`, or `match`. Only a decision-scope
Correction is a pairwise ranking label, because only it names a *better option at one state*.

A turn or match Correction is a **plan-layer** judgment: the individual picks may each have been
locally defensible and the *set* — the ordering, the game plan — was wrong. There is no inequality
$\text{Score}(k) > \text{Score}(c)$ to write down, and no weight that could satisfy one. So the
Tuner short-circuits a scoped Correction **before** it can become a constraint (`tuner/run.py`) and
routes it straight to the open worklist that `/blunder-buster` drains. This is load-bearing: without
it, the fit would try to repair a sequencing error by moving a Tier-0 weight, which is exactly the
failure §5 and the `forgo-KO` refutations exist to prevent.

What a scoped Correction *does* carry:

- Its **Span** — the Decisions it covers. A turn's Span keeps each Decision's `obs`, so
  `tuner/retest.py::retest_span` can re-drive the turn under a candidate Pilot and report the
  **first divergence**. Everything after that point is off-policy (those `obs` describe a board the
  new Pilot would never have reached) and is reported as such rather than guessed at. A match's
  Span keeps per-turn headers and the `game_plan`, and is never re-driven — its gate is the ladder.
- An optional **Anchor prescription**. A turn Correction *may* still name a `correct` option, at the
  Anchor only; giving it asserts the Anchor is the first divergent Decision. When present, the
  fired-rule diff of §4 is still computed — but recorded as **information** for routing, never fed
  to the fit. When absent, `retest` reports `fixed: None`: there is nothing asserted to check.

---

## 4. Where does the fix belong? — attribution (W vs H)

Before changing anything we ask **what kind of fix this is**, by replaying the agent on the state and
looking at *which rules fired* on the chosen vs the correct option:

- **The fired rules differ → a weight problem (route "W").** The two options are already
  distinguished by existing rules; we just have the *relative weights* wrong. A weight change can
  re-order them.
- **The fired rules are identical → a missing rule (route "H").** No re-weighting can ever separate
  two options that look identical to every rule. The agent is *blind* to the distinction and needs a
  **new Hypothesis**. (If only the combat term differs, it's `tactical` and out of scope here.)

This split matters: weight-tuning is automatic and safe; authoring a new rule is higher-leverage but
needs a human. Formally, the W route is a **linear ranking (learning-to-rank) problem**; the H route
is **feature engineering**.

---

## 5. The W route — fitting the weights

### 5.1 Each Correction becomes a linear inequality

Because the score is linear, the requirement $\text{Score}(k) > \text{Score}(c)$ becomes, after the
shared rules cancel:

$$\sum_i w_i\,\Delta_i \;+\; \Delta\text{tactical} \;>\; 0, \qquad
\Delta_i = \text{fired}_i(k) - \text{fired}_i(c) \in \{-1, 0, +1\}$$

$\Delta_i = +1$ means rule $i$ fired only on the **correct** option (raising its weight helps);
$-1$ means it fired only on the **chosen** option (lowering it helps). We call the left-hand side the
**margin**. "Satisfied" means margin $> 0$.

**Multi-pick selects** (a Discard-2, a multi-grab) are diffed on the **set difference**: $k$ = the
first option the human picked that the agent didn't, $c$ = the first the agent picked that the human
didn't. (Diffing position 0 of each list made any correction whose lists share that element — e.g.
chosen $[0,1]$ vs correct $[0,2]$ — an empty-delta constraint, unsatisfiable by construction: a
phantom UNSATISFIED no weight could ever fix, ep83454549 f36.)

### 5.2 The loss we minimise

We want weights that satisfy as many of these inequalities as possible while staying close to the
expert seeds. We use the **hinge loss** (the same loss as a Support Vector Machine), which charges a
penalty whenever the margin falls short of a small target $\tau$ (we use $\tau = 1$, to keep a
satisfied comparison off the knife-edge), and an **L2 regularisation** term that pulls every weight
back toward its authored seed:

$$J(\mathbf{w}) \;=\; \underbrace{\sum_{\text{corrections}} \max\!\big(0,\; \tau - \text{margin}\big)}_{\text{ranking loss (hinge)}}
\;+\; \underbrace{\tfrac{\lambda}{2}\sum_i (w_i - w_i^{\text{seed}})^2}_{\text{stay near the expert prior}}$$

This is exactly a **soft-margin, L2-regularised linear ranking model** (a RankSVM-style objective).
Two intuitions to carry:

- The hinge term rewards satisfying Corrections.
- The regularisation term is **quadratic**, so it is cheap to nudge several weights a little but
  expensive to move one weight a lot. This is the single most important property — see §5.5.

$\lambda$ (in code: `reg`) is the **conservatism knob**. High $\lambda$ = trust the expert seeds and
move little; low $\lambda$ = trust the data and move freely.

### 5.3 How we minimise it — a regularised structured perceptron

We do not need a heavy optimiser. We use a **structured perceptron** (sub-gradient descent on $J$),
which is a few lines of arithmetic and has no external dependencies. Starting from the seeds, repeat:

1. For every Correction still violated (margin $< \tau$), nudge each discriminating weight in the
   helpful direction: $w_i \leftarrow w_i + \eta\,\Delta_i$ (learning rate $\eta = 1$). *(This is the
   sub-gradient of the hinge term.)*
2. Pull every weight back toward its seed: $w_i \leftarrow w_i - \eta\,\lambda\,(w_i - w_i^{\text{seed}})$.
   *(The sub-gradient of the regularisation term.)*
3. Clamp every weight into the legible band $[-100, 100]$ (a hard backstop; `>100` is reserved for
   combat-scale weights — [weights.md](../weights.md)).

Without the regularisation in step 2, a raw perceptron on **contradictory** data never settles and
drives a weight to absurd values (we actually saw `power-up-attacker` reach `156`). With it, a
perpetually-violated push settles at roughly $w^{\text{seed}} + (\text{push})/\lambda$ — bounded.

### 5.4 The pocket — return the best, not the last

On contradictory data the iteration **oscillates** around the boundary, so the *last* weights it
produces can be worse than ones it already passed through. So we keep a **pocket**: remember the
weights with the lowest objective $J$ seen across all iterations, and return those. (This is the
classic **pocket algorithm** for the perceptron on non-separable data.) Without it, satisfiable
Corrections were silently being reported as unsatisfiable.

### 5.5 The adoption gate — ship only what earns it

Even a bounded fit can be a bad idea. The fitted weights are written to `tuned.json` **only if they
satisfy strictly more Corrections than the authored seeds already do.** Otherwise the movement bought
nothing (or merely traded one satisfied Correction for another) and we keep the expert priors. This
is why an empty `tuned.json` (`{}`) is a normal, honest result: it means *this batch of mistakes is
not fixable by re-weighting — it needs new rules.*

Anything the shipped weights still cannot satisfy is reported as **unsatisfied** — a precise list of
Corrections that are either mutually contradictory or genuinely need a new rule (route H).

### 5.6 Why both the regularisation and the gate?

They guard different failure modes. The quadratic regularisation makes the optimiser **prefer** small,
spread-out moves over collapsing one doctrine weight. The gate is the **veto**: if the only way to
satisfy a couple more Corrections is a large, doctrine-gutting move, the gate refuses and surfaces
those Corrections for a human to turn into a rule. The competition's **ladder A/B test is the final
arbiter** of whether a shipped change actually helps — the tuner never self-certifies.

---

## 6. The H route — authoring a new rule

When attribution says "missing rule," the tuner emits a **proposal**: the rationale, a seed weight in
the right band, and a human-readable trigger sketch. A human (assisted by the `/blunder-buster`
skill) then writes the executable trigger `when(ctx)` against the agent's feature catalog, and it
must clear two gates before shipping:

1. **The Verifier** (`tools/train/tuner/verify.py`): inject the candidate rule, **re-fit the weights
   over all Corrections**, and accept only if (a) it satisfies its target cluster and (b) it does not
   regress any Correction that was already satisfied. *(Confirmation testing + regression testing.)*
2. **Retest** (`tools/train/tuner/retest.py`): re-derive the decision with the new rule and compare
   it, in the same telemetry format the live agent emits, against what the shipped agent actually did
   — showing `chosen before → after`, the margin, and the lifted `lethal`/`planned` layer verdicts
   (before → after). *(A concrete before/after proof.)*

Then a human reviews the diff and commits. No executable rule is ever auto-committed.

**Layer routing (not weight-tunable at all).** A Correction whose live trace carries a non-null
`lethal` (ADR-0030) or `planned` (ADR-0031) verdict was decided by a layer that **short-circuits**
the scored pipeline — the fired features and weights never chose. Neither route above applies: the
fix is code in that layer (`planner.py`: the win rung for `lethal`, the heuristic rungs for
`planned` — one module since ADR-0037) gated by a fixtured regression test, and the
tuner only *surfaces* these (`[LETHAL]` / `[PLANNED]` line tags, `lethal_locked` /
`planner_committed` snapshot flags) so `/blunder-buster` routes them out of rule authoring.

**Parallel-mode join (`union_verify`).** When `/blunder-buster` fans clusters out to parallel agents,
each cluster clears the per-cluster Verifier *in isolation* — but isolated passes don't compose:
cluster A's rule can regress cluster B's Correction once both ship. The **join** therefore re-runs a
single `union_verify` (`tools/train/tuner/verify.py`): inject **all** authored rules at once against a
**seeds-only** baseline and reject the round if any previously-satisfied Correction regressed. It is
the same re-fit-and-no-regression logic as gate 1, lifted from one candidate to the union — with two
guards that keep the base-vs-union delta honest: no duplicate authored rule ids (a dict-merge would
drop one and the pilot would double-weight it), and no authored rule already present in the baseline
(which would mask its own interference). The full `pytest` suite at the join covers over-firing on
non-Correction states the corpus can't see.

---

## 7. A worked example — `accel-into-main` and the Ignition energy

This is the clearest illustration of W-vs-H and why the gate matters.

**The symptom.** Five Corrections flag the same kind of blunder: the agent attached **Ignition
Energy** to **Cinderace** when it should have attached a plain **Basic {W} Energy** (Ignition Energy
is discarded at end of turn and is precious — it powers the Mega Starmie ex line, where three
colourless on an Evolution fires Nebula Beam in one attach).

**Why the tuner wanted to gut a doctrine.** The rule `accel-into-main` ("rush energy onto the line")
fires on the *Ignition→Cinderace* option (both are tagged `accel_source`) but **not** on the
*Basic→Cinderace* option. So it is the discriminating rule, and the only weight lever to make
"Basic ≻ Ignition" is to **lower `accel-into-main`**. The fit duly tried to drop it from `30`
(strong doctrine) all the way to `~2` (a faint tiebreaker).

**Why that is wrong, and what caught it.** `accel-into-main` is good general doctrine; collapsing it
to satisfy five narrow energy-choice cases is over-fitting. The quadratic regularisation made that
collapse expensive, and the **adoption gate refused it** (it satisfied only two more Corrections at
the cost of gutting a doctrine), instead **listing those five Corrections as "unsatisfied — needs a
rule."** That is the system correctly telling us this is a **route-H problem**.

**The rule we authored (`dont-waste-discard-energy`).** The real insight is that a discard-at-end-of-turn
Energy is only worth attaching if the Pokémon it goes on **attacks that same turn** — otherwise it
just vanishes. So the rule penalises attaching such an Energy (identified by a universal `discard_eot`
Function Tag, not a card id) when it would be wasted: onto a **benched** Pokémon (can't attack this
turn), on the **first turn going first** (can't attack at all), or when a **reusable Basic is already
in hand** (use that and save the discard Energy) — *except* onto the **win-condition**, where its bulk
acceleration is the point. Because it keys on the tag plus deck-agnostic board signals, it lives in the
General Strategy and every future deck running such an Energy inherits it. Authoring it freed
`accel-into-main` to stay healthy (30 → ~27 after a normal fit, not gutted to ~2). It deliberately does
**not** fire on `Ignition → active Cinderace with no Basic in hand`, preserving the deck's Turbo Flare
line (attack to search three Basic Energy onto the Bench).

**The neighbouring pattern.** Separately, eight Corrections flag retreating Cinderace away during
setup ("keep Cinderace active — we need it to attack and accelerate three energy to the bench"). That
pattern is already covered by the `hold-position-in-setup` Hypothesis, so it does **not** appear as
unsatisfied. Same deck theme, different mechanism — a good example of reading the reports correctly.

---

## 8. Glossary (and the formal names to use with a data scientist)

| Term here | What it means | The formal name |
|---|---|---|
| Hypothesis | a weighted if-then rule that fires on an option | a binary **feature** with a learned **weight** |
| Score | weighted sum of fired rules + combat value | a **linear scoring function** |
| Correction | "k should beat c at this state" | a **pairwise ranking label** |
| margin | $\sum w_i\Delta_i + \Delta\text{tactical}$ | the ranking **margin** |
| the fit | nudging weights to satisfy Corrections | **structured perceptron** / sub-gradient descent |
| ranking loss | penalty for an unsatisfied Correction | **hinge loss** (soft-margin / SVM) |
| `reg` ($\lambda$) | pull toward the expert seeds | **L2 regularisation** (a Gaussian prior on weights) |
| the pocket | return the best iterate, not the last | **pocket algorithm** (perceptron on non-separable data) |
| adoption gate | ship weights only if they satisfy more | a **validation/acceptance criterion** |
| Verifier | re-fit + no-regression check for a new rule | **confirmation + regression testing** |
| ladder A/B | which build actually wins more games | the **evaluation metric** (the ground truth) |

One-sentence summary for a reviewer: *"Decisions are scored by a linear model over hand-authored
rule-features; corrections are pairwise ranking labels; weights are fit by an L2-regularised
soft-margin structured perceptron with a pocket, and shipped only behind an acceptance gate, with a
ladder A/B test as the final evaluator."*
