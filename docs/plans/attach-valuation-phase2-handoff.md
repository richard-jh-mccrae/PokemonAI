# Energy-attach valuation — Phase 2 handoff (staged swaps)

Phase 1 (the grill + the shadow oracle) is DONE and committed on
`claude/valuation-systems-coverage-09t75e`. This handoff hands off Phase 2 — folding the shadow into
the live deciders. Read it with the grill spec (`attach-valuation-grill-spec.md`, whose "Grill
rulings — 2026-07-21" ledger + build-status table are the design of record) and the coverage review
(`valuation-systems-coverage-review.md`, the standing cautions).

## Where Phase 1 landed (what "done" means)

**The oracle is a SHADOW — it DECIDES NOTHING.** `Pilot._attach_shadow` is attached to the `Decision`
and emitted to telemetry (`telemetry.to_record` → `attach_shadow`), but `decide()` / `plan_turn` are
untouched: the 22 rungs in `src/common/strategy/baseline/baseline_energy.py` still make every live
attach call. That is why the full suite (3108 passed) held unchanged at every increment.

- **Entry:** `Pilot._attach_shadow(obs, select, board, options, traces, chosen)` — sparse (None off a
  real attach choice or mid-sim `self._planning`), wired onto BOTH `Decision` returns (the planned-
  turn path ~pilot.py:1225 and the fall-through ~pilot.py:1271). Fires when ≥2 options are `_ATTACH`
  (or `_ATTACH_FROM` `_CARD` recipients).
- **Per-option pricing:** `Pilot._attach_value(...)` → a row, or None to ABSTAIN (a Pokémon Tool —
  Ruling 3). `eq_pick` ranks rows by `(marginal, line_value, not type_wasted, −resource_cost)`;
  `eq_pick = None` when nothing buys durable progress (all-Tool menu / pure waste).
- **Row schema** (the working, per ADR-0019 "full working"): `marginal` (= `max(this_turn, build,
  accel_value)`, gated 0 for a non-attacking role / evaporating burst / overkill), `this_turn`,
  `build`, `accel_value`, `doomed`, `line_value`, `resource_cost`, `type_wasted`, `burst`,
  `evaporates`. Record: `{eq, eq_pick, abstained, picks, agree}`.
- **Helpers added:** `_attach_readiness` (2-point affordable damage), `_attach_progress` (convex
  `(min(e,M)/M)²·maxDamage`), `_opp_body_hps` (overkill cap), `_accel_attack_id` / `_accel_routed_value`
  (Ruling 4), `_partner_absent` (Ruling 6, reads `Strategy.partners`).
- **New deck-layer data:** `Strategy.partners: dict` (cardId → [partner cardIds]); mega_lucario
  declares `{Solrock: [Lunatone], Lunatone: [Solrock]}`.
- **Tests:** `tests/strategy/test_attach_shadow.py` (32 passed, 0 xfailed) — synthetic term-pins +
  mid-sim/telemetry guards + 11 corpus-replay frames.

All eight ruled behaviors are live: 3 gate, 5b role/type-fit, over-attach/concentrate, 1 carrier-
survival, 2a arm-doomed, 2b overkill cap, 4 accel-routing, 6 partner-conditional. See the build-status
table in the grill spec for the one-line mechanism of each.

## Phase 2 — the goal

Fold the shadow into the live deciders: for each rung-family in `baseline_energy.py` that the oracle
SHADOWS, replace/re-point the tuned rung magnitudes with the oracle's one-currency call, per the
seam-D migration pattern (the discard convergence) and the shadow-equations ruling. The oracle
REPLACES the rungs it shadowed (the currency-zone rule) — never co-exists as a second positive term.

### The rung → term fold map (which rungs each oracle term subsumes)

From the grill spec's "hypothesis" section, verified against the shipped `baseline_energy.py`:

| Oracle term | Rungs it subsumes | Rungs that SURVIVE (structure, not value) |
|---|---|---|
| `marginal` (build/this_turn/concentrate) | `concentrate-energy-on-wincon`, `build-active-wincon`, `power-up-attacker`, `spread-attach-to-the-needy`, `concentrate-accel-on-one-line-body` | `attach-energy-last` (sequencing tier), `use-acceleration` (PLAY-side source selection) |
| doomed sign (1 / 2a) | `dont-feed-the-doomed`, `arm-the-doomed-active`, `dont-overbuild-the-doomed-wincon` | `feed-the-line-for-disruptor-lock` (a lock maneuver, ADR-0061 family) |
| overkill cap (2b) | `conserve-burst-when-no-ko`, `dont-overbuild-*` (payoff side) | — |
| role gate (5b) | `dont-fund-the-non-attacking-body`, `dont-power-the-draw-engine` | — |
| type-fit | `dont-waste-off-type-energy` | `fuel-the-dormant-ability` (ability fuel, not attack cost) |
| resource_cost | `prefer-reusable-over-burst`, `conserve-discard-energy-prefer-basic`, `dont-waste-discard-energy` (partial), the Ignition family | `dont-attach-discard-energy-turn1` (a rules gate — first-turn can't attack) |
| accel-routing (4) | `feed-the-firing-accelerator`, `advance-the-accel-pieces` (attach side) | the PLAY-side `advance-the-accel-pieces` (source selection) |
| partner-conditional (6) | mega_lucario `aura-jab-skip-partnerless-solrock` (deck rung, ADR-0034 fold) | — |

### How to rank the fold order (do NOT blind-build)

1. **The measurement probe.** Author `tools/train/probes/attach_sweep.py` on the `needs_sweep`
   pattern (fresh Pilot per frame, the corpus instrument finding): replay every committed attach
   frame, print `chosen` vs `eq_pick` vs the human `correct`, plus the `agree` bit and the term
   breakdown. This is the Round-0 measurement the grill spec calls for — it tells you which rung-
   families the oracle already reproduces (swap last / never) and which it FIXES (swap first).
2. **On live telemetry**, `attach_shadow` disagreement rows (`agree == False`) become the discovery
   channel for latent rung bugs the corpus never caught — collect them once the dev window opens.
3. Fold **failing legs first, agreeing families last**; each swap under: discard corpus 12/12 + the
   full suite + a `score_diff` gate + the currency-zone rule. Deck-rung folds (the mega_lucario
   attach family) go via `/deck-align` (ADR-0034), score_diff-gated.

## Standing cautions (paid for — from the coverage review; don't re-buy)

- **Shadow-first for anything touching a live decider; fresh Pilot per replay; verify card facts at
  source** (rules.md / rulebook.txt / EN_Card_Data.csv — never from memory). The Ignition
  `{C}{C}{C}`-on-Evolution + discard-EOT rule is load-bearing across the corpus.
- **Adding a big positive term silently voids guards calibrated against the old scale** (the +76
  shape). Seed each swap at the OLD currency's mid-band (the ADR-0060 calibration-anchor pattern);
  full-family pin re-audit — the attach pins span `test_blunder_*`, `test_attach_discipline.py`,
  `test_attach_target_priority.py`, the six ADR-0060 ordering pins, and now `test_attach_shadow.py`.
- **Blind pokes at shared machinery risk the frames that already pass.** The oracle's overkill cap
  and accel-routing read opponent HP and accel riders — a swap must hold the 16 currently-correct
  snipe frames and the discard 12/12.

## Open refinements (not blockers — future increments, each its own red→green)

- **Ruling 2a refill-discount (deeper).** The anchor `83664340-45` passes via `max(this_turn, build)`
  (the doomed Active's this-turn attack beats the survivor's build). The fuller ruling — discount the
  SURVIVOR's attach-need by `(1 − refill_odds)` — isn't separately modeled; a frame where the
  survivor's this-turn value is comparable would need it.
- **Accel-routing: expected vs floor.** The shadow uses expected routing (`recoverN` capped by
  recipient need); the live decider's `_recover_units` floors by the prize-paranoid deck-fuel bound.
  Decide at swap time which currency the LIVE decider uses (likely keep the sound floor for the
  commitment, the expected value only for the shadow's discovery signal).
- **Ignition burst-units.** `_attach_readiness`/`_attach_progress` add +1 unit per attach; Ignition on
  an Evolution really adds `{C}{C}{C}`. No current green frame needs it (they prefer the Basic), but a
  frame where Ignition UNLOCKS a bigger attack this turn would.
- **Evolution-lookahead value.** `line_value` uses `_role_value` (line-aware worth); the fuller
  Ruling 5a — value a pre-evo attach by the LINE's payoff attack damage (Dreepy → Dragapult 200) — is
  approximated by the role tier, not the payoff attack. Fine for target-choice today.
- **Generalize `Strategy.partners`.** Only mega_lucario declares a pairing; other decks' engine pairs
  (if any surface) are `/deck-align` candidates.

## The one corpus fix made this session

`82523811-59` was mislabeled — `correct=[6]` pointed at a redundant BENCH index identical to the
bot's pick, contradicting its own rationale ("add a second energy to the ACTIVE Mega Starmie …
Nebula Beam in two turns"). Re-tagged `[6]→[1]` (an active index) with a disambiguated label, user-
confirmed. Watch for similar redundant-index mistags when authoring the `attach_sweep` acceptance set.

## Grilled this session — `85786096-70` (a trap frame: OUT of the attach oracle's scope)

Flagged for grilling; classified and recorded here (NOT added to `test_attach_shadow.py`'s `_CORPUS`
as a pick/abstain). `dragapult_ex`, category **`slow_setup`** (not `misattachment`): `chosen=[1]`
**Play Boss's Orders** → `correct=[2]` **Play Crispin**. Every option is `_PLAY` (type 7) in MAIN
context — there is NO `_ATTACH` option, so the shadow correctly **returns `None`** (verified via
`_build_pilot('dragapult_ex').explain(obs)`). Card facts at source: Crispin (SCR 133) = *search 2
Basic Energy of different types, keep 1, **attach the other to 1 of your Pokémon**, shuffle*; Boss's
Orders (PAL 172) = gust. Three rulings fall out:

- **Not an attach-oracle frame — a "which Supporter" (gust vs energy-accel) decision.** Adding it to
  `_CORPUS` as a pick/abstain would be a category error; the oracle has nothing to price at this
  select.
- **The real defect is gust-vs-setup PRIORITY, not attach valuation.** Crispin (1198) is already
  correctly tagged `energy_accel`/`accel_source` (dragapult "primary un-gated accel"), so
  `use-acceleration` (+25) endorses it — yet the gust doctrine still out-scored fixing our own
  energy. That root cause lives OUTSIDE `baseline_energy.py`; grilling it through the attach lens
  chases the wrong system.
- **The oracle's real fire is one step DOWNSTREAM.** Crispin's baked-in "attach the other to 1 of
  your Pokémon" raises a follow-on target select where the oracle SHOULD price the active Dragapult
  first (it needs energy to attack), then the {P} onto benched Drakloak for the Phantom Dive line
  (concentrate/line-build, Rulings 1/5). This frame is a doorway to an attach, not the attach.

**Use it as a SILENCE pin** (a real committed board proving the shadow stays silent on a Supporter
select) and as the worked example for the `attach_sweep` **eligibility filter** (§"How to rank the
fold order" step 1): replay only frames where the shadow FIRES — never ingest energy-adjacent
`_PLAY` frames by category/keyword, or the sweep will report a phantom "disagreement" (the oracle
can't rank the correct Crispin option) and send someone hunting a non-existent attach bug. Same
hazard class as the redundant-index mistag above.
