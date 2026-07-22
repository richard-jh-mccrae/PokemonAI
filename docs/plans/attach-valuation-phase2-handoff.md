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
attach call. That is why the full suite held unchanged at every Phase-1 increment (a shadow that
decides nothing changes no live pick). Re-run `python -m pytest tests/ -q` for the current total —
earlier snapshots (3105 in the grill spec, 3108 here) are stale now that the evolve-valuation arc
merged; don't cite a fixed number.

- **Entry:** `Pilot._attach_shadow(obs, select, board, options, traces, chosen)` — sparse (None off a
  real attach choice or mid-sim `self._planning`), wired onto BOTH `Decision` returns in `explain()`
  — the planned-turn path and the fall-through (grep `attach_shadow=self._attach_shadow`; line numbers
  drift with every merge, so search the call, don't trust a number). Fires when ≥2 options are
  `_ATTACH` (or `_ATTACH_FROM` `_CARD` recipients).
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

### The rung → term fold map (HYPOTHESISED — which rungs each oracle term SHOULD subsume)

⚠️ **This map was HYPOTHESISED (read off `baseline_energy.py`), then partially MEASURED.** Round-0
has now run (`tools/train/probes/attach_sweep.py`, results below). It CONFIRMED two families as
pure-reproduction (`accel-routing`, `doomed-sign`), found `marginal` mixed (real fixes but
regressions that gate a swap), and left FIVE families (`overkill`, `role-gate`, `type-fit`, the
burst-veto row, `resource_cost`) **UNMEASURED** — the corpus never exercises them as the dominant
driver. Treat any UNMEASURED cell as still-hypothesised; the measured status per family is in the
Round-0 table below.

| Oracle term | Rungs it subsumes | Rungs that SURVIVE (structure, not value) |
|---|---|---|
| `marginal` (build/this_turn/concentrate) | `concentrate-energy-on-wincon`, `build-active-wincon`, `power-up-attacker`, `spread-attach-to-the-needy`, `concentrate-accel-on-one-line-body` | `attach-energy-last` (sequencing tier), `use-acceleration` (PLAY-side source selection) |
| doomed sign (1 / 2a) | `dont-feed-the-doomed`, `arm-the-doomed-active`, `dont-overbuild-the-doomed-wincon` | `feed-the-line-for-disruptor-lock` (a lock maneuver, ADR-0061 family) |
| overkill cap (2b) | `conserve-burst-when-no-ko`, `dont-overbuild-*` (payoff side) | — |
| role gate (5b) | `dont-fund-the-non-attacking-body`, `dont-power-the-draw-engine` | — |
| type-fit | `dont-waste-off-type-energy` | `fuel-the-dormant-ability` (ability fuel, not attack cost) |
| `marginal` (`evaporates` gate — burst VETOES) | the burst-veto branches of `dont-waste-discard-energy` (benched / turn-1 / already-affords), `dont-attach-discard-energy-turn1` | — |
| resource_cost (burst TIE-BREAK only) | `prefer-reusable-over-burst`, `conserve-discard-energy-prefer-basic`, and the same-target reusable-vs-burst branch of `dont-waste-discard-energy` | — |
| accel-routing (4) | `feed-the-firing-accelerator`, `advance-the-accel-pieces` (attach side) | the PLAY-side `advance-the-accel-pieces` (source selection) |
| partner-conditional (6) | mega_lucario `aura-jab-skip-partnerless-solrock` (deck rung, ADR-0034 fold) | — |

### Round-0 results — measured 2026-07-22 (`tools/train/probes/attach_sweep.py`)

Full corrections corpus, fresh Pilot per frame, slot-based comparison (Decision 1). The oracle
FIRED on **122 frames**. The 2×2 is over IN-SCOPE frames only (`correct` IS an attach).

**Scope, quantified:** **50 of 122** fires are OUT-OF-SCOPE — `correct` is a NON-attach play
(Supporter / retreat / evolve). The oracle prices WHERE energy goes, not WHETHER to attach vs act
elsewhere (the `_PLAY` layer, the `85786096-70` lesson). On 17 of those 50 the oracle correctly
declined (`eq_pick=None`). These 50 never enter the fold ranking. The remaining **72 are in-scope.**

| Family | SAFE | REGR | SHARED_GAP | FIX | DIVERGENT | Round-0 verdict |
|---|---|---|---|---|---|---|
| `accel-routing` | 4 | 0 | 0 | 0 | 0 | **MEASURED-SAFE** — oracle reproduces the rung; safe to fold but no behaviour change |
| `doomed-sign` | 4 | 0 | 0 | 0 | 0 | **MEASURED-SAFE** — same; swap LAST / never |
| `marginal` | 24 | **2** | 2 | 3 | 1 | **MEASURED-MIXED** — was 21/**5**/2/3/1; **evolution-lookahead cleared 3 regressions** (see below). 2 remain, each a SEPARATE root cause |
| `overkill`, `role-gate`, `type-fit`, `marginal(burst-veto)`, `resource_cost` | 0 | 0 | 0 | 0 | 0 | **UNMEASURED** — no in-scope frame attributes here; fold stays hypothesised |
| `(rung-silent)` | 0 | 0 | 6 | 13 | 7 | whether-to-attach signal: oracle catches **13** attaches the rungs MISSED; not a rung-fold |
| `(unmapped: deck)` | 3 | 0 | 1 | 0 | 0 | ADR-0034 deck folds: `attach-solrock-over-line-base`, `aurajab-load-the-wincon-line` |
| `structure` (survivors) | 0 | 2 | 0 | 0 | 0 | not fold targets; 2 dragapult regressions (`85786096-24/25`) to eyeball |

**`marginal` regression triage (2026-07-22).** The original 5 split into ONE shared root cause + two
singletons: `82752604-61`, `83116081-21`, `85059103-84` all failed because the oracle priced a
pre-evolution's attach by its OWN cheap attack (maxed at 1 Energy) instead of the LINE's payoff — now
**FIXED by evolution-lookahead** (`_line_payoff_stat`, below), which also required a pre-evo build
discount so the payoff-priced pre-evo doesn't out-credit an evolved body or a this-turn arm of the
doomed Active (would have regressed `doomed-sign` 4→1 and `83007714-22`; both held after the 0.25
discount). The **2 that remain** are each a distinct, separate root cause, NOT a spread/concentrate
bug: `82523811-105` needs the **Ignition burst-units** fix (Ignition on an Evolution = CCC=3, the
oracle counts +1, so it misses the Nebula lethal); `85058574-121` is the **convex first-step edge**
(a cheap secondary's completing energy, Solrock 70@1, out-marginals the wincon Mega's first energy,
67.5, before `line_value` breaks the tie).

**Completeness check** flagged 4 fired rungs missing from the map: the 2 deck attach rungs above
(ADR-0034), and 2 TOOL rungs (`deploy-hp-tool`, `equip-the-retreat-tool-on-the-active`) that ride
`OptionType.ATTACH` but are out of scope — the oracle abstains on Tools (correct, Ruling 3).

**Bottom line:** the fold map is NOT globally validated. Only `marginal` carries real fold signal,
and it is gated by 5 regressions. `accel-routing`/`doomed-sign` are safe but pointless to fold (pure
reproduction). Five families are unmeasured until live telemetry (item 2) or new corrections supply
frames. The clean-equation goal is intact — the equation already reproduces two families exactly and
matches `marginal` 21/32 with 3 net fixes — but it is not yet good enough to replace `marginal`
wholesale, and most families have no evidence at all.

### How to rank the fold order (do NOT blind-build)

1. **The measurement probe — BUILT & RUN.** `tools/train/probes/attach_sweep.py` (the `needs_sweep`
   pattern: fresh Pilot per frame, slot-based comparison, fires-only primary + a structural audit
   section, per-family 2×2 via an executable `{rung → family}` fold map). Round-0 results are in the
   table above. Re-run it after any rung change to refresh the ranking.
2. **On live telemetry**, `attach_shadow` disagreement rows (`agree == False`, now slot-based) become
   the discovery channel for latent rung bugs the corpus never caught, AND the source of frames for
   the five UNMEASURED families — collect them once the dev window opens.
3. Fold **failing legs first, agreeing families last**; each swap under: discard corpus 12/12 + the
   full suite + a `score_diff` gate + the currency-zone rule. Per Round-0: `accel-routing`/
   `doomed-sign` fold safely but change nothing; `marginal` is down to **2** regressions (evolution-
   lookahead cleared 3), each a distinct separate cause (Ignition-units; convex first-step edge);
   the five UNMEASURED families cannot be folded until frames exist. Deck-rung folds (the mega_lucario
   attach family — `attach-solrock-over-line-base`, `aurajab-load-the-wincon-line`) go via
   `/deck-align` (ADR-0034), score_diff-gated.

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
  snipe frames and the discard 12/12. Two sharp edges to preserve verbatim: (a) the accel-routing
  value is gated on board signals the live `feed-the-firing-accelerator` rung does NOT share —
  `_attach_value`'s `feeds_accel` also requires `not board.accel_recipient_missing and not
  board.bench_wincon_ready`; a swap that drops them changes when routing is credited. (b) the overkill
  cap mixes two damage notions — the KO gate is `board.active_cheap_attack_kos` but the coverage test
  is `_attach_readiness(have)` (current affordable printed damage); they are not the same currency, so
  don't "simplify" one into the other.
- **The strong burst VETOES live in `marginal`, not `resource_cost`.** `resource_cost` is only the
  4th (tie-break) ranking key. The −60/−60/−40 burst penalties are reproduced by the `evaporates` →
  marginal-0 gate (benched / turn-1 / can't-cash burst). When folding a burst rung, replace it against
  the `evaporates` gate, not the tie-break term (see the fold map's two burst rows).

## Open refinements (not blockers — future increments, each its own red→green)

- **Ruling 2a refill-discount — a KNOWN CORRECTNESS GAP, not a refinement (no repro frame yet).**
  The `(1 − refill_odds)` discount on the SURVIVOR's attach-need is entirely UNIMPLEMENTED — the
  oracle has no refill-odds term at all. Every corpus frame that touches Ruling 2a is nonetheless
  decided correctly by the simpler `max(this_turn, build)` (on the anchor `83664340-45` the doomed
  60-HP Active's this-turn attack (~120) dominates the fresh bench Mega's small convex build (~23),
  so the tie never reaches the refill logic). It becomes wrong only on a frame where the survivor
  ALSO has a comparable this-turn attack — and we have NO such frame, so it CANNOT become an xfail
  target today. File it as an xfail the moment live telemetry (the item-2 disagreement channel)
  surfaces a board that turns on it; until then it stays prose.
- **Accel-routing: expected vs floor.** The shadow uses expected routing (`recoverN` capped by
  recipient need); the live decider's `_recover_units` floors by the prize-paranoid deck-fuel bound.
  Decide at swap time which currency the LIVE decider uses (likely keep the sound floor for the
  commitment, the expected value only for the shadow's discovery signal).
- **Ignition burst-units.** `_attach_readiness`/`_attach_progress` add +1 unit per attach; Ignition on
  an Evolution really adds `{C}{C}{C}`. No current green frame needs it (they prefer the Basic), but a
  frame where Ignition UNLOCKS a bigger attack this turn would.
- **Evolution-lookahead value — IMPLEMENTED (2026-07-22).** `_attach_progress` now prices a
  win-condition pre-evo's convex build by the LINE PAYOFF's attack (`_line_payoff_stat`: Staryu builds
  toward Mega Starmie's Nebula CCC=210, not Water Gun 20), × a 0.25 pre-evo discount (the body must
  still evolve, so its build sits below an evolved body's and below a this-turn arm). Cleared 3 of the
  5 `marginal` Round-0 regressions with no net new regression; pinned by
  `test_evolution_lookahead_concentrates_on_the_started_preevo`. Remaining nuance (future, no repro
  frame): a PER-HOP discount (a 2-hop Dreepy sits further from Dragapult than a 1-hop Drakloak — flat
  0.25 today), and extending the payoff pricing to SECONDARY-attacker lines (only win-condition lines
  today, matching `_line_preevo_set` / ADR-0048).
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
