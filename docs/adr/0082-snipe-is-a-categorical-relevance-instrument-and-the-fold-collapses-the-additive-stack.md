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
