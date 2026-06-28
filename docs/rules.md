# Game rules — canonical reference (READ BEFORE any strategy/blunder/meta reasoning)

**Mandate.** Before stating, using, or reasoning about a game rule, card stat, or mechanic — in
strategy authoring, blunder-busting, meta parsing, tuning, or anything else — **read it here or at the
cited source. Never recall a rule from training/general knowledge.** This is the Pokémon **TCG**
(Scarlet & Violet rules), *not* Pokémon TCG Pocket — they differ. The card *set* here also differs from
the mainline TCG (see CLAUDE.md: e.g. `Riolu → Mega Lucario ex` is a single hop, no Lucario).

## Provenance hierarchy (most authoritative first)

The **native engine** (`cg/cg.dll`, `cg/libcg.so`) is the final arbiter, but it's a binary — you can't
read rules text from it. So "verify at source" means, in order:

| Tag | Source (readable) | What it's authoritative for |
|---|---|---|
| `[ENGINE-LEGAL]` | engine behavior — only legal options are ever offered | move legality; the agent **cannot** make an illegal move (verify by replay/option enumeration) |
| `[ENGINE-ENUM]` | [`src/cg/api.py`](../src/cg/api.py) IntEnums | mechanics *vocabulary* (areas, card types, energy types, special conditions, select contexts) |
| `[ENGINE-STAT]` | [`data/EN_Card_Data.csv`](../data/EN_Card_Data.csv) → `cg.api.all_card_data()` → `CardStat` ([provider.py](../src/common/scouting/provider.py)) | per-card numbers (HP, weakness *type*, resistance *type*, retreat, attacks, costs, damage) |
| `[ENGINE-TAG]` | [`src/common/card_functions.json`](../src/common/card_functions.json) | per-card *behavioral* tags (draw/search/heal/…) — behavioral only |
| `[SIM-DELTA]` | [`rulebook.txt`](rulebook.txt) §"Differences …" (L647-674) | where the simulator **deliberately differs** from official rules — **outranks `[RULE]`**; the sim is declared authoritative (L674) |
| `[RULE]` | **in-repo** [`rulebook.txt`](rulebook.txt) (official S&V rulebook + competition notes); secondary: Bulbapedia | numeric/procedural rules the engine *implements* but doesn't expose as text (multipliers, per-turn limits) |
| `[PROJECT-VERIFIED]` | this repo's research/correction history | rules already confirmed (or refuted) here |

> **Primary in-repo source = [`docs/rulebook.txt`](rulebook.txt)** — the official
> Scarlet & Violet rulebook **plus** a competition-specific "Differences … and Simulator Behavior"
> section. Read the raw file for anything not digested here. **The simulator's behavior is declared the
> correct behavior (L674)** — so `[SIM-DELTA]` and `[ENGINE-*]` beat `[RULE]` whenever they conflict.

