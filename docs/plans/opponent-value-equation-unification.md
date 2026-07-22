# The Opponent Value Equation — unifying snipe, threat/doom, board-clock, deny & gust (design, 2026-07-22)

**For the session building the unified opponent-read value system.** Supersedes the two fold-candidate
handoffs as their synthesis: `snipe-system-handoff.md` (the ADR-0065 snipe-fold question) and
`threat-clock-unification-handoff.md` (the doom + board-clock merge). Companions still live:
`turn-planner-snipe-and-gust-scenarios.md` (the threshold-race + gust-tempo scenarios, corpus-scoped),
`valuation-systems-coverage-review.md` (the coverage map + ranked work). This doc records the **user
grill of 2026-07-22** (six rulings, below), the unification thesis those rulings settle, and the staged,
shadow-first build path. **It is a design, not a build — the standing discipline holds: grill first,
shadow-first, bench always, do NOT blind-poke shared machinery.**

## The thesis

The user's intuition — "snipe and threat-clock can fold into one opponent value equation" — is correct
**and wider than the two systems named.** Snipe and threat-clock are two of **five** opponent-read
consumers that are all projections of ONE **opponent-attacker model** onto different axes:

| Consumer | Question | Currency today | Policy | Home |
|---|---|---|---|---|
| **Threat / doom** | Does their attack KO my Active next turn? | damage vs my HP (bool) | **ceiling** (pessimistic) | `combat.active_doomed` / `reachable_incoming` (18 call sites) |
| **Board-clock** | Turns until their line is armed? | turns (count) | **slow** (optimistic) | `_opp_turns_to_ready` → `needs.turns_to_ready` |
| **Deny value** | What does stripping their Energy take away? | `best_affordable(E)−best_affordable(E−1)`, `/2^turns` | slow | ADR-0062 `_opp_denial_best` / `needs.deny_slot` |
| **Snipe targeting** | Which body to damage? | additive positional points (12–60) | — | `baseline_snipe.py` (6 rungs) + `_target_threat_rank` |
| **Gust-line tempo** | Which body to gust-KO; is the trade good? | `KO_prizes + tempo − return_threat` | — | ADR-0066 `_gust_target_tactical` (separate session) |

Three facts make this a **buildable unification, not a metaphor**:

1. **ADR-0045 already NAMES the "Threat Clock" as the unifier** of "the six scattered reads" — explicitly
   including `_body_threat_rank` (the snipe order). ADR-0064 already BUILT `reachable_incoming` =
   `incoming(t=1, policy)`. The threat-clock handoff's whole proposal is: **generalize `t=1 → t=N`** and
   make every read a *query that inverts the curve*.
2. **The codebase already did this exact fold once** — ADR-0065's keep-value story: four disjoint
   card-worth shadows collapsed into one `Worth × Odds` currency, with the **Needs assignment**
   (`needs.py`) as the marginal-coverage engine. The snipe handoff says it outright: snipe is *"the exact
   analog of the old discard equation before the Needs successor replaced it."* And `needs.deny_slot`
   **already prices opponent bodies as slots in that same assignment** (WP-N7) — snipe/gust simply are not
   in it yet.
3. **The family is already converging organically.** ADR-0051's **MatchupPlan** is described in-code as
   *"the unified opponent target-priority spine read by the snipe/gust consumers"*; the gust doctrine
   already reaches into snipe (`_gust_snipe_synergy`) and the ADR-0062 strip (`_gust_energy_denial`, *"the
   marginal-strip ruling pointed across the table"*). Four half-built spines (Threat Clock, MatchupPlan,
   deny-slot, gust-value) are each reaching for the same shape. The unification's job is to **converge
   them onto one backend + one marginal**, not to build greenfield.

## The user rulings (grill, 2026-07-22)

