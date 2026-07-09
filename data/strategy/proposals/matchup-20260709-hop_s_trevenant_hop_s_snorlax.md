<!-- Strategy Proposal queue — matchup-brief proposal from /matchup-genie.
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md
Producer STOPS here (ADR-0046): /update-strategy authors src/common/scouting/briefs/hop_s_trevenant_hop_s_snorlax.json,
runs validate_brief.py, presents the diff, human commits (commit msg begins `matchup: `). -->

## matchup-brief · Hop's Trevenant / Hop's Snorlax counterplay
- id: matchup-hop_s_trevenant_hop_s_snorlax
- source: matchup-genie
- target_layer: matchup-brief
- candidate_signal: opponent_properties Board fields (reuse `opp_single_prize`, `opp_tempo`; two NEW registered keys `opp_special_energy_fragile` + `opp_effect_immune_bodies`, both consumer:"unwired" = forward contracts) + Dossier `threats`/`targets` role fields
- verification_contract: brief-validator
- provenance: docs/matchups/hop_s_trevenant_hop_s_snorlax.md (locked doctrine, signed off 2026-07-09)
- status: open
- for: opponent:Hop's Trevenant / Hop's Snorlax

**Spec (authoring spec — the locked Brief-field content; `/update-strategy` authors the JSON, not this skill):**

Author `src/common/scouting/briefs/hop_s_trevenant_hop_s_snorlax.json` from the locked doctrine. All card
facts are engine-verified (dump + `docs/rules.md`); the web was a strategy prior only.

- **slug:** `hop_s_trevenant_hop_s_snorlax` (must match filename)
- **label:** copy verbatim from `data/meta/decks/index.json[hop_s_trevenant_hop_s_snorlax].label`
- **covers:** **copy VERBATIM from `index.json` — do NOT retype.** The four strings mix straight (`'`) and
  curly (`’`, U+2019) apostrophes; a hand-typed value will fail the routing match. They are:
  `Hop's Trevenant`, `Hop's Trevenant / Hop’s Cramorant`, `Hop's Trevenant / Hop’s Cramorant / Hop’s Snorlax`,
  `Hop's Trevenant / Hop’s Snorlax`. (validate_brief warns on any divergence from index.json.)
- **authored:** 2026-07-09
- **tempo:** `midrange` — Stage-1 wincon (Phantump→Trevenant) needs tool+stadium+benched-Snorlax assembly;
  a real window before the boost stack is online, but not a slow deck (redundant draw + Night Stretcher recursion).
- **summary** (one line, objective): All-single-prize Hop's aggro-control / revenge-trap deck. Stacks three
  pre-Weakness +30 boosts (Snorlax's Extra Helpings aura from the bench + Hop's Choice Band + Postwick) on a
  Stage-1 Trevenant: Corner (PCC, 90→180) traps your Active with a no-retreat lock; Horrifying Revenge (C,
  30→~130→~220, free with Choice Band) punishes every return-KO — the plan is to make YOU trade badly. Beat
  it by racing the fragile setup and OHKOing THROUGH Weakness (Darkness ×2 on the 140 Trevenant / Fighting
  ×2 on the 150 Snorlax aura — cuts through the +90 buffer AND ignores Mist), denying the Revenge trigger
  (control trade timing; never over-commit to a straight KO race), overwriting Postwick, and starving the
  all-special energy base. Don't waste effect-riders on Mist-holders and don't sink removal into
  self-shuffling Dudunsparce.

