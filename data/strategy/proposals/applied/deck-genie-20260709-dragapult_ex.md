<!-- Strategy Proposal queue — deck-genie re-author round 2026-07-09 (dragapult_ex).
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md
Source doctrine: src/agents/dragapult_ex/STRATEGY.md (re-authored 2026-07-09 — Cinderace/Judge OUT;
Budew + Dunsparce/Dudunsparce + Rosa's Encouragement IN). Every gap below was CONFIRMED against real
code (workflow wjzvrtwbk) + engine-free probe (scratchpad/probe_ability.py). The preferred_start="second"
flip + the Cinderace/Judge strategy.py dead-ref cleanup were applied directly by deck-genie (user-requested
hygiene; blast radius verified: 19 dragapult + 22 mega_starmie tests pass) — NOT queued here.
NOTE for update-strategy: 3 of the 4 are GENERAL (help every deck), keyed on universal signals, so they
ship silent for decks without the trigger. The dragapult deck opts in only by running the tagged cards. -->

## use-the-draw-engine-ability
- id: use-the-draw-engine-ability
- source: deck-genie
- target_layer: general-hypothesis
- candidate_signal: `option_type == _ABILITY` (10, EXISTS, resolves `card_id`+tags on the option — probe-verified) + the ability card's `draw`/`dig` Function Tag + `not cost_discard`; sibling of `dig-before-commit` (baseline_sequencing.py, keyed on `_PLAY`)
- verification_contract: seed-ladder
- provenance: src/agents/dragapult_ex/STRATEGY.md §6 `use-the-draw-engine-ability` + §8 verify-1 | probe scratchpad/probe_ability.py (Recon+Run Away Draw both score 0, Pilot took the attack) | workflow wjzvrtwbk synthesis "DRAW-ABILITY ACTIVATION GAP"
- status: applied
- for: general

**Spec (authoring spec — thin fodder):**
**The biggest finding — a latent GENERAL bug, not dragapult-specific.** A pure card-advantage Ability
activated at the MAIN menu (`_ABILITY` option, type 10 — Drakloak **Recon Directive** `dig`, Dudunsparce
**Run Away Draw** `draw`) has **no combat value** (`_tactical` = 0 for any non-`_ATTACK` option), and
`dig-before-commit` (+20) only fires on `option_type == _PLAY`, so **nothing endorses the ability**. It
therefore scores 0 → `_finish_turn_last` drops it to **tier 4** (`if score <= 0: return 4`) alongside the
turn-ending attack, and `by_score` (descending) picks any positive-tactical attack **first** → the turn
ends → **the free draw/dig is systematically skipped whenever an attack is on the menu.** It fires only
incidentally on a pure-setup turn (no attack). Probe (`scratchpad/probe_ability.py`, real dragapult
Pilot + GENERAL_STRATEGY): Recon and Run Away Draw both `score=+0.0 fired={}`, and the Pilot chose the
chip attack in both cases; the ability option **does** resolve `card_id` (120 / 66) and its tags (`dig`/
`draw`) are readable — so a tag-keyed rule fires cleanly.

**Author** a general Hypothesis (the `_ABILITY` sibling of `dig-before-commit`, in `baseline_sequencing`):
when `option_type == _ABILITY` and the ability/card carries `draw` or `dig` (and not `cost_discard`),
give it a positive weight (seed ≈ +18) so it sequences to tier 0 (before the attack). **Why it wins:**
"use your free draw engine each turn" is universal; the 2026-07-03 build's whole "keep Recon-digging" +
"Run Away Draw self-recycle engine" plan is currently **undriven**. Every ability-engine deck (Bibarel,
Dudunsparce, Drakloak) inherits it; it is silent for decks with no draw/dig Ability, so verify **inert on
non-triggering decks** (score-diff on mega_starmie/mega_lucario) as part of authoring, then ladder-validate.
**Scope guard:** keep v1 to `draw`/`dig` only. Munkidori **Adrena-Brain** activation shares the same gap
(its MAIN `_ABILITY` also scores 0; infra C only handles the follow-up selects), but a blanket "activate any
ability" risks firing a counter-move with no good target — extending to the counter-move/heal activation is
a **deferred** refinement, noted separately, not this rule.

---

## open-the-item-lock-starter
- id: open-the-item-lock-starter
- source: deck-genie
- target_layer: general-hypothesis
- candidate_signal: `select_context == _SETUP_ACTIVE` + a new `item_lock` Function Tag on the candidate; twin of `open-the-accelerator` (baseline_opening.py, keyed on the `accel_source` Role). DEPENDENCY: add tag `item_lock` to Budew (card id 235) in card_functions.json — currently untagged.
- verification_contract: seed-ladder
- provenance: src/agents/dragapult_ex/STRATEGY.md §6 `open-the-item-lock-starter` + §3 Budew | probe wjzvrtwbk "BUDEW ITEM-LOCK OPENER NOT PREFERRED" (Dreepy/Budew/Dunsparce all score 0, decide()=index 0)
- status: applied
- for: general

**Spec (authoring spec — thin fodder):**
Budew is a deliberate turn-1 free item-lock opener (`Itchy Pollen`: 0-cost attack, 10 dmg, opponent can't
play Items next turn), best going **second** (this sim's first player can't attack T1). But at the pregame
`SETUP_ACTIVE` pick **nothing prefers it**: the only positive SETUP_ACTIVE selector, `open-the-accelerator`
(+40), keys on the `accel_source` Role — Budew has none, and Cinderace (the old accel opener) was removed,
so that rule is now dead in this deck. Probe: offering Dreepy/Budew/Dunsparce, all three 1-prize Basics
score **0**, `fired={}`, and `decide()` returns option index 0 (arbitrary) → Budew is opened only when it
happens to sit at index 0, and the turn-1 item-lock is frequently wasted.

**Two-part author:** (1) **card-functions:** add an `item_lock` behavioral tag to Budew (id 235) — an attack
that blocks the opponent's Items next turn (a new tag in the disruption family the `baseline_disruption`
cluster header already anticipates: "grows as ... ability lock ... land"). (2) **general Hypothesis**
(`baseline_opening`, twin of `open-the-accelerator`): at `SETUP_ACTIVE`, prefer a candidate carrying
`item_lock` (seed ≈ +35, just below the accel opener). **Why it wins:** "lead with your free item-lock
disruptor" is universal; a deck opts in by running an `item_lock` card and the rule is silent otherwise
(verify inert on non-`item_lock` decks). KO-safe (a pregame pick). No first/second gate needed — opening
Budew going first is still fine, the lock just waits to T2. **Deck declaration (dragapult):** Budew gets
Role `starter` (documentation; the rule is tag-keyed). This complements `preferred_start="second"`
(applied directly) — together they land Budew Active on the turn Itchy Pollen can fire.

