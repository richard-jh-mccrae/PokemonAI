# ADR-0135 - A retreat Tool is priced by the MOBILITY it buys, and the composer structurally cannot price it

**Status:** Accepted (Issue #423, 2026-08-09); BUILT. Adds one channel to ADR-0069's attach decider
and CONSUMES ADR-0100's retreat equation unmodified. Re-points two false `FOLDED` rows left by
Issue #386. **Amends nothing.**

## Context — two mechanisms, both silent

`_attach_value` refused every Pokémon Tool at its own guard (*"a Pokémon Tool is not Energy"*), and
the composer — the MAIN decider since Issue #386 — prices a Tool attach at **exactly 0.0**.

Measured on all 7 corpus frames that offer an Air Balloon, applying each option through the shipped
`apply_option` seam and diffing every `state_value` family:

| | measured |
|---|---|
| 25 Air Balloon applications, 7 frames, every recipient | `Δ = +0.000000`, **empty leg set**, including `hand` |
| *positive control* — Basic {F} → Lunatone@BENCH0 | `readiness` **+0.004482** |
| *positive control* — PLAY Solrock | `development` **+0.104167**, `survival` −0.000488 |
| *positive control* — a flat-HP Tool on a damaged holder | `survival` **+0.755063** |

So the silence is the codebase's, not the instrument's. The cause is narrow: the only value-consuming
reader of `BodyView.tool_ids` anywhere in `src/` is `state_model.damage_boosts` (the `damageBoost`
class). `composer._still_legal` reads it too, but as a LEGALITY gate — one Tool per body.

Consequence: on the three frames whose human ruling is *Air Balloon on the Active*, the Active was
indistinguishable from every benched body, every recipient's best sequence tied to six decimal
places, and `_composer_line`'s tie-defer (ADR-0131) abstained — onto a score term that also abstained.

## Why the composer is not the home, and cannot be

`board_delta._retreat` is the whole retreat transition:

    current["retreated"] = True
    return Delta(obs=new_obs, writes=frozenset({"allowance_retreat_used"}))

No Active/bench swap and no Energy discard, because the engine poses cost and promotion as separate
selects and the MAIN option is a bare `{"type": 12}`. **A retreat inside a composed sequence therefore
has no consequence to score**, so no `state_value` term could make the composer value mobility — the
board it would price is the board it started on. That is Issue #385's beam admission, named in that
function's own docstring, and it is why this channel lives in the Pilot's score term instead.

## Decision

    mobility(A) = 0.0                                  if the retreat is UNAFFORDABLE on A
                = max(0, best_B promote_value(B, A))    otherwise
    term        = clamp(mobility(A with tool) − mobility(A without tool), ± _ATTACH_RETREAT_EQUITY)

`best_B promote_value(B, A)` is ADR-0100 §9's whether-site, asked as a COUNTERFACTUAL — the same
`_retreat_cost_legs` / `_promote_body` / `promote_value` chain the retreat decider already runs.
`retreat_cost.py` and `promote_retreat_value.py` are UNCHANGED; two functions gained a keyword-only
`active=` so the counterfactual body can be passed instead of duplicating them.

Four properties carry the design:

1. **0.0 off the Active by ARITHMETIC, not by an area gate.** Both legs read `_my_active(obs)`, so a
   Tool landing anywhere else differences one board against itself. No `if area == _ACTIVE` exists to
   get wrong later.
2. **Fires when the Tool makes an ILLEGAL retreat legal** — the without-leg is 0 because the option
   does not exist. This is the case the refuted equation scored 0.0.
3. **Cannot explode when the retreat is already legal** — both legs are floored at 0.
4. **SIGNED** (Issue #306): a surcharge Tool can drop the with-leg to 0 while the without-leg is
   positive. Gravity Gemstone prices negative.

Scope is `retreatReduction != 0`. A Tool that moves no Retreat Cost still ABSTAINS.

## What was refuted on the way

The issue's ORIGINAL equation differenced `RetreatSide.retreat_cost()`. That leg prices **the Energy a
retreat discards**, not whether a retreat is possible — `build_after` is the Active's Build Standing
after discarding `effective_retreat_cost` Energy, so with **zero** Energy attached it returns 0, which
is precisely when the Tool converts an illegal retreat into a legal one. Built and evaluated on all 7:

| frame | ruled | refuted equation |
|---|---|--:|
| `85058574-87` | Balloon → ACTIVE | +270.0 |
| `85709280-42` | Balloon → ACTIVE | **0.0** |
| `85709280-55` | Balloon → ACTIVE | **0.0** |
| `84071010-64` | {F} → Makuhita | **+270.0** |
| `86090147-22` | RETREAT | +6.67 |
| `85058051-4` | Ultra Ball | 0.0 |

Right on 1 of 7, silent on 4, wrong by +270 (Mega Brave's whole printed damage) on 2.

## The clamp, and what it costs

**Half principled, half fitted — recorded as such rather than defended.** That *a* bound exists is
principled: `_ATTACH_RETREAT_EQUITY` is ADR-0069 §1's declared price of FULL coverage of a printed
Retreat Cost, and two claims about one Retreat Cost must not disagree by fifty times. That the bound
is exactly that constant is a choice the corpus decided, not an argument.

| | ruled Balloon frames matched | regressions |
|---|--:|--:|
| before this change | 1/6 | — |
| uncapped | 3/6 | **1** (`84071010-64` moved OFF its ruling) |
| clamped | **4/6** | **0** |

Uncapped, one unlocked retreat priced 160.47. **The cost is real and is not smoothed over:** above the
band the channel is FLAT, so an unlocked retreat worth 3.0 and one worth 160.5 now price identically,
which gives up the currency-consistency argument that made the raw number defensible. A graded form
inside the band is the open question; nobody has ruled on it.

Two variants were built and REJECTED on measurement, not taste:

- **A flat per-recipient credit** (mirroring `_attach_retreat_equity`'s own shape, +3.0 on these
  bodies) so that no play prices exactly 0. It moves the pick ONTO the Balloon on `85058051-4` and
  `86090147-22` — the two frames whose Correction category is literally `wasted_resource`. Inventing a
  credit to avoid a zero reproduces the blunder the corpus is complaining about.
- **Charging the Active's forgone attack.** Conceptually wrong for a Tool: attaching one costs no
  allowance and does not end the turn, so it buys an OPTION that a later retreat pays for itself.

## Measured

Suite 5121 passed / 4 skipped / 43 xfailed (`tests/arena`, `tests/sim`, `tests/submit` excluded —
all three segfault the interpreter on clean `HEAD` too, attributed by stash with the revert asserted
by `git diff --stat`). Discrimination Gate output **byte-identical** with and without the change.
Decision Gate agreement **199/343 → 202/343** (context 0: 132/254 → 135/254); `85058574-87` enters
FIX, `85709280-42` and `85709280-55` leave REGRESSED; the gated number — unruled REGRESSION — is
**49 before and 49 after**. **Neither gate is green, and neither was before this change**: both have
been red on `main` since Issue #386 armed the composer with unruled flips by design.

## Two records this corrects

`tools/rung_registry.py` recorded BOTH `deploy-hp-tool` and `hold-the-retreat-tool-with-no-retreat`
as folded into `common.composer:compose`. Measurement says the composer absorbed neither.
`hold-the-retreat-tool-with-no-retreat` and `equip-the-retreat-tool-on-the-active` are now EMERGENT
from this channel; `deploy-hp-tool` becomes `UNREPLACED` — the +HP class moves `survival` only when
its grant crosses the integer `turns_to_ko_me` clock, which on sampled Hero's Cape frames is **1 of
6**. That class is a real second gap and belongs to ADR-0028's survival-turns math, not here.

## What the review caught

Its own `/code-review`, briefed that the spec was SELF-FILED, found four things, and both axes
independently re-verified the load-bearing claim at source with a positive control before grading it:

- **A VACUOUS test.** `test_the_benched_zero_is_arithmetic_and_not_an_area_gate` compared
  `_retreat_option_value(obs, board, active)` to *itself* — a tautology that could not fail, guarding
  the one property (0 by arithmetic) the design rests on. It now asserts the oracle DISCRIMINATES on
  that board before asserting the bench differences to 0.
- **An acceptance criterion with no test at all**: the frames whose ruling is NOT a Balloon had no
  guard, which is exactly where a mobility channel would do damage.
- **Measurements living in comments** instead of here. This ADR is where they were moved to.
- **The spec's own §3 table was stale against the shipped build** — it described the uncapped run in
  places and the clamped run in others, and its acceptance magnitudes (11.328 / 160.469) are
  unreachable once the clamp lands. Corrected in the issue body.

A pre-existing defect was fixed in passing and is flagged rather than folded in silently:
`tests/scouting/test_cardstat_fixture_facts.py::_csv_truth` built its `fake_card` with
`skills=[str]`, but `card_text._skill_texts` reads `s.text` / `s["text"]` and skips a bare string —
so the audit derived `hpBonus=0` and `retreatReduction=0` for **every Tool in the pool**, including
Hero's Cape's unambiguous +100. Every Tool fixture in the tree had been marking itself
`synthetic=True` to route around it. Both legs are now derived and genuinely checked against the CSV.

## Superseded by Issue #500

The local ADR-0100 counterfactual and ADR-0069 clamp are retired. The Composer can now price the
current-turn legal-pivot option because `board_choice.legal_manual_retreat_outcomes` materializes the
full swap, whole-card discard, condition clear, and allowance spend. Tool scoring consumes only the
canonical Active-position marginal. Direct HP remains owned by `survival`; canonical zero abstains.
