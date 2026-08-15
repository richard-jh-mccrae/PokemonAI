# vs Kyogre / Mega Abomasnow ex — Counterplay Doctrine

> Phase-A deliverable of `/matchup-genie`. The **objective** game-plan against ONE opponent archetype;
> the machine `src/common/scouting/briefs/<slug>.json` Brief is generated from this **after sign-off**
> (ADR-0027). Shared across all our decks — write deck-neutral; each agent relativizes it.

**Slug:** `kyogre_mega_abomasnow_ex` · **Status:** `locked` (signed off 2026-07-09; proposal emitted → `data/strategy/proposals/matchup-kyogre_mega_abomasnow_ex.md`) · **Last grilled:** 2026-07-09 · **Author:** matchup-genie + Richard
**Covers** (from `data/meta/decks/index.json`): `Jynx / Kyogre / Mega Abomasnow ex`, `Kyogre / Mega Abomasnow ex`, `Mega Abomasnow ex` — every variant routes to this one Brief.
**Meta:** rank 6 · play-rate 6.8% · **win-rate 36.8%** (368 episodes) — a below-average deck; the doctrine leans on exploiting its slowness + variance.

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped (`dump_deck.py --deck-dir data/meta/decks/kyogre_mega_abomasnow_ex`) + `covers` read from index.json
- [x] Phase 1 how-it-wins confirmed (user: "continue")
- [x] Phase 2 counterplay research synthesised (45/49 claims verified, confidence high)
- [x] Phase 3 weakness grill: 8/8 seams locked
- [x] Phase 4 Brief-field reconciliation locked (opp_tempo=slow + minted opp_no_pivot + opp_deckout_vulnerable; 3 threats; 2 targets)
- [x] Phase 5 signed off ("ship it" 2026-07-09) → Phase B done: proposal emitted to `data/strategy/proposals/matchup-kyogre_mega_abomasnow_ex.md`

Forks resolved (grill 2026-07-09): opp_is_engine_dependent NOT asserted · minted BOTH new keys · Maximum Belt kept as a threat.
Next: `/update-strategy` authors `src/common/scouting/briefs/kyogre_mega_abomasnow_ex.json` + runs validate_brief.py; human commits (`matchup: `).

## 1 · How it wins (DRAFT — awaiting confirmation)

- **Win condition:** Tank behind a **350-HP Mega Abomasnow ex** and grind 6 prizes with high-variance burst. Prize math: Mega Abomasnow ex = **3 prizes**, Kyogre = 1, Snover = 1. The deck is stuffed with **35 Water Energy** specifically to fuel that burst.
- **Line(s):** Snover (Basic, 90 HP) → **Mega Abomasnow ex** (Mega ex, 350 HP) — a **single hop** (like Riolu→Mega Lucario ex; no intermediate). · Kyogre is a standalone Basic support/finisher. · **online at:** WW on Abomasnow (~turn 2–3 after evolving); Kyogre only comes online once the discard is stocked.
- **Main attacker(s):**
  - **Mega Abomasnow ex — Hammer-lanche (WW, 0 base):** discard top 6 of deck, **100 damage per Basic {W} Energy discarded**. With 35/60 energy density ≈ 3.5 energy in 6 → ~**350 avg**, range 0–600. Burst mode, high variance.
  - **Mega Abomasnow ex — Frost Barrier (WWW, 200):** flat 200 + takes **30 less** next turn. Sustained tanky mode.
  - **Kyogre — Riptide (0 cost):** 20 × Basic {W} Energy in **your discard**, then shuffle those back into deck. Free finisher that **scales off the pile Hammer-lanche fills** and **recycles energy back** to refuel the mill.
- **Engine (draw/search):** **Lillie's Determination** (×4, shuffle hand→draw 6, or 8 on turn 1) is the only real draw. **Mega Signal** (×4, tutor the Mega ex) + **Cyrano** (×2, search up to 3 ex) find Abomasnow. **Acceleration:** **Waitress** (×4, dig top 6, attach a basic energy found). **Disruption (to US):** none — no gust/switch/hand-attack in the list; the deck is purely reactive.
- **Tempo:** **slow-midrange.** Needs the evolution + WW; Kyogre does 0 on turn 1 (empty discard). Real prize pressure lands turn 3+.
- **User context:** _(none supplied)_