---

## tag-rosas-encouragement-energy-accel
- id: tag-rosas-encouragement-energy-accel
- source: deck-genie
- target_layer: general-hypothesis
- candidate_signal: Function Tag `energy_accel` on Rosa's Encouragement (card id 1240 — currently ABSENT from card_functions.json); once tagged, the EXISTING `use-acceleration` (+25, baseline_energy.py) fires. No new when().
- verification_contract: score-diff
- provenance: src/agents/dragapult_ex/STRATEGY.md §6 `energy_accel` tag on Rosa's + §3 Rosa's | probe wjzvrtwbk "ROSA'S UNTAGGED -> use-acceleration dead"
- status: applied
- for: general

**Spec (authoring spec — thin fodder):**
Rosa's Encouragement (Supporter, id 1240) is comeback energy acceleration — only when you have MORE prizes
remaining than the opponent (behind), attach up to 2 Basic Energy from **discard** to a **Stage 2**
(= Dragapult ex). It is the deck's only fast re-arm of a KO'd Dragapult. But id 1240 is **absent from
card_functions.json** → `CardFunctions.tags(1240) == []` → `use-acceleration` (`"energy_accel" in c.tags`)
**cannot fire**. The accel value is invisible to the general layer.

**Author:** add `energy_accel` to id 1240 (via the card-functions source / `tools/build_card_functions.py`).
That alone closes the gap — no new Hypothesis. Once tagged, `use-acceleration` (+25) endorses playing Rosa's,
and it is **safe by construction**: the engine only OFFERS Rosa's as a legal PLAY when you are behind on
prizes (card text), and the Stage-2-only target is resolved in the engine's follow-up attach — so
`use-acceleration`'s ungated `when()` never misfires. **Do NOT** give Rosa's the `accel_source` **Role** —
`advance-the-accel-pieces` is `not line_ready` (setup) gated and Rosa's is a behind-on-prizes comeback that
targets an already-online Stage 2, so a Role would mis-boost it at setup; the tag alone is correct (verify
`advance-the-accel-pieces` stays silent). Verify score-neutral for decks not running Rosa's.

