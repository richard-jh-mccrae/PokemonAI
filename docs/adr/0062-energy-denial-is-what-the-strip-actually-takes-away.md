# ADR-0062: Energy denial is what the strip actually takes away, not whether Energy is present

**Status.** Accepted (grilled 2026-07-14, `/grill-with-docs`) and **BUILT 2026-07-14 (`/tdd`)**, default
ON — it corrects a live gate rather than adding a seam. Suite green.

## Context

**Crushing Hammer** (1120, Item) — *"Flip a coin. If heads, discard an Energy from **1 of your
opponent's Pokémon**."* **Enhanced Hammer** (1081) — *"Discard a Special Energy from **1 of your
opponent's Pokémon**."*

Not "Active Pokémon". **Any** of them. And the engine agrees: `op_trash_energy_enemy`
(`src/cgpy/chain.py`, the trace-verified twin, pinned to `ml_dx_2001 f175` / `ms_mirror_1002 f14`)
builds its `DISCARD_ENERGY` option list from **ACTIVE + BENCH**. `activeOnly` is a different flavour —
the attack-rider one — which Crushing Hammer does not set.

**dragapult_ex and mega_starmie each run 4 copies.** Three defects were live, and they compound:

1. **The gate was narrower than the card.** `play-energy-denial` fired on `opp_active_has_energy`, so
   we stood down whenever their Active was bare — even with a loaded bench. That is the *standard* TCG
   pattern (power up on the bench, promote later), so against a bench-loading opponent four Hammers sat
   dead in hand all game. The gate came from ep82753102 f37, which correctly diagnosed a whiff and then
   cured it by checking the wrong pile.
2. **No whiff model.** It fired whenever Energy was *present*. Strip one Energy from a body carrying
   more than its dearest attack costs and it **still affords the same attack** — nothing is denied.
   Mega Lucario ex (Aura Jab `{F}` 130 / Mega Brave `{F}{F}` 270) on **3** Energy loses **zero** damage
   to a Hammer.
3. **The target select was unscored.** **No rung in the codebase fired on `DISCARD_ENERGY`.** Every
   option scored 0.0, so the argmax fell through to index 0 — which the engine orders **oldest-attached
   first**. A won coin flip routinely stripped a Basic off a benched support mon while their Active sat
   one Energy above its nuke. That is the literal waste.

## Decision

**A Hammer is worth exactly what it stops them doing.** `strategy/denial.py`:

```
best_affordable_damage(energy, attacks) = max damage of the attacks `energy` can pay for  (0 if none)
denial_value(energy, attacks)           = best_affordable(energy) − best_affordable(energy − 1)
```

Worked on Mega Lucario ex:

| their Energy | best now | after the strip | denies |
|---|---|---|---|
| 1 | 130 | 0 | **130** — the attacker goes off |
| 2 | 270 | 130 | **140** — the nuke goes off |
| **3** | 270 | 270 | **0** — SURPLUS, the Hammer is wasted |

`Board.opp_denial_best` is the max over **every** body they have, Active **and** Bench.

**`play-energy-denial` (the flat +20 rung) is RETIRED.** The oracle owns the value, exactly as in
ADR-0060 — price the quantity, don't threshold it:

```
play value = coin_odds(card) * _DENIAL_PLAY_W * opp_denial_best  -  _DENIAL_ITEM_COST
```

and `_denial_target_tactical` ranks the `DISCARD_ENERGY` options by the denial each one achieves.

### Why a flat rung could not work, even with the gate fixed

Fixing only the gate left a live regression: **ms 82749168 f29** — *"wasted crushing hammer because
opponents active has no energy"*. Their Active was indeed bare, but a benched Dragapult ex held 1
Energy (denial 70), so the widened gate opened and the Pilot played the Hammer. The human's *stated
reason* is a card-fact error (the card hits the bench), but the *conclusion* was right.

Two things were missing, and both are forced by the data rather than tuned to taste:

1. **`_DENIAL_ITEM_COST` — the value of KEEPING the card.** A free Item is tiered ahead of everything
   by `_finish_turn_last`, so a purely positive term can never *decline* one: any score above zero
   gets it played. The strip must beat the hold.
