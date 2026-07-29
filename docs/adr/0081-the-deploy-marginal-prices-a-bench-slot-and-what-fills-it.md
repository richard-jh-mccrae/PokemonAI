# ADR-0081 — The deploy marginal prices a bench slot and what fills it

**Status:** Accepted (grilled 2026-07-29, `/grill-with-docs` on Issue #197 — **eight locked
decisions**). **Nothing here is built.** The build is a new Value-System phase (tracker Issue #136),
originally filed blocked-by Issue #199; that issue MERGED **without deriving the Worth Damage Rate**
(ADR-0080 ruled it moot for deny), which re-opened decision 4 (**Amendment A**). Decision 4 was then
**re-ruled** — the Worth legs are dimensionless RATIOS, so no rate is needed (**Amendment B**), with a
fixed yardstick and a preservation-pinned band (**Amendment C**). **The phase is UNBLOCKED.**
Decisions 1-3 and 5-8 stand as originally ruled. **Renumbered 0079 -> 0081 on rebase (2026-07-29)** — the SIXTH collision in the series (#136
directive 8). Issue #161's *the Set-Up Active pick is one deck declaration* merged first and KEEPS
0079 under the standing first-merged rule; Issue #199's *deny is a categorical relevance instrument*
took 0080. Cite the issue alongside the number ("ADR-0081, Issue #197") — the number is a rebase
artifact, not an identifier.

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

**6. ONE equation across all three Bench entry points; multi-picks resolve by the existing
greedy-with-gap-update.** *(User ruling, 2026-07-29.)*

The decider owns `_SETUP_BENCH` (2, pregame), `_PLAY` (7) at `_MAIN`, and `_TO_BENCH` (5, the
Poffin-class fetch straight onto the Bench). `_SETUP_BENCH` and `_TO_BENCH` are already members of
`_GRAB_CONTEXTS`, whose ADR-0023 contract is exactly what a marginal wants — *"single multi-pick
resolved GREEDILY w/ gap-update + take-fewer (not static top-N) so a satisfied need isn't
double-grabbed"* — because decisions 2/3/5 all re-derive against the live board: after pick #1 the
slot displacement is steeper, the Ability yield may be satisfied, and the path delta has moved. The
`minCount == 0` **take-fewer decline** survives untouched and is how a below-zero deploy expresses
itself, which is how `setup_bench_decline_f3` keeps passing.

**Issue #197's item 2 dissolves rather than being solved.** "Highest-ranked card present is
single-winner, the Bench is multi-pick" is a problem for a ranked DECLARATION (Issue #161's
`starter_priority` shape), which has no way to say "and now the second pick is worth less". A marginal
says it by construction.

A set-level search over the offered picks was rejected on the repo's own mechanical test (ADR-0070
amendment J): benching Basics is explicitly any-order and unlimited per turn (`rulebook.txt`
L120–122), so bench filling is a **Commutative Set**, and the ruling there is categorical — *"needs no
planner; the only way one can be missed is if an action is priced at or below zero. The fix is the
equation's price."* Since the drops commute, a set search can find nothing correct per-option pricing
does not already reach.

Also rejected: a mid-game-only decider leaving `_SETUP_BENCH` to the surviving rules. It re-splits the
seam decision 1 unified and re-creates Issue #197 item 3's two-vocabulary cost *inside* the Bench.

Cost accepted: the pregame board is information-poor — no `line_ready`, the opponent's Active face
down, Read γ ≈ 0, prizes hidden — so decision 5's exposure term is near noise at `_SETUP_BENCH` and
decision 3's odds read is at its widest. Covered by the standing fail-closed discipline (ADR-0069
decision 5): a term that cannot be computed contributes **ZERO**, never a guess. The consequence to
expect is that the pregame decision is carried almost entirely by decisions 2 and 3, with 5 ≈ 0.

**7. The empty-Bench guard does NOT fold into the marginal — it is a SOUND RUNG above it, scoped to
POST-SETUP contexts only.** *(User ruling, 2026-07-29, with the post-setup scoping as the user's own
refinement.)*

