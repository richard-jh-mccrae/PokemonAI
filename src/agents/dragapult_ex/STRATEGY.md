# dragapult_ex — Playing Doctrine

> Phase-A deliverable of `/deck-genie`. The human-readable strategy the deck plays; the executable
> `strategy.py` is authored from this by `/update-strategy` **after sign-off** (ADR-0017 / ADR-0046).
> Build on the [General Strategy](../../../docs/general-strategy.md): reuse, override, or extend — don't restate.

**Status:** `aligned 2026-07-15` (all 2026-07-09 proposals shipped into common — see §6 banner) · was `locked — proposals queued` (deck swapped to the standard meta list — Cinderace OUT; Budew +
Dunsparce/Dudunsparce + Rosa's Encouragement IN) · **Signed off:** 2026-07-09 (start SECOND) · **Author:** deck-genie
+ Richard · **Supersedes** the 2026-07-03 Cinderace build (full re-author). Phase 6 done: 4 general proposals in
`data/strategy/proposals/applied/deck-genie-20260709-dragapult_ex.md` for `/update-strategy`; `preferred_start="second"` +
Cinderace/Judge dead-ref cleanup applied to `strategy.py` (all gates green — 25 agent tests + check_agent 4/4).

> **Update 2026-07-15 (deck-align):** **1× Judge re-added** (SVI 176, `shuffle_hand` Supporter — "each player
> shuffles their hand into their deck and draws 4") in a **1-for-1 swap for a Psychic energy**. Energy is now
> **3F / 3P / 2D (8 Basic)**; Trainers 34. Judge is **covered as-is** by the general Shuffle-Refresh doctrine
> (`shuffle_hand` tag — the same coverage Lillie's and Unfair Stamp ride), so **no new rule and no `strategy.py`
> logic change**; deck.csv/deck.txt regenerated. **Rosa's stays** — Judge and Rosa's now coexist (proactive
> hand disruption returns alongside the comeback accel). The "Judge removed" notes below are superseded by this.

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped (new list; `deck.csv` rebuilt via `deck_convert.py`, all 60 resolved)
- [x] Phase 1 overview confirmed (spread + disruption CONTROL; Cinderace accel engine removed)
- [x] Phase 2 research synthesised (high confidence; 46/55 claims verified; **0 card-fact conflicts**)
- [x] Phase 3 card-by-card: 23/23 cards locked
- [x] Phase 4 General-Strategy disposition complete
- [x] Dispositions adversarially verified vs real code + engine-free probes (workflow `wjzvrtwbk` + `probe_ability.py`): 5 gaps CONFIRMED, rest covered-as-is
- [x] Phase 5 sign-off (2026-07-09 — **start SECOND**, guru-unanimous vs the "setup-heavy → first" steelman, workflow `wh8ls1w6m`)
- [x] Phase 6 done: **4 general proposals emitted** → `data/strategy/proposals/applied/deck-genie-20260709-dragapult_ex.md`: (1) `use-the-draw-engine-ability`, (2) `open-the-item-lock-starter` + `item_lock` tag on Budew, (3) `energy_accel` tag on Rosa's, (4) `dont-strand-the-evolving-engine`. **Applied directly** (user-requested hygiene): `preferred_start="second"` + Cinderace/Judge dead-ref cleanup in `strategy.py` — 25 agent tests + check_agent 4/4 green.
- [x] **All 4 proposals SHIPPED into common** (deck-align 2026-07-15): verified live in `baseline_opening.py` / `baseline_sequencing.py` / `doctrine_fetch.py` + tags in `card_functions.json`. Deck covers-as-is; tuned.json 14/14 keys live; no folds available (3 deck hypotheses stay deck-bound).

**What changed vs the 2026-07-03 build (the delta this re-author covers):**

| Out | In | Consequence |
|---|---|---|
| **4 Cinderace** (Explosiveness opener + Turbo Flare bench-accel) | — | **No acceleration engine.** Energy = manual attach (1/turn) + **Crispin** + **Rosa's** (comeback). Dragapult only needs 2 (FP), so it arms by evolving over energy pre-loaded on Dreepy/Drakloak. Leaner, standard, slightly slower first Phantom Dive. `open-the-accelerator` / `develop-the-accel-recipient` / `dont-fetch-the-setup-only-opener` all go **inert** (no accel opener). |
| **2 Judge** | **1 Rosa's Encouragement** | Less proactive hand disruption; a comeback accel added. *(1 Judge re-added 2026-07-15 — see Update at top; Judge + Rosa's now coexist.)* |
| — | **1 Budew** | `Itchy Pollen` (FREE attack, 10 dmg): opp can't play **Items** next turn. Item-lock **opener**. It is an *attack* (turn-ender) → needs Budew Active; first player can't attack T1 → fires my T2 going first / my T1 going **second**. |
| — | **1 Dunsparce + 1 Dudunsparce** | `Run Away Draw`: draw 3, shuffle Dudunsparce (+attached) back into deck → a **re-usable** consistency engine (fetch base → evolve → draw → self-recycle). |
| 4F/3P/2D | **3F / 4P / 2D** → **3F/3P/2D** | Psychic-primary (no Turbo-Flare Fire engine to feed); **2026-07-15: −1 P for Judge → even 3F/3P.** |
| Crushing Hammer 3, Night Stretcher 2 | **4 / 3** | More energy denial + more recursion (feeds Rosa's discard fuel + line rebuild). |
| `preferred_start="first"` | **`"second"`** | Budew item-lock fires T1 only going second (first player can't attack T1). Flipped. |

**Carries over UNCHANGED** (still-present cards → the 2026-07-03 structural infra + deck rules still fire):
Phantom Dive spread valuation + placement (**infra A**), Cruel Arrow any-target (**B**), Munkidori
Adrena-Brain handler (**C**), Stadium `Board` signal (**D**), and the 3 deck Hypotheses
(`bench-the-comeback-drawer`, `hold-evolution-until-attacker-ready`, `play-risky-ruins-when-net-positive`).
No re-build of those; only the new-card gaps below.

## 1 · Overview

- **Archetype:** Dragapult ex **spread + disruption** — a **chip-then-cash CONTROL** deck, *not* a race
  deck (research consensus). Map prizes, don't just hit big.
- **Win condition — UNCHANGED.** Phantom Dive (`FP`) = 200 to the Active **+ 6 damage counters placed
  anywhere on the opponent's Bench** — it **pre-loads** benched mons with softening chip you cash into
  prizes on LATER turns via **Munkidori** (move ≤3 counters ours→theirs, needs {D}), **Fezandipiti**
  Cruel Arrow (flat 100 to any bench mon, no W/R), and **Boss's Orders** (gust the softened body Active
  to finish). Prize math: Dragapult / Fezandipiti / Meowth ex are 2-prize; the rest 1-prize. Dragapult's
  320 HP + Tera bench-immunity + no weakness keep our prizes off the table.
- **Line:** **Dreepy → Drakloak → Dragapult ex** (Stage 2, single family). **Online at:** `Ready(energy=2)`
  = FP for Phantom Dive (NOT the engine's cheapest-attack default, `C` Jet Headbutt 70 — that's a fallback poke).
- **Tempo shape — SLOW to arm, hard to punish once online.** No Turbo Flare: energy is **manual attach +
  Crispin** (any board) **+ Rosa's** (comeback only). Budew's free item-lock **buys the setup turns**;
  Crushing Hammer / Unfair Stamp / Risky Ruins tax the opponent's tempo the whole time. **Deliberately
  falling behind on prizes is fine — it turns ON Rosa's Encouragement.**
- **Main attacker:** Dragapult ex. **Finishers/tech attackers:** Fezandipiti ex (Cruel Arrow), Munkidori
  (Mind Bend pinch swing; its *ability* is the real value).
- **Openers / engines:** **Budew** (item-lock starter), **Dunsparce → Dudunsparce** (Run Away Draw),
  **Drakloak** Recon Directive (mid-line dig), **Meowth ex** (one-shot Supporter tutor).
- **Draw/search:** Lillie's Determination (draw 6/8), Dudunsparce Run Away Draw (draw 3, self-recycle),
  Drakloak Recon (dig 2 pick 1), Fezandipiti Flip-the-Script (draw 3 after a KO), Poké Pad (non-Rule-Box
  Pokémon), Ultra Ball (any Pokémon, discard 2), Buddy-Buddy Poffin (≤70 HP Basics → **Dreepy / Budew / Dunsparce**).
- **Acceleration:** Crispin (2 basic diff types, attach 1 / hand 1) — the **un-gated** accel; Rosa's (2 basic
  from **discard** → Stage 2 = Dragapult ex, **only when behind**). **Disruption:** Budew item-lock, Crushing
  Hammer (coin energy denial), Unfair Stamp (KO-gated hand strip), Boss's (gust), Risky Ruins (bench chip),
  Munkidori Mind Bend (Confuse). **Recovery:** Night Stretcher (Pokémon or Basic Energy from discard).
- **Energy:** 8 Basic — **3 Fire, 3 Psychic, 2 Darkness.** F+P power Phantom Dive; the 2 {D} gate Munkidori
  Adrena-Brain (+ Fezandipiti). Very low count — Crispin/Rosa's/Night Stretcher do the fixing.
- **Validation:** the list is tournament-proven — a near-exact match to Limitless **28250** (Newdorf, 3rd NAIC
  2026); the Prague winner **26243** (Laszkiewicz) is a leaner Dudunsparce-ex variant that cuts our
  Fezandipiti/Meowth/Rosa's/Crushing Hammer/Unfair Stamp — **treat ours as the aggressive-control variant.**

## 2 · Research synthesis (cited)

_High confidence · 9 angles · 28 sources · **46/55 claims survived adversarial verification** · 9 card
deep-dives · 11 trainers. **Web-vs-engine card-fact conflicts: NONE.** Raw: `tasks/wqa1xzek7.output`._
_Caveat the whole synthesis carries: most web coverage is of DIFFERENT Dragapult shells (Arven / Lance /
Dusknoir / Rare Candy / Iono / Counter Catcher / Neo Upper Energy / Dudunsparce **ex**) — **none of those
cards are in this 60.** Companion combos are filtered to this exact list; treat generic archetype advice as
directional._

**Gameplan — chip-then-cash CONTROL (not a race).** Distribute board-wide chip over several turns via
Phantom Dive's spread, then convert multiple KOs. Budew buys setup turns; the disruption package taxes tempo;
Dragapult (320 HP, no weakness) is hard to punish once online. **Do NOT rush single KOs — set up FUTURE
multi-KO turns.**

**Key combos:**
- **Phantom Dive → Munkidori (needs {D}) → Boss's Orders** — the central prize-cashing engine: spread 6
  counters, move ≤3 more onto ONE softened target to push it into KO range, gust it Active to take the prize.
- **Risky Ruins → Munkidori self-launder** — Risky Ruins chips OUR own non-{D} Basics on bench-entry;
  Munkidori relays that self-chip onto the opponent (Munkidori is {D} → exempt). Turns our tax into KO pressure.
- **Fezandipiti Cruel Arrow** (100 to any, ignores bench W/R) stacked on prior spread = a bench KO Boss's can't drag.
- **Unfair Stamp + Fezandipiti Flip the Script** — SAME KO trigger (a KO of *our* Pokémon last turn): strip
  their hand to 2 (Item, no Supporter cost) AND draw 3, the turn our body dies.
- **Budew item-lock + manual-attach runway** — each locked turn you hand-attach toward FP; Dragapult arms
  before the opponent recovers.
- **Lillie's + Dudunsparce Run Away Draw** — draw off a Supporter AND an Ability the same turn; Dudunsparce
  then self-shuffles to free its bench slot and be re-fetched.
- **Rosa's re-arm** — after a Dragapult is KO'd (you now trail → gate live), evolve a fresh Dragapult and pull
  2 basics (F+P) from discard in ONE Supporter = full Phantom Dive cost re-assembled, skipping two attach turns.
- **Meowth ex → the exact Supporter** — bench Meowth to tutor Boss's (gust KO) or Rosa's (the turn its gate flips).

**Sequencing ladder (developing turn):** free draw/dig FIRST (**Drakloak Recon** + **Dudunsparce Run Away
Draw** — *before* committing, so the drawn cards inform attaches / Ultra Ball pitches / which Supporter) →
Items (**Poffin → Poké Pad → Ultra Ball** → Night Stretcher / Crushing Hammer) → the one **Supporter** →
evolve/attach → **attack LAST** (Phantom Dive / Itchy Pollen). Carve-outs: **Recon before evolving Drakloak**
(ability gone after); **hold the Drakloak→Dragapult evolve until the body has 2 FP** (keep Recon-digging;
evolve early only if the Drakloak is in KO range); **never attach Energy/Tool to Dudunsparce before drawing**
(Run Away Draw shuffles attachments away); **Munkidori Adrena-Brain BEFORE the attack and BEFORE Boss's**
(read the board, then place spread / drag the corpse); **bench our vulnerable Basics BEFORE Risky Ruins**;
**bench Meowth BEFORE the tutored Supporter**; **soften BEFORE the snipe**; **Crushing Hammer after draw/dig,
before Boss's**; **Unfair Stamp near-last** (it shuffles your own hand).

**Opening lines (prefer going SECOND):**
- **Ideal (second):** Budew Active (retreat 0) → Poffin 2 Dreepy → Poké Pad/Ultra Ball for pieces → **Itchy
  Pollen** locks the opponent's T2 Items. Free-retreat Budew into the line later.
- **Going first:** you can't lock T1 (no attack) — bench Budew, just develop; the lock is delayed to T2.
- **Draw engine:** bench Dunsparce (Poffin/Poké-Pad target) when bench room allows → evolve → Run Away Draw.
- **Lillie's rocket:** at exactly 6 prizes Lillie's draws **8** — heaviest use T1–T2 to assemble the line.

**Matchups (competitive-reasoning level, ladder-validate):**
- **Item-reliant / turbo / search-heavy = FAVORABLE** — Budew disproportionately hurts them; you trade nothing.
- **Gardevoir = hard** — out-tempos the slow manual-attach setup; protect the fragile 70-HP Dreepy; note the
  ENEMY counter-mover (Munkidori/Cresselia) can relay our own Phantom Dive damage BACK onto our line.
- **Roaring Moon / aggro = hard** — races the Stage-2 line; lean on Budew + Crushing Hammer + Boss's to buy time.
  **Budew is weak to Fire** → Fire aggro is the counter to the Budew plan.
- **Mirror** — **Munkidori is the best card**: HEALS our line (peel counters off 90-HP Drakloaks) AND finishes theirs.
- **Item-lock is ITEMS ONLY** — does not stop Supporter draw/search, Energy, Tools, or Stadiums. Don't over-value Budew vs Supporter-driven setup.

**Tech reasoning (why these counts):** Crushing Hammer ×4 = an aggressive-disruption commitment (a split tech,
~62% of lists; lower its priority once behind on the KO race). 1-1 Dunsparce/Dudunsparce is CORRECT (Run Away
Draw self-recycles → one copy services many turns). **NON-ex Dudunsparce only** — no attacker role, no
Enriching-Energy combo (those are the Dudunsparce-**ex** shell, not ours). Unfair Stamp is the ACE SPEC (vs Neo
Upper Energy in energy-accel builds) — this manual-attach build chose the disruption ACE SPEC. Crispin ×3
solves the FP two-type requirement out of 9 energy.

**Sources:** Going Second (Spenser Gow); PokeBeach (Budew's World 2025/04; Dragapult rotation 2025/02; BDIF
318766; 319761); Cardsrealm (Dragapult/Dudunsparce deck tech); JustInBasil (Draw / Consistency); Limitless
(decklists 26243 / 28250; cards POR/84 Rosa's, SFA/38 Fezandipiti, TEF/129 Dudunsparce, MEG/127 Risky Ruins);
PokemonCard.io (tier list); Pokemon.com (Budew / Dragapult strategy); Ultimate Guard (Budew; Dragapult meta);
TCGplayer (June 2025 guide); Wargamer (Meowth ex); Bulbapedia / SNKRDUNK (Unfair Stamp).

## 3 · Card-by-card

Every block opens with the **engine profile** (dump = ground truth) then the researched usage. **NEW / changed
cards are grilled in full;** unchanged cards carry the 2026-07-03 lock (condensed) since their code coverage is
intact.

### NEW — 1× Budew (235) — Role: `starter` (item-lock opener) · tags: **`item_lock` (SHIPPED)** · LOCKED
- **Mechanics:** Basic **Grass**, 30 HP, 1-prize, **weakness Fire**, retreat **0**. `—` **Itchy Pollen** (10,
  **no energy cost**): "During your opponent's next turn, they can't play any **Item** cards from their hand."
  It is an **attack** (turn-ender), NOT an ability.
- **Use:** the turn-1 free **item-lock opener**. Open Budew Active (prefer going **second** so Itchy Pollen fires
  your first turn, locking the opponent's turn-2 Items — Poffin / Ball / accel / Switch). Off-type Grass purely
  because it's the format's best free item-lock body. Retreat 0 → pivot into the Dragapult line once the lock has
  bought tempo. Blocks **Items only** (not Supporters/Tools/Energy/Stadiums).
- **Sequencing:** as the Active, develop the whole board first (Poffin/Poké-Pad/attach) then Itchy Pollen LAST
  (attack-last). The lock recurs each turn Budew survives + stays Active.
- **Anti-patterns:** don't expect a T1 lock going **first** (can't attack — bench Budew, develop). Don't over-value
  it vs Supporter-driven decks. Beware **Fire** (30 HP dies to any Fire hit) — Fire aggro counters the plan.
- **General-Strategy disposition:** **GAP.** At `SETUP_ACTIVE`, nothing prefers an item-lock Basic
  (`open-the-accelerator` keys on the `accel_source` Role — Budew has none; among Dreepy/Budew/Dunsparce, all
  1-prize Basics score ~0, so the pick is arbitrary/index-order — Budew may never take the Active and Itchy Pollen
  never fires). → **new GENERAL rule `open-the-item-lock-starter`** (§6) + a new **`item_lock` Function Tag** on
  Budew. `keep-a-startable-hand` already keeps it (a Basic). `dont-open-multiprize-active` N/A (1-prize).

### NEW — 1× Dunsparce (305) — Role: draw-engine base · tags: **none** · LOCKED
- **Mechanics:** Basic **Colorless**, 70 HP, 1-prize, weakness Fighting, retreat 1. `C` **Trading Places** (0):
  switch this with 1 of your Benched Pokémon (free pivot). `CC` **Ram** (20). Evolves into **Dudunsparce**.
  Poffin / Poké Pad target (≤70, non-Rule-Box).
- **Use:** its job is to **become Dudunsparce** (the Run Away Draw engine). Bench it when bench room allows, evolve
  next turn. Trading Places is a niche free pivot (rarely relevant). Do NOT evolve it just to attack with Land Crush.
- **Anti-patterns:** don't strand it Active as a chump when the line needs the slot; don't spend Ram as a plan.
- **General-Strategy disposition:** **mostly covers-as-is** (fetchable as a ≤70 Basic via Poffin / as any Basic
  via `fetch-a-starter`; a benched Basic). **Minor gap flagged (§6):** Dunsparce is *not* `card_is_support` (no
  engine ability), so the fetch doctrine doesn't prioritise it as the **engine precursor**; and its evolution
  Dudunsparce **is** `card_is_support` but is Stage-1-unplayable → a mild stranded-in-hand risk (Ultra-Ball a
  Dudunsparce you can't yet play). Low priority — see §6 · `dont-strand-the-evolving-engine`.

### NEW — 1× Dudunsparce (66) — Role: draw engine (ability) · tags: `draw`, `stall` · LOCKED
- **Mechanics:** **Stage 1** Colorless, 140 HP, 1-prize, weakness Fighting, retreat **3**, evolves from Dunsparce.
  Ability **Run Away Draw** (once/turn): "draw 3 cards. If you drew any cards in this way, **shuffle this Pokémon
  and all attached cards into your deck.**" `CCC` **Land Crush** (90).
- **Use:** a **recurring, penalty-free draw-3 engine** — the ability, never the body. Fire it **early in the turn,
  BEFORE committing** other resources so the 3 cards inform the turn. It **self-recycles** (shuffles itself + all
  attached back), so one copy services many turns and it clears its own bench slot; re-fetch (Poffin the Dunsparce)
  when you want it again. **NEVER attach Energy/Tool to it before drawing** (attachments shuffle into the deck,
  wasted). **Never pay its retreat 3** — it works from the bench.
- **Anti-patterns:** don't evolve/hold it as an attacker (Land Crush is not a plan); don't fire it when the shuffle
  would bury a card you need next turn (rare — it shuffles only itself + its own attachments).
- **General-Strategy disposition:** the **fetch** side is covered (`fetch-the-support` sees Dudunsparce as a `draw`
  engine; Drakloak also fills `support_in_play`). The **activation** side is the open question — a pure `draw`
  `_ABILITY` (option-type 10) has **no combat value** and `dig-before-commit` keys on `_PLAY` (7), so it may score
  0 → drop to `_finish_turn_last`'s LAST tier and be **skipped before the turn-ending attack**. **This is load-bearing
  (Run Away Draw AND Drakloak Recon share the mechanism) → being verified empirically** (workflow `wjzvrtwbk`);
  if confirmed, a new GENERAL `use-the-draw-engine-ability` rule (§6) fixes both. *(Munkidori's Adrena-Brain
  auto-activates only because its counter-move earns tactical value — pure draw/dig abilities don't.)*

### NEW — 1× Rosa's Encouragement (1240) — Role: comeback accel (tech) · tags: **`energy_accel` (SHIPPED)** · LOCKED
- **Mechanics:** **Supporter.** "You can use this card only if you have **more Prize cards remaining than your
  opponent** [= you are BEHIND]. Attach up to 2 Basic Energy cards from your **discard pile** to 1 of your **Stage
  2** Pokémon." (The only Stage 2 here = **Dragapult ex**.)
- **Use:** the **comeback-only** discard-recursion accel — the fast way to **re-arm a KO'd Dragapult**: evolve a
  fresh one, pull 2 basics (F+P) from discard in one Supporter, skip two manual-attach turns. Needs basics already
  in discard (Ultra Ball's discard-2 and normal trades feed it). **Dead when even/ahead** — insurance, not the
  primary energy plan. Meowth ex tutors it exactly the turn the prize gate flips on. Lowest Supporter priority
  (below Boss's / Crispin / Lillie's).
- **Anti-patterns:** don't plan around it while even/ahead (engine won't even offer it); don't pitch ALL your
  Fire/Psychic to "fuel" it (Phantom Dive gate — keep a working F+P base; Night Stretcher recovers).
- **General-Strategy disposition:** **covers-as-is ONCE TAGGED.** Untagged today → `use-acceleration`
  (`energy_accel` tag) can't fire. → propose the **`energy_accel` tag** on Rosa's (§6); then `use-acceleration`
  (+25) endorses playing it, engine-gated to "behind", target-gated to Stage 2 — no deck rule needed. Do **NOT**
  give it the `accel_source` **Role** (that would wrongly boost it at SETUP via `advance-the-accel-pieces`; Rosa's
  is comeback-only, not a setup accel). The discard-as-fuel nuance is left to the general discard keep-value.

### 3× Dragapult ex (121) — Role: `win_condition`, `primary_attacker` · tags: `spread` · LOCKED (unchanged)
- **Mechanics:** Stage 2 Dragon, 320 HP, 2-prize, **Tera**, **no weakness**, retreat 1. `C` Jet Headbutt (70).
  `FP` **Phantom Dive** (200 + **6 damage counters on the opp Bench, any way you like**).
- **Readiness:** `Ready(energy=2)` (FP) — stay in SETUP digging until FP is affordable; Jet Headbutt is a fallback poke only.
- **Phantom Dive placement (the deck's core decision):** cross-turn truth — Phantom Dive is the **turn-ender**, so
  Munkidori/Boss's/Cruel Arrow resolve BEFORE it and convert **prior-turn** chip. This turn's spread pays off THIS
  turn only by a DIRECT bench KO. **(1) take every direct bench KO first** (greedy knapsack within the 6 counters);
  **(2) else marginal-value** — concentrate on the single most-convertible threat (a board proxy: spread when the
  opp has ≥2 benched threats, else concentrate). **Bench safety (Tera):** a benched Dragapult takes no attack
  damage; the Pilot treats it bench-immune both ways. `dont-bench-multiprize` exempts `win_condition`.
- **Disposition:** **infra A** (benchSpread valuation + `place-counter-to-convert` placement, ctx-14) covers it —
  **built + general, unchanged.** Readiness = `Line.ready` override.

### 2× Munkidori (112) — Role: `counter_mover` (tech) · tags: `confuse`, `heal`, `spread` · LOCKED (unchanged)
- **Mechanics:** Basic Psychic, 110 HP, 1-prize, weakness Darkness, resist Fighting, retreat 1. Ability
  **Adrena-Brain** (once/turn, **needs {D} attached**): move ≤3 counters (30) from 1 of YOUR Pokémon → 1 of the
  OPPONENT's. `PC` Mind Bend (60 + Confuse) — a pinch swing, not the plan.
- **Use:** the Phase-2 finisher/consolidator + mirror self-healer. Two-sided: OFFENSE (top a softened bench mon
  into KO range for Boss's) or DEFENSE (peel counters off our own 90-HP Drakloaks / Dragapult). **#1 misplay:
  forgetting it is DEAD without {D} attached** (only 2 {D} in the deck — route via Crispin's free attach / Night
  Stretcher). It MOVES counters (bypasses damage-prevention); a move with no follow-up finisher is pure tempo loss.
- **Sequencing:** activate BEFORE the attack and BEFORE Boss's. Benched ability-mon; MAY Mind-Bend in a pinch (no veto).
- **Disposition:** **infra C** (Adrena-Brain source/amount/target handler, ctx 16/40/13) covers it — **built +
  general, unchanged.** `{D}` routing via Crispin (branch-2). *Deferred refinement:* explicit finish-vs-heal
  value-compare (v1 = most-damaged source body + convert target).

### 1× Fezandipiti ex (140) — Role: `comeback_engine` (tech) · tags: **none** · LOCKED (unchanged)
- **Mechanics:** Basic Darkness, 210 HP, 2-prize, weakness Fighting, retreat 1. Ability **Flip the Script**
  (once/turn, if any of your Pokémon were KO'd during opp's LAST turn: draw 3). `CCC` **Cruel Arrow** (100 to ANY
  opp Pokémon, no W/R on Bench). {D} → immune to our Risky Ruins.
- **Use:** PRIMARY = comeback draw (fires almost every turn in this trade-heavy deck; **bench it BEFORE the KO** to
  trigger — entering the grind, not T1). SECONDARY = Cruel Arrow, a situational benched finisher (don't steal
  Dragapult's FP for it). Fetch = **Ultra Ball only** (Rule Box). 2-prize liability — don't bench too early.
- **Disposition:** `bench-the-comeback-drawer` (deck rule, retained) overrides `dont-bench-multiprize` in
  RACE/STABILIZE. Cruel Arrow valuation = **infra B** (built, general). Flip-the-Script draw = auto (the on-KO
  draw ability; benched engine).

### 1× Meowth ex (1071) — Role: none (tag-driven) · tags: `search`, `supporter_tutor` · LOCKED (unchanged)
- **Mechanics:** Basic Colorless, 170 HP, 2-prize, weakness Fighting, retreat 1. Ability **Last-Ditch Catch**
  (on-play from hand → Bench: tutor ANY Supporter to hand). `CCC` Tuck Tail (60, self-bounce).
- **Use:** one-of Supporter valve — bench to tutor the exact situational Supporter (Boss's for a gust KO; Rosa's
  when the gate flips). Needs an open bench slot AND your Supporter play still available (the tutored card must
  still be PLAYED). Cannot tutor Unfair Stamp (Item). Don't dangle as free prizes.
- **Disposition:** **covers-as-is** — general `bench-the-supporter-tutor` + `grab-a-gust-supporter-for-the-ko`
  (doctrine_fetch, `supporter_tutor` tag) + `dont-open-multiprize-active` / `dont-pre-bench-the-supporter-tutor`.
  **NO Role, NO deck rule** (mega_lucario model).

### 4× Dreepy (119) — Role: `win_condition_base` · tags: none · LOCKED (unchanged)
Basic Dragon 70 HP, 1-prize, no weakness, retreat 1; chip attacks only. Poffin target. Covered: `keep-a-bench`,
`fetch-a-starter`, `prefer-bench-fill-first`, `fetch-base-before-stranded-payoff`, the Line.

### 4× Drakloak (120) — Role: line mid + `dig`/`draw` engine · tags: `dig`, `draw` · LOCKED (unchanged)
Stage 1, 90 HP, evolves from Dreepy. **Recon Directive** (top-2 → 1). **Use Recon BEFORE evolving** (ability lost
on evolve). **Hold the Drakloak→Dragapult evolve until the body carries 2 FP** (keep Recon-digging; carve-out:
evolve now if the Drakloak is in KO range). Keep a spare Drakloak as a standing Recon engine. Disposition: line +
`dig`; the two timing gates are the deck rule `hold-evolution-until-attacker-ready` + §4 carve-outs. **Note:** its
Recon activation shares the pure-draw-ability question with Dudunsparce (§6 verify).

### 2× Risky Ruins (1260) — Role: `disruption` (tech) · tags: none (deck-rule + stadium infra) · LOCKED (unchanged)
Stadium. Any player benches a Basic **non-{D}** → 2 counters on it. Our Stage-1/2 attackers immune; our vulnerable
Basics = Dreepy/Budew/Dunsparce/Meowth; Fezandipiti/Munkidori ({D}) immune. **Double-edged** (symmetric) — accept
the self-chip because **Munkidori relays it back** onto the opponent. Play proactively; bench our vulnerable Basics
FIRST that turn; re-slam the 2nd copy after an opponent stadium bump. Disposition: deck rule
`play-risky-ruins-when-net-positive` (retained) + **infra D** stadium signal. *(bench-first sequencing +
skip-vs-{D}-decks refinement deferred to the Read.)*

### 4× Crushing Hammer (1120) — Role: `disruption` · tags: `energy_denial` · LOCKED (unchanged)
Item, coin-flip discard 1 opp Energy. **covers-as-is** by general `play-energy-denial` (stands down on no-energy
Active / when we already KO). Now ×4 (aggressive commitment) — flip all copies in one turn for a key energy; lower
priority once behind on the KO race. Count change needs no doctrine change.

### 3× Boss's Orders (1182) — Role: `gust` · tags: `gust` · LOCKED (unchanged)
The prize-converter. **covers-as-is** by the Gust doctrine (ADR-0022, id 1182): whether-to-play + target. TOP
Supporter on a convert/lethal turn; resolve the gust BEFORE attacking.

### 3× Crispin (1198) — Role: `accel_source` · tags: `energy_accel`, `search`, `tutor_energy` · LOCKED (unchanged)
The **primary, un-gated** accel now (Cinderace gone). Search 2 basic diff types → attach the missing Phantom Dive
color (F/P) or arm Munkidori ({D}). **covers-as-is** by `use-acceleration` + `advance-the-accel-pieces`
(`accel_source` Role); branch-2 {D}-routing.

### 4× Lillie's Determination (1227) — `draw`, `shuffle_hand` · LOCKED (unchanged)
Primary hand-refresh (draw 6; **8 at exactly 6 prizes**). Shuffle-Refresh doctrine (ADR-0024): endorsed by
`dig-before-commit`, floored by the keep-value guards, tier-3 sequenced. Heaviest T1–T2. **(Judge re-added
2026-07-15 — Lillie's + Judge are the two `shuffle_hand` refills; both ride the same doctrine, no card conflict.)**

### 1× Judge (1213) — Role: none (tag-driven) · tags: `draw`, `hand_disruption`, `shuffle_hand` · covers-as-is
- **Mechanics:** **Supporter** (SVI 176). "Each player shuffles their hand into their deck and draws **4** cards."
- **Use:** proactive **hand disruption** + symmetric refresh — cut a loaded opponent to 4 (post-refresh / pre-combo),
  or use as a leaner Lillie's when our own hand stalls. Symmetric draw-4, so play it when the swap favors us (we're
  low / they're high). Re-added 2026-07-15 for a Psychic energy; **coexists with Rosa's** (disruption + comeback accel).
- **Disposition:** **covers-as-is** by the Shuffle-Refresh doctrine (ADR-0024, `shuffle_hand` tag) + keep-value
  floors — the exact coverage Lillie's rides. **No Role, no deck rule** (user-confirmed general coverage, 2026-07-15).
  The max-strip nuance (fire Judge when it most hurts a loaded opp) is the deferred general `hand_disruption` seam,
  same as Unfair Stamp's.

### Fetch suite — 4× Buddy-Buddy Poffin (1086) / 4× Poké Pad (1152) / 4× Ultra Ball (1121) / 3× Night Stretcher (1097) · LOCKED (unchanged)
Fetch doctrine (ADR-0023): **Poffin** → ≤70 Basics (**now Dreepy / Budew / Dunsparce**; play FIRST, earliest dev
rung); **Poké Pad** → free non-Rule-Box tutor (Dreepy/Drakloak/Dunsparce/Dudunsparce/Munkidori/Budew; play before
Ultra Ball); **Ultra Ball** → the only Rule-Box tutor (Dragapult/Fezandipiti/Meowth ex), discard-2 **feeds Rosa's
+ Night Stretcher**; **Night Stretcher** → recover a Pokémon or the exact F/P/{D} (a Phantom-Dive / Munkidori
gate), or refuel the discard for Rosa's. Covered: `prefer-bench-fill-first`, `fetch-a-starter`, `fetch-the-wincon`,
`fetch-base-before-stranded-payoff`, discard keep-value.

### 1× Unfair Stamp (1080) [ACE SPEC] — `draw`, `hand_disruption`, `shuffle_hand` · LOCKED (unchanged)
KO-gated (only the turn after our Pokémon was KO'd): both shuffle hands, you draw 5 / opp 2. Item → **stacks with a
Supporter**; shares Fezandipiti's trigger. Play near-**last** with a thin hand. **covers-as-is** by the
Shuffle-Refresh doctrine (`shuffle_hand`) + the aceSpec discard/keep guard (the max-impact strip nuance stays the
deferred general `hand_disruption` seam).

### Energy — 3 F / 3 P / 2 D (8 Basic) · LOCKED (2026-07-15: −1 Psychic for Judge)
F+P gate Phantom Dive (even F/P now); the 2 {D} gate Munkidori (+ Fezandipiti). F/P → the Dragapult line
(manual + Crispin + Rosa's-from-discard); {D} → Munkidori via Crispin's free attach. Covered:
energy-attachment procedure (ADR-0016) + `develop-the-accel-recipient` (now inert without an accel Active — fine).

## 4 · Combos, sequencing & opening hands

**Combos (min pieces → payoff):** as §2 — Phantom-Dive→Munkidori→Boss's (cross-turn convert); Risky-Ruins→Munkidori
launder; Cruel Arrow stack; Unfair-Stamp+Flip-the-Script; Budew lock + attach runway; Lillie's+Run-Away-Draw double
draw; Rosa's re-arm; Meowth→exact Supporter.

**Sequencing ladder (developing turn):** free draw/dig (**Recon + Run Away Draw** — before committing) → Items
(**Poffin → Poké Pad → Ultra Ball** → Night Stretcher/Crushing Hammer) → the one **Supporter** (Boss's on a convert
turn, else Crispin/Lillie's/Rosa's) → **evolve/attach** → **attack LAST**. Carve-outs listed in §2.

**Opening hands — prefer going SECOND** (Budew item-lock T1):
- **Dream (second):** Budew + 2 Dreepy (Poffin) + energy → Budew Active, seed Dreepy, attach, **Itchy Pollen T1**.
- **Median:** a Basic + a tutor + energy → develop the line; Budew Active if held.
- **Survivable:** a lone Dreepy/Dunsparce + an Item → keep; dig.
- **Mulligan keeps:** any hand with a Basic (Dreepy/Budew/Dunsparce/Munkidori/Fezandipiti/Meowth) →
  `keep-a-startable-hand`. 10 Basics → mulligans rare.

**Plan mapping:**
- **SETUP** = Budew lock (going second) + assemble Dreepy→Drakloak→Dragapult + seed F/P; slam Risky Ruins; don't bench the 2-prize exes yet.
- **RACE** (flips at `Ready(energy=2)` — FP) = Phantom Dive every turn; place spread by the matchup-switched policy; convert with Munkidori/Boss's.
- **STABILIZE** (behind — desirable, arms Rosa's) = Munkidori-reverse heals the line; Fezandipiti/Unfair Stamp refuel+strip; **Rosa's re-arms a KO'd Dragapult**; Crushing Hammer buys tempo.
- **CLOSE** (ahead) = gust + finisher sequencing to cash the last prizes.

## 5 · General-Strategy disposition table

| General Hypothesis / doctrine | Disposition | Why (deck-specific) |
|---|---|---|
| `keep-a-startable-hand` | covers-as-is | 10 real Basics keep hands (Budew/Dunsparce added) |
| `honor-preferred-start` | **param (CHANGED)** | `preferred_start="second"` (Budew item-lock fires T1 only going second; was "first") |
| `open-the-accelerator` / `develop-the-accel-recipient` / `dont-fetch-the-setup-only-opener` | **inert** | Cinderace removed → no `accel_source` opener / no accel Active. Harmless. |
| `dig-before-commit` | covers-as-is (PLAY only) **+ GAP** | covers `draw`/`search` **card PLAYs**; **does NOT reach the ABILITY draws** (Recon / Run Away Draw) — `_ABILITY` option, confirmed skipped → new `use-the-draw-engine-ability` (§6) |
| `attach-energy-last`/`power-up-attacker`/`use-acceleration`/`advance-the-accel-pieces` | covers-as-is | Crispin the primary accel; F/P → line. Rosa's covered **once `energy_accel`-tagged** (§6) |
| `dont-bench-multiprize` | **override** | Fezandipiti/Meowth ex benched for abilities in RACE/STABILIZE (`bench-the-comeback-drawer` + tutor rules); −15 stays right in SETUP |
| Snipe cluster + **infra A** (Phantom Dive spread valuation/placement) | covers-as-is (built) | Dragapult unchanged → benchSpread + `place-counter-to-convert` still fire |
| **infra B** (Cruel Arrow any-target) / **infra C** (Munkidori Adrena-Brain) / **infra D** (Stadium signal) | covers-as-is (built) | Fezandipiti / Munkidori / Risky Ruins unchanged |
| Gust doctrine (`gust-for-the-ko`/`gust-target`/`gust-for-the-stall`) | covers-as-is | Boss's id 1182; convert-the-softened-mon IS `gust-for-the-ko` (`gust_ko` uses REMAINING HP) |
| Fetch doctrine (all rungs) | covers-as-is | Poffin→Dreepy/Budew/Dunsparce, Poké-Pad-first, Ultra-Ball-Rule-Box, `fetch-base-before-stranded-payoff` |
| `fetch-the-support` | covers-as-is (+ minor gap) | grabs Dudunsparce (`draw` engine) / Drakloak; **minor gap §6**: Dunsparce base under-prioritised + Dudunsparce stranded-in-hand risk |
| Shuffle-Refresh (Lillie's / **Judge** / Unfair Stamp) | covers-as-is | `shuffle_hand` + keep-value floors + aceSpec guard; **Judge (1213) re-added 2026-07-15 — same coverage, no new rule** |
| `play-energy-denial` (Crushing Hammer ×4) | covers-as-is | `energy_denial` tag; count change needs nothing |
| Tool doctrine | **N/A** | no Tools |
| Tactical: Weakness×2 / `prize-trade-target` | covers-as-is | Dragapult no weakness; prize preference applies |
| `conserve-discard-energy-prefer-basic` | **N/A** | no `discard_eot` special energy (all Basic) |

> **ADR-0079 migration (2026-07-28).** The Set-Up ACTIVE seam is now ONE deck declaration —
> `Strategy.starter_priority` in this deck's `strategy.py`, read by the general
> `open-the-declared-starter`. Rows above naming `open-the-accelerator`,
> `open-the-item-lock-starter`, `dont-open-multiprize-active`, `dont-open-with-the-engine`,
> `start-solrock-over-lunatone` or the `starter` Role are **history** — all are deleted. See
> [ADR-0079](../../../docs/adr/0079-the-setup-active-pick-is-one-deck-declaration.md).

**Existing deck Hypotheses (retained, cards all still present):** `bench-the-comeback-drawer` (Fezandipiti),
`hold-evolution-until-attacker-ready` (Drakloak→Dragapult), `play-risky-ruins-when-net-positive` (Risky Ruins).

**Net-new work (gaps, all CONFIRMED by probe/code — §6):** `use-the-draw-engine-ability` (Recon / Run Away Draw
skipped); Budew item-lock opener (+ `item_lock` tag); Rosa's `energy_accel` tag; `dont-strand-the-evolving-engine`
(Dunsparce/Dudunsparce fetch inversion); `preferred_start="second"`; Cinderace/Judge cleanup.

## 6 · New rules / tags (drafts — trigger sketches, NOT lambdas yet)

> **✅ ALL SHIPPED (deck-align 2026-07-15).** Every rule + tag drafted below has since landed in `common`,
> gated + committed by `/update-strategy`; this deck is **covered-as-is** and opts in via its tagged cards —
> no deck-file wiring needed. Landed: `open-the-item-lock-starter` → `baseline/baseline_opening.py`;
> `use-the-draw-engine-ability` → `baseline/baseline_sequencing.py`; `dont-strand-the-evolving-engine` →
> `doctrines/doctrine_fetch.py`; **tags** `item_lock`→Budew (235), `energy_accel`→Rosa's (1240) in
> `card_functions.json`. The per-rule "status:" lines below are kept as the authoring record.

### `open-the-item-lock-starter` · GENERAL (`baseline_opening`) · seed +35 · status: **SHIPPED** (baseline_opening.py)
> At the pregame `SETUP_ACTIVE` pick, prefer opening an `item_lock`-tagged Basic (Budew) — leading with the free
> item-lock body lets its Itchy Pollen-class attack fire on your first turn (esp. going **second**, where the
> attack is legal T1), taxing the opponent's Item-based setup for a turn at no cost.

**Trigger sketch:** `select_context == SETUP_ACTIVE` AND the candidate card carries the `item_lock` tag. **Reads:**
SETUP_ACTIVE + the `item_lock` Function Tag. **Seed +35** (just below `open-the-accelerator` +40; both are pregame
Active-pick boosts). **Lives in:** **GENERAL** `baseline_opening` — "lead with your free item-lock disruptor" is
universal; a deck opts in by running an `item_lock` card (and the rule is silent for decks that don't). **Why
general:** identical shape to `open-the-accelerator` (Role/tag-keyed opener). **KO-safe:** a pregame pick, no KO
involved. *(No first/second gate needed: opening Budew going first is still fine — the lock just waits to T2.)*
**Companion tag:** add **`item_lock`** to Budew (235) in `card_functions.json` (behavioral: an attack that blocks
the opponent's Items next turn) — the card-functions pipeline; the proposal notes it.

### `energy_accel` tag on Rosa's Encouragement (1240) · card-functions · then covers-as-is
> Rosa's is energy acceleration (attach ≤2 basic from discard to a Stage 2) but is untagged, so `use-acceleration`
> can't see it. Tag it `energy_accel`.

**Effect:** `use-acceleration` (+25, `energy_accel` tag) then endorses playing Rosa's — engine-gated to "behind on
prizes", target-gated to Stage 2 (Dragapult ex) by the engine, so no over-firing. **Do NOT** add the `accel_source`
Role (would mis-boost at SETUP via `advance-the-accel-pieces`; Rosa's is comeback-only). **Lives in:**
card_functions.json (tag) — no new Hypothesis. **Note:** consider a future `tutor_energy`-style secondary if the
discard-fuel needs its own keep-value term; deferred (general discard keep-value suffices for v1).

### `use-the-draw-engine-ability` · GENERAL (`baseline_sequencing`) · seed +18 · status: **SHIPPED** (baseline_sequencing.py)
> Activate a benched engine Pokémon's once-per-turn **draw/dig Ability** (`_ABILITY` option on a Pokémon whose
> ability carries a `draw`/`dig` engine tag — Drakloak Recon Directive, Dudunsparce Run Away Draw) during SETUP/RACE,
> sequenced early (before the turn-ending attack), because a pure card-advantage ability has no combat value and
> `dig-before-commit` (keyed on `_PLAY`) never reaches it — so nothing currently lifts it above `_finish_turn_last`'s
> LAST tier, and the engine **is** skipped.

**Trigger sketch:** `option_type == _ABILITY` AND the option's ability/card carries a `draw` or `dig` tag AND not
`cost_discard`. **Fires:** SETUP/RACE. **Lives in:** **GENERAL** `baseline_sequencing` (the free-dig family) — a
tag+option-type read, no card id; every ability-engine deck (Bibarel, Dudunsparce, Drakloak) inherits it. **Why
general:** "use your free draw engine" is universal; it's the `_ABILITY` sibling of `dig-before-commit`.

**VERIFIED (probe `scratchpad/probe_ability.py`, 2026-07-09) — CONFIRMED GAP, NOT redundant.** No hypothesis in
the general or deck layer reads `option_type == _ABILITY`; a pure draw/dig ability scores **0** (`_tactical`=0 for
non-attacks) → drops to `_finish_turn_last` tier 4 (`pilot.py` `score<=0 → 4`) → any positive-tactical attack
outsorts it (`by_score` descending) → the ability is **skipped** whenever an attack is on the menu; it fires only
incidentally on a pure-setup turn (no attack). Probe: Recon & Run Away Draw both `score=+0.0 fired={}` and the
Pilot took the attack instead. **The `_ABILITY` option DOES resolve `card_id` (120 / 66) and its tags** — so this
tag-keyed rule fires cleanly and lifts it to tier 0. **This is the biggest finding — a GENERAL fix the 2026-07-03
build silently needed (its "keep Recon-digging each turn" plan was undriven).** **Related (note, not this rule's
scope):** Munkidori **Adrena-Brain activation** shares the mechanism (its MAIN `_ABILITY` option also scores 0);
infra C only handles the *follow-up selects* once it's active. On a lethal/KO-completing turn the planner may
sequence it, but a non-lethal **pre-load** activation is skipped. v1 scopes this rule to `draw`/`dig` (clean,
load-bearing); extending it to the counter-move/heal activation is a **deferred** refinement (§8) — a blanket
"activate any ability" risks firing a counter-move with no good target.

### `dont-strand-the-evolving-engine` · GENERAL (`doctrine_fetch`) · seed −20 · status: **SHIPPED** (doctrine_fetch.py)
> Don't tutor a Stage-1 engine Pokémon (Dudunsparce — `card_is_support`, Run Away Draw) to HAND when its base
> (Dunsparce) is not in play and not in hand — it's a stranded dead card (can't be played). The engine-precursor
> analogue of `fetch-base-before-stranded-payoff` (which is scoped to the win-condition **Line**, so it does not
> cover a non-Line draw engine).

**Trigger sketch:** at a `_TO_HAND` search, penalise grabbing a Stage-1 `card_is_support` whose evolvesFrom base is
absent from play+hand. **Lives in:** **GENERAL** `doctrine_fetch` (extends the stranded-payoff logic beyond the
Line). **VERIFIED (workflow `wjzvrtwbk`) — a real PRIORITY INVERSION, worse than "minor":** `fetch-the-support`
(+15) grabs the UNPLAYABLE Stage-1 Dudunsparce (id 66, `card_is_support`, base Dunsparce present so the
`_stranded_evolution_set` guard is inert and `dont-grab-a-baseless-mid-evolution` is `card_is_line_preevo`-gated →
both miss it), OUTSCORING `fetch-a-starter` (+12) on its own **base** Dunsparce (id 305, no tags, not a line
pre-evo) — so at an Ultra Ball the doctrine actively **prefers tutoring the dead Stage 1 over the Basic that
enables it.** **Fix:** extend the base-before-payoff / anti-baseless-grab guards to **non-wincon engine evolution
lines** (a general `card_is_support` variant of `card_is_line_preevo`), OR ship this `dont-strand` penalty.
**Companion (recommended, same fix):** a soft positive to fetch the Dunsparce **base** as the engine precursor
(mirrors `fetch-base-before-stranded-payoff`). Priority: medium — a 1-of engine, but the inversion actively
mis-fetches. **General** (helps any evolving-engine deck: Bibarel/Bidoof, Dudunsparce).

### `preferred_start = "second"` · param · covers-as-is
Flip `Strategy.params["preferred_start"]` `"first"` → `"second"`. `honor-preferred-start` then penalises choosing
to go first. **Two simulator-verified rule facts drive it** (rules.md L72-73): the first player T1 **cannot attack**
(Budew Itchy Pollen can't lock until your T2 — a full turn late) **AND cannot play a Supporter** (this sim is
stricter than real SV — a Supporter-hungry line loses its first setup Supporter too). Guru-unanimous for a
Budew/Unfair-Stamp shell (Going Second / TheGamer / TCGplayer / Pokemon.com; verified vs the "setup-heavy → first"
steelman 2026-07-09, workflow `wh8ls1w6m`). The conventional "setup-heavy Stage-2 → first" heuristic is real but
overridden here. Ship default; kill-switch = one-line revert to "first" (matchup-conditioned first/second is a
later Read refinement).

### Cinderace / Judge cleanup · strategy.py + this doc · hygiene (user-requested)
Remove `CINDERACE = 666` const + its `ROLES` entry + all Cinderace/Judge prose from `strategy.py` (scoped to
dragapult — id 666 is **shared with mega_starmie**, do not touch there). No `when()` referenced Cinderace/Judge, so
no rule breaks. The trigger tests use a local `CINDERACE` filler (self-contained) — they still pass; modernising
that filler to Dunsparce/Dreepy is a nicety for `/update-strategy`.

## 7 · Roles, Lines, params (the executable shape, pre-code)

**Card ids** (dragapult_ex/deck.csv, verified 2026-07-09): DUDUNSPARCE 66, MUNKIDORI 112, DREEPY 119, DRAKLOAK 120,
DRAGAPULT_EX 121, FEZANDIPITI_EX 140, BUDEW 235, DUNSPARCE 305, MEOWTH_EX 1071, UNFAIR_STAMP 1080, BUDDY_POFFIN 1086,
NIGHT_STRETCHER 1097, CRUSHING_HAMMER 1120, ULTRA_BALL 1121, POKE_PAD 1152, BOSS_ORDERS 1182, CRISPIN 1198,
LILLIES 1227, ROSAS 1240, RISKY_RUINS 1260; FIRE 2, PSYCHIC 5, DARKNESS 7. **JUDGE 1213 re-added 2026-07-15 (−1
Psychic; NOT a `strategy.py` const — tag-driven `shuffle_hand`, no deck rule references it). (Removed: CINDERACE 666.)**

```
roles = {
  DRAGAPULT_EX:    ["win_condition", "primary_attacker"],
  DREEPY:          ["win_condition_base"],        # Line pre-evo
  CRISPIN:         ["accel_source"],              # primary un-gated accel (color-fixer)
  BOSS_ORDERS:     ["gust"],
  NIGHT_STRETCHER: ["recovery"],
  BUDEW:           ["starter"],                   # item-lock opener (drives open-the-item-lock-starter via the item_lock TAG)
  MUNKIDORI:       ["counter_mover"],             # DECLARED 2026-07-19 (user doctrine): Adrena-Brain relays ≤3
                                                  # counters ours→theirs — spreads toward multi-KO Phantom Dive
                                                  # turns AND heals the lock body (peel an Active Budew). Worth =
                                                  # engine band; the attach seam reads it: the {D} is FUEL (never
                                                  # "wasted off-type"), and a stuck-Active Munkidori takes its {P}
                                                  # on top once the benched line is fed (Mind Bend 60 + Confusion).
  # Rosa's (1240): NO Role — the energy_accel TAG drives use-acceleration (accel_source would mis-boost at SETUP).
  # Fezandipiti / Risky Ruins / Crushing Hammer: deck Hypotheses / infra / tags — not a Role.
  # Meowth ex: NO Role — supporter_tutor TAG drives it. Dunsparce/Dudunsparce: fetch/ability tags — not a Role.
  # Tutors + Lillie's: Fetch / Shuffle-Refresh doctrines key on their tags — no Role.
  # (CINDERACE role removed.)
}

lines = [ Line(path=[DREEPY, DRAKLOAK, DRAGAPULT_EX], payoff=DRAGAPULT_EX,
               role="win_condition", ready=Ready(energy=2)) ]   # FP Phantom Dive

params = {
  "preferred_start":     "second",   # CHANGED — Budew item-lock fires T1 only going second
  "setup_energy_target": 2,          # FP for Phantom Dive
  "search_budget":       0,          # Tier-0 closed-form combat
  "my_archetype":        "Dragapult ex spread + disruption",  # Read favorability key (ADR-0026)
}

hypotheses = [   # deck rules that DON'T fold to general (unchanged from 2026-07-03; all cards present)
  bench-the-comeback-drawer,            # Fezandipiti
  hold-evolution-until-attacker-ready,  # Drakloak -> Dragapult
  play-risky-ruins-when-net-positive,   # Risky Ruins (+ infra D)
  # NEW general rules (open-the-item-lock-starter, [use-the-draw-engine-ability], dont-strand-the-evolving-engine)
  #   + tags (item_lock on Budew, energy_accel on Rosa's) land in common/ + card_functions.json, NOT here.
]
```

## 8 · Open questions / deferred / verify

**VERIFIED (workflow `wjzvrtwbk` + probe `scratchpad/probe_ability.py`, 2026-07-09) — all RESOLVED, gaps confirmed:**
1. **Draw-engine-ability activation — CONFIRMED GAP.** Probe: Recon + Run Away Draw score 0, no hypothesis fires,
   the Pilot takes the attack instead (skipped whenever an attack is on the menu; fires only on a pure-setup turn).
   → ship `use-the-draw-engine-ability` (§6). The `_ABILITY` option resolves `card_id`/tags, so the rule works.
2. **Budew opener — CONFIRMED GAP.** Probe: Dreepy/Budew/Dunsparce all score 0, `fired={}`, `decide()` = option
   index 0 (arbitrary). No rule prefers an item-lock starter. → ship `open-the-item-lock-starter` + `item_lock` tag.
   (rules.md L72 confirms the second player CAN attack turn 1 → Itchy Pollen T1.)
3. **Rosa's tag — CONFIRMED GAP.** id 1240 absent from `card_functions.json`; `use-acceleration` can't fire. →
   add `energy_accel`; once tagged it fires correctly (engine gates legality to behind-on-prizes; no misfire) and
   `advance-the-accel-pieces` stays correctly silent (setup-gated).
4. **Dunsparce/Dudunsparce fetch — CONFIRMED GAP (priority inversion).** `fetch-the-support` +15 mis-fetches the
   unplayable Dudunsparce over its +12 base. → §6 `dont-strand-the-evolving-engine` (+ base-before-payoff extension).
5. **Cinderace/Judge removal — blast radius SAFE.** Simulated removal + `preferred_start` flip → 19 dragapult-scoped
   + 22 mega_starmie tests pass. id 666 shared with mega_starmie → scope the removal to dragapult only.

**Partial risks / notes (do NOT block; carry into the doctrine / `/deck-align`):**
- **Munkidori Adrena-Brain ACTIVATION** shares the draw-ability gap (its MAIN `_ABILITY` scores 0). Infra C covers
  the follow-up selects only. Planner may sequence it on a lethal/KO turn; a non-lethal **pre-load** activation is
  skipped. v1 `use-the-draw-engine-ability` scopes to draw/dig; extending to counter-move/heal is a deferred refinement.
- **Poké Pad** now carries a `no_rule_box` FETCH clause (`card_effects.json`, the tier that replaced
  `_FETCH_FILTERS`) → the Fetch doctrine's play/whiff/redundancy signals fire for it and correctly EXCLUDE
  Rule-Box targets (Dragapult ex / Fezandipiti ex / Meowth ex) — it no longer over-counts them as fetchable.
- **The fetch-set predicates are exact** (`_fetch_target_matches` over FETCH clauses): Poffin's ≤70-HP cap
  (`hp_max`), Poké Pad's no-Rule-Box, Fighting Gong's Basic-only Pokémon are encoded, so `dont-search-an-empty-deck`
  and the confirmed-hit endorsement no longer false-fire on targets a card cannot actually reach.
- **Unfair Stamp disruption facet** (opp draws only 2) was not rewarded generically — the rung that
  could have was gated on the retired `opp_has_hand_size_attacker` boolean → valued purely as
  self-refresh. **Since ADR-0102** the facet is priced where it is real: Stamp's 5/2 branch shrinks
  their hand hardest of the three symmetric refreshes, so `_hand_size_relief_tactical` credits it
  most against a hand-scaling attacker, and nothing at all against a board with no such line.

**Deferred (designed seams, not shipped):**
- Munkidori explicit **finish-vs-heal** value-compare (v1 = most-damaged source + convert target).
- Risky Ruins **bench-first sequencing** + skip-vs-{D}-decks (needs the Read).
- Rosa's **discard-as-fuel** keep-value term (a `good-in-discard` for basic F/P when behind) — general discard suffices for v1.
- `dont-strand-the-evolving-engine` positive companion (fetch the Dunsparce base as precursor) — hand to `/deck-align` if the ladder shows under-development.
- Matchup spreads are competitive-reasoning-level → **ladder-validate** (gauntlet-invalid; ladder + corrections are the signal).

**Ladder-ship posture (gauntlet-invalid, ladder-only):** the behavioral changes (`preferred_start="second"`,
Budew opener, draw-ability activation) ship **default-ON, kill-switched, with blunder-buster telemetry** — not
A/B-gated (cross-deck gauntlet proves nothing about gain). Verify via ladder corrections + user feedback.

---

## Appendix A · Phase-0 raw fact dump (verbatim substrate — engine ground truth, 2026-07-09)

```
# Deck facts — dragapult_ex (60 cards, 24 unique — Judge re-added 2026-07-15)

## Pokémon
- 3× Dragapult ex (121) — Stage 2 Dragon · 320 HP · 2 prize · ex Tera · ← Drakloak · weak - · retreat 1
  · tags spread · [C] Jet Headbutt 70 · [FP] Phantom Dive 200: put 6 damage counters on opp Bench any way.
- 4× Drakloak (120) — Stage 1 Dragon · 90 HP · 1 prize · ← Dreepy · tags dig,draw · Ability Recon Directive:
  once/turn look at top 2, put 1 in hand, other to bottom · [FP] Dragon Headbutt 70.
- 4× Dreepy (119) — Basic Dragon · 70 HP · 1 prize · [P] Petty Grudge 10 · [FP] Bite 40.
- 2× Munkidori (112) — Basic Psychic · 110 HP · 1 prize · weak Darkness · resist Fighting · tags confuse,heal,spread
  · Ability Adrena-Brain: once/turn if {D} attached, move ≤3 counters from 1 of yours to 1 of opponent's · [PC] Mind Bend 60 (Confuse).
- 1× Fezandipiti ex (140) — Basic Darkness · 210 HP · 2 prize · ex · weak Fighting · Ability Flip the Script:
  once/turn if any of your Pokémon KO'd during opp last turn, draw 3 · [CCC] Cruel Arrow 0: 100 to 1 opp Pokémon (no W/R on Bench).
- 1× Budew (235) — Basic Grass · 30 HP · 1 prize · weak Fire · retreat 0 · [—] Itchy Pollen 10: opp can't play Items next turn.
- 1× Dunsparce (305) — Basic Colorless · 70 HP · 1 prize · weak Fighting · → Dudunsparce · [C] Trading Places 0 (self↔bench switch) · [CC] Ram 20.
- 1× Dudunsparce (66) — Stage 1 Colorless · 140 HP · 1 prize · weak Fighting · retreat 3 · ← Dunsparce · tags draw,stall
  · Ability Run Away Draw: once/turn draw 3; if you drew, shuffle this + all attached into deck · [CCC] Land Crush 90.
- 1× Meowth ex (1071) — Basic Colorless · 170 HP · 2 prize · ex · weak Fighting · tags search,supporter_tutor
  · Ability Last-Ditch Catch: on-play to Bench, search deck for a Supporter to hand · [CCC] Tuck Tail 60 (self+attached to hand).

## Supporter
- 3× Boss's Orders (1182) · gust — switch in 1 opp Benched Pokémon to Active.
- 3× Crispin (1198) · energy_accel,search,tutor_energy — search 2 Basic Energy diff types, 1 to hand, attach the other.
- 4× Lillie's Determination (1227) · draw,shuffle_hand — shuffle hand into deck, draw 6 (8 if exactly 6 prizes).
- 1× Rosa's Encouragement (1240) · (untagged) — only if MORE prizes remaining than opp; attach ≤2 Basic Energy from discard to 1 Stage 2.
- 1× Judge (1213) · draw,hand_disruption,shuffle_hand — each player shuffles their hand into their deck and draws 4 (re-added 2026-07-15).

## Item
- 4× Buddy-Buddy Poffin (1086) · search,bench_fill — search ≤2 Basics ≤70 HP to Bench (Dreepy/Budew/Dunsparce).
- 4× Poké Pad (1152) · search — search a non-Rule-Box Pokémon to hand.
- 4× Ultra Ball (1121) · cost_discard,search,tutor_pokemon — discard 2, search any Pokémon.
- 4× Crushing Hammer (1120) · energy_denial — flip a coin; heads discard 1 opp Energy.
- 3× Night Stretcher (1097) · recycle — a Pokémon or Basic Energy from discard to hand.
- 1× Unfair Stamp (1080) [ACE SPEC] · draw,hand_disruption,shuffle_hand — only if your Pokémon KO'd last turn; both shuffle hands, you draw 5 / opp 2.

## Stadium
- 2× Risky Ruins (1260) — any player benches a Basic non-{D} → 2 counters on it.

## Energy
- 3× Basic {R} Fire (2) · 3× Basic {P} Psychic (5) · 2× Basic {D} Darkness (7).  (2026-07-15: −1 Psychic for Judge.)
```
