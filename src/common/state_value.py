"""**State Value** — the ONE prize-denominated scalar for a board (POC-T3, ADR-0092, Issue #262).

`state_value(model)` answers *what is this position worth, in prizes?*; a play is priced by
DIFFERENCING it against `apply_option`'s closed-form `after`. Damage crosses on
`currency.PRIZE_DAMAGE_RATE`, Worth only on :data:`POC_WORTH_PRIZE_RATE`; one prize == `KO_SCORE`.

Three standing constraints (reasoning in the ADRs):

* TWO BANDS — `prize_race`/`survival` forecast real prize flow and are UNCAPPED; the four positional
  families are scale-anchored then runaway-guarded, and `LOSS_PRIZES`/`WIN_PRIZES` derive above both
  (`ko-score-band`, `sound_rules.py`).
* DOUBLE-COUNTING — every board fact enters through exactly ONE family (:data:`REGISTRY`), `reads`
  asserted pairwise disjoint (ADR-0092 §4-T0).
* CANNOT price information ORDERING — both orderings reach the SAME end state, so no end-state
  function separates them; a structural rule, not a gap (ADR-0095 decision 3)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Mapping, NamedTuple, Sequence

from common import currency, needs as _needs
from common.card_worth import ROLE_TIER
from common.grading import HORIZON, halve
from common.strategy.context import ENERGY_RECOVER, FOLLOWUP_W, _BENCH_MAX
from common.strategy.sequence import followup_damage

if TYPE_CHECKING:                      # the seam, expressed without importing the Pilot's world at
    from common.state_model import StateModel   # runtime — `deploy_value`'s "no engine, no obs" rule

#: **AUTHORED, never derived** — 1/120 prizes per Worth point, the one Worth->prize bridge (ADR-0097).
#: A LITERAL, not an expression over `currency.py`'s DERIVED constants, and it must never migrate there.
POC_WORTH_PRIZE_RATE: float | None = 1.0 / 120.0

# ── the positional band — every constant below is a SCALE anchor or a RUNAWAY GUARD ───────────────
# Bound per-play, never as a family TOTAL: a saturated term has zero derivative and is never explored.

#: Scale anchor for `readiness` — `planner._READINESS_ATTACK_W` 0.45 re-expressed at 1 prize ==
#: `KO_SCORE`. Prices POTENTIAL only; the swing is `attack_ev`'s. Importing the planner = a cycle.
_READINESS_W = 0.045
#: `planner._READINESS_BODY_CAP` 120 / `KO_SCORE` — a RUNAWAY GUARD; the biggest body lands ~0.095.
_READINESS_BODY_CAP = 0.12
#: `planner._READINESS_CAP` 300 / `KO_SCORE` — the whole board's readiness. Runaway guard.
_READINESS_CAP = 0.3
#: `planner._PLANNER_THREAT_CAP` 100 / `KO_SCORE` — a RUNAWAY GUARD that DOES bite (Issue #329).
#: **Do not fold `_THREAT_W` in**: :data:`POSITIONAL_MAX` and :data:`LOSS_PRIZES` derive from it.
_THREAT_CAP = 0.1
#: `threat`'s scale anchor — DERIVED (Issue #329, ADR-0107's form): the cap over
#: `needs.TARGET_VALUE_CEILING`, `opponent_target_value`'s true ceiling. Both operands are shipped.
_THREAT_W = _THREAT_CAP / _needs.TARGET_VALUE_CEILING
#: A hidden hand card is one normalised target unit, so it cannot fill the threat band as a known body.
_OPPONENT_HAND_RESOURCE_W = _THREAT_W / _needs.TARGET_VALUE_CEILING

#: One body on the board, in prizes — `currency.DEPLOY_BAND` across `PRIZE_DAMAGE_RATE` (ADR-0086).
_DEPLOY_PRIZE_BAND = currency.DEPLOY_BAND / currency.PRIZE_DAMAGE_RATE

#: The LAST Bench slot's price, in prizes: exactly what the best possible body is worth, so filling
#: it with a spare Basic is a measured loss (Issue #232).
_BENCH_SLOT_PRICE = _DEPLOY_PRIZE_BAND

#: `development`'s runaway guard: a full board at the maximum per-body band.
_DEVELOPMENT_CAP = (_BENCH_MAX + 1) * _DEPLOY_PRIZE_BAND

#: `hand`'s runaway guard. The incumbent `_HAND_READINESS_CAP` (40 / `KO_SCORE`) is deliberately NOT
#: carried over: against the ratified Worth rate it would bite at Worth 4.8 and flatten every play.
_HAND_CAP = _DEVELOPMENT_CAP

#: Prize-proximity weight in :func:`prize_race`, anchored to `needs._PHASE_PRIZE_W`. Sub-prize by
#: construction — a difference of two `halve` grades — so it can never invert the LEAD leg.
_PROXIMITY_W = 0.5

# ── the terminal band ─────────────────────────────────────────────────────────────────────────────

#: A full Bench plus the Active; `_BENCH_MAX` is 5 (`docs/rulebook.txt` L75).
_MAX_BODIES = _BENCH_MAX + 1
#: The biggest prize yield in the set — a Mega Evolution Pokemon ex (`docs/rules.md` §6, RULE L333).
_MAX_PRIZE_VALUE = 3.0
#: The Prize count both sides race down from (`docs/rulebook.txt` L57). One fact, one home (ADR-0087).
_PRIZES_START = _needs._PRIZES_START

#: The four positional runaway guards, summed. :data:`LOSS_PRIZES` is DERIVED from this plus the
#: prize-denominated maxima plus a prize of headroom, so it dominates by construction, not by taste.
POSITIONAL_MAX = _THREAT_CAP + _READINESS_CAP + _HAND_CAP + _DEVELOPMENT_CAP

LOSS_PRIZES = (
    _MAX_BODIES * _MAX_PRIZE_VALUE
    + _PRIZES_START + _PROXIMITY_W
    + POSITIONAL_MAX
    + 1.0)

#: An ACHIEVED GAME WIN, in prizes — the DERIVED mirror of :data:`LOSS_PRIZES` (Issue #362).
#: `survival` is absent from the sum: it is non-positive, so a win has no exposure of its own to clear.
WIN_PRIZES = (
    _PRIZES_START + _PROXIMITY_W
    + POSITIONAL_MAX
    + 1.0)


class ExposedBody(NamedTuple):
    """One of MY bodies as `survival` reads it. NAMED rather than a bare ``(float, int)``: a
    transposed anonymous pair still type-checks and prices the board wrong."""

    prize_at_risk: float
    #: Turns until they can Knock it Out; 1 = on their very next turn.
    turns_to_ko_me: int


class ReadyBody(NamedTuple):
    """One of MY bodies as `readiness` reads it — named for :class:`ExposedBody`'s reason."""

    #: What this body achieves once online, in prizes.
    payoff: float
    #: P(it gets there), from the Attach-Budget / readiness-odds machinery. In [0, 1].
    readiness_odds: float
    #: How much this body's role matters to the current plan. In [0, 1].
    role_relevance: float


@dataclass(frozen=True)
class TermFamily:
    """A family, the facts it prices, and the facts it refuses. A fact in some ``does_not_read``
    and in no ``reads`` is a coverage hole with an address — see :func:`registry_gaps`."""

    #: The family's name, and its key in the `working` breakdown.
    name: str
    #: Board facts this family PRICES. Pairwise disjoint across the registry, asserted by test.
    reads: tuple[str, ...]
    #: Facts left to another family. An entry no family `reads` names a gap.
    does_not_read: tuple[str, ...]
    #: How the family composes — the frozen semantics.
    composition: str
    #: Dimensions this family plausibly OUGHT to price and knowingly does not — owned by NOBODY,
    #: unlike `does_not_read`. Under 1-ply differencing a 0 delta is never explored. Read by nothing.
    blind_to: tuple[str, ...] = ()


