# dragapult_ex — Playing Doctrine

> Phase-A deliverable of `/deck-genie`. The human-readable strategy the deck plays; the executable
> `strategy.py` is generated from this **after sign-off** (ADR-0017). Build on the
> [General Strategy](../../../docs/general-strategy.md): reuse, override, or extend — don't restate.

**Status:** `shipped` (Phase B complete — strategy.py + infra built, all gates green; human commits) ·
**Last grilled:** 2026-07-03 · **Author:** deck-genie + Richard

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped
- [x] Phase 1 overview confirmed (spread + disruption)
- [x] Phase 2 research synthesised (high confidence; 0 card-fact conflicts)
- [x] Phase 3 card-by-card: 21/21 cards locked
- [x] Phase 4 General-Strategy disposition complete
- [x] Phase 5 signed off (`/tdd go! build`) → **Phase B COMPLETE** (strategy.py + A/B/C/D infra + 3 deck rules;
      all gates green — see §8 "Phase B COMPLETE"). Human commits.

**Grill outcomes (all 7 branches resolved):**
1. Phantom Dive spread → **matchup-switched** marginal-value placement; **online at FP `Ready(energy=2)`**.
2. Munkidori Adrena-Brain → **value-compare finish vs heal**; {D} via Crispin's free attach (manual stays on Dragapult).
3. Fezandipiti + Meowth → **positive plan-gated triggers** override `dont-bench-multiprize`; Fezandipiti benched entering the grind.
4. Risky Ruins → **proactive + bench-our-Basics-first + soft net gate**.
5. Crushing Hammer → **value-targeted before lethal** (single-attach attacker).
6. `preferred_start="first"`; **{D} = normal energy** (no discard-protection bump).
7. Unfair Stamp (ACE SPEC) → **hold for a max-impact post-KO turn**; staples covered-as-is.

Resolved open questions: Tera benched-immunity handled by the Pilot (§3 Dragapult); mulligan × Explosiveness
covered by `keep-a-startable-hand`. Carried to Phase 6: Phantom Dive select encoding + `gust_ko` remaining-HP (§8).

## 1 · Overview  (DRAFT — awaiting confirmation)

- **Archetype:** Dragapult ex **spread + disruption**. Phantom Dive is the damage engine (big hit to the
  Active *plus* 6 free damage counters spread across the opponent's Bench); Munkidori + Risky Ruins +
  Fezandipiti convert that distributed chip into prizes, while Crushing Hammer / Judge / Boss slow and
  redirect the opponent.
- **Win condition:** take 6 prizes by *pre-loading* KOs. Phantom Dive (200 Active + 6 bench counters) both
  KOs the Active and softens 1-3 benched targets into range; then **Munkidori** slides counters to finish
  a benched mon, **Fezandipiti** Cruel Arrow snipes 100 anywhere, and **Boss's Orders** drags the softened
  target Active for the last-prize KO. Prize math: Dragapult ex / Meowth ex / Fezandipiti ex are 2-prize
  liabilities; the rest are 1-prize. Dragapult's 320 HP + Tera bench-immunity keep our own prizes off the
  table.
- **Line:** **Dreepy → Drakloak → Dragapult ex** (Stage 2, single evolution family). **Online at:** FP
  (Fire+Psychic = 2 energy) for Phantom Dive; C (1 energy) for Jet Headbutt (70) as a cheap early poke.
- **Main attacker:** Dragapult ex (320 HP, Tera, no weakness). **Finishers/tech attackers:** Fezandipiti
  ex (Cruel Arrow — 100 to any Pokémon, ignores bench W/R), Munkidori (Mind Bend 60 + Confuse; and its
  *ability* is the real value).
- **Supporting Pokémon:** **Cinderace** ×4 = opener (Explosiveness → Active during setup) + energy engine
  (Turbo Flare → 3 Basic Energy onto the Bench); **Drakloak** = mid-line dig (Recon Directive); **Meowth
  ex** ×1 = one-shot Supporter tutor on bench-entry; **Munkidori** ×2 = counter-mover / healer / confuse.
- **Engine (draw/search):** Lillie's Determination (draw 6/8), Judge (draw 4 + disrupt), Drakloak Recon
  (dig 2 pick 1), Fezandipiti Flip-the-Script (draw 3 after a KO), Poké Pad (non-rulebox Pokémon search),
  Ultra Ball (any Pokémon, discard 2), Buddy-Buddy Poffin (≤70 HP Basics → Bench = **Dreepy only** here).
- **Acceleration:** Cinderace Turbo Flare (3 Basic Energy to Bench), Crispin (2 Basic Energy diff types,
  attach 1 / hand 1). **Disruption:** Crushing Hammer (coin-flip energy denial), Judge / Unfair Stamp
  (hand disruption), Boss's Orders (gust), Risky Ruins (bench-chip stadium), Munkidori Mind Bend (Confuse).
  **Recovery:** Night Stretcher (Pokémon or Basic Energy from discard).
- **Energy:** 9 Basic — **4 Fire, 3 Psychic, 2 Darkness**. Fire+Psychic power Phantom Dive; Darkness feeds
  Munkidori's Adrena-Brain ability (needs {D} attached) and Fezandipiti. Very low count — Cinderace/Crispin
  do the heavy lifting so the deck runs lean on energy.
- **User context:** _(none supplied yet — folding in on confirmation)._

## 2 · Research synthesis (cited)

_High confidence; 7 angles · 20 sources · 18/20 claims survived adversarial verification · 4 card
deep-dives · 10 trainers. **Web-vs-engine card-fact conflicts: NONE** — every stat/text matches the
engine. Raw output: `tasks/wno2xxdj6.output`._

**Gameplan — two-phase SPREAD → CONVERT prize engine** (a comeback/tempo damage-mapper, not aggro).
*Phase 1 (spread):* land Dreepy→Drakloak→Dragapult ex by ~T3, Phantom Dive = 200 to Active **+ 6 counters
(60) placed anywhere on the opp Bench** — rarely KOs benched mons, *pre-loads* them. *Phase 2 (convert):*
finish softened bench with (a) **Munkidori** Adrena-Brain (move ≤3 counters ours→theirs, needs {D}),
(b) **Fezandipiti** Cruel Arrow (flat 100 to ANY, no W/R on bench), (c) **Boss's Orders** gust the corpse
Active (prizes only come from KOing the Active). *Layered disruption* buys convert-tempo: Crushing Hammer,
Judge/Unfair Stamp, Risky Ruins passive chip. **Cinderace** = energy engine off the thin 9-energy base;
**Fezandipiti** Flip-the-Script refuels the grind.

**Key combos:**
- Phantom Dive spread **+ Munkidori move-3** = a benched KO the opponent can't answer (Munkidori = the
  Dusknoir substitute this list runs instead).
- Phantom Dive **+ Cruel Arrow** (100 to any, no W/R bench) = snipe a bench target softened to ≤100.
- Softened bench **+ Boss's Orders** = gust corpse Active → prize.
- Risky Ruins (20/opp-bench-entry) **+ spread + finisher** = compounding chip, lethal a turn early.
- **Munkidori REVERSE** — peel counters OFF our own damaged Dragapult/Drakloak → onto opp = ~30 HP/turn
  heal on the win-con line; **wins the mirror** (residual Phantom Dive snipes our benched Drakloaks).
- Cinderace Explosiveness → Turbo Flare = power Dragapult; **Crispin** assembles the missing color.
- Meowth ex → tutor Boss's → gust same turn (ability, so the fetched Supporter still plays).
- Opp KO → Unfair Stamp (draw 5 / opp to 2) **+** Fezandipiti Flip-the-Script (draw 3) — shared trigger.

**Sequencing ladder (confirmed):** free draw/dig first (Recon, Cinderace/Meowth abilities) → Items
(Poké Pad → Poffin → Ultra Ball → Night Stretcher/Hammer) → the one Supporter → evolve/attach → **attack
last.** Carve-outs: **use Drakloak Recon BEFORE evolving it** (ability gone after); **Poké Pad before Ultra
Ball** (reserve the discard-2 for Rule-Box grabs); **fire Munkidori BEFORE attacking & BEFORE Boss's**
(read board, then drag the dead-on-arrival target); **soften BEFORE snipe** (never Cruel Arrow a >100 mon);
**bench Meowth, resolve fetch, THEN play the Supporter**; **Lillie's after free draw**, prefer at exactly 6
prizes (8-card dig).

