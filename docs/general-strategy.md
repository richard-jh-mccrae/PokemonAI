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

Source: the positional hypotheses live in `src/common/strategy/baseline/baseline_*.py` (clustered by
decision-context — energy / snipe / promote / …) plus the three card-archetype doctrines in
`src/common/strategy/doctrines/`, assembled by `src/common/strategy/general_strategy.py`
([ADR-0025](adr/0025-baseline-rules-cluster-by-decision-context.md)); the Tactical Evaluator
in `common/pilot.py` handles combat. Each Hypothesis carries a plain-English `rationale`
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

### `open-the-accelerator` · weight 40 · status: assumed *(folded from mega_starmie `open-cinderace`, 2026-07-02)*
> At the Set-Up Active pick, prefer an `accel_source`-Role opener — acceleration on from turn one.

**Reads:** `SETUP_ACTIVE` select + the candidate's `accel_source` Role. Role-keyed: a deck opts in
by naming its accelerator. The only rule in the system at the Set-Up Active pick.

### `honor-preferred-start` · weight −30 · status: assumed *(folded from mega_starmie `prefer-going-second`, 2026-07-02)*
> At the coin toss, honor the deck's declared tempo: `params["preferred_start"]` = `"first" | "second"`.

**Reads:** `IS_FIRST` select + `Strategy.params` (Context passthrough); penalises the option that
**contradicts** the declaration (turbo → second: the player going first can't attack turn 1;
setup-heavy → first). Undeclared decks are untouched.

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

### `advance-the-accel-pieces` · weight 30 · status: assumed *(folded from mega_starmie `accel-into-main`, 2026-07-02)*
> During SETUP, PLAY or ATTACH the deck's own `accel_source`-Roled pieces (the burst Energy that IS
> the acceleration; the accelerator body).

**Reads:** the option card's `accel_source` **Role** (the deck's opt-in; `use-acceleration` is the
tag-keyed sibling). Co-fires additively with the other SETUP energy rules — tune against that
cluster, not alone. Also in `baseline_energy`, folded 2026-07-02:
**`conserve-discard-energy-prefer-basic`** (weight −40, from `conserve-ignition-prefer-water`) —
don't spend a `discard_eot` burst on the Active wincon when its cheap attack already KOs and a
reusable Basic is in hand; the KO-aware sibling of `prefer-reusable-over-burst` (−12), carve-outs in
`build-active-wincon` / `dont-waste-discard-energy` unchanged.

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

### `develop-the-accel-recipient` · weight 20 · status: assumed *(folded from mega_starmie `develop-turbo-flare-recipient`, 2026-07-02)*
> A bench-accelerator in the Active Spot accelerates onto NOTHING while the Bench holds no
> win-condition-Line recipient — developing one is the top setup priority.

**Reads:** `Board.accel_recipient_missing` (accel Active + no Line member benched) + a `PLAY` of a
Line pre-evolution or `bench_fill` card, Bench not full. The DEVELOP half of the pair whose FETCH
half is `fetch-base-before-stranded-payoff`.

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

### `energy-recover-credit` *(2026-07-02, mega_lucario deck-genie)*
An attack with an **energy-recover rider** ("Attach up to N Basic {X} Energy cards from your
discard pile…" — `AttackStat.recoverN/recoverEnergyType/recoverTarget`; pool-verified 6: Aura Jab,
Pick and Stick, Regi Charge ×3, Abundant Harvest) is credited `_ENERGY_RECOVER` (75) per Energy it
would ACTUALLY re-attach — `min(N, matching Basic fuel in my open discard)`, 0 when its target scope
has no recipient (bench-targeted with an empty Bench). Attacking IS the acceleration for these
decks, so a fueled Aura Jab (130 + load 3) outweighs a bare bigger chip (Mega Brave 270) while an
unfueled one doesn't. Inside the KO branch the credit is **sub-prize** (0.25/Energy, cap 0.75) —
"the cheaper KO that also develops" — never overriding a real prize difference.

