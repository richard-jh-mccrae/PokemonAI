# ADR-0079 — The deploy marginal prices a bench slot and what fills it

**Status:** DRAFT — grilling in progress (`/grill-with-docs` on Issue #197, 2026-07-29). Decisions are
recorded here as they lock; nothing below is built. **Expect renumbering at merge** (#136 directive 8 —
0079 is claimed, not settled; ADR-0078 is itself claimed-not-merged on the Issue #199 line).

**Context issues:** Issue #197 (this grill — split out of the Issue #161 grill as the pregame-Bench
half), Issue #161 (`starter_priority`, the Active-slot sibling), Issue #136 (the Value System build
tracker), ADR-0069 (attach, Phase 1a — the axes-sum shape this follows), ADR-0070 (evolve, Phase 1b),
ADR-0073 (promote/retreat, Phase 1c — `PRIZE_DAMAGE_RATE`), ADR-0065 + ADR-0076 (the Needs assignment
this extends), ADR-0078 (the currency triangle), ADR-0034 (deck rules fold general when the vocabulary
is general), ADR-0072 (the gates a decider swap owes).

## Context

Issue #197 was opened as a narrow question — does the *pregame* bench placement (`_SETUP_BENCH`,
SelectContext 2) want a deck declaration the way the Active slot got one in Issue #161? The grill
widened it on the user's framing: **bench filling is not a setup event, it is a whole-game decision**,
and the interesting cases are mid-game.

Facts established at source before the first ruling (2026-07-29):

- **Meowth ex (1071)** — Basic, 170 HP, `{C}`, weakness `{F}`, retreat 1, **2 prizes**.
  *Last-Ditch Catch*: "**Once during your turn, when you play this Pokémon from your hand onto your
  Bench**, you may use this Ability. Search your deck for a **Supporter** card, reveal it, and put it
  into your hand. Then, shuffle your deck. **You can't use more than 1 Ability that has 'Last-Ditch'
  in its name each turn.**" *Tuck Tail* `●●●` 60 puts the body and all attached cards back into your
  hand — so a benched Meowth is **re-armable** for a later second fetch
  (`data/EN_Card_Data.csv`).
- **Set Up precedes the first turn** (`docs/rulebook.txt` L110–122), so "once during your turn" is
  structurally unsatisfiable at `_SETUP_BENCH`: pre-benching Meowth genuinely burns the Ability.
  The Bench holds **5** (L75, L122); benching Basics from hand is unlimited per turn and order-free
  (L120–122), so a bench drop is a **Commutative Set** member, not a Maneuver.
- **The bench slot is unpriced today.** Every bench rule gates on `c.board.my_bench < _BENCH_MAX`
  — a hard binary — and `Board.bench_full` is a boolean. The 5th slot costs exactly what the 1st
  costs: nothing.
- **Meowth's bench drop is mis-modelled as development.** `bench-the-supporter-tutor` (+25,
  `doctrine_fetch.py`) is gated on `not board.line_ready` (i.e. SETUP) **and**
  `board.no_supporter_in_hand` — so it cannot fire mid-game for a *specific* Supporter while any
  Supporter at all sits in hand. The value of the drop is a **fetch** value, not a development value.
- **The rule layer shows the diagnostic symptom of an unpriced resource:** three separate NEGATIVE
  rules exist only to veto deployments a slot price would have out-ranked on its own —
  `dont-pre-bench-the-supporter-tutor` (−15), `dont-pre-bench-a-redundant-utility` (−15),
  `dont-bench-multiprize` (−15) — alongside seven flat-weight rules in `baseline_bench.py`.
- **#197's "no motivating frame" premise is false.** `ml_dont_bench_redundant_solrock_f51` is a
  CRITICAL correction naming exactly the slot-scarcity defect: *"played a 2nd Solrock into the last
  bench slot … clogs the bench needed for the Makuhita→Hariyama line."* None of the three vetoes
  caught it, because the defect was the **cost of the last slot**, not the identity of the body.
  Supporting frames: `dp_dont_pre_bench_redundant_munkidori_f4`,
  `ml_dont_play_a_needless_pokemon_tutor_f114`, `ms_free_bench_evolve_f17`,
  `setup_bench_decline_f3` (the already-solved pregame Meowth case).
