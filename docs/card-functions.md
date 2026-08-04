# Card-function tags

> Sibling tiers (ADR-0032): per-**attack** effect facts (ignore flags, riders) live in
> [attack-effects.md](attack-effects.md); parametric Trainer/Ability **Effect Clauses** (heal
> amounts, riders, restrictions) ship as `card_effects.json`. Tags here stay the coarse boolean
> *routing triggers*; those tiers carry the quantities the math reads.

Coarse, per-card **Function Tags** describing what a card *does* (`draw`, `search`,
`gust`, `spread`, `energy_accel`, `heal`, `poison`, …). **Behavioral only** — structural facts
(ex/Mega-ex, trainer type, ACE SPEC) are *not* tagged; the runtime reads those off `CardData`
directly (see ADR-0006 revision). Compiled offline, shipped as `card_functions.json`, loaded once
at match start → **O(1)** lookup each decision. A *routing hint* for play/Posture and for deciding
which Search-API queries are worth the per-move budget — never a substitute for the Search API,
which resolves exact effects.

Decision: [ADR-0006](adr/0006-function-tags-single-source-of-structural-facts.md) (revised
2026-06-24 — structural facts removed; Function Tags are behavioral-only).

## Consumers — where tags feed decisions (reach for a tag here)

Function Tags are the **canonical universal *behavioral* signal**. When you add behavioral decision
logic, read a tag — don't re-derive what a card does.

- **Now (wired).** The Pilot loads the table once (`agents/<deck>/main.py` → `Pilot(functions=…)`)
  and exposes it as `Context.tags`. Reading it today: `dig-before-commit` (`draw`/`search`),
  `use-acceleration` (`energy_accel`), and `keep-a-startable-hand` (`opener`, with a `starter`-Role
  fallback) — see [general-strategy.md](general-strategy.md).
- **Planned (designed, not yet wired).** **Posture** (Read-conditioned play) and **Search-API
  query gating** (`search_budget` / Tier-1 — deciding which cards are worth a per-move query). When
  those land they **must** consult tags ([ADR-0008](adr/0008-pilot-is-a-layered-rules-pipeline.md)).

**Which signal to read** — the three sources never overlap:

| Need | Source | In the Pilot |
|---|---|---|
| a card's *behavior* (draw / search / gust / accel / heal / opener / …) | **Function Tag** | `c.tags` |
| a deck's *intent* for a card (win_condition / accel_source / starter / …) | **Role** | `c.roles` |
| a *structural* fact (HP, weakness, prize value, stage, attack cost) | **CardStat** | `c.stat` |

Toggling `card_functions.json` off (comment the `functions=` arg / remove the file) disables only
the tag-reading rules; Role- and stat-driven decisions are unaffected.

## Why probe (not parse, not embed)

The engine exposes a card's effect only as free `text` (`Skill.text` / `Attack.text`) —
**no structured effect data**. So behavioral tags are derived **primarily by probing**:
play the card in the engine and read the `Log` / `SelectContext` it produces (deck→hand
move = `search`, `DRAW` = `draw`, `DAMAGE_COUNTER_ANY` = `spread`, opponent `SWITCH` =
`gust`, …). Text keyword-parsing (lossy) and learned embeddings (no semantics) were both
rejected. Structural facts (ex / trainer-type / ACE SPEC) aren't tagged at all — the runtime reads
them off `CardData` directly, so duplicating them here would only bloat the table.

## Architecture

```
probe_cards.probe_card (lib) ────────────┐
  stable + controlled-combat passes,     │  build_card_functions.py ─► card_functions.json
  per card → {actor, logs, contexts}     │    classify_functions() over the pool   (shipped)
function_overrides.json ─────────────────┘  (curated escape hatch)
```

- **`classify_functions(card, probe, overrides)`** (`meta_tracker/card_functions.py`) —
  pure, lib-free, the brain. Unions probe-derived behavioral tags + curated overrides (no
  structural tags). Fully unit-tested.
