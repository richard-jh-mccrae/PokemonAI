# ADR-0082 — Gust is a THREE-surface instrument, and only ONE of its surfaces crosses a scale boundary

**Status:** Accepted (grilling 2026-07-29, `/grill-with-docs` on Issue #189 — decisions land as they
are ruled; this document is authored during the grill, not after it).

**Expect to renumber.** 0082 is claimed at grill time per `docs/adr/README.md`'s *Next free number*
and is settled only at merge. There have been **five** collisions in four days (0071, 0074×3, 0076,
0077, 0079), and #161's ADR was renumbered three times in its own life. Cite the issue alongside the
number ("ADR-0082, Issue #189"); the number is a rebase artifact, not an identifier. When renumbering,
change **only this branch's references**.

**Context issues:** Issue #189 (this grill, S4-gust), Issue #136 (the Value System tracker),
Issue #187 (S4-deny, `status:2-spec`), Issue #188 (S4-snipe, `status:1-grilling`), Issue #190 (S5,
which owns `return_threat`), Issue #165 (the Turn Planner, which now owns `86091435-13`).
**ADRs:** ADR-0022 (the gust doctrine), ADR-0066 (the rider-aware gust baseline and marginal denial),
ADR-0076 (the opponent-target slot family split — Amendment E raised the currency debt, Amendment F
moved it away, and this ADR receives it back), ADR-0078 (the three scales; its decision 1 one-backend
claim is at issue here), ADR-0080 (deny is categorical — withdrew the one-backend claim for deny and
re-inherited the debt to this issue), ADR-0072 (the two merit gates and the three Claim shapes),
ADR-0065 (the no-fudge discipline).

## Context

Issue #189's charter describes a **behavior-preserving repoint of one surface**: lift the merged
`doctrine_gust._gust_target_tactical` sum into the shared assignment as the gust instrument's marginal,
*"not a new calculation, since the merged gust value is already prize-denominated."* Its acceptance
criterion is that four named bench frames hold unchanged.

Read at source on `main` before any build, both halves of that premise fail. The findings below are
recorded first because they are what the scope ruling rests on.

### Finding 1 — gust is three surfaces, not one

The same correction ADR-0077 made to Issue #187's charter applies here:

| | surface | question | where | value today |
|---|---|---|---|---|
| (a) | keep price | is a held Boss's Orders worth KEEPING? | `needs.gust_target_slot`, emitted `pilot.py:3791` | `opponent_target_value`, **prize-equivalents 0–3.9**, deadline 0 |
| (b) | fire now | do I PLAY it this turn? | `_gust_tactical` (KO_SCORE) + **5** `HYPOTHESES` | gate-shaped: prize-count comparisons inside `when`, then a flat positional weight (50 / 50 / 95 / 20 / 10) |
| (c) | which body | which benched body do I DRAG UP? | `_gust_target_tactical` (KO-gated) **and** `_gust_stall_target_tactical` (the non-KO strand path) | 8-term sum on a `KO_SCORE` offset; the strand path is `retreatCost + _STALL_EX_BONUS` |

Surface (a) is **live and armed ON** today (`runtime.py:158`, `gust_target_slots: True`, ADR-0076).
Surface (c) has a **second, non-KO path** the charter does not mention at all.

### Finding 2 — the "already prize-denominated, behavior-preserving" premise does not hold

`_gust_target_tactical` is an **eight**-term sum; `needs.opponent_target_value` is **two** terms. Only
one pair maps cleanly.

