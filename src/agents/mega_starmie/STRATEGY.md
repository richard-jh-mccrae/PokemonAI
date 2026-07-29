# mega_starmie — Playing Doctrine

> Phase-A deliverable of `/deck-genie`. The human-readable strategy the deck plays; the executable
> `strategy.py` is generated from this **after sign-off** (ADR-0017). Build on the
> [General Strategy](../../../docs/general-strategy.md): reuse, override, or extend — don't restate.

**Status:** Phase A doctrine **complete**; Phase B (executable `strategy.py`) **deferred** · **Last grilled:** 2026-06-30 · **Author:** deck-genie + Richard

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped
- [x] Phase 1 overview confirmed
- [x] Phase 2 research synthesised + user-confirmed (confidence LOW — Cinderace build web-uncovered)
- [x] Phase 3 card-by-card: 18/18; opening hands + Plan mapping locked (§4)
- [x] Phase 4 General-Strategy disposition + hypothesis drafts complete
- [x] Phase 5 — doctrine accepted as the deliverable; **Phase B deferred** (user, 2026-06-28)
- [~] Phase 6 — executable `strategy.py`: the 3 residual deck hypotheses authored **test-first +
  gated** (`prefer-going-second`, `never-fetch-cinderace`, `conserve-ignition-prefer-water`); full
  suite green (441), Playability deferred to CI (`kaggle_environments` not local)
- [x] **Recipient-first (2026-06-30, TDD):** `develop-turbo-flare-recipient` (deck) +
  `fetch-base-before-stranded-payoff` (general) — the "find & bench a Staryu while Cinderace attacks"
  blunder (§4 HARD RULE, §6). Sound-oracle only; probabilistic own-deck estimate deferred (§8)

Cards still to grill: none — all 18 locked. Open questions / deferred infra: see §8.
**To resume Phase B later:** `/deck-genie mega_starmie` reads this doc + checklist and authors the
gated `strategy.py` from the locked doctrine.

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
- **Disposition:** `open-the-accelerator` + `advance-the-accel-pieces` (general; folded from the
  deck rules 2026-07-02) cover opening/accel.
  **CONFLICT: `hold-position-in-setup`** penalizes the *intended* retreat-to-promote → override (§6).
  Never-fetch → §6. Note: Cinderace is tagged `energy_accel` (gap closed 2026-07-02) though general
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
- **Disposition:** the gust **decisions** (whether to play it, which benched mon) are **NOT supported
  today** — `prize-trade-target` is a Tactical prize-preference over the *current* Active (not a
  Hypothesis), and the gust decisions happen before the gust resolves, so Tactical can't see "gust X up
  → KO X" at the point of choosing. The gust (whether-to-play **and** which benched mon)
  is **shipped** as the general Boss's Orders doctrine (ADR-0022, 2026-06-29): the `_can_ko` lethal
  oracle generalizing Tactical to any defender, a whether-to-play gate (+ lethal Tactical term), and
  the **SWITCH(3)** target-select (KO + prizes + denial + the tier-5 stall). Sniping an evolving pre-evo
  with our own attack → general `snipe-the-evolving-threat` (covers the DAMAGE target).

### 2× Hilda — `search` (targeted setup)
- **Mechanics:** Supporter. Search deck for an **Evolution Pokémon AND an Energy**, both to hand.
- **Use:** the targeted setup engine — fetch **Mega Starmie ex + an Energy** in one card. High
  Supporter priority in setup over raw draw.
- **Disposition:** general `dig-before-commit` + `play-a-tutor-for-the-unfound-wincon` (general;
  folded from deck `tutor-the-wincon`) cover the lift; `fetch-the-wincon` governs the pull.

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
- **Disposition:** "Pokégear before your Supporter" is **structural**, not `dig-before-commit`: that
  rule lifts digs above the *attach/attack*, but a Supporter is *also* a `search`/`draw` card, so it
  collected the same bonus — it never ordered the Item-dig vs the Supporter. The Pilot's
  `_finish_turn_last` tiers a Supporter as a commitment (tier 1) **below** a free Item dig (tier 0), so
  Pokégear resolves first and may upgrade which Supporter you commit. (The `dig-before-commit` +20 the
  Supporter still gets is harmless — the tier decides the order.)

