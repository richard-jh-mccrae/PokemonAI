# vs Hop's Trevenant / Hop's Snorlax — Counterplay Doctrine

> Phase-A deliverable of `/matchup-genie`. The **objective** game-plan against ONE opponent archetype;
> the machine `src/common/scouting/briefs/hop_s_trevenant_hop_s_snorlax.json` Brief is generated from this
> **after sign-off** (ADR-0027). Shared across all our decks — write deck-neutral; each agent relativizes it.

**Slug:** `hop_s_trevenant_hop_s_snorlax` · **Status:** `locked → shipping` · **Last grilled:** 2026-07-09 · **Author:** matchup-genie + Richard
**Covers** (from `data/meta/decks/index.json`): `Hop's Trevenant`, `Hop's Trevenant / Hop's Cramorant`, `Hop's Trevenant / Hop's Cramorant / Hop's Snorlax`, `Hop's Trevenant / Hop's Snorlax` — every variant routes to this one Brief.
**Meta note:** rank **3** by play-rate (**30.69%** — a top-3 meta deck), **54.65%** win-rate, 1661 episodes. An all-single-prize Hop's aggro-control / revenge-trap deck.

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped (`dump_deck.py --deck-dir data/meta/decks/hop_s_trevenant_hop_s_snorlax`) + `covers` read from index.json
- [x] Phase 1 how-it-wins confirmed (user: read right, **tempo = midrange**)
- [x] Phase 2 counterplay research synthesised (65 agents, 8 sources, confidence **high**, 27/45 verified, 0 material conflicts)
- [x] Phase 3 weakness grill: `8/8` seams locked (3 decisions resolved 2026-07-09)
- [x] Phase 4 Brief-field reconciliation complete (4 opponent_properties incl. 2 new keys, 3 threats, 1 target)
- [x] Phase 5 signed off → Phase B authorised (user: Snorlax threat-only, exclude Dunsparce, **mint both keys**)
- [x] Phase B: Strategy Proposal emitted → `data/strategy/proposals/matchup-20260709-hop_s_trevenant_hop_s_snorlax.md` + 2 keys registered. **matchup-genie stops here** (→ `/update-strategy` authors the Brief JSON)

Open seams to grill: single-prize economy, fragile pre-evos (Phantump 70 / Dunsparce 60), boost-stack dependence + Postwick stadium war, Mist-Energy effect-immunity (blunts OUR disruption), Corner retreat-lock, Horrifying Revenge punish-the-trade, all-special-energy base (denial live), mixed weakness (Darkness vs Trevenant / Fighting vs Snorlax+Dunsparce), donk window, Dudunsparce-is-a-trap. Open questions: tempo = midrange vs fast; does Mist-immunity warrant a new opponent_properties key.

## 1 · How it wins

