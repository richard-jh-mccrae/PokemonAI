# ADR-0085 — Snipe is a CATEGORICAL RELEVANCE instrument too: the fold collapses the additive rung stack into one [0,1] scalar under hard gates, not onto the prize marginal

**Status:** Accepted (grilled 2026-07-29, `/grill-with-docs` on Issue #188 — **thirteen locked
decisions**, one of them taken and then reverted on measurement and recorded as such). Build =
Issue #188, **rechartered** by decision 1 from *"fold the snipe rungs onto the unified marginal"* to
*"build the Snipe Relevance instrument"*. Extends ADR-0080's relevance shape to a second instrument;
supersedes the design doc's S4 snipe bullet and ADR-0078's *"snipe is now the shortest hop"*
consequence. Nothing here is built.

**Renumbered 0082 → 0083 → 0084 across two rebases in one day (2026-07-30).** The number was claimed
at grill time when `docs/adr/README.md` read *next free number 0082*; Issue #211's *a Correction's
ruling lives in its Claim* merged to `main` first (PR #216) and KEEPS 0082 under the standing
first-merged rule. On the **second** rebase — onto Issue #213, which had merged in the interval —
0083 was gone too (#213's *a scaler's variable is named by measurement* took it and survived its own
rebase), so this is **0084**. **Eighth collision in five days**, and this file predicted it in this
very paragraph twice over, which is now the evidence rather than the warning. The number is a rebase
artifact, not an identifier: **cite the issue alongside it** ("ADR-0085, Issue #188"). The convention
earned its keep on the second move — 2 lines in `src/common/CONTEXT.md` reading `ADR-0083, Issue #213`
belong to the ADR that KEPT 0083 and had to be held back while 48 lines across 13 files moved; a
number-only replace would have repointed #213's own references at this ADR.

**Context issues:** Issue #188 (this grill, S4-snipe), Issue #136 (the Value System tracker),
Issue #143 (the un-split original, closed), Issue #187 (S4-deny — the sibling instrument this
mirrors), Issue #199 / ADR-0080 (the deny relevance ruling this extends to a second instrument),
ADR-0076 (the slot-family split that keeps snipe outside the DP), ADR-0078 (the three-scales ADR),
ADR-0044 (the prize-redundant / forced-promotion reads that turn out to be the discriminators),
ADR-0062 (the "no monotone pricing of magnitude alone can separate them" precedent),
ADR-0065 (the fold discipline and the no-fudge rule),
`docs/plans/opponent-value-equation-unification.md` (the design), `docs/plans/snipe-system-handoff.md`
(the standing fold question).

## Context

Issue #188 was chartered to *"fold the snipe rung pile — the last un-folded opponent-read pile — onto
the unified marginal (ADR-0065 fold)"*, fixing the ruled threshold-race frame `83667237-107` on the
way and deleting `baseline_snipe.py`'s folded rungs. Reading the live code and measuring the corpus
found the charter stale in three ways and its central premise refuted.

### The charter's facts, re-measured (19 replayable `DAMAGE(15)` corpus frames, fresh Pilot per frame)

1. **"the 16/18 snipe record"** is now **17/19**.
2. **`83667237-107` is not a live gap — it already passes.** The shipped Pilot picks `[3]` Makuhita,
   the human's `correct`. It was fixed on 2026-07-21 by `snipe_prize_reach` — a Prize-Path
   rider-reach tie-break (`⌈80/50⌉ = 2` rider hits finish the 80-HP body alongside my main KOs) — and
   is asserted end-to-end by
   `test_opponent_choice_reads.py::test_107_snipes_an_on_path_small_not_the_redundant_second_mega`.
   Its `data/corrections/reviewed.json` disposition remains `deferred`, but for the **discard-fuel
   rationale residual**, not for the pick.
3. **Both remaining misses are already-adjudicated non-targets.** `82749168-38` is `refuted`
   (the label itself is wrong); `81905522-75` is the two-identical-Riolu transposition the design doc's
   own risk R3 says *"don't chase it; log it as a known tie."*

**So the fold has no failing frame to fix.** Whatever justifies it has to be architectural.

### The chartered fold is destructive, and the mechanism is deny's failure mirrored

Ranking each frame's *offered options* by the shared marginal alone
(`_opponent_target_rows` → `needs.opponent_target_value`):

```
marginal-argmax agrees with the SHIPPED pick:  6/19   => 13 FLIPS
marginal-argmax agrees with the HUMAN label:   7/19   (shipped rungs: 17/19)
```

`_opponent_target_rows` computes `prize_advance = combat.prize_value(b)`, which its own docstring
calls the *"**if-KO'd** term"*, and `combat.prize_value`'s docstring reads *"Prizes a knockout of this
body yields."* But the bench-snipe rider is **50 damage** in every corpus frame, and in **14 of 19**
frames no offered body can be Knocked Out at all (`board.snipe_ko_available is False`). The marginal
therefore pays a full **3.0 prize-equivalents** to chip a 340-HP Mega Lucario ex that keeps ~85% of its
HP. `survival_shift` compounds it by being 0 in most frames — removing one *benched* body rarely moves
`turns_to_ko_me` — so the marginal degenerates into a **prize-size ranker**, which is precisely what the
snipe rungs are deliberately not.

Gust escapes this because every gust consumption is gated on `_gust_can_ko`
(`doctrine_gust.py:90,299,317,363`). Snipe cannot be, because positional sniping is *defined* by not
Knocking Out. This is ADR-0078 Amendment A's deny failure with the sign flipped: there the shared Δ
**collapsed to ~0** because the Threat-Clock credits a replacement attach every turn; here it
**saturates to the full prize** because it credits a Knock Out that does not happen. Both because the
removal Δ was built for gust, the one instrument that actually removes the body.

The sharpest consequence: on `83667237-107` the marginal ranks the opponent's **redundant second** Mega
Lucario ex top at `3.0` — which is exactly the pre-ADR-0044 blunder pick that fixture records as
`fx["chosen"]`. **A naive fold un-fixes ADR-0044.**

### No magnitude of any shape can carry snipe — the corpus proves it, it is not an estimate

Two magnitude-shaped chip-conversion Δs were built and measured — the "threshold-race" reading the
design doc calls the heart of the phase (ruling 4), in the two natural forms, both monotone in
`(hp, prize, rider)`:

| candidate | form | agrees with human |
|---|---|---|
| prize RATE | `prize_value(b) / ⌈hp_remaining / rider⌉` | 11/19 |
| prize FRACTION | `min(rider, hp) / hp × prize_value(b)` | 10/19 |
| the chartered prize marginal | `prize_advance + phase × survival_shift` | 7/19 |
| **the shipped additive rungs** | — | **17/19** |

The counts are not the finding. **This pair is:**

| frame | Makuhita (673) | Mega Lucario ex (678) | human rules |
|---|---|---|---|
| `82756021-57` | hp 80, prize 1, `t2`, rate 0.50 | hp 340, prize 3, `t7`, rate 0.43 | **the Mega** |
| `83667237-107` | hp 80, prize 1, `t2`, rate 0.50 | hp 340, prize 3, `t7`, rate 0.43 | **Makuhita** |

Identical HP, identical prize values, identical rider, identical turns-to-finish — **opposite
rulings.** No monotone function of those inputs separates them at any exchange rate; the arithmetic is
the same on both sides. What differs is **categorical**: on `107` the Mega carries
`target_prize_redundant` (ADR-0044's body-identity Prize-Path read — it is the opponent's *second*
copy, off my path) and on `57` it does not.

This is ADR-0062's wall, reached again by a second instrument: *"no monotone pricing of magnitude alone
can separate them."* For deny that finding produced ADR-0080's categorical relevance ruling. Snipe
reaches it for the same structural reason both share and gust does not — **the target survives**, so
what matters is whether it *matters*, not how big it is.

## Decision

**1. Snipe is a CATEGORICAL RELEVANCE instrument, not a magnitude one. The fold is real, but its
currency is relevance — not prize-equivalents.** Snipe stops asking *"how much prize value does this
target carry?"* and asks *"does damaging this body actually matter to their plan and to my prize
route?"*

Concretely, and mirroring ADR-0080 decision 3's shape for the sibling instrument:

- **`relevance(target) ∈ [0,1]`**, one scalar per offered target, scaling **one existing** constant.
  No new scale, and no new undetermined constants — the pile's six hand-seeded weights (60 / 45 / 40 /
  30 / 20 / 12) are **deleted**, not normalized into six [0,1] coefficients.
- **Hard gates force it to 0**, above the scalar rather than competing inside it: the Tera card fact
  (`CardStat.tera`; a benched Tera takes NO damage — `docs/rules.md §185`) and the ADR-0044
  redundancy reads (`target_prize_redundant`, `target_promotion_mirage`).
- **`snipe-for-the-ko` and `_snipe_tera_veto` remain structural dominators** outside the scalar, in the
  Tactical layer where they already live.
- The scalar is what `baseline_snipe.py`'s **six target rungs** fold into. The three
  `DAMAGE_COUNTER_ANY` / counter-mover rungs are a different problem (spread knapsack, not target
  relevance) — their scope is a later decision in this grill, not assumed here.

**This is still the ADR-0065 fold** — the pile becomes one number in one currency — and it carries a
correctness payoff rather than only tidiness. The additive stack is a **documented blunder class**, in
`baseline_snipe.py`'s own rationales: `snipe-for-the-ko` records `top-threat 30 + forced-promotion 40 +
evolving-threat 45 = 115` on an un-KO-able Grookey out-voting `60` on the KO-able Applin
(`82754241-45`, and `97-vs-72` in `82753102-63`), and the Tera veto had to be **retired from being a
weight at all** because it *"held only by a 10-point margin ... and was DEFEATED once
`snipe-on-the-path` (+12) also fired."* A single scalar under hard gates removes both failure modes by
construction, where re-tuning weights never could.

**What this does NOT claim.** It does not withdraw the one-backend thesis for gust, which genuinely
removes bodies and is correctly served by the prize marginal. It withdraws it for the **second** of the
three S4 instruments — so after this ADR the score is: gust reads the shared prize marginal; deny and
snipe are each categorical relevance instruments over their own subject (`(body, energy)` pairs for
deny, offered targets for snipe).

**2. The legs combine as a PRODUCT of two conjunctive sides, `max` within each side.** Snipe's
discriminators split across two different subjects, which deny's do not:

```
relevance(target) = gates × their_plan × my_route          each factor ∈ [0,1]
    their_plan = max(threat legs)      # does this body matter to the opponent's offence?
    my_route   = max(route legs)       # does hurting it advance MY prize route?
    gates      = 0 on Tera / target_prize_redundant / target_promotion_mirage