- **opponent_properties** (every key registered in `assets/opponent_properties.json`):
  - `opp_single_prize`: `true` — reuse. No ex/Mega; race even trades, no 2-for-1 gust swing to farm (line
    recurs via Night Stretcher ×3; expect one Legacy-Energy [ACE SPEC] prize-denial on its holder's KO).
  - `opp_tempo`: `"midrange"` — reuse.
  - `opp_special_energy_fragile`: `true` — **NEW KEY, minted + registered this session, consumer:"unwired"**.
    9/9 energy are special (4 Mist + 4 Telepath + 1 Legacy) with NO special-energy discard-recovery (Night
    Stretcher recovers only Pokémon/Basic energy; Colress's Tenacity is deck-only). **Flag in the diff as an
    inert forward contract** — nothing reads it until a consumer is wired.
  - `opp_effect_immune_bodies`: `true` — **NEW KEY, minted + registered this session, consumer:"unwired"**.
    Mist Energy makes its holder immune to our attack EFFECTS (damage/abilities/spread still land). **Flag in
    the diff as an inert forward contract.**

- **threats** (attackers/abilities to respect — each `{card, why}`):
  - `Hop's Trevenant` — Wincon. Corner (PCC, 90→180 boosted) no-retreat traps the Active; Horrifying Revenge
    (C, 30 → ~130 if a Hop's body was KO'd by an attack last turn → ~220 boosted, **free with Choice Band**)
    punishes return-KOs. Cheap 1-prize Stage 1. Darkness ×2, resists Fighting −30.
  - `Hop's Snorlax` — Extra Helpings **+30 aura** (always-on **from the bench**) is the damage floor lifting
    Corner/Revenge over our HP thresholds; also a 150-HP wall + Dynamic Press burst (140, self-80). Remove it
    by **KO (Fighting ×2) or ability-lock — a gust does NOT disable the aura** (it works from the bench).
  - `Boss's Orders` — the deck's only reach to our bench; gusts a fragile piece Active to KO around a wall or
    reposition. Don't leave a snipeable key piece benched assuming it's safe.

- **targets** (disrupt/snipe — each `{card, role, why}`; roles ∈ fragile_preevo/prize_liability/engine):
  - `Hop's Phantump` — role `fragile_preevo` — 70 HP, 1 prize, Darkness ×2; base of the ONLY wincon line.
    Snipe/gust in the evolution window to deny a Trevenant prize-free. **This is the sole target row** (arms
    the live `brief_preevo` lever at the high-value wincon pre-evo).
  - **Anti-targets (grilled — do NOT add as target rows):** `Dudunsparce`/`Dunsparce` (redundant,
    self-recurring draw line — Run Away Draw refunds any KO/gust; ability-lock is the only clean off-switch);
    `Hop's Snorlax` (threat, not a target — aura works from the bench, deck-relative to remove).
  - `prize_liability`: none — no ex / Mega-ex.

- **sources** (`name — url`): Hop's Trevenant 1st-Place list (Special Event Turin) —
  https://limitlesstcg.com/decks/list/27927 · Standard Deck Tech (Cardsrealm) —
  https://pokemon.cardsrealm.com/en-us/articles/pokemon-tcg-standard-deck-tech-hops-trevenant-special-event ·
  Deck Guide (Deltia's Gaming) — https://deltiasgaming.com/pokemon-tcg-hops-trevenant-deck-guide-ascended-heroes/ ·
  matchup/win-rate data — https://play.limitlesstcg.com/decks/hops-trevenant · card refs (Mist Energy TEF 161,
  Postwick JTG 154, Dudunsparce TEF 129) — Bulbapedia · engine ground truth — data/EN_Card_Data.csv + docs/rules.md.

**Engine-truth overrides to preserve when authoring (web/research got these WRONG):**
1. **Mist Energy does NOT block damage/spread** — "damage is not an effect" (cardsrealm claim is false). Only
   rider effects fizzle. This underpins both `opp_effect_immune_bodies` and the raw-damage counterplay.
2. **Extra Helpings works from the bench** (rulebook L148: abilities work from Active AND Bench) — so a gust
   on Snorlax does NOT turn off the +30 aura; only KO/ability-lock removes it. This is why Snorlax is a
   threat, not an `engine` target.

**Applier checklist (`/update-strategy`):** author the JSON above → `python .claude/skills/matchup-genie/scripts/validate_brief.py hop_s_trevenant_hop_s_snorlax`
(expect: schema OK; covers non-empty & matching index.json; every threat/target card in the deck; legal
roles; both new keys resolve in the registry) → `python -m pytest tests/ -q` green (Brief is live data;
covers-collision freedom is pinned) → present diff, **flag the 2 new unwired keys** → human commits
(`matchup: Hop's Trevenant / Hop's Snorlax counterplay doctrine`).