**Confusing-card purposes** (per-card deep dives):
- **Munkidori:** Phase-2 finisher/consolidator + mirror self-healer. Each turn pick ONE direction; misreading
  which side needs it wastes the activation. Hard-gated by 2 {D} — route deliberately. Ability MOVES counters
  (bypasses damage-prevention) — does NOT un-KO or clear conditions. Sits benched, never goes Active.
- **Fezandipiti ex:** PRIMARY = comeback draw (Flip the Script, benched 210-HP body); SECONDARY = Cruel Arrow
  situational late finisher (going Active exposes a 2-prizer; CCC steep on 9 energy). Immune to our Risky Ruins
  ({D}). Fetch with Ultra Ball, not Poké Pad.
- **Meowth ex:** one-of Supporter valve — Last-Ditch Catch tutors ANY Supporter on bench-play (usually Boss's
  on the lethal turn). Tuck Tail (CCC) bounces it to re-tutor / dodge a KO. 170 HP/2 prize, Fighting-weak, takes
  20 from our Risky Ruins. Cannot tutor Unfair Stamp (Item).
- **Risky Ruins:** redundancy tech — our real attackers (Stage 1/2) are immune; only taxes opp Basic non-{D}
  bench-entries. Run 2 to re-slam after an opposing stadium bump. Proactive (T1 if possible).

**Trainer purposes** (each with its priority/sequencing):
- **Boss's Orders ×3** — prize-converter; TOP Supporter priority on a convert/lethal turn (beats draw/disruption
  which can't cash a prize); yields to Lillie's/Crispin on pure development turns.
- **Crispin ×3** — the only card that fetches AND attaches a color; brings Phantom Dive online (missing Fire/Psy)
  or arms Munkidori ({D}). Above draw when the second color is all that gates Phantom Dive; below Boss's on a drag turn.
- **Judge ×2** — proactive OPPONENT disruption (leave them at 4), not our refill. Play vs a big/fresh opp hand,
  esp. right after a KO. Low default priority.
- **Lillie's Determination ×4** — primary draw-refuel; default develop-turn Supporter. After free draw; 8-card dig at 6 prizes.
- **Unfair Stamp ×1 (ACE SPEC)** — reactive post-KO refill+strip (draw 5/opp 2); Item, so STACKS with a Supporter;
  double-dips Fezandipiti's trigger. Sequence near-last.
- **Buddy-Buddy Poffin ×4** — T1 Dreepy multiplier (Dreepy is its ONLY legal target here); earliest dev rung.
- **Night Stretcher ×2** — recursion insurance for 9-energy: recover the exact Fire/Psychic (Phantom Dive gate)
  or the 2 {D} (Munkidori gate), or a stranded Stage-2 piece.
- **Crushing Hammer ×3** — coin-flip energy denial; buys convert-tempo. Best on a single-attach/re-powered
  attacker the turn before lethal. Low vs energy-flood. Item (stacks with Supporter).
- **Ultra Ball ×4** — the ONLY Rule-Box tutor (Dragapult/Fezandipiti/Meowth ex); discard-2 fuels Night
  Stretcher/Crispin recursion. Poké Pad first to reserve it.
- **Poké Pad ×4** — free non-Rule-Box tutor (Dreepy/Drakloak/Cinderace/Munkidori only); stretches search without
  draining the hand. Play first among searches.

**Opening lines:** ideal = 2 Dreepy T1 via Poffin → Drakloaks T2 → Dragapult ex T3; Cinderace Explosiveness
open + Turbo Flare seed; slam Risky Ruins T1 (proactive); Lillie's-for-8 at 6 prizes; bench Munkidori early +
route {D} via Crispin; bench Fezandipiti early/mid; vs Item-lock (Gholdengo) front-load Items T1.

**Matchups:** Charizard ex (favorable — snipe benched Charmander pre-evolve); Gholdengo ex (unfavorable — Item
lock; front-load Items T1); Gardevoir (grind, Boss's+Munkidori); Roaring Moon (spread broad); **mirror** (fire
Munkidori reactively to peel damage off our benched line — the defensive half wins it).

**Research-flagged gaps** (align with the §8 infra gaps): confirm the engine's Phantom Dive counter-placement
encoding; energy contention (Fire/Psy for Dragapult vs the 2 {D} for Munkidori) needs in-sim tuning; KO
thresholds are illustrative (compute from live board); mulligan/prize-mapping under-developed; bleeding-edge
web coverage references stock partners (Dusknoir/Iono/Froslass) NOT in this 60 — nuance is deck-adapted.

**Sources:** Monster Card Corner; TheGamer (Dragapult 2025); Going Second (Spenser Gow); Deltia's Gaming;
TCGplayer (×3); Heroes Hideout; Limitless (Munkidori TWM95, Fezandipiti SFA38, Meowth POR62, Risky Ruins MEG127,
deck 284); PokéGym Compendium (Adrena-Brain ruling); PokeBeach; Bulbapedia.

## 3 · Card-by-card

### 3× Dragapult ex — Role: `win_condition`, `primary_attacker` · tags: `spread` · LOCKED
- **Mechanics:** Stage 2 (Dreepy→Drakloak→Dragapult ex), 320 HP, 2-prize, **Tera**, **no weakness**,
  retreat 1. `C` Jet Headbutt (70). `FP` Phantom Dive (200 to Active **+ 6 damage counters on opp Bench,
  any way you like**).
- **Online / readiness:** **`Ready(energy=2)`** — the RACE flip is Phantom Dive (FP), NOT the engine's
  cheapest-attack default (Jet Headbutt at C). Jet Headbutt is a fallback chip only, so we stay in SETUP
  (digging) until the real payoff is affordable. *(Confirmed 2026-07-03.)*
- **Phantom Dive placement doctrine (the deck's core decision):**
  0. **Cross-turn truth:** Phantom Dive is the **turn-ender**, so Munkidori (ability), Boss's (Supporter),
     and Cruel Arrow (a *separate* attack) all resolve BEFORE it — they convert **prior-turn** chip, they
     are NOT same-turn combos with this placement. This turn's spread pays off THIS turn only by a DIRECT KO.
  1. **Imperative — take every DIRECT bench KO first:** if a benched mon's remaining HP ≤ K×10, spend K
     counters to KO it outright (a prize now); greedily KO as MANY benched mons as the 6 counters allow
     (prior Phantom Dive / Risky-Ruins chip makes this common — e.g. a 20-left + a 40-left mon = both, 2+4).
  2. **Default — MATCHUP-SWITCHED** *(confirmed)*: with the rest, **concentrate** on the single most-
     *convertible* threat (biggest energized threat / a key pre-evo we must deny, e.g. Charmander /
     a gust target) to set up ONE clean next-turn KO; **spread broad** vs bench-reliant boards + the
     mirror, so Munkidori's move-3 can finish whichever develops.
  3. **Grounding mechanism** (how a policy reads "matchup-switched"): greedy **marginal-value** placement
     — each counter goes where it most advances a prize (completing a this/next-turn KO on a target ×
     its prize value × threat). Concentrate/spread then EMERGE (one dominant target → concentrate; a
     flat field of near-dead threats → spread). The explicit concentrate↔spread bias comes from **(a)
     the Read** (matchup identity: mirror/bench-reliant) — **DEFERRED until the Read is wired** ([[scouting-feature]])
     — with a **board proxy usable now:** spread when the opp has ≥2 benched threats, concentrate on one
     dominant convertible target.
- **Sequencing:** attack LAST; fire Munkidori Adrena-Brain + read the board BEFORE choosing Phantom Dive
  placement and before Boss's. Prefer Phantom Dive over Jet Headbutt whenever FP is affordable (strictly
  more Active damage + the spread); Jet Headbutt only when just `C` is available.
- **Bench safety (Tera):** a benched Dragapult ex takes NO attack damage (rules §11) — the Pilot already
  treats a benched Tera as bench-snipe/spread-immune ([pilot.py](../../common/pilot.py):713), resolving the
  §8 Tera question in our favour both ways (opp can't snipe our benched copy; we don't waste spread onto
  their benched Tera). `dont-bench-multiprize` exempts the `win_condition` Role, so benching a 2nd Dragapult
  behind Tera is fine.