```

`max` within a side is `deny_relevance`'s shape used where deny's reasoning actually applies —
alternative claims about **one** subject, the same combination `card_worth.role_value` uses for
heterogeneous claims. The **product** across sides is the divergence, and it is deliberate: a snipe is
worth spending only when the body matters to them *and* the damage advances me, so the two sides are
conjunctive rather than alternative. A flat `max` over all legs would score a purely on-route body with
zero threat identically to one that is both, losing the legitimate half of what the additive stack
expressed. Multiplication is also the codebase's stated composition discipline — *"a booster must scale
the oracle, never add to it"* (ADR-0063, `pilot.py:129-136`) — and it makes the additive failure mode
**unrepresentable** rather than merely capped. A matched Brief's `threats[]` scales `their_plan` only,
clipped back into `[0,1]`, mirroring `_BRIEF_THREAT_BOOST = 1.25` including its "0 × anything is 0"
property, so authored scouting can never promote a whiff.

Recorded honestly: the `82756021-57` / `83667237-107` pair does **not** discriminate between the product
and a flat `max`, because decision 1 already makes redundancy a hard gate, so that pair separates under
any combination rule. Decision 2 is made on failure-mode and composition grounds, not on that pair.

### Measurement that shaped decisions 1–2: magnitude is not the driver at all

Ranking the offered options by magnitude alone, with no gates, no tier and no route factor:

| ranker | agrees with human |
|---|---|
| `max(own maxDamage, forward_max_damage)`, printed | 7/19 |
| the same, with the missing bench scaler applied (below) | 7/19 |
| `needs.opponent_target_value` (the chartered fold) | 7/19 |
| **the shipped rungs** | **17/19** |

Three independent magnitude rankers land on exactly 7/19. **The shipped 17/19 is produced almost
entirely by the categorical reads** — the ADR-0044 gates, the Prize-Path membership, the imminence
tier — not by any magnitude. That is decision 1's thesis measured from a second direction, and it sets
the priority for the build: the gates and route legs carry the record; the magnitude leg is a
tie-breaker inside them.

### Two card-fact blindnesses in `_body_threat_rank`, found during the grill and verified at source

Both are real, both are latent rather than corpus-visible today, and both are evidence about where
`their_plan`'s magnitude should come from (**settled by decision 3**: the Threat Clock curve, which
fixes the first of these and makes the second a one-regex addition):

- **Self-locking attacks are invisible to the snipe order.** Latias ex (184) `Eon Blade` `{P}{P}●` 200
  reads *"During your next turn, this Pokémon can't use attacks"*, and the fact **is** parsed —
  `AttackStat(243).nextTurnSelfLock is True` — and **is** honoured by `combat.incoming` /
  the payability walk (ADR-0033, `combat.py:693,992,1018,1238`). But `_body_threat_rank` reads raw
  `stat.maxDamage = 200`, so it prices a body that attacks every *other* turn as a full 200-per-turn
  threat. ADR-0061 already rules that *a locking attack's value includes its forced follow-up*; the
  snipe order never got the memo.
- **A damage-scaling family is missing from the parser, and it hits a corpus-live body.** Lillie's
  Clefairy ex (272) `Full Moon Rondo` `{P}●` 20 reads *"20 more damage for each Benched Pokémon (both
  yours and your opponent's)"*. `_SCALE_FAMILIES` (`scouting/card_text.py:347`) ships
  *"each of **your** Benched Pokémon"* → `atk_bench` and *"each of **your opponent's** Benched
  Pokémon"* → `def_bench`, but nothing for the **combined** count, so `parse_attack_scaling` returns
  `None` and `AttackStat(371).scaleVar is None` → the body is priced at **20**. On the corpus boards its
  real damage is 100–120; on a full board it is 20 + 20×9 = **200**. Skeledirge (203) `Torcherto` shares
  the exact phrasing. This is the same class as the `hand_size_attacker` gap `_forced_promotion_key`'s
  docstring already records (*"Alakazam's printed 10 hides the real threat — the ms f85 gap"*), and that
  tag covers exactly one card (743) in `card_functions.json`.

The bot currently gets `81785223-28/39/45` right — the human takes the energized Clefairy over the bare
Latias ex — but for the **wrong reason**: `_ENERGIZED_SNIPE_TIER = 100000` promotes it because it
carries Energy, not because the model understands either the scaler or the lock. Reverse the Energy and
the pick reverses with it. Right answer, wrong reason, is a latent regression waiting for an unseen
board.

**3. `their_plan` is sourced from the THREAT CLOCK CURVE, not from `_body_threat_rank`.** The magnitude
and the imminence both come from the machinery that already models them:
`combat.incoming(my_active, [body], t, policy)` for the damage a body's line can actually land, and
`combat.turns_to_afford(body)` for how soon. This is ADR-0045's own thesis — it names
`_body_threat_rank` among the six scattered reads the Threat Clock exists to unify — and the design
doc's policy table already specifies this exact query: *"`strongest_threat_rank` (snipe imminence) | the
curve's earliest-KO-turn / slope per body | prep policy."*

Won for free, rather than re-derived: `nextTurnSelfLock` (honoured at `combat.py:693,992,1018,1238`),
typed affordability, Weakness/Resistance, `AttackStat.handSizeDamage`, and the 59 already-parsed
`scaleVar` attacks — i.e. **both blindnesses above become non-bugs by construction** rather than needing
their own patches. The missing combined-bench scaler family is still owed as a one-regex addition with
its test.

**`_ENERGIZED_SNIPE_TIER = 100000` retires as SUBSUMED, not re-expressed** — the standing discipline
(*a graded term REPLACES its guard family*). This also dissolves the tier-vs-factor question rather than
answering it: imminence stops being a separate structure and becomes `turns_to_afford`.

### Gate: does the curve actually subsume the tier? — RUN, and it PASSES

The subsumption claim was a prediction, so it was measured before being accepted (two earlier
predictions in this same grill were refuted by their own measurements). Over the **9 MIXED frames** —
both energized and bare bodies on offer, the only frames that discriminate a tier — scoring
`gates × normalize(incoming(t=1)) × imminence(turns_to_afford)`:

| shape | MIXED frames | all 19 |
|---|---|---|
| product, half-life `1/2**tta` (the `deny_slot` grade idiom) | **8/9** | 10/19 |
| product, reciprocal `1/(1+tta)` | **8/9** | 10/19 |
| lexicographic (gate, then soonest, then biggest) | **8/9** | 10/19 |
| the curve with NO gates at all, ceiling argmax | 5/9 | 8/19 |
| **Tera as the only gate** (ADR-0044 reads dropped) | 6–7/9 | 8–10/19 |

Three findings, in order of how load-bearing they are:

1. **The tier is genuinely unnecessary.** All six frames where the human takes the energized body are
   reproduced by `turns_to_afford` alone; no 100000 constant is required. Decision 3 stands.
2. **Product and lexicographic are indistinguishable on this evidence** (8/9 each). So decision 2's
   product shape is unrefuted for this leg, and is kept on its own composition grounds rather than on a
   measured advantage — recorded so it is not later cited as measured.
3. **The ADR-0044 reads are doing real work as gates.** Dropping them to Tera-only costs 1–2 mixed
   frames, so they are not merely a suppression that the graded curve subsumes.

The `10/19` figure is a **floor from a deliberately partial model** — `their_plan` + gates only, with no
`my_route` factor built — not a verdict on the design.

### The fork the gate exposed: gate SCOPE (settled by decision 4)

Decision 1 says the ADR-0044 reads *"force it to 0"* on the whole target. **The shipped rungs do not do
that**, and the corpus sides with the shipped rungs. Read at source in `baseline_snipe.py`, the guards
are attached to exactly two rungs:

| rung | `target_prize_redundant` | `target_promotion_mirage` |
|---|---|---|
| `snipe-the-top-threat` | guards | guards |
| `snipe-the-threat` | guards | guards |
| `snipe-the-evolving-threat` | — | — |
| `snipe-the-forced-promotion` | — | — (rationale: *"its mirages are suppressed"*) |
| `snipe-on-the-path` | — | — |
| `snipe-for-the-ko` | — | — |

So they suppress the **threat-rank / imminence** reads specifically, not the target. And three corpus
frames — `81905522-75`, `82523811-41`, `85164131-22` — have the human picking a body that carries
`target_promotion_mirage`, which a whole-target gate makes **unreachable**. Under decision 1 as written
those three frames cannot be won at all.

Decision 1's gate list is therefore too coarse and needs amending. **Resolved by decision 4 below:
leg-scoped.**

**4. The ADR-0044 reads are LEG-SCOPED guards, not whole-target gates. This AMENDS decision 1.** Only
the Tera fact is a whole-target zero.

```
relevance(target) = tera_veto x ( their_plan x my_route )