#: **The coverage map** — the six families of ADR-0092 §4-T0.
REGISTRY: tuple[TermFamily, ...] = (
    TermFamily(
        name="prize_race",
        reads=("my_prizes_remaining", "their_prizes_remaining"),
        does_not_read=("prize_at_risk", "opponent_target_value"),
        composition="Lead plus proximity over the two prize counts. The RACE only — what a body is "
                    "worth when it falls is `survival` (mine) or `threat` (theirs), so the prize "
                    "VALUES of individual bodies are deliberately absent here. One reader arrives "
                    "from the other side and must not mistake it for a breach: `survival`'s "
                    "terminal `_predicted_loss` ALSO reads `their_prizes_remaining`, as a "
                    "win-condition TEST rather than as race value (ADR-0064 Amendment B, Issue "
                    "#283). Lead-and-proximity stays this family's alone.",
        blind_to=(
            "deck_count / deck-out proximity — win condition 3 (`docs/rules.md` §7) is a second "
            "race and no family reads either side's deck count. A mill or a heavy-draw line moves "
            "it and prices 0. Owned post-POC; the corpus has no deck-out frames.",
            "turn number / who went first — the tempo half of a race. `model.turn` exists; no "
            "family reads it, so a line that trades a turn for position prices the trade at 0.",
        ),
    ),
    TermFamily(
        name="survival",
        reads=("prize_at_risk", "turns_to_ko_me", "bench_harvest", "predicted_loss"),
        does_not_read=("my_prizes_remaining", "readiness_odds"),
        composition="Sum over MY bodies, both areas, of prize_at_risk x halve(turns_to_ko_me - 1), "
                    "Bench-Harvest-aware. Both of this family's damage reads — the "
                    "`turns_to_ko_me` clock and `_predicted_loss`'s Incoming — are taken at "
                    "`damage_context(attacker='theirs')`, so a scaling attack of theirs prices its "
                    "actual damage rather than its printed 0 (Issue #280); the direction is the "
                    "attacker's, and on a survival read the attacker is them. "
                    "`_predicted_loss` (ADR-0064) survives here as a TERMINAL "
                    "term at `LOSS_PRIZES`, outside the positional band by construction. The band "
                    "is the SUM of the positional caps (readiness 300 + survival 50 + threat 100 + "
                    "value 40 + line 100 = 590) against KO_SCORE 1000, of which `_LINE_CAP` is the "
                    "line term's 100 (`strategy/planner.py`) — a loss-avoidance value cannot be "
                    "both bounded under that band AND un-outbiddable, so it is neither. That "
                    "terminal term prices BOTH loss conditions of `docs/rules.md` §7 a next-turn "
                    "Knock Out can reach (ADR-0064 Amendment B, Issue #283): case 2, no Pokémon in "
                    "play to promote, and case 1, the Knock Out takes their LAST prize. "
                    "**Case 1 consults `their_prizes_remaining`, and that is not a disjointness "
                    "breach**, which is stated here because it is the first thing a reader of the "
                    "tuples will suspect. It is consulted as a WIN-CONDITION TEST and never as race "
                    "value: does THIS body's prize yield cover what they still need? Lead and "
                    "proximity stay `prize_race`'s alone and this family prices neither. The "
                    "registry fact remains `predicted_loss` — already in `reads` — because what "
                    "enters the scalar is the terminal verdict, not their count; the count is an "
                    "input to that verdict the way `turns_to_ko_me`'s own inputs are. Splitting the "
                    "count into a second fact string to make the read visible was considered and "
                    "rejected: `sound_rules.SCHEDULED_PAIRS` records the same temptation and the "
                    "same answer — a fact renamed to dodge a detector makes the detector pass "
                    "VACUOUSLY. Which is exactly why this paragraph exists instead.",
        blind_to=(
            "the MARGIN below the case-1 win-condition test — a body whose loss hands them 2 of "
            "the 3 prizes they need is worse than the flat exposure above and prices identically "
            "to one that hands them none, so moving a body across that margin is a genuine 0 "
            "delta. BINARY is Issue #283's explicit POC ruling (a terminal term firing on a "
            "non-terminal fact is the worse error), which makes this an OWNED zero rather than an "
            "oversight: the graded form is the named post-POC question and nobody prices it today.",
            "special_conditions — Asleep/Paralyzed/Poisoned/Burned change what survives and what "
            "can act, and `snapshot_coverage` lists the zone as OWED (no snapshot home). Curing a "
            "condition therefore prices 0. Owned by T1 (Issue #260) via the completeness contract.",
            "attached_tools — a defensive Tool's survival contribution (ADR-0028's math) has no "
            "snapshot home either, so equipping one prices 0 at ordering time. Same owner.",
            "healing that does NOT move `turns_to_ko_me` — the clock is integer turns, so a heal "
            "smaller than one turn of incoming is invisible here. Real, accepted at POC bar: the "
            "clock is the shipped survival vocabulary and a sub-turn HP term would be new math.",
        ),
    ),
    TermFamily(
        name="threat",
        # `denied_forward_payoff` -> `denied_line_prize` (ADR-0119) is a REPLACEMENT, not a rename:
        # the old fact was forward DAMAGE, which `incoming()` already puts inside `survival`.
        reads=("opponent_target_value", "my_reachable_kos", "denied_line_prize",
               "opponent_hand_resource"),
        does_not_read=("turns_to_ko_me", "their_prizes_remaining"),
        composition="Their exposure to ME: per-body `needs.opponent_target_value` over the Knock "
                    "Outs I can reach, across BOTH seats. The mirror of `survival`, and the reason "
                    "THIS family must not read a clock — `turns_to_ko_me` is THEIR clock on MY "
                    "bodies, which says nothing about how exposed THEIR bodies are to me, so "
                    "reading it here would be a genuine second pricing of `survival`'s fact rather "
                    "than a different consequence of it. (Since Issue #332 `readiness` DOES consult "
                    "the clock, on the forward leg of `readiness_odds`; that is argued at "
                    "`_survives_to_spend` and is a different question from this one. The rule was "
                    "never *at most one family may consult a fact* — it is *at most one family may "
                    "PRICE it*, which is what `reads` records.) "
                    "Reach is one affordability filter (the Attach Budget) over two damage "
                    "ROUTES: their Active through `best_reachable_damage_vs`, the DAMAGE MODEL "
                    "against the body actually in front of me (Weakness, Resistance, prevention, my "
                    "live boosts — Issue #281); their Bench through `best_reachable_bench_damage`, "
                    "the attack's single-target snipe RIDER, which ignores Weakness and Resistance "
                    "by rule and is zeroed on the Active path (Issue #284). What the bench leg "
                    "prices is the STANDING position — chip already on their bench makes a body one "
                    "rider from dead between turns — never the conversion, which stays `attack_ev`'s. "
                    "`prize_advance` then carries the denied LINE PRIZE (`needs.line_prize_advance` over "
                    "`theirs.forward_line_prize`) — ADR-0119 REPLACED the forward-payoff leg rather "
                    "than renaming it — the same "
                    "anchors, because forward payoff is printed damage held as POTENTIAL on either "
                    "side of the board. Not a second reading of `development`, which is MY-side only "
                    "by its own `blind_to`: this prices ONE reachable Knock Out more precisely, from "
                    "card knowledge about that body, and reads nothing about their board.",
        blind_to=(
            "SPREAD riders as a bench route — `benchSpread` is a SHARED counter budget across their "
            "whole Bench (Phantom Dive: *put 6 damage counters on your opponent's Benched Pokémon "
            "in any way you like*), so crediting its full total against each body separately would "
            "claim three Knock Outs from one 60-counter payload. The subset question has an owner "
            "— `CombatMath.spread_ko_prizes`' `best_ko_subset` knapsack — and it answers in PRIZES "
            "over a whole Bench, which does not compose into this family's per-body shape. So the "
            "bench leg reads the indivisible single-target snipe only and UNDER-reads the three "
            "spread attacks in the pool (Flutter Mane 20, Sinistcha 40, Dragapult ex 60). Under-"
            "reading my own damage is the fail-closed direction; no attack in the set prints both "
            "riders, so nothing is double-counted by the split.",
            "a multi-target snipe's COUNT — `AttackStat.benchSnipe` holds the PER-BODY damage and "
            "no multiplicity, so Kyurem's Trifrost (*110 damage to 3 of your opponent's Pokémon*) "
            "and Greninja ex's 2-target rider read as reachable against a fourth and fifth body "
            "they could not actually all fell. An over-read, and unrepresentable as a fix without a "
            "new parsed field. **It was free while the cap bound on every input; since Issue #329's "
            "scale anchor it is not.** A phantom extra target now costs `_THREAT_W` x its "
            "`opponent_target_value` — 0.0256 prizes for a 1-prize body, up to 0.0769 for a Mega ex "
            "— where it previously cost exactly 0, and the corpus carries 2 or 3 targets on 74 of "
            "614 non-empty calls. So this entry moved from harmless to priced, in the OVER-read "
            "direction, and it is the one entry here the anchor made worse rather than better.",
            "the BENCH LEG'S OWN REACH beyond the SNIPE RIDER — narrowed by Issue #284 and no "
            "longer erased by the cap. The old form of this entry recorded a ceiling that Issue "
            "#329 removed: `min(_THREAT_CAP, sum)` bound on every non-empty input, so a second "
            "reachable body added exactly 0 and a chipped bench under a reachable Active scored "
            "identically to a fresh one. **Both figures below are in `threat()` CALLS over one leaf "
            "pass (2061 calls, the leg severed to 0.0 as the control), so they are comparable**; "
            "Issue #284's own 904-ask / 338-reach / 13-move measurement is denominated in corpus "
            "FRAMES and is NOT the same denominator. Under the old equation the leg could only move "
            "the output by making an empty input non-empty, which is **278** calls. Under the "
            "anchor it moves **336**, by 0.023 to 0.077 prizes — and the extra **58** are exactly "
            "the boards where the Active leg ALREADY read something, the case the cap used to erase "
            "(commonest shape 0.0769 -> 0.1, 31 calls). What remains blind is the leg's reach "
            "itself: the route is the indivisible single-target rider, so spread payloads and "
            "un-parsed riders still contribute nothing at all.",
            "THE DENIAL CREDIT'S SIZE relative to the prize leg it rides on (Issue #285) — real, "
            "read, and small. Until Issue #329 it was not merely small but INVISIBLE: every "
            "appended target contributes `prize_advance >= 1.0` (`CombatMath.prize_value` returns "
            "1, 2 or 3 and never less), so `min(_THREAT_CAP, sum)` bound on every frame the loop "
            "touched and the credit could not move the family on ANY board. **Re-measured after the "
            "anchor** (same leaf pass, the then-`_denied_forward_payoff` severed to 0.0 as the "
            "control, and in the same CALL denominator as the entry above): the "
            "credit changed 327 of 614 non-empty inputs and moved `threat`'s OUTPUT on **296** "
            "of 2061 calls, by **0.000115 to 0.002192** prizes, against **0** calls under the old "
            "equation — a credit can never make an empty input non-empty, so this was the one leg "
            "the cap erased completely rather than partly. **RETIRED by ADR-0119**: that leg "
            "priced the forward DAMAGE a removal denies, which `incoming()`'s all-descendants gate "
            "already puts inside `survival`'s clock — and this module DIFFERENCES, so removing the "
            "body moves `survival` unaided. The measurement above is kept as the record of what the "
            "leg did while it existed, not as a live reading. `prize_advance` now carries the LINE's "
            "prize instead (`needs.line_prize_advance`), which is the half nothing priced. "
            "The residual 31 are where the runaway guard "
            "absorbs it — small, not zero, and no longer structural. "
            "**Two credit maxima are recorded in this module and they measure different things; do "
            "not overwrite one with the other.** 0.054 prizes is the largest SINGLE-target credit "
            "on the corrections corpus (Riolu 30 → Mega Lucario ex 270: 0.045 x 240/100 x "
            "halve(1); the doctrine's headline Staryu 20 → Mega Starmie ex 210 is smaller still at "
            "0.043). 0.0855 is the largest TOTAL across every target in ONE `threat()` call, which "
            "only became possible when Issue #284 let the loop append more than one body; at "
            "`_THREAT_W` that is the 0.002192 above. Both are correct at their own seam.",
            "THE PRIZE a denied line would have YIELDED — CLOSED by ADR-0119: `needs.line_prize_advance` "
            "prices the line's PRIZE, so a pre-evolution one hop from a 3-prize Mega ex no longer "
            "prices identically to a 1-prize body of equal printed damage. Kept as the record of "
            "the doctrine's own headline, *\"trade 1 prize for a denied 3\"* — the sentence is about "
            "PRIZES and this term answers in DAMAGE. Re-checked at Issue #329 and it SURVIVES the "
            "scale anchor unchanged, because the anchor scales the whole marginal and adds no leg: "
            "`ForwardPayoff` still carries no prize leg, and `development.evolve_marginal` still "
            "prices its my-side mirror the same way, so adding one here would give the same card "
            "two valuation bases across the board. What the anchor DID retire is the old reason "
            "given for deferring it — *\"the parked scale anchor first\"* — so this is now a plain "
            "ForwardPayoff-shape gap with no prerequisite, recorded so the damage-only reading is "
            "read as measured rather than as complete.",
            "THEIR DECKLIST, when crediting a denied forward payoff — `TheirSide.forward_payoff` "
            "reads the POOL-level forward index, so a Staryu on their board carries the Mega Starmie "
            "ex credit whether or not they run one, and the `reachable` leg is hardcoded True "
            "because their hand is a COUNT and their deck is untracked. Both are OVER-reads, both "
            "deliberate: `MySide.forward_payoff` can prove a line dead from `unseen_counts` and "
            "CANCELS the credit (`development.line_topology`), and claiming the same proof about a "
            "hidden deck would zero a denial against a threat that is perfectly real. The eventual "
            "narrowing supplier is the archetype Read (`TheirSide.read` / the matched Brief), which "
            "is a probability rather than a decklist — consuming it here would hand this family a "
            "second opinion about the Read, which the sole-supplier ruling forbids.",
            "BACKWARD topology on the denial credit — whether they can actually EVOLVE the body this "
            "turn. The credit prices what the line owes, not what they hold: an evolution card in "
            "hand, a Rare Candy skipping the Stage 1 (`data/EN_Card_Data.csv` id 1079), the "
            "played-this-turn gate (`docs/rules.md` §4) and their remaining hops are all unread, so "
            "a Dreepy they can never grow and one holding Drakloak price identically. `hand`'s "
            "mirror of this question is Issue #288's playability gate on MY side; there is no "
            "opponent-side equivalent and there cannot be one without their hand.",
            "the SCALING half of a denied payoff — the credit reads printed `maxDamage`, mirroring "
            "`MySide.forward_payoff` exactly so one card prices the same from either side. That "
            "makes it blind the way the printed forward index is blind: Alakazam's whole threat is a "
            "scaling term and its printed damage is 10, so denying an Abra credits almost nothing. "
            "`CombatMath.forward_threat_ceiling` is the board-priced instrument and is deliberately "
            "NOT substituted — using it on one side only would give the same card two valuation "
            "bases, and using it on both would retune `development.evolve_marginal`, which ADR-0070 "
            "rules.",
            "the non-Tera BENCH-IMMUNITY set — `docs/rules.md` §11's own warning: the immunity set "
            "is BROADER than Tera ex (Antique Plume Fossil, Misty's Magikarp, Poltchageist all "
            "carry unconditional prevent-all-while-Benched) and `CardStat` has no field for it "
            "(ADR-0020). `tera` is read and fails closed; the rest read as reachable and are "
            "over-credited. The residual gap, recorded rather than papered over — the fix is the "
            "same one ADR-0020 names, threading the engine's benched-immunity ability into "
            "`CardStat`.",
            "an {ex}-RESTRICTED bench rider — Zeraora's Thunder Raid (*210 damage to 1 of your "
            "opponent's Benched Pokémon {ex}*) parses to 0, so `slowking` gets no bench route from "
            "it. That is `parse_attack_bench_snipe`'s documented fail-closed doctrine (match only "
            "the clean unconditional phrasing; `tests/scouting/test_attack_riders.py` pins the "
            "restricted case at 0 by name), not a defect here — under-reading my own reach is the "
            "safe direction, and widening the parser is a card-fact change with its own blast "
            "radius over the whole pool.",
            "CONVERTING either seat's exposure into a prize — that is the attack's, and "
            "`attack_ev` prices it at the terminal action. This family prices the exposure STANDING "
            "on the board, capped at `_THREAT_CAP`, because `score(sequence) = state_value(end "
            "board) + EV(terminal)` adds the two and would otherwise pay for one Knock Out twice.",
            "their Energy denial / resource strip — removing fuel lengthens their clock without "
            "removing a body, and `opponent_target_value` prices bodies. `deny_relevance` is the "
            "instrument and is still dark (T2 / Issue #228 arms it).",
            "their DECK as a resource — their hidden composition has no sound value supplier. Their "
            "HAND COUNT is priced here; card identities remain hidden and are never fabricated.",
            "CHIP DAMAGE — progress toward a Knock Out I cannot yet complete. Reachability is a "
            "STEP: `_reachable_target_values` credits nothing for a body unless my Active's best "
            "reachable damage AGAINST THAT SEAT already meets its remaining HP, so a Mega "
            "Lucario chipped from 330 to 120 scores the same as one at full HP. Issue #281 made "
            "the step's height honest and Issue #284 gave their BENCH a step of its own — both "
            "legs are still steps, so bench chip that does not reach the rider still prices 0. "
            "This family is `survival`'s mirror "
            "in name and NOT in form — survival grades continuously by a clock "
            "(`halve(turns_to_ko_me - 1)`), while this family's REACHABILITY is on/off however "
            "finely Issue #329's anchor grades what a reached body yields — and that is exactly what "
            "the wave-3 ruling on `83116501|0|decision|60` objects to: *\"Our Starmie cannot KO the "
            "Lucario in under 3 turns. We can KO it with 2 Jetting Blows and a single Nebula "
            "Beam.\"* A multi-turn KO plan prices 0 every turn until the last one. Closing it needs "
            "a MY-side KO clock on the model — `CombatMath.turns_to_ko` is the shipped oracle but "
            "gates affordability on a raw energy COUNT while this family's reachability filter uses "
            "the Attach Budget, so routing to it as-is would give the family a second and weaker "
            "opinion about affordability than the one it already holds (the sole-supplier ruling "
            "forbids exactly that). The accessor is substrate, owned by T1's completeness contract "
            "(Issue #260); named here rather than derived inline, because `ceil(hp / damage)` "
            "written in this module WOULD be the second opinion.",
            "the SURVIVAL half of `opponent_target_value` — `survival_shift` is passed as 0 here, "
            "and **ADR-0119 decision 3 RETIRES that as a debt rather than discharging it**. It "
            "was recorded as owed to T1 (Issue #260), which would supply a removal-delta accessor on "
            "the model; building it would be a DEFECT. This module DIFFERENCES — its one live "
            "consumer is `planner.py`'s leaf evaluator, scoring an end-of-turn board — so removing "
            "their body already moves `survival`, which reads the same clock. Passing the delta here "
            "too would count one quantity twice. The live ranking at `pilot._opponent_target_rows` "
            "passes a REAL shift because it has no 'after' to difference against (its consumer "
            "prices HOLDING a gust card, for a play not made this turn); two idioms, one quantity, "
            "and the asymmetry is structural rather than transitional. So this 0 is not a gap: it is "
            "the correct reading for a differencing family, and a later change that 'fixes' it "
            "re-introduces the double-count.",
        ),
    ),
    TermFamily(
        name="readiness",
        reads=("body_payoff", "readiness_odds", "role_relevance"),
        does_not_read=("assignment_coverage", "bench_slot_price"),
        composition="Per-body payoff x readiness odds x role relevance, composed from the existing "
                    "Attach-Budget / readiness-odds / Needs machinery rather than a second opinion "
                    "about any of them. The payoff is `StateModel.attack_payoff` — the best attack the "
                    "body can pay off with ON THIS BOARD, not the printed `CardStat.maxDamage` "
                    "roll-up (ADR-0109). That makes `body_payoff` depend on MY Bench CONTENTS for a "
                    "bench-gated attack, which is not a second claim on `bench_slot_price`: "
                    "`development` prices how many slots are left, this prices what one attack can "
                    "land, and the two never read the same number. "
                    "**`readiness_odds` consults `turns_to_ko_me`, and that is not a disjointness "
                    "breach** — stated here because it is the first thing a reader of the tuples "
                    "will suspect, and because Issue #332 required the call to be argued rather "
                    "than assumed. The odds ask *does this body get to its payoff attack*, and a "
                    "body the opponent removes first does not get there; the clock is an INPUT to "
                    "that probability the way `turns_to_afford` already is, consulted on the "
                    "FORWARD leg alone (`_survives_to_spend`). `survival` prices a different "
                    "CONSEQUENCE of the same fact in a different currency — the `prize_at_risk` "
                    "handed over when the body falls, against the damage-denominated potential that "
                    "dies with it — so removing the body raises one family and lowers the other, "
                    "which is not one quantity added twice. Both families read the clock through "
                    "ONE call (`_survival_clock`), so they cannot come to disagree about it. The "
                    "registry fact stays `readiness_odds`, exactly as `survival` keeps "
                    "`predicted_loss` while consulting `prize_race`'s counts: splitting the clock "
                    "into a second fact string to make the read visible would make "
                    "`double_counted()` pass VACUOUSLY, which is the answer "
                    "`sound_rules.SCHEDULED_PAIRS` already records for the same temptation.",
        blind_to=(
            "the VALUE of the Active slot — narrowed by Issue #351, which took the legality half. "
            "`_may_attack_now` now gates the now-leg on the area and on `attack_blocked`, so a "
            "benched body no longer claims it can attack this turn; what stays unpriced is the "
            "slot's WORTH, so a retreat that puts the right body in front still moves this family "
            "only through the Attach Budget and the gate's on/off step. `promote_retreat_value` is "
            "the instrument and composes into `survival`; the retreat allowance itself is an OWED "
            "snapshot zone (T1).",
            "a board condition that is NOT a bench-partner condition — ADR-0109 routed the payoff "
            "through the damage oracle, which reads the one condition family the card-text parser "
            "extracts (`AttackStat.requiresBench`). Walking the whole set for *\"this attack does "
            "nothing\"* finds 24 attacks: 10 are coin flips (the `damageMin`/`damageMax` family, a "
            "different question), 2 are bench-partner gates and are now priced, and the remaining "
            "**12 are unread** — no Stadium in play (Fan Rotom 174), a Bench-count floor (Victini "
            "490), an exact hand size (Medicham 884), hand parity with the opponent (Iron Boulder "
            "971), a defender predicate (Sawk 602 vs {ex}, Camerupt 857 vs Burned, Basculin 577 vs "
            "an undamaged Active), their prize count (Hop's Cramorant 311), and a pay-from-hand "
            "discard (Decidueye 129, Lurantis 398, Ceruledge 797). Each still prices its PRINTED "
            "damage. **Exposure across the five shipped decks is 0** — the deck-csv walk finds only "
            "Solrock 676 — which is why Issue #278's *\"add only what the four decks need\"* leaves "
            "them here rather than in the build. This is the address, not a verdict: a deck change "
            "that adds one of the 12 makes it a live over-price, and the fix is another parser in "
            "`scouting/card_text.py` plus a context key, never a hand-enumerated condition "
            "vocabulary (ADR-0109's rejected option).",
            "Ability readiness — the incumbent leaf scored attack and Ability CO-EQUALLY "
            "(`planner._ability_readiness`, `_READINESS_ABILITY_VALUE`). Nothing in the model "
            "supplies an Ability payoff, so an evolve whose whole point is switching an engine "
            "Ability on prices only its attack payoff. The largest single regression risk in this "
            "swap, and named here so T4 reads it as a gap rather than a verdict.",
            "an Energy that EVAPORATES, on the now-leg of a body that CAN cash it — and this is now "
            "a VERDICT rather than a gap (Issue #351). `_readiness_odds` is `max(readiness_p, "
            "halve(turns_to_afford))`; the forward clock drops `discard_eot` Energy "
            "(`MySide.turns_to_afford(exclude_expiring=True)`) but `readiness_p` keeps it, and the "
            "two legs read the same attachment through the same matcher, so an Energy that FULLY "
            "arms the body zeroes the clock and pins the now-leg at 1.0 together. Issue #351 gated "
            "the now-leg on LEGALITY (`_may_attack_now` — the area plus `attack_blocked`) rather "
            "than stripping the Energy from it, and the measurement is why: over the committed "
            "corpus, 25 of 1018 of my bodies hold a `discard_eot` Energy and the clock moves on all "
            "25, but **21 of those are the Active on an unblocked turn**, where the body really can "
            "spend the Energy this turn and the 1.0 is TRUE. Masking the forward leg there is this "
            "family answering its own question correctly. What remains unpriced is only the "
            "residue: an Active that will attack with a DIFFERENT attack than its payoff, leaving "
            "the Ignition partly unspent. That is `attack_ev`'s at the terminal action (Issue #263) "
            "rather than a hole here, and it is bounded by the same 21 frames.",
            "what a DOOMED body could still do THIS turn OUTSIDE its payoff attack — the "
            "survivability discount (`_survives_to_spend`, Issue #332) zeroes the FORWARD leg on a "
            "body whose clock reads 1, which is exact for a payoff that lands on a later turn, and "
            "the now-leg is what keeps that body priced for a swing it can take right now. What "
            "nothing prices is the lesser swing: `attack_payoff` names ONE attack, so a doomed Mega "
            "Starmie ex whose Nebula Beam is unaffordable reads 0 forward while Jetting Blow is "
            "still on the menu in front of it. That swing is `attack_ev`'s at the terminal action "
            "rather than a hole in this family, and it is recorded because the zero is NEW — before "
            "Issue #332 the forward leg paid the doomed body anyway, so a reader diffing the two "
            "would otherwise read the drop as the body's whole value disappearing.",
        ),
    ),
    TermFamily(
        name="hand",
        reads=("assignment_coverage", "re_access", "hand_worth", "slot_demand"),
        does_not_read=("body_payoff", "deploy_marginal"),
        composition="Assignment coverage of LIVE slots plus re-access, on the `set_keep_v2` spine, "
                    "MINUS the demand those slots represent (Issue #400 Phase 2). Its "
                    "Worth-denominated part is the one place POC_WORTH_PRIZE_RATE crosses. A "
                    "card's value once PLAYED belongs to `readiness` or `development`; this family "
                    "prices it only while it is still in hand — but it also prices the NEED that "
                    "playing it retires, which is what makes a play a gain rather than a loss.",
        blind_to=(
            "hand SIZE as such — a bigger hand is more options, but the assignment prices coverage "
            "of live slots and a card covering nothing contributes only its latent worth. A draw "
            "that whiffs therefore prices near 0, which is correct, and a draw that hits prices "
            "through the slots it fills, which is also correct — recorded so the near-zero is read "
            "as measured rather than missing.",
            "information already revealed — see the module header: two orderings that reveal then "
            "commit, or commit then reveal, reach the SAME end state, so no end-state function can "
            "separate them. Structural, whitelisted (`information-before-commitment`), not a gap.",
            "MY HAND on a simulated end board — the whole family prices 0 there, so on the develop "
            "rollout's leaf a card leaving my hand currently costs nothing. Not an equation gap: "
            "the engine's end observation is OPPONENT-perspective, so my hand is hidden, and the "
            "`leaf_hand_value` capture that works around it is one action stale in a per-branch way "
            "(`planner._simulate_line` carries the measurement — arming it scored a branch that SPENT "
            "a card ABOVE one that spent nothing). A snapshot at the true end of my turn is the fix "
            "and it needs substrate the sim does not have. The family is fully live wherever a REAL "
            "board is scored, which is every call Issue #263's 1-ply ordering makes. **MEASURED, no "
            "longer merely predicted** (2026-08-02, Issue #262): across all 22 gating "
            "Discrimination-Gate frames the T3 layer owns, this family read exactly 0.0000 on BOTH "
            "sides of every comparison — inert, 22 for 22. The consequence is the one the entry "
            "warned of, and it decides ten of those frames on its own: `development` credits the "
            "body a card play lands while NOTHING on the leaf path charges for the card leaving my "
            "hand, so spending is free. `_line_account`'s spend charge is the only counterweight, "
            "and on those ten frames it fires on FOUR and is out-scaled about 3:1 where it does "
            "(-0.06 prizes against a +0.20 deploy credit) — on the other six nothing charges for "
            "the card at all. That is why the leaf prefers Ultra Ball / Buddy-Buddy Poffin / "
            "Lillie's over the developer's *\"just save it for next turn\"* on every one of them.",
            "DECK THINNING as a reason to spend a card. The assignment prices what a card COVERS, so "
            "a card whose slot is already satisfied prices at its latent worth and playing it reads "
            "as a small loss. The wave-3 ruling on `83457493|1|decision|33` says otherwise on a real "
            "board: with all three Staryu/Starmie already out, Buddy-Buddy Poffin covers nothing AND "
            "is worth playing anyway, because removing a dead card raises the quality of every "
            "subsequent draw. That is a property of the DECK's composition, which no term reads — "
            "`readiness` and `development` price bodies, and this family prices the hand. Named "
            "rather than left as a silent zero, because at ordering time a 0 delta is never explored "
            "(Issue #263's blind-spot contract).",
        ),
    ),
    TermFamily(
        name="development",
        reads=("deploy_marginal", "evolve_marginal", "bench_slot_price", "line_topology"),
        does_not_read=("role_relevance", "prize_at_risk"),
        composition="Bench and line topology through the deploy (ADR-0086) and evolve (ADR-0070) "
                    "marginals, PLUS an escalating Bench-slot price: a slot's marginal cost rises as "
                    "open slots deplete, so the last slot is not spent on a non-critical support "
                    "body a second wincon should have had. That escalation replaces the flat +60 "
                    "`keep-a-bench` cliff (a spare body priced 1.96 on a non-empty Bench against "
                    "61.96 on an empty one — the entire gap was the rung). Issue #232.",
        blind_to=(
            "the STADIUM — `model.stadium` has a supplier and no reader, so playing or replacing "
            "one prices exactly 0. T4 lists stadium among the families it takes over, and this is "
            "the term that would have to grow the read.",
            "their board topology — development is MY-side only. Their bench filling up, or their "
            "line completing, moves nothing here; `threat` reads their bodies as targets, not as "
            "development. An accepted POC asymmetry (there is no opponent model).",
        ),
    ),
)

