# ADR-0070: The evolve marginal is a body-substituted delta, and its constants are odds

**Status.** Accepted (grilled 2026-07-25, `/grill-with-docs` on issue #140 — eleven locked
decisions). Build: #140 (Phase 1b of the Value System, tracker #136), the second no-shadow decider
swap, following the pattern ADR-0069 set (fold → diff → user-ruled review → delete → retune →
paired A/B). Companion vocabulary: **Build Standing · The Two Clocks · Income Horizon ·
Area-at-Damage-Time** in the Agent Runtime [`CONTEXT.md`](../../src/common/CONTEXT.md). Consumes
ADR-0067 (#137, the Budget/reachability family), ADR-0068 (#138, the snapshot) and ADR-0069 (#139,
the attach decider). Amends the 2026-07-15 evolve grill
(`docs/plans/evolve-valuation-grill-spec.md`), whose Rulings 5 and 7 it partially overturns.

## Context

`evolve_value` computed a full equation and decided nothing. A swap was attempted on 2026-07-15 and
REVERTED on two recorded calibration gaps. This grill found the record stale and the equation
thinner than its own design in three ways:

- **The units collided.** ADR-0069 moved the attach decider to a real **damage** currency at
  `_ATTACH_VALUE_SCALE = 1.0` (thinnest build step 5.83). `evolve_value` still spoke Needs
  (`_DEPLOY_WINCON_READY = 40`, `_ENGINE = ROLE_TIER["engine"] = 12`). The leak was already
  observable: `test_advance_the_line_beats_spreading_f29` had to be rewritten from a score claim to
  a decision claim because *"a 37.5-damage build step out-numbers a +20 evolve rung"*
  (`docs/plans/attach-decider-swap-review.md`). The evolve survived on planner tier ordering, not on
  value. The recorded gap ("an unready Mega evolve scores 10 but must beat a competing attach at
  45") was measured in a currency that no longer exists.
- **Four of eleven `EvolveInputs` fields were never filled.** `pilot._evolve_shadow` passed seven;
  `result_ability_oneshot`, `body_ability_oneshot`, `hold_turns` and `engines_online` sat at
  defaults. `_ability_income` therefore computed `base × max(1, 1)` for everything, so Ruling 1's
  one-shot/persistent split — the mechanism by which "hold until ready" is DERIVED rather than
  asserted — was inert. Recon priced identically to Run Away Draw.
- **A target with no term.** Ruling 5's exposure term was struck on 2026-07-15 (f32 showed evolving
  *reduces* exposure: Drakloak 90 HP > Dreepy 70), yet xfail target `f2` remained in the evolve
  corpus labelled "exposure / opener" — on a `_SETUP_ACTIVE` path this equation never reaches.

Card facts load-bearing here, all verified at source 2026-07-25 (`data/EN_Card_Data.csv`,
`docs/rules.md`):

- Drakloak (120): 90 HP; *Recon Directive* — "look at the top **2** cards of your deck and put 1 of
  them into your hand", once per turn, persistent. Dragon Headbutt `{R}{P}` **70**.
- Dragapult ex (121): 320 HP; Phantom Dive `{R}{P}` **200** + 6 damage counters. **Identical cost to
  Drakloak's attack** — so the evolve decision collapses to "can I pay `{R}{P}`?", and the doctrine
  derives without a threshold. Tera: no attack damage while Benched (rules.md §185).
- Manual Energy attachment is capped at **1 per turn** (rules.md:86) — which refutes pricing a draw
  engine as "more Energy drawn ⇒ more build".
- Prize value (rules.md §136-142): `megaEx` **3**, `ex` **2**, regular **1** — project-verified,
  "Mega-ex = 2" refuted.
- Abilities are usable "per the ability's own text" (rules.md:91), and the engine re-presents the
  menu after each non-ending action — so **Recon → evolve → use R's ability** is one legal turn.

## Decision

**1. The evolve marginal is damage-denominated — one currency with the attach decider.** Two units
in one `score` means every retune on either side silently re-opens the other, and a single
Needs→damage conversion scalar cannot serve both a damage-shaped deploy term and a not-damage-shaped
income term.