### 4× Mega Signal — `search` (payoff tutor)
- **Mechanics:** Item. Search deck for a **Mega Evolution ex** (→ Mega Starmie ex), reveal, to hand.
- **Use:** the dedicated wincon tutor — primary way to find Mega Starmie ex. High setup priority.
- **Disposition:** `fetch-the-wincon` + `play-a-tutor-for-the-unfound-wincon` (both general; the
  latter folded from deck `tutor-the-wincon`) cover it.

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
- **Disposition:** `fetch-the-wincon` covers the target choice; `dont-fetch-the-setup-only-opener`
  (general; folded from deck `never-fetch-cinderace`, §6) guards Cinderace.

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

### 1× Hero's Cape — **ACE SPEC** Tool (+100 HP; one-per-deck, irreplaceable) · tag `tool`
- **Mechanics:** Pokémon Tool, **ACE SPEC** (engine `aceSpec=True`; rule: max 1 ACE SPEC per deck —
  `docs/rules.md` Appendix 3). +100 HP to the holder (Mega Starmie ex → 430). The deck's **only**
  ACE SPEC, a hard 1-of, and **unrecoverable** once lost (Night Stretcher returns a Pokémon or Basic
  Energy, **not** a Tool; no 2nd copy is legal). Tools **transfer on evolution** (verified
  `rulebook.txt:125`), so a Cape on Staryu carries up to Mega Starmie ex.
