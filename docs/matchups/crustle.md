# vs Crustle — Counterplay Doctrine

> Phase-A deliverable of `/matchup-genie`. The **objective** game-plan against ONE opponent archetype;
> the machine `src/common/scouting/briefs/crustle.json` Brief is generated from this **after sign-off**
> (ADR-0027). Shared across all our decks — write deck-neutral; each agent relativizes it.

**Slug:** `crustle` · **Status:** `locked — proposal emitted` · **Last grilled:** 2026-07-09 · **Author:** matchup-genie + Richard
**Covers** (from `data/meta/decks/index.json`): `Crustle`, `Crustle / Drednaw / Sylveon`, `Crustle / Sylveon` — every variant routes to this one Brief.

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped (`dump_deck.py --deck-dir data/meta/decks/crustle`) + `covers` read from index.json
- [x] Phase 1 how-it-wins confirmed (user ✓)
- [x] Phase 2 counterplay research synthesised (89-agent sweep, 55/66 claims verified, confidence high) + variant engine facts pulled
- [x] Phase 3 weakness grill: 7/7 seams locked
- [x] Phase 4 Brief-field reconciliation complete — 2 new keys minted (`opp_ex_damage_immune`, `opp_caps_big_hits`), pierce-override verified at source
- [x] Phase 5 ship-it (user "continue") → Phase B proposal emitted: `data/strategy/proposals/matchup-20260709-crustle.md`

Decisions resolved (user ✓): mint BOTH keys; each encodes the **pierce override** (an effect-ignoring attack negates the immunity/cap). Next: `/update-strategy` authors `briefs/crustle.json` + runs `validate_brief.py`; human commits (`matchup: …`).

## 1 · How it wins

