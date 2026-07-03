# mega_lucario — Playing Doctrine

> Phase-A deliverable of `/deck-genie`. The human-readable strategy the deck plays; the executable
> `strategy.py` is generated from this **after sign-off** (ADR-0017). Build on the
> [General Strategy](../../../docs/general-strategy.md): reuse, override, or extend — don't restate.

**Status:** Phase A **signed off** · Phase B build **in progress** (gated, tranched) · **Last grilled:** 2026-06-29 · **Re-baselined:** 2026-07-02 (§5b/§9) · **Author:** deck-genie + Richard

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped
- [x] Phase 1 overview confirmed (2026-06-29 — flexible multi-attacker / Aura-Jab-is-the-engine / go-first)
- [x] Phase 2 research synthesised + confirmed (2026-06-29; fan-out 125 claims → 44 supported / 50 refuted)
- [x] Phase 3 card-by-card: 20/20 cards locked (§3); combos/sequencing/opening/plan in §4
- [x] Phase 4 General-Strategy disposition + hypothesis drafts complete (§5/§6/§7)
- [x] Phase 5 **signed off** (2026-06-29) → Phase B authorised (verify-vs-general + decide placement + build all + infra)
- [x] 2026-07-02 **re-baseline** vs merged `src/common` (ADR-0028/0030/0031/0032/0033/0034/0035 landed): §5b + revised §9
- [x] Phase 6 Phase B build **COMPLETE** (2026-07-02, gated): T2'–T7' built — see §9 statuses. Gates:
  trigger tests 18/18 (`tests/agents/test_mega_lucario_triggers.py`), full suite green, `check_agent`
  playable + deployable. `aligned.json` ledger written.
- [x] 2026-07-03 **T8': the five deferred items BUILT** (damage-boost OHKO model, attack-condition
  oracle + cosmic-rule retire, recoil-doom survival charge, stadium tech reads, Lunar-Cycle pair) —
  see §9 T8'. Trigger tests 33/33; residual deferrals shrunk to the §9 "Still deferred" line.

Cards still to grill: none (20/20 locked). Open questions: see §8 (infra/deferred only).

## 0 · Card facts (engine dump — substrate, do not hand-edit)

Source: `python .claude/skills/deck-genie/scripts/dump_deck.py mega_lucario`. Engine is ground truth.
deck.txt → deck.csv via `tools/deck_convert.py to-csv`.

### Pokémon (16)
- **3× Riolu** — Basic Fighting · 80 HP · 1 prize · weak **Psychic** · retreat 2 · **(untagged)**
  - *F — Accelerating Stab (30):* during your next turn, this Pokémon can't use Accelerating Stab.
- **3× Mega Lucario ex** — **Mega ex** Fighting · **340 HP** · **3 prize** · weak **Psychic** · retreat 2 · evolves from **Riolu** · **(untagged)**
  - *F — Aura Jab (130):* attach up to 3 Basic {F} Energy from your **discard pile** to your **Benched** Pokémon any way.
  - *FF — Mega Brave (270):* during your next turn, this Pokémon can't use Mega Brave.
- **3× Solrock** — Basic Fighting · 110 HP · 1 prize · weak **Grass** · retreat 1 · **(untagged)**
  - *F — Cosmic Beam (70):* does **nothing** if you don't have Lunatone on your Bench; damage **not** affected by Weakness/Resistance.
- **2× Makuhita** — Basic Fighting · 80 HP · 1 prize · weak **Psychic** · retreat 2 · **(untagged)**
  - *F — Corkscrew Punch (10).* · *FF — Confront (30).*
- **2× Hariyama** — Stage 1 Fighting · 150 HP · 1 prize · weak **Psychic** · retreat 3 · evolves from **Makuhita** · **(untagged)**
  - *Ability — Heave-Ho Catcher:* once/turn, when you play this from hand to **evolve**, you may switch in 1 of the opponent's Benched Pokémon to the Active Spot. (gust-on-evolve)
  - *FFF — Wild Press (210):* this Pokémon also does 70 damage to itself.
- **2× Lunatone** — Basic Fighting · 110 HP · 1 prize · weak **Grass** · retreat 1 · **(untagged)**
  - *Ability — Lunar Cycle:* once/turn, if you have **Solrock** in play, you may discard a Basic {F} Energy from hand → **draw 3**. Max 1 Lunar Cycle per turn.
  - *FF — Power Gem (50).*
- **1× Meowth ex** — Basic **Colorless** · 170 HP · 2 prize · ex · tags `search`, `stall`
  - *Ability — Last-Ditch Catch:* once/turn, when you play this from hand onto your **Bench**, search your deck for a **Supporter** to hand; shuffle. (Max 1 "Last-Ditch" Ability/turn.)
  - *CCC — Tuck Tail (60):* put this Pokémon and all attached cards into your hand.

### Supporter (9)
- **4× Lillie's Determination** — `draw`: shuffle hand into deck, draw **6** (**8** if exactly 6 prizes remaining).
- **3× Judge** — `draw`,`hand_disruption`: each player shuffles hand into deck and draws **4**.
- **2× Boss's Orders** — `gust`: switch in 1 of opponent's Benched Pokémon to the Active Spot.

### Item (18)
- **4× Ultra Ball** — `search`: discard **2** cards, then search deck for **any Pokémon** to hand.
- **4× Fighting Gong** — `search`: search a **Basic {F} Energy OR a Basic {F} Pokémon** to hand.
- **4× Poké Pad** — `search`: search a Pokémon **without a Rule Box** (no ex) to hand.
- **4× Premium Power Pro** — **(untagged)**: this turn, your {F} Pokémon attacks do **+30** to opp Active (before W/R).
- **2× Switch** — `switch`: switch your Active with a Benched Pokémon.

### Tool (2)
- **1× Maximum Belt** — **[ACE SPEC]** — holder's attacks do **+50** to opp Active **{ex}** (before W/R).
- **1× Air Balloon** — retreat cost of holder is **{C}{C} less**.

### Stadium (3)
- **2× Team Rocket's Watchtower** — **{C}** Pokémon in play (both players) have **no Abilities**.
- **1× Gravity Mountain** — each **Stage 2** Pokémon in play (both players) gets **−30 HP**.

### Energy (12)
- **12× Basic {F} (Fighting) Energy.**

## 1 · Overview (CONFIRMED — 2026-06-29)

**Confirmed gameplan decisions (user, 2026-06-29):**
- **Flexible / matchup-dependent win condition.** Mega Lucario ex is primary, but **Solrock (70)
  and Hariyama (210) carry real offensive load** depending on matchup (Solrock spam vs a wall;
  Hariyama gust-beatdown; Lucario nuke). The doctrine must support **multiple live attack lines**,
  not a single-wincon sprint (this is the structural contrast with mega_starmie).
- **Aura Jab IS the energy engine.** Deliberately attack with Aura Jab to bank Fighting from the
  discard onto the Bench; the off-turn load is the **core acceleration** that keeps several
  attackers powered — not incidental filler.
