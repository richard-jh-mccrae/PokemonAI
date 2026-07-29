# ADR-0082 — Snipe is a CATEGORICAL RELEVANCE instrument too: the fold collapses the additive rung stack into one [0,1] scalar under hard gates, not onto the prize marginal

**Status:** Proposed — grill IN PROGRESS (`/grill-with-docs` on Issue #188, 2026-07-29). **Decision 1
locked**; further decisions appended as they resolve. Build = Issue #188 (rechartered by decision 1).

**Number claimed at grill time** (`docs/adr/README.md`: *next free number 0082*). Six collisions in
four days precede this one, so the number is a rebase artifact rather than an identifier — **cite the
issue alongside it** ("ADR-0082, Issue #188").

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
Lucario ex top at `3.0` — which is exactly the pre-ADR-0044 blunder pick that fixture pins as
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
`their_plan`'s magnitude should come from (an open decision at time of writing):

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

### The fork the gate exposed: gate SCOPE (open at time of writing)

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

Decision 1's gate list is therefore too coarse and needs amending; which way is the next locked
decision, not assumed here.

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

**6. `my_route = max( 1/⌈hp_remaining / max_rider_snipe⌉ , min(1, prize_value / my_prizes_remaining) )`
— ungated, with NO membership boolean and NO floor constant.** Two alternative reasons a body helps
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

**Policy note (owed, not yet ruled).** The prototype read the curve at `incoming(t=1, charged=None)` —
the **ceiling** policy — and reached 17/19 there. The design doc's per-consumer conservatism table
(ruling 2) specifies something more specific for this consumer: snipe-prep is *"existence-gated ceiling
on the THREAT, slow on the INVESTMENT."* Pinning that split is an open ruling for the build, not
settled by the prototype's default.

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
— which pins that divergence deliberately — must be re-baselined and the doom sweep re-run. Splitting
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

The forced-promotion leg therefore needs a **derived grade** rather than a saturating constant — an open
ruling, not settled here.

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
the fixture written to pin it** ("the energized ex, at 6 prizes remaining"). Its fate is the last open
ruling.

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
