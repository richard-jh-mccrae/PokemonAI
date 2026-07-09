# vs Dragapult ex — Counterplay Doctrine

> Phase-A deliverable of `/matchup-genie`. The **objective** game-plan against ONE opponent archetype;
> the machine `src/common/scouting/briefs/dragapult_ex.json` Brief is generated from this **after sign-off**
> (ADR-0027). Shared across all our decks — write deck-neutral; each agent relativizes it.

**Slug:** `dragapult_ex` · **Status:** `locked` · **Last grilled:** 2026-07-09 · **Author:** matchup-genie + Richard
**Covers** (from `data/meta/decks/index.json`): `Dragapult ex`, `Dragapult ex / Dusknoir`, `Dragapult ex / Dusknoir / N’s Zoroark ex` — every variant routes to this one Brief.

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped (`dump_deck.py --deck-dir data/meta/decks/dragapult_ex`) + `covers` read from index.json
- [x] Phase 1 how-it-wins confirmed (2026-07-09; win-con = Phantom Dive spread behind 320 no-weakness wall; base-build scope, Dusknoir/Zoroark variant gap noted)
- [x] Phase 2 counterplay research synthesised (high confidence, 58/69 claims verified) — engine-fact reconciled (Tera bench-immunity VERIFIED)
- [x] Phase 3 weakness grill: **8/8 seams locked**
- [x] Phase 4 Brief-field reconciliation complete — **3 decisions resolved** (D1 mint `opp_spreads_bench` ✓ · D2 mint `opp_item_locks` ✓ · D3 `opp_is_engine_dependent`=false ✓); both new keys registered in `src/common/scouting/opponent_properties.json` (`consumer: "unwired"`)
- [x] Phase 5 signed off (2026-07-09) → **Phase B complete**: Strategy Proposal emitted → `data/strategy/proposals/matchup-dragapult_ex.md` (`target_layer: matchup-brief`, `verification_contract: brief-validator`, provenance → this doc). **Hand-off to `/update-strategy`** to author `src/common/scouting/briefs/dragapult_ex.json` behind the validator gate (ADR-0046).

**Decisions resolved (see §7):** D1 mint `opp_spreads_bench` (YES) · D2 mint `opp_item_locks` (YES) · D3 `opp_is_engine_dependent` = false (NOT set).
**matchup-genie is DONE for this archetype.** Next: `/update-strategy` applies the proposal (writes the Brief JSON, runs `validate_brief.py`, human commits). The Brief does not ship — and the two new keys stay inert — until then.

## 1 · How it wins  *(CONFIRMED 2026-07-09)*