- **Anti-patterns:** don't Jet-Headbutt-chip when FP Phantom Dive is affordable; don't place spread on a
  target we have no line to convert (bench chip only pays via a later gust / Cruel Arrow / Munkidori /
  re-Phantom-Dive — never a prize by itself).
- **General-Strategy disposition:** snipe cluster (`snipe-for-the-ko` @ remaining-HP, `snipe-the-top-threat`)
  covers per-select targeting IF the engine presents placement as DAMAGE select(s); the **spread-rider
  valuation + the marginal-value multi-counter policy are a GAP** (infra gap A → Phase 6). Readiness =
  `Line.ready` override. `dont-bench-multiprize` covers-as-is (win_condition exempt).

### 2× Munkidori — Role: tech counter-mover (residence TBD Phase 4) · tags: `confuse`, `heal`, `spread` · LOCKED
- **Mechanics:** Basic Psychic, 110 HP, 1-prize, weakness Darkness, resist Fighting, retreat 1. Ability
  **Adrena-Brain** (once/turn, **needs {D} attached**): move ≤3 counters (30) from 1 of YOUR Pokémon → 1
  of the OPPONENT's. `PC` Mind Bend (60, opp Active Confused) — a permitted **pinch swing**, not the plan.
- **Use:** the Phase-2 finisher/consolidator + mirror self-healer. Benched ability-mon — **~90% here for
  Adrena-Brain, not an attacker** — but MAY swing Mind Bend in a pinch (no hard veto; the Tactical layer
  scores the attack normally). Moves counters (bypasses damage-prevention); does NOT un-KO or clear conditions.
- **Adrena-Brain direction — VALUE-COMPARE each turn** *(confirmed)*:
  - `finish_value` = prize value of a benched opp mon a move-≤3 KOs OUTRIGHT (remaining HP ≤ prior chip + 30)
    — Munkidori acts BEFORE the attack, so it converts PRIOR-turn Phantom Dive / Risky-Ruins damage, not this turn's spread.
  - `heal_value` = prize value of OUR own body a move-≤3 lifts OUT of next-turn-KO range — counted only
    when that body is actually doomed (`active_doomed` / incoming ≥ remaining HP) AND the move genuinely saves it.
  - Take **max(finish, heal)**; if neither fires, **offensive-chip** the top convertible threat (advance a
    next-turn KO). Wins the mirror when heal_value (save the 2-prize Dragapult) > a small finish.
  - **Source pick:** the own body that most needs counters removed (when healing); any own body carrying
    counters (pure offense). **Target pick:** reuse the marginal-value / snipe logic (finish > soften the top threat).
- **Sequencing:** activate BEFORE the attack and BEFORE Boss's (read the resulting board, then place
  Phantom Dive spread / drag the dead-on-arrival target).
- **{D} routing** *(confirmed)*: {D} has no other home (Dragapult uses F+P), so proactively arm Munkidori —
  but via **Crispin's free attach** or Night Stretcher recovery, reserving the 1/turn manual attach for
  Dragapult's F+P. Arm once the Dragapult line is online. Only 2 {D} exist — Night Stretcher recovers a
  discarded/prized one (a Munkidori gate).
- **Anti-patterns:** don't promote Munkidori as an attacker (Mind Bend is a fallback); don't spend the
  activation on a direction that neither finishes nor saves a doomed body; don't strand the scarce {D} elsewhere.
- **General-Strategy disposition:** **GAP** — no general handler for a counter-mover ability (infra gap C
  → Phase 6: an ability-activation decision + source/target selects; reuse the snipe marginal-value terms
  for the target, `active_doomed` for the heal gate). Residence (deck Hypothesis vs a general
  `heal`+`spread`-ability doctrine, keyable on the existing tags) decided in Phase 4. `dont-bench-multiprize`
  N/A (1-prize). Promote priority covers "never promote the utility mon".

### 1× Fezandipiti ex — Role: comeback_engine (tech; residence TBD Phase 4) · LOCKED
- **Mechanics:** Basic Darkness, 210 HP, 2-prize, weakness Fighting, retreat 1. Ability Flip the Script
  (once/turn, if any of your Pokémon were KO'd during opponent's LAST turn: draw 3). `CCC` Cruel Arrow
  (100 to ANY opp Pokémon, no W/R on Bench). Darkness → **immune to our Risky Ruins**.
- **Use:** PRIMARY = comeback draw engine — draw 3 every turn after the opponent takes a KO; refuels the
  grind after our Judge/Lillie's/Unfair Stamp hand-thinning. SECONDARY = Cruel Arrow, a situational late
  finisher on a bench target softened to ≤100 remaining — a valid **pinch swing** when it's the best available
  line, but rarely mainline (going Active exposes a 2-prizer, CCC steep on 9 energy).
- **Bench timing** *(confirmed)*: bench it **entering the grind / after the first trade** (a KO has
  happened or is imminent) so Flip the Script is online — NOT turn 1. A positive `bench-the-comeback-drawer`
  trigger overrides `dont-bench-multiprize` in RACE/STABILIZE; the −15 correctly keeps it off the early bench.
- **Fetch:** Ultra Ball only (Rule Box — not Poké Pad).
- **Anti-patterns:** don't bench T1; don't go Active with Cruel Arrow while a cheaper benched finish
  (Munkidori) exists; don't Cruel-Arrow a target still >100 remaining that could be chipped first.
- **General-Strategy disposition:** `dont-bench-multiprize` **override** in RACE/STABILIZE (positive bench
  trigger). "Play the on-KO drawer" = **GAP** (positive play-the-engine-ability rule; residence Phase 4,
  likely general). Cruel Arrow bench-targeting = infra gap B (Phase 6). Ultra-Ball tutor covered by fetch.

### 1× Meowth ex — Role: supporter_tutor (tech; residence TBD Phase 4) · tags: `search`, `stall` · LOCKED
- **Mechanics:** Basic Colorless, 170 HP, 2-prize, weakness Fighting, retreat 1. Ability Last-Ditch Catch
  (on-play from hand → Bench: tutor ANY Supporter to hand, once/turn). `CCC` Tuck Tail (60, put this +
  attached into hand). Takes 20 from our Risky Ruins (Basic non-{D}).
- **Use:** a one-of Supporter valve — play it to bench to tutor the Supporter the turn needs, most often
  **Boss's Orders** on a convert/lethal turn (ability → the tutored Supporter still plays that turn; bench
  Meowth FIRST). Tutor priority: **Boss's-first**, else the acute need (Lillie's hand-starved / Crispin
  color-starved / Judge disruption) via the fetch comparator. Cannot tutor Unfair Stamp (Item).
