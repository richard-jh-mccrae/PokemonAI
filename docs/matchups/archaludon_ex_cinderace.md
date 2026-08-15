# vs Archaludon ex / Cinderace — Counterplay Doctrine

> Phase-A deliverable of `/matchup-genie`. The **objective** game-plan against ONE opponent archetype;
> the machine `src/common/scouting/briefs/archaludon_ex_cinderace.json` Brief is generated from this
> **after sign-off** (ADR-0027). Shared across all our decks — write deck-neutral; each agent relativizes it.

**Slug:** `archaludon_ex_cinderace` · **Status:** `locked → shipping` · **Last grilled:** 2026-07-04 · **Author:** matchup-genie + Richard
**Covers** (from `data/meta/decks/index.json`): `Archaludon ex / Cinderace` — every variant routes to this one Brief.
**Meta note:** rank 9 by play-rate (3.47%) but **62.4% win-rate — the highest in the tracked top 10** (188 episodes). A strong, underplayed grindy wall deck.

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped (`dump_deck.py --deck-dir data/meta/decks/archaludon_ex_cinderace`) + `covers` read from index.json
- [x] Phase 1 how-it-wins confirmed (user: "Confirmed, research it")
- [x] Phase 2 counterplay research synthesised (engine-grounded + web sweep folded in: 13 sources, high confidence, 0 conflicts)
- [x] Phase 3 weakness grill: `7/7` seams locked
- [x] Phase 4 Brief-field reconciliation complete (3 opponent_properties incl. 2 new keys, 3 threats, 4 targets)
- [x] Phase 5 signed off → Phase B authorised (user: "Lock it, ship the Brief")

All seams locked. New keys minted: `opp_is_heal_wall`, `opp_accel_dependent` (both consumer: unwired).

## 1 · How it wins

- **Win condition:** Assemble an effectively-unkillable **Archaludon ex** wall (300 HP) and grind out prizes with **Metal Defender** (220) while the opponent can't punch back. Prize math: Archaludon ex = **2 prizes** each; Cinderace / Duraludon / Relicanth = **1 prize** each. It's a **tank-and-grind** deck, not a race — it wins by attrition, not speed.
- **Line(s):**
  - **Attacker:** `Duraludon` (Basic) → `Archaludon ex` (Stage 1). Comes **online turn 2–3** once it has MMM (3 Metal). Assemble Alloy (on evolve) attaches **up to 2 Basic {M} from discard** to your Metal Pokémon, so the evolve turn itself ramps energy.
  - **Opener / accel:** `Cinderace` (Stage 2 Fire) enters play **only via its Explosiveness ability** — "if in your hand when setting up to play, put it face-down in the Active Spot." **There is no Raboot/Scorbunny line in the deck**, so Cinderace can only come down at initial setup. Retreat 0. Turbo Flare (C, 50) searches **up to 3 Basic Energy → attach to Bench** (all their energy is Metal), so Cinderace is the deck's turn-1 **Metal accelerator** onto the benched Duraludon, plus a cheap 50 attacker.