---

## dont-strand-the-evolving-engine
- id: dont-strand-the-evolving-engine
- source: deck-genie
- target_layer: general-hypothesis
- candidate_signal: `card_is_support` (EXISTS, doctrine_fetch.py) + the option card's `evolvesFrom` base NOT in play+hand; generalize the `card_is_line_preevo`-gated `fetch-base-before-stranded-payoff` / `dont-grab-a-baseless-mid-evolution` beyond the win-condition Line to non-Line engine evolutions.
- verification_contract: score-diff
- provenance: src/agents/dragapult_ex/STRATEGY.md §6 `dont-strand-the-evolving-engine` + §3 Dunsparce/Dudunsparce | workflow wjzvrtwbk "DUNSPARCE->DUDUNSPARCE FETCH PRIORITY INVERSION"
- status: applied
- for: general

**Spec (authoring spec — thin fodder):**
A confirmed **fetch priority inversion** for the Dunsparce → Dudunsparce draw engine. Dudunsparce (id 66,
Stage 1, tags `draw`/`stall`, hp 140) satisfies `card_is_support` so `fetch-the-support` (+15) grabs it —
but it is **unplayable from hand** (evolvesFrom Dunsparce), and its base Dunsparce (id 305, no tags, not a
win-condition-Line pre-evo) scores only `fetch-a-starter`/`bench-fill-a-basic` (+12). Neither guard fires:
`_stranded_evolution_set` is inert (the base Dunsparce IS in the deck, so the chain grounds out), and
`dont-grab-a-baseless-mid-evolution` is `card_is_line_preevo`-gated (the line-preevo set is only the
Dragapult path, excluding Dudunsparce). Net: at an Ultra Ball the doctrine **actively prefers tutoring the
dead Stage-1 Dudunsparce (+15) over the base Dunsparce (+12) that would enable it.**

**Author** (general, `doctrine_fetch`): (1) a penalty rung `dont-strand-the-evolving-engine` — at a
`_TO_HAND` search, penalise grabbing a Stage-1 `card_is_support` whose `evolvesFrom` base is absent from
play+hand (a stranded dead card); and/or (2) the cleaner fix — extend the base-before-payoff /
anti-baseless-grab guards to recognise **non-win-condition engine evolution lines** (a `card_is_support`
variant of `card_is_line_preevo`), so the base Dunsparce is preferred as the engine precursor. **Why it
wins:** any evolving-draw-engine deck (Bibarel/Bidoof, Dudunsparce) inherits it; it should be score-neutral
for decks whose only evolutions are win-condition Line pieces (already covered). Priority: medium — a 1-of
engine, but the inversion actively mis-fetches. Verify inert on line-only decks (mega_starmie/mega_lucario).