2. **`_DENIAL_BENCH = 0.25`, not 0.5.** A benched body must be PROMOTED before the denial bites *and*
   they get a turn in between to simply re-attach. The bound is **derived**: f29 (bench, 70) must hold
   while f15 (Active, 30) must play, which forces bench weight `< 30/70 = 0.43`. Note this also proves
   that **no monotone pricing of magnitude alone can separate them** — f29's raw denial (70) is more
   than twice f15's (30). Imminence, not size, is the discriminator.

Measured on all five Hammer corrections:

| frame | want | denial | play value | result |
|---|---|---|---|---|
| ms f29 | HOLD | 17.5 (bench 70 × 0.25) | **−1.25** | held ✔ |
| ms f15 | PLAY | 30 (Active Riolu) | **+5.00** | played ✔ |
| ms f79 | PLAY | 130 | **+55.00** | played ✔ |
| ms f92 / f102 | PLAY | 140 | **+60.00** | played ✔ |

### What the new gate subsumes

`opp_active_can_damage_us` is gone as a separate premise, because the arithmetic already covers it: a
body that cannot pay any attack has `best_affordable = 0`, so its denial is 0 and we hold. dragapult
**f6** (the Kyogre that cannot attack off an empty discard) is still correctly held — now by the
damage math rather than a flag. ep82753102 **f37** (a bare Kadabra Active) likewise denies 0.

## Consequences

- **Two test boards turned out to be describing wasted Hammers.**
  `test_play_energy_denial_sequences_the_strip_before_a_higher_value_attack` gave the opponent **2**
  Energy on a Pokémon whose only attack costs **1** — the second Energy is surplus, so the strip does
  nothing, and the test asserted we play it anyway. The board was corrected to 1 Energy (the sequencing
  claim it actually tests is unchanged). This is the defect in miniature: the old model could not
  represent "denies nothing", so nobody noticed the board.
- `_DISCARD_ENERGY` (SelectContext 30) and `_ENERGY` (OptionType 6) join the engine vocabulary in
  `strategy/context.py`. **Both had to be added to that module's explicit `__all__`** — `import *` skips
  underscore names, and omitting them fails at *call* time with a `NameError`, not at import. Sharp edge.

## Deferred

> **All three resolved by [ADR-0063](0063-a-booster-scales-the-oracle-and-a-doomed-body-denies-nothing.md)
> (2026-07-14).** Two were real; one was a phantom. See below.

- **Denial against the target's FORWARD form.** ~~Deferred.~~ **BUILT (ADR-0063, `_DENIAL_FORWARD = 0.5`).**
  It was the honest weakness and it was worse than recorded here: this note says the Riolu's own attack
  is "Quick Attack", but Riolu **677** (the one in the line) has **Accelerating Stab** (`{F}`, 30) —
  Quick Attack belongs to a *different printing* (333). The conclusion held anyway. Denial is now
  `max(denial_now, _DENIAL_FORWARD × denial_forward)`, and the discount is **derived** from two frames:
  ms 82225643 f12 must PLAY (`> 0.154`) and dragapult 85046350 f32 must NOT bury the line advance
  (`< 0.8`). At face value the forward credit resurrects that CRITICAL.
- **Enhanced Hammer's Special-Energy filter.** Still deferred, still latent — no deck in the pool runs it.
- **Multi-Hammer sequencing.** ~~The second is over-valued.~~ **PHANTOM — refuted.** `decide()` is greedy
  **per frame** and rebuilds the Board from fresh `obs` every call, so Hammer #2 is already rescored on
  the post-strip board. Proven on ms 82525101 f92: `opp_denial_best` **140.0** → the engine resolves the
  first strip → the next menu reads **130.0**. Both Hammers show the same score in the *same* menu, which
  is harmless — `decide()` returns ONE option. The Planner never double-counts either (`energy_denial` is
  only a `_DISRUPT_TAGS` member there; it never scores denial magnitude). **Nothing to fix.**

