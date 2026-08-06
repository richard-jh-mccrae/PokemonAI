# ADR-0122 - The `_TO_HAND` grab equation was BUILT to spec and measured SIX FRAMES WORSE — five things the assignment must learn first

**Status:** **Rejected as specified** (Issue #406, built and measured 2026-08-06). The build is
preserved at commit `bd9187d7` and reverted by its successor; Issue #406 returns to
`status:1-grilling` carrying the five findings below as its agenda. **Does not amend ADR-0023** —
the shared-oracle invariant it asserts is untouched, and this ADR is evidence *for* it. **Amends
nothing else**: no shipped behaviour changed. Retains one artifact, `tools/train/grab_sweep.py`,
because the successor needs the same instrument and it now grades the incumbent.

This is ADR-0119's shape — a change justified by what it measured rather than by what it shipped —
except that here the measurement said *stop*.

## Context

Issue #406's premise is correct and was verified at `HEAD` before any code was written, by the
`/implement` step-0 protocol. Every claim reproduced:

| the issue claims | measured on `44734ca5` |
|---|---|
| 42 fetch rungs, 23 gated on `_TO_HAND` | 42; 23 (plus 18 `_PLAY`, 1 `_ATTACH_TO`) |
| `prefer-wincon-line-piece` carries a `_TO_ACTIVE` leg | `doctrine_fetch.py:838` |
| no equation exists at ctx 7 | `grep _TO_HAND src/common/pilot.py` → rung gates and `_grab_value_of`, nothing else |
| *positive control* | the same grep finds `_deploy_decision` resolving `deploy_marginal` and `_discard_needs_pick` resolving `cheapest_removal`, so the instrument finds an equation where one exists |
| 31 ruled ctx-7 corpus frames, all `maxCount == 1` | 31; `(0,1)` × 25, `(1,1)` × 6 |
| Night Stretcher is `zone: "discard"` | `card_effects.json` id 1097 |

So the defect the issue names is real: `doctrine_fetch._greedy_grab` states it against itself —
*"At a `_TO_HAND` grab there is no equation, only one-sided endorsement rungs"* — while both sibling
contexts have one. The issue's **answer** is what does not survive.

## Decision 0 — HALF THE VALIDATION BASE IS UNGRADEABLE, and this supersedes every count below

**A follow-up select is only gradeable if the decision that opened it was correct.** A `_TO_HAND`
menu exists because the agent played a search. If playing that search was itself the blunder, the
board is one the agent should never have reached, and the grab it makes there is not evidence about
the grab. This is `retest_span`'s own doctrine (ADR-0049) — *"it stops at the first divergence,
because every later obs was produced by the line the agent originally played"* — applied WITHIN a
turn rather than across turns, which nothing was doing.

The developer ruled it on two frames during this re-grill (*"this one should not have played ultra
ball in the first place. should have just placed Riolu on bench"* … *"also should never have played
ultra ball in this situation"* … *"both cannot be honestly tested because the first decision was
wrong"*). Generalised and measured over the whole ctx-7 base by scanning for a ruled Correction on an
earlier frame of the SAME episode and turn:

| | ctx-7 frames |
|---|---:|
| no ruling recorded | 1 |
| **OFF-POLICY — an earlier decision in the same turn was itself ruled wrong** | **15** |
| **gradeable** | **15** |

**On the 15 gradeable frames the incumbent ladder scores 14/15.** It has exactly ONE demonstrable
defect at this seam (`86088989-29` — Lillie's Determination over Team Rocket's Petrel, via Meowth
ex's bench-drop tutor). Applying the same filter to the specified build's recorded misses — 6 of its
13 are off-policy — puts it at **8/15**.

|   | on all 30 ruled | on the 15 GRADEABLE |
|---|---:|---:|
| incumbent | 25 | **14 / 15** |
| the spec | 17 | **8 / 15** |

So the gap widens (6 frames on a 15-frame base) and, far more importantly, **the thing the issue set
out to replace turns out to have one demonstrable defect.** Issue #406 proposed retiring 23 rungs
at a seam where the incumbent is wrong once on evidence that can honestly be tested.

**The detector is sound but INCOMPLETE, and that matters in the honest direction.** It only fires
where somebody happened to file a Correction on the predecessor. `84889011-7` shows no ruled
predecessor and is still off-policy — the developer ruled it directly, and it is carried in
`grab_sweep._RULED_OFF_POLICY` with provenance. So 15 is a floor: the true gradeable base is at most
15 and may be smaller, which can only make the incumbent look better and the case for replacing it
weaker.

**This is a corpus-wide methodological finding, not a ctx-7 one.** Of the 372 correction frames, 93
are non-MAIN — every one a follow-up whose validity depends on its MAIN predecessor, and none of them
checked. Anything graded on follow-up contexts (ctx 8 `_DISCARD`, 15 `_DAMAGE`, 21 `_ATTACH_FROM`, 4
`_TO_ACTIVE`, …) inherits the same exposure.

## Decision 1 — The specified build is worse than the incumbent, and the measurement is controlled

Built exactly as ruled (R1–R10): `needs.keep_v2` over `hand ∪ {one candidate}` as the add-marginal,
`capacity=None`, `include_general=True`, `intrinsic=0.0`, crossing to the damage scale as a
dimensionless ratio through `DEPLOY_BAND`, folded into `_option_trace`'s `tactical`; all 23 rungs
deleted; `fetch-deck-priority` demoted to an `_order_key` ordering leg.

Replayed over the issue's own validation base — the 30 ruled ctx-7 correction frames that name a
`correct` option. **The two numbers that matter come from `tools/train/grab_sweep.py` run against
real trees, not from a patched Pilot:**

| tree | configuration | agrees with the human |
|---|---|---:|
| `8dbde0fe` (shipped) | incumbent — 23 rungs, no equation | **25 / 30** |
| `bd9187d7` (the build) | **the spec** — rungs deleted, equation on | **17 / 30** |

**Eight frames worse.** A supporting four-way sweep with a fresh Pilot per frame placed the other
arms — both (19), neither (15), ordering-only band → 0 (23), and rungs deleted at 4× band (**14 —
below doing nothing at all**, which is what says the ranking is actively wrong rather than merely
incomplete). Its ORDERING is sound and its positive control passed (the arms are distinguishable),
but two of its absolute values are not quotable, for a reason that is itself a finding — see
Decision 3. The clean pair above supersedes them.

Read against the clean incumbent: the rung ladder is worth **ten frames** over an empty seam
(15 → 25); the equation is worth **two** (15 → 17).

Two defects of the build's own were found and fixed before this table was taken, both from rulings
already in the code, and neither was the problem (they moved the corpus 14 → 17):

* **LINE slots were not re-stamped with the acquisition deadline.** `_deploy_decision` does exactly
  this and `_deploy_line_deadline` says why: the resolver supplies the held-PAYOFF direction, *"which
  is structurally 99 for a held base … deploying a base is precisely what STARTS its clock."*
* **Resupply asked `deck_contains_probability`** (*"could a copy be prized?"*, ≈1.0 whenever any copy
  remains) instead of *"will I draw one in time?"*. Every line slot whose class the deck still held
  discounted to ≈0 — which is ADR-0086 decision 2's already-ruled defect, *"With the deck always
  holding a twin, that zeroed nearly every deploy in the corpus"*, walking back in one seam over.

A second, independent instrument agrees. The full suite under the specified build:
**54 failed, 5132 passed** — including `test_hyperclosure_corpus::test_correction_ranks_the_human_pick_top`
and nine blunder regression fixtures across six files.

Acceptance criteria 5 (*delete all 23*) and 7 (*no ruled frame moves*) cannot both hold for this
design. **Criterion 7 is the binding one**, and it is the issue's own bar.

## Decision 2 — The 13 moved frames are not a tuning gap; they are five things `needs` cannot represent

Every moved frame traces to a specific structural limit, verified at source. This is the successor's
agenda, and none of it is reachable by re-weighting.

### F1 — a LINE has one slot per CLASS; a fetch needs one per COPY

`needs.line_slots` opens with `if not primary_met: out.append(Slot("line", ...))` — a copy already in
play **deletes the slot entirely**. The PAYOFF is compensated: `SUCCESSION_ROLES`
(`win_condition` / `primary_attacker`) keeps a half-tier `:succ` slot because *"the plan needs the
line to survive attrition (KOs and prizing take bodies)."* The **base gets no such insurance** — and
bases are precisely what attrition takes, and precisely what a fetch is for.

Measured on `82228640-9` (Staryu active, a Mega Starmie ex already in hand, empty Bench):

```
Staryu           add= 9.00   general:1030  9.00                     <- NO line slot: primary_met
Mega Starmie ex  add=13.50   line:1031 30.00 + :succ 15.00 + general 13.50
```

The human's ruling is Staryu. The model prices a second payoff it cannot deploy above the base that
would let it deploy the first. `fetch-base-before-stranded-payoff` (+20) is the rung that carried
this, and its name is the finding.

**The corpus states the rule in the other direction too, which is what pins its shape.** On
`84889011-7` the human takes a **second Riolu while already holding one** — Poké Pad, engine already
complete (Lunatone active, Solrock benched), Riolu in hand, and the menu offering Makuhita, Hariyama,
Solrock, Lunatone and a second Riolu. The ladder took Makuhita (30.00) because
`dont-grab-a-card-already-in-hand` (−12) had pushed Riolu down to 18.00. So the generic duplicate
penalty is **actively fighting the correct pick**: a spare Supporter really is waste, a spare LINE
BASE is not, because this deck runs more than one Mega Lucario ex and each needs its own Riolu.

Together the two frames fix the model precisely: **a line needs one base per un-based PAYOFF copy**,
counted over hand and play — not one per class, and not capped by a duplicate rule written for cards
that saturate at one.

### F2 — `capacity=None` cannot see a full Bench

R3 is right that a grab lands in HAND and costs no board slot — `_keep_slot_dp` says so: *"the
keep/discard family has no capacity: holding a card costs no board slot."* The inference that
capacity is therefore irrelevant is wrong: **a card whose only value is a board slot that does not
exist is worth nothing.**

Measured on `86091435-69` — Bench FULL (Budew, Drakloak, Dragapult ex, Dunsparce, Meowth ex):

```
Dragapult ex   add=26.90   line:121:succ 30.00 dl=0     <- cannot be benched; a copy is ALREADY down
Dudunsparce    add= 0.00                                 <- evolves onto the benched Dunsparce: needs NO slot
```

The human's ruling is Dudunsparce, for exactly that reason. The equation gave an unplayable card an
urgent-succession slot at full tier.

### F3 — `fund_attack` is colour-blind, and it is the last consumer that is

`needs.fund_attack_slots(body_key, cost_remaining)` takes a **scalar count**, values every unit at
`ENERGY_TIER`, and admits any `is_basic_energy` row. Meanwhile `state_model` is fully typed —
`attached_types` is *"the typed supply a cost shape is matched against"*, and `turns_to_afford`
carries `typed=True` because (ADR-0070 §2) *"over-crediting an off-colour Energy prices an unpayable
line as armed."* The typed model exists and is consumed at the attach and evolve seams. `needs` is
the one consumer that throws the type away — and it is internally inconsistent about it, because
`fuel_slot`'s eligibility **is** colour-filtered through `_discard_fuel_types`.

Two frames turn on colour and the equation prices both Energies identically at 8.00:
`85046350-18` (*"save darkness energy for when we have Munkidori available"*) and `85785609-22`
(*"fetched the darkness energy to attach to the Munkidori, then use its ability to move damage"*) —
and they point in **opposite directions**, so no colour-blind number can satisfy both.
`fetch-the-attack-color` (+3) and `fetch-the-ability-fuel-color` (+5) are the retired rungs, and the
second names a need the slot vocabulary has no kind for at all: **ability fuel**.

### F4 — there is no per-(row, slot) factor, so a tutor's REACH is unrepresentable

`_keep_slot_dp`'s weights are per-SLOT (`s.value * (1 - r)`) and eligibility is a plain set of slot
indices. There is nowhere to say *"this row supplies this slot, at a discount."* The `deploy` gate
already strains against this: `_resolve_needs` applies it at slot EMISSION off **one** member —
`deploy = rows[members[0]].get("deploy", 1.0)` — which is a per-row quantity folded into a per-slot
value because the model has no other place to put it.

A tutor supplies the slots its fetch closure reaches, at `δ` per hop. Both chain frames price every
option at 0.00 and fall to menu order: `85059103-9` (*"fetch a Petrel, which can be used to fetch a
fighting gong, which can be used to fetch a solrock"*) and `85058574-71` (*"fetched fighting gong,
then used that to fetch an energy, then discarded that energy to draw 3 cards"*). The number the
human is reasoning with **already exists** — `doctrine_fetch._chain_grab_value` computes exactly
`δ × max` over the reachable set — and the retirement orphans it along with its three consuming
rungs.

### F5 — the band is NOT free: a surviving DECK rung is calibrated against two of the deleted ones

R8 argues the band is *"nearly free"* because *"a ctx-7 menu is homogeneous — every option is a grab,
and the equation never competes against an attack or `End`."* Homogeneous in option TYPE, yes.
Homogeneous in SCORING, no: deck-level Hypotheses fire at `_TO_HAND` and survive the retirement,
because they do not live in `doctrine_fetch`. `src/agents/mega_lucario/strategy.py:155`:

```
fetch-the-missing-engine-half   weight=+22   when: c.select_context == _TO_HAND and c.card_id in _ENGINE_IDS
```

and its own rationale calibrates the number against two rungs this issue deletes:

> *"+22 clears the general line-piece stack `prefer-wincon-line-piece` (+18) +
> `develop-the-cheap-prize-wall-line` (+3, ADR-0048) = 21"*

So the retirement **silently un-calibrates a weight in another file**, and the equation (capped at
`DEPLOY_BAND` 25) lands in the same range as an additive +22 it was never sized against. Three frames
are lost exactly here — `83966336-9`, `83967841-14`, `83661652-31` — each to that rung out-scoring an
Energy the human wanted.

Acceptance criterion 3's ordering-invariance test passes, and is not evidence: it exercises the
equation in isolation, where the menu really is homogeneous. **A band-invariance claim has to be
made against the whole scored menu, not against one term of it.**

### F7 — the search's OWN COST is invisible, and the fact is already in the obs

`83661652-31`, in the human's words: *"we discarded a riolu to fetch a riolu. what a waste!"* Ultra
Ball's `cost: discard_2` had just paid Riolu + Makuhita out of hand; the ladder then scored a fetched
Riolu at 50.00 (`fetch-base-before-stranded-payoff` + `prefer-wincon-line-piece` + `fetch-a-starter`,
all firing precisely because no Riolu is in play — which is true only because this search removed
it), and took it. Two cards spent, one recovered, board unchanged. The human's pick is Mega Lucario
ex, the payoff, which nothing else can supply.

Neither the ladder nor the assignment can see this, and both would price the same. But **the fact
needs no derivation at all** — it is in `obs["logs"]` at decision time, exactly and only:

```json
{"cardId": 677, "fromArea": 2, "toArea": 3, "type": 6, "serial": 25}   // Riolu,    HAND -> DISCARD
{"cardId": 673, "fromArea": 2, "toArea": 3, "type": 6, "serial": 14}   // Makuhita, HAND -> DISCARD
```

`LogType.MOVE_CARD` with `fromArea` HAND and `toArea` DISCARD, and the log is a per-decision delta
rather than a cumulative history, so it contains these two entries and nothing else. Four consumers
already read `obs["logs"]` (`deck_tracker`, `pilot` twice, `scouting/scout`), so the plumbing exists.

This is the **cheapest** finding here: one Context signal — *"this candidate is a card the current
select's own cost just discarded"* — with no new slot kind, no `needs.py` change, and no perturbation
of the discard decider or the refresh shed.

### F6 — 17 derived Board/Context signals lose their last consumer

Retiring the 23 rungs leaves these read by nothing (measured by walking every `when=` clause in
`src/`, then excluding definition sites):

```
card_already_in_hand          card_is_recognized_line_preevo   card_unplayable_this_turn
card_base_unreachable         card_is_starter                  in_play_attack_colors
card_chain_value              card_is_support                  in_play_unfueled_ability_colors
card_evolution_baseless       card_is_top_fetch_priority       support_in_play
card_forward_payoff_prize     card_is_wincon                   wincon_prize_value
card_spends_last_evolution_route                               card_stranded_evolution
```

Each is still computed every decision. An unconsumed board signal is an unbuilt feature, and 17 of
them is the same finding as F1–F5 counted a different way: **these are the facts the rungs were
reading and the assignment does not model.**

## Decision 3 — the ladder is NOT abstaining, and that reframes what is left to fix

The issue's framing is that 23 rungs *"decide the grab by hand"* with *"no equation"*, and the
implied consequence — the one that makes it urgent — is `_deploy_decision`'s recorded failure mode:
*"every option on that select tied and the pick fell to menu position."* **Measured, that is not
happening at ctx 7.**

A first count said it was: 19 of 31 frames share their top score, over a mean 3.42 distinct scores
across 8.9 options — a ladder that looks hopelessly coarse. That count is **vacuous**, and ADR-0091
says exactly why: *options a board cannot tell apart are ONE decision.* Re-counted by DISTINCT CARD
CLASS at the top:

| | ctx-7 frames |
|---|---:|
| ladder produced a sole top option | 12 |
| tied, but every tied option is the SAME card (ADR-0091: one decision, any pick correct) | 17 |
| **tied between DISTINCT cards — the ladder genuinely abstained** | **2** |

Seventeen of the nineteen "ties" are duplicate copies of one Energy or one Basic. The ladder
abstains on **two frames in thirty-one**, not nineteen.

And the two abstentions are already named above:

* `85046350-18` — Basic {P} vs Basic {R} Energy, tied at 38.0. That is **F3**.
* `86091435-69` — Dragapult ex / Dudunsparce / Fezandipiti ex / Munkidori, all at 0.0 on a full
  Bench. That is **F2**.

So the honest target is not thirteen frames and not an equation. The incumbent misses **five**
frames, and they are a short list with short causes:

| frame | wanted | ladder took | cause |
|---|---|---|---|
| `86091435-69` | Dudunsparce | Fezandipiti ex | **F2** — full Bench; all four tie at 0.0 |
| `86091728-47` | Night Stretcher | Ultra Ball | **F4** — the recycle line (Drakloak → evolve → ability) is a chain the ladder prices at 0 |
| `83661652-31` | Mega Lucario ex | Riolu | **F7** — the Ultra Ball's own `discard_2` had just paid the Riolu it then re-fetched |
| `84889011-7` | Riolu | Makuhita | **F1** — `dont-grab-a-card-already-in-hand` (−12) demotes the second line base the line actually needs |
| `86088989-29` | Lillie's Determination | Team Rocket's Petrel | **F4/F5** — `grab-the-chain-opener` (+15) out-scores `grab-a-draw-supporter-in-setup` (+10) |

**Every one is a missing FACT, not a missing marginal.** That is the re-grill's actual agenda, and
it is far smaller than either the issue or the first draft of this ADR implied.

### Two defects in the build's own instrumentation, recorded so the successor does not repeat them

**The kill-switch did not switch everything off.** `grab_value=False` gated `_grab_decision` but NOT
the `_grab_value_of` rewrite (R7), which is reached through `_context` → `card_chain_value` and the
refresh's probable-miss on every decision regardless. So every measurement arm that KEPT the rungs
was scored with the new oracle feeding `grab-the-chain-opener` and `demote-the-costly-chain-opener`,
which is why the patched "incumbent" read 23/30 where the shipped tree reads 25/30 — the two frames
of difference are `86091728-47` and `86088989-29`, both chain-rung frames. This is the shape
`runtime.PROFILE` exists to prevent (the 2026-07-03 dark-planner incident): **a shared-oracle swap
is not covered by the flag on its consumer, and needs its own.**

**R10's ordering leg is structurally inert on every deck we ship.** `fetch-deck-priority` was demoted
to an `_order_key` leg reading `Board.top_fetch_priority_id`, which resolves from
`Strategy.fetch_priority` — measured `[]` for `mega_starmie`, `mega_lucario` and `dragapult_ex`
alike. So the demotion could neither help nor hurt, and no corpus measurement could ever have graded
it. A successor should either populate the list or drop the leg, not ship it unmeasurable.

## Decision 4 — the cost facts, recorded because they are true regardless (AC 8 and 9)

Censused over the ctx-7 corpus at the resolver, n = 1177 candidate resolves:

```
eligibility breadth  0:346  1:339  2:220  3:129  4:86  5:24  6:9  7:24     max=7  mean=1.57
slot count per resolve                                                      max=15 mean=5.7
```

Two things follow, neither of which needed the equation to be true:

* **`_MAX_KEEP_SLOTS = 16` is one slot from biting.** The observed maximum is 15. The truncation the
  issue flagged as a hazard is not hypothetical; it is adjacent.
* **`_keep_slot_dp`'s docstring is false at its own declared bound.** It says *"(≤ `_MAX_KEEP_SLOTS`
  × ≤ ~10 cards ⇒ trivial)"*; the issue measured that configuration at **748 ms**. The claim is true
  only of the SPARSE eligibility real hands produce — mean breadth 1.57 here — and the exposure is
  not confined to any new site: `pilot._needs_v2` already runs one `keep_v2` per hand row at every
  forced discard, and that path DECIDES. The docstring is corrected in the same commit as this ADR.

## Consequences

* **Nothing ships.** No behaviour changed; the incumbent 23-rung ladder stands at **25/30**.
* **The build is in history, not in the tree** (`bd9187d7`), on ADR-0093's discipline and Issue
  #386's precedent: a refuted design is evidence, and deleting it makes the successor re-derive it.
* **`tools/train/grab_sweep.py` is retained**, degraded to score + fired-rung output so it runs
  against `main`. It is the seam-scoped gate ctx 7 has lacked: the Discrimination Gate grades the
  develop-rung leaf and the Decision Gate grades whatever its baseline holds, while ctx 7 is the
  second-largest non-MAIN population in the corpus (31 frames against MAIN's 279).
* **A note on the precedent this issue modelled itself on.** ctx 5 — the `_TO_BENCH` seam whose
  Deploy Marginal the grab was built to mirror — has exactly **one** ruled corpus frame. The mirror
  was drawn from a seam validated on a single ruling, onto a seam with thirty. That asymmetry is the
  best short explanation of why the analogy held in argument and failed in measurement.

### What the successor should actually do — and what it should NOT

**Decision 0 supersedes what follows.** On gradeable evidence the incumbent misses ONE frame, so
four of the five findings below rest on boards the agent should never have reached. They are kept
because each is a real limit of the model, verified at source, and each will matter when a
gradeable frame does exercise it — but **none of them is currently justified by evidence**, and the
successor must not treat them as a work list. The single gradeable defect is `86088989-29` (F4/F5).

What follows is therefore a REGISTER of known model limits, ordered by cost, not a plan:

1. **F7 — the search's own cost.** The cheapest thing on this list: the fact is already in
   `obs["logs"]` as a `MOVE_CARD` HAND → DISCARD delta, four consumers already read that log, and it
   needs no slot kind, no `needs.py` change and no perturbation of the other two consumers. One
   Context signal, one frame.
2. **F2 — bench capacity reaches the grab.** Sole cause of one of the two genuine abstentions, and
   it wants no new slot kind either. A Basic whose only route to the board is a Bench slot that does
   not exist should read through the existing `deploy` gate (`_deploy_odds` already owns exactly this
   class of question), not through `capacity`.
3. **F1 — a line needs one base per un-based PAYOFF copy**, not one per class — and the fix must
   also stand `dont-grab-a-card-already-in-hand` down for line bases, since that rung is what
   demotes the correct pick on `84889011-7`. Note this one is reachable *without* touching
   `line_slots` at all if the duplicate rung is narrowed first; try the narrow move and measure
   before opening the slot model.
4. **F3 — typed `fund_attack` slots plus an `ability_fuel` kind.** The other genuine abstention.
   `state_model` is already fully typed and `fuel_slot` already filters by colour, so this removes an
   inconsistency rather than adding a model — but it is the first item that changes `needs.py`, and
   so the first that perturbs the discard decider and the refresh shed.
5. **F4 — the tutor chain.** Two of the five misses, and the only one needing a genuine model
   extension (a per-(row, slot) factor). Its knowledge already exists in code (`_chain_grab_value`),
   so the cheaper first move is to RANK with it rather than price with it — `_order_key`'s
   ordering-leg shape, which by construction cannot dominate a working score.

Items 1–3 touch no shared model at all. But **the honest next step is none of them.**

Four of the five frames that motivated this register are off-policy, and the correct response to an
off-policy frame is to fix the decision that produced it — the `_PLAY` side, where all 18 surviving
fetch rungs already live. The developer's ruling on both Ultra Ball frames is exactly that: *"should
have just placed Riolu on bench"* — a whether-to-play defect, not a which-card-to-take one. F7's
cost-netting fact is the clearest case: *"we discarded a riolu to fetch a riolu"* is a reason not to
PLAY the Ultra Ball, and pricing it at the grab would be treating the symptom on a board that should
not exist.

So the register's real use is as a **filter on future work**: when a gradeable ctx-7 frame fails,
check it against F1–F7 before inventing anything new.

**Items 4 and 5 change `needs.py`'s model, so each also perturbs the DISCARD decider and the REFRESH
shed through the shared `_resolve_needs`.** Both main-watchdog gates must be re-measured for those,
and `grab_sweep.py` run alongside. Take every item ONE at a time with a measurement between; the
failure recorded here is what happens when five gaps are closed at once by a single new term.

**Do not** re-attempt the retirement as a bundle. The 23 rungs are worth ten frames over an empty
seam and the assignment is worth two; any rung retired must be retired against the specific fact
that replaced it, measured at ctx 7, one at a time — and now, on a GRADEABLE frame.

### The recommendation, given Decision 0

**Close Issue #406 rather than re-spec it.** The seam it targets has one demonstrable defect on
honest evidence, which does not justify a new equation, a model extension, or a rung retirement. The
two rulings that arrived during the re-grill both point at the `_PLAY` side instead, and that is
where the next ctx-7-adjacent work belongs.

The two artifacts that outlive it are the ones worth keeping: `grab_sweep.py`, which now segregates
off-policy frames instead of grading them, and Decision 0's rule — **which should be applied to every
non-MAIN context in the corpus before anything else is graded on one.**