**The single most useful distinction:** most turn-structure rules are **`[ENGINE-LEGAL]`** — the engine
only offers legal options, so the agent can't violate them. They still matter for **reasoning** (e.g.
"don't attach Ignition T1-going-first — you can't attack, so it's discarded for nothing", correction
ep81903490 f5). Rules below are flagged **enforced** (legality, can't break) vs **reason-only** (the
engine won't stop you, your strategy must).

---

## 0. Competition deltas (simulator ≠ official — these OVERRIDE the official rules) `[SIM-DELTA]`

From [`rulebook.txt`](rulebook.txt) L647-674. **The sim is authoritative (L674).**

- **Simultaneous win ⇒ DRAW.** When both players would win at the same time (e.g. both take their last
  prize on a double-KO), the competition treats it as a **draw** — NOT the official tiebreaker game
  (L672, contrast official L285-291). Strategic consequence: a "both-win" line is a draw, not a win.
- **Prize-take order on simultaneous KO** differs (turn-player takes fully, then opponent — L664-671),
  but result is a draw anyway, so it doesn't change outcomes.
- **Some attacks are simply not offered** when their effect can't resolve — e.g. a bench-placing attack
  with no open bench, a draw attack with 0 cards in deck, a hand-interaction attack vs an empty hand
  (L651). Reinforces `[ENGINE-LEGAL]`: if it's not in the options, don't reason about declaring it.
- **Mega Zygarde ex — Nullifying Zero:** target order can't be chosen; coins flip automatically
  left-to-right (L653). (Only matters if that card appears.)
- **Meta-rule:** any further sim/official divergence — **the simulator wins** (L674).

---

## 1. Vocabulary (straight from `[ENGINE-ENUM]` — `src/cg/api.py`)

- **Areas** (`AreaType`): DECK, HAND, DISCARD, ACTIVE, BENCH, PRIZE, STADIUM, ENERGY, TOOL,
  PRE_EVOLUTION, PLAYER, LOOKING.
- **Card types** (`CardType`): POKEMON, ITEM, TOOL (Pokémon Tool), SUPPORTER, STADIUM, BASIC_ENERGY,
  SPECIAL_ENERGY.
- **Energy types** (`EnergyType`): COLORLESS, GRASS, FIRE, WATER, LIGHTNING, PSYCHIC, FIGHTING,
  DARKNESS, METAL, DRAGON, RAINBOW (= every type), TEAM_ROCKET (= Psychic+Darkness).
- **Special conditions** (`SpecialConditionType`): POISON, BURN, SLEEP, PARALYZE, CONFUSE.
- **Select contexts** (`SelectContext`): the decision the engine is asking for — incl. `IS_FIRST=41`
  ("go first?"), `MULLIGAN=42`, `DAMAGE=15` (snipe target), `TO_HAND=7` (search), `EVOLVE=37`, etc.
  Read the enum, don't assume the meaning of a context integer.

## 2. Turn structure & first/second player

- **Coin flip** decides who chooses to go first (`SelectContext.IS_FIRST`). `[ENGINE-LEGAL]`
- **Player going FIRST, turn 1 — restrictions:** `[RULE: rulebook]` `[ENGINE-LEGAL]`
  - **CANNOT attack** (the starting player skips the attack step on turn 1). `[RULE: rulebook L152]` `[PROJECT-VERIFIED: ep81903490 f5]`
  - **CANNOT play a Supporter.** `[RULE: rulebook L133]` (confirmed by the official rulebook)
  - **CAN** attach an Energy, play Items, bench Basics, evolve (subject to §4), retreat, use Abilities.
- **Player going SECOND:** no first-turn restrictions — full turn available. `[RULE: rulebook]`
- **Turn phases (each turn):** draw a card → take actions in any order → (optionally) attack, which
  **ends your turn**. `[RULE: rulebook L105-116]`
- Running out of cards to draw at the start of your turn = you lose (deck-out). `[RULE: rulebook L119]` (see §7)

## 3. Action economy — per-turn limits

All **`[ENGINE-LEGAL]`** (the engine simply won't offer a second one) and **`[RULE: rulebook L105-148]`**:

| Action | Limit per turn |
|---|---|
| Attach Energy from hand | **1** (manual attachment; card effects can add more) |
| Play a Supporter | **1** |
| Play a Stadium | **1** (and only if it differs from the one in play) |
| Retreat (manual) | **1** (pay the Retreat cost in Energy; card effects can switch for free) |
| Play Items / Pokémon Tools | unlimited (Tool: 1 per Pokémon) |
| Use Abilities | per the ability's own text |
| Attack | **1**, and it **ends the turn** |

## 4. Evolution timing `[RULE: rulebook L123-128]` `[ENGINE-LEGAL]`

- Cannot evolve a Pokémon **the turn it was played/put into play** (it's "new in play").
- Cannot evolve **on either player's very first turn** of the game.
- Stage gate: Basic → Stage 1 → Stage 2. Evolving keeps attached cards + damage counters; **clears**
  Special Conditions and attack effects.
- Evolve by name: the Evolution's `evolvesFrom` (Previous stage) must match the Pokémon in play.
  `[ENGINE-STAT]` — verify the line in `EN_Card_Data.csv` (do **not** assume mainline chains).
- **Mega Evolution Pokémon *ex* (this set) have NO special rules** (rulebook Appendix 1, L331-337):
  they evolve under the normal rules and **evolving into one does NOT end your turn.** `[RULE: rulebook L335]`
  ⚠️ This is the *opposite* of the older Mega Evolution Pokémon-**EX** (XY), where becoming one ends your
  turn (L481/L569) — don't import that from memory. Strategically load-bearing for `mega_starmie`
  sequencing (you can evolve into the Mega and still act/attack). Mega ex can be Basic/Stage 1/Stage 2;
  Mega Kangaskhan ex is even a Basic. **`Riolu` → `Mega Lucario ex` is a single hop** — the rulebook
  states it explicitly (L335). *(Sim is authoritative; confirm turn-end behavior by replay if a
  sequencing decision hinges on it.)*

## 5. Attacking & damage `[RULE: rulebook L168-270]`

- **Weakness:** the defending **Active** takes **more** damage from an attack of its weakness type —
  multiplier is the **printed amount** (S&V cards print **×2**, e.g. L172). Active base damage **only** —
  never Bench (L170), never ability/effect damage counters. `[PROJECT-VERIFIED]`
- **Resistance:** the defending Active takes **less** damage — by the **per-card printed amount** next to
  its resistance type (L265, glossary L614). **There is no universal number** (my earlier "−30" was
  wrong — it's whatever the card prints). Bench Pokémon ignore Resistance too.
- Weakness/Resistance are stored as a **type** on the card (`{P}` = Psychic): `CardStat.weakness` /
  `.resistance` = an `EnergyType`. The multiplier/reduction is the **rule**, not card data. `[ENGINE-STAT]` type; `[RULE]` amount.
- **Damage calc order** (L255-270): base printed → effects on *your* Active (e.g. "+40 this turn") → **×
  Weakness** → **− Resistance** → effects on the *defender* (e.g. "takes 20 less") → place 1 counter per
  10. Damage counters placed directly (not "damage") are **not** modified by Weakness/Resistance (L258).
- Attack **Cost** = Energy requirement; `CardStat.minAttackCost` = cheapest attack's energy count,
  `maxDamage` = highest printed damage. A 0-cost attack needs no Energy. `[ENGINE-STAT]`
- Attacking **ends your turn** (L150). An attack with no damage (e.g. "Call for Family") is still an attack.

## 6. Knockouts & prizes `[RULE: rulebook]`

- Damage ≥ HP → Knocked Out → it + attached cards go to discard; **attacker takes prize card(s)** (L175).
- **Prize value** (`[ENGINE-STAT]` `megaEx`/`ex` booleans → practical mapping for this set):
  | Category | Prizes |
  |---|---|
  | Mega Evolution Pokémon ex (`megaEx`) | **3** `[PROJECT-VERIFIED: "Mega-ex=2" refuted]` `[RULE: L333]` |
  | Pokémon ex / -EX (`ex`) | **2** `[RULE: Appendix 5/25]` |
  | regular Pokémon | **1** |
  *(General TCG also: V/VSTAR/GX/Tera ex = 2; VMAX/V-UNION/TAG TEAM = 3 — unlikely in this S&V Mega set, but verify per card.)*

## 7. Win conditions `[RULE: rulebook L83-89]`

You win when any one is true (goal-state for plan selection, not a reflex):
1. You take your **last prize card**.
2. Opponent has **no Pokémon in play** to replace a KO'd Active.
3. Opponent **cannot draw** at the start of their turn (deck-out).

⚠️ **Simultaneous win = DRAW** in this competition (see §0) — not a tiebreaker.

## 8. Special conditions `[ENGINE-ENUM]` `[RULE: rulebook L185-216]`

Only the **Active** can have them; **cleared** when it leaves the Active spot OR evolves. Resolved during
**Pokémon Checkup** (between turns) in this order: **Poisoned → Burned → Asleep → Paralyzed** (L181).

| Condition | Effect |
|---|---|
| POISON | place **1** damage counter each Checkup (marker; persists) |
| BURN | place **2** damage counters each Checkup, then flip — heads removes it |
| SLEEP | can't attack/retreat; flip each Checkup — heads wakes |
| PARALYZE | can't attack/retreat; auto-recovers after the owner's next turn |
| CONFUSE | flip before attacking — tails: attack fails + **3** counters on self; does not block retreat |

Rotating conditions (Asleep/Confused/Paralyzed) overwrite each other; marker conditions (Poison/Burn)
stack alongside. Only **Asleep & Paralyzed** block retreat.

## 9. Deck building `[RULE: rulebook L313-316, Appendices]`

- Exactly **60 cards**. At least **1 Basic Pokémon**. Max **4** of any one name **except Basic Energy**
  (unlimited). **ACE SPEC:** 1 total per deck (Appendix 3). **Radiant:** max 1 (Appendix 8).
- Naming subtleties matter for the 4-copy rule and evolution: suffix/owner/regional forms are part of the
  name (`Riolu` ≠ none here, but e.g. `Iono's Tadbulb` ≠ `Tadbulb`); Level is not. Verify names at source.

## 10. Effect-quantity wording `[RULE: rulebook L272-278]`

- "**up to X**" (attack effects) → choose 0…X. Other effects (Trainers/Abilities) → 1…max.
  "**any amount / any number**" → may choose 0. Search "for any card" → must choose ≥1.
- Draw/look more than remain → take what's left; you only lose on a **start-of-turn** empty-deck draw,
  not an effect-driven one (L280-283).

## 11. Bench-protection (snipe-relevant) `[RULE: Appendix 6]`

- **Tera Pokémon ex take NO attack damage while Benched** (both players' attacks). A Tera ex on the
  bench is an **invalid snipe target for damage** — relevant to the M0 evolving-threat snipe work.
  Verify per card (`CardStat` / card text); flag if it appears in the meta.

---

## Where each fact lives (source map)

| You need… | Read… |
|---|---|
| A card's HP / weakness type / resistance type / retreat / attacks / costs / damage / stage / evolvesFrom | `data/EN_Card_Data.csv` (or `CardStat` at runtime) `[ENGINE-STAT]` |
| What a card *does* behaviorally (draw/search/heal/gust/energy_accel/…) | `src/common/card_functions.json` `[ENGINE-TAG]` |
| What decision the engine is asking / the option encoding | `src/cg/api.py` enums `[ENGINE-ENUM]` |
| Whether a move is legal right now | the offered options (engine) `[ENGINE-LEGAL]` |
| A multiplier / per-turn limit / procedural rule | this file → [`rulebook.txt`](rulebook.txt) `[RULE]` |
| How the **sim differs** from official rules | [`rulebook.txt`](rulebook.txt) L647-674 `[SIM-DELTA]` (§0 above) |

## Bibliography (the in-repo rulebook is primary; the sim overrides it where noted)

- **`docs/rulebook.txt`** — official Pokémon TCG (Scarlet & Violet) rulebook **+ the
  competition's "Differences … and Simulator Behavior" section** (the authoritative deltas). **Primary.**
- Pokémon TCG Rulebook (S&V), upstream PDF. <https://www.pokemon.com/static-assets/content-assets/cms2/pdf/trading-card-game/rulebook/par_rulebook_en.pdf>
- Bulbapedia — *Attack (TCG)* / *Rule Box (TCG)* (secondary cross-check only).

> Anything tagged "confirm/verify before relying" is **not yet** corroborated against this engine — do
> that (replay/option inspection) before treating it as ground truth, and upgrade the tag here.
