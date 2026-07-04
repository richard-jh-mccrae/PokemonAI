# vs Cinderace / Mega Starmie ex — Counterplay Doctrine

> Phase-A deliverable of `/matchup-genie`. The **objective** game-plan against ONE opponent archetype;
> the machine `src/common/scouting/briefs/cinderace_mega_starmie_ex.json` Brief is generated from this
> **after sign-off** (ADR-0027). Shared across all our decks — write deck-neutral; each agent relativizes it.

**Slug:** `cinderace_mega_starmie_ex` · **Status:** `shipped` · **Last grilled:** 2026-07-05 · **Author:** matchup-genie + Richard
**Covers** (from `data/meta/decks/index.json`): `Cinderace / Mega Froslass ex / Mega Starmie ex`, `Cinderace / Mega Starmie ex` — every variant routes to this one Brief.

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped (`dump_deck.py --deck-dir data/meta/decks/cinderace_mega_starmie_ex`) + `covers` read from index.json
- [x] Phase 1 how-it-wins confirmed (deck-neutral; posture for ALL our decks)
- [x] Phase 2 counterplay research synthesised + confirmed
- [x] Phase 3 weakness grill: 6/6 seams locked (Q1 donk=FALSE, Q2 mint key=YES)
- [x] Phase 4 Brief-field reconciliation complete (opponent_properties + threats + targets)
- [x] Phase 5 signed off → Phase B run: Brief emitted + validator green + registry key minted

All seams locked; both open questions resolved (see §7).

## 1 · How it wins

- **Win condition:** Fast Mega-ex beatdown — take 6 prizes with **Mega Starmie ex** (3 prizes each; only needs two KOs to close if it also nets a cheap prize). Prize math: Mega Starmie ex = **3**, Cinderace = **1**, Staryu = **1**. Deck runs only **3 Staryu / 3 Mega Starmie ex** — a thin payoff count.
- **Line(s):** `Staryu (Basic) → Mega Starmie ex (Mega Stage-1)`, a single hop. **Online turn 1–2** via **Salvatore** (rush-evolve a just-placed Staryu — legal because Mega Starmie ex has no Ability), **Mega Signal** (tutor the Mega), **Hilda** (Evolution + Energy), **Buddy-Buddy Poffin** (fill Staryu). One Energy powers an attack the same turn.
- **Main attacker(s):**
  - **Mega Starmie ex — Jetting Blow ({W}, 120 + 50 to a benched Pokémon).** The sustained workhorse: *one Water*, plus a 50 bench snipe (ignores Weakness/Resistance on the bench).
  - **Mega Starmie ex — Nebula Beam ({C}{C}{C}, 210, ignores Weakness/Resistance AND any effects on your Active).** Ignition-fueled burst that punches through damage-reduction/protection. **One Ignition = CCC on an Evolution**, but Ignition **discards end-of-turn** (only 4 in deck) → per-turn burst, not sustained.
- **Engine (draw/search):** Salvatore ×4, Mega Signal ×4, Pokégear ×4, Lillie's Determination ×4, Hilda ×2, Ultra Ball ×1, Night Stretcher ×2 — all **Trainers** (no Pokémon draw-engine). **Acceleration:** Cinderace **Turbo Flare** (search 3 basic Water to Bench) — *plus* Ignition self-powers Nebula. **Disruption (to US):** Crushing Hammer ×4 (coin-flip energy discard), Boss's Orders ×1 (gust), Harlequin ×2 (hand shuffle-disrupt).
- **Tempo:** **fast** — payoff online turn 1–2.
- **User context:** Brief must give **all** our decks (not just Lightning/Water) a posture vs this archetype; any agent may face it.

## 2 · Counterplay research (cited)