their_plan = max(
    imminence/threat leg   -> ZEROED by target_prize_redundant OR target_promotion_mirage,
    forward-wincon leg     -> guarded only by its own target_forward_form_in_play,
    forced-promotion leg   -> unguarded,
)
my_route   = max( path leg, rider-reach leg )        # unguarded
```

Rationale: *"I don't need this body's prizes"* and *"they will never actually promote this"* are
objections to treating the body as an **imminent attacker**. They are not objections to pre-chipping a
developing win-condition on it, nor to hitting the body they are *forced* to bring up. Each objection
stays attached to the claim it actually refutes — which is what `baseline_snipe.py` already does, and
what the corpus endorses: `81905522-75`, `82523811-41` and `85164131-22` all have the human picking a
`target_promotion_mirage` body, so a whole-target gate makes them unreachable. Dropping the reads
instead is also refuted (Tera-only measured 6–7/9 against 8/9). The fold's job is to replace the
*scoring mechanism*, not to silently re-rule which reads apply where.

Two implementation constraints, both verified at source and both easy to lose in a refactor:

- **The Tera veto is an ORDERING, not a removal.** `_snipe_tera_veto` returns `-KO_SCORE`, and its
  docstring is explicit: *"Orders the Tera LAST; it does NOT remove the option — when a benched Tera is
  the ONLY target the select is forced and the rider is wasted either way, so the agent must still
  answer."* A literal `relevance = 0` that made the option unselectable would break a legal-move case.
  The whole-target zero must therefore mean *ranked last among the offered options*.
- **The Brief / MatchupPlan multiplier keeps its OWN whole-target stand-down.**
  `_snipe_matchup_tactical` (ADR-0051) already stands a **positive** priority down on
  `target_prize_redundant` / `target_promotion_mirage` / `target_is_bench_tera`, while a negative
  (`avoid`) priority always applies. Under decision 2 the Brief scales `their_plan` — which now includes
  an unguarded forward-wincon leg — so without preserving that stand-down explicitly a Brief boost would
  start reaching mirage bodies through the forward leg. The asymmetry (positive stands down, negative
  never does) is load-bearing and must survive.

**5. Scope: the fold takes the SIX target rungs plus the MatchupPlan steer. The three counter rungs
stay, deliberately.** The charter names *"6 target rungs + 3 counter rungs"*; the counter half is
excluded on three independently verified grounds:

| surface | select context | corpus frames |
|---|---|---|
| the 6 target rungs | `DAMAGE` 15 | **23** |
| `place-counter-to-convert` | `DAMAGE_COUNTER` 13 / `_ANY` 14 | **0** |
| `move-counters-off-the-damaged` | `REMOVE_DAMAGE_COUNTER` 16 | **0** |
| `move-max-counters` | `..._COUNT` 40 | **0** |

1. **The defect cannot occur there.** Contexts 13/14/16/40 are disjoint from 15, so no counter rung
   ever co-fires with a target rung — the additive stack this fold exists to delete cannot form.
2. **There is no hand-seeded stack to collapse.** Their value already comes from derived knapsack reads
   (`board.best_counter_slot`, `best_counter_source_slot`, `is_max_counter_move`).
3. **Zero corpus frames**, so any rewrite would be unbenched and unfalsifiable — the *"isolated
   hand-built probes manufacture phantom misplays"* trap `turn-planner-snipe-and-gust-scenarios.md`
   warns about.

`_snipe_matchup_tactical` (ADR-0051) **does** fold: it is already a Brief-shaped multiplier carrying
exactly decision 2's stand-down semantics, so it becomes the Brief factor on `their_plan` instead of an
additive tactical term. Leaving it additive beside the graded scalar would be the "bolts on beside"
the standing discipline forbids.

**Consequence to state plainly rather than let a later reader infer:** `baseline_snipe.py` is NOT
deleted — it survives holding the three counter Hypotheses, which are **live and deliberately
retained**, not residue. Issue #136's standing directive #1 ("no dead rungs left behind") is satisfied
for the target half only, on the record above. Relevance-informed counter placement is a real future
extension and is logged as such, not silently dropped.

**6. `my_route` is a max over DERIVED route legs — ungated, with NO membership boolean and NO floor
constant.** *(As first ruled: `max(reach, share)`. **Decision 11 replaces `reach`'s role with the
turns-to-KO delta and decision 12 settles the final leg set — read decision 12 for the shipped
shape.** The ungated / no-constant property is what survives unchanged.)* Two alternative reasons a body helps
*me*: my repeatable rider can finish it cheaply alongside my real attacks (**reach** — the arithmetic
`snipe_prize_reach` already computes at `objectives.py:424`), or its prizes are a large share of what I
still need (**share**). `max` because they are alternative claims about one subject, per decision 2.

The ADR-0040 Prize-Path machinery is **not** abandoned: `target_prize_redundant` is derived from the
path and is still doing gate work inside `their_plan` (decision 4). What is dropped is the separate
`target_on_path` **boolean** as a route leg, because it measured no better than the two derived legs
alone and cost a floor constant.

### The full prototype, measured — decisions 1–6 reach the shipped record

Assembling decisions 1–6 (with `snipe-for-the-ko` as the structural dominator decision 1 keeps outside
the scalar, and the Tera ordered last), over all 19 frames:

| `my_route` shape | agreement | extra misses beyond the two non-targets |
|---|---|---|
| `1.0` (no route factor) | 15/19 | `82523811-41`, `85164131-22` |
| `on_path ? 1.0 : 0.5` | 15/19 | same |
| `share` alone | 15/19 | same |
| `reach` alone | 16/19 | `82756021-57` |
| `on_path ? reach : 0.5×reach` | 16/19 | `82756021-57` |
| `on_path ? max(reach, share) : 0.5×…` | 17/19 | — |
| **`max(reach, share)` (decision 6)** | **17/19** | **—** |

**17/19 with the only two misses being `81905522-75` (the transposition, design-doc R3) and
`82749168-38` (the refuted label)** — i.e. the prototype reaches the shipped record exactly, on the two
frames the design doc already rules out of scope, while introducing **zero tunable constants**. The
KO-dominator line is load-bearing: without it the same model scores 10–11/19, and all five of the
missing frames are the five where `board.snipe_ko_available` is True.

**Overfitting risk, stated rather than buried.** The route shape was selected by trying eight variants
against the same 19 frames used to validate it. With n = 19 that is shape-selection on the validation
set, so *"matches on the 19"* must NOT be the acceptance bar for the build — see the acceptance
decision. The prototype is evidence that the design is *expressible*, not that it generalises.

**Policy note — RULED by decision 8.** The prototype read the curve at `incoming(t=1, charged=None)` —
the **ceiling** policy — and reached 17/19 there. The design doc's per-consumer conservatism table
(ruling 2) specifies something more specific for this consumer: snipe-prep is *"existence-gated ceiling
on the THREAT, slow on the INVESTMENT."* **Decision 8 pins that split**, and ratifies the pairing the
prototype had reached only by parameter default.

**7. The acceptance bar is the full ADR-0072 pair, plus AUTHORED per-leg fixtures, plus a dedicated
decider sweep — and reproducing 17/19 on the 19 DAMAGE frames is explicitly NOT one of the bars.**
The prototype's shape was selected against those 19 frames, so scoring it on them again validates a fit
against itself. Five bars:

1. **Discrimination Gate** — `leaf_lab.py diff --baseline data/leaf_lab/baseline.json` over the gated
   leaf frames, run **BEFORE** the arming decision, not after it (ADR-0072 decision 5 — the ordering
   ADR-0076 Amendment E got wrong and had to write an amendment about). No unruled `OK → MISS`.
2. **Decision Gate** — a new `tools/train/probes/snipe_decider_sweep.py`, following the
   `deny_gate1.py` / `attach_decider_sweep.py` shape, classifying every change as **FIX / regression /
   unlabelled** against the corpus ruling rather than reporting any behaviour change as a failure (the
   ADR-0078 Amendment C framing). ADR-0072 names "the phase's `*_decider_sweep.py`" and none exists for
   snipe today.
3. **Paired-A/B Tripwire** — `gauntlet_ab.py --overlay` on the kill-switch at the ADR-0072 mid-build
   bound (`crashes == 0 AND CI-lo >= -5%`), across the three historically-calibrated agents.
4. **Per-leg unit fixtures AUTHORED from worked examples, not harvested from the 19** — the ADR-0080
   pattern ("the five worked examples become the acceptance fixtures"). At minimum: the
   `82756021-57` / `83667237-107` identical-magnitude pair (the impossibility proof, which any
   magnitude-shaped successor fails by construction); a forward-leg ordering case (a pre-evo carrying a
   wincon outranks one carrying nothing); the Tera **ordering-not-removal** case (a benched Tera as the
   ONLY offered target must still be selectable); and Lillie's Clefairy ex reading its board-effective
   damage rather than 20 once the combined-bench scaler family lands.
5. **Kill-switch OFF byte-identical first, then armed** (the `develop_rollout` / seam-D precedent).

`81905522-75` (transposition) and `82749168-38` (refuted label) stay **recorded misses**; a build that
"fixes" either has almost certainly overfitted.

**8. The policy SPLITS across the two curve calls, per design ruling 2's snipe-prep row.**
*Fail-scared on the threat, fail-slow on the investment:*

| call | policy | why |
|---|---|---|
| `incoming(t=1, charged=None)` — how HARD they can hit | **ceiling**, no affordability discount | under-counting their reach feeds them the wincon (ADR-0064's hidden-burst lesson) |
| `turns_to_afford(body, attaches_per_turn=1)` — how SOON | **slow**: the `rules.md §3` floor of one manual attach per turn, crediting no acceleration | over-counting their speed merely wastes a rider |

**Measured, and the corpus is SILENT: ceiling 17/19, slow 17/19 on the incoming leg.** So this is ruled
on the fail-direction asymmetry the design doc states (*"over-counting their reach costs a nudge;
under-counting feeds them the wincon"*), not on evidence — recorded that way so it is never cited as
measured.

The prototype already used exactly this pairing, but **by parameter default rather than by choice**.
Ratifying it makes it a decision instead of an accident: a later reader finding an unexplained
`charged=None` would otherwise be free to "fix" it. The split must be stated in the code, or the next
refactor will collapse it.

**9. The two `+500` boosts split by KIND — one is a curve gap to fix, the other is filed under the
wrong side.** They are not the same sort of fact and do not share a fate:

- **`_HAND_SIZE_ATTACKER_BOOST = 500`** (`hand_size_attacker` → **743 Alakazam**, corpus-present) *is* a
  threat magnitude — a latent attacker whose printed damage hides it. But decision 3's source does
  **not** model it: the hand-scaled counter is a bespoke addition inside `forward_incoming_damage`
  (`combat.py:719-720`) only, and `doomed_incoming`'s docstring names its omission from the curve as one
  of its two known divergences. **Fix `combat.incoming` / `_reach_form_damage` to model it**, at which
  point the boost retires as genuinely subsumed. This also closes one of the two pinned doom-curve
  divergences, in the **fail-safe direction**: it makes the curve more pessimistic, and since
  `doom_matched_relax` is relax-only, a more pessimistic curve yields *fewer* relaxes, never a phantom
  doom.
- **`_PREVENT_EX_SNIPE_BOOST = 500`** (`prevent_ex_damage` → **345 Crustle** corpus-present, **330
  Sylveon** not) is **not a threat magnitude at all.** The line does not hit me harder once evolved — it
  becomes *immune to my ex attacker*. It does not threaten me; it **blocks my prize route**. It
  therefore moves to **`my_route`** as a leg: a body whose line reaches `prevent_ex_damage` while my
  Active is an ex/Mega ex is one my rider can never finish later, so its route value is maximal now.
  Filing it under "how scary are they" was always a category error, and the two-sided product of
  decision 2 is what makes the distinction expressible at all.

Retiring both was considered and refuted: 743 and 345 both appear in the corrections corpus, and
`_forced_promotion_key`'s docstring already records the Alakazam blindness as a live gap ("the ms f85
gap"). Cost accepted: (a) touches the shared curve, so `test_threat_shadow.py`'s `REQ-DOOMSHADOW-0002`
— which covers that divergence deliberately — must be re-baselined and the doom sweep re-run. Splitting
(a) into its own issue is acceptable; duplicating the fact inside the snipe leg is not.

### Held-out fixtures: the first generalisation check, and it found a real defect

The four committed snipe fixtures (`ms_snipe_*.json`) live in `tests/fixtures/corrections/`, **not** in
`data/corrections/`, so the 19-frame sweep never saw them — making them a genuine held-out set. Scoring
the decision 1–8 prototype against them:

| fixture | correct | prototype | |
|---|---|---|---|
| `ms_snipe_riolu_over_lunatone_f47` | `[2]` | `[2]` | PASS |
| `ms_snipe_energized_bench_f39` | `[2]` | `[2]` | PASS |
| `ms_snipe_attacker_line_over_support_f85` | `[0]` | `[0]` | PASS |
| **`ms_snipe_evolving_wincon_preevo_f75`** | `[3]` | `[4]` | **MISS** |

**The miss is a design defect, not a tuning miss.** On `f75` the prototype takes Solrock `[4]` (score
0.5) over the Riolu `[3]` (0.386). Cause: the prototype scored the **forced-promotion leg as a flat
`1.0`**, which dominates the Riolu's forward-wincon leg (`normalize(270) = 0.771`). The shipped rungs
resolve this exact conflict the other way on purpose — `snipe-the-evolving-threat` (45) outranks
`snipe-the-forced-promotion` (40), and `f47`'s docstring names the pairing ("Riolu over the
forced-promotion Lunatone"). That flat `1.0` was an **unexamined constant introduced by the prototype**,
precisely what decision 1 forbids, and the first held-out frame caught it. Decision 7's acceptance bar
working as designed, on its first application.

The forced-promotion leg therefore needs a **derived grade** rather than a saturating constant.
**Resolved by decision 10 below**, which fixes this frame.

### `_SNIPE_THREAT_PRIZE_FLOOR = 5` — measured INERT under the new instrument

ADR-0078 handed this constant's re-audit to Issue #188. Measured by forcing the clause
(`not (target_energy and my_prizes_remaining >= FLOOR)`) live, always-rescuing and inert:

| setting | effect | 19 frames | `f39` (its own anchor) |
|---|---|---|---|
| `5` (shipped) | rescues at ≥5 prizes | 17/19 | PASS |
| `99` | clause **inert** — never rescues | **17/19** | **PASS** |
| `0` | always rescues | 16/19 (loses `83667237-107`) | — |

Making redundancy fire *more* costs nothing; making it fire *less* costs `83667237-107`. **The rescue
clause changes no outcome under the new instrument — not on the corpus, and not on `ms_snipe_energized_bench_f39`,
the fixture written to cover it** ("the energized ex, at 6 prizes remaining"). **Retired by decision 13.**

**10. The forced-promotion leg is GRADED on the promoted body's own curve threat, with NO imminence
discount.** `forced_leg = normalize(incoming(my_active, [body], t=1, ceiling))` when
`ctx.target_is_forced_promotion`, else 0. The imminence discount is deliberately **omitted** — a forced
promotion *is* the timing claim (the body attacks next turn by definition), so applying
`turns_to_afford` on top would double-count what the ADR-0044 read already establishes. That asymmetry
is the leg's entire content and must be stated in code or a later reader will "restore" the missing
discount.

This **fixes the `f75` defect**: with the prototype's flat `1.0` the model took card **676 Solrock**
(the forced promotion, saturating the leg); graded, it takes card **677 Riolu** — the developing
Mega Lucario ex line, which is the fixture's ruling and the shipped `snipe-the-evolving-threat` (45) >
`snipe-the-forced-promotion` (40) ordering. Held-out fixtures go **3/4 → 4/4**.

*(A second, separate error was in the measurement rather than the design: `f75` offers **two** Riolu and
its own test matches by CARD ID, not index — `test_snipe_the_real_attacker.py`'s `by_card_id=True`
parameter says so. The probe compared indices. Both errors are recorded because only the first was a
design fault.)*

**11. The route's damage leg is the TURNS-TO-KO DELTA over a two-chip window, not a rider-reach count.
This AMENDS decision 6** (user ruling, 2026-07-29):

> *"if i snipe a benched mega lucario with 50dmg such that it now has not 340 HP but 290HP, that does
> nothing to help — ill still need two turns from mega starmie Nebula Beam to take it down. thus we must
> consider the amount of dmg we will do to the body once it moves into active and how many turns until
> we can KO it. if sniping it once or twice reduces the number of turns itll sit active, thats a real
> win, otherwise we are just wasting our snipes."*

```
ko_delta(b) = ( turns_to_ko(b) − turns_to_ko(b after 2 chips) ) / turns_to_ko(b)
```

via `combat.turns_to_ko(my_active_id, my_energy, body)` — which prices the body **as an Active** against
my real attack (W/R and riders per the oracle), which is precisely the "once it moves into active" the
ruling asks for. Derived; no constants. Decision 6's `reach` measured *how many rider hits finish it*,
a genuinely different question that is blind to threshold crossings.

**Card facts verified at source:** Mega Lucario ex (678) Stage 1, **340 HP**, evolves from Riolu (single
hop); Mega Starmie ex (1031) Jetting Blow `{W}` **120**, Nebula Beam `●●●` **210**.

**The two-chip window is load-bearing, and the corpus proves it:**

| frame | body | `turns_to_ko` | 1 chip | 2 chips | human picks it |
|---|---|---|---|---|---|
| `82756021-57` | Mega Lucario ex, 340 HP | 3 | **0 saved** | **1 saved** (0.33) | yes |
| `82756664-103` | Mega Lucario ex, 290 HP | 3 | **1 saved** (0.33) | 1 saved | yes |

A one-chip-only read scores the `57` Mega at **0** on this leg and loses the frame; the "once or twice"
horizon the ruling names is what rescues it. (On `57` my Active could afford only Jetting Blow 120, not
Nebula Beam 210 — hence 3 turns rather than the 2 the worked example assumes. The oracle is the
authority over hand-arithmetic here, and it changes the number without changing the ruling.)

**Measured — the corpus does NOT discriminate the route leg:** `reach+share`, `kodelta1+share`,
`kodelta2+share` and `kodelta2+reach+share` all score **17/19 on the corpus and 4/4 on the held-out
fixtures**. Decision 11 is therefore adopted on *reasoning* — it answers the question the instrument is
actually asking, and it is the design doc's threshold-race (ruling 4, *"the one live snipe gap"*) —
**not** on a measured advantage. Recorded that way so it is never cited as measured.

**12. `share` STAYS. `my_route = max( ko_delta₂ , reach , share )`.** Decision 12 was first taken as
*"drop `share`; a route leg must describe what the chip achieves, and `share` is a property of the
target"* — the strict reading of decision 11's ruling — and was then **reverted by the user after
measurement refuted it** (2026-07-29). Recorded rather than deleted, because the reasoning is the
useful part.

| shape | corpus | held-out fixtures |
|---|---|---|
| `max(ko_delta₂, reach)` — share dropped | 16/19 (loses `82756021-57`) | 4/4 |
| `max(ko_delta₂, reach × share)` — prize-weighted reach | 16/19 (loses `85164131-22`) | 4/4 |
| **`max(ko_delta₂, reach, share)`** | **17/19** | **4/4** |

**The decisive detail cuts against the argument for dropping it.** On `82756021-57` the 340-HP Mega
Lucario ex scores `ko_delta₂ = 0.33`, `reach = 0.14`, `share = 0.50` — so **`share` is what selects the
Mega, and the human selects the Mega.** What pulls the model away is Makuhita's `reach = 0.50` (an
80-HP body two riders finish). On the single corpus frame where `share` is decisive, the human sides
with `share`.

Two things blunt the "share can reward a wasted chip" worry that motivated dropping it:

- `share` is **multiplied by `their_plan`**, so it can only act on a body that already matters to the
  opponent's plan — a gated body (redundant / mirage / Tera) scores 0 however many prizes it carries.
- Decision 11's principle is carried by **`ko_delta` existing as a leg at all**, which is the change
  that matters. Removing `share` does not strengthen it; it merely lets an 80-HP 1-prize small outrank
  a 3-prize win-condition whose Active clock I can genuinely shorten.

**Method note, recorded as a caution for the build.** Roughly a dozen route shapes were measured against
the same 19 frames across this grill. That is well past the point where a shape difference of one frame
is meaningful evidence, and it is exactly the overfitting decision 7's acceptance bar exists to catch.
`share`'s retention rests on the *mechanism* above — it is bounded by `their_plan` and it decides the
one frame in the human's favour — not on 17 beating 16.

**13. `_SNIPE_THREAT_PRIZE_FLOOR = 5` is RETIRED — the rescue clause is deleted.** This is the
re-audit ADR-0078 handed to this issue. The conditions the standing discipline sets for retiring a
guard are met **and measured**, not asserted:

- **The quantity it thresholds is now priced continuously.** `my_prizes_remaining` enters the
  instrument through decision 12's `share = min(1, prize_value / my_prizes_remaining)`. Keeping the
  threshold beside the graded term is two readings of one fact, one of them a magic number — the
  ADR-0060/0062 *"price the quantity, don't threshold it"* move, and the standing *"a graded term
  REPLACES its guard family and re-audits it"* rule.
- **Both of its calibration anchors hold without it** (verified above): `ms_snipe_energized_bench_f39`
  ("the energized ex, at 6 prizes remaining") PASSES with the clause inert, and `83667237-107` (the
  stand-down at 4 prizes) is unaffected. The clause changes **no** decision at any setting except the
  always-rescue one, which is strictly worse.

Cost accepted: `target_prize_redundant` is shared with `_snipe_matchup_tactical`, so the semantics
change reaches the Brief steer — both are in this issue's scope per decision 5, so it is contained.
`test_snipe_the_real_attacker.py`'s `f39` case is documented as testing this floor specifically; its
docstring must be **rewritten to say what it now tests**, not left describing a constant that no longer
exists.

## The instrument, assembled

The thirteen decisions compose to one scorer. Stated whole, because no single decision above shows it:

```
relevance(target) = tera_veto ⊗ ( their_plan × my_route )        # decisions 1, 2, 4
    snipe-for-the-ko  — structural DOMINATOR, outside the scalar   # decision 1
    tera_veto         — ORDERS LAST (-KO_SCORE), never removes     # decision 4