- **Win condition:** Grind out 6 prizes with a stacked-boost **single-prize** Hop's attacker that *traps* your Active and *punishes* you for trading. Every body is **1 prize** (no ex / Mega-ex) — prize-efficient, and it recurs its Hop's bodies with Night Stretcher ×3. It's a **trade-control / revenge** deck, not a burst-race or a mill.
- **The damage engine (three stacking +30 boosts, all *before* Weakness):** `Hop's Snorlax` **Extra Helpings** (ability: your Hop's attacks do **+30** to the Active; doesn't stack with itself) + `Hop's Choice Band` (Tool: **+30** and attacks cost **{C} less**) + `Postwick` (Stadium: Hop's attacks do **+30**). All three at once = **+90** on top of base.
- **Line(s) / main attackers (the threats):**
  - `Hop's Phantump` (Basic, 70 HP) → **`Hop's Trevenant`** (Stage 1, 140 HP). **Corner** (PCC, 90): the Defending Pokémon **can't retreat** next turn → *traps* your Active. With all boosts = **180** and a lock. **Horrifying Revenge** (C, 30): **+100** if any of your Hop's Pokémon were KO'd by an attack last turn → 130 base, **up to 220** boosted — and **Choice Band drops its cost to 0 energy**. This is the revenge punish: trading into a Hop's body invites a free ~220 swing.
  - **`Hop's Snorlax`** (Basic, 150 HP) — the Extra Helpings **aura source** and a wall. **Dynamic Press** (CCC, 140, **+80 to itself**) = up to **230** boosted, but self-damages to 70 → burst, not sustained.
- **Engine (draw/search):** `Dunsparce` (Basic 60) → `Dudunsparce` (Stage 1 140) **Run Away Draw** (draw 3, then shuffle itself + attached back into the deck — repeatable, **self-recurring**). Plus a heavy item/supporter draw package: `Lillie's Determination` ×4 (shuffle hand, draw 6 / **8 if 6 prizes left**), `Pokégear 3.0` ×4 (dig 7 for a Supporter), `Poké Pad` ×4 (search a non-Rule-Box Pokémon), `Hop's Bag` ×3 (2 Basic Hop's → bench), `Brock's Scouting` ×2 (2 Basic / 1 Evo), `Buddy-Buddy Poffin` ×4 (2 ≤70-HP Basics → bench), `Colress's Tenacity` ×2 (search Stadium + Energy). Draw is **redundant + distributed** — no single draw Pokémon the deck can't live without.
- **Acceleration / energy:** all **9 energy are SPECIAL** — `Mist Energy` ×4 (provides {C}; **prevents all attack EFFECTS** done to the holder — damage still lands), `Telepath Psychic Energy` ×4 (provides {P}; on attach, search **2 Basic {P}** → bench), `Legacy Energy` ×1 [ACE SPEC] (any type, 1 at a time; if the holder is KO'd by an attack, we take **1 fewer prize** — once per game). No basic energy at all.
- **Disruption (what it does to US):** `Boss's Orders` ×2 (gust our bench piece Active — reach around our wall / drag a fragile piece out); `Corner` retreat-lock (traps our Active in the kill zone); `Postwick` (stadium — can overwrite ours).
- **Tempo:** **midrange** (confirmed) — Trevenant is only Stage 1 (Phantump → Trevenant, online ~T2), Snorlax is a Basic, but a *fully boosted* Corner wants Trevenant + 2–3 energy + Snorlax benched + Choice Band + Postwick, which is a real multi-piece setup. Faster than a Stage-2 deck; slower than a pure aggro donk deck.
- **User context:** _(none supplied yet)_

## 2 · Counterplay research (cited)

Engine-grounded synthesis; a web counterplay sweep (5 angles, 6 key cards, **65 agents, 8 sources**,
**confidence high**, **27/45** claims survived adversarial verification, **0 material mechanics
conflicts**) folded on lock. Per CLAUDE.md the web is a *strategy* prior only — every load-bearing
mechanic rests on verified engine facts. Coverage is thin (bleeding-edge set) but consistent; matchup
win-rate figures cited by guides are tiny-sample external data, **not** encoded.

**How it's beaten (objective):** don't play the deck's game (get trapped + trade into Horrifying
Revenge) — **race the fragile Stage-1 setup, out-math the boost stack through Weakness, and starve the
all-special energy base.** Six levers do the work:

- **(a) Race through Weakness — the cleanest lever.** Weakness ×2 is applied *after* the +90 boost stack
  and **ignores Mist entirely** (weakness/damage aren't "effects"). A **Darkness** attacker roughly halves
  the HP needed to kill the 140-HP **Trevenant** (its only wincon attacker, Darkness ×2 / Fighting-resist);
  a **Fighting** attacker OHKOs the 150-HP **Snorlax** aura and the Dunsparce/Dudunsparce line (Fighting
  ×2). No single type covers the whole board, so which half you hit depends on our attacker's type.
- **(b) Deny the Horrifying Revenge trigger (timing).** The +100 is **conditional** — it only arms if one
  of their Hop's bodies was KO'd **by attack damage during our last turn**. So *control trade timing*: KO
  on non-attack terms (bench/spread/effect KOs) or decline the trade, and Revenge stays at **30 base**
  (~130 boosted, not ~220). **Never over-commit to a straight KO race** — the deck is *built* to punish it.
- **(c) Starve the all-special energy base — the sharpest structural seam.** **All 9 energy are special**
  (4 Mist + 4 Telepath + 1 Legacy) and there is **no discard-recovery for special energy**: Night
  Stretcher recovers only "a Pokémon or **Basic** Energy," and Colress's Tenacity only fetches from deck.
  Any energy **discard-off-attacker** or **energy-lock** starves both Corner (PCC) and Horrifying Revenge
  with almost no path to rebuild. (Deck-relative: needs our deck to run energy denial.)
- **(d) Win the stadium war.** Postwick is one of the three +30 layers; only one stadium sits in play and
  **we run no Hop's Pokémon**, so overwriting it with our own stadium **deletes +30 from every Hop's
  attack** (Corner 180→150), breaking specific KO breakpoints. They run 4 copies → ongoing attrition, not
  a one-time kill.
- **(e) Race the midrange setup window.** Trevenant is a Stage 1 that needs Phantump-evolution + tool +
  stadium + a benched Snorlax before it hits real numbers, and the as-built list has **no own-board
  switch-in enabler** (Boss's Orders gusts *us*), so it likely **manual-promotes** its attacker after a KO
  — clunky. Pressure the board before the stack + draw engine come online; force under-boosted or
  self-damaging attacks (Snorlax's Dynamic Press self-KOs it into the 70-HP zone).
- **(f) Don't waste effect-riders on Mist-holders.** Mist protects **only its own holder** and **only vs
  attack EFFECTS** (status / can't-retreat / snipe-redirect fizzle) — **damage, abilities, and spread all
  land**. Route status/switch/energy-discard riders at non-Mist bodies; win Mist-holders on raw damage.

**Key-card findings (function + how we blunt it):**
- **Hop's Trevenant** — the wincon. **Corner** (PCC, 90→180) traps the Active (no-retreat) while the stack
  kills it; **Horrifying Revenge** (C, 30 → ~130 → ~220 boosted, **free with Choice Band**) punishes
  return-KOs. Blunt: **Darkness ×2 OHKO**; deny the Revenge trigger; play around the retreat-lock with a
  **switch** (switch effects bypass "can't retreat" — rules L89: "card effects can switch for free").
- **Hop's Snorlax** — the **Extra Helpings +30 aura** (the damage floor lifting Corner/Revenge over our HP
  thresholds) **plus** a 150-HP wall + emergency Dynamic Press (140, self-80). **The aura is an always-on
  ability that works from the BENCH** (rulebook L148) — so **gusting Snorlax Active does NOT disable it**;
  only **KO-ing it** (Fighting ×2 OHKO) or **ability-lock** removes the +30 board-wide.
- **Dunsparce / Dudunsparce** — the **self-recurring draw line** (Run Away Draw: draw 3, shuffle self +
  attached back). Redundant (4/3 split + heavy search), not a combat threat. **A poor removal target** —
  Dudunsparce refunds any KO/gust; the only clean off-switch is **ability-lock**. Snipe the wincon line
  (Phantump), not this.
- **Postwick** — the +30 stadium; overwrite it (stadium war) to strip a boost layer.
- **Hop's Choice Band** — +30 **and** −{C} cost → enables **0-energy Horrifying Revenge / PC Corner**, so a
  fresh Trevenant attacks immediately. It's a Tool (removable by tool-removal if our deck has it).
- **Mist Energy** — special {C} that makes its holder **effect-immune** (our riders fizzle); **damage &
  abilities & spread bypass it**. Web (cardsrealm) wrongly claims it blocks spread damage — **FALSE** per
  engine.

**Web-vs-engine conflicts surfaced:** **Mist Energy** — cardsrealm claims it blocks spread/damage-counter
damage; **engine says damage is not an effect**, so Mist is damage-transparent (only riders fizzle). Minor
base-damage phrasing drift in guides (Revenge cited as 120/130 "base"; engine = 30 base + 100 conditional)
— boosted totals reconcile. Guides also describe a **variant** (Hop's Dubwool switch-in enabler, Spiky
Energy) **not in this 60-card list** — treat splash/switch-enabler commentary as out-of-scope.

**Sources** (web strategy priors; engine facts — `data/EN_Card_Data.csv`, `docs/rules.md` — are primary):
- Hop's Trevenant deck list (1st Place, Special Event Turin) — <https://limitlesstcg.com/decks/list/27927>
- Standard Deck Tech — Hop's Trevenant (Special Event / Miyagi City League Winner) — <https://pokemon.cardsrealm.com/en-us/articles/pokemon-tcg-standard-deck-tech-hops-trevenant-special-event>
- Hop's Trevenant Deck Guide (Ascended Heroes) — <https://deltiasgaming.com/pokemon-tcg-hops-trevenant-deck-guide-ascended-heroes/>
- Hop's Trevenant — matchup / win-rate data — <https://play.limitlesstcg.com/decks/hops-trevenant>
- Card refs: Mist Energy (TEF 161), Postwick (JTG 154), Dudunsparce (TEF 129) — Bulbapedia

## 3 · Exploitable seams (the weakness map)

### Seam 1 — Race through Weakness (the boost stack + Mist don't protect vs ×2)
- **Weakness:** all three +30 boosts apply **before** Weakness (dump text + rules L255-270), and Mist
  blocks only *effects* — so a Weakness-type OHKO cuts **straight through** the +90 buffer and the Mist
  shield. **Trevenant/Phantump = Darkness ×2** (140 / 70 HP); **Snorlax/Dunsparce/Dudunsparce = Fighting
  ×2** (150 / 140 / 60 HP). Trevenant/Phantump also **resist Fighting −30** (wrong type into them).
- **Exploit:** attack the wincon **Trevenant** with **Darkness** (halves the HP needed) and the **Snorlax**
  aura / Dunsparce line with **Fighting**. No single type covers the board — pick by our attacker's type.
- **Maps to:** type intel (already in the auto-Dossier card facts) → counterplay prose + `target` notes.

### Seam 2 — Horrifying Revenge's +100 is conditional (deny the trigger)
- **Weakness:** the +100 only arms if a Hop's body was KO'd **by attack damage during our last turn**;
  otherwise Revenge is 30 base (~130 boosted).
- **Exploit:** **control trade timing** — KO on non-attack terms (bench/spread/effect KOs) or decline the
  trade so Revenge stays small; **never over-commit to a straight KO race**, which is exactly the deck's
  bait.
- **Maps to:** `threat: Hop's Trevenant` (the punish) + counterplay prose. No Board key (it's a
  sequencing read the Turn Planner would own, not a static property).

### Seam 3 — All-special energy base, no discard-recovery (the sharpest structural seam)
- **Weakness:** **9/9 energy are special**; **no card recovers special energy from discard** (Night
  Stretcher = "Pokémon or **Basic** Energy"; Colress's Tenacity = deck-only). Discard/lock is near-permanent.
- **Exploit:** **energy discard-off-attacker / energy-lock** starves Corner (PCC) and Revenge with no
  rebuild. **Deck-relative** — only live if our deck runs energy denial.
- **Maps to:** **`opp_special_energy_fragile = true`** — **MINTED** (grilled: mint) + registered
  `consumer: "unwired"`. Reusable objective property for any all-special-energy-with-no-recovery deck.

### Seam 4 — Postwick is an overwritable +30 layer (stadium war)
- **Weakness:** one shared stadium slot; we run no Hop's Pokémon, so overwriting Postwick is pure upside
  (−30 to every Hop's attack; Corner 180→150).
- **Exploit:** drop our own stadium to break a specific KO breakpoint; repeat vs their 4 copies (attrition).
- **Maps to:** counterplay prose (stadium capability is deck-relative). No Board key.

### Seam 5 — Fragile Stage-1 setup + no own switch enabler (race the window)
- **Weakness:** Trevenant needs Phantump-evolve + tool + stadium + benched Snorlax; **no own-board
  switch-in** (Boss's gusts *us*) → likely manual-promote its attacker after a KO. Not T1-explosive.
- **Exploit:** pressure the 1-prize board before the stack comes online; force under-boosted / self-KO
  (Dynamic Press) attacks. **Snipe the wincon pre-evo Phantump (70 HP) in the evolution window.**
- **Maps to:** `opp_tempo = "midrange"` + `target: Hop's Phantump` role `fragile_preevo`.

### Seam 6 — Mist Energy voids our attack EFFECTS (not damage)
- **Weakness (to us):** Mist-holders (usually Trevenant/Snorlax) are immune to our attack **riders**
  (status / can't-retreat / snipe-redirect / energy-discard-*via-attack-effect*) — but **damage, abilities,
  and spread all land**; web "blocks spread" claim is FALSE.
- **Exploit:** **math KOs on raw damage**; don't waste effect-riders into a Mist body — route them at
  non-Mist bodies; lean on abilities/spread which bypass Mist.
- **Maps to:** **`opp_effect_immune_bodies = true`** — **MINTED** (grilled: mint) + registered
  `consumer: "unwired"`. Captures "prefer raw damage / abilities / spread over effect-riders vs this deck."

### Seam 7 — All single-prize (race even trades; no multi-prize to farm)
- **Weakness:** no ex / Mega — every body is 1 prize, so no 2-for-1 gust swing to farm, but the Hop's line
  **does recur** (Night Stretcher ×3) so each KO isn't fully permanent. **Legacy Energy** [ACE SPEC]
  denies us **1 prize once/game** on the body it's attached to when we KO it.
- **Exploit:** **win the prize race on even trades** while denying the Revenge trigger (Seam 2); don't
  chase multi-prize plans that have no target here. Expect the Legacy body to eat one "free" KO.
- **Maps to:** `opp_single_prize = true` (reuse registered key).

### Seam 8 — Dudunsparce is a TRAP, not a target
- **Weakness (inverted):** Run Away Draw self-shuffles Dudunsparce + attached back into the deck — any
  KO/gust on it is **refunded**; the draw is redundant (4/3 + heavy search) anyway.
- **Exploit:** **ignore it** (ability-lock is the only clean off-switch). Snipe the **wincon** line
  (Phantump); race the single-prize bodies.
- **Maps to:** an explicit **anti-target** note in §4 / the Brief `targets` reasoning.

## 4 · Threats & targets (objective card-level intel)

- **Threats** (respect):
  - `Hop's Trevenant` — the wincon. Corner (PCC, 90→180) traps the Active with a no-retreat lock; Horrifying
    Revenge (C, 30→~130→~220, free with Choice Band) punishes return-KOs. Cheap 1-prize Stage 1. **Darkness ×2.**
  - `Hop's Snorlax` — the Extra Helpings **+30 aura** (always-on, **from the bench**) is the damage floor;
    also a 150-HP wall + Dynamic Press burst (140, self-80). Removing it (KO / ability-lock, **not** a gust)
    drops their whole board below KO breakpoints. **Fighting ×2.**
  - `Boss's Orders` — the deck's only reach to our bench; gusts a fragile piece Active to KO around a wall
    or to reposition. Don't leave a snipeable key piece benched assuming it's safe.
- **Targets** (disrupt / snipe), by role:
  - `fragile_preevo`: `Hop's Phantump` — 70 HP, 1 prize, Darkness ×2, base of the **only** wincon line;
    snipe/gust in the evolution window to deny a Trevenant prize-free. **The one target row** — it arms the
    live `brief_preevo` lever at the high-value wincon pre-evo.
  - `prize_liability`: **none** — no ex / Mega-ex.
  - **Anti-targets (do NOT list / snipe):**
    - `Dudunsparce` / `Dunsparce` — the redundant, self-recurring draw line; Dudunsparce refunds any KO/gust
      (Run Away Draw) and denying one node is low-value. Ability-lock is the only clean off-switch.
      **(Grilled: Dunsparce EXCLUDED as a fragile_preevo target — keep `brief_preevo` pointed only at Phantump.)**
    - `Hop's Snorlax` — a **threat, not a target** (see above). The aura is always-on **from the bench**, so
      a gust doesn't disable it; removing it needs a Fighting ×2 KO or ability-lock (deck-relative), so it
      stays a threat note. **(Grilled: threat-only — no `engine` target row.)**

## 5 · Objective counterplay summary

Beat Hop's Trevenant / Snorlax by **refusing its game** — don't get trapped and don't trade into
Horrifying Revenge. **Race the fragile Stage-1 setup** (snipe the 70-HP **Hop's Phantump** wincon pre-evo
in the evolution window; it manual-promotes its attacker, so it's clunky), and **out-math the +90 boost
stack through Weakness** — a **Darkness** OHKO on the 140-HP **Trevenant** or a **Fighting** OHKO on the
150-HP **Snorlax** aura cuts straight through the boosts and ignores Mist. **Deny the Revenge trigger** by
controlling trade timing (KO on non-attack terms; never over-commit to a straight KO race) and **win the
prize race on even trades** (all bodies are 1 prize; expect one Legacy-Energy prize-denial). Structural
levers where our deck supports them: **energy discard/lock** (all 9 energy are special with **no
discard-recovery** — the sharpest seam), a **stadium** to overwrite Postwick's +30, and a **switch** to
escape Corner's lock. **Don't** waste effect-riders on Mist-holders (raw damage / abilities / spread
bypass Mist) or sink removal into **Dudunsparce** (it self-shuffles).

## 6 · Brief preview (pre-JSON — filled in Phase 4, emitted in Phase 6)

```
tempo = "midrange"
opponent_properties = {
  "opp_single_prize":          true,       # reuse — no ex/Mega; race even trades, no 2-for-1 to farm (line recurs via Night Stretcher)
  "opp_tempo":                 "midrange", # reuse — fragile Stage-1 setup; a real window before the boost stack is online
  "opp_special_energy_fragile": true,      # NEW KEY (minted + registered, consumer: unwired) — 9/9 special energy, NO discard-recovery
  "opp_effect_immune_bodies":   true       # NEW KEY (minted + registered, consumer: unwired) — Mist Energy voids our attack EFFECTS on the holder
  # NOT asserted: opp_is_engine_dependent (draw is redundant + self-recurring), opp_donk_vulnerable
  #   (60/70 basics but Poffin/Bag/Telepath flood the bench), opp_is_heal_wall, opp_pierces_active_effects.
}
threats = [
  { "card": "Hop's Trevenant", "why": "Wincon. Corner (PCC 90->180) no-retreat traps the Active; Horrifying Revenge (C, 30->~130->~220, free w/ Choice Band) punishes return-KOs. Darkness x2." },
  { "card": "Hop's Snorlax",   "why": "Extra Helpings +30 aura (always-on FROM THE BENCH) is the damage floor lifting Corner/Revenge over our HP thresholds; 150-HP wall + Dynamic Press 140 (self-80). Remove by KO/ability-lock, not gust. Fighting x2." },
  { "card": "Boss's Orders",   "why": "The deck's only reach to our bench; gusts a fragile piece Active to KO around a wall / reposition." }
]
targets = [
  { "card": "Hop's Phantump", "role": "fragile_preevo", "why": "70 HP, 1 prize, Darkness x2; base of the ONLY wincon line. Snipe/gust in the evo window to deny a Trevenant prize-free." }
]
# Anti-targets flagged in reasoning: Dudunsparce/Dunsparce self-recurring draw line (Run Away Draw refunds a KO/gust);
#   Hop's Snorlax is a THREAT not a target (aura works from bench — a gust doesn't disable it).
```

## 7 · Open questions / deferred

**Resolved at grill (2026-07-09):**
- **Snorlax role** — **threat-only** (user call). It's an aura/wall, not draw/search; the aura works from
  the bench so a gust can't disable it, and KO/ability-lock removal is deck-relative — kept as a threat
  note, no `engine` target row.
- **Dunsparce** — **excluded** as a fragile_preevo target (user call, matches draft). The Dunsparce/
  Dudunsparce draw line is redundant + self-recurring; the live `brief_preevo` lever stays pointed only at
  the high-value wincon pre-evo Phantump. Flagged as an anti-target.
- **`opp_special_energy_fragile`** — **MINTED** (user call). All 9 energy special, no discard-recovery;
  reusable objective property. Registered `consumer: "unwired"` — an inert forward contract until a
  consumer wires it (flagged in the Phase-B proposal diff).
- **`opp_effect_immune_bodies`** — **MINTED** (user call). Mist Energy voids our attack EFFECTS on the
  holder (damage/abilities/spread bypass). Registered `consumer: "unwired"` — forward contract, flagged.

**Deferred (not blocking the Brief — inert/deck-relative today):**
- Both new keys await consumer wiring before they change any play (forward contracts; flagged in the diff).
- Energy-denial, stadium-overwrite, switch-out-of-Corner, Darkness/Fighting attacker, ability-lock are all
  **deck-relative capabilities** — each agent maps them to its own roster (`/deck-genie`), not objective keys.
- Web matchup win-rate figures (tiny-sample) — noted, not encoded.
- Legacy Energy [ACE SPEC] one-time prize-denial timing — under-covered; expect one "free" KO on that body.