| `_gust_target_tactical` term | magnitude | maps to the shared marginal? |
|---|---|---|
| `KO_SCORE` | 1000 | no — a dominance-band offset, not a value |
| `prize_value(target)` | 1 – 3 | **yes** → `prize_advance` |
| `_gust_target_denial` | **my Active's full prize value, up to 3.0** | *conflicts* — the shared survival leg caps at `_SURVIVAL_CAP` **0.9** |
| `_gust_forward_denial` | 0.5 | no |
| `_gust_matchup_priority` | ≤ 0.4 (γ-scaled) | no |
| `_gust_wincon_denial` | ~1.5 (γ-scaled) | no |
| `_gust_energy_denial` | ≤ 0.8 | no |
| `_gust_snipe_synergy` | +1 – 3 (a **second** body's prize) | no — the shared marginal is strictly per-body |

So the repoint as chartered is not a lift. It would either discard six terms or bolt them beside the
marginal, and it silently demotes `_gust_target_denial` from up to 3.0 to at most 0.9 — a ~3.3×
reduction in the one term ADR-0022's *"prizes-first is a trap"* ruling exists to defend.

### Finding 3 — none of the four charter bench frames reach `_gust_target_tactical`

Read from `data/corrections/*/corrections.jsonl`:

| frame | agent | select context | what actually decides it |
|---|---|---|---|
| `85785067-41` | mega_lucario | **Switch** | **not** `_gust_target_tactical`: my Active is Makuhita **10/80 with zero Energy**, so `can_pay_cheapest` fails and `_gust_can_ko` is false on every option. Decided by `_gust_stall_target_tactical` (correct pick Meowth ex — `_STALL_EX_BONUS`). |
| `85163079-30` | mega_starmie | **Main** | surface (b) — the `gust-for-the-loaded-equal-ko` rung, which cites this frame by name |
| `86089120-14` | dragapult_ex | **Main** | surface (b) — a don't-play ruling (*"gusting up their main attacker only helps them"*) |
| `85164131-22` | mega_starmie | **Damage** | a **snipe** frame — `_gust_target_tactical` gates on `context != _SWITCH`. Committed as `tests/fixtures/corrections/ms_snipe_evolving_wincon_over_promotion_stack_f22.json`; it belongs to Issue #188. |

Zero of the four exercise the KO-gated target pick the charter is written about. Two exercise the play
rungs, one the non-KO strand path, one is another issue's. **The acceptance criterion is therefore
vacuous as written** — those frames would hold unchanged whatever the repoint did to (c). Only one of
the four is a committed pytest fixture, and it is the one belonging to #188.

### Finding 4 — the live keep-side slot is arithmetically unreachable for a first copy

ADR-0076 Amendment E recorded the currency debt as *"latent, not firing — the general-worth floor
absorbs it."* Measured, it is stronger than that:

```
gust_target slot ceiling   = opponent_target_value max          = 3.9   (prize-equivalents)
Boss's Orders general slot = TAG_TIER["gust"] 10.0 × 0.45        = 4.5   (card-worth points)
                             (_GENERAL_WORTH_W, pilot.py:87; × deploy × liq)
```

`3.9 < 4.5` unconditionally, and `_keep_slot_dp` assigns each card to its single best eligible slot, so
copy 1 of a gust card takes `general` **every time**. The `general` slot is de-duplicated per `cid`
(`pilot.py:3812`), so `gust_target` can only ever win an assignment for a **second held copy** of a
gust card. The slot ADR-0076 shipped and armed is not merely absorbed — for the common case it is dead
on arrival. (`liq < 1` can lower the floor, so this is *near*-total, not total.)

### Finding 5 — `return_threat` is confirmed out of scope

Grill agenda item 1, verified: **no `return_threat` term exists anywhere in `src/`.** It appears only
as design prose in `docs/plans/opponent-value-equation-unification.md:300-303`, which itself states the
shorthand `KO_prizes + tempo − return_threat` was *"the design description; the built code has the
positive terms but not the `return_threat`."* Issue #190 (S5) owns it. Nothing to reconfirm at build
time.

### Finding 6 — one charter frame has already left this issue

`86091435-13` — the frame both of this issue's first two comments are about — was **moved to Issue #165
by user ruling 2026-07-29** (`tests/fixtures/corrections/dp_gust_wasted_over_item_lock_retreat_f13.json`):
*"we already ruled that f21 is a turn planner issue… not our business."* The gust reading is retired
there because the shipped agent no longer plays Boss's Orders on that board (it returns `[0]` Ultra
Ball). Those two issue comments are stale and should not be read as scope.

## Decision

**1. Issue #189 is RECHARTERED from a one-surface repoint to a three-surface audit with a
per-surface currency ruling. A scale boundary is crossed on exactly ONE surface.**

