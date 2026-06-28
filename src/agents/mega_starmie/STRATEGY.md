# mega_starmie — Playing Doctrine

> Phase-A deliverable of `/deck-genie`. The human-readable strategy the deck plays; the executable
> `strategy.py` is generated from this **after sign-off** (ADR-0017). Build on the
> [General Strategy](../../../docs/general-strategy.md): reuse, override, or extend — don't restate.

**Status:** `drafting` · **Last grilled:** 2026-06-28 · **Author:** deck-genie + Richard

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped
- [x] Phase 1 overview confirmed
- [x] Phase 2 research synthesised + user-confirmed (confidence LOW — Cinderace build web-uncovered)
- [x] Phase 3 card-by-card: 18/18; opening hands + Plan mapping locked (§4)
- [x] Phase 4 General-Strategy disposition + hypothesis drafts complete
- [ ] Phase 5 signed off → Phase B authorised  ← **awaiting sign-off**

Cards still to grill: none — all 18 locked. Open questions / deferred infra: see §8.

## 0 · Card facts (engine dump — substrate, do not hand-edit)

Source: `python .claude/skills/deck-genie/scripts/dump_deck.py mega_starmie`. Engine is ground truth.

### Pokémon (10)
- **4× Cinderace** — Stage 2 Fire · 160 HP · 1 prize · weak **Water** · retreat 0 · evolves from Raboot · tag `opener`
  - *Ability — Explosiveness:* if in hand while setting up, may put it face-down in the Active Spot.
  - *C — Turbo Flare (50):* search deck for ≤3 Basic Energy, attach to your **Benched** Pokémon any way; shuffle.
- **3× Staryu** — Basic Water · 70 HP · 1 prize · weak **Lightning** · retreat 1
  - *W — Water Gun (20).*
- **3× Mega Starmie ex** — Mega ex Water · 330 HP · **3 prize** · weak **Lightning** · retreat 2 · evolves from Staryu
  - *W — Jetting Blow (120):* +50 to 1 of opponent's Benched Pokémon (no W/R on bench).
  - *CCC — Nebula Beam (210):* damage unaffected by Weakness/Resistance or any effects on opp's Active.

### Supporter (17)
- **4× Lillie's Determination** — `draw`: shuffle hand, draw 6 (8 if exactly 6 prizes remaining).
- **4× Salvatore** — `search`,`rush_evolve`: search a no-Ability Evolution that evolves from one of your Pokémon and evolve it now (incl. a Pokémon put down this turn / during setup); shuffle.
- **4× Wally's Compassion** — `heal`,`clutch_heal`: heal all damage from 1 Mega ex; if healed, put all its Energy into your hand.
- **2× Harlequin** — `draw`,`hand_disruption`: both shuffle hands into deck; coin: heads you draw 5 / opp 3, tails you 3 / opp 5.
- **2× Hilda** — `search`: search an Evolution Pokémon **and** an Energy to hand; shuffle.
- **1× Boss's Orders** — `gust`: switch in 1 of opp's Benched Pokémon to the Active Spot.

### Item (Trainer) (—)
- **4× Buddy-Buddy Poffin** — `search`,`bench_fill`: ≤2 Basics with ≤70 HP onto Bench; shuffle.
- **4× Pokégear 3.0** — `dig`,`draw`: look top 7, may take a Supporter to hand; rest back.
- **4× Mega Signal** — `search`: search a Mega Evolution ex to hand; shuffle.
- **4× Crushing Hammer** — `energy_denial`: coin, heads discard an Energy from 1 of opp's Pokémon.
- **2× Night Stretcher** — `recycle`: a Pokémon or Basic Energy from discard to hand.
- **1× Ultra Ball** — `search`: discard 2, then search deck for any Pokémon to hand.

### Tool (1)
- **1× Hero's Cape** — +100 HP to the holder (Mega Starmie ex → 430 HP).

### Energy (13)
- **9× Basic Water Energy.**
- **4× Ignition Energy** — `discard_eot`: discarded at end of turn; provides C, **but on an Evolution provides CCC**.