`keep-a-bench` (+60) is the one rule in the deletion list that guards a **win condition** rather than
expressing a preference: `docs/rules.md` §7 case 2 — *"Opponent has no Pokémon in play to replace a
KO'd Active."* An empty Bench under a KO'd Active is not a bad position, it is the game.

It therefore becomes an `empty_bench` **dominance rung** in the sound tier — Bench empty and a legal
Pokémon deploy available ⇒ that deploy is taken; the Deploy Marginal ranks only WHICH body. Two
independent arguments, the second structural:

- **Soundness discipline.** The repo is categorical: the Lethal Solver *"preempts every heuristic Turn
  Goal — no positional value can outrank it"*, and *"a phantom win loses the game."* The mirror
  obligation on the loss side has the same shape, and a weight cannot carry it because a weight can
  always be out-bid.
- **The band invariant.** `_LINE_CAP`'s comment records the design: *"max positional (readiness 300 +
  survival 50 + threat 100 + value 40 + line 100) = 590 < 1000 = KO_SCORE, so no path term can lift a
  positional board over a real prize."* A loss-avoidance value cannot be simultaneously bounded under
  1000 AND un-outbiddable, so it cannot live inside a bounded positional marginal — arithmetic, not
  taste.

**Scope: post-setup only. The rung does NOT fire at `_SETUP_BENCH`.** Verified at source
(`docs/rules.md` §2): the player going FIRST cannot attack on turn 1 (`rulebook.txt` L152,
PROJECT-VERIFIED ep81903490 f5), and the player going SECOND acts only after that turn — so in either
seat **my first turn precedes the first legal attack of the game**. Declining every pregame placement
cannot lose the game before I get a turn to bench. The converse is what makes the scoping mandatory
rather than merely safe: an unscoped rung fires at `setup_bench_decline_f3` — bench `[]`, Meowth ex
the sole option — and forces exactly the placement decision 3 derives us out of, overturning a ruled
corpus frame.

**Placement obligation:** today's rule scores a `_PLAY` option, but the sound claim is about the TURN.
The rung must also prevent `_finish_turn_last` from ending a post-setup turn with an empty Bench while
a deploy was available — one guard covering both the option score and the turn-end sequencing.

**Honest consequence for this ADR's scope claim:** the Deploy Marginal replaces **nine of the ten**
rules in the bench table, not all of them. The tenth is promoted, not deleted.

Rejected: folding the loss at ~6 × `PRIZE_DAMAGE_RATE` = 600 inside the marginal (sits INSIDE the
positional band, so a large readiness or exposure term out-bids it; raising it to compensate breaks
the <1000 invariant and lets a positional board outrank a real prize); and deleting it outright on the
theory that an empty Bench makes every deploy attractive anyway (unsound in the case that matters — a
3-prize body whose decision-5 exposure prices negative can still lose to `End`, ending the turn with
an empty Bench).

**8. `develop-the-accel-recipient` folds onto the ATTACH axis as a deploy counterfactual — not into
the `line` slot.** *(User ruling, 2026-07-29.)*