1. **Currency = a two-term SUM.** `value(act on a body) = prize-race progress + survival-turns bought`.
   Not prize-only, not tempo-only — both, weighed per turn. Matches the observed hybrids: the
   threshold-race (get a body under my finisher's OHKO threshold within my window), gust (KO_prizes +
   tempo − return), deny (pure tempo), forced-promotion (prize-path).
2. **Conservatism = policy PER CONSUMER (a parameter, load-bearing, never collapsed).** Survival reads
   the pessimistic ceiling; deny / board-clock read the optimistic slow clock; snipe-prep / gust pick per
   sub-case. This is the threat-clock handoff's central design and the reason ADR-0045's affordability
   rewire of `active_doomed` was **reverted** (hidden Ignition burst).
3. **Scope = the WHOLE opponent-target family**, one backend feeding snipe + gust + deny + forced-promo +
   posture; deciders stay (the ADR-0065 "one backend, doctrines stay deciders" pattern). **Coordinate
   with / absorb the in-flight gust session** (ADR-0066 unified read) so they do not diverge.
4. **Horizon = the N-turn curve + discard-fuel read IS the heart.** The threshold-race (the one live snipe
   gap) and deny-vs-recycler are the same missing capability: walk the curve forward N turns, reading the
   opponent's DISCARD as a fuel/recovery pool (`discard_energy_recur`, tag built, unwired). Build that as
   the core deliverable, not an add-on.
