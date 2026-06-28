# General Strategy — the deck-agnostic doctrine

> **Game rules** (turn structure, weakness ×2, prizes, per-turn limits, special conditions) are
> canonical in **[rules.md](rules.md)** — read it before reasoning about any rule. This doc covers
> *strategy*; rules.md covers *the rules they operate within*.

The **General Strategy** is the shared baseline of decision rules every deck plays *beneath* its
own [Strategy](../src/common/CONTEXT.md). It is a registry of weighted, testable
**Hypotheses** ([agent-architecture.md](agent-architecture.md)) keyed on **universal** signals —
[Function Tags](card-functions.md) (what a card *does*), engine card stats (HP, weakness, prize
value), and a per-decision **board** summary — so a brand-new deck already plays competent
Pokémon TCG before it authors any deck-specific doctrine. The Pilot scores it together with the
deck's Strategy ([ADR-0008](adr/0008-pilot-is-a-layered-rules-pipeline.md)); a deck specialises or
disables any rule by overriding its weight **by id** (learned from replays/training, not
hand-authored — [ADR-0009](adr/0009-training-methodology.md)). Weights are seeds on the
[weight scale](weights.md), to be ladder-tuned.

Source: `src/common/general_strategy.py` (positional hypotheses) and the Tactical
Evaluator in `common/pilot.py` (combat). Each Hypothesis carries a plain-English `rationale`
(surfaced to users in the decision trace, `Pilot.explain`) and a `status`
(`assumed → testing → confirmed / refuted`). Heuristics are grounded in competitive Pokémon TCG
theory — see the [Bibliography](#bibliography).

**Energy attachment** is a layered, deck-overridable procedure of its own
([ADR-0016](adr/0016-energy-attachment-is-a-layered-procedure.md)): the general rules below
(`power-up-attacker`, `use-acceleration`, `dont-feed-the-doomed`, `attach-energy-last`) read deck
*roles* and engine *stats*, never hand-authored numbers. Readiness (the `SETUP → RACE` flip) is
**engine-derived** — a Line's `ready.energy` defaults to `None`, so "online" is the payoff's
cheapest attack cost (`CardStat.minAttackCost`): Mega Starmie ex is online at 1 W (Jetting Blow),
not the 3 of Nebula Beam.

## Opening

### `keep-a-startable-hand` · weight −40 · status: assumed
> Don't mulligan away a hand you can already start — if a Pokémon in hand can take the Active Spot
> (a Basic, or one whose Ability lets it open, like Explosiveness), keep it rather than redraw and
> give the opponent a free card.

**Reads:** at a `MULLIGAN` select (no Basic in hand → "redraw?"), penalises the **redraw** option
when the hand holds an `opener`-tagged card (Explosiveness — [card-functions.md](card-functions.md))
**or** a `starter`-Role card. The role branch makes the keep survive a `card_functions.json` A/B
toggle. **Source:** F7 — Rulebook (the mulligan rule); the card's own Ability text.

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

### `power-up-attacker` · weight 15 · status: assumed
> Attach an Energy every turn — building energy toward an attack is the core tempo of the game;
> without a steady stream of attachments your attackers never come online.

**Reads:** option is an `ATTACH`. **Fires:** `SETUP` / `RACE`. The positive driver that makes the
agent actually attach — it nets `+10` against `attach-energy-last`'s `−5`, so plain Energy gets
played (sequenced after draw/search, but played). **Source:** F12 — JustInBasil (Deck Strategy).

### `use-acceleration` · weight 25 · status: assumed
> Energy acceleration multiplies your one manual attachment per turn — getting attackers online
> faster is tempo-positive for any deck, so prioritise playing your acceleration.

**Reads:** the option card's `energy_accel` Function Tag. **Fires:** `SETUP` / `RACE`. The universal
form of a deck's `accel_source` rule. **Source:** F12 / F14 — JustInBasil (Consistency / Deck Strategy).

### `build-before-attack` / `dont-chip-with-a-doomed-active` — **removed** (superseded by attack-last)
These two chip-penalty rules made development beat a weak attack. The Pilot's `_finish_turn_last`
("attack last", `pilot.py`) now does that **structurally** — at the open turn menu it sequences every
beneficial non-ending action ahead of the turn-ending attack, then takes the attack (and its KO) the
same turn. A blanket chip penalty became redundant *and* harmful: with no development available it
dragged a useful chip below `End`, so the agent did nothing instead of chipping. Removed (and the
`_CHIP_CEILING` value-floor with them). **Source:** F6 — Bulbapedia (*Attack*: using an attack ends
your turn) — the very fact attack-last is built on.

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

### `dont-feed-the-doomed` · weight −30 · status: assumed
> If your Active will be Knocked Out next turn and you have a benched Pokémon, don't sink this
> Energy into the doomed Active — attach to the successor instead so you aren't rebuilding from
> nothing after it falls.

**Reads:** at an `ATTACH_FROM` select, penalises attaching to my **Active** (`option_area`) when the
board's **incoming-KO** estimate fires (the opponent's biggest attack, doubled on my Active's
Weakness, ≥ my Active's remaining HP) **and** I have a Bench. The threat estimate is closed-form off
engine stats (`maxDamage` / `weakness` / HP); attack-affordability is a future refinement.
**Source:** F8 / F14 — TCG Protectors (Prize Trade); JustInBasil (Secondary Attackers).

## Targeting the opponent's Bench

### `snipe-the-threat` · weight 20 · status: testing
> When an attack lets you choose which benched Pokémon to damage, hit the biggest threat. A benched
> Pokémon already carrying Energy is closest to attacking, so sniping it (chip or Knock Out) denies
> the opponent their next attacker rather than poking a bare, not-yet-online benchsitter.

**Reads:** at a `DAMAGE` select, the per-option `Context.target_energy` / `target_is_threat` — the
Energy attached to the **benched** Pokémon a `CARD` option targets (resolved off the option's
`area`/`index`/`playerIndex` via `Pilot._option_pokemon`, the same path as `_option_card_id`; `None`
for non-target options). Fires on the bench target that already carries Energy. This is the first
wired **opponent-Bench targeting** signal; its value sub-terms are reused (not its order) by the
**Gust (Boss's Orders)** doctrine below.
**Caveat:** "threat" has a second face — a Pokémon that *evolves* into an attacker (e.g. Riolu→Lucario)
is a threat with **zero** Energy, which this energy signal can't see; that is a separate, deferred
cluster (a Function-Tag / Line lookup, not Energy). **Source:** F9 — JustInBasil (Gusting: remove
the opponent's developing attacker).

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

## Gust (Boss's Orders) — designed, not yet built

The doctrine for a **gust** — force the opponent to switch a benched Pokémon into their Active Spot
(Boss's Orders, card id 1182). Grilled 2026-06-29, recorded in
[ADR-0022](adr/0022-gust-is-closed-form-lethal-lookahead.md); it supersedes the earlier
`gust-the-damaged` sketch. A gust is **two** Pilot decisions — *whether to play it* (one Supporter
per turn; can't be played turn 1 on the play) and *which benched Pokémon to drag up* — neither
supported today. (`prize-trade-target` below is a Tactical prize-preference over the *current* Active,
not a Hypothesis; the gust decisions happen *before* the gust resolves, so Tactical can't see the
future KO at the point of choosing.)

**Doctrine — hold by default; gust only into a KO or a decisive stall.** A gust changes *which*
opponent Pokémon is Active, worth your one Supporter only when the best target this turn is on their
**bench**. Priority: **lethal/closing ▸ prize-grab KO ▸ threat-denial ▸ pre-evo tempo ▸ defensive
stall**. **Never gust a target you can't KO** (it gifts the opponent — their committed Active goes
safe to the bench, the dragged-up mon attacks you next turn) — except the stall. This respects the
refuted "blanket gusting is core" caveat below: the gust is **KO-gated**, not a reflex.

**Engine facts** (verified against the replay corpus + `cg/api.py`, per [CLAUDE.md](../CLAUDE.md)):
the target-select is `SelectContext.SWITCH(3)` (**not** `TO_ACTIVE(4)`), opponent-owned options
(`area=BENCH`, `playerIndex != yourIndex`); `SWITCH(3)` is also the agent's own retreat, so
`playerIndex` is the disambiguator. Prizes-remaining is in the observation (`players[i].prize`
length). The `gust` Function Tag spans four mechanically different cards, so v1 gates to **card id 1182**.

### `gust_ko` — the shared lethal oracle (Tactical, generalized to any defender)
`gust_ko(my_active, defender) → (can_ko, prizes)` lifts the Tactical KO math from the *current* Active
to an **arbitrary** opponent Pokémon: the best **affordable** attack (availability-gated **+1** for
the manual attach we can actually make this turn), **×2 on the defender's Weakness, minus the
defender's Resistance**, vs the defender's HP; `prizes = Mega ex 3 / ex 2 / else 1`. Closed-form off
`CardStat`, no Search (the Tier-0 contract). **One oracle feeds both gust decisions**, so the
play-reason and the picked target agree by construction (a Verifier invariant). "Best affordable" =
**best total board value**, not max printed damage — a 120 KO **+ 50 bench snipe** beats a 210 overkill
when a worthwhile snipe target exists (reuse the snipe sub-terms); else fall back to cost-efficiency.

### `gust-for-the-ko` · whether-to-play · seed: value-proportional · status: designed
> Play Boss's Orders only when it converts to a KO this turn that beats your best non-gust line —
> drag up a benched Pokémon you can KO (a prize you couldn't otherwise reach), especially a high-prize
> ex/Mega hiding behind a wall.

**Reads:** a `MAIN`/`PLAY` of a `gust`-tagged card (v1: id 1182) + `Board.gust_best_ko_prizes > 0`.
**Net-of-baseline:** the gust KO must beat (a) KOing the current Active for free (gusting *removes*
that Active) **and** (b) the best alternative Supporter. **Scale:** **lethal** (gust prizes ≥ the
opponent's remaining prizes) scores in `KO_SCORE`-class and dominates any setup Supporter; a
**non-lethal** gust-KO is a tunable seed, **damped in `SETUP` while the win-condition isn't in play**
so a setup tutor can still win the Supporter slot. **Source:** F8/F9 — TCG Protectors (Prize Trade);
JustInBasil (Gusting).

### `gust-target` · the `SWITCH(3)` target-select · comparator · status: designed
> Among the benched Pokémon you can KO after gusting, drag up the most valuable one.

**Reads:** at a `SWITCH(3)` select with an opponent-owned (`playerIndex != yourIndex`) bench option,
per-target `gust_ko`. **Hard-filter to `can_ko` first** — a non-KO gust is a blunder; this is the one
place the gust pipeline differs from snipe (which has no KO filter). Rank survivors by **additive**
value, **lethal short-circuiting above all**: `value = prizes + denial + forward_denial`, where
- **`denial`** (board-only): the target threatens to KO one of my Pokémon soon — its incoming damage
  (×2 on my Weakness) vs my board — scaled by the prize value of what it would KO. So a live 1-prize
  attacker that kills my 3-prize win-condition outranks a fat **inert** 2-prize ex (prizes-first is a
  trap).
- **`forward_denial`** reuses the Evolving-Threat primitive (`forward_max_damage ≥ EVOLVING_THREAT_DMG`).

Engine/replaceability denial ("their irreplaceable accelerator") needs the **Read** and is deferred.
Share only the snipe **value sub-terms** (energy-threat / forward-damage / weakest-HP), never snipe's
order or its (absent) KO filter. **Source:** F8/F9 — TCG Protectors (Prize Trade); JustInBasil (Gusting).

### `gust-for-the-stall` · defensive stall-gust · seed: low (below all tutors) · status: designed
> With no offense available, strand an energyless, high-retreat opponent benched Pokémon in the Active
> Spot to waste their turn.

**Fires only when** `Board.active_doomed` (their current Active will KO mine next turn) **and** no
gustable KO **and** no KO on the current Active **and** an **energyless, retreat ≥ 2** bench target
exists. Gusting their attacker to the bench removes the immediate threat; the stranded mon can't
attack, costing them a retreat to recover. Weighted below every tutor/draw (a last resort). **Never**
gust away an Active you've condition-doomed (Poison/Burn/Asleep clears on leaving the Active Spot — a
rescue). **Mechanical caveat:** Boss's does not stop a normal retreat, so the stall only bites on a
genuinely high retreat cost — hence the `active_doomed` gate (you're losing anyway, so a bought turn
is upside). **Source:** F9 — JustInBasil (Gusting: disrupt the opponent's tempo).

### Defensive guards
- **Draw ≠ win:** a simultaneous double-KO that empties both players' prizes is a **draw**, not a win
  ([rules.md](rules.md)) — `is_lethal` must not count it. But a forced draw beats a loss, so when
  otherwise doomed a draw-forcing line is valued **above a loss, below a clean win**.
- **Self-fragility damper:** reduce a non-lethal gust's value when taking it leaves my Active doomed
  with **no benched win-condition ready**, scaled by my Active's prize value (don't expose the
  3-prizer for a 1-prize gust). Overlaps a general "don't over-extend the win-condition" rule — a
  candidate to promote later.

**New signals this needs** (board-only v1): `Board.my/opp_prizes_remaining`,
`Board.gust_best_ko_prizes` + the lethal flag; `Context.gust_can_ko` / `gust_ko_prizes` at an opponent
`SWITCH(3)` option; the snipe value sub-terms widened to that select behind the `playerIndex` guard;
and, for the stall, `CardStat.retreatCost`, per-bench energy on `Board.opp_bench`, and
special-condition tracking. **Deferred:** the four-mechanic split (Pokémon Catcher coin-flip, Prime
Catcher self-switch Item, Lisia's Appeal Basic-only + Confuse) and Read-conditioned (engine-denial,
proactive-vs-scouted-matchup) gusting.

## Designed, not yet seeded

| Rule | Needs | Source |
|---|---|---|
| `gust-the-damaged` — **superseded** by the full **Gust (Boss's Orders)** doctrine above (board-only, KO-gated; the already-damaged case is just one KO-able target) | — see ADR-0022 | F9 — JustInBasil (Gusting) |
| Damage-boost "crosses an OHKO line" (e.g. Maximum Belt +50 vs ex) | a damage **breakpoint model** + meta stat table; per-tool damage bonus is unstructured (free text), like `hpBonus` | F10 / F11 — JustInBasil (Damage) |

Two **closed-form breakpoints** have landed, both built on the same weakness-doubled incoming-damage
estimate (`Board.incoming_active_damage`: the opponent's biggest attack, doubled on my Active's
Weakness):
- `Board.active_doomed` (incoming ≥ my Active's remaining HP), consumed by `dont-feed-the-doomed`.
- **`deploy-hp-tool-on-breakpoint`** — the **HP-boost half** of the OHKO-line model: deploy a +HP
  Pokémon Tool the turn its boost lifts a doomed win-condition Active *above* the incoming hit
  (`incoming < my_active_hp + hpBonus`). The per-Tool HP is `CardStat.hpBonus`, parsed from the Tool's
  free skill text (the engine has no structured field) — only the **unconditional** "+N HP" phrasing,
  so a conditionally-restricted Tool parses to 0 and is never over-credited. Generalises to any
  unconditional +HP Tool and any weakness — e.g. Hero's Cape (+100) on Mega Starmie ex (330 → 430).

The **damage-boost half** still waits on a damage breakpoint model + attack-affordability +
opponent-Bench targeting ([ADR-0016](adr/0016-energy-attachment-is-a-layered-procedure.md)); the
same `incoming_active_damage` estimate also seeds the Gust doctrine's `denial` term (board-only — no
Posture needed for v1; engine/replaceability denial waits on the Read).

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