#: **The terminal registry** — terms taken at a sequence's TERMINAL ACTION, never on a board, so
#: `score = state_value(end board) + EV(terminal)`. :func:`double_counted` walks BOTH registries.
TERMINAL_REGISTRY: tuple[TermFamily, ...] = (
    TermFamily(
        name="attack_ev",
        reads=("attack_damage", "attack_riders", "attack_economy", "next_turn_lock"),
        does_not_read=("opponent_target_value", "readiness_odds"),
        composition="EV of the attack that ENDS the turn (Issue #263 § Terminal-action valuation; "
                    "old Issue #145 amendment B made concrete). Composed from the shipped oracles, "
                    "never new math: the KO band / `predicted_damage` with coin branches entering "
                    "as an EXPECTATION rather than a printed floor, the target's prize value, "
                    "snipe/spread RIDER value priced against THEIR board, Effect-Clause economy "
                    "riders (energy recycle), and the next-turn clock cost an attacker-side lock "
                    "imposes on ME — BOTH fields, `nextTurnSelfLock` ('can't use attacks') and "
                    "`nextTurnSameAttackLock` ('can't use THIS attack'), which price differently "
                    "and which this line conflated until Issue #384. Readiness is deliberately "
                    "absent: whether I CAN "
                    "attack is `readiness`'s question about the board, and asking it twice would "
                    "multiply the same probability into the same prize.",
        blind_to=(
            "the opponent's REPLY — this is a 1-ply expectation, so an attack that wins the "
            "exchange and an attack that wins the exchange and survives the answer score the same "
            "except through the end board's own `survival`. Depth-2 is out of the POC (Issue #150).",
            "opponent-choice riders — 'your opponent discards a card' and its relatives have no "
            "opponent model, so their value is 0. The apply-seam REFUSES the same class; the two "
            "refusals are the same gap seen from two sides.",
            "opponent ACTION-ECONOMY locks — a rider that restricts what the opponent may DO on "
            "their next turn (an Item lock, an Evolution lock, a named-attack lock) is not a body "
            "grant, so `transient_grants` (ADR-0033, homed `mine.active.grant` only) does not carry "
            "it even in principle: its vocabulary is `self_lock`/`same_lock`/`self_bonus`/"
            "`prevent_all`/`reduction` (`state_model.py`'s `grant` docstring), none of which is "
            "'opponent can't play card-type X'. Budew's Itchy Pollen (235, `item_lock`, free "
            "attack, verified at source) is the concrete case — 1 card in 1 deck, but the reason "
            "`dragapult_ex` sets `preferred_start=\"second\"` (`docs/rules.md` §2: the first player "
            "cannot attack turn 1) — a 1-of that moved a deck-level parameter. Pricing it needs a "
            "THEIR-side extension of `transient_grants`, the same OWED-zone class Issue #282 needs "
            "for damage-boost Trainers; declaring it here is free and honest now (Issue #290).",
            # ── added with the extractor (POC-T4/3, Issue #384) ──────────────────────────────
            "a COIN's actual distribution — `attack_ev_legs` averages a conditional record's floor "
            "and ceiling and, where only that mean crosses the target's HP, credits the Knock Out at "
            "a DECLARED equiprobable 0.5 (`_COIN_KO_BOUND`). A policy, not a derivation: "
            "`AttackStat` carries `damageMin`/`damageMax` and NOTHING about what lies between them, "
            "in neither the parsed record nor the 99-attack engine-audit override table. MEASURED "
            "over a stated population — one row per (card, attack) in `data/EN_Card_Data.csv` with a "
            "`Move Name` that is not an `[Ability]`, put through `provider.build_attack_stats`, "
            "which is 1787 rows (the population is spelled out because a reviewer could not "
            "reproduce the figure from the bare number, and a count nobody can re-run is not "
            "evidence): 138 carry bounds, 148 print a coin in their `Effect Explanation`, only 38 "
            "are in both — so 110 coin attacks carry no bounds at all, and Team Rocket's Kangaskhan "
            "ex's Comet Punch ('Flip 4 coins. This attack does 30 damage for each heads') is "
            "unrepresentable in two numbers however they are read. Right for the pool's commonest "
            "shape (one fair coin, 'if heads, N more damage'), wrong in BOTH directions for a "
            "multi-flip one. Closing it needs a parsed flip count, which is a card-data change and "
            "not this term's.",
            "a CEILING-ONLY Knock Out — a consequence of the entry above, stated separately because "
            "it is the one that costs prizes. `attack_ev` consults `ko_probability` on its Knock Out "
            "branch alone, so an attack whose AVERAGED damage falls short of the target's HP while "
            "its ceiling clears it takes the CHIP branch and the Knock Out is never credited at all. "
            "An UNDER-read, the fail-closed direction for an offensive estimate and the same choice "
            "`threat.blind_to` makes one seam over — but it does mean a coin attack that COULD win "
            "the exchange can rank below one that certainly chips. The MIRROR of it is an OVER-read "
            "and is recorded here rather than left as the flattering half: on the Knock Out branch "
            "`attack_ev` sets `chip = 0.0` by construction, so at `ko_probability = 0.5` the losing "
            "branch contributes NOTHING — a coin attack that misses the kill still lands its floor "
            "damage on the real board, and half a prize is credited where 'half a prize plus the "
            "tails-branch chip' is the honest expectation. Both halves are the frozen shape's, not "
            "the extractor's: `attack_ev`'s branch is corpus-ruled and this issue may not retune it.",
            "a rider carrying BOTH a snipe and a spread — `_attack_rider_value` sums the two "
            "knapsacks independently over the same Bench, so a body finishable by either would be "
            "paid for twice. MEASURED unreachable rather than argued safe: over the population "
            "above, 23 attacks print `benchSnipe` only and 3 print `benchSpread` only, and NOT ONE "
            "prints both — which is also why `threat.blind_to` can split the same pair without "
            "double-counting. Unguarded rather than impossible: a future set printing both would "
            "over-read, and the fix then is one shared allocation, not two sums.",
            "SELF-DAMAGE — `AttackStat.recoil` (ADR-0022 #2) reaches no leg of this term and no "
            "board either. Attack is TERMINAL, so there is no post-attack board for the apply-seam "
            "to hand back and nothing for `survival` to price the recoil on, and the term takes no "
            "kwarg for it. So a recoiling attack's cost to my own body prices at exactly 0. The "
            "Pilot's `_recoil_flips_doom` is a BOOLEAN doom read on the tactical scale rather than a "
            "prize-denominated cost, so there is nothing to compose — pricing it is new math at a "
            "seam this issue may not open, and the direction is an OVER-read of the attack.",
            "a SPREAD that chips several bodies without felling any — `_attack_rider_value` credits "
            "the best SINGLE body's band when the knapsack finishes nothing, because splitting a "
            "shared counter budget to maximise FRACTIONAL progress is an allocation nothing ships: "
            "`CombatMath.spread_ko_prizes` answers the kill question and there is no oracle for the "
            "chip one. Under-reads Phantom Dive's pre-loading turn — which `dragapult_ex`'s doctrine "
            "calls its win plan — in the fail-closed direction.",
        ),
    ),
)