their_plan = max(                                                  # decisions 2, 3, 4, 9, 10
    imminence  = normalize(incoming(t=1, ceiling)) / 2^turns_to_afford(attaches=1)
                 ZEROED by target_prize_redundant OR target_promotion_mirage,
    forward    = normalize(forward damage)  if target_is_strongest_forward
                                            and not target_forward_form_in_play,
    forced     = normalize(incoming(t=1, ceiling))  if target_is_forced_promotion
                 — NO imminence discount: a forced promotion IS the timing claim,
) × brief_multiplier      # ADR-0051 MatchupPlan; positive stands down on
                          # redundant/mirage/Tera, negative always applies

my_route = max(                                                    # decisions 6, 11, 12
    ko_delta₂ = (turns_to_ko(b) − turns_to_ko(b after 2 chips)) / turns_to_ko(b),
    reach     = 1 / ⌈hp_remaining / max_rider_snipe⌉,
    share     = min(1, prize_value(b) / my_prizes_remaining),
)
```

**Constants introduced: none.** `MAX_ATTACK_DAMAGE = 350` (the `normalize` denominator) is the existing
derived, CSV-recomputed normalizer `deny_relevance` already ships, and the Brief multiplier reuses
`_BRIEF_THREAT_BOOST`. **Constants the fold RETIRES: ten** — the six rung weights (60/45/40/30/20/12),
`_ENERGIZED_SNIPE_TIER` (100000, subsumed by `turns_to_afford`), `_HAND_SIZE_ATTACKER_BOOST` and
`_PREVENT_EX_SNIPE_BOOST` (500 each, decision 9), and `_SNIPE_THREAT_PRIZE_FLOOR` (5, decision 13).

⚠️ **"Retires" is not "deleted as of the build commit"** — see Amendment B4. Every one of them is
still in the tree, UNREAD on the armed path and live on the OFF path, because deleting them would
break decision 7 bar 5's byte-identical promise. The deletions land with the arming follow-up.

Measured: **17/19 on the corpus** (misses `81905522-75`, the transposition, and `82749168-38`, the
refuted label — both already out of scope) and **4/4 on the held-out committed fixtures**. Both figures
are sanity floors, not the acceptance bar (decision 7).

## Consequences

- **Issue #188 recharters** from *"fold the snipe rungs onto the unified marginal"* to *"build the Snipe
  Relevance instrument"* — the same recharter ADR-0080 decision 4 gave Issue #187, for the same reason.
- **The design doc's S4 is now two-thirds refuted.** `docs/plans/opponent-value-equation-unification.md`
  ruling 3 ("one backend feeding snipe + gust + deny") holds only for gust. Its S4 bullet's *"then snipe
  (its rungs → the marginal; the ADR-0065 snipe fold)"* is superseded here, and ADR-0078's Consequences
  claim that *"snipe is now the shortest [hop]"* is wrong on the evidence — snipe needs a whole
  instrument, not a slice-read.
- **`83667237-107` is retired as this issue's acceptance target** (already passing, and for a different
  reason than the charter records). The discard-fuel *rationale* residual stays open and unowned by this
  ADR; its `reviewed.json` disposition should be corrected to say the pick is fixed and only the
  rationale is deferred.
- **The `82756021-57` / `83667237-107` pair becomes the instrument's primary acceptance fixture** — two
  frames with identical magnitudes and opposite rulings, which any magnitude-shaped successor fails by
  construction. It is the snipe analogue of ADR-0080's five worked examples.
- **The two known misses stay misses and must be recorded as such**, not repaired by the scalar:
  `82749168-38` (refuted label) and `81905522-75` (transposition, design-doc R3).
- Snipe still needs **no** Worth Damage Rate and is unaffected by ADR-0080's gate-2 failure — ADR-0076
  Decision 2 + Amendment A keep it outside the DP.
- `currency.PRIZE_DAMAGE_RATE` gains a consumer only at the exit boundary (relevance → the damage-scale
  `score`), not as the instrument's internal currency.
- **The Value System's S4 now reads: gust alone uses the shared prize marginal.** After ADR-0080 (deny)
  and this ADR (snipe), two of the three S4 instruments are categorical relevance instruments over their
  own subject — `(body, energy)` pairs for deny, offered targets for snipe. The one-backend thesis
  survives only for gust, which genuinely removes the body. Issue #189 should start from that rather
  than rediscovering it, and ADR-0080's warning that gust *"has no escape route of deny's kind"* now has
  a second data point behind it.
- **`combat.incoming` gains the `hand_size_attacker` counter (decision 9)**, which closes one of the two
  divergences `test_threat_shadow.py::REQ-DOOMSHADOW-0002` pins deliberately. That test must be
  re-baselined and `threat_sweep.py --doom` re-run. The direction is fail-safe (a more pessimistic curve
  yields fewer relaxes, and `doom_matched_relax` is relax-only), but it is a shared-machinery change and
  may be split into its own issue — **not** duplicated inside the snipe leg.
- **A parser family is owed:** *"does N more damage for each Benched Pokémon (both yours and your
  opponent's)"* matches neither shipped bench family in `_SCALE_FAMILIES`, so Lillie's Clefairy ex (272)
  and Skeledirge (203) read at printed damage. One regex plus its test.
- **`test_snipe_the_real_attacker.py`'s `f39` case needs its docstring rewritten** — it is documented as
  testing `_SNIPE_THREAT_PRIZE_FLOOR`, which decision 13 deletes. The frame still tests something real
  (the energized bench pick); the description must say what.
- **`baseline_snipe.py` survives**, holding the three counter Hypotheses as live, deliberately retained
  deciders (decision 5). Anyone auditing Issue #136's standing directive #1 should read that decision
  before recording them as dead rungs.
- **Ten constants are deleted and none introduced** — see *The instrument, assembled*. That is the fold's
  concrete deliverable, and it is what makes the two documented blunder classes (the additive stack
  out-voting a KO; the Tera veto losing on points) unrepresentable rather than merely re-tuned.
- **Method caution for the build, carried from decisions 6/11/12:** roughly a dozen scorer shapes were
  measured against the same 19 corpus frames during this grill. One-frame differences between shapes are
  not evidence at that point. Decision 7's acceptance bar exists for exactly this, and it already earned
  its keep once — the held-out fixtures caught a real design defect (the flat forced-promotion constant)
  on their first application.

## Amendment A — four findings inherited from the sibling's consumer build (2026-07-30, rebase)

Issue #187 merged (PR #216) the day after this grill, wiring Deny Relevance onto its three surfaces,
and **ADR-0080 Amendment B** records what arming it exposed. Its headline is the single most useful
thing this ADR can inherit: *"measuring the corpus with the switch armed exposed three defects that no
compute-only test could have caught — the read was correct in isolation and wrong at every consumer."*
Three of its four findings transfer; one **corrects decision 7's exit-boundary claim outright**.

**A1 — `K` is DERIVED, and this ADR's exit boundary was wrong.** The Consequences bullet below says
*"`currency.PRIZE_DAMAGE_RATE` gains a consumer only at the exit boundary."* **That is incorrect.**
Relevance is a `[0,1]` scalar, not a prize-denominated value, so multiplying it by a prizes↔damage rate
converts nothing — it merely rescales. Deny found the principled answer by measurement: since
`relevance = setback / MAX_ATTACK_DAMAGE`, setting **`K = MAX_ATTACK_DAMAGE`** makes `K × relevance`
the setback **damage**, so the armed rung prices in the incumbent's own units and is a strict
generalisation rather than a re-scaling — *"there is no free parameter"*. Snipe's `their_plan` runs
through the same `normalize`, so the same identity holds and snipe takes the same exit: **`K =
MAX_ATTACK_DAMAGE`, imported not copied**, so a future set re-deriving it from the CSV carries `K`
along. `PRIZE_DAMAGE_RATE` is **not** a consumer of this instrument. Decision 3's ADR-0080 mirror was
right; the Consequences bullet drifted from it and is superseded here rather than edited in place.

**A2 — the banked-potential question must be ASKED, not assumed.** Deny's Finding A split its read:
full relevance credits banked potential (correct for deciding whether to KEEP a Hammer), while the
FIRE rung must price only what the opponent can afford NOW (*"it fires at a threat that has not
arrived"*). Snipe has no keep/spend split — every snipe is a spend — so the naive transfer would
restrict snipe to the affordable-now read. **That is very likely wrong for snipe**, because
`snipe-the-evolving-threat` exists precisely to pre-chip a body that cannot attack yet, and decision 3
sources `their_plan` from a `t=1` ceiling curve that deliberately credits one attach. The finding is
recorded not as a change but as a **question the build must answer with a fixture** rather than inherit
by symmetry: does snipe's imminence leg credit banked potential? This ADR's position is yes; deny's
experience is that the opposite was true for it, so the assumption needs a test, not a shrug.

**A3 — the Brief sharpener is safe here, and here is why.** Deny's Finding C scoped the Brief off its
fire reading, because that reading alone is compared against `_DENIAL_ITEM_COST`, where a `1.25×`
multiplier becomes an **override** (it flipped f21 from `-1.25` to `+0.94`). Snipe's score is never
compared against an absolute cost threshold — the DAMAGE select is a pure ranking among offered
options — so decision 5's Brief-as-multiplier on `their_plan` does not have that failure mode.
Recorded because the reasoning is what makes it safe; if a future change ever gates snipe on an
absolute threshold, this exemption lapses with it.

**A4 — a constant this ADR proposes deleting was RE-EXPRESSED rather than retired next door.**
ADR-0078 decision 6 retired `_DENIAL_UNFAVORED`; ADR-0080 Amendment B **withdrew that retirement**,
because `_denial_play_tactical` turned out to be ADR-0026 Lever A's last live consumer and retiring it
unreplaced would have deleted Lever A as a side effect of a deny refactor. Direct caution for decision
9 and decision 13: before deleting `_PREVENT_EX_SNIPE_BOOST` and `_SNIPE_THREAT_PRIZE_FLOOR`, check
whether either is the **last** consumer of a lever or read that would silently vanish with it. This
ADR's measurements establish that neither changes a decision; they do **not** establish that nothing
else depends on their existence.

**Also noted, minor:** the stale in-code `ADR-0081` references that should read ADR-0080 are now **9**
in `pilot.py`, not the 16 recorded during this grill — Issue #187's merge cleaned seven of them in
passing. Still not this issue's to finish.

## Amendment B — the build (2026-07-30, Issue #188)

Built the day after the grill. Three things did not survive contact with the code exactly as written,
and one pre-existing gate failure was measured rather than inherited.

**B1 — decision 1's "delete the six weights" is STAGED behind arming, not done in this change.** The
standing directive #1 on Issue #136 (*"rungs an equation replaces are DELETED, not suppressed"*) and
this ADR's own decision 7 bar 5 (*"kill-switch OFF byte-identical first"*) cannot both hold in one
commit: deleting the rungs makes OFF non-identical by construction. The conflict is settled by
**precedent rather than by preference** — Issue #187 hit it one day earlier and resolved it the same
way, keeping `_DENIAL_BENCH` live on deny's OFF path with ADR-0080 Amendment B recording the rule
outright: *"The constant stays live on the OFF path … so ADR-0062's derivation is unread while armed,
not deleted."* So the six target rungs each gain a single `not c.snipe_relevance_armed` first
conjunct and go silent **as a body** when the scalar decides; deletion is the arming follow-up's
commit. `Context.snipe_relevance_armed` exists only to carry that stand-down.

**B2 — `snipe-for-the-ko` had to MOVE, not merely stand down.** Decision 1 says both that the six
weights (which include the KO rung's 60) are deleted *and* that `snipe-for-the-ko` remains a
structural dominator. Gating it off with the other five leaves the armed path with **nothing scoring
a Knock-Out target**, because `_snipe_relevance_tactical` deliberately stands the scalar down when
`board.snipe_ko_available`. The coherent reading — and the one that makes the ADR's two clauses both
true — is that the KO rung makes exactly the journey the Tera veto already made: from a tuner-mutable
positional weight to a `KO_SCORE`-class Tactical term (`Pilot._snipe_ko_dominator`). This is strictly
better than preserving the weight: at 60 it was *out-voted in the corpus* (`30+40+45 = 115` on an
un-KO-able Grookey, `82754241-45`), whereas `K x relevance` is bounded by `MAX_ATTACK_DAMAGE` 350
against `KO_SCORE` 1000, so no leg, tune or Brief multiplier can ever reintroduce the misplay.

**B3 — `_HAND_SIZE_ATTACKER_BOOST` is NOT retired here.** Decision 9 retires it *"once Issue #213
lands"*, and Issue #213 has not landed, so the constant stays exactly as it is. Retiring it now would
delete a live read the curve does not yet replace — the A4 caution in Amendment A, applied to itself.

**B4 — the constant-retirement ledger, stated honestly. ZERO are deleted as of the build commit.**
`/code-review`'s Spec pass caught this ADR claiming *"ten constants deleted"* while the tree still
holds all ten, and caught two of them being neither deleted nor self-reported:

| constant | armed path | OFF path | why not deleted yet |
|---|---|---|---|
| the six rung weights | unread (rungs stand down) | live | B1 — byte-identical promise |
| `_ENERGIZED_SNIPE_TIER` | unread (`_body_threat_rank` not consulted) | live | same, and `_body_threat_rank` still serves `planner.py` |
| `_SNIPE_THREAT_PRIZE_FLOOR` | **rescue clause retired** | live | its flag `target_prize_redundant` feeds BOTH paths |
| `_PREVENT_EX_SNIPE_BOOST` | unread (re-homed into `my_route`) | live | same |
| `_HAND_SIZE_ATTACKER_BOOST` | live | live | B3 — blocked on Issue #213 |

`_SNIPE_THREAT_PRIZE_FLOOR` is the one that mattered, and the review was right that B1 did not cover
it: the rescue clause sits *inside* `target_prize_redundant`, which the **armed** scorer consumes as
its imminence gate — so leaving it untouched meant the armed instrument read floor-rescued semantics
rather than decision 13's. It is now retired **on the armed path only** (`not self.snipe_relevance
and …`), which delivers decision 13 where it actually bites while keeping OFF identical. The Decision
Gate re-ran clean afterwards, which is the corpus confirming the measurement that called it inert.

**B5 — three further defects the review found, all fixed.**

- **The Brief multiplier invented a constant.** The build scaled the MatchupPlan priority by
  `_MATCHUP_PRIORITY_SCALE / KO_SCORE` to reach the `[0,1]` band. Nothing derives that divisor, it is
  unrelated to the band, and it contradicted this ADR's own *"constants introduced: none"* — the exact
  ADR-0065 fudge the instrument was built to avoid, reintroduced at the last mile. Now only the SIGN
  of the priority is read and the magnitude is the caller's existing `_BRIEF_THREAT_BOOST`, with the
  avoid direction as its mirror (`1/boost`) so one constant governs both.
- **The unknown-clock read was fail-OPEN.** `turns_to_afford` returns `None` for an unknown body or
  unknown attack cost (fail-closed at source, `combat.py:1321`) — not for "can never attack". Mapping
  it to `t = 99` discounted an unknown body to zero threat, the opposite of decision 8's ceiling
  discipline. It now takes no discount.
- **The scalar's scope was wider than the rungs it replaces.** `_snipe_relevance_terms` omitted
  `option.type == _CARD`, which every incumbent rung requires, so a non-CARD bench option at a DAMAGE
  select would have been scored where nothing scored it before.

**B6 — one test was vacuous, which is worse than a missing test.**
`test_off_is_byte_identical_to_the_incumbent` compared a shipped pilot against a shipped pilot with
the flag set to its own default — OFF against OFF — so it could not have detected any OFF-path change
at all while reading as though it guarded one. Replaced with assertions on what "unchanged" actually
means: the scalar contributes nothing, an incumbent rung still fires, the steer still scores. The
behavioural evidence proper is the sweep's OFF column. Recorded because a test that cannot fail is a
false negative in the acceptance bar, not a gap in it.

Amendment A2's owed fixture is also now written
(`test_snipe_credits_banked_potential_unlike_denys_fire_reading`): snipe DOES credit banked potential,
refuting the naive transfer from deny's fire reading, because `snipe-the-evolving-threat` exists to
chip a body that cannot attack yet.

### The gates, run

| gate | result |
|---|---|
| **Decision Gate** (`snipe_decider_sweep.py`, new) | **PASS** — 19/19 DAMAGE frames unchanged, 0 FIX, 0 regressions |
| **Discrimination Gate** (`leaf_lab.py diff`) | **PASS** — after the standing drift was ruled to Issue #165, see below |
| Paired-A/B Tripwire | **NOT RUN** — the switch therefore ships OFF |

The Decision Gate's "19/19 unchanged" is not vacuous: the `--legs` breakdown shows the scalar live and
discriminating (on `82756021-57` the Mega Lucario ex tops at `0.500` against Makuhita's `0.300`; on
`83667237-107` Makuhita is the *only* non-zero option because every other body is redundancy-gated).
Both recorded misses stay missing, which the probe reports explicitly in both directions so a run that
starts passing them is visible as the overfitting signal it would be.

**The Discrimination Gate initially failed on a regression this branch does not cause, and the
standing drift has now been RULED rather than worked around.** `84071010|0|decision|15` flips
`OK → MISS` (rank 1 → 2). A **control run with this branch's changes stashed reported the identical
regression at the identical rank**, so the branch was gate-identical to main and the flip is
pre-existing drift against the baseline pinned at `e4c46ca`.

**Ruled to Issue #165 (user, 2026-07-30), and it is not a snipe frame at all.** The endorsed play is
the head of a five-step dependent chain: Team Rocket's Petrel searches Air Balloon (a Pokémon Tool
*is* a Trainer card), attach it to the Active Makuhita (retreat 2) to make the retreat `2−2 = 0`,
retreat free, promote the benched Mega Lucario ex already holding one `{F}`, and Aura Jab (`{F}`, 130)
Knocks Out the opponent's Active Riolu (80 HP) — their Bench is 0 of 5, so `docs/rules.md` §7
condition 2 ends the match on turn 3. ADR-0070 amendment J's discriminator settles the ownership
without appeal to taste: playing Petrel is **not** individually valuable at the moment it becomes
legal, and the steps **do not commute**, so it is a **Maneuver**, which is Issue #165's by definition
rather than any equation's. It is also a `Main` select, so the DAMAGE-select instrument this ADR
builds could never have scored it.

`tests/fixtures/corrections/ml_petrel_balloon_retreat_lethal_f15.json` already declared the `frame_key` but
carried **no owner**, which is exactly why the gate counted it unruled; the Decision Claim now carries
`owner` / `ruled` / `why` per ADR-0072 decision 4, and the gate reports it under `HELD OUT` —
**visible, never gating**. Re-run: **`GATE: PASS`, gated on 266 frames, 1 held out.**

ADR-0072 decision 5's prescription — *"run the gate on `main` before the next swap, not after it"* —
is what this discharges, one swap later than it should have been.

## Amendment C — the Tripwire ran; `snipe_relevance` armed ON (2026-07-30)

Decision 7's bar 5 stages the kill-switch **OFF byte-identical first, then armed**. Amendment B closed
the first stage; this closes the second. All five bars now cleared, and the two that had to be re-run
in the *armed* configuration were.

**C1 — the paired-A/B Tripwire.** `gauntlet_ab.py --overlay '{"params":{"snipe_relevance":true}}'` at
`-n 200` per arm per directed matchup across the three historically-calibrated agents
(`mega_starmie`, `mega_lucario`, `dragapult_ex`) — 6 directed matchups, **2400 games**, ~25 min. The
instrument choice follows ADR-0076 Amendment D: this switch is a pure additive kill-switch whose OFF
path is fully intact, so the flag-overlay A/B is the mechanically correct tool, not
`gauntlet_swap_ab.py` (which A/Bs two *builds* and is for a swap that deletes what a flag used to fall
back to).

| matchup (overlay on the first) | ON | OFF | delta | crashes |
|---|---|---|---|---|
| mega_starmie vs mega_lucario | 138/200 | 145/200 | −3.5 pp | 0 |
| mega_starmie vs dragapult_ex | 175/200 | 172/200 | +1.5 pp | 0 |
| mega_lucario vs mega_starmie | 57/200 | 64/200 | −3.5 pp | 0 |
| mega_lucario vs dragapult_ex | 105/200 | 114/200 | −4.5 pp | 0 |
| dragapult_ex vs mega_starmie | 37/200 | 34/200 | +1.5 pp | 0 |
| dragapult_ex vs mega_lucario | 93/200 | 91/200 | +1.0 pp | 0 |

**Aggregate −1.25 pp, 95% CI [−4.79, +2.29], achieved half-width 3.54 pp, 0 crashes / 2400 games.**

`paired_ab.mid_build_verdict(result, crashes=0)` → **True** (`ci_lo ≥ −5% AND crashes == 0`, no delta
clause). The script's own printed `FLIP value_model ON: False` is the **post-composition** rule
(`flips_on`, `delta ≥ 0 AND ci_lo ≥ −1%`) and is not this phase's bar — the same disregard ADR-0076
Amendment D recorded, except applied here through the canonical function rather than by hand.

Two things must be said plainly rather than rounded off:

- **The margin over the bound is +0.21 pp**, and the point estimate is negative. The thinness is not
  an underpowered run — the half-width came in at 3.54 pp, i.e. the design point the tolerance was
  calibrated for (`MID_BUILD_REG_TOL`'s own comment: *"achieved half-width there is ~3.4 pp, so a
  truly neutral swap clears −5 pp with margin"*). The margin is thin because the delta is −1.25 pp,
  not because the measurement was.
- **Re-running for a tighter answer was considered and rejected as forbidden, not merely expensive.**
  ADR-0072's Context settles it: half-width scales as `1/√n`, so resolving −1 pp near a zero delta
  needs n ≈ 2340/arm/matchup — **~28,000 games, 8–10 h** — and the native engine is unseedable
  (`src/cgpy/rng.py`), so common-random-numbers pairing is unavailable and the deals are unpaired
  between arms. ADR-0072 names re-running until the sign lands as **p-hacking** outright.

What makes this decidable is that the outcome is a **statistical twin of the precedent the tolerance
was written about**. Phase 1b measured −1.17 pp, CI [−4.59, +2.25], 0 crashes / 2400 games and was
merged on a `FLIP: False` (ADR-0070 amendment H); ADR-0072 then created `mid_build_verdict` precisely
so that shape stops being read as a regression. This run is −1.25 pp, CI [−4.79, +2.29], 0 crashes /
2400 games. Treating it as disqualifying would retroactively re-litigate Phase 1b and make the
mid-build bar unpassable by any neutral decider swap, which is the failure mode ADR-0072 exists to
prevent. **The verdict claims what it says and nothing more: no catastrophe, no crashes.** It is not a
non-regression claim. Merit rests on the two deterministic per-frame gates below, which answer exactly
rather than statistically.

**C2 — the Discrimination Gate, re-run ARMED.** This was the real gap, and Amendment B did not close
it. `leaf_lab.py:153` builds its pilots through `tune._build_pilot`, i.e. from the **shipped**
`PROFILE` — so Amendment B's passing run measured the OFF path and could say nothing about arming.
ADR-0072 decision 5 requires the gate *before* the arming decision, which only has content if the
gate sees the armed instrument. Re-run with `PROFILE["snipe_relevance"] = True`:

**`GATE: PASS` — 267 frames vs `e4c46ca`, 0 unruled `OK → MISS`, gated on 266, 1 held out**
(`84071010|0|decision|15`, `owner=#165`). Byte-identical verdict to the OFF run: **arming introduces
no new leaf regression anywhere in the 266.**