- **`supporter_tutor` is absent from `needs.SUPPLIES`**, so a bench-drop tutor has no slot kind to
  fill and no route into the Needs assignment.
- The Value System has per-seam equations for attach (1a), evolve (1b), promote/retreat (1c) and the
  opponent-target family (1e). **There is no deploy/bench phase.**

## Decisions

**1. Bench/deploy becomes the missing per-seam value equation — the Deploy Marginal — not a rule
repair and not a deck declaration.** *(User ruling, 2026-07-29.)*

One equation answers "what is putting THIS body into a bench slot worth, right now?", denominated in
the same damage currency as ADR-0069/0070/0073, and it DECIDES (no shadow staging — #136 directive 1).
It spans the whole game, not the pregame: the setup placement is simply the case with the longest
deadline and no Ability trigger. The flat rules it replaces are DELETED, not suppressed — the seven
`baseline_bench.py` Hypotheses plus `bench-the-supporter-tutor` /
`dont-pre-bench-the-supporter-tutor` / `dont-pre-bench-a-redundant-utility`.

Rejected alternatives:

- *A targeted rule-layer repair* (a bench-pressure signal + a sharpened `supporter_tutor` gate). Buys
  a fourth veto and leaves the currency problem: f51's defect is not expressible as a weight on a
  body, because it is a property of the SLOT.
- *A deck-declared `Strategy.bench_priority`* (Issue #161's sibling). Hardcodes per deck what is plainly
  general vocabulary — Roles, Function Tags, Needs slots, prize value — which ADR-0034 says folds
  general. It would also have to be re-declared for every future deck, and it cannot express
  "bench Meowth *this* turn because *this* Supporter is now needed."

Consequence for Issue #197's stated agenda: its item 3 ("the two-vocabulary cost" of a declaration for
the Active slot and derived rules for the Bench) is **superseded rather than answered** — the Bench
gets an equation, so the asymmetry with Issue #161's `starter_priority` becomes deliberate, and item 4's
shared-completeness-invariant question falls away with it.

Cost accepted with the ruling: this is a Value-System decider swap and owes the full ADR-0072
gauntlet (a `deploy_decider_sweep.py` Decision Gate with zero unruled REGRESSIONs, the Discrimination
Gate against `data/leaf_lab/baseline.json` run BEFORE the arming decision, and the mid-build
Tripwire A/B), its own glossary entries, and a sequencing decision against the in-flight
Issue #199 → Issue #187/#188/#189 chain.

**2. The slot cost is an EXACT ASSIGNMENT over deck-reachable suppliers — never a constant, never a
binary gate.** *(User ruling, 2026-07-29.)*

The Bench is five deadline-tagged slots in the `needs.py` slot family (ADR-0065's DP, as extended to a
second family by ADR-0076). The **supplier set** is the deployable bodies in hand **plus** the bodies
reachable from deck, read through `fetch_closure`'s **reach** direction (ADR-0073) and weighted by
Deck-Content Odds. The marginal is a difference of assignment values —

```
deploy_marginal(X) ⊃ − [ assignment_value(suppliers) − assignment_value(suppliers, X pinned) ]
```

— so the cost of the 5th slot is **emergent**: exactly the contribution of the supplier it displaces.
Zero on an empty Bench, steep on a full one with live candidates, and it needs no tuned constant. The
`my_bench < _BENCH_MAX` binary gate and `Board.bench_full` as a decision input both retire (the engine
still won't offer an illegal placement; that is the engine's job, not a weight's).

The deck leg is load-bearing rather than incidental. On the motivating frame the displaced body is
**Makuhita, in the deck** — reachable via the Ultra Ball in hand — and the human's recorded reason is
literally *"clogs the bench needed for the Makuhita→Hariyama line."* A hand-only supplier set prices
f51's last slot at ~0 and would leave the slot term untested by the only evidence there is for it.

Alternatives rejected, and why the frame does not settle it by itself: **f51 admits two independent
diagnoses.** The 2nd Solrock is also *redundant* (Solrock + Lunatone already in play; the readiness
leaf's `_READINESS_SATURATED` prices a duplicate utility body at 0.1×), so a body-side-only equation
(*option 3: no slot term*) and a hand-only assignment (*option 2*) BOTH land the right answer on that
board — for a reason the human did not give. That is the weight-coincidence pattern ADR-0069 catalogues
(the desperation attach that lived at `+15 − 12 = +3`). Only the displacement reading generalizes to
the case the user raised — filling every Bench slot with a *suboptimal combination* — because a bad
combination is one where every body looked fine individually and the SET was wrong, and only an
assignment sees sets.

Costs accepted with the ruling: the term reads a hidden zone, so it owes ADR-0077 **Leg Assignment**
discipline (this is a RANKED consumer, so a count question reads `expected` and a presence question
reads `p_any`; it may never read either as a gate); it adds a `fetch_closure` reach query to the
deploy path; and the supplier set needs an explicit cap, since the DP is `_MAX_KEEP_SLOTS`-bounded
at 16.

**3. A bench-drop Ability is valued as its NEED-MATCHED fetch yield — odds-weighted, quota-aware, and
structurally zero where the trigger cannot fire.** *(User ruling, 2026-07-29.)*

`supporter_tutor` joins `needs.SUPPLIES`, and the drop's Ability leg is

```
ability_yield = max over Supporter classes reachable in deck of
                  [ needs marginal of that class into the LIVE assignment ] × P(class still in deck)
```

— reusing the `fetch_closure` **reach** query and Deck-Content Odds decision 2 already brings in. The
downstream *which Supporter* pick is NOT this equation's: Meowth ex is tagged `["search",
"supporter_tutor"]` and the resulting `_TO_HAND` select is already owned by the Fetch Doctrine. The
deploy marginal owes only the ESTIMATE at drop time — the same shape as ADR-0069 decision 2's
`this_turn` counterfactual.

Three riders fall out as arithmetic instead of gates:

- **Quota-aware.** One Supporter per turn (`rulebook.txt` L133), so a fetch made after
  `supporterPlayed` banks for NEXT turn and takes the standard one-turn discount. This is the
  precision `board.no_supporter_in_hand` structurally cannot express — it is silenced by ANY Supporter
  in hand, so today the agent can never dig for the *specific* one.
- **"You can't use more than 1 Ability that has 'Last-Ditch' in its name each turn"** is a card fact
  the equation reads: a second Meowth dropped the same turn credits ZERO Ability yield and is judged
  purely as a 2-prize body eating a slot.
- **Zero at `_SETUP_BENCH` by DERIVATION.** Set Up precedes the first turn, so "once during your turn"
  is unsatisfiable and the yield term is 0 there. This is what makes
  `dont-pre-bench-the-supporter-tutor` (−15) *deletable* rather than replaced: the existing
  `setup_bench_decline_f3` test re-passes as a consequence of the equation, not of a hand-placed
  weight.

The live defect this repairs, beyond the pregame case: `bench-the-supporter-tutor` is gated on `not
board.line_ready` — SETUP only — so the agent **cannot** bench Meowth mid-game to dig out the
Boss's Orders that wins the turn, however badly it needs it.

Cost accepted: this is the most expensive read in the equation (a closure query plus a needs
re-assignment per candidate Supporter class, several times a turn). It wants memoisation on the
`SideState` per ADR-0068's lazy-field pattern, and it will move the **Leaf Profile** field-set pin —
which is exactly what that pin exists to force.

**4. The Worth→damage conversion is Issue #199's shared rate. This phase is a CONSUMER of S3c and is
sequenced behind it; it does not mint its own.** *(User ruling, 2026-07-29.)*

Decisions 2 and 3 both yield **Worth**-denominated quantities (`needs.py` assignment values in
`ROLE_TIER` / `TAG_TIER` / `ENERGY_TIER`), while the Deploy Marginal must compete on the **damage**
scale — against `_finish_turn_last`'s floor, against the attach and evolve marginals, under
`KO_SCORE`. That is one crossing of the scale boundary ADR-0078 governs, so the **Worth Damage Rate**
is imported from `common/currency.py` (the home ADR-0078 decision 2 creates), and this phase joins
Issue #187 / #188 / #189 as a fourth consumer of S3c.

Rejected: a deploy-local rate (mints a rival for the same conversion — the exact incoherence ADR-0078
found and refused to guess past, with ADR-0073's `_PRIZE_UNIT = 12`, wrong by ~8×, as the standing
example of the cost), and routing the assignment through the damage-native readiness leaf instead of
the Worth scale (it prices the slot-displacement leg cleanly but leaves decision 3's Ability leg
homeless — pricing a HAND card through a board-evaluation leaf is the mismatch `needs.general_worth_slot`
was created to fix, WP-N5).

**Contribution, not just consumption.** ADR-0078 decision 3 records that S3c's blocker is an anchor:
every committed deny fixture is a `context = 0` play/hold frame and **not one is a DISCARD select**,
which is why deny cannot anchor itself. The deploy seam's frames are natively play-side, so its
corpus joins S3c's anchor sweep. Whether any of them DISCRIMINATE the rate is a measurement to run,
not a claim made here.

**Schedule consequence, accepted:** the build does not start until Issue #199 lands, and Issue #199's
own step 1 is an adjudication session with the user rather than a computation. Per #136 directive 2,
ladder-performance risk is accepted. **Issue #197 therefore becomes the grill record, not the build
ticket** — the build is a new tracker phase filed blocked-by Issue #199.

**5. Prize exposure is the PRIZE-PATH DELTA as a magnitude, not a flat liability.** *(User ruling,
2026-07-29.)*

```
exposure(X) = ( their_path_turns(board) − their_path_turns(board + X) )
              × PRIZE_DAMAGE_RATE × needs.phase_scale(...)
```

The magnitude is **already computed and discarded today**: `_bench_shortens_their_path`
(`objectives.py:564`) builds the hypothetical board with the candidate body added, calls
`prize_paths()` for `new_turns`, compares it against `board.their_path_turns`, and then returns
`new_turns < old_turns` — a boolean, consumed by a flat −10. The change is to return the delta
instead of its sign.

Reachability is sharpened by feeding it `CombatMath.bench_harvest` (ADR-0071, **built**), which models
the opponent's bench riders as ONE shared budget — attacking ends their turn, so a turn's bench damage
is one attack's riders — rather than the per-body `_their_turns_to_ko` read the path currently uses.

This folds BOTH surviving exposure rules into one derived term: `dont-bench-multiprize` (−15, flat and
reach-blind) and `dont-bench-onto-their-path` (−10, the discarded magnitude).

Rejected: a **harvest-delta-only** exposure (correctly shared-budget and reading-independent — the
delta of an optimum VALUE needs no `POSSIBLE`/`UNAVOIDABLE` declaration, since that names which bodies
achieve it — but it sees only bench-RIDER reach, so it prices a second Mega ex at zero against an
opponent who simply gusts it up and knocks it out, which is how multi-prize bench liabilities are
actually collected); and a **flat** `prize_value × PRIZE_DAMAGE_RATE × phase_scale`, which preserves
today's blindness in a new currency.

**Structural consequence, and the reason the equation is one thing rather than three bolted terms:**
decisions 2, 3 and 5 now share one shape — *a difference of two optimal values under a hypothetical
board change* (the displaced supplier, the fetched Supporter, the shortened path).

Costs accepted: `bench_harvest` returns only the index frozenset, so the objective's prize total
(`_harvest_optima`'s `best_key[0]`) needs a sibling accessor; the Prize-Path re-derivation now runs
per deploy OPTION rather than once per decision (ADR-0040 calls it "small by construction" —
subset-sums over ≤6 bodies — but it multiplies against decision 3's closure query on the same path);
and the term inherits the `objectives_path` kill-switch, so it needs a defined value when that flag
is off.

**Observation handed to the build, NOT ruled here:** `_PATH_BENCH_EXTRA = 1` (`objectives.py:124`)
charges a benched body a flat extra turn "to bring into KO range", while ADR-0071 decision 6 corrected
exactly that reasoning on the Threat Clock (retreat is paid in Energy, not a turn, so a benched
attacker is an AFFORDABILITY gate, not a +1). Whether the Prize Path's copy of the surcharge is
likewise stale is worth checking when this term is built.

*(Further decisions appended as they lock.)*