The value the rule expresses is not the recipient's own worth; it is the accelerator's yield that
currently has nowhere to land (glossary, **Acceleration Recipient**: *"With no recipient the
acceleration is wasted"*). So it is priced as

```
accel_unlock(X) = best_readiness(board + X) − best_readiness(board)      # re-read through the
                                                                        # Attach Budget (ADR-0067)
                                                                        # + Build Standing (ADR-0069 §3)
```

— literally ADR-0069 decision 2's `this_turn` counterfactual (*"best_dmg(B | Budget with E committed)
− best_dmg(B | manual leg unspent)"*) extended from an attach option to a DEPLOY option.
`develop-the-accel-recipient` deletes, and `board.accel_recipient_missing` retires as a decision input.

Three behaviours become derived instead of asserted: **zero** when the accelerator is not Active
(nothing to land), **zero** when the Budget already has a landing spot (the rule's hand-written
stand-down), and **proportional** — a 3-Energy Turbo Flare pays more than a 1-Energy trickle, which
the flat +20 cannot express.

Rejected: keeping it as an eleventh surviving rule (it is a pure VALUE claim, so unlike decision 7's
guard it has no principled exemption, and +20 is a coincidence with no referent); and folding it as a
tier bump on the body's `line` slot, which attributes the value to the wrong object and would keep
paying when the accelerator is benched, dead, or already supplied. That third option is ADR-0069 §3's
mistake in miniature — the retired `_attach_type_wasted` BOOLEAN was replaced by a typed FRACTION
exactly because a flag cannot express how much actually lands, and "has a recipient" is the same flag
standing in for a quantity ADR-0067 already computes.

## Consequences

**The equation.** Four value legs, all one shape — *a difference of two optimal values under a
hypothetical board change*:

```
deploy_marginal(X) =   BAND × ( net_assignment_relevance(X)   # decisions 2 + 4B, ONE netted marginal
                              + ability_relevance(X) )     # decision 3, the need-matched fetch
                     + accel_unlock(X)                     # decision 8, the realised Attach Budget
                     − exposure(X)                         # decision 5, the Prize-Path delta

  where  net_assignment_relevance(X) = [ V(suppliers ∪ {X deployed}) − V(suppliers) ] / D
         ability_relevance(X)        = [ best fetchable Supporter's slot marginal ] / D
         D    = max(ROLE_TIER) = 30.0            # fixed yardstick, board-independent (Amendment C)
         BAND = preservation-pinned to the incumbent rung range (+12…+25), NEVER a derivation
```

**FOUR legs, not five** (Amendment B): the Needs DP over five bench slots already prices scarcity, so
one marginal nets a body's contribution against what it displaces. The two Worth legs are
**dimensionless ratios** — the Worth scale never escapes the assignment (Amendment B), so no
`WORTH_DAMAGE_RATE` is referenced and `test_currency.py`'s guard stands. The prize-denominated leg
converts through `PRIZE_DAMAGE_RATE`. Scored at all three Bench entry points
(decision 6). Above it, outside the equation, sits the post-setup `empty_bench` sound rung
(decision 7).

**Deletions — nine of ten bench rules, plus two doctrine rungs.** `baseline_bench.py`:
`dont-bench-multiprize`, `pre-position-attacker`, `develop-a-basic-in-setup`,
`develop-the-wincon-base-first`, `dont-bench-onto-their-path`, `develop-the-accel-recipient` (six of
seven; `keep-a-bench` is PROMOTED to the sound rung, not deleted). `doctrine_fetch.py`:
`bench-the-supporter-tutor`, `dont-pre-bench-the-supporter-tutor`, `dont-pre-bench-a-redundant-utility`.
Signals retiring as decision inputs: `Board.bench_full` / the `my_bench < _BENCH_MAX` gates
(decision 2), `board.accel_recipient_missing` (decision 8),
`board.no_supporter_in_hand` (decision 3), and `bench_shortens_their_path` as a BOOLEAN — its
magnitude survives (decision 5).

**Additions.** `supporter_tutor` → `needs.SUPPLIES` (decision 3); a Bench slot family in `needs.py`
(decision 2); a `bench_harvest` sibling exposing `_harvest_optima`'s objective prize total
(decision 5); `_bench_shortens_their_path` returns a delta rather than a sign (decision 5).

**Gates owed (ADR-0072 / #136 directive 6).** A `tools/train/probes/deploy_decider_sweep.py`
**Decision Gate** with zero unruled `REGRESSION` frames; the **Discrimination Gate**
(`leaf_lab.py diff --baseline data/leaf_lab/baseline.json`) run BEFORE the arming decision; and the
mid-build **Tripwire** (`gauntlet_swap_ab.py --stage mid-build` — this swap DELETES what its flag
would fall back to, so `gauntlet_swap_ab` is the right instrument, not the `--overlay` variant). The
`Leaf Profile` field-set pin WILL move (decisions 3 and 8 add reads) and must be deliberately
re-measured, not auto-conformed.

**Corpus.** `setup_bench_decline_f3` and `dp_dont_pre_bench_redundant_munkidori_f4` must keep passing
as CONSEQUENCES of the equation (decisions 3 and 2), not of the weights that currently carry them.
`ml_dont_bench_redundant_solrock_f51` is the phase's motivating frame; it was **re-ruled with the user
2026-07-29 to `correct: [0]`** (play Lillie's Determination) and now GATES as a cross-lane Decision
Claim — see **Amendment D**. The degenerate `correct == []` is gone from both stores.
`ms_free_bench_evolve_f17`, `ml_dont_play_a_needless_pokemon_tutor_f114` and
`ml_dont_energize_the_supporter_tutor_f84` are adjacent and should be swept.

**Issue #197 is closed by this ADR as the grill record.** Its item 1 (is there a defect?) — yes, and
its "no motivating frame" premise was false. Item 2 (multi-pick shape) — dissolved by decision 6.
Items 3 and 4 (the two-vocabulary cost and the shared completeness invariant with Issue #161) —
superseded by decision 1: the Bench gets an equation, not a declaration, so the asymmetry with
`starter_priority` is deliberate and there is no shared universe to invariant over. The BUILD is a new
Value-System tracker phase, filed **blocked-by Issue #199** (decision 4).

## Amendment A — decision 4 is RE-OPENED: the deploy seam cannot anchor the Worth Damage Rate, structurally (2026-07-29)

**Trigger.** Issue #199 merged, and it did **not** derive the Worth Damage Rate. ADR-0080 ran
ADR-0078's gate 2, found the corpus holds 12 `Discard`-context frames of which exactly one holds a
Hammer, measured that frame at `deny_value = 0.000` on both instruments — so `m = 0` makes the rate
divide out — and then ruled the rate **MOOT for deny** by reformulating deny as a *categorical
relevance* instrument that never crosses a scale boundary. The guard test asserting
`not hasattr(currency, "WORTH_DAMAGE_RATE")` **stays**, and ADR-0080 decision 1 makes the constant's
absence by design rather than pending.

Decision 4 said "consume Issue #199's rate". There is no rate to consume, it is not scheduled, and
adding one would require deleting a test that exists to prevent exactly that.

**The measurement.** ADR-0078 decision 3 noted the deploy seam is natively play-side, which is the
shape deny lacked, so decision 4 committed this seam's corpus to the anchor hunt. That sweep is now
built and run — `tools/train/probes/deploy_anchor_sweep.py`, offline and read-only:

- 508 ruled records; **11** deploy-involved frames in the tracked `data/corrections/` corpus (19
  counting the `tests/fixtures/corrections/` duplicates); **2** cross-scale candidates, both from
  episode 83661652.
- **Both sides price NONZERO** — Riolu carries `win_condition_base` → `ROLE_TIER` **20.0**, against
  Lunatone's Power Gem **50**. So this is NOT deny's failure mode; the rate does not divide out, and
  the resulting `rate > 2.50` would even discriminate (it excludes the trainer pair at ~1.0 and is
  consistent with the derived energy pair at ~6.7).
- **But the rulings are SEQUENCING claims, not exclusive choices.** f33: *"should have played solrock,
  riolu, **then** attached to riolu."* f44: *"Pilot resisting to play basics to bench … and **just
  attack**."* Benching Basics is unlimited and any-order and only the attack ends the turn
  (`docs/rulebook.txt` L120–122), so "play Riolu **and** attack" is ONE legal turn. Each is therefore
  an ADR-0072 **Endorsement Claim** asserting only `deploy_value > 0` — which every positive rate
  satisfies. This is ADR-0080's degenerate outcome reached by a different route.
- **Zero upper bounds.** No ruling anywhere in the corpus puts an attack over a deploy.

**The structural finding, which is the load-bearing part.** This is not a corpus gap and no amount of
further capture can close it: **a deploy is never exclusive with a damage-denominated option.**
Benching consumes no attach, no Supporter slot, and does not end the turn, so it cannot TRADE against
an attack or an attach. The only genuine competitor for a Bench slot is another deploy, and that
comparison is worth-versus-worth, carrying no rate information. **The same commutativity that let
decision 6 rule out a set-level planner is what closes this seam as a rate anchor** — one fact,
two consequences, pulling opposite ways.

**Status of the decisions.** Decisions 1, 2, 3, 5, 6, 7 and 8 STAND — none depends on the currency
route. **Decision 4 is re-opened** and needs its own grill. Options as they stand, none ruled:

1. **Reformulate the Worth-denominated legs as relevance reads**, following ADR-0080's pattern — a
   scalar in `[0,1]` scaling an incumbent constant, adding no new scale. The **ability yield** looks
   amenable ("is there a Supporter my deck holds that this position actually needs?" is a relevance
   question). **Slot displacement is the hard case** — "how much value does the displaced body carry"
   is a magnitude by construction. ADR-0080's move was to notice deny's question had been *mis-framed*;
   whether ours has been is exactly what the grill must settle.
2. **Ship only the damage-native legs** (exposure, accel unlock). Rejected on sight here: it violates
   #136 directive 1's no-shadow rule and drops the two legs that fix the Meowth defect this issue was
   opened for. Recorded so it is not re-proposed as a compromise.
3. **Anchor the rate from another seam entirely.** Out of this issue's scope, and after ADR-0080 there
   is no consumer left asking for it — which is itself an argument that the rate may never be built.

**Consequence for the build.** The phase stays parked, but the blocker CHANGES: it is no longer
"waiting on Issue #199" (that issue is closed) but "decision 4 has no answer". Issue #197 returns to
`status:1-grilling`.

## Amendment B — decision 4 RE-RULED: the Worth legs are dimensionless RATIOS, and the Worth scale never escapes the assignment (2026-07-29)

*(User ruling, 2026-07-29, the Amendment-A grill.)*

**Decision 4 was mis-framed, in the same way ADR-0080 found deny's charter mis-framed.** It asked how
to *convert* a Worth magnitude into damage. The answer is that no magnitude ever needs to cross:

```
displacement_relevance(X) = [ V(suppliers) − V(suppliers | X pinned) ] / D          ∈ [0,1]
ability_relevance(X)      = [ best fetchable Supporter's slot marginal ] / D'       ∈ [0,1]
deploy_marginal(X)        = BAND × ( … the relevance terms … )
                            + accel_unlock(X) − exposure(X)        # already damage-native
```

`V` is `needs.assignment_value`, and the numerator is exactly `keep_v2`'s existing shape
(`V(all) − V(all − index)`). **A ratio of two assignment values is dimensionless — the Worth points
cancel.** The Worth tiers keep doing all the ranking work; they simply do it *inside* the assignment
and never leave it. `WORTH_DAMAGE_RATE` is never referenced, so `test_currency.py`'s guard and
ADR-0080's "absent by design" both stand untouched.

This is structurally the object ADR-0080 decision 3 shipped for deny — a scalar in `[0,1]` scaling an
incumbent constant, adding no new scale — except **derived from the existing DP arithmetic rather than
authored**.

**The band exists and is already damage-denominated.** Two candidates: the readiness leaf's per-body
contribution (`_READINESS_BODY_CAP` 120.0, `_READINESS_BENCH_DISCOUNT` 0.45, `_READINESS_SATURATED`
0.1 — readiness IS scaled damage, `_READINESS_ATTACK_W` 0.45), and the incumbent rung weights this
equation deletes (`develop-a-basic-in-setup` +12, `pre-position-attacker` +25,
`develop-the-accel-recipient` +20, `bench-the-supporter-tutor` +25, `dont-bench-multiprize` −15),
which already compete in `score` against attacks.

**Evidence this is the right reading, not a workaround.** Amendment A's anchor hunt found that no
ruled comparison in the corpus puts a Worth magnitude against a damage magnitude — because a deploy is
never exclusive with a damage-denominated option. If the magnitude is never *compared*, it was never
the thing being decided. The failed anchor is evidence about the model, not just about the corpus.

Rejected: running the assignment over **readiness** values instead of Worth tiers (single currency,
no ratio, no band — but decision 3's ability yield is a HAND-card question, and pricing a hand card
through a board-evaluation leaf is the WP-N5 mismatch `needs.general_worth_slot` exists to fix, so it
fixes displacement and orphans the Meowth leg this issue was opened for); and deriving the rate from
some other seam (after ADR-0080 there is no consumer left asking for it, which inverts ADR-0076
decision 3's rationale for centralising shared adjudications).

**Costs accepted with the ruling, and carried forward as open sub-decisions:**

- **The normalizer `D` is its own decision**, with a real failure mode: dividing by `V(suppliers)`
  makes a thin board inflate every displacement. It must also keep scores comparable ACROSS boards,
  since the marginal competes against `End` (0) and against attacks — which rules out a
  within-decision normalization.
- **A ratio discards absolute magnitude.** "20 of 100" and "2 of 10" both read 0.2. Deny accepted
  exactly this trade; whether the deploy seam can is not yet ruled.
- **`BAND` is a PRESERVATION CHOICE, never a derivation** — ADR-0080 decision 3's discipline for its
  `K`, verbatim: *"pinned to the incumbent's observed range so the swap starts behaviour-preserving,
  and recorded as a preservation choice, never dressed as a derivation"* (ADR-0065).

**Also exposed by the reformulation, and folded here:** decision 2's `supplier_contribution` and
`slot_displacement` are NOT two legs. The Needs DP over five bench slots already prices scarcity — if
better bodies fill every slot, a candidate's marginal is ~0 automatically — so
`V(assignment | X deployed) − V(assignment | X not deployed)` **nets contribution against displacement
in one quantity**. The Consequences section's five-leg form is corrected to four:
`net_assignment_relevance · ability_relevance · accel_unlock · exposure`.

## Amendment C — the normalizer is a FIXED yardstick and `BAND` is preservation-pinned; the seam owns one honestly-labelled local rate (2026-07-29)

*(User ruling, 2026-07-29, closing the Amendment-A/B grill. Decision 4 is now fully re-ruled and the
phase is UNBLOCKED.)*

**The constraint that settles it.** The deploy marginal competes against `End` (0) and against attacks
(damage), so `relevance` must mean the same thing on EVERY board. A within-decision normalizer
(`D = max over candidates at this decision`) is therefore **rejected on correctness**: the best
available deploy would read 1.0 whether it is excellent or merely least-bad, so a board on which every
deploy is mediocre would still score a full band and the agent would deploy every turn.

**Ruling.**

- `D = max(ROLE_TIER) = 30.0` — a **fixed, board-independent** yardstick, and a shipped tier rather
  than an invented figure: it is the ceiling on any single card's assignment contribution.
- The SAME `D` normalizes both Worth legs. Two ratios divided by different yardsticks would not be
  comparable to each other, and they are summed.
- `BAND` is **pinned** so the resulting scores reproduce the incumbent rung range (+12…+25) across the
  deploy corpus, and is **recorded as a preservation choice, never dressed as a derivation** —
  ADR-0080 decision 3's discipline for its `K`, applied verbatim. The `deploy_decider_sweep` Decision
  Gate is what VERIFIES the pin actually preserved behaviour; that is the check ADR-0073's
  `_PRIZE_UNIT = 12` never had, and the reason this is a difference in discipline rather than a repeat
  of the same mistake.

**Stated plainly, because the ADR must not hide it: `BAND / D` has units of damage-per-worth-point.
It IS a Worth Damage Rate, scoped to one seam.** Amendment B did not make the rate unnecessary — it
made it *local, small, and honestly labelled* instead of universal, large, and claimed-derived. This
is a **third** entry in ADR-0078's catalogue of seam-scoped worth↔damage constants (trainer ≈ 1.0,
energy ≈ 6.7, deploy ≈ `BAND/30`).

The one honest mitigation, not oversold: ADR-0078's complaint was that two constants priced **the same
object** differently. Nothing else in the codebase prices a bench deployment, so this constant
contradicts nothing today.

**Reconciliation debt, recorded here so it is not discovered later:** if a general Worth Damage Rate
is ever derived, `BAND / D` becomes a thing to reconcile against it — and a disagreement would be
evidence about one of the two, not automatically about this one.

**Accepted consequence:** a ratio discards absolute magnitude — "20 of 100" and "2 of 10" both read
0.2. Deny accepted the identical trade under ADR-0080. Consequence to watch for at the Decision Gate:
a board whose whole supplier field is weak will price its best deploy the same as a board whose field
is strong but crowded.

Rejected: **making both Worth legs damage-native** (price the displaced body through readiness and the
fetched Supporter through what it *enables*) — the only option that adds nothing to the constants
catalogue, and it is genuinely cleaner on the currency axis. It loses on robustness and verifiability:
"what does this Supporter enable" is a per-Supporter-class lookahead on an already-heavy path, close to
re-implementing a mini turn-planner inside a marginal, and a much larger surface to get wrong than one
pinned scalar that a gate can prove. It also re-imports the WP-N5 hand-card mismatch.

## Amendment D — the motivating frame is RE-RULED and now gates (2026-07-29)

*(User ruling, 2026-07-29, on the pulled-up board state of `85709280-51`.)*

`ml_dont_bench_redundant_solrock_f51` recorded `correct: []` at a `minCount 1` Main select —
degenerate, ungateable, and only ever meaning "not this". Both the Correction-log record and the
committed fixture are re-ruled to **`correct: [0]` — play Lillie's Determination** instead of the
second Solrock. The rationale is unchanged and was confirmed correct; only the positive pick was
missing.

**The board (turn 6, `frame_view.py`).** Active Meowth ex (no Energy); Bench **4 of 5** — Solrock
(1 {F}), Mega Lucario ex (1 {F} + Air Balloon), a second Mega Lucario ex (bare, played this turn),
Lunatone. Hand: **Solrock, Ultra Ball, Lillie's Determination**. Deck 33, holding **2× Makuhita**,
Hariyama, Riolu, a third Mega Lucario ex. Nothing spent this turn — attach, Supporter, Stadium and
retreat all still available.

So the engine is already complete (Solrock **and** Lunatone in play), the second Solrock is redundant,
and it would spend the **last** bench slot the Makuhita→Hariyama line needs — while both Makuhita sit
in the deck behind the Ultra Ball in hand. Lillie's shuffles and redraws rather than committing the
slot.

**Claim shape.** A **cross-lane Decision Claim** (a Supporter `PLAY` preferred over a Pokémon `PLAY`),
which ADR-0072 permits explicitly — *"Decision Claims are cross-lane by nature."* Written as an
explicit `claims.decision` block with `ruled` and `why` and **no `owner`**, so it **GATES** rather
than sitting held-out.

**What the agent actually did, and why this is the phase's motivating frame.** The recorded
`live_trace` shows the two rungs this ADR deletes deciding it against each other:

| option | score | fired |
|---|---|---|
| `[0]` Lillie's Determination | **20.0** | `dig-before-commit` +20 |
| `[1]` Ultra Ball | −50.0 | `dont-shed-a-live-card` −20, `dont-costly-tutor-when-starved-and-developed` −30 |
| `[2]` **Solrock (chosen)** | **25.0** | `pre-position-attacker` +25 |
| `[3]` End | 0.0 | — |

`pre-position-attacker` (+25) out-scored `dig-before-commit` (+20) by **5 points**, and it is blind to
both facts that decide the frame: that the engine is already complete, and that this is the last slot.
Under the Deploy Marginal the netted assignment marginal prices a redundant body into a contested last
slot near zero, and `pre-position-attacker` is deleted outright.

**A constraint on `BAND`, recorded because it is the only one the corpus supplies.** This frame is not
a rate anchor (Amendment A's structural finding stands — the two options are both `PLAY`s and neither
is damage-denominated). But as a gating Decision Claim it *bounds the pin from above*:

```
BAND × net_assignment_relevance(2nd Solrock | bench 4/5, engine complete)  <  20.0
```

Weak, since the relevance should be ≈0 on this board anyway — but it is a real, checkable constraint
on the preservation pin rather than a free parameter, and the Decision Gate enforces it.

## Open, deliberately not ruled here

- Whether any deploy-corpus frame actually DISCRIMINATES the Worth Damage Rate (decision 4) — a
  measurement for S3c, not a claim.
- Whether `_PATH_BENCH_EXTRA = 1` (`objectives.py:124`) is stale against ADR-0071 decision 6's
  correction of the same reasoning on the Threat Clock (decision 5's observation).
- The runtime budget: three per-option optima (closure query, path re-derivation, Attach Budget) on
  one path. Memoisation strategy is a build decision; the `Leaf Profile` is the instrument that will
  price it.