#: Name -> family, for the `working` breakdown and for T3's dispatch.
FAMILIES: Mapping[str, TermFamily] = {f.name: f for f in REGISTRY}

#: Separate from :data:`FAMILIES`, so iterating one cannot pick up a term needing an action.
TERMINAL_FAMILIES: Mapping[str, TermFamily] = {f.name: f for f in TERMINAL_REGISTRY}


def state_value(model: "StateModel", *, working: dict | None = None) -> float:
    """The board's worth **in prizes**, higher better for ME; memoized per model. PROVENANCE-AGNOSTIC
    — never branch on how the model was made. ``working`` if passed is FILLED with the family breakdown."""
    terms = model._memoized(("state_value",), lambda: _terms(model))
    if working is not None:
        working.update(terms)
    return float(sum(terms.values()))


def _terms(model: "StateModel") -> dict:
    """The six families, evaluated once. **Insertion order is REGISTRY order and that is a contract**
    — float addition is not associative, so a reorder moves the sum's last bits (Issue #262)."""
    race = model.prize_race
    return {
        "prize_race": prize_race(my_prizes_remaining=race.my_prizes_remaining,
                                 their_prizes_remaining=race.opp_prizes_remaining),
        "survival": survival(_exposed_bodies(model), predicted_loss=_predicted_loss(model)),
        "threat": threat(_reachable_target_values(model),
                         opponent_hand_resource=model.theirs.hand_size),
        "readiness": readiness(_ready_bodies(model)),
        "hand": hand(**_hand_legs(model)),
        "development": development(**_development_legs(model)),
    }