- **`probe_cards.py`** — split into *pure helpers* (unit-tested: `build_probe_deck`,
  `find_play_option`/`find_ability_option`/`find_evolve_option`, `evolution_chain`,
  `extract_probe`, `_damaged_option_indices`) and a *lib drive-shell* (`probe_card`, lazy `cg`
  import, run-validated). The shell drives a real game (`battle_start`/`battle_select`): it seeds
  a board, attaches an Energy each turn, plays the target on the actor's MAIN, and records its
  effect. **Three scenarios per card**: *stable* (no attacks → draw/search/dig/gust/switch/
  energy_accel/hand_disruption); *controlled combat* (`attack=True`: only the **opponent**
  attacks, with its **weakest** attack on **high-HP** basics, to chip slowly; target held until
  my Active is damaged, heal's sub-decision prefers a *damaged* Pokémon → `heal`); and
  *attrition* (`ko=True`: the opponent **KOs** my **frail** basics with its **strongest** attack,
  target held until my discard is stocked → a Pokémon + Energy in my discard give `recycle`
  targets, and the opponent's attached Energy gives `energy_denial` targets). I never attack
  back. The latter two align in only ~1-in-N games, so the builder runs several passes and
  **unions** them (`_COMBAT_PASSES`, `_KO_PASSES`).
- **`probe_pokemon`** (Phase 2a) — a Pokémon's function is its *attack*, not "playing" it. This
  drive places the target Active, attaches the matching basic Energy (attack costs sourced from
  the engine's `all_attack()`, since the shipped `cards.json` lacks them — see below), and
  attacks once able, capturing the attack's effect (a Special Condition — `poison`/`burn`/`sleep`/
  `paralyze`/`confuse` — / damage; `spread` for cheap-attack basics like Flutter Mane). The record
  is bounded to the **attacking turn** (`_attack_turn_logs`:
  first `ATTACK` → next turn boundary) so neither the pre-attack energize nor a *later* turn's
  re-energize leaks in as a false `energy_accel`. Basic Pokémon only; Stage 1/2 are
  `probe_evolution` below.
- **`probe_pokemon_ability`** (Phase 2b) — a Pokémon's *other* function is its Ability. This
  drive places the target Active, banks its **own-type** Energy each turn (fuel for
  energy-hungry Abilities), and activates the `ABILITY` option the moment the engine offers it
  — the option only appears when the Ability is *usable*, so its presence proves the
  precondition is met; the Ability's sub-decisions are resolved with the shared play resolver.
  This yields the same behavioral tags as trainers (Fan Rotom → `search`, Teal Mask Ogerpon ex
  → `draw`+`energy_accel`, Tatsugiri → `dig`). *Which* basics have an Ability comes from the
  engine (`CardData.skills`), not the stale `cards.json`. A mon's attack-record and
  ability-record are **unioned** (`_merge_into`), so a mon that searches *and* inflicts a
  condition gets both (e.g. `[search, poison]`).
  Passive Abilities (locks, free-retreat) never become an option → no tag; discard/Supporter-fed
  Abilities (Goldeen, Latios) go ungated to overrides, like precondition-gated trainers. Basic
  mons only.
- **`probe_evolution`** (Phase 3) — Stage 1/2 functions need the mon *in play*, so this drive
  builds the whole line (`evolution_chain` walks `evolvesFrom` names → `[Dreepy, Drakloak,
  Dragapult ex]`), places the Basic Active, **evolves the Active one step per turn**, banks the
  target's **costliest** attack's Energy, then activates the Ability (once) and fires that
  costliest attack. Costliest, not cheapest: marquee effects (spread, heavy status) sit on the
  expensive attack — Dragapult's *Phantom Dive* `[2,5]` spreads, its cheap *Jet Headbutt* `[0]`
  doesn't. The opponent gets a **basics-rich deck** (`_bench_deck`) so spread has surviving Bench
  targets and a KO'd Active is replaced (else the game ends before the counters land). The free
  `DAMAGE_COUNTER_ANY` placement is resolved so `spread` is recorded; the attack record is bounded
  to the attacking turn (`_attack_turn_logs`, the Ability captured separately before it).
  Yields `spread` (Dragapult, Sinistcha), evolved Special Conditions, and Ability `energy_accel`
  (Gardevoir/Hydreigon/Bellibolt class), `draw`, `dig`/`search` (Drakloak's *Recon Directive*).
- **`function_overrides.json`** *(as needed)* — hand-authored `{cardId: [tags]}` for what
  the probe can't reach; never clobbered by regeneration.

> **Note — stale `cards.json`:** the shipped `cards.json` predates the `dump_cards.py` enrichment,
> so it lacks `attacks`/`abilities`/`weakness`/`resistance`, and `dump_cards.py`'s `sys.path` still
> points at the old `slowpoke_0/`. The probes work around it (engine-sourced attack data), but it
> should be regenerated.

## Tag vocabulary

All tags are **behavioral** — structural facts (ex/Mega-ex, trainer type, ACE SPEC) are *not*
tagged; the runtime reads those off `CardData` (`ex`/`megaEx`/`cardType`/`aceSpec`) directly.

| Group | Tags | Source |
|---|---|---|
| Resource | `draw`, `search`, `dig`, `energy_accel`, `recycle` | probe |
| Disruption | `gust`, `hand_disruption`, `energy_denial` | probe |
| Board | `switch`, `heal`, `spread` | probe |
| Conditions | `poison`, `burn` (chip attrition), `sleep`, `paralyze` (lock out attack/retreat), `confuse` (attack deterrent) | probe |
| Defensive | `bench_guard` (protect the Bench from attack/Ability *effects* — Battle Cage) | override |
| Setup | `opener` (a non-Basic that may take the Active Spot from hand during setup — Explosiveness; keeps a no-Basic hand from being mulliganed away — Cinderace), `rare_candy` (put a Stage 2 from hand onto its root Basic, skipping the Stage 1) | override |
| Play-role | `stall` (a big-HP setup wall that *declines to attack* to buy tempo — Mega Kangaskhan ex, Dudunsparce, Meowth ex) | curated seed |

### Complete tag reference

The full **behavioral** vocabulary — name, what it's *for*, and how the label is assigned.
"Probe" = derived by playing the card in the engine and reading the resulting `Log`/`SelectContext`
(see *Why probe*); "override/curated" = hand-set in `function_overrides.json`. (Structural facts —
ex/Mega-ex, trainer type, ACE SPEC — are *not* here; the runtime reads them off `CardData`.)

| Tag | Group | Purpose (why it matters) | How it's labeled |
|---|---|---|---|
| `draw` | resource | Draws cards into hand — raw card advantage / engine fuel. | Probe: a `DRAW` log by the actor, or a "look at top N, take 1" (`LOOKING→HAND`). |
| `search` | resource | Tutors a *specific* card straight out of the deck — consistency. | Probe: a `MOVE_CARD` from `DECK` directly to `HAND`/`BENCH`/`ACTIVE`. |
| `dig` | resource | Looks at / reorders the top or bottom of the deck — selection & information. | Probe: a `MOVE_CARD` touching the `LOOKING` area. |
| `energy_accel` | resource | Attaches Energy beyond the manual once-per-turn drop — ramp / tempo. | Probe: an `ATTACH` log by the actor from a non-Tool card. |
| `recycle` | resource | Returns cards from the discard pile to hand/deck/play — resource recursion. | Probe: a `MOVE_CARD` from `DISCARD` into a hand/deck/play area. |
| `gust` | disruption | Drags the opponent's Active out to pull up a target (the "Boss's Orders" effect). | Probe: a `SWITCH` log on the *opponent's* side. |
| `hand_disruption` | disruption | Shuffles or discards the opponent's hand — resource denial. | Probe: the opponent's cards move `HAND→DECK`/`DISCARD` during the card's resolution. |
| `energy_denial` | disruption | Removes/discards the opponent's attached Energy — tempo denial. | Probe: the opponent's Energy moves `ENERGY→DISCARD`. |
| `switch` | board | Moves my *own* Active out — reposition / escape a bad matchup. | Probe: a `SWITCH` log on the *actor's* side. |
| `heal` | board | Removes damage from my Pokémon — longevity / tanking. | Probe: an `HP_CHANGE` (value > 0, not a damage counter) on my side, surfaced in the controlled-combat pass. |
| `spread` | board | Places damage counters across the opponent's Bench "in any way" — snipe / multi-KO setup. | Probe: a `DAMAGE_COUNTER_ANY` select context. |
| `poison` | condition | Poisoned — passive damage each turn (chip attrition). | Probe: a `POISONED` condition log it inflicted (not a recovery). |
| `burn` | condition | Burned — passive damage + a recovery coin flip (chip). | Probe: a `BURNED` condition log. |
| `sleep` | condition | Asleep — can't attack/retreat until a wake flip (lock). | Probe: an `ASLEEP` condition log. |
| `paralyze` | condition | Paralyzed — can't attack/retreat for one turn (hard lock). | Probe: a `PARALYZED` condition log. |
| `confuse` | condition | Confused — attacking risks self-damage on a coin flip (deterrent). | Probe: a `CONFUSED` condition log. |
| `bench_guard` | defensive | Protects benched Pokémon from the *effects* of attacks/Abilities (anti-spread/disruption — Battle Cage). | Override: passive/preventive, so not probe-observable, but readable from card text. |
| `opener` | setup | A non-Basic that may be placed in the Active Spot from hand during setup (Explosiveness — Cinderace) — so a hand with no Basic Pokémon is still keepable. The Pilot reads it to *keep* (not mulligan) a startable opening hand. | Override: a setup-phase placement ability, not probe-observable, but readable from card text (like `bench_guard`). |
| `stall` | play-role | A big-HP wall piloted *not to attack*, buying tempo to set up. | Curated seed (`function_overrides.json`): a usage pattern, not parseable — full coverage needs replay-usage data (future). |
| `team_rocket` | membership | **The one owner-NAME-family tag, and the one ruled exception to REQ-FUNC-0001** (Issue #374, developer-ruled). Marks the 52 Pokémon whose printed name carries the *"Team Rocket's"* prefix. Nine cards in the pool gate an effect on *"Team Rocket's Pokémon"* — 15 Team Rocket's Energy, 414 Articuno, 431 Mewtwo ex, 436 Orbeetle, 1154 Hypnotizer, 1216 Ariana, 1217 Archer, 1218 Giovanni, 1220 Proton. For a body already **in play** that test is already free (`CardStat.name` → `card_text.name_in_family`); what has no answer is the hidden-**deck** half (*"search your deck for up to 3 Basic Team Rocket's Pokémon"*), which needs an index over the POOL — the *"no build-time family index"* Issue #301 recorded, and why those clause sets are `covers: partial`. **Why it is not structural-and-therefore-excluded:** REQ-FUNC-0001 excludes structural facts *because the runtime reads them off `CardData`*; there is no `CardData` field for an owner family (the dump carries `stage`/`ex`/`megaEx`/`tera`/`aceSpec`/`evolvesFrom`/`energy`, and the 52 span 8 energy types), so the rationale does not reach it. Note `tool`/`item`/`supporter` are a **counter**-precedent, not a precedent — ADR-0006 removed those structural tags. **Inert today** (no consumer whitelist names it) and does not by itself promote any `partial` verdict; ledgered as authored-ahead-of-its-consumer. Beware a name collision that is not a functional one: `EnergyType.TEAM_ROCKET` (11) is the special *Energy card's* type, not a Pokémon trait. | Curated (`function_overrides.json`): derived from the printed name in `tools/meta_tracker/cards.json`, not probe-derived. |
| `discard_eot` | energy | An Energy that is **discarded at end of turn** (Ignition Energy) — worth attaching only if the holder attacks that same turn. The Pilot reads it (`dont-waste-discard-energy`) to avoid wasting it (benched target / can't-attack first turn / a reusable Basic is in hand). | Curated seed (`function_overrides.json`): energies aren't probed, but the discard clause is readable from card text. |
| `rare_candy` | setup | A card that puts a **Stage 2 from hand straight onto its root Basic, skipping the Stage 1** (*"Choose 1 of your Basic Pokémon in play. If you have a Stage 2 card in your hand that evolves from that Pokémon, put that card onto the Basic Pokémon to evolve it, skipping the Stage 1"* — Rare Candy, id 1079). Read in two places, which is why it is a tag at all: the Turn Planner's Rare Candy KO line (`_is_rare_candy`) asks it of a PLAY option, and the backward playability oracle (`common.playability`, ADR-0104) asks whether one is reachable in hand or deck at all — a missing Stage 1 does not prove a Stage 2 dead. Distinct from `rush_evolve`: that one is a TUTOR that also evolves; this fetches nothing and needs the Stage 2 already in hand. | Curated seed (`function_overrides.json`): the evolve-skip is readable from card text, not probe-derived. |
| `rush_evolve` | setup | A card that **evolves a Pokémon ahead of the normal schedule** — even the turn its pre-evolution was played (Salvatore: search a no-Ability Pokémon and evolve onto a matching pre-evo). High tempo: it brings the win-condition online a turn early. | Curated seed (`function_overrides.json`): the evolve-bypass isn't probe-derived, but is readable from card text. |
| `clutch_heal` | board | A heal that also **bounces the healed Pokémon's attached Energy back to hand** (Wally's Compassion) — a *defensive* save, not a value heal: it recovers both the Pokémon and its Energy from a Knock Out, but disarms it until re-powered. The Pilot reads it (`hold-clutch-heal`) to hold it until the Active is doomed, then play it first and re-power the same turn. | Curated seed (`function_overrides.json`): the energy-bounce clause is readable from card text, refining the probe's plain `heal`. |
| `bench_fill` | setup | A card that **fetches Basics straight onto your Bench** (Buddy-Buddy Poffin) — fast bench development *and* deck-thinning in one play. The Pilot reads it (`prefer-bench-fill-first`) to sequence it ahead of hand-refill tutors in a thin deck, so every later draw/search is higher quality. | Curated seed (`function_overrides.json`): the deck→bench placement is readable from card text (refines the probe's plain `search`, which only sees `DECK→HAND`). |
| `tutor_energy` | resource | A deck-search specifically for an **Energy card into hand** (Hilda, Energy Search, Energy Search Pro, Fighting Gong, Colress's Tenacity, Crispin, Larry's Skill, Ethan's Adventure, Firebreather) — the attachable Energy that the Turn Planner's *Supporter-enabled KO line* needs. The Planner reads it (`_supporter_ko_candidate`, ADR-0031) to play the tutor first, then retreat→attach→KO the same turn. **Deck-search only**: discard-pile energy retrieval is `recycle`, a top-N look (Bug Catching Set) is `dig`, and a Pokémon's energy-tutor *attack/ability* (Gimmighoul, Eevee, …) is out of scope — it isn't a Trainer play-event and would misfire the Planner. | Curated seed (`function_overrides.json`): refines the probe's plain `search`, which only sees the generic `DECK→HAND` move, not that the fetched card is an Energy. |

`search` is a *direct* deck tutor (`DECK→HAND`); a "look at top N, take 1" is `dig`+`draw`, not
`search`. `tutor_energy` refines `search` to a deck-search *for an Energy card into hand* — the
attachable fuel the Turn Planner's Supporter-enabled KO line needs; discard-pile energy retrieval
stays `recycle` and a top-N look stays `dig`, so neither carries it. `bench_guard` is a real
card-function — passive, so override-supplied for now, but text-derivable. **`stall` is a different kind of label: a *play-role*, not a card-function** — it
depends on *how a card is piloted* (turns alive, attacks declined, tempo bought), which isn't in
the text or a single-card probe. It ships as a **small curated seed** (the obvious meta walls);
real coverage needs a **replay-usage** signal (per-card turns-in-play / attack-rate / survival)
that the current pipeline doesn't capture — raw replays are parsed to decklists and discarded
(ADR-0002), so the meta DB has no per-turn actions. That's future replay-training (the Base Value
Model layer); until then, extend the `stall` seed in `function_overrides.json` by hand.

**The whole vocabulary is implemented** — every tag above is derived from a real probe
observation (no imagined rules):
- `search` (a *direct* deck→hand/play **tutor** — Ultra Ball), `draw` (a card drawn, *including*
  look-at-top-then-take — Drakloak's Recon Directive, a draw engine not a tutor), `dig` (deck
  top/bottom inspection), `switch` (own Active out), `gust` (opponent's Active forced),
  `energy_accel` (a non-Tool card attaching Energy) — the **stable** pass. The search/draw split
  is by log shape: `DECK→HAND` = tutor (`search`); `DECK→LOOKING→HAND` = look-and-take (`dig`+`draw`).
- `hand_disruption` (opponent's hand → deck/discard, Iono/Judge + *Astonish*/*Knock Off*
  attacks) — also the stable pass (opponent always has a hand).
- `heal` (my Pokémon's HP rises) — the **combat** pass (`_COMBAT_PASSES`).
- `recycle` (a card pulled back out of my discard, Night Stretcher) and `energy_denial`
  (an Energy knocked off the opponent, Crushing Hammer) — the **attrition** pass (`_KO_PASSES`).
- the **Special Conditions**, each its own purpose-specific tag — `poison`/`burn` (chip
  attrition), `sleep`/`paralyze` (lock out attack/retreat), `confuse` (deterrent) — and `spread`
  (Dragapult ex, Sinistcha, Flutter Mane; `DAMAGE_COUNTER_ANY`) — probing **attacks** (basics in
  Phase 2a, evolved attackers in Phase 3). (The old vague `status` was split per-condition.)
- Ability-driven `search`/`draw`/`dig`/`energy_accel` (the Gardevoir/Hydreigon class) — basics
  in Phase 2b (`probe_pokemon_ability`), Stage 1/2 in Phase 3 (`probe_evolution`).

`heal`, `recycle`, `energy_denial`, and `energy_accel` have **lower, stochastic coverage** — they
need a specific board (damaged / stocked discard / opponent Energy) that aligns in only ~1-in-N
games, so the builder runs several combat + attrition passes and **unions** them, and (since
[accumulation](#status) is monotonic) **coverage keeps climbing across re-runs** — counts here are
a floor, not a ceiling. Raising `_COMBAT_PASSES`/`_KO_PASSES` or just re-running trades time for
coverage. True stragglers (e.g. Enhanced Hammer, which needs *special* Energy the basic-only
opponent never attaches) are the job of `function_overrides.json`.

## Testing — verifying tags are *correct*

Three layers, because the probe is stochastic and the engine exposes no ground-truth labels:

1. **Unit (pure, fast)** — `classify_functions` rules against synthetic probe records
   (`tests/cards/test_card_functions.py`) and the pure probe helpers (`tests/cards/test_probe_cards.py`).
   Verifies "this log-pattern → this tag", not that any real card is right.
2. **Golden oracle (deterministic regression gate)** — `tests/cards/test_card_functions_oracle.py`
   asserts a handful of unambiguous cards keyed by *name* carry their tag in the *shipped*
   table (Ultra Ball→`search`, Dragapult ex→`spread`, Judge→`hand_disruption`, …). Catches
   end-to-end pipeline regressions; refresh it on a pool update.
3. **Text-consistency audit (independent oracle, all cards)** — `tools/audit_card_functions.py`
   + `meta_tracker/function_audit.py`. The tags come from probing, *never* from text, so the
   rules-text is an independent check: a behavioral tag with no supporting text cue is a suspect
   *false positive*; a strong text cue with no tag is a suspect *miss*. Heuristic (text is noisy
   — that's why we probe), so it's a **review report**, not a gate. Run:
   `python tools/audit_card_functions.py`.
4. **Meta-card double-verification (the cards that matter most)** — `tools/verify_meta_cards.py`.
   Same text cross-check, but **ranked by real usage** in the meta_tracker DB (Elite/High bands
   weighted, `meta_tracker/meta_usage.rank_card_usage`), so the most-played staples are vetted
   first. **Flag-only**: a prioritised review list; confirmed fixes go in `function_overrides.json`
   by hand. The motivating case — **Munkidori** ships as `confuse` (Mind Bend), but Adrena-Brain ("move damage
   counters from your Pokémon to your opponent's") is **heal + spread** (a counter-*move* the probe
   can't reach); the audit recognises the counter-move phrasing and flags it.

> **Audit-driven fixes (resolved):** the audit caught two real bugs, now fixed —
> (a) **`energy_accel` over-tagging** (false positives 37→0): the attack capture bled into a
> *later* turn whose re-energize `ATTACH` read as acceleration (the `ATTACH` log carries no
> source area, so movement/cost can't be told apart there). `_attack_turn_logs` now bounds the
> capture to the attacking turn (first `ATTACK` → next turn boundary); plus the stale artifacts
> were cleared by a `--fresh` rebuild. (b) **`search` recall gap**: the probe deck seeded only
> *high-HP* basics, so HP-capped fetches (Buddy-Buddy Poffin: "≤70 HP") and Supporter-fetches
> found no target — `build_probe_deck(search_fodder=True)` now adds frail basics + a Supporter on
> the **stable pass only** (no combat → can't disturb heal/attrition probing).
>
> **Still open (inherent):** most of the "missing" pile is reach/stochastic, not a bug — ~96
> Pokémon `search` effects sit on unreached lines/abilities; `energy_denial`/`recycle`/
> `hand_disruption` need board states that align ~1-in-N (accumulation + passes chip away);
> evolution probes only the costliest attack. The few remaining "unsupported" flags are audit
> *cue* gaps (a real tag whose text phrases it unusually — Drakloak's "look at top 2, put 1 in
> hand" is a real search), not wrong tags.

Lib-free unit/oracle/audit tests run without the engine; the audit *tool* reads engine text.

| ID | Requirement |
|---|---|
| REQ-FUNC-0001 | Structural facts (ex/Mega-ex, trainer subtype, ACE SPEC) are *not* tagged — the table is behavioral-only; the runtime reads them off `CardData`. **One ruled exception, `team_rocket` (Issue #374)**: the rule's own rationale is *the runtime reads them off `CardData`*, and every fact it names has a `CardData` field. An owner NAME family has none, so the exception is where the rationale stops applying rather than a hole in it. See the tag's row below. |
| REQ-FUNC-0002 | Behavioral tags from the engine probe record (draw, search, spread, …). |
| REQ-FUNC-0003 | Curated overrides union with derived tags; sparse input degrades to empty, never raises. |
| REQ-FUNC-0004 | Probe harness builds a legal 60-card deck featuring the target (startable, ≤4 copies, ACE SPEC=1). |
| REQ-FUNC-0005 | Probe helpers: locate the card's PLAY option; extract `{actor, logs, contexts}` that feeds the classifier. |
| REQ-FUNC-0006 | Build the shipped `{cardId: tags}` table from the pool + probes + overrides (untagged omitted). |
| REQ-FUNC-0007 | Probe a basic Pokémon's attack (matching-energy deck, place Active, energize, attack → the inflicted Special Condition). |
| REQ-FUNC-0008 | Locate the option that activates a target Pokémon's Ability (by area/index → in-play card id). |
| REQ-FUNC-0009 | Evolution probing: basic-first `evolution_chain`, a chain+energy deck, and locating the EVOLVE option (→ `spread`/evolved attacks & abilities). |
| REQ-FUNC-0010 | Attrition probing: build a frail/diverse-energy deck; detect a stocked discard (→ `recycle`/`energy_denial` via the opponent KO'ing my Active). |
| REQ-FUNC-0011 | Cross-run accumulation: `accumulate_tables` unions a run into the prior table — monotonic, a once-observed tag is never dropped (rebuild `--fresh` to reset). |
| REQ-FUNC-0012 | Text-consistency audit: `audit_card` flags a behavioral tag with no supporting text cue (false positive) and a strong text cue with no tag (miss). |
| REQ-FUNC-0013 | Golden oracle: named, deterministic cards carry their expected tag in the shipped table (end-to-end regression gate). |
| REQ-FUNC-0014 | Meta-card verification: rank cards by real usage (`rank_card_usage`, band-weighted) to prioritise the text-audit toward the staples that decide games. |
| REQ-FUNC-0015 | Triggered-Ability shape probe (Issue #305): build a deck whose triggers have real targets, and reduce a captured select to the shuffle-INVARIANT record a fixture can pin (`build_trigger_deck`, `select_shape`, `_strip_serials`). |

## Status

**Feature complete — every tag in the vocabulary is derived from a real probe and observed in
the shipped table.** (Build ~50s. **Behavioral-only**: structural-only cards — a vanilla ex, a
plain Item — are now omitted, so the table is smaller than the old structural-inclusive count.)

- Classifier + probe pure helpers fully unit-tested (`build_probe_deck` also
  engine-validated — every card category accepted by `battle_start`).
- **Drive-shell + three scenarios built** (`probe_card`): *stable*, *controlled-combat*
  (opponent chips a high-HP board, target held until damaged → `heal`), and *attrition*
  (opponent KOs a frail board, target held until my discard is stocked → `recycle`/
  `energy_denial`). Validated on real cards — Ultra Ball → `search`, Boss's Orders → `gust`,
  Switch → `switch`, Potion → `heal`, Judge → `hand_disruption`, Night Stretcher → `recycle`.
- **Phase 2a (Pokémon attacks) shipped** (`probe_pokemon`): probes basic Pokémon attacks → the
  **Special Conditions**, each its own tag (Munkidori→`confuse`, Heatran→`burn`, …). The record is
  bounded to the attacking turn (`_attack_turn_logs`) so neither the pre-attack energize (briefly
  mis-tagged ~500 Pokémon `energy_accel`) nor a later turn's re-energize leaks in.
- **Phase 2b (Pokémon abilities) shipped** (`probe_pokemon_ability`): activates basics'
  Abilities → `search`/`draw`/`dig`/`energy_accel` (Fan Rotom, Teal Mask Ogerpon ex, Tatsugiri).
  ~11/78 ability-basics fire; the rest are passive or need discard/Supporter state (→ overrides).
  Attack- and ability-records union per mon (a searcher that also inflicts a condition → `[search, poison]`).
- **Phase 3 (evolutions) shipped** (`probe_evolution`): evolves the line up and captures the
  Stage 1/2 Ability + costliest attack → unlocks `spread` (Dragapult ex, Sinistcha) and roughly
  doubles Special-Condition and `energy_accel` coverage (the Gardevoir/Hydreigon/Bellibolt class).
  435/461 evolutions yield a record; the opponent runs a basics-rich deck so spread has targets.
- **Builder shipped** (`tools/build_card_functions.py`): Trainers (stable + `_COMBAT_PASSES`
  combat + `_KO_PASSES` attrition passes), basic Pokémon attacks, basic abilities, **and**
  evolutions — all unioned (`_merge_into`) → `common/card_functions.json` (behavioral-tagged cards
  only, rising with accumulation — see below). Full build ~50s. `build_function_table` unit-tested.
- **Accumulative builds** (`accumulate_tables`, REQ-FUNC-0011): each run is one *stochastic*
  sample, so the builder **unions into the existing table** by default — a tag once observed is
  never dropped, and re-running only *improves* coverage of the rng-gated tags. Three runs took
  `recycle` 1→3, `heal` 7→11, `energy_accel` 28→**53** (a single run misses ~half the accel
  cards); nothing ever decreases. **Re-run the build (or loop it) to converge**; deterministic
  tags (draw/search/status/spread/…) reproduce identically. `--fresh` rebuilds from scratch
  (use after editing `classify_functions`, so corrected rules aren't shadowed by stale tags).
- **Curated overrides** (`function_overrides.json`): confirmed probe-unreachables surfaced by
  `verify_meta_cards.py` — tutors the probe deck can't satisfy (Telepath Psychic Energy, Hop's Bag,
  Thwackey, Dwebble, Ethan's Quilava, Salvatore, Team Rocket's Transceiver → `search`),
  `hand_disruption` (Xerosic's Machinations, Team Rocket's Archer), `recycle` (Sacred Ash, Kyogre,
  Levincia), `energy_denial` (Enhanced Hammer), `heal` (Wally's Compassion), Munkidori's
  counter-move `heal`+`spread`, plus the **override-only** tags `bench_guard` (Battle Cage),
  `opener` (Cinderace's Explosiveness — a startable non-Basic), `tutor_energy` (the nine
  deck-search-Energy-into-hand Trainers — a `search` refinement the probe can't derive, feeding the
  Turn Planner's Supporter-enabled KO line), and the curated `stall` seed
  (Mega Kangaskhan ex, Dudunsparce, Meowth ex). They union in at build
  time and are guarded by the golden oracle; extend the file as the meta-verification flags more.
- Optional future polish (not blocking): richer probing of conditional Abilities; regenerating
  the stale `cards.json`. The tag *vocabulary* itself is done.