5. **Exchange rate = PHASE-SCALED by the KO-race margin.** A survival turn scales with how close either
   player is to their last prize: near-worthless when I'm stable and ahead, worth ~a prize when I'm about
   to be KO'd on my last defender. Uses ADR-0045's KO-race margin — **NOT** a blanket match-importance γ
   (ADR-0065's refused +76 runaway). The scaler is the *phase signal already trusted at match scale*, not
   a new fudge factor.
6. **Decline-a-prize = ALLOWED behind ADR-0045 S4's tight sound gate.** The equation may forgo a
   non-winning KO / decline a gust when ALL hold: the KO is off my committed prize path; the promoted
   body is *strictly* scarier by the clock; I have a productive develop instead; confidence is high. Any
   doubt → take the prize ("don't wake the giant"; the refuted-forgo-KO prior stays the fallback). A real
   Lethal is never forgone (win rung preempts). This subsumes the parked ADR-0045 S4 (`forgo_ko`,
   default-OFF) and Scenario B (the bad-trade gust).

## The two layers

### Layer 1 — the Threat Clock curve (the shared BACKEND)

Promote ADR-0064's one-step `reachable_incoming` to the N-turn curve the threat-clock handoff specs:

```
incoming(t, policy, my_target) = worst W/R-adjusted damage the opponent's board deals my_target
                                 at future turn t, under `policy`'s accel/evolve model over t turns
```

Inputs (all card-fact / visible-zone, Read γ-sharpens — the ADR-0045 fallback contract):
- **Energy clock** — attached + `policy`'s attach rate (1/turn floor, rules.md §3) + known accel
  (`energy_accel`) + **discard-recur fuel** (`discard_energy_recur`: Mega Lucario ex reloads `{F}` from
  discard, Archaludon ex; the pending #2 wiring). Reading the live discard pile tracks the renewable pool
  even against a recycler (coverage-review finding (a)).
- **Evolution hops** — one per turn over the forward index (`_ForwardIndex`, ADR-0020), promotion
  surcharge (ADR-0045 `_promotion_surcharge`, reduced by a revealed/Read switch-enabler).
- **HP + W/R** — the combat oracle's W/R-adjusted damage (ADR-0052), multi-hit accumulation (the Survival
  Window generalized).

**`policy` is a PARAMETER, never collapsed** (ruling 2). The seed already carries it: `reachable_incoming`
takes `charged=None` (ceiling) vs `charged={base_attach, burst_on_evo}` (budgeted). Every existing read is
a query:

| Read | Query | Policy |
|---|---|---|
| `active_doomed` | `incoming(1, ceiling) ≥ my_hp` | ceiling (survival never under-prepares — the hidden-burst gate) |
| `turns_to_ready` | `min{ t : incoming(t, slow) ≥ armed_threshold }` | slow (a speculative deny never over-priced) |
| `strongest_threat_rank` (snipe imminence) | the curve's earliest-KO-turn / slope per body | prep policy (ruling 2, per sub-case) |
| gust `return_threat` | `incoming(1, ceiling)` of what promotes back | ceiling (assume the full-health attacker fires) |
| `deny_value` | how far a strip shifts the curve right (Δt on `turns_to_ready`) | slow |

Cost discipline (threat-clock handoff blocker 1): a full curve is costlier than a one-step worst-case;
**memoize once per decision** (the `_opp_attack_context` / `_incoming_budget` stash precedent). Consumers
that only want the boolean must not pay for the whole curve — expose cheap `incoming(1,·)` and lazy
`incoming(t,·)`.

### Layer 2 — the opponent-target marginal (the DECIDER)

One currency for "what is applying my removal-instrument to opponent body *b* worth to MY match":

```
value(remove / chip / deny body b) =
      prize_advance(b, my prize path)                         # prize term (ruling 1)
    + survival_shift(b) × phase_scale(KO-race margin)         # tempo term, phase-scaled (rulings 1, 5)
    − redundancy(b)                                           # ADR-0044 guards (prize-redundant / mirage / bench-tera)
    [ forgo/decline gate: ADR-0045 S4, tight sound gate ]     # ruling 6
```

- `prize_advance` = does this chip/KO advance my cheapest prize route (ADR-0040 path) or deny theirs; the
  KO/prize magnitude for a KO instrument, the path-membership chip for a snipe.
- `survival_shift` = Δ(my turns-to-live) = how far the strip/KO/chip moves the Layer-1 curve **right** for
  my threatened body — the deny "Δt" and the snipe threshold-race "get it under my finisher's threshold"
  are the SAME quantity read through different instruments.
- `phase_scale` = the KO-race-margin phase signal (ruling 5): ≈0 when stable+ahead, ≈1 prize when
  stabilize-or-die. Bounded, derived from ADR-0040's two-sided KO Race — never a blanket γ.

**Snipe rider, gust+KO, Hammer strip, forced-promotion pre-chip are the SAME question, different
instrument** — each plugs its own `Δ` into the two terms. This is ADR-0065's `value = Worth × Odds` shape;
the `deny_slot` in the Needs assignment is already exactly this, so the concrete realization is: **bring
the snipe/gust/forced-promo instruments into the same marginal vocabulary the deny-slot already speaks**
(a Needs-style opponent-target assignment, or a shared `opponent_target_value` primitive the doctrines
consume — see Open question O1).

## The seams to fold INTO (not around)

The unification is a **convergence of existing spines**, each a corpus-gated flip under its own family:

- **ADR-0064 `reachable_incoming`** → the Layer-1 curve. Generalize `t=1 → t=N` behind a shadow; emit old
  + new, assert byte-identical on the corpus at `t=1`; then add `t>1` + discard-fuel as net-new behavior.
- **ADR-0045 Threat Clock (S1)** → the same curve. It exists (`objectives.py _threat_clock` /
  `_threat_forms`) but is a *complement*, not the *replacement*. Promote it; re-express `active_doomed`
  and `_opp_turns_to_ready` as two queries against it (threat-clock handoff's recommended first step).
- **ADR-0051 MatchupPlan** → the Layer-2 marginal's Read-sharpened target priority. Already the shared
  snipe/gust spine; fold its priority into `prize_advance` rather than beside it.
- **ADR-0062 / WP-N7 `deny_slot`** → the Layer-2 marginal for the strip instrument. Already in the Needs
  assignment; the WP-N8 ruling (deny slot = disruption card-tier `TAG_TIER["gust"]` graded by
  turns-to-ready, NOT the ~140 damage swing) is the currency precedent — the marginal is a *tier*, the
  damage magnitude stays on the play-side rungs.
- **ADR-0066 gust-value** → the Layer-2 marginal for the gust instrument. **In-flight in a separate
  session** (`_gust_target_tactical` = `KO_prizes + tempo − return_threat`). Ruling 3 says coordinate /
  absorb — this is the primary cross-session seam (see Coordination).

## The policy-parameter table (ruling 2 — load-bearing)

| Consumer | Fail direction | Policy | Why |
|---|---|---|---|
| Survival (`active_doomed`, loss rung, heal/retreat/tool) | fail-scared | **ceiling** | under-preparing loses games; hidden burst Energy (ADR-0064) |
| Deny (Hammer) / board-clock | fail-slow | **slow** | over-valuing a speculative strip wastes Hammers (ADR-0062 bench 0.25) |
| Snipe-prep (evolving threat, threshold-race) | fail-scared on the THREAT existence, fail-slow on the INVESTMENT | **prep** (existence-gated ceiling on the body; slow on how much to spend) | ADR-0064's asymmetric availability gate: existence for threat, budget bounds the pessimism; but don't over-chip a speculative line |
| Gust return-threat | fail-scared | **ceiling** | assume the promoted full-health attacker fires (Scenario B) |

The asymmetry ADR-0064 §4 already ships (existence for threat, matched-Read for safety) is the template:
**over-counting their reach costs a nudge; under-counting feeds them the wincon.** Keep it per-consumer.

## Build staircase (staged, shadow-first, per-family — the ADR-0065 discipline)

Each stage independently valuable and revertible; no stage flips behavior until the one below is proven
no-regression. **Do NOT big-bang** (ADR-0065 rejected "converge all four at once"; the compounded seam is
unbisectable — T5/T6 precedent).

- **S1 — the curve, shadow-only.** Extract `incoming(t, policy)` generalizing `reachable_incoming` (t a
  param, memoized). Re-express `active_doomed` and `_opp_turns_to_ready` as queries behind a shadow (emit
  old + new, assert **byte-identical on the corpus at t=1**). Compute-only; zero decisions change. Bench:
  the 18 doom call sites + the discard corpus 12/12 + full suite; fresh Pilot per replay.
- **S2 — the N-turn + discard-fuel net-new behavior.** Thread `discard_energy_recur` into the accel policy
  (the first net-new read once the shadow is clean). Fixes deny-vs-recycler and arms the threshold-race
  input. Still no decider swap — telemetry only.
- **S3 — the Layer-2 marginal, shadow-only.** Define `opponent_target_value` (the two-term sum with the
  phase-scaled exchange). Emit it beside every snipe/gust/deny decision as a shadow (the seam-D pattern,
  ADR-0065). First corpus sweep over the 23 DAMAGE frames (`snipe_sweep`) + the gust frames + the Hammer
  frames — localize disagreements, adjudicate frame-by-frame with the user (the WP-N8 currency grill).
  **Acceptance = byte-identical on the 16 passing snipe role reads + fix the ruled threshold-race**
  (`83667237-107`), hold the deny 5/5 (ADR-0062) and gust frames.
- **S4 — the decider swaps, per instrument.** Snipe first (its rungs → the marginal; the ADR-0065 snipe
  fold), then deny (already a slot), then gust (coordinated with the ADR-0066 session). Each a PROFILE
  kill-switch, OFF byte-identical (`develop_rollout` / seam-D precedent).
- **S5 — the decline-a-prize gate (ruling 6).** The riskiest behavior, LAST, behind its own kill-switch
  (ADR-0045 S4's `forgo_ko`, promoted from parked-OFF). The tight four-condition sound gate; any doubt →
  take the prize. Own bench: a captured can-KO-but-bad-trade anchor (Scenario B still lacks one — flag for
  capture) + the forgo-KO corrections.

## Coordination with the in-flight gust session (ruling 3)

`valuation-systems-coverage-review.md` (today) records the ADR-0066 unified gust read — `gust value =
KO_prizes + tempo_denied(role, turns_out_of_position) − return_threat` — as *"being built in a separate
session; do NOT author it here."* Ruling 3 changes that to **coordinate / absorb**. Concretely:
- The gust `return_threat` is `incoming(1, ceiling)` — a Layer-1 query. The gust `tempo_denied` is the
  `survival_shift` term. So the ADR-0066 equation IS the Layer-2 marginal for the gust instrument. Do not
  build a rival — **make the gust session's `_gust_target_tactical` a consumer of `opponent_target_value`**
  once S3 lands, or (if it lands first) treat its shape as the marginal's first concrete instance and fold
  snipe/deny to match it.
- **Action for the next session:** before touching gust code, check the gust branch/PR state (PR #128
  merged the gust target/whether cluster; the unified read is elsewhere) and sync with that session so the
  two do not author two currencies. This is the one hard cross-session dependency.

## Open questions / risks

- **O1 — assignment vs primitive.** Is the Layer-2 marginal a **Needs-assignment slot family** (opponent
  bodies as slots, the deny-slot generalized to snipe/gust — one global assignment prices all removal
  instruments together) or a **shared `opponent_target_value` primitive** the doctrines call (the ADR-0052
  KO-oracle shape)? The deny-slot is already in the assignment, which argues for the former; but snipe/gust
  fire in different SelectContexts (DAMAGE 15 / SWITCH / DISCARD_ENERGY 30) that rarely collide in one
  select, which argues the primitive is enough. **Decide at S3 against the shadow evidence**, not now.
- **R1 — the phase scaler is the +76 risk surface.** Ruling 5 is phase-scaled, and ADR-0065 refused a
  match-importance multiplier for exactly this reason. The guard: the scaler is ADR-0040's *derived* KO-race
  margin (bounded [0, ~1 prize]), consumed intact — never a free γ. Enumerate the computable phase inputs
  (my/their prizes remaining, turns-to-live), never a taste fudge. Re-audit any guard the new term voids.
- **R2 — blind-poke of shared machinery.** `strongest_threat_rank` + the ADR-0044 prize-guards are ridden
  by the 16 passing snipe frames AND the deny/gust reads. The threshold-race fix needs to lift the rank for
  a discard-fueled line AND relax the redundant guard for an imminent fueled threat — touching both. Grill
  frame-by-frame, bench the 23 DAMAGE frames, hold the 16. (snipe-scope handoff.)
- **R3 — the transposition floor.** `81905522-75` (two identical Riolu) is unfixable by any value term —
  don't chase it; log it as a known tie.

## Acceptance bars (carried from the source discipline)

- The discard corpus holds **12/12** and the full suite stays green through every stage; shadow-first for
  anything touching a live decider; **fresh Pilot per replay**; card facts verified at source.
- S1 is byte-identical at t=1 on the corpus (the 18 doom call sites re-baselined deliberately, not
  discovered — ADR-0064's blast-radius recipe).
- The Kaggle ladder is the only valid GAIN gate (gauntlet invalid); each decider swap ships default-OFF
  then armed, blunder-buster-parseable telemetry into `live_trace` (ADR-0045 §10 / ADR-0041 pattern).
- No new magic-number / γ fudge (ADR-0065): every term is a derived tier, a derived odds, or a derived
  phase margin. A graded term REPLACES its guard family and re-audits it — never bolts on beside it.

## Recommended first step

S1: extract `incoming(t, policy)` and re-express `active_doomed` + `_opp_turns_to_ready` as two shadowed
queries, byte-identical at t=1. It is a real bug-fix (the N-turn read the threshold-race and deny-recycler
both need) and behavior-neutral to land — the safe wedge into the whole unification.
