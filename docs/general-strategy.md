# General Strategy — the deck-agnostic doctrine

The **General Strategy** is the shared baseline of decision rules every deck plays *beneath* its
own [Strategy](../my_submissions/common/CONTEXT.md). It is a registry of weighted, testable
**Hypotheses** ([agent-architecture.md](agent-architecture.md)) keyed on **universal** signals —
[Function Tags](card-functions.md) (what a card *does*), engine card stats (HP, weakness, prize
value), and a per-decision **board** summary — so a brand-new deck already plays competent
Pokémon TCG before it authors any deck-specific doctrine. The Pilot scores it together with the
deck's Strategy ([ADR-0008](adr/0008-pilot-is-a-layered-rules-pipeline.md)); a deck specialises or
disables any rule by overriding its weight **by id** (learned from replays/training, not
hand-authored — [ADR-0009](adr/0009-training-methodology.md)). Weights are seeds on the
[weight scale](weights.md), to be ladder-tuned.

Source: `my_submissions/common/general_strategy.py` (positional hypotheses) and the Tactical
Evaluator in `common/pilot.py` (combat). Each Hypothesis carries a plain-English `rationale`
(surfaced to users in the decision trace, `Pilot.explain`) and a `status`
(`assumed → testing → confirmed / refuted`). Heuristics are grounded in competitive Pokémon TCG
theory — see the [Bibliography](#bibliography).

## Setup & sequencing

### `dig-before-commit` · weight 20 · status: assumed
> During setup, play draw and search cards first — see more of your deck and find your pieces
> before making irreversible plays like attaching Energy.

**Reads:** tags `draw` / `search`. **Fires:** `SETUP`. **Source:** F12 — TCG Protectors
(Sequencing); JustInBasil (Consistency).

### `attach-energy-last` · weight −5 · status: assumed
> Attach Energy late in the turn — it's the one irreversible setup action, so play your draw,
> search and development first to reveal the best target before committing.

**Reads:** option is an `ATTACH`. **Fires:** `SETUP`. **Source:** F12 — JustInBasil (Damage:
"once it's on a Pokémon, it's stuck there").

### `build-before-attack` · weight −20 · status: assumed
> During setup, don't waste the turn chipping with a non-lethal attack — your turn ends when you
> attack, so develop your board instead unless the attack scores a knockout.

**Reads:** option is an attack that is **not** a KO (`is_attack & !is_ko`). **Fires:** `SETUP`.
**Source:** F6 — Bulbapedia (*Attack*: using an attack ends your turn).

## Bench development & prize liability

### `keep-a-bench` · weight 60 · status: assumed
> Never leave yourself with an empty Bench — if your Active is Knocked Out and you have no Pokémon
> to promote, you lose on the spot. With an empty Bench, develop a Basic.

**Reads:** `board.my_bench == 0` & a `PLAY` of a Pokémon. **Fires:** any plan. Near-imperative
(loss prevention). **Source:** F7 — Rulebook (win condition 2: no Pokémon in play = loss).

### `dont-bench-multiprize` · weight −15 · status: assumed
> Avoid putting a 2-prize (ex) or 3-prize (Mega ex) Pokémon into play during setup unless it's
> your win-condition attacker — every benched multi-prizer is an easy multi-prize knockout the
> opponent can target.

**Reads:** stat `ex` / `megaEx` + the deck Role `win_condition` / `primary_attacker`.
**Fires:** `SETUP`. **Source:** F8 — TCG Protectors (Prize Trade); JustInBasil (Secondary
Attackers).

### `pre-position-attacker` · weight 25 · status: assumed
> While racing, keep developing the next attacker on the Bench so a Knocked-Out Active is replaced
> without losing a turn.

**Reads:** a `PLAY` of a Pokémon. **Fires:** `RACE` (aggression). **Source:** F14 — JustInBasil
(Deck Strategy: maintain a stream of attackers).

## Combat (Tactical Evaluator)

These live in the Search-backed Tactical Evaluator, not as positional weights — they score
attacker × attack outcomes.

### Weakness ×2
A knockout is computed from printed damage **doubled when the defending Active is Weak to my
Active's type** (S&V rule; Active base damage only — never Bench, never ability/effect counters).
Closed-form Tier-0; Tier-1 Search resolves the exact figure. **Source:** F4 — Rulebook;
Bulbapedia (*Attack*).

### `prize-trade-target`
Among knockouts, prefer the **higher-prize target** — a KO yields `Mega ex → 3`, `ex → 2`,
`else → 1` prizes, so the agent values taking down multi-prizers. (The per-turn shadow of prize
mapping; see below.) **Source:** F1 / F3 — TCG Protectors (Prize Trade); JustInBasil; PokeBeach
("Small is Good").

## Designed, not yet seeded

| Rule | Needs | Source |
|---|---|---|
| `gust-the-damaged` — gust an *already-damaged* benched opponent into a KO (chip → prize) | opponent-bench targeting, i.e. **Posture** ([scouting.md](scouting.md)) + the gust option's target | F9 — JustInBasil (Gusting) |
| HP-/damage-boost "crosses an OHKO line" | a damage/HP **breakpoint model** + meta stat table | F10 / F11 — JustInBasil (Damage) |

## Not a reflex weight — handled elsewhere

- **Prize map** (the multi-turn planned KO sequence) → **planning**: Tier-1 Search + the Base
  Value Model ([ADR-0007](adr/0007-learning-is-one-offline-value-model.md)). A single weight can't
  sequence knockouts across turns; its *per-turn shadows* are `prize-trade-target` +
  `dont-bench-multiprize` + `keep-a-bench`. (F13)
- **Win conditions** (take 6 prizes / opponent has no Pokémon / opponent decks out) → goal-state
  for `choose_plan` (steer CLOSE / STABILIZE by the prize race). (F2)
- **Action economy** (one Energy / Supporter / Stadium / retreat per turn; first player can't
  attack T1; no evolving on entry turn) → **engine-enforced**: only legal options are ever
  offered, so no hypothesis is needed. (F5)

## Encoding caveats (from the research)

- **Mega ex = 3 prizes** (verification *refuted* "Mega-ex = 2"). Prize value: `megaEx → 3`,
  `ex → 2`, else `1`.
- **Weakness ×2 applies only to the Active's base damage** — never the Bench, never
  ability/effect damage counters.
- Sequencing is a **default**, not an absolute (carve-outs: deck-thinning; Energy-first when an
  Ability needs the attachment) — hence small weights, to be tuned.
- Deliberately *not* encoded (adversarially refuted as non-universal): blanket "gusting is core
  for any deck," and opponent-prize-count triggers ("when the opponent has 2 prizes, snipe").

## Bibliography

Sources the heuristics were drawn from, verified during research (2026-06-24). Official rules are
primary; strategy heuristics lean on JustInBasil (an authoritative community reference) and were
cross-corroborated by non-commercial sources.

**Official rules**
- Pokémon TCG Rulebook (Scarlet & Violet). <https://www.pokemon.com/static-assets/content-assets/cms2/pdf/trading-card-game/rulebook/par_rulebook_en.pdf>
- Bulbapedia — *Attack (TCG)* (weakness ×2, Active-only; attacking ends your turn). <https://bulbapedia.bulbagarden.net/wiki/Attack_(TCG)>
- Bulbapedia — *Rule Box (TCG)* (prize values by category). <https://bulbapedia.bulbagarden.net/wiki/Rule_Box_(TCG)>

**Competitive strategy**
- JustInBasil — *Deck Strategy*. <https://www.justinbasil.com/guide/deck-strategy>
- JustInBasil — *Gusting*. <https://www.justinbasil.com/guide/gusting>
- JustInBasil — *Damage*. <https://www.justinbasil.com/guide/damage>
- JustInBasil — *Secondary Attackers*. <https://www.justinbasil.com/guide/secondary-attackers>
- JustInBasil — *Consistency*. <https://www.justinbasil.com/guide/consistency>
- TCG Protectors — *Intermediate Strategy Guide*. <https://tcgprotectors.com/blogs/pokemon-deck-guides/pokemon-tcg-intermediate-strategy-guide>
- TCG Protectors — *Prize Mapping Guide*. <https://tcgprotectors.com/blogs/pokemon-blog/pokemon-tcg-prize-mapping-guide-2026>
- TCG Protectors — *Prize Trade Guide (Advanced Prize Mapping)*. <https://tcgprotectors.com/blogs/pokemon-blog/pokemon-tcg-prize-trade-guide-advanced-prize-mapping>
- TCG Protectors — *Advanced Sequencing Guide*. <https://tcgprotectors.com/blogs/pokemon-blog/pokemon-tcg-advanced-sequencing-guide-grandmaster-playbook>
- TheGamer — *Beginner's Tips & FAQ*. <https://www.thegamer.com/beginners-tips-faq-guide-pokemon-trading-card-game/>
- Pixel Hub — *12 Beginner Mistakes in Pokémon TCG*. <https://pixel-hub.co.uk/blogs/news/12-beginner-mistakes-in-pokemon-tcg>
- Levels PTCG — *How Pokémon Prize Cards Work*. <https://levelsptcg.com/how-pokemon-prize-cards-work/>
- Pokémon Authority — *Prize Cards Mechanic*. <https://pokemonauthority.com/pokemon-tcg-prize-cards-mechanic>