## 2 · Counterplay research (cited)

Parallel sweep (4 angles) + 6 per-card deep-dives + adversarial verify vs engine facts (45/49 claims survived). Confidence **high** — bleeding-edge set (thin web coverage) but the engine facts carry the doctrine.

- **How it wins (web-confirmed):** single-hop Snover→Mega Abomasnow ex tank; Hammer-lanche variance burst (0–600, needs ~60% Water density to reliably chunk); Kyogre recycles the milled energy back and finishes. Thin engine; no disruption; slow. All matches the engine dump.
- **How it's beaten (web-confirmed):** it's a **losing archetype** (Limitless PFL Standard 2025: 115W/174L/3T = **39.4%**; fringe JP City League placements only). Named soft spots: brick/variance hands, self-mill deck-out, **no disruption → vulnerable to setup denial**, retreat-locked bodies, trimmed/inconsistent search.

**Key-card findings:**
- **Mega Abomasnow ex:** sole attacker + 350-HP wall; Hammer-lanche ~350 avg (600 ceiling), Frost Barrier 200 flat + −30 one turn. Slow (turn 3+), Metal-weak, 3-prize KO, retreat 4 → focus-fire when Active.
- **Kyogre:** 0-cost Riptide scales off the discard the mill fills (300+ once stocked) and shuffles it back to refuel — a sustainable loop. But dead early (empty discard) and a 1-prize Lightning-weak Basic.
- **Snover:** 90-HP Basic, the ONLY line to the wincon, must survive a turn to evolve → snipe/KO before it evolves.
- **Waitress / Lillie's Determination:** the (thin) engine — both **Supporters**, so **not snipe/gust targets**; disrupt via hand-denial/out-tempo, not removal.
- **Maximum Belt:** ACE SPEC, +50 vs our **Active ex only**, before W/R → pushes Frost Barrier to 250 / Hammer-lanche higher, flipping 2HKO→OHKO on our ex Actives.

**Web-vs-engine conflicts surfaced (engine wins):**
1. Web build = ~29 Water + recovery tech (Super Rod / Energy Recycler / Exp. Share / Codebreaking floor-seeding). **This deck has NONE of it** (35 Water, only Maximum Belt as ACE SPEC) → cross-build claims don't transfer, and the deck-out seam is genuinely open here.
2. Web/Pocket Snover = 70 HP / **Fire** weakness / multi-hop. **Engine overrides:** 90 HP / **Metal** / single hop. Any Fire-weakness counterplay is WRONG.
3. One web summary says Maximum Belt boosts vs "all Pokémon ex"; **engine restricts to the opponent's *Active* ex only** — benched ex get nothing.

**Sources:** Flipside Gaming — searching-standard-mega-abomasnow-ex · Deltia's Gaming deck guide · Limitless MEG/36 (card) · Limitless Play PFL Standard 2025 (finishes) · pokemoncard.io Mega Abomasnow Kyogre deck · Bulbapedia Maximum Belt (TEF 154).

## 3 · Exploitable seams (the weakness map)

### Seam 1 — Line-wide Metal weakness (×2)
- **Weakness:** both Snover (90 HP) and Mega Abomasnow ex (350 HP) are weak to **Metal**, no resistance. Kyogre is separately weak to **Lightning**.
- **Exploit:** a Metal attacker halves the wall — 175 KOs the Mega for **3 prizes**; any Snover dies trivially. Weakness KOs faster than their drawing can restock.
- **Maps to:** structural (auto-Dossier reads weakness from CardStat); carried in the `primary_attacker` target `why`. No new key.

### Seam 2 — Mega Abomasnow ex is a 3-prize liability
- **Weakness:** the wall IS the deck and it's a **Mega-ex = 3 prizes** on KO.
- **Exploit:** one clean KO = half your prize requirement. Prioritise it over 1-prize bodies. Unlike a heal-wall, **chip sticks** (no healing in the list) — weakness/burst just closes faster; grinding it is fine, not wasted.
- **Maps to:** `target: Mega Abomasnow ex` role `primary_attacker`.

