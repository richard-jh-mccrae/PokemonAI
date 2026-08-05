# ADR-0121 - The `_TO_HAND` grab equation was BUILT to spec and measured SIX FRAMES WORSE — five things the assignment must learn first

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

## Decision 1 — The specified build is six frames worse than the incumbent, and the measurement is controlled

Built exactly as ruled (R1–R10): `needs.keep_v2` over `hand ∪ {one candidate}` as the add-marginal,
`capacity=None`, `include_general=True`, `intrinsic=0.0`, crossing to the damage scale as a
dimensionless ratio through `DEPLOY_BAND`, folded into `_option_trace`'s `tactical`; all 23 rungs
deleted; `fetch-deck-priority` demoted to an `_order_key` ordering leg.

Replayed over the issue's own validation base — the 30 ruled ctx-7 correction frames that name a
`correct` option — with a **fresh Pilot per frame** (an earlier pass mutated the shared
`GENERAL_STRATEGY` singleton and returned 20/30 for all four arms; that number is void):

|   | configuration | agrees with the human |
|---|---|---:|
| A | incumbent — 23 rungs, no equation | **23 / 30** |
| B | both — rungs + equation | 19 / 30 |
| C | **the spec** — rungs deleted, equation on | **17 / 30** |
| D | neither | 15 / 30 |
| E | rungs + equation at band → 0 (ordering-only) | 23 / 30 |
| F | rungs deleted, equation at 4× band | 14 / 30 |

*Positive control:* the four arms are distinguishable, which is what says the levers are live. Row F
is the one that settles it — at four times the band the equation scores **below doing nothing at
all**, so its ranking is not merely incomplete, it is actively wrong on frames the ladder gets right.

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

## Decision 3 — the cost facts, recorded because they are true regardless (AC 8 and 9)

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

* **Nothing ships.** No behaviour changed; the incumbent 23-rung ladder stands at 23/30.
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
* **The successor's bar**: F1–F5 are prerequisites, not follow-ups. Each is a change to `needs.py`'s
  MODEL (a per-copy line need, a capacity reading, typed fund slots plus an ability-fuel kind, a
  per-(row, slot) factor) and each therefore perturbs the DISCARD decider and the REFRESH shed as
  well, since all three share `_resolve_needs`. Both main-watchdog gates must be re-measured for any
  of them. That is a larger job than Issue #406 scopes, and it should be grilled before it is built.