- **DOCTRINE REVERSED 2026-06-30 (ADR-0028) — deploy proactively; do NOT hold for a breakpoint.** The
  old "hold = safe, wait for the OHKO-dodge" doctrine was wrong for THIS deck: it runs **six** hand-shuffle
  Supporters (4× Lillie's + 2× Harlequin), so a held Cape's most likely fate is the agent **shuffling its
  own irreplaceable ACE SPEC back into the deck** (observed: ep82866415 f43/f48). The Cape goes down on the
  body that carries the game; the breakpoint is just one trigger now.
- **WHEN — deploy when ANY of:** (a) the **survival-turns** at-risk math says +100 buys a body a full extra
  turn (`ceil(hp / incoming)` rises by ≥1 — "survives 2 turns instead of 1"); (b) a `shuffle_hand` Supporter
  is in hand this turn (deploy before it can shuffle the Cape away); (c) the wincon is your **Active attacker**
  and there's no reason to hold. Two drivers: the **anti-shuffle floor** (high-frequency) + **at-risk value**
  (refinement).
- **TARGET (wincon always priority):** **(1)** the **Active Mega Starmie ex** if the Cape saves it (gains a
  turn) or as the anti-shuffle default; **(2)** if the Active is **doomed even at +100**, the **next-in-line
  we'll promote** (ready benched Mega → a Staryu we can evolve → staller) — the Cape rides up the line;
  **(3)** a benched **Staryu being sniped down** (Jetting Blow 50/turn — the snipe-survival case, ep#2);
  **(4)** a defensive **wall** (re-emerged Cinderace) only if +100 buys it a turn AND no wincon need outranks.
- **Predict the threat:** incoming = the opponent's best **affordable** attack next turn (their predicted
  promotion, from attached Energy + attack cost), not just their current Active; a benched body counts only
  bench-snipe (snipe-only — we don't assume the opponent gusts it up).
- **Anti-patterns:** Cape a body the opponent KOs **even at +100** (here it IS never — wasted); override a
  lethal **KO** with a positional deploy (the KO always wins); fritter on a spent Cinderace **when a wincon
  body needs it** (a wall *can* earn it only when the math gives it a survival turn and nothing better wants it).
- **Disposition (BUILT 2026-06-30/07-01, ADR-0028, test-first `/tdd`; full suite 694 passed):** promoted `baseline_tool.py` →
  a **Tool Doctrine** (`doctrines/doctrine_tool.py` + `ToolMixin`) carrying the closed-form board-math
  (`opp_best_attack_vs` next-attacker prediction, `survival_turns`, the target picker, our-next-promotion
  predictor). **Belt-and-suspenders:** positive `deploy-*` rungs score the picked attach > 0 (→ tier 2,
  before the tier-3 shuffle — the root-cause fix: a ≤0 attach drops to tier 4 *below* the shuffle) **+** new
  `hold-irreplaceable-tool-dont-shuffle` (mirror of `hold-wincon-dont-shuffle`, for the no-good-target case).
  **Reconciled weights:** `deploy-hp-tool-on-breakpoint` **removed** (subsumed by survival-turns);
  `save-tool-for-the-attacker` (−15) + `protect-ace-spec-tool` (−10) **re-scoped** to fire only on a body the
  picker rejected (a spent/off-line opener), never a wincon **line-piece** (the −25-on-bench-Staryu mis-fire
  that broke ep#2). New infra: `CardStat.benchSnipeDamage` (wire `parse_attack_bench_snipe`). All **general**
  (keyed on `aceSpec`/`hpBonus`/`tool` + wincon Roles), not deck-hardcoded.

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

**Recipient-first — HARD RULE (2026-06-30, TDD).** Turbo Flare loads the **Bench**, so it needs a
**recipient** — a benched Staryu (→ the future Mega Starmie ex) — or its 3-Water acceleration is
wasted. While Cinderace (the accelerator) is Active with a **bare Bench** (no Line recipient),
*developing one is the top setup priority*: play a Staryu, play Buddy-Buddy Poffin, or — at a search —
**fetch the deployable base (Staryu) over a stranded Mega** you can't yet evolve. Enshrined as
**`develop-the-accel-recipient`** (general; folded from deck `develop-turbo-flare-recipient`) + the
general **`fetch-base-before-stranded-payoff`** (§6). It
is **behaviour-neutral** on the held-bencher cases (those already sequence the bench before the
deferred attack via `keep-a-bench`/attack-last — live-retest-confirmed) and **endorses development
only** (never blocks the attack — a turn with no Staryu to find still Turbo Flares for the 50). Needs
**no deck deduction**: the fetch picks among *revealed* options; the develop reads the *visible* board
(the probabilistic own-deck estimate is a separate, deferred feature — §8).

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

**Promote after a KO** (general rules, no deck code): bring up a **ready benched Mega Starmie ex**
first (`promote-the-ready-wincon`, 40); else promote **Cinderace** as a disposable wall/staller
(`promote-the-staller`, 20 — fires on the `opener` tag) to keep a bare Staryu safe on the Bench and
retreat it free once you can evolve; never strand a bare pre-evolution you can't evolve this turn.

**Sequencing is structural, not a weight:** "attack last" (develop everything first, then the
turn-ending attack) is enforced by the Pilot's `_finish_turn_last`, so the old chip-penalty
hypotheses (`build-before-attack`, `dont-chip-with-a-doomed-active`) were **removed** from the
General Strategy — don't reference them. `dig-before-commit` now also fires in RACE (dig before the
turn-ending attack, not only in SETUP).

## 5 · General-Strategy disposition table (growing)

> **2026-07-02 FOLD — the deck now ships ZERO Hypotheses.** Every remaining deck rule moved into
> the General Strategy (same trigger + weight; score-equality proven by `tools/sim/score_diff.py`
> over 1869 corpus frames, 0 divergent). The deck's opt-in is its DECLARATIONS (Roles / Lines /
> params); per-deck tuning still works by id via `tuned.json` (ADR-0009).
>
> | deck rule | → general rule | home |
> |---|---|---|
> | `open-cinderace` | `open-the-accelerator` | baseline_opening |
> | `accel-into-main` | `advance-the-accel-pieces` | baseline_energy |
> | `develop-turbo-flare-recipient` | `develop-the-accel-recipient` | baseline_bench |
> | `tutor-the-wincon` | `play-a-tutor-for-the-unfound-wincon` | doctrine_fetch |
> | `never-fetch-cinderace` | `dont-fetch-the-setup-only-opener` (+ NEW structural guard `card_stranded_evolution`) | doctrine_fetch |
> | `conserve-ignition-prefer-water` | `conserve-discard-energy-prefer-basic` | baseline_energy |
> | `prefer-going-second` | `params["preferred_start"]="second"` + `honor-preferred-start` | baseline_opening |

> **ADR-0075 migration (2026-07-28).** The Set-Up ACTIVE seam is now ONE deck declaration —
> `Strategy.starter_priority` in this deck's `strategy.py`, read by the general
> `open-the-declared-starter`. Rows above naming `open-the-accelerator`,
> `open-the-item-lock-starter`, `dont-open-multiprize-active`, `dont-open-with-the-engine`,
> `start-solrock-over-lunatone` or the `starter` Role are **history** — all are deleted. See
> [ADR-0075](../../../docs/adr/0075-the-setup-active-pick-is-one-deck-declaration.md).

| General Hypothesis | Disposition | Seed weight | Why (deck-specific reasoning) |
|---|---|---|---|
| `prefer-rush-evolve-tutor` | covers-as-is (refined) | — | Salvatore rush-evolves Staryu→Mega Starmie ex; now gated on `line_preevo_in_play` (stands down with no Staryu in play to evolve) |
| `evolve-into-wincon` | covers-as-is | — | Staryu→Mega Starmie ex |
| `hold-clutch-heal` | covers-as-is | — | Wally's Compassion defensive save |
| `fetch-the-wincon` | covers-as-is | — | fetch Mega Starmie ex (Mega Signal / Hilda / Ultra Ball) |
| `dont-bench-multiprize` | covers-as-is | — | Mega Starmie ex (3-prize) is the wincon → exempt; no loose multiprizers to bench |
| `dont-waste-discard-energy` | covers + general sibling | — | wincon exemption kept; the even-on-the-wincon conserve is now general `conserve-discard-energy-prefer-basic` (folded 2026-07-02) |
| `hold-position-in-setup` | covers-as-is (resolved) | — | Cinderace-pivot conflict **resolved** by general **`retreat-to-ready-attacker`** (60 > 25): retreat the spent non-wincon Active into the ready benched wincon. No deck rule needed. |
| `use-acceleration` | gap **CLOSED** 2026-07-02 | — | Cinderace now tagged `energy_accel` (function_overrides). Score-equal for this deck: `use-acceleration` is PLAY-gated (a Stage-2 Cinderace has no play-from-hand option) and `fetch-the-support` carries a stranded-evolution guard (a dead grab is never endorsed). Vocabulary correct for future rules/decks. |
| `develop-turbo-flare-recipient` (deck) | **folded → general** `develop-the-accel-recipient` 2026-07-02 | +20 | accelerator Active + bare Bench → endorse developing a Line recipient (Staryu / `bench_fill`) so Turbo Flare has a target; enshrines #3, behaviour-neutral over `keep-a-bench`. New signal `Board.accel_recipient_missing` |
| `fetch-base-before-stranded-payoff` (general) | **shipped** 2026-06-30 (TDD) | +20 | grab the deployable base over an un-evolvable payoff (no base in play/hand); fixes the verified Ultra-Ball Mega-over-Staryu trap. New signal `Board.wincon_base_deployable` |
| Boss's gust (offensive KO + stall) | **shipped** 2026-06-29 (ADR-0022) | `gust-for-the-ko` 50, `gust-for-the-stall` 10 | general gust doctrine: `_can_ko` oracle → whether-to-play + lethal (Tactical) + SWITCH(3) target-select (KO+prizes+denial) + tier-5 stall. Refinements pending: condition/draw guards, 4-mechanic split |
| `snipe-the-evolving-threat` / `snipe-the-weakest` | covers-as-is | — | Jetting Blow's 50 bench-snipe target (evolving pre-evo / lowest-HP) — forward-evolution index, ADR-0020 |
| Boss's **gust-target** (stall + offensive pre-evo) | **shipped** → general (ADR-0022) | — | not deck-specific: the general Boss's Orders doctrine — SWITCH(3) target-select (KO+prizes+denial+forward-denial) + tier-5 stall |
| `power-up-attacker` | covers-as-is (refined) | — | now gated on `attach_target_needs` — won't pile surplus Energy on an already-online Mega Starmie ex (1 W = Jetting Blow) |
| `promote-the-ready-wincon` / `promote-the-staller` | covers-as-is | — | promote-after-KO: ready Mega Starmie ex first (40), else Cinderace (`opener`) as a staller (20); no deck rule |
| `save-tool-for-the-attacker` / `protect-ace-spec-tool` | **re-scoped** (ADR-0028) | — | Tool Doctrine reversal 2026-06-30: these now fire ONLY on a picker-rejected off-line body, never a wincon line-piece; the Cape **deploys proactively** (survival-turns), it is no longer held (§3, Hero's Cape) |
| `deploy-hp-tool-on-breakpoint` | **removed** (ADR-0028) | — | subsumed by the Tool Doctrine's survival-turns deploy (covers Active + bench + doomed→successor, not just the Active OHKO-dodge) |
| `build-before-attack`, `dont-chip-with-a-doomed-active` | **removed** | — | superseded by the Pilot's structural `_finish_turn_last` ("attack last") — no longer weights |

## 6 · New deck Hypotheses (drafts — trigger sketches, NOT lambdas yet)

### `develop-turbo-flare-recipient` · +20 · **FOLDED → general `develop-the-accel-recipient` (baseline_bench), 2026-07-02**
> Turbo Flare attaches its 3 Basic Energy to **Benched** Pokémon only — with no Staryu (or benched
> Mega Starmie ex) on the Bench the acceleration is wasted. While the accelerator (Cinderace) is the
> Active and the Bench has no Line recipient, developing one is the **top setup priority**.

**Implemented** as a deck Hypothesis on a new general Pilot signal **`Board.accel_recipient_missing`**
(my Active is an `accel_source`-Role Pokémon AND no Line member — pre-evo or payoff — is benched).
**Trigger:** a `PLAY` of a Line pre-evolution (`card_is_line_preevo` = Staryu) or a `bench_fill` card
(Buddy-Buddy Poffin) while `accel_recipient_missing` and the Bench isn't full. **Behaviour-neutral**
on the cases the general `keep-a-bench` (+60) / `prefer-bench-fill-first` already cover — live retests
confirm Staryu-in-hand and Poffin-in-hand already bench *before* the deferred attack — so it rides
alongside them to **enshrine + regression-lock** the doctrine and add trace legibility. Positive
endorsement of development **only** (never penalises the attack), so a turn with no Staryu to find
still Turbo Flares for the 50. The **fetch** half is the general rule below.

### `fetch-base-before-stranded-payoff` (GENERAL — `doctrine_fetch.py`) · weight +20 · status: testing · **IMPLEMENTED 2026-06-30 (TDD)**
> At a search, when the evolved payoff is NOT yet deployable (no Line pre-evolution in play **or
> hand**), prefer fetching the deployable **base** over the payoff — a fetched Mega with no Staryu to
> evolve from is a stranded dead card (and starves Turbo Flare of a recipient).

**General** (any evolution deck inherits it), on a new Board signal **`wincon_base_deployable`** (a
Line pre-evo is in play or hand). Lifts the base ABOVE `fetch-the-wincon` (+30) when the base is
missing; **additive** (never zeroes the payoff) — if only the payoff is on offer you still grab it.
The inverse of `prefer-payoff-over-preevo`. **Fixes the verified trap:** Ultra Ball [Staryu, Mega],
bare Bench, no Staryu in play/hand — was Mega 35 > Staryu 30 (grabbed the un-evolvable Mega); now
Staryu 50 > Mega 35. Needs **no deck deduction** — it picks among the search's *revealed* options.

### `conserve-ignition-prefer-water` · −40 · **FOLDED → general `conserve-discard-energy-prefer-basic` (baseline_energy), 2026-07-02**
> Ignition is finite (4, non-recyclable) — even on the win-condition, prefer a Basic Water attach
> (→ Jetting Blow) over an Ignition unless Nebula Beam's 210 / ignore-effects is needed this turn.

**Implemented** via two new (general, additive) Pilot signals built test-first:
`CardStat.minCostDamage` (damage of the cheapest-cost attack — Jetting Blow's 120, not Nebula's 210)
and `Board.active_cheap_attack_kos` (closed-form: my Active's cheap attack KOs the opp Active,
weakness-doubled — mirror of `active_doomed`). **Trigger:** `ATTACH` of Ignition (`discard_eot`) onto
the **Active** wincon, when a reusable Water is in hand AND `active_cheap_attack_kos`. The greedy
"≥2 Ignition" exception is **subsumed** — if the cheap attack KOs, Nebula never gets ahead, so no
count signal is needed. Stands down when the cheap attack can't KO (Nebula genuinely needed).

### ~~`pivot-cinderace-to-attacker`~~ — **COVERED** by general `retreat-to-ready-attacker` (60); draft dropped 2026-06-28 (forward-evolution / blunder-round reconciliation).

### `never-fetch-cinderace` · −60 · **FOLDED → general `dont-fetch-the-setup-only-opener` (doctrine_fetch, + structural `card_stranded_evolution` guard), 2026-07-02**
> Cinderace can only enter via Explosiveness at game start; fetching it later is a dead card. Never
> select it at a search. (Generalize via the `opener` tag → "don't fetch a setup-only opener.")

**Trigger sketch:** at a `TO_HAND` search whose candidate card is an `opener`-tagged setup-only
Pokémon → strongly penalize. **Reads:** `select_context` TO_HAND, the candidate's `opener` tag.
Prefer the tag form over a hard-coded Cinderace id.

### `prefer-going-second` · −30 · **FOLDED → `params["preferred_start"]="second"` + general `honor-preferred-start` (baseline_opening), 2026-07-02**
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

- **Recipient-first shipped (2026-06-30, TDD), with one deferred dependency.** `develop-turbo-flare-
  recipient` + `fetch-base-before-stranded-payoff` close the "find & bench a Staryu while Cinderace
  attacks" blunder (the verified Ultra-Ball Mega-over-Staryu trap + the bare-Bench framing). They rely
  on the **sound** own-deck model only (`OwnCardModel`, certain-or-silent): the fetch picks among
  *revealed* options, the develop reads the *visible* board, and the speculative dig stays bounded by
  the sound `dont-search-an-empty-deck`. **Deferred (user concern, 2026-06-30):** a **probabilistic**
  own-deck-content estimate ("a Staryu *probably* still remains" — for the 2nd-Buddy-Poffin-might-whiff
  call) is a **separate feature**, not needed for this fix. Tracked as a follow-up; see the
  [[sound-deck-emptiness-oracle]] memory + the refuted ep82524455-f6 correction.
- **Resolved:** Cinderace never evolved (no Raboot in deck) — opener/accel/wall only, opening-hand
  only, never fetched.
- **Jetting Blow bench-snipe targeting — RESOLVED.** The forward-evolution index shipped (ADR-0020):
  provider `forward_max_damage` + Context `target_forward_damage` + general `snipe-the-evolving-threat`
  (18), under `snipe-the-threat` (20) and over `snipe-the-weakest` (15), now pick the snipe target.
  Residual: the Jetting-Blow-vs-Nebula **attack selection** on an un-KO-able wall is the **Tactical
  Evaluator's** job, not a positional weight.
- **Designed — comprehensive GENERAL Boss's Orders strategy** (grilled 2026-06-29, ADR-0022; **build pending**; user directive 2026-06-28) — Boss's is
  powerful in nearly every deck, so its gust-target doctrine (offensive pre-evo gust, defensive
  stall-gust, reach-a-prize KO) belongs in the General Strategy, built AFTER this reconciliation +
  implementation. Will consume the opponent read (Posture/Scout) + the shipped forward-evolution index.
- **Resolved → REVERSED 2026-06-30 (ADR-0028):** Hero's Cape is no longer *held for a breakpoint* — it
  **deploys proactively** (survival-turns board-math + anti-shuffle floor), because the deck's six
  hand-shuffle Supporters made "hold = safe" false (it shuffled its own ACE SPEC away). Target picker +
  next-attacker prediction in §3; Tool Doctrine build pending.
- **Resolved:** Crushing Hammer — spam on sight vs energy decks; hold when our attack already KOs the
  target (§3).
- **Resolved:** Energy economy — Turbo Flare (3 Water, sustainable) is the default CCC route;
  Ignition is the finite burst, conserved (see §4/§6).
- **New Context signals the drafted hypotheses need (Phase B / infra):**
  - "Jetting Blow suffices this turn" (a non-Nebula KO available) + "Ignition count in hand" → for
    `conserve-ignition-prefer-water`.
  - "benched wincon ready (energized)" → for `pivot-cinderace-to-attacker`.
  - **Boss's Orders gust-TARGET selection** (which benched Pokémon to drag up — offensive pre-evo
    gust + defensive stall-gust) → **specified in the general Boss's Orders doctrine** (grilled
    2026-06-29, ADR-0022; build pending); not a mega_starmie-specific rule. (forward-evolution index
    already shipped; engine/replaceability-denial + proactive use still need the opponent read.)
  - "we have lethal on this target" → for Crushing Hammer (don't hammer a Pokémon we're about to KO).
  - HP-breakpoint ("would +HP dodge an OHKO") → ✅ landed as general `deploy-hp-tool-on-breakpoint`
    (`CardStat.hpBonus` + `incoming_active_damage`). Line-continuity (a Cape on Staryu transfers up
    the evolution line — choosing the attach target with that in mind) is still open.
  Until these land, those rules may be partial/deferred — note at authoring time.