- **When to play** *(confirmed — positive trigger)*: when a needed Supporter (esp. Boss's) is unreachable
  and the tutor enables a convert/lethal/critical-draw — overriding `dont-bench-multiprize` at the point of
  need. Not proactively early.
- **Tuck Tail:** niche — a permitted **pinch swing** (60 + self-bounce) to re-tutor or dodge a KO (removes
  the 2-prize liability); CCC steep on 9 energy so rare. Not mainline.
- **Fetch:** Ultra Ball only (Rule Box).
- **Anti-patterns:** don't bench early with no tutor need; don't play the tutored Supporter before benching
  Meowth (lose the card); don't leave it exposed as a free 2-prize KO.
- **General-Strategy disposition:** the on-play Supporter-tutor = **GAP** (same positive play-the-engine-
  ability rule as Fezandipiti; the tutor TARGET at the resulting select is covered by fetch —
  `play-a-tutor-for-the-unfound-wincon` / Boss's-first). `dont-bench-multiprize` override at point of need.

> **Ability-first mons (Munkidori · Fezandipiti · Meowth) — ~90% for their abilities, benched by plan, but NO
> hard attack-veto** *(confirmed 2026-07-03)*. All three earn their slot on Adrena-Brain / Flip the Script /
> Last-Ditch Catch, not their attacks — but each **MAY swing in a pinch** (Mind Bend / Cruel Arrow / Tuck Tail)
> when it's the best available line. **Phase B must NOT author a rule that suppresses their attacks;** the
> Tactical layer scores those normally, and the ability-first bias comes from `dont-bench-multiprize` + not
> Roling them as attackers — never a veto.

### 2× Risky Ruins (Stadium) — Role: `disruption` (tech) · LOCKED
- **Mechanics:** Stadium. When any player puts a Basic **non-{D}** Pokémon onto their Bench during their
  turn, place 2 counters (20) on it. Both players. Triggers on bench-ENTRY only (not retroactive). Our
  Stage-1/2 attackers immune; our vulnerable Basics = Dreepy/Munkidori/Meowth; Fezandipiti ({D}) immune.
- **Play policy** *(confirmed — proactive + bench-first + soft net gate)*: play early to chip the opponent
  across the most turns; on the play-turn **bench our own vulnerable Basics FIRST** so they enter before
  Ruins and dodge the 20. Softly **hold** when we still have more non-{D} benching ahead than the opponent
  (v1 board proxy: count of our un-benched core Basics; the Read later refines to skip {D}-Basic decks
  where it only taxes us). Re-slam the 2nd copy after an opponent bumps ours.
- **Stadium denial** *(added — your review)*: playing Risky Ruins ALSO **knocks out an opponent's Stadium** —
  a second, independent reason to play it (disruption), even when the chip net-value is only neutral. v1
  heuristic: replace ANY non-ours Stadium in play (safe — we want Ruins out anyway); the "does it specifically
  HELP them" refinement needs stadium-effect labels (see disposition + §8 infra).
- **Combo:** 20/opp-bench-entry compounds with Phantom Dive counters + Munkidori/Cruel Arrow — pushes
  benched targets into finisher range a turn early.
- **Anti-patterns:** don't play it before benching our own Dreepy/Munkidori/Meowth this turn; don't play it
  vs a Darkness-Basic opponent (pure self-tax); don't overwrite our own useful Ruins.
- **General-Strategy disposition:** **GAP** — no general stadium-play doctrine (mega_lucario also runs
  stadiums → a fold candidate). v1 = deck rule `play-risky-ruins-when-net-positive` (bench-first sequencing +
  soft net gate + stadium-denial). Engine enforces "different from the stadium in play" (rules §3).
  **INFRA GAP (verified 2026-07-03):** stadiums are identifiable (`CardType.STADIUM`) but **effect-unlabelled**
  — 26 in the pool, function tags empty (only Levincia/Battle Cage tagged) — and `common/` reads NO stadium
  state (`AreaType.STADIUM`=7 exists, but no `Board.stadium_in_play`). The stadium-denial trigger needs net-new
  infra: (1) a Board signal for the in-play Stadium (id + whose), (2) a stadium-effect labelling pass to judge
  "helps the opponent" (else the v1 replace-any-non-ours heuristic). → §8 Phase-6.

### 3× Crushing Hammer (Item) — Role: `disruption` · tags: `energy_denial` · LOCKED
- **Mechanics:** Item. Flip a coin; heads → discard 1 Energy from 1 opponent Pokémon. Stacks with a Supporter.
- **Use** *(confirmed — value-targeted before lethal)*: play on a freshly-powered / single-attach opponent
  attacker the turn before our planned KO — a heads denies their counter-swing, a whiff costs little. Skip
  vs energy-flood/accel decks. Don't spam randomly.
- **Sequencing:** early in the turn (plan around a heads); before a planned KO. Item → stacks with the Supporter.
- **Anti-patterns:** don't fire into an energy-flooded board; don't waste all 3 early with no target value.
- **General-Strategy disposition:** **GAP** — no general energy-denial rule. v1 = deck rule
  `crush-the-key-energy` (single-attach/re-powered attacker pre-lethal). Coin-flip = 0.5× expected; modest seed.

### Covered-as-is cards (line pieces, Cinderace, staple trainers, energy) — compact blocks

**4× Dreepy** — `starter`, line base. Basic Dragon 70 HP, 1-prize, no weakness, retreat 1; attacks are chip
only. Poffin's ONLY legal target (≤70). Covered: `keep-a-bench`, `fetch-a-starter`, `prefer-bench-fill-first`,
`fetch-base-before-stranded-payoff`, the Line.

**4× Drakloak** — line mid + `dig` engine. Stage 1, 90 HP, evolves from Dreepy. Recon Directive (top-2 → 1).
**Use Recon BEFORE evolving** (ability lost on evolve; Recon then evolve same turn). **Delay evolving Drakloak →
Dragapult ex until the (future-Dragapult) body already carries its 2 FP energy** — keep Recon-digging each turn
meanwhile — so it Phantom Dives the turn it evolves (don't strand an energyless Dragapult and waste the Recon
turns). **Carve-out: evolve NOW if the Drakloak is in KO range** (secure the 320-HP body / don't lose the line
piece). **Keep a spare Drakloak as a standing Recon engine** rather than reflexively fielding a 2nd Dragapult.
Covered: line + `dig`; both timing gates = §4 carve-outs.

**4× Cinderace** — `accel_source`, `starter`. Stage 2 Fire 160 HP, retreat 0. Explosiveness (setup-open) +
Turbo Flare (≤3 Basic Energy → **Bench only**). Stranded (no Raboot). **Fully covered by the mega_starmie
folds:** `open-the-accelerator`, `advance-the-accel-pieces`, `develop-the-accel-recipient`,
`dont-fetch-the-setup-only-opener`, `keep-a-startable-hand`.

**3× Boss's Orders** — `gust`. The prize-converter (drag a softened bench mon Active). Gust doctrine
(ADR-0022, id 1182) covers whether-to-play + target. TOP Supporter on a convert/lethal turn.

**3× Crispin** — `accel_source`. Color-fixer: attach the missing Phantom Dive color (F/P) to Dragapult, or
free-attach {D} to Munkidori. Covered: `use-acceleration` + branch-2 {D}-routing.

**2× Judge + 4× Lillie's Determination** — Shuffle-Refresh doctrine (ADR-0024): `refresh-when-hand-is-dead`
+ hold floors + Lillie's-at-6-prizes. Lillie's = primary refuel (after free draw); Judge = proactive opp
strip (both to 4, vs a fresh opp hand). Judge's offensive-strip axis = DEFERRED general seam (§6).

**4× Buddy-Buddy Poffin / 4× Poké Pad / 4× Ultra Ball / 2× Night Stretcher** — Fetch doctrine (ADR-0023):
Poffin→2 Dreepy (earliest rung); Poké Pad = free non-Rule-Box tutor (play FIRST); Ultra Ball = Rule-Box
tutor (the exes), discard-2 fuels recursion (after Poké Pad); Night Stretcher recovers a Pokémon or the exact
F/P/{D} (a Phantom-Dive/Munkidori gate). Covered: `prefer-bench-fill-first`, `fetch-a-starter`,
`fetch-the-wincon`, `fetch-base-before-stranded-payoff`, `dont-fetch-the-setup-only-opener`, discard keep-value.

**Energy — 4 F / 3 P / 2 D (9 Basic)** — F+P gate Phantom Dive; the 2 {D} gate Munkidori. F/P → the Dragapult
line (manual + Turbo Flare seed + Crispin); {D} → Munkidori via Crispin's free attach (branch 2). **{D} =
normal energy for the Ultra Ball discard** — no keep-value bump; Night Stretcher recovers it, the discard-2 is
engine fuel *(confirmed branch 6)*. Covered: energy-attachment procedure (ADR-0016) + `develop-the-accel-recipient`.

## 4 · Combos, sequencing & opening hands

**Combos** (min pieces → payoff):
- **Spread → convert (CROSS-TURN):** Phantom Dive (turn N) pre-loads the bench → (turn N+1, before the
  attack) Munkidori move-3 / a Cruel-Arrow turn / gust+the 200 converts the prior chip. Same-turn, the
  spread converts only by KOing an already-≤60-remaining benched mon outright. Min: Dragapult online (FP)
  + a softened target + one finisher.
- **Munkidori-reverse (mirror):** peel counters off our damaged Dragapult/Drakloak → onto opp = ~30 HP/turn
  heal on the win-con line. Needs {D} on Munkidori.
- **Cinderace → Turbo Flare:** open Cinderace, seed 3 Basic Energy onto the bench line; **Crispin** cashes a
  missing color on the Active.
- **Meowth → Boss's:** bench Meowth (tutor Boss's) → gust a softened mon Active, same turn.
- **Comeback:** opp KO → Unfair Stamp (draw 5 / opp to 2, Item) + Fezandipiti Flip-the-Script (draw 3) — shared trigger.
- **Risky Ruins compounding:** 20/opp-bench-entry + a Phantom Dive counter puts a benched mon in
  Munkidori/Cruel-Arrow range a turn early.

**Sequencing ladder (developing turn):** free draw/dig first (**Drakloak Recon — before evolving it**,
Cinderace/Meowth abilities) → Items (**Poké Pad → Poffin → Ultra Ball** → Night Stretcher/Crushing Hammer) →
the one **Supporter** (Boss's on a convert turn, else Lillie's/Crispin/Judge) → **evolve/attach** → **attack
LAST**. Carve-outs: **hold the Drakloak → Dragapult ex evolution until the body has its 2 FP energy** (keep
Recon-digging each turn; evolve early ONLY if the Drakloak is in KO range); **Munkidori Adrena-Brain BEFORE the
attack and BEFORE Boss's** (read the board, then place spread / drag the corpse); **bench our own
Dreepy/Munkidori/Meowth BEFORE Risky Ruins**; **bench Meowth BEFORE the tutored Supporter**; **soften BEFORE the
snipe** (never Cruel-Arrow a >100-remaining mon).

**Opening hands — going FIRST** *(confirmed branch 6)* (T1: no Supporter / no evolve / no attack):
- **Dream:** Cinderace (Explosiveness open) + 2 Dreepy via Poffin + energy → T1 open Cinderace, bench 2
  Dreepy, attach, Turbo Flare seed; slam Risky Ruins T1. Drakloaks T2, Dragapult ex online T3.
- **Median:** a Basic/Cinderace + a tutor + energy → T1 fetch the line + develop.
- **Survivable:** a lone Dreepy + an Item → keep (going first = a full setup turn); T1 dig.
- **Mulligan keeps:** any hand with a Basic (Dreepy/Munkidori/Meowth/Fezandipiti) OR a Cinderace (`opener` →
  `keep-a-startable-hand`). 8 real Basics + 4 Cinderace → mulligans rare.

**Plan mapping:**
- **SETUP** = assemble the Dreepy→Drakloak→Dragapult line + seed F/P; slam Risky Ruins; don't bench the 2-prize exes yet.
- **RACE** (flips at **`Ready(energy=2)` — FP**) = Phantom Dive every turn, place spread by the matchup-switched
  policy, convert with Munkidori/Boss's.
- **STABILIZE** (behind) = Munkidori-reverse heals the line; Fezandipiti draws; Judge/Crushing Hammer/Unfair
  Stamp disrupt to buy convert-tempo.
- **CLOSE** (ahead) = gust + finisher sequencing to cash the last prizes.

## 5 · General-Strategy disposition table

| General Hypothesis / doctrine | Disposition | Why (deck-specific) |
|---|---|---|
| `keep-a-startable-hand` | covers-as-is | Cinderace `opener` + 8 real Basics keep hands |
| `open-the-accelerator` | covers-as-is | Cinderace `accel_source` at SETUP_ACTIVE |
| `honor-preferred-start` | **param** | `preferred_start="first"` (setup-heavy → first; −30 on SECOND) |
| `dig-before-commit` | covers-as-is | draw/search-heavy deck |
| `attach-energy-last`/`power-up-attacker`/`use-acceleration`/`advance-the-accel-pieces` | covers-as-is | Cinderace + Crispin accel; F/P → line |
| `develop-the-accel-recipient` | covers-as-is | Cinderace Active + bench a Dreepy recipient |
| `keep-a-bench`/`pre-position-attacker`/`dont-feed-the-doomed` | covers-as-is | standard board upkeep; multi-line development |
| `dont-bench-multiprize` | **override** | Fezandipiti/Meowth ex benched for abilities in RACE/STABILIZE (positive triggers §6); −15 stays right in SETUP |
| Snipe cluster (`snipe-for-the-ko`@remaining-HP / `snipe-the-top-threat`) | covers-as-is (targeting) **+ GAP** | per-DAMAGE-select targeting covered; the 6-counter **spread valuation + placement** is infra gap A (§6) |
| Gust doctrine (`gust-for-the-ko`/`gust-target`/`gust-for-the-stall`) | covers-as-is | Boss's id 1182; convert-the-softened-mon IS `gust-for-the-ko` — **verify `gust_ko` uses REMAINING HP** so it sees the chip (§8) |
| Fetch doctrine (all rungs) | covers-as-is | Poffin→Dreepy, Poké-Pad-first, Ultra-Ball-Rule-Box, `fetch-base-before-stranded-payoff`, `dont-fetch-the-setup-only-opener` (Cinderace) |
| Shuffle-Refresh (`refresh-when-hand-is-dead` + hold floors) | covers-as-is | Lillie's/Judge; Judge's **offensive-strip axis DEFERRED** (general seam, §6) |
| Tool doctrine | **N/A** | no Tools |
| Tactical: Weakness×2 / `prize-trade-target` | covers-as-is | Dragapult has no weakness; prize preference applies |
| `conserve-discard-energy-prefer-basic` | **N/A** | no `discard_eot` special energy |

**Net-new (gaps) — §6:** Phantom Dive spread (A, structural); Cruel Arrow targeting (B, structural); Munkidori
Adrena-Brain (C, structural+decision); **Stadium state + labelling (D, structural — your review)**;
`play-the-engine-ability`; `bench-the-comeback-drawer`; `hold-evolution-until-attacker-ready`;
`play-risky-ruins-when-net-positive` (+ stadium-denial); `crush-the-key-energy`; `hold-unfair-stamp-for-impact`.

## 6 · New Hypotheses (drafts — trigger sketches, NOT lambdas yet)

**Two kinds:** **(A/B/C) are STRUCTURAL** combat-layer infra (Tactical/Lethal/oracle) — built in Phase 6 like
the mega_lucario AttackStat mint, NOT weight-tunable; the rest are **positional Hypotheses** (`when()` + seed).

### A · Phantom Dive spread — valuation + placement (STRUCTURAL, infra gap A) · status: assumed
> The deck's core mechanic. Model the distributable bench-counter rider so the oracle values it and the Pilot
> places the 6 counters by the matchup-switched marginal-value policy (branch 1).

**Build:** a new `AttackStat` bench-spread field parsed from "Put N damage counters on your opponent's
**Benched** Pokémon in any way you like" (`_COUNTER_PUT_RE` misses "Benched … any way"; also skips because
printed>0 — fix both). Oracle credits the spread (bypasses W/R) in valuation + Lethal. **Placement policy:**
greedy marginal-value at the DAMAGE select(s); concentrate/spread emerges (board proxy: spread ≥2 threats else
concentrate). **Lives in:** `provider.py` + damage oracle + snipe/placement path — **GENERAL** (rider-keyed).
**Verify:** the engine's placement-select encoding (maxCount=6 vs sequential) — Phase-6 probe.