**C3 — the Decision Gate, re-confirmed.** `snipe_decider_sweep.py`: **19/19 unchanged**, 0 FIX, 0
REGRESSION, 0 neutral, and both recorded misses (`81905522-75`, `82749168-38`) **still missing** — the
overfitting tripwire stayed silent. The armed scalar reproduces the incumbent's pick on every corpus
DAMAGE frame, which is the strongest available statement that the −1.25 pp is noise rather than a
decision defect: there is no frame on which the two readings disagree.

**C4 — the scalar subsumes `evolving_wincon_priority`'s stand-down.** Found while updating the suite,
and worth recording as evidence rather than as a test fix. On the f22 CRITICAL
(`ms_snipe_evolving_wincon_over_promotion_stack_f22.json`), the four switch combinations read:

| `snipe_relevance` | `evolving_wincon_priority` | pick |
|---|---|---|
| armed | ON (shipped) | `[1]` Staryu ✓ |
| armed | **OFF** | `[1]` Staryu ✓ |
| OFF | ON | `[1]` Staryu ✓ |
| OFF | **OFF** | `[0]` Cinderace ✗ (the blunder) |

Armed, the pick survives `evolving_wincon_priority` being switched off. The blunder is a property of
the additive stack — the `30 + 20 + 40 = 90` sum burying the `+45` rung — and armed there is no sum
left to bury anything, because decision 5 stands the six target rungs down as a body. So the scalar
does not *depend* on that stand-down; it makes it redundant. That file's kill-switch test now forces
`snipe_relevance=False`, since the mechanism it guards only exists on the OFF path.

