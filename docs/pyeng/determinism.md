# Native-engine determinism pins (ADR-0050, M0)

Empirical facts about the native engine that the docs don't state and the API doesn't guarantee —
pinned by `tools/parity/pin_determinism.py` against the live DLL on 2026-07-10, and enforced by
`tests/parity/test_determinism_pins_engine.py` (skips without the native lib). cgpy implements
exactly these; any future engine update that changes one fails the pin test, not the parity corpus
first.

## 1. Serial assignment — positional, stable, pre-shuffle

- Card serials are assigned by **submitted deck position**, before the setup shuffle:
  seat 0's card at position `i` (0-based in the `BattleStart` list) gets **serial `3 + i`**;
  seat 1's gets **serial `63 + i`**. Stable across games (probe: 3 games, distinct-name decks).
- Serials **1 and 2 are never card serials** — evidently reserved (consistent with
  `AreaType.PLAYER` entities).
- The god-view (`visualize_data`) frame-0 deck listing is **already shuffled** (order ≠ submitted),
  while serials stick to the card — so the mapping `serial ↔ (seat, submitted position)` is exact
  and shuffle-independent.

## 2. `select.deck` reveals the true deck order

When a select carries a `deck` listing (searches: `ToHand`, `ToBench`, …), the listing order is
**identical to the god-view deck order** — the engine's internal array, not a canonicalized sort
(probe: `same-as-god-order=True`, not id- or serial-sorted). Consequences:

- CARD options with `area=DECK` use `index` = position **in that revealed listing**.
- The RevealOracle can bind the full remaining deck order at every search select.
- (Strategy note, outside engine scope: a search reveals exact deck order until the post-effect
  shuffle.)

## 3. Option ordering (MAIN)