# ── the extractors — StateModel -> the families' plain numbers ────────────────────────────────────
# One per family, so "which family reads `turns_to_ko_me`" has a code answer rather than a prose one.


def _exposed_bodies(model: "StateModel") -> tuple:
    """MY bodies as `survival` reads them — both areas, Bench-Harvest-aware. ``attacker="theirs"`` is
    the correctness: the Damage Formula names its variables per ATTACKER — here, them (Issue #280)."""
    return tuple(
        ExposedBody(prize_at_risk=float(b.prize_value), turns_to_ko_me=_survival_clock(model, b))
        for b in model.mine.bodies)


def _survival_clock(model: "StateModel", body) -> int:
    """**THE** clock on one of my bodies (Issue #332) — the ONE call `survival` and `readiness` both
    read. `int` turns, deliberately NOT ADR-0117's fractional `TheirSide.survival_clock`."""
    return int(model.theirs.turns_to_ko_me(
        body.body, my_benched=not body.is_active, my_bench=model.mine.bench_raws,
        opp_active=model.theirs.active_raw, context=model.damage_context(attacker="theirs")))


def _predicted_loss(model: "StateModel") -> bool:
    """Can the opponent WIN next turn? — both `docs/rules.md` §7 cases (bench-empty doom; the Knock
    Out takes their LAST prize). ADR-0064 + Amendment B; ``evo_min_energy=1`` is its pessimism guard."""
    mine, theirs = model.mine, model.theirs

    def _doomed(body) -> bool:
        return bool(body.hp_remaining) and theirs.reachable_incoming(
            body.body, evo_min_energy=1, my_benched=not body.is_active,
            context=model.damage_context(attacker="theirs")) >= body.hp_remaining

    # case 2 — the cheap bench-empty fact gates the expensive clock read.
    active = mine.active
    if active is not None and not mine.bench and _doomed(active):
        return True

    # case 1 — the cheap prize comparison gates the expensive clock read. An ABSENT prize zone reads
    # 0, which is falsy: a board making no claim predicts no loss.
    left = model.prize_race.opp_prizes_remaining
    return bool(left) and any(b.prize_value >= left and _doomed(b) for b in mine.bodies)