- **Main attacker(s):** `Archaludon ex` (Metal Defender 220, and self-negates its own Fire Weakness on the opponent's next turn). Secondary: `Duraludon` Raging Hammer (80 + 10 per damage counter on itself — scales as it gets hit) and `Cinderace` Turbo Flare (50).
- **Engine (draw/search):** **All-Trainer draw** — Explorer's Guidance (dig 6→2), Lillie's Determination (shuffle-hand → draw 6, or 8 at exactly 6 prizes), Pokégear 3.0 (dig 7 for a Supporter), Poké Pad (search a non-Rule-Box Pokémon), Ultra Ball (tutor Pokémon, discard 2 — also *fuels* Assemble Alloy by discarding Metal), Night Stretcher ×3 (recycle Pokémon/Basic energy from discard). **No draw-engine Pokémon** (no Dudunsparce/Bibarel) — draw is trainer-based and hard to strangle by KO.
- **Acceleration:** Cinderace **Turbo Flare** (deck → bench) + Archaludon ex **Assemble Alloy** (discard → Metal Pokémon on evolve). 11 Metal in deck; Night Stretcher + Ultra Ball keep the discard stocked for Assemble Alloy.
- **The tank stack (why the wall doesn't die):** `Archaludon ex` 300 HP **+ Full Metal Lab** (Metal Pokémon take **−30** from opponent attacks) **+ Hero's Cape** [ACE SPEC] (**+100 HP** → 400 effective) **+ Jumbo Ice Cream** (heal 80 from a 3+-energy Active). Stacked, the wall shrugs off most single attacks and heals back up.
- **Disruption (what it does to US):** **Boss's Orders ×4** — gusts our benched piece (an accelerator, a fragile pre-evo, a low-HP support) into the Active to KO it and dictate the prize race. That's the deck's main proactive disruption.
- **Tempo:** **Slow.** Wall online ~turn 2–3; the deck wins the long game by out-tanking and cannot race, so there's a real **early window (turns 1–2)** before Archaludon ex is assembled and armored.
- **User context:** User calls it "the most dominant archetype" and wants a plan to stomp it. (Data: highest win-rate in the tracked top 10.)

## 2 · Counterplay research (cited)

Synthesis (engine-grounded; adversarial verification against the FACTS). A web counterplay sweep for the
real-meta Archaludon ex archetype ran in parallel — its verified priors + citations are folded on lock;
where web coverage was thin (these are bleeding-edge SSP/MEG/PFL cards + simulator deltas), the doctrine
rests on **verified engine facts**, not the web (per CLAUDE.md: web = strategy prior only, never mechanics).

**How it's beaten (objective):** this is a *slow heal-wall*, not a clock. It cannot race. Two levers do
the work: **(a) win the early tempo window** (turns 1–2, before Archaludon ex is evolved + armored), and
**(b) burst the wall through its Fire weakness in a Metal-Defender-OFF window** — because chip damage is
worthless against Full Metal Lab (−30) + Jumbo Ice Cream (heal 80) + the ability to pivot.

**The Fire math (verified — docs/rules.md §5 damage order: base → ×Weakness → −Resistance → defender
"takes-less"):**
- Bare **Archaludon ex** (300 HP) under Full Metal Lab: a Fire attack of base `X` KOs when `2X − 30 ≥ 300`
  → **X ≥ 165**. A non-Fire attack needs `X ≥ 330` — effectively impossible. **Fire ×2 is the only
  realistic single-hit out.**
- **Hero's-Caped** Archaludon (400 HP): Fire needs **X ≥ 215**. But there is only **one** Hero's Cape
  (ACE SPEC, 1/deck) — only one body wears it; direct Fire at the un-Caped Archaludons.
- **Metal Defender's "no Weakness" shields ONLY the single Archaludon that attacked with it last turn**,
  and only for one opponent turn. A **benched / idle / freshly-evolved** Archaludon has **live ×2**. → the
  clean line is **gust an idle Archaludon Active and Fire it**, or strike in the pre-MMM setup window.

**Key-card findings (function + how we blunt it):**
- **Archaludon ex** — the wall + payoff (Metal Defender 220, self-negates own Fire weakness next turn).
  Blunt: Fire ×2 in an off-window; gust an idle copy up; don't chip (it heals + feeds Raging Hammer).
- **Cinderace** — sole Metal accelerator (Turbo Flare → 3 energy to bench) and **can only enter at setup**
  (no Raboot line). Blunt: KO it early (160 HP, Water ×2, 1 prize) — it can't be re-established; or exploit
  games where it whiffs the opening hand.
- **Duraludon** — the wall's fragile pre-evo (130 HP Basic, Fire ×2). Blunt: KO it *Active* (weakness ×2:
  a Fire ~80 base OHKOs) or gust it up before it evolves. Note: sniping it *benched* is inefficient (bench
  ignores weakness **and** Full Metal Lab still applies its −30 → need ~160 raw).
- **Relicanth (Memory Dive)** — lets Archaludon ex borrow **Raging Hammer** (80 + 10 per damage counter on
  itself). Consequence: **the more you chip Archaludon and leave it, the harder it hits back** — reinforces
  burst-or-bust; don't leave a damaged Archaludon alive.
- **Full Metal Lab** — the −30 damage floor on the whole Metal line. Contesting it with our own Stadium
  removes the −30 for a turn — but they run **4 copies**, so the stadium war favors them; treat it as a
  one-turn tempo buy, not a fix.

**Web-vs-engine conflicts surfaced:** none. The parallel web sweep (13 sources, 16/25 claims survived
adversarial verification, **confidence high**) independently confirmed every load-bearing engine fact —
300 HP / Metal Defender 220 / Assemble Alloy / Fire ×2 / Full Metal Lab −30-after-W&R / Cinderace
Explosiveness + Turbo Flare "up to 3". Two guard notes from the sweep: (1) several web-cited counters
(Iono handlock, Lost Vacuum tool/stadium removal, Scoop Up) are **standard-format tech that may not exist
in this simulator's pool** — so those levers are *conditional on our own deck having equivalents* (a
deck-relativization concern, not an objective deck fact); (2) many web decklists are **different
Archaludon variants** (Dialga VSTAR, Pecharunt poison-spread, Maximum Belt) — none of their facts were
used; this Cinderace list's engine facts are authoritative.