### Seam 3 — No gust / no switch / brutal retreat
- **Weakness:** zero gust, switch, or hand-disruption in all 60; retreat Snover 3 / Kyogre 3 / **Abomasnow 4**. Purely reactive.
- **Exploit:** if WE have gust/switch, drag an un-energized Water body Active — it's **stranded for multiple turns**, buying free setup + KO windows. They can't reposition or snipe our bench.
- **Maps to:** `opponent_properties.opp_no_pivot = true` — **NEW key minted** (registry, `consumer: "unwired"` — inert until a future trap/gust-value lever reads it).

### Seam 4 — Slow start (real pressure turn 3+)
- **Weakness:** needs Snover in play → evolve → WW; Kyogre does **0** on an empty discard.
- **Exploit:** race the opening. Prizes taken turns 1–2 force answers this reactive deck doesn't have.
- **Maps to:** `opponent_properties.opp_tempo = "slow"` (registered; consumer currently unwired — accurate forward contract).

### Seam 5 — Fragile Snover is the only path to the wincon
- **Weakness:** 90-HP Basic, single point of failure, must survive a turn to evolve (single hop, no intermediate).
- **Exploit:** snipe/KO Snover **before it evolves** — a 1-prize cost denies a whole 3-prize Mega. Deck can't switch it out of harm's way.
- **Maps to:** `target: Snover` role `fragile_preevo` — **the load-bearing, WIRED add** (brief_preevo lever, default ON).

### Seam 6 — Hammer-lanche self-mills with no recovery
- **Weakness:** every Hammer-lanche blind-discards 6 of its own deck; Kyogre recycles **only Basic Water Energy** — Pokémon/Trainers milled are gone (no Super Rod/Energy Recycler in THIS build).
- **Exploit:** grind long. Trading HP while it self-mills its irreplaceable line drifts it toward deck-out / attacker drought.
- **Maps to:** `opponent_properties.opp_deckout_vulnerable = true` — **NEW key minted** (registry, `consumer: "unwired"` — inert until a future grind-vs-race lever reads it).