**C5 — suite consequences of the flip.** Nine tests asserted the shipped default rather than the
configuration they meant, and all nine were tests whose intent was *the OFF path*: they used
`_shipped_pilot()` **as** the OFF arm, which was only sound while shipped meant OFF. Arming split the
two. Fixed by adding an explicit `_off()` helper and asking for OFF by name — the kill-switch path
remains a live requirement and keeps its coverage. Two required more than a helper swap:
`test_the_switch_ships_off` → `test_the_switch_ships_armed` (it asserted the thing this amendment
changes), and REQ-READ-0005's forced-promotion test, which read the requirement off *hypothesis IDs*
from the now-stood-down rung family. Rather than swap one mechanism for the other, that requirement is
now covered on **both** paths: `..._via_the_rungs` (forced OFF) and `..._via_the_scalar`, the latter
asserting the graded terms directly — the mirage zeroed at source (`imminence 0.0 → their_plan 0.0 →
relevance 0.0`, collapsing the conjunctive product however good our route is) and the ready wincon's
`forced` leg dominating its own discounted `imminence` (`0.6` vs `0.075`). Suite: **4071 passed, 1
skipped, 3 xfailed**.

**What arming does and does not settle.** It settles that the instrument is admissible: exact on every
frame either gate can adjudicate, and no catastrophe in play. It does **not** settle that Snipe
Relevance is an improvement — the mid-build instrument cannot show that at affordable `n`, by
construction. Two legs remain owed and are tracked elsewhere: the `incoming` fix split to **Issue
#213**, and Lillie's Clefairy ex reading board-effective damage rather than its printed 20 (decision 7
bar 4), which lands with the combined-bench scaler family. The 18-kwarg signature is **Issue #219**
— LANDED 2026-07-31: `target_relevance` now takes `TheirPlanInputs` and `MyRouteInputs`, one frozen
`Inputs` dataclass per side of decision 2's product, taking the shape ADR-0070 / ADR-0073 already set.
A signature change and nothing else: the sweep is byte-identical and the Discrimination Gate unmoved,
so no decision here is amended.

## Amendment D — rebased onto Issue #213; both gates re-run; Issue #204 inherited (2026-07-30)

**D1 — why the gates were re-run rather than carried forward.** Issue #213 (*the threat rank prices
the Damage Formula, not printed damage*, ADR-0083 — a different ADR, see the numbering note above)
merged while this branch was open, armed ON. It re-sourced the **threat ceiling** and the
**forced-promotion read** from printed `maxDamage` to `CombatMath.threat_ceiling` /
`forward_threat_ceiling` against the live board. Those are not neighbouring code — they are two of the
three inputs this instrument's `their_plan` side reads (`imminence` and `forced` both take
`incoming(t=1, ceiling)`; `forward` takes the forward index). Amendment C's gate numbers were
therefore measured against inputs that no longer exist, and carrying them forward would have been a
false claim rather than a stale one.

Re-run on the rebased base, both **PASS** and both identical to Amendment C's verdicts:

- **Decision Gate** — 19/19 unchanged, 0 FIX, 0 REGRESSION, 0 neutral; both recorded misses
  (`81905522-75`, `82749168-38`) still missing.
- **Discrimination Gate** (armed) — 267 frames vs `e4c46ca`, **0 unruled `OK → MISS`**, gated on 266,
  1 held out (`84071010|0|decision|15`, `owner=#165`).
- Suite **4102 passed**, 1 skipped, 3 xfailed (up from 4071 — #213's own tests arrived with the base).

That the verdicts are unchanged under a changed threat source is worth stating as a property, not a
relief: decision 1's categorical shape reads `incoming` through `normalize(...)` into `[0,1]`, so a
re-scaling of the underlying damage estimate moves the input without reordering the targets. A
magnitude-shaped successor — the kind decision 1 rejected — would have had no such insulation.

**D2 — the Tripwire was NOT re-run, deliberately.** It A/Bs the flag ON against OFF on one build, so a
new base moves both arms together; its verdict is a statement about the switch, not about the base.
Re-running would also have re-rolled 2400 unseeded games and invited exactly the sign-chasing ADR-0072
names as p-hacking. Amendment C's numbers stand as measured.

**D3 — Issue #204 is now this issue's, and it lands on `imminence`.** Issue #217 (deny's timing
unification) explicitly scopes snipe OUT — *"verified deny-scoped"*, blocking nothing here — but its
out-of-scope section hands one item forward: *"`discard_recur_fuel` on `turns_to_afford` — still
unowned, still belongs to whichever of Issue #188 / Issue #189 lands first."* This issue lands first,
so #204 is ours.

It is not incidental to this instrument. `imminence` divides by `2^turns_to_afford` (`pilot.py:7665`
→ the `turns_to_afford=tta` argument), and `turns_to_afford` assumes the rules floor of **one attach
per turn** (`rules.md` §3). The two cards carrying `discard_energy_recur` are, verified at source
(`src/common/card_functions.json` → `data/EN_Card_Data.csv`): **190 Archaludon ex** and **678 Mega
Lucario ex** — the latter reloading up to 3 Basic `{F}` from the discard onto its Bench via Aura Jab.
For those lines the true clock is **faster** than the floor, so `turns_to_afford` reads too high, the
`2^t` discount is too deep, and this instrument **under-rates** their imminence — i.e. under-snipes
exactly the bodies that rearm fastest.

Worth testing but NOT claimed here: `mega_lucario` was the agent with the least favourable armed delta
in Amendment C's Tripwire (both its matchups negative, averaging −4.0 pp), and it is the deck built
around card 678. A per-matchup delta at n=200 sits inside one standard error, so this is a hypothesis
for #204 to measure, not a finding. Recorded because the mechanism is specific and checkable, and
because "the deck whose wincon the clock under-rates is the deck the swap served worst" is the kind of
coincidence that should be either confirmed or killed rather than left unremarked.

**D4 — the rebase left the instrument reading PRINTED damage, and both gates were blind to it.**
Found by auditing the build against decision 7's bars rather than by any test. Issue #213 made
`context=` the thing that exposes the Damage Formula's `per_unit × count(variable)` term, and
`_snipe_relevance_terms` was written before that existed:

- `combat.incoming(...)` was called **without `context=`** — the only decider-facing `incoming` call
  in `pilot.py` that omitted it (the other two omissions are the `discard_recur_fuel` diagnostic rows,
  unread by any decider). Measured on card **272 Lillie's Clefairy ex** (Full Moon Rondo, printed 20,
  +20 per COMBINED bench body): `context=None → 20`, `both_bench=9 → 200`. A **10× under-read**, and
  both `imminence` and `forced` take that number.
- `forward_damage` read `stats.forward_max_damage(cid)` — the provider's PRINTED forward index, the
  exact read #213 replaced. It returns **0** for card 272. Now routed through `_threat_damage_pair`,
  so it respects the `scaled_threat_rank` lever like every other threat read.

**Neither gate could have caught this, and that is the structural point.** The Decision Gate compares
OFF against ARMED, and **zero of the 23 committed `DAMAGE` frames offer a bench-count or hand-count
scaler as a target** — so it reports 19/19 whether the context is passed or not. The Discrimination
Gate compares against a baseline captured before #213. Two green gates, one whole card class
mispriced. This is the precise reason decision 7 bar 4 demanded **authored** per-leg fixtures rather
than fixtures harvested from the 19: the corpus cannot pose a question it contains no instance of.

Bar 4's fourth fixture — *"Lillie's Clefairy ex reading its board-effective damage rather than 20 once
the combined-bench scaler family lands"* — was deferred at build time as unsatisfiable, since the
family had not landed. It landed with #213, so the bar is now **met**, asserted at the seam
(`test_a_bench_count_scaler_is_priced_at_its_board_effective_damage_not_its_printed_base`) with the
plumbing itself checked, not just `threat_ceiling`'s arithmetic — the arithmetic was already right;
the caller was not passing the board.

Re-run after the fix: Decision Gate **19/19 unchanged** (as expected — the corpus is blind here),
Discrimination Gate **PASS** (0 unruled `OK → MISS`, 1 held out), suite **4103 passed**.

## Amendment E — the deletion pass (2026-07-30)

Decision 1 says the six hand-seeded weights are *"deleted, not normalized"*, #136 standing directive 1
says *"rungs an equation replaces are DELETED, not suppressed"*, and #188's acceptance names
`baseline_snipe.py`'s folded rungs. Amendments B–D shipped them **staged** instead. This closes that.

**E1 — what was deleted.** The six DAMAGE(15) target rungs (`snipe-for-the-ko` 60,
`snipe-the-evolving-threat` 45, `snipe-the-forced-promotion` 40, `snipe-the-top-threat` 30,
`snipe-the-threat` 20, `snipe-on-the-path` 12) and, with them: `EVOLVING_THREAT_DMG` (their floor),
`_SNIPE_THREAT_PRIZE_FLOOR` + its rescue clause (decision 13, finally as written),
`_snipe_matchup_tactical` + `_MATCHUP_PRIORITY_SCALE` (decision 5), `Context.snipe_relevance_armed`
(it existed only to carry the stand-down), `Context.target_is_top_threat`,
`Board.strongest_threat_rank` and `_strongest_threat_rank` — a whole-bench max computed per decision
solely to answer one argmax equality. Four stale **tuner** overrides were also removed from
`mega_starmie/tuned.json` (`snipe-the-evolving-threat` 48.0, `snipe-the-forced-promotion` 37.0,
`snipe-the-threat` 17.0, `snipe-the-top-threat` 27.0) — ladder-learned weights for rungs that no
longer exist, which `test_tuned_wiring.py` correctly refused to ship.

The three counter rungs are retained (decision 5): disjoint select contexts, knapsack-derived, no
corpus frames to bench a rewrite against. `snipe_relevance` therefore ships ON with **OFF as
documented DEGRADED MODE, never a rollback** — the `attach_value` (19 rungs) / `evolve_value` (4) /
`promote_retreat_value` (11) precedent, now stated in `PROFILE` and asserted by a renamed consumer
test.

**E2 — two constants this ADR claimed and CANNOT delete.** `_ENERGIZED_SNIPE_TIER` (100000) and
`_PREVENT_EX_SNIPE_BOOST` (500) live inside `_body_threat_rank`, and the snipe pick is not its only
consumer: `planner.py:_ko_key_threat_lines` ranks the opponent bench with it for the ADR-0031
`ko_key_threat` Goal-Ladder rung (`planner_key_threat`, shipped ON), and `test_posture_read.py`
covers its ADR-0026 lever-C read modulation. They are snipe-**named** but Planner-**shared**;
retiring them is a Planner behaviour change owing its own gate and is outside decision 5's scope.
This is the same error class as the *"ten constants deleted, none introduced"* claim Amendment B had
to correct — a constant's NAME is not its ownership. Honest count for this issue: **seven constants
and fields deleted, two provably undeletable here.**

**E3 — the deletion makes the Brief steer inert on all-zero boards. OPEN, needs a ruling.** Found by
`test_posture_read.py`, not by the gates. `relevance = tera_veto ⊗ (their_plan × my_route)` is
conjunctive by decision 2, so when `their_plan` is 0 for *every* offered target the product is 0 for
every one of them and the pick falls to option index. The Brief's steer is a MULTIPLIER (decision 5),
and **a multiplier cannot express a preference over a zero**. Measured on the ADR-0051 fixture:
`brief_multiplier` is correctly 1.25 on the briefed Riolu and 0.8 on the draw-engine Solrock, while
`their_plan` is 0.0 for both — Riolu's forward leg standing down because Mega Lucario ex is already
Active (the ADR-0044 discriminator working *correctly*), Solrock bare and unable to attack soon.

Previously `_snipe_matchup_tactical` was a signed ADDEND and steered regardless. Two tests are marked
`xfail(strict=True)` rather than rewritten to match, because rewriting them would launder a
behaviour change into a test edit. **Adding an all-zero tie-break reopens decision 2**, which made
the sides conjunctive precisely so that *"either alone is worthless"* — so this is a user ruling, not
an implementation choice. The candidate shapes, for that conversation: fall back to `my_route` alone
when `their_plan` is uniformly 0; or let a negative `avoid` priority act as an ordering term rather
than a scaler; or accept index order on boards where nothing is relevant.

**E4 — the Decision Gate is now VACUOUS for this instrument, and must be re-pointed.** It compares
*shipped OFF* against *armed ON*. With the rungs deleted, OFF is index order, so the comparison is
"the scalar versus nothing": this run reports **12 FIX, 0 REGRESSION, 1 neutral** where every prior
run reported 19/19 unchanged. Nothing improved — the baseline collapsed. **A gate that can only ever
report FIX cannot detect a regression**, which is the one thing ADR-0072 built it to do. Before the
next change touches this instrument, `snipe_decider_sweep.py` needs its OFF column replaced by a
RECORDED baseline of armed picks, exactly as `leaf_lab.py` uses `data/leaf_lab/baseline.json`. Filed
rather than fixed here, because inventing a baseline format mid-deletion is how a gate quietly stops
gating.

The **Discrimination Gate is unaffected** and still discriminates — it compares against a recorded
baseline, not against a live OFF arm, which is precisely the property E4 says the Decision Gate now
lacks. Re-run: **PASS**, 0 unruled `OK → MISS`, gated on 266, 1 held out to #165. Suite **4094
passed, 1 skipped, 5 xfailed** (the two new strict xfails are E3).

## Amendment F — rebased onto Issue #217; what it corroborates, and the switch the deletion orphaned (2026-07-30)

Issue #217 (*deny's derived clock is a tiebreak, not a deadline* — **ADR-0084**, a different ADR)
merged with both go/no-go gates passing. It was checked for re-grill triggers against this ADR before
rebasing, because it rules on the same two primitives snipe reads: `turns_to_afford` and the clock
delta.