## 1 · Overview (CONFIRMED — 2026-06-28)

- **Win condition:** turbo a single 3-prize **Mega Starmie ex** online fast and race with it,
  keeping it alive (heal/bulk) while taking 6 prizes with **Nebula Beam (210, ignores
  effects/weakness)** and **Jetting Blow (120 + 50 bench snipe)**.
- **Line:** `Staryu → Mega Starmie ex` (payoff). Online at **1 W** (Jetting Blow) per the engine;
  Nebula Beam wants CCC, reachable in ONE attach via **Ignition Energy on the Evolution = CCC**.
- **Key combo (signature):** Ignition Energy on Mega Starmie ex → instant CCC → Nebula Beam the
  turn it evolves. **Salvatore** rush-evolves Staryu→Mega Starmie ex (no-Ability Evolution) a turn
  early. **Cinderace** opens via Explosiveness (no Raboot needed) and **Turbo Flare** loads bench
  energy; retreat 0 lets it pivot out.
- **Main attacker:** Mega Starmie ex. **Support Pokémon:** Cinderace (opener + accel + 160-HP wall),
  Staryu (wincon basic).
- **Trainers by purpose:** draw/consistency = Lillie's Determination, Harlequin, Pokégear 3.0;
  tutors = Mega Signal (the Mega ex), Hilda (Evolution + Energy), Salvatore (rush-evolve), Ultra
  Ball, Buddy-Buddy Poffin (Staryu onto bench); disruption = Crushing Hammer, Boss's Orders;
  recovery = Night Stretcher; defensive = Wally's Compassion (clutch heal+rescue), Hero's Cape (bulk).
- **Energy:** 13 (9 Water + 4 Ignition). Ignition is the burst that powers Nebula Beam in one drop;
  Water is the reusable backbone. **Prize liability:** our own attacker is a 3-prizer — losing it
  hands the opponent half the game, so survival tools matter.

### Confirmed gameplan decisions (2026-06-28, user)

- **Sprint to Mega Starmie ex.** Open with **Cinderace** for quick chip (Turbo Flare 50) + Energy
  acceleration *when able*; the whole deck sprints the Mega Starmie ex line online and wins with it.
- **Attack choice — Jetting Blow vs Nebula Beam.** Lead **Jetting Blow** (1 W · 120 + 50 snipe) when:
  - **(A) it KOs the Active** — Active ≤120 HP, **or** Water-weak with ≤240 HP — then the 50 bench
    snipe is free extra value; **or**
  - **(B) the Active is a non-dangerous wall >210 HP** (not efficiently KO-able) **and** sniping the
    opponent's **bench threat** is the higher-value play (Jetting Blow used purely for the snipe).
  Otherwise **Nebula Beam** (CCC · 210 · ignores Weakness/Resistance + all effects on their Active)
  is the workhorse — the answer to big and effect-protected threats.
- **Cinderace is opening-hand-only.** It can ONLY enter via Explosiveness at game start; **never
  fetch it** (Ultra Ball / any tutor) — a fetched Cinderace is a dead card. Keep an opening hand
  containing it; never search for it.

## 2 · Research synthesis (cited — confidence: LOW)

**Coverage is thin and our exact build is web-uncovered.** Both usable sources describe Mega Starmie
ex but pair it with a **Froslass/Mega Froslass ex + Munkidori spread variant (explicitly NO
Cinderace)**. Our Cinderace + Salvatore + Lillie's/Hilda/Harlequin engine is a different,
undocumented build — so the web corroborates card mechanics + the generic single-attacker plan
only; the Cinderace engine is ours. Off-deck Froslass/Munkidori/Meowth-ex combos were rejected. The
sample-list ratio (2 Mega / 3 Staryu) is **not** authoritative — our list runs 3/3.

