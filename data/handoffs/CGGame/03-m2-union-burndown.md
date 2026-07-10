# M2 — chain interpreter + 50-union burn-down ✅ DONE (2026-07-11)

**Result:** the full 50-card union is authored and trace-verified. **41/41 traces replay
clean** — 12 vanilla + 5 original agent-deck traces + 12 fresh v2 captures (all three
mirrors + all three crosses, seeds 5000-5501). **29 traces committed** to
`tests/fixtures/parity/` (12 vanilla + 17 agent-deck) — the CI parity gate now owns the
union. The ADR-0032 damage goldens are re-asserted on cgpy in
`tests/parity/test_damage_goldens.py` (Weakness ×2 → Jetting Blow 240 into Cinderace,
Nebula Beam 210 ignoring W/R, Resistance −30, flat-50 bench snipe, benched-Tera zero).
Full repo suite: 1486 passed.

## What got built (all trace-pinned; pins digested in docs/pyeng/determinism.md §8)

- **Trainers (all 26):** Pokégear (LOOKING zone flow), Salvatore (deck-evolve, two
  selects), Hilda (pick sequence), Crispin (TWO sequential max-1 picks — never max 2 —
  hand first, different-type attach second), Petrel, Poké Pad, Fighting Gong (anyOf
  filter; for Pokémon `energyType` IS the elemental type), Judge/Unfair Stamp/Harlequin
  (both-shuffle: actor moves+shuffle, opp moves+shuffle, THEN draws), Lillie's
  (draw 6 / 8 at exactly 6 prizes; front-to-back returns), Rosa's (min-1 discard-energy
  pick + single stage-2 target), Wally's (damaged-mega gate + heal + energy bounce),
  PPP / Black Belt's (silent turn_markers consumed in damage.py), Crushing Hammer
  (oppEnergyExists gate; options in GLOBAL ATTACH ORDER; remainEnergyCost=1), Switch
  (benchExists), Boss's, Night Stretcher, Ultra Ball, Poffin (bench-room maxCount
  clamp), Mega Signal.
- **Trainer discard timing** rewritten: limbo during own selects → silent discard at
  program completion (`chain._after_program`).
- **Tools:** Hero's Cape (+100, survives evolution), Air Balloon (retreat −2; retreat
  gating counts provided UNITS).
- **Stadiums:** play/replace flow (old → owner's discard), Risky Ruins bench trigger
  (2 counters, putDamageCounter=true), Gravity Mountain (−30 floating over stage-2
  hp/max in render + KO thresholds).
- **Special energy:** Ignition (provides C / CCC-on-evolution, EOT self-discard between
  TURN_END and TURN_START; option `count` = units).
- **Abilities:** MAIN ABILITY options (`{type:10, area, index}`, once-per-turn per mon +
  global-name limits), ACTIVATE asks for onEvolve/onBench (Hariyama, Meowth ex),
  Drakloak Recon Directive (look-2, rest to deck-BOTTOM toArea 14; deck-gated),
  Dudunsparce Run Away Draw (self-shuffle + immediate TO_ACTIVE promotion when Active),
  Munkidori Adrena-Brain (3 selects; forced COUNT auto-skips, no tac bump),
  Fezandipiti (koLastTurn), Lunatone Lunar Cycle (offered even with empty deck).
- **Attacks:** rider framework (riders run BEFORE the KO sweep; `_after_attack` sweeps
  active-then-bench, one prize claim per KO), Jetting Blow snipe, Cruel Arrow (any-1;
  W/R on active only), Mind Bend (condition rider machinery), Trading Places
  (self-switch), Aura Jab (discard-energy attach, per-energy bench targets), Cosmic Beam
  (requiresBenchNamed → silent nothing; ignore W/R), Accelerating Stab / Mega Brave
  (selfLockNextTurn markers), benched-Tera damage prevention (value-0 HP_CHANGE).
- **Trigger arbitration:** pending_triggers queue; 1 → auto-run, ≥2 → SKILL_ORDER select
  (stadium trigger listed before the mon's own), resolution in answer order.
- **Endgame:** NO_POKEMON outranks the prize win (result 1 reason 3 — NOT a draw);
  terminal select carries the last posed min/max; multi-prize claims per KO value.
- **Setup:** bench placements DEFERRED to the reveal stage (fp order); Explosiveness
  keep-hand logs `hasBasicPokemon: true`.

## Residual watchlist (unexercised by the 17 agent traces — the loop continues in M3/M4)

- **Attack programs never used in any capture:** Phantom Dive (154, the 6-counter bench
  spread — ctx 13/14 with remainDamageCounter still unbuilt), Turbo Flare (Cinderace
  energy search-attach), Wild Press recoil (Hariyama), Meowth ex Tuck Tail, Budew Itchy
  Pollen (ITEM-LOCK gating of opponent PLAY options), Irritated Outburst (prize-scaled
  damage — 184 def absent). First capture that uses one will diverge loudly; author then.
- **Crustle-class defender-side mods** (ex-damage immunity etc.): the ADR-0032 goldens
  "through Crustle" need the defender-mods seam — deferred to the pool-wide fan-out
  (M4); the achievable goldens are asserted now.
- Crispin's 2-pick attach stage and Aura Jab multi-energy loops extrapolate the pinned
  1-pick shapes (per-energy target selects) — differ-checked live but not yet exercised
  with >1 pick... Aura Jab 1-pick and Rosa's 2-pick ARE pinned.

## Method notes that carried the milestone

- Divergences ARE the specification; one at a time; capture more traces when a rule is
  ambiguous (they're free). Per-viewer log windows mean a play event appears in BOTH
  players' next frames — read `yourIndex` before attributing.
- mover = `(firstPlayer + turn - 1) % 2` for MAIN frames; god hands settle option
  identity questions instantly.
- The differ's god-sync (deck/prize multiset + exact hand) catches state drift EARLIER
  than obs compare — a "deck multiset mismatch" usually means a missed draw/return flow,
  not rng.
- Empirical beats text: Lillie's "draw 6" is draw-8-at-6-prizes; Crispin never poses
  max 2; supporter texts hide engine peeks (Wally's needs a DAMAGED mega).