## 9 · Reconciliation log + open items (2026-06-28, vs forward-evolution index + blunder round)

**Resolved this session** (general rules now cover former deck drafts/deferrals):
- `pivot-cinderace-to-attacker` → general `retreat-to-ready-attacker` (60); `hold-position-in-setup`
  conflict **resolved**.
- Bench-snipe targeting (Jetting Blow 50) → `snipe-the-evolving-threat`/`-weakest` + forward-evolution
  index (ADR-0020). Boss's **gust-target** selection → now **designed** as the general Boss's Orders doctrine (grilled 2026-06-29, ADR-0022; build pending).
- Hero's Cape = **ACE SPEC** doctrine written (§3): reactive deploy on an HP breakpoint, default the
  wincon. WHERE → `save-tool-for-the-attacker`; WHEN → HP-breakpoint model (general, not-built).
  **No standalone general ace-spec rule** (ACE SPECs too heterogeneous; scarcity = deckbuild principle);
  at most a small `aceSpec` extra-reluctance weight bump.

**Rulings (2026-06-28):** Hero's Cape **reactive for now** (proactive-vs-Lightning needs Posture).
`save-tool-for-the-attacker` is **too crude — the right Tool target/timing depends 100% on the tool's
function** (a +HP defensive Cape wants breakpoint timing; a damage/utility Tool wants a different
target). → fold into the general Tool / HP-breakpoint work, don't leave it a blanket −15.

