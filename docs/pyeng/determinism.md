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
- The fork **is deterministic**: two identical `search_begin` calls + identical steps produce
  identical draws/outcomes. (So cgpy's `state_from_obs` may apply its own deterministic shuffle;
  callers already must not trust order-dependent verdicts — planner doctrine.)

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