Observed invariant: MAIN options are ordered by **the source card's hand index, ascending, with
option types interleaved** (a PLAY at hand index 3 comes after ATTACHes at 0-2). One ATTACH option
per (hand card, in-play target); target order within one hand index repeats the in-play order
(active first — to be confirmed by the differ). The tail is `ATTACK` (then) `RETREAT` (then) `END`.
ABILITY placement and EVOLVE interleaving follow the same hand-index rule (EVOLVE carries the hand
card's index) — first-divergence diffs in M1 will correct any residue here.

## 4. `search_begin` fork semantics

- The fork **does not preserve** the provided `your_deck` order — it reshuffles the predicted
  hidden zones itself (probe: draws did not follow a distinctive given order).
- The fork **is deterministic from a plain MAIN select** (`(select.type, select.context) ==
  (0, 0)`): two identical `search_begin` calls + identical steps produce identical
  draws/outcomes — 0/186 divergent (2026-07-12 probe). (So cgpy's `state_from_obs` may apply
  its own deterministic shuffle; callers already must not trust order-dependent verdicts —
  planner doctrine.)
- **Mid-effect forks are NOT reproducible**: begun from a pending effect select (TO_HAND,
  TO_BENCH, DISCARD, EVOLVES_*, ATTACH_*, …) the fork's reshuffle varies call-to-call —
  44/62 divergent in the same probe, and no mid-effect context is trustworthy (EVOLVES_FROM
  diverged 2/4; SWITCH/DISCARD_ENERGY were quiet only at n≤7). Fork from MAIN; never pin or
  replay through a mid-effect fork.

## 5. Setup & mulligan state machine

Observed sequence (ordered logs, mulligan game):

1. `f0`: **`IsFirst` is always asked of seat 0** (10/10 games), *before* any dealing.
   The answer sets `firstPlayer` (Yes → 0, No → 1).
2. Both players draw 7 (`Draw` ×7 each, seat 0 logged first).
3. Per player: `HasBasicPokemon` check logged. A basic-less player **auto-redraws** — hand→deck
   (`MoveCard` HAND→DECK ×7), `Shuffle`, `Draw` ×7 — repeated until a Basic appears; **each round
   is preceded by a `Mulligan` YesNo select** which is a confirm-gate, not a choice: a player
   *with* a Basic answering Yes does **not** redraw, a player *without* one redraws regardless.
   (Exact ask-seat conditions per round get pinned by trace replay in M1.)
4. `SetupActivePokemon` per player in `firstPlayer` order, except a still-mulliganing player's
   setup is **deferred** until their redraw succeeds. Placement logs `MoveCard` HAND→ACTIVE, then
   **prizes are dealt immediately after that player's placement**: `MoveCard` DECK→PRIZE ×6.
5. `SetupBenchPokemon` (optional multi-select) when the hand allows it.
6. **`DrawCount` mulligan compensation**: the non-mulliganing player is asked how many extra cards
   to draw, options `0..N` (N = opponent's mulligan rounds).
7. Turn 1 begins: `TurnEnd`/`TurnStart` + turn draw; `turn` increments per player-turn.

## 6. Deck-validation error codes (`BattleStart` → `StartData`)

Pinned by `tools/parity/snapshot_tables.py` probes (see `src/cgpy/defs/tables_meta.json`):

| Case | errorPlayer | errorType |
|---|---|---|
| legal deck | −1 | 0 |
| unknown card id | offender | **1** |
| >4 copies of one name | offender | **2** |
| no Basic Pokémon | offender | **3** |
| >1 ACE SPEC (distinct or duplicate) | offender | **4** |

(The 60-card length check lives in the Python shim `cg/game.py`, not the DLL.)

## 7. Encoding facts

- **Live observations** encode enums as **ints** (the `cg.api` IntEnums) — the agent-facing parity
  contract. **God-view frames** (`visualize_data`) encode enum values as **name-strings**
  ("MoveCard", "Number") with int areas inside log entries, and carry a `selected` field: the
  choice made in response to the **previous** frame's select (+1 offset, as in
  `tools/sim/record.py`).
- God-log type names are CamelCase over the log enum's words — `MoveCard`, `HpChange`,
  `HasBasicPokemon`, `TurnEnd` — and god logs always carry the FULL entry (a seat-1 `Draw`
  keeps its cardId/serial; no `*Reverse` variants). Probed from committed trace `god_logs`
  (ms_mirror_1000); `cgpy.game.visualize_data` renders the same.
- Logs are per-viewing-seat (`Draw` vs `DrawReverse`, `MoveCard` vs `MoveCardReverse`); each
  observation replays events since that seat's last select.

## 8. M2 effect-layer pins (trace-verified, 2026-07-11)

Each rule below was pinned by a first-divergence during the M2 union burn-down; the trace
frame references live as comments at the enforcement sites in `src/cgpy/`.

- **Trainer discard timing:** a played trainer sits OUTSIDE every zone during its own
  selects and lands in the discard silently (no MOVE_CARD log) at program completion.
- **Empty optional selects are never posed** — the engine auto-resolves them. The skipped
  ask still bumps `turnActionCount` for the deck-search family (Poffin/Pokégear/Crispin
  class, matching the setup empty-bench rule) but NOT for skipped attack riders or for
  forced single-value COUNT selects (Munkidori with exactly one counter).
- **Prizes: one select per KO'd Pokémon**, min=max=that Pokémon's prize value (a mega KO
  poses min 3; two 1-prize KOs pose two min-1 selects). The terminal degenerate select
  carries the LAST posed select's min/max, not 1/1.
- **Simultaneous triggers** (bench-entry class): one trigger auto-runs; two or more pose
  SKILL_ORDER (type 5, ctx 34, one `{type:15, cardId, serial}` option per trigger, the
  stadium's trigger listed before the entering Pokémon's own) and resolve in answer order.
- **Setup bench placements are deferred:** picks stay in hand through the opponent's bench
  ask and land at the reveal stage in first-player order, right before TURN_START. Keeping
  an Explosiveness hand logs `hasBasicPokemon: true` despite no real Basic.
- **Energy-discard selects** (Crushing Hammer / retreat class) list the target energies in
  GLOBAL ATTACH ORDER (oldest first) and carry `count` = provided units. Ignition Energy
  provides {C} ({C}{C}{C} on an Evolution Pokémon — retreat gating counts UNITS, and one
  Ignition pays multi-unit costs) and self-discards between TURN_END and TURN_START.
- **Hand-return orders:** Judge-class effects run BOTH players' returns+shuffles (actor
  first) before ANY draws; per-player returns run front-to-back in hand order. The
  mulligan return, KO discards, and self-shuffle-ins (Run Away Draw) return energies LIFO.