**Status / OPEN:**
1. ✅ DONE (Phase B, TDD 2026-06-28): **`conserve-ignition-prefer-water`** + **`prefer-going-second`**
   authored test-first + gated (see §6; `tests/agents/test_mega_starmie_triggers.py`).
2. ✅ DONE: **`never-fetch-cinderace`** kept as a deck rule (user ruling) and implemented — the general
   `prefer-wincon-line-piece` only *prefers* Staryu, it doesn't forbid a strictly-dead Cinderace fetch.
3. ✅ DONE: stale `tuned.json` keys for the removed `build-before-attack` / `dont-chip-with-a-doomed-active`
   cleaned (suite-green); doc folds applied — §4 now states "attack last is structural" + the
   promote-after-KO note, and §5 records the `power-up-attacker` (`attach_target_needs`) and
   `prefer-rush-evolve-tutor` (`line_preevo_in_play`) gating refinements + the removed chip rules.
4. Future **general** work (separate, after reconciliation + Phase B): comprehensive **Boss's Orders**
   strategy (**designed** 2026-06-29, ADR-0022; build pending); the **damage**-boost OHKO-line model
   (Maximum Belt et al.); per-tool-aware
   `save-tool-for-the-attacker` (target/timing by tool function — the line 469 ruling). (The HP-boost
   breakpoint model is now done — see item 7.)