**Coverage caveat (load-bearing):** the web has *no* deck-specific coverage of THIS 60-card list. The
strategy prose that exists (Deltia's, Pokémon.com) describes real-TCG-meta Mega Starmie shells
(Munkidori / Froslass / Dusknoir damage-spread + Battle Cage / Flareon counters) whose tech cards are
**not in this simulator's pool** — excluded. Several card pages are **Pokémon TCG Pocket** (mobile): they
list Staryu at 50 HP and Lightning weakness as "+20". **Engine FACTS override** — Staryu is 70 HP, weakness
**×2**; the one-shot threshold is **70**, not 50. All counter-math below is derived from engine facts
(weakness math, prize economy, Ignition burst mechanics, single-hop fragility), **not** validated
tournament matchup data. No hard rules conflict surfaced (see §7).

**How it wins (web-confirmed shape):** one evolution hop to a 330-HP / 3-prize payoff online turn 1–2;
Cinderace front-loads Water so Jetting Blow (cheap, two-target) sustains a turn early; Nebula Beam is the
effect-ignoring burst; Wally's Compassion resets the race. Wins by out-tempoing — one evolution to
threaten KOs, and the heal-reset re-arms cheaply (Jetting = 1 Water) faster than a grinder can re-KO 330.

**Key-card findings** (its threats + engine — function + how we blunt it):
- **Mega Starmie ex:** the whole win condition. Jetting Blow ({W}, 120 + 50 bench) sustained; Nebula Beam
  ({C}{C}{C} = 1 Ignition, 210) ignores Weakness/Resistance **and effects on our Active** → effect-walls
  don't stop the burst; **raw HP, healing, Lightning-play, or removal do.** Gives **3 prizes**, Lightning ×2.
- **Cinderace:** the tempo enabler, not a payoff. Turbo Flare ({C}, 50) accelerates ≤3 Water to Bench.
  Soft body (160 HP, Water ×2, 1 prize). Only **one ever enters** (Explosiveness at setup; no Raboot line).
- **Staryu:** the sole foundation — 70 HP, 1 prize, Lightning ×2, only 3 in deck, **no replacement path**.
- **Ignition Energy:** CCC on an Evolution powers Nebula but **discards EOT**; only 4 exist → Nebula is a
  per-turn burst that can't be banked; denying one Nebula turn re-costs one of four Ignition.
- **Wally's Compassion:** only rewards **chip** — full-heals + returns all Energy to hand; leaves the Mega
  **Energy-empty (can't attack) that turn.** Prefer burst-lethal so there's nothing to heal.

**Web-vs-engine conflicts surfaced:** none on rules text. Divergences are all **card-pool / list**
(published lists run 1× Ignition + Munkidori/Dark spread + no Cinderace; this build runs 4× Ignition +
Cinderace Water-accel → *more* Nebula turns, energy-denial even weaker against it) and **Pocket stat
errors** (Staryu 50 HP / "+20") — engine facts used throughout.

**Sources:**
- Mega Starmie ex Deck Guide — Deltia's Gaming — https://deltiasgaming.com/pokemon-tcg-mega-starmie-ex-deck-guide-perfect-order/
- Best Cinderace Deck Guide (Mega Evolution) — Deltia's Gaming — https://deltiasgaming.com/pokemon-tcg-best-cinderace-deck-guide-mega-evolution/
- Build a Mega Starmie ex Deck — Pokémon.com — https://www.pokemon.com/us/strategy/build-a-mega-starmie-ex-deck-from-pokemon-tcg-mega-evolution-perfect-order
- Mega Starmie ex (POR 21) / Cinderace (MEG 28) / Wally's Compassion (MEG 132) / Ignition Energy (WHT 86) — Limitless TCG — https://limitlesstcg.com/cards/POR/21
- Mega Starmie deck overview — Limitless TCG — https://limitlesstcg.com/decks/362
- engine ground truth — `data/EN_Card_Data.csv` + `dump_deck.py` + `docs/rules.md`

## 3 · Exploitable seams (the weakness map)

### S1 · Lightning weakness ×2 on the payoff
- **Weakness:** Mega Starmie ex's 330 HP is its *only* defense — no passive reduction. Lightning ×2 halves the raw damage needed: **~165 raw = 330 OHKO**. (Staryu is Lightning ×2 too.)
- **Exploit:** any Lightning source drastically lowers the bar to a one-turn, 3-prize KO. Even non-Lightning decks note the 330-flat ceiling: a true OHKO number, not a wall.
- **Maps to:** `target: Mega Starmie ex` role `prize_liability` (why cites Lightning ×2). Weakness itself is auto-derived by the Dossier → **no property**.

### S2 · The whole payoff funnels through one fragile pre-evo
- **Weakness:** `Staryu → Mega Starmie ex` is a single hop, but Staryu is 70 HP / 1 prize / Lightning ×2, only **3 copies**, **no un-evolve or replacement path**. Kill a Staryu the turn it lands (before Salvatore/Mega Signal rush-evolve) → deny a full 3-prize Mega for a 1-prize trade; permanently taxes a 3-line deck.
- **Exploit:** snipe/gust a benched Staryu; 70 damage (or any Lightning ping) suffices. Bench-spread can clear multiple at once. Tiny KO window — pressure the turn it appears.
- **Maps to:** `target: Staryu` role `fragile_preevo`. **NOT** classic donk (see §7 Q1 — the opener is usually the 160-HP Cinderace, Staryu sits on Bench).

### S3 · Acceleration is irreplaceable but NOT load-bearing
- **Weakness:** exactly one Cinderace ever enters (Explosiveness at setup; no Raboot line). Once it fires Turbo Flare and retreats, there's no second accelerator. **But** Ignition self-powers Nebula (CCC on Evolution) and one Water self-powers Jetting Blow — so removing Cinderace only costs the opponent **a turn of tempo**, not the gameplan. This deck is **not accel-dependent** the way a ramp deck is.
- **Exploit:** don't over-invest in the 160-HP body (1 prize, likely already fired). Prefer to **deny the distributed Water** (energy strip) or race the benched Staryu / fresh Mega so front-loaded Energy sits on nothing. Gusting the retreated Cinderace back Active can strand their Active slot as a tempo tax.
- **Maps to:** `target: Cinderace` role `engine` (secondary). `opp_accel_dependent` = **false** (do NOT set — distinct from archaludon, whose Cinderace WAS the sole irreplaceable ramp).

### S4 · Nebula Beam is a per-turn burst — and it ignores your Active's effects
- **Weakness:** the effect-piercing 210 needs an **Ignition attached that turn**; Ignition **discards EOT**; only **4** exist and none can be banked. Denying one Nebula turn re-costs one of four. Meanwhile the sustained mode (Jetting Blow, 120) **is** stopped by damage-reduction — so the burst and the workhorse have opposite defensive profiles.
- **Exploit:** against the **burst**, effect-walls (damage-reduction, protection, "can't be damaged" on the Active) are **useless — Nebula ignores them**; only **raw HP (survive 210), healing, board removal, or Lightning-play** work. Present a 210-surviving body (or gust the intended target away) to force a wasted Ignition turn. Against sustained **Jetting**, your effect-walls *do* work.
- **Maps to:** **NEW** `opponent_properties.opp_pierces_active_effects` = true (see §7 Q2 — mint decision) + `threat: Mega Starmie ex` why.

### S5 · Wally's Compassion only rewards chip — and de-powers the attacker
- **Weakness:** the full-heal returns **all** Energy to hand → the Mega is Energy-empty and **cannot attack that turn**. It erases *non-lethal* damage only; a clean OHKO leaves nothing to heal.
- **Exploit:** prefer **burst-lethal over two-turn chip** — a one-turn 330 KO takes 3 prizes outright. When you can't one-shot, press the **post-Wally window** (naked Mega): gust elsewhere or develop a lethal follow-up. This deck is **not a heal-wall** (no passive reduction; the heal is a finite, tempo-costly reset), so grinding isn't *wasted* — it *forces* the reset.
- **Maps to:** `threat: Mega Starmie ex` / `target: Mega Starmie ex` why. `opp_is_heal_wall` = **false** (do NOT set).

### S6 · Single Supporter lane
- **Weakness:** one Supporter/turn must cover setup (Salvatore/Hilda/Lillie's), disruption (Boss's/Harlequin), AND reset (Wally's). Every reactive Wally's/Harlequin turn is a turn not developing.
- **Exploit:** race prizes hard on the 1-prize pieces (Staryu, Cinderace) so repeated heals buy **tempo but never prizes**; force the Supporter slot onto reactive survival turns.
- **Maps to:** `opp_tempo` = `fast` (the race clock) + §5 summary.

## 4 · Threats & targets (objective card-level intel)

- **Threats** (attackers to respect):
  - `Mega Starmie ex` — the whole win condition. Jetting Blow ({W}, 120 + 50 bench) = cheap sustained two-target chip; Nebula Beam ({C}{C}{C} via one Ignition, 210) = burst that ignores Weakness/Resistance **and effects on our Active**. Respect as both chipper and wall-piercer. Gives **3 prizes**, Lightning ×2.
  - `Cinderace` — the tempo threat (not a payoff): Turbo Flare ({C}, 50) accelerates ≤3 Water, bringing the Mega online a turn early. Soft body (160 HP, Water ×2, 1 prize). Respect the **accel**, not the attack.
- **Targets** (disrupt / snipe), by role:
  - `fragile_preevo`: `Staryu` — 70 HP / 1 prize / Lightning ×2, sole foundation for the 3-prize Mega, only 3 copies, no replacement. Snipe/gust the turn it lands, before rush-evolve. Highest-leverage early play.
  - `prize_liability`: `Mega Starmie ex` — 3 prizes, Lightning ×2 → trading into it is prize-positive. Answer with a Lightning OHKO or kill it pre-evolution. Do **not** rely on effect-walls vs Nebula.
  - `engine`: `Cinderace` — the one-and-only accelerator; KO yields 1 prize and it's usually already fired. Prefer denying the distributed Water / racing the Staryu over spending resources on the body.

## 5 · Objective counterplay summary

Beat this deck by **racing the prize count while denying the 3-prize payoff at its root.** It's fast but
brittle: the entire win condition rides on **three Staryu → three Mega Starmie ex** with no replacement,
so **snipe/gust a Staryu before it rush-evolves** (or exploit **Lightning ×2** to OHKO the 330 body) to
trade 1 prize for a denied 3. When the Mega is set up, **prefer a burst OHKO over chip** — anything
non-lethal gets erased by Wally's Compassion (which also de-powers the Mega for a turn, a window to
press). Crucially, **its Nebula Beam ignores your Active's defensive effects** — don't bank on
damage-reduction/protection; rely on raw HP, healing, board removal, or Lightning-play. Out-prize the
1-prize pieces so its finite heals buy tempo but never prizes.

## 6 · Brief preview (pre-JSON — filled in Phase 4, emitted in Phase 6)

```
opponent_properties = {
  "opp_tempo": "fast",
  "opp_pierces_active_effects": true    # NEW key — forward contract, consumer unwired (see §7 Q2)
}
threats = [
  { "card": "Mega Starmie ex", "why": "..." },
  { "card": "Cinderace",       "why": "..." }
]
targets = [
  { "card": "Staryu",          "role": "fragile_preevo",  "why": "..." },
  { "card": "Mega Starmie ex", "role": "prize_liability", "why": "..." },
  { "card": "Cinderace",       "role": "engine",          "why": "..." }
]
```

## 7 · Open questions / deferred

- **Q1 · `opp_donk_vulnerable` — RESOLVED FALSE.** The opener is normally the 160-HP Cinderace
  (Explosiveness places it Active), with Staryu on the Bench. That's a *fragile-pre-evo-snipe* seam
  (captured as `target: Staryu` `fragile_preevo`), **not** a classic single-Basic-opener donk. Setting
  `opp_donk_vulnerable` would over-claim early-aggression value the board doesn't support. → **not set.**
- **Q2 · `opp_pierces_active_effects` — RESOLVED: MINTED.** No registered key captured "its burst ignores
  effects on your Active." Objective, cross-deck posture (every wall/defensive-tool deck of ours must know
  effect-defenses are bypassed by the 210 burst — rely on raw HP/heal/removal/Lightning). Added to
  `assets/opponent_properties.json` with `consumer: "unwired"`. **Forward contract — needs a consumer to
  wire it onto a `Board` field before it affects play** (separate, unbuilt item).
- `opp_accel_dependent` = **false** and `opp_is_heal_wall` = **false** (S3, S5) — deliberately NOT set;
  distinct from `archaludon_ex_cinderace` which sets both.

**Deferred / low-confidence (from research §2):** web coverage is thin + partly off-target — no
deck-specific tournament data for THIS 60-card list; all counter-math is engine-fact-derived. If a future
Lightning meta-read wants a lever beyond the auto-Dossier weakness, revisit whether a `opp_weakness_*`
key adds value (currently the Dossier derives weakness, so none minted).