### Seam 7 — Draw is a single point of failure
- **Weakness:** Lillie's Determination ×4 is the ONLY real draw; its 8-card mode is gated on **exactly 6 prizes** (i.e. dies the moment we take one).
- **Exploit:** any early prize drops their dig from 8→6 every subsequent turn; hand-disruption around a shuffle-draw is devastating.
- **Maps to:** doctrine. **NOT** an `engine` target (Lillie's is a Supporter — ungustable); `opp_is_engine_dependent` deliberately **not asserted** (see §6/§7 rationale).

### Seam 8 — High-variance damage, no floor-fixing
- **Weakness:** 0–600 range, no Codebreaking/top-deck seeding in this list → the floor stays random.
- **Exploit:** don't respect the ceiling as reliable; play to the ~350 average / low floor and punish whiff turns.
- **Maps to:** doctrine (informs how much of the Mega's damage to fear; no key).

## 4 · Threats & targets (objective card-level intel)

- **Threats** (respect):
  - **Mega Abomasnow ex** — sole attacker + 350-HP wall; ~350 avg (600 ceiling) Hammer-lanche for WW, or 200 + −30 Frost Barrier. Slow, Metal-weak, 3-prize KO.
  - **Kyogre** — 0-cost Riptide, 20 × Water-in-discard (300+ once stocked), then recycles it to refuel the mill. Dead early; 1-prize Lightning-weak.
  - **Maximum Belt** — ACE SPEC (Tool, not an attacker) that adds +50 vs our **Active ex only** → flips 2HKO→OHKO on our ex bodies. Play around by seating a non-ex Active. _(Flagged: a Tool as a `threat`; listed for visibility since it changes our survival math — fold into the Mega's `why` if we prefer threats = attackers only.)_
- **Targets:**
  - `fragile_preevo`: **Snover** — 90-HP sole line to the wincon; snipe pre-evolution (Metal OHKOs), deny the 3-prize Mega for a 1-prize trade. **WIRED (brief_preevo, default ON).**
  - `primary_attacker`: **Mega Abomasnow ex** — 3-prize Mega-ex, Metal-weak, retreat 4; once Active/trapped it can't reposition → focus-fire.

## 5 · Objective counterplay summary

Race and snipe a slow, reactive deck. It comes online turn 3+ and carries **no gust / switch / disruption** and a single fragile line (Snover → the 350-HP, 3-prize Mega Abomasnow ex). Take early prizes before the Mega lands, and prioritise **sniping Snover pre-evolution** — a 1-prize cost erases a 3-prize wincon. Once the Mega is up, **focus-fire it**: it's a 3-prize KO and **Metal-weak (×2)**, and unlike a heal-wall **chip sticks** (no healing), so weakness/burst just KO faster — don't be scared off by Frost Barrier's −30. Keep a **non-ex body in the Active seat** to deny Maximum Belt's +50. If you can trap/strand, an un-energized Water body (retreat 3/4, no switch) is stuck for turns. Don't fear the long game — Hammer-lanche self-mills its own irreplaceable line with no recovery.

## 6 · Brief preview (pre-JSON — Phase-4 reconciliation)

```
opponent_properties = {
  "opp_tempo": "slow",              # registered; consumer unwired — accurate forward contract
  "opp_no_pivot": true,             # NEW key minted — no gust/switch + retreat 3/3/4; consumer unwired
  "opp_deckout_vulnerable": true    # NEW key minted — self-mills, no recovery; consumer unwired
}
   # opp_is_engine_dependent DELIBERATELY OMITTED: the engine is all Supporters/Items (Lillie's/Mega
   #   Signal/Cyrano/Waitress) — there is NO gustable engine Pokemon for the wired brief_engine lever to
   #   act on, and a wrong assertion is priced ~4% (registry HIGH-BAR note). Engine dependence is real
   #   DOCTRINE (§ seams 6-7) but has no wired lever here.
   # opp_is_heal_wall = FALSE: 350 HP is raw bulk + a one-turn -30, NOT healing/stacked reduction — chip
   #   is NOT undone (contrast archaludon). Do NOT assert.

threats = [
  { "card": "Mega Abomasnow ex", "why": "sole attacker + 350 HP wall; Hammer-lanche ~350 avg / 600 ceiling for WW, Frost Barrier 200 + -30. Slow (turn 3+), Metal-weak, 3-prize KO." },
  { "card": "Kyogre",            "why": "0-cost Riptide, 20 x Water-in-discard (300+ once stocked), then recycles it to refuel the mill. Dead early; 1-prize, Lightning-weak." },
  { "card": "Maximum Belt",      "why": "ACE SPEC +50 vs our ACTIVE ex only (before W/R) -> flips 2HKO->OHKO on our ex; seat a non-ex Active to deny it." }
]

targets = [
  { "card": "Snover",            "role": "fragile_preevo",  "why": "90 HP sole line to the wincon; single hop, must survive a turn to evolve. Snipe pre-evolution (Metal OHKOs); deny the 3-prize Mega for a 1-prize trade. Deck cannot switch it away." },
  { "card": "Mega Abomasnow ex", "role": "primary_attacker", "why": "3-prize Mega-ex, Metal-weak (175 KOs), retreat 4; once Active/trapped it cannot reposition. Chip sticks (no heal) -> focus-fire." }
]
```

## 7 · Open questions / deferred (resolved in grill 2026-07-09)

- **`opp_is_engine_dependent` — NOT asserted** (user-confirmed). No gustable engine Pokémon (engine = Supporters/Items); wired lever has no valid target; wrong-assertion priced ~4%. Real as doctrine (seams 6–7), no lever.
- **Two NEW keys minted + asserted** (user chose "mint both"), both `consumer: "unwired"` — inert forward contracts until a consumer is built:
  - `opp_no_pivot = true` (seam 3): no gust/switch + retreat 3/3/4 → a trapped Active is stranded. **Needs consumer wiring** (a future trap/gust-value lever).
  - `opp_deckout_vulnerable = true` (seam 6): self-mills its own irreplaceable line, no recovery → long-game deck-out. **Needs consumer wiring** (a future grind-vs-race lever).
- **Maximum Belt kept as a `threat`** (user-confirmed) — a Tool, not an attacker, listed for visibility (it changes our ex-Active survival math and drives the "seat a non-ex Active" line).
- **`Jynx / Kyogre / Mega Abomasnow ex` variant** in `covers` — no Jynx in this export; the Brief is objective/shared, so a tech Pokémon may exist we haven't dumped. `covers` copied verbatim regardless (routes all variants here).