- **KO / leave-play sweeps:** the stack discards top-first — the top card logs its zone,
  lower stack cards log fromArea PRE_EVOLUTION (10); deck-BOTTOM inserts (Recon Directive)
  log toArea **14**, a wire value beyond the AreaType snapshot. Special conditions clear
  when the Active leaves play. A self-removed Active (Run Away Draw) poses an immediate
  TO_ACTIVE promotion (effect=null) and the turn continues.
- **Attack riders run before the KO sweep.** Benched Tera Pokémon take 0 attack damage
  (the HP_CHANGE still logs, value 0); a `requiresBenchNamed` miss (Cosmic Beam without
  Lunatone) deals no damage and logs nothing; `selfLockNextTurn` attacks (Accelerating
  Stab, Mega Brave) are omitted from MAIN on the owner's next turn.
- **Stadiums:** the play logs PLAY only (placement is silent); the replaced stadium moves
  to its OWNER's discard (full-visible MOVE, after the PLAY log). One stadium play per
  turn. Gravity Mountain's −30 floats over stored hp/max (render + KO thresholds); Risky
  Ruins queues a bench trigger (2 counters, `putDamageCounter: true`).
- **Abilities:** MAIN ABILITY options are `{type:10, area, index}` (no playerIndex), listed
  after the hand sweep in in-play order, data-driven opt-in, once per turn per Pokémon
  (+ a global per-name limit where the text says so); activation itself logs nothing.
  Triggered on-evolve/on-bench abilities pose an ACTIVATE YesNo (ctx 43, contextCard = the
  Pokémon). Recon Directive-class LOOK abilities are not offered with an empty deck;
  pure-draw abilities (Lunar Cycle) still are.

## 9. M4 pool-fan-out pins (micro-trace-verified, 2026-07-11)

Established by per-card micro-traces (`tools/parity/capture_card.py`, committed under
`tests/fixtures/parity/micro_*.trace.json.gz`) during the pool-wide ChainDef fan-out:

- **Menu gating of attacks.** The engine builds the ATTACK menu from cost AND effect
  preconditions: a 0-damage attack whose whole effect lacks its resource is UNOFFERED —
  Terminal Period without exactly-6 opposing counters (micro_mill2 f33), Abundant
  Harvest with an empty discard (micro_earthquake f6). Plain effect attacks are offered
  regardless (Phantom Dive / Tuck Tail appear in committed match traces without their
  machinery ever running). cgpy: attack defs carry `legal` conds evaluated at menu
  time; deferred attacks stay offered (`menuOffer: false` marks the gated ones) and
  raise UnsupportedCard on use.
- **Zero-value logging.** An attack WITH a damage component (printed damage, a scaler,
  or a per-heads formula) logs HP_CHANGE even when the computation lands on 0
  (micro_perheads f61: all-tails Ball Roll logs value 0); a component-less status attack
  logs nothing. Heal riders log HP_CHANGE even at full HP (value 0 — micro_healself f91).
- **"You may <effect>" attack riders** pose a YES_NO with ctx **ACTIVATE (43)** and
  `effect` = the attacker (micro_mill2 f49, Strafe) — and are SKIPPED silently when the
  optional effect has no live target (benchless Strafe poses nothing, micro_tucktail).
- **Phantom-Dive counter distribution:** one CARD select per counter, ctx
  **DAMAGE_COUNTER_ANY (14)** over the opponent's bench, `remainDamageCounter` counting
  down from the full count, effect = the attacker; the main-damage HP_CHANGE lands
  before the distribution selects (micro_phantomdive f16).
- **Tuck-Tail self-return:** the returning stack logs top-first (lower cards fromArea
  PRE_EVOLUTION), then energies LIFO, then tools, all to HAND full-visible; the owner
  promotes via TO_ACTIVE. A side emptied by a NON-KO departure loses by NO_POKEMON
  immediately (micro_tucktail_9521: benchless Tuck Tail = instant loss, reason 3).
- **"Discard all Energy from this Pokémon"** discards in ATTACH order — forward, unlike
  the KO sweep's LIFO (micro_discardall f13).