def _reachable_target_values(model: "StateModel") -> tuple:
    """Their bodies as `threat` reads them — `needs.opponent_target_value` over the Knock Outs I can
    reach THIS turn: their Active by the damage model, their Bench by the snipe RIDER alone."""
    mine = model.mine.active
    race = model.prize_race
    phase = _needs.phase_scale(race_ahead=None,
                               opp_prizes_remaining=race.opp_prizes_remaining)
    values = []
    for target in model.theirs.bodies:
        if not target.hp_remaining:
            continue
        reach = (model.mine.best_reachable_damage_vs(
                     mine, target, context=model.damage_context(attacker="mine"))
                 if target.is_active else
                 model.mine.best_reachable_bench_damage(mine, target))
        if reach < target.hp_remaining:
            continue
        # THE LINE'S PRIZE (ADR-0119 decision 2), the same reading `_opponent_target_rows` takes, so
        # this family and the live ranking cannot hold two opinions about what one line is worth.
        line_prize, line_hops = model.theirs.forward_line_prize(target.card_id)
        advance = _needs.line_prize_advance(own_prize=float(target.prize_value),
                                            max_line_prize=line_prize, hops=line_hops)
        values.append(_needs.opponent_target_value(prize_advance=advance,
                                                   survival_shift=0, phase=phase))
    return tuple(values)


def _forward_credit(forward, *, relevance: float = 1.0) -> float:
    """A line's UNPAID forward payoff, in prizes — `_READINESS_W` band, `halve(hops)` (ADR-0070 §6).
    The guard is DEFENSIVE, not load-bearing: `halve(0)` is 1.0, so a 0-hop read would go undiscounted."""
    if forward.hops <= 0 or forward.owed_damage <= 0.0:
        return 0.0
    return (_READINESS_W * (forward.owed_damage / currency.PRIZE_DAMAGE_RATE)
            * halve(forward.hops) * relevance)


def _ready_bodies(model: "StateModel") -> tuple:
    """MY bodies as `readiness` reads them: `attack_payoff` on THIS board, not the printed roll-up
    (ADR-0109), x odds asked about that SAME attack, x role relevance."""
    out = []
    seen: set = set()
    for b in model.mine.bodies:
        if b.stat is None:
            continue                       # unknown card: make no claim (the oracle's own direction)
        paying = model.mine.attack_payoff(b)
        payoff = paying.damage / currency.PRIZE_DAMAGE_RATE
        if payoff <= 0.0:
            continue                       # nothing this body can land: a condition it cannot meet
        out.append(ReadyBody(payoff=payoff,
                             readiness_odds=_readiness_odds(model, b, paying.attack_id),
                             role_relevance=_body_relevance(model, b.card_id, seen)))
    return tuple(out)


#: A repeated UTILITY body's discount — `planner._READINESS_SATURATED`, carried at the same value.
_SATURATED = 0.1


def _saturation(model: "StateModel", card_id, seen: set) -> float:
    """1.0 for a card's first in-play copy and for any attacker (at or above the `secondary_attacker`
    tier); :data:`_SATURATED` for a SECOND utility copy. **Mutates ``seen``**, the caller's set."""
    if card_id is None:
        return 1.0
    if model.mine.role_worth(card_id) >= ROLE_TIER["secondary_attacker"]:
        return 1.0
    if card_id in seen:
        return _SATURATED
    seen.add(card_id)
    return 1.0


