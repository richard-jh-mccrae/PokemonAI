<!-- Strategy Proposal queue — matchup-brief proposal from the Kyogre / Mega Abomasnow ex counterplay doctrine.
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md
Producer: matchup-genie (ADR-0046). update-strategy authors src/common/scouting/briefs/kyogre_mega_abomasnow_ex.json,
runs validate_brief.py, presents the diff; the human commits (commit msg begins "matchup: "). -->

## matchup-brief-kyogre_mega_abomasnow_ex
- id: matchup-kyogre_mega_abomasnow_ex
- source: matchup-genie
- target_layer: matchup-brief
- for: opponent:Kyogre / Mega Abomasnow ex
- candidate_signal: `fragile_preevo` target → brief_preevo lever (WIRED, default ON) — the one behavioral output; `opp_tempo` (registered, unwired); `opp_no_pivot` + `opp_deckout_vulnerable` (NEW keys minted in src/common/scouting/opponent_properties.json, consumer:"unwired" — inert forward contracts)
- verification_contract: brief-validator
- provenance: docs/matchups/kyogre_mega_abomasnow_ex.md (locked + signed off 2026-07-09; grill forks in §7)
- status: applied

**Spec (authoring spec — the locked Brief content; author the JSON from this, don't re-litigate):**

**slug / label / covers** — from `data/meta/decks/index.json` (copy `covers` VERBATIM; it routes all variants to this one Brief):
- slug: `kyogre_mega_abomasnow_ex`
- label: `Kyogre / Mega Abomasnow ex`
- covers: `["Jynx / Kyogre / Mega Abomasnow ex", "Kyogre / Mega Abomasnow ex", "Mega Abomasnow ex"]`

**tempo:** `slow` (needs Snover-in-play → evolve → WW; Kyogre does 0 on an empty discard; real prize pressure lands turn 3+).

**summary (objective, deck-neutral):** Slow, purely reactive Water tank/burst deck. Single-hop evolves Snover (Basic, 90 HP, Metal-weak) into Mega Abomasnow ex (Mega ex, 350 HP, **3 prizes**, Metal-weak, retreat 4) and tanks behind it. Damage is Hammer-lanche (WW, 0 base): self-mills top 6 of its own deck for 100 per Basic Water Energy discarded — 35/60 Water → ~350 avg, 0–600 range, high variance, and it mills its own irreplaceable Pokémon/engine with **no recovery** (Kyogre recycles ONLY Basic Water Energy). Frost Barrier (WWW, 200 + takes −30 one turn) is the sustained-wall mode. Kyogre (150 HP, 1 prize, Lightning-weak) is a 0-cost recycling finisher (Riptide = 20 × Water-in-discard, then shuffle back to refuel the mill). Engine is thin and entirely Supporter/Item (Lillie's Determination ×4 = only draw; Mega Signal ×4 + Cyrano ×2 tutor the Mega; Waitress ×4 accel). **No gust, no switch, no hand-disruption anywhere.** Beat it by racing the opening and **sniping Snover before it evolves** (1-prize cost denies a 3-prize Mega); once the Mega is up, focus-fire it — Metal-weak (175 KOs) and chip *sticks* (no heal). Meta win-rate ~37–39% (a losing deck).

**opponent_properties:**
- `opp_tempo: "slow"` — registered key; consumer currently unwired (accurate forward contract).
- `opp_no_pivot: true` — **NEW key, minted in the registry (consumer:"unwired")**. No gust/switch/pivot in all 60 + retreat Snover 3 / Kyogre 3 / Abomasnow 4 → a body forced Active is stranded for turns. ⚠️ NEEDS CONSUMER WIRING (a future trap/gust-value lever) before it affects play; inert until then.
- `opp_deckout_vulnerable: true` — **NEW key, minted in the registry (consumer:"unwired")**. Hammer-lanche self-mills 6/turn with no Pokémon/Trainer recovery → long games drift toward deck-out / attacker drought. ⚠️ NEEDS CONSUMER WIRING (a future grind-vs-race lever); inert until then.
- **DELIBERATELY NOT asserted** (user-confirmed in grill — do not add):
  - `opp_is_engine_dependent` — the engine is all Supporters/Items, so there is **no gustable engine Pokémon** for the wired brief_engine lever to act on; a wrong assertion is priced ~4% (registry HIGH-BAR note). Engine dependence is real doctrine but has no lever here.
  - `opp_is_heal_wall` — 350 HP is raw bulk + a one-turn −30, **not** healing/stacked reduction; chip is NOT undone (contrast archaludon). Chip lines are fine here.

**threats** (attackers/effects to respect — card + why):
- `Mega Abomasnow ex` — sole attacker + 350-HP wall; Hammer-lanche ~350 avg / 600 ceiling for WW, or Frost Barrier 200 + −30. Slow (turn 3+), Metal-weak, 3-prize KO.
- `Kyogre` — 0-cost Riptide, 20 × Basic Water in discard (300+ once stocked), then recycles it to refuel the next mill. Dead early (empty discard); 1-prize, Lightning-weak.
- `Maximum Belt` — ACE SPEC Tool (1 copy), +50 vs the opponent's **Active ex only** (before W/R) → flips 2HKO→OHKO on our ex Actives (Frost Barrier→250, Hammer-lanche higher). Seat a non-ex Active to deny it. (A Tool, not an attacker — kept as a threat for visibility per the grill; fold into the Mega's why if the applier prefers threats = attackers only.)

**targets** (disrupt/snipe — card + role + why):
- `Snover` — role `fragile_preevo` — **the load-bearing WIRED target** (brief_preevo lever, default ON). 90-HP Basic, single-hop sole line to the wincon, must survive a turn to evolve. Snipe pre-evolution (Metal OHKOs); deny the 3-prize Mega for a 1-prize trade. Deck cannot switch it away.
- `Mega Abomasnow ex` — role `prize_liability` — 3-prize Mega-ex, Metal-weak (175 KOs), retreat 4; once Active/trapped it cannot reposition. Chip sticks (no heal) → focus-fire.

**sources** (for the Brief's `sources[]`):
- Flipside Gaming — Searching Standard: Mega Abomasnow ex — https://flipsidegaming.com/blogs/pokemon-blog/searching-standard-mega-abomasnow-ex
- Deltia's Gaming — Best Mega Abomasnow ex Deck Guide — https://deltiasgaming.com/pokemon-tcg-best-mega-abomasnow-ex-deck-guide-mega-evolution/
- Limitless — Mega Abomasnow ex (MEG #36) — https://limitlesstcg.com/cards/MEG/36
- Limitless Play — Mega Abomasnow ex PFL Standard 2025 finishes (39.38%) — https://play.limitlesstcg.com/decks/mega-abomasnow-ex?format=standard&rotation=2025&set=PFL
- pokemoncard.io — Mega Abomasnow Kyogre deck — https://pokemoncard.io/deck/mega-abomasnow-kyogre-deck-136757
- Bulbapedia — Maximum Belt (TEF 154) — https://bulbapedia.bulbagarden.net/wiki/Maximum_Belt_(Temporal_Forces_154)
- engine ground truth — data/EN_Card_Data.csv via dump_deck.py (Scarlet & Violet Mega era + simulator deltas)

**Applier notes:**
- Run `python .claude/skills/matchup-genie/scripts/validate_brief.py kyogre_mega_abomasnow_ex` after authoring — every threat/target card (Mega Abomasnow ex, Kyogre, Maximum Belt, Snover) is in the deck; roles legal; `covers` must match index.json; the two new opponent_properties keys are now registered.
- Web-vs-engine conflicts already resolved (engine wins): (1) web build ≠ this build (29 energy + recovery tech it does NOT run); (2) Snover is 90 HP / **Metal** / single-hop (NOT the web/Pocket 70 HP / Fire / multi-hop); (3) Maximum Belt is Active-ex-only. Author from the engine facts above.