**2. `deploy` is ADR-0069's attack axis with the BODY SUBSTITUTED.**
`deploy = max(this_turn(R), build_standing(R))·P(R survives) − max(this_turn(B), build_standing(B))·P(B survives)`,
`max` within, per ADR-0069 §1 — the terms re-read one progress on one body. Budgets built
per-body (the #137 consumer contract), R inheriting B's attached Energy. The recorded gap dissolves
with **zero new constants**: `_line_payoff_stat` already credits a pre-evolution against its
evolution's attack at `_ATTACH_PREEVO_DISCOUNT = 0.25`, so **evolving is precisely the removal of
that discount**. Staryu at 2 of Nebula Beam's 3 typed slots: `(2/3)²×210×0.25 = 23.3` becomes
`(2/3)²×210 = 93.3`, a **+70** deploy where the shipped equation scored 10. Requires extracting the
LEVEL form (`build_standing`) out of `_attach_build_delta`, which is then defined as its difference.

**3. The engine's worth is an ODDS READ, not a constant.**
`income = dmax × [readiness_p(…, draws=D) − readiness_p(…)]`, the exact hypergeometric already
shipped in `deck_odds.draw_hit_probability`. This DERIVES three things the constant only asserted:
saturation (`readiness_p` returns 1.0 when the body already reaches, so a redundant engine is worth
exactly zero — what `draw_engine_slot`'s halving approximated); Ruling 1's collapse ("the hold
pressure collapses to 0 exactly when the body is typed-ready"); and the one-shot/persistent split's
SHAPE. The one remaining per-card number — dig depth `D` (Recon: 2) — moves into
`card_functions.json` as **data** maintained by the card-functions pipeline, where it ages with the
card pool, rather than into code as a constant. Accepted limitation: this prices only the engine's
attach-enabling half (Recon also finds Supporters, the payoff, a tutor), so it is a FLOOR and will
systematically under-hold.

**4. No exposure term.** Struck for the second time: refuted at source by f32, and its one
motivating frame (`f2`) is a `_SETUP_ACTIVE` placement decision off the `_EVOLVE` path. `f2` is
**re-ruled out of scope** and relocated out of `test_evolve_valuation_corpus.py` to a placement
follow-up, leaving 4 pins + 2 in-path targets. Should a genuine exposure frame appear, it lands as a
per-axis **Gate** (ADR-0069 §4), never as a subtracted term.

**5. The doom override is deleted, not re-expressed.** "This body is about to die" is a statement
about what its banked Energy is worth, which is the same currency as everything else — so it belongs
INSIDE the comparison as the survival weighting of decision 2, not stapled outside it. This also
fixes a blindness: the shipped override fired whenever the body could be KO'd, never checking
whether evolving *escapes* the KO. ADR-0069's Out of Scope explicitly parked "requiring the
evolution be reachable for the evolution-escape — refinement later, with a frame"; 1b is the phase
that knows, and takes the 1b half. Tightening 1a's own exemption still awaits a frame.

**6. A bare-body evolve earns THE TWO CLOCKS, and where they are silent, sequencing owns it.**
`build_standing` is zero at zero Energy on both sides, so a naive port scores a bare evolve 0 — and
`_finish_turn_last` sequences early only when `score > 0`, which would have regressed "megas evolve
on sight". Rejected: a low-band constant floor (ages with the card pool) and crediting the next
attach's un-discounting (double-counts within one turn). Instead the value is the race between
`turns_to_afford` (mine, **hop-aware** — `combat.py:940` already takes the `evolvesFrom` chain depth
as a parallel leg) and `turns_to_ko_me` (theirs, HP-driven): evolving shortens the first and
lengthens the second, and is worth `dmax × ΔP(fires)`. Where it changes neither clock the value is
LEGITIMATELY zero, and "evolve on sight" is then not a value claim but a free-action claim —
sequenced tier-0 structurally from card facts, the same move ADR-0069 §7 made converting
`attach-energy-last` from a weight to a decide()-only ordering mechanism. `P(fires)` grades by
`deny_slot`'s shipped halving (`/2**t`), never a new decay rate.

**7. The income horizon is SPLIT, because the turn structure is asymmetric.** The sequencer takes
the free ability before the evolve (both tier 0; the menu re-presents), so evolving does not cost
this turn's Recon. `income_gain` is immediate and undiscounted when R's ability is usable now;
`income_loss` is a strictly FUTURE stream, halved per turn out. This-turn loss is counted only when
B's ability is **still on the menu** — the fact is read, never inferred from an assumed ordering.
Consequence to measure, not assume: an honestly discounted future stream is a much LOWER bar than
the deleted `−46` rung, so `f35` (the hold frame) may get harder, not easier. That would be evidence
about the doctrine, not licence to bend the discount.

**8. The decider stays PRIZE-BLIND, with no gate.** Evolving a doomed body into a higher-prize form
(Drakloak 1 → Dragapult ex 2; Staryu 1 → Mega Starmie ex **3**) is a real blunder, and the tier-0
free-action rule of decision 6 actively drives it. It is nonetheless NOT fixed here: in the end
state #145's `state_value` is prize-denominated and evolve is differenced
(`state_value(after) − state_value(before)`), so the conceded prize appears automatically, and
pricing it here too would double-count the race — ADR-0069 §6's reasoning exactly. A temporary gate
was considered and REJECTED on the user's ruling that only the epic's end state matters. What 1b
owes instead is a **named acceptance case registered on #145**, not scaffolding. Accepted exposure:
the agent can commit this blunder until #145 lands.

**9. `incoming` gains a bench branch, keyed on AREA-AT-DAMAGE-TIME.** Today `incoming` credits the
opponent's full Active-attack damage against any body, with no Active/Bench branch — so a benched
pre-evolution reads as doomed and the survival weighting of decision 2 would OVER-evolve, inverting
the doctrine. Against a benched body only `rider_snipe` / `rider_spread` reach, and `is_tera` on MY
body zeroes it (both card facts already shipped, used only offensively).

**Caller enumeration — corrected during the build.** The grill reported one existing consumer as a
bench read that the branch would correct (`opp_cannot_punish_wincon`). That was WRONG, and the error
is instructive enough to record: it passes a body that is benched *now*, but every consumer of that
veto decides whether to **expose the wincon in the Active Spot** (`interpose-…` stands down so
`promote-the-ready-wincon` wins; `dont-promote-into-their-prize-reach` stands down so the promote
goes through). Its area-at-damage-time is ACTIVE, and its existing read is correct. It is the same
class as `_survives_after_ko`, which the lethal tiers call about bodies benched now but Active when
they swing.

So **no existing consumer wants the bench branch**: it is entirely new surface for this phase's
deploy term, and the blast radius on shipped behaviour is zero (1564 strategy/agent tests unchanged).
The planner's catastrophe rung is Active-only by design (*"a bench body soaks — recoverable, not a
loss"*).

**Which is exactly why the area is an explicit caller-passed argument, never inferred.** Two
independent readers — the grill and the build — disagreed about the area of the *same* call site by
reasoning from the board rather than from the decision. A board-inferred area would have silently
granted a 3-prize wincon phantom safety and manufactured phantom lethals in the lethal tiers. The
default is ACTIVE, so the conservative read is what an undeclared caller gets; the bench branch is
strictly opt-in. Every existing call site now states its claim in the source.

**10. Rung disposition — four delete, one folds, one survives as a Gate.** `evolve-into-wincon`
(+40) and `advance-the-evolution-line` (+15) are the deploy term; both `+5` energized tie-breaks are
EMERGENT (an energized body has higher standing, so its delta is naturally larger — which is what
they were compensating for). All four delete, as does dragapult's `hold-evolution-until-attacker-
ready` (−46), which is `income_loss`, via `/deck-align` (ADR-0034). **`prefer-rush-evolve-tutor` (+30) SURVIVES as a rung — the fold is DEFERRED to #145** (amendment
G below overturns this decision's original "folds to `evolve_value`" disposition, which the build
found under-determined).
`dont-rush-evolve-without-target` (−60) survives as a pure **Gate** — structural absence, not value
— and MUST keep its `_CLASS_B_SPEND_IDS` membership or the develop-rollout planner's spend account
loses a term.

**11. 1a merges before 1b branches.** 1b's corpus diff and paired A/B measure against the SHIPPED
agent; branching off an unmerged #159 would leave any regression ambiguous between two swaps,
defeating the protocol ADR-0069 established. (Executed: #159 merged at `13a0c81`.)

## Amendments from the build

**A. The composition of §2 and §6 was underspecified, and resolving it cost the headline.** Both the
`build_standing` reading and the clock reading estimate one forward payoff on one body, so they
compose with `max` (ADR-0069 §1) — under which the clock term swamps standing and the "+70 from
removing the `0.25`" becomes zero. Ruled (user, 2026-07-25): the discount and the hop clock are TWO
MODELS OF ONE FACT, so the decider uses only the measured one. `deploy(X) = max(this_turn(X),
payoff_damage(X) · p_arrive(X) · p_survive(X))`. A hop costs a turn only when hops OUTNUMBER the
energy turns owed — attaching and evolving run in parallel — and in the frame the grill quoted they
tie, so the honest delta there is 0. The recorded gap's frame instead earns from `this_turn`
(Jetting Blow `{W}` 120 vs Water Gun 20) and from survivability (70 → 330 HP). Because both bodies
build toward the SAME line payoff, `payoff_damage` cancels: the deploy delta is driven purely by
what evolving does to the two clocks.

**B. `turns_to_afford`'s energy leg is COUNT-based, which broke the hold frame.** It read Drakloak
on `{R}{D}` as armed for Phantom Dive's `{R}{P}` and priced f35 — the hold frame — as a 100-point
evolve. Fixed with a `typed=` parameter rather than a global change, because the reading is a
FAIL-DIRECTION choice: the count reading is pessimistic about THEIR clock (safe for a threat read)
and wrong for mine. My side passes `typed=True`.

**C. f82 is a TURN-PLANNER maneuver, not an evolve gap** (user ruling 2026-07-25, applying the f32
precedent verbatim). The frame is won by a five-step chain whose value is the END STATE: Crispin
attaches `{D}` to Munkidori, evolve the Active Dreepy (40 damage carries → Drakloak 50/90),
Adrena-Brain moves 3 counters (mine → 80/90, theirs → 60/90), Recon Directive, then Dragon Headbutt
70 ≥ 60 KOs. The standalone deploy (30.0 Active vs 37.5 benched) is CORRECT; the maneuver is simply
better and belongs to the Turn Planner. **CROSS-LAYER REQUIREMENT, BLOCKING THE SWAP:** f82 is a
corpus PIN, and no lethal tier currently reaches an Ability that moves damage counters onto the
defender (the ladder covers develop, attach, energy-tutor, evolution-tutor, damage-boost retreat and
retreat-enabler). The pin therefore regresses the moment the flag flips ON, unless the planner gains
that reach or the pin is re-ruled to planner scope.

**D. The bench survival read prices a SHARED spread budget per-body.** `turns_to_ko_me` asks "can 60
kill this body?" once per body, so it credits rescuing one benched Pokémon as though the whole
spread were dedicated to it — when the opponent simply redirects the counters to another body in
range. Parked as its own issue rather than fixed here (user ruling 2026-07-25); it inflates every
bench survival delta, so it touches 1c and 1d as well.

**E. §6's "structural tier-0 free evolve" is WITHDRAWN — the corpus argues against it.** The grill
supposed a strictly-dominant free evolve should be sequenced ahead structurally, on the reasoning
that evolving is free. The sweep says otherwise: three mega_starmie frames (81785223-32/38/44) are
FIXES precisely BECAUSE the decider declines a zero-value evolve and plays a free dig instead. Ruled
(user, 2026-07-25): **information before commitment** — within tier 0 a free dig precedes an evolve,
then the Supporter if applicable. That is the sequencer's own stated doctrine ("take the most
informative, reversible actions first"), applied within a tier rather than across tiers.

No code implements a tier-0 evolve rule, and none is needed: a valueless evolve scores 0.0, and
`_finish_turn_last` sequences early only on `score > 0`, so the dig wins by construction. The one
case no frame exercises is a HIGH-value evolve competing with a free dig — left unbuilt rather than
built on speculation, and named here so a future frame can settle it.

**F. Two corpus frames left the evolve lane on re-ruling** (user, 2026-07-25), neither an evolve gap:

- **82525741-78** — labelled "Evolve: Mega Starmie ex", but the blunder was playing a DEAD
  Buddy-Buddy Poffin: it fetches Basics of 70 HP or less, Staryu is the only such card in the deck,
  and all 3 copies were already on the board. Evolving either Staryu is merely fine (the decider
  scores both 0.0, i.e. exactly indifferent). The defect belongs to the fetch/search family's
  exhausted-target gate. Re-ruled out of scope; tracked separately.
- **85785609-82 (f82)** — the turn-planner maneuver of amendment C.

With both removed the sweep stands at 24 frames / 14 agree / 10 flips: **6 FIX, 0 REGRESSION**, 2
re-ruled out of scope, 2 DIVERGENT (both correct on the evolve axis — 86091435-35 is f35 and the
hold fires as designed).

**G. The rush-evolve tutor fold was BUILT, then REVERTED — it is under-determined without #145.**
Decision 10 ruled that `prefer-rush-evolve-tutor`'s worth IS the evolve it enables, so it should
fold to `evolve_value` over the hypothetical result. Built (`_rush_evolve_tutor_tactical`, with
`_evolve_inputs` factored out so the tutor could never be priced by a different equation than the
evolve it buys) and reverted on measurement: Salvatore scored **0.0** where the rung gave +30
(`test_a_free_item_dig_is_sequenced_before_the_one_per_turn_supporter`).

The cause is a gap in the ruling, not the implementation. A rush-evolve tutor does TWO things —
it **fetches a Pokémon onto the bench** and **evolves it the same turn**. The fold priced only the
second, so whenever the enabled evolve's clocks do not move (which decision 6 establishes is often
and correctly zero) the tutor read as worthless despite having put a body on the board a turn early.
**The deployment half is unpriced.**

Pricing it here would mean inventing a damage-denominated "what is a body on my board worth" term —
which is precisely the question `state_value` exists to answer (#145 build shape 1 counts *"my
development (readiness + Needs coverage)"*, and build shape 3 differences it per option). But whether
that actually absorbs a tutor is UNSETTLED: #145's grill agenda item 2 owns the simulability
boundary and names only *"attach/evolve/retreat likely differenced"* — a deck search's outcome is a
choice over hidden cards, so it may land as an explicit action term instead.

So the rung stays, at its **unchanged +30**, as one acknowledged currency mismatch — visible and
documented rather than papered over with a re-banded figure that would be a guess dressed as a
derivation. Unlike the four deleted rungs, where f29 gave a concrete leak (a 37.5-damage build step
out-numbering a +20 rung), **no frame currently demonstrates that +30 is wrong.** #145's ruling on
the simulability boundary decides whether this fold is worth doing at all — if tutors are
differenced, it is dead work.

**H. The paired A/B returned FLIP: False, and 1b merged anyway — on a user ruling, recorded here so
the red gate is never silently passed.** Directive 6's A/B (`gauntlet_swap_ab.py`, candidate
`a8b6127` vs `origin/main` `25fa8e5`, n=200/arm/matchup) returned **−1.17 pp, 95% CI [−4.59, +2.25],
0 crashes / 2400 games**. The verdict rested on one cell (−9.5 pp); re-measured at n=600 **both**
dragapult/lucario cells changed sign (−9.5 → +2.2; +7.5 → −3.3). Pooled over 4800 games the best
estimate is **−1.06 pp, 95% CI [−3.90, +1.78], 0 crashes**. The run demonstrated neither a regression
nor a non-regression. Full working: `docs/plans/evolve-decider-swap-review.md`.

Ruled (user, 2026-07-26): **merge.** The reasoning is that the instrument, not the build, is what
failed. Clearing `CI-lo >= −1%` near a zero delta needs n ≈ 2270/arm/matchup (~27,000 games), and
even then `delta >= 0` is a coin flip on a neutral swap — so the rule can only be passed by a swap
with a positive *win-rate* effect, which a mid-build decider swap is not trying to have. A Phase-1
swap makes one axis correct in one currency so #165 and #145 can compose the axes; grading it by
whole-agent win rate measures it through the weakest consumer it will ever have. The general
re-scope of directive 6 — and the discrimination gate that should replace it mid-build, on the
267-frame leaf lab that Gate 0 already used — is **#167**, not this ADR.

What the run establishes unconditionally still stands and is not small: **0 crashes in 4800 games**
on the real engine across every deck pairing and both seats, and the exclusion of a regression worse
than 3.90 pp.

The one signal worth carrying forward: 5 of 6 cells are negative, 1 exactly zero, none positive. That
is weak (≈3% under a null, and the cells share a build so they are not independent), but it points
the same way as the term diagnosis — the deploy **re-banding** of decision 2, which moved evolves
from 15–20 in Needs to 30–50 in damage and lets an evolve out-score a **non-evolve** option. f32's
correct answer is a retreat-to-item-lock-wall; `docs/plans/turn-planner-retreat-to-item-lock-wall.md`
called this exact shot on 2026-07-15, during the first reverted swap attempt, and ruled it the
planner's to own rather than the equation's to nerf. §7's income-discount worry is **refuted** as the
cause: on both f35 frames the candidate scores the premature evolve **0.0 where the incumbent scored
45.0** — it holds MORE, not less, and the deleted −46 rung was not firing there at all (its `when`
needs `evolve_body_energy < 2`; the body holds 2 wrong-typed Energy). Amendment B's `typed=` fix does
that work.

**I. "Suite green both OS" was not measurable on this build.** #140's acceptance and directive 3 both
require Windows + Linux, but `.github/workflows/ci.yml:33` is `os: [ubuntu-latest]` — on `main` too,
so this predates 1b. CI on `a8b6127` ran exactly one job (`tests (ubuntu-latest, py3.12)`, success,
the suite genuinely ran). `CLAUDE.md:33` and directive 3 both still claim CI runs both. Recorded as a
known gap in this phase's evidence rather than marked satisfied; the CI defect is not 1b's to fix.

## Consequences

- `evolve_value`'s five calibration constants and the `doom` field all disappear. What replaces them
  is one extracted level function, two shipped clocks, one shipped hypergeometric, and one per-card
  data field.
- The equation's quality now depends on read quality — the doom/incoming reads (worst-case and
  sometimes phantom, ADR-0064) and `readiness_p`'s fail-closed-at-0.0 contract (ADR-0067), under
  which an engine whose enabler is unmodelled prices at zero and would be evolved away. That wants
  the same coverage-gate treatment the Attach Budget got.
- Scope grows beyond the `_EVOLVE` path in two places, both deliberate: the `build_standing`
  extraction refactors freshly-merged 1a code, and the bench branch touches shared `incoming`.
- `_ATTACH_PREEVO_DISCOUNT = 0.25` becomes redundant in principle — `turns_to_afford`'s forward-hop
  leg does its job properly. Retiring it is a FOLLOW-UP with its own frame and its own A/B, not 1b.
- Two known-open items ship with the phase: the #145 prize acceptance case, and the `f2` placement
  follow-up.

## Alternatives rejected

- **A Needs→damage conversion scalar** (`_EVOLVE_VALUE_SCALE`, mirroring `_ATTACH_VALUE_SCALE`'s
  0.3→1.0) — one exchange rate cannot be right for both a damage-shaped deploy term and a
  not-damage-shaped income term.
- **Deriving the engine's worth from expected draws** (`P(Energy) × build step × cards/turn`) —
  refuted by the one-attach-per-turn cap (rules.md:86); more Energy drawn buys no more build.
- **A low-band constant floor for the bare-body evolve** — rejected on the user's objection that
  constants age with the card pool; superseded by decision 6's clocks.
- **Loosening `_finish_turn_last`'s `score > 0` endorsement to `>= 0`** — load-bearing across the
  whole sequencer; would pull every neutral option into tier 0.
- **A temporary prize gate as Phase-2 scaffolding** — rejected: the epic's end state is what
  matters, and a permanent veto would additionally foreclose the correct sacrifice evolve.

**J. Term 3 (the bare-body evolve floor) is a MEASURED regression, not an accepted cost — ruled by
the user 2026-07-26 in #167's decision-5 sitting.** Amendment E priced a bare-body evolve at exactly
**0.0**, and the swap review recorded the consequence as term 3: *"a class of evolves that used to be
endorsed at +15 now never clears `_finish_turn_last`'s `score > 0`."* That was logged as "correct by
ruling." It has now been measured, and it costs real board.

**The evidence — `81785223|0|decision|44` (mega_starmie, turn 9).** My Active is Mega Starmie ex
330/330 on one {W}; bench holds Cinderace 160 and a bare **Staryu 70**; hand holds a second **Mega
Starmie ex**, Pokégear 3.0, Hilda, Salvatore ×2, Lillie's Determination, Night Stretcher. The
opponent's Active is Lillie's Clefairy ex at **70 HP remaining** behind a Lillie's Pearl.

Simulating the two candidate openings to end-of-turn produces boards that differ in **exactly one
slot**:

```
Pokégear-first  -> my bench ends:  Cinderace 160,  Staryu 70
Evolve-first    -> my bench ends:  Cinderace 160,  Mega Starmie ex 330
```

Identical otherwise — same KO, same discards, same empty hand. The greedy continuation after
Pokégear-first **never evolves the Staryu**, because the evolve scores 0.0 with no rule firing and
`_finish_turn_last` only sequences options above zero. The evolve happens *only* when it is forced as
the first action.

So the leaf's preference for evolve-first is not an ordering opinion — it is the only line in which
the evolve occurs at all. The user's own ruled line for this turn (Pokégear → **evolve the Staryu** →
Hilda for an Energy → attach → Jetting Blow, sniping the energised benched Clefairy) contains the
evolve; **the shipped agent cannot reach it.** A 70 HP Staryu stays a 70 HP Staryu instead of becoming
a second 330 HP Mega Starmie ex, on the turn we take their Active.

**Scope: 4 of the 5 outstanding leaf regressions share this cause** (three ruled so far —
`81785223|0|decision|44`, `81905522|0|decision|64`, `82226116|0|decision|48` — each isolated by an
end-board diff to a single un-evolved bench slot, with every other slot identical). Of #167's six `OK -> MISS`
frames, `81785223|0|decision|44`, `81905522|0|decision|64`, `82226116|0|decision|48` and
`82229122|0|decision|17` all show every evolve on the menu at 0.0 with the leaf's top line being an
evolve-first. `83968638|1|decision|17` has no evolve on the menu and is a different defect.
The −9.72 leaf decrement is exact on the first three; frames 4 and 5 drop further (−54.0, −1054.0).

**The fix is NOT the obvious one.** Loosening `_finish_turn_last` to `>= 0` is already rejected above
— it is load-bearing across the whole sequencer and would pull every neutral option into tier 0. What
this amendment establishes is narrower: **a bare-body evolve that materially upgrades a body is not
worth zero**, and pricing it at exactly zero makes it unreachable rather than merely unattractive.
Where that value comes from — a survivability/HP-substitution term, a development term, or #145's
`state_value` differencing the board — is not ruled here.

**The fix belongs HERE, not to #165 — user ruling 2026-07-26.** The three actions this frame class
misses are a **Commutative Set**: evolve the benched Staryu, attach an Energy, Boss's Orders to gust.
They reach the same end-of-turn state in any order, because actions may be taken in any order
(`docs/rules.md:76-77`), **evolving keeps attached cards** (`:98`), and evolving into a Mega ex does
not end the turn (`:103`). Only the attack is order-forced.

That is decisive for scope. The sequencer already takes every option above `_finish_turn_last`'s floor
before the turn-ender, so a Commutative Set needs **no planner** — the sole reason one of its members
is missed is that it is priced at zero, which makes it *unreachable* rather than merely unattractive.
**Verified empirically on `81905522|0|decision|64`:** pricing the evolve `+10.0` instead of `0.0`,
changing nothing else, makes the greedy rollout reach the evolve from BOTH candidate openings —

| opening | evolve @ 0.0 (shipped) | evolve @ +10.0 |
|---|---|---|
| ATTACH-first (the human's `correct`) | Staryu 70, Staryu 70 | Staryu 70, **Mega Starmie ex 330** |
| Boss's Orders-first (the agent's live pick) | Staryu 70, Staryu 70 | **Mega Starmie ex 330**, Staryu 70 |

(It evolves whichever Staryu is left over; the two are interchangeable, so both are the same state.)

So this class is **Phase 1b's own defect to price**, not Turn-Planner work. Contrast f32/f82, which
are **Maneuvers** — ordered, mutually dependent steps whose value is the end state — and correctly
stay with #165. The discriminator is mechanical: *do the actions commute?*

**Not discharged.** #167's baseline capture stays blocked on this: re-baselining now would bake four
frames of this regression into the Discrimination Gate's reference.