### B · Cruel Arrow bench-targeting (STRUCTURAL, infra gap B) · status: assumed
> Value Fezandipiti's "100 to ANY Pokémon (no W/R on Bench)" as a benched finisher, not 100-to-Active.

**Build:** model the any-target full-damage attack (benchSnipe-class or extended DAMAGE-targeting) so
Tactical/Lethal see it can KO a benched ≤100-remaining target. Damage (100) already parsed; only targeting.
**Lives in:** `provider.py` + oracle — **GENERAL**.

### C · Munkidori Adrena-Brain (STRUCTURAL + decision, infra gap C) · status: assumed
> The counter-mover ability doctrine (branch 2): value-compare finish vs heal each turn.

**Build:** an ability handler at Adrena-Brain's activation + source/target selects applying
`max(finish_value, heal_value)` (finish = a move-≤3 KO prize; heal = lift OUR `active_doomed` body out of KO
range), else offensive-chip the top threat; reuse the snipe marginal-value terms. Gated on {D} attached
(engine-enforced). **Lives in:** likely a **GENERAL** `counter_move` ability doctrine keyable on the
`heal`+`spread` ability tags (Munkidori the only instance → may start DECK and fold, ADR-0034).

### `play-the-engine-ability` · seed 22 · status: assumed
> Play a benched-engine Pokémon whose on-play / once-per-turn Ability (`draw`/`search`/`tutor`) fills a current
> need — the positive driver missing beside `dont-bench-multiprize`. Covers Meowth ex (tutor a needed Supporter,
> esp. Boss's) and Fezandipiti ex (comeback draw once trading starts).

**Trigger sketch:** on a `PLAY` of a Pokémon whose Ability is `draw`/`search`/`tutor` AND the matching need is
lacking (a needed Supporter unreachable → Meowth; in the grind / own-KO taken → Fezandipiti), overriding
`dont-bench-multiprize`. **Reads:** the ability function tag + a per-tag need gate + plan. **Fires:**
RACE/STABILIZE/CLOSE. **Lives in:** **GENERAL** (`baseline_bench` / fetch play-side; tag+need-keyed, no card id).
The Meowth tutor TARGET is already the fetch doctrine (Boss's-first). **Why general:** "play your engine mon when
its ability is needed" is universal; the deck opts in by running such a mon.

### `bench-the-comeback-drawer` · seed 18 · status: assumed
> Bench a KO-gated comeback drawer (Fezandipiti) once we're entering the grind, so it's online when the opponent
> takes KOs — a specialization of `play-the-engine-ability` with a "trading has started" gate.

**Trigger sketch:** on a `PLAY` of Fezandipiti (`draw`-Ability gated on "your Pokémon was KO'd"), when trading
has started (prizes < 6 or a recent own-KO), RACE/STABILIZE. **Lives in:** **GENERAL** — likely subsumed by
`play-the-engine-ability` (its `draw`-on-KO need-gate = "in the grind"); keep as one rule, note the Fezandipiti gate.

### `play-risky-ruins-when-net-positive` · seed 15 · status: assumed
> Play the bench-chip Stadium when it taxes the opponent's Basic non-{D} bench-entries more than ours — and bench
> our own vulnerable Basics FIRST that turn (branch 4).

**Trigger sketch:** on a `PLAY` of a Stadium (Risky Ruins) when our vulnerable-Basic benching for the turn is done
AND our un-benched non-{D} Basic count ≤ the opponent's expected non-{D} bench-entries (board proxy; Read later).
**Reads:** stadium PLAY + our/opp bench composition + sequencing. **Lives in:** **DECK** initially (self-damage
net-value is Risky-Ruins-specific) → a **general stadium-play doctrine** is a fold candidate (no general stadium
handling exists; mega_lucario also runs stadiums). Bench-first sequencing is structural (Basic PLAYs before the stadium).

### `crush-the-key-energy` · seed 12 · status: assumed
> Play a coin-flip energy-denial Item on a single-attach / freshly-powered opponent attacker the turn before a
> planned KO; skip energy-flood boards (branch 5).

**Trigger sketch:** on a `PLAY` of an `energy_denial` Item, when an opponent attacker carries few energy (a
removable swing) and we're near a convert/lethal; damped vs a flooded board. **Reads:** `energy_denial` tag + opp
attacker energy count + plan. **Lives in:** **DECK** initially → general energy-denial fold candidate. Coin-flip
(0.5× expected) → modest seed.

### `hold-evolution-until-attacker-ready` · seed −18 · status: assumed *(added — your review)*
> Delay evolving a pre-evolution that carries an ongoing-value Ability (Drakloak's Recon `dig`) into its payoff
> until the payoff can attack THIS turn (its energy meets `Line.ready`) — keep using the pre-evo's ability each
> turn meanwhile. Override: evolve immediately if the pre-evo is in KO range (secure the higher-HP body).

**Trigger sketch:** at an `EVOLVE` option (a win-con-Line pre-evo → its payoff), penalize the evolve when the
pre-evo has a `dig`/`draw` Ability AND the payoff couldn't attack this turn (attached energy < `ready.energy`)
AND the pre-evo is NOT in KO range (`active_doomed` / incoming < remaining HP). **Reads:** EVOLVE option + pre-evo
ability tag + payoff energy vs `Line.ready` + KO-range. **Lives in:** **GENERAL** (`baseline_evolution` /
`baseline_sequencing`; tags/Line/energy/board — no card id). Any evolution deck with an ability-carrying pre-evo
inherits it. **Why general:** "don't evolve away a useful pre-evo ability before the evolved form can act" is universal.

### `hold-unfair-stamp-for-impact` · seed −20 · status: assumed
> Don't fritter the single ACE SPEC (Unfair Stamp — engine-gated to post-KO turns, unrecoverable once played):
> hold it for a max-impact post-KO turn (branch 7 — a dead hand needing the 5, or a Boss's lethal / big opp-hand
> strip it enables); suppress the play on a low-value post-KO turn.

**Trigger sketch:** at a `PLAY` of Unfair Stamp, penalize UNLESS (`hand_is_dead` OR it enables a lethal/convert OR
a large opp-hand strip). **Reads:** `aceSpec` + `hand_disruption` facts + `hand_is_dead` + lethal-enable + opp
hand size. **Lives in:** **GENERAL** — extends the Shuffle-Refresh dead-hand logic (ADR-0024) to the KO-gated Item
+ the doctrine's deferred `hand_disruption` strip term. A keep-value floor mirroring the Supporter refresh.

## 7 · Roles, Lines, params (the executable shape, pre-code)

**Card ids** (dragapult_ex/deck.csv): DREEPY 119, DRAKLOAK 120, DRAGAPULT_EX 121, MUNKIDORI 112, FEZANDIPITI_EX
140, CINDERACE 666, MEOWTH_EX 1071, UNFAIR_STAMP 1080, BUDDY_POFFIN 1086, NIGHT_STRETCHER 1097, CRUSHING_HAMMER
1120, ULTRA_BALL 1121, POKE_PAD 1152, BOSS_ORDERS 1182, CRISPIN 1198, JUDGE 1213, LILLIES 1227, RISKY_RUINS 1260;
FIRE 2, PSYCHIC 5, DARKNESS 7.

```
roles = {
  DRAGAPULT_EX:    ["win_condition", "primary_attacker"],
  CINDERACE:       ["accel_source", "starter"],     # Explosiveness + Turbo Flare (mega_starmie folds)
  DREEPY:          ["starter"],
  CRISPIN:         ["accel_source"],                # color-fixer / manual attach
  BOSS_ORDERS:     ["gust"],
  MUNKIDORI:       ["counter_mover"],               # tech — Adrena-Brain doctrine (gap C)
  FEZANDIPITI_EX:  ["comeback_engine"],             # bench for Flip the Script (play-the-engine-ability)
  MEOWTH_EX:       ["supporter_tutor"],             # on-play Last-Ditch Catch (play-the-engine-ability)
  RISKY_RUINS:     ["disruption"],
  CRUSHING_HAMMER: ["disruption"],
  NIGHT_STRETCHER: ["recovery"],
  ULTRA_BALL:      ["tutor"], POKE_PAD: ["tutor"], BUDDY_POFFIN: ["tutor"],
  # Judge / Lillie's ride their function tags (draw / shuffle_hand) — no extra role.
}

lines = [ Line(path=[DREEPY, DRAKLOAK, DRAGAPULT_EX], payoff=DRAGAPULT_EX,
               role="win_condition", ready=Ready(energy=2)) ]   # FP Phantom Dive, NOT the C Jet-Headbutt default

params = {
  "preferred_start":     "first",     # setup-heavy → honor-preferred-start (−30 on SECOND)
  "setup_energy_target": 2,           # FP for Phantom Dive
  "search_budget":       0,           # Tier-0 closed-form combat
  "my_archetype":        "Dragapult ex spread + disruption",  # Read favorability key (ADR-0026)
}

hypotheses = [   # deck rules that DON'T fold to general (residence per §6)
  play-risky-ruins-when-net-positive,   # DECK (stadium net-value; general fold candidate)
  crush-the-key-energy,                 # DECK (energy-denial; general fold candidate)
  # play-the-engine-ability, bench-the-comeback-drawer, hold-unfair-stamp-for-impact -> GENERAL (baseline/doctrine)
  # A/B/C (Phantom Dive spread, Cruel Arrow, Munkidori) -> STRUCTURAL infra (provider.py/oracle/ability handler)
]
```

**Roles note:** `counter_mover`/`comeback_engine`/`supporter_tutor` are deck-intent labels the §6 rules key on
(deck opts in). If those rules land general keyed on ability tags instead, the roles become documentation —
confirm role-vs-tag keying in Phase 6. **`Ready(energy=2)`** — verify the `Line.ready`/`Ready` API against live
source in Phase 6.

## 8 · Open questions / deferred

**Phase-0 open questions** (see checklist): mulligan × Explosiveness; Risky Ruins self-chip net value;
Tera + effect-counters on a benched Dragapult.

**Engine-verified infra gaps (headline — the deck's signature mechanics are unmodeled).** Confirmed
2026-07-03 by dumping `build_attack_stats` (compendium ADR-0032). These are STRUCTURAL (Tactical /
Lethal / damage-oracle), not weight-Hypotheses — build them in Phase 6 like the mega_lucario run minted
its AttackStat fields:

- **A · Phantom Dive spread rider — UNMODELED.** atk 154 = `damage 200, benchSnipe 0`. "Put 6 damage
  counters on your opponent's **Benched** Pokémon in any way you like" is caught by NEITHER parser: the
  effect-damage parser only runs on printed-0 attacks (this is printed-200), and `parse_attack_bench_snipe`
  doesn't match the "Benched … any way you like" spread. **The oracle sees a plain 200-to-Active** — the
  60 distributable bench damage (the whole deck) is invisible to valuation and the Lethal Solver. Needs a
  new spread-rider field + oracle/Lethal handling. **The central deck mechanic.**
- **B · Cruel Arrow targeting — PARTIAL.** atk 183 damage correctly parsed to `100`, but `benchSnipe 0`
  — the "to *any* Pokémon incl. Bench, ignore W/R on Bench" is not encoded, so Tactical/Lethal value it
  as 100-to-Active and miss its job as a benched-mon finisher. (Targeting AT the DAMAGE select is likely
  handled by the snipe cluster; the valuation is what's blind.)
- **C · Munkidori Adrena-Brain — UNMODELED.** An ability (move ≤3 counters from 1 of ours → 1 of theirs,
  gated on {D} attached). Not an attack (no AttackStat). The activation + source/target placement is a
  Pilot ability decision with no current handler. The deck's finisher/heal lever.

**Open — engine select encoding (resolve via probe in Phase 6):** does Phantom Dive present its 6-counter
placement as ONE `maxCount=6` DAMAGE select, six sequential single-target DAMAGE selects, or a
distribution select? Determines whether the snipe cluster (`snipe-for-the-ko` uses *remaining* HP —
finishes softened mons) covers optimal spread, or whether a spread-placement doctrine is needed.

**Verify — `gust_ko` must use REMAINING HP.** The convert plan ("drag the Phantom-Dive / Risky-Ruins-softened
bench mon Active to KO it") depends on the Gust doctrine's `gust_ko` oracle scoring the target at its
**remaining** HP (chip already on it), not full HP. `snipe-for-the-ko` uses remaining HP, so `gust_ko` likely
does too — but confirm in Phase 6; if it reads full HP, that's a fix, not just a deck concern.

**Phase-6 build checklist (structural infra + deck rules to author):**
1. **Infra A** — Phantom Dive spread rider: `AttackStat` field + parser fix + oracle/Lethal credit + the
   marginal-value placement policy (probe the select encoding first).
2. **Infra B** — Cruel Arrow any-target valuation (benched finisher).
3. **Infra C** — Munkidori Adrena-Brain ability handler (value-compare finish vs heal; {D}-gated).
4. **Infra D — Stadium state + labelling** *(from your review)* — for the stadium-denial trigger: a
   `Board.stadium_in_play` signal read from `AreaType.STADIUM` (id + whose), plus a **stadium-effect labelling
   pass** over the 26 unlabelled stadiums (who-benefits) — or ship the v1 replace-any-non-ours heuristic and
   defer the labelling.
5. **Verify `gust_ko` remaining-HP** (above).
6. **Deck Hypotheses** (`when()` + trigger tests): `play-risky-ruins-when-net-positive` (chip net-gate +
   stadium-denial), `crush-the-key-energy`.
7. **General rules** (fold-forward): `play-the-engine-ability` (+ `bench-the-comeback-drawer` gate),
   `hold-evolution-until-attacker-ready`, `hold-unfair-stamp-for-impact`.
8. **Declarations:** roles / lines (`Ready(energy=2)`) / params (`preferred_start="first"`) per §7. **Do NOT
   author any attack-veto on Munkidori/Fezandipiti/Meowth** — ability-first is a bench-bias, not a veto (§3 note).
9. **Gates:** per-Hypothesis trigger checks; `pytest tests/ -q` green; `check_agent.py dragapult_ex`
   (self-match: no crash / timeout / illegal move).

---

### Phase-B GROUNDING UPDATE (2026-07-03 — authored against live source, per deck-genie mandate)

Building revealed the General Strategy has **grown past what §5/§6 assumed** — three planned deck rules are
already **covered-as-is** (fold policy: never author what the general layer covers):

- **Crushing Hammer → `play-energy-denial`** (baseline_disruption.py; its rationale literally names
  Crushing Hammer + reads `energy_denial` tag & `opp_active_has_energy`, stands down on `active_cheap_attack_kos`).
  **DROP `crush-the-key-energy`.**
- **Meowth ex → `bench-the-supporter-tutor` + `grab-a-gust-supporter-for-the-ko`** (doctrine_fetch.py; the
  first's rationale explicitly names `dragapult_ex`; tag-`supporter_tutor`-driven). **DROP the Meowth half of
  `play-the-engine-ability`; give Meowth NO Role.**
- **Unfair Stamp → Shuffle-Refresh doctrine** (`shuffle_hand` tag, not Supporter-gated) **+ aceSpec discard
  guard** — the same coverage mega_lucario relies on. **DROP `hold-unfair-stamp-for-impact`** (the max-impact
  strip nuance stays the deferred general `hand_disruption` seam).

**M1 DONE (tracer bullet):** `strategy.py` (declarations: roles/Line `Ready(energy=2)`/params
`preferred_start="first"`) + `main.py` Bundle → `check_agent dragapult_ex` PASS (contents/legality/
playability×3/deployability). The agent already rides the covered-as-is layer (energy-denial, Meowth tutor,
Unfair Stamp, Gust, Fetch, Shuffle-Refresh, snipe cluster, Cinderace folds).

**FINAL remaining build set:**
- **Structural infra:** A · Phantom Dive spread (valuation + placement) · B · Cruel Arrow any-target · C ·
  Munkidori Adrena-Brain handler · D · Stadium Board signal (+ labelling or v1 heuristic).
- **Deck/general rules:** `hold-evolution-until-attacker-ready` (GENERAL — counters the +40 `evolve-into-wincon`
  pull when the payoff can't attack + pre-evo has `dig` + not KO-range; needs a Context "evolve yields a
  ready attacker" signal) · `bench-the-comeback-drawer` (Fezandipiti — needs a tag + a rule beside
  `bench-the-supporter-tutor`) · `play-risky-ruins-when-net-positive` (needs Infra D).

### Phase-B BUILD PROGRESS (2026-07-03, TDD)

- **M1 · playable agent — DONE** (`strategy.py` + `main.py`; `check_agent` PASS).
- **Infra A1 · Phantom Dive spread parser — DONE.** `AttackStat.benchSpread` + `parse_attack_bench_spread`
  ("Put N counters … in any way you like" → N×10); Phantom Dive=60, Jet Headbutt/Cruel Arrow=0. Tests green.
- **Infra A2 · spread valuation — DONE.** `_rider_spread` + `_spread_ko_prizes` (subset knapsack: max prizes
  from KOing benched mons within the 60) + `_bench_spread_bonus` (sub-prize chip), wired into `_tactical`
  and `_best_affordable_ko_value` parallel to the snipe rider. 4 new tactical tests + **full suite green (1202)**.
- **A3 PROBE — RESOLVED (the §8 open question).** Self-play probe (`scratchpad/probe_phantom_dive.py`): the
  attack is chosen at MAIN as `{type:13, attackId:154}`, then the engine asks **6 sequential single-counter
  selects**, each `context = DAMAGE_COUNTER_ANY (14)`, `min=max=1`, options = `{type:3, area:5 (BENCH),
  index}` — pick which benched mon gets THIS counter. **Context 14 ≠ DAMAGE(15)**, so the snipe cluster does
  NOT fire; the placement is currently unguided. **`DAMAGE_COUNTER_ANY` is ALSO Munkidori's "onto opponent"
  target context** — so the ctx-14 offensive-placement policy (A3) is SHARED with Infra C's target half.
- **A3 · placement policy — DONE.** `_DAMAGE_COUNTER_ANY` constant + `Board.best_counter_slot` +
  `Context.counter_is_best_placement` + the general rule **`place-counter-to-convert`** (baseline_snipe,
  the adjacent bench-targeting cluster). Per counter, knapsack-optimal (`_best_ko_subset`, shared with A2's
  valuation): finish the closest-to-dying member of the highest-prize affordable KO set (budget =
  `remainDamageCounter`×10), else pre-load the lowest-HP opp target. Recomputed per select → correct
  sequential greedy. **4 placement tests + full suite green (1206, deterministic order).** *(The lone
  random-order failure is pre-existing native-engine global-state flakiness, unrelated — passes in isolation
  and `_bench_spread_bonus` is 0 for every non-spread attack.)* **This ctx-14 policy also targets Munkidori's
  "onto opponent" half (C).**
- **Infra C · Munkidori Adrena-Brain — DONE (v1).** Probe corrected the assumption: the ability is a MAIN
  `ABILITY` option (already activated by the default — the probe captured its selects), then **3 selects**:
  `REMOVE_DAMAGE_COUNTER`(16)=SOURCE (our Pokémon, remove=heal) → `REMOVE_DAMAGE_COUNTER_COUNT`(40)=AMOUNT →
  `DAMAGE_COUNTER`(13)=TARGET (opponent, add=finish/chip). NOT ctx-14. Built: **target** = `place-counter-to-
  convert` extended to ctx-13 (budget→30, reuses A3's knapsack); **source** = `move-counters-off-the-damaged`
  (our most-damaged body = biggest heal, the reverse-heal); **amount** = `move-max-counters`. 3 tests + full
  suite green (1209). The offense+heal synergy (source heals our line WHILE the target chips theirs) subsumes
  the finish-vs-heal comparator for v1. *Deferred refinement:* explicit finish-vs-heal value-compare +
  win-con-preference on the source (v1 = most-damaged body).
- **Infra B · Cruel Arrow any-target — DONE.** A free-target "does N to 1 of your opponent's Pokémon"
  effect (Cruel Arrow) is routed in `build_attack_stats` to a full-damage **bench snipe** (`benchSnipe=100`,
  `damage=0`, ignores W/R) instead of fixed Active damage — so the oracle values + targets it as the benched
  finisher its doctrine role calls for. (13 pool attacks reclassified; test updated.)
- **Infra D · Stadium — DONE.** `Board.stadium_in_play` (id) + `Board.opp_stadium_in_play` read from
  `current.stadium` (`[{id, playerIndex}]`). Deck rule **`play-risky-ruins-when-net-positive`**: play Risky
  Ruins when no Stadium is up OR an opponent's is (replace it). *(bench-first sequencing + skip-vs-{D}-decks
  deferred to the Read.)*
- **`hold-evolution-until-attacker-ready` — DONE** (deck; `Context.evolve_body_energy` — hold the
  Drakloak→Dragapult evolve while the body has < 2 FP energy and my Active isn't doomed; counters the +40
  `evolve-into-wincon` pull, seed −18).
- **`bench-the-comeback-drawer` — DONE** (deck; bench Fezandipiti in RACE/STABILIZE with bench room).

### ✅ Phase B COMPLETE (2026-07-03)

All slices built test-first, **full suite green (1215 passed)**, and **`check_agent dragapult_ex` passes all
four gates** (contents / legality / playability / **deployability**). Deck-rule trigger tests:
`tests/agents/test_dragapult_ex_triggers.py` (6). Structural-infra tests: `tests/strategy/test_attack_value.py`
(spread valuation + placement + counter-move) + `tests/scouting/test_attack_riders.py` (spread parser). Every
shared-code change is guarded inert for non-dragapult decks (verified by the suite + the cluster
characterization guard). The agent is packaged and ladder-ready. **The human commits.**

---

## Appendix A · Phase-0 raw fact dump (verbatim substrate — engine ground truth)

```
# Deck facts — dragapult_ex (60 cards, 21 unique)

## Pokémon

### 2× Munkidori — Basic Psychic · 110 HP · 1 prize
- weakness Darkness · resist Fighting · retreat 1
- function tags: confuse, heal, spread
- Ability — Adrena-Brain: Once during your turn, if this Pokémon has any {D} Energy attached, you
  may move up to 3 damage counters from 1 of your Pokémon to 1 of your opponent's Pokémon.
- PC — Mind Bend (60): Your opponent's Active Pokémon is now Confused.

### 4× Dreepy — Basic Dragon · 70 HP · 1 prize
- weakness - · resist - · retreat 1
- P — Petty Grudge (10)
- FP — Bite (40)

### 4× Drakloak — Stage 1 Dragon · 90 HP · 1 prize · evolves from Dreepy
- weakness - · resist - · retreat 1
- function tags: dig, draw
- Ability — Recon Directive: Once during your turn, you may look at the top 2 cards of your deck and
  put 1 of them into your hand. Put the other card on the bottom of your deck.
- FP — Dragon Headbutt (70)

### 3× Dragapult ex — Stage 2 Dragon · 320 HP · 2 prize · ex Tera · evolves from Drakloak
- weakness - · resist - · retreat 1
- function tags: spread
- C — Jet Headbutt (70)
- FP — Phantom Dive (200): Put 6 damage counters on your opponent's Benched Pokémon in any way you like.

### 1× Fezandipiti ex — Basic Darkness · 210 HP · 2 prize · ex
- weakness Fighting · resist - · retreat 1
- Ability — Flip the Script: Once during your turn, if any of your Pokémon were Knocked Out during your
  opponent's last turn, you may draw 3 cards. You can't use more than 1 Flip the Script Ability each turn.
- CCC — Cruel Arrow (0): This attack does 100 damage to 1 of your opponent's Pokémon. (Don't apply
  Weakness and Resistance for Benched Pokémon.)

### 4× Cinderace — Stage 2 Fire · 160 HP · 1 prize · evolves from Raboot
- weakness Water · resist - · retreat 0
- function tags: opener, energy_accel
- Ability — Explosiveness: If this Pokémon is in your hand when you are setting up to play, you may put
  it face down in the Active Spot.
- C — Turbo Flare (50): Search your deck for up to 3 Basic Energy cards and attach them to your Benched
  Pokémon in any way you like. Then, shuffle your deck.

### 1× Meowth ex — Basic Colorless · 170 HP · 2 prize · ex
- weakness Fighting · resist - · retreat 1
- function tags: search, stall
- Ability — Last-Ditch Catch: Once during your turn, when you play this Pokémon from your hand onto your
  Bench, you may use this Ability. Search your deck for a Supporter card, reveal it, and put it into your
  hand. Then, shuffle your deck. You can't use more than 1 Ability that has "Last-Ditch" in its name each turn.
- CCC — Tuck Tail (60): Put this Pokémon and all attached cards into your hand.

## Supporter
- 3× Boss's Orders · gust — Switch in 1 of your opponent's Benched Pokémon to the Active Spot.
- 3× Crispin · energy_accel, search, tutor_energy — Search your deck for up to 2 Basic Energy cards of
  different types, reveal them, and put 1 of them into your hand. Attach the other to 1 of your Pokémon.
- 2× Judge · draw, hand_disruption, shuffle_hand — Each player shuffles their hand into their deck and draws 4.
- 4× Lillie's Determination · draw, shuffle_hand — Shuffle your hand into your deck. Then, draw 6 cards.
  If you have exactly 6 Prize cards remaining, draw 8 cards instead.

## Item
- 1× Unfair Stamp [ACE SPEC] · draw, hand_disruption — Use only if any of your Pokémon were KO'd during
  your opponent's last turn. Each player shuffles hand into deck; you draw 5, opponent draws 2.
- 4× Buddy-Buddy Poffin · search, bench_fill — Search deck for up to 2 Basic Pokémon with 70 HP or less
  onto Bench. (Only Dreepy qualifies here.)
- 2× Night Stretcher · recycle — Put a Pokémon or a Basic Energy from discard into hand.
- 3× Crushing Hammer · energy_denial — Flip a coin; heads, discard an Energy from 1 opponent's Pokémon.
- 4× Ultra Ball · cost_discard, search, tutor_pokemon — Discard 2 cards; search deck for any Pokémon.
- 4× Poké Pad · search — Search deck for a Pokémon that doesn't have a Rule Box; put in hand.

## Stadium
- 2× Risky Ruins — Whenever any player puts a Basic non-{D} Pokémon onto their Bench during their turn,
  place 2 damage counters on that Pokémon.

## Energy
- 4× Basic {R} (Fire) · 3× Basic {P} (Psychic) · 2× Basic {D} (Darkness)
```