## Amendment A (2026-07-29) — f29's ruling was superseded; the bound it derives SURVIVES

Recorded during the Issue #187 review grill (**ADR-0082**). Nothing in this ADR's arithmetic changes;
this note exists so a reader verifying Issue #187's *"Deny 5/5 (ADR-0062) holds"* acceptance criterion
does not trip over a quotation that no longer matches the corpus.

**What changed.** `ms 82749168 f29` was **re-ruled 2026-07-28** during Issue #177's grill (`2d647ba`):
`correct` is now **`[10]` Play Salvatore**, not the *"attach Basic {W} to a Staryu"* pick this ADR was
written against. The re-ruling is not about the Hammer — it found a **2-prize KO** on the board that
both the original tagging and this ADR's analysis missed: Salvatore evolves a benched Staryu into
Mega Starmie ex (its printed text permits a body put into play this turn), Ignition Energy provides
`{C}{C}{C}` on an Evolution, Cinderace retreats for free (retreat 0), and Nebula Beam `●●●`/210 clears
Terapagos ex's 130 remaining HP. Verified at source: `EN_Card_Data.csv` ids 1189, 1031, 17, 176;
`docs/rules.md` §4 (a Mega ex evolving does **not** end your turn) and §6 (`ex` → 2 prizes).

**What survives — re-measured on HEAD, not assumed.**

| this ADR's claim | status |
|---|---|
| f29's Hammer play value `−1.25` | **exact** — option 9 prices `−1.25` on the shipped Pilot today |
| f29 must HOLD the Hammer | **holds** — the Pilot plays Salvatore; the Hammer is not played |
| `_DENIAL_BENCH = 0.25`, derived from `< 30/70 = 0.43` | **holds** — the derivation needs f29 to *not play* the Hammer, and Salvatore-instead-of-Hammer satisfies that exactly as attach-instead-of-Hammer did |
| *"no monotone pricing of magnitude alone can separate them"* (f29 denial 70 > f15 denial 30, yet f29 must hold) | **holds** — untouched by which non-Hammer option wins |

**What is now stale in the text above.** The *"Why a flat rung could not work"* section quotes the
original rationale (*"wasted crushing hammer because opponents active has no energy"*) as the motivating
blunder. That quote is preserved deliberately as the historical record — it is what the decision was
made against — but the corpus no longer contains it. This ADR already noted the stated reason was a
card-fact error whose conclusion was right; the re-ruling adds that the *whole turn* was undersold by
both readings.

**Consequence for the frame's role.** f29 is now **two** anchors at once: the dead-Hammer anchor this
ADR derives its bench weight from, and a missed-KO anchor for the *"a positive-scoring free Item is
tiered ahead of an available Knock Out"* family (`_finish_turn_last`). ADR-0082 declined to charter that
family; it was **split and filed 2026-07-29** once measured, because it turned out to be two problems:

- **The frame half → Issue #165.** Of the five frames Issue #199's gate-1 note listed as live instances,
  **three now HIT** on HEAD (`83053965-28`, `83455356-11`, `85046350-32`) and `86091435-68` is
  refuted-as-labelled — so exactly **one** genuine miss survives, `83664340-24`, whose own rationale
  names the Turn Planner. ⚠️ That frame's *embedded agent trace is stale*: it shows
  `disrupt-when-unfavored +18` on the Hammer, a rung whose `energy_denial` half **this ADR's amendment
  retired**. At HEAD the Hammer prices `+7.88` as a pure tactical — a **bench** strip via
  `_DENIAL_BENCH`, which ADR-0063's `active_can_ko` guard deliberately does not zero. So the frame is a
  **doctrine conflict with a passing test of ours**
  (`test_the_hammer_still_hits_the_BENCH_on_a_turn_i_knock_out_their_active`), not a tuning gap.
- **The structural half → Issue #212.** `_DENIAL_ITEM_COST` prices *keeping* an Item for `energy_denial`
  and nothing else (`_denial_play_tactical` returns 0.0 otherwise), so no other free Item in the pool
  has a finite-resource hold price at all — the defect this ADR named, still unfixed for everything that
  is not a Hammer.