- **Go first.** Setup-heavy evolution deck — take the first turn to develop Riolu / Solrock /
  Lunatone and accept no T1 attack. (Opposite of mega_starmie's go-second.)

**Phase-2 rulings (user, 2026-06-29):**
- **Dual-Mega when able.** Sustained Mega Brave from **two powered Mega Lucario ex** (lock is
  per-Pokémon, not positional) is the strategically superior high-end plan. **Aura Jab (130 + load 3
  F to the Bench) is the BRIDGE** that builds the second Mega, and the fallback when only one is
  online. So the deck actively **pre-positions + powers a second Mega** rather than camping one.
- **Vs Psychic: keep evolving, play around it.** Do NOT author a suppress-the-evolve rule. Still
  evolve the Mega but protect it (positioning, don't over-expose the 3-prizer); Solrock single-prize
  is a **fallback**, not a default pivot. Avoids a Read/Posture dependency.


- **Win condition (draft):** race 6 prizes behind **Mega Lucario ex** (Stage 1 off Riolu, 340 HP,
  3-prize nuke) — alternate **Mega Brave (FF · 270)** big hits with **Aura Jab (F · 130 + load 3 F
  from discard onto the Bench)** on the off-turns (Mega Brave is once-every-other-turn). The
  Solrock/Lunatone pair is a self-contained **draw engine + cheap 70 attacker** that also feeds the
  discard pile Aura Jab refuels from; Hariyama is a **secondary attacker + gust-on-evolve**.
- **Line(s) (draft):** `Riolu → Mega Lucario ex` (payoff). **Online at 1 F** per the engine
  (cheapest attack = Aura Jab); the *big* turn (Mega Brave) wants 2 F. Secondary line:
  `Makuhita → Hariyama`. Solrock, Lunatone, Meowth ex are Basics (no evolution).
- **Main attacker:** Mega Lucario ex. **Secondary attackers:** Solrock (1 F · 70, needs Lunatone
  benched), Hariyama (FFF · 210, self-70).
- **Support Pokémon:** Lunatone (draw engine — discard F → draw 3, needs Solrock), Solrock (enables
  Lunatone + cheap attacker), Meowth ex (one-shot Supporter tutor on bench-drop).
- **Engine (draw/search):** draw = Lillie's Determination, Judge, **Lunatone ability**; search =
  Ultra Ball (any mon), Fighting Gong (F energy/basic), Poké Pad (non-ex mon), Meowth ex (Supporter).
- **Acceleration:** **Aura Jab** is the deck's energy engine — recurs F energy from discard onto the
  Bench (so attacking *is* the acceleration). Plus 12 basic F + Fighting Gong to find them.
- **Disruption:** Judge (hand-strip), Boss's Orders (gust), Hariyama Heave-Ho (gust-on-evolve),
  Gravity Mountain (−30 to opp Stage 2), Team Rocket's Watchtower (turns off {C} abilities).
- **Damage boost:** Premium Power Pro (+30 to {F} attacks this turn), Maximum Belt (ACE SPEC, +50 vs ex).
- **Energy:** 12× basic Fighting — the *only* energy; reusable, and the discard pile is a second
  reservoir thanks to Aura Jab. No special energy.
- **User context:** _(none supplied yet — fold in on confirm)_

### Notable interactions — VERIFIED at the engine/rulebook (2026-06-29)
- **Gravity Mountain is one-sided tech — it never touches our board.** Engine flags: Mega Lucario ex
  (id 678) `stage1=True, stage2=False, megaEx=True`; Hariyama (id 674) `stage1=True, stage2=False`.
  Gravity Mountain reduces only **Stage 2** Pokémon, so **none of our Pokémon lose HP** (everything
  is Basic or single-hop Stage 1). Confirms the rulebook delta (`rulebook.txt:335`): "Mega Evolution
  Pokémon ex can appear as Basic, Stage 1, or Stage 2… Mega Lucario ex evolves directly from Riolu."
  It evolves from a Basic ⇒ it's a Stage 1. **Use:** drop Gravity Mountain freely vs Stage-2 decks to
  shave 30 HP off their attackers (crosses our damage breakpoints) at zero cost to us.
- **Mega ex does NOT end your turn on evolving** (rulebook delta, CLAUDE.md) → evolve Riolu→Mega
  Lucario ex and attack the **same turn**. This is the engine of the whole deck's tempo.
- **Team Rocket's Watchtower suppresses {C} abilities including our own Meowth ex** (id 1071,
  `energyType=0` = Colorless). Last-Ditch Catch triggers *on entering play*; if Watchtower is already
  down, Meowth's ability is OFF → no Supporter fetch. **Sequencing rule:** use Meowth's ability
  BEFORE laying your own Watchtower; Watchtower is primarily an opponent-facing ability-lock.
- **Premium Power Pro** (+30 to {F} attacks this turn, Item, unlimited/turn): the damage-boost
  engine. Strong prior that identical "+30" effects **stack** (TCG norm) → multiple = +60/+90/+120.
  Exact stacking is a simulation detail → defer the breakpoint number to the General Strategy's
  (deferred) **damage-boost OHKO-line model**; doctrine intent is "stack Power Pro to cross a KO line."
- **Maximum Belt** (ACE SPEC, +50 to opp **{ex}** Active only): conditional on the *target* being an
  ex/Mega. Whether the engine counts a `megaEx` target as "{ex}" for the bonus is unconfirmed — note
  for Phase 3. Like Power Pro, its breakpoint use sits in the deferred damage-boost model.

## 2 · Research synthesis (cited — confidence: MEDIUM)

Fan-out research (4 search angles → adversarial verify each claim vs the engine card facts → cited
synthesis): **125 raw claims → 44 supported, 50 refuted, 30 card-neutral.** **Card mechanics are
HIGH-confidence** (multi-source + ground-truth-verified). **Strategic prose is thinner** and leans on
two sources ([Pokemon.com][p], [Dark Fox][df]); much of the web corpus describes the **mainline SV
Lucario deck, not this MEG-set engine deck** — every line below was filtered against our actual 60.
Matchup win-rates are unverified meta opinion (soft priors only).

### Core gameplan (verified)
A **consistency-focused, prize-trading Fighting attacker around a high-HP finisher.** The arc: chip
early with cheap Basics (Riolu 30 / Solrock 70), power up a finisher via **Aura Jab**, then close
prizes ([Pokemon.com][p]). Establishing early is realistic — the line is a **single hop** Riolu →
Mega Lucario ex, and **Mega ex don't end your turn on evolving** (evolve-and-attack same turn)
([UltimaSupply][us]). The **single-prize core (Solrock / Lunatone / Hariyama) offsets the 3-prize
liability** of Mega Lucario ex — a sound prize-trade frame (card-neutral prior, not a mechanic).

### The finisher — Mega Lucario ex
- **340 HP, Fighting, Stage 1 Mega ex from Riolu.** Very hard to OHKO **except through Psychic
  weakness (×2)** → ~170 is the OHKO threshold; **Psychic is the realistic one-shot route** ([p]).
- **Aura Jab** (F · 130): the deck's **SOLE energy-acceleration engine** — attach up to 3 Basic F
  from **discard** to the **Bench** ("up to 3" is a ceiling). Nothing else moves energy into play ([p]).
- **Mega Brave** (FF · 270): "almost enough" to OHKO the format; modifiers exist to close the gap
  (e.g. 270 + Maximum Belt 50 = 320). **The restriction is bound to THAT specific Mega Lucario ex**,
  not the Active Spot ([p]).

### Key combos (verified)
- **Aura Jab → bench power-up:** 130 *and* pre-load benched attackers from discard, staging a Mega
  Brave (FF) or Hariyama Wild Press (FFF) ([us], [Beckett][b]).
- **Lunatone ↔ Solrock (mutually dependent):** Lunar Cycle needs Solrock *in play* (discard 1 F →
  draw 3); Cosmic Beam (70, ignores W/R) needs Lunatone *on the Bench* — symbiotic ([p], [b]).
- **Discard-as-fuel loop:** Lunar Cycle discards exactly what Aura Jab re-attaches (Basic F) — the
  draw cost stocks the discard for later acceleration ([b]).
- **Hariyama gust-on-evolve:** Heave-Ho Catcher gusts on the Makuhita→Hariyama evolve — **doesn't
  spend a Boss's Orders, repeatable across both copies** (Makuhita must already be benched). Drag a
  bench-sitter Active → KO it the same turn (no evolve ends the turn) ([p], [df]).
- **Two-KO turn:** Aura Jab KOs one body (while accelerating) + a *separately evolved* Hariyama
  gusts-and-KOs another. **Constraint:** Aura Jab and Mega Brave are the same Pokémon's attacks —
  one attack/turn, they never chain on one Lucario ([p]).

### Sequencing & opening (verified + priors)
- **Set up Solrock + Lunatone first**, then Lunar Cycle to dig ([b]). Solrock *in play* to draw;
  Lunatone *on the Bench* for Cosmic Beam damage ([jwa], [df]).
- **Evolution discipline:** don't commit both Riolu→Mega unless they won't be immediately OHKO'd; in
  grindy/Psychic matchups **keep a Riolu unevolved** — each Mega is 3 prizes if KO'd ([df]).
- **Opening (prior):** lead 2 Riolu, evolve one, hold the other as Riolu — denies an easy 6-prize
  two-Mega board ([df]). **Matchup-dependent lead:** Solrock vs single-prize decks; the Mega line vs
  multi-prize/ex decks where prize math is forgiving ([p], card-neutral).

### Matchups (priors — unverified meta)
- **Vs Dragapult ex (320 HP):** Mega Brave 270 **+ Maximum Belt +50 = 320 = exact OHKO**; Dragon
  type, no Fighting weakness, lands clean ([p]).
- **Vs Gardevoir ex (very unfavorable, ~5/95):** whole line is Psychic-weak → cheap OHKO on the
  3-prizer. Plan: **don't evolve into Mega Lucario ex; pivot to Solrock** (Grass-weak, Cosmic Beam
  ignores W/R). Solrock has **no native snipe** → drag bench threats Active via Boss's/Heave-Ho. As a
  risky out: Mega Brave + Belt 50 + Power Pro 30 = 350 KOs a Gardevoir ex ([df]).
- **Vs Fighting-weak fields (favored):** weakness ×2 + Power Pro/Belt stack — even Riolu's 30 scales
  to 140 vs a weak ex with both modifiers ([df]).
- **Other priors (directional only, opponent cards outside our data):** ~95/5 Joltik Box, ~50/50
  Dragapult/Dusknoir (going second matters there — note vs our go-first default), ~80/20 Gholdengo.

### Tech choices (verified vs our 60)
- **Fighting Gong ×4:** fetches a Basic F energy **or** a Basic F Pokémon — every engine Basic
  (Riolu, Solrock, Lunatone, Makuhita) but **NOT** Hariyama or Mega Lucario ex ([jwa], [b]).
- **Premium Power Pro ×4:** +30 to F attacks this turn — clears OHKO thresholds (270→300, 210→240);
  mono-Fighting so every attacker benefits. **Not tutorable — draw-only** ([p]).
- **Maximum Belt (ACE SPEC ×1):** +50 vs an opposing **Active ex** only. **Pure offense — no
  survivability, no weakness/resistance interaction**; the Dragapult-OHKO enabler ([df], [p]).
- **Judge:** hand disruption (both draw 4) — pairs with Heave-Ho to set the opponent behind ([p]).
- **Gravity Mountain:** −30 to each Stage 2 — **we run zero Stage 2, so it's pure anti-opponent tech**
  (verified against engine stage flags; see §1) ([p]).

### Web misreads — do NOT adopt (refuted vs card facts)
1. **"Reset Mega Brave by retreating + re-promoting."** False — the lock is on that specific Mega
   Lucario ex, not the Active Spot. **Only a *different* Mega Lucario ex has Mega Brave open** — the
   real argument for running **3 copies** (alternate big hits across two powered Megas) ([p]).
2. **"Aura Jab strips opponent energy."** False — it only moves *your* discard energy to *your*
   bench. The deck has **no energy denial** ([df]).
3. **"Baby Lucario / intermediate Lucario as a single-prize attacker."** No such card — single hop
   Riolu → Mega Lucario ex ([df], [p]).
4. **"Rocky/Stone Fighting Energy for damage reduction / retreat-lock immunity."** We run **12 basic
   Fighting, no special energy** — the card and all its effects don't exist here ([us], [p]).
5. **"Maximum Belt is defensive / pierces resistance / helps survive OHKOs."** Single flat +50 vs an
   opposing ex — zero defensive value ([us], [df]).
