# Promote / retreat — the prize-trade differential (design SETTLED 2026-07-22)

**Status.** DESIGNED — grill closed 2026-07-22 (six rulings, §Settled design below); NOT yet built.
The shadow ruling (`docs/plans/shadow-equations-ruling.md`) applies: the equation ships as a SHADOW
emitter beside the promote ladder regardless of how many corrections the ladder already satisfies;
swaps stay corpus + score-diff gated. Supersedes the attach spec's "sibling consumer" paragraph,
which under-called this family as "a cheap composition of two existing oracles" — the user's
counterexamples (below) refute that: readiness is hand-AND-closure aware, and the value is a TRADE
over an exchange window, not a single-body score.

The original SEED (musing, hypothesis, inventory, grill agenda) is preserved below §Settled design
as provenance — read the settled section first; the seed's open questions are now answered there.

---

## Settled design (grill closed 2026-07-22) — scoped to the RETREAT/PROMOTE decision

Walked the retreat/promote correction family (52 flavoured corrections) against the seed equation,
one disagreeing frame at a time. Six rulings settle the design and, as importantly, settle the
**scope** — most of the family is owned by tiers ABOVE the value equation.

### The decision stack (what owns retreat/promote, top to bottom)

| Tier | Owner | Fires when | Corpus anchors |
|---|---|---|---|
| 0 | **Lethal solver** (turn player) | retreat unlocks a **provable match win** (`deck_definitely_has` + engine-confirmed) — it **takes over** and preempts the equation | `84071010-15` (`retreat_enabler_lethal`) |
| 1 | **Turn planner** (`ko_for_prizes`) | retreat unlocks a **provable KO / multi-prize** sequence THIS turn | `83053965-32/-48`, `82224509-41`, `82226116-48/100`, `83455356-11`, and the live gaps `82751468-14`, `83007714-92` |
| 2 | **Retreat value equation** (THIS doc) | everything else — **uncertain / positional** value | Groups A, B, D, E below |

The stack IS the speculation cap: the equation never multiplies "win = game" (or a certain KO) by a
soft probability, because those branches are handed UP to certainty-gated / engine-verified owners.

### The equation (tier 2), fully specified by the rulings

```
retreat_value(B) = window-rollout diff  { A active, B benched }  vs  { B active, A benched }   (ruling 2: option b, two-sided)
                                         take the max; the FORGONE ATTACK of the current Active
                                         is the A-side of the diff, NOT a separate term (ruling 1)

   my_yield(B)     = EV over closure of SUB-LETHAL outcomes only                                (ruling 3: expected value, NOT fail-closed)
                     { stall, chip, charge-up DIVIDEND, sub-lethal KO }                          (rulings 4/5: win→solver, provable KO→planner, so
                     via the gamble Outcome-Class machinery (_gamble_ko_classes /                 they are absent here by construction — no P·win)
                     _fetch_reaches_slot) pointed at the promote target; P(fetch) from
                     deck_odds + fetch_closure

 − their_yield(B)   = prize_value(B) × P(they KO B) × prize-map asymmetry                         (threat_turns / prize_paths / opp_prizes_remaining)
                     + TEMPO-DENIED: Δt(their Threat-Clock curve shifts right) × opp_prize_rate,  (ruling 6: retreat-as-disruption / item-lock
                       bounded by opp_prizes_remaining                                             folds in as reduced opponent whole-window yield)

 − retreat_cost     = Energy paid to retreat, priced via card_worth
```

### The six rulings (user, 2026-07-22)

