# mega_lucario — Playing Doctrine

> Phase-A deliverable of `/deck-genie`. The human-readable strategy the deck plays; the executable
> `strategy.py` is generated from this **after sign-off** (ADR-0017). Build on the
> [General Strategy](../../../docs/general-strategy.md): reuse, override, or extend — don't restate.

**Status:** Phase A **signed off** · Phase B build **COMPLETE** (gated, tranched) · **Last grilled:** 2026-06-29 · **Re-baselined:** 2026-07-02 (§5b/§9) · **Trainer-swap re-run:** 2026-07-03 (§0/§2/§3/§5/§9 — deck.txt trainer package edited; Pokémon core unchanged) · **Author:** deck-genie + Richard

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
- [x] 2026-07-03 **Trainer-swap re-run (deck-genie, this session).** deck.txt trainer package edited
  (Pokémon core 100% unchanged). **Removed:** Maximum Belt (ACE SPEC tool), Team Rocket's Watchtower ×2;
  Judge 3→2, Switch 2→1, Fighting Energy 12→11. **Added:** Unfair Stamp (ACE SPEC Item), Black Belt's
  Training, Team Rocket's Petrel, Wally's Compassion; Air Balloon 1→2, Gravity Mountain 1→2. **Key
  finding:** the general layer (grown since Phase A) already covers all four new cards — `baseline_heal`
  is built around Wally's Compassion (`clutch_heal`), the damage-boost model already parses Black Belt's
  Training, the ace-spec/discard guards handle Unfair Stamp — so **no new deck Hypotheses**; the change
  is doc blocks + disposition flips + deleting the two removed cards' deck rules (Watchtower). See §9 T9'.

Cards still to grill: none. Open questions: see §8 (infra/deferred only).

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

### Supporter (11)  — *trainer-swap 2026-07-03: 9→11 (−1 Judge, +Petrel +Black Belt's +Wally's)*
- **4× Lillie's Determination** — `draw`,`shuffle_hand`: shuffle hand into deck, draw **6** (**8** if exactly 6 prizes remaining).
- **2× Judge** — `draw`,`hand_disruption`,`shuffle_hand`: each player shuffles hand into deck and draws **4**.
- **2× Boss's Orders** — `gust`: switch in 1 of opponent's Benched Pokémon to the Active Spot.
- **1× Team Rocket's Petrel** — `search`: search deck for **any Trainer** card to hand; shuffle. *(NEW — toolbox tutor.)*
- **1× Black Belt's Training** — **(boost via CardStat)**: this turn, your attacks do **+40** to opp Active **{ex}** (before W/R). *(NEW — the ex-breakpoint boost; a Supporter, so it costs the slot.)*
- **1× Wally's Compassion** — `heal`,`clutch_heal`: heal **all** damage from **1 of your Mega ex**, then put **all its Energy into your hand**. *(NEW — reactive Mega reset.)*

### Item (18)
- **4× Ultra Ball** — `cost_discard`,`search`,`tutor_pokemon`: discard **2** cards, then search deck for **any Pokémon** to hand.
- **4× Fighting Gong** — `search`,`tutor_energy`: search a **Basic {F} Energy OR a Basic {F} Pokémon** to hand.
- **4× Poké Pad** — `search`: search a Pokémon **without a Rule Box** (no ex) to hand.
- **4× Premium Power Pro** — **(boost via CardStat)**: this turn, your {F} Pokémon attacks do **+30** to opp Active (before W/R).
- **1× Unfair Stamp** — **[ACE SPEC]** `draw`,`hand_disruption`: **only if a Pokémon of yours was KO'd during the opponent's last turn** — each player shuffles hand into deck; **you draw 5, opponent draws 2**. *(NEW ACE SPEC — comeback disruption.)*
- **1× Switch** — `switch`: switch your Active with a Benched Pokémon.

### Tool (2)
- **2× Air Balloon** — retreat cost of holder is **{C}{C} less** (→ free retreat for our retreat-2 bodies). *(2×: Belt gone → the Mega's Tool slot is free.)*

### Stadium (2)
- **2× Gravity Mountain** — each **Stage 2** Pokémon in play (both players) gets **−30 HP**. *(Now the sole Stadium; Watchtower cut.)*

### Energy (11)
- **11× Basic {F} (Fighting) Energy.**  *(12→11 in the swap.)*

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
  Bench (so attacking *is* the acceleration). Plus 11 basic F + Fighting Gong to find them.
- **Disruption:** Judge (hand-strip), Boss's Orders (gust), Hariyama Heave-Ho (gust-on-evolve),
  Gravity Mountain (−30 to opp Stage 2), **Unfair Stamp** (ACE SPEC — comeback hand-strip after a KO).
- **Damage boost:** Premium Power Pro (+30 to {F} attacks this turn), **Black Belt's Training**
  (Supporter, +40 vs ex — the ex-breakpoint tool, replacing Maximum Belt), Gravity Mountain (−30 to
  opp Stage 2 crosses the same breakpoints one-sidedly).
- **Survival / toolbox:** **Wally's Compassion** (heal a Mega ex to full + bank its Energy to hand —
  a reactive reset vs non-OHKO threats), **Team Rocket's Petrel** (fetch any Trainer — the 1-of
  silver bullets: Boss's, the ACE SPEC, Black Belt's, a Stadium).