**F1 — it CORROBORATES decisions 3 and 11 rather than conflicting with them.** Its decision 1 rules
that *"a clock DELTA may never be substituted for a clock READING"* — a reading is a *when*
(`turns_to_afford = 1` → armed next turn), a delta is a *payoff* (`strip_shift` → this buys N turns),
and substituting one for the other imports VALUE into a timing term, the scale crossing ADR-0080
decision 1 found underivable. This instrument already splits exactly that way and did so independently:

| side | term | kind | #217's verdict |
|---|---|---|---|
| `their_plan` | `imminence = … / 2^turns_to_afford` | **reading** | the correct use of a reading |
| `my_route` | `ko_delta₂ = f(turns_to_ko_before, after)` | **delta** | legitimate — *"at target-pick time the card is already spent, so the cost is sunk and maximising payoff is the right objective"* |

That last quote is #217 justifying its own target-pick tiebreak, and it is the same argument decision
11 makes for `ko_delta₂`. Two instruments reached the reading/delta split independently; no re-grill.

**F2 — tie exposure MEASURED, and it is materially lower than deny's.** #217 decision 2 found **28 of
47** contested deny frames (60%) have a tied argmax resolved by engine option order — the ADR-0062
defect — and added a lexicographic `strip_shift` tiebreak. The same measurement over this
instrument's corpus, run before rebasing:

```
DAMAGE frames replayed        : 19
  >=2 nonzero-relevance opts  : 9      (a real choice exists)
  TIED argmax                 : 2      (22%)
     81905522-75   2 options tied at 0.385714
     85164605-48   2 options tied at 0.214286
```

`81905522-75` is decision 7's RECORDED MISS — two IDENTICAL Riolu, where no board-derived signal can
split them by construction, so it is unbreakable rather than unsolved. `85164605-48` ties and lands on
the ruled option **by engine option order**, i.e. correctly by luck. Recorded as a known exposure, not
fixed: a tiebreak is only worth adding once a frame shows index order landing the WRONG way, and none
does. #217's lexicographic pattern is the shape to reuse if one appears.

**F3 — the deletion pass ORPHANED a shipped kill-switch, and this is Amendment A's defect class.**
#217's own Amendment A found that ADR-0080's mandated `_DENIAL_FORWARD` discount *"was never applied
to the relevance read — its only consumer was `_denial_at`, the OFF path."* A doctrine that lived only
on the path nobody armed. Auditing this build for the same shape found the mirror image, created by
Amendment E: a doctrine whose only consumers were the rungs we **deleted**.

`board.evolving_wincon_on_bench` now has **zero readers**. Its only consumers were the
`and not (c.board.evolving_wincon_on_bench and not c.target_is_strongest_forward)` clauses on three of
the six deleted rungs. The `evolving_wincon_priority` PROFILE flag therefore gates a computation
nothing reads, and is **inert** — measured on the f22 CRITICAL it exists for:

| `evolving_wincon_priority` | pick |
|---|---|
| `True` (shipped) | `[1]` Staryu ✓ |
| `False` | `[1]` Staryu ✓ |

The *doctrine* survives — Amendment C4 already showed the scalar reaches Staryu without it, because
the `30 + 20 + 40 = 90` sum it defended against no longer exists. What does not survive is the flag's
honesty: `PROFILE` advertises a shipped switch backed by a CRITICAL correction (ms 85164131 f22) that
now changes nothing on any board.

**This is left OPEN for a user ruling rather than resolved here.** Retiring a shipped kill-switch whose
provenance is a CRITICAL is a decision, not a cleanup, and the deletion pass has already made one such
call this session. The options are (a) retire `evolving_wincon_priority`,
`Pilot._evolving_wincon_on_bench` and `Board.evolving_wincon_on_bench` together, citing f22 under the
scalar as the witness that the doctrine is carried; or (b) keep the flag and record that it is
deliberately inert pending a future consumer. Recommendation is (a) — an inert switch in the
deployment record is exactly the "two contradictory models" problem #217 decision 5 retired
`_DENIAL_BENCH` to avoid, one level up.

**F4 — two independent corroborations of this branch's own findings.** #217's Amendment B attributes
`84071010|0|decision|15` to a **clean tree** across four stashed configurations, confirming
Amendment B's control run here; and it records that the leaf baseline, captured at `e4c46ca`, is stale
against Issue #213's `scaled_threat_rank` — the same staleness Amendment D worked around by re-running
both gates rather than carrying numbers forward.

**F5 — the S4 family inconsistency now has an owner.** Amendment E flagged that deny ships OFF while
snipe ships ON. #217's Amendment B took its pre-registered ship-dark fallback and chartered
**Issue #228** for deny's arming, explicitly calling OFF *"a KNOWN DEBT, not a decision."* So the
inconsistency is a sequencing artefact with a filed resolution, not an unowned divergence.

**F6 — NINTH collision, and this ADR is the record holder.** Issue #217's ADR took **0084**, having
skipped 0083 in the belief that Issue #188 held it — a correct skip for the wrong reason, since 0083
had gone to Issue #213. This ADR has now moved **0082 → 0083 → 0084 → 0085** across three rebases in a
single day. `main`'s index had already predicted the landing spot before this branch rebased.

## Amendment G — `evolving_wincon_priority` is RETIRED (2026-07-30, user ruling)

Amendment F3 left this open. The user ruled: *"retire it (flag + `_evolving_wincon_on_bench` + the
Board field), citing f22 under the scalar as the witness."* Done.

**Deleted:** the `evolving_wincon_priority` `PROFILE` entry and ctor flag, `Pilot._evolving_wincon_on_bench`,
and `Board.evolving_wincon_on_bench`. The flag had gated a stand-down that kept the current-attacker
rungs from burying `snipe-the-evolving-threat` (+45) under their `30 + 20 + 40 = 90` sum. Amendment E
deleted all six rungs, which left the field with **zero readers** and the flag changing no pick on any
board — measured directly on the ms 85164131 f22 CRITICAL it was built for: Staryu either way.

**Why retire rather than leave it inert.** A `PROFILE` entry is the deployment record's answer to
"what ships"; an entry that advertises a CRITICAL-backed behaviour it no longer has is a false answer,
and the next person to read it would reasonably believe the stand-down is live. That is the same
failure #217 decision 5 retired `_DENIAL_BENCH` to avoid — *"the codebase currently holds two
contradictory models of promotion… every future deny change would have to pick one"* — one level up:
here the two models are "the rungs stand down under a switch" and "the scalar orders continuously",
and only the second exists in code.

**The witness, and why it is stronger than what it replaces.** `test_snipe_evolving_wincon_f22.py`'s
kill-switch test asserted the blunder was *restorable* by flipping the flag off — a claim about the
mechanism. That claim is no longer posable, so the test now asserts the **doctrine** instead: on f22
the developing win-condition pre-evo must outrank the energized 1-prize current attacker, and it must
do so by ORDERING rather than by anything standing down. Staryu earns the `forward` leg (its line
reaches Mega Starmie ex, a 3-prize wincon not yet in play); Cinderace has no forward payoff to bank.
The test also asserts Cinderace stays *scorable* — a stand-down that zeroes every option is index
order with a bad prior, which is the degeneracy `test_neither_target_scores_zero` was written to
catch and which the deletion pass must not reintroduce.

This is the ADR-0060/0062 move applied to a boolean rather than a threshold: **the graded term
replaces its guard family, and the guard is deleted rather than left switched on.** Three such guards
have now gone this way in Issue #188 — `_SNIPE_THREAT_PRIZE_FLOOR` (decision 13), the six rungs'
`snipe_ko_available` / `evolving_wincon_on_bench` stand-down clauses (Amendment E), and now the flag
that fed the second of those.

**Note for the S4 family.** `snipe_prize_redundant` and `forced_promotion` (ADR-0044) are NOT in the
same position and were deliberately left alone: the scalar *consumes* them as leg-scoped guards
(decision 4), so they have live readers and their switches still change picks.

Gates re-run after the retirement: Discrimination Gate **PASS**, suite **4102 passed, 1 skipped,
5 xfailed**.

## Amendment H — E3 resolved: a Brief TIEBREAK beneath relevance (2026-07-30, grilled)

Amendment E3 left the Brief steer inert on all-zero boards and flagged it as needing a ruling because
any fix appeared to reopen decision 2. Grilled 2026-07-30; **two decisions locked**, and decision 2 is
NOT reopened.

**H1 — the fix is a LEXICOGRAPHIC tiebreak, not a term.** Relevance remains the sole ranker. Among
options scoring **exactly** equal, the signed MatchupPlan/Brief priority orders them instead of the
engine's option index. Because a comparison key is not a value, `relevance` arithmetic is untouched
and decision 2's *"either alone is worthless"* stays literally true — no amendment to the product.

This is Issue #217 decision 2's shape, adopted deliberately rather than reinvented: *"Relevance stays
the sole ranker; `strip_shift` orders only options already exactly tied."* It also subsumes
**Amendment F2**: 2 of 9 contested corpus frames carry a tied argmax, one of which
(`85164605-48`) lands correctly only by engine order. One mechanism closes both findings.

**Three measurements shaped this, two of them refuting candidates I had recommended.**

- **The `my_route` fallback is refuted.** Falling back to `my_route` when `their_plan` is uniformly 0
  was the obvious fix and does not work: on the witness fixture `my_route` is **0.500 for both**
  targets, so it produces a tie at 0.500 and falls to index order anyway.
- **There is no corpus anchor.** **0 of 19** committed `DAMAGE` frames reach an all-zero board; the
  only witness is a SYNTHETIC fixture (hand-built `state()`/`poke()`, the ADR-0051 threading proof).
  Recorded because this repo's standing discipline is *"refinements await a frame"*, and this
  refinement proceeds on a requirement (REQ-POSTURE-0006/0007) rather than on a corrected frame — a
  weaker warrant, and the honest reason to prefer the narrowest mechanism that works.
- **No corpus frame changes.** On `81905522-75` the two tied options are both card 677 with
  IDENTICAL priority (`89.9999…`), so the tiebreak is itself tied and decision 7's recorded miss
  **stays missing**. On `85164605-48` the relevance-tied pair share priority `0.0`. Nothing reorders.

**H2 — it FIRES at relevance zero, diverging from the sibling on exactly one line.** Deny's tiebreak
guards `if mine is None or not rel: return 0.0` — *"absent reading, or nothing relevant — not a
zero."* Snipe's omits `not rel`.

The divergence is principled, and the principle is the **source of the ordering signal**:

| instrument | ordering signal | source | fires at relevance 0? |
|---|---|---|---|
| deny (ADR-0084) | `strip_shift` | **derived** from the same board | **no** — would re-assert a fact relevance already priced at nothing |
| snipe (this) | Brief priority | **independent authored scouting** | **yes** — carries information the board reads do not |

A zero `their_plan` says the threat clock is silent about this body, not that the Brief is wrong about
it. Decision 2's *"authored scouting can never promote a whiff"* is preserved exactly as written: it
protects a whiff from outranking a **non**-whiff, and on an all-zero menu there is nothing of value to
promote it above.

**Inherited from the sibling without change:** the epsilon is DERIVED, not hardcoded — half the finest
distinction relevance draws on this menu, falling back to `1 / K` (one damage unit) when the menu
draws none, which is exactly the all-zero case. Hardcoding it is the ADR-0063 failure mode (a constant
sized against arithmetic that later changes, rotting silently). It stays tiny by construction so it
orders a tie without swamping the other tacticals summed into the same option score — the error an
earlier deny draft made by bounding the bonus with its own relevance.