- **Recoil ("also does N damage to itself")** logs HP_CHANGE `putDamageCounter: false`
  on the attacker after the main damage (micro_recoil); the KO sweep covers both sides.
- **Checkup:** between TURN_END and TURN_START. Coin flips are attributed to the
  CONDITION OWNER (micro_collapse f17: the asleep wake-flip logs the sleeper's
  playerIndex, not the mover's), so replay binds coins per owner. Self-inflicted
  conditions ("This Pokémon is now Asleep") log the same shape as opponent-inflicted.
- **Item lock (Itchy Pollen):** "can't play Item cards" is menu-enforced — the locked
  side's PLAY options for ITEM cards are simply absent for one turn (ml_dx_2000 was
  green only because the locked side held no items; the lock is now modeled).
- **Crustle-class defense passives** ("Prevent all damage … by attacks from your
  opponent's Pokémon {ex}") zero the damage in the defender-mods stage, pierced only by
  an ignores-effects attack (Nebula Beam's 210 through Crustle — ADR-0032 golden,
  re-verified cross-engine by the audit seam 46/46).

### 9b. Burn-down batch pins (2026-07-11, micro-trace-verified)

- **Multi-condition inflict order = condition-ENUM order**, not text order: "Asleep and
  Poisoned" logs POISONED(17)→ASLEEP(19) (micro_onboard780a1128), "Burned and Confused"
  logs BURNED(18)→CONFUSED(21) (micro_onboard409a573).
- **Re-applying a condition the target already has is SILENT** — no log
  (micro_onboard780a1128 f51: second Pollen Bomb on a still-poisoned target logs
  ASLEEP only).
- **Leaving the Active Spot clears conditions WITH isRecover logs**, emitted after the
  SWITCH log in REVERSE enum order — CONFUSED before BURNED
  (micro_onboard780a1128 f28; order pinned micro_onboard409a573_9901 f41).
- **Checkup/confusion condition-damage HP_CHANGEs log `putDamageCounter: false`**
  (poison tick pinned micro_onboard780a1128 f13; burn/confusion by family analogy).
  `true` is reserved for counter-PLACEMENT effects (Risky Ruins, distribute-counters).
- **`energyAttached` resets at TURN_END**, observable False during a between-turns
  promotion select (micro_onboard780a1128 f54); the sibling flags stay
  reset-at-TURN_START until a trace pins them.
- **Imperative "up to N" selects pose min=1** — Energy Retrieval min=1 max=2
  (micro_onboard1118 f41), Abundant Harvest discard-attach min=1 (micro_onboard534
  f16); only a "You may …" wording drops to min 0 (Pokégear's pinned shape).
- **"You may draw cards until you have N" is skipped silently once hand ≥ N** (the
  may-ask targetless rule; micro_onboard125a159: Return with a full hand poses
  nothing) — `handBelow` legality gate.
- **Happy Switch (energy-move ability)**: energy pick ctx SWITCH_ENERGY_CARD(28) type
  ATTACHED_CARD over own BASIC energies in GLOBAL ATTACH order, then destination ctx
  ATTACH_FROM with `contextCard` = the energy and the source mon EXCLUDED; one
  MOVE_ATTACHED log with Before/After mons. **A moved energy keeps its original attach
  tick** and the holder's energy list stays tick-ordered (micro_happyswitch_9951 f47:
  moved-older lands before resident-newer).
- **Lucky-Attachment class** ("Attach a Basic Energy from your hand to 1 of your
  Pokémon", 0 damage): menu-gated on hand fuel; hand pick ctx ATTACH_TO (type CARD),
  then holder ctx ATTACH_FROM with contextCard; standard ATTACH log, fresh tick
  (micro_happyswitch_9950 f28-f31).
- **Dig-family protection** ("prevent all damage from and effects of attacks")
  rides the mon as a next-turn transient; an attack into it logs HP_CHANGE **0**
  (micro_onboard65a75_9902 f23) — same defender-mods stage and ignores-effects pierce
  seam as Crustle.
- **ACE SPEC deck rule**: one copy per deck (native battle_start errorType 4 on 4×;
  capture_card now builds 1×).

### 9c. Burn-down batches 2b–3 pins (2026-07-11)

- **Hand-pick randomness channel** (Psych Out family): the native poses NO select and
  NO reveal — one public MOVE_CARD HAND→DISCARD per pick, serial visible in BOTH
  windows (micro_psychout_9970 f21/f23). Replay binds picks from a per-victim FIFO of
  forced hand exits — MOVE_CARDs out of HAND while the TURN belongs to the victim's
  opponent (god stream when present; else the victim's OWN windows, per-seat
  turn-tracked). Every KNOWN-identity forced exit (Judge's opponent half) must drain
  the same FIFO via `hand_pick_expect` — multiset-asserted — or mixed games skew
  (`rng.py`; the M4 alignment hazard, now built).
- **Astonish-family shuffle rides the variant**: the plain shuffle-in shuffles only
  when a card actually MOVED (micro_onboard103a130_9901 f45, empty hand → no
  SHUFFLE); the per-heads flavor (Horrifying Bite) shuffles whenever picks were
  ATTEMPTED (micro_onboard753a1087_9901 f33: 1 heads, empty hand, SHUFFLE logged).
- **Hand Trim is menu-gated on `oppHandAbove`** — offered at opp hand 6, hidden at 5
  (micro_onboard1076a1554); the plain 1-card random discards are NOT gated (offered
  at opp hand 0, micro_onboard103a130_9901 f39).
- **Ascension's EVOLVES_TO deck pick carries `contextCard` = the evolving mon itself**
  (micro_psychout_9970 f37; effect = the same serial).
- **Count-scaled own-energy discard** (Steel Burst class): `all` variants pose
  nothing — matching energies leave in forward attach order BEFORE the HP_CHANGE
  (micro_cnt_steelburst_9980 f12); choose variants pose ONE ATTACHED_CARD select,
  ctx DISCARD_ENERGY_CARD(26), min 0, max = min(n, present), options in board order
  with per-holder `energyIndex` (micro_cnt_lavaburst_9980 f16 self-scope,
  micro_cnt_bellowing_9980 f17 own-wide; "You may" adds nothing — min is already 0).
  Zero candidates pose nothing (micro_cnt_flashspear_9980 f14). Hand flavor: ONE CARD
  select ctx DISCARD(8) min 0 over the filtered hand (micro_cnt_doubleeater_9980 f11).
- **Gust attacks** (Pull / Drag Off / Follow Me) reuse the Boss's-Orders shape: ctx
  SWITCH(3) CARD select over the defender's bench posed to the ATTACKER,
  effect=attacker, then a SWITCH log; Drag Off's rider hits the NEW Active flat,
  `putDamageCounter: false` (micro_cnt_dragoff_9980 f8/f9 — pin target had no
  weakness, so W/R remains formally open).
- **Melt Away** ("no Energy attached → no Retreat Cost") is a card passive on the
  RETREAT menu gate: offered on a bare cost-3 Magcargo (micro_cnt_lavaburst_9980
  f32); modeled as `retreat.freeIfNoEnergy` (Charmander 788 shares the text). The
  payability convention itself stands.
- **"Then, discard that Stadium."** rider = the replace-and-place discard shape (the
  stadium to its OWNER's discard, public STADIUM→DISCARD move); the discard-path
  branch is authored-but-unexercised (no stadium reached play in the pin traces).

### 9d. Burn-down batch 4 pins (2026-07-12)

- **Reveal-hand family** ("Your opponent reveals their hand."): the whole hand
  round-trips through LOOKING with no net state change — per card HAND→LOOKING
  rendered MOVE_CARD_REVERSE **to the hand's OWNER** but visible-with-ids to the
  attacker, then LOOKING→HAND visible both ways, both directions in hand order
  (rvl73/297/786_9000). The in-moves are opp-turn hand exits → they FEED the
  hand-pick FIFO; every reveal op drains itself via `hand_pick_expect`. Choose
  variants park the hand in LOOKING (victim handCount 0, looking_owner = attacker)
  and pose a CARD select over area 12 — ctx DISCARD for "you discard" (rvl995 f13),
  ctx TO_DECK_BOTTOM for bottom-of-deck (rvl401 f13; the exit logs pseudo
  `toArea: 14`); the chosen exit logs FIRST, the rest return in original order.
  Crushing Pulse returns EVERYTHING then discards Items+Tools HAND→DISCARD in hand
  order, no HP log (rvlitems284). Scaled variants (per-Trainer / per-Energy) log
  HP_CHANGE after the moves, even at 0 matches (rvl800 f12 value 0; rvl1230 −640);
  flat-damage variants log HP before the reveal. The plain and discard-all scripts
  menu-gate on a nonempty opponent hand; the choose script does NOT (rvl995_9001
  f53 offered at oppHand 0).
- **Search-straggler shapes**: unrevealed to-hand searches ("a card", "up to N
  cards", benched-count caps) render MOVE_CARD_REVERSE to the opponent
  (sg1093/sg1/sg33); "a card" prints pose min 1 (sg1093 f14); "You may search" is a
  real ctx ACTIVATE YES_NO ask before the pick (sg33 f18). Search-attach
  distributions: ctx ATTACH_TO multi-pick over the listing, then ctx ATTACH_FROM
  placement — per picked card with contextCard = that energy for "in any way you
  like" (sg965 f63; two sequential picks sgc87_9302 f12-f13), ONE cc-less select
  for "to 1 of your …" (sg328 f15 keeps the deck listing, sg242 f16 drops it —
  per-script quirk), Jolting Charge's two typed buckets pose SEQUENTIALLY (an
  empty bucket auto-skips: sg208 poses max 2, never 4). Picked cards with NO legal
  target stay in the deck silently (sg1463 empty bench; sg321 no Tera in play —
  Terapagos itself is NOT tera-flagged). Distinct-types picks cap max at the
  distinct type count among matches (sg321_9001 f9: max 1 over 12 same-type).
  Per-bench loops pose one pick per benched mon in bench order with contextCard =
  that mon (attach sg1078 f37; evolve ctx EVOLVES_TO sg740 f48-f49), one SHUFFLE
  after the loop. Menu gates: benchExists for benched-count/benched-target/
  per-bench scripts (sg1_9000 f9 / sg242 f7 / sg1078 f10); deckNotEmpty for
  Kaleidowaltz (trc_9001 f223). An EMPTY deck logs no SHUFFLE (trc_9000 f279).
- **Future/Ancient family**: no native table carries the tag — the engine provably
  filters by it (sgc87_9300 f51: fodder excluded from Peak Acceleration's targets,
  Miraidons kept). cgpy seeds explicit id lists from the official CSV's Category
  column (CSV Card ID == engine cardId, verified).
- **Fighting Roar / Multiplying Cocoon** (ability-tail rode-alongs): Luxio's
  passive waives BOTH evolve gates while the opponent's Active is a Pokémon {ex} —
  megaEx qualifies (rvl1371_9000 f8: Luxray ex offered onto a this-turn Luxio vs
  Mega Latias ex); Silcoon's onEvolve ask → ctx TO_BENCH min0 max1 deck pick
  (rvl1230_9000 f7-f9).
- **Coin composites**: effect-KOs ("… is Knocked Out") log NO HP_CHANGE — the mon's
  stack discards directly and the normal claims/prize flow runs (cn259 f17,
  cn364_9001 f18); choose-and-KO poses ctx DISCARD over the matching opponent mons
  (cn259 f16). When BOTH sides die in one attack, the CREDITED side's deaths sweep
  and claim FIRST (cn364_9001: the recoil corpse discards before the effect-KO'd
  defender; the opponent's 1-prize pick poses before the attacker's 3).
  Opponent-owned flips log COIN with playerIndex = the victim (cn607: Bench
  Manipulation; damage per TAILS still logs HP 0 on a zero). Bemusing Aroma's
  heads inflicts POISON then PARALYZE in that log order (cn686 f14). Miraculous
  Paint's heads poses ctx AFFECT_SPECIAL_CONDITION, type SPECIAL_CONDITION, all
  five conditions in enum order (cn1003_9701 f15). Mystical Return's heads poses
  ctx TO_DECK over the opponent bench and shuffles the mon + attachments into
  their deck with one SHUFFLE (cn173_9000 f10-f11); the benched flavor menu-gates
  on oppBenchExists (f13). Kaleidowaltz makes ONE combined pick with max =
  2×heads (zero heads still shuffles — cn1453_9000 f19); Gormandizer's zero-heads
  does NOTHING, not even a shuffle (cn1547_9000 f8); All-You-Can-Grab picks to
  hand UNREVEALED with max = heads (cn1013). Magical Leaf's pre-coin outcome
  gates its rider heal (pre→rider vars threading). Sand Attack arms a
  defender-side attack-gate transient (the fire path — the gated mover flips,
  tails = the attack does nothing — is authored but unexercised in the pins).
- **Rare Candy**: PLAY is menu-gated on a legal (in-play Basic that did not enter
  this turn, hand Stage 2 matching through the name chain) pair — never offered
  without one (trc_9000: 0 offers all game); the play poses ctx EVOLVE, type
  EVOLVE, options in the MAIN-menu evolve encoding (hand index + in-play target),
  and resolves as one EVOLVE log skipping the Stage 1 (trcx_9100 f13-f14).
- **Hand Trimmer**: both players trim to 5, opponent first, each with ONE ctx
  DISCARD pick over their whole hand, min = max = hand−5 (trh_9000 f105: min2
  max2; f68: min1 max1), moves public both ways; the opponent's chosen exits
  drain the hand-pick FIFO. Menu-gated unless SOMEONE holds >5 (f75).
- **Levincia** (the stadium-ability machinery): MAIN option {type ABILITY,
  area 7, index 0} placed after the mon abilities, once per player-turn,
  legal-gated on discard targets; activation poses ctx TO_HAND over the discard
  (min 1, max = min(2, targets)), DISC→HAND moves visible both ways
  (lev_9000-9003).
- **God-free listing reconciliation**: a revealed deck listing that contradicts
  provisionally-dealt prize identities swaps the differences pairwise through the
  prize row (the `prize_take` rule applied at listing time), re-points a pending
  select's listing snapshot and remaps + resorts its deck-indexed options
  (match-replay fixture: 4/60 → 34/60 green; the next divergence names card 269's
  ability).

### 9e. Ability-tail batch pins (2026-07-12, kaggle-ladder-verified)

- **Electric Streamer** (Iono's Bellibolt ex 269 — the first REPEATABLE ability):
  MAIN option {type ABILITY, area, index} per in-play Bellibolt, re-offered after
  each use — 3 activations in one turn (estream_9000 t85); menu gate = the hand
  holds a Basic {L} (perfect biconditional over 63 MAIN frames; match-replay
  f34-f38: gated off the moment the last L basic leaves the hand). Activation =
  the Chansey hand-attach shape (ctx ATTACH_TO hand pick, then ctx ATTACH_FROM
  holder) EXCEPT the holder select carries NO contextCard (estream_9000 f63 vs
  the pinned Chansey energy echo) and targets filter to the Iono's name family —
  Latias/Zygarde unlisted (f113), Voltorb/Tadbulb/Wattrel/Kilowattrel listed
  (match-replay f37). Def keys: `repeatable`, `targetFilter`,
  `targetContextCard: false`.
- **Flashing Draw** (Iono's Kilowattrel 271): once-per-turn (a used mon's option
  vanishes for the turn — flashdraw_9002); menu gate = an L basic attached to
  THIS mon AND hand < 6 (139 hand≥6 frames all unoffered; deck-empty gating
  UNPINNED — authored without a deck gate on the Lunar-Cycle precedent). Cost =
  ONE attached L basic: ctx DISCARD_ENERGY_CARD, type ATTACHED_CARD, min1 max1,
  ENERGY_CARD options on the holder (bench holders keep their area/index —
  flashdraw_9001 f162; six candidates energyIndex-ascending — 9002 f77); then a
  silent draw-to-6. `xDiscardEnergyCountScaled` grew `scope: "holder"` +
  `min` for this.
- **Dusk Ball** (1102): the Pokégear op with `fromBottom` — takes deck[:7]
  BOTTOM-FIRST (moves == god deck[:7] in order, duskball_9000 f6), ctx TO_HAND
  min0 max1 over Pokémon matches only (9001 f113 two options; empty choice []
  declines), pick exits LOOKING→HAND revealed, rest back + shuffle.
- **Carmine** (1192): `allowedFirstTurn` on a SUPPORTER def waives the
  first-player-T1 supporter ban (carmine_9000 f4 / 9002 f5: PLAY offered and
  taken at t1); body = silent discard-hand-draw-5 (no effect-1192 select in any
  capture).
- **No-target distribute bump**: `xDeckEnergyAttachDistribute` picks with NO
  legal placement stay in the deck, but the unposable placement asks still bump
  turnActionCount — one per remaining card (anyWay; kaggle ep-82228017 f18 tac +3
  for 3 energies on an empty bench), one per batch (oneTarget, by the family
  convention). The sg1463 "stays silently" pin is compatible: its attack ends the
  turn before tac ever renders again.

## 10. Cross-engine audit + god-free replay (M4)

- The ADR-0032 measurement harness (`tools/sim/audit_attacks.py`) runs unchanged on
  cgpy via `CG_ENGINE=py` (the alias seam); `tools/parity/diff_audit_engines.py`
  compares record-for-record with zero tolerance (coin attacks compare on the
  deterministic min/max fork rows). Sample gate 2026-07-11: 46/46 equal; burn-down
  batch: all 69 newly-live attacks equal. Rows whose incidental staging differs
  (defenderBench/attackerEnergies/myHandSize/defenderHp — each engine plays its own
  chaos game to the attack) are skipped as `staging-mismatch`, the coin-luck rule's
  sibling: own-board-sensitive scalers (Round / Sweet Circle class) measure
  legitimately different values there; micro-trace replay is that family's exact
  verifier (707/708/1114/1386 all pinned).
  Nightly full-pool run (manual, needs the DLL for the native half):

      python tools/sim/audit_attacks.py --all --out reports/attack_audit/native_all.json
      CG_ENGINE=py python tools/sim/audit_attacks.py --all --out reports/attack_audit/cgpy_all.json
      python tools/parity/diff_audit_engines.py reports/attack_audit/native_all.json reports/attack_audit/cgpy_all.json

- cabt replays (`tools/parity/from_cabt.py`) convert to GOD-FREE parity traces: draws
  and coins bind from the mover's own log windows, prize identities bind AT TAKE TIME
  (the owner's PRIZE→HAND move carries the serial; provisional deal identities swap
  multiset-exactly), and a revealed `select.deck` listing's order is adopted
  (multiset-checked) — the reveal-oracle path. Kaggle +1 offset: an agent's action at
  step k+1 answers its observation at step k; step-1 actions are the deck submissions.
- Reveal-oracle channels beyond the deal (2026-07-12, all multiset-preserving swaps
  through the provisional prize row): a recorded DRAW whose serial sits provisionally
  in the prize row swaps with the would-have-drawn deck top (`draw_bind`'s prize
  kwarg); a NEXT-frame `select.deck` listing is adopted BEFORE the step poses the
  search, so option SETS filter over the true deck — a post-hoc index remap cannot
  fix a wrong set (kaggle 83692318 f6: Poké Pad offered supporters; skipped when the
  CURRENT select is itself deck-indexed); NEXT-frame DECK→LOOKING move logs pre-feed
  `rng.look_feed`, consumed by `look_bind` in recorded order whichever deck end the
  op reads (Pokégear top / Dusk Ball bottom), cleared after one step.
- The kaggle-episode ladder: every `data/replays/*/episode-*-replay.json` under the
  MAIN checkout converts and replays; the first divergence per episode, attributed
  back to the option it misses (ability slot → board mon, play/attach → hand card,
  attackId → attack), is the ranked real-game burn-down queue. 2026-07-12 state:
  **123/414 episodes fully green** (was 19 before this batch); top of the queue:
  Full Metal Lab 1244 / Battle Cage 1264 (stadiums), Dawn 1231 / Brock's Scouting
  1210 (supporters), Telepath Psychic Energy 19 (special energy), Lucky Helmet 1156
  (tool). Gate: `tests/parity/test_cabt_replays.py` pins the two committed episodes
  (arena 60/60, kaggle-81364540 43/43) end-to-end.