1. **Forgone attack is an opportunity-cost SUBTRACTION inside the differential, not a hard veto.**
   Collapses Group A ("don't retreat, A can attack") and Group C ("do retreat, the destination
   out-earns A") into ONE term: retreat wins iff the destination clears `my_yield(A, stay)`. One
   veto dies, one term is born.
2. **Retreat MUST consider the opponent's side → option (b): the two-sided window-rollout diff**
   (not the per-turn shortcut, which double-charges the deferred-not-destroyed attack). Buildable
   NOW at the 1-exchange window on the merged `objectives.py` arithmetic (`threat_turns`,
   `prize_paths`, `race_values`; PR #128/#131, main).
3. **Readiness leg = EXPECTED VALUE over closure**, not the fail-closed floor. Reuses the gamble
   Outcome-Class machinery but keeps it probabilistic; `P(fetch)` flows in from Odds + Closure.
4. **The retreat-to-WIN branch is the lethal solver's, which takes over.** The equation never prices
   it → no `P·win`. The speculation hazard EV opened is capped structurally at the lethal boundary.
5. **The provable retreat→KO / multi-prize branch is the turn planner's (`ko_for_prizes`),** same
   shape as ruling 4. Group C re-classifies OUT of the equation as planner-sequencing gaps.
6. **Retreat-as-disruption (item-lock, free-pivot) and `disruptor_lock_maneuver` fold INTO the
   equation** as a tempo-denied term in `their_yield` (same currency), NOT a separate axis. The
   fold replaces `disruptor_lock_maneuver`'s SHIP-AND-REFINE kill-switch with a computed trade:
   `tempo_denied − prize_value(fragile Budew) × P(they KO it)`.

### Two curve terms declare a Threat-Clock dependency (the single clean deferral)

`my_yield`'s **preservation dividend** (my bench charges faster — Cinderace's 3/turn onto the Mega)
and `their_yield`'s **tempo-denied** (their curve slips under a lock) are MIRRORS: my curve up vs
their curve down, both over the N-turn window. Both are buildable only as an **immediate 1-exchange
slice now**; their full N-turn form BLOCKS on the unified Threat Clock
(`threat-clock-unification-handoff.md`, `incoming(t,policy)` for t>1). Everything else ships at
1-exchange.

### Round-0 corpus classification (retreat/promote family)

- **A — forgone-attack ("don't retreat, attack"):** `86090164-52/67`, `81904451-17`, `81905063-16`,
  `81906755-9`, `82867148-62`, `81785223-12`, `81905522-10` → priced by the window diff's A-side; NO
  separate veto. (`86090164-67` "insanely retreat happy" is the headline live flag.)
- **B — readiness (equation `my_yield`):** `82753102-120` ✓ WALKED — Cinderace-over-Staryu holds on
  band value alone; the speculative "retreat-to-win if I draw Ignition" is NOT banked (ruling 4) and
  the pick survives without it. `83007714-104` — same-prize (both Mega ex) so `their_yield` equal →
  pure `my_yield` readiness; should be covered by `promote-the-ready-wincon +40` per-option (RETEST).
- **C — provable KO seq → PLANNER, not the equation:** several already `covered` via `ko_for_prizes`
  (`83053965-32/-48` etc.). Live planner-sequencing gaps to hand to the planner session:
  `82751468-14` (flat 4-way attach tie), `83007714-92` (retreated into the dead Cinderace, not the
  430/3⚡ Hero's-Cape Mega that KOs).
- **D — target / prize-map (`their_yield`):** anchored by the `dont-promote-into-their-prize-reach`
  family (spec's four stand-downs, `bench_wincon_prize_value`) — real, but never the SOLE decider in
  an anchored 1-exchange frame. `85164131-22` re-classed OUT to the snipe system (a `Damage`-context
  snipe-target pick, not a retreat).
- **E — disruption (folded into `their_yield`, ruling 6):** `85046350-20` shipped
  `disruptor_lock_maneuver` (kill-switched); live gaps `86091435-20` (retreat→Budew→item-lock),
  `85709280-42/55` (Air Balloon free-pivot). Proposal seed: `capability-gap-retreat-to-item-lock.md`.

### Build shape (supersedes the seed's §Build shape)

Phase 1 — the **1-exchange two-sided shadow**: `my_yield` (EV-over-closure sub-lethal band via the
gamble Outcome-Class) − `their_yield` (prize-map + immediate tempo-denied slice) − retreat_cost,
emitted per promote/retreat option beside the ladder, with the agreement bit. Wins/provable-KOs are
handed up (tiers 0/1) and MUST be absent from the shadow. Phase 2 — staged swaps by Round-0 +
shadow-disagreement ranking; preserve `disruptor_lock_maneuver`'s kill-switch as a floor and re-audit
the `test_blunder_20260710_split_fixes.py` pins. Phase 3 (BLOCKED on the Threat Clock) — extend the
two curve terms (preservation dividend, tempo-denied) from the 1-exchange slice to the N-turn window.

### Build status — the shadow is BUILT (as of 2026-07-22)

`common/promote_retreat_value.py` (pure equation) + `pilot._promote_retreat_shadow` (wiring, emitted
REPORTING-ONLY on `OptionTrace.promote_retreat_shadow`). Tests: `tests/strategy/test_promote_retreat_value.py`
(14 unit, the six rulings) + `tests/strategy/test_promote_retreat_corpus.py` (3 corpus frames — f120/f104/f92
ranked correctly through the live Pilot). Built incrementally:

- **my_yield / their_yield / tempo-denied / retreat_cost** — wired to the Context flags the ladder reads
  (1:1). Readiness is sourced off the option body (`_promote_can_attack`), NOT the TO_ACTIVE-scoped
  `ctx.promote_target_can_attack` — a fix for the readiness leg being dead on SWITCH retreats (found by
  the f92 corpus test).
- **stay_yield + retreat cost** — the voluntary-retreat side (`_retreat_side`): the Active's forgone
  sub-lethal attack priced by the SAME my_yield term (ruling 1), and its retreat Energy via `card_worth`.
- **fetch_enables_p (ruling 3, EV over closure)** — INTERIM: the CERTAIN one-attach-short accel case only,
  reusing the body-agnostic `_active_attack_payable_via_accel` (the f70 machinery) pointed at the promote
  target → 1.0/0.0, fail-closed. The probabilistic MIDDLE (drawing a not-yet-held enabler over the turn's
  remaining dig) is DEFERRED to the shared **self reachable-attach affordability oracle** (the f70 finding
  in `valuation-systems-coverage-review.md`, symmetric to ADR-0064 `reachable_incoming`) — a shared build
  that also serves stall-gust/posture/doom. Point `fetch_enables_p` at it when it lands.

Still deferred (unchanged): the two N-turn curve terms (preservation dividend, tempo-denied) block on the
unified Threat Clock; the SWAP (retire the rungs) blocks on the shadow-disagreement corpus sweep.

### Sweep #1 — offline disagreement sweep (2026-07-22)

Telemetry wired (`Decision.promote_retreat_shadow`, the FIFTH shadow, emitted in `telemetry.py` beside
discard/refresh/attach) + the reusable tool `tools/train/promote_retreat_sweep.py`. Replays every
RECORDED promote/retreat SELECT frame through a fresh Pilot; NO ladder submission. Results:

- **Only 10 promote/retreat SELECT frames in the whole corpus** — and **4 are Boss's-gust-target
  selects** (opponent bodies on a `_SWITCH`). The sweep **found + fixed a scoping bug**: the shadow was
  firing on gust selects (pricing the equation over the OPPONENT's body); now guarded by option
  ownership (`playerIndex == yourIndex`) — gust is the gust-value equation's turf.
- **On the 6 genuine own-promote/retreat selects: shadow AGREES with the shipped ladder 6/6, ZERO
  disagreements.** Consistent with Round-0's prediction (this family is the most-hardened; high
  agreement expected). No swap evidence yet, and no shadow bugs surfaced on these frames.
- **The load-bearing finding — the emission SITE.** The ~14 `bad_retreat` + the "insanely retreat happy"
  mass (Group A, ruling 1) are **not** body-PICK selects; they are the **whether-to-retreat** decision at
  a **MAIN** select (Play Switch / Retreat action vs Attack). The shadow emits only at the body-PICK
  (TO_ACTIVE/SWITCH), so **Group A is currently invisible to the sweep** — which is exactly why the
  corpus shows so few select-frames and agreement is trivially high. **Next build to make the sweep bite:
  a SECOND emission site** — emit `retreat_value` on the retreat ACTION option at MAIN, ranked against
  the attack sibling (the `stay_yield` subtraction becomes live there). Until then the swap stays
  un-evidenced, correctly.

### Sweep #2 — the whether-to-retreat site is live (2026-07-22)

Built the second emission site: `_promote_retreat_record` now dispatches on context — **pick**
(TO_ACTIVE/SWITCH) and **whether** (MAIN with a native RETREAT option). The whether-site emits
`_retreat_action_value` = the BEST two-sided total over all benched destinations − retreat cost −
`stay_yield` (ruling 1 goes live), with a SIGN-agreement bit (retreat-worth-it vs did-the-ladder-retreat).
Sweep now covers **96 whether-frames** (vs 6 pick) — Group A is finally visible.

- **whether-site: 84/96 agree with the shipped ladder; 12 disagreements** — 4 shadow-fixes-ladder,
  8 shadow-regresses. Two real findings fall straight out:
- **Finding A — the tempo-denied term (ruling 6) OVER-FIRES.** 7 of the 12 disagreements are the
  dragapult `86091435-*` cluster, all at the SAME `value=27` — the item-lock credit fires **whenever a
  benched Budew exists**, unconditional of whether item-lock is worth anything THIS turn. It correctly
  catches `86091435-20` ("retreat into Budew, then item lock" — a genuine shadow-fixes-ladder) but then
  credits the same +27 on frames whose real play is an attach/ability (`-30/-35/-96`). **The tempo fold
  needs a gate:** credit item-lock only when the opponent actually relies on Items (early game /
  Item-dependent matchup), mirroring `disruptor_lock_maneuver`'s matchup-dependence. Top swap-staging fix.
- **Finding B — `stay_yield` under-counts a planner-tier forgone play.** The other regressions
  (`82749168-61`, `82750161-59`) are frames where the Active's forgone play is a KO / attach-to-KO —
  which is the PLANNER's tier (ruling 5), not the shadow's sub-lethal `stay_yield`. Consistent with the
  decision stack: those belong above the equation, so the shadow "regressing" there is expected, not a bug.
- **pick-site unchanged: 6/6 agree.** The swap still waits on tightening Finding A, then a re-sweep.

### Sweep #3 — Finding A fixed (2026-07-22)

Gated the `item_lock` credit (both its staller and tempo portions) on `board.turn <= _ITEM_LOCK_EARLY_TURN`
(=3) via `_item_lock_live`: Itchy Pollen denies the opponent's SETUP Items, valuable early, worthless once
they're built (the data: correct retreats at turn 2, over-fires at turn 4/6/12; the disruptor signals
were False on both, so game-phase is the real discriminator — a proxy for a future opp-Item-reliance read).

Re-sweep — the disagreement QUALITY improved (agreement held at 84/96, but the mix flipped the right way):
- **shadow-fixes-ladder 4 → 7; shadow-regresses 8 → 5.**
- The false `+27` over-fires (`86091435-30/35/96`, turn 4/6/12) now **agree** (worth_it False).
- **The headline: the gate surfaced the retreat-happy blunders.** `86090164-67` ("insanely retreat
  happy" — the complaint that opened this grill) flipped from shadow-WRONG (`+12`, sided with the
  over-retreating ladder) to **shadow-fixes-ladder** (`−20`, correctly don't-retreat); `86090164-52`
  ("don't retreat the Active that can KO") likewise. The equation now catches the exact pathology.
- **Remaining 5 regressions are Finding B** (development/KO forgone: `81905522-47`, `82749168-61`,
  `82750161-59` — the Active wants an ATTACH or has a planner-tier KO, which `stay_yield` doesn't price)
  plus two marginal (`value` 3–5). Finding B is the next lever: either a "stay to DEVELOP" term or accept
  they sit above the equation (the KO ones are planner-tier by ruling 5).

### Hazards (carried from the seed + added this session)

- Adding the positive tempo-denied term "silently voids guards calibrated against the old scale"
  (standing caution) — seed at the current partial order; keep the kill-switch as a floor.
- This family is ADR-0031/0044/0064-hardened with additive interactions (+50 stacking with +45) —
  re-audit surface is the promote/retreat pins across `test_blunder_*` + the ADR-0064 suite.
- Anti-speculation: high Round-0 pass rate expected; build the shadow anyway (the ruling), swap only
  measured failures first.

---

## PROVENANCE — the original SEED (superseded by §Settled design above; kept for the reasoning trail)

## The musing (user, 2026-07-19)

> "Which Pokémon to promote after an own KO depends highly on not only their readiness but also
> prize mapping. For example: a Cinderace with zero Energy — when we have 1 Energy or an Energy
> fetcher in hand — promoted after the 1st Mega Starmie is KO'd, even though a benched Mega
> Starmie WITH Energy is on the bench. Mega Lucario has similar combinations:
> Solrock > Lucario > Hariyama > Lucario."

Two deck-declared trade patterns: the 1-prize accelerator soaks while it CHARGES the bench
(Cinderace's Turbo Flare = damage + 3-Energy bench accel), and the alternating sacrifice ladder
(1-prize bridge → wincon strike → 1-prize trade star (210) → wincon).

## The hypothesis (the equation)

Promote value is a **prize-trade differential over the exchange window**, not survival × threat:

```
promote_value(B) = Σ over the exchange window t:
      my_yield(B, t)          ← B's fundable actions: damage/KO it can actually pay for on turn t
                                 (hand + CLOSURE + accel riders — the gamble's one-attach-short
                                 Outcome-Class machinery pointed at B), PLUS what B's tenure lets
                                 the BENCH develop (Cinderace: 3 Energy/turn onto the wincon — a
                                 development rate, the preservation dividend)
    − their_yield(B, t)       ← prize_value(B) × P(they KO B on turn t | ADR-0064 incoming),
                                 weighted by PRIZE-MAP ASYMMETRY: prizes near their goal cost
                                 super-linearly (their last prize is unaffordable — today's hard
                                 vetoes are the step-function version of this curve)
```

The Cinderace case falls out: zero on-body Energy but a funded Turbo Flare THIS turn (1 Energy or
a fetcher in hand — the closure) → high my_yield (attack + charges the Mega) at their_yield of
just 1 cheap prize; promoting the energized Mega instead zeroes the accel dividend and exposes
2-3 prizes to the ADR-0064 incoming. The alternating Lucario ladder is HYPOTHESISED to be
**greedy-emergent** — each promote re-evaluating the local differential reproduces the
alternation without a declared sequence (grill question §1; declare the residue only if
measurement refutes emergence).

## Inventory — this ladder is the most-hardened family; respect it (verified 2026-07-19)

`baseline_promote.py` (+ retreat cousins): `interpose-the-cheap-attacker-to-preserve-the-wincon`
(+50 — three drivers: weakness trade / **the Cinderace case verbatim**: `accel_source` +
`bench_wincon_underpowered` + `basic_energy_in_deck` / gust tax; HARD VETO at
`opp_prizes_remaining < 2`; stands down on `opp_cannot_punish_wincon`, ADR-0064 D4),
`promote-the-ko-attacker` (+45, attach-this-turn-aware KO), `promote-the-ready-wincon` (+40,
per-option best target — the f104 first-bench-slot blindness fix), `dont-promote-into-their-prize-
reach` (−20 — "make them take six individual prizes, not two Megas", four stand-downs),
`promote-the-staller` (+20), `dont-promote-onto-their-path`. The boolean gates already encode much
of the trade intelligence; the QUANTITIES are flattened to five fixed weights whose partial order
(+50 > +45 > +40 > +20 > −20) is the hand-tuned shadow of the differential.

**What is genuinely missing (the user's two points, made precise):**
1. **Closure-aware readiness.** `interpose`'s driver (b) checks `basic_energy_in_deck` and
   `promote_target_can_attack` checks attachable-this-turn — neither sees "an Energy FETCHER in
   hand" (Fighting Gong / Energy Search / Ultra Ball chains). The gamble's one-attach-short +
   closure-outs machinery (`_gamble_ko_classes` / `_fetch_reaches_slot`) is EXACTLY this quantity,
   already built, never pointed at the promote target. Correction `82753102-120` is the live
   evidence (a promote decided by what was NOT in hand).
2. **The prize map as a quantity.** Today: step-function vetoes at `opp_prizes < 2` and
   `card_prize_value >= opp_prizes_remaining`. The equation form: a goal-distance weighting on
   their_yield (super-linear near their goal), which also prices the MIDDLE cases the vetoes skip
   (opp at 3-4 prizes with a 2-prize body — currently unpriced).
3. **The preservation dividend as a rate.** The accel driver is a boolean; Cinderace's 3/turn vs
   Aura Jab's discard-recover vs nothing are different dividends — `_recover_units` computes the
   number already.

## Round 0 — measurement (fresh pilot per replay; join reviewed.json)

~31 trade-flavoured corrections (grep promote/sacrif/interpose/wall/trade in rationales) + the 14
`bad_retreat` + relevant `bad_target`. Exemplars: `83037962-70` (the user's Cinderace pattern,
human-praised in an OPPONENT: "they promoted Cinderace after a KO, that was smart"),
`82753102-120` (hand-aware promote), `83007714-104` (first-bench-slot blindness — check it's
covered by the per-option fix), `82751468-14` (attach → retreat → KO sequencing),
`83116081-76`. Classify: already-passing / readiness-leg / prize-map-leg / dividend-leg /
sequence-leg. This family's rationales cite many ml/ms fixtures — expect a HIGH pass rate; the
shadow ruling makes that fine (construction proceeds; swap priority follows the failures).

## Grill agenda

1. **Greedy emergence vs declared sequence.** Does the local differential reproduce
   Solrock>Lucario>Hariyama>Lucario on replayed boards? If yes, no sequence machinery — the
   alternation is emergent. If no, the residue is a deck-declared trade PLAN (Lines-style overlay,
   Tier-3 adjacency) — declare, don't derive.
2. **The exchange window.** One exchange (their next KO) or until the race flips? ADR-0064's
   incoming is one-turn; a multi-turn window needs the 2ply machinery
   (`2ply-opponent-survival-grill-spec.md`) — grill the smallest window that prices the examples.
3. **The prize-map curve.** Shape + where it lives (the equation's their_yield weight vs the hard
   rungs' jurisdiction — the horizon discipline says match-deciding stays with hard vetoes; the
   curve prices the BAND between).
4. **Readiness reuse.** Point the gamble's Outcome-Class assembly at the promote target (hand +
   closure + accel), fail-closed. This is shared machinery — no new closure code.
5. **Retreat's extra term.** Retreat COST (the Energy paid — worth via card_worth) and the
   retreat-blocked cases; `82751468-14`'s attach→retreat→KO shows sequencing coupling with the
   attach oracle (same currency, same trace).
6. **Fold/survive.** The five weights fold into the differential; the HARD vetoes survive as the
   step edges of the prize curve (or the curve subsumes them — grill); `dont-promote-onto-their-
   path` (information/tempo) likely survives on its own axis.

## Hazards

- This family is ADR-0031/0044/0064-hardened with additive interactions (+50 stacking with +45) —
  the re-audit surface is the promote/retreat pins across `test_blunder_*` and the ADR-0064
  scenario suite. Seed calibration at the current partial order (the ADR-0060 anchor pattern).
- The +76 shape: the preservation dividend is an endorser — cap it (a dividend can never exceed
  the preserved wincon's own worth × its deadline odds).
- Anti-speculation as amended: high Round-0 pass rate expected; build the shadow anyway (the
  ruling), swap only measured failures first.

## Build shape (per the shadow ruling)

Phase 1: the shadow differential, emitted per promote/retreat option (terms: fundable-attack
P, dividend rate, their_yield with the curve, the window) + the agreement bit. Phase 2: staged
swaps by Round-0 + shadow-disagreement ranking; the alternating-ladder emergence test decides
whether any sequence residue is declared. Coordinates with the attach oracle (shared readiness +
currency; retreat couples to attach sequencing) — likely the SAME grill session should own both
agendas' §readiness question.