6. **"Open with Mega Lucario ex."** Impossible — it's a Stage 1; every game opens with a Basic ([p]).
7. **Other fictions:** Professor Turo's Scenario reset loop, Cornerstone Mask Ogerpon ex tech, Secret
   Box ACE SPEC, Night Stretcher, decklists with wrong counts (9–10 energy, "2 Judge", "2 Air
   Balloon") — all mainline carry-over, none in our 60 ([df], [limitless], [p]).

**Sources:** [Pokemon.com — Building a Mega Lucario ex Deck][p] · [Dark Fox TCG — Deck & Matchup
Guide][df] · [UltimaSupply — Post-Rotation Guide][us] · [Beckett — New Meta April 2026][b] · [Joseph
Writer Anderson — Deck List & Guide][jwa] · [Limitless — Deck Overview][limitless]

[p]: https://www.pokemon.com/us/strategy/pokemon-tcg-deck-list-and-strategy-building-a-mega-lucario-ex-deck
[df]: https://www.darkfoxtcg.com/blogs/news/mega-lucario-deck-matchup-guide
[us]: https://ultimasupply.com/blogs/news/mega-lucario-ex-deck-guide-post-rotation-strategy-and-list
[b]: https://www.beckett.com/news/a-look-at-the-new-pokemon-tcg-meta-april-2026/
[jwa]: https://www.josephwriteranderson.com/blog/mega-lucario-ex-deck-list-and-guide
[limitless]: https://limitlesstcg.com/decks/345

### Strategic implications I'm carrying into Phase 3 (for your confirm)
- **Run-3-Mega rhythm:** the per-Pokémon Mega Brave lock means with two powered Megas you Mega Brave
  *every* turn (A then B). The "alternate Mega Brave / Aura Jab on one Lucario" cadence is only forced
  when you have a single Lucario online. → big input to the attack-selection doctrine.
- **Psychic-weakness pivot:** vs Psychic, **suppress the Mega Lucario evolve** and run the Solrock
  single-prize plan. This is a real "don't-evolve-the-wincon" carve-out — unusual, worth a rule.
- **Solrock needs a gust to snipe** — pairs Boss's/Heave-Ho with the Solrock plan.
- **Maximum Belt is the ex-OHKO breakpoint tool** (270→320 kills Dragapult ex) — deferred to the
  damage-boost model, but the doctrine should name the breakpoint.

## 3 · Card-by-card

Breakpoint table (real-rules arithmetic; the agent's *evaluation* of boosts defers to the General
Strategy damage-boost model):

| Attack | Cost | Base | +1 PPP | +Belt(vs ex) | +Belt+1PPP |
|---|---|---|---|---|---|
| Mega Brave | FF | 270 | 300 | **320** | 350 |
| Aura Jab | F | 130 | 160 | 180 | 210 |
| Wild Press (Hariyama) | FFF | 210 (self-70) | 240 | 260 | 290 |
| Cosmic Beam (Solrock) | F | 70 *(ignores W/R)* | 100 | 150 | 180 |
| Accelerating Stab (Riolu) | F | 30 | 60 | 80 | 110 |

Named lines: **270** OHKOs ≤270 HP · **320 = Dragapult ex OHKO** (Mega Brave + Belt) · Solrock 70
**ignores Weakness/Resistance** (un-reducible chip/finisher) · Fighting-weak targets double everything.

### 3× Riolu — `win_condition` line base + minor early chip (LOCKED 2026-06-29)
- **Mechanics:** Basic Fighting · 80 HP · 1 prize · weak **Psychic** · retreat 2. Untagged.
  Accelerating Stab (F · 30): can't reuse next turn (not spammable).
- **Use:** the Mega Lucario ex base. **Going first, bench ~2 Riolu**, evolve one, **hold the other as
  a Riolu** (evolution discipline — don't hand over two 3-prize Megas / over-commit). Accelerating
  Stab 30 is a minor chip if Active early with nothing better (scales hugely on a Fighting-weak ex:
  30→140 with weakness + both modifiers).
- **Hand:** keep a Riolu in play before you want the Mega; Fighting Gong / Poké Pad / Ultra Ball fetch it.
- **Anti-patterns:** evolving both Riolu when one Mega is enough / can't be powered (exposes 6 prizes);
  relying on Accelerating Stab as offense.
- **Disposition:** general `evolve-into-wincon` governs the evolve; line piece via `prefer-wincon-line-piece`.

### 3× Mega Lucario ex — `win_condition`, `primary_attacker` (LOCKED 2026-06-29)
- **Mechanics:** Mega ex (engine Stage 1, megaEx) · 340 HP · **3 prize** · Fighting · weak **Psychic
  (×2 → ~170 OHKO threshold)** · retreat 2 · evolves from Riolu (single hop). Untagged in
  `card_functions.json` (→ needs `energy_accel` on Aura Jab; see §8).
  - *Aura Jab (F · 130):* attach up to 3 Basic F from **discard** → **Bench**, any way.
  - *Mega Brave (FF · 270):* this **specific** Pokémon can't Mega Brave next turn.
  - **Mega ex doesn't end your turn on evolving** → evolve-and-attack same turn.
- **Win condition:** flexible multi-attacker, but Mega Lucario ex is the primary. **Goal = two
  powered Megas → a Mega Brave EVERY turn** (the cooldown is per-Pokémon, not positional).
- **Attack selection (KO-first, always — a lethal beats every positional rule):**
  - Among KOs, take the **cheaper KO that also develops**: if **Aura Jab (130 +load) already KOs**,
    prefer it over Mega Brave — banks 3 F to the Bench *and* keeps Mega Brave off cooldown.
  - **Non-KO turns → two-turn lookahead.** If **Aura Jab now (130) + Mega Brave next turn (270) = 400**
    KOs the opponent's key attacker, lead **Aura Jab** (chip + load the bench).
  - **Aura Jab is discard-aware:** its accel only happens if **Basic F sits in the discard**. With an
    empty discard, Aura Jab is a bare 130 → Mega Brave (or a different line) may be better. *(New
    signal: count of Basic F in discard — §8.)*
  - **Mega Brave** when 270 (or 270 + Belt 50 = 320 / + PPP) crosses a KO line 130 can't reach.
- **Aura Jab energy-targeting (the load):** **2nd Mega Lucario ex first** (a benched Riolu/Mega → FF),
  **then Hariyama** (→ FFF Wild Press), then spread. Directly serves the dual-Mega plan. *(New: an
  attach-target priority at Aura Jab's resolve select — §8.)*
- **Sustained dual-Mega cadence (retreat-swap):** Mega Brave with A → next turn (A on cooldown)
  **retreat/Switch/Air-Balloon A → promote powered B → Mega Brave B.** Both Megas are retreat 2, so
  use **Switch / Air Balloon** to swap without dumping energy (or pay the 2 F — it lands in the discard
  where **Aura Jab recovers it**). Needs a "B is powered (2 F, or 1 F + 1 in hand)" read + an
  "A's attack on cooldown" read. *(New signals — §8; partial overlap with general
  `retreat-to-ready-attacker`, but both bodies are the wincon here.)*
- **Evolution discipline:** evolve-and-attack the same turn; build a 2nd Mega **only when powerable**.
  Don't expose a second 3-prizer you can't use — **but never shuffle a usable Mega Lucario ex out of
  hand** via Lillie's/Judge if it can be powered next turn (hold it; see Lillie's/Judge entries).
- **Vs Psychic (×2):** keep evolving, **play around it** — protect/don't over-expose the 3-prizer;
  Solrock single-prize is the fallback (no suppress-evolve rule, per Phase-2 ruling).
- **Anti-patterns:** burning Mega Brave's cooldown for an Aura-Jab-able KO; Aura Jab with an empty
  discard expecting a load; benching a 2nd Mega you can't power into a loose 3-prize gift; retreating
  a Mega by paying 2 F when Switch/Air Balloon was available (only "waste" if Aura Jab can't recover).
- **Disposition:** `evolve-into-wincon` + Tactical KO/weakness math cover the core; the attack-
  selection (discard-aware Aura-Jab-vs-Mega-Brave, two-turn lookahead), the Aura-Jab load-targeting,
  and the retreat-swap cadence are **deck-specific** new rules / Tactical refinements → §6 + §8.

### 3× Solrock — `secondary_attacker` (early), engine enabler (LOCKED 2026-06-29)
- **Mechanics:** Basic Fighting · 110 HP · 1 prize · weak **Grass** (NOT Psychic) · retreat 1.
  Cosmic Beam (F · 70): does **nothing without Lunatone on your Bench**; damage **ignores
  Weakness/Resistance**. Untagged (§8).
- **Role:** **the designated SETUP / early-RACE attacker** — lead with Cosmic Beam 70 to bridge
  while Mega Lucario ex comes online, then settle back as the engine enabler (keeps Lunar Cycle on)
  + the **Psychic-matchup / W-R-wall fallback** (70 can't be reduced; Grass-weak body dodges Psychic).
- **Use:** play early (Basic; Fighting-Gong/Poké-Pad/Ultra-Ball fetchable). Keep it in play to enable
  Lunatone; keep Lunatone benched to enable its own attack — mutually dependent.
- **Anti-patterns:** declaring Cosmic Beam with no Lunatone benched (0 damage); retreating it away
  early when it's both your attacker and Lunatone's enabler.
- **Disposition:** general `power-up-attacker` / `pre-position-attacker` cover the basics; "lead with
  Solrock in setup/early race" + the W/R-ignoring fallback are deck intent (Role + §6 sketch).

### 2× Lunatone — `draw` engine (LOCKED 2026-06-29)
- **Mechanics:** Basic Fighting · 110 HP · 1 prize · weak **Grass** · retreat 1. Untagged (→ needs
  `draw` tag; §8). Lunar Cycle (Ability, once/turn): **if Solrock in play**, discard a Basic F from
  hand → **draw 3** (max 1/turn). Power Gem (FF · 50) — a fallback attack, rarely the plan.
- **Use:** the deck's **native draw engine** — fire **aggressively** (draw 3 is huge; the discarded F
  becomes Aura Jab fuel, not waste). It's a free Ability → use it **before** committing the turn's
  Supporter (dig first).
- **DISCIPLINE — wincon attach has priority over the discard.** Make the turn's manual energy
  attachment to the **Riolu / Mega Lucario line first**, then discard only a **surplus** F for Lunar
  Cycle. **Never discard the F you need to power the wincon.** Don't strand your last F in the discard
  before Aura Jab is online to redistribute it.
- **Combos:** Solrock (enables Lunar Cycle) ↔ Lunatone (enables Cosmic Beam); discard-as-fuel → Aura Jab.
- **Anti-patterns:** Lunar Cycle with no Solrock in play (can't); discarding the only F you'd attach
  to a Mega this turn; relying on Power Gem (50) as offense.
- **Disposition:** general `dig-before-commit` covers the dig **once tagged `draw`** (untagged today →
  won't fire; §8); the attach-before-discard discipline is a deck rule / energy-procedure refinement (§6).

### 2× Makuhita — setup base for Hariyama (LOCKED 2026-06-29)
- **Mechanics:** Basic Fighting · 80 HP · 1 prize · weak Psychic · retreat 2. Corkscrew Punch (F·10) /
  Confront (FF·30) — negligible. Untagged.
- **Use:** pure setup — **bench it early** to keep the Heave-Ho gust trap available. Fetchable by
  Fighting Gong / Poké Pad / Ultra Ball.
- **Anti-patterns:** wasting a turn attacking with it; leaving none benched (no Hariyama line / no
  Heave-Ho).
- **Disposition:** general bench-development (`pre-position-attacker`); no deck rule.

### 2× Hariyama — `secondary_attacker` + `gust` engine (Heave-Ho) (LOCKED 2026-06-29)
- **Mechanics:** Stage 1 Fighting · 150 HP · 1 prize · weak **Psychic** · retreat 3 · from Makuhita.
  Untagged (→ needs `gust` on the ability; §8).
  - *Ability — Heave-Ho Catcher:* on the Makuhita→Hariyama evolve from hand, **may** switch in 1
    opponent benched Pokémon to Active. **Free, repeatable across both copies, doesn't spend Boss's.**
  - *Wild Press (FFF · 210):* also 70 to itself (→ Hariyama at 80 HP after, fragile + Psychic-weak).
- **Role — BOTH, board-dependent + PRIZE-TRADE STAR:** gust-on-evolve for a **drag-and-KO** (no evolve
  ends the turn → gust then KO same turn), **or** the 210 nuke when you need damage. **210 for a
  1-prize body** makes it the deck's best prize-trade attacker — it KOs most 2-prize ex while giving up
  only 1, and **soaks a KO cheaply between Mega exposures** (see §4 Prize-trade sequencing). Holding
  **Hariyama-in-hand + Makuhita-benched = a sprung trap** to spring any turn.
- **Heave-Ho gating (RELAXED vs Boss's):** prefer the free Heave-Ho **before** Boss's. KO-gusts are
  best, **but tempo gusts are ALLOWED** — because it's free, dragging up an **energyless / high-retreat**
  body to waste their turn is worth it even without a KO. **Still never gust up a powered attacker you
  can't KO** (that just helps them). This is more permissive than the general `gust-for-the-ko` /
  `gust-for-the-stall` (which require a KO or `active_doomed`) → deck-specific handling (§6/§8).
- **Wild Press:** when 210 KOs a worthwhile target on a 1-for-1+ trade and you accept dropping to 80.
  Aura Jab's **load-target #2** powers a benched Hariyama to FFF.
- **Anti-patterns:** Wild Press into the recoil when it leaves Hariyama as a free Psychic-weak KO for
  no prize gain; springing the evolve-gust with no KO/tempo payoff; burning Boss's when Heave-Ho was free.
- **Disposition:** Wild Press → Tactical KO/weakness math. Heave-Ho gust = **new deck rule** (the free,
  tempo-permissive gust; reuses the general `gust-target` value terms but a relaxed gate) — §6 + §8.

### 2× Boss's Orders — `gust` (on-demand, KO-gated) (LOCKED 2026-06-29)
- **Mechanics:** Supporter (one/turn). Switch in 1 opponent benched Pokémon to Active. Tag `gust`,
  engine id 1182 (the shipped general gust doctrine's exact target).
- **Use:** the **on-demand** gust for when you **can't** Heave-Ho (no Makuhita ready, or already
  evolved). Strictly **KO-gated** per the general doctrine: lethal/closing ▸ prize-grab KO ▸
  threat-denial ▸ (defensive stall when doomed). Drag up a benched body you can KO (a prize you
  couldn't otherwise reach — often a high-prize ex hiding behind a wall).
- **Sequencing:** your one Supporter — spend it the turn the gust pays; otherwise a tutor/draw
  usually wins the Supporter slot.
- **Anti-patterns:** gusting a target you can't KO (gifts the opponent); spending it when Heave-Ho was
  free; over it a board-advancing tutor on a turn the gust doesn't pay.
- **Disposition:** **covered as-is** by the shipped general Boss's Orders doctrine (ADR-0022:
  `gust-for-the-ko`, `gust-target`, `gust-for-the-stall`). No deck rule needed.

### 1× Meowth ex — `tutor` (situational key-Supporter), `stall` (LOCKED 2026-06-29)
- **Mechanics:** Basic **Colorless** · 170 HP · **2 prize** · ex. Tags `search`, `stall`.
  - *Ability — Last-Ditch Catch:* on bench-drop from hand, search deck for a **Supporter** to hand
    (once; max 1 "Last-Ditch"/turn).
  - *Tuck Tail (CCC · 60):* return Meowth + attached to hand (un-expose the 2 prizes / re-arm the ability).
- **Use — situational tutor.** Bench it when you **critically need a specific Supporter** (Boss's for
  lethal, Judge/Lillie's to dig out of a brick) and the **2-prize exposure is acceptable**. Protect it
  / keep it back; **Tuck Tail** to retrieve when threatened or to reuse Last-Ditch later (CCC = 3 F,
  expensive).
- **Watchtower clash (sequencing):** Meowth is **{C} → Team Rocket's Watchtower suppresses its
  ability**. Use Last-Ditch **before** laying your own Watchtower (and you can't use it under the
  opponent's Watchtower).
- **Anti-patterns:** benching it for value with no specific Supporter need (loose 2-prize gift);
  using its ability with a Watchtower already in play; Tuck Tail unless retrieving/re-arming matters.
- **Disposition:** general `dont-bench-multiprize` correctly discourages a casual bench (it's not a
  wincon) — the "bench it for a *needed* Supporter" override is deck intent (Role `tutor` + §6). The
  Watchtower-before/after sequencing is a deck rule (§6/§8).

### 4× Lillie's Determination — `draw` (refill) (LOCKED 2026-06-29)
- **Mechanics:** Supporter. Shuffle hand into deck, draw **6** (**8** if exactly 6 prizes remaining).
- **Use:** the refill — play on a **low / dead / clogged** hand. **The draw-8 (exactly 6 prizes) lands
  on your first Supporter-legal turn at 6 prizes — T2 going first** (not T1: no Supporter T1 going
  first). With 4 Lillie's + 3 Judge, these **are** the draw engine (no Professor's/Iono) alongside
  Lunatone. Lower priority than a board-advancing tutor / a KO-gust Boss's.
- **Anti-patterns:** **shuffling away a usable Mega Lucario ex / evolution piece** you can deploy next
  turn (A3 ruling) — hold those; don't refill a hand still full of the pieces you need.
- **Disposition:** general `dig-before-commit` covers the lift (once `draw` fires); the "don't shuffle
  out a deployable wincon" carve-out is a deck rule (§6) reading `wincon_in_hand`.

### 3× Judge — `draw`, `hand_disruption` (LOCKED 2026-06-29)
- **Mechanics:** Supporter. Both players shuffle hand into deck, draw **4**.
- **Use:** **disruption-primary** — cut a hoarding opponent's built-up hand (you refill to 4 too); best
  when your hand is small (you net relative to them) and pairs with Heave-Ho to set them behind. Raw-draw
  value below Lillie's (Judge also helps the opponent).
- **Anti-patterns:** same shuffle caveat (don't ditch a usable Mega/pieces); Judging when it refills
  the opponent more than you (you're hoarding).
- **Disposition:** general `dig-before-commit` (draw); disruption-timing is Posture-ish → note. Same
  "don't shuffle out the wincon" carve-out (§6).

### 4× Ultra Ball — `search` (the Mega/any-Pokémon tutor + discard-fuel) (LOCKED 2026-06-29)
- **Mechanics:** Item. **Discard 2**, then search deck for **any Pokémon** to hand.
- **Use:** the **only** tutor for **Mega Lucario ex** (and Meowth ex). The **discard-2 is partial
  upside** — pitch spare **F into the discard (Aura Jab fuel)** and dead cards. Not the first tutor
  (it costs 2) — reach for it for a Rule-Box mon or to stock the discard. **Discard priority: spare F
  (fuel) ▸ excess Trainers/dupes ▸ redundant pieces — never a piece you need.**
- **Anti-patterns:** paying the 2-card cost when a **free** tutor (Fighting Gong / Poké Pad) finds the
  target; discarding pieces you need.
- **Disposition:** `fetch-the-wincon` governs the pull (Mega Lucario ex); free-tutor-first sequencing
  is general `dig-before-commit`. Discard-target choice (pitch F for Aura Jab) is a deck nuance (§8).

### 4× Fighting Gong — `search` (energy + basic tutor) (LOCKED 2026-06-29)
- **Mechanics:** Item. Search a **Basic F Energy OR a Basic F Pokémon** to hand.
- **Use:** the **only energy tutor** + a Basic-mon tutor (Riolu/Solrock/Lunatone/Makuhita — **not**
  Hariyama/Mega Lucario ex). Free → play early; the consistency backbone. **Early priority: the engine
  (Solrock + Lunatone), then Riolu + F energy** (per the fetch-priority ruling).
- **Anti-patterns:** fetching a redundant piece when energy-starved (grab F) or vice-versa.
- **Disposition:** `dig-before-commit` (search) + `fetch-energy-when-starved` (energy mode); the
  engine-first fetch priority is deck intent (§6).

### 4× Poké Pad — `search` (non-ex engine tutor) (LOCKED 2026-06-29)
- **Mechanics:** Item. Search a Pokémon **without a Rule Box** to hand (Riolu/Solrock/Lunatone/
  Makuhita/**Hariyama** — **not** Mega Lucario ex / Meowth ex).
- **Use:** free engine/line tutor; the only free tutor that reaches **Hariyama**. Play early; same
  engine-first priority.
- **Anti-patterns:** expecting it to find Mega Lucario ex / Meowth (it can't).
- **Disposition:** `dig-before-commit` + `prefer-wincon-line-piece` (Riolu) cover it.

### 4× Premium Power Pro — damage modifier (untagged) (LOCKED 2026-06-29)
- **Mechanics:** Item (unlimited/turn). This turn, your **{F}** attacks do **+30** to opp Active
  (before W/R). **Not tutorable — draw-only.** Strong prior that copies **stack** (+60/+90/+120).
- **Use:** **stack to cross a KO breakpoint** the turn you attack (Mega Brave 270→300→…; Wild Press
  210→240; even Solrock 70→100, applies to its W/R-ignoring damage). **Boosts Active damage only** (all
  our attacks hit the Active). Mono-Fighting → every attacker benefits. Play **the turn the attack
  happens** (this-turn effect); use the **minimum copies** to cross the line (don't over-spend cards).
- **Anti-patterns:** playing it on a non-attacking turn (wasted); playing fewer than needed to cross
  the line, or more than needed (over-commit cards).
- **Disposition:** **deferred to the General Strategy damage-boost OHKO-line model** (§8) — like
  Maximum Belt's damage half; no positional weight yet (the model needs a meta HP table + stacking).

### 2× Switch — `switch` (retreat-swap enabler) (LOCKED 2026-06-29)
- **Mechanics:** Item. Switch your Active with a Benched Pokémon (free).
- **Use:** the **preferred retreat-swap enabler** (it's an Item, not a Tool) — promote a fresh powered
  Mega while the cooldowned one benches **without dumping energy AND without occupying the Mega's tool
  slot** (so Maximum Belt can stay on). Also escapes a stuck/gusted Active; pivots Solrock↔Mega.
- **Disposition:** general retreat/pivot handling; supports the deck's retreat-swap cadence (§6).

### 1× Air Balloon — retreat tool (untagged) (LOCKED 2026-06-29)
- **Mechanics:** Pokémon Tool. Holder's retreat cost is **{C}{C} less** (→ free for our retreat-2 bodies).
- **Use:** a **backup** retreat enabler — **one Tool per Pokémon** (rulebook.txt:597), so Air Balloon
  and **Maximum Belt compete for the Mega's single slot**. **Prefer Switch for the retreat-swap** (keeps
  the slot free for Belt); use Air Balloon on a **second Mega** (the non-Belt swapper), on Hariyama
  (retreat 3 → 1), or when Switch is unavailable.
- **Anti-patterns:** equipping a body that won't retreat; **putting Air Balloon on the Mega that wants
  Maximum Belt** (the +50 breakpoint usually wins the slot — swap with Switch instead).
- **Disposition:** general retreat handling; deck tool-target intent (Mega Lucario ex) → §6.

### 1× Maximum Belt — **ACE SPEC** damage tool (LOCKED 2026-06-29)
- **Mechanics:** Pokémon Tool, **ACE SPEC** (max 1/deck, irreplaceable). Holder's attacks do **+50**
  to an opposing **Active {ex}** (before W/R). **Pure offense — no defensive value.**
- **Use:** equip the **primary Mega Lucario ex**; the **270→320 Dragapult-ex OHKO** enabler and the
  cross-an-ex-KO-line tool generally. Hold the 1-of for an **ex/Mega matchup** where +50 reaches an
  otherwise-unreachable KO; don't fritter it onto a doomed body or a non-ex matchup. **Occupies the
  Mega's single Tool slot** (vs Air Balloon) → do the retreat-swap with **Switch** so Belt stays on.
- **ex-target caveat:** unconfirmed whether the engine counts a `megaEx` target as "{ex}" for the
  bonus (§1) — verify in Phase 3/6.
- **Anti-patterns:** equipping early with no breakpoint in sight (exposes the irreplaceable ACE SPEC);
  on a non-wincon; expecting survivability.
- **Disposition:** general `save-tool-for-the-attacker` + `protect-ace-spec-tool` cover "hold it for
  the wincon"; the **offensive deploy-timing breakpoint defers to the damage-boost model** (§8) —
  `deploy-hp-tool-on-breakpoint` does NOT fire (no `hpBonus`).

### 1× Gravity Mountain — Stadium (anti-Stage-2, untagged) (LOCKED 2026-06-29)
- **Mechanics:** Stadium. Each **Stage 2** Pokémon (both players) gets **−30 HP**. **Never touches our
  board** (all Basic/Stage 1 — verified §1).
- **Use:** **the default Stadium** (zero downside to us) and the answer vs **Stage-2-heavy** boards —
  −30 crosses our breakpoints. Also play to **bump a harmful opponent Stadium**.
- **Disposition:** matchup tech; needs an opponent-board Stage-2 read (§8). No general rule.

### 2× Team Rocket's Watchtower — Stadium (ability-lock, untagged) (LOCKED 2026-06-29)
- **Mechanics:** Stadium. **{C}** Pokémon (both players) have **no Abilities**.
- **Use:** proactive ability-lock **only vs Colorless-ability decks**; **sequence around our own
  Meowth** ({C}). Otherwise prefer Gravity Mountain. Also a Stadium-bump tool.
- **Anti-patterns:** laying it before using Meowth's Last-Ditch (self-suppress); playing it with no
  Colorless-ability target.
- **Disposition:** matchup tech; needs an opponent-board {C}-ability read (§8) + the Meowth sequencing
  rule (§6). No general rule.

### 12× Basic Fighting Energy — the only energy (LOCKED 2026-06-29)
- **Use:** manual attach → **Riolu/Mega line first** (priority over Lunar Cycle's discard). The
  **discard is a second reservoir** via Aura Jab (up to 3/turn → bench). Fighting Gong refills; Ultra
  Ball/Lunar Cycle stock the discard. Demanding for dual-Mega (2×FF) + Hariyama (FFF) → Aura Jab is the
  multiplier that makes 12 enough.
- **Anti-patterns:** stranding F in the discard with no Aura Jab online to redistribute; discarding the
  F you need to power an attack now.
- **Disposition:** general energy-attachment procedure (`power-up-attacker`, `attach-energy-last`);
  the wincon-attach-before-Lunar-Cycle discipline is a deck refinement (§6).

## 4 · Combos, sequencing & opening hands (DRAFT — confirm opening/plan)

### Combos (multi-card engines)
- **Solrock ↔ Lunatone (the engine):** Lunatone draws 3 (needs Solrock in play, discard 1 F);
  Solrock hits 70 ignoring W/R (needs Lunatone benched). Minimum hand: both Basics down + 1 spare F.
  Breaks if either is gone (KO'd / not yet down).
- **Discard-as-fuel → Aura Jab:** Lunar Cycle + Ultra Ball stock Basic F in the discard; **Aura Jab
  recovers up to 3/turn onto the Bench** → builds the 2nd Mega / Hariyama. Breaks with an empty discard.
- **Dual-Mega Mega Brave (retreat-swap):** two powered Megas + a free swap = **Mega Brave every turn**
  (the cooldown is per-Pokémon). Min: Mega A (FF) + bench Mega B (FF, or FF reachable via Aura Jab) +
  a retreat enabler. **Prefer Switch** (keeps Belt on; one-Tool-per-Pokémon); Air Balloon as backup.
  Breaks if you can't power/retreat B.
- **Heave-Ho drag-and-KO:** Makuhita benched + Hariyama in hand → evolve (gust a bench-sitter Active)
  → KO it the same turn (no evolve ends the turn). Free; doesn't spend Boss's.
- **Maximum Belt breakpoint:** Mega Brave 270 **+ Belt 50 = 320** OHKOs Dragapult ex; **+ Power Pro
  +30 = 350** reaches a 340 Mega / Gardevoir-with-help.

### Prize-trade sequencing (CRITICAL — user, 2026-06-29)
The deck mixes **1-prize bodies** (Riolu, Solrock, Lunatone, Makuhita, **Hariyama**) with **3-prize
Megas**. **Order your attackers so the opponent can't reach 6 prizes off a couple of Mega KOs** —
make them take six *individual* prizes.

- **Worked example (the rule's whole point):**
  - **Bad:** Solrock → Lucario → Lucario. Opp KOs Solrock (**1**) → Lucario (**4**) → Lucario (**7 ≥ 6
    → opponent wins**).
  - **Good:** Solrock → Lucario → **Hariyama** → Lucario. Opp KOs Solrock (1) → Lucario (4) → Hariyama
    (**5**, still needs 1) → and you finish with Lucario first. **Interleaving a 1-prize body between
    Mega exposures buys the turn that wins.**
- **Hariyama is the prize-trade STAR**, not just a "secondary": **210 damage for a 1-prize body** —
  it KOs most 2-prize ex while giving up only 1, and soaks a KO cheaply between Mega exposures.
  Combined with its free gust, Hariyama is central to the prize plan.
- **Heuristic (per-turn shadow of the prize map):** at a promote / which-attacker choice, **prefer a
  viable 1-prize attacker over exposing a 3-prize Mega when a Mega KO would hand the opponent their
  prize total** (read `Board.opp_prizes_remaining` vs the Active's prize value). Expose a Mega when the
  trade is favorable or you're closing. Full multi-turn prize-mapping is the **planning/Search** layer
  (the General Strategy routes prize-map there) — this is the tractable weight-shadow. → §6 sketch.

### Sequencing ladder (a developing turn)
1. **Free draw/search first** — Lunar Cycle (Ability), then Poké Pad / Fighting Gong (engine pieces
   first: Solrock + Lunatone, then Riolu + F). Dig before committing.
2. **Bench development** — Riolu(s), Makuhita (arm Heave-Ho), the engine.
3. **The one Supporter** — tutor/disruption that advances the board > raw draw; Lillie's only on a
   dead/clogged hand; **never shuffle out a usable Mega**. Boss's only when its gust pays.
4. **Evolve** (Mega ex / Hariyama — does NOT end the turn; Heave-Ho gust on the Hariyama evolve).
5. **Manual energy attach → Riolu/Mega line first** (then a surplus F can feed Lunar Cycle, already
   done in step 1 — so attach-before-discard means hold that F back when firing Lunar Cycle).
6. **Stadium** if it helps the matchup (Gravity default).
7. **Attack LAST** (Pilot `_finish_turn_last`): KO-first; else the discard-aware Aura-Jab-vs-Mega-Brave
   / two-turn-lookahead choice; Aura Jab loads the bench toward the 2nd Mega.

### Opening hands (going first — confirmed; first-turn restrictions verified)
**Going-first T1 is engine-restricted: NO Supporter, NO evolve, NO attack** (`rulebook.txt:133` /
`rules.md:73,97`; engine-legal so the Pilot never sees those options). T1 = **bench Basics + attach 1
F + free Items + Abilities only.**
- **Mulligan:** keep essentially any hand with a Basic (11 Basics → mulligans rare;
  `keep-a-startable-hand` covers). Going first = a full setup turn, so keep light hands and dig.
- **Dream (going first):** Riolu + Solrock + Lunatone + a free **Item** tutor + F → **T1:** bench all,
  attach F to Riolu, play Fighting Gong/Poké Pad, fire **Lunar Cycle** (Solrock in play + spare F; an
  Ability, allowed). **T2:** first Supporter-legal turn (Lillie's-for-8 if hand weak, still at 6
  prizes), evolve (Riolu→Mega / Makuhita→Hariyama), Solrock Cosmic Beam / evolve-and-Aura-Jab.
- **Median:** a Basic + Item tutors → T1 fetch the engine (Solrock+Lunatone) + Riolu, attach, dig.
- **Survivable:** a lone Riolu/Basic + an Item → keep (going first), spend T1 digging the engine.
- **Lillie's-for-8 timing:** the draw-8 (exactly 6 prizes) lands on your **first Supporter-legal turn
  while still at 6 prizes** — T2 going first. Play it then on a genuinely weak hand (not as a reflex).

### Supporter priority (one/turn — confirmed)
**Boss's (only when its gust KOs/closes) ▸ then a draw Supporter by hand-state:** **Lillie's** when the
hand is low/dead (the weak-hand refill; T2 for the 8); **Judge** when disruption matters (opponent
hoarding) or your hand is small (≤3). Board-advancing draw/tutor outranks a raw refill. Meowth's
Last-Ditch *fetches* the needed Supporter into hand (you still spend the slot to play it).

### Mid-game tutor priority (set up — confirmed: need-driven)
Fetch the **immediate bottleneck: energy (Fighting Gong) ▸ next Mega (Ultra Ball) ▸ Hariyama (Poké
Pad)** — energy when an attack is short, the 2nd Mega to build the dual-Mega engine, Hariyama for a
prize-trade KO/gust. (Free Items first; Ultra Ball's discard pitches F as Aura Jab fuel.)

### Plan mapping
- **SETUP** (no real attacker online): bench Riolu(s) + the Solrock/Lunatone engine, attach to the
  line, Lunar Cycle dig, free-tutor the engine first. **Online flips to RACE at 1 F** on the payoff
  (Aura Jab — engine default is correct; **no `Ready` override**), though Solrock (1 F) is usually the
  first attacker.
- **RACE** (attacker online): attack every turn. Early = **Solrock 70** bridging; then **Mega Lucario
  ex** — Aura Jab to build the 2nd Mega / Mega Brave to nuke; **dual-Mega retreat-swap** for sustained
  270s; **Hariyama gust-and-KO**. KO-first; Aura Jab loads toward the 2nd Mega.
- **STABILIZE** (behind / Mega threatened, esp. vs Psychic): lean the **Solrock single-prize plan**
  (Grass-weak, ignores W/R), retreat-swap to a fresh Mega, **gust-stall** (Heave-Ho tempo / Boss's),
  **Judge** to strip the opponent, rebuild via Fighting Gong + Aura Jab.
- **CLOSE** (ahead / lethal): **gust for the last prizes** (free Heave-Ho / Boss's), **Mega Brave +
  Belt/PPP** for the breakpoint KO; the two-KO turn (Aura Jab KO + separately-evolved Hariyama gust-KO).

## 5 · General-Strategy disposition table

| General Hypothesis | Disposition | Seed | Why (deck-specific) |
|---|---|---|---|
| `evolve-into-wincon` | covers-as-is | — | Riolu → Mega Lucario ex |
| `dig-before-commit` | covers-as-is (tag gap) | — | fires on the Trainer draw/search (all tagged); **does NOT fire on Lunatone's Lunar Cycle** (untagged + it's an Ability use, not a card PLAY) — Lunatone draw-first is taken on Tactical/free-ability value, not this rule |
| `power-up-attacker` | covers-as-is (+ deck discipline) | — | attach to a needy attacker; deck adds **wincon-attach-before-Lunar-Cycle-discard** discipline (§6) |
| `attach-energy-last` | covers-as-is | — | standard sequencing |
| `use-acceleration` | **conflicts / gap** | — | the deck's accel is **Aura Jab (an ATTACK)**, not a PLAY of an `energy_accel` card → this rule never fires; the accel value lives in **Tactical** + the deck's **load-targeting** rule (§6). Mega Lucario ex is also untagged. |
| `fetch-the-wincon` | covers-as-is | — | Mega Lucario ex via **Ultra Ball** (only ex-tutor); free tutors can't reach it |
| `fetch-energy-when-starved` | covers-as-is | — | Fighting Gong energy mode |
| `prefer-wincon-line-piece` | covers-as-is | — | Riolu as the line pre-evo at a fetch |
| `keep-a-startable-hand` | covers-as-is | — | 11 Basics → mulligans rare |
| `keep-a-bench` | covers-as-is | — | loss-prevention |
| `dont-bench-multiprize` | covers-as-is (+ deck override) | — | correctly discourages a casual **Meowth ex** bench; the "bench Meowth for a NEEDED Supporter" is deck intent (Role `tutor`); Mega Lucario ex is the wincon → exempt |
| `pre-position-attacker` | covers-as-is | — | develop the bench in RACE → builds the **2nd Mega** |
| `hold-position-in-setup` | covers-as-is | — | go-first/setup-develop; the retreat-**swap** is a RACE action, not penalized |
| `dont-feed-the-doomed` | covers-as-is | — | standard |
| `promote-the-ready-wincon` | covers-as-is | — | promote a ready benched Mega after a KO |
| `promote-the-staller` | **gap (tag)** | — | Solrock is the natural 1-prize staller but is **not `opener`-tagged** → won't fire; tag candidate or accept (§8) |
| `retreat-to-ready-attacker` | covers-as-is (+ gap) | — | covers retreat of a **non-wincon** spent Active into a ready Mega; does **NOT** cover the **dual-Mega retreat-swap** (Active IS the wincon, just cooldowned) → new rule (§6) |
| `save-tool-for-the-attacker` / `protect-ace-spec-tool` | covers-as-is | — | **Maximum Belt** (ACE SPEC) → hold for the wincon Mega; Air Balloon untagged (won't fire — fine, it sometimes wants a non-wincon body) |
| `gust-for-the-ko` / `gust-for-the-stall` | covers-as-is | — | **Boss's Orders (id 1182, `gust` tag, Supporter cardType)** — the shipped doctrine fires on it. **Heave-Ho** is the relaxed deck variant (§6) |
| **`build-active-wincon`** | **covers-as-is (key)** | — | keeps attaching to the Active Mega until its **biggest** attack (Mega Brave, `maxDamageCost`=2) is online → **builds the Mega toward FF** without a deck rule. Matches `setup_energy_target=2` |
| **`attach-before-hand-shuffle`** (−60) | **covers-as-is (key)** | — | attach your F **before** Lillie's/Judge (a `discard_hand` shuffle would pitch held energy). **Needs Judge tagged `discard_hand`** (infra) — Lillie's already is |
| **`keep-key-cards-at-discard`** (−30) | **covers-as-is** | — | at Ultra Ball's discard-2, won't pitch the **wincon**; spare F (not `discard_eot`, not wincon) is freely pitched as Aura Jab fuel — exactly our discard priority |
| `play-energy-denial` | N/A | — | no `energy_denial` card (no Crushing Hammer) |
| `deploy-hp-tool-on-breakpoint` | N/A | — | no +HP tools (Belt is +damage, Air Balloon retreat) |
| `dont-waste-discard-energy`, `hold-clutch-heal`, `prefer-rush-evolve-tutor`/`dont-rush-evolve-without-target`, `prefer-bench-fill-first`, `snipe-*`/`snipe-the-strongest-evolving-threat` | N/A | — | no `discard_eot`/`clutch_heal`/`rush_evolve`/`bench_fill` cards; **no attack damages the opp Bench** (snipe rules never fire — our gust drags bench→active, then we hit the Active) |

**Re-verification note (2026-06-29):** checked the FULL general strategy (32 rules). The deck is **heavily
covered** — `build-active-wincon` + `attach-before-hand-shuffle` + `keep-key-cards-at-discard` were the
high-value finds (they obviate several drafted deck refinements). Genuinely-new general contributions
are narrow: `hold-wincon-dont-shuffle`, the prize-aware shadow, and the Heave-Ho gust split (§6/§9).

### 5b · Re-baseline vs the merged general layer (2026-07-02)

The general layer grew 32 → ~52 rules + new systems since Phase A (Lethal Solver ADR-0030, Turn
Planner ADR-0031, effect compendium `AttackStat`/damage-oracle ADR-0032, `TransientTracker`
ADR-0033, Tool doctrine ADR-0028, the ADR-0034 fold, `Strategy.weight_overrides` ADR-0035).
Disposition deltas that supersede §5/§6 entries:

| Drafted in §6 | New disposition | Why |
|---|---|---|
| `hold-wincon-dont-shuffle` | **shipped GENERAL** (doctrine_shuffle_refresh, −25; + `hold-wincon-with-base-dont-shuffle` −15, `hold-successor-when-doomed` −35) | landed via T1 + evolved; `discard_hand` tag rejected → `shuffle_hand` |
| `aura-jab-load-second-mega` | **covers-as-is** (verify by test) | Aura Jab's resolve is an `ATTACH_FROM` select; general `concentrate-accel-on-one-line-body` (+20, `attach_from_target_is_concentrate` → evolved-wincon-most-energy-short-of-payoff picker) loads the 2nd Mega first, `spread-attach-to-the-needy` (+15) then feeds Hariyama |
| `aura-jab-prefer-when-discard-fueled` | **GENERAL tactical** (new): energy-recover credit + self-lock cost | a weight can't express the ≈140 chip differential (out of band); belongs in the Tactical layer like the bench-snipe rider credit. `AttackStat` gains a parsed recover fact; `_tactical` credits `min(N, discard fuel)` and charges a lock cost (Mega Brave / Accelerating Stab `nextTurnSameAttackLock`) only when a lock-free attack is affordable. Sub-prize variants inside the KO branch ⇒ "the cheaper KO that also develops" falls out |
| `dual-mega-retreat-swap` | **GENERAL rule** `swap-out-the-locked-attacker` + Board signal | ADR-0033 already parses Mega Brave's lock; surface `active_best_attack_locked` on Board from the tracker; `promote-the-ready-wincon` now fires at SWITCH (+40 on `is_best_promote_target`) so the target pick is covered |
| `prize-aware-attacker-choice` | **largely covered** + one GENERAL rule | `interpose-the-cheap-attacker-to-preserve-the-wincon` (GENERAL, 50, 3 drivers + never-at-1 veto) shipped; residual = `dont-promote-into-their-prize-reach` (−20): soften promoting a wincon whose KO hands the opponent their remaining prizes |
| `heave-ho-tempo-gust` | **half-covered**; deck rules for the rest | gust TARGET tacticals are context-keyed (any opp-bench SWITCH select) → Heave-Ho's resolve reuses KO/stall/keystone target logic for free. Remaining: value the Hariyama EVOLVE when a gust pays (deck `spring-heave-ho-when-it-pays`) + the ACTIVATE yes/no gate (deck; engine-probed) |
| `fetch-the-engine-first` | **stays DECK** (shipped in T1) | reads the deck `engine` Role; fold policy keeps role-DECLARATIONS deck-side, and the rule is deck-editorial priority |
| *(new)* Cosmic Beam guard | **DECK rule** `dont-cosmic-beam-without-lunatone` (−60) | the compendium models the condition only as `damageMin=0` (lethal-safe) — scoring still prices printed 70; a 0-damage declaration without Lunatone is a hard misplay. Phantom-KO case (opp ≤70 HP) needs oracle-level condition modeling — deferred (§8) |
| *(new)* Roles/params adoption | DECK declarations | `MEGA_LUCARIO_EX` += `accel_source` (Aura Jab is a bench-accelerator → `develop-the-accel-recipient` endorses benching the 2nd Riolu; `promote-the-accelerator-for-the-ko` applies); `params.preferred_start="first"` (go-first doctrine → general `honor-preferred-start`) |
| Tool rules | covers-as-is (doctrine_tool, ADR-0028) | `deploy-hp-tool` is +HP-only → inert for Belt/Balloon (no `hpBonus`); `save-tool-for-the-attacker` / `protect-ace-spec-tool` still hold Belt for the Mega; Belt deploy-timing still deferred to the damage-boost model |
| main.py wiring | REFRESH | current contract: `attack_stats` (compendium — without it the synth lacks Cosmic Beam's ignore-flags + Mega Brave's lock), `effects`, Scout+artifact, briefs, posture, `OwnCardModel` tracker + `own_prizes`; import path `common.strategy.general_strategy` |

## 6 · New deck Hypotheses (drafts — trigger sketches, NOT lambdas yet)

### Authorable now (fields exist)

#### `hold-wincon-dont-shuffle` · seed −25 · status: assumed
> (Seeded to NET negative against `dig-before-commit` (+20) — so holding a usable Mega makes a
> hand-shuffle Supporter a mild net-negative, not free.)
> Don't shuffle a usable Mega Lucario ex out of your hand with a hand-shuffling draw Supporter
> (Lillie's Determination / Judge) when you could deploy/power it next turn — hold it and find another
> line. (Refilling a dead hand still wins out when nothing else is available.)

**Trigger sketch:** a `PLAY` of a `draw` Supporter that shuffles the hand (Lillie's / Judge) while
`board.wincon_in_hand`. **Reads:** `option_type` PLAY, `tags` (`draw`), `board.wincon_in_hand`.
**Fires:** any plan. Moderate (not absolute) so a truly dead hand still refills.

#### `fetch-the-engine-first` · seed +20 · status: assumed
> Going first / in setup, a free tutor should prioritise the **Solrock + Lunatone engine** (the draw +
> early attacker that fuels everything), then the Riolu line + Fighting Energy.

**Trigger sketch:** at a `TO_HAND` search in `SETUP`, the candidate carries the deck `engine` Role
(Solrock / Lunatone) **and the engine isn't yet fully in play**. **Reads:** `select_context` TO_HAND,
`roles`, `plan`. **Seeded +20 — just above `prefer-wincon-line-piece` (Riolu, +18)** so the engine
edges the line piece early, per the fetch-priority ruling. New deck Role `engine`.

### Needs new infra (drafted; build in Phase B or flag deferred)

#### `aura-jab-prefer-when-discard-fueled` · seed: Tactical refinement + small nudge · status: assumed
> Prefer **Aura Jab** (130 + load) over Mega Brave on a non-KO turn **only when Basic F sits in the
> discard** to load (else Aura Jab is a bare 130). On a KO turn, take the cheaper KO that also develops.
> Two-turn lookahead: Aura Jab now + Mega Brave next (= 400) to KO a key attacker.

**Needs:** `Board.discard_basic_f` (count/presence of Basic F in my discard) — **not in Board today**.
The KO-first + two-turn value is **Tactical/Search**, not a positional weight. **Reads (new):**
`board.discard_basic_f`; existing `is_ko`, `tactical`.

#### `aura-jab-load-second-mega` · seed +20 · status: assumed
> When Aura Jab attaches up to 3 Basic F from discard to the Bench, load a **second Mega Lucario ex
> first** (toward FF), then a benched **Hariyama** (toward FFF), then spread.

**Needs:** the SelectContext of Aura Jab's attach-to-bench resolve (verify in `cg/api.py`); reuses
`attach_target_roles` / `card_is_wincon` / `attach_target_needs`. **Reads:** that select +
`attach_target_roles`.

#### `dual-mega-retreat-swap` · seed +40 · status: assumed
> When your Active Mega Lucario ex can't Mega Brave this turn (per-Pokémon cooldown) and a benched Mega
> is powered (FF, or FF reachable), retreat/Switch/Air-Balloon into it and Mega Brave with the fresh
> copy — sustained 270s every turn.

**Needs:** a **Mega-Brave-cooldown** read (`board.active_attack_on_cooldown` — which Pokémon used Mega
Brave last turn); reuses `board.bench_wincon_ready`, `board.active_is_wincon`. The general
`retreat-to-ready-attacker` won't cover it (`not active_is_wincon` excludes a cooldowned wincon).

#### `heave-ho-tempo-gust` · seed: gust-value + relaxed gate · status: assumed
> On the Makuhita→Hariyama evolve, the **free** Heave-Ho gust may fire for a KO (best) **or** a tempo
> drag (an energyless / high-retreat body to waste their turn) even without a KO — more permissive than
> Boss's (which stays KO-gated), because it costs nothing. Still **never gust up a powered attacker you
> can't KO**.

**Needs:** Heave-Ho's gust mechanic (the **four-mechanic split** deferred in ADR-0022 — the evolve
triggers its own SWITCH select). Reuses the `gust-target` value terms + a `stall_target_exists`-style
read **without** the `active_doomed` precondition.

#### `prize-aware-attacker-choice` · seed: planning-shadow weight · status: assumed
> Don't expose a 3-prize Mega Lucario ex as the attacking Active when the opponent can KO it and that
> KO reaches their remaining prize total, if a **viable 1-prize attacker** (Hariyama 210 / Solrock 70)
> can do the job instead — make them take six individual prizes, not two Megas. Interleave 1-prize
> bodies between Mega exposures.

**Partly authorable** (`board.opp_prizes_remaining` exists; Active prize value off `stat`), but the
"is a 1-prize attacker *viable* this turn" + multi-turn sequencing is the **planning/Search** layer —
the General Strategy routes the full prize-map there ([general-strategy.md] "Not a reflex weight").
**Reads:** `board.opp_prizes_remaining`, `board.active_doomed`, the Active's prize value, a benched
viable 1-prize attacker. **Fires:** promote / which-attacker decisions in RACE/CLOSE/STABILIZE.
**Caveat:** must never suppress a lethal of our own (KO-first).

### Deferred to existing General-Strategy work
- **Damage-boost OHKO-line model** (Premium Power Pro stacking + Maximum Belt +50 breakpoints) — the
  already-deferred general model (needs a meta HP table + stacking); the doctrine names the breakpoints
  (270→320 Dragapult), the executable form waits.
- **Stadium matchup choice** (Gravity Mountain default / Watchtower vs Colorless-ability / bump a
  harmful opp Stadium; Meowth-before-Watchtower sequencing) — needs opponent-board **stage/type/ability
  reads** (the Read/Posture layer). v1: lean Gravity Mountain (zero downside) when a Stadium is wanted.

## 7 · Roles, Lines, params (pre-code)

```python
# ids verified against the engine (2026-06-29)
RIOLU, MEGA_LUCARIO_EX = 677, 678
SOLROCK, LUNATONE, MAKUHITA, HARIYAMA, MEOWTH_EX = 676, 675, 673, 674, 1071
BOSS_ORDERS, MAX_BELT, AIR_BALLOON = 1182, 1158, 1174

roles = {
    MEGA_LUCARIO_EX: ["win_condition", "primary_attacker"],
    RIOLU:           ["win_condition_base"],          # line pre-evo
    SOLROCK:         ["secondary_attacker", "engine"], # early attacker + Lunar Cycle enabler
    LUNATONE:        ["draw", "engine"],               # the native draw engine
    HARIYAMA:        ["secondary_attacker", "gust"],   # Heave-Ho + Wild Press
    MAKUHITA:        ["evolution_base"],
    MEOWTH_EX:       ["tutor"],                         # situational Supporter fetch
    BOSS_ORDERS:     ["gust"],
    MAX_BELT:        ["damage_tool"],
    AIR_BALLOON:     ["retreat_tool"],
}
lines  = [ Line(path=[RIOLU, MEGA_LUCARIO_EX], payoff=MEGA_LUCARIO_EX, role="win_condition") ]
# Secondary attackers (Solrock, Makuhita→Hariyama) are NOT a Line payoff — they're Roles, so the
# Line stays single (the wincon). Online (SETUP→RACE) at the engine default = 1 F (Aura Jab) — correct,
# no Ready() override.
params = { "setup_energy_target": 2, "search_budget": 0 }   # 2 = FF for the first Mega Brave
```

## 8 · Open questions / deferred

### Tag-coverage gap (infra)
The deck's own Pokémon/items are **untagged** in `card_functions.json`: Riolu, Mega Lucario ex,
Solrock, Makuhita, Hariyama, Lunatone, Premium Power Pro. Candidate tags: **Lunatone → `draw`**,
**Hariyama → `gust`** (on Heave-Ho), **Mega Lucario ex → `energy_accel`** (but Aura Jab is an ATTACK,
so `use-acceleration` — keyed on a card PLAY — still won't fire; the value is Tactical), **Solrock →**
attacker/enabler. **Net:** few general rules currently key off these; the deck leans on **Roles**.
Tagging Lunatone `draw` and Hariyama `gust` is the highest-value infra task. (Note: even tagged,
`dig-before-commit` won't fire on Lunar Cycle — an Ability *use* isn't an `option_type == PLAY`.)

### Wild Press recoil (70 self-damage) — representation (investigated 2026-06-29)
- **Parsed & precomputable today:** `parse_attack_recoil` (provider.py, ADR-0022) returns **70** for
  Wild Press (verified), 0 for our other attacks. **Not** a `card_functions.json` tag, **not** a
  `CardStat` field.
- **Consumed today only by the lethal draw-guard** (`Pilot.recoil` dict, attackId→self-damage, wired
  per-agent in `main.py` à la mega_starmie): a lethal whose forced recoil self-KOs my Active into the
  opponent's last prize = a **draw, not a win**.
- **Phase B for this deck:** `mega_lucario/main.py` must build `recoil={a.attackId:
  parse_attack_recoil(a.text)}` and pass it to the Pilot (else the draw-guard is blind to Wild Press).
- **RECOMMENDED infra (the "sensible place"):** promote recoil to **`CardStat.recoil`** (parse in
  `_build`, like `hpBonus`) so it's centrally precomputed and the **Tactical** layer can use it for
  general **survival** math — "don't Wild Press into a free KO at 80 HP for no prize gain" — not just
  the draw-guard. Currently no rule models post-recoil fragility.

### New Context/Board signals the drafted rules need (Phase B)
- **`Board.discard_basic_f`** (count/presence of Basic F in my discard) → `aura-jab-prefer-when-discard-fueled`.
- **Aura Jab attach-to-bench SelectContext** (verify in `cg/api.py`) → `aura-jab-load-second-mega`.
- **`Board.active_attack_on_cooldown`** (Active used Mega Brave last turn) → `dual-mega-retreat-swap`.
- **Heave-Ho gust mechanic** (the ADR-0022 four-mechanic split; the evolve's own SWITCH select) +
  a relaxed (no-`active_doomed`) tempo-stall read → `heave-ho-tempo-gust`.
- A deck **`engine` Role** (Solrock/Lunatone) → `fetch-the-engine-first`.

### Deferred to existing General-Strategy work *(superseded — all but the last BUILT in §9 T8', 2026-07-03)*
- ~~**Damage-boost OHKO-line model**~~ — BUILT (T8'): boost facts on `CardStat`, `TurnBoostTracker`,
  oracle boosts, `_boost_lethal_tactical` (stacking crossings). The megaEx-as-{ex} question is
  resolved: rulebook.txt:337 says Mega Evolution Pokémon ex ARE Pokémon ex.
- ~~**Stadium matchup choice + opponent-board reads**~~ — BUILT (T8') as card-fact reads
  (`opp_has_stage2` / `opp_has_colorless_ability` — no Read/Posture dependency) + the two deck
  rules; only current-Stadium visibility (bump timing) remains unread.
- **Meowth ex "bench for a needed Supporter" override** of `dont-bench-multiprize` — needs a
  "do I need a specific Supporter now" signal; situational, low priority. (Still deferred.)

### Resolved this session
- Gravity Mountain one-sided (engine stage flags verified, §1); Mega-ex evolve-and-attack; Watchtower
  suppresses our Meowth (sequencing); go-first; flexible multi-attacker; Aura Jab is the engine;
  dual-Mega when able; keep-evolving-vs-Psychic (no suppress-evolve / no Read dependency).

## 9 · Phase B build plan (placement decisions + tranches)

**Placement principle** (authoring.md): reads only universal `tags`/`stat`/`board`/`roles` AND helps
any deck → **general**; reads deck `card_id`s / the deck's Line / deck Roles → **deck**. When unsure, deck.

| New rule / infra | Placement | Why |
|---|---|---|
| `CardStat.recoil` (parse in `_build`) | **GENERAL infra** | the "sensible place"; Tactical survival math for any recoil attack (Wild Press 70) |
| Tag Lunatone(675)=`draw`, Hariyama(674)=`gust`, Judge(1213)+=`discard_hand` | **GENERAL infra** (card_functions.json) | behavioral truth; unblocks `attach-before-hand-shuffle` (Judge) + future |
| `hold-wincon-dont-shuffle` (`discard_hand`+`wincon_in_hand`) | **GENERAL** | universal; complements `attach-before-hand-shuffle`(energy)/`keep-key-cards-at-discard`(discard) — neither guards the *hand-shuffle* of the wincon |
| `fetch-the-engine-first` (`engine` Role) | **DECK** | Roles are deck editorial |
| `aura-jab-load-second-mega` (Aura Jab select + roles) | **DECK** | specific to Aura Jab's resolve; promote later if other accel-attacks appear |
| `prize-aware-attacker-choice` (per-turn prize shadow) | **GENERAL** | universal prize-trade; conservative, KO-first-guarded |
| discard-basic-F signal + `aura-jab-prefer-when-discard-fueled` | **GENERAL infra** + Tactical | discard-energy count is universal; Aura-Jab choice is Tactical |
| cooldown signal + `retreat-cooldowned-wincon-swap` | **GENERAL** | "can't use X next turn" is a general mechanic; rule reads board+wincon |
| Heave-Ho gust (four-mechanic split) + relaxed free-gust tempo gate | **GENERAL** | the ADR-0022 deferred split; ability-gust handling is engine-general |
| Damage-boost OHKO model (Power Pro/Belt breakpoints) | **GENERAL, deferred** | large (meta HP table + stacking) — out of scope this build; named only |

**Tranche order (each gated: trigger tests → `pytest tests/ -q` green → `check_agent.py` playable):**
- **T1 (foundation): ✅ DONE 2026-06-29 (gated).** `CardStat.recoil` (parsed in `_build_cache`; Wild
  Press→70 verified); deck `strategy.py` (roles/Line/params) + `main.py` (recoil wired); GENERAL
  `hold-wincon-dont-shuffle` (−25); DECK `fetch-the-engine-first` (+20). (T1's Judge `discard_hand`
  tag was superseded on main by the `shuffle_hand` vocabulary; T1's trigger-test file was never
  committed — recreated in T2'.) _Committed fd3ea94/1fe179a._
- **T2' (hygiene): ✅ DONE 2026-07-02.** origin/main merged (clean); `main.py` refreshed to the current
  wiring contract (attack_stats + effects + Scout/artifact + briefs + posture + `OwnCardModel`/
  `own_prizes`; import path fix); trigger tests recreated as `tests/agents/test_mega_lucario_triggers.py`
  (18 tests); STRATEGY.md re-baselined (§5b).
- **T3' (Aura Jab): ✅ DONE 2026-07-02 — GENERAL tactical.** `AttackStat.recoverN/recoverEnergyType/
  recoverTarget` (+ `parse_attack_energy_recover`; pool-verified 6 recover attacks), Board
  `my_discard_basic_energy`, Context `attack_id`; `_tactical` recover credit (`_ENERGY_RECOVER` 75/energy
  chip-scale; sub-prize 0.25/cap 0.75 in the KO branch) + self-lock cost (`_LOCK_COST` 40 / `_LOCK_KO`
  0.3, charged only when a lock-free attack is affordable — a lone locking attack still beats passing).
  Tests: fueled AJ > MB; empty-discard MB > AJ; AJ-KO over MB-KO; Stab never below END; ATTACH_FROM
  concentrate routes the load to the benched 2nd Mega (covers-as-is proof).
- **T4' (swap): ✅ DONE — GENERAL.** Board `active_best_attack_locked` (TransientTracker serial-gated) +
  `swap-out-the-locked-attacker` (+35, baseline_retreat; RETREAT or `switch`-tag PLAY when
  `bench_wincon_ready`). Target pick at SWITCH = `promote-the-ready-wincon` (covered).
- **T5' (prize reach): ✅ DONE — GENERAL.** `dont-promote-into-their-prize-reach` (−20, baseline_promote;
  TO_ACTIVE wincon option, `card_prize_value >= opp_prizes_remaining >= 2`, not `promote_target_kos`,
  not closing).
- **T6' (Heave-Ho): ✅ DONE — DECK.** Engine probe (6 self-matches) pinned the shapes: the evolve
  triggers **ACTIVATE(43)** with bare YES/NO options and the owner only on **`select.contextCard`**
  (id 674), then the target pick is an **opponent-owned SWITCH(3)** select (same shape as Boss's — the
  general gust target tacticals cover it; `select.effect` carries the ability's owner). New GENERAL
  Context field `context_card_id` exposes the owner; deck rules `spring-heave-ho-when-it-pays` (+25 on
  the Hariyama EVOLVE), `heave-ho-gust-when-it-pays` (+15 on ACTIVATE-YES with payoff) and
  `heave-ho-decline-without-payoff` (−40 on ACTIVATE-YES without — the Pilot's tie-break otherwise
  always answers YES and would gust up a powered gift).
- **T7' (deck guards/adoption): ✅ DONE — DECK.** `dont-cosmic-beam-without-lunatone` (−60, keyed on
  the new `attack_id`); `MEGA_LUCARIO_EX` += `accel_source`; `params.preferred_start="first"` +
  `params.my_archetype="Hariyama / Mega Lucario ex / Solrock"`; `aligned.json` ledger.
- **T8' (the deferred five): ✅ DONE 2026-07-03.**
  - **Damage-boost OHKO model (GENERAL):** `CardStat.damageBoost/damageBoostType/damageBoostVsEx`
    parsed from Trainer text (pool-verified 4: Power Pro {F}+30, Maximum Belt +50-vs-ex, Black
    Belt's Training +40-vs-ex; multi-mode Kieran fail-closed); `TurnBoostTracker` (transients.py)
    accumulates this-turn boost PLAYs from logs (Tools read off the holder directly); the oracle
    applies gated boosts before W/R; `_boost_lethal_tactical` makes a crossing play/attach
    KO_SCORE-class (stacking: k held copies may cross together; fires only when NECESSARY; skips a
    simultaneous-draw crossing). **Belt's megaEx question resolved at the source:** rulebook.txt:337
    — Mega Evolution Pokémon ex ARE Pokémon ex ⇒ the {ex} gate includes them.
  - **Attack-condition oracle (GENERAL):** `AttackStat.requiresBench` ("does nothing without <X> on
    your Bench" — pool-verified 2: Cosmic Beam/Lunatone, Guardian Burst/Uxie+Azelf) + live
    `atk_bench_names` context; exact/min zero on an unmet condition ("max" keeps printed — Incoming
    may bench the partner first). The deck's `dont-cosmic-beam-without-lunatone` is **RETIRED**
    (covered-as-is), phantom-KO included.
  - **Wild-Press recoil survival (GENERAL):** `_RECOIL_DOOM` (100, Tactical) charges a NON-KO attack
    whose recoil flips a safe Active into a free KO (`_recoil_flips_doom` re-asks `_active_doomed`
    at hp−recoil); a KO/snipe-KO or an already-doomed Active is never charged (the trade/the
    chip-before-dying stay right).
  - **Stadium tech reads:** GENERAL Board `opp_has_stage2` (CardStat.stage2 — new engine-flag field)
    + `opp_has_colorless_ability` + `hand_ids`; DECK `gravity-mountain-vs-stage2` (+15) and
    `watchtower-vs-colorless-abilities` (+15, gated on Meowth NOT still in hand — the
    Last-Ditch-first sequencing). Stadium-slot visibility (bump timing) still unread — minor.
  - **Lunar-Cycle guard (DECK pair):** probe fact — Lunar Cycle is an `ABILITY(10)` MAIN option
    (nothing endorsed it: score 0 lost to any attack!), so `fire-lunar-cycle` (+15, tier-0
    sequencing) + `dont-lunar-cycle-away-the-last-attachable-f` (−30, GENERAL Board
    `hand_basic_energy`; self-sequencing: the guard stands down once the turn's attach lands, so
    the ability still fires on the surplus the same turn).
- **Still deferred:** planner multi-turn (AJ-now + MB-next 400 lookahead); Meowth
  "needed-Supporter" override; current-Stadium visibility (bump timing); conditional boosts
  (Kieran's mode); non-lethal breakpoint boost timing (playing Power Pro toward a 2-turn plan).

Status stays `assumed`/`testing` (the ladder A/B promotes to confirmed/refuted). The human commits each diff.
