<!-- Strategy Proposal queue — matchup-genie, Crustle counterplay doctrine (2026-07-09).
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md
Doctrine (signed off): docs/matchups/crustle.md. Deck export: data/meta/decks/crustle/ (mono-Crustle,
index.json rank 4, 11.75% play, 53.4% WR). Two NEW opponent_properties keys minted this round
(opp_ex_damage_immune, opp_caps_big_hits) — registered unwired in the matchup-genie registry. -->

## matchup-brief-crustle
- id: matchup-brief-crustle
- source: matchup-genie
- target_layer: matchup-brief
- candidate_signal: opponent_properties — `opp_ex_damage_immune` (NEW, minted unwired), `opp_caps_big_hits` (NEW, minted unwired), `opp_is_heal_wall`, `opp_pierces_active_effects`, `opp_single_prize` (all registered); threats/targets grounded in deck.csv (Crustle, Dwebble). The pierce OVERRIDE both new keys encode is ALREADY resolved at concrete-attack scoring by `compute_active_damage` (ADR-0032: `AttackStat.ignoresEffects` skips both `_prevented` and `preventsDamageAtLeast`) — no new runtime signal needed for scoring; the two keys are unwired Read/Posture routing forward contracts.
- verification_contract: brief-validator
- provenance: docs/matchups/crustle.md (locked doctrine) | data/meta/decks/crustle/deck.csv + index.json rank 4 (`covers` source) | src/common/scouting/opponent_properties.json (2 new keys) | engine verify: compute_active_damage @ src/common/strategy/damage.py:110,118-126 (Nebula Beam 210 vs Rock-Inn Crustle id 345 / Sylveon Safeguard id 330 / Drednaw cap id 158; Jetting Blow 0)
- status: applied
- for: opponent:Crustle

**Spec (authoring spec — the locked Brief-field content; update-strategy authors briefs/crustle.json, runs validate_brief.py, human commits):**

Author `src/common/scouting/briefs/crustle.json` from the locked doctrine. Objective, deck-neutral — no "our deck" reasoning; each agent relativizes.

- **slug:** `crustle` · **label:** `Crustle` · **tempo:** `slow`
- **covers** (verbatim from index.json — routes every variant here): `["Crustle", "Crustle / Drednaw / Sylveon", "Crustle / Sylveon"]`
- **summary:** Mono-Crustle attrition wall. One near-unkillable Crustle (Stage 1 Grass, 150 HP, 1 prize) whose Mysterious Rock Inn prevents ALL damage from your Pokémon **ex** (Mega-ex count — rulebook L337), so the ex-heavy meta can't touch it; it HP-stacks (Grow Grass +20, Hero's Cape +100 → ~250-270) and out-heals chip (Cook 70, Jumbo Ice Cream 80) while grinding a flat 120/turn with Superb Scissors (ignores effects on your Active). All bodies 1-prize; wins by attrition. **Its whole edge is environmental — worthless vs non-ex damage.** Beat it with a NON-ex attacker (Fire = ×2 weakness, cleanest KO; 2-shot once buffed) OR an effect-ignoring attack (see override); a pure-ex deck must snipe the 70 HP Dwebble before it evolves and race prizes on the bench, or route around the wall via non-attack damage (poison/burn, spread) / ability-lock. No gust, no hand disruption. Variants: Sylveon (2nd ex-immune wall, Metal-weak — Fire won't double it) and Drednaw (walls any single hit ≥200 — stay 140-199) — the non-ex + snipe-the-Basic answer holds against all three.

- **opponent_properties:**
  - `opp_ex_damage_immune: true` — **(NEW KEY, minted unwired.)** Rock Inn + Sylveon Safeguard: your ex/Mega-ex deal 0. **OVERRIDE (verified, already modeled):** an `ignoresEffects` attack ("this attack's damage isn't affected by any effects on your opponent's Active Pokémon") pierces the prevention — Nebula Beam / Spiky Hopper / Demolish / Twin Shotels / Destructive Drill / Shred / Sonic Edge / Surprise Pump. Consumer ANDs the immunity with "no `ignoresEffects` attack payable this turn" before treating the wall as un-attackable.
  - `opp_caps_big_hits: true` — **(NEW KEY, minted unwired.)** Drednaw variant: any single hit ≥200 prevented (Impervious Shell). Same `ignoresEffects` pierce override. Consumer: prefer sub-cap repeatable / multi-hit damage over a single overkill nuke unless the attack pierces effects.
  - `opp_is_heal_wall: true` — Cook 70 + Jumbo 80 + HP stacking; chip is out-healed, single-turn KOs stick.
  - `opp_pierces_active_effects: true` — Superb Scissors' 120 ignores damage-reduction/protection effects on your Active.
  - `opp_single_prize: true` — every base-deck body is 1-prize; no 2-for-1 gust swing. **Confirmed at card level (meta.db):** the Sylveon variant runs Sylveon id 330 (non-ex Safeguard), never Sylveon ex; all variant bodies (Sylveon/Drednaw/Chewtle/Eevee) are 1-prize. The covered archetypes are 100% mono-Crustle-line with <1% ex splashes — the single-prize-wall characterization holds.

- **threats:**
  - `Crustle` — sole attacker + wall; immune to all ex-attack damage (unless pierced by an `ignoresEffects` attack), ~250-270 effective HP with heals, and Superb Scissors' 120 pierces damage-reduction/protection on your Active. Respect it; never grind it with plain ex damage.

- **targets:**
  - `Dwebble` (role `fragile_preevo`) — the sole Basic, 70 HP, no immunity; the only window any attacker can hit the line (Fire OHKOs it, 70 HP ×2). Snipe/gust before it evolves; redundant (4 + Ascension tutor + Buddy Poffin) so pair with fast prizing, not one removal.
  - _(Variant Basics Chewtle/Eevee and the variant walls Sylveon/Drednaw are NOT in the base export — validator would hard-fail them, so they are NOT Brief targets. Their intel lives in the summary + opponent_properties; the fragile_preevo doctrine generalizes to "snipe the Basic.")_

- **sources:** Limitless (Crustle deck 341 / DRI 12 card / JP City-League lists) · PokéBeach "Vacancy at the Mysterious Rock Inn" · Deltia's Crustle guide · Cardsrealm "Anti-Meta Crustle (Praga RU)" · Drednaw SCR44 (pokemon.com) · Sylveon ex SSP86 (Limitless) · engine ground truth: data/EN_Card_Data.csv + docs/rules.md §5 + compute_active_damage (damage.py).

**Apply notes for update-strategy:**
- `covers` verbatim from index.json; the validator warns on drift, hard-fails an empty/collision covers or a threat/target card absent from `data/meta/decks/crustle/deck.csv` — Crustle + Dwebble are the only Pokémon in it, so the threats/targets above are the only card-level intel legal to encode.
- Both new keys are registered `unwired` in `src/common/scouting/opponent_properties.json`; validate_brief.py will accept them (registered) and NOT warn. Call out in the diff that they need consumer wiring — the pierce override is already correct at concrete-attack scoring (compute_active_damage), so no gameplay regression ships today; the unwired half is the higher-level Read routing.
- No code change required. Run `python .claude/skills/matchup-genie/scripts/validate_brief.py crustle` + `python -m pytest tests/ -q` before the human commits (message begins `matchup: `).
