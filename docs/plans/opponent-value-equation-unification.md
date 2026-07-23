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
the `deny_slot` in the Needs assignment is already exactly this.

**Realization = the Needs ASSIGNMENT, generalized (O1 resolved: Option B, user, 2026-07-22).** The
marginal is not a per-doctrine calculator each attack calls independently — it is **one board-wide slot
assignment**. Every opponent in-play body (+ its forward forms) is an **opponent-target slot** on the same
ledger the `deny_slot` already lives on; my available removal instruments this turn (snipe rider, gust,
Hammer, forced-promo chip) are the *cards being assigned to those slots*, and the exact bitmask-DP solver
(`needs.assignment_value` / `set_keep_v2`) prices the whole turn's removal plan in ONE pass. This is what
makes the interactions fall out for free — the value is **marginal**, so:
- I cannot double-spend two instruments on one body and count both (the solver assigns each slot once).
- KOing body X *reprices* body Y in the same pass (the survival curve shifts; the solver re-optimizes).
- Sequencing (gust X for the KO ⇒ the Hammer is now better on Y) is the assignment, not hand-coded.

So the concrete build is: **add an opponent-target slot family to `needs.py`** (generalize `deny_slot` to
`snipe` / `gust` / `promo_chip` instruments over the same slots), and make each doctrine's target pick
read its instrument's marginal out of the shared assignment — the `deny_slot` → Needs precedent (WP-N7),
extended. The doctrines stay the DECIDERS (when to snipe vs gust vs Hammer); the assignment is the shared
value BACKEND they all query.

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
  - **S1a — the pure `incoming(t, policy)` primitive: BUILT (2026-07-22, TDD).** `CombatMath.incoming`
    (`src/common/strategy/combat.py`) — the N-turn curve; `reachable_incoming` now DELEGATES to
    `incoming(t=1)` (one implementation, so t=1 is byte-identical **by construction**). Key finding that
    shaped it: `forward_card_ids` is already **all-descendants** (existence-gated), so the evolution reach
    is maximal at t=1 and **t moves ONLY the energy budget** (`attached + t` ceiling / `attached +
    t·base_attach + burst` charged) — a minimal generalization, not a multi-hop rewrite. `_reach_form_damage`
    gained an `attaches` param (default 1). Tests `tests/strategy/test_incoming_curve.py`
    (`REQ-CURVE-0001..0005`: t=1 parity, monotonic-in-t, the current-form + evolved-nuke energy clocks, t
    clamp). **Full core suite green (2969 passed / 1 skipped / 3 xfailed)** — the existing
    `test_reachable_incoming.py` (9 pins) unchanged. Memoization DEFERRED to S1b (only a multi-t caller
    pays for the curve; the t=1 read is exactly as cheap as before).
  - **S1b — the doom SHADOW: BUILT (2026-07-22, TDD).** `CombatMath.doomed_incoming` re-expresses the
    survival doom read as an `incoming(t=1)` curve query (ceiling policy); `Pilot._threat_shadow` emits the
    incumbent `active_doomed` (the decider, unchanged) beside it + the agreement bit on
    `Decision.threat_shadow` → `telemetry.to_record`'s `threat_shadow` key, **deciding NOTHING** (the
    established shadow-equations pattern — `discard`/`refresh`/`attach` precedent; sparse, `_planning`
    mid-sim guard). **Confirmed NOT byte-identical by design** (the finding that makes it a shadow, not a
    delegate): `active_doomed` is unconditionally worst-case (ADR-0064 §2) while the curve gates the
    current form on `can_pay_cheapest` and omits the `hand_size_attacker` forward counter — the two known
    divergences, pinned in `tests/strategy/test_threat_shadow.py` (`REQ-DOOMSHADOW-0001..0003`: the
    afford-agrees case, the unaffordable-current-form divergence, the emit + mid-sim guard). Suite green
    (strategy+blunder 1247; full core pending). **The corpus sweep of this agree bit is the adjudication
    input for the eventual survival swap — run it next (needs the gitignored corrections corpus).**
  - **S1c — the board-clock one-home extraction: BUILT (2026-07-22, TDD).** `CombatMath.turns_to_afford`
    — the deny-clock's energy/evolve model lifted onto the KO oracle beside `incoming` (the Threat Clock's
    two legs — the damage curve + the affordability clock — now share ONE home and the one forward index);
    `pilot._opp_turns_to_ready` DELEGATES to it (byte-identical, the S1a pattern — NOT a shadow, because
    this read is already an AFFORDABILITY read: "armed = biggest-attack COST payable," blocker 3 already
    satisfied, so nothing diverges). Policy-parameterizable via `attaches_per_turn` (default 1 = the slow
    deny read, ruling 2's per-consumer conservatism as a parameter). Tests
    `tests/strategy/test_turns_to_afford.py` (`REQ-TTR-0001..0004`: the parallel-legs lookahead, fail-closed
    None, the attach-rate policy param, and the delegate drift-guard); the existing
    `test_needs_deny_resolver.py::test_opp_turns_to_ready_is_the_visible_parallel_lookahead` pins the
    byte-identical values. Full core suite green (pending). The full curve-INVERSION
    (`min{t : incoming(t, slow) ≥ armed}`) is a later refinement; the affordability primitive is the shared
    home now.
  - **Memoization** DEFERRED to when a consumer walks multiple t per decision (the t=1 reads stay as cheap
    as before).
- **S2 — the discard-fuel read: BUILT as a shadow (2026-07-22, TDD).** `CombatMath.discard_recur_fuel` —
  the extra Basic Energy a `discard_energy_recur` line reloads from the opponent's discard next turn
  (`min(discard count of the line's own type, _RECUR_RELOAD_CAP=3)`; **card facts verified at source** —
  Mega Lucario ex 678 Aura Jab reloads up to 3 Basic {F} to its Bench, Archaludon ex 190 Assemble Alloy up
  to 2 Basic {M}). `Pilot._recur_shadow` → `Decision.recur_shadow` → telemetry emits, per opponent refueler
  body, the Threat-Clock reads WITH-vs-WITHOUT the fuel (`incoming(t=1)` to my Active + `turns_to_afford`),
  **deciding NOTHING** — the live reads are byte-identical (the shadow models the fuel by augmenting a copy
  of the body's `energies`; no live primitive touched, so no signature/behaviour change). Tests
  `tests/strategy/test_discard_recur_fuel.py` (`REQ-RECUR-0001..0004`: the capped line-type fuel, the
  zero/blind fallbacks, the shadow emit + delta + mid-sim guard). Full core suite green (pending).
  **Conservatism note (ruling 2):** the fuel raises `incoming` (survival = fail-scared, SAFE to adopt) and
  lowers `turns_to_afford` (deny = fail-slow; adopting it there over-values a strip — the UNSAFE direction,
  so the deny swap must stay conservative / Brief-scoped). The sweep of `recur_shadow` (gitignored corpus)
  measures the magnitude before any adoption. The precise reload TARGETING (Aura Jab feeds the BENCH, not
  self; Archaludon any {M}) is a swap-time refinement — the shadow augments the recur body directionally.
- **S3a — the two-term marginal + shadow: BUILT (2026-07-22, TDD).** `needs.phase_scale` (ruling 5 — the
  KO-race phase scaler ∈ [0,1], grounded in `race_ahead` + opp Prize proximity like
  `objectives.plan_confidence`; **bounded, the R1 +76 guard**) and `needs.opponent_target_value` (ruling 1
  — `prize_advance + phase × survival_shift`, survival sub-prize-capped). The survival term is grounded in
  the S1 curve: `CombatMath.turns_to_ko_me` (the survival-window inversion — `min t : incoming(t) ≥ my_hp`),
  so `survival_shift` = the turns bought by removing a body. `Pilot._opponent_target_shadow` →
  `Decision.opp_target_shadow` → telemetry emits the per-opponent-body removal value, **deciding NOTHING**.
  Tests `tests/strategy/test_opponent_target_value.py` (phase bounds+monotonic, the two-term composition,
  `turns_to_ko_me` + survival_shift, the shadow emit). Full core suite green (pending). Seeds are
  grill-/ladder-matured; redundancy (ADR-0044) + instrument specifics (chip vs KO, reachability) are
  swap-time. **The `opp_target_shadow` sweep (gitignored corpus) is the adjudication input for S3b.**
- **S3b — the opponent-target SLOT in `needs.py` + the assignment fold (NEXT).** Add the slot family to `needs.py`
  (generalize `deny_slot` to `snipe` / `gust` / `promo_chip` instruments over opponent-target slots, valued
  by the two-term sum with the phase-scaled exchange). Resolve it once per decision, cache it, and emit
  **each instrument's marginal slice** beside its real snipe/gust/deny decision as a shadow (the seam-D
  pattern, ADR-0065; the deny-slot / WP-N7 precedent). First corpus sweep over the 23 DAMAGE frames
  (`snipe_sweep`) + the gust frames + the Hammer frames — localize disagreements, adjudicate frame-by-frame
  with the user (the WP-N8 currency grill). **Acceptance = byte-identical on the 16 passing snipe role reads
  + fix the ruled threshold-race** (`83667237-107`), hold the deny 5/5 (ADR-0062) and the gust frames.
- **S4 — the decider swaps, per instrument.** Each doctrine's target pick swaps to read its instrument's
  slice out of the shared assignment: deny first (already a slot — the shortest hop), then snipe (its rungs
  → the marginal; the ADR-0065 snipe fold), then gust. **Gust is merged to main** (user; PR #128/#129) — so
  gust folds INTO the assignment as a behavior-preserving lift: the merged prize-denominated SUM (see "The
  merged gust value" — NO `return_threat` term) becomes the gust instrument's marginal, and
  `_gust_target_tactical` re-reads it. Each swap a PROFILE kill-switch, OFF byte-identical (`develop_rollout`
  / seam-D precedent). **`return_threat` is NOT here** — it is S5.
- **S5 — the decline-a-prize gate (ruling 6).** The riskiest behavior, LAST, behind its own kill-switch
  (ADR-0045 S4's `forgo_ko`, promoted from parked-OFF). The tight four-condition sound gate; any doubt →
  take the prize. Own bench: a captured can-KO-but-bad-trade anchor (Scenario B still lacks one — flag for
  capture) + the forgo-KO corrections.

## The merged gust value — the actual shape, and what it tells us (ruling 3; gust merged PR #128/#129)

Read at source on main (`doctrine_gust._gust_target_tactical`, 2026-07-22). The merged gust value is
**entirely prize-denominated**, and KO-gated:

```
gust_target_value = KO_SCORE + prize_value(target)
                  + _gust_target_denial      # a FULL prize for gusting a LIVE threat (energy/imminence read)
                  + _gust_forward_denial      # 0.5 — line becomes an attacker
                  + _gust_matchup_priority    # « 1 prize — ADR-0051 MatchupPlan target priority
                  + _gust_wincon_denial       # ~1.5 prizes — wincon line/pre-evo, γ-scaled
                  + _gust_energy_denial        # « 1 prize — sunk Energy destroyed (ADR-0062 strip, across the table)
                  + _gust_snipe_synergy        # +1 prize — gust enables a second snipe-KO
     (fires only when my Active CAN KO the gusted target — _gust_can_ko gate)
```

**There is NO `return_threat` subtraction term.** The coverage review's shorthand
`gust value = KO_prizes + tempo_denied − return_threat` was the *design* description; the built code has the
`KO_prizes` term (full) and the `tempo_denied` terms (the denial tie-breaks, all in prize-equivalents,
capped < 1 prize so they never override a real prize gap) but **not** the `return_threat` — that is
Scenario B (the bad-trade gust where a full-health attacker promotes back), which the coverage review says
**has no corpus anchor and is unbuilt**. (My earlier "hasn't propagated" caveat was wrong: the code IS
present on my base; the term simply was never built.)

Two things this settles for the unification:

1. **The currency is ONE prize scale, not two loose terms.** The gust already expresses the tempo/denial
   half as **prize-equivalents** (sub-prize tie-breaks), not as a separate turns count. So ruling 1's
   "two-term sum" is, in practice, `prize_advance + survival_shift→prize-equivalents`, and ruling 5's
   phase-scaler is exactly the converter (`survival_shift × phase_scale` yields prize-equivalents). The
   merged gust is the codebase VOTING for this denomination — the unified marginal denominates in prizes,
   and every tempo/denial sub-term is capped < 1 prize unless it is a real prize (KO / wincon-line).
2. **`return_threat` / decline-a-prize is genuinely NET-NEW — it belongs to S5 (ruling 6), not S3/S4.**
   The merged gust is a *KO-target ranker* (which KO-able body to drag), not a *whether-to-gust-when-the-
   trade-is-bad* read. Folding gust into the assignment (S3/S4) is a behavior-preserving lift of the SUM
   above; the `− return_threat` bad-trade is added later, once, as the shared decline-a-prize gate (S5),
   for gust AND snipe AND forgo-KO at the same time — which is precisely the unification's payoff (one gate,
   not a gust-private term).

**Build consequence:** the gust instrument's marginal in the S3 slot family is the merged SUM above, lifted
from `_gust_target_tactical` into the shared assignment as prize-equivalents; snipe and deny fold to match
this prize denomination. `_gust_target_tactical` becomes a consumer of its own slice (ADR-0065 "doctrine
stays the decider, reads the shared backend") — behavior-preserving, benched on the gust corpus frames
(`86089120-14`, `85163079-30`, `85785067-41`, `85164131-22`).

## Open questions / risks

- **O1 — assignment vs primitive. RESOLVED: the assignment (Option B; user, 2026-07-22).** The Layer-2
  marginal is one board-wide Needs slot assignment (opponent bodies as slots, the deny-slot generalized to
  every removal instrument — snipe / gust / Hammer / promo-chip), so all instruments are priced *together*
  in one marginal pass. Rationale: the deny-slot is already in the assignment, and the interactions
  (no-double-spend, KO-reprices-neighbor, sequencing) that a per-doctrine primitive would have to hand-code
  fall out of the marginal for free. The counter-argument (the instruments fire in different SelectContexts
  — DAMAGE 15 / SWITCH / DISCARD_ENERGY 30 — so they rarely collide in one *select*) is answered by the
  assignment being resolved once per DECISION and cached (the `_opp_attack_context` stash precedent): each
  select then reads its instrument's slice out of the shared plan, so the plan is coherent across the turn
  even though the engine asks about the instruments separately. **Consequence for the staircase:** S3's
  shadow emits the assignment's per-instrument marginal (not a standalone value), and S4 swaps each
  doctrine to read that slice.
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

## Progress & next step

**S1 landed (2026-07-22, all behavior-neutral, full core suite green ~2976):** S1a the `incoming(t, policy)`
curve primitive (`reachable_incoming` delegates, byte-identical); S1b the doom SHADOW
(`combat.doomed_incoming` + `Decision.threat_shadow`, deciding nothing — its known divergences pinned);
S1c the board-clock one-home extraction (`combat.turns_to_afford`, `_opp_turns_to_ready` delegates,
byte-identical). The Threat Clock's two legs (damage curve + affordability clock) now live in one home on
`CombatMath`, policy-parameterized.

**Next, in order:**
1. **The S1b corpus sweep** — run the doom `threat_shadow` agree bit over the corrections corpus (needs the
   gitignored `data/meta/`) to quantify the doom divergence; that adjudicates the survival swap (S1's tail).
2. ~~**S2 — the discard-fuel read**~~ **DONE (shadow):** `discard_recur_fuel` + `recur_shadow`. Sweep it
   (gitignored corpus) to size the fuel's clock effect before any adoption; conservatism note in the S2 bullet.
3. **S3 — the opponent-target slot family** (`needs.py`): snipe/gust/deny/promo-chip as slots on one
   assignment (O1 = Option B), modeled on the merged gust prize-denominated marginal. Shadow, then S4 swaps.