**Sources** (web strategy priors; engine facts — `data/EN_Card_Data.csv`, `docs/rules.md` §5 — are primary):
- Archaludon ex Strategy: Testing Your Metal — <https://www.pokemon.com/us/strategy/archaludon-ex-strategy-testing-your-metal>
- Archaludon ex — No Weakness Tank Build — <https://pokemoncard.io/deck/archaludon-ex-no-weakness-tank-build-108722>
- Full Metal Lab (Temporal Forces 148) — <https://bulbapedia.bulbagarden.net/wiki/Full_Metal_Lab_(Temporal_Forces_148)>
- Cinderace (MEG 28) — <https://limitlesstcg.com/cards/MEG/28> · Relicanth (TEF 84) — <https://limitlesstcg.com/cards/TEF/84>
- Archaludon ex Deck Guide — <https://www.tcgplayer.com/content/article/Archaludon-ex-Deck-Guide-Pok%C3%A9mon-TCG/be24d826-991c-4d42-aad9-b2d5f6c7cfb2/>

## 3 · Exploitable seams (the weakness map)

### Seam 1 — Fire weakness + the Metal-Defender-OFF window (the headline)
- **Weakness:** the whole Metal line is Fire ×2. Metal Defender suppresses Archaludon ex's weakness, but
  **only on the one copy that just attacked with it, for one turn**. Idle/benched/just-evolved Archaludons,
  and every Duraludon, have live ×2.
- **Exploit:** attack Archaludon ex with a **Fire attacker in an off-window** (pre-MMM, or after gusting an
  idle copy Active). Fire ×2 collapses 300 HP to a ~165-base one-shot (through Full Metal Lab). This is the
  only realistic path through the tank stack.
- **Maps to:** `threat: Archaludon ex` (weakness-suppression window) + `target: Archaludon ex` role
  `primary_attacker` (hit it in an off-window for the 2-prize swing).

### Seam 2 — It's a heal-wall: chip is worthless, only burst counts
- **Weakness:** Full Metal Lab (−30) + Jumbo Ice Cream (heal 80 from a 3+-energy Active) + retreat-to-bench
  means accumulated small damage gets erased. **And** Raging Hammer punishes leaving a damaged Archaludon.
- **Exploit:** don't grind it down — land **burst that clears the heal in one hit** (a weakness-type OHKO),
  or don't invest at all. Deny the sit-and-heal loop by keeping prize pressure so it must attack, not heal.
