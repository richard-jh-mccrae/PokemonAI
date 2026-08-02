"""**The sound-rule whitelist**, as data (POC-T0 / Issue #259, ADR-0099; ratified wave 1).

The rules that SURVIVE the POC's purge because they encode game structure or fail-direction policy
rather than a strategy hypothesis. Every other tuned weight is deleted by its owning track.

## Why this is data and not only prose

ADR-0092 §6 drafted the whitelist as a flat prose list, and the flat shape failed its first real
test. ONE board fact — an empty Bench under a knock-outable Active — reached that list through
**three** mechanisms simultaneously:

    _predicted_loss         -KO_SCORE terminal rung, CombatMath-gated   (planner.py)
    _empty_bench_forced     order filter, unconditional                 (pilot.py)
    keep-a-bench            +60 tuned weight, unscoped when()           (baseline_bench.py)

in direct violation of T0's own headline rule ("every board fact enters through exactly ONE term
family"), and nothing about writing the line prompted the question. Six parallel tracks will each
delete rungs against this list, so the discipline has to be enforced rather than remembered.

The third mechanism is now GONE — `keep-a-bench` was deleted by T2 (Issue #261 item 2d) on ADR-0096
decision 2, and `baseline_bench.py` with it, since that rung was the whole module. Two remain, by
schedule rather than by exception: `empty-bench-filter` is typed `provisional` with a dated
retirement test, after which `predicted-loss` is the sole guard.

## The four types, and what each MUST carry

* ``structural``        — permanent. Encodes a game rule or a fail-direction policy. Must name it.
* ``provisional``       — a substrate-gap workaround, not a permanent truth. **Must carry a dated
  retirement test.** Without one a workaround becomes permanent through inattention, which is the
  whole failure mode the type exists to name.
* ``authored-scaffold`` — a constant, not a rule. **Must carry a reconciliation note** stating what
  it is checked against, and a fitting-queue entry.
* ``composed-into-the-leaf`` — a per-seam equation that stops being a DECIDER when the composer
  lands, but survives as `state_value` term-family internals. **Must name the term family that
  absorbs it** (``composed_into``). Added 2026-08-01 by the Issue #263 ordering ruling.

`validate()` rejects an entry missing its mandatory field, and every entry names the board fact it
guards — which is what makes the double-counting rule checkable against the whitelist itself and not
only against `state_value`'s term families.

## Two populations: what DECIDES, and what is MATH

The first three types are entries that still decide something at runtime. ``composed-into-the-leaf``
is not: those equations lose decider status to the composer's uniform 1-ply differencing, and are
neither deleted nor whitelisted-as-rules. They are on this list precisely so that "no longer a
decider" is not read as "delete it" — Issue #262 composes readiness and development out of their
math, and Issue #264's disposition table uses this same label, so the string has to match exactly.

`undeclared_double_guarding()` runs over the DECIDERS only. A decider guarding a fact and an
equation pricing it are different roles, so pairing them would be a false positive — and a detector
that cries wolf is one nobody reads.

The human-readable rendering is `docs/plans/value-system-poc-plan.md` §6. It carries the same ``id``
column, and `test_sound_rules.py` cross-checks the two so the doc and the data cannot drift.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

#: Permanent — encodes a game rule or a fail-direction policy.
STRUCTURAL = "structural"
#: A substrate-gap workaround. Carries a dated retirement test.
PROVISIONAL = "provisional"
#: A constant, not a rule. Carries a reconciliation note and a fitting-queue entry.
AUTHORED_SCAFFOLD = "authored-scaffold"
#: A per-seam equation that stops DECIDING when the composer lands but survives as `state_value`
#: term-family internals. Carries the term family that absorbs it. The exact string is shared with
#: Issue #264's disposition table — do not reword it.
COMPOSED_INTO_THE_LEAF = "composed-into-the-leaf"

TYPES = frozenset({STRUCTURAL, PROVISIONAL, AUTHORED_SCAFFOLD, COMPOSED_INTO_THE_LEAF})

#: The types whose entries still DECIDE something at runtime — the population the one-guard-per-fact
#: rule is about. :data:`COMPOSED_INTO_THE_LEAF` is deliberately absent: it is math, not a guard.
DECIDER_TYPES = frozenset({STRUCTURAL, PROVISIONAL, AUTHORED_SCAFFOLD})


@dataclass(frozen=True)
class SoundRule:
    """One whitelist entry. ``id`` is the stable slug a commit message or a track issue cites."""

    id: str
    #: What survives — the rule, filter, rung or constant, named as it appears in the source.
    entry: str
    #: One of :data:`TYPES`.
    type: str
    #: The board fact this guards, or the policy it encodes. Never blank — an entry that cannot say
    #: what it guards cannot be checked against the double-counting rule.
    fact: str
    #: Why it survives the purge. For ``structural``, the rule or policy it encodes.
    reason: str
    #: ``provisional`` ONLY: the measurement that retires it, and who owns it.
    retirement_test: str = ""
    #: ``authored-scaffold`` ONLY: what the number is reconciled against, and when it gets fitted.
    reconciliation: str = ""
    #: ``composed-into-the-leaf`` ONLY: the `state_value` term family that absorbs this equation's
    #: math once it stops deciding. Mandatory, because "survives as an internal" with no named
    #: destination is indistinguishable from "kept out of sentiment", and the next track deletes it.
    composed_into: str = ""


#: The ratified whitelist (wave 1, 2026-08-01). Amended from ADR-0092 §6's draft by this grill:
#: `keep-a-bench` DELETED, the empty-Bench filter re-typed provisional, Set-Up split onto its own
#: line, `_finish_turn_last` narrowed to the named boundary, `POC_WORTH_PRIZE_RATE` bound, the
#: apply-seam coverage floors added. Amended again the same day by the Issue #263 ordering ruling:
#: the four per-seam equations added as ``composed-into-the-leaf``.
WHITELIST: tuple[SoundRule, ...] = (
    SoundRule(
        id="ko-score-band",
        entry="`KO_SCORE` structural band + `_LINE_CAP` invariant",
        type=STRUCTURAL,
        fact="a prize is worth more than any positional term",
        reason="The positional caps SUM to 590 (readiness 300 + survival 50 + threat 100 + value 40 "
               "+ line 100) against KO_SCORE 1000, deliberately, so no positional term can outrank a "
               "real prize. `_LINE_CAP` is the line term's 100 (`strategy/planner.py`), one summand "
               "of that band rather than the band itself. The invariant is what makes "
               "'un-outbiddable' expressible at all. "
               "**OWED A RULING (POC-T3, Issue #262).** `state_value` does NOT reproduce that "
               "arithmetic: `survival` is prize-denominated and uncapped (a 3-prize body they can "
               "Knock Out costs three times a 1-prize one, and a cap under a prize would erase the "
               "distinction and price a heal at ~0), and `hand`/`development` carry runaway guards "
               "at 1.5 prizes each rather than the incumbent 0.04/0.1 (transcribed, they saturate, "
               "and a saturated term has zero derivative — so under 1-ply differencing every play "
               "touching it prices at 0 delta and is never explored). What T3 preserves is the rule "
               "restated on DELTAS: an absolute positional level cancels in "
               "`state_value(after) - state_value(before)`, so what could outbid a prize is a single "
               "play's MOVE, and the per-body bounds hold that under 1.0. That restatement is a "
               "change to a ratified structural entry and is filed in the wave-3 packet; it is "
               "recorded here rather than left as a docstring claim, because a whitelist that "
               "describes a band the code abandoned is worse than one that says so.",
    ),
    SoundRule(
        id="setup-never-bench",
        entry="Set-Up never-bench (ADR-0086 decision 9)",
        type=STRUCTURAL,
        fact="pregame Bench placement",
        reason="Deferring to my own first turn is WEAKLY DOMINANT, from three source-checked facts: "
               "the placement is optional ('up to 5', rulebook L97); no attack reaches me first in "
               "either seat (docs/rules.md §2); and of the 21 damage-counter Abilities in the card "
               "data, ZERO sit on a Basic, so no Ability damage reaches me either. Deferring also "
               "BUYS the bench-drop Abilities, which are unsatisfiable before the game starts.",
    ),
    SoundRule(
        id="empty-bench-filter",
        entry="empty-Bench forced deploy filter (`_empty_bench_forced`)",
        type=PROVISIONAL,
        fact="empty Bench under a knock-outable Active",
        reason="Guards a LOSS condition (docs/rules.md §7 case 2: an Active Knocked Out with nothing "
               "to promote ends the match). Unconditional for now because the read that would "
               "replace it depends on the CombatMath/StateModel completeness T1 is delivering — the "
               "very gap that caused this POC replan.",
        retirement_test="After T1 (Issue #260): measure `reachable_incoming`'s answer rate over "
                        "every post-setup empty-Bench corpus frame. Retire IFF the read answers on "
                        "all of them AND both gates stay green with the filter removed — at which "
                        "point `_predicted_loss` is the sole guard on this fact.",
    ),
    SoundRule(
        id="predicted-loss",
        entry="`_predicted_loss` (−KO_SCORE bench-empty doom, ADR-0064)",
        type=STRUCTURAL,
        fact="empty Bench under a knock-outable Active",
        reason="The SAME fact as `empty-bench-filter`, and deliberately so: this is the doom-gated "
               "form (bench empty AND `combat.reachable_incoming >= my_hp`) that becomes the SOLE "
               "guard once the filter retires. Two entries on one fact is the double-counting rule "
               "being paid down on a schedule, not an exception to it — which is why the filter is "
               "typed provisional and this one is not.",
    ),
    SoundRule(
        id="information-before-commitment",
        entry="`_finish_turn_last` — the information-before-commitment boundary",
        type=STRUCTURAL,
        fact="within-turn action ordering",
        reason="An informative, reversible action weakly dominates a committing one: the engine "
               "re-presents the menu after every non-ending action, so taking the dig first cannot "
               "cost the commitment but can improve it. NOT derivable by the planner — both orders "
               "reach the same end state, so no function of that state separates them "
               "(ADR-0095 decision 3). Narrowed from 'the sequencing tiers': the old line was "
               "unfalsifiable, and was in fact FALSE in the free band, where tier 0 conflated "
               "'free' with 'informative'.",
    ),
    SoundRule(
        id="doom-ceiling-fail-direction",
        entry="worst-case doom ceiling as the survival fail-direction",
        type=STRUCTURAL,
        fact="which way an unknown survival read errs",
        reason="A fail-direction policy, not an estimate: when the clock cannot answer, assume the "
               "worse outcome for me. Becomes a POLICY PARAMETER after T1's fold of the legacy doom "
               "pair, which is a change of shape, not of doctrine.",
    ),
    SoundRule(
        id="declaration-rungs",
        entry="opening / mulligan declaration rungs",
        type=STRUCTURAL,
        fact="the opening declaration",
        reason="Deck-DECLARED, never tuned — the deck's own statement of what it opens on. A "
               "declaration is data the deck author wrote, so there is no weight here to delete.",
    ),
    SoundRule(
        id="lethal-solver-preemption",
        entry="Lethal-Solver preemption above the planner",
        type=STRUCTURAL,
        fact="a verified winning line",
        reason="Sound win detection outranks every heuristic by construction: a confirmed win ends "
               "the game, so no positional value can be worth more. It sits ABOVE the composer for "
               "the same reason it sits above the Turn Goal today.",
    ),
    SoundRule(
        id="firing-equation-constants",
        entry="authored constants inside firing equations (ROLE_TIER / TAG_TIER, readiness-leaf "
              "values, planner sub-prize constants, confidence seeds, the refresh swing's "
              "opponent-side STRIP / GIFT / FRESH per-card prices, the free-Item hold floor "
              "`hold_value.ITEM_HOLD_FLOOR` and its seam rate `currency.ITEM_HOLD_WORTH_RATE`, and "
              "the gust-target seam's `currency.GUST_TARGET_BAND`) — and, "
               "since POC-T3, the `state_value` scale anchors and runaway guards: `_READINESS_W`, "
               "`_SATURATED`, `_ROLE_FLOOR`, `_PROXIMITY_W`, `_DEPLOY_PRIZE_BAND`, "
               "`_BENCH_SLOT_PRICE` and the four family caps. `_THREAT_CAP` is in that list for a "
               "second reason as of 2026-08-02 (Issue #262): it is the one family cap with NO scale "
               "anchor in front of it, so it binds on 100% of inputs and `threat` answers one bit "
               "rather than grading. The anchor that fixes it is derived rather than authored and "
               "would therefore ADD no scaffold debt, but applying it measured -5/+0 on the "
               "Discrimination Gate, so it is parked with the rest of this entry's queue and "
               "recorded as a strict-xfail TARGET instead",
        type=AUTHORED_SCAFFOLD,
        fact="magnitudes inside equations that already fire correctly",
        reason="Tolerated for the POC: these sit INSIDE equations whose shape is right, so they "
               "scale an answer rather than decide one. Deleting them would remove working "
               "behaviour to no benefit before there is anything fitted to replace them.",
        reconciliation="Queued wholesale for the post-POC learning phases (Issues #146–#148). Not "
                       "individually reconciled — the queue is the commitment. ONE member carries a "
                       "named PREREQUISITE besides the queue: the refresh swing's `_REFRESH_OPPONENT_HAND_STRIP` (4) "
                       "/ `_REFRESH_OPPONENT_HAND_GIFT` (8) (ADR-0101, Issue #261 item 2b, discharging Issue #222). "
                       "Grading them is designed (hand-disruption-grill-spec.md design A) and PARKED "
                       "on measurement — 59.4% of an opponent's representative build prices "
                       "`role_value` 0 today, and the missing 59% is exactly their attackers and "
                       "wincons, so a derived GIFT would be biased in ADR-0060's CRITICAL direction. "
                       "They retire when gusting-keepcost-design.md §2's shared opponent role sheet "
                       "exists, not before. A SECOND member joined 2026-08-02 (Issue #261 item 2f) "
                       "and it is a net REDUCTION, not an addition: `_DENIAL_ITEM_COST = 10` was an "
                       "authored constant hard-gated to one card class, and `hold_value.ITEM_HOLD_FLOOR` "
                       "is the same number generalised onto the Needs assignment as a FLOOR, with the "
                       "~1.0 worth<->damage rate it silently implied now named as "
                       "`currency.ITEM_HOLD_WORTH_RATE` beside `DEPLOY_BAND`. Both carry the deploy "
                       "band's reconciliation debt: if a general Worth Damage Rate is derived (the "
                       "`poc-worth-prize-rate` entry is the candidate), they are checked against it, "
                       "and a disagreement is evidence about ONE of the two. A THIRD member joined "
                       "2026-08-02 (Issue #313 item 2g) and it adds no NUMBER at all: "
                       "`currency.GUST_TARGET_BAND` IS `TAG_TIER['gust']`, already listed above, read "
                       "at import as the ceiling of a ratio whose divisor "
                       "(`needs.TARGET_VALUE_CEILING`) is derived from the card set's own largest "
                       "prize value and the existing survival cap. Its rate "
                       "(`GUST_TARGET_WORTH_RATE`, ~2.564 worth per prize-equivalent) is the "
                       "quotient, not an authored figure — but it is listed here because its "
                       "reconciliation is the sharpest of the three: composing the two SHIPPED legs "
                       "(`PRIZE_DAMAGE_RATE` 100 / `ITEM_HOLD_WORTH_RATE` 1.0) says ~100 worth per "
                       "prize, a ~39x disagreement recorded in `currency.py` rather than smoothed "
                       "over. `POC_WORTH_PRIZE_RATE` SETTLED it (POC-T3, 2026-08-02) and settled it "
                       "by REFERENT rather than by moving either number: the gust rate converts a "
                       "prize-equivalent INTO Worth to rank a slot inside a Worth-denominated DP, "
                       "while the scaffold converts a HELD CARD's Worth into prizes to price "
                       "spending it — same pair, opposite directions, different referents. The "
                       "reductio is that at the gust seam's rate a held `ROLE_TIER['win_condition']` "
                       "prices at 11.7 prizes, nearly twice the six that END the match. So Worth is "
                       "an ORDINAL priority scale inside an assignment, not a quantity globally "
                       "exchangeable with prizes, and no general rate is owed. "
                       "The T3 additions are "
                       "NOT free inventions: each is anchored to the constant it replaces at the "
                       "same band (old Issue #145's seeding method 1, the currency-zone rule) — "
                       "`_READINESS_W` to `planner._READINESS_ATTACK_W`, `_SATURATED` to "
                       "`planner._READINESS_SATURATED`, `_ROLE_FLOOR` to the bottom rung of "
                       "`ROLE_TIER`, `_PROXIMITY_W` to `needs._PHASE_PRIZE_W`, `_DEPLOY_PRIZE_BAND` "
                       "and `_BENCH_SLOT_PRICE` to `currency.DEPLOY_BAND`. "
                       "`test_state_value.py` asserts the first two against the planner directly, "
                       "because that import would be a cycle in the source.",
    ),
    SoundRule(
        id="poc-worth-prize-rate",
        entry="`POC_WORTH_PRIZE_RATE` (module-local to `state_value`)",
        type=AUTHORED_SCAFFOLD,
        fact="the Worth -> prize exchange rate",
        reason="Needed because differencing makes every card-spending play cross the scale boundary: "
               "the card is in `hand` (Worth) before and on the board (prizes) after, so the Worth "
               "does not cancel. Pricing the hand at zero instead was rejected — it makes every free "
               "Item strictly worth playing.",
        reconciliation="AUTHORED 1/120 prizes per Worth point, stated against every rate "
                       "`currency.py` catalogues rather than dropped in beside them (ADR-0097 "
                       "decision 1). The catalogue grew to FOUR while T3 was in flight, so all four "
                       "are reconciled: worth<->damage deploy 0.83 (the ANCHOR — 25/30 over "
                       "PRIZE_DAMAGE_RATE IS this constant), trainer `ITEM_HOLD_WORTH_RATE` 1.0 "
                       "(within 20%; it replaced the deleted `_DENIAL_ITEM_COST` this note used to "
                       "cite), energy ~6.7 (DISAGREES ~8x, a real referent difference — a card in "
                       "hand vs fuel already attached); and on the SAME prize<->worth pair, "
                       "`GUST_TARGET_WORTH_RATE` 2.564 worth/prize against this constant's 120, "
                       "~47x. That last one is SETTLED by referent, not split — see the "
                       "`firing-equation-constants` entry above and the reductio it records. "
                       "Composing the two shipped legs (PRIZE_DAMAGE_RATE / ITEM_HOLD_WORTH_RATE) "
                       "gives a second same-pair reading, 100 worth per prize, which this 120 sits "
                       "inside 20% of — so two independent readings agree and one is explained. "
                       "Retires when a post-POC fit against ruled spend-vs-hold frames converges. "
                       "`common/currency.py` and `test_currency.py` stay untouched — including its "
                       "now-stale forward pointer saying this constant 'is None and T3 owns "
                       "authoring it', which is left for its owning track to correct rather than "
                       "edited here.",
    ),
    SoundRule(
        id="apply-seam-coverage-floors",
        entry="apply-seam per-option-kind coverage floors",
        type=AUTHORED_SCAFFOLD,
        fact="how much parity evidence an option kind needs before it is trusted",
        reason="The floors turn a thin parity fixture into a BUILD FAILURE rather than a silent gap "
               "— the exposure accepted when the engine route was declined (ADR-0098 "
               "decision 3). A floor is authored because there is no principled derivation of 'enough "
               "evidence' yet.",
        reconciliation="Reviewed post-POC as the option-kind table grows; a floor that never fails "
                       "is as uninformative as one that always does.",
    ),
    # ── composed-into-the-leaf (added 2026-08-01 by the Issue #263 ordering ruling) ────────────────
    # The composer's ordering heuristic became uniform 1-ply differencing, so these four stop being
    # DECIDERS for any option the enumerator covers. They are listed here — not deleted, not
    # whitelisted as rules — so that losing decider status cannot be read as licence to delete the
    # math. Each names the term family that absorbs it (Issue #262 composes those families).
    SoundRule(
        id="attach-value-composed",
        entry="`attach_value` (ADR-0069)",
        type=COMPOSED_INTO_THE_LEAF,
        fact="the marginal value of attaching an Energy",
        reason="Its axes-sum shape is ratified and stays ratified; what changes is its ROLE. Under "
               "1-ply differencing the ordering comes from `state_value(after) − state_value(before)` "
               "for every option uniformly, so a per-seam equation that also ordered would be a "
               "second opinion on the same question. The math survives as leaf internals, and "
               "optionally as a pruning approximation.",
        composed_into="readiness",
    ),
    SoundRule(
        id="evolve-value-composed",
        entry="`evolve_value` (ADR-0070)",
        type=COMPOSED_INTO_THE_LEAF,
        fact="the marginal value of evolving a body",
        reason="Same role change. Its body-substituted delta-in-damage IS how the readiness family "
               "prices a body swap, so deleting it would delete the only worked derivation of that "
               "delta and leave T2 re-deriving it from nothing.",
        composed_into="readiness",
    ),
    SoundRule(
        id="promote-retreat-value-composed",
        # Cited by ISSUE as well as number on purpose: `docs/adr/README.md`'s numbering log says
        # outright that "the number is not the identifier". This one proves it — ADR-0073 was
        # claimed by TWO merged ADRs for five days, and PR #267 renumbered the promote/retreat
        # half to 0100. Anything citing it as "ADR-0073" now points at the fetch ADR instead.
        entry="`promote_retreat_value` (Issue #141; ADR-0100, was ADR-0073 before PR #267)",
        type=COMPOSED_INTO_THE_LEAF,
        fact="the marginal value of changing who is Active",
        reason="Same role change. The sub-lethal residual it computes is a survival/threat reading "
               "the leaf needs whether or not anything still orders by it.",
        composed_into="survival",
    ),
    SoundRule(
        id="deploy-value-composed",
        entry="`deploy_value` (ADR-0086)",
        type=COMPOSED_INTO_THE_LEAF,
        fact="the marginal value of putting a body into play",
        reason="Same role change, and the one with the sharpest deletion hazard: ADR-0096 already "
               "deleted `keep-a-bench` off this list, so a reader could reasonably conclude the "
               "whole Bench-pricing story was purged. It was not — the bench slot priced as a "
               "scarce resource is exactly this equation, and it becomes development-family math.",
        composed_into="development",
    ),
)

#: id -> rule.
BY_ID = {r.id: r for r in WHITELIST}


def validate(rules: Sequence[SoundRule] = WHITELIST) -> list[str]:
    """Every way an entry fails the typing discipline, as readable problems. Empty is the contract.

    The T0 registry REJECTS an untyped entry (ADR-0099 decision 1) — this is that rejection,
    executable. It is deliberately a list of problems rather than a raise: an author fixing a
    whitelist wants every complaint at once, not the first one."""
    problems: list[str] = []
    seen: set[str] = set()
    for r in rules:
        if r.id in seen:
            problems.append(f"{r.id}: duplicate id")
        seen.add(r.id)
        if r.type not in TYPES:
            problems.append(f"{r.id}: type {r.type!r} is not one of {sorted(TYPES)}")
        if not r.fact.strip():
            problems.append(f"{r.id}: names no board fact — cannot be checked for double-counting")
        if not r.reason.strip():
            problems.append(f"{r.id}: gives no reason for surviving the purge")
        if r.type == PROVISIONAL and not r.retirement_test.strip():
            problems.append(f"{r.id}: provisional entries MUST carry a dated retirement test")
        if r.type == AUTHORED_SCAFFOLD and not r.reconciliation.strip():
            problems.append(f"{r.id}: authored-scaffold entries MUST carry a reconciliation note")
        if r.type == COMPOSED_INTO_THE_LEAF and not r.composed_into.strip():
            problems.append(f"{r.id}: composed-into-the-leaf entries MUST name the state_value term "
                            f"family that absorbs them — an unnamed destination is how a "
                            f"no-longer-deciding equation gets deleted by the next track")
        if r.type != COMPOSED_INTO_THE_LEAF and r.composed_into.strip():
            problems.append(f"{r.id}: only composed-into-the-leaf entries name a destination term "
                            f"family — this one still decides something")
        if r.type == STRUCTURAL and (r.retirement_test.strip() or r.reconciliation.strip()):
            problems.append(f"{r.id}: structural entries are permanent — a retirement test or "
                            f"reconciliation here means the type is wrong")
    return problems


#: The ONE fact the whitelist deliberately guards twice, and the schedule that resolves it:
#: `empty-bench-filter` (provisional) retires INTO `predicted-loss` (structural) once T1 proves the
#: CombatMath read. Declared as data so `undeclared_double_guarding` can exempt exactly this pair and
#: nothing else — an exemption written as a code comment would grow silently.
#:
#: Note the two entries share one ``fact`` string ON PURPOSE. Distinguishing them by tacking "(the
#: CombatMath-gated reading)" onto one would make the coverage map read as two separate facts, and
#: the double-guard detector would pass VACUOUSLY — which is what it did until this was fixed. The
#: differing READING belongs in ``reason``; the fact is the same fact.
SCHEDULED_PAIRS: tuple[tuple[str, ...], ...] = (
    ("empty-bench-filter", "predicted-loss"),
)


def deciders(rules: Sequence[SoundRule] = WHITELIST) -> tuple[SoundRule, ...]:
    """The entries that still DECIDE something at runtime — everything except
    :data:`COMPOSED_INTO_THE_LEAF`. The population the one-guard-per-fact rule is about."""
    return tuple(r for r in rules if r.type in DECIDER_TYPES)


def composed(rules: Sequence[SoundRule] = WHITELIST) -> tuple[SoundRule, ...]:
    """The per-seam equations that survive as `state_value` term-family math rather than as rules.
    Issue #264's disposition table reads this population under the same label."""
    return tuple(r for r in rules if r.type == COMPOSED_INTO_THE_LEAF)