def _readiness_odds(model: "StateModel", body, attack_id) -> float:
    """P(this body gets to its payoff attack) — `readiness_p` for THIS turn or `halve(turns_to_afford)`
    forward, whichever is better. MAX not sum, so it stays a probability and stays monotone."""
    now = model.mine.readiness_p(body, attack_id) if _may_attack_now(model, body) else 0.0
    arm = model.mine.turns_to_afford(body, exclude_expiring=True)
    forward = 0.0 if arm is None else halve(arm) * _survives_to_spend(model, body)
    return max(0.0, min(1.0, max(now, forward)))


def _may_attack_now(model: "StateModel", body) -> bool:
    """May ``body`` attack THIS turn — the legality leg `readiness_p` lacks (Issue #351). Kept out of
    that shared oracle, whose area-blindness `promote_retreat_value` needs. Fails CLOSED on no turn."""
    return body.is_active and not model.mine.attack_blocked


def _survives_to_spend(model: "StateModel", body) -> float:
    """How much of this body's FUTURE I still own, in [0, 1] — ``1 - halve(turns_to_ko_me - 1)``, the
    exact complement of `survival`'s grade on the same clock (Issue #332). A clock of 1 grades 0.0."""
    return 1.0 - halve(_survival_clock(model, body) - 1)


#: The floor under an UNDECLARED body's role relevance — DERIVED as the bottom shipped role rung over
#: `DEPLOY_WORTH_SCALE`. At exactly 0 every play onto such a body would price at 0 delta.
_ROLE_FLOOR = ROLE_TIER["tutor"] / currency.DEPLOY_WORTH_SCALE


def _body_relevance(model: "StateModel", card_id, seen: set) -> float:
    """:func:`_role_relevance` x :func:`_saturation`, in ONE place. Each caller keeps its OWN ``seen``
    set — the families are independent readings — but the expression must not be duplicated."""
    return _role_relevance(model, card_id) * _saturation(model, card_id, seen)


def _role_relevance(model: "StateModel", card_id) -> float:
    """A card's role weight as a dimensionless [0, 1] ratio — `deploy_value._relevance`'s form, off
    `MySide.role_worth`. Roles are DECLARED, not card data, so there is no `CardStat` field to read."""
    if currency.DEPLOY_WORTH_SCALE <= 0:
        return 0.0
    worth = model.mine.role_worth(card_id)
    return max(_ROLE_FLOOR, min(1.0, worth / currency.DEPLOY_WORTH_SCALE))


def _hand_legs(model: "StateModel") -> dict:
    """My hand as `hand` reads it, on the `set_keep_v2` spine. **Fuel slots are excluded from
    ``slot_demand`` because `needs._keep_slot_dp` excludes them from supply** — one rule, both sides."""
    resolution = model.mine.needs
    if resolution is None:
        return {"assignment_coverage": 0.0, "re_access": 0.0, "hand_worth": 0.0, "slot_demand": 0.0}
    re_access, coverage = resolution.split()
    return {"assignment_coverage": float(coverage), "re_access": float(re_access),
            "hand_worth": float(resolution.latent_worth),
            "slot_demand": float(sum(float(s.value) for s in resolution.slots
                                     if not getattr(s, "supplied_by_pitch", False)))}


def _development_legs(model: "StateModel") -> dict:
    """My board's topology as `development` reads it, every leg already in PRIZES. ``line_topology``
    CANCELS the evolve credit of an unreachable forward form rather than shrinking it."""
    mine = model.mine
    deploy = evolve = topology = 0.0
    seen: set = set()
    for b in mine.bodies:
        if b.card_id is None:
            continue
        relevance = _body_relevance(model, b.card_id, seen)
        deploy += currency.deploy_relevance_to_damage(relevance) / currency.PRIZE_DAMAGE_RATE
        forward = mine.forward_payoff(b.card_id)
        credit = _forward_credit(forward, relevance=relevance)
        if credit:
            evolve += credit
            if not forward.reachable:
                topology -= credit
    return {"deploy_marginal": deploy, "evolve_marginal": evolve, "line_topology": topology,
            "bench_slot_price": _bench_slot_price(len(mine.bench))}


def _bench_slot_price(occupied: int) -> float:
    """The escalating price of ``occupied`` Bench slots, in prizes: slot *i* costs
    `_BENCH_SLOT_PRICE x halve(_BENCH_MAX - i)`. CUMULATIVE — differencing recovers the marginal."""
    total = 0.0
    for i in range(1, min(int(occupied), _BENCH_MAX) + 1):
        total += _BENCH_SLOT_PRICE * halve(_BENCH_MAX - i)
    return total


# ── the term families — pure functions over RESOLVED plain numbers ────────────────────────────────
# Plain numbers, not the model, so each equation tests with no engine and no board construction.


def prize_race(*, my_prizes_remaining: int, their_prizes_remaining: int) -> float:
    """Lead plus proximity over the two prize COUNTS, in prizes. **The lead leg has UNIT SLOPE** —
    that is what makes the scalar prize-denominated; proximity is a `halve` difference and cannot invert it."""
    mine, theirs = int(my_prizes_remaining), int(their_prizes_remaining)
    lead = float(theirs - mine)
    proximity = halve(mine - 1) - halve(theirs - 1)
    return lead + _PROXIMITY_W * proximity


def survival(bodies: Iterable[ExposedBody], *, predicted_loss: bool = False) -> float:
    """My bodies' exposure, in prizes — **negative**, UNCAPPED (it forecasts real prize flow), and
    RANK-GRADED because they attack ONCE a turn (`docs/rules.md` §3): ungraded it reached -4.5."""
    graded = sorted((float(b.prize_at_risk) * halve(int(b.turns_to_ko_me) - 1) for b in bodies),
                    reverse=True)
    exposure = sum(g * halve(rank) for rank, g in enumerate(graded))
    return -(exposure + (LOSS_PRIZES if predicted_loss else 0.0))


def threat(targets: Iterable[float], *, opponent_hand_resource: float = 0.0) -> float:
    """Their bodies' exposure to ME, in prizes — positive and POSITIONAL, so :data:`_THREAT_W`-scaled
    THEN capped. Converting any of it is `attack_ev`'s; the guard bites on ~7% of non-empty inputs."""
    resource = _OPPONENT_HAND_RESOURCE_W * float(opponent_hand_resource)
    return max(-_THREAT_CAP, min(_THREAT_CAP,
                                 _THREAT_W * float(sum(float(t) for t in targets)) - resource))


def readiness(bodies: Iterable[ReadyBody]) -> float:
    """How close my board is to DOING something, in prizes. MULTIPLICATIVE — a huge payoff at zero
    odds is zero — then per-body and total runaway guards. Positional: the swing is `attack_ev`'s."""
    total = 0.0
    for body in bodies:
        contribution = (_READINESS_W * float(body.payoff)
                        * min(1.0, max(0.0, float(body.readiness_odds)))
                        * min(1.0, max(0.0, float(body.role_relevance))))
        total += min(_READINESS_BODY_CAP, contribution)
    return min(_READINESS_CAP, total)


def hand(*, assignment_coverage: float, re_access: float, hand_worth: float,
         slot_demand: float = 0.0, worth_prize_rate: float | None = None) -> float:
    """What is still IN HAND against what the position still NEEDS, in prizes. ⚠️ ``slot_demand`` is
    the DEMAND half of one ledger (ADR-0127): without it every card play priced as a loss. SIGNED."""
    rate = POC_WORTH_PRIZE_RATE if worth_prize_rate is None else worth_prize_rate
    if not rate:
        return 0.0
    worth = (float(assignment_coverage) + float(re_access) + float(hand_worth)
             - float(slot_demand))
    # Capped from ABOVE only: a `max(0.0, …)` floor would make an unmet need free again.
    return min(_HAND_CAP, worth * float(rate))


def development(*, deploy_marginal: float, evolve_marginal: float, bench_slot_price: float,
                line_topology: float) -> float:
    """Board topology — bench and evolution lines, in prizes. ``bench_slot_price`` is a COST that
    escalates as slots deplete; the cap is on the SIGNED total, so an over-spent Bench scores negative."""
    return min(_DEVELOPMENT_CAP,
               float(deploy_marginal) + float(evolve_marginal) + float(line_topology)
               - float(bench_slot_price))