**Corroborated (survived adversarial verify vs card facts):**
- **Single-big-attacker beatdown, not spread.** Turbo one 330-HP Mega Starmie ex, race 6 prizes,
  protect it (Hero's Cape → 430).
- **Jetting Blow (1 W) is the CORE/default attack** — cheap, repeatable. **Nebula Beam (CCC, 210,
  ignore-effects) is "second gear"** for when Jetting Blow is the wrong line → corroborates Ignition
  conservation.
- **The 50 bench snipe is incidental, NOT a combo** — no secondary spread source, so don't build
  lines to convert the 50 into KOs (a lone 50 doesn't KO a 70-HP basic). Softening, not a kill.
- **Reserve Ignition for the Nebula line** (CCC only on an Evolution, discards EOT) — never a basic.
- **No native draw engine** — draw is Supporter-only (Lillie's, coin-flip Harlequin) + tutors →
  consistency is the soft spot; spend draw/tutors early.
- **Whole line is Lightning-weak** (Staryu + Mega Starmie ex) → Lightning threatens the OHKO; Hero's
  Cape (430) is the bulk answer.
- **Disruption package** (Crushing Hammer energy-denial + Boss's Orders gust) supports the race.

**RESOLVED — Salvatore → Mega Starmie ex is LEGAL** (user-confirmed 2026-06-28). Mega Starmie ex has
no Ability and evolves from Staryu → a valid Salvatore target; the research agent's rejection
("a Mega ex isn't a vanilla evolution") was a misread (attacks ≠ Abilities) and is refuted. The
Salvatore rush line stands.

**Sources:** [pokemon.com — Build a Mega Starmie ex Deck (Perfect Order)](https://www.pokemon.com/us/strategy/build-a-mega-starmie-ex-deck-from-pokemon-tcg-mega-evolution-perfect-order) · [josephwriteranderson.com — Every Perfect Order Deck Ranked](https://www.josephwriteranderson.com/blog/every-perfect-order-pokemon-deck-ranked)
## 3 · Card-by-card (18/18 locked)

### 3× Mega Starmie ex — `win_condition`, `primary_attacker`
- **Use:** the sole wincon attacker; race 6 prizes with it. **Attack choice:** default **Jetting
  Blow** (1 W · 120 + 50 snipe) whenever it gets the job done; **Nebula Beam** (CCC · 210 ·
  ignore-effects) when Jetting Blow can't (need 210 / effect-protection wall / Water-resist), **or**
  greedily when holding **≥2 Ignition** and Nebula meaningfully gets ahead.
- **Sequencing:** online via Cinderace Turbo Flare (3 Water → CCC, sustainable) **or** one Ignition
  (CCC burst). Minimum-online at 1 W (Jetting Blow).
- **Combos:** Ignition = CCC in one attach; Turbo Flare = 3 Water sustainable CCC; Wally's =
  heal+re-power loop; Hero's Cape → 430 HP.
- **Hand:** wants Staryu in play + an energy source + the evolve (natural or Salvatore).
- **Anti-patterns:** don't burn finite Ignition when Jetting Blow KOs; don't Nebula-chip an
  un-KO-able wall; never bench it as a loose 3-prize liability before it's the plan.
- **Disposition:** `evolve-into-wincon` + Tactical KO math cover the core; attack-selection nuance → §6.

### 4× Cinderace — `accel_source`, `starter` (tag `opener`)
- **Use:** the **sustainable energy engine** + opener. Opens via Explosiveness; **Turbo Flare**
  (1 C · 50) accelerates **3 Basic Water onto the benched Staryu/Mega Starmie line** — the route to
  CCC Nebula *without* spending Ignition. Also a 160-HP wall while setting up. Retreat 0 → free pivot.
- **Sequencing:** open Cinderace → attach → Turbo Flare (50 + 3 Water to the line) → **retreat
  Cinderace (free)** → promote Mega Starmie ex → attack.
- **Hand:** opening-hand only (Explosiveness); keeps a no-Basic hand startable.
- **Anti-patterns:** **NEVER fetched** (Ultra Ball / any tutor) — only enters via Explosiveness at
  game start; a fetched Cinderace is dead. Don't keep it Active once the line is ready.
- **Disposition:** `open-cinderace` + `accel-into-main` (deck rules) cover opening/accel.
  **CONFLICT: `hold-position-in-setup`** penalizes the *intended* retreat-to-promote → override (§6).
  Never-fetch → §6. Note: Cinderace lacks the `energy_accel` tag (probe gap) so general
  `use-acceleration` won't fire — the deck leans on Role `accel_source`.

### 3× Staryu — `starter` (wincon basic)
- **Use:** the Mega Starmie ex basic; bench it (Buddy-Buddy Poffin fetches, ≤70 HP), energize via
  Turbo Flare, then evolve (natural or Salvatore). Water Gun (20) is irrelevant — a stepping stone.
- **Anti-patterns:** don't waste a turn attacking with Staryu.
- **Disposition:** covered by the Line + `evolve-into-wincon`.

### 4× Ignition Energy — `accel_source` (burst, **finite**)
- **Use:** one-attach CCC on the Evolution → instant Nebula Beam. **Finite (4, non-recyclable —
  Night Stretcher can't recover it)** → conserve: spend only when Jetting Blow can't do the job, or
  greedily with ≥2 in hand when Nebula gets ahead.
- **Anti-patterns:** never on a benched/can't-attack Pokémon, never on a basic, never when a single
  Water → Jetting Blow would KO. Discards EOT.
- **Disposition:** `dont-waste-discard-energy` covers gross cases; the "prefer Water even on the
  wincon unless Nebula needed / ≥2 Ignition" refinement → §6.

### 9× Water Energy — sustainable backbone
- **Use:** powers Jetting Blow (1) forever; 3 → Nebula without Ignition; the Turbo-Flare type.
- **Disposition:** general `power-up-attacker` baseline.

### 4× Salvatore — `tutor`, `rush_evolve`
- **Use:** rush-evolve Staryu→**Mega Starmie ex** (legal; user-confirmed) a turn early, incl. the
  turn Staryu was played / during setup. Enables the explosive line (evolve + Ignition + Nebula).
- **Disposition:** general `prefer-rush-evolve-tutor` covers (fires on `rush_evolve`).

### 4× Wally's Compassion — `recovery`, `clutch_heal` (defensive save)
- **Use:** the turn Mega Starmie ex would be KO'd: heal all (energy bounces to hand) → **re-attach
  same turn and attack**. Re-power choice (Water vs Ignition) follows the Ignition-conservation logic.
- **Anti-patterns:** never on minor damage; never outranks a lethal.
- **Disposition:** general `hold-clutch-heal` covers (fires on `clutch_heal` + `active_doomed`).

### 1× Boss's Orders — `gust` (dual-mode disruption)
- **Mechanics:** Supporter. Switch in 1 of the opponent's Benched Pokémon to their Active Spot.
- **Use — two modes:**
  - **Offensive gust:** pull a benched Pokémon you can KO this turn — a prize you couldn't otherwise
    reach, or **an exposed pre-evolution / developing threat you OHKO before it comes online** (even
    Cinderace's 50 or Starmie's Jetting Blow 120 kills a fragile pre-evo). Usable in SETUP/RACE too.
  - **Defensive stall-gust:** when you have **no response** (their main attacker is energized, you're
    not ready) and they have an **energyless, high-retreat-cost wall on the bench** — drag the wall
    into the Active Spot so they waste turns retreating it before they can attack. Buys 1–2 setup turns.
- **Sequencing:** it's your one Supporter — spend it the turn the gust pays (a KO, or the stall).
- **Anti-patterns:** don't burn it on a turn you needed Salvatore/Hilda more, unless the gust wins/saves.
- **Disposition:** offensive gust→KO → Tactical / `prize-trade-target` (covers). **Defensive
  stall-gust → DEFERRED**: needs an opponent-board read (their active/bench energy + retreat costs)
  + a my-not-ready signal → Posture/Scout (designed, not wired). See §8.

### 2× Hilda — `search` (targeted setup)
- **Mechanics:** Supporter. Search deck for an **Evolution Pokémon AND an Energy**, both to hand.
- **Use:** the targeted setup engine — fetch **Mega Starmie ex + an Energy** in one card. High
  Supporter priority in setup over raw draw.
- **Disposition:** general `dig-before-commit` + deck `tutor-the-wincon` cover the lift; `fetch-the-wincon` governs the pull.

### 4× Lillie's Determination — `draw` (refill)
- **Mechanics:** Supporter. Shuffle hand into deck, draw **6** (**8** if exactly 6 prizes remaining).
- **Use:** the refill — play when the hand is **clogged / low / dead**. The 8-at-6-prizes rewards an
  early empty-ish hand. Lower Supporter priority than Salvatore/Hilda when those advance the line
  (board-state dependent).
- **Anti-patterns:** don't shuffle away a hand still holding pieces you need; don't spend your
  Supporter on raw draw when a tutor advances the board more.
- **Disposition:** general `dig-before-commit` (covers the setup lift). Intra-Supporter priority
  (tutor > raw draw) likely emerges from existing weights — verify in Phase B.

### 4× Pokégear 3.0 — `dig`, `draw` (Supporter-finder — the glue)
- **Mechanics:** Item (unlimited/turn). Look at top 7, may take a **Supporter** to hand; rest shuffled back.
- **Use:** play it **first**, before committing your one Supporter — it digs the Supporter you need
  (Salvatore / Hilda / Lillie's / Boss's). Consistency glue for a Supporter-hungry, draw-light deck.
- **Disposition:** general `dig-before-commit` covers the setup lift; "Pokégear before your Supporter"
  is the same sequencing principle.

### 4× Mega Signal — `search` (payoff tutor)
- **Mechanics:** Item. Search deck for a **Mega Evolution ex** (→ Mega Starmie ex), reveal, to hand.
- **Use:** the dedicated wincon tutor — primary way to find Mega Starmie ex. High setup priority.
- **Disposition:** `fetch-the-wincon` (general) + `tutor-the-wincon` (deck) cover it.

### 4× Buddy-Buddy Poffin — `search`, `bench_fill` (bench dev + thinning)
- **Mechanics:** Item. Put up to **2 Basics with ≤70 HP** from deck onto your Bench (Staryu qualifies; Cinderace 160 HP does not).
- **Use:** play **first** in setup — benches Staryu(s) and thins the deck, raising later draw quality. The opening bench-development engine.
- **Disposition:** general `prefer-bench-fill-first` covers (fires on `bench_fill`).

### 1× Ultra Ball — `search` (expensive backup tutor)
- **Mechanics:** Item. **Discard 2 cards**, then search deck for **any Pokémon** to hand.
- **Use:** a backup way to get **Staryu or Mega Starmie ex** when the dedicated tutors aren't in hand
  — expensive (2-card cost), so not the first option in a draw-light deck. The 2-card discard can
  feed Night Stretcher (pitch a spare Water / 2nd Starmie → recover later).
- **Anti-patterns:** **NEVER fetch Cinderace** (opening-hand-only; dead if fetched). Don't pay the
  2-card cost when a free tutor (Mega Signal / Hilda / Poffin) does the job.
- **Disposition:** `fetch-the-wincon` covers the target choice; `never-fetch-cinderace` (§6) guards Cinderace.

### 2× Night Stretcher — `recycle` (recovery backbone)
- **Mechanics:** Item. Put a **Pokémon OR a Basic Energy** from your discard into your hand (**not** Ignition — special Energy).
- **Use:** rebuild after a KO — recover **Staryu** (re-bench → evolve to Starmie) or **Mega Starmie
  ex**, or recover a **Water** when energy-starved. The recovery backbone for the single-attacker
  plan; pairs with Ultra Ball / Lillie's discards.
- **Anti-patterns:** can't recover Ignition — don't count on getting burst energy back.
- **Disposition:** `recycle`-tagged recovery; no deck rule needed.

### 4× Crushing Hammer — `energy_denial` (disruption)
- **Mechanics:** Item. Flip a coin; heads, discard an Energy from 1 of the opponent's Pokémon.
- **Use:** spam **on sight** vs energy-reliant decks to slow their attacker (4 copies ≈ 2 hits);
  target energy on their committed attacker. **Hold it when our own attack will already KO that
  target** — energy denial is redundant on a Pokémon we're removing anyway; save the Hammer for a
  target we can't KO.
- **Disposition:** disruption supporting the race; no general rule fires (coin-flip item). Deck
  nuance "don't hammer a target we're about to KO" → needs a we-have-lethal-on-target signal (§8).

### 1× Hero's Cape — Tool (+100 HP, flexible survival)
- **Mechanics:** Pokémon Tool. +100 HP to the holder.
- **Use:** **default on Mega Starmie ex** (→ 430 HP) to dodge OHKOs, especially vs **Lightning**.
  **Edge cases:** put it on **Staryu or Cinderace** when protecting that Pokémon avoids *losing the
  game*, or to keep **Staryu alive one more turn** so it can evolve to Starmie next turn for the big
  hit. A survival tool for line-continuity, not strictly Mega-only.
- **Disposition:** crossing an OHKO line → HP-breakpoint (general "designed, not yet seeded"); the
  where-to-attach default → deck nuance / Phase B.

### 2× Harlequin — `draw`, `hand_disruption` (disruption-primary)
- **Mechanics:** Supporter. Both players shuffle hands into deck; coin — heads you draw 5 / opp 3, tails you 3 / opp 5.
- **Use:** **best as disruption** — strip a hoarding opponent's built-up hand (you also refill).
  Lower pure-draw value than Lillie's (which doesn't help the opponent); reach for Harlequin when the
  disruption matters.
- **Disposition:** general `dig-before-commit` (draw) covers the setup lift; disruption-timing (vs a
  hoarding opponent) is Posture-ish → note.

### All 18 cards locked — see §4 for combos / sequencing / opening hands / Plan mapping.

## 4 · Combos, sequencing & opening hands

**Sustainable engine (default):** Cinderace opens → attach C → **Turbo Flare** (50 to their Active +
3 Water onto the benched Staryu/Mega Starmie line) → **retreat Cinderace (free, retreat 0)** →
promote Mega Starmie ex (evolve Staryu if needed) → attack (Nebula on the banked 3 Water, or Jetting
Blow on 1). **Conserves Ignition entirely** — this is the deck's bread-and-butter.

**Explosive line (burst):** Salvatore rush-evolves Staryu→Mega Starmie ex + one Ignition (CCC) →
Nebula 210 the same turn. Use to close or leap ahead; spends a finite Ignition.

**Energy economy:** two routes to CCC — **Turbo Flare (3 Water, sustainable)** and **Ignition (1
attach, finite burst)**. Default to Water / Jetting Blow; Ignition→Nebula only when needed, or
greedily with ≥2 Ignition when Nebula gets ahead. Wally's re-power obeys the same logic.

**Supporter priority (one per turn):** play **Pokégear 3.0 first** (Item, free) to find the Supporter
you need, then commit it. In setup, **Salvatore / Hilda** (advance the line) usually outrank
**Lillie's Determination** (raw refill, board-state dependent) — play Lillie's when the hand is
dead/clogged. Hold **Boss's Orders** for the turn its gust pays (a KO, or the defensive stall-gust).

**Fetch & disruption:** fetch priority — **Buddy-Buddy Poffin first** (bench Staryu + thin) → **Mega
Signal** (the payoff) → **Ultra Ball** as an expensive backup for Staryu/Starmie (never Cinderace).
**Crushing Hammer** spams on sight vs energy decks (hold when our attack already KOs that target).
**Night Stretcher** rebuilds the line after a KO. **Harlequin** for hand-disruption.

**Opening hands & turn order:** **Win the coin toss → go SECOND** — this turbo deck wants to attack
turn 1, and the player going first cannot attack T1 (and risks an unusable end-of-turn Ignition).
**Mulligan:** keep essentially any legal hand — Staryu is a Basic and Cinderace opens via
Explosiveness even with no Basic (`keep-a-startable-hand` covers, working as-is).
- **Going first (no T1 attack):** pure development — open Cinderace, Buddy-Buddy Poffin → bench
  Staryu, tutors, attach **Water (never Ignition — it'd discard unused)**.
- **Going second (T1 attack):** Cinderace **Turbo Flare T1** (50 + 3 Water onto the Staryu line) is
  the strong open.

**Plan mapping:**
- **SETUP** — until the line is online (**1 W on Starmie = online → flips to RACE**): open Cinderace,
  bench Staryu, Turbo Flare energy, tutor the payoff.
- **RACE** — attack every turn (Jetting Blow default / Nebula when needed), keep Starmie alive
  (Wally's / Hero's Cape), disrupt (Crushing Hammer / Boss's).
- **STABILIZE** — behind / Starmie threatened: Wally's heal loop, Night Stretcher rebuild, Boss's
  stall-gust.
- **CLOSE** — ahead / lethal: Boss's gust for the last prizes, Nebula for the big KO.
- **Not phase-locked:** **Night Stretcher** rebuilding and **Boss's Orders** — the stall-gust **and**
  the *offensive* gust of an exposed pre-evolution to OHKO it before it evolves into a threat (drag a
  benched basic up, kill it with Cinderace's 50 or Starmie's Jetting Blow 120) — are used across
  **SETUP / RACE / STABILIZE** as the board calls, not reserved for one phase.

## 5 · General-Strategy disposition table (growing)

| General Hypothesis | Disposition | Seed weight | Why (deck-specific reasoning) |
|---|---|---|---|
| `prefer-rush-evolve-tutor` | covers-as-is | — | Salvatore rush-evolves Staryu→Mega Starmie ex |
| `evolve-into-wincon` | covers-as-is | — | Staryu→Mega Starmie ex |
| `hold-clutch-heal` | covers-as-is | — | Wally's Compassion defensive save |
| `fetch-the-wincon` | covers-as-is | — | fetch Mega Starmie ex (Mega Signal / Hilda / Ultra Ball) |
| `dont-bench-multiprize` | covers-as-is | — | Mega Starmie ex (3-prize) is the wincon → exempt; no loose multiprizers to bench |
| `dont-waste-discard-energy` | override / extend | TBD | Ignition is finite + non-recyclable: prefer Water over Ignition **even on the wincon** unless Nebula is needed / ≥2 Ignition in hand → §6 `conserve-ignition-prefer-water` |
| `hold-position-in-setup` | **conflicts** | TBD (condition/raise) | the deck's engine *wants* to retreat Cinderace (retreat 0) to promote the attacker — a planned pivot, not a wasted setup turn → §6 `pivot-cinderace-to-attacker` |
| `use-acceleration` | gap (tag) | — | Cinderace's Turbo Flare isn't tagged `energy_accel` (probe gap) → general rule won't fire; deck uses Role `accel_source` instead. Candidate: add the tag via `function_overrides.json`. |
| `prize-trade-target` / Tactical | covers-as-is | — | Boss's Orders **offensive** gust → KO |
| Boss's **defensive stall-gust** | gap → **deferred** | — | gust a high-retreat energyless wall to deny the opponent's attacker a turn — needs opponent board read + my-not-ready (Posture) → §8 |

## 6 · New deck Hypotheses (drafts — trigger sketches, NOT lambdas yet)

### `conserve-ignition-prefer-water` · seed weight −15 · status: assumed
> Ignition is finite (4, non-recyclable) — even on the win-condition, prefer a Basic Water attach
> (→ Jetting Blow) over an Ignition unless Nebula Beam's 210 / ignore-effects is needed this turn,
> or ≥2 Ignition are in hand and Nebula gets meaningfully ahead.

**Trigger sketch:** at an `ATTACH` whose option is Ignition (`discard_eot`) onto the wincon, when a
reusable Water is available AND Jetting Blow would suffice AND <2 Ignition in hand → penalize.
**Needs new Context signals:** "Jetting Blow suffices this turn" and "Ignition count in hand" — flag §8.

### `pivot-cinderace-to-attacker` · seed weight +30 · status: assumed
> Cinderace (retreat 0) is the accel engine: Turbo Flare, then retreat to promote the Mega Starmie
> ex attacker — a planned pivot, not a wasted setup retreat. Don't penalize retreating Cinderace
> once the Starmie line is ready/energized.

**Trigger sketch:** at a MAIN `RETREAT` option where the Active is Cinderace (`accel_source`/`starter`)
AND a benched wincon is ready → encourage (outweigh `hold-position-in-setup`'s −25).
**Needs new Context signal:** "benched wincon ready" — flag §8.

### `never-fetch-cinderace` · seed weight −60 · status: assumed
> Cinderace can only enter via Explosiveness at game start; fetching it later is a dead card. Never
> select it at a search. (Generalize via the `opener` tag → "don't fetch a setup-only opener.")

**Trigger sketch:** at a `TO_HAND` search whose candidate card is an `opener`-tagged setup-only
Pokémon → strongly penalize. **Reads:** `select_context` TO_HAND, the candidate's `opener` tag.
Prefer the tag form over a hard-coded Cinderace id.

### `prefer-going-second` · seed weight TBD · status: assumed
> This is a turbo deck that wants to attack as early as possible. At the coin-toss "go first?" choice,
> decline — going second lets you attack on your first turn (the player going first cannot), and
> going first wastes a turn and risks an unusable end-of-turn Ignition.

**Trigger sketch:** at `select_context` IS_FIRST (41), penalize the "go first" (YES) option / favor
going second. **Reads:** `select_context`, `option_type`. Likely deck-specific (setup-heavy decks
prefer going first), so keep it in the deck Strategy, not the General Strategy.

## 7 · Roles, Lines, params — current strategy.py (to be revised)

```
roles  = { MEGA_STARMIE_EX: [win_condition, primary_attacker], CINDERACE: [accel_source, starter],
           STARYU: [starter], IGNITION_ENERGY: [accel_source], MEGA_SIGNAL/SALVATORE/HILDA/
           BUDDY_POFFIN/ULTRA_BALL: [tutor], CRUSHING_HAMMER: [disruption], BOSS_ORDERS: [gust],
           WALLYS/NIGHT_STRETCHER: [recovery] }
lines  = [ Line(path=[STARYU, MEGA_STARMIE_EX], payoff=MEGA_STARMIE_EX, role="win_condition") ]
params = { setup_energy_target: 3, search_budget: 0 }
```

## 8 · Open questions / deferred

- **Resolved:** Cinderace never evolved (no Raboot in deck) — opener/accel/wall only, opening-hand
  only, never fetched.
- **Jetting Blow case-B needs an opponent-bench-threat read** → that's the Posture/Scout layer
  (designed, not wired — `docs/scouting.md`). Case-A (KO via HP/weakness) the Tactical Evaluator
  already handles. Flag the snipe-the-wall branch as possibly-deferred until Posture lands.
- **Resolved:** Hero's Cape — default Mega Starmie ex (430 HP); edge-case onto Staryu/Cinderace for
  game-saving survival or line continuity (§3).
- **Resolved:** Crushing Hammer — spam on sight vs energy decks; hold when our attack already KOs the
  target (§3).
- **Resolved:** Energy economy — Turbo Flare (3 Water, sustainable) is the default CCC route;
  Ignition is the finite burst, conserved (see §4/§6).
- **New Context signals the drafted hypotheses need (Phase B / infra):**
  - "Jetting Blow suffices this turn" (a non-Nebula KO available) + "Ignition count in hand" → for
    `conserve-ignition-prefer-water`.
  - "benched wincon ready (energized)" → for `pivot-cinderace-to-attacker`.
  - opponent bench-threat read (Posture/Scout) → for Jetting Blow case-B (snipe-the-wall branch),
    Boss's **defensive stall-gust** (their active/bench energy + retreat costs + my-not-ready), AND
    Boss's **offensive pre-evo gust** (recognising which benched basic evolves into a threat —
    frame-75 "evolves-into-attacker", deferred per [[snipe-threat-two-signals]]).
  - "we have lethal on this target" → for Crushing Hammer (don't hammer a Pokémon we're about to KO).
  - HP-breakpoint ("would +100 HP dodge an OHKO") + line-continuity → for Hero's Cape attach target.
  Until these land, those rules may be partial/deferred — note at authoring time.