def facts_guarded() -> dict:
    """``{fact: [rule ids]}`` — the DECIDER half of the whitelist read as a coverage map.

    Composed entries are excluded: they price a fact, they do not guard it, and folding the two roles
    into one map would report a decider and an equation as a double guard on the same fact."""
    out: dict = {}
    for r in deciders():
        out.setdefault(r.fact, []).append(r.id)
    return out


def undeclared_double_guarding() -> dict:
    """``{fact: [rule ids]}`` for every fact guarded by more than one DECIDER that is NOT a declared
    :data:`SCHEDULED_PAIRS`. Empty is the contract.

    A fact with two entries is not automatically wrong, but it must be DELIBERATE and said out loud.
    What the flat prose list allowed — and this does not — is a second entry nobody noticed, which
    is how one board fact came to carry three guards at once."""
    declared = {frozenset(p) for p in SCHEDULED_PAIRS}
    return {fact: ids for fact, ids in facts_guarded().items()
            if len(ids) > 1 and frozenset(ids) not in declared}


__all__: Sequence[str] = (
    "STRUCTURAL", "PROVISIONAL", "AUTHORED_SCAFFOLD", "COMPOSED_INTO_THE_LEAF", "TYPES",
    "DECIDER_TYPES", "SoundRule", "WHITELIST", "BY_ID", "SCHEDULED_PAIRS", "validate", "deciders",
    "composed", "facts_guarded", "undeclared_double_guarding",
)