The charter's single behavior-preserving lift is withdrawn on findings 1–3. In its place, each of the
three surfaces is ruled on its own, and the currency question — the debt ADR-0076 Amendment E raised,
Amendment F moved away, and ADR-0080 decision 4 sent back — is asked only where a value actually has to
meet a differently-denominated one:

- **(c) which body — NO exchange rate is needed.** Every option at a `_SWITCH` select carries the same
  `KO_SCORE` offset, so the eight terms function purely as an **ordering within one `OptionType` lane**.
  That is an ADR-0072 **Axis Claim** (*"ordering within one lane, resolved by body slot… ordering
  survives a currency re-banding"*), which is precisely the shape that does not need a rate. This is
  structurally the same answer ADR-0080 decision 3 gave deny's surface (c) — `argmax`, not a magnitude —
  reached by different reasoning: deny's ranking is categorical, gust's is a genuine prize magnitude
  that happens never to be compared against another scale.
- **(b) fire now — the rate needed already EXISTS and is DERIVED.** This surface writes to `score` on
  the damage/tactical scale, and `currency.PRIZE_DAMAGE_RATE = 100.0` with `currency.prize_to_damage`
  is exactly the prize↔damage bridge, derived from the card set (median HP-per-prize over 1061 bodies)
  and recomputed rather than pinned by `tests/strategy/test_currency.py`. Nothing underivable is
  required here.
- **(a) keep price — this is the ONLY scale crossing, and it is the underivable leg.** A
  prize-denominated value entering the card-worth-summing `_keep_slot_dp` needs the **Worth Damage
  Rate**, which ADR-0080 measured underivable from the corpus as it stands and deliberately did not
  ship. Gust has no escape of deny's kind: ADR-0080's Consequences say so outright, and finding 2
  confirms it — dragging a body into the Active Spot is a real prize magnitude, not a relevance read.

**Consequently the acceptance criteria are rebuilt.** "The four bench frames hold unchanged" is
retired as vacuous (finding 3). `85164131-22` is handed to Issue #188 as a snipe frame.
`85785067-41` is retained but **re-labelled** as a surface-(c) *non-KO strand* frame, not a
`_gust_target_tactical` one. `85163079-30` and `86089120-14` are retained as surface-(b) frames.
Coverage for the KO-gated target pick must be **authored**, not harvested — the same conclusion
ADR-0080 reached about its own worked examples, and for the same reason.

**2. On surface (c), the shared survival leg is the SUB-LETHAL RESIDUAL. `_gust_target_denial` keeps
the lethal case at its prize denomination, and gust adopts the shared PRIMITIVE without the shared
COMPOSITE.**

The two terms make different claims about the same removal, and the conflict is not a denomination
mismatch to be converted away — it is a lethality boundary:

| | `_gust_target_denial` (`doctrine_gust.py:227`) | shared survival leg (`needs.py:251`) |
|---|---|---|
| fires when | target carries Energy **and** its weakness-doubled best attack ≥ my Active's HP | any Δ in `combat.turns_to_ko_me` from removing the body |
| returns | my Active's **full prize value, up to 3.0** | `min(_SURVIVAL_CAP 0.9, shift × phase × 0.5)` |
| claim | *prizes I do not lose* | *turns of tempo I gain* |

`_SURVIVAL_CAP` is documented as *"breaks ties among prize outcomes, never overrides a real prize
difference."* ADR-0022's ruling that `_gust_target_denial` exists to enforce is the exact inverse —
*"a live attacker that would take my win-condition outranks a bigger but INERT prize; prizes-first is a
trap."* So capping the lethal term at 0.9 would **overturn ADR-0022**, and summing the two terms would
double-count one physical fact under two denominations (the `_PRIZE_UNIT` failure mode in miniature).

Ruled instead: `_gust_target_denial` is unchanged and owns the lethal case; `phase × survival_shift` is
added **gated on `_gust_target_denial == 0`**, so the two are mutually exclusive by construction. This
extends **ADR-0073**'s seam (*"the promote/retreat equation is the sub-lethal residual in damage"*) to
the gust instrument — the same lethal/sub-lethal split, already this codebase's idiom rather than a new
invention.

The consequence for ADR-0078 decision 1 is precise: gust adopts the shared **primitives**
(`combat.turns_to_ko_me` Δ, `needs.phase_scale`) and declines the shared **composite**
(`needs.opponent_target_value`). The six gust-specific terms are untouched, so no existing corpus
ruling is re-opened. It is a genuine behaviour change on (c) — so it needs authored fixtures (there are
none today, finding 3) and both ADR-0072 merit gates before arming, not a byte-identical claim.

**3. On surface (b), the KO rungs become a MAGNITUDE read off surface (c)'s own value;
`gust-for-the-loaded-equal-ko` is DELETED as subsumed; the three stall rungs stay GATE-shaped.**

Today all five `HYPOTHESES` contribute **flat** weights — `gust-for-the-ko` 50,
`gust-for-the-loaded-equal-ko` 50, `gust-for-the-stall` 10, `stall-gust-over-dev-when-starved` 95,
`gust-to-strand-the-key-attacker` 20 — while their `when` clauses compare prize *counts*. So a gust
taking 1 prize and a gust taking 3 score identically, and the play surface cannot agree with the target
pick even though `doctrine_gust.py`'s own docstring claims *"ONE oracle feeds both decisions, so the
play-reason and the picked target agree by construction."*

Ruled: the play value becomes `prize_to_damage(max over targets of the (c) value) − the Supporter cost`,
compared against the same menu baseline as today. That is the ADR-0065 fold with the rate it needs
already **derived** (`currency.PRIZE_DAMAGE_RATE`, recomputed from the CSV by
`tests/strategy/test_currency.py`), and it makes the docstring's claim true instead of aspirational.

Three things are explicitly preserved:

- **`_gust_tactical`'s lethal `KO_SCORE` band stays ungraded.** A game-winning gust must dominate, not
  compete.
- **Every guard stays a guard** — the menu-total comparison, the ADR-0066 threat-forfeit premium, the
  Supporter-economy damping, and `opp_active_condition_gift`. Grading the *value* does not convert a
  gate into a magnitude.
- **`gust-for-the-loaded-equal-ko` is deleted, not suppressed** (tracker standing directive #1). Its
  entire content is `gust_ko_energy_swing >= _LOADED_KO_SWING` (2), and `_gust_energy_denial` already
  prices sunk Energy continuously inside (c)'s sum — so a graded value expresses the threshold as the
  magnitude it always was. `ep85163079 f30` is re-validated as an ADR-0072 **Endorsement Claim** rather
  than a rung-presence check.

**Hygiene owed with this change:** the module docstring (`doctrine_gust.py:7`) and the section comment
(`:447`) both still say *"the two positional weights"*. There are five. The count grew without either
line updating, and the deletion above makes it four.

<!-- Decisions 4+ land as the grill rules them. -->

## Consequences

- **ADR-0078 decision 1's one-backend claim now fails for a second instrument, for the opposite
  reason.** Deny left the shared backend because its value is *not a magnitude at all* (ADR-0080).
  Gust's relationship to it is the inverse: gust's value is a magnitude four times richer than the
  two-term backend. Whether that means gust reads the backend, extends it, or keeps its own composite
  is the next ruling, but "one backend feeds all three" is already not what shipped.
- **A live, armed defect is now named** (finding 4): `gust_target_slots` has been ON since 2026-07-27
  while its slot cannot win an assignment for a first copy. ADR-0076 Amendment E's *"0 decision flips
  across 331 corpus frames"* is fully explained by that, and is an instance of tracker directive #9 —
  *record what made the sweep clean* — with the sharper answer that nothing absorbed it; it never fired.
- **The Discrimination Gate baseline is unaffected by findings alone.** No code has changed; these are
  readings. The gate must still be run **before** any arming decision (ADR-0072 decision 5), which is
  the ordering ADR-0076 Amendment E got wrong.
- **Two of the four charter frames were never this issue's**, and one more (`86091435-13`) left for
  Issue #165 (finding 6). Issue #189's real corpus footprint is smaller than its charter implies and
  must be grown by authoring.

## Alternatives rejected

- **Keep the one-surface charter** (repoint `_gust_target_tactical`, leave (a) and (b)). Literal
  compliance with the issue, and the smallest change. Rejected on findings 2–3: it must either discard
  six terms or duplicate them beside the seam, its acceptance criterion cannot detect either outcome,
  and it leaves the armed dead slot from finding 4 in place. Small blast radius is not a virtue when
  the narrow change is the one that bypasses the seam.
- **Keep-slot only** — disarm `gust_target_slots` back to `deny` routing at 10.0 and defer (b)/(c) to a
  new issue. Attacks the one live defect directly and is genuinely tempting. Rejected because it
  abandons the S4-gust charter mid-family and leaves Issue #190 without gust's half of the
  decline-a-prize gate, which is the one thing #189 is recorded as blocking.
- **Port ADR-0080's relevance shape to gust** — rebuild gust as a `[0,1]` scalar scaling incumbent
  constants. Attractive symmetry, and both instruments would then share one design language. Rejected
  on ADR-0080's own pre-emptive finding: gust *"has no escape route of deny's kind — a gust card's
  value genuinely is a magnitude (it drags a body into the Active slot)."* Compressing prize counts and
  a second body's snipe prize into `[0,1]` discards information the KO terms are built on.
- **Promote gust's 8-term sum to BE the shared backend** that snipe also reads. Inverts the repoint
  rather than abandoning it, and would honour ADR-0078 decision 1's spirit. Rejected as circular:
  `_gust_snipe_synergy` already calls into the snipe rider oracle, so a snipe read of a gust-shaped
  backend would close a loop, and it would drag MatchupPlan γ-scaling into surfaces that do not want it.
- **Extend `needs.opponent_target_value` with the six missing terms** so the backend stays single.
  Rejected: six gust-specific terms inside a function three instruments read is not a shared backend,
  it is gust's function with other callers.
- **Grade all five play rungs, stall rungs included** (decision 3's live alternative — raised in the
  grill and argued on the merits rather than waved off). The mechanism is **more available than it first
  appears, and the first draft of this rejection was wrong about that**: a stall gust genuinely does buy
  survival turns, `combat.turns_to_ko_me` already takes `opp_active=` so the clock can be re-read with
  the gusted body forced Active, `phase_scale` converts turns → prize-equivalents, and
  `_strip_delta_terms` (behind `deny_strip_delta`, ADR-0080 Amendment A) is a shipped precedent for the
  mutate-and-re-read seam. No invented constant is required. Rejected on four other grounds:
  1. **The famine rungs are PRECEDENCE claims, not magnitude claims.**
     `stall-gust-over-dev-when-starved` has seven conjuncts and six describe *my* inability to act
     (`active_doomed`, `active_famine`, `gust_best_ko_prizes == 0`, `active_ko_prizes == 0`). That is a
     last-resort tier — "when nothing else helps, do this" — and which rung wins under famine is a
     user-ruled doctrine ordering (`ep83457493 f20`, Boss's ≻ Salvatore), not a quantity.
  2. **`_SURVIVAL_CAP` would cap a stall at ≈90.** `prize_to_damage(0.9) = 90` against a weight
     deliberately set to **95** so it outranks a tutor's dig stack under the famine gate. Suggestive
     rather than conclusive — positional weights add to tactical score rather than replacing it — but
     the direction is wrong and it risks `ep83457493 f20` for no gain.
  3. **Stall marginality has ALREADY been ruled, as a gate, on this issue's own frame.** ADR-0066
     shipped `_stall_swap_pointless` — *"stall value is with-vs-without the swap, never a flat strand
     bounty"* — decided on `ep86091435 f13`. Re-litigating it as a magnitude overturns ADR-0066 with no
     new evidence.
  4. **Blast radius against an empty evidence base.** It puts ~6 rulings at risk (`ep83457493 f20`,
     `ep82751468 f57`, `85785067-41`, `dragapult f10`, `ml f19`, `dp f70`) in an issue with zero
     authored fixtures of its own (finding 3), spending the whole risk budget on the surface with the
     least to gain.

  **Where it should go instead:** the repositioning Δ this needs is the same primitive `return_threat`
  needs — *what promotes back after the gust, and can it hurt me?* That is **Issue #190 (S5)**, which
  already owns the bad-trade gate. Build the Δ once, there, with both consumers present.