- **Win condition:** Attrition, not a race. Grind six 1-prize KOs behind a single, near-unkillable attacker. Crustle is immune to *all* damage from our ex/Mega-ex attacks (Mysterious Rock Inn; Mega-ex count as ex — rulebook L337), stacks HP (+20 per Grow Grass, +100 Hero's Cape) and out-heals chip (Cook 70, Jumbo Ice Cream 80), while chipping us 120/turn with Superb Scissors. Every body is 1 prize; it wins the war of attrition against the ex-heavy field. **Its whole edge is environment-specific — worthless against non-ex damage.**
- **Line(s):** Dwebble (Basic, 70 HP) → Crustle (Stage 1, 150 HP) — a single hop. Active Dwebble self-evolves via **Ascension** (fetch Crustle from deck, 0 dmg); benched Dwebbles evolve from hand. · **online at:** turn 2–3.
- **Main attacker(s):** **Crustle** — Superb Scissors (GCC, 120); damage "isn't affected by any effects on your opponent's Active Pokémon" (pierces our Active-effect defenses). The **only** attacker in the base deck.
- **Engine (draw/search):** No consistency *Pokémon* — trainer-based: Lillie's Determination (shuffle → draw 6/8), Waitress (dig top-6 + attach a Basic Energy), Buddy-Buddy Poffin (fetch 2 Dwebble), Cook + Jumbo (heal). · **Acceleration:** Waitress; **31 energy** = never energy-starved. · **Disruption:** passive only — Rock Inn zeroes our ex attackers, Spiky Energy puts 2 counters on our attacker when it damages Crustle, Mist Energy makes Crustle immune to attack *effects*. **No gust / hand disruption.**
- **Tempo:** **Slow / grind.** No burst, no speed pressure.
- **User context:** win-con read confirmed; asked to research variants (done — see §2).

## 2 · Counterplay research (cited)

**How it wins (web, matches engine):** an established meta wall (Destined Rivals era; Regional Top-8s, NAIC 2026 representation — not fringe). Hides behind one Crustle, HP-stacks + heals, grinds 120/turn. **Its edge is purely environmental: it does nothing to a non-ex attacker.**

**How it is beaten (verified):**
- **Non-ex attackers** are THE counter. Rock Inn only prevents damage from opponent Pokémon **ex** — a single-prize/non-ex body hits the 150 HP normally. Never feed ex attackers in (0 damage, wasted turns).
- **Fire weakness ×2.** Crustle *and* Dwebble are Fire-weak; weakness math is untouched by Rock Inn or Superb Scissors' effect-ignore. A **non-ex Fire** attacker is the cleanest KO route (~75 base → 150 vs a bare Crustle). Caveat: a caped/Grow-Grass body reaches ~250–270, so plan a 2-shot when buffed, not a guaranteed OHKO.
- **Snipe the pre-evo.** The line passes through a 70 HP Dwebble that has none of Crustle's immunity — the one window *any* attacker (ex included) can damage the line. Gust/snipe Dwebble T1–3 before Poffin/Ascension stack copies. Redundant (4 + tutor + Poffin) so pair snipe with fast prizing, not one removal.
- **Non-attack damage bypasses the wall.** Rock Inn prevents *attack* damage from ex; it is NOT effect immunity. **Special conditions (poison/burn)** and **damage-counter placement** (spread — "put damage counters", not "damage from an attack") land on Crustle (unless it carries Mist Energy). Engine confirms the damage-vs-counter distinction (rules.md L128).
- **Ability-lock** turns off Rock Inn — then even ex damage lands on the 150 HP body (a real paper-meta answer: Mega Lopunny ex "Spiky Hopper"). Objective seam; whether we hold such a tool is each agent's business.
- **Single-turn KO beats the heal.** A 120+ swing clears Cook (70) / Jumbo (80); chipping just gets healed back. Out-tempo — they have no burst to catch up, no gust, no hand disruption, so we set up unmolested and dictate pace.

**Key-card findings:**
- **Crustle** (DRI 12): sole attacker + wall. Immune to all ex damage; ~250–270 effective HP with heals; Superb Scissors 120 pierces our Active-effect defenses. Never grind it with ex damage.
- **Dwebble**: sole Basic, 70 HP, no immunity — the fragile window. Ascension self-fetches Crustle so the line goes online even without drawing Crustle.
- **Sylveon** *(variant)*: coherent printing is **PRE #330** — non-ex, 120 HP, 1 prize, **Safeguard = same ex-immunity as Crustle**, but **Metal**-weak (patches Crustle's Fire hole); chips 100 with Magical Shot. (If the SSP #86 **Sylveon ex** printing is used instead: 270 HP, **2-prize** liability, Angelite bench-shuffle — a different body.)
- **Drednaw** *(variant, SCR 44)*: secondary wall. **Impervious Shell = prevent any single hit ≥200** (walls big burst, even non-ex), **Lightning**-weak (not Fire). Slow 80/160 Hard Crunch — never the wincon, but it inverts "just OHKO it."

**Web-vs-engine conflicts:** none substantive. (Some guides call the ability "Mysterious Stone House" — same effect. Web conflates Sylveon printings — resolved via engine to PRE #330 / SSP #86.)

**Sources:** Limitless — https://limitlesstcg.com/decks/341 · Limitless card — https://limitlesstcg.com/cards/DRI/12 · JP City League lists — https://limitlesstcg.com/cards/DRI/12/decklists/jp · PokéBeach "Vacancy at the Mysterious Rock Inn" — https://www.pokebeach.com/2026/03/vacancy-at-the-mysterious-rock-inn-crustle-surprises-in-seattle · Deltia's Crustle guide — https://deltiasgaming.com/pokemon-tcg-best-crustle-deck-guide-destined-rivals/ · Cardsrealm "Anti-Meta Crustle (Praga RU)" — https://pokemon.cardsrealm.com/en-gb/articles/pokemon-tcg-standard-deck-tech-anti-meta-crustle-praga-regional-runner-up · Drednaw SCR 44 — https://www.pokemon.com/us/pokemon-tcg/pokemon-cards/series/sv07/44 · Sylveon ex SSP 86 — https://limitlesstcg.com/cards/ssp/86

## 3 · Exploitable seams (the weakness map)

### Seam 1 — Rock Inn is dead text vs non-ex attackers (the master seam) — AND vs effect-ignoring attacks
- **Weakness:** Mysterious Rock Inn (and Sylveon's Safeguard) prevent damage only from opponent Pokémon **ex**. Two classes of attacker bypass it: (a) any **non-ex** body (damage fully unblocked); (b) **an effect-ignoring attack** — the "this attack's damage isn't affected by any effects on your opponent's Active Pokémon" clause treats the prevention as an effect on the Active and ignores it, so even an **ex** attacker lands full damage.
- **Exploit:** Attack the wall with a non-ex body, OR with an `ignoresEffects` attack. Never commit a *plain* ex attacker head-on — it does literally nothing.
- **Verified at source (engine + oracle):** `compute_active_damage` ([damage.py:110](../../src/common/strategy/damage.py)) — `if not attack.ignoresEffects and _prevented(...): return 0`. Confirmed end-to-end: **Nebula Beam → 210** into a Rock-Inn Crustle (id 345, `preventsDamageFrom='ex'`) and into Sylveon Safeguard; **Jetting Blow (plain ex) → 0**. The `ignoresEffects` pierce set: **Nebula Beam** (Mega Starmie ex, 210, also ignores W/R), **Spiky Hopper** (Mega Lopunny ex, 160 — the paper-meta counter), **Demolish** (Cornerstone Ogerpon ex, 140), **Twin Shotels** (Iron Crown ex, 50×2), **Destructive Drill** (Dudunsparce ex, 150), **Shred** (Koraidon, 130), **Sonic Edge** (Veluza, 110), **Surprise Pump** (Tatsugiri ex, 100). The Pilot already scores these correctly — no code change needed.
- **Maps to:** `opp_ex_damage_immune = true` **(new key — minted)**, whose consumer contract ANDs the immunity with "no `ignoresEffects` attack payable this turn." Also drives `target: Dwebble fragile_preevo` for pure-ex decks with no non-ex / no-pierce answer.

### Seam 2 — Fire weakness ×2 (the clean KO route)
- **Weakness:** Crustle and Dwebble are Fire-weak; weakness is untouched by Rock Inn / Superb Scissors' effect-ignore.
- **Exploit:** A non-ex **Fire** attacker doubles and is the fastest KO. Plan a 2-shot once the body is caped/Grow-Grass'd (~250–270).
- **Maps to:** auto-Dossier already carries weakness type (CardStat). No property needed — counter-line note. (Drednaw/Sylveon variants are NOT Fire-weak — see Seam 6.)

### Seam 3 — Fragile pre-evo is the only universal window
- **Weakness:** The line passes through a 70 HP Dwebble (Chewtle 80 / Eevee in variants) with no immunity — the one target *any* attacker can hit.
- **Exploit:** Snipe/gust the Basic T1–3 before Poffin/Ascension stack copies. Redundant (4 + tutor + Poffin) → pair with fast prizing, not one removal.
- **Maps to:** `target: Dwebble` role `fragile_preevo`. (Variant Basics can't be Brief targets — not in the base export; §7.)

### Seam 4 — Damage immunity ≠ effect immunity (non-attack damage bypasses it)
- **Weakness:** Rock Inn prevents *attack* damage from ex only. Special conditions (poison/burn) and damage-counter *placement* (spread) are not "damage from an attack" and land — unless Crustle carries Mist Energy.
- **Exploit:** Apply poison/burn or spread counters to erode the wall through its heals; these route around both the ex-immunity and the effect-ignore.
- **Maps to:** counter-line note (no registered key; deck-relative capability). Verify counter-spread-through-Rock-Inn by replay before making it load-bearing (§7).

### Seam 5 — The wall is ability-dependent
- **Weakness:** Turn off Mysterious Rock Inn and even ex damage lands on the 150 HP body.
- **Exploit:** Ability-ignoring attacks (e.g. paper-meta Mega Lopunny ex "Spiky Hopper") neutralise the immunity.
- **Maps to:** counter-line note. Deck-relative; not a property.

### Seam 6 — Burst-cap inversion (Drednaw variant) — same pierce override
- **Weakness:** Drednaw's Impervious Shell prevents any single hit **≥200** — so the OHKO burst you'd use to punch through the heal-wall is *fully wasted* on Drednaw (and it's Lightning-weak, not Fire).
- **Exploit:** Vs the Drednaw variant, land the KO in the **140–199** window (multi-hit / sub-200 repeatable), never overkill — **unless** you have an `ignoresEffects` attack, which pierces the cap (Nebula Beam's 210 lands). The universal answer (non-ex + pre-evo snipe) still holds.
- **Verified at source:** `compute_active_damage` ([damage.py:118-126](../../src/common/strategy/damage.py)) gates `preventsDamageAtLeast` behind `not attack.ignoresEffects`. Confirmed: **Sonic Ripper 220 (plain ex) → 0** into Drednaw (id 158, `preventsDamageAtLeast=200`); **Nebula Beam 210 → 210** (pierces cap).
- **Maps to:** `opp_caps_big_hits = true` **(new key — minted)**, consumer contract mirrors Seam 1's pierce override.

### Seam 7 — Slow, gust-less, disruption-less grind
- **Weakness:** No gust, no hand disruption, flat 120 with no scaling, needs six full KOs.
- **Exploit:** Set up unmolested; clear our board damage in ONE turn (120+ beats the heal); race the prize trade — they can't catch up.
- **Maps to:** `tempo = slow` (Brief top-level field). `opp_is_heal_wall = true` captures the chip-is-wasted half; `opp_pierces_active_effects = true` captures Superb Scissors piercing our Active defenses.

## 4 · Threats & targets (objective card-level intel)

Constrained to the base export (deck.csv = Dwebble + Crustle); the validator hard-fails any card not in it.

- **Threats** (attackers to respect):
  - **Crustle** — sole attacker + wall in one body; immune to all ex-attack damage, ~250–270 effective HP with heals, and Superb Scissors' 120 pierces damage-reduction/protection on our Active. Respect it, but never grind it with ex damage.
- **Targets** (disrupt/snipe), by role:
  - `fragile_preevo`: **Dwebble** — the sole Basic, 70 HP, no immunity; the only window any attacker can hit the line. Snipe before it evolves; redundant, so pair with fast prizing.
- **Variant threats/targets (documented, NOT Brief-eligible — absent from base export):** Sylveon PRE #330 (2nd ex-immune wall, Metal-weak) / Sylveon ex SSP #86 (2-prize, Angelite) · Drednaw SCR 44 (≥200 cap, Lightning-weak) · Chewtle 80 HP + Eevee — variant `fragile_preevo`s (snipe the Basic).

## 5 · Objective counterplay summary

Beat Crustle by **attacking with a non-ex body — Rock Inn is dead text against it** — ideally a **non-ex Fire** attacker (weakness ×2, cleanest KO; plan a 2-shot once buffed), and by **single-turn KOs that clear the heal** (120+ beats Cook/Jumbo; chipping loses). A **pure-ex deck cannot damage an active Crustle at all**: its only path is to **snipe the fragile Dwebble before it evolves**, race prizes on the bench, and lean on **non-attack damage** (poison/burn, spread) or **ability-lock**, which route around the immunity. The deck has no gust and no disruption, so we set up freely and dictate the race. Watch the variants: Sylveon adds a Metal-weak ex-immune wall (Fire won't double it), and Drednaw walls any single 200+ hit (stay in the 140–199 window) — but the non-ex + snipe-the-Basic answer holds against all three.

## 6 · Brief preview (pre-JSON — filled in Phase 4, emitted in Phase 6)

```
tempo = "slow"

opponent_properties = {
  "opp_ex_damage_immune":       true, # NEW KEY (minted, unwired). Rock Inn + Sylveon Safeguard: ex/Mega-ex deal 0 — BUT an ignoresEffects attack (Nebula Beam class) pierces it. Override already modeled in compute_active_damage.
  "opp_caps_big_hits":          true, # NEW KEY (minted, unwired). Drednaw variant: any single hit ≥200 prevented — same ignoresEffects pierce override.
  "opp_is_heal_wall":           true, # registered. Cook 70 + Jumbo 80 + HP stacking — chip is out-healed.
  "opp_pierces_active_effects": true, # registered. Superb Scissors ignores effects on our Active.
  "opp_single_prize":           true  # registered. All base-deck bodies 1-prize (see §7 Sylveon-ex caveat).
}

threats = [ { "card": "Crustle", "why": "sole attacker + wall; immune to all ex damage (unless pierced by an ignoresEffects attack), ~250-270 eff. HP with heals, Superb Scissors 120 pierces our Active-effect defenses" } ]

targets = [ { "card": "Dwebble", "role": "fragile_preevo", "why": "sole Basic, 70 HP, no immunity — the only window any attacker can hit the line; snipe before it evolves (redundant, pair with fast prizing)" } ]
```

## 7 · Open questions / deferred

- **Sylveon printing — RESOLVED at card level (meta.db).** The `Crustle / (Drednaw /) Sylveon` sides run **Sylveon id 330 (non-ex, Safeguard, 1 prize)** — never Sylveon ex SSP#86 (id 316). Confirmed by the per-episode `deck` card-ids (330 ×3 in a real Crustle/Drednaw/Sylveon list) and a global scan (only "Sylveon", 11 sides; never "Sylveon ex"). `opp_single_prize = true` **holds.**
- **Variants are RARE tech.** Across the 874 covered sides: Dwebble+Crustle in **100%**; Sylveon in only **9** sides, Drednaw/Chewtle in **6**, Munkidori **29** (~3%), plus <1% ex splashes (Koraidon ex, Cornerstone Ogerpon ex, Fezandipiti ex). So the **mono-Crustle export is the representative build**; the Sylveon/Drednaw variants (in `covers`) are a ~1% tail — the reason they stay out of the Brief's card-level threats/targets (validator + rarity) costs almost nothing.
- **Meta caveat — QUANTIFIED (meta.db).** Of **1222** Crustle-main sides, the crustle Brief covers **874 (72%)** — the mono/wall builds. The other **348 (28%)** are PARTNER builds routed to different archetype labels, led by **Crustle / Ethan's Typhlosion (167 — a non-ex Fire attacker doing the killing), Crustle / Mega Kangaskhan ex (83), Crustle / Great Tusk (27), Centiskorch / Crustle (12)**. These play differently (the partner is the real attacker, so the "one attacker = Crustle 120" read does NOT apply) and are correctly NOT this Brief's scope. **Open scope decision:** whether to author a separate Brief for partnered Crustle (esp. Typhlosion at ~13% of Crustle games) — see report to user.
- **Counter-spread through Rock Inn.** Strong inference that damage-counter *placement* (not "damage from an attack") bypasses Rock Inn even from an ex (engine distinguishes damage vs counters — rules.md L128). Verify by replay before making it load-bearing.
- **New keys minted (need consumer wiring):** `opp_ex_damage_immune` + `opp_caps_big_hits` — both consumer `unwired` forward contracts. **The pierce OVERRIDE they encode is already correctly resolved at concrete-attack scoring** by `compute_active_damage` (ADR-0032; `ignoresEffects` skips both `_prevented` and `preventsDamageAtLeast`) — so the Pilot never suicides a pierce attack into the wall today. The unwired half is the higher-level Read/Posture *routing* (recognise the wall → route a non-ex/pierce attacker or deny-the-line); the consumer MUST AND each property with "no `ignoresEffects` attack payable this turn." Registered in `src/common/scouting/opponent_properties.json`.