5. **Phase B** largely shipped (test-first + gated): the 3 deck residual hypotheses
   (`prefer-going-second`, `never-fetch-cinderace`, `conserve-ignition-prefer-water`); existing
   `open-cinderace` / `accel-into-main` / `tutor-the-wincon` retained.
6. ✅ DONE (Hero's Cape deep dive, TDD 2026-06-28): general `protect-ace-spec-tool` (ACE SPEC
   reluctance), on new signals `CardStat.aceSpec`, `CardStat.minCostDamage`,
   `Board.incoming_active_damage` / `active_cheap_attack_kos`.
7. ✅ DONE (fully-general "+HP tool" breakpoint model, TDD 2026-06-28): new `CardStat.hpBonus` parses
   a Tool's flat HP from its skill text (`_parse_tool_hp_bonus`, unconditional "+N HP" only — restricted
   tools → 0, never over-credited); new **general** `deploy-hp-tool-on-breakpoint` (+50) reads it +
   `Board.incoming_active_damage`, so ANY unconditional +HP Tool / ANY weakness inherits the breakpoint
   deploy. The deck-specific `deploy-heros-cape-on-breakpoint` (hardcoded +100) was removed as subsumed.
   Live-engine verified: Hero's Cape → hpBonus 100, Cynthia's Power Weight → 0. Remaining general work:
   the comprehensive Boss's Orders strategy (**designed** 2026-06-29, ADR-0022; build pending); the
   **damage**-boost OHKO-line model (Maximum Belt et al.).