**Build notes carried forward.** *(Two of these were amended by the build itself — see "H3, what the
build changed about H" below.)* The tiebreak must live in the Pilot consumer, not
`snipe_relevance.py`: it needs the menu's PEERS and the pure scorer is per-target by construction. It
rides the existing `snipe_relevance` flag — it is part of that instrument, and directive 1 forbids
minting a second switch for it. Its seam test must assert that a tiny positive score on a
previously-zero option cannot flip an ADR-0072 **Endorsement Claim** (`score > 0`, "is this slot taken
at all"); `DAMAGE(15)` is a forced select so it cannot manufacture a snipe that would not happen, but
that is a property to assert rather than assume. The two `xfail(strict=True)` tests in
`test_posture_read.py` are the acceptance witness — strict, so the fix cannot land silently.

### H3 — what the build changed about H, and why (2026-07-30)

Two of H's build notes were amended by building it. Recorded here rather than silently, because a
spec-axis review correctly flagged both as deviations from the amendment as written.

**The arithmetic moved to the pure module; the PLUMBING stayed in the Pilot.** H said *"the tiebreak
must live in the Pilot consumer, not `snipe_relevance.py`: it needs the menu's PEERS."* That reason is
sound and still holds — `Pilot._snipe_brief_peers` collects the menu and remains in the consumer. But
it applies to peer COLLECTION, not to the arithmetic over an already-collected list, and putting the
arithmetic in the Pilot forced the seam test to reimplement it to assert it. `snipe_relevance.brief_tiebreak`
is now the pure function, mirroring the module's existing scoring/plumbing split.

**The epsilon is SHARED with deny, not merely inherited.** H said *"inherited from the sibling without
change"*, which a standards-axis review flagged as the strongest smell in the diff: the derivation was
duplicated verbatim across two files, and the copies had **already drifted** — snipe's docstring cited
`_deny_strip_tiebreak`, a symbol that does not exist (the sibling is `_deny_strip_delta_tiebreak`).
Duplicating to avoid touching a shared module is the worse option under this repo's build ranking, so
the quantum is extracted to `currency.tiebreak_bonus` and BOTH instruments call it. **Deny's shipped
tiebreak was edited under this issue** — behaviour-identical, its own tests green — which is a
cross-issue touch worth naming rather than burying. The GUARDS stay separate, which is the entire
point of H2.

**Three defects in this build's own tests, all found by review and all the same class — an assertion
that cannot fail:**

1. `assert "brief_tiebreak" in inspect.getsource(Pilot._snipe_brief_tiebreak)` — satisfied by the
   method's own `def` line, so it passed unconditionally. Replaced by a behavioural spy.
2. The Endorsement-Claim test ran on a fixture drawing NO relevance tie (`[0.0, 0.375]`), so every
   bonus was `0.0` and it passed with the feature deleted; it also never computed a score. Its claim
   was backwards, too: the tiebreak **does** raise a zero score — that is its job — and what makes it
   safe is that `DAMAGE` is a FORCED select. Now asserted in that direction.
3. `test_snipe_hunts_the_briefed_preevo_end_to_end` asserted `decide(obs) == [0]`, which index order
   already returns on that board, so one of the two named acceptance witnesses was inert. Now asserts
   a strict score ORDERING, which only the tiebreak can produce.

Verified by **deletion**: with `_snipe_brief_tiebreak` removed from the score sum, both witnesses now
fail. Before the fix only one did. That mutation check is the thing that should have been run when the
witnesses were written, and is the reason all three defects reached review at all.

**One latent robustness gap closed on the way:** peers are now DEDUPED by bench slot, as the deny
sibling dedupes by its `(area, index)` key. Two options naming one body would otherwise enter the list
twice and the strict-maximum test would read the duplicate as a rival, silently muting the tiebreak on
a board where the Brief does express a preference. No corpus `DAMAGE` frame offers a body twice, so
this guards a shape the engine may pose rather than fixing one it does.

## Amendment I — E4 resolved: the Decision Gate gets a RECORDED baseline (2026-07-30, grilled)

Amendment E4 found this instrument's Decision Gate vacuous after the deletion pass. Grilled
2026-07-30. **The first thing the grill established is that E4 understated the problem: it is not
snipe's, it is every decider swap's, and all four were broken simultaneously with none of them
saying so.**

**Measured, not inferred.** ADR-0072 defines the Decision Gate as *"the phase's
`tools/train/probes/*_decider_sweep.py`"*, and each compares the shipped agent against its own
kill-switch OFF. That was correct at the swap, when OFF *was* the incumbent rung pile. Every phase
then DELETED its pile — tracker directive 1 requires exactly that — and no gate was re-pointed:

| pile | rungs remaining | was | its sweep |
|---|---|---|---|
| `baseline_promote` | **0** | 12 | `promote_retreat_decider_sweep` |
| `baseline_energy` | 3 | 22 | `attach_decider_sweep` |
| `baseline_evolution` | 2 | 6 | `evolve_decider_sweep` |
| `baseline_snipe` | 3 (counter rungs) | 9 | `snipe_decider_sweep` |

Run on the real corpus: `evolve_decider_sweep` reports **4 FIX, 0 REGRESSION**; `snipe_decider_sweep`
reports **12 FIX, 0 REGRESSION**. With the pile gone, "OFF" is an empty scorer whose argmax falls to
option index, so each gate compares its equation against nothing. **A gate that can only ever report
FIX cannot report the one thing ADR-0072 built it for** — and a vacuous gate is worse than an absent
one, because `PASS` is read as evidence. All four had been reporting `PASS` in this state.

**The fix — `tools/train/decider_lab.py`.** One capture over every replayable Correction, recording
what the shipped agent DECIDES; the gate diffs against a committed baseline
(`data/decider_lab/baseline.json`, 332 frames, `git_rev`-stamped). `--context N` gates one phase's
frames. The diff lives in `train/gates.py` beside `leaf_lab_diff` so the two gates cannot drift in
shape, and it keys through `frame_key_of` so one Held-out ruling holds a frame out of BOTH.

The Discrimination Gate was never exposed to this for one structural reason, and it is the whole
lesson: **it diffs against a recorded capture, never against a live switch.**

**Said plainly: this REPLACES the Decision Gate rather than repairing it.** The original asks *"did
this swap regress against the incumbent?"* — a transition instrument, meaningful exactly once. Once
the incumbent is deleted there is no transition to measure. The recorded baseline asks *"did this
build regress against the last blessed build?"*, which is a different and standing question, and
strictly more end-to-end than the leaf-level Discrimination Gate: it compares the decision actually
played, not the leaf ranking behind it.

**Verified by MUTATION, because "it passes" is exactly the evidence that failed here.** With the
snipe ordering inverted (`return -K * relevance`), the new gate reports **12 REGRESSION and FAILS**
on the same frames the old sweep called FIX. A weaker mutation is recorded too, because it surprised
me: dropping `share` from `my_route` changes **no** decision on this build, though the grill had
recorded it as costing `82756021-57` (16/19). That measurement predates the context fix, the deletion
pass and the tiebreak — a reminder that a measured claim expires when the thing it measured moves.

**The four sweeps are now DIAGNOSTICS**, bannered as such, with the two that called
`print_gate_report` no longer titling themselves the Decision Gate. Their per-leg breakdowns remain
worth running; `decider_lab.py` deliberately does not duplicate them.

**Cross-issue touch, named rather than buried:** this edits probes owned by Issues #139, #140 and
#141 (all closed). The alternative was leaving three known-vacuous gates on `main`.

**Baseline discipline, inherited verbatim from the leaf lab:** it is a RULING RECORD. CI must never
auto-recapture it, or the gate becomes a mirror that agrees with whatever it is shown.

## Amendment J — the rebuild's owed work, closed (2026-07-30)

Amendment I shipped the instrument and listed five things it did **not** settle
(`docs/plans/decision-gate-rebuild-handoff.md`). All five are closed here. Two of them turned on a
measurement that contradicted the hand-off's own expectation, which is the part worth reading.

### J1 — a Correction's `correct` is a CONSTRAINT, not the whole answer

The open question was whether `correct ⊆ chosen` should count as agreement for multi-pick contexts,
or whether those Corrections should record the full answer. **Ruled: satisfaction is `correct ⊆
chosen`** (`gates.satisfies_human`).

The reasoning is that the two sides speak different vocabularies. A Correction's `correct` names *the
card the ruling was about* — exactly what ADR-0082's Claim vocabulary records — while a multi-pick
select returns **every** index the engine demands. Equality across those is simply the wrong test,
and it was measurably wrong: `DISCARD` read **1/12** purely because the agent picks `[2, 3]` where
the ruling says `[2]`. Under satisfaction the same corpus reads **10/12**, and the corpus-wide rate
moves **220/331 → 230/331 with no decision changed**. Ten "disagreements" were never disagreements.

The rejected alternative — rewrite those Corrections to record the full answer — would put indices
into a human ruling that the human never ruled on, destroying the one thing `correct` is for. Read
the record correctly rather than editing the record.

**One predicate, both readings.** `decider_lab_diff` classifies direction through the same function
as the agree-rate readout, so the gate and the report cannot drift into two ideas of "matches the
human". This makes the gate **strictly more sensitive** on multi-pick frames, never less: under
equality a move from `[2, 3]` to `[3, 4]` against `correct: [2]` classifies NEUTRAL and passes;
under satisfaction it is the REGRESSION it actually is.

**The guard that makes `⊆` safe.** The empty set is a subset of everything, so a naive reading would
make `correct: []` vacuously satisfied by every frame — a gate-shaped hole. But `correct: []` is not
absent, it is a recorded **DECLINE**, and **eleven** sit in the corpus today (nine `MAIN`, one
`SETUP_BENCH_POKEMON`, one `TO_HAND`), one of which — `86088989|0|decision|3` — the agent genuinely
satisfies. So a DECLINE is matched EXACTLY, never by subset, and stays labelled and gated. Issue #229
owns whether the *writer* should keep rejecting a shape the corpus already contains.

### J2 — the four sweeps lose their OFF arm

Amendment I bannered them DIAGNOSTIC but left the dead limb attached. Removed now, because a number
that cannot come out any other way is not evidence and `12 FIX` invites being read as merit. Verified
before cutting, not assumed — every switch ships **ON** through `common/runtime.py`, the single
deployment PROFILE, so in every case the OFF arm scored an emptied pile:

| probe | pile | rungs left | what OFF actually scored |
|---|---|---|---|
| `promote_retreat_decider_sweep` | `baseline_promote` | **0** of 12 | a literally empty scorer — the option indices in order |
| `attach_decider_sweep` | `baseline_energy` | 3 of 22 | near-empty |
| `evolve_decider_sweep` | `baseline_evolution` | 2 of 6 | the 2 survivors are Gates the NEW arm never zeroed; **all five ids it did zero no longer exist** |
| `snipe_decider_sweep` | `baseline_snipe` | 3 of 9 (counter rungs) | the six *target* rungs, the ones under test, all gone |

Each now takes ONE reading — the shipped agent, against the human, through `satisfies_human` — and
keeps the per-leg breakdown that is the actual reason to run it (`decider_lab` records decisions,
never the terms behind them). They exit 0 always: they report, they do not gate. Attach's
`--scale`/`--pref` retune search is untouched. Post-strip readings: snipe **17/19** with both misses
the ADR-0085 decision 7 recorded ones, evolve 16/24, attach 78/133, promote/retreat 123/133. Each
also halves its cost, from two engine-backed Pilot builds per frame to one.

### J3 — the baseline moves to a `main` SHA, and it is pure bookkeeping

Re-captured at **`e50735a`** (main's tip) off the feature-branch commit `6328ab7`. The diff was run
first, as decision 2 requires: **zero flips**, so there was nothing to rule. Exactly two fields moved
— `git_rev`, and `agree` 220 → 230 from J1's predicate — and **not one of the 332 rows**. Recorded in
`docs/ci.md`'s new provenance table, mirroring the leaf baseline's.

### J4 — the Decision Gate gets a `main` watchdog, because the objection failed

The hand-off argued *against* rushing this: the gate "replays 332 frames through a full Pilot and is
materially slower than the leaf diff, so measure the runtime before proposing it." Measured
back-to-back on one box (py3.12):

| gate | frames | wall |
|---|---|---|
| `decider_lab diff` | 332 | **31.6 s** |
| `leaf_lab diff` | 267 | 71.0 s |

It is **~2.2× faster** than the gate that already had a watchdog. The objection was a guess and the
measurement retired it — the same "measure before asserting" correction this ADR has now had to make
three times (the fold's prize-marginal recommendation, Amendment I's `share` claim, and this).
`.github/workflows/decider-gate-main.yml` runs it on every push to `main`, never re-captures the
baseline, and warns rather than fails on a shifted corpus. CLAUDE.md's "one main-watchdog gate" rule
becomes two.

### J5 — the 111 blessed disagreements are triaged, and there are 101

`docs/plans/decider-disagreement-triage.md`. First finding is J1's: **ten of the 111 were a
vocabulary artifact, not a defect.** The remaining 101 sort by `data/corrections/reviewed.json`
disposition:

| tier | disposition | n | the work |
|---|---|---|---|
| B | `covered` — reviewed, believed handled, still missed | 28 | **start here** |
| C | never reviewed | 55 | fresh rounds (Issue #146) |
| A | `refuted` — the label is wrong | 18 | none owed; the agent is right |

**The lead worth naming here: 13 of the 28 `covered` frames rest their coverage on a rung the
deletion passes DELETED** — `dont-waste-discard-energy`, `concentrate-energy-on-wincon`,
`build-active-wincon`, `power-up-attacker`, `conserve-burst-when-no-ko`. Each was closed in a blunder
round as handled by a rule that no longer exists, and the agent still misses the frame. That is this
ADR's own lesson recurring one level down — *a measured claim expires when the thing it measured
moves* — and it is a direct test of the premise every deletion pass ran on, that the new equation
subsumes what it retired.

Tier A also means the agree rate is **pessimistic**: 18 of the 101 are refuted labels, so the honest
denominator for "is the agent right" is nearer 230/313 than 230/331. Recording that in the corpus is
a Corrections-schema question and stays with ADR-0082 and Issue #229.

## Alternatives rejected

- **Fold onto the prize marginal as chartered.** 7/19 against the shipped 17/19, and it restores the
  pre-ADR-0044 blunder on `83667237-107`. Rejected on the measurement.
- **Build a magnitude-shaped chip-conversion Δ** (the threshold-race as a prize rate or prize fraction).
  The recommendation this grill opened with, and **refuted by its own measurement**: 11/19 and 10/19,
  and the `57`/`107` pair makes the failure structural rather than a calibration miss. Recorded because
  the sequencing is the lesson — the same "measure before asserting" correction ADR-0078 Amendment C had
  to make, in the same series.
- **Keep the rungs; retire the fold and close Issue #188** with the impossibility proof recorded.
  Honest, cheap, and strictly better than the two refuted options — snipe is at 17/17 on every frame
  anyone still believes. Rejected because it leaves the additive stack's documented blunder class live
  and permanently abandons the fold on the one pile the ADR-0065 story still names as un-folded.
- **Normalize the six incumbent weights into `[0,1]`.** Behaviour-preserving by construction and the
  smallest possible change, but it keeps six undetermined constants where the scalar keeps one — the
  `_PRIZE_UNIT = 12` shape at smaller scale, and the same objection ADR-0080 used to reject a bucketed
  relevance enum. It also preserves the additive stack, i.e. the actual defect.
- **Re-rule the 13 flipped corpus frames to fit the marginal.** Asks the corpus to bend to a value term
  demonstrably answering the wrong question, including one frame whose re-ruling would reinstate a fixed
  blunder. Backwards.