- **Energy:** 11× basic Fighting — the *only* energy; reusable, and the discard pile is a second
  reservoir thanks to Aura Jab. No special energy. *(Note: Wally's Compassion banks a healed Mega's
  Energy to HAND, not the discard — so Aura Jab can't recover it, but you re-attach it directly.)*
- **User context:** _(2026-07-03 trainer-swap: Maximum Belt→Unfair Stamp ACE SPEC + Black Belt's for
  the damage; Watchtower→Gravity Mountain; +Petrel toolbox +Wally's survival. Pokémon core unchanged.)_

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
- **Premium Power Pro** (+30 to {F} attacks this turn, Item, unlimited/turn): the damage-boost
  engine. Strong prior that identical "+30" effects **stack** (TCG norm) → multiple = +60/+90/+120.
  Exact stacking is a simulation detail → defer the breakpoint number to the General Strategy's
  (deferred) **damage-boost OHKO-line model**; doctrine intent is "stack Power Pro to cross a KO line."
- **Black Belt's Training** (Supporter, +40 to opp **{ex}** Active only, this turn): the ex-breakpoint
  boost (Maximum Belt's old role). **CardStat `damageBoost=40, damageBoostVsEx=True`** — parsed and
  consumed by the shipped general damage-boost model (§9 T8'). The `megaEx`-as-{ex} question is
  **resolved**: rulebook.txt:337 — Mega Evolution Pokémon ex ARE Pokémon ex, so the {ex} gate includes
  them (matters when the DEFENDER is a Mega ex). **Key difference vs Maximum Belt:** it's a **Supporter**
  (costs the once/turn slot) not a free Tool — so a breakpoint turn can't also Boss's Orders.

## 2 · Research synthesis (cited — confidence: MEDIUM)

Fan-out research (4 search angles → adversarial verify each claim vs the engine card facts → cited
synthesis): **125 raw claims → 44 supported, 50 refuted, 30 card-neutral.** **Card mechanics are
HIGH-confidence** (multi-source + ground-truth-verified). **Strategic prose is thinner** and leans on
two sources ([Pokemon.com][p], [Dark Fox][df]); much of the web corpus describes the **mainline SV
Lucario deck, not this MEG-set engine deck** — every line below was filtered against our actual 60.
Matchup win-rates are unverified meta opinion (soft priors only).

### Trainer-swap re-run (2026-07-03 — cited; two agents, confidence: MEDIUM-HIGH on purpose)
The edited trainer package matches **tournament Limitless lists** running exactly this config (Unfair
Stamp ACE SPEC + Wally's Compassion + Petrel + Black Belt's Training) — e.g. [Arya Zammit-Blizzard][az].
Purpose findings (mechanics owned by the engine dump; these are strategic-role only):
- **Unfair Stamp (ACE SPEC over Maximum Belt):** the **comeback/disruption** camp's ACE SPEC — *"the
  only aggressive hand disruption option"* post-Iono-rotation ([JPP][jpp]). Turns your worst moment
  (losing the 340-HP Mega) into tempo: after a KO, both shuffle, **you draw 5 / opp to 2**. Crucially
  it's an **Item**, so the canonical line is **Unfair Stamp → then Boss's Orders** (Supporter) to gust
  and KO into their crippled 2-card hand. **Belt's +50 damage role was re-sourced** to Black Belt's +
  Power Pro + Gravity Mountain, freeing the ACE-SPEC slot for a higher-impact effect. **Anti-pattern:**
  low value when you're **already ahead** (it's a comeback card) — the consistency camp runs Secret Box
  instead ([jpp], [tcgp]).
- **Black Belt's Training (+40 vs ex, Supporter):** Maximum Belt's damage role moved to the Supporter
  slot. 270 → 310 alone; **+ one Power Pro clears the ~320–340 Mega/ex tier** (the sources' *"330 =
  the magic number for KO'ing a Pokémon ex"*). **Cost:** a **Supporter** — a breakpoint turn can't also
  Boss's Orders ([tcgp], [pz]).
- **Team Rocket's Petrel (Trainer tutor):** the flexible **Arven replacement** — *"search for any
  trainer… item, tool, stadium, or supporter for your next turn."* Fetches the 1-of silver bullets
  (Boss's, Unfair Stamp, Black Belt's, a Stadium) **the turn before** you need them; doesn't draw, so
  only when you need a specific piece, not as filler ([tcgp]).
- **Wally's Compassion (Mega reset):** heal a Mega ex to full → *"forces your opponent to stack up
  more high-damage hits."* Pairs with **Meowth ex** (fetch it via Last-Ditch). **Downside (the Energy
  bounce):** the healed Mega is **de-powered — can't attack until re-attached** — so it's **reactive
  only** (a Mega about to be KO'd that you can re-load), never proactive; also eats the Supporter slot
  ([tcgp], [df]).
- **Gravity Mountain ×2 over Watchtower:** a **damage-math enabler**, not a hate card — Mega Brave 270
  + GM −30 is a clean OHKO on the **Stage-2-ex field** (Dragapult / Gardevoir / Gholdengo / Charizard /
  Hydreigon / Grimmsnarl ex), *"380 vs a Stage-2 ex with GM + boosts."* **Near-strict upside** (our deck
  has NO Stage 2 → the symmetric −30 never touches us). Watchtower is a **tax not damage** and its
  symmetric {C}-ability lock also fights **our own Meowth ex** — so the fixed-damage finisher prefers
  the damage Stadium. **Caveat:** dropping Watchtower cedes the anti-Colorless-ability angle (Pidgeot
  control etc.); some lists still split — **not settled consensus** ([p], [pz], [pb]).
- **1 Switch + 2 Air Balloon (from 2 + 1):** the A↔B two-Mega Mega-Brave loop wants **repeatable** free
  retreat. **Air Balloon stays attached** → free retreat every turn for a retreat-2 Mega; two Balloons
  **pre-equip both Megas** so the alternation costs zero per turn. **Belt gone frees the Tool slot** —
  the enabling change; this **INVERTS** the old §3 "prefer Switch to keep Belt on." Switch stays as a
  1-of one-shot hedge (a Balloon can be knocked off by tool-removal tech) ([pkm], [df]).

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
  (e.g. 270 + Black Belt's 40 + Power Pro 30 = 340, or Gravity Mountain −30 vs a Stage-2 ex). **The
  restriction is bound to THAT specific Mega Lucario ex**, not the Active Spot ([p]).

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

### Matchups (priors — unverified meta) *(breakpoint math updated 2026-07-03: Belt +50 → Black Belt's +40)*
- **Vs Dragapult ex (320 HP):** Mega Brave 270 **+ Black Belt's +40 = 310 (short)** → needs **+ 1
  Power Pro +30 = 340 = OHKO** (Belt's old 270+50=320 no longer available). If it's a **Stage-2**
  Dragapult, **Gravity Mountain −30** does the same one-sidedly: 270 vs a 290-after-−30 body ([p]).
- **Vs Gardevoir ex (very unfavorable, ~5/95):** whole line is Psychic-weak → cheap OHKO on the
  3-prizer. Plan: **don't evolve into Mega Lucario ex; pivot to Solrock** (Grass-weak, Cosmic Beam
  ignores W/R). Solrock has **no native snipe** → drag bench threats Active via Boss's/Heave-Ho. As a
  risky out: Mega Brave 270 + Black Belt's 40 + Power Pro 30 = **340**, plus Gravity Mountain −30 vs a
  Stage-2 Gardevoir line, reaches the KO ([df]).
- **Vs Fighting-weak fields (favored):** weakness ×2 + Power Pro/Black Belt's stack — even Riolu's 30
  scales past 100 vs a weak ex with both modifiers ([df]).
- **Other priors (directional only, opponent cards outside our data):** ~95/5 Joltik Box, ~50/50
  Dragapult/Dusknoir (going second matters there — note vs our go-first default), ~80/20 Gholdengo.

### Tech choices (verified vs our 60)
- **Fighting Gong ×4:** fetches a Basic F energy **or** a Basic F Pokémon — every engine Basic
  (Riolu, Solrock, Lunatone, Makuhita) but **NOT** Hariyama or Mega Lucario ex ([jwa], [b]).
- **Premium Power Pro ×4:** +30 to F attacks this turn — clears OHKO thresholds (270→300, 210→240);
  mono-Fighting so every attacker benefits. **Not tutorable — draw-only** ([p]).
- **Black Belt's Training (Supporter ×1, replaced Maximum Belt):** +40 vs an opposing **Active ex**
  only, this turn. **Pure offense**; the ex-breakpoint enabler — but a **Supporter** (costs the slot),
  not a free Tool. **Unfair Stamp (ACE SPEC ×1)** now fills the ACE-SPEC slot (comeback, not damage) ([tcgp], [jpp]).
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
4. **"Rocky/Stone Fighting Energy for damage reduction / retreat-lock immunity."** We run **11 basic
   Fighting, no special energy** — the card and all its effects don't exist here ([us], [p]).
5. **"Maximum Belt is defensive / pierces resistance / helps survive OHKOs."** *(Moot 2026-07-03 —
   Maximum Belt was cut; retained as a mainline-misread note.)* Single flat +50 vs an
   opposing ex — zero defensive value ([us], [df]).
6. **"Open with Mega Lucario ex."** Impossible — it's a Stage 1; every game opens with a Basic ([p]).
7. **Other fictions:** Professor Turo's Scenario reset loop, Cornerstone Mask Ogerpon ex tech, Secret
   Box ACE SPEC (the *consistency*-camp ACE SPEC — our build is the Unfair Stamp *comeback* camp),
   Night Stretcher — mainline carry-over, none in our 60 ([df], [limitless], [p]). *(2026-07-03 note:
   the earlier "wrong counts" callout for "2 Judge / 2 Air Balloon / ~11 energy" is now STALE — the
   trainer-swap list runs exactly 2 Judge, 2 Air Balloon, 11 Fighting Energy.)*

**Sources:** [Pokemon.com — Building a Mega Lucario ex Deck][p] · [Dark Fox TCG — Deck & Matchup
Guide][df] · [UltimaSupply — Post-Rotation Guide][us] · [Beckett — New Meta April 2026][b] · [Joseph
Writer Anderson — Deck List & Guide][jwa] · [Limitless — Deck Overview][limitless]

[p]: https://www.pokemon.com/us/strategy/pokemon-tcg-deck-list-and-strategy-building-a-mega-lucario-ex-deck
[df]: https://www.darkfoxtcg.com/blogs/news/mega-lucario-deck-matchup-guide
[us]: https://ultimasupply.com/blogs/news/mega-lucario-ex-deck-guide-post-rotation-strategy-and-list
[b]: https://www.beckett.com/news/a-look-at-the-new-pokemon-tcg-meta-april-2026/
[jwa]: https://www.josephwriteranderson.com/blog/mega-lucario-ex-deck-list-and-guide
[limitless]: https://limitlesstcg.com/decks/345

**Trainer-swap sources (2026-07-03):** [Limitless list — Unfair Stamp + Wally's + Petrel + Black
Belt's][az] · [JustPressPlay — rotation / ACE SPEC][jpp] · [TCGplayer — Mega Lucario ex Guide][tcgp] ·
[Pokémon Zone — Mega Lucario][pz] · [pokeman/Bindex — Upgrade Guide][pkm] · [PokéBeach — Post-Rotation
First Impressions][pb]

[az]: https://limitlesstcg.com/decks/list/27458
[jpp]: https://justpressplayonline.com/blogs/news/rotation-for-dummies-part-two-the-staples-that-leave-and-what-to-replace-them-with
[tcgp]: https://www.tcgplayer.com/content/article/Mega-Lucario-ex-Deck-Guide-Pok%C3%A9mon-TCG/edf0e1de-efdd-4702-979e-b27efe3e5171/
[pz]: https://www.pokemon-zone.com/champions/pokemon/lucario-mega-lucario/
[pkm]: https://pokeman.app/blog/mega-lucario-ex-league-battle-deck-upgrade-guide.html
[pb]: https://www.pokebeach.com/?p=318816

### Strategic implications I'm carrying into Phase 3 (for your confirm)
- **Run-3-Mega rhythm:** the per-Pokémon Mega Brave lock means with two powered Megas you Mega Brave
  *every* turn (A then B). The "alternate Mega Brave / Aura Jab on one Lucario" cadence is only forced
  when you have a single Lucario online. → big input to the attack-selection doctrine.
- **Psychic-weakness pivot:** vs Psychic, **suppress the Mega Lucario evolve** and run the Solrock
  single-prize plan. This is a real "don't-evolve-the-wincon" carve-out — unusual, worth a rule.
- **Solrock needs a gust to snipe** — pairs Boss's/Heave-Ho with the Solrock plan.
- **Black Belt's Training is the ex-OHKO breakpoint tool** (270+40=310, +Power Pro=340 kills
  Dragapult ex) — handled by the built damage-boost model; it's a Supporter, so it costs the slot.

## 3 · Card-by-card

Breakpoint table (real-rules arithmetic; the agent's *evaluation* of boosts defers to the General
Strategy damage-boost model — now sourcing the +vs-ex boost from **Black Belt's Training (+40,
Supporter)** instead of the removed Maximum Belt (+50, Tool)):

| Attack | Cost | Base | +1 PPP | +BBT(vs ex) | +BBT+1PPP | +GravMtn(vs Stage2) |
|---|---|---|---|---|---|---|
| Mega Brave | FF | 270 | 300 | **310** | **340** | effective 300 vs 270-after-−30 |
| Aura Jab | F | 130 | 160 | 170 | 200 | — |
| Wild Press (Hariyama) | FFF | 210 (self-70) | 240 | 250 | 280 | effective 240 |
| Cosmic Beam (Solrock) | F | 70 *(ignores W/R)* | 100 | 110 | 140 | 100 |
| Accelerating Stab (Riolu) | F | 30 | 60 | 70 | 100 | 60 |

Named lines: **270** OHKOs ≤270 HP · **Black Belt's +40 → 310**, and **+ 1 Power Pro → 340** clears the
~320–340 Mega/ex tier (the sources' "330 magic number"); note BBT costs the **Supporter slot** so that
turn can't also Boss's Orders · **Gravity Mountain −30 to opp Stage 2** crosses the same lines
one-sidedly (our deck has no Stage 2) — e.g. Mega Brave 270 vs a 300-HP Stage-2 ex after −30 · Solrock
70 **ignores Weakness/Resistance** (un-reducible chip/finisher) · Fighting-weak targets double everything.

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
  - **Mega Brave** when 270 (or 270 + Black Belt's 40 / + PPP / + Gravity Mountain −30) crosses a KO line 130 can't reach.
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

### 1× Meowth ex — `search`, `supporter_tutor` (GRILLED + RE-MODELED 2026-07-03)
- **Mechanics:** Basic **Colorless** · 170 HP · **2 prize** · ex · weak Fighting · retreat 1. Tags
  **`search`, `supporter_tutor`** *(was `search`,`stall`; `stall` removed — inert + wrong for a 2-prize
  body; `supporter_tutor` added, see below)*.
  - *Ability — Last-Ditch Catch:* **when you play this from hand onto your Bench**, search deck for a
    **Supporter** to hand (once; max 1 "Last-Ditch"/turn).
  - *Tuck Tail (CCC · 60):* return Meowth + attached to hand (un-expose the 2 prizes / re-arm the ability).
- **The bug we fixed (2026-07-03 grill).** Meowth carried the `tutor` Role, which the GENERAL rule
  `play-a-tutor-for-the-unfound-wincon` (+25 in SETUP) reads as *"dig for the **win-condition**."* But
  Last-Ditch fetches a **Supporter**, not the wincon — so the role MISFIRED: +25 (mislabeled wincon-dig)
  vs `dont-bench-multiprize` −15 = **net +10 → benched the 2-prize ex in setup for the wrong reason**,
  with `search_targets_exhausted` checking the wrong fetch-set. **Fix:** remove the `tutor` Role; model
  Meowth as a **`supporter_tutor`** (a general tag) with its own correct trigger.
- **Use — PROACTIVE setup Supporter-grab (user ruling 2026-07-03).** Meowth's edge over Petrel: its
  tutor is a **free Ability** (bench Meowth, grab a Supporter, **and still play a Supporter + attack the
  same turn**). So **in SETUP, when you hold NO Supporter, bench Meowth to bank one** — SETUP itself is
  the safety proxy (opponents rarely have a gust + a 170-KO online that early), accepting the 2-prize
  liability for the tempo/consistency.
- **What to grab (context-ranked, at the Last-Ditch search):** **Boss's** if a gust would KO/close now
  ▸ a **draw** Supporter (Lillie's/Judge) to keep digging (the SETUP default) ▸ **Wally's Compassion**
  if a Mega is doomed + resettable.
- **Tuck Tail escape (user ruling: author it).** When Meowth is **Active + doomed** with **3 F**
  attached, Tuck Tail **bounces it to deny the 2-prize KO** (and re-arms Last-Ditch). Its value is the
  return-to-hand, not the 60 damage — so it needs explicit modelling (the Pilot won't pick a weak CCC-60
  attack otherwise). **Built GENERAL** as a Tactical credit (like the recoil-doom charge's mirror):
  `AttackStat.selfReturn` (parses "Put this Pokémon … into your hand") + `_SELF_RETURN_ESCAPE` (50/prize)
  credited in the NON-KO branch of `_tactical` only when the Active is ex/megaEx AND `active_doomed` —
  so a real KO always wins and a healthy Meowth never scoops itself away. Corner case in a Fighting deck
  (3 F is steep), but real, and the fact is reusable (scoop-up-style attacks).
- **Anti-patterns:** benching it with a Supporter already in hand (no need — save the 2-prize); benching
  it out of SETUP into a live gust; Tuck Tail when not doomed / when it strands 3 F for no denial.
- **Disposition:** `dont-bench-multiprize` still guards a casual bench; the new **GENERAL** rule
  `bench-the-supporter-tutor` (SETUP + PLAY + `supporter_tutor` + no Supporter in hand) supplies the
  positive trigger; the grab is a **GENERAL** context-ranked TO_HAND supporter-target pair
  (`grab-a-gust-supporter-for-the-ko` / `grab-a-draw-supporter-in-setup`); Tuck Tail is the Tactical
  `_SELF_RETURN_ESCAPE` credit above. See §5/§9 T9'.

### 4× Lillie's Determination — `draw` (refill) (LOCKED 2026-06-29)
- **Mechanics:** Supporter. Shuffle hand into deck, draw **6** (**8** if exactly 6 prizes remaining).
- **Use:** the refill — play on a **low / dead / clogged** hand. **The draw-8 (exactly 6 prizes) lands
  on your first Supporter-legal turn at 6 prizes — T2 going first** (not T1: no Supporter T1 going
  first). With 4 Lillie's + 2 Judge, these **are** the draw engine (no Professor's/Iono) alongside
  Lunatone. Lower priority than a board-advancing tutor / a KO-gust Boss's.
- **Anti-patterns:** **shuffling away a usable Mega Lucario ex / evolution piece** you can deploy next
  turn (A3 ruling) — hold those; don't refill a hand still full of the pieces you need.
- **Disposition:** general `dig-before-commit` covers the lift (once `draw` fires); the "don't shuffle
  out a deployable wincon" carve-out is a deck rule (§6) reading `wincon_in_hand`.

### 2× Judge — `draw`, `hand_disruption`, `shuffle_hand` (LOCKED 2026-06-29 · count 3→2 2026-07-03)
- **Mechanics:** Supporter. Both players shuffle hand into deck, draw **4**. *(Cut to 2 in the swap —
  Unfair Stamp now carries the heavy post-KO hand-strip; Judge stays as the always-on small disruptor.)*
- **Use:** **disruption-primary** — cut a hoarding opponent's built-up hand (you refill to 4 too); best
  when your hand is small (you net relative to them) and pairs with Heave-Ho to set them behind. Raw-draw
  value below Lillie's (Judge also helps the opponent).
- **Anti-patterns:** same shuffle caveat (don't ditch a usable Mega/pieces); Judging when it refills
  the opponent more than you (you're hoarding).
- **Disposition:** general `dig-before-commit` (draw); disruption-timing is Posture-ish → note. Same
  "don't shuffle out the wincon" carve-out (§6). Unfair Stamp now carries the heavy post-KO strip.

### 1× Team Rocket's Petrel — `search` (Trainer toolbox tutor) (NEW 2026-07-03)
- **Mechanics:** Supporter. Search your deck for **any Trainer** card, reveal it, put it in hand; shuffle.
- **Use:** the **Arven-style toolbox tutor** — fetch the deck's **1-of silver bullets**: **Boss's
  Orders** (gust for a lethal), the **ACE SPEC Unfair Stamp**, **Black Belt's Training** (a breakpoint
  OHKO), or a **Gravity Mountain**. Fetches to **hand a turn ahead**, so grab the piece the turn BEFORE
  you need it (it doesn't play the card). It **doesn't draw**, so it's Supporter-slot card-neutral —
  use it only when you need a specific toolbox piece, not as filler draw.
- **Anti-patterns:** burning it as generic draw (nets card disadvantage vs Lillie's/Judge); fetching a
  piece you can't yet act on when a draw Supporter would develop more.
- **Disposition:** **covers-as-is** by general search handling (`dig-before-commit` / the fetch
  doctrine at the TO_HAND select). The "which Trainer to grab" value pick is situational for a 1-of
  toolbox — left to Tactical/board value; a deck fetch-priority rule is **not** authored (a 1-of
  tutor doesn't justify the hard-coded ids). Flagged as a ladder-watch item (§8) — revisit only if
  misplays surface.

### 1× Wally's Compassion — `heal`, `clutch_heal` (Mega reset) (NEW 2026-07-03)
- **Mechanics:** Supporter. Heal **all** damage from **1 of your Mega ex**, then put **all Energy
  attached to it into your hand**.
- **Use — a REACTIVE survival reset, never proactive.** Play it on a Mega Lucario ex that took a big
  hit but **survived** (340 HP eats most single hits), to reset it to full and force the opponent to
  re-stack a two-hit KO from scratch. The Energy → hand means the Mega is **de-powered until you
  re-attach** — so only do it when you can re-load it (or when banking the Energy beats losing it to a
  KO). **Pairs with Meowth ex** (fetch Wally's via Last-Ditch). It eats the Supporter slot (no Boss's
  that turn).
- **Anti-patterns:** using it on a healthy attacker (strands its Energy, skips your attack); using it
  vs a clean OHKO threat (Psychic weakness → the Mega dies anyway before you profit); proactively.
- **Disposition:** **covers-as-is** by the GENERAL heal doctrine (`baseline_heal.py`, built around this
  exact card): `hold-clutch-heal` (+60 — hold until `active_doomed` and NOT `active_can_ko`, so it
  never forfeits a lethal) and `dont-waste-clutch-heal` (−40 when not doomed). Both fire on the
  `clutch_heal` tag Wally's carries. No deck rule needed.

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
- **Disposition:** **covers-as-is by the built damage-boost model** (§9 T8') — `CardStat.damageBoost=30,
  damageBoostType={F}`; `_boost_lethal_tactical` stacks copies to cross a KO line (same model that
  consumes Black Belt's +40-vs-ex). No positional weight needed.

### 1× Switch — `switch` (retreat-swap backup) (LOCKED 2026-06-29 · count 2→1 2026-07-03)
- **Mechanics:** Item. Switch your Active with a Benched Pokémon (free).
- **Use — now the 1-of hedge (was the preferred enabler).** With **Maximum Belt gone the Mega's Tool
  slot is free**, so **Air Balloon is now the primary retreat-swap engine** (it stays attached →
  free retreat every turn). Switch is the **one-shot backup**: an immediate/early pivot before a
  Balloon is attached, escaping a stuck/gusted Active, or when a Balloon has been knocked off by
  tool-removal tech. Still free, still doesn't dump energy.
- **Disposition:** general retreat/pivot handling; supports the deck's retreat-swap cadence (§6).

### 1× Unfair Stamp — **ACE SPEC** Item, comeback disruption (NEW 2026-07-03; the new ACE SPEC)
- **Mechanics:** Item, **ACE SPEC** (max 1/deck, irreplaceable; CardStat `aceSpec=True`). Tags `draw`,
  `hand_disruption`. **Legal only if a Pokémon of yours was Knocked Out during the opponent's last
  turn** — then each player shuffles hand into deck; **you draw 5, opponent draws 2.**
- **Use — the comeback engine.** After the opponent KOs one of your bodies (typically a Mega), Unfair
  Stamp turns the setback into tempo: refuel to **5** while stripping them to **2**. Because it's an
  **Item**, the canonical line is **Unfair Stamp → then Boss's Orders** (your Supporter) to gust and KO
  into their crippled 2-card hand. Its legality is **engine-gated** (only offered after a KO), so it
  self-times.
- **Anti-patterns:** low value when you're **already ahead** (a comeback card — it also refuels the
  opponent by 2); shuffling a **usable Mega out of your hand** with it — same carve-out as Judge/Lillie's
  (it shuffles YOUR hand too). *(Tag note: Unfair Stamp does NOT currently carry `shuffle_hand`, so the
  general `hold-wincon-dont-shuffle` guard doesn't see it — candidate infra fix, §8.)*
- **Disposition:** **covers-as-is** — the ACE SPEC is protected at cost-discards by
  `keep-key-cards-at-discard` (reads `aceSpec`, so Ultra Ball won't pitch it); `hand_disruption` is
  read by `disrupt-the-hand-size-attacker`. Engine legality gates the play. No deck rule needed;
  the only open item is the `shuffle_hand` tag (§8).

### 2× Air Balloon — retreat tool (untagged) (LOCKED 2026-06-29 · count 1→2 2026-07-03; role inverted)
- **Mechanics:** Pokémon Tool. Holder's retreat cost is **{C}{C} less** (→ free for our retreat-2 bodies).
  Stays attached (repeatable, unlike one-shot Switch).
- **Use — now the PRIMARY retreat-swap engine.** **Belt is gone, so the Mega's single Tool slot is
  free** — pre-equip Air Balloon on **both** Mega Lucario ex so the A↔B Mega-Brave alternation
  (per-Pokémon cooldown) runs at **zero per-turn cost** every turn. Two copies let you arm both Megas;
  also fits Hariyama (retreat 3 → 1). This **inverts** the old doctrine (which preferred Switch to keep
  Belt's slot free) — that constraint no longer exists.
- **Anti-patterns:** equipping a body that won't retreat; relying on a single Balloon on a body that
  tool-removal tech can strip (keep the 1 Switch as the hedge).
- **Disposition:** general retreat handling; deck tool-target intent (Mega Lucario ex) → §6.

### 1× Black Belt's Training — Supporter, ex-breakpoint boost (NEW 2026-07-03; replaces Maximum Belt)
- **Mechanics:** Supporter. This turn, **your attacks do +40 to the opponent's Active {ex}** (before
  W/R). CardStat `damageBoost=40, damageBoostType=None (any attack), damageBoostVsEx=True`. The `{ex}`
  gate **includes Mega ex** (rulebook.txt:337). **Pure offense — no defensive value.** No behavioral
  tag (the boost is a structural CardStat fact).
- **Use:** the **ex-breakpoint tool** (Maximum Belt's old role, now a Supporter). **270 → 310**, and
  **+ 1 Power Pro → 340** clears the ~320–340 Mega/ex tier ("330 magic number"). Play it the turn you
  swing for the OHKO; **fetch it a turn ahead via Petrel** so the boost turn is free.
- **KEY difference vs Maximum Belt — it costs the Supporter slot.** A boost turn **can't also Boss's
  Orders**; gust the target the PRIOR turn (or via free Heave-Ho) so Black Belt's + attack lands
  without needing the gust the same turn. This is the central tax of the ACE-SPEC swap.
- **Anti-patterns:** playing it vs a non-ex target (the +40 does nothing — wasted Supporter); playing
  it on a turn a gust was the higher-value Supporter; expecting any survivability.
- **Disposition:** **covers-as-is** by the shipped general damage-boost model (§9 T8'):
  `CardStat.damageBoost` parsed, `TurnBoostTracker` accumulates it, the oracle applies it before W/R,
  and `_boost_lethal_tactical` makes a boost PLAY that CROSSES a KO line KO_SCORE-class (fires only
  when necessary; stacks with Power Pro copies). No deck rule needed.

### 2× Gravity Mountain — Stadium (anti-Stage-2, untagged) (LOCKED 2026-06-29 · count 1→2, sole Stadium 2026-07-03)
- **Mechanics:** Stadium. Each **Stage 2** Pokémon (both players) gets **−30 HP**. **Never touches our
  board** (all Basic/Stage 1 — verified §1).
- **Use:** **the deck's only Stadium now** (Watchtower cut) — a **damage-math enabler**, near-strict
  upside for us. Mega Brave 270 + GM −30 is a clean OHKO on the **Stage-2-ex field** (Dragapult /
  Gardevoir / Gholdengo / Charizard / Hydreigon / Grimmsnarl ex). Two copies: **findable + re-settable**
  after the opponent bumps it. Also play to **bump a harmful opponent Stadium**.
- **Trade-off vs the cut Watchtower:** dropping Watchtower cedes the anti-Colorless-ability angle
  (Pidgeot control, Meowth-reliant lists) — a meta call, not settled consensus (§2). No self-clash with
  our Meowth anymore (Gravity Mountain doesn't touch abilities).
- **Disposition:** COMPUTED since Issue #424 by `_boost_lethal_tactical`'s HP-delta leg — the
  −30 is priced as a KO-breakpoint crossing off the card's own `stadium_static`/`hp_delta` clause,
  differenced against whatever Stadium is already in play. *(The deck rule
  `gravity-mountain-vs-stage2` (+15, `board.opp_has_stage2`) is RETIRED — a flat weight could not
  tell a board where the −30 crosses from one where it does not. The older
  `watchtower-vs-colorless-abilities` deck rule is RETIRED too — card removed.)*

### 11× Basic Fighting Energy — the only energy (LOCKED 2026-06-29 · count 12→11 2026-07-03)
- **Use:** manual attach → **Riolu/Mega line first** (priority over Lunar Cycle's discard). The
  **discard is a second reservoir** via Aura Jab (up to 3/turn → bench). Fighting Gong refills; Ultra
  Ball/Lunar Cycle stock the discard. Demanding for dual-Mega (2×FF) + Hariyama (FFF) → Aura Jab is the
  multiplier that makes **11** enough (12→11 in the swap — one slot went to the trainer toolbox).
  **Wally's Compassion caveat:** a healed Mega's Energy returns to **hand** (not discard), so Aura Jab
  can't recover it — but you re-attach it directly next turn.
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
  a retreat enabler. **Now: pre-equip Air Balloon on BOTH Megas** (Belt gone → the Tool slot is free)
  → the alternation costs zero per turn; Switch is the 1-of hedge (early pivot / a Balloon knocked off).
  *(This inverts the old "prefer Switch" — that only existed to keep Belt's slot free.)* Breaks if you
  can't power/retreat B.
- **Heave-Ho drag-and-KO:** Makuhita benched + Hariyama in hand → evolve (gust a bench-sitter Active)
  → KO it the same turn (no evolve ends the turn). Free; doesn't spend Boss's.
- **Black Belt's Training breakpoint:** Mega Brave 270 **+ Black Belt's 40 = 310**; **+ Power Pro
  +30 = 340** reaches the ~320–340 Mega/ex tier. Costs the **Supporter slot** (no Boss's that turn) →
  gust the target the PRIOR turn or via free Heave-Ho. **Gravity Mountain −30** crosses the same lines
  vs a Stage-2 ex one-sidedly (stacks with the boosts).
- **Unfair Stamp comeback (Item):** after the opponent KOs a body → Unfair Stamp (you draw 5, opp to 2)
  **then Boss's Orders** the same turn (Stamp is an Item, doesn't cost the Supporter) → gust + KO into
  their 2-card hand.

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

### Supporter priority (one/turn — now 11 Supporters after the swap)
Priority by situation (the slot is now more contested — 4 Lillie's / 2 Judge / 2 Boss's / 1 Petrel /
1 Black Belt's / 1 Wally's):
- **Lethal this turn:** **Boss's** (gust the KO) — or **Black Belt's Training** when +40 vs an ex is
  what crosses the breakpoint (mutually exclusive with Boss's — gust the target the prior turn).
- **Survival:** **Wally's Compassion** when the Active Mega is doomed but resettable (general
  `hold-clutch-heal` gates this — held until doomed, stands down if the Mega can already KO).
- **Toolbox need:** **Petrel** to fetch a specific 1-of (Boss's / Unfair Stamp / Black Belt's / Stadium)
  a turn ahead — only when you need the piece, not as filler.
- **Draw by hand-state:** **Lillie's** when low/dead (T2 for the 8); **Judge** when disruption matters
  or your hand is small (≤3). Board-advancing draw/tutor outranks a raw refill.
- **Note:** Unfair Stamp is an **Item**, not a Supporter — it doesn't compete for this slot (it's the
  post-KO comeback, played alongside a Supporter). Meowth's Last-Ditch *fetches* a Supporter into hand
  (you still spend the slot to play it).

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
  **Judge** to strip the opponent, **Wally's Compassion** to reset a survivable Mega, and after a KO
  the **Unfair Stamp → Boss's** comeback line; rebuild via Fighting Gong + Aura Jab.
- **CLOSE** (ahead / lethal): **gust for the last prizes** (free Heave-Ho / Boss's), **Mega Brave +
  Black Belt's/PPP** (or **Gravity Mountain −30** vs a Stage-2 ex) for the breakpoint KO; the two-KO
  turn (Aura Jab KO + separately-evolved Hariyama gust-KO).

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
| `dont-bench-multiprize` | covers-as-is | — | still guards a casual **Meowth ex** bench; Mega Lucario ex is the wincon → exempt |
| `play-a-tutor-for-the-unfound-wincon` | **conflicts → FIXED (2026-07-03)** | — | MISFIRED on Meowth's `tutor` Role (+25 "wincon-dig" but Last-Ditch fetches a **Supporter**). **Role removed**; replaced by the new general `supporter_tutor` model below |
| **`bench-the-supporter-tutor`** (NEW general) | **gap → general rule** | +weight | Meowth `supporter_tutor` tag: in SETUP with NO Supporter in hand, bench it to bank one (free-ability edge). SETUP = the safety proxy. Grab is a context-ranked TO_HAND supporter-target rule (Boss's-KO ▸ draw ▸ Wally's) |
| **Tuck Tail escape** (`_SELF_RETURN_ESCAPE`, NEW) | **gap → GENERAL Tactical** | +50/prize | Meowth Active + `active_doomed` + 3 F → bounce to deny the 2-prize KO / re-arm. `AttackStat.selfReturn` fact + a Tactical credit (non-KO branch only; a real KO always wins) — mirror of `_RECOIL_DOOM` |
| `pre-position-attacker` | covers-as-is | — | develop the bench in RACE → builds the **2nd Mega** |
| `hold-position-in-setup` | covers-as-is | — | go-first/setup-develop; the retreat-**swap** is a RACE action, not penalized |
| `dont-feed-the-doomed` | covers-as-is | — | standard |
| `promote-the-ready-wincon` | covers-as-is | — | promote a ready benched Mega after a KO |
| `promote-the-staller` | **gap (tag)** | — | Solrock is the natural 1-prize staller but is **not `opener`-tagged** → won't fire; tag candidate or accept (§8) |
| `retreat-to-ready-attacker` | covers-as-is (+ gap) | — | covers retreat of a **non-wincon** spent Active into a ready Mega; does **NOT** cover the **dual-Mega retreat-swap** (Active IS the wincon, just cooldowned) → new rule (§6) |
| `save-tool-for-the-attacker` / `protect-ace-spec-tool` | **N/A now** (Belt removed) | — | 2026-07-03: Maximum Belt gone; the new ACE SPEC (Unfair Stamp) is an **Item**, not a Tool, so these ATTACH-keyed rules don't fire. Air Balloon is a plain retreat tool (not `aceSpec`) → general retreat handling |
| `hold-clutch-heal` / `dont-waste-clutch-heal` | **covers-as-is (key, NEW)** | — | 2026-07-03: **Wally's Compassion** (`clutch_heal`) — `baseline_heal.py` is built around this card: hold until `active_doomed` & not `active_can_ko` (+60), penalize when not doomed (−40). No deck rule |
| damage-boost model (`_boost_lethal_tactical`) | **covers-as-is (Black Belt's)** | — | 2026-07-03: **Black Belt's Training** `damageBoost=40, damageBoostVsEx=True` parsed + consumed (a KO-crossing PLAY goes KO_SCORE-class). Replaces Maximum Belt's breakpoint role (now a Supporter — costs the slot) |
| `keep-key-cards-at-discard` (ACE SPEC arm) | **covers-as-is** | — | 2026-07-03: now protects **Unfair Stamp** (`aceSpec`) from Ultra Ball's discard-2 (was Maximum Belt) |
| `disrupt-the-hand-size-attacker` (`hand_disruption`) | covers-as-is | — | Judge + **Unfair Stamp** both carry `hand_disruption` |
| general search (`dig-before-commit` at TO_HAND) | covers-as-is (+ watch) | — | **Team Rocket's Petrel** (`search`, Trainer tutor) — general search handles the PLAY + the fetch pick; the 1-of "which Trainer" value is Tactical, no deck rule (§8 ladder-watch) |
| `gust-for-the-ko` / `gust-for-the-stall` | covers-as-is | — | **Boss's Orders (id 1182, `gust` tag, Supporter cardType)** — the shipped doctrine fires on it. **Heave-Ho** is the relaxed deck variant (§6) |
| **`build-active-wincon`** | **covers-as-is (key)** | — | keeps attaching to the Active Mega until its **biggest** attack (Mega Brave, `maxDamageCost`=2) is online → **builds the Mega toward FF** without a deck rule. Matches `setup_energy_target=2` |
| **`attach-before-hand-shuffle`** (−60) | **covers-as-is (key)** | — | attach your F **before** Lillie's/Judge (a `shuffle_hand` would pitch held energy). **Live**: Lillie's (1227), Judge (1213) **and** Unfair Stamp (1080) all now carry `shuffle_hand` in card_functions.json (2026-07-15 align) — the guard sees every hand-shuffle Supporter/Item |
| **`keep-key-cards-at-discard`** (−30) | **covers-as-is** | — | at Ultra Ball's discard-2, won't pitch the **wincon**; spare F (not `discard_eot`, not wincon) is freely pitched as Aura Jab fuel — exactly our discard priority |
| `play-energy-denial` | N/A | — | no `energy_denial` card (no Crushing Hammer) |
| `deploy-hp-tool-on-breakpoint` | N/A | — | no +HP tools (Air Balloon is retreat-only; Belt removed) |
| `dont-waste-discard-energy`, `prefer-rush-evolve-tutor`/`dont-rush-evolve-without-target`, `prefer-bench-fill-first`, `snipe-*`/`snipe-the-strongest-evolving-threat` | N/A | — | no `discard_eot`/`rush_evolve`/`bench_fill` cards; **no attack damages the opp Bench** (snipe rules never fire — our gust drags bench→active, then we hit the Active). *(`clutch_heal` moved OUT of this N/A list 2026-07-03 — Wally's Compassion now covers it.)* |

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
| Tool rules | covers-as-is (doctrine_tool, ADR-0028) | `deploy-hp-tool` is +HP-only → inert for Air Balloon (no `hpBonus`). **2026-07-03: Maximum Belt removed** — no ACE SPEC Tool now, so `protect-ace-spec-tool` is inert (the new ACE SPEC, Unfair Stamp, is an Item); Air Balloon is a plain retreat tool. Belt's +damage role → Black Belt's Training via the damage-boost model |
| main.py wiring | **owned by runtime (ADR-0055)** | — | `main.py` is now the 5-line shell `make_agent(STRATEGY)`; `common.runtime` PROFILE is the single source of the deployment profile / knowledge seams (attack_stats, effects, Scout+artifact, briefs, posture, `OwnCardModel`+`own_prizes`) / kill-switches, each resolved as `params.get(flag, PROFILE[flag])` — no per-deck enumeration, and omitting a seam is structurally impossible (pinned both ways by a test) |

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

### Deferred to existing General-Strategy work *(Phase-A drafts — ALL BUILT in §9 T8'/T9'; cards updated 2026-07-03)*
- **Damage-boost OHKO-line model** (Premium Power Pro stacking + ex-breakpoints) — **BUILT** (T8').
  The +vs-ex boost now comes from **Black Belt's Training +40** (Maximum Belt removed): 270+40=310,
  +Power Pro=340 Dragapult.
- **Stadium matchup choice** — **BUILT** (T8') as `gravity-mountain-vs-stage2` (read `opp_has_stage2`),
  then **REPLACED BY COMPUTATION** (Issue #424, 2026-08-06): the rung is retired and
  `_boost_lethal_tactical` prices the crossing itself.
  *(Watchtower cut 2026-07-03 → the Watchtower/Meowth-sequencing half is retired; Gravity Mountain is
  now the sole Stadium.)*

## 7 · Roles, Lines, params (pre-code)

```python
# ids verified against the engine (2026-06-29; trainer-swap ids added 2026-07-03)
RIOLU, MEGA_LUCARIO_EX = 677, 678
SOLROCK, LUNATONE, MAKUHITA, HARIYAMA, MEOWTH_EX = 676, 675, 673, 674, 1071
BOSS_ORDERS, AIR_BALLOON, GRAVITY_MOUNTAIN = 1182, 1174, 1252
# NEW 2026-07-03: UNFAIR_STAMP=1080, BLACK_BELTS=1211, PETREL=1219, WALLYS=1229 (all covers-as-is,
# no deck rule → no const needed in strategy.py). REMOVED: MAX_BELT=1158, WATCHTOWER=1256.

roles = Roles({
    MEGA_LUCARIO_EX: ["win_condition", "primary_attacker", "accel_source"],
    SOLROCK:         ["secondary_attacker", "engine"], # early attacker + Lunar Cycle enabler
    LUNATONE:        ["engine"],                        # the native draw engine (Lunar Cycle)
    HARIYAMA:        ["secondary_attacker", "gust"],   # Heave-Ho + Wild Press
    MEOWTH_EX:       ["tutor"],                         # situational Supporter fetch
    BOSS_ORDERS:     ["gust"],
    AIR_BALLOON:     ["retreat_tool"],
    # Black Belt's / Wally's / Petrel / Unfair Stamp: NO Role — all covered by tag/CardStat-keyed
    # general rules (damage-boost model / clutch_heal doctrine / search / aceSpec guards).
}, evolves={RIOLU: MEGA_LUCARIO_EX, MAKUHITA: HARIYAMA})
# The terminal Roles distinguish the win-condition and secondary-attacker paths. Online
# (SETUP→RACE) at the engine default = 1 F (Aura Jab) — correct; no readiness override.
params = { "setup_energy_target": 2, "search_budget": 0 }   # 2 = FF for the first Mega Brave
```

> **ADR-0079 migration (2026-07-28).** The Set-Up ACTIVE seam is now ONE deck declaration —
> `Strategy.starter_priority` in this deck's `strategy.py`, read by the general
> `open-the-declared-starter`. Rows above naming `open-the-accelerator`,
> `open-the-item-lock-starter`, `dont-open-multiprize-active`, `dont-open-with-the-engine`,
> `start-solrock-over-lunatone` or the `starter` Role are **history** — all are deleted. See
> [ADR-0079](../../../docs/adr/0079-the-setup-active-pick-is-one-deck-declaration.md).

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
  (`opp_has_stage2` — no Read/Posture dependency) + the deck rule `gravity-mountain-vs-stage2`.
  *(2026-08-06, Issue #424: the rung is RETIRED and the crossing COMPUTED; the current-Stadium
  visibility that "remains unread" here is now read — `_stadium_hp_shift` differences against the
  in-play Stadium, because playing one ends the other, `docs/rulebook.txt` L136.)*
  *(2026-07-03: Watchtower cut, so
  `watchtower-vs-colorless-abilities` is RETIRED; `opp_has_colorless_ability` stays as general infra,
  now unused by this deck.)*
- ~~**Meowth ex "bench for a needed Supporter" override**~~ — **RESOLVED (2026-07-03 grill).** Was
  worse than deferred: the `tutor` Role actively MISFIRED (`play-a-tutor-for-the-unfound-wincon` benched
  the 2-prize ex in setup as a "wincon dig"). Re-modeled GENERAL: `supporter_tutor` tag + the
  `bench-the-supporter-tutor` SETUP rule (no-Supporter-in-hand) + a context-ranked grab + a Tuck-Tail
  escape. Since Meowth splashes into many decks, this is a system-wide fix, not a deck patch. See §9 T9'.

### Trainer-swap open items (2026-07-03)
- ~~**`shuffle_hand` tag on Unfair Stamp (1080).**~~ **RESOLVED — the note was stale.** Unfair Stamp's
  `card_functions.json` entry *is* `["draw","hand_disruption","shuffle_hand"]`, so
  `hold-wincon-dont-shuffle` has always seen it. (Verified 2026-07-14 during the ADR-0060 audit, which
  found the *real* Unfair Stamp gap elsewhere: it was missing from `_DRAW_COUNTS`, so
  `dont-refresh-into-a-probable-miss` could never fire on it. That dict is now deleted and the card
  facts live once, in `strategy/refresh.py` — Unfair Stamp draws **5 to their 2**, the only
  asymmetric-favourable refresh we run, and an *Item*, so it doesn't even spend the Supporter.)
- **Petrel "which Trainer to fetch" (ladder-watch, not a rule).** A 1-of Trainer tutor; the value pick
  (Boss's for lethal / Unfair Stamp / Black Belt's for a breakpoint / a Stadium) is left to general
  search + Tactical board value. A deck fetch-priority rule would hard-code card ids for a single 1-of
  — not justified now. Revisit only if the ladder surfaces Petrel misplays.

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
    *(Historical, as authored. Both DECK rules are now RETIRED — Watchtower's with its card in
    2026-07-03, Gravity Mountain's by Issue #424, which also closed the bump-timing gap.
    `opp_has_stage2` survives as general Board infra with no reader in this deck, exactly as
    `opp_has_colorless_ability` does.)*
  - **Lunar Cycle (DECK):** direct MAIN policy retired by Issue #469. The clause-driven composer now
    prices its Solrock gate, Basic {F} discard, draw Worth, and once-per-card Ability allowance.
- **T9' (trainer-swap re-run): ✅ DONE 2026-07-03 — mostly DELETIONS + covers-as-is.** deck.txt trainer
  package edited (Pokémon core unchanged). The general layer (grown since Phase A) already covers all
  four new cards, so **no new deck Hypotheses were authored**:
  - **Removed cards → deleted deck rules:** `watchtower-vs-colorless-abilities` RETIRED (Team Rocket's
    Watchtower cut); Maximum Belt removed (its `damage_tool` Role + const dropped — its breakpoint role
    is re-sourced to Black Belt's Training via the general damage-boost model).
  - **Black Belt's Training (1211):** covers-as-is — `CardStat.damageBoost=40, damageBoostVsEx=True`
    already parsed + consumed by `_boost_lethal_tactical` (the T8' model). Now a Supporter (slot cost).
  - **Wally's Compassion (1229):** covers-as-is — `clutch_heal` tag → `baseline_heal.py`
    (`hold-clutch-heal` +60 / `dont-waste-clutch-heal` −40), the doctrine literally built around it.
  - **Unfair Stamp (1080):** covers-as-is — `aceSpec` guarded at discard (`keep-key-cards-at-discard`),
    `hand_disruption` read by `disrupt-the-hand-size-attacker`, engine-gated legality. `shuffle_hand` tag
    now present (2026-07-15 align) — `hold-wincon-dont-shuffle` sees it.
  - **Team Rocket's Petrel (1219):** covers-as-is — general search at the TO_HAND select; the 1-of
    "which Trainer" pick left to Tactical (ladder-watch, §8). *(User sign-off 2026-07-03.)*
  - **Unfair Stamp `shuffle_hand` tag:** ✅ DONE (2026-07-15 align) — card_functions.json (1080) now carries
    `shuffle_hand`, so `hold-wincon-dont-shuffle` sees it. *(Verified: 1080 = ['draw','hand_disruption','shuffle_hand'].)*
  - **Meowth ex RE-MODEL (GENERAL — grilled 2026-07-03; "get it right, it's splashable").** The `tutor`
    Role misfired (see §3 Meowth). Build:
    1. **card_functions.json (1071):** `['search','stall']` → `['search','supporter_tutor']` (drop inert
       `stall`, add the new tag).
    2. **GENERAL `bench-the-supporter-tutor`:** `plan==SETUP and PLAY and 'supporter_tutor' in tags and
       no Supporter in hand` (SETUP = the safety proxy). Needs a **`Board.no_supporter_in_hand`** (or
       `hand_has_supporter`) signal — verify/build.
    3. **GENERAL context-ranked grab** at Last-Ditch's TO_HAND Supporter select — **BUILT (2 rungs):**
       `grab-a-gust-supporter-for-the-ko` (+20, a `gust` candidate when `gust_best_ko_prizes>0`) and
       `grab-a-draw-supporter-in-setup` (+10, the SETUP dig default). Wally's-when-doomed rung deferred
       (rare; general fetch + the heal doctrine cover it) — a documented follow-up, not shipped.
    4. **Tuck Tail escape — BUILT GENERAL as a Tactical credit** (not a Hypothesis): `AttackStat.selfReturn`
       (parses "Put this Pokémon … into your hand") + `_SELF_RETURN_ESCAPE` (50/prize) in the NON-KO
       branch of `_tactical`, gated on `active_doomed` + ex/megaEx Active. Mirror of `_RECOIL_DOOM`; a
       real KO always wins. Parser pool-unit-tested (self vs opponent/energy/plain).
    5. **Select-shape validation:** authored the bench (PLAY), grab (TO_HAND) and Tuck Tail (ATTACK)
       against the standard engine option shapes (no non-obvious ACTIVATE like Heave-Ho's — benching a
       Basic and a deck-search are the well-known shapes the trigger-test helpers already model), with
       **`check_agent` real self-matches as the shape safety-net** (a wrong shape surfaces as a
       crash/illegal move). A dedicated T6'-style probe was not needed here.
  - **strategy.py delta:** drop `MAX_BELT`/`WATCHTOWER` consts + the `MAX_BELT` Role + the
    `watchtower-vs-colorless-abilities` Hypothesis; **remove the `MEOWTH_EX: ["tutor"]` Role** (the tag
    now drives it); `GRAVITY_MOUNTAIN` const already present; docstring refresh. **Trigger-test delta:**
    remove the Watchtower test; re-point the boost tests from Maximum Belt (+50) to Black Belt's Training
    (+40); add Meowth `bench-the-supporter-tutor` / grab / Tuck-Tail trigger tests. Gates: trigger tests
    green, `pytest tests/ -q` green, `check_agent.py` playable. `aligned.json` refreshed.
- **Still deferred:** planner multi-turn (AJ-now + MB-next 400 lookahead); Meowth
  "needed-Supporter" override; current-Stadium visibility (bump timing); conditional boosts
  (Kieran's mode); non-lethal breakpoint boost timing (playing Power Pro toward a 2-turn plan).

Status stays `assumed`/`testing` (the ladder A/B promotes to confirmed/refuted). The human commits each diff.