# ── the terminal-action term ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AttackEV:
    """:func:`attack_ev`'s answer, with its sub-values named. Mirrors `DeployValue.working()`."""

    #: The prize value of the Knock Out, weighted by P(the damage lands it).
    knockout: float = 0.0
    #: Damage that does NOT knock out, carried at the currency rate — chip is progress, not nothing.
    chip: float = 0.0
    #: Snipe / spread rider value against THEIR board.
    riders: float = 0.0
    #: Effect-Clause economy riders (energy recycling and its relatives).
    economy: float = 0.0
    #: What an attacker-side next-turn lock costs ME next turn; `nextTurnSelfLock` and
    #: `nextTurnSameAttackLock` price differently. A COST — already subtracted.
    next_turn_cost: float = 0.0
    #: The sum. In prizes.
    total: float = 0.0

    def working(self) -> dict:
        return {"knockout": self.knockout, "chip": self.chip, "riders": self.riders,
                "economy": self.economy, "next_turn_cost": self.next_turn_cost}


def attack_ev(*, damage: float, target_hp: float, target_prizes: float,
              ko_probability: float = 1.0, rider_value: float = 0.0,
              economy_value: float = 0.0, next_turn_cost: float = 0.0) -> AttackEV:
    """**EV of the attack that ENDS the turn**, in prizes: `score = state_value(end board) + this`.
    An EXPECTATION (`ko_probability`); chip is credited below the KO band; ``next_turn_cost`` SUBTRACTS."""
    dmg, hp = max(0.0, float(damage)), max(0.0, float(target_hp))
    prizes, p_ko = max(0.0, float(target_prizes)), min(1.0, max(0.0, float(ko_probability)))
    if hp and dmg >= hp:
        knockout, chip = prizes * p_ko, 0.0
    elif hp:
        knockout = 0.0
        chip = prizes * (dmg / hp)
    else:                                   # unreadable HP: fall back to the median crossing
        knockout = 0.0
        chip = min(prizes, dmg / currency.PRIZE_DAMAGE_RATE)
    total = knockout + chip + float(rider_value) + float(economy_value) - float(next_turn_cost)
    return AttackEV(knockout=knockout, chip=chip, riders=float(rider_value),
                    economy=float(economy_value), next_turn_cost=float(next_turn_cost),
                    total=total)


# ── the terminal-action term's EXTRACTOR (POC-T4/3, Issue #384) ───────────────────────────────────
# The model->term bridge. The SUM belongs to `common/composer.py` and to nothing else.


class AttackLegs(NamedTuple):
    """One affordable attack, and the kwargs `attack_ev` takes for it. The kwargs travel as a dict so
    the bridge is a SPLAT and a new term kwarg is a `TypeError`, never a silent default."""

    attack_id: int | None
    #: Exactly :func:`attack_ev`'s parameters. Splat it.
    kwargs: dict


#: **DECLARED, not derived**: `AttackStat` carries ``damageMin``/``damageMax`` and nothing about the
#: distribution between them, so a mean-crossing Knock Out is credited equiprobably (Issue #384).
_COIN_KO_BOUND = 0.5


def attack_ev_legs(model: "StateModel") -> tuple:
    """:func:`attack_ev`'s kwargs for every attack my Active can pay for — the model->term bridge
    (Issue #384). ⚠️ `AttackEV.working()` is FROZEN ASYMMETRIC: read ``.total``, never the dict sum."""
    body = model.mine.active
    if body is None or model.mine.attack_blocked:
        return ()
    stat = body.stat
    profiles = [p for p in (model.attack_profile(body, aid)
                            for aid in (getattr(stat, "attacks", None) or ()))
                if p.affordable]
    if not profiles:
        return ()
    defender = model.theirs.active
    hp = float(defender.hp_remaining) if defender is not None else 0.0
    prizes = float(defender.prize_value) if defender is not None else 0.0
    # MATCHUP-FREE: the lock leg asks what this body could do NEXT turn, so it reads `printed`.
    followups = {p.attack_id: p.printed for p in profiles if p.attack_id is not None}
    costless = _lock_is_costless(model, body, followups)
    return tuple(AttackLegs(p.attack_id, {
        "damage": _attack_damage(p),
        "target_hp": hp,
        "target_prizes": prizes,
        "ko_probability": _attack_ko_probability(p, hp),
        "rider_value": _attack_rider_value(p),
        "economy_value": _attack_economy_value(p),
        "next_turn_cost": 0.0 if costless else _attack_next_turn_cost(p, followups),
    }) for p in profiles)


def _attack_damage(profile) -> float:
    """The damage MODEL's answer, a conditional attack's branches already averaged (ADR-0039's ranking
    convention). The ``damage > 0`` guard keeps a BOARD gate (`requiresBench`) out of the coin family."""
    if profile.conditional and profile.damage > 0:
        return (float(profile.damage_floor) + float(profile.damage_ceiling)) / 2.0
    return float(profile.damage)


def _attack_ko_probability(profile, target_hp: float) -> float:
    """1.0 when deterministic, and 1.0 when a conditional attack's FLOOR already kills; else
    :data:`_COIN_KO_BOUND`. A ceiling-only kill takes `attack_ev`'s CHIP branch — an under-read."""
    if not (profile.conditional and target_hp):
        return 1.0
    return 1.0 if float(profile.damage_floor) >= target_hp else _COIN_KO_BOUND


def _attack_rider_value(profile) -> float:
    """Snipe and spread riders against THEIR Bench, in prizes: the knapsack's prize total when it
    finishes something, else the best single body's chip band. UNDER-reads a fell-nothing spread."""
    value = 0.0
    for reach, ko_prizes in ((profile.bench_snipe, profile.snipe_ko_prizes),
                             (profile.bench_spread, profile.spread_ko_prizes)):
        if not reach:
            continue
        value += (float(ko_prizes) if ko_prizes
                  else max((prize * min(1.0, reach / hp)
                            for hp, prize in profile.rider_targets if hp), default=0.0))
    return value


def _attack_economy_value(profile) -> float:
    """The energy-recycle rider, in prizes — a scale crossing only (``ENERGY_RECOVER`` is
    damage-per-Energy, ``PRIZE_DAMAGE_RATE`` damage-per-prize). Both consumed, neither re-derived."""
    return float(profile.recover_units) * ENERGY_RECOVER / currency.PRIZE_DAMAGE_RATE


def _lock_is_costless(model: "StateModel", body, followups: dict) -> bool:
    """Does a next-turn lock cost NOTHING here? — a LONE affordable attack has no lock-free
    alternative to lose against, and a doomed Active (clock 1) has no next turn to be locked out of."""
    return len(followups) <= 1 or _survival_clock(model, body) <= 1


def _attack_next_turn_cost(profile, followups: dict) -> float:
    """What an attacker-side lock costs ME next turn, in prizes — ADR-0061's `followup_damage` gap
    against the best lock-free pick, at ``FOLLOWUP_W``. Floored at 0: this leg can only subtract."""
    if not (profile.self_lock or profile.same_attack_lock):
        return 0.0
    left = followup_damage(profile.attack_id, affordable=followups,
                           full_lock=profile.self_lock,
                           same_attack_lock=profile.same_attack_lock)
    forfeited = max(0.0, max(followups.values(), default=0.0) - float(left))
    return FOLLOWUP_W * forfeited / currency.PRIZE_DAMAGE_RATE


# ── the coverage map, executable ──────────────────────────────────────────────────────────────────


def _all_families() -> tuple:
    """Both registries — the one-fact-one-family rule spans the state/terminal seam."""
    return REGISTRY + TERMINAL_REGISTRY


def blind_spots() -> dict:
    """``{family: (dimension — why it is uncovered, …)}``. Under 1-ply differencing a play moving only
    a blind dimension prices 0 delta, and 0 means never EXPLORED. No production caller reads it."""
    return {f.name: f.blind_to for f in _all_families() if f.blind_to}


def registry_gaps() -> list[str]:
    """Facts some family disclaims and NO family reads — the coverage holes. Empty is the contract.
    SELF-REFERENTIAL: a board signal nobody wrote into a ``does_not_read`` stays invisible to it."""
    read = {fact for f in _all_families() for fact in f.reads}
    return sorted({fact for f in _all_families() for fact in f.does_not_read} - read)


def double_counted() -> list[str]:
    """Facts claimed by MORE than one family. Empty is the contract (ADR-0092 §4-T0)."""
    seen: dict[str, int] = {}
    for f in _all_families():
        for fact in f.reads:
            seen[fact] = seen.get(fact, 0) + 1
    return sorted(k for k, n in seen.items() if n > 1)


__all__: Sequence[str] = (
    "POC_WORTH_PRIZE_RATE", "LOSS_PRIZES", "WIN_PRIZES",
    "REGISTRY", "FAMILIES", "TERMINAL_REGISTRY", "TERMINAL_FAMILIES",
    "TermFamily", "ExposedBody", "ReadyBody", "AttackEV",
    "state_value", "prize_race", "survival", "threat", "readiness", "hand", "development",
    "attack_ev", "registry_gaps", "double_counted", "blind_spots",
)