- **Win condition:** Set up a **Dragapult ex** (Stage 2, 320 HP, **2 prizes**, **NO weakness**, **Tera**) and win with **Phantom Dive** ({R}{P}, **200 to the Active + 60 spread** = 6 damage counters placed on the opponent's **Bench** in any distribution) each turn. It takes prizes **two ways at once** — a big Active hit *plus* softening the Bench so the next Phantom Dive or a **Cruel Arrow** finisher converts the chip into extra KOs. The 320-HP no-weakness body is very hard to OHKO, so it out-durables grinders while the spread out-tempos them. Prize math: Dragapult ex / Fezandipiti ex / Latias ex / Meowth ex = **2 each**; Dreepy / Drakloak / Budew = **1 each**.
- **Line(s):** `Dreepy (Basic, 70 HP) → Drakloak (Stage 1, 90 HP) → Dragapult ex (Stage 2, 320 HP)`, thick **4-4-3**. **Rare Candy ×2** skips Drakloak. **Online turn 2–3** via Ultra Ball ×4 / Buddy-Buddy Poffin ×4 / Poké Pad ×3 / Brock's Scouting ×2 / Crispin ×4 / Lillie's ×4.
- **Main attacker(s):**
  - **Dragapult ex — Phantom Dive ({R}{P}, 200 + 60 Bench spread).** The wincon. Cheap 2-energy dual-type cost; flat 200 (no innate boost) to the Active; 6-counter spread on our **Bench** sets up Bench KOs.
  - **Dragapult ex — Jet Headbutt ({C}, 70).** Cheap opener/filler before the spread is worth it.
  - **Fezandipiti ex — Cruel Arrow ({C}{C}{C}, 0 base → 100 to ANY 1 Pokémon, ignores Bench W/R).** Free-aim 100 snipe finisher that converts Phantom Dive's Bench chip into KOs — but **3 energy** to power (deck runs only 8 energy), so **situational**, not every-turn. Its real value is the **ability** (see engine).
  - **Latias ex — Eon Blade ({P}{P}{C}, 200; can't attack next turn).** One-off 200 punch that OHKOs ~200-HP bodies then self-locks; a respect-window, not a clock. Mostly present for **Skyliner**.
- **Engine (draw/search):**
  - **Drakloak — Recon Directive** (once/turn: look top 2, take 1, other to bottom) — the recurring Pokémon dig engine.
  - **Fezandipiti ex — Flip the Script** (draw 3 if any of your Pokémon were KO'd last turn) — recovery draw after trades.
  - **Meowth ex — Last-Ditch Catch** (on play to Bench: tutor a Supporter) — consistency toolbox; **value banked on entry** (can't be denied after it lands).
  - **Trainer engine (redundant, load-bearing):** Ultra Ball ×4, Poké Pad ×3, Brock's Scouting ×2, Buddy-Buddy Poffin ×4, Crispin ×4 (energy accel + tutor: 2 basic energy of different types, attach 1), Lillie's Determination ×4 (draw 6 / 8 at 6-prize).
  - **Acceleration:** **Crispin only** (the dual-type enabler for Phantom Dive's {R}{P}); **8 energy total** (4 Fire / 4 Psychic) — no Pokémon-based ramp.
  - **Disruption (to US):** **Crushing Hammer ×4** (coin-flip discard our Energy, ~2 expected hits/game), **Boss's Orders ×3** (gust our key piece), **Budew — Itchy Pollen** (lock our Items for a turn), **Unfair Stamp** ACE SPEC (hand disruption after a KO), **Team Rocket's Watchtower ×2** (Stadium: {C} Pokémon have no Abilities — both players; also shuts off their own Meowth).
  - **Pivot:** **Latias ex — Skyliner** (your Basic Pokémon have no retreat cost — free pivoting for Dreepy/Budew/the ex Basics **including Latias itself**; does NOT free-retreat the evolved Drakloak/Dragapult).
- **Tempo:** **midrange** (Stage 2 wincon, online turn 2–3 — faster than a clunky Stage 2 via Rare Candy + heavy search, but no attack before ~T2 and no energy accel beyond Crispin). Durable-grindy once online (320 no-weakness wall + spread).
- **User context:** *(none supplied — Brief must posture ALL our decks vs this archetype).*

## 2 · Counterplay research (cited)

**Coverage caveat (load-bearing):** the web has broad Dragapult ex coverage, but almost all of it describes the **STANDARD-format shell** (Charizard ex / **Dusknoir** partner, Arven / Iono / Professor's Research, Munkidori, Neo Upper Energy ACE SPEC). This engine's **base list runs NONE of those** — it uses Crispin / Lillie's Determination / Brock's Scouting for draw+search and **Unfair Stamp** as its ACE SPEC. **Core Dragapult ex card facts all MATCH the engine** (320 HP, NO weakness, 2 prizes, Stage 2, Phantom Dive 200 + 6 counters, no built-in energy accel). So the *shell* advice may not transfer, but the *principles* (race the pre-evos, deny/reverse the spread, energy-deny the low count, out-HP the flat 200, gust the support ex) are deck-neutral and are what this doctrine keeps. Named external counters in the sources (Miraidon ex, Blissey/Munkidori damage-reversal, Banette ex, TM Devolution, League HQ) are **out-of-format** cards not in this sim's pool — only their principles are used, no specific counter card is assumed present.

**Key-card findings** (its threats + engine — function + how we blunt it):
- **Dragapult ex** — wincon. Phantom Dive flat 200 Active + 60 Bench spread; **Tera → a benched copy takes no attack damage** (can't be sniped/spread on the Bench). 320 / no-weakness → near-impossible to OHKO, but only **2 prizes**. Blunt it by racing the pre-evos before it evolves and out-HP-ing the flat 200; don't waste chip on the Active tank.
- **Fezandipiti ex** — recovery engine (Flip the Script: draw 3 after any of your Pokémon are KO'd) + Cruel Arrow (100 free-aim, ignores Bench W/R). 210 HP, **Fighting weak**, 2 prizes, **not Tera**. Gust it Active and KO for 2 prizes → deletes recovery + finisher in one shot; close fast to starve the draw-3.
- **Drakloak** — the real dig engine (Recon Directive) **and** the middle hop / rebuild piece; 90 HP, 1 prize, no weakness, not Tera. Snipe/gust to strip consistency + delay the rebuild.
- **Dreepy** — 70-HP Basic base of the line; pure setup fodder. KO before it evolves; clear multiples to beat the 4-4-3 redundancy.
- **Budew** — Itchy Pollen locks our Items one turn (setup tax); 30 HP, retreat 0, **Fire weak**, re-usable if left alive. Sequence items before the lock; OHKO the 30-HP body to stop repeat locks.
- **Latias ex** — Skyliner (their Basics free-retreat pivot) + Eon Blade 200 self-lock window; 210 HP, **Darkness weak**, 2 prizes, not Tera. Gust+KO for 2 prizes strips pivot mobility.
- **Meowth ex** — Last-Ditch Catch tutors a Supporter **on entry (value banked — can't deny after)**; 170 HP, 2 prizes, **Fighting weak**, Colorless (its own ability is shut off by their Watchtower). Punish the body: gust/snipe the soft 170 for 2 prizes before Tuck Tail bounces it.
- **Crushing Hammer ×4** — coin-flip energy strip on US (~2 hits/game); buys the Stage-2 setup time by taxing our attackers, not by stopping Dragapult. Keep energy redundant; attach late.

**Web-vs-engine conflicts surfaced:** none on card **stats** — every Dragapult/Fezandipiti/Latias/Meowth/Budew stat the web cited matches the engine. All divergence is **shell/list** (published lists run Dusknoir/Munkidori/Charizard/Iono; this base build does not) and **out-of-format counter cards** (principles kept, cards excluded). The Dusknoir variant (in `covers`) would add **damage-counter manipulation** amplifying the spread — flagged in §7, not enumerable from the base list.

**Sources:**
- Three decks to beat Dragapult ex — Stéphane Ivanoff — https://alexschemanske.substack.com/p/three-decks-to-beat-dragapult-ex
- Dragapult: Phantom Diving to Victory — Going Second (Spenser Gow) — https://goingsecond.substack.com/p/dragapult-phantom-diving-to-victory
- Dragapult ex Counters? — Pokémon Forums — https://community.pokemon.com/en-us/discussion/14286/dragapult-ex-counters
- Dragapult ex deck guide — PokeBeach — https://www.pokebeach.com/?p=319761
- Enter the Dragapult: the new format and its top decks — PokeBeach — https://www.pokebeach.com/2026/05/enter-the-dragapult-the-new-format-and-its-top-decks
- How To Play A Dragapult Ex Deck — TheGamer — https://www.thegamer.com/pokemon-tcg-dragapult-ex-2025-post-rotation-deck-strategy-guide/
- Fezandipiti ex (SFA 38) / Latias ex (SSP 76) / Meowth ex (POR 62) / Budew — Limitless TCG + Pokémon.com
- engine ground truth — `data/EN_Card_Data.csv` + `dump_deck.py` + `docs/rules.md` (Tera bench-immunity Appendix 6, weakness ×2, damage order)

## 3 · Exploitable seams (the weakness map)  *(PROPOSED — pending Phase-3 lock)*

### S1 · Slow Stage-2 climb through fragile pre-evos (no accel but Crispin)
- **Weakness:** no attack before ~turn 2, no energy acceleration beyond a single Crispin/turn, and the whole clock lives in **Dreepy (70 HP, 1 prize)** and **Drakloak (90 HP, 1 prize)** before they become the wall.
- **Exploit:** race the evolution clock. KO/snipe/gust a Dreepy or Drakloak **before** it becomes Dragapult ex — every dead pre-evo delays or denies a Phantom Dive turn. Early prize pressure punishes the slow setup. (Thick 4-4-3 → clear multiples, not one.)
- **Maps to:** `target: Dreepy` `fragile_preevo`, `target: Drakloak` `fragile_preevo`; `opp_tempo` = `midrange`.

### S2 · The spread hits the BENCH only — flat 60, never the Active
- **Weakness:** Phantom Dive's 6 counters go on our **Bench**; the payoff exists only if we present soft Bench bodies to pre-soften into free follow-up KOs (incl. via Cruel Arrow). It never touches the Active.
- **Exploit:** keep the **Bench thin and high-HP**; don't park multiple fragile 60–90 HP support Basics for it to convert into two-prize turns. Committing/bursting bench pieces in one turn raises HP thresholds above lethal counter math.
- **Maps to:** **NEW key `opp_spreads_bench` = true** (§7 D1, registered `consumer: "unwired"`) + `threat: Dragapult ex` why.

### S3 · Tera locks the wincon body out of our reach on the Bench  *(VERIFIED engine rule)*
- **Weakness/for-us-constraint:** Dragapult ex is **Tera** → a benched copy **takes no attack damage** (Appendix 6, engine-enforced). We **cannot** snipe/spread a benched backup Dragapult; it's only answerable while Active, where it's a 320/no-weakness wall.
- **Exploit:** therefore the denial plan is **kill the pre-evos before they Tera up** (S1), not "snipe the benched wincon." Dragapult ex is a **threat, not a snipe/prize target** — do not spend removal trying to reach it on the Bench.
- **Maps to:** shapes targeting — Dragapult ex stays in `threats`, is **excluded** from `targets`; reinforces S1's `fragile_preevo` priority.

### S4 · A 320 no-weakness wall — but only 2 prizes, and the attack is a flat 200
- **Weakness:** the Active Dragapult can't be OHKO'd by most lines, but it's only a **2-prize** ex, and Phantom Dive is a **flat 200 with no innate boost** in this list.
- **Exploit:** don't **chip** the tank — chip is wasted. Push key bodies **out of the 200 OHKO band** (any ≳210 effective HP survives Phantom Dive's Active hit), forcing multi-turn math. And when you *can* reach 320 (multi-hit / boost / after your own chip), a clean **2-prize** KO on Dragapult is an **even trade, not a loss**.
- **Maps to:** `threat: Dragapult ex` why (objective posture: out-HP the flat 200; even-trade the tank when reachable).

### S5 · Low energy count + Crispin-only accel → energy denial bites
- **Weakness:** only **8 basic energy** (4 R / 4 P) in 60, and Phantom Dive needs **exactly one Fire + one Psychic** attached; the only accel is Crispin (1 Supporter/turn).
- **Exploit:** stripping or moving a single Fire **or** Psychic off the attacker shuts off **Phantom Dive specifically** (Jet Headbutt {C} and the ex attacks don't need Fire) — a real tempo tax for decks that carry energy denial/removal.
- **Maps to:** `threat`/summary note (objective; no property — energy-denial is our-kit-relative).

### S6 · Four 2-prize ex bodies — three are NON-Tera and gustable
- **Weakness:** Fezandipiti ex (210, **Fighting** weak), Latias ex (210, **Darkness** weak), Meowth ex (170) all sit on the Bench as **2-prize** ex with **no Tera protection** — gustable and KO-able. Their weaknesses are auto-derived by the Dossier.
- **Exploit:** **gust a benched support ex and KO it for 2 prizes** while removing its job — Fezandipiti's recovery+finisher, Latias's pivot, Meowth's toolbox body. A 2-for-1 prize swing the deck can't insure (only Dragapult is Tera-protected).
- **Maps to:** `target: Fezandipiti ex` `prize_liability`, `target: Latias ex` `prize_liability`, `target: Meowth ex` `prize_liability`.

### S7 · Budew item-lock is a one-turn tax on a 30-HP body
- **Weakness:** Itchy Pollen locks our **Items** for one turn — real vs item-heavy engines (Ball / Candy / Poffin) — but Budew is **30 HP / 1 prize / Fire weak / retreat 0**, and locking costs *them* a develop turn.
- **Exploit:** **sequence our Items before the lock lands**, lean on Supporters/Abilities the locked turn, then OHKO the 30-HP Budew to deny repeat locks.
- **Maps to:** **NEW key `opp_item_locks` = true** (§7 D2, registered `consumer: "unwired"`) + `threat: Budew` why (disruption to respect + the 30-HP snipe play-around).

### S8 · Recovery is reactive — and consistency is distributed, not choke-pointed
- **Weakness:** Fezandipiti's Flip-the-Script draw-3 only fires **after** they take a KO; and setup is spread across a redundant trainer engine + banked-on-entry Meowth + Drakloak dig — **no single Pokémon whose removal strangles the deck**.
- **Exploit:** close prizes fast to **starve the reactive draw-3**; don't over-invest resources hunting a single "engine" body — there isn't a strangleable one (the leverage is the pre-evo clock in S1, not an engine kill).
- **Maps to:** `opp_is_engine_dependent` = **false** (see §7 D3 — deliberately NOT set); summary note.

## 4 · Threats & targets (objective card-level intel)  *(PROPOSED)*

- **Threats** (attackers/disruption to respect):
  - `Dragapult ex` — the wincon. Phantom Dive flat 200 Active + 60 Bench spread every turn, taking prizes on two axes; 320 HP, NO weakness, **Tera (benched copies untouchable)**, 2 prizes. Out-HP the flat 200; even-trade it only when reachable; deny it at the pre-evo stage.
  - `Fezandipiti ex` — recovery + finisher: Flip the Script (draw 3 after a KO) refuels; Cruel Arrow (CCC, 100 free-aim, ignores Bench W/R) converts spread into prizes (situational at 3 energy). Also a `prize_liability` target.
  - `Latias ex` — Eon Blade (PPC, 200) one-off OHKO window (self-locks after); Skyliner grants their Basics free retreat. Respect the single Eon Blade turn; don't leave a ≤200-HP body Active into it. Also a `prize_liability` target.
  - `Budew` — Itchy Pollen locks our Items for a turn (30 HP, Fire weak, retreat 0). Play around the lock; OHKO to stop repeats.
- **Targets** (disrupt / snipe), by role:
  - `fragile_preevo`: `Dreepy` — 70 HP / 1 prize base of the line; KO before it evolves (clear multiples vs 4-4-3). Not Tera — valid target.
  - `fragile_preevo`: `Drakloak` — 90 HP / 1 prize Stage 1; also the Recon Directive dig engine + rebuild hop. Snipe/gust to strip consistency and delay the wall. Not Tera.
  - `prize_liability`: `Fezandipiti ex` — 210 HP / 2 prizes / Fighting weak; gust+KO banks 2 prizes and deletes recovery+finisher. Not Tera.
  - `prize_liability`: `Latias ex` — 210 HP / 2 prizes / Darkness weak; gust+KO banks 2 prizes and strips pivot mobility. Not Tera.
  - `prize_liability`: `Meowth ex` — 170 HP / 2 prizes / Fighting weak; toolbox value is banked on entry, so punish the soft body (gust/snipe for 2) before Tuck Tail bounces it. Not Tera.
  - *(No `engine`-role target: consistency is distributed + banked; Drakloak's engine-ness is folded into its `fragile_preevo` why. See §7 D3.)*

## 5 · Objective counterplay summary  *(DRAFT)*

Beat Dragapult ex by **racing the prize count at the roots it can't protect — not by out-grinding the wall.** The Active Dragapult is a 320/no-weakness Tera body you usually can't OHKO and *can't even touch on the Bench*, so don't spend chip on it; it's only a 2-prize ex, an even trade when you *can* reach 320. Instead: (1) **race the fragile pre-evos** — KO Dreepy (70) / Drakloak (90) before they become the wall, clearing multiples to beat the 4-4-3; (2) **gust the non-Tera support ex** (Fezandipiti / Latias / Meowth) for clean 2-prize swings that also strip recovery, pivot, and toolbox; (3) **starve the spread** by keeping our Bench thin and high-HP (it never hits the Active, and a >200-HP Active dodges the flat 200); (4) **tax the low energy** with denial/removal (one Fire *or* Psychic off the attacker shuts off Phantom Dive), and **sequence Items before Budew's lock**, then delete the 30-HP Budew. Close fast to starve Fezandipiti's reactive draw-3.

## 6 · Brief preview (pre-JSON — filled in Phase 4, emitted in Phase 6)  *(PROPOSED)*

```
opponent_properties = {
  "opp_tempo": "midrange",             # registered, consumer unwired
  "opp_spreads_bench": true,           # NEW key (D1) — registered, consumer unwired (forward contract)
  "opp_item_locks": true               # NEW key (D2) — registered, consumer unwired (forward contract)
  # opp_is_engine_dependent: NOT set (false) — distributed/banked consistency, no strangle point (§7 D3)
}
threats = [
  { "card": "Dragapult ex",  "why": "..." },
  { "card": "Fezandipiti ex","why": "..." },
  { "card": "Latias ex",     "why": "..." },
  { "card": "Budew",         "why": "..." }
]
targets = [
  { "card": "Dreepy",        "role": "fragile_preevo",  "why": "..." },
  { "card": "Drakloak",      "role": "fragile_preevo",  "why": "..." },
  { "card": "Fezandipiti ex","role": "prize_liability", "why": "..." },
  { "card": "Latias ex",     "role": "prize_liability", "why": "..." },
  { "card": "Meowth ex",     "role": "prize_liability", "why": "..." }
]
```

## 7 · Open questions / deferred

- **D1 · Mint `opp_spreads_bench` (bool)? — RESOLVED: MINTED.** Phantom Dive's signature is a Bench-only spread the deck converts into two-prize turns; no registered key captured "this deck punishes a wide/fragile Bench → keep Bench thin + high-HP." Objective and cross-deck. Added to `src/common/scouting/opponent_properties.json` with `consumer: "unwired"`. **Forward contract — needs a consumer to wire it onto a `Board` field before it affects play** (separate, unbuilt item).
- **D2 · Item-lock key for Budew? — RESOLVED: MINTED.** User elected to make the item-lock read machine-readable. `opp_item_locks` added to `src/common/scouting/opponent_properties.json` with `consumer: "unwired"` (forward contract — a future consumer sequences our Items before the lock / avoids item-dependent lines the locked turn). Budew is *also* carried as a `threat` (the 30-HP snipe play-around).
- **D3 · `opp_is_engine_dependent` — RESOLVED: NOT set (false).** HIGH-BAR wired key (~4% wrong-assertion cost). Consistency here is distributed across a redundant trainer engine + banked-on-entry Meowth + Drakloak dig; there is **no single Pokémon whose removal strangles setup**. Deliberately NOT set.
- **Variant gap (Dusknoir / N’s Zoroark ex):** `covers` routes those variants here, but this export is the **base build**. Threats/targets ground only in base-list cards (validator hard-fails others). The Dusknoir variant adds **damage-counter manipulation** amplifying the spread — noted in the summary, not enumerable as card intel. Expected: no validator warn (covers copied verbatim; no cross-Brief collision).
- **Weakness types** (Fezandipiti/Meowth Fighting, Latias Darkness, Budew Fire; Dragapult/Dreepy/Drakloak none) are **auto-derived by the Dossier** — no `opp_weakness_*` key minted.