### `boost-lethal` — the damage-boost OHKO-line model *(2026-07-03, mega_lucario deck-genie)*
The **breakpoint model** that was deferred here is now closed-form. Card facts: `CardStat.damageBoost/
damageBoostType/damageBoostVsEx` parse the Trainer families ("During this turn, attacks used by your
[{X}] Pokémon do N more damage to your opponent's Active [{ex}]" — Premium Power Pro; the attached-Tool
variant — Maximum Belt; pool-verified 4, the multi-mode Kieran fail-closed). Live state: a match-scoped
`TurnBoostTracker` (transients.py) accumulates this-turn boost PLAYs from the log stream; an attached
Tool is read off the holder. The damage oracle applies each gated boost **before W/R** (both directions
— the opponent's Power Pro play is as visible as mine), and `_boost_lethal_tactical` scores a PLAY/ATTACH
that CROSSES an affordable KO line as KO_SCORE-class (a Power-Pro-class Item may cross with k held
copies together; fires only when no affordable attack already KOs; skips a simultaneous-draw crossing).
The {ex} defender gate includes Mega ex — rulebook.txt:337.

### `recoil-doom` *(2026-07-03, mega_lucario deck-genie)*
A NON-KO attack whose unconditional recoil FLIPS my currently-safe Active into a free KO (outright
self-KO, or post-recoil HP inside `_active_doomed` re-asked at hp−recoil) is charged `_RECOIL_DOOM`
(100, combat-scale) — Wild Press 210 self-70 is a fine prize trade (the KO branch is never charged)
but not a chip that leaves an 80-HP body for nothing. An already-doomed Active is never charged
(chip big before it dies).

### Attack conditions — bench-partner gate *(2026-07-03, mega_lucario deck-genie)*
`AttackStat.requiresBench` ("If you don't have <X> on your Bench, this attack does nothing" —
pool-verified 2: Cosmic Beam needs Lunatone, Guardian Burst needs Uxie AND Azelf) + the live
`atk_bench_names` context zero the attack's **exact/min** damage when the condition is unmet on the
board — so scoring (not just the Lethal floor) sees the 0, and the phantom KO vs a low-HP Active dies.
The **max** bound keeps printed damage: Incoming is a worst case and the opponent can bench the
partner before attacking.

### `self-lock-cost` *(2026-07-02, mega_lucario deck-genie)*
An attack that locks itself (or all its user's attacks) for my next turn (`nextTurnSameAttackLock` /
`nextTurnSelfLock` — Mega Brave class) is charged `_LOCK_COST` (40) **only when a lock-free attack
was also affordable**: burning the nuke's cooldown on a non-KO turn wastes the turn it would KO. A
lone locking attack is never charged (chipping still beats passing — Riolu's Accelerating Stab).
Sub-prize (−0.3) inside the KO branch: among equal-prize KOs, keep the big attack off cooldown.

## Gust (Boss's Orders) — implemented (ADR-0022)

The doctrine for a **gust** — force the opponent to switch a benched Pokémon into their Active Spot
(Boss's Orders, card id 1182). Grilled 2026-06-29, recorded in
[ADR-0022](adr/0022-gust-is-closed-form-lethal-lookahead.md); it supersedes the earlier
`gust-the-damaged` sketch. A gust is **two** Pilot decisions — *whether to play it* (one Supporter
per turn; can't be played turn 1 on the play) and *which benched Pokémon to drag up*. Both are now
**shipped** test-first (`tests/strategy/test_gust.py`, plus an end-to-end check through the real mega_starmie
Pilot). All KO / lethal / prize value lives in the **Tactical layer** (structural, so the weight-tuner
never ingests a KO_SCORE-magnitude seed); only the two tunable positional weights below are
Hypotheses. **Refinements shipped 2026-06-29** (ADR-0022 §Refinements): the special-condition rescue
guard (all 5 conditions) + its offensive poison/burn baseline (#10), the Item-vs-Supporter economy
split (#12), Resistance in the KO oracle (simulator-verified flat **−30**), the simultaneous-double-KO
draw-guard (#2, half a), and the bench-snipe attack-value bonus (#14) — the last three on a new
`Attack.text` rider parser. **Still deferred:** the draw-*over-loss* valuation (#2 half b), the
four-mechanic split's coin-flip (Pokémon Catcher) / Basic-only-Confuse (Lisia's Appeal) branches
(v1 fires on any `gust` card, correct for mega_starmie which runs only Boss's), and Read-conditioned
gusting. (`prize-trade-target` below is a Tactical prize-preference over the *current* Active, not a
Hypothesis.)

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

### `gust-for-the-ko` · whether-to-play · seed: value-proportional · status: assumed (shipped)
> Play Boss's Orders only when it converts to a KO this turn that beats your best non-gust line —
> drag up a benched Pokémon you can KO (a prize you couldn't otherwise reach), especially a high-prize
> ex/Mega hiding behind a wall.

**Reads:** a `MAIN`/`PLAY` of a `gust`-tagged card (v1: id 1182) + `Board.gust_best_ko_prizes > 0`.
**Net-of-baseline:** the gust KO must beat every FREE KO of the current Active — (a) attacking it
(`active_ko_prizes`), (b) **poison/burn finishing it at the next Checkup** when its HP ≤ the fixed tick
(poison 10, burn 20 — `active_condition_ko_prizes`, #10), since gusting it off would only cure it, and
(c) the best alternative Supporter. **Scale:** **lethal** (gust prizes ≥ the opponent's remaining
prizes) scores in `KO_SCORE`-class and dominates any setup Supporter; a **non-lethal** gust-KO is a
tunable seed, **damped in `SETUP` while the win-condition isn't in play** — but only for a **Supporter**
gust (`cardType == SUPPORTER`, #12): a free **Item** gust (Pokémon Catcher) into a KO costs no Supporter
slot, so it fires even in setup. **Source:** F8/F9 — TCG Protectors (Prize Trade); JustInBasil (Gusting).

### `gust-target` · the `SWITCH(3)` target-select · comparator · status: assumed (shipped)
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

### `gust-for-the-stall` · defensive stall-gust · seed: low (below all tutors) · status: assumed (shipped)
> With no offense available, strand an energyless, high-retreat opponent benched Pokémon in the Active
> Spot to waste their turn.

**Fires only when** `Board.active_doomed` (their current Active will KO mine next turn) **and** no
gustable KO **and** no KO on the current Active **and** an **energyless, retreat ≥ 2** bench target
exists. Gusting their attacker to the bench removes the immediate threat; the stranded mon can't
attack, costing them a retreat to recover. Weighted below every tutor/draw (a last resort). **Never**
gust away an Active that carries **any** special condition (`Board.opp_active_condition_gift` —
poison/burn/sleep/paralyze/confuse): switching it to the bench **clears** the condition (rules.md §8),
so the stall would hand the opponent a free cure. **Mechanical caveat:** Boss's does not stop a normal retreat, so the stall only bites on a
genuinely high retreat cost — hence the `active_doomed` gate (you're losing anyway, so a bought turn
is upside). **Source:** F9 — JustInBasil (Gusting: disrupt the opponent's tempo).

### Defensive guards
- **Draw ≠ win (#2, half a — shipped):** a game-winning KO whose **unconditional recoil** also KOs my
  own Active and hands the opponent their LAST prize at the same Checkup is a **draw**, not a win
  ([rules.md](rules.md)) — `_tactical` must not score it `KO_SCORE`. Recoil is parsed from `Attack.text`
  (`parse_attack_recoil`, clean unconditional phrasing only; a "you may" recoil we'd decline → 0).
  *Deferred (half b):* valuing a forced draw **above a loss** when otherwise doomed (needs best-line
  reasoning the closed-form layer doesn't express).
- **Weakness/Resistance in every damage estimate (shipped):** a single helper `_wr_adjusted(attacker,
  defender, dmg)` applies the defender's Weakness (×2) **then** Resistance (−30) vs the attacker's type
  (rules.md §5), and **every** closed-form damage site routes through it — my attacks (`_tactical`,
  `_can_ko`) **and** incoming damage (`_incoming_active_damage`/`active_doomed`, `_gust_target_denial`),
  so Resistance is honoured in **both** directions (e.g. if MY Active resists the attacker's type, the
  agent doesn't wrongly think it's doomed). The amount is a per-card printed fact (e.g. Slowking
  "Fighting −30"), **not in our data export** (`CardData`/CSV carry resistance-*type* only; the type IS
  precompiled into `CardStat.resistance`) — but it is a **uniform −30** across this set, verified by
  probing **47** resistant Pokémon through the simulator (`tools/sim/probe_resistance.py`) + the printed
  cards. Moot for mega_starmie (Water/Fire attacks never meet the pool's Fighting/Grass resistances, and
  its Pokémon carry no resistance); matters for a Fighting deck (mega_lucario).
- **Self-fragility damper (deferred):** reduce a non-lethal gust's value when taking it leaves my Active
  doomed with **no benched win-condition ready**, scaled by my Active's prize value (don't expose the
  3-prizer for a 1-prize gust). A candidate to promote later.

**Signals (shipped, board-only v1):** `Board.my/opp_prizes_remaining`, `gust_best_ko_prizes`,
`active_ko_prizes`, `active_condition_ko_prizes`, `opp_active_condition_gift`, `stall_target_exists`;
`CardStat.retreatCost` / `cardType`; per-`attackId` `recoil` / `bench_snipe` maps off `Attack.text`.
**Deferred:** the four-mechanic split's coin-flip (Pokémon Catcher) / Basic-only-Confuse (Lisia's
Appeal) branches and Read-conditioned (engine-denial, proactive-vs-scouted-matchup) gusting.

## Fetch (Search) doctrine — designed; core shipped (ADR-0023)

The doctrine for a **fetch** — a card that presents a *choose-from-deck* select (the engine reveals
deck cards and you pick **which** to pull: Ultra Ball, Nest Ball, Mega Signal, Buddy-Buddy Poffin).
Spans the Function Tags `search` / `dig` / `bench_fill` / `tutor_*`; **raw draw** (Professor's
Research, Iono — no pick) is excluded. Grilled 2026-06-29, recorded in
[ADR-0023](adr/0023-fetch-is-a-shared-value-comparator.md). It is the deck-agnostic counterpart of
the **Gust** doctrine above, and **generalises the shipped rules already in the registry** (listed at
the end of this section) into one coherent comparator. Glossary: [Fetch](../src/common/CONTEXT.md).

**Doctrine — a fetch is three decisions over one shared value primitive.** Every fetch entails
*(A) whether to play it now*, *(B) what to grab*, and *(C) what to discard* (when the card has a
discard cost). All three read **one** closed-form primitive:

> **`fetch_value(card, board) = importance × still-lacking × available`**

so the play-reason, the grab, and the discard agree by construction (the same shared-oracle invariant
as [ADR-0022](adr/0022-gust-is-closed-form-lethal-lookahead.md)'s `gust_ko`).

- **importance** — *derived first, overridden sparsely.* **Tier 1 (free, every deck):** `Strategy.lines`
  membership (a Line pre-evo/payoff is a win-condition piece), Function Tags (`energy_accel`/`draw`/
  `search` ⇒ engine piece; `bench_fill` ⇒ board-builder), and `CardStat` + the forward-evolution index
  ([ADR-0020](adr/0020-forward-evolution-index-is-a-provider-primitive.md)) (is it a Basic? does its
  line reach an attacker?). **Tier 2 (sparse Role overlay):** the deck's `roles` refine intent where it
  diverges (`starter`, `accel_source`, a tech `disruption`), each Role mapping to a default fetch-weight
  the deck tunes **by id** (the existing `_weight` override path, [`Pilot._weight`](../src/common/pilot.py)).
  **Tier 3 (rare escape hatch):** a combo deck declares an explicit per-card fetch priority. No
  exhaustive per-card table — a zero-label deck still grabs sensibly off derived importance.
- **still-lacking** — the gap gate. **Need is per-category** ("a starter" = any Basic in play; "energy
  in play" = attached count below the online threshold), with the **win-condition as the per-Line
  exception** (specific). **"Have" = hand + in-play only** — a wincon in the *discard* or *prizes* is
  **not** had. **Satisfy-count default 1, overridable** (energy/basics want count) — this is what makes a
  redundant second copy fall to ~0 with no special guard.
- **available** — `Board.deck_definitely_empty_of(cid)` *filters* a dead candidate (the sound
  empty-deck oracle); `deck_definitely_has(cid)` gives positive confidence but **never forces** a fetch.
  Its **probabilistic complement** `deck_contains_probability(cid)` (ADR-0029) softly stands down a
  *likely* whiff the sound oracle can't see (a target probably sitting in the hidden prizes) — never
  replacing the sound gate. **Gap drives, availability only gates.**

**(B) What to grab** = argmax `fetch_value` over the revealed candidates. **Multi-pick is shipped**
(`_greedy_grab`, [pilot.py](../src/common/pilot.py)): a fetch-grab is a **single** `maxCount>1` select
(verified against the replay corpus — `TO_HAND` up to 3, `TO_BENCH` up to 2 in one select, *not*
sequential), so static top-N would double-grab a met need. Instead the Pilot picks **greedily with
gap-update**: take the best, rebuild a virtual board where the acquired card counts as *had*
(`wincon/support_in_play`, `my_bench`, `in_play_ids`, the next `fetch_priority` all close), re-score the
rest — so the second pick moves to the *next* unmet need. **Take-fewer:** with `minCount 0`, stop once
nothing remaining has positive grab value (don't bench a prize-liability body you don't need). Scoped to
`_GRAB_CONTEXTS` (`TO_HAND`/`TO_BENCH`/`SETUP_BENCH`); discard and every other context keep static top-N.

**(C) What to discard** reuses the **same primitive, inverted**: keep-value = `fetch_value` read as
"want it *in hand*", and a discard sheds the **lowest-keep-value** N. One function, two directions →
**you can never pitch a card you'd immediately fetch back**. Protected (never discarded): win-condition
Line pieces, the `discard_eot` Energy you'll spend this turn, anything needed this turn. The one term
discard adds that grab lacks is a deck-overridable **`good-in-discard`**: for a recursion / discard-fed
accelerator deck the *right* pitch is a card it *wants* in the bin, so the deck lowers that card's
effective keep-value.

**(A) Whether to play now** — *positive endorsement shipped (`fetch-when-it-fills-a-need`); cost-netting
deferred.* = `best_grab_value − cost_of_playing ≥ bar`, where `best_grab_value` is the
top candidate from the same comparator (≈ 0 when nothing's lacking or the deck whiffs → stand down) and
`cost_of_playing` splits by economy: a **free Item** fetch fires on any positive grab (deck-thinning
floors it); a **`cost_discard`** fetch subtracts the keep-value of the cards shed (delay it until the
discard is cheap); a **Supporter** fetch must beat the best alternative Supporter (the Item-vs-Supporter
split [ADR-0022](adr/0022-gust-is-closed-form-lethal-lookahead.md) already built). The **bar is
Plan-scaled** (low in `SETUP` where digging is king, higher in `RACE`/`CLOSE` where tempo is precious).
Sequencing stays structural in `_finish_turn_last` ([pilot.py](../src/common/pilot.py)) — free Item
digs first (tier 0), then the one-per-turn **Supporter** (tier 1, so a Pokégear may upgrade which one
you commit), then the blind Energy attach / `cost_discard` search (tier 2), then a `shuffle_hand`
Supporter (tier 3, attach before nuking the hand), then the turn-ender (tier 4).

**Deferred (designed-in seams, not built):** **(A) cost-netting + Plan-scaled bar** — the positive
endorsement (`fetch-when-it-fills-a-need`) is shipped, but subtracting the shed cards' keep-value from a
`cost_discard` fetch, the Supporter-economy opportunity cost, and a tuned per-Plan bar remain (the whiff /
redundant / `cost_discard`-sequencing rules already cover the common stand-down cases). **Read-conditioned
fetching** (grab a tech card *because* the Read names the matchup) → M2, via a Read-scaled bump on the
deck's `disruption`/tech Role (drops in without reshaping the comparator), mirroring the Gust doctrine's
Read deferral. **A prized win-condition raising the urgency to fetch its line-mate** → out of v1 (gap
drives; too clever for now).

### Shipped — the need-gated rungs (this build, status: testing)

The grab/discard comparator is **built test-first** (`tests/strategy/test_fetch_doctrine.py`, REQ-GEN-0035..0040)
as five need-gated Hypotheses + greedy multi-pick — the additive scored sum of these *is* `fetch_value`
(no monolithic function; the ADR-0008 idiom). New `Context`/`Board` gap signals back them
(`card_is_starter`/`_support`/`_redundant`/`_top_fetch_priority`, `support_in_play`, `in_play_ids`,
`top_fetch_priority_id`).

#### `fetch-when-it-fills-a-need` · weight 8 · status: testing  *(whether-to-play, decision A)*
> Play a fetch when its reachable deck set still holds a card you currently lack — `fetch_fills_a_need`,
the lookahead that scores the best grab with the **same** grab rungs (`_grab_value_of` over
`_search_deck_set − deck_empty_ids`) before the search reveals the deck. Gives a discard-COST fetch
(Ultra Ball) the positive driver `dig-before-commit` denies it; silent on a whiff / when nothing is
lacking. Weighted **below a free needed development** (`power-up-attacker` nets +10 — the ep82228640-fr7
shape), which also stands in for the deferred cost-netting. **Source:** ADR-0023; F12 — JustInBasil (Consistency).

#### `play-a-tutor-for-the-unfound-wincon` · weight 25 · status: assumed *(folded from mega_starmie `tutor-the-wincon`, 2026-07-02)*
> In SETUP, play a `tutor`-**Roled** card while the win-condition is unfound. Role-keyed (the deck
names its assembly Trainers); stands down on `wincon_in_hand` and on a provable whiff
(`search_targets_exhausted`). Co-fires with `fetch-when-it-fills-a-need` by design.

#### `dont-fetch-the-setup-only-opener` · weight −60 · status: assumed *(folded from mega_starmie `never-fetch-cinderace`, 2026-07-02)*
> At a search, never take an `opener`-tagged card that is **provably dead in hand**:
`card_stranded_evolution` — an evolution whose previous-stage chain (full depth,
`CardStat.evolvesFrom` names) is absent from the deck list (Cinderace with no Raboot). The
structural guard keeps an opener whose line IS in the deck fetchable.

#### `fetch-a-starter` · weight 12 · status: testing
> In SETUP with a thin Bench (`my_bench < 2`), grab a startable Basic (`card_is_starter`: hp > 0, no
`evolvesFrom`) — develop the board. The fallback grab beneath the win-condition rungs. **Source:** F12 —
JustInBasil (Consistency: a startable board).

#### `fetch-the-support` · weight 15 · status: testing
> With no engine Pokémon in play (`not board.support_in_play`), grab one (`card_is_support`: a Pokémon
with a `draw`/`energy_accel`/`search`/`dig` Ability). An online engine multiplies every later turn.
Gap-gated — silent once an engine is online. **Source:** F12 — JustInBasil (Consistency: engine first).

#### `fetch-deck-priority` · weight 40 · status: testing
> Tier-3 escape hatch: with an explicit `Strategy.fetch_priority`, grab the highest-priority candidate
the search reveals (`card_is_top_fetch_priority`, resolved cross-option in `Board.top_fetch_priority_id`).
Weighted above the derived rungs so the deck's stated order wins. Empty list → silent. **Source:** ADR-0023.

#### `prefer-good-in-discard` · weight 25 · status: testing
> Deck-override of the discard side: a card the deck marks Role `discard_fodder` (good in the bin for a
recursion / discard-fed deck) is the preferred pitch. Outranks `discard-the-redundant`. **Source:** ADR-0023.

#### `discard-the-redundant` · weight 20 · status: testing
> At a forced discard, shed a card whose need is met first — v1 signal: a hand copy of a Pokémon already
in play (`card_is_redundant`). The keep-value mirror of the grab side. **Source:** ADR-0023.

#### `discard-the-hand-duplicate` · weight 12 · status: assumed
> At a forced discard, pitch a card held in **2+ copies** (fungible Basic Energy excluded) before a
singleton — a keep-value floor: the duplicate is the cheapest thing to lose. Ranks below the redundant/
fodder rungs and above keeping a singleton disruptor. **Reads:** `_DISCARD` + `Context.card_is_hand_duplicate`
(`Board.hand_duplicate_ids`). **Source:** PR#9 critical batch C4 (2026-07-01).

### Shipped earlier — partial instances of the comparator (status: testing)

These seven Hypotheses pre-date this build; the doctrine unifies them (each is one importance rung or one
gap/availability gate of `fetch_value`), and the new rungs above slot in beside them.

#### `fetch-the-wincon` · weight 30 · status: testing
> Pull your win-condition / primary attacker first — the highest-value grab. **Reads:** `_TO_HAND` +
the `win_condition`/`primary_attacker` Role; the *gap gate* `not board.wincon_in_play` and the
energy-starve carve-out are the satisfy-gate in embryo. **Source:** F1 — JustInBasil (Consistency).

#### `prefer-wincon-line-piece` · weight 18 · status: testing
> Prefer a card that builds the win-condition **Line** (a pre-evolution on the path) over an off-line
opener/accelerator; at a PROMOTE only when the payoff is in hand. **Reads:** `card_is_line_preevo`.
Ranks below `fetch-the-wincon`. **Source:** F1 — JustInBasil (Consistency).

#### `fetch-base-before-stranded-payoff` · weight 20 · status: testing
> When the evolved payoff is NOT yet deployable — no Line pre-evolution in play **or hand**
(`board.wincon_base_deployable` False) — prefer fetching the **base** over the payoff. A fetched
payoff with no base to evolve from is a stranded dead card (and starves a bench-accelerator of a
recipient). The inverse of `prefer-payoff-over-preevo`: it lifts the pre-evolution ABOVE
`fetch-the-wincon` (+30) when the base is missing, but is **additive** (never zeroes the payoff), so
if only the payoff is on offer you still grab it. **Reads:** `card_is_line_preevo` +
`board.wincon_base_deployable`. Any evolution deck inherits it (origin: the mega_starmie Ultra-Ball
Mega-over-Staryu trap, 2026-06-30).

#### `fetch-energy-when-starved` · weight 25 · status: testing
> With no Energy on the Active and none in hand, take a reusable Basic Energy — the energy *need rung*
(satisfy-count = the online threshold). **Reads:** `board.my_active_energy == 0` & a reusable Energy
candidate. **Source:** F12 — JustInBasil (Deck Strategy: power an attacker).

#### `prefer-bench-fill-first` · weight 15 · status: testing
> Play a `bench_fill` (Poffin) first in a thin deck — develops the Bench and thins the deck (raising
later draw quality); the *bench need rung* + the greedy multi-pick. **Reads:** `bench_fill` tag &
`board.my_bench < BENCH_MAX`. Fires `SETUP`/`RACE`. **Source:** F12 — JustInBasil (Consistency).

#### `dont-search-an-empty-deck` · weight −60 · status: testing
> Stand down a search whose **every** target is provably gone (the *availability* gate). **Reads:**
`Context.search_targets_exhausted`, built on the **sound** `deck_definitely_empty_of` — a copy that
could sit in hidden prizes leaves it silent, so suppression is only on a CERTAIN whiff. **Source:**
F12 — JustInBasil (Consistency); the sound empty-deck oracle.

#### `dont-search-a-probable-whiff` · weight −25 · status: testing
> The **probabilistic** complement (ADR-0029): stand down a search whose best still-**reachable** target
is *probably* (not provably) prized — `Board.deck_contains_probability(cid)` below the 0.20 whiff
threshold, the card's unseen copies split hypergeometrically over the hidden prize slots
([deck_odds.py](../src/common/deck_odds.py)). **Reads:** `Context.search_targets_unlikely`. **Mutually
exclusive** with `search_targets_exhausted` (it needs a reachable target), and weighted *above* the
−60 sound guard: a guess only cancels a lone free-dig `dig-before-commit` (+20), never a real
lacking-need grab (you still dig hard for an unfound win-condition). The refuted `82524455-f6` shape (2
of 3 Staryu hideable in 6 prizes → P ≈ 0.98) stays above the bar, so it is **not** suppressed.
**Source:** ADR-0029; reviewed.json `82524455-f6` (the probabilistic read the sound oracle refused).

#### `dont-tutor-the-held-wincon` · weight −45 · status: testing
> Stand down a wincon-ONLY tutor (Mega Signal) when the wincon is already in hand — the *redundant
second copy* (satisfy-count met). **Reads:** `Context.search_redundant_wincon`. Stays silent for a
flexible Ultra Ball (its fetch-set isn't ⊆ the wincon). **Source:** F1 — JustInBasil (Consistency).

#### `keep-key-cards-at-discard` · weight −30 · status: testing
> At a discard select, rank engine pieces and win-conditions **last** — the keep-value floor (the
protected set). **Reads:** `_DISCARD` select + a `discard_eot`/win-condition card. The full
keep-value ranking and `good-in-discard` term generalise it. **Source:** F12 — JustInBasil
(Consistency: don't pitch your engine).

## Shuffle-Refresh doctrine — designed (ADR-0024)

The doctrine for a **Shuffle-Refresh** — a Supporter that **shuffles your whole hand into your deck
then draws** (Lillie's Determination, Judge, Harlequin, Lacey; Function Tag `shuffle_hand`). Almost
every deck runs one and the dominant misplay is **refreshing away
a working hand**. Grilled 2026-06-29, recorded in
[ADR-0024](adr/0024-shuffle-refresh-is-fetch-decision-a-over-keep-value.md). Glossary: **Hand Refresh
/ Shuffle-Refresh / Discard-Refresh** in [src/common/CONTEXT.md](../src/common/CONTEXT.md).

**A Shuffle-Refresh is not a fetch — it is the Fetch comparator's decision (A) only.** A fetch
presents a *choose-from-deck select* (three decisions: A play / B grab / C discard). A Shuffle-Refresh
presents **no select** — the shuffle and the draw are automatic — so the only choice is *whether to
play it*, and the gain is **stochastic** (N random cards), not a chosen card. It therefore **reuses**
the [Fetch comparator (ADR-0023)](adr/0023-fetch-is-a-shared-value-comparator.md) rather than restating
it, with **no grab and no discard** decision:

- **Cost = the hand you'd shuffle away**, valued by the Fetch **keep-value** (`fetch_value` read as
  "want it in hand"). Invariant inherited for free: **never shuffle away a hand you'd fetch back.**
- **Gain-exists = does the deck still hold a card I lack**, reusing the need model
  (`_fetch_fills_a_need` / `_grab_value_of`).
- **Supporter-slot economy and the Plan-scaled bar** are the same as Fetch (A); deck-knowledge stays an
  **availability gate, never a forcer**.

**"Dead hand" is a full play-scan, not a keep-value floor.** `Board.hand_is_dead` ⇔ **no non-refresh
card in hand yields any positive-scoring play this turn** (each hand card virtually scored through the
real hypothesis + closed-form tactical pipeline — the same virtual-scoring pattern as
`_fetch_fills_a_need`), **and** the deck still holds something I lack (`deck_holds_a_need`). Keep-value
≈ 0 alone is blind to a playable tutor / gust-for-KO / clutch heal and would refresh them away. The
full scan **is** "use your key cards first" proven structurally: every useful card outscores the
refresh, so the refresh is reached only when nothing else is worth doing. It never preempts an attack
(the scan is hand-only; attacks stay last-tier turn-enders in `_finish_turn_last`, after the tier-3
shuffle, so a dead-hand + lethal refreshes **then** KOs the same turn).

**v1 = Layer A (the dead-hand fallback) — shipped (ADR-0024), test-first (`tests/strategy/test_shuffle_refresh.py`).**

#### `refresh-when-hand-is-dead` · weight +8 · status: testing
> Play a Shuffle-Refresh **only when the hand is dead** — `shuffle_hand and board.hand_is_dead and
board.deck_holds_a_need`. Beats `End` (≈0), loses to any real play or rival Supporter (a dead hand
can't *contain* a better Supporter, so the slot economy is subsumed). Board-only, all Plans, fires
from turn 1. **`hand_is_dead`** scans the REAL menu: no non-refresh PLAY/EVOLVE/ATTACH scores positive
and no Pokémon PLAY is a (non-discouraged) development out — a bare bench-development isn't positively
scored in SETUP, so it counts structurally. The scan is gated behind a refresh actually being in hand,
so the common decision pays nothing.

Three explicit keep-value **floors** stand beside the comparator:
`hold-wincon-dont-shuffle` (−25) for the *wincon-in-hand-but-not-playable-this-turn* case,
`attach-before-hand-shuffle` (−60) for held energy + sequencing, and
`hold-wincon-with-base-dont-shuffle` (−15, PR#9 critical batch C5) which **strengthens the hold** when
the held wincon already has a Line pre-evolution in play (`wincon in hand` + `line_preevo_in_play`) — it
stacks additively with `hold-wincon-dont-shuffle` (net −40), because a wincon you can evolve into next
turn is worth even more not to shuffle away.

**Deferred (designed-in seams, not built):** **Layer B — stochastic pull-EV** (the "what can I expect
to pull" pillar): a hypergeometric over the deck-tracker's exact `deck_known_counts`, live only
**post-anchor**, refining "deck holds a need" into "P(the N-card draw fills it)" and unlocking the
conditional 8-card windows (Lillie's at exactly 6 prizes, Lacey at opp ≤ 3) — and it must account for
the shuffle **growing** the deck by the returned hand (a subtlety a fetch lacks). **`hand_disruption`
offensive axis** (Judge / Harlequin wreck the opponent's hand — a term scaling with the opponent's hand
size). **Deck-override** is mostly the existing `_weight` by-id path; no new seam.

## Tool doctrine — shipped (ADR-0028)

The doctrine for a **+HP Pokémon Tool** (Function Tag `tool` + a parsed `CardStat.hpBonus > 0`, e.g.
Hero's Cape +100, ACE SPEC, irreplaceable). It **reverses** the old reactive hold-for-breakpoint rule:
because a deck that shuffles its own hand (`shuffle_hand` Supporters) would otherwise bury the one-of ACE
SPEC back in the deck, the Cape is deployed **PROACTIVELY** onto the body that carries the game. The value
model is closed-form **survival-turns board-math** (a Doctrine trait, not a tunable weight), so it lives in
`doctrines/doctrine_tool.py` + a Pilot-side `ToolMixin`. Glossary: **Irreplaceable Tool / Survival Window**
in [src/common/CONTEXT.md](../src/common/CONTEXT.md).

**Survival-turns picker** (`_tool_deploy_slot`, `ToolMixin`): `survival_turns = ceil(hp / incoming)`;
the boost earns its slot when `survival_turns(hp + hpBonus) − survival_turns(hp) ≥ 1`. Incoming is the
**predicted next attacker** (`opp_best_attack_vs` — the hardest-hitting opponent body that can afford to
attack next turn, weakness-adjusted; benched bodies of mine take bench-snipe only). Priority: **(1)** the
win-condition body that gains the most turns (incl. the doomed→benched-successor redirect); **(2)** else the
proactive anti-shuffle default — park it on the Active win-condition so a hand-shuffle can't bury it, unless
that Active dies anyway; **(3)** else a non-win-condition **wall**, but only if the boost buys it a real
survival turn.

#### `deploy-hp-tool` · weight 40 · status: assumed
> Equip the +HP Tool onto the body the survival-turns picker chose (`attach_is_tool_deploy_target`). A
positive weight → tier-2 attach → sequenced **before** a tier-3 hand-shuffle Supporter (the root-cause fix:
a ≤0 equip drops to tier 4, below the shuffle). Positional, so a lethal KO still outranks it.

#### `hold-irreplaceable-tool-dont-shuffle` · weight −30 · status: assumed
> Don't play a `shuffle_hand` Supporter while holding an unattached **irreplaceable** Tool (ACE SPEC, not
recoverable from discard) with no good deploy target — the belt to `deploy-hp-tool`'s suspenders. **Reads:**
`Board.irreplaceable_tool_in_hand`.

#### `save-tool-for-the-attacker` · weight −15 *(tuned −12)* · status: testing
> Don't fritter a Tool onto an **off-role** body (a spent opener / accelerator). RE-SCOPED (ADR-0028): stands
**down** on the picker's chosen deploy target (`attach_is_tool_deploy_target`), so it fires only on a
picker-rejected off-line body — never on a wincon Line piece.

#### `protect-ace-spec-tool` · weight −10 *(tuned −7)* · status: testing
> Extra reluctance to spend an **ACE SPEC** Tool on an off-role body; stacks additively on
`save-tool-for-the-attacker`, reads the structural `aceSpec` fact, and is likewise re-scoped to stand down on
the picker's chosen target.

**Accepted limitation (branch 3, decision 5(d)).** When the wincon line is only benched (so branch 1 can't
select it — benched bodies take 0 non-snipe incoming), branch 3 deploys even the irreplaceable Cape onto a
present-survival **off-line wall** (e.g. a turn-1 Active Cinderace) it can never transfer off. Two corrections
land here (`82227388-7`, `82756664-9`) and are **accepted as-is** (`refuted`): proactive-deploy beats holding
into six self-shuffle Supporters, at the known cost of occasionally spending the ACE SPEC on a non-wincon body.
A "carrier retains the Cape's value" gate is a deferred refinement. See ADR-0028 post-build note.

## Designed, not yet seeded

| Rule | Needs | Source |
|---|---|---|
| `gust-the-damaged` — **superseded** by the full **Gust (Boss's Orders)** doctrine above (board-only, KO-gated; the already-damaged case is just one KO-able target) | — see ADR-0022 | F9 — JustInBasil (Gusting) |
| ~~Damage-boost "crosses an OHKO line" (e.g. Maximum Belt +50 vs ex)~~ — **BUILT 2026-07-03**: see `boost-lethal` in the Combat section (parsed card facts + `TurnBoostTracker` + oracle boosts + the crossing tactical) | — | F10 / F11 — JustInBasil (Damage) |

One **closed-form breakpoint** stays here; the +HP-Tool half graduated into its own doctrine:
- `Board.active_doomed` (incoming ≥ my Active's remaining HP), consumed by `dont-feed-the-doomed`.
- **`deploy-hp-tool-on-breakpoint` was REVERSED and removed** ([ADR-0028](adr/0028-tool-deploy-is-survival-turns-board-math.md)):
  the reactive "hold for an HP breakpoint" rule lost the one-of ACE SPEC to self-shuffle. It is now the
  **Tool doctrine** below — a proactive survival-turns deploy, not a breakpoint gate. See `## Tool doctrine`.

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