- **Maps to:** **new key** `opp_is_heal_wall = true` (see §6 — mint + flag).
- **Objective note (removable padding):** the effective-HP is stacked on *removable* pieces, not the body —
  Full Metal Lab is a Stadium (overwriting it with our own restores +30/hit; but they run **4 copies**, so
  it's a one-turn buy) and **Hero's Cape is a single ACE SPEC** (one per game, no re-equip) → if our pool
  has tool removal, stripping the Cape *permanently* collapses the 400-HP body back toward 300. Both levers
  are *conditional on our deck having a stadium / tool-removal* — a relativization for `/deck-genie`, not a
  Board key here.

### Seam 3 — Cinderace is a setup-only accel engine (no re-establishment)
- **Weakness:** Cinderace is the sole Metal accelerator, enters play **only** via Explosiveness at setup
  (no Raboot/Scorbunny), and once KO'd is gone for good; if it whiffs the opening hand it never comes down.
- **Exploit:** KO Cinderace early (160 HP, Water ×2, 1 prize, retreat 0 so it can't hide) — this strips
  turn-1 acceleration and delays the wall by turns. Water attackers double it. Its value **decays fast**:
  highest turns 0–1; once it has dumped energy and pivoted to the bench it's a spent 1-prize liability —
  redirect pressure to the wall rather than chasing it.
- **Maps to:** `opp_accel_dependent = true` (NEW key — user chose accel-specific over reusing
  `opp_is_engine_dependent`, which is draw-engine only) + `target: Cinderace` role `engine`.

### Seam 4 — Slow tempo + a soft engine: a real turns-1–2 window before the wall exists
- **Weakness:** wall online ~turn 2–3; the deck wins by attrition and **cannot race**. Its consistency is
  **all-Trainer draw** (no draw-engine Pokémon) on **single-type (Metal) energy** — structurally soft to
  hand disruption (shuffle-down) and energy denial, either of which starves the setup.
- **Exploit:** establish board + prize pressure early; get ahead before the armor assembles, then close
  through the Fire windows. Falling behind or durdling hands them the grind. (Hand/energy disruption is a
  deck-relative lever — flag for `/deck-genie` if our pool has it; it's not an objective Board key.)
- **Maps to:** `opp_tempo = "slow"`.

### Seam 5 — Duraludon is the wall before it evolves (fragile pre-evo)
- **Weakness:** 130 HP Basic, Fire ×2, 1 prize. No Archaludon ex wall exists until Duraludon evolves.
- **Exploit:** KO/gust Duraludon **Active** on turns 1–2 (Fire ~80 base OHKOs via ×2). Every Duraludon
  removed pre-evolution is an Archaludon ex that never assembles. (Benched snipe is inefficient — see §2.)
- **Maps to:** `target: Duraludon` role `fragile_preevo`.

### Seam 6 — Boss's Orders is its only proactive disruption (respect, don't fear)
- **Weakness:** the deck's disruption is a gust (Boss's Orders ×4), not lock or denial — it dictates the
  prize race by pulling our fragile piece up, but it does nothing to our engine directly.
- **Exploit:** keep fragile accelerators/support off a gustable-and-KO-able bench state; don't over-extend a
  soft body it can snipe for a cheap prize. (Captured in the counterplay summary, not a Board key.)
- **Maps to:** counterplay prose (a gust caution), not a threat/target — Boss's Orders isn't an attacker.

### Seam 7 — Relicanth is the Raging-Hammer comeback's single point of failure (research-surfaced)
- **Weakness:** Relicanth's Memory Dive is what lets a *chipped* Archaludon ex borrow Duraludon's **Raging
  Hammer** (80 + 10 per damage counter on itself) — the deck's punish for leaving a damaged wall alive
  (up to ~370 when near-death). Decks run **exactly one** Relicanth, and it's a **100-HP Fighting Basic**
  that is **NOT Metal**, so Full Metal Lab's −30 and the whole tank stack do **not** protect it.
- **Exploit:** gust/snipe Relicanth early (before the wall is chipped) to delete the Raging Hammer option,
  capping Archaludon to flat-220 Metal Defender. This *also* re-opens the chip-then-finish line that Seam 2
  otherwise forbids. Secondary/situational — it only matters in a grind, and only if Relicanth is in play.
- **Maps to:** `target: Relicanth` role `engine` (an ability-enabler support Pokémon whose removal strangles
  a capability; not a pre-evo, not a prize liability).

## 4 · Threats & targets (objective card-level intel)

- **Threats** (attackers to respect):
  - `Archaludon ex` — Metal Defender **220** (OHKOs most ~200–220-HP 2-prize attackers) and self-negates
    its Fire weakness on your next turn; the near-unkillable payoff (300 HP + tank stack, 2 prizes).
  - `Cinderace` — cheap `{C}` **50** attacker *and* the turn-1 Metal accelerator (Turbo Flare → 3 energy
    to bench); it arms the wall.
  - `Duraludon` — **Raging Hammer** (80 + 10 per damage counter on itself) scales as it's chipped; don't
    leave a battered Duraludon (or, via Relicanth, a battered Archaludon) alive.
- **Targets** (disrupt / snipe), by role:
  - `fragile_preevo`: `Duraludon` — 130 HP Basic, Fire ×2; the wall before it evolves. KO Active pre-evo.
  - `engine`: `Cinderace` — sole accelerator, setup-only, unrecoverable once KO'd; 160 HP, Water ×2. **Primary.**
  - `engine`: `Relicanth` — the lone Raging-Hammer enabler (Memory Dive); 100 HP Fighting Basic, not Metal
    (Full Metal Lab doesn't shield it). **Secondary/situational** — only in a grind. Snipe to cap Archaludon
    at flat-220 and re-open the chip-then-finish line.
  - `primary_attacker`: `Archaludon ex` — 2 prizes, the payoff; hit it in a Metal-Defender-OFF window (live
    ×2) for the biggest swing.

## 5 · Objective counterplay summary

Beat Archaludon ex / Cinderace by **out-tempoing early, then bursting through Fire weakness** — never by
grinding. It's a slow heal-wall that erases chip damage and punishes it (Raging Hammer), so small hits are
wasted: you need weakness-type **burst** (Fire ×2 turns 300 HP into a ~165-base one-shot) landed in a
**Metal-Defender-OFF window** (pre-MMM, or after gusting an idle Archaludon Active). In parallel, attack
its consistency: KO **Cinderace** (setup-only, unrecoverable accel engine) and **Duraludon** (the fragile
pre-evo) before the wall assembles, and press a **prize lead in the turns-1–2 window** so the deck must
attack rather than sit and heal. Respect its one disruption (Boss's Orders gust) by not over-extending a
soft, snipeable bench. If you let it stabilize into the Metal-Defender + heal cycle, you lose the grind.

## 6 · Brief preview (pre-JSON — filled in Phase 4, emitted in Phase 6)

```
opponent_properties = {
  "opp_is_heal_wall":    true,   # NEW KEY — mint + flag (consumer: unwired). Chip is worthless (Full Metal
                                 #   Lab -30 + Jumbo Ice Cream heal 80 + Raging Hammer punish); only
                                 #   weakness-type burst that clears the heal in one hit works.
  "opp_accel_dependent": true,   # NEW KEY — mint + flag (consumer: unwired). Setup hinges on a sole energy-
                                 #   ACCEL Pokémon (Cinderace); gust+KO it to strangle the ramp. Distinct
                                 #   from opp_is_engine_dependent (which is DRAW-engine only).
  "opp_tempo":           "slow"  # reuse — wall online turn 2-3; cannot race; win the early window.
}
threats = [
  { "card": "Archaludon ex", "why": "Metal Defender 220 + self-negates Fire weakness next turn; 300 HP tank, 2 prizes." },
  { "card": "Cinderace",     "why": "Cheap {C} 50 attacker AND the turn-1 Metal accelerator (Turbo Flare)." },
  { "card": "Duraludon",     "why": "Raging Hammer (80 +10/counter on self) scales as it is chipped." }
]
targets = [
  { "card": "Duraludon",     "role": "fragile_preevo",  "why": "130 HP Basic, Fire x2; the wall before it evolves — KO Active pre-evo." },
  { "card": "Cinderace",     "role": "engine",          "why": "Sole accelerator, setup-only, unrecoverable once KO'd; 160 HP, Water x2 (primary)." },
  { "card": "Relicanth",     "role": "engine",          "why": "Lone Raging-Hammer enabler (Memory Dive); 100 HP, not Metal so Full Metal Lab doesn't shield it (secondary/situational)." },
  { "card": "Archaludon ex", "role": "primary_attacker", "why": "2 prizes, the payoff; hit in a Metal-Defender-OFF window (live x2)." }
]
```

## 7 · Resolved decisions & deferred

**Resolved at sign-off (2026-07-04):**
- `opp_is_heal_wall` — **minted** (user confirmed the "burst-not-chip, lean on weakness" shape over the
  narrower `opp_heals` / `opp_damage_floor`).
- `opp_accel_dependent` — **minted** (user chose an accel-specific key over reusing `opp_is_engine_dependent`,
  which stays draw-engine only). Both new keys land in `assets/opponent_properties.json` with `consumer:
  "unwired"` (forward contracts — a separate, unbuilt consumer must map them onto `Board`).
- Relicanth added as a secondary `engine` target (research-surfaced; the human reviews it in the Brief diff).
- Boss's Orders gust caution stays prose-only (it's a Supporter, not an attacker → no threat/target row).

**Deferred (not blocking the Brief — inert data today):**
- Two new keys await consumer wiring before they change any play; flagged in the Phase-B diff.
- Metal-Defender-OFF adjudication (does a gusted idle Archaludon leave weakness live in-sim?) — objective
  mechanic is sound per rules.md §5; the Pilot-side consumer should replay-confirm before relying in-match.
- Stadium-swap / tool-strip / hand-disruption levers are deck-relative (need our pool to have the tech) —
  handed to `/deck-genie` relativization, not encoded as objective Board keys.
